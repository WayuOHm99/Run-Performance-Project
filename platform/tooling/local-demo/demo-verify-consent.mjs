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
//
// **Every assertion is a row count.** No health value, id, email, token, or row
// is read into a variable that is printed. `countRows` requests `select=id`, so
// the RPE, feeling, and pain columns never enter this process at all.

import { callSharingRpc, countRows, insertCheckIn, signIn } from "./api.mjs";
import { ATHLETE_EMAIL, COACH_EMAIL, DEMO_TEAM_ID } from "./accounts.mjs";
import { runReset } from "./reset.mjs";

// Synthetic, and deliberately unremarkable. These are the only health values in
// the whole task, they exist for a few seconds, and they belong to an account
// that cannot receive email.
const SYNTHETIC_CHECK_IN = {
  rpe: 5,
  overallFeeling: 3,
  painStatus: "none",
};

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
    ...SYNTHETIC_CHECK_IN,
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

main().catch(async (error) => {
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
});
