/**
 * Duplicate-submission guard.
 *
 * A double-tapped sign-up button sends two `signUp()` calls, which at best
 * burns a rate-limit allowance and at worst produces two confirmation emails.
 * The guard is a pure transition so the rule can be tested without a rendered
 * button.
 */

export type SubmissionState = "idle" | "submitting";

export type SubmissionAttempt = {
  /** False when the caller must drop this attempt entirely. */
  readonly accepted: boolean;
  readonly next: SubmissionState;
};

export function beginSubmission(current: SubmissionState): SubmissionAttempt {
  if (current === "submitting") {
    return { accepted: false, next: current };
  }

  return { accepted: true, next: "submitting" };
}

export function endSubmission(): SubmissionState {
  return "idle";
}

export function isSubmitting(current: SubmissionState): boolean {
  return current === "submitting";
}
