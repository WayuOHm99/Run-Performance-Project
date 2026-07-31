// Subprocess helpers whose defining property is what they *do not* return.
//
// `supabase start` and `supabase status` print a development database URL, a
// JWT secret, a service-role key, and an S3 secret. Those are local-only values,
// but decision 5 forbids printing or persisting the raw output regardless,
// because a terminal scrollback is routinely pasted into a chat, an issue, or a
// screenshot.
//
// So there are exactly two ways to run a command here:
//
//   * `runSuppressed` — stdio is `ignore`. The child's output goes to the null
//     device at the OS level; this process never holds it, so it cannot leak it
//     even by accident.
//   * `runCapturedStdout` — captures stdout for a caller that must parse it.
//     Only `credential-filter.mjs` uses it, and that module returns a filtered
//     object rather than the text.
//
// A failure never carries the child's output into the error. That is the
// output-leak path that matters most: the natural way to write this is
// `throw new Error(stderr)`, which would print a service-role key the first time
// the CLI failed.

import { spawn } from "node:child_process";

export class DemoSubprocessError extends Error {
  name = "DemoSubprocessError";

  constructor(message, exitCode) {
    super(message);
    this.exitCode = exitCode;
  }
}

// The message is built from the caller-supplied label and the numeric exit code
// only. Nothing derived from stdout or stderr can reach it.
export function describeSubprocessFailure(label, exitCode) {
  const code = Number.isInteger(exitCode) ? exitCode : "unknown";

  return `${label} failed (exit code ${code}). Output was suppressed on purpose; re-run the underlying command yourself if you need to diagnose it.`;
}

export function subprocessFailure(label, exitCode) {
  return new DemoSubprocessError(
    describeSubprocessFailure(label, exitCode),
    exitCode,
  );
}

function runWith(command, args, options, stdio) {
  const spawnFn = options.spawnFn ?? spawn;

  return new Promise((resolve, reject) => {
    const child = spawnFn(command, args, {
      cwd: options.cwd,
      env: options.env ?? process.env,
      shell: options.shell ?? false,
      stdio,
    });

    let stdout = "";

    if (stdio[1] === "pipe" && child.stdout) {
      child.stdout.setEncoding("utf8");
      child.stdout.on("data", (chunk) => {
        stdout += chunk;
      });
    }

    // A spawn error (command missing, EACCES) carries a path and an errno but no
    // credential material. It is still reduced to a fixed sentence so callers
    // cannot come to depend on rendering a raw system error.
    child.on("error", () => {
      reject(
        subprocessFailure(
          `${options.label ?? command} could not be started`,
          1,
        ),
      );
    });

    child.on("close", (code) => {
      resolve({ exitCode: code ?? 0, stdout });
    });
  });
}

// stdio `ignore` on every stream. Nothing is buffered here, so nothing can be
// leaked by a later change to error handling.
export async function runSuppressed(command, args, options = {}) {
  const result = await runWith(command, args, options, [
    "ignore",
    "ignore",
    "ignore",
  ]);

  return result.exitCode;
}

export async function runSuppressedOrThrow(command, args, options = {}) {
  const exitCode = await runSuppressed(command, args, options);

  if (exitCode !== 0) {
    throw subprocessFailure(options.label ?? command, exitCode);
  }

  return exitCode;
}

// stderr stays `ignore`: the Supabase CLI writes progress lines there, and there
// is no reason for this process to hold them.
export async function runCapturedStdout(command, args, options = {}) {
  return runWith(command, args, options, ["ignore", "pipe", "ignore"]);
}

// Replaces the current process's stdio for a long-lived foreground command such
// as the Expo dev server. Used only for commands that print no credential.
export function runInheritedStdio(command, args, options = {}) {
  return runWith(command, args, options, ["inherit", "inherit", "inherit"]);
}
