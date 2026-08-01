// `demo:start` — bring the local stack up **without printing its credentials**.
//
// This command exists because the obvious alternative is not safe. `supabase
// start`, and therefore `db:start`, ends by printing a block containing the
// local database URL, the JWT secret, the secret key, the service-role key, and
// S3 credentials. Decision 5 forbids that output being printed or persisted, and
// a terminal scrollback is routinely pasted into a chat or a screenshot. So the
// restart path the Product Owner is told to use is this one: the same
// non-destructive `supabase start`, with all three streams discarded at the OS
// level, followed by a status read through the credential filter to confirm the
// stack really is up and really is the canonical local endpoint.
//
// **It is not destructive.** It runs no reset, applies no fixture, creates no
// user, and writes nothing to the database. Data from the last reset survives.
// It still takes the destructive-workflow lock, briefly, so it cannot race a
// reset that is already rebuilding the same stack.

import { withDemoLock } from "./lock.mjs";
import { readLocalCredentials } from "./credential-filter.mjs";
import { startLocalStack, statusCommand } from "./supabase-cli.mjs";

async function main() {
  console.log("Starting the LOCAL Supabase stack.");
  console.log("This resets nothing and reseeds nothing.\n");
  console.log("  starting (this can take a few minutes on a cold start)");

  const credentials = await withDemoLock("demo:start", async () => {
    await startLocalStack();

    return readLocalCredentials(statusCommand());
  });

  console.log(`  local endpoint verified: ${credentials.apiUrl}\n`);
  console.log("Running. Existing demo data is unchanged.");
  console.log("Rebuild the baseline with `corepack pnpm demo:reset`, or check");
  console.log("it with `corepack pnpm demo:verify`.");
}

main().catch((error) => {
  console.error(`\ndemo:start failed — ${error.message}`);
  process.exitCode = 1;
});
