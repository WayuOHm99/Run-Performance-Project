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
  /**
   * One athlete's own check-in sharing state, for every team they actively play
   * for.
   *
   * There is deliberately **no team id in the key**: the whole list is one cache
   * entry, so a grant or revoke for one team refreshes the same server-confirmed
   * view that every other team's control is read from. Per-team keys would let two
   * controls disagree about what the database says.
   *
   * The cached value is consent metadata and team names — no health value, and no
   * health value in the key either. It is memory-only and dropped outright by
   * `clearAuthScopedQueries`.
   */
  checkInSharing: (userId: string) =>
    [AUTH_SCOPE, userId, "check-in-sharing"] as const,
  /**
   * One coach's review of the latest check-ins shared with the teams they
   * actively coach.
   *
   * The id in this key is the **coach's**, not any athlete's, because the key
   * names whose *view* this is. There is deliberately **no team id and no athlete
   * id**: the whole review is one cache entry, so a revoked grant cannot leave a
   * per-athlete entry behind that a later render still reads. Per-athlete keys
   * would also put the identity of a consenting athlete into the cache key itself,
   * where `clearAuthScopedQueries` removes it but nothing else would.
   *
   * The cached value carries protected health data — this is the only key that
   * does so for someone other than the caller. It is memory-only, dropped outright
   * by `clearAuthScopedQueries`, and its query sets `gcTime: 0`, so the entry is
   * collectible the moment the screen is left. No health value appears in the key.
   */
  coachCheckInReview: (userId: string) =>
    [AUTH_SCOPE, userId, "coach-check-in-review"] as const,
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
