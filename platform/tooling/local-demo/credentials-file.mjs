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

import { mkdir, open, rename, rm } from "node:fs/promises";

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

// Removes the credential file, and any temporary file a previous crash left
// behind, so nothing survives that could be mistaken for the current baseline.
// Called before the destructive step of a reset, and safe to call when no file
// exists.
export async function discardCredentialsFile({ file = CREDENTIALS_FILE } = {}) {
  await rm(file, { force: true });
  await rm(temporaryPathFor(file), { force: true });
}

function temporaryPathFor(file) {
  // Pid-qualified, so two processes cannot write the same temporary file. The
  // lock already prevents that; this makes it true even without one.
  return `${file}.${process.pid}.tmp`;
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

  // A leftover temporary file from a killed run would fail the exclusive create
  // below, so it is cleared first. Nothing reads it; only this function ever
  // writes it.
  await rm(temporaryFile, { force: true });

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
