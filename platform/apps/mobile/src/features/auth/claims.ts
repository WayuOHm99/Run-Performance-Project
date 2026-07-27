/**
 * Verified-claims validation.
 *
 * `getSession()` reads on-device storage. It proves only that *something* is
 * stored, never that the stored JWT is authentic, so a session object alone
 * must not produce an authenticated identity. `supabase.auth.getClaims()` is
 * the supported verification path: for an asymmetric signing key it verifies
 * the signature locally against the cached JWKS, and for a symmetric secret it
 * validates at the Auth server. This module turns that result into an identity,
 * or into nothing.
 *
 * The identity is taken from the verified `sub` claim. It is never taken from
 * the stored `user.id`, because that value is attacker-controlled on a device
 * with writable storage.
 *
 * Every rejection path returns `null`. There is no partially-trusted outcome.
 * Nothing here logs or returns a token, a claim value, or an error.
 */

import type { AuthenticatedIdentity } from "./session";

/** Supabase issues user JWTs with this role; anything else is not a user. */
const AUTHENTICATED_ROLE = "authenticated";

export type VerifiedClaimsOptions = {
  /** Injected for testing. Defaults to the current wall clock. */
  readonly now?: number;
};

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

/**
 * Reduces a `getClaims()` result to a verified identity, or to `null`.
 *
 * Accepts `unknown` on purpose: this is a trust boundary, so the shape is
 * checked rather than assumed, and a client-library change cannot silently
 * widen what is accepted.
 */
export function readVerifiedIdentity(
  result: unknown,
  options: VerifiedClaimsOptions = {},
): AuthenticatedIdentity | null {
  if (typeof result !== "object" || result === null) {
    return null;
  }

  const candidate = result as { data?: unknown; error?: unknown };

  // A verification error means unverifiable, which means signed out.
  if (candidate.error !== null && candidate.error !== undefined) {
    return null;
  }

  if (typeof candidate.data !== "object" || candidate.data === null) {
    return null;
  }

  const data = candidate.data as { claims?: unknown };

  if (typeof data.claims !== "object" || data.claims === null) {
    return null;
  }

  const claims = data.claims as {
    sub?: unknown;
    exp?: unknown;
    role?: unknown;
    is_anonymous?: unknown;
  };

  if (!isNonEmptyString(claims.sub)) {
    return null;
  }

  // getClaims already rejects an expired token, but the check is repeated here
  // so the rule holds even if a caller ever passes `allowExpired`.
  if (claims.exp !== undefined) {
    if (typeof claims.exp !== "number" || !Number.isFinite(claims.exp)) {
      return null;
    }

    const nowInSeconds = Math.floor((options.now ?? Date.now()) / 1000);

    if (claims.exp <= nowInSeconds) {
      return null;
    }
  }

  // `role` is a required Supabase claim. A token carrying anything else is not
  // an authenticated end user and must not open a role area.
  if (claims.role !== undefined && claims.role !== AUTHENTICATED_ROLE) {
    return null;
  }

  // Anonymous sign-in is disabled for this project. An anonymous token must
  // never satisfy authentication here even if it were ever enabled upstream.
  if (claims.is_anonymous === true) {
    return null;
  }

  return { userId: claims.sub };
}

/**
 * Whether the verified subject matches the identity the stored session claimed.
 *
 * A mismatch means the stored session and the verified token disagree about who
 * the user is. That should be impossible in normal operation, so it is treated
 * as tampering and fails closed rather than trusting either side.
 */
export function verifiedIdentityMatches(
  storedUserId: string,
  verified: AuthenticatedIdentity,
): boolean {
  return storedUserId === verified.userId;
}
