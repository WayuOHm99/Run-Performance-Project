// `demo:web` and `demo:android` share this launcher.
//
// Three properties define it:
//
//   * **It never resets or reseeds.** It runs no `db reset`, applies no fixture,
//     creates no user, and writes nothing to the database. Launching the app and
//     rebuilding the demo data are separate commands on purpose.
//   * **It never touches `apps/mobile/.env.local`** (decision 3). Configuration
//     is passed as process-scoped environment variables to the child only, and
//     `EXPO_NO_DOTENV=1` stops Expo reading any dotenv file at all — so the
//     Product Owner's real hosted `.env.local` is neither consumed nor
//     shadowed nor modified.
//   * **The publishable key is read fresh from the running stack** through the
//     credential filter, never from the credential file (which holds the
//     password) and never from a dotenv file.
//
// If the stack is not running this fails with an instruction rather than
// starting it, so "launching the app" can never become a side effect that
// rebuilds anything. The instruction names `demo:start`, which brings the stack
// up with its credential block suppressed — the Product Owner is never told to
// run a command that prints a service-role key to their terminal.

import { createRequire } from "node:module";
import { dirname, join } from "node:path";

import { readLocalCredentials } from "./credential-filter.mjs";
import { resolveSurfaceUrl } from "./endpoint.mjs";
import { MOBILE_DIR } from "./paths.mjs";
import { runInheritedStdio } from "./subprocess.mjs";
import { statusCommand } from "./supabase-cli.mjs";

const EXPO_FLAG = { web: "--web", android: "--android" };

// Stopping the dev server from the keyboard is not a failure.
const INTERACTIVE_STOP_SIGNALS = new Set(["SIGINT", "SIGTERM", "SIGHUP"]);

const require = createRequire(import.meta.url);

// `expo/bin/cli` is a plain Node script. Spawning it with `process.execPath` and
// `shell: false` avoids the `node_modules/.bin` shim, which on Windows is a
// `.CMD` batch file that cannot be executed without a shell.
function resolveExpoCli() {
  const packageJsonPath = require.resolve("expo/package.json", {
    paths: [MOBILE_DIR],
  });

  return join(dirname(packageJsonPath), "bin", "cli");
}

export function buildDemoEnv({ baseEnv, surfaceUrl, publishableKey }) {
  return {
    ...baseEnv,
    // Decision 3. Expo reads `.env`, `.env.local`, and friends unless this is
    // set; with it set, the three variables below are the only configuration the
    // app sees.
    EXPO_NO_DOTENV: "1",
    EXPO_PUBLIC_SUPABASE_ENVIRONMENT: "local",
    EXPO_PUBLIC_SUPABASE_URL: surfaceUrl,
    EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY: publishableKey,
  };
}

export async function launchDemo(surface) {
  const flag = EXPO_FLAG[surface];

  if (!flag) {
    throw new Error(
      "Unsupported demo surface. Only web and android are in scope.",
    );
  }

  console.log(`Launching the LOCAL demo on ${surface}.`);
  console.log("This does not reset or reseed any data.\n");

  // Throws with a "start it first" instruction when the stack is down.
  const credentials = await readLocalCredentials(statusCommand());

  // The app is handed the surface's URL: `127.0.0.1` for web, and the emulator's
  // host-loopback alias for Android. `resolveSurfaceUrl` is the only place that
  // mapping exists, and the app independently refuses `10.0.2.2` unless it is
  // actually running on Android.
  const surfaceUrl = resolveSurfaceUrl(surface);

  console.log(`  local stack:  ${credentials.apiUrl}`);
  console.log(`  app endpoint: ${surfaceUrl}`);
  console.log(
    "  credential:   local publishable key (validated, not printed)\n",
  );

  const { exitCode, signal } = await runInheritedStdio(
    process.execPath,
    [resolveExpoCli(), "start", flag],
    {
      cwd: MOBILE_DIR,
      env: buildDemoEnv({
        baseEnv: process.env,
        surfaceUrl,
        publishableKey: credentials.publishableKey,
      }),
      label: `expo start ${flag}`,
    },
  );

  // Ctrl-C is how a foreground dev server is *supposed* to end, so an interrupt
  // is reported as a clean stop. Every other signal, and every non-zero code, is
  // a failure — the general rule from `subprocess.mjs` holds here, with this one
  // documented exception.
  process.exitCode = INTERACTIVE_STOP_SIGNALS.has(signal) ? 0 : exitCode;
}

export function runLaunch(surface) {
  launchDemo(surface).catch((error) => {
    console.error(`\ndemo:${surface} failed — ${error.message}`);
    process.exitCode = 1;
  });
}
