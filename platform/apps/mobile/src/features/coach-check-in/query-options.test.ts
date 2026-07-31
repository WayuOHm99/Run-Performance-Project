import { QueryClient, QueryObserver } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { clearAuthScopedQueries } from "../../lib/query/client";
import { authScopedKeys } from "../../lib/query/keys";

import type { CoachReviewTeam } from "./domain";
import { CoachReviewDataError } from "./errors";
import {
  ANONYMOUS_KEY_USER_ID,
  coachCheckInReviewQueryOptions,
} from "./query-options";
import {
  COACH_ID,
  OTHER_COACH_ID,
  TEAM_A,
  TEAM_A_NAME,
  ATHLETE_1,
  ATHLETE_1_NAME,
} from "./test-fixtures";
import { readCoachReviewView, visibleTeams } from "./view-state";

/**
 * The cache contract, exercised against a **real** `QueryClient` and
 * `QueryObserver` rather than by reading the options object back.
 *
 * Reading the object back would prove only that the literals were written. What
 * matters is that each one *wins over the application default* — `createQueryClient`
 * sets `staleTime: 30_000`, `gcTime: 5 * 60_000`, and `retry: 1`, all of which are
 * wrong for consent-gated health data. Every client below is therefore built with
 * deliberately hostile defaults, so a dropped override fails here.
 *
 * **Failure-output discipline.** The fixture list carries one synthetic check-in.
 * No assertion receives it: results are reduced to counts, booleans, fixed status
 * words, and labels first.
 */

const HOSTILE_DEFAULTS = {
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      gcTime: 5 * 60_000,
      retry: 5,
      networkMode: "online",
      refetchOnMount: false,
    },
  },
} as const;

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

function hostileClient(): QueryClient {
  return new QueryClient(HOSTILE_DEFAULTS);
}

/** Subscribes, fetches once, and returns the settled observer result. */
async function observeOnce(
  client: QueryClient,
  options: ReturnType<typeof coachCheckInReviewQueryOptions>,
) {
  const observer = new QueryObserver(client, options);
  const unsubscribe = observer.subscribe(() => undefined);
  const result = await observer.refetch();

  return { observer, unsubscribe, result };
}

/** Lets a zero-length garbage-collection timer fire. */
async function flushTimers(): Promise<void> {
  await new Promise((resolve) => {
    setTimeout(resolve, 0);
  });
}

// ---------------------------------------------------------------------------
// The key
// ---------------------------------------------------------------------------

describe("the coach-review query key", () => {
  it("is the auth-scoped key for the verified coach", () => {
    const options = coachCheckInReviewQueryOptions({
      userId: COACH_ID,
      load: () => Promise.resolve(TEAMS),
    });

    expect(options.queryKey).toEqual(
      authScopedKeys.coachCheckInReview(COACH_ID),
    );
  });

  it("holds no health value, no team id, and no athlete id", () => {
    const serialized = JSON.stringify(
      coachCheckInReviewQueryOptions({
        userId: COACH_ID,
        load: () => Promise.resolve(TEAMS),
      }).queryKey,
    );

    const leaks = [
      "rpe",
      "pain",
      "feeling",
      "check_in_date",
      TEAM_A,
      ATHLETE_1,
    ].filter((fragment) => serialized.includes(fragment));

    // Fragment names only — and the two identifiers would print as themselves
    // only if the test were already failing for exactly that reason.
    expect(leaks.map((fragment) => fragment.slice(0, 4))).toEqual([]);
  });

  it("is disabled and anonymous while signed out", () => {
    const options = coachCheckInReviewQueryOptions({
      userId: undefined,
      load: () => Promise.resolve(TEAMS),
    });

    expect(options.enabled).toBe(false);
    expect(options.queryKey).toContain(ANONYMOUS_KEY_USER_ID);
  });

  it("separates two coaches", () => {
    const forA = coachCheckInReviewQueryOptions({
      userId: COACH_ID,
      load: () => Promise.resolve(TEAMS),
    });
    const forB = coachCheckInReviewQueryOptions({
      userId: OTHER_COACH_ID,
      load: () => Promise.resolve(TEAMS),
    });

    expect(
      JSON.stringify(forA.queryKey) === JSON.stringify(forB.queryKey),
    ).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// The overrides, against hostile defaults
// ---------------------------------------------------------------------------

describe("the cache overrides beat the application defaults", () => {
  it("declares every required option", () => {
    const options = coachCheckInReviewQueryOptions({
      userId: COACH_ID,
      load: () => Promise.resolve(TEAMS),
    });

    // Scalars only.
    expect(options.staleTime).toBe(0);
    expect(options.gcTime).toBe(0);
    expect(options.retry).toBe(0);
    expect(options.networkMode).toBe("always");
    expect(options.refetchOnMount).toBe("always");
  });

  it("declares no polling, no placeholder, and no previous data", () => {
    const options: Record<string, unknown> = coachCheckInReviewQueryOptions({
      userId: COACH_ID,
      load: () => Promise.resolve(TEAMS),
    });

    const present = [
      "refetchInterval",
      "refetchIntervalInBackground",
      "placeholderData",
      "initialData",
      "keepPreviousData",
      "persister",
    ].filter((option) => options[option] !== undefined);

    // Option names only.
    expect(present).toEqual([]);
  });

  it("does not retry a refused read even though the default retries five times", async () => {
    let calls = 0;
    const client = hostileClient();

    const { unsubscribe } = await observeOnce(
      client,
      coachCheckInReviewQueryOptions({
        userId: COACH_ID,
        load: () => {
          calls += 1;

          return Promise.reject(new CoachReviewDataError("load", "denied"));
        },
      }),
    );

    unsubscribe();

    // A count only.
    expect(calls).toBe(1);
  });

  it("is stale the instant it settles, though the default keeps it fresh for 30s", async () => {
    const client = hostileClient();
    const { observer, unsubscribe } = await observeOnce(
      client,
      coachCheckInReviewQueryOptions({
        userId: COACH_ID,
        load: () => Promise.resolve(TEAMS),
      }),
    );

    // A revocation twenty seconds old must not be hidden behind a fresh entry.
    expect(observer.getCurrentQuery().isStale()).toBe(true);

    unsubscribe();
  });

  it("makes the entry collectible the moment the screen is left", async () => {
    // gcTime: 0. The health values must not linger in memory for the five
    // minutes the application default would keep them.
    const client = hostileClient();
    const key = authScopedKeys.coachCheckInReview(COACH_ID);

    const { unsubscribe } = await observeOnce(
      client,
      coachCheckInReviewQueryOptions({
        userId: COACH_ID,
        load: () => Promise.resolve(TEAMS),
      }),
    );

    expect(client.getQueryCache().find({ queryKey: key }) !== undefined).toBe(
      true,
    );

    unsubscribe();
    await flushTimers();

    // A boolean only.
    expect(client.getQueryCache().find({ queryKey: key }) === undefined).toBe(
      true,
    );
  });
});

// ---------------------------------------------------------------------------
// Identity isolation
// ---------------------------------------------------------------------------

describe("account-scoped cache isolation", () => {
  it("drops the previous coach's entry on an identity change", async () => {
    const client = hostileClient();

    const { unsubscribe } = await observeOnce(
      client,
      coachCheckInReviewQueryOptions({
        userId: COACH_ID,
        load: () => Promise.resolve(TEAMS),
      }),
    );

    clearAuthScopedQueries(client);

    const remaining = client
      .getQueryCache()
      .findAll()
      .filter((query) => query.state.data !== undefined).length;

    // A count only.
    expect(remaining).toBe(0);

    unsubscribe();
  });

  it("gives the second coach a different entry, never the first one's data", async () => {
    const client = hostileClient();

    const first = await observeOnce(
      client,
      coachCheckInReviewQueryOptions({
        userId: COACH_ID,
        load: () => Promise.resolve(TEAMS),
      }),
    );
    first.unsubscribe();

    // A fresh observer for a different identity, whose loader never resolves with
    // the first coach's list. If the key were not account-scoped this observer
    // would read the cached entry above.
    const second = new QueryObserver(
      client,
      coachCheckInReviewQueryOptions({
        userId: OTHER_COACH_ID,
        load: () => Promise.resolve([]),
      }),
    );

    // Before any fetch. A shared key would surface the first coach's data here.
    expect(
      visibleTeams(readCoachReviewView(second.getCurrentResult())).length,
    ).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// The refresh contract, through the same function the section uses
// ---------------------------------------------------------------------------

describe("a failed refresh hides the previously loaded health values", () => {
  it("keeps the old list internally but renders none of it", async () => {
    const client = hostileClient();
    let attempt = 0;

    const { observer, unsubscribe } = await observeOnce(
      client,
      coachCheckInReviewQueryOptions({
        userId: COACH_ID,
        load: () => {
          attempt += 1;

          return attempt === 1
            ? Promise.resolve(TEAMS)
            : Promise.reject(new CoachReviewDataError("load", "unknown"));
        },
      }),
    );

    // The first load is on screen.
    expect(
      visibleTeams(readCoachReviewView(observer.getCurrentResult())).length,
    ).toBe(1);

    await observer.refetch();
    const failed = observer.getCurrentResult();

    // TanStack genuinely still holds the previous list here — that is the hazard.
    expect(failed.data !== undefined).toBe(true);
    // And the view derivation is what makes it unrenderable.
    expect(readCoachReviewView(failed).status).toBe("error");
    expect(visibleTeams(readCoachReviewView(failed)).length).toBe(0);

    unsubscribe();
  });
});
