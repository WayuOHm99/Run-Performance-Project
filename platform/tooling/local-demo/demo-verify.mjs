// `demo:verify` — re-reads the baseline without changing anything.
//
// Read-only: it runs one scalar aggregate query and compares it against
// `EXPECTED_BASELINE`. It starts nothing, resets nothing, and writes nothing.

import { compareBaseline, formatBaseline, readBaseline } from "./baseline.mjs";

async function main() {
  const counts = await readBaseline();
  const mismatches = compareBaseline(counts);

  console.log("Local demo baseline:\n");
  console.log(formatBaseline(counts));
  console.log("");

  if (mismatches.length > 0) {
    for (const mismatch of mismatches) {
      console.error(
        `  mismatch: ${mismatch.key} expected ${mismatch.expected}, got ${mismatch.actual}`,
      );
    }

    throw new Error("The demo baseline is not what it must be.");
  }

  console.log("Baseline verified.");
}

main().catch((error) => {
  console.error(`\ndemo:verify failed — ${error.message}`);
  process.exitCode = 1;
});
