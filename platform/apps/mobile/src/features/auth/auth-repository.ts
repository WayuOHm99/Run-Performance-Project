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

import type { Credentials } from "./credentials";
import {
  authErrorMessage,
  classifyAuthError,
  type AuthFailure,
} from "./errors";
import {
  readAuthenticatedIdentity,
  type AuthenticatedIdentity,
} from "./session";

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
  return readAuthenticatedIdentity(result.session) === null
    ? { kind: "confirmation-required" }
    : { kind: "session" };
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

  if (error) {
    throw toAuthActionError(error);
  }

  return classifySignUpResult({ session: data.session });
}

export async function signInWithPassword(
  client: AuthClient,
  credentials: Credentials,
): Promise<AuthenticatedIdentity> {
  const { data, error } = await client.auth.signInWithPassword({
    email: credentials.email,
    password: credentials.password,
  });

  if (error) {
    throw toAuthActionError(error);
  }

  const identity = readAuthenticatedIdentity(data.session);

  if (identity === null) {
    // A sign-in that reports success without a usable session is a state we
    // refuse to interpret, so it fails closed rather than half-authenticating.
    throw new AuthActionError("unknown", authErrorMessage(null));
  }

  return identity;
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

/**
 * Reads the restored session, failing closed.
 *
 * A storage read that throws, or a session that does not survive
 * `readAuthenticatedIdentity`, both resolve to signed out rather than
 * propagating. A corrupt blob must not be able to wedge the app on the loading
 * screen.
 */
export async function restoreIdentity(
  client: AuthClient,
): Promise<AuthenticatedIdentity | null> {
  try {
    const { data, error } = await client.auth.getSession();

    if (error) {
      return null;
    }

    return readAuthenticatedIdentity(data.session);
  } catch {
    return null;
  }
}
