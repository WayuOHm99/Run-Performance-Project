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
//
// A child that is killed by a signal is a **failure**, never a success. Node
// reports `code === null` in that case, and the obvious `code ?? 0` reads a
// killed `db reset` as a completed one. Every result here therefore carries the
// signal alongside the code, and `succeeded()` is the only definition of success
// in this tooling.

import { spawn } from "node:child_process";

// A child killed by a signal reports a `null` exit code. Treating that as 0 is
// the failure mode this constant exists to prevent: a `supabase db reset` that
// is killed part-way through leaves a half-migrated database, and reporting it
// as success would let the reset pipeline carry on and write a credential file
// for a baseline that was never built. 128 is the shell convention for
// "terminated by a signal" and is deliberately non-zero.
export const SIGNAL_TERMINATION_EXIT_CODE = 128;

// Node's signal names are fixed identifiers, not child output, but they are
// still passed through a shape check so nothing else can ever reach a message
// through this parameter.
function sanitizeSignal(signal) {
  return typeof signal === "string" && /^SIG[A-Z0-9]{1,12}$/.test(signal)
    ? signal
    : null;
}

export class DemoSubprocessError extends Error {
  name = "DemoSubprocessError";

  constructor(message, exitCode, signal = null) {
    super(message);
    this.exitCode = exitCode;
    this.signal = sanitizeSignal(signal);
  }
}

// The message is built from the caller-supplied label, the numeric exit code,
// and — at most — a signal name matched against the shape above. Nothing derived
// from stdout or stderr can reach it.
export function describeSubprocessFailure(label, exitCode, signal = null) {
  const terminatingSignal = sanitizeSignal(signal);

  if (terminatingSignal) {
    return `${label} was terminated by ${terminatingSignal} and did not complete. Output was suppressed on purpose, because it can carry a database URL, a JWT secret, and a service-role key. See docs/app/LOCAL-DEMO.md for recovery steps that do not print any of them.`;
  }

  const code = Number.isInteger(exitCode) ? exitCode : "unknown";

  return `${label} failed (exit code ${code}). Output was suppressed on purpose, because it can carry a database URL, a JWT secret, and a service-role key. See docs/app/LOCAL-DEMO.md for recovery steps that do not print any of them.`;
}

export function subprocessFailure(label, exitCode, signal = null) {
  return new DemoSubprocessError(
    describeSubprocessFailure(label, exitCode, signal),
    exitCode,
    signal,
  );
}

// The one place the "did this child succeed?" question is answered. A zero exit
// code is not enough on its own: a signalled child can report one on some
// platforms, so the signal is checked too.
export function succeeded({ exitCode, signal }) {
  return exitCode === 0 && !signal;
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

    // `code` is null exactly when the child was killed by a signal. It is mapped
    // to a non-zero code here rather than at each call site, so no caller can
    // forget and read a kill as a success.
    child.on("close", (code, signal) => {
      const terminatingSignal = sanitizeSignal(signal);

      resolve({
        exitCode:
          typeof code === "number" ? code : SIGNAL_TERMINATION_EXIT_CODE,
        signal: terminatingSignal,
        stdout,
      });
    });
  });
}

// stdio `ignore` on every stream. Nothing is buffered here, so nothing can be
// leaked by a later change to error handling.
export async function runSuppressed(command, args, options = {}) {
  const { exitCode, signal } = await runWith(command, args, options, [
    "ignore",
    "ignore",
    "ignore",
  ]);

  return { exitCode, signal };
}

export async function runSuppressedOrThrow(command, args, options = {}) {
  const result = await runSuppressed(command, args, options);

  if (!succeeded(result)) {
    throw subprocessFailure(
      options.label ?? command,
      result.exitCode,
      result.signal,
    );
  }

  return result.exitCode;
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
