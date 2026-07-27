import { useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PropsWithChildren,
} from "react";

import type { AppSupabaseClient } from "@/features/profile/account-repository";
import { clearAuthScopedQueries } from "@/lib/query/client";
import { getSupabaseClient } from "@/lib/supabase/client";

import {
  readStoredSession,
  resolveVerifiedIdentity,
  signOutGlobally,
} from "./auth-repository";
import {
  INITIAL_SEQUENCE_TOKEN,
  nextSequenceToken,
  shouldApplyResult,
  type SequenceToken,
} from "./sequence";
import { identityChanged, type AuthenticatedIdentity } from "./session";

type AuthContextValue = {
  readonly client: AppSupabaseClient;
  readonly restored: boolean;
  readonly identity: AuthenticatedIdentity | null;
  readonly awaitingEmailConfirmation: boolean;
  readonly beginEmailConfirmation: () => void;
  readonly dismissEmailConfirmation: () => void;
  readonly signOut: () => Promise<void>;
};

/** A raw auth observation, tagged with the order in which it was seen. */
type AuthSignal = {
  readonly token: SequenceToken;
  readonly session: unknown;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const queryClient = useQueryClient();
  const client = useMemo(() => getSupabaseClient(), []);

  const [restored, setRestored] = useState(false);
  const [identity, setIdentity] = useState<AuthenticatedIdentity | null>(null);
  const [signal, setSignal] = useState<AuthSignal | null>(null);
  const [emailConfirmationRequested, setEmailConfirmationRequested] =
    useState(false);

  // Derived rather than stored, so signing in never leaves a stale
  // check-email state behind and no effect has to reset it.
  const awaitingEmailConfirmation =
    identity === null && emailConfirmationRequested;

  // Monotonic ordering for asynchronous auth work. `issued` hands out tokens,
  // `emitted` drops an observation that a newer one already superseded, and
  // `applied` drops a validation result that finished too late to matter.
  const issuedToken = useRef<SequenceToken>(INITIAL_SEQUENCE_TOKEN);
  const emittedToken = useRef<SequenceToken>(INITIAL_SEQUENCE_TOKEN);
  const appliedToken = useRef<SequenceToken>(INITIAL_SEQUENCE_TOKEN);

  // Tracks the identity the cache currently belongs to, so a change can be
  // detected without adding the identity to an effect dependency.
  const cachedIdentity = useRef<AuthenticatedIdentity | null>(null);

  useEffect(() => {
    let active = true;

    const claimToken = (): SequenceToken => {
      issuedToken.current = nextSequenceToken(issuedToken.current);
      return issuedToken.current;
    };

    const emit = (token: SequenceToken, session: unknown) => {
      if (!active || !shouldApplyResult(token, emittedToken.current)) {
        return;
      }

      emittedToken.current = token;
      setSignal({ token, session });
    };

    const { data } = client.auth.onAuthStateChange((_event, session) => {
      // Synchronous by design. Calling another Supabase Auth method from
      // inside this callback can re-enter the auth lock and deadlock, so this
      // only records the observation. Verification is scheduled by the effect
      // below, outside the callback.
      emit(claimToken(), session);
    });

    // The token is claimed *before* the read starts, not when it resolves, so
    // a restore that finishes after a later sign-out carries the older token
    // and is discarded instead of resurrecting the session.
    const restoreToken = claimToken();

    void readStoredSession(client).then((session) => {
      emit(restoreToken, session);
    });

    return () => {
      active = false;
      data.subscription.unsubscribe();
    };
  }, [client]);

  useEffect(() => {
    if (signal === null) {
      return undefined;
    }

    let active = true;

    // A stored session is only a claim. The identity below comes from the
    // verified JWT `sub`, and any failure resolves to null, which the gate
    // reads as signed out. `restored` stays false until the first result is
    // applied, so no protected route can render while this is pending.
    void resolveVerifiedIdentity(client, signal.session).then((verified) => {
      if (!active || !shouldApplyResult(signal.token, appliedToken.current)) {
        return;
      }

      appliedToken.current = signal.token;
      setIdentity(verified);
      setRestored(true);
    });

    return () => {
      active = false;
    };
  }, [signal, client]);

  useEffect(() => {
    if (!identityChanged(cachedIdentity.current, identity)) {
      return;
    }

    // The user changed, or signed out. Drop every auth-bound entry before the
    // next render can read one that belonged to the previous account.
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
