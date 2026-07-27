import "react-native-url-polyfill/auto";

import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  createClient,
  processLock,
  type SupabaseClient,
} from "@supabase/supabase-js";
import { AppState, Platform, type NativeEventSubscription } from "react-native";

import {
  readPublicSupabaseEnvironment,
  type PublicSupabaseEnvironment,
} from "./environment";

let supabaseClient: SupabaseClient | undefined;
let appStateSubscription: NativeEventSubscription | undefined;

function createConfiguredClient(
  environment: PublicSupabaseEnvironment,
): SupabaseClient {
  return createClient(environment.url, environment.publishableKey, {
    auth: {
      ...(Platform.OS === "web" ? {} : { storage: AsyncStorage }),
      autoRefreshToken: true,
      persistSession: true,
      detectSessionInUrl: false,
      lock: processLock,
    },
  });
}

function startNativeAuthLifecycle(client: SupabaseClient): void {
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

export function getSupabaseClient(): SupabaseClient {
  if (!supabaseClient) {
    const environment = readPublicSupabaseEnvironment();
    supabaseClient = createConfiguredClient(environment);
    startNativeAuthLifecycle(supabaseClient);
  }

  return supabaseClient;
}
