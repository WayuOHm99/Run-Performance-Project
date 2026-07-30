/**
 * The TanStack Query and mutation options, built by pure functions.
 *
 * Separated from the hooks so the cache rules are unit-tested directly rather
 * than through a rendered tree. This module imports no React and no React
 * Native; `use-daily-check-in.ts` supplies the client and the query client.
 *
 * Four rules are encoded here:
 *
 *   1. **The key is auth-scoped and date-scoped.** It carries the verified user
 *      id and the captured local date, keeps the shared `AUTH_SCOPE` prefix so
 *      `clearAuthScopedQueries` still removes it on a user change, and contains
 *      no health value.
 *
 *   2. **`networkMode: "always"`.** This is not a detail. TanStack Query's
 *      default `networkMode: "online"` does not fail an offline mutation — it
 *      *pauses* it, retaining the variables in memory and running it
 *      automatically once connectivity returns. That is an in-memory outbox
 *      holding `rpe`, `overall_feeling`, and `pain_status`, plus an automatic
 *      delayed health write, both of which decision 10 forbids. `"always"` makes
 *      the attempt happen immediately and settle immediately, so a failure is
 *      reported to the athlete instead of being queued behind their back.
 *
 *   3. **`retry: 0`.** A rejected health-bearing write is never resent without
 *      the athlete asking again.
 *
 *   4. **The invalidation target is captured at mutation start.** TanStack
 *      swaps a pending mutation's options on rerender, so a callback belonging
 *      to a *later* render can be the one that runs at settle time. If
 *      `onSuccess` rebuilt the key from its own closure, a sign-out or account
 *      switch mid-flight would invalidate the new identity's entry instead of
 *      the one that was actually written. The exact key is therefore built
 *      inside `mutationFn` before any `await`, returned as the mutation's data,
 *      and invalidated from that returned value. There is no `onMutate`, so no
 *      unconfirmed health value ever enters the cache.
 */

import { authScopedKeys } from "../../lib/query/keys";

import type { DailyCheckIn } from "./domain";
import { CheckInDataError } from "./errors";

/**
 * The key placeholder used while no identity exists.
 *
 * The query is disabled in that state, so nothing is ever fetched under it; it
 * exists only so the key is well-typed, and it matches the placeholder the
 * account query already uses.
 */
export const ANONYMOUS_KEY_USER_ID = "anonymous";

export type SaveCheckInVariables = {
  readonly localDate: string;
  readonly input: DailyCheckIn;
};

/**
 * What a completed save reports back.
 *
 * The exact auth-scoped key that was written, plus its two non-health parts for
 * legibility. No health value is present, so this can safely be held as mutation
 * data and read by any later callback.
 */
export type SaveCheckInResult = {
  readonly queryKey: readonly unknown[];
  readonly userId: string;
  readonly localDate: string;
};

export type CheckInQueryOptions = {
  readonly queryKey: readonly unknown[];
  readonly queryFn: () => Promise<DailyCheckIn | null>;
  readonly enabled: boolean;
};

export function checkInQueryOptions(args: {
  readonly userId: string | undefined;
  readonly localDate: string;
  readonly load: (
    userId: string,
    localDate: string,
  ) => Promise<DailyCheckIn | null>;
}): CheckInQueryOptions {
  const { userId, localDate, load } = args;

  return {
    queryKey: authScopedKeys.dailyCheckIn(
      userId ?? ANONYMOUS_KEY_USER_ID,
      localDate,
    ),
    // Only ever called while `enabled`, which requires a verified id.
    queryFn: () => load(userId as string, localDate),
    enabled: userId !== undefined,
  };
}

export type SaveCheckInMutationOptions = {
  readonly networkMode: "always";
  readonly retry: 0;
  readonly mutationFn: (
    variables: SaveCheckInVariables,
  ) => Promise<SaveCheckInResult>;
  readonly onSuccess: (result: SaveCheckInResult) => void;
};

export function saveCheckInMutationOptions(args: {
  /** The verified authenticated user id, or undefined while signed out. */
  readonly userId: string | undefined;
  readonly save: (
    userId: string,
    localDate: string,
    input: DailyCheckIn,
  ) => Promise<void>;
  readonly invalidateKey: (queryKey: readonly unknown[]) => void;
}): SaveCheckInMutationOptions {
  return {
    networkMode: "always",
    retry: 0,
    mutationFn: async (variables) => {
      const userId = args.userId;

      if (userId === undefined) {
        // No verified identity means no owner to scope the write to. Refused
        // before any client call rather than sent with a placeholder.
        throw new CheckInDataError("save", "unknown");
      }

      // Captured before the await, from the identity this attempt belongs to.
      const result: SaveCheckInResult = {
        queryKey: authScopedKeys.dailyCheckIn(userId, variables.localDate),
        userId,
        localDate: variables.localDate,
      };

      await args.save(userId, variables.localDate, variables.input);

      return result;
    },
    onSuccess: (result) => {
      // The key comes from the returned result, never rebuilt from a closure
      // that may belong to a later render.
      args.invalidateKey(result.queryKey);
    },
  };
}
