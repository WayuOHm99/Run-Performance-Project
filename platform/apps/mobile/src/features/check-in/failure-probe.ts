/**
 * A failure-safe probe for awaiting a rejection, used by the TASK-013 tests.
 *
 * The shared `src/test-support/capture-error.ts` **rethrows** a value that is not
 * the expected class. On a protected-health table that is a leak channel: a raw
 * PostgREST error carrying a message, `details`, `hint`, or a failing row would
 * be rethrown by the helper, reported by the runner, and printed. This task may
 * not modify that shared file, so it uses this local probe instead.
 *
 * The contract is that **nothing unknown ever escapes**. A caught value is
 * reduced here to a small fixed vocabulary, and only that vocabulary crosses into
 * an assertion:
 *
 *   - `outcome` — one of three fixed words;
 *   - `intent` and `failure` — the sanitized error's own enum fields;
 *   - `messageIsFixed` — a boolean, computed against the known message table.
 *
 * The captured value itself is never returned, never rethrown, never stringified,
 * and never passed to `expect`. A test that fails therefore prints a word like
 * `"unexpected-error"` and nothing else.
 *
 * Lives in the feature directory because it is TASK-013-owned. It is excluded
 * from the source-safety scan's runtime set, which is documented there.
 */

import type { DataFailure } from "../auth/errors";

import {
  CheckInDataError,
  UNEXPECTED_CHECK_IN_MESSAGE,
  type CheckInIntent,
} from "./errors";

export type ProbeOutcome =
  /** The promise resolved when the test expected a rejection. */
  | "resolved"
  /** Rejected with a sanitized `CheckInDataError`. */
  | "sanitized-error"
  /** Rejected with something else — the leak case, reported without detail. */
  | "unsanitized-error";

export type FailureProbe = {
  readonly outcome: ProbeOutcome;
  readonly intent: CheckInIntent | null;
  readonly failure: DataFailure | null;
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
 * Every message a sanitized check-in error is allowed to carry.
 *
 * Built from the class itself rather than duplicated, so the check cannot drift
 * from the implementation, and comparing against it yields a boolean.
 */
const FIXED_MESSAGES: ReadonlySet<string> = new Set<string>([
  ...(["load", "save"] as const).flatMap((intent) =>
    (["offline", "denied", "unknown"] as const).map(
      (failure) => new CheckInDataError(intent, failure).message,
    ),
  ),
  UNEXPECTED_CHECK_IN_MESSAGE,
]);

export async function probeFailure(
  promise: Promise<unknown>,
): Promise<FailureProbe> {
  try {
    await promise;

    return RESOLVED;
  } catch (error) {
    if (!(error instanceof CheckInDataError)) {
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
