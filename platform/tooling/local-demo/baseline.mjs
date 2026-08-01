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
//   * `BASELINE_QUICK_ATTEMPTS` — retried with no questions asked, to absorb a
//     one-off blip cheaply.
//   * After that, every further retry must be **justified** by the canary
//     below: the tooling keeps waiting only while it can show the CLI's query
//     path is itself unhealthy. See `readBaseline`.
//   * `BASELINE_DEADLINE_MS` — the outer bound. Nothing waits past it.
//   * `BASELINE_MAX_ATTEMPTS` — a second, independent ceiling, so a pathological
//     zero-cost query cannot spin inside the deadline.
//
// **The deadline bounds waiting, not total duration.** Each attempt also spawns
// a Supabase CLI process; round 6 and round 9 both measured a single baseline
// query at roughly 1.5–1.7s against a healthy local stack. The deadline is
// checked *between* attempts, so the real worst case is the deadline plus one
// in-flight query, and the wall clock can exceed 60s slightly. No caller sets a
// timeout against it.
export const BASELINE_QUICK_ATTEMPTS = 3;
export const BASELINE_MAX_ATTEMPTS = 30;
export const BASELINE_RETRY_DELAY_MS = 1000;
export const BASELINE_DEADLINE_MS = 60_000;

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
// Termination is now driven by evidence, with two independent outer bounds:
//
//   1. **A short no-questions-asked allowance** (`BASELINE_QUICK_ATTEMPTS`)
//      absorbs a one-off blip without paying for a diagnosis.
//   2. **After that, every further retry has to be earned.** Before waiting
//      again, the tooling runs `CANARY_SQL` through the *same* CLI path. The
//      canary reads nothing from the database — it is `select 1::int as ok` —
//      so it isolates the transport from the query.
//
//      - Canary comes back as a clean one-row result → **the CLI path is
//        provably healthy**, so a structurally broken baseline read is not a
//        transport blip and will not fix itself. Stop immediately and fail
//        closed. Retrying here would only burn the deadline before reporting
//        the same thing.
//      - Canary is also broken, or fails → the path itself is unhealthy. That is
//        positive evidence the condition is transient, so keep waiting.
//
//   3. **`BASELINE_DEADLINE_MS`** ends it regardless, and
//      **`BASELINE_MAX_ATTEMPTS`** bounds it a second way. Whichever binds
//      first, the loop stops and rethrows the last structural error unchanged.
//
// So a healthy baseline no longer needs a destructive reset to be re-read: the
// tooling waits out a genuinely unhealthy transport for up to a minute, and
// `demo:verify` stays read-only throughout.
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
// Runs the canary through the same path as the baseline read and answers one
// question: **is the CLI's query path returning well-formed single-row results
// right now?**
//
// It never throws — a broken canary is an answer, not an error — and it returns
// nothing but a boolean. Neither the canary's output nor its failure is
// inspected beyond its shape, so no content can travel from here to a caller.
export async function cliQueryPathLooksHealthy(query) {
  try {
    const document = JSON.parse(await query(CANARY_SQL));
    const rows = Array.isArray(document) ? document : document?.rows;

    return Array.isArray(rows) && rows.length === 1 && rows[0] !== null;
  } catch {
    return false;
  }
}

export async function readBaseline({
  query = queryLocalScalars,
  wait = delay,
  now = Date.now,
  quickAttempts = BASELINE_QUICK_ATTEMPTS,
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
  const quick = Math.min(
    boundedInteger(quickAttempts, BASELINE_QUICK_ATTEMPTS, ceiling),
    ceiling,
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
  let lastError;

  for (let attempt = 1; attempt <= ceiling; attempt += 1) {
    try {
      return parseBaselineRow(await query(BASELINE_SQL));
    } catch (error) {
      if (!(error instanceof DemoBaselineError) || error.retryable !== true) {
        throw error;
      }

      lastError = error;

      // Ceiling one: attempts.
      if (attempt >= ceiling) {
        break;
      }

      // Ceiling two: wall clock. Checked between attempts, so the real worst
      // case is this deadline plus one in-flight query.
      if (now() - startedAt >= deadline) {
        break;
      }

      // Past the blip allowance, waiting again has to be justified. A healthy
      // canary proves the transport is fine, which means this structural
      // failure will not clear on its own — so stop and report it now rather
      // than spending the rest of the deadline to report the same thing.
      if (attempt >= quick && (await isPathHealthy(query))) {
        break;
      }

      await wait(pause);
    }
  }

  throw lastError;
}
