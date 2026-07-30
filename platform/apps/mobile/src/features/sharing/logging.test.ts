import { describe, expect, it, vi } from "vitest";

import type { AppSupabaseClient } from "../../lib/supabase/app-client";

import { planSharingAction } from "./action-plan";
import {
  parseCheckInSharingList,
  resolveSharingTarget,
  type SharingTarget,
  type TeamSharingState,
} from "./domain";
import { sharingErrorFrom, sharingErrorMessage } from "./errors";
import { sharingActionMutationOptions } from "./query-options";
import {
  grantCheckInSharing,
  loadCheckInSharing,
  revokeCheckInSharing,
} from "./sharing-repository";

/**
 * Proves at runtime that nothing in the feature writes to a console channel.
 *
 * The source scan in `source-safety.test.ts` shows no log call is written; this
 * shows none *happens*, including on the failure paths — a refused read, a refused
 * RPC, a rejected transport, a malformed response, and a forged team id — which are
 * exactly where a careless edit would add one "just for debugging" and put a team
 * id, a user id, a raw refusal, or the RPC arguments into a log, a crash report, or
 * session replay.
 *
 * Only a call count is asserted, so a failure reveals nothing.
 */

const USER_ID = "00000000-0000-4000-9000-000000000014";
const TEAM_A = "00000000-0000-4000-8000-00000000000a";
const FORGED_TEAM = "00000000-0000-4000-8000-0000000000ff";

const TEAMS: readonly TeamSharingState[] = [
  { teamId: TEAM_A, teamName: "Alpha Runners", sharing: false },
];

const CHANNELS = ["log", "info", "warn", "error", "debug", "trace"] as const;

/** Non-null by construction. */
function target(): SharingTarget {
  const resolved = resolveSharingTarget(TEAM_A, TEAMS);

  if (resolved === null) {
    throw new Error("test fixture: team is not in the loaded list");
  }

  return resolved;
}

/**
 * A raw server error carrying everything that must never be logged: a message
 * naming the function and a team id, plus details, hint, and cause.
 */
function rawServerError(): Error {
  return Object.assign(
    new Error(
      "permission denied for function revoke_team_data_sharing: active athlete membership required",
    ),
    {
      code: "42501",
      details: "active athlete membership required",
      hint: "sharing_grants_select_own_history",
      cause: { p_team_id: TEAM_A },
    },
  );
}

/** A client double whose every read and RPC is refused. */
function refusingClient(): AppSupabaseClient {
  const builder = {
    select: () => builder,
    eq: () => builder,
    is: () => builder,
    then: (
      onfulfilled?: (value: { data: unknown; error: unknown }) => unknown,
    ) =>
      Promise.resolve({ data: null, error: { code: "42501" } }).then(
        onfulfilled,
      ),
  };

  return {
    from: () => builder,
    rpc: () => ({
      then: (onfulfilled?: (value: unknown) => unknown) =>
        Promise.resolve({ data: null, error: { code: "42501" } }).then(
          onfulfilled,
        ),
    }),
  } as unknown as AppSupabaseClient;
}

/** A client double that rejects with a raw, detail-bearing server error. */
function rejectingClient(): AppSupabaseClient {
  const rejecting = {
    select: () => rejecting,
    eq: () => rejecting,
    is: () => rejecting,
    then: (_onfulfilled?: unknown, onrejected?: (reason: unknown) => unknown) =>
      Promise.reject(rawServerError()).then(undefined, onrejected),
  };

  return {
    from: () => rejecting,
    rpc: () => rejecting,
  } as unknown as AppSupabaseClient;
}

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

describe("nothing in the sharing feature reaches a log", () => {
  it("stays silent across the pure paths", async () => {
    const calls = await countConsoleCalls(async () => {
      parseCheckInSharingList({
        membershipRows: [
          {
            team_id: TEAM_A,
            role: "athlete",
            status: "active",
            teams: { name: "Alpha Runners" },
          },
        ],
        grantRows: [{ team_id: TEAM_A, data_category: "check_in" }],
      });
      parseCheckInSharingList({ membershipRows: null, grantRows: null });
      parseCheckInSharingList({
        membershipRows: [{ team_id: TEAM_A, role: "coach", status: "active" }],
        grantRows: [],
      });
      resolveSharingTarget(TEAM_A, TEAMS);
      resolveSharingTarget(FORGED_TEAM, TEAMS);
      planSharingAction({ busy: false, teams: TEAMS, teamId: TEAM_A });
      planSharingAction({ busy: true, teams: TEAMS, teamId: FORGED_TEAM });
      sharingErrorMessage(sharingErrorFrom("grant", { code: "42501" }));
      sharingErrorMessage(rawServerError());

      await Promise.resolve();
    });

    expect(calls).toBe(0);
  });

  it("stays silent when both reads are refused", async () => {
    const calls = await countConsoleCalls(async () => {
      await loadCheckInSharing(refusingClient(), USER_ID).catch(
        () => undefined,
      );
    });

    expect(calls).toBe(0);
  });

  it("stays silent when a read rejects with a raw server error", async () => {
    const calls = await countConsoleCalls(async () => {
      await loadCheckInSharing(rejectingClient(), USER_ID).catch(
        () => undefined,
      );
    });

    expect(calls).toBe(0);
  });

  it("stays silent when there is no verified identity", async () => {
    const calls = await countConsoleCalls(async () => {
      await loadCheckInSharing(refusingClient(), "").catch(() => undefined);
    });

    expect(calls).toBe(0);
  });

  it("stays silent when a grant is refused", async () => {
    const calls = await countConsoleCalls(async () => {
      await grantCheckInSharing(refusingClient(), target()).catch(
        () => undefined,
      );
    });

    expect(calls).toBe(0);
  });

  it("stays silent when a grant rejects with a raw server error", async () => {
    const calls = await countConsoleCalls(async () => {
      await grantCheckInSharing(rejectingClient(), target()).catch(
        () => undefined,
      );
    });

    expect(calls).toBe(0);
  });

  it("stays silent when a revoke is refused", async () => {
    const calls = await countConsoleCalls(async () => {
      await revokeCheckInSharing(refusingClient(), target()).catch(
        () => undefined,
      );
    });

    expect(calls).toBe(0);
  });

  it("stays silent when an action is refused before any request", async () => {
    const options = sharingActionMutationOptions({
      userId: undefined,
      teams: TEAMS,
      grant: () => Promise.resolve(),
      revoke: () => Promise.resolve(),
      refetchKey: () => Promise.resolve(),
    });

    const calls = await countConsoleCalls(async () => {
      await options
        .mutationFn({ teamId: TEAM_A, action: "grant" })
        .catch(() => undefined);
      await options
        .mutationFn({ teamId: FORGED_TEAM, action: "revoke" })
        .catch(() => undefined);
    });

    expect(calls).toBe(0);
  });
});
