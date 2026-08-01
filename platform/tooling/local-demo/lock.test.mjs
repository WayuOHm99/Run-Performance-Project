// The destructive-workflow lock.
//
// Every test here uses a temporary lock file rather than the real one in
// `platform/.local-demo/`, so running the suite can never take the lock away
// from a `demo:reset` that happens to be running, and a failing test can never
// leave the real lock behind.

import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { hostname, tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, it } from "node:test";

import {
  currentLockDepth,
  DemoLockError,
  describeLockConflict,
  isStaleLock,
  STALE_LOCK_MS,
  withDemoLock,
} from "./lock.mjs";
import { LOCK_DISPLAY_PATH } from "./paths.mjs";

let directory;
let lockFile;

beforeEach(async () => {
  directory = await mkdtemp(join(tmpdir(), "local-demo-lock-"));
  lockFile = join(directory, "demo.lock");
});

afterEach(async () => {
  await rm(directory, { recursive: true, force: true });
});

function heldLock(overrides = {}) {
  return JSON.stringify({
    label: "demo:reset",
    pid: process.pid,
    host: hostname(),
    startedAt: new Date().toISOString(),
    ...overrides,
  });
}

describe("withDemoLock", () => {
  it("creates the lock while running and removes it afterwards", async () => {
    let heldDuringRun = false;

    await withDemoLock(
      "demo:reset",
      async () => {
        heldDuringRun = existsSync(lockFile);
      },
      { lockFile },
    );

    assert.equal(heldDuringRun, true);
    assert.equal(existsSync(lockFile), false);
    assert.equal(currentLockDepth(), 0);
  });

  it("releases the lock when the workflow throws", async () => {
    await assert.rejects(
      withDemoLock(
        "demo:reset",
        async () => {
          throw new Error("synthetic failure");
        },
        { lockFile },
      ),
    );

    assert.equal(existsSync(lockFile), false);
    assert.equal(currentLockDepth(), 0);
  });

  // The consent verification holds the lock across its whole workflow and calls
  // `runReset`, which takes it again. Without reentrancy that is a deadlock
  // against itself.
  it("is reentrant within one process", async () => {
    const order = [];

    await withDemoLock(
      "demo:verify:consent",
      async () => {
        order.push(`outer:${currentLockDepth()}`);

        await withDemoLock(
          "demo:reset",
          async () => {
            order.push(`inner:${currentLockDepth()}`);
          },
          { lockFile },
        );

        order.push(`after-inner:${currentLockDepth()}`);
        assert.equal(existsSync(lockFile), true);
      },
      { lockFile },
    );

    assert.deepEqual(order, ["outer:1", "inner:2", "after-inner:1"]);
    assert.equal(existsSync(lockFile), false);
  });

  it("returns the workflow's value", async () => {
    const value = await withDemoLock("demo:reset", async () => 42, {
      lockFile,
    });

    assert.equal(value, 42);
  });

  // The interprocess property. A live lock written by another process is the
  // exact state a concurrent `demo:reset` leaves behind.
  it("refuses to run while another live process holds the lock", async () => {
    await writeFile(lockFile, heldLock(), "utf8");

    let ran = false;

    await assert.rejects(
      withDemoLock(
        "demo:reset",
        async () => {
          ran = true;
        },
        { lockFile },
      ),
      (error) => {
        assert.ok(error instanceof DemoLockError);
        assert.ok(error.message.includes("demo:reset"));

        return true;
      },
    );

    assert.equal(ran, false);
    // The other holder's lock is left exactly as it was.
    assert.equal(existsSync(lockFile), true);
    assert.equal(currentLockDepth(), 0);
  });

  it("takes over a lock abandoned by a dead process", async () => {
    // Pid 1 exists on every platform, so a pid that cannot exist is used
    // instead: `isStaleLock` sees it is not running.
    await writeFile(lockFile, heldLock({ pid: 0x7fffffff }), "utf8");

    let ran = false;

    await withDemoLock(
      "demo:reset",
      async () => {
        ran = true;

        const record = JSON.parse(await readFile(lockFile, "utf8"));
        assert.equal(record.pid, process.pid);
      },
      { lockFile },
    );

    assert.equal(ran, true);
    assert.equal(existsSync(lockFile), false);
  });

  it("takes over a lock file that is not readable as a record", async () => {
    await writeFile(lockFile, "{ not json", "utf8");

    let ran = false;

    await withDemoLock(
      "demo:reset",
      async () => {
        ran = true;
      },
      { lockFile },
    );

    assert.equal(ran, true);
  });

  it("writes no credential into the lock file", async () => {
    await withDemoLock(
      "demo:reset",
      async () => {
        const contents = await readFile(lockFile, "utf8");

        for (const fragment of [
          "sb_publishable_",
          ["sb", "secret", ""].join("_"),
          "eyJ",
          "postgres://",
          "password",
          "token",
        ]) {
          assert.ok(
            !contents.includes(fragment),
            "the lock file must carry no credential material",
          );
        }

        assert.deepEqual(Object.keys(JSON.parse(contents)).sort(), [
          "host",
          "label",
          "pid",
          "startedAt",
        ]);
      },
      { lockFile },
    );
  });
});

describe("isStaleLock", () => {
  const now = Date.parse("2026-08-01T12:00:00.000Z");
  const alive = () => true;
  const dead = () => false;

  function record(overrides = {}) {
    return {
      label: "demo:reset",
      pid: 4242,
      host: hostname(),
      startedAt: new Date(now - 1000).toISOString(),
      ...overrides,
    };
  }

  it("treats a live, recent lock from this host as held", () => {
    assert.equal(isStaleLock(record(), { now, isAlive: alive }), false);
  });

  it("treats a lock whose owner is gone as abandoned", () => {
    assert.equal(isStaleLock(record(), { now, isAlive: dead }), true);
  });

  it("treats a lock older than the stale window as abandoned even if a pid is live", () => {
    const old = record({
      startedAt: new Date(now - STALE_LOCK_MS - 1).toISOString(),
    });

    assert.equal(isStaleLock(old, { now, isAlive: alive }), true);
  });

  // A pid from another machine says nothing about a process here, so it is never
  // assumed dead.
  it("never assumes a lock from another host is dead", () => {
    const foreign = record({ host: "another-machine" });

    assert.equal(isStaleLock(foreign, { now, isAlive: dead }), false);
  });

  it("treats a malformed record as abandoned", () => {
    for (const value of [
      null,
      "a string",
      42,
      {},
      record({ pid: "4242" }),
      record({ pid: -1 }),
      record({ startedAt: "not a date" }),
      record({ startedAt: 1754049600000 }),
    ]) {
      assert.equal(isStaleLock(value, { now, isAlive: alive }), true);
    }
  });
});

describe("describeLockConflict", () => {
  it("names the holder and the file to remove, and nothing else", () => {
    const message = describeLockConflict({ label: "demo:reset", pid: 4242 });

    assert.ok(message.includes("demo:reset"));
    assert.ok(message.includes("4242"));
    assert.ok(message.includes(LOCK_DISPLAY_PATH));
  });

  it("degrades safely when the record is unusable", () => {
    for (const value of [null, {}, "text", 42]) {
      const message = describeLockConflict(value);

      assert.ok(message.includes("a demo command"));
      assert.ok(message.includes("unknown"));
    }
  });
});
