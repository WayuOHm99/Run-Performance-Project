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

// A bounded, deterministic retry budget for exactly one condition: a baseline
// document whose row set exists but is not exactly one row. Four attempts,
// three waits, so the worst case adds 1.5s and then fails.
//
// Round 6 re-derived these numbers from measurement rather than keeping them by
// default; see the long note on `readBaseline`. The short version: the readiness
// gap at the point this runs measured 0ms in 4 of 4 cold cycles, and an unready
// database fails with a non-zero exit instead of this condition, so there is no
// measured window that a larger budget would cover.
export const BASELINE_ATTEMPTS = 4;
export const BASELINE_RETRY_DELAY_MS = 500;

// Ceilings, not settings. They exist so the injected seams below cannot widen
// the budget past what "bounded" means here.
const MAX_BASELINE_ATTEMPTS = 10;
const MAX_BASELINE_RETRY_DELAY_MS = 2000;

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

  // Two different failures, deliberately separated in round 6.
  //
  // A document with **no row set at all** — `{}`, `{ rows: null }`,
  // `{ rows: {} }`, or a document that is not an object — is not a database
  // that is still coming up. It is output that does not match the CLI's result
  // contract, and round 6 measured what an unready local database actually
  // produces: a **non-zero exit**, never a well-formed envelope missing its
  // `rows` array. Round 5 lumped this in with the row-count condition and
  // retried it four times on no evidence. It now fails immediately, with its
  // own fixed sanitized message.
  if (!Array.isArray(rows)) {
    throw new DemoBaselineError("The baseline query returned no row set.");
  }

  // A row set that exists but is the wrong size is the one retryable
  // condition. See `readBaseline` for why, and for what round 6 could and
  // could not measure about it.
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

// Bounded retry, one condition only: a row set that exists and is the wrong
// size. The SQL is ten scalar subqueries with no `from` and no predicate on the
// outer select, so exactly one row is the only result the database can return;
// a different cardinality is not a report about the demo's contents.
//
// Why retrying it is safe: the query is a read-only aggregate with no side
// effect, so re-running it changes nothing. It cannot mask a wrong baseline,
// because a wrong baseline parses fine — `compareBaseline` is a separate step
// that this function never reaches into and never re-runs.
//
// ## What round 6 measured, and why the budget did not grow
//
// The budget stayed at four attempts and 500ms because the measurements say a
// larger one would be sizing for a window this code cannot be in. On this
// machine, over two `stop → cold start → db reset` cycles polled continuously:
//
//   - Once `supabase start` or `db reset` **returns**, the first baseline query
//     answers with exactly one row, 4 times out of 4, with no gap at all.
//   - **While** either command is still running the database is genuinely
//     unreachable — up to ~21.8s during `db reset`, which restarts containers.
//     Every single one of those failures was a **non-zero exit**, never a
//     well-formed document with the wrong number of rows.
//
// The second point is the important one: an unready local database does not
// produce the retried condition. It produces a subprocess failure, which is a
// different error that is deliberately not retried.
//
// And by the time this function runs, `db reset`, two real Auth signups, and
// the fixture application have all already succeeded against that same
// database. Three successful round-trips are a stronger readiness proof than
// any timer, so a readiness gap here has already closed.
//
// The condition this retry covers was therefore **never reproduced**. It is
// kept as bounded, cheap insurance for the incident that motivated it, not
// because its duration is known — no duration was measurable, and enlarging a
// budget against an unmeasured window is the arbitrary increase this was asked
// not to be.
//
// Why the other failures are *not* retried:
//
//   - A **count mismatch** is not a failure of this function at all. It is a
//     real, correct read of a database in the wrong state, and the caller must
//     see it on the first attempt.
//   - **A missing or non-array row set** is not retried as of round 6. Round 5
//     did retry it, on the assumption it was the same readiness condition; the
//     measurements above say readiness failures are non-zero exits instead, so
//     the assumption had no evidence behind it. It now fails immediately.
//   - **Malformed JSON**, a **non-integer count**, and a **subprocess failure**
//     are not retried. The first two are consistent with a broken invocation or
//     a changed CLI contract, and retrying a broken contract only delays a
//     failure that should be immediate. The third is the shape an unready
//     database actually takes — but it is also the shape a genuinely broken one
//     takes, and the pipeline's own earlier steps already prove the database was
//     reachable, so treating it as transient here would hide a real fault.
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
