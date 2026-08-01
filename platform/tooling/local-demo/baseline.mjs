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

// The bounded, deterministic retry budget for the two structural readiness
// conditions described on `readBaseline`. Ten attempts, nine waits.
//
// **9000ms is the maximum *wait* budget, not the maximum duration.** The nine
// waits are the only part of the elapsed time this module controls. Each of the
// ten attempts also spawns a Supabase CLI process and waits for it to answer,
// and that cost is real: round 6 measured a single baseline query taking roughly
// 1.5s against a healthy local stack. So a full exhaustion is closer to 9s of
// waiting **plus** ten query round-trips, and the wall-clock total can be well
// over twenty seconds. Nothing here promises otherwise, and no caller sets a
// deadline against it.
//
// Round 8 raised these from four attempts and 500ms. See `readBaseline`.
export const BASELINE_ATTEMPTS = 10;
export const BASELINE_RETRY_DELAY_MS = 1000;

// Ceilings, not settings — and deliberately the production values themselves.
// The seams below exist for the tests, so a test may ask for a *smaller* budget
// to keep itself fast, but nothing can ask for a larger one. "Bounded" has to
// mean the same thing in a test as it does in `demo:reset`.
const MAX_BASELINE_ATTEMPTS = BASELINE_ATTEMPTS;
const MAX_BASELINE_RETRY_DELAY_MS = BASELINE_RETRY_DELAY_MS;

function boundedAttempts(attempts) {
  return Number.isInteger(attempts) &&
    attempts >= 1 &&
    attempts <= MAX_BASELINE_ATTEMPTS
    ? attempts
    : BASELINE_ATTEMPTS;
}

function boundedDelay(delayMs) {
  return Number.isFinite(delayMs) &&
    delayMs >= 0 &&
    delayMs <= MAX_BASELINE_RETRY_DELAY_MS
    ? delayMs
    : BASELINE_RETRY_DELAY_MS;
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

  const rows = document?.rows;

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
// ## The budget
//
// Ten attempts and 1000ms, up from four and 500ms. The old budget was chosen
// against a window measured at 0ms; this one is chosen against an incident that
// survived a whole `demo:reset` and an immediate `demo:verify`, which is a far
// longer window than any timer here can cover. Ten attempts do not promise to
// outlast it. They make a short blip recoverable and leave a long one failing
// closed, which is the honest shape for a condition whose duration is still
// unknown.
//
// See the constants above for why 9000ms is a wait budget rather than a
// duration.
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
export async function readBaseline({
  query = queryLocalScalars,
  attempts = BASELINE_ATTEMPTS,
  delayMs = BASELINE_RETRY_DELAY_MS,
  wait = delay,
} = {}) {
  // The seams exist for the tests, so they must not be able to remove the
  // bound they are testing. Anything that is not a positive integer inside the
  // ceiling — including `NaN`, `Infinity`, and 0, which would skip the loop
  // entirely and leave nothing to throw — falls back to the default.
  const budget = boundedAttempts(attempts);
  const pause = boundedDelay(delayMs);

  let lastError;

  for (let attempt = 1; attempt <= budget; attempt += 1) {
    try {
      return parseBaselineRow(await query(BASELINE_SQL));
    } catch (error) {
      if (!(error instanceof DemoBaselineError) || error.retryable !== true) {
        throw error;
      }

      lastError = error;

      if (attempt < budget) {
        await wait(pause);
      }
    }
  }

  throw lastError;
}
