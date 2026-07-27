import type { SupabaseClient } from "@supabase/supabase-js";

import type { Database } from "./database.types";

/**
 * The schema-typed client used everywhere in the app.
 *
 * Kept in its own type-only module so data-access code can depend on the type
 * without importing `client.ts`, which pulls in React Native. That is what lets
 * the repositories be unit-tested with a plain object double and no native
 * runtime.
 */
export type AppSupabaseClient = SupabaseClient<Database>;
