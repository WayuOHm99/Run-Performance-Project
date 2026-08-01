// Baseline verification, restricted to scalar counts by construction.
//
// The query below selects only `count(*)` aggregates. It returns no id, no
// email, no display name, no timestamp, and — critically — no column of
// `daily_check_ins` other than how many rows exist. Verifying the baseline must
// never become a way to read protected health data, so the check counts the
// check-in table and never looks inside it.
//
// `parseBaselineRow` and `compareBaseline` are pure so the leak-shape can be
// tested without a database.

import { setTimeout as delay } from "node:timers/promises";

import { EXPECTED_BASELINE } from "./accounts.mjs";
import { queryLocalScalars } from "./supabase-cli.mjs";

// `retryable` is a fixed boolean set at the throw site from the shape of the
// failure, never from anything the CLI returned. Nothing derived from the
// response is attached to the error, here or anywhere below.
export class DemoBaselineError extends Error {
  name = "DemoBaselineError";
  retryable;

  constructor(message, { retryable = false } = {}) {
    super(message);
    this.retryable = retryable;
  }
}

// Round 9 replaced a fixed attempt count with a **wall-clock deadline plus an
// evidence check**. Rounds 5 through 8 all made the same mistake in different
// sizes: they picked a number, and the Product Owner's transient outlasted it.
// A bigger number is the same mistake again, so the termination condition is no
// longer a count.
//
//   * `BASELINE_DEADLINE_MS` — the outer bound. Nothing retries past it.
//   * `BASELINE_MAX_ATTEMPTS` — a second, independent ceiling, so a pathological
//     zero-cost query cannot spin inside the deadline.
//
// Round 10 removed the third mechanism, a "quick allowance" after which a
// healthy control query could end the retry early. See finding M1 on
// `readBaseline`: that let an unproven assumption declare a transient
// permanent.
//
// ## The real bound, stated honestly
//
// Every attempt's CLI child now carries a timeout capped to whatever is left of
// the deadline, so an in-flight query cannot overrun the budget. The worst case
// a caller must allow for is:
//
//   BASELINE_DEADLINE_MS                 retrying and waiting        60s
//   + 2 × SUBPROCESS_KILL_GRACE_MS       terminating a stuck child    4s
//   + BASELINE_DIAGNOSIS_TIMEOUT_MS      the one diagnostic query     5s
//   + 2 × SUBPROCESS_KILL_GRACE_MS       terminating that child too   4s
//   ────────────────────────────────────────────────────────────────────
//   ≈ 73s
//
// The grace terms are the SIGTERM → SIGKILL escalation in `subprocess.mjs`, and
// they are only paid if a child actually hangs. A healthy failure — one where
// every query answers promptly and the result is simply wrong — costs the
// deadline plus one diagnostic query, so about 65s.
export const BASELINE_MAX_ATTEMPTS = 30;
export const BASELINE_RETRY_DELAY_MS = 1000;
export const BASELINE_DEADLINE_MS = 60_000;
export const BASELINE_DIAGNOSIS_TIMEOUT_MS = 5000;

// The canary. Deliberately the most trivial statement that still exercises the
// whole path this module depends on — the pinned CLI, `--local`, `-o json`, the
// subprocess capture, and the JSON envelope — while reading **nothing** from the
// database. It names no table, no schema, and no column, so it cannot return a
// count, an identifier, or a health value even in principle.
export const CANARY_SQL = "select 1::int as ok";

// Ceilings, not settings — deliberately the production values themselves. The
// seams exist for the tests, so a test may ask for a *smaller* budget to stay
// fast, but nothing can ask for a larger one. "Bounded" has to mean the same
// thing in a test as it does in `demo:reset`.
function boundedInteger(value, fallback, ceiling) {
  return Number.isInteger(value) && value >= 1 && value <= ceiling
    ? value
    : fallback;
}

function boundedMs(value, fallback, ceiling) {
  return Number.isFinite(value) && value >= 0 && value <= ceiling
    ? value
    : fallback;
}

// One row, all integers. `named_profiles` counts profiles that carry a usable
// display name, because a null one would make the coach surface fail closed and
// the demo look broken for a reason that has nothing to do with consent.
export const BASELINE_SQL = [
  "select",
  "  (select count(*) from auth.users)::int as auth_users,",
  "  (select count(*) from auth.users where email like '%@example.test')::int as example_test_users,",
  "  (select count(*) from public.profiles)::int as profiles,",
  "  (select count(*) from public.profiles where btrim(coalesce(display_name, '')) <> '')::int as named_profiles,",
  "  (select count(*) from public.teams)::int as teams,",
  "  (select count(*) from public.team_memberships where status = 'active')::int as active_memberships,",
  "  (select count(*) from public.team_memberships where status = 'active' and role = 'athlete')::int as active_athlete_memberships,",
  "  (select count(*) from public.team_memberships where status = 'active' and role = 'coach')::int as active_coach_memberships,",
  "  (select count(*) from public.sharing_grants)::int as sharing_grants,",
  "  (select count(*) from public.daily_check_ins)::int as daily_check_ins",
].join("\n");

// The CLI wraps rows in a document that also carries a `boundary` marker and a
// prose `warning`. Only `rows[0]` is read, and only the expected integer keys are
// copied out of it.
export function parseBaselineRow(stdout) {
  let document;

  try {
    document = JSON.parse(stdout);
  } catch {
    throw new DemoBaselineError("Could not read the baseline query result.");
  }

  // Round 9 accepts a **bare array** as well as the `{ boundary, rows, warning }`
  // envelope. The pinned CLI emitted the envelope in every one of the 80+
  // structural probes round 9 ran, so this is defensive rather than a fix for an
  // observed shape: `db query -o json` has no versioned output contract, and a
  // row set is a row set whether or not it arrives wrapped. It costs one
  // `Array.isArray` and removes a whole class of contract-drift failure.
  const rows = Array.isArray(document) ? document : document?.rows;

  // Two structural failures, kept as **separate messages** but both retryable.
  //
  // Round 6 made this branch fail immediately, reasoning that an unready
  // database produces a non-zero exit and therefore a missing row set had to be
  // a permanent contract violation. **Round 8 removes that reasoning**: the
  // Product Owner hit this exact message on a `demo:reset`, again on an
  // immediate `demo:verify`, and again on a second `demo:reset` — after which a
  // structural probe showed the normal envelope with one row and everything
  // passed. A condition that clears on its own is transient, whatever my
  // measurements failed to provoke.
  //
  // The messages stay distinct on purpose. They are the only thing that will
  // tell a future reader which shape actually occurred, and round 6's one real
  // contribution was creating that distinction.
  if (!Array.isArray(rows)) {
    throw new DemoBaselineError("The baseline query returned no row set.", {
      retryable: true,
    });
  }

  // A row set that exists but is the wrong size. Retryable for the same reason
  // and on the same budget; see `readBaseline`.
  if (rows.length !== 1) {
    throw new DemoBaselineError(
      "The baseline query did not return exactly one row.",
      { retryable: true },
    );
  }

  const row = rows[0];
  const counts = {};

  for (const key of Object.keys(EXPECTED_BASELINE)) {
    const value = row?.[key];

    if (!Number.isInteger(value)) {
      throw new DemoBaselineError(
        "The baseline query returned a non-integer count.",
      );
    }

    counts[key] = value;
  }

  return Object.freeze(counts);
}

// Returns the mismatches rather than throwing, so the caller can report every
// wrong count at once instead of one per run.
export function compareBaseline(counts, expected = EXPECTED_BASELINE) {
  const mismatches = [];

  for (const [key, want] of Object.entries(expected)) {
    const got = counts[key];

    if (got !== want) {
      mismatches.push({ key, expected: want, actual: got });
    }
  }

  return mismatches;
}

// Safe to print: key names and integers only.
export function formatBaseline(counts) {
  return Object.entries(counts)
    .map(([key, value]) => `  ${key.padEnd(28)} ${value}`)
    .join("\n");
}

// Bounded retry over the two **structural** readiness conditions: a row set
// that is missing or not an array, and a row set that is an array of the wrong
// length. Ten attempts, nine 1000ms waits.
//
// The SQL is ten scalar subqueries with no `from` and no predicate on the outer
// select, so exactly one row is the only result the database can return.
// Neither structural shape is therefore a report about the demo's contents —
// they are reports that the read did not come back intact.
//
// Why retrying is safe: the query is a read-only aggregate with no side effect,
// so re-running it changes nothing. It cannot mask a wrong baseline, because a
// wrong baseline parses fine — `compareBaseline` is a separate step that this
// function never reaches into and never re-runs.
//
// ## Why round 8 exists, and what it corrects
//
// Round 6 measured a local stack across two `stop → cold start → db reset`
// cycles and found that an unready database fails with a **non-zero exit**,
// never with a malformed envelope. From that it concluded a missing row set had
// to be a permanent CLI-contract violation, and made it fail immediately.
//
// **The Product Owner then hit it, three times in a row.** `demo:reset` failed
// with "returned no row set"; an immediate `demo:verify` failed the same way; a
// second `demo:reset` failed the same way again. A structural probe afterwards
// returned the normal envelope with `rows` an array of length 1, `demo:verify`
// passed, and a later reset completed and wrote its credential file.
//
// A condition that clears on its own is transient. The round 6 measurement was
// not wrong about what it saw — it was wrong to treat "I could not provoke this
// in four container transitions on one machine" as "this cannot happen". An
// absence of reproduction is not evidence of impossibility, and a real failure
// on the Product Owner's machine outranks my inability to reproduce it.
//
// So both structural shapes are retryable, on one shared budget, with their
// messages kept distinct so a future exhaustion still says which one occurred.
//
// ## Why round 9 exists: ten was also too few
//
// The Product Owner then ran `demo:verify` against the round 8 code and it
// **exhausted all ten attempts** with "returned no row set" — against a database
// that was healthy, unchanged, and which structural probes moments later showed
// returning one row with all ten integer fields. `demo:verify` then passed on
// the same untouched baseline.
//
// That is the fourth round in a row where a number was chosen and the transient
// outlasted it. The lesson is not "pick a bigger number": it is that **an
// attempt count is the wrong termination condition**, because it encodes a guess
// about a duration nobody has measured.
//
// It also exposed a worse problem than the failure itself. A read-only check had
// no way to recover a healthy baseline, and the only remedy on offer was
// `demo:reset` — which destroys and recreates both accounts and rotates the
// credential file, purely because one *read* came back in an unrecognised shape.
// Rebuilding the world to work around a bad read is not a recovery procedure.
//
// ## The mechanism
//
// ## Round 10, finding M1: the control query is a label, not a gate
//
// Round 9 stopped retrying as soon as `select 1::int as ok` came back healthy,
// reasoning that a working CLI path proves a structurally broken
// `BASELINE_SQL` will not recover. **That inference was never proven**, and the
// round 9 handoff said so in its own limitations. If the transient is specific
// to the baseline query rather than to the transport, round 9 would declare it
// permanent after three attempts — turning the exact failure this whole
// sequence is about into a fast, confident, wrong answer.
//
// This is the same error as round 6, one level up: treating "I have no evidence
// for X" as "I have evidence against X". So the control query no longer touches
// control flow. It runs **once, after the loop has already given up**, and its
// only effect is which fixed sentence the error carries.
//
// Termination is therefore driven by two bounds and nothing else:
//
//   1. **`BASELINE_DEADLINE_MS`** — retrying stops when the remaining budget
//      cannot fit another wait plus another attempt. Each attempt's CLI child
//      also carries a timeout capped to the remaining budget, so an in-flight
//      query cannot overrun it.
//   2. **`BASELINE_MAX_ATTEMPTS`** — an independent ceiling.
//
// Whichever binds first, the loop stops and rethrows the last structural
// failure, its message unchanged apart from the appended fixed diagnosis.
//
// A healthy baseline suffering the observed transient therefore stays
// recoverable for the whole minute, whatever the control query says, and
// `demo:verify` stays read-only throughout. **A destructive `demo:reset` is not
// the recovery path for a read-only transient and is not recommended as one.**
//
// **What round 9 did not establish.** The root cause is still unproven. Round 9
// ran 80+ structural probes against the pinned CLI and could not produce the
// failing shape at all: the healthy envelope was byte-stable, a zero-row result
// came back as `rows: []` rather than a missing row set, a statement with no
// result set produced unparseable plain text, concurrent invocations failed with
// a non-zero exit and empty stdout, and the envelope did not vary with the
// environment. The mechanism above is therefore built to be correct **without**
// knowing the cause, which is why it reasons from live evidence at failure time
// rather than from a stored assumption about what the cause is.
//
// Why the other failures are still *not* retried:
//
//   - A **count mismatch** is not a failure of this function at all. It is a
//     real, correct read of a database in the wrong state, and the caller must
//     see it on the first attempt. It is also structurally unreachable from
//     here: a mismatching baseline parses, so it returns rather than throwing.
//   - **Malformed JSON** and a **non-integer count** mean the CLI wrote
//     something that is not a result document, or that a `count(*)::int` came
//     back as a non-integer. Both are consistent with a broken invocation or a
//     changed contract, and neither has ever been observed transiently.
//   - A **subprocess failure** is the shape an unready database takes, but it is
//     equally the shape a genuinely broken one takes, and by the time this runs
//     the reset, two Auth signups, and the fixture have all already succeeded
//     against the same database. Treating it as transient here would hide a real
//     fault.
//
// If any of those three is ever seen to clear on its own, the answer is the same
// as it was here: believe the observation, not the previous round's reasoning.
//
// When the budget is exhausted the last error is rethrown unchanged, so a
// persistent structural failure fails closed with the same fixed sanitized
// message a single attempt would have produced.
// Round 10, finding M2: the canary used to accept **any** non-null singleton
// row, so `{}` or `{ ok: "bad" }` counted as a healthy CLI path. A control query
// whose own contract is not checked is not a control.
//
// The contract is now exact: one row, an `ok` field, an **integer**, equal to
// `1`. `row.ok === 1` rejects `true`, `"1"`, `1.0`-as-string, and every other
// number; `Number.isInteger` rejects `1.5` and `NaN` reaching it by any other
// route. Anything else — missing rows, a non-array row set, zero or two rows, a
// non-object row, an array row, malformed JSON — is unhealthy.
export function canaryResultIsHealthy(stdout) {
  let document;

  try {
    document = JSON.parse(stdout);
  } catch {
    return false;
  }

  const rows = Array.isArray(document) ? document : document?.rows;

  if (!Array.isArray(rows) || rows.length !== 1) {
    return false;
  }

  const row = rows[0];

  if (row === null || typeof row !== "object" || Array.isArray(row)) {
    return false;
  }

  return Number.isInteger(row.ok) && row.ok === 1;
}

// Runs the canary through the same path as the baseline read and answers one
// question: **was the CLI's query path returning a well-formed result at the
// moment the baseline read gave up?**
//
// It never throws — a broken canary is an answer, not an error — and it returns
// nothing but a boolean. Neither the canary's output nor its failure is
// inspected beyond the contract above, so no content can travel from here to a
// caller.
//
// **Round 10, finding M1: this is a diagnostic, not a control.** See
// `readBaseline` for why its result can no longer end a retry.
export async function cliQueryPathLooksHealthy(query, options = {}) {
  try {
    return canaryResultIsHealthy(await query(CANARY_SQL, options));
  } catch {
    return false;
  }
}

// The three fixed sentences the diagnosis can add to an exhaustion message.
// Each is a constant chosen by a boolean; none is derived from any response.
export const BASELINE_DIAGNOSIS_SENTENCE = Object.freeze({
  "cli-query-path-healthy":
    "A trivial control query answered normally, so the local CLI query path itself was working.",
  "cli-query-path-unhealthy":
    "A trivial control query also failed, so the local CLI query path itself was not working.",
  "cli-query-path-unknown": "The control query was not run.",
});

export async function readBaseline({
  query = queryLocalScalars,
  wait = delay,
  now = Date.now,
  maxAttempts = BASELINE_MAX_ATTEMPTS,
  delayMs = BASELINE_RETRY_DELAY_MS,
  deadlineMs = BASELINE_DEADLINE_MS,
  isPathHealthy = cliQueryPathLooksHealthy,
} = {}) {
  // The seams exist for the tests, so they must not be able to remove or exceed
  // the bound they are testing. Anything that is not a positive value inside the
  // production ceiling — including `NaN`, `Infinity`, and 0, which would skip
  // the loop entirely and leave nothing to throw — falls back to the production
  // value.
  const ceiling = boundedInteger(
    maxAttempts,
    BASELINE_MAX_ATTEMPTS,
    BASELINE_MAX_ATTEMPTS,
  );
  const pause = boundedMs(
    delayMs,
    BASELINE_RETRY_DELAY_MS,
    BASELINE_RETRY_DELAY_MS,
  );
  const deadline = boundedMs(
    deadlineMs,
    BASELINE_DEADLINE_MS,
    BASELINE_DEADLINE_MS,
  );

  const startedAt = now();
  const remaining = () => deadline - (now() - startedAt);

  let lastError;

  for (let attempt = 1; attempt <= ceiling; attempt += 1) {
    try {
      // The per-attempt timeout is capped to whatever is left of the deadline,
      // so an in-flight query cannot overrun the overall budget. This is what
      // makes the deadline a real bound rather than a between-awaits check.
      return parseBaselineRow(
        await query(BASELINE_SQL, { timeoutMs: Math.max(1, remaining()) }),
      );
    } catch (error) {
      if (!(error instanceof DemoBaselineError) || error.retryable !== true) {
        throw error;
      }

      lastError = error;

      // Bound one: attempts.
      if (attempt >= ceiling) {
        break;
      }

      // Bound two: wall clock. There must be room for the wait *and* a further
      // attempt, or there is no point starting one.
      if (remaining() <= pause) {
        break;
      }

      await wait(pause);
    }
  }

  throw await annotateWithDiagnosis(lastError, query, isPathHealthy);
}

// Runs the control query **once**, after the retry loop has already finished,
// purely to label the failure. It cannot shorten, extend, or end a retry —
// by the time it runs there is nothing left to end.
//
// This is round 10's correction of finding M1. Round 9 let a healthy control
// query terminate the loop early, on the assumption that a working
// `select 1::int as ok` proves a structurally broken `BASELINE_SQL` will not
// recover. That assumption was never proven — the round 9 handoff admitted as
// much — and acting on it meant a baseline-specific transient could be declared
// permanent after three attempts. It now changes only the wording of the error.
// It gets its own small budget rather than the deadline's leftovers, which are
// normally zero by the time it runs — a diagnosis that never runs is useless.
// That budget is part of the documented overall bound.
async function annotateWithDiagnosis(error, query, isPathHealthy) {
  let diagnosis = "cli-query-path-unknown";

  if (typeof isPathHealthy === "function") {
    diagnosis = (await isPathHealthy(query, {
      timeoutMs: BASELINE_DIAGNOSIS_TIMEOUT_MS,
    }))
      ? "cli-query-path-healthy"
      : "cli-query-path-unhealthy";
  }

  // A fixed enum and a fixed sentence. Both are chosen by a boolean; neither is
  // derived from any response.
  const annotated = new DemoBaselineError(
    `${error.message} ${BASELINE_DIAGNOSIS_SENTENCE[diagnosis]}`,
    { retryable: error.retryable },
  );

  annotated.diagnosis = diagnosis;
  annotated.structuralFailure = error.message;

  return annotated;
}
