const SUPABASE_PROJECT_URL = "https://altlphxckxsudnuwhqfw.supabase.co";
const PUBLISHABLE_KEY_PATTERN = /^sb_publishable_[A-Za-z0-9_-]{20,}$/;

export type PublicSupabaseEnvironment = Readonly<{
  url: string;
  publishableKey: string;
}>;

export type PublicSupabaseEnvironmentInput = {
  url: string | undefined;
  publishableKey: string | undefined;
};

export class PublicSupabaseEnvironmentError extends Error {
  override readonly name = "PublicSupabaseEnvironmentError";
}

export function validatePublicSupabaseEnvironment(
  input: PublicSupabaseEnvironmentInput,
): PublicSupabaseEnvironment {
  if (!input.url) {
    throw new PublicSupabaseEnvironmentError(
      "EXPO_PUBLIC_SUPABASE_URL is required.",
    );
  }

  if (input.url !== SUPABASE_PROJECT_URL) {
    throw new PublicSupabaseEnvironmentError(
      "EXPO_PUBLIC_SUPABASE_URL does not match the configured project.",
    );
  }

  if (!input.publishableKey) {
    throw new PublicSupabaseEnvironmentError(
      "EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY is required.",
    );
  }

  if (
    input.publishableKey.startsWith("sb_secret_") ||
    input.publishableKey.startsWith("eyJ")
  ) {
    throw new PublicSupabaseEnvironmentError(
      "The mobile app accepts a publishable key only.",
    );
  }

  if (!PUBLISHABLE_KEY_PATTERN.test(input.publishableKey)) {
    throw new PublicSupabaseEnvironmentError(
      "EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY has an invalid format.",
    );
  }

  return Object.freeze({
    url: input.url,
    publishableKey: input.publishableKey,
  });
}

export function readPublicSupabaseEnvironment(): PublicSupabaseEnvironment {
  return validatePublicSupabaseEnvironment({
    url: process.env.EXPO_PUBLIC_SUPABASE_URL,
    publishableKey: process.env.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
  });
}
