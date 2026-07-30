/**
 * The in-progress form value and the decision of what a save press should do.
 *
 * Kept pure and separate from the card so the two rules that matter are testable
 * without a renderer:
 *
 *   1. **Nothing is preselected.** An empty draft holds three nulls, so a
 *      partially answered form is structurally distinguishable from an answered
 *      one and cannot be saved.
 *   2. **A rollover is checked before anything else.** The local date is
 *      recomputed at submission time, and if the day or the offset moved since
 *      the form was created, the answers are discarded rather than written to the
 *      stale date. Checking this ahead of completeness means a rollover during a
 *      half-filled form still resets, so the athlete cannot finish yesterday's
 *      form after midnight and have it silently land on yesterday.
 *
 * The draft lives in component state only. It is never persisted, queued, or
 * written anywhere outside the approved server row.
 */

import {
  parseCheckInInput,
  type DailyCheckIn,
  type PainStatus,
} from "./domain";
import { localDateStampChanged, type LocalDateStamp } from "./local-date";

export type CheckInDraft = {
  readonly rpe: number | null;
  readonly overallFeeling: number | null;
  readonly painStatus: PainStatus | null;
};

/** No default answer for any of the three fields — decision 6. */
export const EMPTY_DRAFT: CheckInDraft = {
  rpe: null,
  overallFeeling: null,
  painStatus: null,
};

/** Prefills an edit of today's existing row, or stays empty when there is none. */
export function draftFromCheckIn(checkIn: DailyCheckIn | null): CheckInDraft {
  if (checkIn === null) {
    return EMPTY_DRAFT;
  }

  return {
    rpe: checkIn.rpe,
    overallFeeling: checkIn.overallFeeling,
    painStatus: checkIn.painStatus,
  };
}

/** True only once all three answers are explicitly chosen. */
export function isDraftComplete(draft: CheckInDraft): boolean {
  return (
    draft.rpe !== null &&
    draft.overallFeeling !== null &&
    draft.painStatus !== null
  );
}

export type SubmissionPlan =
  /** Not all three answers are chosen, or one of them failed validation. */
  | { readonly kind: "incomplete" }
  /** The local day moved; reset against `stamp` and ask for a fresh review. */
  | { readonly kind: "rollover"; readonly stamp: LocalDateStamp }
  | {
      readonly kind: "submit";
      readonly localDate: string;
      readonly input: DailyCheckIn;
    };

export function planSubmission(args: {
  readonly captured: LocalDateStamp;
  readonly current: LocalDateStamp;
  readonly draft: CheckInDraft;
}): SubmissionPlan {
  // Deliberately first. A stale date must win over a complete draft.
  if (localDateStampChanged(args.captured, args.current)) {
    return { kind: "rollover", stamp: args.current };
  }

  const parsed = parseCheckInInput(args.draft);

  // Covers both an unanswered field and a value that failed validation, so an
  // invalid draft never reaches a write.
  if (!parsed.ok) {
    return { kind: "incomplete" };
  }

  return {
    kind: "submit",
    localDate: args.current.date,
    input: parsed.value,
  };
}
