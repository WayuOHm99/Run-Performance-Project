import "react-native-url-polyfill/auto";

import AsyncStorage from "@react-native-async-storage/async-storage";
import { createClient, processLock } from "@supabase/supabase-js";
import { AppState, Platform, type NativeEventSubscription } from "react-native";

import type { AppSupabaseClient } from "./app-client";
import type { Database } from "./database.types";
import {
  readPublicSupabaseEnvironment,
  type PublicSupabaseEnvironment,
} from "./environment";

// The client carries the generated schema types, so a typo in a column name or
// a table this app holds no grant on fails at typecheck rather than at runtime.
// The types are generated from the local database only; see the mobile README.

let supabaseClient: AppSupabaseClient | undefined;
let appStateSubscription: NativeEventSubscription | undefined;

function createConfiguredClient(
  environment: PublicSupabaseEnvironment,
): AppSupabaseClient {
  return createClient<Database>(environment.url, environment.publishableKey, {
    auth: {
      ...(Platform.OS === "web" ? {} : { storage: AsyncStorage }),
      autoRefreshToken: true,
      persistSession: true,
      detectSessionInUrl: false,
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
    const environment = readPublicSupabaseEnvironment();
    supabaseClient = createConfiguredClient(environment);
    startNativeAuthLifecycle(supabaseClient);
  }

  return supabaseClient;
}
