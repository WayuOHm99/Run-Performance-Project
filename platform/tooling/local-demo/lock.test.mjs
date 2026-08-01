// The destructive-workflow lock.
//
// Every test here uses a temporary lock file rather than the real one in
// `platform/.local-demo/`, so running the suite can never take the lock away
// from a `demo:reset` that happens to be running, and a failing test can never
// leave the real lock behind.
//
// Concurrency is driven through the `isAlive` and `onBreakWindow` seams rather
// than by starting processes and hoping the timing lands. Every test below is
// deterministic: the interleaving it exercises is the one it asks for.

import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { hostname, tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { afterEach, beforeEach, describe, it } from "node:test";

const here = dirname(fileURLToPath(import.meta.url));

import {
  currentLockDepth,
  DemoLockError,
  describeLockConflict,
  DESTRUCTIVE_LOCK_LABELS,
  isLockBreakable,
  parseLockRecord,
  withDemoLock,
} from "./lock.mjs";
import { BREAK_DISPLAY_PATH } from "./paths.mjs";

const THIRTY_MINUTES_MS = 30 * 60 * 1000;

let directory;
let lockFile;
let breakFile;

beforeEach(async () => {
  directory = await mkdtemp(join(tmpdir(), "local-demo-lock-"));
  lockFile = join(directory, "demo.lock");
  breakFile = join(directory, "demo.lock.break");
});

afterEach(async () => {
  await rm(directory, { recursive: true, force: true });
});

function lockRecord(overrides = {}) {
  return JSON.stringify({
    label: "demo:reset",
    pid: 4242,
    host: hostname(),
    startedAt: new Date().toISOString(),
    nonce: "abcdef0123456789abcdef01",
    ...overrides,
  });
}

const alive = () => true;
const dead = () => false;

function options(extra = {}) {
  return { lockFile, breakFile, ...extra };
}

describe("withDemoLock", () => {
  it("creates the lock while running and removes it afterwards", async () => {
    let heldDuringRun = false;

    await withDemoLock(
      "demo:reset",
      async () => {
        heldDuringRun = existsSync(lockFile);
      },
      options(),
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
        options(),
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
          options(),
        );

        order.push(`after-inner:${currentLockDepth()}`);
        assert.equal(existsSync(lockFile), true);
      },
      options(),
    );

    assert.deepEqual(order, ["outer:1", "inner:2", "after-inner:1"]);
    assert.equal(existsSync(lockFile), false);
  });

  it("returns the workflow's value", async () => {
    const value = await withDemoLock("demo:reset", async () => 42, options());

    assert.equal(value, 42);
  });

  it("refuses to run while another live process holds the lock", async () => {
    await writeFile(lockFile, lockRecord(), "utf8");

    let ran = false;

    await assert.rejects(
      withDemoLock(
        "demo:reset",
        async () => {
          ran = true;
        },
        options({ isAlive: alive }),
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

  // Round 2 broke any lock older than thirty minutes, which meant a slow cold
  // start was punished by having its lock stolen mid-migration. Age is not
  // evidence of death and is no longer consulted.
  it("honours a LIVE lock that is far older than thirty minutes", async () => {
    const ancient = new Date(Date.now() - THIRTY_MINUTES_MS * 4).toISOString();

    await writeFile(lockFile, lockRecord({ startedAt: ancient }), "utf8");

    let ran = false;

    await assert.rejects(
      withDemoLock(
        "demo:reset",
        async () => {
          ran = true;
        },
        options({ isAlive: alive }),
      ),
      DemoLockError,
    );

    assert.equal(ran, false);
    // Not merely refused: the ancient live lock is still intact and unchanged.
    assert.equal(existsSync(lockFile), true);
    assert.equal(
      parseLockRecord(await readFile(lockFile, "utf8")).startedAt,
      ancient,
    );
  });

  it("recovers a lock whose owning process is gone", async () => {
    await writeFile(lockFile, lockRecord(), "utf8");

    let ran = false;

    await withDemoLock(
      "demo:reset",
      async () => {
        ran = true;

        const record = parseLockRecord(await readFile(lockFile, "utf8"));
        assert.equal(record.pid, process.pid);
      },
      options({ isAlive: dead }),
    );

    assert.equal(ran, true);
    assert.equal(existsSync(lockFile), false);
    // The recovery claim is always cleaned up.
    assert.equal(existsSync(breakFile), false);
  });

  it("recovers a lock file that holds no usable record", async () => {
    await writeFile(lockFile, "{ not json", "utf8");

    let ran = false;

    await withDemoLock(
      "demo:reset",
      async () => {
        ran = true;
      },
      options({ isAlive: alive }),
    );

    assert.equal(ran, true);
    assert.equal(existsSync(breakFile), false);
  });

  it("never breaks a lock written by another host", async () => {
    await writeFile(lockFile, lockRecord({ host: "another-machine" }), "utf8");

    await assert.rejects(
      withDemoLock("demo:reset", async () => {}, options({ isAlive: dead })),
      DemoLockError,
    );

    assert.equal(existsSync(lockFile), true);
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
          "nonce",
          "pid",
          "startedAt",
        ]);
      },
      options(),
    );
  });
});

// The round 2 bug this whole design replaces: read the lock, decide it is stale,
// unlink it — and delete a lock another process legitimately acquired in
// between. Both then run, and the holder never finds out.
describe("concurrent recovery of the same abandoned lock", () => {
  it("does not delete a live lock acquired inside the recovery window", async () => {
    await writeFile(lockFile, lockRecord({ nonce: "aaaa1111" }), "utf8");

    // While this process holds the recovery claim, simulate the other process
    // having completed its own recovery and taken a fresh, live lock.
    const freshNonce = "bbbb2222";
    let ran = false;

    await assert.rejects(
      withDemoLock(
        "demo:reset",
        async () => {
          ran = true;
        },
        // The lock is genuinely abandoned when inspected, so recovery starts.
        // The nonce — not the liveness check — is what stops the unlink, which
        // is the point: even a lock whose owner still looks dead is not the lock
        // this process proved abandoned.
        options({
          isAlive: dead,
          onBreakWindow: async () => {
            await writeFile(
              lockFile,
              lockRecord({ nonce: freshNonce, pid: 5150 }),
              "utf8",
            );
          },
        }),
      ),
      (error) => {
        assert.ok(error instanceof DemoLockError);

        return true;
      },
    );

    assert.equal(ran, false);

    // The decisive assertion: the other process's lock is still there, with its
    // own nonce. A nonce check is what makes "the file I proved abandoned" and
    // "the file that is there now" different questions.
    const survivor = parseLockRecord(await readFile(lockFile, "utf8"));

    assert.equal(survivor.nonce, freshNonce);
    assert.equal(survivor.pid, 5150);
    assert.equal(existsSync(breakFile), false);
  });

  it("refuses when another process already holds the recovery claim", async () => {
    await writeFile(lockFile, lockRecord(), "utf8");
    await writeFile(breakFile, JSON.stringify({ pid: 5150 }), "utf8");

    let ran = false;

    await assert.rejects(
      withDemoLock(
        "demo:reset",
        async () => {
          ran = true;
        },
        options({ isAlive: dead }),
      ),
      (error) => {
        assert.ok(error instanceof DemoLockError);
        assert.ok(error.message.includes("recovering"));
        assert.ok(error.message.includes(BREAK_DISPLAY_PATH));

        return true;
      },
    );

    assert.equal(ran, false);
    // Neither the other recovery's claim nor the lock it is working on is
    // touched.
    assert.equal(existsSync(breakFile), true);
    assert.equal(existsSync(lockFile), true);
  });

  it("refuses when the lock is re-taken by a live owner during recovery", async () => {
    await writeFile(lockFile, lockRecord({ nonce: "cccc3333" }), "utf8");

    await assert.rejects(
      withDemoLock("demo:reset", async () => {}, {
        lockFile,
        breakFile,
        // Dead when first inspected, alive by the time the claim is held: the
        // pid was reused, or the check raced a restart.
        isAlive: (() => {
          let calls = 0;

          return () => {
            calls += 1;

            return calls > 1;
          };
        })(),
      }),
      DemoLockError,
    );

    assert.equal(existsSync(lockFile), true);
    assert.equal(existsSync(breakFile), false);
  });

  // The reentrancy counter is process-local, so "another process" cannot be
  // simulated in this one — a second `withDemoLock` here would take the
  // reentrant path and prove nothing. These two use a real child process, and
  // are still deterministic: the parent decides exactly when the child runs.
  it("refuses a genuinely separate process while this one holds the lock", async () => {
    const result = await withDemoLock(
      "demo:reset",
      () => acquireInChildProcess(),
      options(),
    );

    assert.equal(result.acquired, false);
    assert.ok(result.message.includes("already running"));
    // The child saw this process as alive, so it refused rather than recovering.
    assert.ok(!result.message.includes("recovering"));
  });

  it("lets a separate process recover a lock whose owner is gone", async () => {
    // Pid 0x7fffffff cannot be running, so the child's real liveness check
    // reports it dead without any injection.
    await writeFile(lockFile, lockRecord({ pid: 0x7fffffff }), "utf8");

    const result = await acquireInChildProcess();

    assert.equal(result.acquired, true);
    assert.equal(existsSync(lockFile), false);
    assert.equal(existsSync(breakFile), false);
  });
});

// Runs one acquire-and-release in a child `node`, against the same lock file.
// The child uses the real liveness check and the real module.
function acquireInChildProcess() {
  const source = `
    const { withDemoLock } = await import(${JSON.stringify(pathToFileURL(join(here, "lock.mjs")).href)});
    const options = {
      lockFile: ${JSON.stringify(lockFile)},
      breakFile: ${JSON.stringify(breakFile)},
    };
    try {
      await withDemoLock("demo:stop", async () => {}, options);
      process.stdout.write(JSON.stringify({ acquired: true, message: "" }));
    } catch (error) {
      process.stdout.write(
        JSON.stringify({ acquired: false, message: error.message }),
      );
    }
  `;

  return new Promise((resolve, reject) => {
    const child = spawn(
      process.execPath,
      ["--input-type=module", "-e", source],
      { stdio: ["ignore", "pipe", "ignore"] },
    );

    let stdout = "";

    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });
    child.on("error", reject);
    child.on("close", () => {
      try {
        resolve(JSON.parse(stdout));
      } catch {
        reject(new Error("the child process produced no usable result"));
      }
    });
  });
}

describe("isLockBreakable", () => {
  it("treats a live lock from this host as held", () => {
    assert.equal(
      isLockBreakable(JSON.parse(lockRecord()), { isAlive: alive }),
      false,
    );
  });

  it("treats a lock whose owner is gone as breakable", () => {
    assert.equal(
      isLockBreakable(JSON.parse(lockRecord()), { isAlive: dead }),
      true,
    );
  });

  it("never assumes a lock from another host is dead", () => {
    assert.equal(
      isLockBreakable(JSON.parse(lockRecord({ host: "another-machine" })), {
        isAlive: dead,
      }),
      false,
    );
  });

  it("treats an unusable record as breakable", () => {
    assert.equal(isLockBreakable(null, { isAlive: alive }), true);
  });

  // Age is not an input. It cannot be, or a slow run loses its lock.
  it("ignores age entirely, however old the lock is", () => {
    for (const ageMs of [0, THIRTY_MINUTES_MS, THIRTY_MINUTES_MS * 100]) {
      const record = JSON.parse(
        lockRecord({ startedAt: new Date(Date.now() - ageMs).toISOString() }),
      );

      assert.equal(isLockBreakable(record, { isAlive: alive }), false);
      assert.equal(isLockBreakable(record, { isAlive: dead }), true);
    }
  });

  it("takes no timestamp argument at all", () => {
    assert.equal(isLockBreakable.length, 1);
  });
});

describe("parseLockRecord", () => {
  it("rejects anything that is not a usable record", () => {
    for (const text of [
      "{ not json",
      "null",
      '"a string"',
      "42",
      "[]",
      JSON.stringify({ pid: "4242", host: hostname(), nonce: "a" }),
      JSON.stringify({ pid: -1, host: hostname(), nonce: "a" }),
      JSON.stringify({ pid: 1, host: 42, nonce: "a" }),
      JSON.stringify({ pid: 1, host: hostname(), nonce: "" }),
      JSON.stringify({ pid: 1, host: hostname() }),
    ]) {
      assert.equal(parseLockRecord(text), null);
    }
  });

  it("accepts a well-formed record", () => {
    assert.equal(parseLockRecord(lockRecord()).pid, 4242);
  });
});

// The lock file is ordinary, writable, unauthenticated state on disk. Anything
// read back out of it is untrusted input, and a label is the one field that used
// to reach a message verbatim.
describe("describeLockConflict never echoes an untrusted label", () => {
  const sentinel = [
    "sb",
    "secret",
    "synthetic-sentinel-that-must-never-be-printed",
  ].join("_");

  function serializeError(error) {
    return [
      error?.message ?? "",
      error?.stack ?? "",
      error?.cause?.message ?? "",
      JSON.stringify(error, Object.getOwnPropertyNames(error ?? {})),
    ].join("\n");
  }

  it("replaces a credential-shaped label with a fixed fallback", () => {
    const message = describeLockConflict({
      label: sentinel,
      pid: 4242,
      host: hostname(),
      nonce: "a",
    });

    assert.ok(!message.includes(sentinel), "the label was echoed");
    assert.ok(!message.includes("sb_secret"), "a credential prefix was echoed");
    assert.ok(message.includes("a demo command"));
    assert.ok(message.includes("4242"));
  });

  it("keeps a sentinel label out of the message, stack, cause, and properties", async () => {
    await writeFile(
      lockFile,
      lockRecord({ label: sentinel, host: hostname() }),
      "utf8",
    );

    await assert.rejects(
      withDemoLock("demo:reset", async () => {}, options({ isAlive: alive })),
      (error) => {
        const serialized = serializeError(error);

        assert.ok(
          !serialized.includes(sentinel),
          "the failure output leaked the lock file's label",
        );
        assert.ok(!serialized.includes("synthetic-sentinel"));

        return true;
      },
    );
  });

  it("echoes only labels this tooling itself writes", () => {
    for (const label of DESTRUCTIVE_LOCK_LABELS) {
      const message = describeLockConflict({
        label,
        pid: 1,
        host: "h",
        nonce: "n",
      });

      assert.ok(message.includes(label));
    }

    for (const label of ["demo:reset ", "DEMO:RESET", "", null, 42, {}]) {
      const message = describeLockConflict({
        label,
        pid: 1,
        host: "h",
        nonce: "n",
      });

      assert.ok(message.includes("a demo command"));
    }
  });

  it("degrades safely when there is no record at all", () => {
    const message = describeLockConflict(null);

    assert.ok(message.includes("a demo command"));
    assert.ok(message.includes("unknown"));
  });

  it("never echoes a hostname", () => {
    const message = describeLockConflict({
      label: "demo:reset",
      pid: 1,
      host: "synthetic-hostname-that-should-not-appear",
      nonce: "n",
    });

    assert.ok(!message.includes("synthetic-hostname-that-should-not-appear"));
  });
});
