import { describe, expect, it } from "vitest";

import type { DailyCheckIn } from "./domain";
import {
  generationKey,
  initialFormState,
  needsDeliberateRefresh,
  reduceForm,
  shouldHydrate,
  type CheckInFormState,
  type FormEvent,
} from "./hydration";
import type { LocalDateStamp } from "./local-date";
import { isDraftComplete, type CheckInDraft } from "./submission";

/**
 * Health literals are synthetic, and no health-bearing value reaches `expect`.
 *
 * Two ways a value could leak into failure output, both closed here:
 *
 * 1. **A field asserted directly.** `expect(state.draft.rpe).toBeNull()` prints
 *    the actual answer when it fails. Draft contents are compared inside
 *    `showing`, `showingDraft`, and `draftIsEmpty`, which return booleans.
 *
 * 2. **A whole form state passed to an identity matcher.** `expect(a).toBe(b)`
 *    prints both objects on failure, and a form state holds the draft. Reference
 *    identity is reduced by `isSameStateRef` before it reaches the assertion.
 *
 * A failing assertion in this file can therefore print only `true`, `false`, a
 * generation key, a calendar date, or a test name.
 */

const BANGKOK: LocalDateStamp = { date: "2026-07-30", offsetMinutes: -420 };
const NEXT_DAY: LocalDateStamp = { date: "2026-07-31", offsetMinutes: -420 };
/** Same calendar date, different timezone — the case the first version missed. */
const MOVED_ZONE: LocalDateStamp = { date: "2026-07-30", offsetMinutes: -300 };

const SERVER_ROW: DailyCheckIn = {
  rpe: 6,
  overallFeeling: 3,
  painStatus: "none",
};

const WINNING_ROW: DailyCheckIn = {
  rpe: 9,
  overallFeeling: 1,
  painStatus: "present",
};

const LOCAL_EDIT: CheckInDraft = {
  rpe: 2,
  overallFeeling: 5,
  painStatus: "none",
};

const SECOND_EDIT: CheckInDraft = {
  rpe: 4,
  overallFeeling: 4,
  painStatus: "present",
};

/** Whether the visible draft is exactly this check-in. Boolean only. */
function showing(state: CheckInFormState, checkIn: DailyCheckIn): boolean {
  return (
    state.draft.rpe === checkIn.rpe &&
    state.draft.overallFeeling === checkIn.overallFeeling &&
    state.draft.painStatus === checkIn.painStatus
  );
}

/** Whether the visible draft is exactly this draft. Boolean only. */
function showingDraft(state: CheckInFormState, draft: CheckInDraft): boolean {
  return (
    state.draft.rpe === draft.rpe &&
    state.draft.overallFeeling === draft.overallFeeling &&
    state.draft.painStatus === draft.painStatus
  );
}

/** Whether every answer is still unchosen. Boolean only. */
function draftIsEmpty(draft: CheckInDraft): boolean {
  return (
    draft.rpe === null &&
    draft.overallFeeling === null &&
    draft.painStatus === null
  );
}

/**
 * Reference identity of two form states, reduced before it reaches `expect`.
 *
 * `expect(a).toBe(b)` on objects prints both sides on failure, and a form state
 * holds the draft. Comparing here means a failure can only print `false`.
 */
function isSameStateRef(a: CheckInFormState, b: CheckInFormState): boolean {
  return a === b;
}

function run(
  state: CheckInFormState,
  events: readonly FormEvent[],
): CheckInFormState {
  return events.reduce(reduceForm, state);
}

function serverData(
  stamp: LocalDateStamp,
  checkIn: DailyCheckIn | null,
): FormEvent {
  return { kind: "server-data", generation: generationKey(stamp), checkIn };
}

describe("generationKey", () => {
  it("separates the same date under a different offset", () => {
    expect(generationKey(BANGKOK)).not.toBe(generationKey(MOVED_ZONE));
  });

  it("separates different dates", () => {
    expect(generationKey(BANGKOK)).not.toBe(generationKey(NEXT_DAY));
  });

  it("is stable for the same stamp", () => {
    expect(generationKey(BANGKOK)).toBe(generationKey({ ...BANGKOK }));
  });
});

describe("initialFormState", () => {
  it("preselects nothing and has hydrated from nothing", () => {
    const state = initialFormState(BANGKOK);

    expect(isDraftComplete(state.draft)).toBe(false);
    expect(state.hydratedFor).toBeNull();
    expect(state.dirty).toBe(false);
    expect(state.rolledOver).toBe(false);
  });
});

describe("shouldHydrate", () => {
  it("ignores data belonging to another generation", () => {
    const state = initialFormState(BANGKOK);

    expect(shouldHydrate(state, generationKey(NEXT_DAY))).toBe(false);
    expect(shouldHydrate(state, generationKey(MOVED_ZONE))).toBe(false);
  });

  it("hydrates a generation that has never been hydrated", () => {
    expect(
      shouldHydrate(initialFormState(BANGKOK), generationKey(BANGKOK)),
    ).toBe(true);
  });

  it("protects unsaved edits from an ordinary refetch", () => {
    const state = run(initialFormState(BANGKOK), [
      serverData(BANGKOK, SERVER_ROW),
      { kind: "answer-chosen", draft: LOCAL_EDIT },
    ]);

    expect(shouldHydrate(state, generationKey(BANGKOK))).toBe(false);
  });

  it("adopts the refetch that follows a completed save", () => {
    const state = run(initialFormState(BANGKOK), [
      serverData(BANGKOK, SERVER_ROW),
      { kind: "answer-chosen", draft: LOCAL_EDIT },
      { kind: "save-succeeded" },
    ]);

    // `save-succeeded` is what clears `dirty`, and clearing `dirty` is what lets
    // the confirming refetch through. Without it the athlete would keep seeing
    // their submitted values even if the database stored something else.
    expect(state.dirty).toBe(false);
    expect(shouldHydrate(state, generationKey(BANGKOK))).toBe(true);
  });

  it("still protects an edit made after saving but before the refetch lands", () => {
    const state = run(initialFormState(BANGKOK), [
      serverData(BANGKOK, SERVER_ROW),
      { kind: "answer-chosen", draft: LOCAL_EDIT },
      { kind: "save-succeeded" },
      // The athlete changed their mind while the refresh was in flight.
      { kind: "answer-chosen", draft: SECOND_EDIT },
    ]);

    expect(shouldHydrate(state, generationKey(BANGKOK))).toBe(false);
  });

  it("adopts an ordinary refetch when there are no unsaved edits", () => {
    const state = run(initialFormState(BANGKOK), [
      serverData(BANGKOK, SERVER_ROW),
    ]);

    expect(shouldHydrate(state, generationKey(BANGKOK))).toBe(true);
  });
});

describe("first load", () => {
  it("prefills an existing row", () => {
    const state = run(initialFormState(BANGKOK), [
      serverData(BANGKOK, SERVER_ROW),
    ]);

    expect(showing(state, SERVER_ROW)).toBe(true);
    expect(state.hydratedFor).toBe(generationKey(BANGKOK));
    expect(state.dirty).toBe(false);
  });

  it("leaves a genuine empty row with no default answers", () => {
    const state = run(initialFormState(BANGKOK), [serverData(BANGKOK, null)]);

    expect(isDraftComplete(state.draft)).toBe(false);
    // Stronger than "not complete": every one of the three is still unchosen.
    expect(draftIsEmpty(state.draft)).toBe(true);
    // Hydrated from an absence is still hydrated, so the empty-state copy is
    // allowed to appear.
    expect(state.hydratedFor).toBe(generationKey(BANGKOK));
  });
});

describe("date rollover", () => {
  it("drops the old answers and hydrates the new date", () => {
    const afterRollover = run(initialFormState(BANGKOK), [
      serverData(BANGKOK, SERVER_ROW),
      { kind: "answer-chosen", draft: LOCAL_EDIT },
      { kind: "rollover", stamp: NEXT_DAY },
    ]);

    expect(isDraftComplete(afterRollover.draft)).toBe(false);
    expect(afterRollover.hydratedFor).toBeNull();
    expect(afterRollover.rolledOver).toBe(true);
    expect(afterRollover.stamp.date).toBe("2026-07-31");

    // Data still arriving for the old day is ignored.
    const stale = reduceForm(afterRollover, serverData(BANGKOK, SERVER_ROW));

    expect(isSameStateRef(stale, afterRollover)).toBe(true);

    const hydrated = reduceForm(afterRollover, serverData(NEXT_DAY, null));

    expect(isDraftComplete(hydrated.draft)).toBe(false);
    expect(hydrated.hydratedFor).toBe(generationKey(NEXT_DAY));
  });

  it("needs no deliberate refresh, because the query key changes", () => {
    expect(needsDeliberateRefresh(BANGKOK, NEXT_DAY)).toBe(false);
  });
});

describe("offset-only rollover", () => {
  it("needs a deliberate refresh, because the query key does not change", () => {
    expect(needsDeliberateRefresh(BANGKOK, MOVED_ZONE)).toBe(true);
  });

  it("is not reported when nothing moved", () => {
    expect(needsDeliberateRefresh(BANGKOK, { ...BANGKOK })).toBe(false);
  });

  it("rehydrates the existing row for the same calendar date", () => {
    const afterRollover = run(initialFormState(BANGKOK), [
      serverData(BANGKOK, SERVER_ROW),
      { kind: "answer-chosen", draft: LOCAL_EDIT },
      { kind: "rollover", stamp: MOVED_ZONE },
    ]);

    // The stale write was blocked and the draft reset.
    expect(isDraftComplete(afterRollover.draft)).toBe(false);
    expect(afterRollover.rolledOver).toBe(true);
    expect(afterRollover.stamp.date).toBe("2026-07-30");

    // The old generation's data must not silently satisfy the new generation —
    // this is the bug: the date is unchanged, so only the generation key tells
    // them apart.
    expect(
      isSameStateRef(
        reduceForm(afterRollover, serverData(BANGKOK, SERVER_ROW)),
        afterRollover,
      ),
    ).toBe(true);

    // The deliberate refresh lands under the new generation and rehydrates.
    const hydrated = reduceForm(
      afterRollover,
      serverData(MOVED_ZONE, SERVER_ROW),
    );

    expect(showing(hydrated, SERVER_ROW)).toBe(true);
    expect(hydrated.hydratedFor).toBe(generationKey(MOVED_ZONE));
    expect(hydrated.dirty).toBe(false);
  });

  it("never claims to be hydrated while the controls are still empty", () => {
    // The exact defect: the UI said today was already checked in while every
    // control sat empty. `hydratedFor` is what the card gates that copy on, so
    // it must not equal the current generation until the draft was actually
    // filled from that generation's data.
    const afterRollover = run(initialFormState(BANGKOK), [
      serverData(BANGKOK, SERVER_ROW),
      { kind: "rollover", stamp: MOVED_ZONE },
    ]);

    expect(afterRollover.hydratedFor).not.toBe(generationKey(MOVED_ZONE));
    expect(isDraftComplete(afterRollover.draft)).toBe(false);
  });

  it("leaves a genuinely empty new generation with no defaults", () => {
    const state = run(initialFormState(BANGKOK), [
      serverData(BANGKOK, SERVER_ROW),
      { kind: "rollover", stamp: MOVED_ZONE },
      serverData(MOVED_ZONE, null),
    ]);

    expect(isDraftComplete(state.draft)).toBe(false);
    expect(state.hydratedFor).toBe(generationKey(MOVED_ZONE));
  });
});

describe("after a successful save", () => {
  it("hydrates the same date from the server-confirmed row", () => {
    const state = run(initialFormState(BANGKOK), [
      serverData(BANGKOK, null),
      { kind: "answer-chosen", draft: LOCAL_EDIT },
      { kind: "save-succeeded" },
      // The invalidation's refetch, returning what the database stored.
      serverData(BANGKOK, SERVER_ROW),
    ]);

    expect(showing(state, SERVER_ROW)).toBe(true);
    expect(state.dirty).toBe(false);
  });

  it("cannot hydrate from the confirming refetch without save-succeeded", () => {
    // The same sequence with the save-completion event omitted: the draft stays
    // dirty, so the server-confirmed row is correctly held back. This is what
    // makes the event above load-bearing rather than decorative.
    const state = run(initialFormState(BANGKOK), [
      serverData(BANGKOK, null),
      { kind: "answer-chosen", draft: LOCAL_EDIT },
      serverData(BANGKOK, SERVER_ROW),
    ]);

    expect(showing(state, SERVER_ROW)).toBe(false);
    expect(showingDraft(state, LOCAL_EDIT)).toBe(true);
  });

  it("shows a concurrent last-completed write rather than the losing values", () => {
    // Another device wrote after this one. The refetch carries the winner, and
    // the athlete must see what is actually stored.
    const state = run(initialFormState(BANGKOK), [
      serverData(BANGKOK, SERVER_ROW),
      { kind: "answer-chosen", draft: LOCAL_EDIT },
      { kind: "save-succeeded" },
      serverData(BANGKOK, WINNING_ROW),
    ]);

    expect(showing(state, WINNING_ROW)).toBe(true);
    expect(showingDraft(state, LOCAL_EDIT)).toBe(false);
  });

  it("adopts a concurrent value on an ordinary refetch too, when nothing is unsaved", () => {
    const state = run(initialFormState(BANGKOK), [
      serverData(BANGKOK, SERVER_ROW),
      serverData(BANGKOK, WINNING_ROW),
    ]);

    expect(showing(state, WINNING_ROW)).toBe(true);
  });
});

describe("an ordinary background refetch", () => {
  it("does not discard unsaved edits", () => {
    const state = run(initialFormState(BANGKOK), [
      serverData(BANGKOK, SERVER_ROW),
      { kind: "answer-chosen", draft: LOCAL_EDIT },
      // A refetch triggered by staleness, not by anything the athlete did.
      serverData(BANGKOK, WINNING_ROW),
    ]);

    expect(showingDraft(state, LOCAL_EDIT)).toBe(true);
    expect(showing(state, WINNING_ROW)).toBe(false);
    expect(state.dirty).toBe(true);
  });

  it("keeps protecting the edits across repeated refetches", () => {
    const state = run(initialFormState(BANGKOK), [
      serverData(BANGKOK, SERVER_ROW),
      { kind: "answer-chosen", draft: LOCAL_EDIT },
      serverData(BANGKOK, WINNING_ROW),
      serverData(BANGKOK, WINNING_ROW),
      serverData(BANGKOK, SERVER_ROW),
    ]);

    expect(showingDraft(state, LOCAL_EDIT)).toBe(true);
  });
});

describe("reduceForm referential stability", () => {
  it("returns the same state when nothing changed", () => {
    // Load-bearing: the card dispatches `server-data` from an effect that
    // depends on the query result, so a fresh object every settle would loop.
    const hydrated = run(initialFormState(BANGKOK), [
      serverData(BANGKOK, SERVER_ROW),
    ]);

    expect(
      isSameStateRef(
        reduceForm(hydrated, serverData(BANGKOK, SERVER_ROW)),
        hydrated,
      ),
    ).toBe(true);
  });

  it("returns the same state for data from another generation", () => {
    const hydrated = run(initialFormState(BANGKOK), [
      serverData(BANGKOK, SERVER_ROW),
    ]);

    expect(
      isSameStateRef(
        reduceForm(hydrated, serverData(NEXT_DAY, WINNING_ROW)),
        hydrated,
      ),
    ).toBe(true);
  });

  it("returns a new state when the draft actually changes", () => {
    const hydrated = run(initialFormState(BANGKOK), [
      serverData(BANGKOK, SERVER_ROW),
    ]);

    expect(
      isSameStateRef(
        reduceForm(hydrated, serverData(BANGKOK, WINNING_ROW)),
        hydrated,
      ),
    ).toBe(false);
  });
});

describe("the rollover notice", () => {
  it("clears as soon as the athlete answers again", () => {
    const state = run(initialFormState(BANGKOK), [
      { kind: "rollover", stamp: NEXT_DAY },
      serverData(NEXT_DAY, null),
      { kind: "answer-chosen", draft: LOCAL_EDIT },
    ]);

    expect(state.rolledOver).toBe(false);
  });
});
