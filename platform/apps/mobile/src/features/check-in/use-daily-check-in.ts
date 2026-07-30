/**
 * The two hooks the check-in card uses.
 *
 * Thin by design: the cache rules live in `query-options.ts`, the hydration
 * policy in `hydration.ts`, and the data access in `check-in-repository.ts`, all
 * of which are tested without a renderer. This layer only binds them to the
 * verified identity and the query client.
 *
 * The user id always comes from `useAuth`, which exposes only an identity
 * verified against the JWT `sub`. It is never read from a prop, a route
 * parameter, or the form — the card does not even have access to it.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/auth-provider";

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
 * Saves today's check-in and refreshes exactly the entry that was written.
 *
 * `invalidateKey` receives the key captured inside `mutationFn` before the write
 * began, so the entry refreshed is the one the write actually targeted even if
 * the identity or the day changed while the request was in flight. The query
 * client itself is stable across renders, which is why passing it through a
 * closure here is safe while passing the user id would not be.
 */
export function useSaveDailyCheckIn() {
  const { client, identity } = useAuth();
  const queryClient = useQueryClient();

  return useMutation(
    saveCheckInMutationOptions({
      userId: identity?.userId,
      save: (userId, localDate, input) =>
        saveDailyCheckIn(client, userId, localDate, input),
      invalidateKey: (queryKey) => {
        void queryClient.invalidateQueries({ queryKey });
      },
    }),
  );
}
