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

// A bounded, deterministic retry budget for exactly one condition: a
// well-formed baseline document whose `rows` is not exactly one row. Four
// attempts, three waits, so the worst case adds 1.5s and then fails.
export const BASELINE_ATTEMPTS = 4;
export const BASELINE_RETRY_DELAY_MS = 500;

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

  if (!Array.isArray(rows) || rows.length !== 1) {
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

// Bounded retry, one condition only.
//
// On a cold stack the first baseline read has been observed to come back as a
// well-formed envelope — `boundary`, `warning`, `rows` — whose `rows` is not the
// single row the query can only ever produce. The SQL is ten scalar subqueries
// with no `from` and no predicate on the outer select, so exactly one row is the
// only result the database can return; anything else means the read did not
// reach a ready database, not that the demo is in a different state. That is the
// one condition retried here.
//
// Why retrying it is safe: the query is a read-only aggregate with no side
// effect, so re-running it changes nothing; and a retry can only ever end in one
// of the same three outcomes as the first attempt. It cannot mask a wrong
// baseline, because a wrong baseline parses fine — `compareBaseline` is a
// separate step that this function never reaches into and never re-runs.
//
// Why the other two failures are *not* retried:
//
//   - A **count mismatch** is not a failure of this function at all. It is a
//     real, correct read of a database that is in the wrong state, and the
//     caller must see it on the first attempt.
//   - **Malformed JSON** and a **non-integer count** are not retried, because I
//     cannot prove they are transient. Malformed output means the CLI wrote
//     something other than a result document, and a non-integer count means a
//     `count(*)::int` came back as something that is not an integer; both are
//     consistent with a broken invocation or a changed contract, and retrying a
//     broken contract only delays a failure that should be immediate. Requiring
//     proof rather than plausibility is deliberate: an unprovable retry is how a
//     permanent fault gets reported as a slow one.
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
  let lastError;

  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      return parseBaselineRow(await query(BASELINE_SQL));
    } catch (error) {
      if (!(error instanceof DemoBaselineError) || error.retryable !== true) {
        throw error;
      }

      lastError = error;

      if (attempt < attempts) {
        await wait(delayMs);
      }
    }
  }

  throw lastError;
}
