// Every path the demo tooling touches, resolved from this file's own location so
// the commands behave identically whatever the current working directory is.
//
// The list is deliberately short and complete. Note what is absent:
// `apps/mobile/.env.local` appears nowhere in this tooling, by decision 3. The
// demo commands pass configuration through process-scoped environment variables
// and set `EXPO_NO_DOTENV=1`, so that file is neither read nor written nor backed
// up nor deleted.

import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

// tooling/local-demo -> tooling -> platform
export const PLATFORM_DIR = resolve(here, "..", "..");

export const MOBILE_DIR = join(PLATFORM_DIR, "apps", "mobile");

// Git-ignored through `platform/.gitignore`.
export const LOCAL_DEMO_DIR = join(PLATFORM_DIR, ".local-demo");

export const CREDENTIALS_FILE = join(LOCAL_DEMO_DIR, "credentials.txt");

// The interprocess lock for destructive demo commands. In the same ignored
// directory, so nothing about it is ever committed.
export const LOCK_FILE = join(LOCAL_DEMO_DIR, "demo.lock");

// Held only while an abandoned lock is being recovered, so that at most one
// process can be doing that at any moment. See `lock.mjs`.
export const BREAK_FILE = join(LOCAL_DEMO_DIR, "demo.lock.break");

// Passed to the Supabase CLI as a path relative to `PLATFORM_DIR`, which is the
// directory holding `supabase/config.toml`.
export const FIXTURE_SQL_RELATIVE = "supabase/fixtures/local-demo.sql";

// What the Product Owner is told. A repository-relative path, never an absolute
// one, so it is safe to show and safe to paste.
export const CREDENTIALS_DISPLAY_PATH = "platform/.local-demo/credentials.txt";

// Named in a message only in the two cases a person genuinely has to act on: a
// lock whose record never became readable, and a recovery claim left behind by a
// killed run. An abandoned lock with a well-formed record is recovered
// automatically and is never advertised as something to delete by hand.
export const LOCK_DISPLAY_PATH = "platform/.local-demo/demo.lock";

export const BREAK_DISPLAY_PATH = "platform/.local-demo/demo.lock.break";
