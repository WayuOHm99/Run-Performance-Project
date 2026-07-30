/**
 * When server data may replace what the athlete currently sees.
 *
 * The card's first version got this wrong in two ways, both of which this module
 * exists to make impossible and testable:
 *
 * 1. It keyed "already prefilled" on the calendar **date** alone. An offset-only
 *    rollover — same date, new timezone — cleared the draft but could not
 *    rehydrate, because the query key had not changed and the effect had nothing
 *    new to react to. The card could then say today was already checked in while
 *    every control sat empty.
 *
 * 2. It prefilled **once** per date, permanently. After a save invalidated and
 *    refetched the same date, the server-confirmed row could not reach the
 *    controls. When another device was the last-completed writer, the cache held
 *    the winning row while the athlete kept looking at their losing values.
 *
 * The fix is a generation key that includes the offset, plus explicit `dirty` and
 * `awaitingRefresh` flags. The precedence in `shouldHydrate` is the whole policy:
 *
 *   - data for another generation is ignored outright;
 *   - a generation that has never been hydrated always hydrates;
 *   - a deliberately requested refresh always hydrates, which is what carries a
 *     post-save confirmation and an offset-only rollover;
 *   - otherwise unsaved edits win, so an ordinary background refetch never
 *     discards deliberate typing;
 *   - otherwise an ordinary refetch hydrates, which is how a concurrent
 *     last-completed write becomes visible.
 *
 * Everything here is pure. The draft lives in component state only and is never
 * persisted, queued, or written anywhere outside the approved server row.
 */

import type { DailyCheckIn } from "./domain";
import type { LocalDateStamp } from "./local-date";
import { localDateStampChanged } from "./local-date";
import { EMPTY_DRAFT, draftFromCheckIn, type CheckInDraft } from "./submission";

/**
 * Identity of "the local day this form is for".
 *
 * The offset is part of it deliberately: the same printed date under a different
 * offset is a different day boundary, so it must not reuse the previous
 * generation's hydration.
 */
export type GenerationKey = string;

export function generationKey(stamp: LocalDateStamp): GenerationKey {
  return `${stamp.date}|${String(stamp.offsetMinutes)}`;
}

export type CheckInFormState = {
  readonly stamp: LocalDateStamp;
  readonly draft: CheckInDraft;
  /** The generation the visible draft was hydrated from, or null if none yet. */
  readonly hydratedFor: GenerationKey | null;
  /** The athlete changed an answer since the last hydration. */
  readonly dirty: boolean;
  /** A refresh was deliberately requested and its result should be adopted. */
  readonly awaitingRefresh: boolean;
  /** Show the rollover notice. */
  readonly rolledOver: boolean;
};

export function initialFormState(stamp: LocalDateStamp): CheckInFormState {
  return {
    stamp,
    draft: EMPTY_DRAFT,
    hydratedFor: null,
    dirty: false,
    awaitingRefresh: false,
    rolledOver: false,
  };
}

export type FormEvent =
  /** The query settled successfully for `generation`. */
  | {
      readonly kind: "server-data";
      readonly generation: GenerationKey;
      readonly checkIn: DailyCheckIn | null;
    }
  /** The athlete chose an answer. */
  | { readonly kind: "answer-chosen"; readonly draft: CheckInDraft }
  /** The write completed; its refresh should be adopted when it lands. */
  | { readonly kind: "save-succeeded" }
  /** The local day moved; the old answers are dropped. */
  | { readonly kind: "rollover"; readonly stamp: LocalDateStamp };

/**
 * Whether incoming server data for `generation` may replace the visible draft.
 *
 * Exported because it is the decision this module exists for, and asserting it
 * directly is clearer than inferring it from reduced state.
 */
export function shouldHydrate(
  state: CheckInFormState,
  generation: GenerationKey,
): boolean {
  if (generation !== generationKey(state.stamp)) {
    // Data for a day the form is no longer showing. Never adopted.
    return false;
  }

  if (state.hydratedFor !== generation) {
    return true;
  }

  if (state.awaitingRefresh) {
    return true;
  }

  // Deliberate unsaved edits outrank an ordinary background refetch.
  return !state.dirty;
}

/**
 * True when the local day moved in a way the query key cannot see.
 *
 * The key carries the date only, so a date change refetches on its own while an
 * offset-only change does not. The card uses this to decide whether it must ask
 * for a refresh explicitly.
 */
export function needsDeliberateRefresh(
  previous: LocalDateStamp,
  next: LocalDateStamp,
): boolean {
  return localDateStampChanged(previous, next) && previous.date === next.date;
}

function draftsEqual(a: CheckInDraft, b: CheckInDraft): boolean {
  return (
    a.rpe === b.rpe &&
    a.overallFeeling === b.overallFeeling &&
    a.painStatus === b.painStatus
  );
}

function sameFormState(a: CheckInFormState, b: CheckInFormState): boolean {
  return (
    a.stamp === b.stamp &&
    a.hydratedFor === b.hydratedFor &&
    a.dirty === b.dirty &&
    a.awaitingRefresh === b.awaitingRefresh &&
    a.rolledOver === b.rolledOver &&
    draftsEqual(a.draft, b.draft)
  );
}

function reduce(state: CheckInFormState, event: FormEvent): CheckInFormState {
  switch (event.kind) {
    case "server-data": {
      if (event.generation !== generationKey(state.stamp)) {
        return state;
      }

      if (!shouldHydrate(state, event.generation)) {
        // The generation is now known to have server data even though the draft
        // was kept, so a later refetch is an ordinary one rather than a first
        // load.
        return { ...state, hydratedFor: event.generation };
      }

      return {
        ...state,
        // `null` yields the empty draft, so a genuine absence still preselects
        // nothing.
        draft: draftFromCheckIn(event.checkIn),
        hydratedFor: event.generation,
        dirty: false,
        awaitingRefresh: false,
      };
    }

    case "answer-chosen":
      return {
        ...state,
        draft: event.draft,
        dirty: true,
        rolledOver: false,
      };

    case "save-succeeded":
      // Not dirty any more, and the invalidation's refetch is wanted: it carries
      // whatever the database actually stored, including another device's win.
      return { ...state, dirty: false, awaitingRefresh: true };

    case "rollover":
      return {
        stamp: event.stamp,
        draft: EMPTY_DRAFT,
        hydratedFor: null,
        dirty: false,
        awaitingRefresh: true,
        rolledOver: true,
      };
  }
}

/**
 * The reducer the card uses.
 *
 * Returns the **same reference** when nothing changed. That is load-bearing, not
 * a micro-optimization: the card dispatches `server-data` from an effect that
 * depends on the query result, and a fresh object on every settle would
 * re-trigger that effect forever.
 */
export function reduceForm(
  state: CheckInFormState,
  event: FormEvent,
): CheckInFormState {
  const next = reduce(state, event);

  return sameFormState(state, next) ? state : next;
}
