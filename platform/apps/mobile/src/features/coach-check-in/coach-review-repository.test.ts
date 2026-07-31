import { describe, expect, it } from "vitest";

import { loadCoachCheckInReview } from "./coach-review-repository";
import { MAX_SHARING_PAIRS } from "./domain";
import { probeFailure, summarize } from "./failure-probe";
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
  clientDouble,
  grantRow,
  membershipRow,
  profileRow,
  rawServerError,
  type StageBehaviour,
  type StageTable,
} from "./test-fixtures";

/**
 * The three-stage read, against injected Supabase doubles. No network, no local
 * database, no rendered tree.
 *
 * **Failure-output discipline.** A resolved list is reduced by `summarize` to team
 * labels, athlete labels, counts, and `present`/`none` before any assertion. A
 * rejection is reduced by `probeFailure` to a fixed vocabulary and the caught value
 * is discarded inside the probe — a raw PostgREST error, its `details`, its `hint`,
 * its `cause`, and the synthetic athlete id inside them are never returned,
 * rethrown, or stringified. The client recording holds table and method names only.
 */

const BOTH_TEAMS = [
  membershipRow(),
  membershipRow({ team_id: TEAM_B, teams: { name: TEAM_B_NAME } }),
];

function load(behaviours: Partial<Record<StageTable, StageBehaviour>>) {
  const double = clientDouble(behaviours);

  return {
    double,
    result: loadCoachCheckInReview(double.client, COACH_ID),
  };
}

/** A complete, valid three-stage response. */
function happyPath(
  overrides?: Partial<Record<StageTable, StageBehaviour>>,
): Partial<Record<StageTable, StageBehaviour>> {
  return {
    team_memberships: { data: BOTH_TEAMS },
    sharing_grants: { data: [grantRow()] },
    profiles: { data: [profileRow()] },
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// The success paths
// ---------------------------------------------------------------------------

describe("loadCoachCheckInReview success paths", () => {
  it("returns the latest shared check-in under its exact team", async () => {
    const { result } = load(happyPath());

    expect(summarize(await result)).toEqual([
      `${TEAM_A_NAME}:1:${ATHLETE_1_NAME}=present`,
      `${TEAM_B_NAME}:0:`,
    ]);
  });

  it("returns an empty list, not an error, when the caller coaches no team", async () => {
    const { double, result } = load({ team_memberships: { data: [] } });

    expect((await result).length).toBe(0);
    // Neither later stage was issued. `sharing_grants` is unconfigured, so a
    // repository that issued it would have thrown and this list would differ.
    expect(double.recording().tables).toEqual(["team_memberships"]);
  });

  it("does not issue the health-bearing read when nobody shares", async () => {
    // Decision 6, and the single most important assertion in this file: with no
    // active grant, no query for a protected value is ever sent.
    const { double, result } = load({
      team_memberships: { data: BOTH_TEAMS },
      sharing_grants: { data: [] },
    });

    expect(summarize(await result)).toEqual([
      `${TEAM_A_NAME}:0:`,
      `${TEAM_B_NAME}:0:`,
    ]);
    expect(double.recording().tables).toEqual([
      "team_memberships",
      "sharing_grants",
    ]);
  });

  it("reports an active grant with no check-in as the pending state", async () => {
    const { result } = load(
      happyPath({ profiles: { data: [profileRow({ daily_check_ins: [] })] } }),
    );

    expect(summarize(await result)).toEqual([
      `${TEAM_A_NAME}:1:${ATHLETE_1_NAME}=none`,
      `${TEAM_B_NAME}:0:`,
    ]);
  });

  it("materializes a multi-team athlete from one deduplicated profile read", async () => {
    const { result } = load(
      happyPath({
        sharing_grants: {
          data: [grantRow({ team_id: TEAM_A }), grantRow({ team_id: TEAM_B })],
        },
      }),
    );

    expect(summarize(await result)).toEqual([
      `${TEAM_A_NAME}:1:${ATHLETE_1_NAME}=present`,
      `${TEAM_B_NAME}:1:${ATHLETE_1_NAME}=present`,
    ]);
  });

  it("orders two athletes in one team stably", async () => {
    const { result } = load(
      happyPath({
        sharing_grants: {
          data: [
            grantRow({ athlete_profile_id: ATHLETE_2 }),
            grantRow({ athlete_profile_id: ATHLETE_1 }),
          ],
        },
        profiles: {
          data: [
            profileRow({ id: ATHLETE_2, display_name: ATHLETE_2_NAME }),
            profileRow(),
          ],
        },
      }),
    );

    expect(summarize(await result)).toEqual([
      `${TEAM_A_NAME}:2:${ATHLETE_1_NAME}=present,${ATHLETE_2_NAME}=present`,
      `${TEAM_B_NAME}:0:`,
    ]);
  });
});

// ---------------------------------------------------------------------------
// The query contract
// ---------------------------------------------------------------------------

describe("the query contract", () => {
  it("orders and limits the embedded relation on the referenced table", async () => {
    // Both halves. The order alone returns a whole history; the limit alone
    // returns an arbitrary row from it.
    const { double, result } = load(happyPath());

    await result;

    expect(double.recording().embeddedOptions).toEqual([
      "limit:101:none",
      "order:check_in_date:daily_check_ins:desc",
      "limit:1:daily_check_ins",
    ]);
  });

  it("reads the three tables in the fail-safe order", async () => {
    const { double, result } = load(happyPath());

    await result;

    expect(double.recording().tables).toEqual([
      "team_memberships",
      "sharing_grants",
      "profiles",
    ]);
  });

  it("never writes and never calls an RPC", async () => {
    const { double, result } = load(happyPath());

    await result;

    const recording = double.recording();

    // Counts only. The double owns real insert/update/upsert/delete methods, so
    // a write would be recorded rather than throwing and passing as a failure.
    expect(recording.writeCalls).toBe(0);
    expect(recording.rpcCalls).toBe(0);
  });

  it("issues no request at all without a verified identity", async () => {
    const double = clientDouble(happyPath());
    const probe = await probeFailure(loadCoachCheckInReview(double.client, ""));

    expect(probe.outcome).toBe("sanitized-error");
    expect(double.recording().tables).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Fail-closed behaviour
// ---------------------------------------------------------------------------

describe("loadCoachCheckInReview fails closed", () => {
  /** Every failure shape, reduced to `outcome|failure|messageIsFixed`. */
  async function describeFailure(
    behaviours: Partial<Record<StageTable, StageBehaviour>>,
  ): Promise<string> {
    const probe = await probeFailure(load(behaviours).result);

    return [
      probe.outcome,
      probe.failure ?? "none",
      probe.messageIsFixed ? "fixed" : "unfixed",
    ].join("|");
  }

  it("sanitizes a refusal at each stage", async () => {
    const refusal = { error: { code: "42501" } } as const;

    expect(await describeFailure({ team_memberships: refusal })).toBe(
      "sanitized-error|denied|fixed",
    );
    expect(await describeFailure(happyPath({ sharing_grants: refusal }))).toBe(
      "sanitized-error|denied|fixed",
    );
    expect(await describeFailure(happyPath({ profiles: refusal }))).toBe(
      "sanitized-error|denied|fixed",
    );
  });

  it("sanitizes a rejected builder carrying a raw server error", async () => {
    // The leak case. `rawServerError` holds a policy name, an athlete id, an RPE,
    // details, hint, and a cause; none of it may survive.
    const probe = await probeFailure(
      load(happyPath({ profiles: { reject: rawServerError() } })).result,
    );

    expect(probe.outcome).toBe("sanitized-error");
    expect(probe.messageIsFixed).toBe(true);
    expect(probe.withoutCause).toBe(true);
    // Field names only.
    expect(probe.fields).toEqual(["failure", "intent", "name"]);
  });

  it("sanitizes a synchronous throw", async () => {
    expect(
      await describeFailure(
        happyPath({ profiles: { throwSync: rawServerError() } }),
      ),
    ).toBe("sanitized-error|denied|fixed");
  });

  it("sanitizes a thenable that rejects with a non-error", async () => {
    expect(
      await describeFailure(happyPath({ profiles: { reject: "refused" } })),
    ).toBe("sanitized-error|unknown|fixed");
  });

  it("classifies a transport failure as offline, not as an empty list", async () => {
    const offline = Object.assign(new Error("network"), { name: "TypeError" });

    expect(
      await describeFailure({ team_memberships: { reject: offline } }),
    ).toBe("sanitized-error|offline|fixed");
  });

  it("refuses a Team A coach any association with an uncoached team", async () => {
    expect(
      await describeFailure(
        happyPath({
          sharing_grants: { data: [grantRow({ team_id: TEAM_UNCOACHED })] },
        }),
      ),
    ).toBe("sanitized-error|unknown|fixed");
  });

  it("refuses a grant for the wrong sharing category", async () => {
    expect(
      await describeFailure(
        happyPath({
          sharing_grants: {
            data: [grantRow({ data_category: "sleep_summary" })],
          },
        }),
      ),
    ).toBe("sanitized-error|unknown|fixed");
  });

  it("refuses an impossible self-targeted grant", async () => {
    expect(
      await describeFailure(
        happyPath({
          sharing_grants: {
            data: [grantRow({ athlete_profile_id: COACH_ID })],
          },
        }),
      ),
    ).toBe("sanitized-error|unknown|fixed");
  });

  it("refuses a duplicate grant and a duplicate embedded row", async () => {
    expect(
      await describeFailure(
        happyPath({ sharing_grants: { data: [grantRow(), grantRow()] } }),
      ),
    ).toBe("sanitized-error|unknown|fixed");

    expect(
      await describeFailure(
        happyPath({
          profiles: {
            data: [
              profileRow({ daily_check_ins: [checkInRow(), checkInRow()] }),
            ],
          },
        }),
      ),
    ).toBe("sanitized-error|unknown|fixed");
  });

  it("refuses a missing expected profile", async () => {
    expect(await describeFailure(happyPath({ profiles: { data: [] } }))).toBe(
      "sanitized-error|unknown|fixed",
    );
  });

  it("refuses a malformed membership, team name, and health value", async () => {
    expect(
      await describeFailure({
        team_memberships: { data: [membershipRow({ teams: null })] },
      }),
    ).toBe("sanitized-error|unknown|fixed");

    expect(
      await describeFailure({
        team_memberships: { data: [membershipRow({ role: "athlete" })] },
      }),
    ).toBe("sanitized-error|unknown|fixed");

    expect(
      await describeFailure(
        happyPath({
          profiles: { data: [profileRow({ display_name: null })] },
        }),
      ),
    ).toBe("sanitized-error|unknown|fixed");

    expect(
      await describeFailure(
        happyPath({
          profiles: {
            data: [profileRow({ daily_check_ins: [checkInRow({ rpe: 99 })] })],
          },
        }),
      ),
    ).toBe("sanitized-error|unknown|fixed");
  });

  it("refuses more than the maximum scope with capacity wording", async () => {
    const rows = Array.from(
      { length: MAX_SHARING_PAIRS + 1 },
      (_unused, index) =>
        grantRow({ athlete_profile_id: `athlete-${String(index)}` }),
    );

    // Not "unknown": the coach must not be told to retry a load that cannot
    // succeed, and the list must not be truncated to fit.
    expect(
      await describeFailure(happyPath({ sharing_grants: { data: rows } })),
    ).toBe("sanitized-error|capacity|fixed");
  });

  it("does not reach the health-bearing read when stage b is over capacity", async () => {
    const rows = Array.from(
      { length: MAX_SHARING_PAIRS + 1 },
      (_unused, index) =>
        grantRow({ athlete_profile_id: `athlete-${String(index)}` }),
    );

    const { double, result } = load({
      team_memberships: { data: BOTH_TEAMS },
      sharing_grants: { data: rows },
    });

    await probeFailure(result);

    expect(double.recording().tables).toEqual([
      "team_memberships",
      "sharing_grants",
    ]);
  });

  it("never returns a partial list when one pair is malformed", async () => {
    // Two consenting athletes, one malformed profile. The valid one must not be
    // rendered alone: a dropped athlete reads as "has not checked in".
    const probe = await probeFailure(
      load(
        happyPath({
          sharing_grants: {
            data: [grantRow(), grantRow({ athlete_profile_id: ATHLETE_2 })],
          },
          profiles: {
            data: [
              profileRow(),
              profileRow({ id: ATHLETE_2, display_name: "  " }),
            ],
          },
        }),
      ).result,
    );

    expect(probe.outcome).toBe("sanitized-error");
  });

  it("never carries a message that is not from the fixed table", async () => {
    // One aggregate sweep over every failure shape above.
    const behaviours: readonly Partial<Record<StageTable, StageBehaviour>>[] = [
      { team_memberships: { error: { code: "PGRST301" } } },
      { team_memberships: { reject: rawServerError() } },
      { team_memberships: { throwSync: rawServerError() } },
      happyPath({ sharing_grants: { reject: rawServerError() } }),
      happyPath({ profiles: { reject: rawServerError() } }),
      happyPath({ profiles: { data: "not-an-array" } }),
      happyPath({ sharing_grants: { data: null } }),
    ];

    const unfixed: number[] = [];

    for (const [index, behaviour] of behaviours.entries()) {
      const probe = await probeFailure(load(behaviour).result);

      if (probe.outcome !== "sanitized-error" || !probe.messageIsFixed) {
        unfixed.push(index);
      }
    }

    // Indices only.
    expect(unfixed).toEqual([]);
  });
});
