// The destructive-workflow lock.
//
// `demo:reset`, `demo:verify:consent`, and `demo:stop` all drive the same local
// Supabase project, and two of them running at once is not merely slow — it is
// wrong in ways that are hard to see afterwards:
//
//   * two resets interleaved produce a database built by one run and a
//     credential file written by the other, so the recorded password no longer
//     opens the accounts that exist;
//   * a reset that lands between the consent verification's grant and its
//     restore leaves a sharing grant and a synthetic check-in behind, which is
//     exactly the decision-9 violation the bracketing exists to prevent;
//   * a stop racing a reset kills the stack mid-migration.
//
// So the destructive commands take an exclusive lock on a file in the ignored
// `platform/.local-demo/` directory. The lock is **interprocess**: it is an
// `open(..., "wx")` exclusive create, which the OS resolves atomically, so two
// separate `node` processes cannot both hold it.
//
// It **fails fast rather than queueing**. A destructive command that silently
// waits and then fires minutes later, after the person who ran it has moved on,
// is worse than one that refuses and says why.
//
// Within a single process the lock is **reentrant**, counted by depth, because
// the consent verification holds it across the whole workflow while the resets
// it calls take it again.
//
// The lock file holds a pid, a hostname, a label, and a timestamp. No
// credential, no password, no path outside the repository.

import { hostname } from "node:os";
import { dirname } from "node:path";
import { mkdir, open, readFile, rm } from "node:fs/promises";

import { LOCK_DISPLAY_PATH, LOCK_FILE } from "./paths.mjs";

// A reset that has to start the stack from cold can legitimately take several
// minutes on Docker Desktop. A lock older than this, whose owner is not running,
// is treated as abandoned.
export const STALE_LOCK_MS = 30 * 60 * 1000;

export class DemoLockError extends Error {
  name = "DemoLockError";
}

let depth = 0;

// A lock is abandoned when the process that wrote it is gone, or when it is old
// enough that no plausible run is still in progress. Both conditions are
// required to be sure, except that an unreadable or malformed lock file is
// itself proof that no orderly holder exists.
export function isStaleLock(record, { now = Date.now(), isAlive } = {}) {
  if (record === null || typeof record !== "object") {
    return true;
  }

  const { pid, host, startedAt } = record;

  if (!Number.isInteger(pid) || pid <= 0 || typeof startedAt !== "string") {
    return true;
  }

  const startedMs = Date.parse(startedAt);

  if (!Number.isFinite(startedMs)) {
    return true;
  }

  if (now - startedMs > STALE_LOCK_MS) {
    return true;
  }

  // Liveness is only meaningful for a lock written by this machine. A lock from
  // another host is never assumed dead, whatever its pid says here.
  if (host !== hostname()) {
    return false;
  }

  return !(isAlive ?? isProcessAlive)(pid);
}

function isProcessAlive(pid) {
  try {
    // Signal 0 performs the permission and existence check without delivering
    // anything. On Windows, Node maps this to an process-handle probe.
    process.kill(pid, 0);

    return true;
  } catch (error) {
    // EPERM means the process exists but belongs to someone else.
    return error?.code === "EPERM";
  }
}

async function readLockRecord(lockFile) {
  try {
    return JSON.parse(await readFile(lockFile, "utf8"));
  } catch {
    // Unreadable or malformed: treated as abandoned by `isStaleLock`.
    return null;
  }
}

// Names the holder by label and pid only. A label is a fixed command name from
// this tooling, never anything user- or CLI-supplied.
export function describeLockConflict(record) {
  const label =
    record && typeof record.label === "string"
      ? record.label
      : "a demo command";
  const pid = record && Number.isInteger(record.pid) ? record.pid : "unknown";

  return `Another destructive demo command is already running (${label}, pid ${pid}). Only one may touch the local demo at a time. Wait for it to finish, or — if it is definitely gone — delete ${LOCK_DISPLAY_PATH} and try again.`;
}

async function acquire(label, lockFile) {
  await mkdir(dirname(lockFile), { recursive: true });

  for (let attempt = 0; attempt < 2; attempt += 1) {
    let handle;

    try {
      // Atomic: exactly one process can create the file.
      handle = await open(lockFile, "wx", 0o600);
    } catch (error) {
      if (error?.code !== "EEXIST") {
        throw new DemoLockError(
          `Could not take the local demo lock (${error?.code ?? "unknown error"}). Refusing to run a destructive command without it.`,
        );
      }

      const record = await readLockRecord(lockFile);

      if (!isStaleLock(record)) {
        throw new DemoLockError(describeLockConflict(record));
      }

      // Abandoned. Remove it and try once more; a second EEXIST means another
      // process won the race for the same abandoned lock, and it is theirs.
      await rm(lockFile, { force: true });
      continue;
    }

    try {
      await handle.writeFile(
        `${JSON.stringify({
          label,
          pid: process.pid,
          host: hostname(),
          startedAt: new Date().toISOString(),
        })}\n`,
        "utf8",
      );
    } finally {
      await handle.close();
    }

    return;
  }

  throw new DemoLockError(describeLockConflict(await readLockRecord(lockFile)));
}

// The only way to run a destructive workflow. Reentrant within this process, so
// a workflow that calls another one does not deadlock against itself.
//
// `lockFile` is overridable for the unit tests only; every command uses the
// default, so they all contend for the same lock.
export async function withDemoLock(label, run, { lockFile = LOCK_FILE } = {}) {
  if (depth > 0) {
    depth += 1;

    try {
      return await run();
    } finally {
      depth -= 1;
    }
  }

  await acquire(label, lockFile);
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
