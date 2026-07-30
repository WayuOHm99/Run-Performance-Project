/**
 * The TanStack Query and mutation options, built by pure functions.
 *
 * Separated from the hooks so the cache rules are unit-tested directly rather
 * than through a rendered tree. This module imports no React and no React
 * Native; `use-daily-check-in.ts` supplies the client and the query client.
 *
 * Three rules are encoded here:
 *
 *   1. **The key is auth-scoped and date-scoped.** It carries the verified user
 *      id and the captured local date, keeps the shared `AUTH_SCOPE` prefix so
 *      `clearAuthScopedQueries` still removes it on a user change, and contains
 *      no health value.
 *   2. **A mutation invalidates the exact date it wrote.** The local date travels
 *      through the mutation variables and back out of `mutationFn`, so a rollover
 *      between submission and completion cannot cause a different day's entry to
 *      be invalidated.
 *   3. **No optimistic update and no retry.** There is no `onMutate`, so an
 *      unconfirmed health value is never written into the cache, and `retry: 0`
 *      means a failed health-bearing write is never resent automatically. The
 *      athlete retries deliberately or not at all.
 */

import { authScopedKeys } from "../../lib/query/keys";

import type { DailyCheckIn } from "./domain";

/**
 * The key placeholder used while no identity exists.
 *
 * The query is disabled in that state, so this is never fetched under; it exists
 * only so the key is well-typed. It matches the placeholder the account query
 * already uses.
 */
export const ANONYMOUS_KEY_USER_ID = "anonymous";

export type SaveCheckInVariables = {
  readonly localDate: string;
  readonly input: DailyCheckIn;
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
  readonly retry: 0;
  readonly mutationFn: (variables: SaveCheckInVariables) => Promise<string>;
  readonly onSuccess: (localDate: string) => void;
};

export function saveCheckInMutationOptions(args: {
  readonly save: (localDate: string, input: DailyCheckIn) => Promise<void>;
  readonly invalidate: (localDate: string) => void;
}): SaveCheckInMutationOptions {
  return {
    retry: 0,
    mutationFn: async (variables) => {
      await args.save(variables.localDate, variables.input);

      // The date, not the health values. This is what `onSuccess` invalidates,
      // so the write and the invalidation cannot disagree about the day.
      return variables.localDate;
    },
    onSuccess: (localDate) => {
      args.invalidate(localDate);
    },
  };
}
