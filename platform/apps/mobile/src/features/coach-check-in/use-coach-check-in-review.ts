/**
 * The single hook the coach review uses.
 *
 * Thin by design: the cache rules live in `query-options.ts`, the validation in
 * `domain.ts`, the data access in `coach-review-repository.ts`, and the rendered
 * derivation in `view-state.ts`, all of which are tested without a renderer. This
 * layer only binds them to the verified identity.
 *
 * The user id always comes from `useAuth`, which exposes only an identity verified
 * against the JWT `sub`. It is never read from a prop, a route parameter, or the
 * section — which does not even have access to it.
 *
 * There is deliberately **no mutation hook and no query client here**. This feature
 * performs no write, and it has no cross-entry invalidation to do: its one entry is
 * `staleTime: 0` and `refetchOnMount: "always"`, so a deliberate `refetch` is the
 * whole refresh mechanism.
 */

import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/auth-provider";

import { loadCoachCheckInReview } from "./coach-review-repository";
import { coachCheckInReviewQueryOptions } from "./query-options";

/** Every team the signed-in coach actively coaches, with its shared check-ins. */
export function useCoachCheckInReviewQuery() {
  const { client, identity } = useAuth();

  return useQuery(
    coachCheckInReviewQueryOptions({
      userId: identity?.userId,
      load: (userId) => loadCoachCheckInReview(client, userId),
    }),
  );
}
