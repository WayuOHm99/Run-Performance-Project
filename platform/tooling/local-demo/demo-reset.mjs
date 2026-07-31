// `demo:reset` — rebuild the local demo baseline. See `reset.mjs` for the
// pipeline and why its order is fixed.
//
// This is the only command the Product Owner runs that destroys data, and it
// destroys only the local Supabase project.

import { runReset } from "./reset.mjs";

async function main() {
  console.log("Resetting the LOCAL demo environment.");
  console.log("Local Supabase only. No hosted project is contacted.\n");

  const { credentialsPath } = await runReset({
    log: (message) => console.log(`  ${message}`),
    showCounts: true,
  });

  console.log("Baseline verified: 2 profiles, 1 team, 2 active memberships,");
  console.log("0 sharing grants, 0 check-ins.\n");
  console.log(`Local demo credentials written to: ${credentialsPath}`);
  console.log("That file is git-ignored. The password is not printed here.\n");
  console.log(
    "Next: `corepack pnpm demo:web` or `corepack pnpm demo:android`.",
  );
}

// Errors from this tooling are already sanitized at their source. Only the
// message is printed; a stack trace would add file paths and no diagnosis.
main().catch((error) => {
  console.error(`\ndemo:reset failed — ${error.message}`);
  process.exitCode = 1;
});
