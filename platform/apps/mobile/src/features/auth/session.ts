/**
 * Reading a stored session, failing closed.
 *
 * A stored session comes out of on-device storage, which means it can be
 * absent, truncated, hand-edited, or left over from an older schema. Every one
 * of those cases must resolve to "signed out".
 *
 * **A session candidate is not an identity.** `getSession()` proves only that
 * something is stored; it does not prove the JWT is authentic. This module
 * therefore produces a `SessionCandidate`, which is explicitly untrusted and is
 * only good for two things: deciding whether verification is worth attempting,
 * and cross-checking the verified subject afterwards. The authenticated
 * identity is produced by `claims.ts` from a verified `sub`.
 *
 * Nothing here returns, stores, or logs the access or refresh token.
 */

/** A verified user. Only `claims.ts` may construct one. */
export type AuthenticatedIdentity = {
  readonly userId: string;
};

/**
 * An unverified claim about who is signed in, read from local storage.
 *
 * Deliberately a distinct type from `AuthenticatedIdentity` so the two cannot
 * be confused at a call site: no route guard or query key accepts this.
 */
export type SessionCandidate = {
  readonly unverifiedUserId: string;
};

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

/**
 * Reduces an unknown stored session to a candidate, or to `null`.
 *
 * `null` is the only failure mode: there is no partially-valid session worth
 * keeping. This is a cheap structural pre-check that avoids a pointless
 * verification round trip when nothing usable is stored.
 */
export function readSessionCandidate(
  session: unknown,
): SessionCandidate | null {
  if (typeof session !== "object" || session === null) {
    return null;
  }

  const candidate = session as {
    access_token?: unknown;
    user?: unknown;
  };

  // Without a token there is nothing for getClaims to verify.
  if (!isNonEmptyString(candidate.access_token)) {
    return null;
  }

  if (typeof candidate.user !== "object" || candidate.user === null) {
    return null;
  }

  const user = candidate.user as { id?: unknown };

  if (!isNonEmptyString(user.id)) {
    return null;
  }

  return { unverifiedUserId: user.id };
}

/**
 * Whether the identity changed between two applied results.
 *
 * Used to decide when auth-bound cached data has to be discarded. A change from
 * one user to another and a change from signed in to signed out both count.
 */
export function identityChanged(
  previous: AuthenticatedIdentity | null,
  next: AuthenticatedIdentity | null,
): boolean {
  if (previous === null && next === null) {
    return false;
  }

  if (previous === null || next === null) {
    return true;
  }

  return previous.userId !== next.userId;
}
