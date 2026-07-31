// The ignored local credential file, decision 7.
//
// The password is written here and nowhere else. It is never printed to the
// terminal; `demo:reset` prints only the repository-relative path of this file.
//
// The file holds the two synthetic `example.test` addresses and the generated
// local password. It holds no token, no session, no publishable key, and no
// Supabase status output.

import { mkdir, writeFile } from "node:fs/promises";

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

export async function writeCredentialsFile({ accounts, password }) {
  await mkdir(LOCAL_DEMO_DIR, { recursive: true });

  const contents = renderCredentialsFile({
    accounts,
    password,
    generatedAt: new Date().toISOString(),
  });

  // Owner-only where the platform honours it. Windows ignores the mode, which is
  // why the directory is git-ignored rather than relying on file permissions.
  await writeFile(CREDENTIALS_FILE, contents, {
    encoding: "utf8",
    mode: 0o600,
  });

  // The path, never the contents.
  return CREDENTIALS_DISPLAY_PATH;
}
