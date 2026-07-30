/**
 * The two hooks the check-in card uses.
 *
 * Thin by design: the cache rules live in `query-options.ts` and the data access
 * lives in `check-in-repository.ts`, both of which are tested without a renderer.
 * All this layer does is bind them to the verified identity and the query client.
 *
 * The user id always comes from `useAuth`, which exposes only an identity
 * verified against the JWT `sub`. It is never read from a prop, a route
 * parameter, or the form.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/auth-provider";
import { authScopedKeys } from "@/lib/query/keys";

import { loadDailyCheckIn, saveDailyCheckIn } from "./check-in-repository";
import {
  checkInQueryOptions,
  saveCheckInMutationOptions,
} from "./query-options";

/** Today's check-in for the signed-in athlete, or `null` if there is none yet. */
export function useDailyCheckInQuery(localDate: string) {
  const { client, identity } = useAuth();

  return useQuery(
    checkInQueryOptions({
      userId: identity?.userId,
      localDate,
      load: (userId, date) => loadDailyCheckIn(client, userId, date),
    }),
  );
}

/**
 * Saves today's check-in and refreshes exactly the date that was written.
 *
 * No optimistic update: the cache is refreshed from the server rather than
 * assumed, so what the athlete sees after saving is what was actually stored.
 */
export function useSaveDailyCheckIn() {
  const { client, identity } = useAuth();
  const queryClient = useQueryClient();
  const userId = identity?.userId;

  return useMutation(
    saveCheckInMutationOptions({
      save: (localDate, input) =>
        saveDailyCheckIn(client, userId as string, localDate, input),
      invalidate: (localDate) => {
        if (userId === undefined) {
          return;
        }

        void queryClient.invalidateQueries({
          queryKey: authScopedKeys.dailyCheckIn(userId, localDate),
        });
      },
    }),
  );
}
