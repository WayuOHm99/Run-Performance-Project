// `demo:verify:consent` — mechanically proves acceptance criteria 2, 4, 5, and 6
// against the real local stack.
//
// This is a **destructive verification**: it creates a synthetic check-in and an
// explicit grant, which the baseline must not contain. It therefore brackets
// itself with a full reset at both ends, so the environment it leaves behind is
// the approved decision-9 baseline — zero grants, zero check-ins — regardless of
// how it exits.
//
// It is not a substitute for the Product Owner walking the story in the real UI.
// It proves the database enforces consent; the UI walk proves the product does.
// In particular it says nothing about acceptance criterion 3 — that the athlete
// *lands* in the athlete area and the coach in the coach area — which only a
// real Web or Android run can show.
//
// The whole workflow holds the destructive-workflow lock, including its restore.
// A `demo:reset` landing between the grant and the restore would leave the
// grant and the synthetic check-in behind, which is the decision-9 violation the
// bracketing exists to prevent.
//
// **Every assertion is a row count.** No health value, id, email, token, or row
// is read into a variable that is printed. `countRows` requests `select=id`, so
// the RPE, feeling, and pain columns never enter this process at all.

import { randomInt } from "node:crypto";

import { callSharingRpc, countRows, insertCheckIn, signIn } from "./api.mjs";
import { ATHLETE_EMAIL, COACH_EMAIL, DEMO_TEAM_ID } from "./accounts.mjs";
import { withDemoLock } from "./lock.mjs";
import { runReset } from "./reset.mjs";

// The synthetic check-in is **generated at run time, never written down**.
//
// A fixed `rpe: 5, overall_feeling: 3` in this file would be an exact health
// value living permanently in a committed artifact, which acceptance criterion 8
// forbids regardless of how synthetic it is. What is committed here is the
// *domain* the schema already declares in
// `20260728140000_daily_check_ins_rls.sql` — RPE 0–10, feeling 1–5, pain none or
// present — and not the value any run actually used.
//
// The generated values are never printed, never asserted on, and never read
// back: every assertion below is a row count, and `countRows` requests
// `select=id`, so no health column returns to this process at all. The row
// itself is deleted by the restoring reset a few seconds later, and it belongs
// to an account that cannot receive email.
const PAIN_STATUS_DOMAIN = Object.freeze(["none", "present"]);

function synthesizeCheckIn() {
  return {
    rpe: randomInt(0, 11),
    overallFeeling: randomInt(1, 6),
    painStatus: PAIN_STATUS_DOMAIN[randomInt(0, PAIN_STATUS_DOMAIN.length)],
  };
}

const results = [];

function check(label, actual, expected) {
  const passed = actual === expected;
  results.push({ label, actual, expected, passed });
  console.log(
    `  ${passed ? "pass" : "FAIL"}  ${label.padEnd(52)} expected ${expected}, got ${actual}`,
  );
}

function today() {
  return new Date().toISOString().slice(0, 10);
}

async function main() {
  console.log("Consent verification against the LOCAL stack only.\n");
  console.log("Rebuilding the baseline first.\n");

  const { credentials, password } = await runReset({
    log: (message) => console.log(`  ${message}`),
  });

  const { apiUrl, publishableKey } = credentials;
  const base = { apiUrl, publishableKey };

  console.log("\nSigning both accounts in through real local Auth.\n");

  // Acceptance criterion 2. A thrown error here fails the run; a success is
  // reported as a boolean and the returned session is never printed.
  const athlete = await signIn({ ...base, email: ATHLETE_EMAIL, password });
  const coach = await signIn({ ...base, email: COACH_EMAIL, password });

  check("athlete authenticates through real local Auth", true, true);
  check("coach authenticates through real local Auth", true, true);

  // Role source, acceptance criterion 3. Read from team_memberships under RLS,
  // which is the only place the app reads it from either.
  check(
    "athlete holds exactly one active athlete membership",
    await countRows({
      ...base,
      session: athlete,
      table: "team_memberships",
      filters: { status: "eq.active", role: "eq.athlete" },
    }),
    1,
  );
  check(
    "coach holds exactly one active coach membership",
    await countRows({
      ...base,
      session: coach,
      table: "team_memberships",
      filters: { status: "eq.active", role: "eq.coach" },
    }),
    1,
  );

  console.log("\nBefore consent.\n");

  await insertCheckIn({
    ...base,
    session: athlete,
    checkInDate: today(),
    ...synthesizeCheckIn(),
  });

  check(
    "athlete reads their own check-in",
    await countRows({ ...base, session: athlete, table: "daily_check_ins" }),
    1,
  );

  // Acceptance criterion 4. This is the one that matters most: membership alone
  // must never be enough.
  check(
    "coach CANNOT read the check-in before consent",
    await countRows({ ...base, session: coach, table: "daily_check_ins" }),
    0,
  );

  console.log("\nAfter an explicit athlete grant.\n");

  await callSharingRpc({
    ...base,
    session: athlete,
    fn: "grant_team_data_sharing",
    teamId: DEMO_TEAM_ID,
    dataCategory: "check_in",
  });

  // Acceptance criterion 5.
  check(
    "coach reads the check-in after the grant",
    await countRows({ ...base, session: coach, table: "daily_check_ins" }),
    1,
  );

  console.log("\nAfter the athlete revokes.\n");

  await callSharingRpc({
    ...base,
    session: athlete,
    fn: "revoke_team_data_sharing",
    teamId: DEMO_TEAM_ID,
    dataCategory: "check_in",
  });

  // Acceptance criterion 6, both halves. The coach loses access on the very next
  // query — no re-authentication, no token refresh — because authorization lives
  // in the database and not in the token.
  check(
    "coach loses access on the next query",
    await countRows({ ...base, session: coach, table: "daily_check_ins" }),
    0,
  );
  check(
    "athlete keeps self-access after revoke",
    await countRows({ ...base, session: athlete, table: "daily_check_ins" }),
    1,
  );

  const failed = results.filter((result) => !result.passed);

  console.log("\nRestoring the decision-9 baseline (0 grants, 0 check-ins).\n");
  const restored = await runReset({
    log: (message) => console.log(`  ${message}`),
  });

  console.log(
    `\n  baseline restored; credentials at ${restored.credentialsPath}`,
  );
  console.log(
    `\n${results.length - failed.length}/${results.length} checks passed.`,
  );

  if (failed.length > 0) {
    throw new Error(`${failed.length} consent check(s) failed.`);
  }
}

// The failure path runs **inside** the lock claim, so the restoring reset cannot
// be overtaken by another destructive command between the failure and the
// restore. `runReset` takes the lock reentrantly, so it is not blocked by the
// claim this workflow already holds.
async function verifyConsent() {
  try {
    await main();
  } catch (error) {
    console.error(`\ndemo:verify:consent failed — ${error.message}`);

    // Best effort: never leave a grant or a synthetic check-in behind, even on a
    // failure part-way through.
    try {
      await runReset();
      console.error("The baseline was restored despite the failure.");
    } catch {
      console.error(
        "The baseline could NOT be restored automatically. Run `corepack pnpm demo:reset`.",
      );
    }

    process.exitCode = 1;
  }
}

// A failure to take the lock is the one case with nothing to restore: this
// process never touched the database.
withDemoLock("demo:verify:consent", verifyConsent).catch((error) => {
  console.error(`\ndemo:verify:consent failed — ${error.message}`);
  process.exitCode = 1;
});
