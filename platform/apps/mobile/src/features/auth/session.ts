/**
 * Session restore, failing closed.
 *
 * A restored session comes out of on-device storage, which means it can be
 * absent, truncated, hand-edited, or left over from an older schema. Every one
 * of those cases must resolve to "signed out", never to a partially trusted
 * session, because the alternative is rendering a protected shell around a
 * user id that was read out of a corrupt blob.
 *
 * Nothing here returns, stores, or logs the access or refresh token. Only the
 * user id is lifted out, and only after the surrounding shape has been checked.
 */

export type AuthenticatedIdentity = {
  readonly userId: string;
};

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

/**
 * Reduces an unknown restored-session value to an identity, or to `null`.
 *
 * `null` is the only failure mode on purpose: there is no "unknown" identity to
 * fall back to and no partially-valid session worth keeping. Anything this
 * function cannot fully vouch for is treated as signed out.
 */
export function readAuthenticatedIdentity(
  session: unknown,
): AuthenticatedIdentity | null {
  if (typeof session !== "object" || session === null) {
    return null;
  }

  const candidate = session as {
    access_token?: unknown;
    user?: unknown;
  };

  // A session without a usable token cannot authorize a request, so treating it
  // as signed in would only produce a screen full of failed queries.
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

  return { userId: user.id };
}

/**
 * Whether the identity changed between two restores.
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
