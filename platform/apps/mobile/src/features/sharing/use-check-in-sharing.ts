/**
 * The two hooks the sharing section uses.
 *
 * Thin by design: the cache rules live in `query-options.ts`, the validation in
 * `domain.ts`, and the data access in `sharing-repository.ts`, all of which are
 * tested without a renderer. This layer only binds them to the verified identity
 * and the query client.
 *
 * The user id always comes from `useAuth`, which exposes only an identity verified
 * against the JWT `sub`. It is never read from a prop, a route parameter, or the
 * section — which does not even have access to it.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/auth-provider";

import type { TeamSharingState } from "./domain";
import {
  checkInSharingQueryOptions,
  sharingActionMutationOptions,
} from "./query-options";
import {
  grantCheckInSharing,
  loadCheckInSharing,
  revokeCheckInSharing,
} from "./sharing-repository";

/** Every active athlete team of the signed-in user, with its sharing state. */
export function useCheckInSharingQuery() {
  const { client, identity } = useAuth();

  return useQuery(
    checkInSharingQueryOptions({
      userId: identity?.userId,
      load: (userId) => loadCheckInSharing(client, userId),
    }),
  );
}

/**
 * Grants or revokes check-in sharing for one team, then refreshes the list.
 *
 * `teams` is the currently loaded list and is the only source of a writable team
 * id, so the caller passes what the server returned rather than anything the UI
 * assembled. `refetchKey` receives the key captured inside `mutationFn` before the
 * write began, so the entry refreshed is the one the write actually targeted even
 * if the identity changed while the request was in flight. The query client itself
 * is stable across renders, which is why passing it through a closure here is safe
 * while passing the user id would not be.
 */
export function useSharingAction(teams: readonly TeamSharingState[]) {
  const { client, identity } = useAuth();
  const queryClient = useQueryClient();

  return useMutation(
    sharingActionMutationOptions({
      userId: identity?.userId,
      teams,
      grant: (target) => grantCheckInSharing(client, target),
      revoke: (target) => revokeCheckInSharing(client, target),
      refetchKey: (queryKey) => queryClient.invalidateQueries({ queryKey }),
    }),
  );
}
