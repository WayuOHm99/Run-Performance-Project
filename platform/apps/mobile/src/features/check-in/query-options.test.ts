import {
  MutationObserver,
  QueryClient,
  onlineManager,
} from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { authScopedKeys, isAuthScopedKey } from "../../lib/query/keys";

import type { DailyCheckIn } from "./domain";
import { probeFailure } from "./failure-probe";
import {
  ANONYMOUS_KEY_USER_ID,
  checkInQueryOptions,
  saveCheckInMutationOptions,
  type SaveCheckInResult,
  type SaveCheckInVariables,
} from "./query-options";

/**
 * The cache contract, tested without a renderer.
 *
 * Health literals are synthetic. Assertions are keys, counts, dates, statuses,
 * and booleans; no health-bearing object is compared, snapshotted, or printed,
 * and mutation variables never reach an assertion.
 */

const USER_ID = "00000000-0000-4000-9000-000000000013";
const OTHER_USER_ID = "00000000-0000-4000-9000-0000000000ff";
const LOCAL_DATE = "2026-07-30";

const VALID_INPUT: DailyCheckIn = {
  rpe: 6,
  overallFeeling: 3,
  painStatus: "none",
};

const VARIABLES: SaveCheckInVariables = {
  localDate: LOCAL_DATE,
  input: VALID_INPUT,
};

function noopLoad(): Promise<DailyCheckIn | null> {
  return Promise.resolve(null);
}

describe("checkInQueryOptions", () => {
  it("keys the query by the verified user and the local date", () => {
    const options = checkInQueryOptions({
      userId: USER_ID,
      localDate: LOCAL_DATE,
      load: noopLoad,
    });

    expect(options.queryKey).toEqual(
      authScopedKeys.dailyCheckIn(USER_ID, LOCAL_DATE),
    );
    expect(options.queryKey).toContain(USER_ID);
    expect(options.queryKey).toContain(LOCAL_DATE);
  });

  it("puts no health value in the key", () => {
    const options = checkInQueryOptions({
      userId: USER_ID,
      localDate: LOCAL_DATE,
      load: noopLoad,
    });

    expect(options.queryKey).toEqual([
      "auth-scoped",
      USER_ID,
      "daily-check-in",
      LOCAL_DATE,
    ]);
    expect(options.queryKey.every((part) => typeof part === "string")).toBe(
      true,
    );

    const serialized = JSON.stringify(options.queryKey);
    const leaks = ["none", "present", "rpe", "feeling", "pain"].filter(
      (fragment) => serialized.includes(fragment),
    );

    expect(leaks).toEqual([]);
  });

  it("stays inside the auth scope so a user change clears it", () => {
    expect(
      isAuthScopedKey(
        checkInQueryOptions({
          userId: USER_ID,
          localDate: LOCAL_DATE,
          load: noopLoad,
        }).queryKey,
      ),
    ).toBe(true);
  });

  it("produces a different entry per user and per date", () => {
    const key = (userId: string, localDate: string) =>
      checkInQueryOptions({ userId, localDate, load: noopLoad }).queryKey;

    expect(key(USER_ID, LOCAL_DATE)).not.toEqual(
      key(OTHER_USER_ID, LOCAL_DATE),
    );
    // Crossing midnight must not serve yesterday's answers as today's.
    expect(key(USER_ID, LOCAL_DATE)).not.toEqual(key(USER_ID, "2026-07-31"));
  });

  it("is disabled and placeholder-keyed while no identity exists", () => {
    const options = checkInQueryOptions({
      userId: undefined,
      localDate: LOCAL_DATE,
      load: noopLoad,
    });

    expect(options.enabled).toBe(false);
    expect(options.queryKey).toContain(ANONYMOUS_KEY_USER_ID);
  });

  it("is enabled once an identity exists", () => {
    expect(
      checkInQueryOptions({
        userId: USER_ID,
        localDate: LOCAL_DATE,
        load: noopLoad,
      }).enabled,
    ).toBe(true);
  });

  it("loads with the exact user and date the key was built from", async () => {
    const seen: string[] = [];

    await checkInQueryOptions({
      userId: USER_ID,
      localDate: LOCAL_DATE,
      load: (userId, localDate) => {
        seen.push(`${userId}|${localDate}`);
        return Promise.resolve(null);
      },
    }).queryFn();

    expect(seen).toEqual([`${USER_ID}|${LOCAL_DATE}`]);
  });
});

/** Records only non-health facts about a save attempt. */
function createSaveHarness(
  userId: string | undefined,
  options: { readonly defer?: boolean } = {},
) {
  const savedScopes: string[] = [];
  const invalidatedKeys: unknown[][] = [];
  let inputMatched = false;
  let release: (() => void) | undefined;
  let markStarted: (() => void) | undefined;

  /** Resolves the moment `save` is actually entered. */
  const started = new Promise<void>((resolve) => {
    markStarted = resolve;
  });

  const built = saveCheckInMutationOptions({
    userId,
    save: (owner, localDate, input) => {
      savedScopes.push(`${owner}|${localDate}`);
      // Compared here so only a boolean is ever asserted.
      inputMatched =
        input.rpe === VALID_INPUT.rpe &&
        input.overallFeeling === VALID_INPUT.overallFeeling &&
        input.painStatus === VALID_INPUT.painStatus;

      markStarted?.();

      if (options.defer !== true) {
        return Promise.resolve();
      }

      return new Promise<void>((resolve) => {
        release = resolve;
      });
    },
    invalidateKey: (queryKey) => {
      invalidatedKeys.push([...queryKey]);
    },
  });

  return {
    options: built,
    savedScopes,
    invalidatedKeys,
    inputMatched: () => inputMatched,
    started,
    release: () => {
      release?.();
    },
  };
}

describe("saveCheckInMutationOptions", () => {
  it("disables automatic retries", () => {
    // A failed health-bearing write is never resent without the athlete asking.
    expect(createSaveHarness(USER_ID).options.retry).toBe(0);
  });

  it("declares networkMode always", () => {
    // The runtime option, not the type. `"online"` would pause an offline
    // mutation and keep its health-bearing variables in memory for later.
    expect(createSaveHarness(USER_ID).options.networkMode).toBe("always");
  });

  it("uses no optimistic update", () => {
    // No `onMutate`, so an unconfirmed health value never enters the cache.
    expect("onMutate" in createSaveHarness(USER_ID).options).toBe(false);
  });

  it("saves as the verified user for the submitted date", async () => {
    const harness = createSaveHarness(USER_ID);

    await harness.options.mutationFn(VARIABLES);

    expect(harness.savedScopes).toEqual([`${USER_ID}|${LOCAL_DATE}`]);
    expect(harness.inputMatched()).toBe(true);
  });

  it("returns the exact auth-scoped key and no health value", async () => {
    const harness = createSaveHarness(USER_ID);

    const result = await harness.options.mutationFn(VARIABLES);

    expect(result.queryKey).toEqual(
      authScopedKeys.dailyCheckIn(USER_ID, LOCAL_DATE),
    );
    expect(result.userId).toBe(USER_ID);
    expect(result.localDate).toBe(LOCAL_DATE);
    expect(Object.keys(result).sort()).toEqual([
      "localDate",
      "queryKey",
      "userId",
    ]);

    const serialized = JSON.stringify(result);
    const leaks = ["none", "present", "overallFeeling", "rpe"].filter(
      (fragment) => serialized.includes(fragment),
    );

    expect(leaks).toEqual([]);
  });

  it("invalidates exactly the key it returned", async () => {
    const harness = createSaveHarness(USER_ID);

    harness.options.onSuccess(await harness.options.mutationFn(VARIABLES));

    expect(harness.invalidatedKeys).toEqual([
      [...authScopedKeys.dailyCheckIn(USER_ID, LOCAL_DATE)],
    ]);
  });

  it("invalidates the submitted date even if the device day has since moved", async () => {
    const harness = createSaveHarness(USER_ID);

    harness.options.onSuccess(
      await harness.options.mutationFn({
        localDate: "2026-07-29",
        input: VALID_INPUT,
      }),
    );

    expect(harness.savedScopes).toEqual([`${USER_ID}|2026-07-29`]);
    expect(harness.invalidatedKeys).toEqual([
      [...authScopedKeys.dailyCheckIn(USER_ID, "2026-07-29")],
    ]);
  });

  it("refuses to write when there is no verified identity", async () => {
    const harness = createSaveHarness(undefined);

    const probe = await probeFailure(harness.options.mutationFn(VARIABLES));

    expect(probe.outcome).toBe("sanitized-error");
    expect(probe.intent).toBe("save");
    expect(harness.savedScopes).toEqual([]);
  });

  it("does not invalidate when the write failed", async () => {
    const invalidatedKeys: unknown[][] = [];
    const options = saveCheckInMutationOptions({
      userId: USER_ID,
      save: () => Promise.reject(new Error("refused")),
      invalidateKey: (queryKey) => {
        invalidatedKeys.push([...queryKey]);
      },
    });

    const probe = await probeFailure(options.mutationFn(VARIABLES));

    // The raw error is not a CheckInDataError here, which is fine: the
    // repository sanitizes before this layer. Only the outcome is asserted.
    expect(probe.outcome).toBe("unsanitized-error");
    expect(invalidatedKeys).toEqual([]);
  });
});

/**
 * Options replaced while a mutation is pending.
 *
 * TanStack swaps a pending mutation's options on rerender, so the callback that
 * runs at settle time can belong to a *later* render. That is why the key is
 * captured inside `mutationFn` before the await and returned as the mutation's
 * data: the invalidation target must be the entry that was written, not whoever
 * happens to be signed in when the request lands.
 */
describe("a pending save whose options are replaced", () => {
  it("still invalidates the original user and date", async () => {
    const client = new QueryClient({
      defaultOptions: { mutations: { retry: 0 } },
    });
    client.mount();

    try {
      const first = createSaveHarness(USER_ID, { defer: true });
      const replacement = createSaveHarness(OTHER_USER_ID);

      const observer = new MutationObserver<
        SaveCheckInResult,
        Error,
        SaveCheckInVariables
      >(client, first.options);

      const settled = observer.mutate(VARIABLES);

      // Wait until the write is genuinely in flight. Replacing the options any
      // earlier would swap the mutation function itself before it ran, which is a
      // different situation from the one being tested.
      await first.started;

      // The account changed mid-flight; the component rerendered with options
      // built from the new identity.
      observer.setOptions(replacement.options);

      first.release();
      await settled;

      // The replacement's onSuccess is the one that ran...
      expect(replacement.invalidatedKeys.length).toBe(1);
      expect(first.invalidatedKeys.length).toBe(0);
      // ...but the key it invalidated is the original user's, not its own.
      expect(replacement.invalidatedKeys[0]).toEqual([
        ...authScopedKeys.dailyCheckIn(USER_ID, LOCAL_DATE),
      ]);
      expect(replacement.invalidatedKeys[0]).not.toEqual([
        ...authScopedKeys.dailyCheckIn(OTHER_USER_ID, LOCAL_DATE),
      ]);
      // The write itself was performed as the original user.
      expect(first.savedScopes).toEqual([`${USER_ID}|${LOCAL_DATE}`]);
      expect(replacement.savedScopes).toEqual([]);
    } finally {
      client.unmount();
      client.clear();
    }
  });
});

/**
 * Offline behaviour.
 *
 * With the library default `networkMode: "online"`, an offline mutation is
 * *paused* rather than failed: its variables — the three protected health values
 * — stay in memory and the write runs automatically on reconnect. That is an
 * in-memory outbox plus a delayed automatic health write. `"always"` is what
 * makes the attempt immediate and its failure the athlete's to see.
 */
describe("while the device is offline", () => {
  /**
   * Note on structure: the online state is restored in a `finally` in each test
   * rather than by a wrapper that returns the pending promise. An `async`
   * wrapper flattens a returned promise, so awaiting it would wait for the
   * mutation to settle *before* restoring connectivity — which deadlocks
   * precisely in the paused case this file is about.
   */

  it("runs the feature mutation immediately instead of queueing it", async () => {
    const client = new QueryClient({
      defaultOptions: { mutations: { retry: 0 } },
    });
    client.mount();

    const wasOnline = onlineManager.isOnline();
    onlineManager.setOnline(false);

    const harness = createSaveHarness(USER_ID);
    const observer = new MutationObserver<
      SaveCheckInResult,
      Error,
      SaveCheckInVariables
    >(client, harness.options);

    const seenPaused: boolean[] = [];
    const unsubscribe = observer.subscribe((result) => {
      seenPaused.push(result.isPaused);
    });

    try {
      await observer.mutate(VARIABLES);

      const settledResult = observer.getCurrentResult();

      // Executed while offline, and settled from that immediate attempt.
      expect(harness.savedScopes.length).toBe(1);
      expect(settledResult.status).toBe("success");
      expect(settledResult.isPaused).toBe(false);
      expect(seenPaused.filter(Boolean).length).toBe(0);
      expect(client.isMutating()).toBe(0);

      // Reconnecting must not run it a second time.
      onlineManager.setOnline(true);
      await client.resumePausedMutations();
      await Promise.resolve();

      expect(harness.savedScopes.length).toBe(1);
      expect(harness.invalidatedKeys.length).toBe(1);
    } finally {
      unsubscribe();
      onlineManager.setOnline(wasOnline);
      client.unmount();
      client.clear();
    }
  });

  it("would have been queued under the library default networkMode", async () => {
    // The positive control. Identical options minus `networkMode`, so this fails
    // if TanStack ever stops pausing and the guard above becomes moot.
    const client = new QueryClient({
      defaultOptions: { mutations: { retry: 0 } },
    });
    client.mount();

    const wasOnline = onlineManager.isOnline();
    const harness = createSaveHarness(USER_ID);
    const { networkMode: _networkMode, ...withoutNetworkMode } =
      harness.options;

    const observer = new MutationObserver<
      SaveCheckInResult,
      Error,
      SaveCheckInVariables
    >(client, withoutNetworkMode);

    try {
      onlineManager.setOnline(false);

      const pending = observer.mutate(VARIABLES).catch(() => undefined);

      await Promise.resolve();

      const pausedResult = observer.getCurrentResult();

      // Paused, not failed: the health-bearing variables are held for later.
      expect(pausedResult.status).toBe("pending");
      expect(pausedResult.isPaused).toBe(true);
      expect(harness.savedScopes.length).toBe(0);
      expect(client.isMutating()).toBe(1);

      // Back online: the retained mutation runs by itself, with nobody asking.
      onlineManager.setOnline(true);
      await client.resumePausedMutations();
      await pending;

      expect(harness.savedScopes.length).toBe(1);
      expect(observer.getCurrentResult().isPaused).toBe(false);
    } finally {
      onlineManager.setOnline(wasOnline);
      client.unmount();
      client.clear();
    }
  });
});
