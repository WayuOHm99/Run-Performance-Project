import { describe, expect, it } from "vitest";

import {
  MAX_SHARING_PAIRS,
  athleteIdsToRead,
  composeCoachReview,
  parseCoachedTeams,
  parseGrantPairs,
  sharedPairCount,
  type CoachedTeam,
  type GrantPair,
} from "./domain";
import { summarize } from "./failure-probe";
import {
  ATHLETE_1,
  ATHLETE_1_NAME,
  ATHLETE_2,
  ATHLETE_2_NAME,
  COACH_ID,
  TEAM_A,
  TEAM_A_NAME,
  TEAM_B,
  TEAM_B_NAME,
  TEAM_UNCOACHED,
  checkInRow,
  grantRow,
  label,
  membershipRow,
  profileRow,
} from "./test-fixtures";

/**
 * The pure domain: the three stage parsers and the composition.
 *
 * **Failure-output discipline.** Not one assertion in this file receives a parsed
 * team, athlete, or check-in object. Results are reduced first to a boolean, a
 * count, a fixed rejection reason, a fixed label, or the `summarize` string —
 * which carries team labels, athlete labels, counts, and the word `present` or
 * `none`, and never an RPE, a feeling, a pain status, or a recorded date. A test
 * that fails here prints nothing protected.
 */

const COACHED_TEAMS: readonly CoachedTeam[] = [
  { teamId: TEAM_A, teamName: TEAM_A_NAME },
  { teamId: TEAM_B, teamName: TEAM_B_NAME },
];

const COACHED_IDS = new Set([TEAM_A, TEAM_B]);

/** The parse outcome as one fixed word. Never the value itself. */
function outcome(parse: { readonly ok: boolean; readonly reason?: string }) {
  return parse.ok ? "ok" : (parse.reason ?? "unknown");
}

function grants(rows: unknown) {
  return parseGrantPairs({
    rows,
    coachedTeamIds: COACHED_IDS,
    callerUserId: COACH_ID,
  });
}

// ---------------------------------------------------------------------------
// Stage a
// ---------------------------------------------------------------------------

describe("parseCoachedTeams", () => {
  it("accepts an active coach membership with a visible team name", () => {
    const parsed = parseCoachedTeams([membershipRow()]);

    expect(outcome(parsed)).toBe("ok");
    expect(parsed.ok ? parsed.value.length : -1).toBe(1);
    expect(parsed.ok ? label(parsed.value[0]?.teamId) : "none").toBe("team-a");
  });

  it("treats no coach membership as a real empty answer, not a rejection", () => {
    // The genuine no-active-coach-team state. It must stay distinguishable from
    // every failure, which is why the parse is `ok` with an empty list.
    const parsed = parseCoachedTeams([]);

    expect(outcome(parsed)).toBe("ok");
    expect(parsed.ok ? parsed.value.length : -1).toBe(0);
  });

  it("accepts a to-one embed shaped as a one-element array", () => {
    const parsed = parseCoachedTeams([
      membershipRow({ teams: [{ name: TEAM_A_NAME }] }),
    ]);

    expect(outcome(parsed)).toBe("ok");
  });

  it("rejects every malformed membership shape", () => {
    const cases: readonly (readonly [string, unknown])[] = [
      ["not-an-array", null],
      ["missing-team-id", membershipRow({ team_id: undefined })],
      ["blank-team-id", membershipRow({ team_id: "   " })],
      ["non-string-team-id", membershipRow({ team_id: 42 })],
      ["athlete-role", membershipRow({ role: "athlete" })],
      ["missing-role", membershipRow({ role: undefined })],
      ["pending-status", membershipRow({ status: "pending" })],
      ["revoked-status", membershipRow({ status: "revoked" })],
      ["hidden-team", membershipRow({ teams: null })],
      ["blank-team-name", membershipRow({ teams: { name: "  " } })],
      ["empty-embed-array", membershipRow({ teams: [] })],
      [
        "two-row-embed",
        membershipRow({ teams: [{ name: "a" }, { name: "b" }] }),
      ],
      ["row-is-null", null],
      ["row-is-string", "membership"],
    ];

    const accepted = cases
      .filter(([, row]) => parseCoachedTeams(row === null ? row : [row]).ok)
      .map(([name]) => name);

    // Case names only.
    expect(accepted).toEqual([]);
  });

  it("rejects a duplicate team", () => {
    // team_memberships is unique on (team_id, profile_id), so a repeat means the
    // response is not the database's actual state.
    expect(outcome(parseCoachedTeams([membershipRow(), membershipRow()]))).toBe(
      "invalid",
    );
  });
});

// ---------------------------------------------------------------------------
// Stage b
// ---------------------------------------------------------------------------

describe("parseGrantPairs", () => {
  it("accepts an active check_in grant for a coached team", () => {
    const parsed = grants([grantRow()]);

    expect(outcome(parsed)).toBe("ok");
    expect(parsed.ok ? parsed.value.length : -1).toBe(1);
  });

  it("treats no grant as a real empty answer, not a rejection", () => {
    const parsed = grants([]);

    expect(outcome(parsed)).toBe("ok");
    expect(parsed.ok ? parsed.value.length : -1).toBe(0);
  });

  it("keeps one athlete's grants to two coached teams as two pairs", () => {
    const parsed = grants([
      grantRow({ team_id: TEAM_A }),
      grantRow({ team_id: TEAM_B }),
    ]);

    expect(outcome(parsed)).toBe("ok");
    expect(parsed.ok ? parsed.value.length : -1).toBe(2);
    // Deduplicated for the profile read, materialized twice afterwards.
    expect(parsed.ok ? athleteIdsToRead(parsed.value).length : -1).toBe(1);
  });

  it("rejects a grant naming a team the caller does not coach", () => {
    // Team A's coach must never obtain Team B's — or any other team's — data.
    expect(outcome(grants([grantRow({ team_id: TEAM_UNCOACHED })]))).toBe(
      "invalid",
    );
  });

  it("rejects every sharing category that is not exactly check_in", () => {
    const categories = [
      "workout_summary",
      "sleep_summary",
      "CHECK_IN",
      "check_in ",
      "",
      undefined,
      null,
      7,
    ];

    const accepted = categories
      .filter((category) => grants([grantRow({ data_category: category })]).ok)
      .map((category) => typeof category);

    // Types only, never the category strings themselves.
    expect(accepted).toEqual([]);
  });

  it("rejects a self-targeted grant among coached teams", () => {
    // A dual-role user cannot hold a coach and an athlete membership in the same
    // team, so this response is impossible and is refused rather than filtered.
    expect(outcome(grants([grantRow({ athlete_profile_id: COACH_ID })]))).toBe(
      "invalid",
    );
  });

  it("rejects a duplicate team/athlete pair", () => {
    expect(outcome(grants([grantRow(), grantRow()]))).toBe("invalid");
  });

  it("rejects a malformed grant row", () => {
    const cases: readonly (readonly [string, unknown])[] = [
      ["not-an-array", null],
      ["missing-team", grantRow({ team_id: undefined })],
      ["missing-athlete", grantRow({ athlete_profile_id: undefined })],
      ["blank-athlete", grantRow({ athlete_profile_id: " " })],
      ["numeric-athlete", grantRow({ athlete_profile_id: 1 })],
      ["row-is-null", null],
    ];

    const accepted = cases
      .filter(([, row]) => grants(row === null ? row : [row]).ok)
      .map(([name]) => name);

    expect(accepted).toEqual([]);
  });

  it("accepts exactly the maximum scope", () => {
    const rows = Array.from({ length: MAX_SHARING_PAIRS }, (_unused, index) =>
      grantRow({ athlete_profile_id: `athlete-${String(index)}` }),
    );

    expect(outcome(grants(rows))).toBe("ok");
  });

  it("refuses one pair beyond the maximum scope as a capacity failure", () => {
    // The overflow probe. Never truncated, and reported as its own reason so the
    // wording can say "too large" rather than "try again".
    const rows = Array.from(
      { length: MAX_SHARING_PAIRS + 1 },
      (_unused, index) =>
        grantRow({ athlete_profile_id: `athlete-${String(index)}` }),
    );

    expect(outcome(grants(rows))).toBe("capacity");
  });
});

// ---------------------------------------------------------------------------
// Stage c and composition
// ---------------------------------------------------------------------------

describe("composeCoachReview", () => {
  const pairsA: readonly GrantPair[] = [
    { teamId: TEAM_A, athleteProfileId: ATHLETE_1 },
  ];

  it("materializes one validated pair under its exact team", () => {
    const composed = composeCoachReview({
      teams: COACHED_TEAMS,
      pairs: pairsA,
      profileRows: [profileRow()],
    });

    expect(outcome(composed)).toBe("ok");
    // Labels, counts, and presence only.
    expect(composed.ok ? summarize(composed.value) : []).toEqual([
      `${TEAM_A_NAME}:1:${ATHLETE_1_NAME}=present`,
      `${TEAM_B_NAME}:0:`,
    ]);
  });

  it("renders a multi-team athlete under both exact teams", () => {
    const composed = composeCoachReview({
      teams: COACHED_TEAMS,
      pairs: [
        { teamId: TEAM_A, athleteProfileId: ATHLETE_1 },
        { teamId: TEAM_B, athleteProfileId: ATHLETE_1 },
      ],
      profileRows: [profileRow()],
    });

    expect(outcome(composed)).toBe("ok");
    expect(composed.ok ? summarize(composed.value) : []).toEqual([
      `${TEAM_A_NAME}:1:${ATHLETE_1_NAME}=present`,
      `${TEAM_B_NAME}:1:${ATHLETE_1_NAME}=present`,
    ]);
    expect(composed.ok ? sharedPairCount(composed.value) : -1).toBe(2);
  });

  it("reports an active grant with no check-in as the only pending state", () => {
    const composed = composeCoachReview({
      teams: COACHED_TEAMS,
      pairs: pairsA,
      profileRows: [profileRow({ daily_check_ins: [] })],
    });

    expect(outcome(composed)).toBe("ok");
    expect(composed.ok ? summarize(composed.value) : []).toEqual([
      `${TEAM_A_NAME}:1:${ATHLETE_1_NAME}=none`,
      `${TEAM_B_NAME}:0:`,
    ]);
  });

  it("keeps a coached team with no consenting athlete as an empty team", () => {
    // Distinguishable from "you coach no team", which decision 7 requires.
    const composed = composeCoachReview({
      teams: COACHED_TEAMS,
      pairs: [],
      profileRows: [],
    });

    expect(outcome(composed)).toBe("ok");
    expect(composed.ok ? summarize(composed.value) : []).toEqual([
      `${TEAM_A_NAME}:0:`,
      `${TEAM_B_NAME}:0:`,
    ]);
  });

  it("orders teams then athletes stably", () => {
    const composed = composeCoachReview({
      teams: [...COACHED_TEAMS].reverse(),
      pairs: [
        { teamId: TEAM_A, athleteProfileId: ATHLETE_2 },
        { teamId: TEAM_A, athleteProfileId: ATHLETE_1 },
      ],
      profileRows: [
        profileRow({ id: ATHLETE_2, display_name: ATHLETE_2_NAME }),
        profileRow(),
      ],
    });

    expect(outcome(composed)).toBe("ok");
    expect(composed.ok ? summarize(composed.value) : []).toEqual([
      `${TEAM_A_NAME}:2:${ATHLETE_1_NAME}=present,${ATHLETE_2_NAME}=present`,
      `${TEAM_B_NAME}:0:`,
    ]);
  });

  it("rejects every malformed profile or check-in shape", () => {
    const cases: readonly (readonly [string, unknown])[] = [
      ["rows-not-an-array", null],
      ["missing-profile", []],
      ["extra-profile", [profileRow(), profileRow({ id: ATHLETE_2 })]],
      ["duplicate-profile", [profileRow(), profileRow()]],
      ["wrong-profile", [profileRow({ id: ATHLETE_2 })]],
      ["missing-id", [profileRow({ id: undefined })]],
      ["null-display-name", [profileRow({ display_name: null })]],
      ["blank-display-name", [profileRow({ display_name: "  " })]],
      ["embed-not-an-array", [profileRow({ daily_check_ins: null })]],
      ["embed-is-an-object", [profileRow({ daily_check_ins: checkInRow() })]],
      [
        "two-embedded-rows",
        [profileRow({ daily_check_ins: [checkInRow(), checkInRow()] })],
      ],
      [
        "missing-date",
        [
          profileRow({
            daily_check_ins: [checkInRow({ check_in_date: null })],
          }),
        ],
      ],
      [
        "impossible-date",
        [
          profileRow({
            daily_check_ins: [checkInRow({ check_in_date: "2026-02-30" })],
          }),
        ],
      ],
      [
        "timestamp-not-a-date",
        [
          profileRow({
            daily_check_ins: [
              checkInRow({ check_in_date: "2026-07-30T00:00:00Z" }),
            ],
          }),
        ],
      ],
      [
        "rpe-out-of-range",
        [profileRow({ daily_check_ins: [checkInRow({ rpe: 11 })] })],
      ],
      [
        "rpe-fractional",
        [profileRow({ daily_check_ins: [checkInRow({ rpe: 6.5 })] })],
      ],
      [
        "rpe-missing",
        [profileRow({ daily_check_ins: [checkInRow({ rpe: undefined })] })],
      ],
      [
        "feeling-out-of-range",
        [profileRow({ daily_check_ins: [checkInRow({ overall_feeling: 0 })] })],
      ],
      [
        "pain-unknown",
        [
          profileRow({
            daily_check_ins: [checkInRow({ pain_status: "mild" })],
          }),
        ],
      ],
      [
        "pain-miscased",
        [
          profileRow({
            daily_check_ins: [checkInRow({ pain_status: "None" })],
          }),
        ],
      ],
    ];

    const accepted = cases
      .filter(
        ([, profileRows]) =>
          composeCoachReview({
            teams: COACHED_TEAMS,
            pairs: pairsA,
            profileRows,
          }).ok,
      )
      .map(([name]) => name);

    // Case names only. No row, value, or date reaches this assertion.
    expect(accepted).toEqual([]);
  });

  it("rejects a pair naming a team that is not in the coached list", () => {
    // The forged-relation case, asserted at the composition boundary as well as
    // at the stage-b boundary.
    const composed = composeCoachReview({
      teams: COACHED_TEAMS,
      pairs: [{ teamId: TEAM_UNCOACHED, athleteProfileId: ATHLETE_1 }],
      profileRows: [profileRow()],
    });

    expect(outcome(composed)).toBe("invalid");
  });
});

describe("athleteIdsToRead", () => {
  it("deduplicates while preserving first-seen order", () => {
    const ids = athleteIdsToRead([
      { teamId: TEAM_A, athleteProfileId: ATHLETE_1 },
      { teamId: TEAM_B, athleteProfileId: ATHLETE_1 },
      { teamId: TEAM_A, athleteProfileId: ATHLETE_2 },
    ]);

    expect(ids.map(label)).toEqual(["athlete-1", "athlete-2"]);
  });

  it("is empty for no pairs, so no profile read is warranted", () => {
    expect(athleteIdsToRead([]).length).toBe(0);
  });
});
