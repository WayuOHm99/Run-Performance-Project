import "react-native-url-polyfill/auto";

import { createClient, processLock } from "@supabase/supabase-js";
import { AppState, Platform, type NativeEventSubscription } from "react-native";

import type { AppSupabaseClient } from "./app-client";
import { createAuthPersistenceOptions } from "./auth-options";
import type { Database } from "./database.types";
import {
  readPublicSupabaseEnvironment,
  type PublicSupabaseEnvironment,
} from "./environment";
import {
  nativeCiphertextStore,
  nativeSessionCrypto,
  nativeSessionKeyStore,
} from "./native-session-storage";
import { createSecureSessionStorage } from "./secure-session-storage";

// The client carries the generated schema types, so a typo in a column name or
// a table this app holds no grant on fails at typecheck rather than at runtime.
// The types are generated from the local database only; see the mobile README.

let supabaseClient: AppSupabaseClient | undefined;
let appStateSubscription: NativeEventSubscription | undefined;

function createConfiguredClient(
  environment: PublicSupabaseEnvironment,
): AppSupabaseClient {
  // Native stores an AES-256-GCM envelope; the session never reaches
  // AsyncStorage in readable form. Web persists nothing. See `auth-options.ts`.
  const persistence = createAuthPersistenceOptions({
    isWeb: Platform.OS === "web",
    createStorage: () =>
      createSecureSessionStorage({
        keys: nativeSessionKeyStore,
        ciphertexts: nativeCiphertextStore,
        crypto: nativeSessionCrypto,
      }),
  });

  return createClient<Database>(environment.url, environment.publishableKey, {
    auth: {
      ...persistence,
      lock: processLock,
    },
  });
}

function startNativeAuthLifecycle(client: AppSupabaseClient): void {
  if (Platform.OS === "web" || appStateSubscription) {
    return;
  }

  const updateRefreshState = (state: string) => {
    if (state === "active") {
      client.auth.startAutoRefresh();
      return;
    }

    client.auth.stopAutoRefresh();
  };

  updateRefreshState(AppState.currentState);
  appStateSubscription = AppState.addEventListener(
    "change",
    updateRefreshState,
  );
}

export function getSupabaseClient(): AppSupabaseClient {
  if (!supabaseClient) {
    // The endpoint is validated before `createClient` is ever called, so a
    // rejected URL means no client exists rather than a client pointed
    // somewhere it should not be. `isAndroid` is passed because the emulator's
    // host-loopback alias is accepted on Android and nowhere else; see
    // `environment.ts`.
    const environment = readPublicSupabaseEnvironment({
      isAndroid: Platform.OS === "android",
    });
    supabaseClient = createConfiguredClient(environment);
    startNativeAuthLifecycle(supabaseClient);
  }

  return supabaseClient;
}
