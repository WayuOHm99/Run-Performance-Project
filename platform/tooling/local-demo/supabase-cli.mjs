// The pinned Supabase CLI, invoked as a Node script.
//
// Resolved through `createRequire` rather than by spawning `supabase` from
// `PATH`, so a globally installed CLI of a different version can never be picked
// up. `platform/README.md` already states the pinned version is the only
// supported one; this makes that true rather than merely documented.
//
// Spawned as `node <script>` with `shell: false`. On Windows that avoids the
// `.CMD` shim entirely, which also means no argument ever passes through a shell
// parser.
//
// **Every command in this module is local-only.** `--local` is passed explicitly
// wherever the CLI accepts it. `--linked`, `--db-url`, a project ref, `login`,
// `link`, `db push`, and `db pull` appear nowhere in this tooling.

import { createRequire } from "node:module";
import { dirname, join } from "node:path";

import { PLATFORM_DIR } from "./paths.mjs";
import {
  runCapturedStdout,
  runSuppressedOrThrow,
  subprocessFailure,
} from "./subprocess.mjs";

const require = createRequire(import.meta.url);

function resolveCliScript() {
  const packageJsonPath = require.resolve("supabase/package.json", {
    paths: [PLATFORM_DIR],
  });

  return join(dirname(packageJsonPath), "dist", "supabase.js");
}

const CLI_SCRIPT = resolveCliScript();

function cliArgs(args) {
  return [CLI_SCRIPT, ...args];
}

const baseOptions = { cwd: PLATFORM_DIR, shell: false };

// `supabase start` prints a full credential block on success. Output is
// discarded at the OS level, and only the exit code is observed.
export async function startLocalStack() {
  return runSuppressedOrThrow(process.execPath, cliArgs(["start"]), {
    ...baseOptions,
    label: "supabase start",
  });
}

// Never `--all`, never `--no-backup`. This stops this project's containers and
// leaves the local database volume intact, so `demo:web` after `demo:stop` finds
// the same data.
export async function stopLocalStack() {
  return runSuppressedOrThrow(process.execPath, cliArgs(["stop"]), {
    ...baseOptions,
    label: "supabase stop",
  });
}

export function statusCommand() {
  return {
    command: process.execPath,
    args: cliArgs(["status", "-o", "json"]),
    cwd: PLATFORM_DIR,
  };
}

// Explicitly destructive, and explicitly local. `--no-seed` keeps
// `supabase/seed.sql` out of the picture entirely, so the only thing that
// populates the demo is this task's fixture.
export async function resetLocalDatabase() {
  return runSuppressedOrThrow(
    process.execPath,
    cliArgs(["db", "reset", "--local", "--no-seed"]),
    { ...baseOptions, label: "supabase db reset --local --no-seed" },
  );
}

// Applies the fixture as the local database owner. Output suppressed: a failing
// statement would otherwise print the offending SQL, and a successful one prints
// result rows.
export async function applyLocalSqlFile(relativePath) {
  return runSuppressedOrThrow(
    process.execPath,
    cliArgs(["db", "query", "--local", "--file", relativePath]),
    { ...baseOptions, label: "local fixture application" },
  );
}

// The only place a query result is read back. Callers must keep the SQL to
// scalar aggregates; see `baseline.mjs`.
export async function queryLocalScalars(sql) {
  const { exitCode, stdout } = await runCapturedStdout(
    process.execPath,
    cliArgs(["db", "query", "--local", "-o", "json", sql]),
    { ...baseOptions, label: "local scalar query" },
  );

  if (exitCode !== 0) {
    throw subprocessFailure("local scalar query", exitCode);
  }

  return stdout;
}
