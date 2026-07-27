/**
 * Supabase Auth calls.
 *
 * The client is passed in rather than imported so this module stays free of
 * React Native imports and can be unit-tested against a hand-written double
 * with no network and no native runtime.
 *
 * Every function here raises `AuthActionError`, which carries only a
 * pre-sanitized message and a coarse failure category. The original error
 * object never escapes, so an email address, token, request payload, or server
 * string cannot reach a screen or a log through this path.
 */

import type { SupabaseClient } from "@supabase/supabase-js";

import { readVerifiedIdentity } from "./claims";
import type { Credentials } from "./credentials";
import {
  authErrorMessage,
  classifyAuthError,
  isExistingAccountError,
  type AuthFailure,
} from "./errors";
import { readSessionCandidate, type AuthenticatedIdentity } from "./session";

export type AuthClient = Pick<SupabaseClient, "auth">;

export class AuthActionError extends Error {
  override readonly name = "AuthActionError";
  readonly failure: AuthFailure;

  constructor(failure: AuthFailure, message: string) {
    super(message);
    this.failure = failure;
  }
}

function toAuthActionError(error: unknown): AuthActionError {
  return new AuthActionError(classifyAuthError(error), authErrorMessage(error));
}

/**
 * A sign-up either hands back a session or does not.
 *
 * A null session means the project requires email confirmation. That is a
 * normal outcome, not a failure, and it is the only signal this task acts on:
 * there is no confirmation deep-link handling here.
 */
export type SignUpOutcome =
  { readonly kind: "session" } | { readonly kind: "confirmation-required" };

export function classifySignUpResult(result: {
  session: unknown;
}): SignUpOutcome {
  return readSessionCandidate(result.session) === null
    ? { kind: "confirmation-required" }
    : { kind: "session" };
}

/**
 * Decides what a sign-up response means, without leaking account existence.
 *
 * Pure, so the enumeration-resistance rule is testable on its own. Three inputs
 * collapse into the single `confirmation-required` outcome:
 *
 *   * a null session, which is what an unconfirmed *new* account looks like;
 *   * an obfuscated user with no session, which is what Supabase returns for an
 *     *existing* address while confirmations are enabled;
 *   * an existing-account error code, which is what it returns instead while
 *     confirmations are disabled.
 *
 * A caller therefore cannot tell those three apart, which is the point.
 */
export function resolveSignUpResponse(response: {
  session: unknown;
  error: unknown;
}): SignUpOutcome {
  if (response.error !== null && response.error !== undefined) {
    if (isExistingAccountError(response.error)) {
      return { kind: "confirmation-required" };
    }

    throw toAuthActionError(response.error);
  }

  return classifySignUpResult({ session: response.session });
}

/**
 * Creates an account from an email and password and nothing else.
 *
 * No `options.data`, no display name, no role, no team, and no membership is
 * sent. Anything written here would land in `raw_user_meta_data`, which is
 * user-controlled and is never an authorization input; roles come from
 * `team_memberships` under RLS.
 */
export async function signUpWithPassword(
  client: AuthClient,
  credentials: Credentials,
): Promise<SignUpOutcome> {
  const { data, error } = await client.auth.signUp({
    email: credentials.email,
    password: credentials.password,
  });

  return resolveSignUpResponse({ session: data.session, error });
}

/**
 * Signs in, and fails closed on any response that is not a usable session.
 *
 * Deliberately returns nothing. The authoritative identity is produced by
 * `resolveVerifiedIdentity` in the provider, from verified JWT claims; returning
 * an identity from here would create a second, weaker source of truth.
 */
export async function signInWithPassword(
  client: AuthClient,
  credentials: Credentials,
): Promise<void> {
  const { data, error } = await client.auth.signInWithPassword({
    email: credentials.email,
    password: credentials.password,
  });

  if (error) {
    throw toAuthActionError(error);
  }

  if (readSessionCandidate(data.session) === null) {
    // Success without a usable session is a state we refuse to interpret.
    throw new AuthActionError("unknown", authErrorMessage(null));
  }
}

/**
 * Signs out everywhere.
 *
 * Global scope on purpose: a user signing out after losing a device expects the
 * other sessions to end too, and TASK-009 offers no per-device session view
 * that would make a local-only sign-out understandable.
 */
export async function signOutGlobally(client: AuthClient): Promise<void> {
  const { error } = await client.auth.signOut({ scope: "global" });

  if (error) {
    throw toAuthActionError(error);
  }
}

/** Reads the stored session without interpreting it. Fails closed on throw. */
export async function readStoredSession(client: AuthClient): Promise<unknown> {
  try {
    const { data, error } = await client.auth.getSession();

    return error ? null : data.session;
  } catch {
    return null;
  }
}

/**
 * Turns a stored session into a **verified** identity, or into `null`.
 *
 * This is the only function in the app that produces an `AuthenticatedIdentity`
 * from storage, and it does so from the JWT's verified `sub` claim rather than
 * from the stored `user.id`.
 *
 * Order matters:
 *
 *   1. a cheap structural check, so a missing or truncated blob costs no round
 *      trip;
 *   2. `getClaims()`, which verifies the signature and expiry;
 *   3. a cross-check that the verified subject matches what storage claimed.
 *
 * Step 3 catches a stored session whose user was swapped while the token was
 * left intact. Any failure at any step returns `null`; there is no partially
 * trusted result and no error is propagated to a caller that might display it.
 */
export async function resolveVerifiedIdentity(
  client: AuthClient,
  session: unknown,
): Promise<AuthenticatedIdentity | null> {
  const candidate = readSessionCandidate(session);

  if (candidate === null) {
    return null;
  }

  try {
    const verified = readVerifiedIdentity(await client.auth.getClaims());

    if (verified === null) {
      return null;
    }

    if (verified.userId !== candidate.unverifiedUserId) {
      // Storage and the verified token disagree about who this is. Treated as
      // tampering rather than trusting either side.
      return null;
    }

    return verified;
  } catch {
    return null;
  }
}
