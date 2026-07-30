import { describe, expect, it } from "vitest";

import {
  CHECK_IN_CATEGORY,
  parseCheckInSharingList,
  resolveSharingTarget,
  targetTeamId,
  type SharingListParse,
  type TeamSharingState,
} from "./domain";

/**
 * The validation and composition rules, tested as pure functions.
 *
 * **Failure-output safety.** Sharing metadata is not a health measurement but it is
 * sensitive authorization data, so nothing here lets a team id, a team name, a
 * grant object, or a whole row reach an assertion:
 *
 * - team ids are reduced to the fixed case labels `A`, `B`, `C`, or `unknown` by
 *   `label`, so a forged or unexpected id prints as `unknown` rather than as
 *   itself;
 * - a parsed list is reduced to strings like `A:on`, and a rejection to the single
 *   word `rejected`;
 * - team names are compared privately by `namesMatch`, which returns a boolean;
 * - sets of cases are asserted as lists of **case names**.
 *
 * All identifiers and names are synthetic.
 */

const TEAM_A = "00000000-0000-4000-8000-00000000000a";
const TEAM_B = "00000000-0000-4000-8000-00000000000b";
const TEAM_C = "00000000-0000-4000-8000-00000000000c";
const FORGED_TEAM = "00000000-0000-4000-8000-0000000000ff";

const NAME_A = "Alpha Runners";
const NAME_B = "Beta Runners";
const NAME_C = "Gamma Runners";

const LABELS = new Map<string, string>([
  [TEAM_A, "A"],
  [TEAM_B, "B"],
  [TEAM_C, "C"],
]);

/** A safe case name for a synthetic id. Anything unexpected becomes `unknown`. */
function label(teamId: string): string {
  return LABELS.get(teamId) ?? "unknown";
}

/** Safe: case labels and on/off only. Never an id, a name, or a row. */
function summarize(parse: SharingListParse): readonly string[] {
  return parse.ok
    ? parse.value.map(
        (team) => `${label(team.teamId)}:${team.sharing ? "on" : "off"}`,
      )
    : ["rejected"];
}

/** Compared privately so a mismatch cannot print either side's team names. */
function namesMatch(
  parse: SharingListParse,
  expected: readonly (readonly [string, string])[],
): boolean {
  if (!parse.ok || parse.value.length !== expected.length) {
    return false;
  }

  return expected.every(([teamId, name], index) => {
    const team = parse.value[index];

    return (
      team !== undefined && team.teamId === teamId && team.teamName === name
    );
  });
}

function membershipRow(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    team_id: TEAM_A,
    role: "athlete",
    status: "active",
    teams: { name: NAME_A },
    ...overrides,
  };
}

function grantRow(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return { team_id: TEAM_A, data_category: CHECK_IN_CATEGORY, ...overrides };
}

function parse(membershipRows: unknown, grantRows: unknown): SharingListParse {
  return parseCheckInSharingList({ membershipRows, grantRows });
}

describe("parseCheckInSharingList, accepted responses", () => {
  it("treats no membership as a real empty answer, not a rejection", () => {
    // The empty state and a load failure must never look alike. This is the empty
    // state: the caller holds no active athlete membership.
    const result = parse([], []);

    expect(result.ok).toBe(true);
    expect(summarize(result)).toEqual([]);
  });

  it("reports a team with no grant as not sharing", () => {
    // A missing grant means off, and reading it creates nothing.
    expect(summarize(parse([membershipRow()], []))).toEqual(["A:off"]);
  });

  it("reports a team with an active grant as sharing", () => {
    expect(summarize(parse([membershipRow()], [grantRow()]))).toEqual(["A:on"]);
  });

  it("keeps each team's state independent", () => {
    // A grant for Team A must leave Team B off, which is the whole point of a
    // per-team control.
    const result = parse(
      [
        membershipRow(),
        membershipRow({ team_id: TEAM_B, teams: { name: NAME_B } }),
      ],
      [grantRow()],
    );

    expect(summarize(result)).toEqual(["A:on", "B:off"]);
  });

  it("keeps a Team B grant off Team A", () => {
    const result = parse(
      [
        membershipRow(),
        membershipRow({ team_id: TEAM_B, teams: { name: NAME_B } }),
      ],
      [grantRow({ team_id: TEAM_B })],
    );

    expect(summarize(result)).toEqual(["A:off", "B:on"]);
  });

  it("labels every team by name, never by identifier", () => {
    const result = parse(
      [
        membershipRow(),
        membershipRow({ team_id: TEAM_B, teams: { name: NAME_B } }),
      ],
      [],
    );

    expect(
      namesMatch(result, [
        [TEAM_A, NAME_A],
        [TEAM_B, NAME_B],
      ]),
    ).toBe(true);
  });

  it("orders by team name so the section does not reshuffle", () => {
    const result = parse(
      [
        membershipRow({ team_id: TEAM_C, teams: { name: NAME_C } }),
        membershipRow(),
        membershipRow({ team_id: TEAM_B, teams: { name: NAME_B } }),
      ],
      [],
    );

    expect(summarize(result)).toEqual(["A:off", "B:off", "C:off"]);
  });

  it("orders two identically named teams stably by identifier", () => {
    const result = parse(
      [
        membershipRow({ team_id: TEAM_B, teams: { name: NAME_A } }),
        membershipRow({ team_id: TEAM_A, teams: { name: NAME_A } }),
      ],
      [],
    );

    expect(summarize(result)).toEqual(["A:off", "B:off"]);
  });

  it("is stable across repeated parses of the same response", () => {
    const memberships = [
      membershipRow({ team_id: TEAM_B, teams: { name: NAME_B } }),
      membershipRow(),
    ];

    expect(summarize(parse(memberships, [grantRow()]))).toEqual(
      summarize(parse(memberships, [grantRow()])),
    );
  });

  it("accepts a to-one embed shaped as a single-element array", () => {
    // Some builder and version combinations shape a to-one embed as an array.
    const result = parse([membershipRow({ teams: [{ name: NAME_A }] })], []);

    expect(summarize(result)).toEqual(["A:off"]);
    expect(namesMatch(result, [[TEAM_A, NAME_A]])).toBe(true);
  });

  it("trims nothing and accepts a name with inner spacing", () => {
    const result = parse([membershipRow({ teams: { name: "  Alpha  " } })], []);

    expect(namesMatch(result, [[TEAM_A, "  Alpha  "]])).toBe(true);
  });
});

describe("parseCheckInSharingList, rejected responses", () => {
  /**
   * Every case here must fail closed. The assertion is a list of **case names**,
   * so a regression prints which rule stopped holding and nothing else.
   */
  const CASES: readonly (readonly [
    name: string,
    memberships: unknown,
    grants: unknown,
  ])[] = [
    // Shape of the responses themselves.
    ["memberships-null", null, []],
    ["memberships-undefined", undefined, []],
    ["memberships-object", { length: 0 }, []],
    ["memberships-string", "", []],
    ["grants-null", [membershipRow()], null],
    ["grants-undefined", [membershipRow()], undefined],
    ["grants-object", [membershipRow()], { length: 0 }],

    // Malformed membership rows.
    ["membership-row-null", [null], []],
    ["membership-row-string", ["team"], []],
    ["membership-row-number", [1], []],
    ["membership-missing-team-id", [membershipRow({ team_id: undefined })], []],
    ["membership-null-team-id", [membershipRow({ team_id: null })], []],
    ["membership-empty-team-id", [membershipRow({ team_id: "" })], []],
    ["membership-blank-team-id", [membershipRow({ team_id: "   " })], []],
    ["membership-numeric-team-id", [membershipRow({ team_id: 7 })], []],

    // Unexpected role or status. The query filters on both; a response that
    // disagrees with the filter is refused rather than trusted.
    ["membership-role-coach", [membershipRow({ role: "coach" })], []],
    ["membership-role-missing", [membershipRow({ role: undefined })], []],
    ["membership-role-null", [membershipRow({ role: null })], []],
    ["membership-role-cased", [membershipRow({ role: "Athlete" })], []],
    ["membership-status-revoked", [membershipRow({ status: "revoked" })], []],
    ["membership-status-missing", [membershipRow({ status: undefined })], []],
    ["membership-status-cased", [membershipRow({ status: "Active" })], []],

    // Missing or inaccessible team name. RLS returns null for a team row the
    // caller cannot see, and a raw id must never become the label.
    ["team-embed-null", [membershipRow({ teams: null })], []],
    ["team-embed-missing", [membershipRow({ teams: undefined })], []],
    ["team-embed-empty-object", [membershipRow({ teams: {} })], []],
    ["team-name-null", [membershipRow({ teams: { name: null } })], []],
    ["team-name-empty", [membershipRow({ teams: { name: "" } })], []],
    ["team-name-blank", [membershipRow({ teams: { name: "   " } })], []],
    ["team-name-number", [membershipRow({ teams: { name: 42 } })], []],
    ["team-embed-empty-array", [membershipRow({ teams: [] })], []],
    [
      "team-embed-two-rows",
      [membershipRow({ teams: [{ name: NAME_A }, { name: NAME_B }] })],
      [],
    ],
    ["team-embed-array-bad-name", [membershipRow({ teams: [{}] })], []],

    // Duplicate active state. team_memberships is unique on (team_id,
    // profile_id) and one active grant per team/athlete/category is enforced by
    // a partial unique index, so a duplicate means the response is not the
    // database's state.
    ["duplicate-membership", [membershipRow(), membershipRow()], []],
    ["duplicate-grant", [membershipRow()], [grantRow(), grantRow()]],

    // Malformed grant rows and a category that is not check_in.
    ["grant-row-null", [membershipRow()], [null]],
    ["grant-row-string", [membershipRow()], ["grant"]],
    [
      "grant-missing-team-id",
      [membershipRow()],
      [grantRow({ team_id: undefined })],
    ],
    ["grant-empty-team-id", [membershipRow()], [grantRow({ team_id: "" })]],
    ["grant-numeric-team-id", [membershipRow()], [grantRow({ team_id: 7 })]],
    [
      "grant-category-workout",
      [membershipRow()],
      [grantRow({ data_category: "workout_summary" })],
    ],
    [
      "grant-category-sleep",
      [membershipRow()],
      [grantRow({ data_category: "sleep_summary" })],
    ],
    [
      "grant-category-missing",
      [membershipRow()],
      [grantRow({ data_category: undefined })],
    ],
    [
      "grant-category-null",
      [membershipRow()],
      [grantRow({ data_category: null })],
    ],
    [
      "grant-category-cased",
      [membershipRow()],
      [grantRow({ data_category: "CHECK_IN" })],
    ],

    // A grant naming a team with no active athlete membership. The TASK-011
    // membership trigger makes this combination impossible in committed state.
    [
      "grant-for-unowned-team",
      [membershipRow()],
      [grantRow({ team_id: TEAM_B })],
    ],
    ["grant-with-no-membership", [], [grantRow()]],
    [
      "grant-for-forged-team",
      [membershipRow()],
      [grantRow({ team_id: FORGED_TEAM })],
    ],

    // One good row and one bad row must not yield a partial list.
    [
      "one-good-one-malformed-membership",
      [membershipRow(), membershipRow({ team_id: TEAM_B, teams: null })],
      [],
    ],
    [
      "one-good-one-malformed-grant",
      [
        membershipRow(),
        membershipRow({ team_id: TEAM_B, teams: { name: NAME_B } }),
      ],
      [
        grantRow(),
        grantRow({ team_id: TEAM_B, data_category: "sleep_summary" }),
      ],
    ],
  ];

  it("fails closed on every malformed or inconsistent response", () => {
    const accepted = CASES.filter(
      ([, memberships, grants]) => parse(memberships, grants).ok,
    ).map(([name]) => name);

    // Case names only.
    expect(accepted).toEqual([]);
  });

  it("never yields a partial list when it rejects", () => {
    const leaked = CASES.filter(
      ([, memberships, grants]) =>
        summarize(parse(memberships, grants)).join(",") !== "rejected",
    ).map(([name]) => name);

    expect(leaked).toEqual([]);
  });

  it("covers every rule with at least one case", () => {
    // Guards against the table being emptied and the file passing vacuously.
    expect(CASES.length).toBeGreaterThan(40);
  });
});

describe("resolveSharingTarget", () => {
  const TEAMS: readonly TeamSharingState[] = [
    { teamId: TEAM_A, teamName: NAME_A, sharing: false },
    { teamId: TEAM_B, teamName: NAME_B, sharing: true },
  ];

  it("resolves a team the server returned", () => {
    const target = resolveSharingTarget(TEAM_A, TEAMS);

    expect(target === null).toBe(false);
    // Compared privately so only a boolean is asserted.
    expect(target !== null && targetTeamId(target) === TEAM_A).toBe(true);
  });

  it("resolves each loaded team independently", () => {
    const resolved = TEAMS.map((team) => {
      const target = resolveSharingTarget(team.teamId, TEAMS);

      return target === null ? "unresolved" : label(targetTeamId(target));
    });

    expect(resolved).toEqual(["A", "B"]);
  });

  it("refuses an id the server did not return", () => {
    // The forged/unowned team-id case. No RPC can be built from it.
    const refused: readonly (readonly [string, unknown])[] = [
      ["forged", FORGED_TEAM],
      ["other-team", TEAM_C],
      ["empty", ""],
      ["blank", "   "],
      ["undefined", undefined],
      ["null", null],
      ["number", 7],
      ["object", { teamId: TEAM_A }],
      ["array", [TEAM_A]],
    ];

    const accepted = refused
      .filter(
        ([, candidate]) => resolveSharingTarget(candidate, TEAMS) !== null,
      )
      .map(([name]) => name);

    // Case names only.
    expect(accepted).toEqual([]);
  });

  it("refuses everything when no team is loaded", () => {
    expect(resolveSharingTarget(TEAM_A, []) === null).toBe(true);
  });

  it("refuses a team that disappeared from a later load", () => {
    // A revoked membership stops being returned, so its control and its write
    // capability both go away on the next successful load.
    const afterRevocation = TEAMS.filter((team) => team.teamId !== TEAM_B);

    expect(resolveSharingTarget(TEAM_B, afterRevocation) === null).toBe(true);
    expect(resolveSharingTarget(TEAM_A, afterRevocation) === null).toBe(false);
  });
});

describe("the category constant", () => {
  it("is exactly check_in", () => {
    expect(CHECK_IN_CATEGORY).toBe("check_in");
  });
});
