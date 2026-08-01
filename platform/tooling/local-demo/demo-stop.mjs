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

// It also takes the destructive-workflow lock. Stopping the stack while a reset
// is applying migrations is how a half-built database happens, and the lock is
// what makes that impossible rather than merely unlikely.

import { withDemoLock } from "./lock.mjs";
import { stopLocalStack } from "./supabase-cli.mjs";

async function main() {
  console.log("Stopping the local Supabase stack for this project only.");
  console.log("Local data is preserved (no --no-backup, no --all).\n");

  await withDemoLock("demo:stop", () => stopLocalStack());

  console.log("Stopped. Local demo data is still on disk.");
  console.log("Bring it back with `corepack pnpm demo:start`, or rebuild the");
  console.log("baseline from scratch with `corepack pnpm demo:reset`.");
  console.log(
    "Both keep the stack's own credential output suppressed at the OS level.",
  );
}

main().catch((error) => {
  console.error(`\ndemo:stop failed — ${error.message}`);
  process.exitCode = 1;
});
