import { QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useMemo } from "react";

import { AuthProvider } from "@/features/auth/auth-provider";
import { canEnterRoleArea, needsRoleChoice } from "@/features/auth/gate";
import { useAuthGate } from "@/features/profile/use-account";
import { createQueryClient } from "@/lib/query/client";
import { colors } from "@/theme/tokens";

export default function RootLayout() {
  // One client for the lifetime of the app. It is never persisted to disk.
  const queryClient = useMemo(() => createQueryClient(), []);

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <StatusBar style="dark" />
        <GuardedStack />
      </AuthProvider>
    </QueryClientProvider>
  );
}

/**
 * Route guards.
 *
 * `Stack.Protected` removes a screen from the navigator entirely while its
 * guard is false, so a direct navigation to `/athlete` or `/coach` has nothing
 * to navigate to and falls back to the index route, which redirects to wherever
 * the gate says the user actually belongs. That is the fail-closed behaviour:
 * every guard below is derived from the gate, and the gate only ever reports
 * `ready` when a restored session and current active memberships say so.
 *
 * These guards are UX protection. PostgreSQL grants and RLS remain the
 * authorization boundary, and nothing here is a reason to trust a query.
 */
function GuardedStack() {
  const gate = useAuthGate();

  const unauthenticated =
    gate.status === "signed-out" || gate.status === "check-email";
  const busy =
    gate.status === "restoring" ||
    gate.status === "loading-account" ||
    gate.status === "account-error";
  const onboarding = gate.status === "onboarding";
  const pending = gate.status === "no-active-team";
  const canEditProfile = gate.status === "ready" || pending;

  return (
    <Stack
      screenOptions={{
        contentStyle: { backgroundColor: colors.canvas },
        headerShadowVisible: false,
        headerStyle: { backgroundColor: colors.canvas },
        headerTintColor: colors.ink,
        headerTitleStyle: { fontWeight: "700" },
      }}
    >
      <Stack.Screen name="index" options={{ headerShown: false }} />

      <Stack.Protected guard={busy}>
        <Stack.Screen name="loading" options={{ headerShown: false }} />
      </Stack.Protected>

      <Stack.Protected guard={unauthenticated}>
        <Stack.Screen name="sign-in" options={{ headerShown: false }} />
        <Stack.Screen name="sign-up" options={{ title: "สร้างบัญชี" }} />
      </Stack.Protected>

      <Stack.Protected guard={gate.status === "check-email"}>
        <Stack.Screen name="check-email" options={{ headerShown: false }} />
      </Stack.Protected>

      <Stack.Protected guard={onboarding}>
        <Stack.Screen name="onboarding" options={{ headerShown: false }} />
      </Stack.Protected>

      <Stack.Protected guard={pending}>
        <Stack.Screen name="pending" options={{ headerShown: false }} />
      </Stack.Protected>

      <Stack.Protected guard={needsRoleChoice(gate)}>
        <Stack.Screen name="choose-role" options={{ headerShown: false }} />
      </Stack.Protected>

      <Stack.Protected guard={canEditProfile}>
        <Stack.Screen name="profile" options={{ title: "บัญชีของฉัน" }} />
      </Stack.Protected>

      <Stack.Protected guard={canEnterRoleArea(gate, "athlete")}>
        <Stack.Screen name="athlete/index" options={{ title: "วันนี้" }} />
      </Stack.Protected>

      <Stack.Protected guard={canEnterRoleArea(gate, "coach")}>
        <Stack.Screen name="coach/index" options={{ title: "ภาพรวมทีม" }} />
      </Stack.Protected>
    </Stack>
  );
}
