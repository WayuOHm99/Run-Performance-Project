/**
 * Platform-specific Supabase Auth persistence.
 *
 * Split out of `client.ts` and kept free of runtime React Native imports so the
 * web/native difference is a pure, directly tested decision rather than an
 * inline ternary nobody can assert on.
 *
 * Native persists an encrypted envelope. Web persists nothing at all: it is an
 * export and smoke-test target in this task, not a production dashboard, and
 * there is no browser storage worth putting a session token in. A refresh
 * therefore requires signing in again, which is the intended trade.
 */

import type { SupportedStorage } from "@supabase/supabase-js";

export type AuthPersistenceOptions = {
  readonly storage?: SupportedStorage;
  readonly autoRefreshToken: boolean;
  readonly persistSession: boolean;
  readonly detectSessionInUrl: boolean;
};

export function createAuthPersistenceOptions(input: {
  readonly isWeb: boolean;
  readonly createStorage: () => SupportedStorage;
}): AuthPersistenceOptions {
  if (input.isWeb) {
    // No `storage` key at all, so there is nothing for Supabase to fall back
    // to, and `persistSession: false` keeps the session in memory only.
    return {
      autoRefreshToken: true,
      persistSession: false,
      detectSessionInUrl: false,
    };
  }

  return {
    storage: input.createStorage(),
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: false,
  };
}
