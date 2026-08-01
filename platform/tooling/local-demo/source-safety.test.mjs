// Scans the demo tooling's own source for things decisions 1, 3, 5, and 7 forbid.
//
// The point is that these are properties of the code rather than of my care
// while writing it: a future edit that adds `--linked`, reads `.env.local`, or
// prints the password fails here rather than at review.
//
// Comments are stripped before scanning, because the modules deliberately
// *document* the forbidden flags ("never `--all`, never `--no-backup`") and a
// naive scan would flag the documentation that exists to prevent the mistake.

import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";

const here = dirname(fileURLToPath(import.meta.url));

// Block comments first, then whole-line `//` comments. Trailing-comment
// stripping is deliberately not attempted: a naive `//` rule would truncate the
// `postgres://` literals in the credential filter's rejection list.
function stripComments(source) {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split(/\r?\n/)
    .filter((line) => !line.trim().startsWith("//"))
    .join("\n");
}

// For the "never logs a credential" scan the risk is an *interpolated variable*,
// not the English word. Prose such as "the password is not printed here" is
// exactly the reassurance the terminal should carry, so string literals are
// removed before scanning — except the `${...}` holes in a template literal,
// which are precisely the interpolations worth catching.
function stripStringLiterals(line) {
  return line
    .replace(/`([^`]*)`/g, (_match, inner) =>
      (inner.match(/\$\{[^}]*\}/g) ?? []).join(" "),
    )
    .replace(/'(?:[^'\\]|\\.)*'/g, "''")
    .replace(/"(?:[^"\\]|\\.)*"/g, '""');
}

const sourceFiles = readdirSync(here)
  .filter((name) => name.endsWith(".mjs") && !name.endsWith(".test.mjs"))
  .map((name) => ({
    name,
    code: stripComments(readFileSync(join(here, name), "utf8")),
  }));

it("finds the tooling modules to scan", () => {
  assert.ok(
    sourceFiles.length >= 12,
    `only found ${sourceFiles.length} modules`,
  );
});

describe("decision 1 — local Supabase only", () => {
  const forbidden = [
    "--linked",
    "--db-url",
    "db-url",
    "supabase.co",
    "db push",
    "db pull",
    '"push"',
    '"link"',
    '"login"',
    '"deploy"',
    "project-ref",
  ];

  for (const { name, code } of sourceFiles) {
    it(`${name} contacts nothing hosted`, () => {
      for (const fragment of forbidden) {
        assert.ok(
          !code.includes(fragment),
          `${name} must not contain ${fragment}`,
        );
      }
    });
  }

  it("passes --local to every CLI command that accepts it", () => {
    const cli = sourceFiles.find((file) => file.name === "supabase-cli.mjs");

    for (const subcommand of ["reset", "query"]) {
      const uses = cli.code.split(`"${subcommand}"`).length - 1;
      assert.ok(uses > 0, `expected the CLI module to run db ${subcommand}`);
    }

    // Every `db` invocation carries `--local`.
    const dbInvocations =
      cli.code.match(/cliArgs\(\[[^\]]*"db"[^\]]*\]\)/g) ?? [];
    assert.ok(dbInvocations.length >= 3);

    for (const invocation of dbInvocations) {
      assert.ok(
        invocation.includes('"--local"'),
        `a db invocation is missing --local: ${invocation}`,
      );
    }
  });

  it("always resets with --no-seed", () => {
    const cli = sourceFiles.find((file) => file.name === "supabase-cli.mjs");
    const resets = cli.code.match(/cliArgs\(\[[^\]]*"reset"[^\]]*\]\)/g) ?? [];

    assert.equal(resets.length, 1);
    assert.ok(resets[0].includes('"--no-seed"'));
  });
});

describe("decision 3 — never touch apps/mobile/.env.local", () => {
  for (const { name, code } of sourceFiles) {
    it(`${name} names no dotenv file`, () => {
      for (const fragment of [
        ".env.local",
        ".env.example",
        "dotenv",
        '.env"',
      ]) {
        assert.ok(
          !code.includes(fragment),
          `${name} must not reference ${fragment}`,
        );
      }
    });
  }

  it("sets EXPO_NO_DOTENV when launching", () => {
    const launch = sourceFiles.find((file) => file.name === "launch.mjs");

    assert.ok(launch.code.includes("EXPO_NO_DOTENV"));
  });
});

describe("decision 4 — the endpoint allowlist is the only source of URLs", () => {
  it("only endpoint.mjs contains a literal Supabase endpoint", () => {
    for (const { name, code } of sourceFiles) {
      if (name === "endpoint.mjs") {
        continue;
      }

      assert.ok(
        !code.includes("127.0.0.1:54321"),
        `${name} must take the endpoint from endpoint.mjs, not restate it`,
      );
      assert.ok(
        !code.includes("10.0.2.2"),
        `${name} must not restate the alias`,
      );
    }
  });
});

describe("decision 5 — only the publishable field crosses the boundary", () => {
  const secretFields = [
    "ANON_KEY",
    "SERVICE_ROLE_KEY",
    "SECRET_KEY",
    "JWT_SECRET",
    "DB_URL",
    "S3_PROTOCOL_ACCESS_KEY_ID",
    "S3_PROTOCOL_ACCESS_KEY_SECRET",
  ];

  for (const { name, code } of sourceFiles) {
    it(`${name} reads no secret-bearing status field`, () => {
      for (const field of secretFields) {
        assert.ok(!code.includes(field), `${name} must not read ${field}`);
      }
    });
  }

  it("only credential-filter.mjs captures CLI stdout for parsing", () => {
    const capturing = sourceFiles.filter((file) =>
      file.code.includes("runCapturedStdout"),
    );

    assert.deepEqual(capturing.map((file) => file.name).sort(), [
      "credential-filter.mjs",
      "subprocess.mjs",
      "supabase-cli.mjs",
    ]);
  });

  it("start and stop are run with output suppressed", () => {
    const cli = sourceFiles.find((file) => file.name === "supabase-cli.mjs");

    for (const command of ['"start"', '"stop"']) {
      const line = cli.code
        .split("\n")
        .find((candidate) => candidate.includes(command));

      assert.ok(line, `expected an invocation of ${command}`);
    }

    assert.ok(!cli.code.includes("runInheritedStdio"));
  });
});

describe("decision 5 and 7 — nothing secret is ever printed", () => {
  for (const { name, code } of sourceFiles) {
    it(`${name} never logs a credential-shaped value`, () => {
      for (const rawLine of code.split("\n")) {
        if (!rawLine.includes("console.")) {
          continue;
        }

        const line = stripStringLiterals(rawLine);

        for (const forbidden of [
          "password",
          "publishableKey",
          "accessToken",
          "stdout",
          "stderr",
          "token",
        ]) {
          assert.ok(
            !line.includes(forbidden),
            `${name} logs ${forbidden}: ${line.trim()}`,
          );
        }
      }
    });
  }

  it("prints only the repository-relative credential path", () => {
    const reset = sourceFiles.find((file) => file.name === "demo-reset.mjs");

    assert.ok(reset.code.includes("credentialsPath"));

    // The generated password is never even a name in this module, let alone a
    // logged one. Prose mentioning the word is stripped first.
    assert.ok(!stripStringLiterals(reset.code).includes("password"));
  });
});

describe("decision 9 — no health value is written down", () => {
  // A committed `rpe: 5, overall_feeling: 3` would be an exact health value
  // living permanently in the repository, which acceptance criterion 8 forbids
  // however synthetic it is. The consent verification generates its values at
  // run time instead; what is committed is the schema's domain, not a reading.
  const healthAssignments = [
    /\brpe\s*:\s*-?\d/,
    /\boverallFeeling\s*:\s*-?\d/,
    /\brpe\s*=\s*-?\d/,
    /\boverall_feeling\s*=\s*-?\d/,
  ];

  for (const { name, code } of sourceFiles) {
    it(`${name} assigns no literal health value`, () => {
      for (const pattern of healthAssignments) {
        assert.ok(
          !pattern.test(code),
          `${name} must not hard-code a health value (${pattern})`,
        );
      }
    });
  }

  it("the consent verification generates its check-in at run time", () => {
    const consent = sourceFiles.find(
      (file) => file.name === "demo-verify-consent.mjs",
    );

    assert.ok(consent.code.includes("randomInt"));
    assert.ok(consent.code.includes("synthesizeCheckIn"));
  });
});

describe("the destructive commands hold the interprocess lock", () => {
  // Two destructive commands driving the same local stack at once produce a
  // database built by one run and a credential file written by the other.
  for (const name of [
    "reset.mjs",
    "demo-stop.mjs",
    "demo-verify-consent.mjs",
  ]) {
    it(`${name} runs under withDemoLock`, () => {
      const file = sourceFiles.find((candidate) => candidate.name === name);

      assert.ok(file, `expected ${name} to exist`);
      assert.ok(
        file.code.includes("withDemoLock"),
        `${name} must serialize itself against other destructive commands`,
      );
    });
  }

  it("the lock file lives in the ignored local demo directory", () => {
    const paths = sourceFiles.find((file) => file.name === "paths.mjs");

    assert.ok(paths.code.includes('LOCAL_DEMO_DIR, "demo.lock"'));
    assert.ok(paths.code.includes('LOCAL_DEMO_DIR, "demo.lock.break"'));
  });

  // Age is not evidence of death. A lock broken on a timer is a lock taken away
  // from a slow but perfectly healthy `supabase start`.
  it("the lock never expires a holder on age", () => {
    const lock = sourceFiles.find((file) => file.name === "lock.mjs");

    for (const pattern of [/STALE_LOCK_MS/, /Date\.parse/, /\bnow\b\s*-/]) {
      assert.ok(
        !pattern.test(lock.code),
        `lock.mjs must not decide staleness from a timestamp (${pattern})`,
      );
    }
  });

  // The lock file is ordinary writable state on disk, so everything read back
  // out of it is untrusted.
  it("the lock echoes only an allowlisted label", () => {
    const lock = sourceFiles.find((file) => file.name === "lock.mjs");

    assert.ok(lock.code.includes("DESTRUCTIVE_LOCK_LABELS.includes"));
    assert.ok(!/\$\{\s*record\.label\s*\}/.test(lock.code));
    assert.ok(!/\$\{\s*record\.host\s*\}/.test(lock.code));
    assert.ok(!/\$\{\s*rawLabel\s*\}/.test(lock.code));
  });
});

describe("the restart path never prints a credential block", () => {
  // `supabase start` ends by printing a database URL, a JWT secret, and a
  // service-role key. The command the Product Owner is told to run must be one
  // that suppresses that, which is why `demo:start` exists and why nothing here
  // points at `db:start`.
  it("demo:start runs the suppressed start, not an inherited-stdio one", () => {
    const start = sourceFiles.find((file) => file.name === "demo-start.mjs");

    assert.ok(start, "expected demo-start.mjs to exist");
    assert.ok(start.code.includes("startLocalStack"));
    assert.ok(!start.code.includes("runInheritedStdio"));
  });

  it("no module tells the Product Owner to run db:start or db:status", () => {
    for (const { name, code } of sourceFiles) {
      for (const script of ["db:start", "db:status"]) {
        assert.ok(
          !code.includes(script),
          `${name} must point at demo:start, whose output is suppressed`,
        );
      }
    }
  });

  // A failure is the moment someone is most likely to paste a terminal into a
  // chat, and the raw CLI output at that moment is the most credential-bearing
  // thing on their screen. No message may send them there.
  it("no message tells anyone to re-run the underlying CLI", () => {
    const invitations = [
      /re-?run the (underlying|request|command)/i,
      /run the (supabase )?cli/i,
      /yourself if you need/i,
      /supabase (start|status) (yourself|by hand)/i,
    ];

    for (const { name, code } of sourceFiles) {
      for (const rawLine of code.split("\n")) {
        if (!rawLine.includes("`") && !rawLine.includes('"')) {
          continue;
        }

        for (const invitation of invitations) {
          assert.ok(
            !invitation.test(rawLine),
            `${name} invites a raw CLI re-run: ${rawLine.trim().slice(0, 60)}`,
          );
        }
      }
    }
  });
});

describe("decision 6 — real Auth signup only", () => {
  for (const { name, code } of sourceFiles) {
    it(`${name} uses no admin or bypass path`, () => {
      for (const fragment of [
        "auth/v1/admin",
        "admin/users",
        "serviceRole",
        "service_role_key",
        "insert into auth",
      ]) {
        assert.ok(!code.includes(fragment), `${name} must not use ${fragment}`);
      }
    });
  }

  it("signs up through the public signup endpoint", () => {
    const api = sourceFiles.find((file) => file.name === "api.mjs");

    assert.ok(api.code.includes("/auth/v1/signup"));
  });
});

describe("decision 10 — no merge, push, deploy, or worktree operation", () => {
  for (const { name, code } of sourceFiles) {
    it(`${name} runs no git or deployment command`, () => {
      for (const fragment of ["git ", "eas ", "worktree", '"merge"']) {
        assert.ok(
          !code.includes(fragment),
          `${name} must not contain ${fragment}`,
        );
      }
    });
  }
});

describe("the fixture", () => {
  const fixture = readFileSync(
    join(here, "..", "..", "supabase", "fixtures", "local-demo.sql"),
    "utf8",
  );

  const statements = fixture
    .split(/\r?\n/)
    .filter((line) => !line.trim().startsWith("--"))
    .join("\n");

  // Decision 6: the fixture must not create or authenticate a user.
  it("writes nothing into the auth schema", () => {
    assert.ok(!/insert\s+into\s+auth\./i.test(statements));
    assert.ok(!/update\s+auth\./i.test(statements));
    assert.ok(!/delete\s+from\s+auth\./i.test(statements));
    assert.ok(!/encrypted_password/i.test(statements));
    assert.ok(!/crypt\s*\(/i.test(statements));
  });

  it("reads auth.users only to look ids up by email", () => {
    assert.ok(/from\s+auth\.users/i.test(statements));
  });

  // Decision 9.
  it("seeds no consent and no health value", () => {
    assert.ok(!/insert\s+into\s+public\.sharing_grants/i.test(statements));
    assert.ok(!/insert\s+into\s+public\.daily_check_ins/i.test(statements));

    for (const column of ["rpe", "overall_feeling", "pain_status"]) {
      assert.ok(
        !statements.includes(column),
        `the fixture must not set ${column}`,
      );
    }
  });

  it("clears consent and health rows so the baseline is its own guarantee", () => {
    assert.ok(/delete\s+from\s+public\.sharing_grants/i.test(statements));
    assert.ok(/delete\s+from\s+public\.daily_check_ins/i.test(statements));
  });

  // Decision 8.
  it("creates exactly one team and two memberships", () => {
    assert.equal(
      (statements.match(/insert\s+into\s+public\.teams/gi) ?? []).length,
      1,
    );
    assert.equal(
      (statements.match(/insert\s+into\s+public\.team_memberships/gi) ?? [])
        .length,
      2,
    );
  });

  it("uses only example.test addresses", () => {
    const emails = statements.match(/'[^']*@[^']*'/g) ?? [];

    assert.equal(emails.length, 2);

    for (const email of emails) {
      assert.ok(email.endsWith("@example.test'"));
    }
  });

  // `supabase db query --file` sends the file as a single prepared statement,
  // so an explicit `begin; ... commit;` would fail outright. One DO statement is
  // atomic in its own right, which is the guarantee that matters: a raised
  // exception rolls back every write in the fixture.
  it("is exactly one atomic statement", () => {
    const body = statements.trim();

    // Starts with the only top-level statement and ends with its terminator, so
    // nothing can precede or follow the DO block. Inner statements terminate
    // inside the dollar-quoted body and are not top-level.
    assert.ok(body.startsWith("do $$"));
    assert.ok(body.endsWith("$$;"));
    assert.equal((body.match(/\$\$/g) ?? []).length, 2);
    assert.ok(!/^\s*begin;/m.test(statements));
    assert.ok(!/^\s*commit;/m.test(statements));
  });
});
