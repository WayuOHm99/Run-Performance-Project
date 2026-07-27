import { Redirect } from "expo-router";

import { resolveLandingRoute } from "@/features/auth/gate";
import { useAuthGate } from "@/features/profile/use-account";

/**
 * The only place that decides where a user starts.
 *
 * Every other screen is reached either by this redirect or by an explicit
 * action, so there is one rule to test rather than a scattering of per-screen
 * navigation effects.
 */
export default function IndexScreen() {
  const gate = useAuthGate();

  return <Redirect href={resolveLandingRoute(gate)} />;
}
