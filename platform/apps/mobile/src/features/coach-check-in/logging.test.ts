import { describe, expect, it, vi } from "vitest";

import { loadCoachCheckInReview } from "./coach-review-repository";
import {
  MAX_SHARING_PAIRS,
  composeCoachReview,
  parseCoachedTeams,
  parseGrantPairs,
} from "./domain";
import {
  CoachReviewDataError,
  coachReviewErrorFrom,
  coachReviewErrorMessage,
} from "./errors";
import { probeFailure } from "./failure-probe";
import {
  ATHLETE_1,
  COACH_ID,
  TEAM_A,
  TEAM_A_NAME,
  TEAM_UNCOACHED,
  checkInRow,
  clientDouble,
  grantRow,
  membershipRow,
  profileRow,
  rawServerError,
} from "./test-fixtures";
import { readCoachReviewView, visibleTeams } from "./view-state";

/**
 * Proves at runtime that nothing in the feature writes to a console channel.
 *
 * The source scan in `source-safety.test.ts` shows no log call is *written*; this
 * shows none *happens*, including on the failure paths — a refused read at each
 * stage, a rejected transport, a malformed response, an over-capacity response, and
 * an unsanitized error reaching the view derivation — which are exactly where a
 * careless edit would add one "just for debugging" and put an RPE, a pain status, a
 * recorded date, an athlete id, or a raw refusal into a log, a crash report, or
 * session replay.
 *
 * Only a call count is asserted, so a failure reveals nothing.
 */

const CHANNELS = ["log", "info", "warn", "error", "debug", "trace"] as const;

async function countConsoleCalls(run: () => Promise<void>): Promise<number> {
  const spies = CHANNELS.map((channel) =>
    vi.spyOn(console, channel).mockImplementation(() => undefined),
  );

  try {
    await run();

    // Counted here, before the `finally` restores the spies. `mockRestore` also
    // resets the mock, which clears `mock.calls`, so reading the totals after it
    // would report zero unconditionally and the whole file would pass vacuously.
    return spies.reduce((total, spy) => total + spy.mock.calls.length, 0);
  } finally {
    for (const spy of spies) {
      spy.mockRestore();
    }
  }
}

describe("nothing in the coach-review feature reaches a log", () => {
  it("stays silent across the pure paths", async () => {
    const calls = await countConsoleCalls(async () => {
      parseCoachedTeams([membershipRow()]);
      parseCoachedTeams(null);
      parseCoachedTeams([membershipRow({ teams: null })]);

      const coached = new Set([TEAM_A]);

      parseGrantPairs({
        rows: [grantRow()],
        coachedTeamIds: coached,
        callerUserId: COACH_ID,
      });
      parseGrantPairs({
        rows: [grantRow({ team_id: TEAM_UNCOACHED })],
        coachedTeamIds: coached,
        callerUserId: COACH_ID,
      });
      parseGrantPairs({
        rows: [grantRow({ athlete_profile_id: COACH_ID })],
        coachedTeamIds: coached,
        callerUserId: COACH_ID,
      });
      parseGrantPairs({
        rows: Array.from({ length: MAX_SHARING_PAIRS + 1 }, () => grantRow()),
        coachedTeamIds: coached,
        callerUserId: COACH_ID,
      });

      composeCoachReview({
        teams: [{ teamId: TEAM_A, teamName: TEAM_A_NAME }],
        pairs: [{ teamId: TEAM_A, athleteProfileId: ATHLETE_1 }],
        profileRows: [profileRow()],
      });
      composeCoachReview({
        teams: [{ teamId: TEAM_A, teamName: TEAM_A_NAME }],
        pairs: [{ teamId: TEAM_A, athleteProfileId: ATHLETE_1 }],
        profileRows: [
          profileRow({ daily_check_ins: [checkInRow({ rpe: 99 })] }),
        ],
      });

      coachReviewErrorMessage(coachReviewErrorFrom("load", rawServerError()));
      coachReviewErrorMessage(rawServerError());
      coachReviewErrorMessage(undefined);

      await Promise.resolve();
    });

    expect(calls).toBe(0);
  });

  it("stays silent when each stage is refused", async () => {
    const refusal = { error: { code: "42501" } } as const;

    const calls = await countConsoleCalls(async () => {
      await probeFailure(
        loadCoachCheckInReview(
          clientDouble({ team_memberships: refusal }).client,
          COACH_ID,
        ),
      );
      await probeFailure(
        loadCoachCheckInReview(
          clientDouble({
            team_memberships: { data: [membershipRow()] },
            sharing_grants: refusal,
          }).client,
          COACH_ID,
        ),
      );
      await probeFailure(
        loadCoachCheckInReview(
          clientDouble({
            team_memberships: { data: [membershipRow()] },
            sharing_grants: { data: [grantRow()] },
            profiles: refusal,
          }).client,
          COACH_ID,
        ),
      );
    });

    expect(calls).toBe(0);
  });

  it("stays silent when a read rejects with a raw server error", async () => {
    // `rawServerError` carries a policy name, an athlete id, an RPE, details, a
    // hint, and a cause. None of it may reach a console channel.
    const calls = await countConsoleCalls(async () => {
      await probeFailure(
        loadCoachCheckInReview(
          clientDouble({
            team_memberships: { data: [membershipRow()] },
            sharing_grants: { data: [grantRow()] },
            profiles: { reject: rawServerError() },
          }).client,
          COACH_ID,
        ),
      );
    });

    expect(calls).toBe(0);
  });

  it("stays silent when a client method throws synchronously", async () => {
    const calls = await countConsoleCalls(async () => {
      await probeFailure(
        loadCoachCheckInReview(
          clientDouble({
            team_memberships: { throwSync: rawServerError() },
          }).client,
          COACH_ID,
        ),
      );
    });

    expect(calls).toBe(0);
  });

  it("stays silent when there is no verified identity", async () => {
    const calls = await countConsoleCalls(async () => {
      await probeFailure(
        loadCoachCheckInReview(
          clientDouble({ team_memberships: { data: [] } }).client,
          "",
        ),
      );
    });

    expect(calls).toBe(0);
  });

  it("stays silent while the view derivation handles every state", async () => {
    const calls = await countConsoleCalls(async () => {
      for (const state of [
        { data: undefined, isFetching: true, isError: false, error: null },
        {
          data: [],
          isFetching: true,
          isError: false,
          error: null,
        },
        {
          data: [],
          isFetching: false,
          isError: true,
          error: new CoachReviewDataError("load", "capacity"),
        },
        {
          data: [],
          isFetching: false,
          isError: true,
          // An unsanitized error reaching the view is the worst case, so it is
          // exercised here too.
          error: rawServerError(),
        },
      ]) {
        visibleTeams(readCoachReviewView(state));
      }

      await Promise.resolve();
    });

    expect(calls).toBe(0);
  });
});
