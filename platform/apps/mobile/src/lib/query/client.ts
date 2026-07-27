/**
 * The TanStack Query client.
 *
 * Two privacy decisions are encoded here.
 *
 * 1. **The cache is never persisted to disk.** No persister, no
 *    `PersistQueryClientProvider`, no AsyncStorage-backed storage. Profile and
 *    membership data therefore live only in memory and disappear when the
 *    process does. This matters more once health data exists, so the rule is
 *    established before it does.
 *
 * 2. **Auth-bound data is dropped, not merely invalidated, when the user
 *    changes.** `clearAuthScopedQueries` removes the entries outright, so no
 *    stale value from a previous account can be served while a refetch is in
 *    flight.
 */

import { QueryClient } from "@tanstack/react-query";

import { isAuthScopedKey } from "./keys";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Short: membership and role state must reflect a revocation quickly.
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        retry: 1,
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: 0,
      },
    },
  });
}

/**
 * Removes every cached entry that belongs to a signed-in user.
 *
 * Called on sign-out and whenever the restored identity changes. `removeQueries`
 * rather than `invalidateQueries`: invalidation keeps the old data readable
 * until a refetch resolves, which would briefly show the previous account's
 * profile to the new one.
 */
export function clearAuthScopedQueries(client: QueryClient): void {
  client.removeQueries({
    predicate: (query) => isAuthScopedKey(query.queryKey),
  });
  client.getMutationCache().clear();
}
