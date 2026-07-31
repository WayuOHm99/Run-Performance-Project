// The local demo endpoint allowlist.
//
// This mirrors `apps/mobile/src/lib/supabase/environment.ts` deliberately: the
// tooling decides which URL to hand the app, and the app independently refuses
// anything else. Neither trusts the other, so a mistake in one is still caught by
// the other.
//
// Validation is exact string equality against an allowlist rather than URL
// parsing. Userinfo, a path, a query, a fragment, a different port, a LAN
// address, and a hosted project URL are all simply unequal to an allowed value,
// so there is no parser branch that could be written too permissively.

export const LOCAL_SUPABASE_URL = "http://127.0.0.1:54321";

// Only the Android emulator may use this. It is the emulator's alias for the
// host loopback, so it addresses the same local stack and never leaves the
// machine.
export const ANDROID_EMULATOR_SUPABASE_URL = "http://10.0.2.2:54321";

export const DEMO_SURFACES = Object.freeze(["web", "android"]);

export class DemoEndpointError extends Error {
  name = "DemoEndpointError";
}

// Never interpolates the rejected value. A rejected URL is exactly the kind of
// string that ends up pasted into a chat or an issue.
export function assertCanonicalLocalUrl(url) {
  if (url !== LOCAL_SUPABASE_URL) {
    throw new DemoEndpointError(
      "The local Supabase API URL is not the canonical local endpoint.",
    );
  }

  return url;
}

export function resolveSurfaceUrl(surface) {
  if (surface === "web") {
    return LOCAL_SUPABASE_URL;
  }

  if (surface === "android") {
    return ANDROID_EMULATOR_SUPABASE_URL;
  }

  throw new DemoEndpointError(
    "Unsupported demo surface. Only web and android are in scope.",
  );
}
