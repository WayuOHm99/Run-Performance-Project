/**
 * The authentication state machine.
 *
 * `AuthProvider` is a thin shell over this reducer: it issues tokens, performs
 * I/O, and dispatches. Every ordering and exposure decision lives here, pure, so
 * the interleavings that matter can be tested without a renderer.
 *
 * Two rules are the whole point of this module, and both were wrong in an
 * earlier revision:
 *
 * 1. **A newer signal invalidates the current identity immediately.** Observing
 *    a sign-out, or a switch to another user, must close protected routing at
 *    once rather than after the new validation settles. Otherwise the previous
 *    user's screens stay live — and their auth-scoped queries stay readable —
 *    for the length of a round trip.
 *
 * 2. **A validation result may apply only if its token is still the latest
 *    observed signal.** "Newer than the last applied result" is not enough:
 *
 *      applied = 1 (user A)      validation for 2 in flight
 *      signal 3 observed         (sign-out, or user B)
 *      2 resolves                2 > 1 passes -> user A reapplied
 *
 *    after signal 3 was already observed. Equality with the latest token is
 *    what closes that hole; the `> appliedToken` term is kept only so a
 *    duplicated result cannot re-apply.
 */

import type { SequenceToken } from "./sequence";
import { INITIAL_SEQUENCE_TOKEN, isNewerSignal } from "./sequence";
import type { AuthenticatedIdentity, SessionCandidate } from "./session";

/**
 * - `restoring` — nothing observed yet, at app start.
 * - `verifying` — a signal is observed and its JWT is being validated. No
 *   identity is exposed in this phase, by construction.
 * - `settled` — the latest signal has been validated; `identity` is either a
 *   verified user or `null` for signed out.
 */
export type AuthPhase = "restoring" | "verifying" | "settled";

export type AuthState = {
  readonly phase: AuthPhase;
  /** The newest auth signal observed. */
  readonly latestToken: SequenceToken;
  /** The token whose validation result is currently applied. */
  readonly appliedToken: SequenceToken;
  /** Only ever non-null while `phase` is `settled`. */
  readonly identity: AuthenticatedIdentity | null;
  /**
   * The unverified candidate for the latest signal, awaiting validation.
   *
   * Deliberately the candidate and not the session: the access and refresh
   * tokens never enter React state at all.
   */
  readonly candidate: SessionCandidate | null;
};

export const INITIAL_AUTH_STATE: AuthState = {
  phase: "restoring",
  latestToken: INITIAL_SEQUENCE_TOKEN,
  appliedToken: INITIAL_SEQUENCE_TOKEN,
  identity: null,
  candidate: null,
};

export type AuthEvent =
  | {
      readonly type: "signal-observed";
      readonly token: SequenceToken;
      readonly candidate: SessionCandidate | null;
    }
  | {
      readonly type: "validation-settled";
      readonly token: SequenceToken;
      readonly identity: AuthenticatedIdentity | null;
    };

/**
 * Whether a validation result is still relevant.
 *
 * Exported so the rule can be asserted directly, not only through the reducer.
 */
export function canApplyValidation(
  token: SequenceToken,
  state: AuthState,
): boolean {
  // Equality: a result is meaningless the moment a newer signal is observed.
  if (token !== state.latestToken) {
    return false;
  }

  // Strictly greater: a repeated result cannot re-apply.
  return token > state.appliedToken;
}

export function authReducer(state: AuthState, event: AuthEvent): AuthState {
  switch (event.type) {
    case "signal-observed": {
      // An out-of-order observation — a slow restore resolving after a newer
      // event — must not reopen an older signal.
      if (!isNewerSignal(event.token, state.latestToken)) {
        return state;
      }

      return {
        phase: "verifying",
        latestToken: event.token,
        appliedToken: state.appliedToken,
        // The previous identity stops being exposed here, before any
        // validation runs. This is what makes a sign-out or a user switch
        // close protected routing immediately.
        identity: null,
        candidate: event.candidate,
      };
    }

    case "validation-settled": {
      if (!canApplyValidation(event.token, state)) {
        return state;
      }

      return {
        phase: "settled",
        latestToken: state.latestToken,
        appliedToken: event.token,
        identity: event.identity,
        candidate: state.candidate,
      };
    }
  }
}

/**
 * Whether session restoration has produced a usable answer.
 *
 * False while restoring *and* while verifying, so the gate reports `restoring`
 * and no protected route renders during either.
 */
export function isAuthSettled(state: AuthState): boolean {
  return state.phase === "settled";
}

/**
 * The identity that may be used for routing and query scoping.
 *
 * Guarded on the phase as well as the field. `identity` is already cleared on
 * every new signal, so this is belt and braces against a future edit that
 * forgets to.
 */
export function authIdentity(state: AuthState): AuthenticatedIdentity | null {
  return state.phase === "settled" ? state.identity : null;
}

/** True while a signal is observed but not yet validated. */
export function isVerificationPending(state: AuthState): boolean {
  return state.phase === "verifying";
}
