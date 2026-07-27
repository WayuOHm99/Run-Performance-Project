import { useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
  type PropsWithChildren,
} from "react";

import type { AppSupabaseClient } from "@/features/profile/account-repository";
import { clearAuthScopedQueries } from "@/lib/query/client";
import { getSupabaseClient } from "@/lib/supabase/client";

import {
  readStoredSession,
  signOutGlobally,
  verifyStoredIdentity,
} from "./auth-repository";
import {
  INITIAL_AUTH_STATE,
  authIdentity,
  authReducer,
  isAuthSettled,
} from "./auth-state";
import { nextSequenceToken, type SequenceToken } from "./sequence";
import {
  identityChanged,
  readSessionCandidate,
  type AuthenticatedIdentity,
} from "./session";

type AuthContextValue = {
  readonly client: AppSupabaseClient;
  readonly restored: boolean;
  readonly identity: AuthenticatedIdentity | null;
  readonly awaitingEmailConfirmation: boolean;
  readonly beginEmailConfirmation: () => void;
  readonly dismissEmailConfirmation: () => void;
  readonly signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

/**
 * Owns the Supabase client, the auth state machine, and the auth-bound cache.
 *
 * All ordering and exposure rules live in `auth-state.ts`. This component only
 * issues tokens, performs I/O, and dispatches, so the behaviour Codex flagged is
 * tested directly against the reducer rather than through a rendered tree.
 */
export function AuthProvider({ children }: PropsWithChildren) {
  const queryClient = useQueryClient();
  const client = useMemo(() => getSupabaseClient(), []);

  const [authState, dispatch] = useReducer(authReducer, INITIAL_AUTH_STATE);
  const [emailConfirmationRequested, setEmailConfirmationRequested] =
    useState(false);

  // Both guarded on the phase, so no identity is readable while a newer signal
  // is still being validated.
  const identity = authIdentity(authState);
  const restored = isAuthSettled(authState);

  // Derived rather than stored, so signing in never leaves a stale
  // check-email state behind and no effect has to reset it.
  const awaitingEmailConfirmation =
    identity === null && emailConfirmationRequested;

  const issuedToken = useRef<SequenceToken>(INITIAL_AUTH_STATE.latestToken);

  // Tracks the identity the cache currently belongs to, so a change can be
  // detected without adding the identity to an effect dependency.
  const cachedIdentity = useRef<AuthenticatedIdentity | null>(null);

  useEffect(() => {
    let active = true;

    const claimToken = (): SequenceToken => {
      issuedToken.current = nextSequenceToken(issuedToken.current);
      return issuedToken.current;
    };

    const observe = (token: SequenceToken, session: unknown) => {
      if (!active) {
        return;
      }

      // readSessionCandidate is pure and synchronous, so calling it here is
      // safe even inside the auth-state callback. Reducing to a candidate also
      // keeps the access and refresh tokens out of React state entirely.
      dispatch({
        type: "signal-observed",
        token,
        candidate: readSessionCandidate(session),
      });
    };

    const { data } = client.auth.onAuthStateChange((_event, session) => {
      // Synchronous by design. Calling another Supabase Auth method from
      // inside this callback can re-enter the auth lock and deadlock, so this
      // only records the observation. Verification is scheduled by the effect
      // below, outside the callback.
      observe(claimToken(), session);
    });

    // The token is claimed *before* the read starts, not when it resolves, so
    // a restore that finishes after a later sign-out carries the older token
    // and the reducer discards it.
    const restoreToken = claimToken();

    void readStoredSession(client).then((session) => {
      observe(restoreToken, session);
    });

    return () => {
      active = false;
      data.subscription.unsubscribe();
    };
  }, [client]);

  const { phase, latestToken, candidate } = authState;

  useEffect(() => {
    if (phase !== "verifying") {
      return undefined;
    }

    let active = true;

    // The identity below comes from the verified JWT `sub`; any failure
    // resolves to null, which the gate reads as signed out. The result is
    // dispatched with the token it was started for, and the reducer applies it
    // only if that token is still the latest observed signal.
    void verifyStoredIdentity(client, candidate).then((verified) => {
      if (!active) {
        return;
      }

      dispatch({
        type: "validation-settled",
        token: latestToken,
        identity: verified,
      });
    });

    return () => {
      // Covers unmount and any newer signal that supersedes this validation.
      active = false;
    };
  }, [phase, latestToken, candidate, client]);

  useEffect(() => {
    if (!identityChanged(cachedIdentity.current, identity)) {
      return;
    }

    // Runs the moment a new signal clears the identity, not when validation
    // finishes, so auth-scoped data for the previous user stops being readable
    // at the signal boundary rather than a round trip later.
    clearAuthScopedQueries(queryClient);
    cachedIdentity.current = identity;
  }, [identity, queryClient]);

  const signOut = useCallback(async () => {
    await signOutGlobally(client);
    // onAuthStateChange clears the cache on the resulting identity change; this
    // is belt and braces for the case where the event is delayed.
    clearAuthScopedQueries(queryClient);
    setEmailConfirmationRequested(false);
  }, [client, queryClient]);

  const beginEmailConfirmation = useCallback(() => {
    setEmailConfirmationRequested(true);
  }, []);

  const dismissEmailConfirmation = useCallback(() => {
    setEmailConfirmationRequested(false);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      client,
      restored,
      identity,
      awaitingEmailConfirmation,
      beginEmailConfirmation,
      dismissEmailConfirmation,
      signOut,
    }),
    [
      client,
      restored,
      identity,
      awaitingEmailConfirmation,
      beginEmailConfirmation,
      dismissEmailConfirmation,
      signOut,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);

  if (value === null) {
    throw new Error("useAuth must be used inside AuthProvider.");
  }

  return value;
}
