import { describe, expect, it } from "vitest";

import { planSharingAction } from "./action-plan";
import type { TeamSharingState } from "./domain";

/**
 * The press decision, tested as a pure function.
 *
 * **Failure-output safety.** A plan is reduced to a short fixed string — `busy`,
 * `unknown-team`, `A:grant`, `B:revoke` — before it reaches an assertion, so no
 * team id and no variables object is ever printed. Team ids are mapped to the case
 * labels `A`, `B`, `C`, or `unknown`.
 *
 * All identifiers and names are synthetic.
 */

const TEAM_A = "00000000-0000-4000-8000-00000000000a";
const TEAM_B = "00000000-0000-4000-8000-00000000000b";
const FORGED_TEAM = "00000000-0000-4000-8000-0000000000ff";

const LABELS = new Map<string, string>([
  [TEAM_A, "A"],
  [TEAM_B, "B"],
]);

const TEAMS: readonly TeamSharingState[] = [
  { teamId: TEAM_A, teamName: "Alpha Runners", sharing: false },
  { teamId: TEAM_B, teamName: "Beta Runners", sharing: true },
];

/** Safe: a case label plus a direction, or the refusal reason. */
function outcome(args: {
  readonly busy: boolean;
  readonly teams: readonly TeamSharingState[];
  readonly teamId: string;
}): string {
  const plan = planSharingAction(args);

  return plan.accepted
    ? `${LABELS.get(plan.variables.teamId) ?? "unknown"}:${plan.variables.action}`
    : plan.reason;
}

describe("planSharingAction", () => {
  it("grants for a team that is not sharing", () => {
    expect(outcome({ busy: false, teams: TEAMS, teamId: TEAM_A })).toBe(
      "A:grant",
    );
  });

  it("revokes for a team that is sharing", () => {
    expect(outcome({ busy: false, teams: TEAMS, teamId: TEAM_B })).toBe(
      "B:revoke",
    );
  });

  it("takes the direction from the loaded state, never from the press", () => {
    // The same press on the same team yields the opposite direction once the
    // server-confirmed state changes, so a control rendered from stale data cannot
    // ask to grant what is already granted.
    const afterGrant: readonly TeamSharingState[] = [
      { teamId: TEAM_A, teamName: "Alpha Runners", sharing: true },
    ];

    expect(outcome({ busy: false, teams: afterGrant, teamId: TEAM_A })).toBe(
      "A:revoke",
    );
  });

  it("refuses a duplicate press while an action is in flight", () => {
    expect(outcome({ busy: true, teams: TEAMS, teamId: TEAM_A })).toBe("busy");
  });

  it("refuses a press on another team while an action is in flight", () => {
    // One in-flight action blocks every control, so a Team A action can never be
    // interleaved with a Team B one.
    expect(outcome({ busy: true, teams: TEAMS, teamId: TEAM_B })).toBe("busy");
  });

  it("refuses a team the server did not return", () => {
    const refused: readonly (readonly [string, string])[] = [
      ["forged", FORGED_TEAM],
      ["empty", ""],
      ["blank", "   "],
    ];

    expect(
      refused.map(([name, teamId]) => [
        name,
        outcome({ busy: false, teams: TEAMS, teamId }),
      ]),
    ).toEqual([
      ["forged", "unknown-team"],
      ["empty", "unknown-team"],
      ["blank", "unknown-team"],
    ]);
  });

  it("refuses every press when no team is loaded", () => {
    // The coach-only, pending, and load-failure cases all present an empty list.
    expect(outcome({ busy: false, teams: [], teamId: TEAM_A })).toBe(
      "unknown-team",
    );
  });

  it("refuses a team that disappeared from a later load", () => {
    // A revoked membership stops being returned, so its control loses both its row
    // and its ability to start an action.
    const afterRevocation = TEAMS.filter((team) => team.teamId !== TEAM_B);

    expect(
      outcome({ busy: false, teams: afterRevocation, teamId: TEAM_B }),
    ).toBe("unknown-team");
    expect(
      outcome({ busy: false, teams: afterRevocation, teamId: TEAM_A }),
    ).toBe("A:grant");
  });

  it("checks busy before the team, so a stale press cannot slip through", () => {
    expect(outcome({ busy: true, teams: [], teamId: FORGED_TEAM })).toBe(
      "busy",
    );
  });

  it("produces variables with exactly two fields and no health value", () => {
    const plan = planSharingAction({
      busy: false,
      teams: TEAMS,
      teamId: TEAM_A,
    });

    expect(plan.accepted).toBe(true);
    expect(plan.accepted ? Object.keys(plan.variables).sort() : []).toEqual([
      "action",
      "teamId",
    ]);
  });
});
