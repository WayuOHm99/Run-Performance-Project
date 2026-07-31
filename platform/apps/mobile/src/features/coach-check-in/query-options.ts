/**
 * The TanStack Query options, built by a pure function.
 *
 * Separated from the hook so the cache rules are unit-tested directly against a
 * real `QueryClient`/`QueryObserver` rather than through a rendered tree. This
 * module imports no React and no React Native; `use-coach-check-in-review.ts`
 * supplies the client.
 *
 * There is **no mutation module in this feature at all**. Decision 10 makes the
 * coach side read-only, so the absence of `useMutation`, an RPC, and any write
 * option is itself part of the contract and is enforced by the source scan.
 *
 * Every option below overrides a `createQueryClient` default, and each one is a
 * consent decision rather than a performance one:
 *
 *   1. **The key is auth-scoped.** It carries the verified coach user id, keeps the
 *      shared `AUTH_SCOPE` prefix so `clearAuthScopedQueries` still removes it on
 *      an identity change, and holds no health value, no team id, and no athlete
 *      id.
 *
 *   2. **`staleTime: 0`** against the client default of 30s. Consent is not
 *      cacheable state: a grant revoked twenty seconds ago must not be served from
 *      a "still fresh" entry. Every read of this screen re-asks the database.
 *
 *   3. **`gcTime: 0`** against the client default of five minutes. The moment the
 *      coach leaves the screen and the last observer unsubscribes, the entry — and
 *      the health values inside it — becomes immediately collectible instead of
 *      lingering in memory for five minutes after it stopped being displayed.
 *
 *   4. **`retry: 0`** against the client default of 1. A refused health read is a
 *      statement about authorization; resending it automatically turns one refusal
 *      into two and can turn a revocation into a race.
 *
 *   5. **`networkMode: "always"`.** Not a detail. The default `"online"` *pauses*
 *      a query while offline and runs it automatically once connectivity returns,
 *      which is a deferred health read the coach did not ask for and is not
 *      present to see. `"always"` makes the attempt immediate and its failure
 *      visible.
 *
 *   6. **`refetchOnMount: "always"`.** Returning to the screen re-checks consent
 *      even if the entry were somehow considered fresh. With `staleTime: 0` this is
 *      belt and braces, deliberately: the two would have to be weakened together
 *      for stale consent to be rendered.
 *
 *   7. **No polling and no Realtime.** No `refetchInterval` and no subscription, so
 *      health data is never pulled to a device nobody is looking at.
 *
 *   8. **No placeholder and no previous data.** No `placeholderData`, no
 *      `initialData`, no `keepPreviousData`. A refresh must not have anything to
 *      show *from a previous answer* — see `view-state.ts` for why hiding it is not
 *      enough on its own.
 */

import { authScopedKeys } from "../../lib/query/keys";

import type { CoachReviewTeam } from "./domain";

/**
 * The key placeholder used while no identity exists.
 *
 * The query is disabled in that state, so nothing is ever fetched under it; it
 * exists only so the key is well-typed, and it matches the placeholder the account,
 * check-in, and sharing queries already use.
 */
export const ANONYMOUS_KEY_USER_ID = "anonymous";

export type CoachCheckInReviewQueryOptions = {
  readonly queryKey: readonly unknown[];
  readonly queryFn: () => Promise<readonly CoachReviewTeam[]>;
  readonly enabled: boolean;
  readonly staleTime: 0;
  readonly gcTime: 0;
  readonly retry: 0;
  readonly networkMode: "always";
  readonly refetchOnMount: "always";
};

export function coachCheckInReviewQueryOptions(args: {
  /** The verified authenticated coach user id, or undefined while signed out. */
  readonly userId: string | undefined;
  readonly load: (userId: string) => Promise<readonly CoachReviewTeam[]>;
}): CoachCheckInReviewQueryOptions {
  const { userId, load } = args;

  return {
    queryKey: authScopedKeys.coachCheckInReview(
      userId ?? ANONYMOUS_KEY_USER_ID,
    ),
    // Only ever called while `enabled`, which requires a verified id.
    queryFn: () => load(userId as string),
    enabled: userId !== undefined,
    staleTime: 0,
    gcTime: 0,
    retry: 0,
    networkMode: "always",
    refetchOnMount: "always",
  };
}
