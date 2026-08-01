// The ignored local credential file, decision 7.
//
// The password is written here and nowhere else. It is never printed to the
// terminal; `demo:reset` prints only the repository-relative path of this file.
//
// The file holds the two synthetic `example.test` addresses and the generated
// local password. It holds no token, no session, no publishable key, and no
// Supabase status output.
//
// **Staleness is the failure that matters here.** The password in this file is
// only true of the accounts that the same reset created. A reset that is
// interrupted after wiping the database but before writing the file would
// otherwise leave the previous run's password sitting there, pointing at
// accounts that no longer exist — and the Product Owner would read it, fail to
// sign in, and have no way to tell whether the demo or their typing was wrong.
//
// Two rules prevent that:
//
//   * `discardCredentialsFile` is called **before** the destructive step, so a
//     run that dies part-way leaves no file at all rather than a wrong one;
//   * `writeCredentialsFile` writes a temporary file and then renames it over
//     the target. Rename is atomic on both POSIX and Windows (libuv uses
//     `MoveFileEx` with replace-existing), so a reader sees either the whole
//     previous file or the whole new one, never a half-written one.

import { basename, join } from "node:path";
import { mkdir, open, readdir, rename, rm } from "node:fs/promises";

import { LOCAL_SUPABASE_URL } from "./endpoint.mjs";
import {
  CREDENTIALS_DISPLAY_PATH,
  CREDENTIALS_FILE,
  LOCAL_DEMO_DIR,
} from "./paths.mjs";

export function renderCredentialsFile({ accounts, password, generatedAt }) {
  const lines = [
    "Run Performance — local demo credentials",
    "",
    "Synthetic accounts for the LOCAL Supabase stack only.",
    "This file is git-ignored. Do not commit it, paste it into an AI chat, or",
    "screenshot it. It is regenerated on every `corepack pnpm demo:reset`.",
    "",
    `Generated: ${generatedAt}`,
    `Endpoint:  ${LOCAL_SUPABASE_URL} (local only)`,
    "",
    "Shared password for both accounts:",
    `  ${password}`,
    "",
    "Accounts:",
  ];

  for (const account of accounts) {
    lines.push(`  ${account.role.padEnd(7)}  ${account.email}`);
  }

  lines.push(
    "",
    "Roles come from public.team_memberships under RLS, not from these labels.",
    "The baseline has no sharing grant and no check-in: create a check-in as the",
    "athlete and grant sharing explicitly in the app.",
    "",
  );

  return lines.join("\n");
}

const TEMPORARY_SUFFIX = ".tmp";

function temporaryPathFor(file) {
  // Pid-qualified, so two processes cannot write the same temporary file. The
  // lock already prevents that; this makes it true even without one.
  return `${file}.${process.pid}${TEMPORARY_SUFFIX}`;
}

function escapeForPattern(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Matches this tooling's own temporary files and nothing else: the exact
// credential file name, a dot, a run of digits that was somebody's pid, and the
// suffix. A file that does not match that shape is left alone, whatever it is.
function temporaryFilePattern(file) {
  return new RegExp(
    `^${escapeForPattern(basename(file))}\\.\\d+${escapeForPattern(TEMPORARY_SUFFIX)}$`,
  );
}

// Removes every temporary credential file in the ignored directory, **including
// ones written by other processes**.
//
// Round 2 only cleaned this process's own pid-qualified file, which meant a run
// killed part-way left a temporary file that nothing would ever remove: it is
// not the credential file, so no reset replaced it, and it carried the password
// that run had generated. Cleaning only the current pid made that permanent.
//
// Deleting another process's temporary file is safe here because writing one
// happens only inside the destructive-workflow lock, so no other run can have
// one in flight while this code runs. The scan is confined to the ignored
// `.local-demo/` directory and to names matching the exact temporary-file shape;
// `readdir` returns bare entry names, so nothing here can reach outside it. No
// file is opened and no content is read, so nothing can be printed either.
async function removeTemporaryFiles(directory, file) {
  const pattern = temporaryFilePattern(file);

  let entries;

  try {
    entries = await readdir(directory);
  } catch {
    // No directory yet: nothing to clean.
    return;
  }

  for (const entry of entries) {
    if (pattern.test(entry)) {
      await rm(join(directory, entry), { force: true });
    }
  }
}

// Removes the credential file, and any temporary file any run left behind, so
// nothing survives that could be mistaken for the current baseline. Called
// before the destructive step of a reset, and safe to call when no file exists.
export async function discardCredentialsFile({
  directory = LOCAL_DEMO_DIR,
  file = CREDENTIALS_FILE,
} = {}) {
  await rm(file, { force: true });
  await removeTemporaryFiles(directory, file);
}

export async function writeCredentialsFile({
  accounts,
  password,
  directory = LOCAL_DEMO_DIR,
  file = CREDENTIALS_FILE,
} = {}) {
  await mkdir(directory, { recursive: true });

  const contents = renderCredentialsFile({
    accounts,
    password,
    generatedAt: new Date().toISOString(),
  });

  const temporaryFile = temporaryPathFor(file);

  // Leftover temporary files from killed runs are cleared first — this run's own
  // pid-qualified name would otherwise fail the exclusive create below, and
  // another run's would sit there forever holding a password nothing will ever
  // use. Nothing reads them; only this function ever writes one.
  await removeTemporaryFiles(directory, file);

  // Owner-only where the platform honours it. Windows ignores the mode, which is
  // why the directory is git-ignored rather than relying on file permissions.
  const handle = await open(temporaryFile, "wx", 0o600);

  try {
    await handle.writeFile(contents, "utf8");
    // Flushed before the rename, so a power loss cannot publish a file name that
    // points at unwritten bytes.
    await handle.sync();
  } finally {
    await handle.close();
  }

  try {
    await rename(temporaryFile, file);
  } catch (error) {
    // Never leave the temporary file behind to be found later and trusted.
    await rm(temporaryFile, { force: true });

    throw error;
  }

  // The path, never the contents.
  return CREDENTIALS_DISPLAY_PATH;
}
