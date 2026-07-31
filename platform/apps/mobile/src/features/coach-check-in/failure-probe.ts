/**
 * A failure-safe probe for awaiting a rejection, used by the TASK-016 tests.
 *
 * The shared `src/test-support/capture-error.ts` **rethrows** a value that is not
 * the expected class. For this feature that is the worst possible leak channel: a
 * raw PostgREST error from the stage-c read can carry a message, `details`, `hint`,
 * a policy name, and an athlete profile id, and a rethrown value is reported by the
 * runner and printed to a terminal and a CI log. This task may not modify that
 * shared file, so it uses this local probe instead.
 *
 * The contract is that **nothing unknown ever escapes**. A caught value is reduced
 * here to a small fixed vocabulary, and only that vocabulary crosses into an
 * assertion:
 *
 *   - `outcome` — one of three fixed words;
 *   - `intent` and `failure` — the sanitized error's own enum fields;
 *   - `messageIsFixed` — a boolean, computed against the known message table;
 *   - `withoutCause` — a boolean;
 *   - `fields` — own enumerable field names, which are safe to print.
 *
 * The captured value itself is never returned, never rethrown, never stringified,
 * and never passed to `expect`. A test that fails therefore prints a word like
 * `"unsanitized-error"` and nothing else.
 *
 * Lives in the feature directory because it is TASK-016-owned. It is excluded from
 * the source-safety scan's runtime set, which is documented there.
 */

import {
  CoachReviewDataError,
  fixedCoachReviewMessages,
  type CoachReviewFailure,
  type CoachReviewIntent,
} from "./errors";

export type ProbeOutcome =
  /** The promise resolved when the test expected a rejection. */
  | "resolved"
  /** Rejected with a sanitized `CoachReviewDataError`. */
  | "sanitized-error"
  /** Rejected with something else — the leak case, reported without detail. */
  | "unsanitized-error";

export type FailureProbe = {
  readonly outcome: ProbeOutcome;
  readonly intent: CoachReviewIntent | null;
  readonly failure: CoachReviewFailure | null;
  /** True when the message is one of the fixed application strings. */
  readonly messageIsFixed: boolean;
  /** True when the error carries no `cause`. */
  readonly withoutCause: boolean;
  /** Own enumerable field names, which are safe to print. */
  readonly fields: readonly string[];
};

const RESOLVED: FailureProbe = {
  outcome: "resolved",
  intent: null,
  failure: null,
  messageIsFixed: false,
  withoutCause: false,
  fields: [],
};

const UNSANITIZED: FailureProbe = {
  outcome: "unsanitized-error",
  intent: null,
  failure: null,
  messageIsFixed: false,
  withoutCause: false,
  fields: [],
};

/**
 * Every message a sanitized coach-review error is allowed to carry.
 *
 * Built from the class itself rather than duplicated, so the check cannot drift
 * from the implementation, and comparing against it yields a boolean.
 */
const FIXED_MESSAGES = fixedCoachReviewMessages();

export async function probeFailure(
  promise: Promise<unknown>,
): Promise<FailureProbe> {
  try {
    await promise;

    return RESOLVED;
  } catch (error) {
    if (!(error instanceof CoachReviewDataError)) {
      // Deliberately discarded. Returning, logging, or rethrowing it here is
      // exactly the disclosure this probe exists to prevent.
      return UNSANITIZED;
    }

    return {
      outcome: "sanitized-error",
      intent: error.intent,
      failure: error.failure,
      messageIsFixed: FIXED_MESSAGES.has(error.message),
      withoutCause: (error as { cause?: unknown }).cause === undefined,
      fields: Object.keys(error).sort(),
    };
  }
}

/**
 * Reduces a resolved coach-review list to non-health scalars.
 *
 * Used wherever a success path is asserted. A test that compares whole team
 * objects would print RPE, feeling, pain status, and a recorded date on failure;
 * this reduces the same information to team labels, athlete labels, counts, and
 * booleans, so a failing assertion prints nothing protected.
 */
export function summarize(
  teams: readonly {
    readonly teamName: string;
    readonly athletes: readonly {
      readonly athleteName: string;
      readonly checkIn: unknown;
    }[];
  }[],
): readonly string[] {
  return teams.map(
    (team) =>
      `${team.teamName}:${String(team.athletes.length)}:${team.athletes
        .map(
          (athlete) =>
            `${athlete.athleteName}=${athlete.checkIn === null ? "none" : "present"}`,
        )
        .join(",")}`,
  );
}
