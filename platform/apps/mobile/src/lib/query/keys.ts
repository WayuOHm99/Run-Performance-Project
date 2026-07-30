/**
 * Query keys for auth-bound server state.
 *
 * Every key in here embeds the authenticated user id. That is not for cache
 * granularity, it is a correctness rule: a key without the user id would let
 * one account read a cache entry populated by another after a sign-out and
 * sign-in on the same device.
 *
 * The shared `AUTH_SCOPE` prefix additionally makes "drop everything belonging
 * to a signed-in user" expressible as one predicate, which is what
 * `clearAuthScopedQueries` uses.
 */

export const AUTH_SCOPE = "auth-scoped" as const;

export const authScopedKeys = {
  /** Everything owned by one user. Use for invalidation, not for a query. */
  user: (userId: string) => [AUTH_SCOPE, userId] as const,
  profile: (userId: string) => [AUTH_SCOPE, userId, "profile"] as const,
  memberships: (userId: string) => [AUTH_SCOPE, userId, "memberships"] as const,
  account: (userId: string) => [AUTH_SCOPE, userId, "account"] as const,
  /**
   * One athlete's own check-in for one device-local calendar date.
   *
   * The date is part of the key, not a filter applied afterwards, so crossing
   * midnight or a timezone produces a different entry rather than serving
   * yesterday's answers as today's. It is a plain calendar date and carries no
   * health value — the three protected values stay in the cached data, which is
   * memory-only and dropped outright by `clearAuthScopedQueries`.
   */
  dailyCheckIn: (userId: string, localDate: string) =>
    [AUTH_SCOPE, userId, "daily-check-in", localDate] as const,
} as const;

/** True for any key produced by `authScopedKeys`. */
export function isAuthScopedKey(key: readonly unknown[]): boolean {
  return key[0] === AUTH_SCOPE;
}

/** The user id a scoped key belongs to, or null if it is not a scoped key. */
export function authScopedUserId(key: readonly unknown[]): string | null {
  if (!isAuthScopedKey(key)) {
    return null;
  }

  const userId = key[1];

  return typeof userId === "string" ? userId : null;
}
