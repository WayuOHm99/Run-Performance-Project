// The destructive-workflow lock.
//
// `demo:reset`, `demo:start`, `demo:stop`, and `demo:verify:consent` all drive
// the same local Supabase project, and two of them running at once is not merely
// slow — it is wrong in ways that are hard to see afterwards:
//
//   * two resets interleaved produce a database built by one run and a
//     credential file written by the other, so the recorded password no longer
//     opens the accounts that exist;
//   * a reset that lands between the consent verification's grant and its
//     restore leaves a sharing grant and a synthetic check-in behind, which is
//     exactly the decision-9 violation the bracketing exists to prevent;
//   * a stop racing a reset kills the stack mid-migration.
//
// ## What provides mutual exclusion
//
// One thing only: `open(lockFile, "wx")`. The OS resolves that atomically, so of
// any number of racing processes exactly one creates the file. Everything else
// below exists to make sure **nobody deletes a lock that somebody else holds**,
// because a wrongly deleted lock is worse than no lock at all: the holder keeps
// working believing it is protected while a third process acquires and runs
// alongside it.
//
// ## Two rules that were wrong in round 2 and are now fixed
//
// **Age is never proof.** The previous version broke any lock older than thirty
// minutes even when its owner was demonstrably running. A cold `supabase start`
// followed by a reset on a slow machine can exceed that, and the reward for
// being slow was having your lock stolen mid-migration. Age is now not consulted
// at all. The only thing that makes a lock breakable is that its owning process
// is **gone**, proven by `kill(pid, 0)`, and only for a lock written by this
// host.
//
// **Reading a lock and then deleting it is a race.** `if (stale) rm(lock)` looks
// safe and is not: between the read and the unlink another process can break the
// same stale lock and acquire a live one, which this process then deletes. Both
// then run. Breaking is therefore serialized by its own exclusively created
// claim file, and the claim holder re-reads the lock and requires the identical
// nonce before unlinking. Since the lock's owner is already proven dead, and a
// dead process cannot release its own lock, and only the single claim holder may
// unlink, nothing can change the lock file inside that window.
//
// The claim file is **never broken automatically**. It is held for milliseconds
// and removed in a `finally`, so the only way it survives is a hard kill inside
// that window; when that happens every destructive command refuses and names the
// file to delete. That is deliberate: refusing is recoverable in one command,
// and automatic claim recovery would reintroduce the race the claim exists to
// remove.
//
// ## What is in the file
//
// A label, a pid, a hostname, a timestamp, and a random nonce. No credential, no
// password, no path outside the repository. Nothing read back out of it is ever
// echoed: the label is matched against an allowlist before it reaches a message,
// and every other field is either a validated integer or unused.

import { randomBytes } from "node:crypto";
import { hostname } from "node:os";
import { dirname } from "node:path";
import { mkdir, open, readFile, rm } from "node:fs/promises";

import { BREAK_DISPLAY_PATH, BREAK_FILE, LOCK_FILE } from "./paths.mjs";

// The only labels this tooling ever writes. A label read back from the lock file
// is untrusted input — the file is world-writable in practice — so it reaches a
// message only by matching one of these exactly.
export const DESTRUCTIVE_LOCK_LABELS = Object.freeze([
  "demo:reset",
  "demo:start",
  "demo:stop",
  "demo:verify:consent",
]);

const FALLBACK_LOCK_LABEL = "a demo command";

export class DemoLockError extends Error {
  name = "DemoLockError";
}

let depth = 0;

// `kill(pid, 0)` performs the existence and permission check without delivering
// anything. EPERM means the process exists but belongs to someone else, which is
// still alive.
function isProcessAlive(pid) {
  try {
    process.kill(pid, 0);

    return true;
  } catch (error) {
    return error?.code === "EPERM";
  }
}

// A record is well-formed only if every field this module relies on is the type
// it is supposed to be. Anything else is treated as no orderly holder at all.
export function parseLockRecord(text) {
  let record;

  try {
    record = JSON.parse(text);
  } catch {
    // The parse error would quote the file. Discarded.
    return null;
  }

  if (record === null || typeof record !== "object") {
    return null;
  }

  const { pid, host, nonce } = record;

  if (!Number.isInteger(pid) || pid <= 0) {
    return null;
  }

  if (typeof host !== "string" || typeof nonce !== "string" || nonce === "") {
    return null;
  }

  return record;
}

// The single definition of "may be broken".
//
// Age is deliberately absent. A lock is breakable only when this host wrote it
// and the process that wrote it is gone, or when the file is not a usable record
// at all — which is itself proof that no orderly holder exists.
export function isLockBreakable(record, { isAlive = isProcessAlive } = {}) {
  if (record === null) {
    return true;
  }

  // A pid from another machine says nothing about a process here, so a foreign
  // lock is never assumed dead.
  if (record.host !== hostname()) {
    return false;
  }

  return !isAlive(record.pid);
}

// Names the holder using an **allowlisted** label and a validated integer pid.
// Nothing else from the file reaches the message, so a lock file carrying a
// credential-shaped label cannot print it here, in a stack, or in a serialized
// property.
export function describeLockConflict(record) {
  const rawLabel = record === null ? undefined : record.label;
  const label = DESTRUCTIVE_LOCK_LABELS.includes(rawLabel)
    ? rawLabel
    : FALLBACK_LOCK_LABEL;
  const pid =
    record !== null && Number.isInteger(record.pid) ? record.pid : "unknown";

  return `Another destructive demo command is already running (${label}, pid ${pid}). Only one may touch the local demo at a time. Wait for it to finish; if it is definitely gone, the next run will recover the lock by itself.`;
}

function describeBreakInProgress() {
  return `Another process is recovering an abandoned local demo lock. Only one may do that at a time, so this command stopped rather than risk running alongside it. Try again in a moment; if it never clears, delete ${BREAK_DISPLAY_PATH} and try again.`;
}

// `exists` and `record` are separate answers. "The file is gone" and "the file is
// there but says nothing usable" call for opposite actions, and collapsing them
// into one null is how a garbage lock file becomes unrecoverable.
async function readLockState(lockFile) {
  try {
    return {
      exists: true,
      record: parseLockRecord(await readFile(lockFile, "utf8")),
    };
  } catch {
    return { exists: false, record: null };
  }
}

async function readLockRecord(lockFile) {
  return (await readLockState(lockFile)).record;
}

async function writeLockFile(handle, label) {
  const record = {
    label,
    pid: process.pid,
    host: hostname(),
    startedAt: new Date().toISOString(),
    // Identifies *this* claim of the lock. A breaker must see the same nonce it
    // proved abandoned, or it refuses rather than unlinking.
    nonce: randomBytes(12).toString("hex"),
  };

  try {
    await handle.writeFile(`${JSON.stringify(record)}\n`, "utf8");
  } finally {
    await handle.close();
  }
}

// Returns a handle on success, or null when the file already exists.
async function tryCreateExclusive(file) {
  try {
    return await open(file, "wx", 0o600);
  } catch (error) {
    if (error?.code === "EEXIST") {
      return null;
    }

    throw new DemoLockError(
      `Could not take the local demo lock (${error?.code ?? "unknown error"}). Refusing to run a destructive command without it.`,
    );
  }
}

// Breaks a lock this caller has already proven abandoned, under a claim file so
// that at most one process can be doing so at any moment.
//
// `onBreakWindow` is a test seam: it runs while the claim is held and before the
// lock is re-read, which is exactly the window a concurrent recovery would have
// to exploit.
async function breakAndAcquire(
  lockFile,
  breakFile,
  label,
  provenNonce,
  { isAlive, onBreakWindow },
) {
  const claim = await tryCreateExclusive(breakFile);

  if (claim === null) {
    throw new DemoLockError(describeBreakInProgress());
  }

  try {
    await claim.writeFile(
      `${JSON.stringify({
        pid: process.pid,
        host: hostname(),
        startedAt: new Date().toISOString(),
      })}\n`,
      "utf8",
    );
  } finally {
    await claim.close();
  }

  try {
    if (onBreakWindow) {
      await onBreakWindow();
    }

    const current = await readLockState(lockFile);

    if (current.exists) {
      // Anything other than the exact record proven abandoned means the world
      // moved: a different holder, a re-acquired lock, a rewritten file. Refuse
      // rather than unlink something that might be live.
      //
      // A file that still holds no usable record is the one exception, and it is
      // not really one: it names no owner, and only this claim holder can have
      // touched it, so it cannot have become live since.
      if (
        current.record !== null &&
        (current.record.nonce !== provenNonce ||
          !isLockBreakable(current.record, { isAlive }))
      ) {
        throw new DemoLockError(describeLockConflict(current.record));
      }

      await rm(lockFile, { force: true });
    }

    const handle = await tryCreateExclusive(lockFile);

    if (handle === null) {
      // Someone acquired between the unlink and here. Only a claim holder can
      // unlink and there is only one, so this is the honest "lost the race"
      // case: refuse.
      throw new DemoLockError(
        describeLockConflict(await readLockRecord(lockFile)),
      );
    }

    await writeLockFile(handle, label);
  } finally {
    await rm(breakFile, { force: true });
  }
}

async function acquire(label, lockFile, breakFile, options) {
  await mkdir(dirname(lockFile), { recursive: true });

  const handle = await tryCreateExclusive(lockFile);

  if (handle !== null) {
    await writeLockFile(handle, label);

    return;
  }

  const record = await readLockRecord(lockFile);

  if (record === null) {
    // No usable record. There is no nonce to prove anything with, so the file
    // itself is the proof that no orderly holder exists: break it under the
    // claim, with a nonce that cannot match anything.
    await breakAndAcquire(lockFile, breakFile, label, null, options);

    return;
  }

  if (!isLockBreakable(record, options)) {
    throw new DemoLockError(describeLockConflict(record));
  }

  await breakAndAcquire(lockFile, breakFile, label, record.nonce, options);
}

// The only way to run a destructive workflow. Reentrant within this process, so
// a workflow that calls another one does not deadlock against itself.
//
// Every option is a default in production; `lockFile`, `breakFile`, `isAlive`,
// and `onBreakWindow` exist so the tests can drive the concurrent paths
// deterministically rather than by timing.
export async function withDemoLock(
  label,
  run,
  {
    lockFile = LOCK_FILE,
    breakFile = BREAK_FILE,
    isAlive = isProcessAlive,
    onBreakWindow = null,
  } = {},
) {
  if (depth > 0) {
    depth += 1;

    try {
      return await run();
    } finally {
      depth -= 1;
    }
  }

  await acquire(label, lockFile, breakFile, { isAlive, onBreakWindow });
  depth = 1;

  try {
    return await run();
  } finally {
    depth -= 1;

    if (depth === 0) {
      await rm(lockFile, { force: true });
    }
  }
}

// Test-only. Nothing in the commands calls this.
export function currentLockDepth() {
  return depth;
}
