// The reset pipeline, shared by `demo:reset` and the consent verification.
//
// It is destructive to **exactly one thing**: the local Supabase project defined
// by `platform/supabase/config.toml`. It contacts no hosted project, and the
// Supabase CLI it drives is never given `--linked`, `--db-url`, or a project ref.
//
// Order matters and is not incidental:
//
//   1. start the stack if it is not already up;
//   1a. discard the previous credential file, so an interrupted run leaves no
//      password that no longer opens anything;
//   2. `db reset --local --no-seed` — wipes the local database, applies
//      migrations, applies no seed;
//   3. create both users through the **real public Auth signup flow**;
//   4. apply the fixture as the local database owner;
//   5. verify the baseline with scalar counts only;
//   6. write the generated password to the ignored credential file.
//
// Steps 3 and 4 cannot be swapped: the fixture refuses to invent auth users, and
// the profile rows it updates are created by the signup trigger.

import { signUp } from "./api.mjs";
import { DEMO_ACCOUNTS } from "./accounts.mjs";
import { compareBaseline, formatBaseline, readBaseline } from "./baseline.mjs";
import { readLocalCredentials } from "./credential-filter.mjs";
import {
  discardCredentialsFile,
  writeCredentialsFile,
} from "./credentials-file.mjs";
import { withDemoLock } from "./lock.mjs";
import { generateLocalDemoPassword } from "./password.mjs";
import { FIXTURE_SQL_RELATIVE } from "./paths.mjs";
import {
  applyLocalSqlFile,
  resetLocalDatabase,
  startLocalStack,
  statusCommand,
} from "./supabase-cli.mjs";

export async function ensureStackRunning(log) {
  try {
    return await readLocalCredentials(statusCommand());
  } catch {
    log(
      "local stack is not running; starting it (this can take a few minutes)",
    );
    await startLocalStack();

    return readLocalCredentials(statusCommand());
  }
}

// Returns the credentials and the generated password so a caller that needs to
// sign in as the synthetic users can do so without reading the credential file.
// The password is a value in memory here; no caller prints it.
//
// The whole pipeline runs under the destructive-workflow lock, so a second
// reset — or a `demo:stop` — cannot interleave with it and leave a database
// built by one run described by the other's credential file. The lock is
// reentrant, so a caller that already holds it (the consent verification does)
// is not blocked by its own claim.
export async function runReset({ log = () => {}, showCounts = false } = {}) {
  return withDemoLock("demo:reset", () => resetUnderLock({ log, showCounts }));
}

async function resetUnderLock({ log, showCounts }) {
  const credentials = await ensureStackRunning(log);
  log(`local endpoint verified: ${credentials.apiUrl}`);

  // Before the database is touched, not after. From here until the new file is
  // written there is deliberately no credential file at all: an interrupted
  // reset must leave nothing rather than something untrue.
  await discardCredentialsFile();

  log("resetting the local database (--local --no-seed)");
  await resetLocalDatabase();

  const password = generateLocalDemoPassword();

  log("creating both accounts through the real local Auth signup flow");
  for (const account of DEMO_ACCOUNTS) {
    await signUp({
      apiUrl: credentials.apiUrl,
      publishableKey: credentials.publishableKey,
      email: account.email,
      password,
    });
  }

  log("applying the synthetic fixture as the local database owner");
  await applyLocalSqlFile(FIXTURE_SQL_RELATIVE);

  log("verifying the baseline");
  const counts = await readBaseline();
  const mismatches = compareBaseline(counts);

  if (showCounts) {
    console.log("");
    console.log(formatBaseline(counts));
    console.log("");
  }

  if (mismatches.length > 0) {
    for (const mismatch of mismatches) {
      console.error(
        `  baseline mismatch: ${mismatch.key} expected ${mismatch.expected}, got ${mismatch.actual}`,
      );
    }

    throw new Error("The demo baseline is not what it must be.");
  }

  const credentialsPath = await writeCredentialsFile({
    accounts: DEMO_ACCOUNTS,
    password,
  });

  return { credentials, password, credentialsPath, counts };
}
