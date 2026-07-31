import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { Readable } from "node:stream";
import { describe, it } from "node:test";

import {
  DemoSubprocessError,
  describeSubprocessFailure,
  runCapturedStdout,
  runSuppressed,
  runSuppressedOrThrow,
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
function fakeSpawn({ exitCode = 0, stdout = "", stderr = "", record }) {
  return (command, args, options) => {
    record?.push({ command, args, stdio: options.stdio, shell: options.shell });

    const child = new EventEmitter();

    child.stdout = options.stdio[1] === "pipe" ? Readable.from([stdout]) : null;
    child.stderr = options.stdio[2] === "pipe" ? Readable.from([stderr]) : null;

    // `close` on a real ChildProcess fires only after its stdio streams have
    // closed. Emitting it before the fake stream drains would model a race that
    // does not exist and would make the capture assertion flaky.
    if (child.stdout) {
      child.stdout.on("end", () => child.emit("close", exitCode));
    } else {
      queueMicrotask(() => child.emit("close", exitCode));
    }

    return child;
  };
}

describe("describeSubprocessFailure", () => {
  it("is built from the label and exit code only", () => {
    const message = describeSubprocessFailure("supabase start", 1);

    assert.ok(message.includes("supabase start"));
    assert.ok(message.includes("1"));
  });

  it("cannot carry output, because it never receives any", () => {
    assert.equal(describeSubprocessFailure.length, 2);
  });

  it("handles a null exit code without printing 'null'", () => {
    assert.ok(describeSubprocessFailure("x", null).includes("unknown"));
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

  it("returns the exit code and nothing else", async () => {
    const result = await runSuppressed("node", [], {
      spawnFn: fakeSpawn({ exitCode: 7 }),
    });

    assert.equal(result, 7);
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

    // A number cannot carry a credential. This is the point of the API shape.
    assert.equal(typeof result, "number");
    assert.equal(record[0].stdio[1], "ignore");
    assert.equal(record[0].stdio[2], "ignore");
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

  it("never runs through a shell", async () => {
    const record = [];
    await runCapturedStdout("node", ["-e", ""], {
      spawnFn: fakeSpawn({ record }),
      shell: false,
    });

    assert.notEqual(record[0].shell, true);
  });
});
