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
