// `demo:stop` — stops **only this project's** local Supabase containers.
//
// Two flags are deliberately absent and must stay absent:
//
//   * `--all` would stop every Supabase project on the machine, including one
//     belonging to unrelated work.
//   * `--no-backup` would discard the local database volume, which would silently
//     destroy the demo data this command is not supposed to touch. Stopping and
//     restarting must leave the athlete's check-in and the coach's view exactly
//     as they were.
//
// Output is suppressed: `supabase stop` echoes project and container detail, and
// there is nothing in it the Product Owner needs.

import { stopLocalStack } from "./supabase-cli.mjs";

async function main() {
  console.log("Stopping the local Supabase stack for this project only.");
  console.log("Local data is preserved (no --no-backup, no --all).\n");

  await stopLocalStack();

  console.log("Stopped. Local demo data is still on disk.");
  console.log("Bring it back with `corepack pnpm db:start`, or rebuild the");
  console.log("baseline from scratch with `corepack pnpm demo:reset`.");
}

main().catch((error) => {
  console.error(`\ndemo:stop failed — ${error.message}`);
  process.exitCode = 1;
});
