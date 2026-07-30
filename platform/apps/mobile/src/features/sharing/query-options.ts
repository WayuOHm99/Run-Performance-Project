/**
 * The TanStack Query and mutation options, built by pure functions.
 *
 * Separated from the hooks so the cache rules are unit-tested directly rather than
 * through a rendered tree. This module imports no React and no React Native;
 * `use-check-in-sharing.ts` supplies the client and the query client.
 *
 * Five rules are encoded here:
 *
 *   1. **The key is auth-scoped.** It carries the verified user id, keeps the
 *      shared `AUTH_SCOPE` prefix so `clearAuthScopedQueries` still removes it on
 *      an identity change, and holds no health value and no team id.
 *
 *   2. **`networkMode: "always"`.** Not a detail. TanStack Query's default
 *      `networkMode: "online"` does not fail an offline mutation — it *pauses* it,
 *      retaining the variables in memory and running it automatically once
 *      connectivity returns. For a consent change that is an authorization outbox:
 *      the athlete presses "stop sharing", sees nothing happen, and the revoke
 *      fires minutes later without them asking — or worse, a *grant* does.
 *      `"always"` makes the attempt immediate and its failure the athlete's to see.
 *
 *   3. **`retry: 0`.** A refused or failed consent change is never resent without
 *      a new deliberate press.
 *
 *   4. **No optimistic state, and the server confirms before success.** There is
 *      no `onMutate` and no `setQueryData`, so nothing writes an unconfirmed
 *      sharing state into the cache. The refetch of the exact list is awaited
 *      *inside* `mutationFn`, so by the time the mutation reports success the
 *      section is already rendering server-confirmed state.
 *
 *   5. **There is no settle-time callback at all.** TanStack swaps a pending
 *      mutation's options on rerender, so an `onSuccess` belonging to a *later*
 *      render is the one that runs — which is how a mid-flight account switch
 *      could redirect a refresh to the new identity. `mutationFn` is instead read
 *      once when execution begins, so the key captured before the write, and the
 *      refetch performed with it, both belong to the identity the write was made
 *      as. Removing the callback removes the hazard rather than guarding it.
 */

import { authScopedKeys } from "../../lib/query/keys";

import {
  resolveSharingTarget,
  type SharingTarget,
  type TeamSharingState,
} from "./domain";
import { SharingDataError, type SharingIntent } from "./errors";

/**
 * The key placeholder used while no identity exists.
 *
 * The query is disabled in that state, so nothing is ever fetched under it; it
 * exists only so the key is well-typed, and it matches the placeholder the account
 * and check-in queries already use.
 */
export const ANONYMOUS_KEY_USER_ID = "anonymous";

export type SharingAction = "grant" | "revoke";

export type SharingActionVariables = {
  readonly teamId: string;
  readonly action: SharingAction;
};

/**
 * What a completed action reports back: the direction, and nothing else.
 *
 * Deliberately minimal. Earlier this also carried the auth-scoped key, the owner,
 * and the team, which were only ever needed *inside* `mutationFn` — and mutation
 * data outlives the identity that produced it on an active observer, so keeping
 * authorization metadata here meant the previous account's user id, team id, and
 * query key could still be read from observer state after an account change. They
 * are now locals; the only field that survives is the one the success banner needs.
 *
 * Deliberately **not** a sharing state either: what the section shows comes only
 * from the refetched query, never from this value.
 */
export type SharingActionResult = {
  readonly action: SharingAction;
};

export type CheckInSharingQueryOptions = {
  readonly queryKey: readonly unknown[];
  readonly queryFn: () => Promise<readonly TeamSharingState[]>;
  readonly enabled: boolean;
};

export function checkInSharingQueryOptions(args: {
  /** The verified authenticated user id, or undefined while signed out. */
  readonly userId: string | undefined;
  readonly load: (userId: string) => Promise<readonly TeamSharingState[]>;
}): CheckInSharingQueryOptions {
  const { userId, load } = args;

  return {
    queryKey: authScopedKeys.checkInSharing(userId ?? ANONYMOUS_KEY_USER_ID),
    // Only ever called while `enabled`, which requires a verified id.
    queryFn: () => load(userId as string),
    enabled: userId !== undefined,
  };
}

export type SharingActionMutationOptions = {
  readonly networkMode: "always";
  readonly retry: 0;
  readonly mutationFn: (
    variables: SharingActionVariables,
  ) => Promise<SharingActionResult>;
};

function intentOf(action: SharingAction): SharingIntent {
  return action;
}

export function sharingActionMutationOptions(args: {
  /** The verified authenticated user id, or undefined while signed out. */
  readonly userId: string | undefined;
  /** The currently loaded list. The only source of a writable team id. */
  readonly teams: readonly TeamSharingState[];
  readonly grant: (target: SharingTarget) => Promise<void>;
  readonly revoke: (target: SharingTarget) => Promise<void>;
  /** Refetches the exact list that was written. Must not reject. */
  readonly refetchKey: (queryKey: readonly unknown[]) => Promise<void>;
}): SharingActionMutationOptions {
  return {
    networkMode: "always",
    retry: 0,
    mutationFn: async (variables) => {
      const intent = intentOf(variables.action);
      const userId = args.userId;

      if (userId === undefined) {
        // No verified identity means no caller to attribute consent to. Refused
        // before any client call rather than sent with a placeholder.
        throw new SharingDataError(intent, "unknown");
      }

      // The pressed team must be one the server returned for *this* caller. A
      // forged, stale, or unowned id stops here, so no RPC is attempted with it.
      const target = resolveSharingTarget(variables.teamId, args.teams);

      if (target === null) {
        throw new SharingDataError(intent, "denied");
      }

      // Captured before the await, from the identity this attempt belongs to, and
      // kept as a local rather than returned: nothing downstream needs it, and
      // mutation data outlives its identity on an active observer.
      const invalidationKey = authScopedKeys.checkInSharing(userId);

      if (variables.action === "grant") {
        await args.grant(target);
      } else {
        await args.revoke(target);
      }

      try {
        // Awaited here, not in a callback, so success is reported only after the
        // server's own list has been re-read under the captured key.
        await args.refetchKey(invalidationKey);
      } catch {
        // The write already succeeded, so a failed refresh must not be reported as
        // a failed consent change — that wording would tell the athlete sharing is
        // still off when it is on. The query owns its own error state and the
        // section shows the load error and its retry instead.
      }

      return { action: variables.action };
    },
  };
}
