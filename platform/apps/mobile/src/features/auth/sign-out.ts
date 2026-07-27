/**
 * Sign-out orchestration.
 *
 * Extracted from `AuthProvider` so the ordering guarantee below is testable
 * without a renderer, against the real reducer and the real gate.
 *
 * ## The rule: close locally first, then talk to the server
 *
 * The obvious implementation — `await signOutGlobally(); then clear state` —
 * has a hole that TASK-010 widened. Supabase's `_removeSession` stops before it
 * emits `SIGNED_OUT` if `storage.removeItem()` throws, and TASK-010's encrypted
 * adapter throws by design whenever either backend fails to remove its half. So
 * on exactly the failure that matters, no `SIGNED_OUT` ever arrives, the awaited
 * call rejects, and the previous identity plus its protected routes stay live
 * until the app restarts — even though the persisted session is already
 * unusable.
 *
 * A sign-out the user initiated is authoritative about the *local* identity, so
 * nothing here waits for the network or for Supabase to agree. The local
 * identity, protected routing, and the auth-scoped cache are closed before any
 * I/O begins, and no later result can reopen them.
 *
 * The remote call still runs, and its failure is still reported — the user
 * should know their other devices may not have been signed out — but that
 * report is a sanitized error, and it arrives *after* local access is already
 * closed.
 */

import { AuthActionError } from "./auth-repository";
import type { AuthEvent } from "./auth-state";
import { authErrorMessage, classifyAuthError } from "./errors";
import type { SequenceToken } from "./sequence";

export type SignOutPorts = {
  /** Claims the next sequence token, so no older signal can outrank this one. */
  readonly claimToken: () => SequenceToken;
  readonly dispatch: (event: AuthEvent) => void;
  /** Drops every auth-scoped cache entry for the outgoing identity. */
  readonly clearAuthScopedCache: () => void;
  /** The remote sign-out. Allowed to reject. */
  readonly signOutGlobally: () => Promise<void>;
};

/**
 * Signs out locally first, then globally.
 *
 * Rejects with a sanitized `AuthActionError` when the remote sign-out fails.
 * The local sign-out has already happened by then and is never rolled back: a
 * failed remote call is a reason to warn, never a reason to keep the user
 * signed in.
 */
export async function performSignOut(ports: SignOutPorts): Promise<void> {
  // Ordering here is the whole point. Both of these run before any await, so
  // there is no suspension point at which the old identity is still readable.
  ports.dispatch({ type: "sign-out-initiated", token: ports.claimToken() });
  ports.clearAuthScopedCache();

  try {
    await ports.signOutGlobally();
  } catch (error) {
    // Re-sanitized rather than re-thrown. Whatever Supabase surfaces here — a
    // SessionStorageError, an AuthActionError, or a raw native error from the
    // storage backend — is collapsed into a fixed message and a coarse
    // category. `classifyAuthError` reads only `code`, `status`, and `name`,
    // never a message body, so no token, key, ciphertext, storage value, email,
    // user id, or native error string can travel out with it. No `cause` is
    // attached.
    throw new AuthActionError(
      classifyAuthError(error),
      authErrorMessage(error),
    );
  }
}
