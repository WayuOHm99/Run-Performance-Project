import {
  MutationObserver,
  QueryClient,
  onlineManager,
} from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import {
  authScopedKeys,
  authScopedUserId,
  isAuthScopedKey,
} from "../../lib/query/keys";

import { targetTeamId, type TeamSharingState } from "./domain";
import { SharingDataError } from "./errors";
import { probeFailure } from "./failure-probe";
import {
  ANONYMOUS_KEY_USER_ID,
  checkInSharingQueryOptions,
  sharingActionMutationOptions,
  type SharingActionResult,
  type SharingActionVariables,
} from "./query-options";

/**
 * The cache contract, tested without a renderer.
 *
 * **Failure-output safety.** Nothing here passes a user id, a team id, a key, a
 * variables object, or a captured error to an assertion:
 *
 * - a query key is reduced by `describeKey` to
 *   `auth-scoped|owner-a|check-in-sharing|3` — fixed literals, an owner *label*,
 *   and a length;
 * - team ids are reduced to the case labels `A`, `B`, or `unknown`;
 * - rejections go through `probeFailure`, which never rethrows and never passes a
 *   captured value to `expect`;
 * - sets of cases are asserted as lists of **case names**.
 *
 * All identifiers are synthetic.
 */

const USER_ID = "00000000-0000-4000-9000-000000000014";
const OTHER_USER_ID = "00000000-0000-4000-9000-0000000000ff";
const TEAM_A = "00000000-0000-4000-8000-00000000000a";
const TEAM_B = "00000000-0000-4000-8000-00000000000b";
const FORGED_TEAM = "00000000-0000-4000-8000-0000000000ff";

const TEAM_LABELS = new Map<string, string>([
  [TEAM_A, "A"],
  [TEAM_B, "B"],
]);

const OWNER_LABELS = new Map<unknown, string>([
  [USER_ID, "owner-a"],
  [OTHER_USER_ID, "owner-b"],
  [ANONYMOUS_KEY_USER_ID, "anonymous"],
]);

const TEAMS: readonly TeamSharingState[] = [
  { teamId: TEAM_A, teamName: "Alpha Runners", sharing: false },
  { teamId: TEAM_B, teamName: "Beta Runners", sharing: true },
];

function teamLabel(teamId: string): string {
  return TEAM_LABELS.get(teamId) ?? "unknown";
}

/** Safe: fixed key literals, an owner label, and the key length. */
function describeKey(key: readonly unknown[]): string {
  const owner = OWNER_LABELS.get(key[1]) ?? "unknown";

  return `${String(key[0])}|${owner}|${String(key[2])}|${String(key.length)}`;
}

/** Fragment names only. A non-empty result names what leaked, never the value. */
function leakFragments(value: unknown): readonly string[] {
  const serialized = JSON.stringify(value) ?? "";

  return (
    [
      ["rpe", "rpe"],
      ["pain", "pain"],
      ["feeling", "feeling"],
      ["team-a-id", TEAM_A],
      ["team-b-id", TEAM_B],
      ["team-name", "Runners"],
    ] as const
  )
    .filter(([, fragment]) => serialized.includes(fragment))
    .map(([name]) => name);
}

function noLoad(): Promise<readonly TeamSharingState[]> {
  return Promise.resolve([]);
}

describe("checkInSharingQueryOptions", () => {
  it("keys the list by the verified user and nothing else", () => {
    const options = checkInSharingQueryOptions({
      userId: USER_ID,
      load: noLoad,
    });

    expect(describeKey(options.queryKey)).toBe(
      "auth-scoped|owner-a|check-in-sharing|3",
    );
  });

  it("stays inside the auth scope so an identity change clears it", () => {
    const options = checkInSharingQueryOptions({
      userId: USER_ID,
      load: noLoad,
    });

    expect(isAuthScopedKey(options.queryKey)).toBe(true);
    // Compared privately; only the boolean escapes.
    expect(authScopedUserId(options.queryKey) === USER_ID).toBe(true);
  });

  it("produces a different entry per user", () => {
    const first = checkInSharingQueryOptions({ userId: USER_ID, load: noLoad });
    const second = checkInSharingQueryOptions({
      userId: OTHER_USER_ID,
      load: noLoad,
    });

    expect(describeKey(first.queryKey)).not.toBe(describeKey(second.queryKey));
    expect(
      JSON.stringify(first.queryKey) === JSON.stringify(second.queryKey),
    ).toBe(false);
  });

  it("holds no health value, no team id, and no team name", () => {
    // One entry for the whole list, so no team id belongs in the key. Team names
    // and the three check-in values are not in it either — this feature never even
    // reads a check-in value.
    const options = checkInSharingQueryOptions({
      userId: USER_ID,
      load: noLoad,
    });

    expect(options.queryKey.length).toBe(3);
    expect(options.queryKey.every((part) => typeof part === "string")).toBe(
      true,
    );
    expect(leakFragments(options.queryKey)).toEqual([]);
  });

  it("matches the shared key builder exactly", () => {
    const options = checkInSharingQueryOptions({
      userId: USER_ID,
      load: noLoad,
    });

    expect(
      JSON.stringify(options.queryKey) ===
        JSON.stringify(authScopedKeys.checkInSharing(USER_ID)),
    ).toBe(true);
  });

  it("is disabled and placeholder-keyed while no identity exists", () => {
    const options = checkInSharingQueryOptions({
      userId: undefined,
      load: noLoad,
    });

    expect(options.enabled).toBe(false);
    expect(describeKey(options.queryKey)).toBe(
      "auth-scoped|anonymous|check-in-sharing|3",
    );
  });

  it("is enabled once an identity exists", () => {
    expect(
      checkInSharingQueryOptions({ userId: USER_ID, load: noLoad }).enabled,
    ).toBe(true);
  });

  it("loads as the exact user the key was built from", async () => {
    let matched = false;

    await checkInSharingQueryOptions({
      userId: USER_ID,
      load: (userId) => {
        // Compared here so only a boolean is ever asserted.
        matched = userId === USER_ID;
        return Promise.resolve([]);
      },
    }).queryFn();

    expect(matched).toBe(true);
  });
});

type HarnessOptions = {
  readonly defer?: boolean;
  readonly failWrite?: boolean;
  readonly failRefetch?: boolean;
  readonly teams?: readonly TeamSharingState[];
};

/** Records only non-sensitive facts about an attempt. */
function createHarness(
  userId: string | undefined,
  options: HarnessOptions = {},
) {
  /** Ordered log of what happened, in safe vocabulary only. */
  const log: string[] = [];
  const refetchedKeys: unknown[][] = [];
  let release: (() => void) | undefined;
  let markStarted: (() => void) | undefined;

  const started = new Promise<void>((resolve) => {
    markStarted = resolve;
  });

  const settle = (): Promise<void> => {
    markStarted?.();

    if (options.failWrite === true) {
      return Promise.reject(new SharingDataError("grant", "denied"));
    }

    if (options.defer !== true) {
      return Promise.resolve();
    }

    return new Promise<void>((resolve) => {
      release = resolve;
    });
  };

  const built = sharingActionMutationOptions({
    userId,
    teams: options.teams ?? TEAMS,
    grant: (target) => {
      log.push(`grant:${teamLabel(targetTeamId(target))}`);
      return settle();
    },
    revoke: (target) => {
      log.push(`revoke:${teamLabel(targetTeamId(target))}`);
      return settle();
    },
    refetchKey: (queryKey) => {
      log.push("refetch");
      refetchedKeys.push([...queryKey]);

      return options.failRefetch === true
        ? Promise.reject(new Error("refresh failed"))
        : Promise.resolve();
    },
  });

  return {
    options: built,
    /** Safe: directions, case labels, and the word `refetch`, in order. */
    log: () => [...log],
    refetchCount: () => refetchedKeys.length,
    /** Safe: the reduced description of each refetched key, in order. */
    refetchedKeys: () => refetchedKeys.map(describeKey),
    /** Safe: fragment names found in any refetched key. */
    refetchLeaks: () => refetchedKeys.flatMap(leakFragments),
    started,
    release: () => {
      release?.();
    },
  };
}

const GRANT_A: SharingActionVariables = { teamId: TEAM_A, action: "grant" };
const REVOKE_B: SharingActionVariables = { teamId: TEAM_B, action: "revoke" };

describe("sharingActionMutationOptions", () => {
  it("disables automatic retries", () => {
    // A refused consent change is never resent without a new deliberate press.
    expect(createHarness(USER_ID).options.retry).toBe(0);
  });

  it("declares networkMode always", () => {
    // The runtime option, not the type. `"online"` would pause an offline action
    // and run it on reconnect with nobody asking.
    expect(createHarness(USER_ID).options.networkMode).toBe("always");
  });

  it("exposes no optimistic hook and no settle-time callback", () => {
    // No `onMutate` and no `setQueryData`, so no unconfirmed sharing state ever
    // enters the cache; and no `onSuccess`, so there is no callback a later render
    // could swap and redirect.
    const options = createHarness(USER_ID).options;

    // Option names only.
    expect(Object.keys(options).sort()).toEqual([
      "mutationFn",
      "networkMode",
      "retry",
    ]);
  });

  it("grants the pressed team, then refetches", async () => {
    const harness = createHarness(USER_ID);

    await harness.options.mutationFn(GRANT_A);

    expect(harness.log()).toEqual(["grant:A", "refetch"]);
  });

  it("revokes the pressed team, then refetches", async () => {
    const harness = createHarness(USER_ID);

    await harness.options.mutationFn(REVOKE_B);

    expect(harness.log()).toEqual(["revoke:B", "refetch"]);
  });

  it("touches only the pressed team", async () => {
    const harness = createHarness(USER_ID);

    await harness.options.mutationFn(GRANT_A);

    // No second write, and nothing referenced Team B.
    expect(harness.log().filter((entry) => entry.endsWith(":B"))).toEqual([]);
    expect(harness.log().filter((entry) => entry.startsWith("revoke"))).toEqual(
      [],
    );
  });

  it("refetches exactly the caller's auth-scoped list", async () => {
    const harness = createHarness(USER_ID);

    await harness.options.mutationFn(GRANT_A);

    expect(harness.refetchedKeys()).toEqual([
      "auth-scoped|owner-a|check-in-sharing|3",
    ]);
    // No team id and no team name reached the key, so one refresh serves every row.
    expect(harness.refetchLeaks()).toEqual([]);
  });

  it("returns only the direction, and no sharing state", async () => {
    const harness = createHarness(USER_ID);

    const result = await harness.options.mutationFn(GRANT_A);

    // Field names only. There is deliberately no `sharing` field: the state the UI
    // shows comes from the refetched query, never from this value. There is also no
    // key, owner, or team, because mutation data outlives the identity that produced
    // it on an active observer — see `identity-boundary.test.ts`. The captured key is
    // still proved to be used, by the refetch assertion above.
    expect(Object.keys(result).sort()).toEqual(["action"]);
    expect(result.action).toBe("grant");
    expect(leakFragments(result)).toEqual([]);
  });

  it("refuses to act without a verified identity", async () => {
    const harness = createHarness(undefined);

    const probe = await probeFailure(harness.options.mutationFn(GRANT_A));

    expect(probe.outcome).toBe("sanitized-error");
    expect(probe.intent).toBe("grant");
    expect(probe.messageIsFixed).toBe(true);
    // Nothing was written and nothing was refreshed.
    expect(harness.log()).toEqual([]);
  });

  it("refuses a revoke without a verified identity, with revoke wording", async () => {
    const harness = createHarness(undefined);

    const probe = await probeFailure(harness.options.mutationFn(REVOKE_B));

    expect(probe.intent).toBe("revoke");
    expect(harness.log()).toEqual([]);
  });

  it("refuses a team the server did not return", async () => {
    const CASES: readonly (readonly [string, SharingActionVariables])[] = [
      ["forged", { teamId: FORGED_TEAM, action: "grant" }],
      ["empty", { teamId: "", action: "grant" }],
      ["forged-revoke", { teamId: FORGED_TEAM, action: "revoke" }],
    ];

    const wrong: string[] = [];

    for (const [name, variables] of CASES) {
      const harness = createHarness(USER_ID);
      const probe = await probeFailure(harness.options.mutationFn(variables));

      if (
        probe.outcome !== "sanitized-error" ||
        probe.failure !== "denied" ||
        harness.log().length !== 0
      ) {
        wrong.push(name);
      }
    }

    // Case names only. No RPC was attempted for any of them.
    expect(wrong).toEqual([]);
  });

  it("refuses every action when the loaded list is empty", async () => {
    // The coach-only, pending, and revoked-membership cases.
    const harness = createHarness(USER_ID, { teams: [] });

    const probe = await probeFailure(harness.options.mutationFn(GRANT_A));

    expect(probe.outcome).toBe("sanitized-error");
    expect(harness.log()).toEqual([]);
  });

  it("refuses a team that disappeared from a later load", async () => {
    const harness = createHarness(USER_ID, {
      teams: TEAMS.filter((team) => team.teamId !== TEAM_B),
    });

    const probe = await probeFailure(harness.options.mutationFn(REVOKE_B));

    expect(probe.outcome).toBe("sanitized-error");
    expect(harness.log()).toEqual([]);
  });

  it("does not refetch when the write failed", async () => {
    const harness = createHarness(USER_ID, { failWrite: true });

    const probe = await probeFailure(harness.options.mutationFn(GRANT_A));

    expect(probe.outcome).toBe("sanitized-error");
    expect(harness.log()).toEqual(["grant:A"]);
    expect(harness.refetchCount()).toBe(0);
  });

  it("does not report a successful write as failed when the refresh fails", async () => {
    // The write happened. Saying "ยังไม่ได้เริ่มแชร์" here would tell the athlete
    // sharing is off when it is on. The query owns its own error state instead.
    const harness = createHarness(USER_ID, { failRefetch: true });

    const result = await harness.options.mutationFn(GRANT_A);

    expect(result.action).toBe("grant");
    expect(harness.log()).toEqual(["grant:A", "refetch"]);
  });
});

/**
 * Options replaced while a mutation is pending.
 *
 * TanStack swaps a pending mutation's options on rerender, so a settle-time
 * callback belonging to a *later* render is the one that runs. That is why the
 * refresh happens inside `mutationFn`, from a key captured before the write: the
 * entry refreshed is the one that was written, not whoever happens to be signed in
 * when the request lands.
 */
describe("a pending action whose options are replaced", () => {
  it("still writes and refreshes as the original identity", async () => {
    const client = new QueryClient({
      defaultOptions: { mutations: { retry: 0 } },
    });
    client.mount();

    try {
      const first = createHarness(USER_ID, { defer: true });
      const replacement = createHarness(OTHER_USER_ID);

      const observer = new MutationObserver<
        SharingActionResult,
        Error,
        SharingActionVariables
      >(client, first.options);

      const settled = observer.mutate(GRANT_A);

      // Wait until the write is genuinely in flight. Replacing the options any
      // earlier would swap the mutation function before it ran, which is a
      // different situation from the one being tested.
      await first.started;

      // The account changed mid-flight; the component rerendered with options built
      // from the new identity.
      observer.setOptions(replacement.options);

      first.release();
      await settled;

      // The original closure did the work and the refresh...
      expect(first.log()).toEqual(["grant:A", "refetch"]);
      expect(first.refetchedKeys()).toEqual([
        "auth-scoped|owner-a|check-in-sharing|3",
      ]);
      // ...and the replacement identity was never written or refreshed.
      expect(replacement.log()).toEqual([]);
      expect(replacement.refetchCount()).toBe(0);
      expect(
        first
          .refetchedKeys()
          .includes("auth-scoped|owner-b|check-in-sharing|3"),
      ).toBe(false);
    } finally {
      client.unmount();
      client.clear();
    }
  });
});

/**
 * Offline behaviour.
 *
 * With the library default `networkMode: "online"`, an offline mutation is *paused*
 * rather than failed: its variables stay in memory and the write runs automatically
 * on reconnect. For a consent change that is an authorization outbox — the athlete
 * presses "stop sharing", nothing appears to happen, and the revoke fires later, or
 * a *grant* does. `"always"` is what makes the attempt immediate and its failure
 * the athlete's to see.
 */
describe("while the device is offline", () => {
  /**
   * Note on structure: the online state is restored in a `finally` in each test
   * rather than by a wrapper that returns the pending promise. An `async` wrapper
   * flattens a returned promise, so awaiting it would wait for the mutation to
   * settle *before* restoring connectivity — which deadlocks precisely in the
   * paused case this file is about.
   */

  it("runs the action immediately instead of queueing it", async () => {
    const client = new QueryClient({
      defaultOptions: { mutations: { retry: 0 } },
    });
    client.mount();

    const wasOnline = onlineManager.isOnline();
    onlineManager.setOnline(false);

    const harness = createHarness(USER_ID);
    const observer = new MutationObserver<
      SharingActionResult,
      Error,
      SharingActionVariables
    >(client, harness.options);

    const seenPaused: boolean[] = [];
    const unsubscribe = observer.subscribe((result) => {
      seenPaused.push(result.isPaused);
    });

    try {
      await observer.mutate(GRANT_A);

      const settledResult = observer.getCurrentResult();

      // Executed while offline, and settled from that immediate attempt.
      expect(harness.log()).toEqual(["grant:A", "refetch"]);
      expect(settledResult.status).toBe("success");
      expect(settledResult.isPaused).toBe(false);
      expect(seenPaused.filter(Boolean).length).toBe(0);
      expect(client.isMutating()).toBe(0);

      // Reconnecting must not run it a second time.
      onlineManager.setOnline(true);
      await client.resumePausedMutations();
      await Promise.resolve();

      expect(harness.log()).toEqual(["grant:A", "refetch"]);
      expect(harness.refetchCount()).toBe(1);
    } finally {
      unsubscribe();
      onlineManager.setOnline(wasOnline);
      client.unmount();
      client.clear();
    }
  });

  it("would have been queued under the library default networkMode", async () => {
    // The positive control. Identical options minus `networkMode`, so this fails if
    // TanStack ever stops pausing and the guard above becomes moot.
    const client = new QueryClient({
      defaultOptions: { mutations: { retry: 0 } },
    });
    client.mount();

    const wasOnline = onlineManager.isOnline();
    const harness = createHarness(USER_ID);
    const { networkMode: _networkMode, ...withoutNetworkMode } =
      harness.options;

    const observer = new MutationObserver<
      SharingActionResult,
      Error,
      SharingActionVariables
    >(client, withoutNetworkMode);

    try {
      onlineManager.setOnline(false);

      const pending = observer.mutate(GRANT_A).catch(() => undefined);

      await Promise.resolve();

      const pausedResult = observer.getCurrentResult();

      // Paused, not failed: the consent change is held for later.
      expect(pausedResult.status).toBe("pending");
      expect(pausedResult.isPaused).toBe(true);
      expect(harness.log()).toEqual([]);
      expect(client.isMutating()).toBe(1);

      // Back online: the retained action runs by itself, with nobody asking.
      onlineManager.setOnline(true);
      await client.resumePausedMutations();
      await pending;

      expect(harness.log()).toEqual(["grant:A", "refetch"]);
      expect(observer.getCurrentResult().isPaused).toBe(false);
    } finally {
      onlineManager.setOnline(wasOnline);
      client.unmount();
      client.clear();
    }
  });

  it("does not retry a failed action", async () => {
    const client = new QueryClient({
      defaultOptions: { mutations: { retry: 3 } },
    });
    client.mount();

    const harness = createHarness(USER_ID, { failWrite: true });
    const observer = new MutationObserver<
      SharingActionResult,
      Error,
      SharingActionVariables
    >(client, harness.options);

    try {
      await observer.mutate(GRANT_A).catch(() => undefined);

      // `retry: 0` in the options beats the client default of 3.
      expect(harness.log()).toEqual(["grant:A"]);
      expect(observer.getCurrentResult().failureCount).toBe(1);
    } finally {
      client.unmount();
      client.clear();
    }
  });
});
