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
import { useQueryClient } from "@tanstack/react-query";

import { clearAuthScopedQueries } from "@/lib/query/client";
import { getSupabaseClient } from "@/lib/supabase/client";
import type { AppSupabaseClient } from "@/features/profile/account-repository";

import { restoreIdentity, signOutGlobally } from "./auth-repository";
import {
  identityChanged,
  readAuthenticatedIdentity,
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

export function AuthProvider({ children }: PropsWithChildren) {
  const queryClient = useQueryClient();
  const client = useMemo(() => getSupabaseClient(), []);

  const [restored, setRestored] = useState(false);
  const [identity, setIdentity] = useState<AuthenticatedIdentity | null>(null);
  const [emailConfirmationRequested, setEmailConfirmationRequested] =
    useState(false);

  // Derived rather than stored, so signing in never leaves a stale
  // check-email state behind and no effect has to reset it.
  const awaitingEmailConfirmation =
    identity === null && emailConfirmationRequested;

  // Tracks the identity the cache currently belongs to, so a change can be
  // detected without adding the identity to an effect dependency and
  // re-running the clear on every unrelated render.
  const cachedIdentity = useRef<AuthenticatedIdentity | null>(null);

  useEffect(() => {
    let active = true;

    // Restoration is explicit rather than inferred from the INITIAL_SESSION
    // event, so `restored` flips exactly once and the loading state has a
    // single, testable owner. restoreIdentity already fails closed.
    void restoreIdentity(client).then((restoredIdentity) => {
      if (!active) {
        return;
      }

      setIdentity(restoredIdentity);
      setRestored(true);
    });

    const { data } = client.auth.onAuthStateChange((_event, session) => {
      if (!active) {
        return;
      }

      // Synchronous by design. Calling another Supabase Auth method from
      // inside this callback can re-enter the auth lock and deadlock, so this
      // only moves local state; every fetch is left to TanStack Query.
      setIdentity(readAuthenticatedIdentity(session));
      setRestored(true);
    });

    return () => {
      active = false;
      data.subscription.unsubscribe();
    };
  }, [client]);

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
