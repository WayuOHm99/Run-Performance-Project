import { describe, expect, it } from "vitest";

import type { CoachReviewTeam } from "./domain";
import { CoachReviewDataError } from "./errors";
import {
  NO_IDENTITY_BOUNDARY,
  coachReviewBoundaryChanged,
  coachReviewIdentityBoundaryKey,
  hidesHealthValues,
  readCoachReviewView,
  visibleTeams,
  type CoachReviewQueryState,
} from "./view-state";
import {
  ATHLETE_1,
  ATHLETE_1_NAME,
  COACH_ID,
  OTHER_COACH_ID,
  TEAM_A,
  TEAM_A_NAME,
} from "./test-fixtures";

/**
 * The rendered derivation and the identity boundary.
 *
 * These two rules cannot be exercised through a rendered tree, because this task
 * may not add a component renderer. They are asserted instead against the exact
 * pure functions the section calls, which is why the section derives nothing
 * itself.
 *
 * **Failure-output discipline.** Every assertion is a fixed status word, a
 * boolean, or a count. The one fixture carrying a synthetic check-in is never
 * passed to `expect`.
 */

const TEAMS: readonly CoachReviewTeam[] = [
  {
    teamId: TEAM_A,
    teamName: TEAM_A_NAME,
    athletes: [
      {
        athleteProfileId: ATHLETE_1,
        athleteName: ATHLETE_1_NAME,
        checkIn: {
          checkInDate: "2026-07-30",
          rpe: 6,
          overallFeeling: 3,
          painStatus: "none",
        },
      },
    ],
  },
];

function state(
  overrides: Partial<CoachReviewQueryState>,
): CoachReviewQueryState {
  return {
    data: undefined,
    isFetching: false,
    isError: false,
    error: null,
    ...overrides,
  };
}

describe("readCoachReviewView", () => {
  it("is loading before anything has arrived", () => {
    expect(readCoachReviewView(state({ isFetching: true })).status).toBe(
      "loading",
    );
    expect(readCoachReviewView(state({})).status).toBe("loading");
  });

  it("is ready only when settled, error-free, and data-bearing", () => {
    const view = readCoachReviewView(state({ data: TEAMS }));

    expect(view.status).toBe("ready");
    expect(visibleTeams(view).length).toBe(1);
    expect(hidesHealthValues(view)).toBe(false);
  });

  it("hides every health value while a refresh is in flight", () => {
    // The previous list is still in `data`; the view must not carry it.
    const view = readCoachReviewView(state({ data: TEAMS, isFetching: true }));

    expect(view.status).toBe("refreshing");
    expect(visibleTeams(view).length).toBe(0);
    expect(hidesHealthValues(view)).toBe(true);
  });

  it("hides every health value after a refresh fails", () => {
    const view = readCoachReviewView(
      state({
        data: TEAMS,
        isError: true,
        error: new CoachReviewDataError("load", "unknown"),
      }),
    );

    expect(view.status).toBe("error");
    expect(visibleTeams(view).length).toBe(0);
    expect(hidesHealthValues(view)).toBe(true);
  });

  it("puts the error branch ahead of the fetching branch", () => {
    // A retry that is itself in flight after a failure must still show the
    // failure, not a list.
    const view = readCoachReviewView(
      state({ data: TEAMS, isError: true, isFetching: true, error: null }),
    );

    expect(view.status).toBe("error");
    expect(visibleTeams(view).length).toBe(0);
  });

  it("marks a capacity failure so the wording can differ", () => {
    const capacity = readCoachReviewView(
      state({
        isError: true,
        error: new CoachReviewDataError("load", "capacity"),
      }),
    );
    const other = readCoachReviewView(
      state({
        isError: true,
        error: new CoachReviewDataError("load", "denied"),
      }),
    );

    expect(capacity.status === "error" && capacity.capacity).toBe(true);
    expect(other.status === "error" && other.capacity).toBe(false);
  });

  it("does not treat an unsanitized error as a capacity failure", () => {
    const view = readCoachReviewView(
      state({ isError: true, error: { code: "42501", rpe: 6 } }),
    );

    expect(view.status === "error" && view.capacity).toBe(false);
  });

  it("renders an empty settled list as ready, not as loading", () => {
    // "You coach no active team" is an answer, not an absence of one.
    const view = readCoachReviewView(state({ data: [] }));

    expect(view.status).toBe("ready");
    expect(visibleTeams(view).length).toBe(0);
  });

  it("carries no health value in any non-ready state", () => {
    const nonReady = [
      state({ isFetching: true }),
      state({ data: TEAMS, isFetching: true }),
      state({ data: TEAMS, isError: true, error: null }),
      state({ isError: true, error: null }),
      state({}),
    ].map(readCoachReviewView);

    // Counts and booleans only.
    expect(nonReady.every(hidesHealthValues)).toBe(true);
    expect(nonReady.every((view) => visibleTeams(view).length === 0)).toBe(
      true,
    );
    expect(
      nonReady.filter((view) => JSON.stringify(view).includes("rpe")).length,
    ).toBe(0);
  });
});

describe("the identity boundary", () => {
  it("gives each verified identity its own key", () => {
    expect(
      coachReviewIdentityBoundaryKey(COACH_ID) ===
        coachReviewIdentityBoundaryKey(OTHER_COACH_ID),
    ).toBe(false);
  });

  it("treats signed out as its own identity", () => {
    expect(coachReviewIdentityBoundaryKey(undefined)).toBe(
      NO_IDENTITY_BOUNDARY,
    );
    expect(coachReviewIdentityBoundaryKey("")).toBe(NO_IDENTITY_BOUNDARY);
  });

  it("remounts on every identity transition", () => {
    const transitions: readonly (readonly [
      string,
      string | undefined,
      string | undefined,
    ])[] = [
      ["sign-in", undefined, COACH_ID],
      ["sign-out", COACH_ID, undefined],
      ["account-switch", COACH_ID, OTHER_COACH_ID],
    ];

    const missed = transitions
      .filter(([, from, to]) => !coachReviewBoundaryChanged(from, to))
      .map(([name]) => name);

    // Transition names only.
    expect(missed).toEqual([]);
  });

  it("does not remount when the identity is unchanged", () => {
    expect(coachReviewBoundaryChanged(COACH_ID, COACH_ID)).toBe(false);
  });

  it("is stable across calls", () => {
    expect(
      coachReviewIdentityBoundaryKey(COACH_ID) ===
        coachReviewIdentityBoundaryKey(COACH_ID),
    ).toBe(true);
  });
});
