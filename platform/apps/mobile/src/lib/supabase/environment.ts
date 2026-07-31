// The mobile app talks to exactly one of two endpoints, and which one is an
// explicit, declared decision rather than whatever happens to be in the
// environment.
//
// TASK-017 adds the local demo endpoint. It is deliberately gated behind its own
// mode variable instead of widening the accepted URL set, so a machine that
// forgets to declare local mode cannot silently point a demo build at the hosted
// project, and a hosted build cannot be talked into a local one.
//
// Both modes validate by **exact equality against an allowlist**, not by parsing.
// That is the whole userinfo / path / query / fragment / alternate-port defence:
// `http://user:pw@127.0.0.1:54321`, `http://127.0.0.1:54322`,
// `http://127.0.0.1:54321/x`, `http://192.168.1.10:54321`, and a trailing slash
// are all simply unequal to an allowed string, so none of them needs its own
// parser branch that could be got wrong.

const SUPABASE_PROJECT_URL = "https://altlphxckxsudnuwhqfw.supabase.co";

// The canonical local endpoint. `127.0.0.1` rather than `localhost`, so the
// value cannot resolve through IPv6 or a hosts-file entry.
const LOCAL_SUPABASE_URL = "http://127.0.0.1:54321";

// The Android emulator reaches the host loopback through its own alias. This is
// the same local stack seen from inside the emulator, and it is accepted *only*
// on Android, so a web or iOS build can never use it.
const ANDROID_EMULATOR_SUPABASE_URL = "http://10.0.2.2:54321";

const PUBLISHABLE_KEY_PATTERN = /^sb_publishable_[A-Za-z0-9_-]{20,}$/;

// Prefixes that identify a credential this app must never hold, checked before
// the format pattern so the refusal is attributable to "this is server-capable"
// rather than merely "this is malformed".
const SERVER_CAPABLE_KEY_PREFIXES = [
  "sb_secret_",
  "eyJ",
  "postgres://",
  "postgresql://",
  "service_role",
] as const;

export type SupabaseEnvironmentMode = "hosted" | "local";

export type PublicSupabaseEnvironment = Readonly<{
  url: string;
  publishableKey: string;
}>;

export type PublicSupabaseEnvironmentInput = {
  url: string | undefined;
  publishableKey: string | undefined;
  mode?: string | undefined;
  isAndroid?: boolean | undefined;
};

export type SupabaseRuntimeOptions = {
  isAndroid: boolean;
};

export class PublicSupabaseEnvironmentError extends Error {
  override readonly name = "PublicSupabaseEnvironmentError";
}

// Absent means hosted, which keeps every existing build and test unchanged.
// An unrecognised value is an error rather than a fallback to hosted: a typo
// such as `locl` must stop the app, not quietly aim it at production.
export function resolveSupabaseEnvironmentMode(
  raw: string | undefined,
): SupabaseEnvironmentMode {
  if (raw === undefined || raw === "") {
    return "hosted";
  }

  if (raw === "hosted" || raw === "local") {
    return raw;
  }

  throw new PublicSupabaseEnvironmentError(
    "EXPO_PUBLIC_SUPABASE_ENVIRONMENT must be hosted or local.",
  );
}

// No message in this module interpolates the offending value. A rejected URL or
// key is exactly the kind of thing that ends up in a crash report or a terminal
// the Product Owner pastes somewhere, so the error says which variable was wrong
// and nothing about what it contained.
function assertAllowedUrl(
  url: string,
  mode: SupabaseEnvironmentMode,
  isAndroid: boolean,
): void {
  if (mode === "hosted") {
    if (url !== SUPABASE_PROJECT_URL) {
      throw new PublicSupabaseEnvironmentError(
        "EXPO_PUBLIC_SUPABASE_URL does not match the configured project.",
      );
    }

    return;
  }

  if (url === LOCAL_SUPABASE_URL) {
    return;
  }

  if (isAndroid && url === ANDROID_EMULATOR_SUPABASE_URL) {
    return;
  }

  throw new PublicSupabaseEnvironmentError(
    "EXPO_PUBLIC_SUPABASE_URL is not the canonical local Supabase endpoint.",
  );
}

function assertPublishableKey(publishableKey: string): void {
  if (
    SERVER_CAPABLE_KEY_PREFIXES.some((prefix) =>
      publishableKey.startsWith(prefix),
    )
  ) {
    throw new PublicSupabaseEnvironmentError(
      "The mobile app accepts a publishable key only.",
    );
  }

  if (!PUBLISHABLE_KEY_PATTERN.test(publishableKey)) {
    throw new PublicSupabaseEnvironmentError(
      "EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY has an invalid format.",
    );
  }
}

export function validatePublicSupabaseEnvironment(
  input: PublicSupabaseEnvironmentInput,
): PublicSupabaseEnvironment {
  // Resolved first: an unusable mode must fail before either value is examined,
  // so a bad mode cannot be masked by a bad URL that happens to be reported
  // instead.
  const mode = resolveSupabaseEnvironmentMode(input.mode);

  if (!input.url) {
    throw new PublicSupabaseEnvironmentError(
      "EXPO_PUBLIC_SUPABASE_URL is required.",
    );
  }

  assertAllowedUrl(input.url, mode, input.isAndroid === true);

  if (!input.publishableKey) {
    throw new PublicSupabaseEnvironmentError(
      "EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY is required.",
    );
  }

  assertPublishableKey(input.publishableKey);

  return Object.freeze({
    url: input.url,
    publishableKey: input.publishableKey,
  });
}

export function readPublicSupabaseEnvironment(
  options: SupabaseRuntimeOptions = { isAndroid: false },
): PublicSupabaseEnvironment {
  return validatePublicSupabaseEnvironment({
    url: process.env.EXPO_PUBLIC_SUPABASE_URL,
    publishableKey: process.env.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
    mode: process.env.EXPO_PUBLIC_SUPABASE_ENVIRONMENT,
    isAndroid: options.isAndroid,
  });
}
