import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { Readable } from "node:stream";
import { describe, it } from "node:test";

import {
  DemoSubprocessError,
  describeSubprocessFailure,
  describeSubprocessTimeout,
  runCapturedStdout,
  runSuppressed,
  runSuppressedOrThrow,
  SIGNAL_TERMINATION_EXIT_CODE,
  SUBPROCESS_TIMEOUT_EXIT_CODE,
  succeeded,
} from "./subprocess.mjs";

// What a failing `supabase start` would realistically put on its streams.
const CREDENTIAL_BEARING_OUTPUT = [
  "API URL: http://127.0.0.1:54321",
  "DB URL: postgresql://postgres:synthetic-password@127.0.0.1:54322/postgres",
  "JWT secret: synthetic-jwt-secret-for-tests",
  "service_role key: eyJsynthetic-legacy-jwt-for-tests-only",
].join("\n");

const FORBIDDEN_FRAGMENTS = [
  "synthetic-password",
  "synthetic-jwt-secret-for-tests",
  "eyJsynthetic-legacy-jwt-for-tests-only",
  "postgresql://",
];

// A fake child process. It records the stdio it was given, then emits the
// configured output and exit code.
//
// `signal` models a killed child: Node emits `close` with a **null** code and
// the signal name in that case, which is precisely the shape that a `code ?? 0`
// reading turns into a false success.
function fakeSpawn({
  exitCode = 0,
  signal = null,
  stdout = "",
  stderr = "",
  record,
}) {
  const closeCode = signal ? null : exitCode;

  return (command, args, options) => {
    record?.push({ command, args, stdio: options.stdio, shell: options.shell });

    const child = new EventEmitter();

    child.stdout = options.stdio[1] === "pipe" ? Readable.from([stdout]) : null;
    child.stderr = options.stdio[2] === "pipe" ? Readable.from([stderr]) : null;

    // `close` on a real ChildProcess fires only after its stdio streams have
    // closed. Emitting it before the fake stream drains would model a race that
    // does not exist and would make the capture assertion flaky.
    if (child.stdout) {
      child.stdout.on("end", () => child.emit("close", closeCode, signal));
    } else {
      queueMicrotask(() => child.emit("close", closeCode, signal));
    }

    return child;
  };
}

// Round 10, finding M3. A child that never closes on its own, so the timeout is
// the only thing that can end the call. It records every signal it is sent and
// can be told when — or whether — to close in response.
function hangingChild({ closeOn = "SIGTERM", closeCode = null } = {}) {
  const signals = [];
  const child = new EventEmitter();

  child.stdout = null;
  child.stderr = null;
  child.kill = (signal) => {
    signals.push(signal);

    if (signal === closeOn) {
      queueMicrotask(() => child.emit("close", closeCode, signal));
    }

    return true;
  };

  return { child, signals };
}

describe("subprocess timeouts", () => {
  it("resolves normally when the child finishes inside its timeout", async () => {
    const result = await runCapturedStdout("cmd", [], {
      spawnFn: fakeSpawn({ exitCode: 0, stdout: "done" }),
      timeoutMs: 5000,
    });

    assert.equal(result.exitCode, 0);
    assert.equal(result.stdout, "done");
  });

  it("terminates a stuck child and rejects with a sanitized timeout", async () => {
    const { child, signals } = hangingChild();

    await assert.rejects(
      () =>
        runCapturedStdout("cmd", [], {
          spawnFn: () => child,
          label: "local scalar query",
          timeoutMs: 5,
          killGraceMs: 5,
        }),
      (error) => {
        assert.ok(error instanceof DemoSubprocessError);
        assert.equal(error.exitCode, SUBPROCESS_TIMEOUT_EXIT_CODE);
        assert.equal(error.timedOut, true);
        assert.ok(error.message.includes("local scalar query"));
        assert.ok(error.message.includes("5ms"));

        return true;
      },
    );

    // The exact spawned child was signalled, by its own handle.
    assert.deepEqual(signals, ["SIGTERM"]);
  });

  it("escalates to SIGKILL when SIGTERM is ignored", async () => {
    const { child, signals } = hangingChild({ closeOn: "SIGKILL" });

    await assert.rejects(
      () =>
        runCapturedStdout("cmd", [], {
          spawnFn: () => child,
          timeoutMs: 5,
          killGraceMs: 5,
        }),
      DemoSubprocessError,
    );

    assert.deepEqual(signals, ["SIGTERM", "SIGKILL"]);
  });

  it("still settles when the child ignores SIGKILL entirely", async () => {
    const { child, signals } = hangingChild({ closeOn: "never" });

    await assert.rejects(
      () =>
        runCapturedStdout("cmd", [], {
          spawnFn: () => child,
          timeoutMs: 5,
          killGraceMs: 5,
        }),
      (error) => {
        assert.equal(error.timedOut, true);

        return true;
      },
    );

    assert.deepEqual(signals, ["SIGTERM", "SIGKILL"]);
  });

  // Double settlement is the classic defect in this shape of code: a late
  // `close` or `error` arriving after the timeout already rejected.
  it("cannot be settled twice by a late close or error", async () => {
    const { child } = hangingChild({ closeOn: "never" });

    const settled = [];
    const promise = runCapturedStdout("cmd", [], {
      spawnFn: () => child,
      timeoutMs: 5,
      killGraceMs: 5,
    }).then(
      () => settled.push("resolved"),
      () => settled.push("rejected"),
    );

    await promise;

    // Everything a dying child could still emit, after the fact.
    child.emit("close", 0, null);
    child.emit("close", 1, "SIGKILL");
    child.emit("error", new Error("late spawn error"));
    await new Promise((resolve) => setTimeout(resolve, 20));

    assert.deepEqual(settled, ["rejected"]);
  });

  it("does not reject a child that closes just before its deadline", async () => {
    const { child } = hangingChild({ closeOn: "never" });

    const promise = runCapturedStdout("cmd", [], {
      spawnFn: () => child,
      timeoutMs: 50,
      killGraceMs: 5,
    });

    queueMicrotask(() => child.emit("close", 0, null));

    const result = await promise;

    assert.equal(result.exitCode, 0);
  });

  it("kills nothing when no timeout is configured", async () => {
    const { child, signals } = hangingChild({ closeOn: "never" });

    const promise = runCapturedStdout("cmd", [], { spawnFn: () => child });

    await new Promise((resolve) => setTimeout(resolve, 20));
    assert.deepEqual(signals, []);

    child.emit("close", 0, null);
    assert.equal((await promise).exitCode, 0);
  });

  it("leaves no timer holding the event loop open", async () => {
    // A pending kill timer must be unref'd or cleared; if it were neither, the
    // handle count would keep climbing across calls.
    const before = process.getActiveResourcesInfo().length;

    for (let i = 0; i < 5; i += 1) {
      await runCapturedStdout("cmd", [], {
        spawnFn: fakeSpawn({ exitCode: 0, stdout: "x" }),
        timeoutMs: 10_000,
      });
    }

    assert.ok(process.getActiveResourcesInfo().length <= before + 1);
  });
});

describe("describeSubprocessTimeout", () => {
  it("is built from the label and the timeout only", () => {
    const message = describeSubprocessTimeout("local scalar query", 20_000);

    assert.ok(message.includes("local scalar query"));
    assert.ok(message.includes("20000ms"));
  });

  it("cannot carry output, because it never receives any", () => {
    assert.equal(describeSubprocessTimeout.length, 2);

    const message = describeSubprocessTimeout("label", 1);

    for (const secret of CREDENTIAL_BEARING_OUTPUT.split("\n")) {
      assert.ok(!message.includes(secret));
    }
  });
});

describe("describeSubprocessFailure", () => {
  it("is built from the label and exit code only", () => {
    const message = describeSubprocessFailure("supabase start", 1);

    assert.ok(message.includes("supabase start"));
    assert.ok(message.includes("1"));
  });

  it("cannot carry output, because it never receives any", () => {
    // Label, exit code, and an optional signal name. No parameter through which
    // stdout or stderr could arrive.
    assert.equal(describeSubprocessFailure.length, 2);
    assert.equal(
      describeSubprocessFailure("supabase start", 1, "SIGKILL").includes(
        "SIGKILL",
      ),
      true,
    );
  });

  it("handles a null exit code without printing 'null'", () => {
    assert.ok(describeSubprocessFailure("x", null).includes("unknown"));
  });

  it("says a signalled child did not complete, rather than that it failed", () => {
    const message = describeSubprocessFailure(
      "supabase db reset",
      null,
      "SIGTERM",
    );

    assert.ok(message.includes("SIGTERM"));
    assert.ok(message.includes("did not complete"));
    assert.ok(!message.includes("unknown"));
  });

  // The signal name reaches the message, so it goes through a shape check like
  // everything else that does.
  it("ignores a signal value that is not a signal name", () => {
    for (const value of [
      "DB URL: postgresql://postgres:synthetic-password@127.0.0.1:54322/postgres",
      "sigterm",
      "",
      42,
      { toString: () => "SIGTERM" },
    ]) {
      const message = describeSubprocessFailure("supabase start", 3, value);

      assert.ok(message.includes("exit code 3"));
      assert.ok(!message.includes("synthetic-password"));
    }
  });
});

describe("succeeded", () => {
  it("requires a zero exit code and no signal", () => {
    assert.equal(succeeded({ exitCode: 0, signal: null }), true);
    assert.equal(succeeded({ exitCode: 1, signal: null }), false);
    assert.equal(succeeded({ exitCode: 0, signal: "SIGKILL" }), false);
  });
});

describe("runSuppressed", () => {
  it("ignores all three streams", async () => {
    const record = [];
    await runSuppressed("node", ["-e", ""], {
      spawnFn: fakeSpawn({ record }),
    });

    assert.deepEqual(record[0].stdio, ["ignore", "ignore", "ignore"]);
  });

  it("returns the exit code and the signal, and nothing else", async () => {
    const result = await runSuppressed("node", [], {
      spawnFn: fakeSpawn({ exitCode: 7 }),
    });

    assert.deepEqual(result, { exitCode: 7, signal: null });
  });

  it("holds no output even when the child writes to both streams", async () => {
    const record = [];
    const result = await runSuppressed("node", [], {
      spawnFn: fakeSpawn({
        exitCode: 0,
        stdout: CREDENTIAL_BEARING_OUTPUT,
        stderr: CREDENTIAL_BEARING_OUTPUT,
        record,
      }),
      label: "supabase start",
    });

    // A number and a signal name cannot carry a credential. This is the point of
    // the API shape.
    assert.equal(typeof result.exitCode, "number");
    assert.equal(result.signal, null);
    assert.equal(record[0].stdio[1], "ignore");
    assert.equal(record[0].stdio[2], "ignore");
  });

  // The bug this guards: Node reports `code === null` for a killed child, and
  // `code ?? 0` reads that as success. A `supabase db reset` killed part-way
  // leaves a half-migrated database, and calling it a success would let the
  // reset pipeline carry on and write a credential file describing a baseline
  // that was never built.
  it("reports a signalled child as a non-zero failure, not a success", async () => {
    const result = await runSuppressed("node", [], {
      spawnFn: fakeSpawn({ signal: "SIGKILL" }),
    });

    assert.notEqual(result.exitCode, 0);
    assert.equal(result.exitCode, SIGNAL_TERMINATION_EXIT_CODE);
    assert.equal(result.signal, "SIGKILL");
    assert.equal(succeeded(result), false);
  });
});

describe("runSuppressedOrThrow", () => {
  it("throws a sanitized error on a non-zero exit", async () => {
    await assert.rejects(
      runSuppressedOrThrow("node", [], {
        spawnFn: fakeSpawn({ exitCode: 1, stderr: CREDENTIAL_BEARING_OUTPUT }),
        label: "supabase start",
      }),
      (error) => {
        assert.ok(error instanceof DemoSubprocessError);
        assert.equal(error.exitCode, 1);

        for (const fragment of FORBIDDEN_FRAGMENTS) {
          assert.ok(
            !error.message.includes(fragment),
            `the failure message leaked: ${fragment}`,
          );
        }

        return true;
      },
    );
  });

  // The leak path that would matter most in practice: the child prints its
  // credential block and *then* fails.
  it("leaks nothing when a failing child printed credentials to stdout", async () => {
    await assert.rejects(
      runSuppressedOrThrow("node", [], {
        spawnFn: fakeSpawn({ exitCode: 2, stdout: CREDENTIAL_BEARING_OUTPUT }),
        label: "supabase start",
      }),
      (error) => {
        const serialized = `${error.message}${error.stack ?? ""}`;

        for (const fragment of FORBIDDEN_FRAGMENTS) {
          assert.ok(!serialized.includes(fragment));
        }

        return true;
      },
    );
  });

  it("sanitizes a spawn error too", async () => {
    const spawnFn = () => {
      const child = new EventEmitter();
      child.stdout = null;
      child.stderr = null;
      queueMicrotask(() =>
        child.emit("error", new Error(CREDENTIAL_BEARING_OUTPUT)),
      );

      return child;
    };

    await assert.rejects(
      runSuppressedOrThrow("missing-binary", [], {
        spawnFn,
        label: "supabase",
      }),
      (error) => {
        for (const fragment of FORBIDDEN_FRAGMENTS) {
          assert.ok(!error.message.includes(fragment));
        }

        return true;
      },
    );
  });

  it("does not throw on a zero exit", async () => {
    await runSuppressedOrThrow("node", [], { spawnFn: fakeSpawn({}) });
  });

  it("throws when the child is killed by a signal", async () => {
    await assert.rejects(
      runSuppressedOrThrow("node", [], {
        spawnFn: fakeSpawn({
          signal: "SIGTERM",
          stdout: CREDENTIAL_BEARING_OUTPUT,
        }),
        label: "supabase db reset --local --no-seed",
      }),
      (error) => {
        assert.ok(error instanceof DemoSubprocessError);
        assert.equal(error.signal, "SIGTERM");
        assert.notEqual(error.exitCode, 0);
        assert.ok(error.message.includes("did not complete"));

        const serialized = `${error.message}${error.stack ?? ""}`;

        for (const fragment of FORBIDDEN_FRAGMENTS) {
          assert.ok(!serialized.includes(fragment));
        }

        return true;
      },
    );
  });

  // A child that is killed *and* reports a zero code — which some platforms do —
  // must still be a failure.
  it("throws when a signalled child also reports exit code 0", async () => {
    await assert.rejects(
      runSuppressedOrThrow("node", [], {
        spawnFn: (command, args, options) => {
          const child = new EventEmitter();
          child.stdout = null;
          child.stderr = null;
          void options;
          queueMicrotask(() => child.emit("close", 0, "SIGKILL"));

          return child;
        },
        label: "supabase stop",
      }),
      (error) => {
        assert.equal(error.signal, "SIGKILL");

        return true;
      },
    );
  });
});

describe("runCapturedStdout", () => {
  it("captures stdout but still ignores stderr", async () => {
    const record = [];
    const { stdout, exitCode } = await runCapturedStdout("node", [], {
      spawnFn: fakeSpawn({ stdout: '{"ok":1}', record }),
    });

    assert.equal(stdout, '{"ok":1}');
    assert.equal(exitCode, 0);
    assert.deepEqual(record[0].stdio, ["ignore", "pipe", "ignore"]);
  });

  // The captured-stdout path is the one that feeds the credential filter. A
  // child killed mid-write returns a truncated document, so the signal must
  // reach the caller rather than being read as a complete result.
  it("reports a signal alongside whatever it managed to capture", async () => {
    const { exitCode, signal } = await runCapturedStdout("node", [], {
      spawnFn: fakeSpawn({ signal: "SIGTERM", stdout: '{"API_URL":' }),
    });

    assert.equal(signal, "SIGTERM");
    assert.notEqual(exitCode, 0);
  });

  it("never runs through a shell", async () => {
    const record = [];
    await runCapturedStdout("node", ["-e", ""], {
      spawnFn: fakeSpawn({ record }),
      shell: false,
    });

    assert.notEqual(record[0].shell, true);
  });
});
