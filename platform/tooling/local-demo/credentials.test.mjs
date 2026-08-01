// **Assertions here never pass a rendered credential file to an assertion that
// prints its input.** `assert.match(contents, /…/)` reports the whole input
// string on failure, and that input is a file containing a password — so a
// single failing test would print the credential this task exists to keep out of
// terminal scrollback. Every check below is `assert.ok(...)` with a fixed
// message, which reports the message and nothing else.
//
// For the same reason the rendering tests use a fixed synthetic stand-in rather
// than a freshly generated password: even a value that opens nothing real should
// not be printable by a failing assertion.

import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { mkdtemp, readdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, it } from "node:test";

import {
  ATHLETE_EMAIL,
  COACH_EMAIL,
  DEMO_ACCOUNTS,
  DEMO_TEAM_ID,
} from "./accounts.mjs";
import {
  discardCredentialsFile,
  renderCredentialsFile,
  writeCredentialsFile,
} from "./credentials-file.mjs";
import { buildDemoEnv } from "./launch.mjs";
import {
  generateLocalDemoPassword,
  isPlausibleLocalDemoPassword,
} from "./password.mjs";
import { CREDENTIALS_DISPLAY_PATH } from "./paths.mjs";

// Assembled from fragments so no line in this file looks like a credential to a
// secret scanner, and fixed so no assertion can print a real generated one.
const SYNTHETIC_PASSWORD = ["synthetic", "local", "demo", "secret"].join("-");

// `assert.ok` reports only the message it is given. `assert.match` and
// `assert.equal` would report the input, which for these tests is the credential
// file itself.
function assertContains(haystack, needle, what) {
  assert.ok(haystack.includes(needle), `expected the ${what}`);
}

function assertOmits(haystack, needle, what) {
  assert.ok(!haystack.includes(needle), `the ${what} must not appear`);
}

describe("generateLocalDemoPassword", () => {
  it("produces a 32-character URL-safe password", () => {
    assert.ok(isPlausibleLocalDemoPassword(generateLocalDemoPassword()));
  });

  it("is different every time", () => {
    const seen = new Set();

    for (let index = 0; index < 200; index += 1) {
      seen.add(generateLocalDemoPassword());
    }

    assert.equal(seen.size, 200);
  });

  it("comfortably exceeds the local minimum password length", () => {
    assert.ok(generateLocalDemoPassword().length > 6);
  });
});

describe("DEMO_ACCOUNTS", () => {
  // Decision 8.
  it("is exactly two example.test accounts, one athlete and one coach", () => {
    assert.equal(DEMO_ACCOUNTS.length, 2);
    assert.deepEqual(DEMO_ACCOUNTS.map((account) => account.role).sort(), [
      "athlete",
      "coach",
    ]);

    for (const account of DEMO_ACCOUNTS) {
      assert.ok(account.email.endsWith("@example.test"));
    }
  });

  it("uses the RFC 6761 reserved test domain, which cannot receive mail", () => {
    for (const email of [ATHLETE_EMAIL, COACH_EMAIL]) {
      assert.match(email, /@example\.test$/);
    }
  });

  it("uses a fixed synthetic team id so a reset is deterministic", () => {
    assert.match(
      DEMO_TEAM_ID,
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    );
  });
});

describe("renderCredentialsFile", () => {
  const contents = renderCredentialsFile({
    accounts: DEMO_ACCOUNTS,
    password: SYNTHETIC_PASSWORD,
    generatedAt: "2026-07-31T00:00:00.000Z",
  });

  it("contains the password so the Product Owner can sign in", () => {
    assertContains(contents, SYNTHETIC_PASSWORD, "password to be written");
  });

  // The generated password reaches the file too, but the assertion reports only
  // whether it did — never the file, and never the value.
  it("writes a generated password without any assertion printing it", () => {
    const generated = generateLocalDemoPassword();
    const rendered = renderCredentialsFile({
      accounts: DEMO_ACCOUNTS,
      password: generated,
      generatedAt: "2026-07-31T00:00:00.000Z",
    });

    assert.ok(
      rendered.includes(generated),
      "expected the generated password to be written",
    );
    assert.ok(
      isPlausibleLocalDemoPassword(generated),
      "expected a well-formed generated password",
    );
  });

  it("lists both synthetic accounts", () => {
    assertContains(contents, ATHLETE_EMAIL, "athlete address");
    assertContains(contents, COACH_EMAIL, "coach address");
  });

  it("carries no publishable key, token, session, or database URL", () => {
    for (const fragment of [
      "sb_publishable_",
      "sb_secret_",
      "eyJ",
      "postgres://",
      "postgresql://",
      "access_token",
      "service_role",
    ]) {
      assertOmits(contents, fragment, `credential fragment ${fragment}`);
    }
  });

  it("says it is local-only and git-ignored", () => {
    assertContains(contents, "LOCAL", "local-only notice");
    assertContains(contents, "git-ignored", "git-ignored notice");
  });

  it("states the baseline has no grant and no check-in", () => {
    assertContains(
      contents,
      "no sharing grant and no check-in",
      "zero-consent baseline notice",
    );
  });
});

// Decision 7, and the staleness problem underneath it: the password in this file
// is only true of the accounts the same reset created.
describe("writeCredentialsFile", () => {
  let directory;
  let file;

  beforeEach(async () => {
    directory = await mkdtemp(join(tmpdir(), "local-demo-credentials-"));
    file = join(directory, "credentials.txt");
  });

  afterEach(async () => {
    await rm(directory, { recursive: true, force: true });
  });

  async function write(password) {
    return writeCredentialsFile({
      accounts: DEMO_ACCOUNTS,
      password,
      directory,
      file,
    });
  }

  it("returns the safe display path, never the file's location or contents", async () => {
    const returned = await write(SYNTHETIC_PASSWORD);

    assert.equal(returned, CREDENTIALS_DISPLAY_PATH);
  });

  it("replaces a previous file completely, leaving no trace of the old password", async () => {
    const previous = ["synthetic", "previous", "demo", "secret"].join("-");

    await write(previous);
    await write(SYNTHETIC_PASSWORD);

    const contents = await readFile(file, "utf8");

    assertContains(contents, SYNTHETIC_PASSWORD, "current password");
    assertOmits(contents, previous, "previous password");
  });

  // A crash between the write and the rename must not leave a file that looks
  // like a credential file.
  it("leaves no temporary file behind", async () => {
    await write(SYNTHETIC_PASSWORD);

    const entries = await readdir(directory);

    assert.deepEqual(entries, ["credentials.txt"]);
  });

  it("replaces a leftover temporary file from an earlier crash", async () => {
    await writeFile(`${file}.${process.pid}.tmp`, "partial", "utf8");

    await write(SYNTHETIC_PASSWORD);

    const entries = await readdir(directory);

    assert.deepEqual(entries, ["credentials.txt"]);
  });

  // Round 2 cleaned only this process's own pid-qualified file. A run killed
  // part-way therefore left a temporary file that nothing would ever remove —
  // not the credential file, so no reset replaced it, and carrying the password
  // that run had generated.
  it("removes a temporary file left by a different process", async () => {
    const otherPid = process.pid + 1;

    await writeFile(`${file}.${otherPid}.tmp`, "partial", "utf8");

    await write(SYNTHETIC_PASSWORD);

    assert.deepEqual(await readdir(directory), ["credentials.txt"]);
  });

  it("leaves files that are not this tooling's temporary files alone", async () => {
    const bystanders = [
      "demo.lock",
      "credentials.txt.tmp",
      "credentials.txt.notapid.tmp",
      "credentials.txt.123.tmp.bak",
      "other.txt.123.tmp",
      "notes.md",
    ];

    for (const name of bystanders) {
      await writeFile(join(directory, name), "synthetic", "utf8");
    }

    await write(SYNTHETIC_PASSWORD);

    const remaining = await readdir(directory);

    for (const name of bystanders) {
      assert.ok(
        remaining.includes(name),
        `cleanup must not remove ${name}, which is not a temporary credential file`,
      );
    }
  });

  // The important one. A truncated file is not merely useless: it is a password
  // that silently does not work, which reads as a broken demo rather than a
  // broken file.
  it("never publishes a partially written file", async () => {
    await write(SYNTHETIC_PASSWORD);

    const contents = await readFile(file, "utf8");
    const complete = renderCredentialsFile({
      accounts: DEMO_ACCOUNTS,
      password: SYNTHETIC_PASSWORD,
      generatedAt: "ignored",
    });

    // Same body, modulo the generated-at line, which is a timestamp.
    assert.equal(
      contents.split("\n").length,
      complete.split("\n").length,
      "expected a complete file",
    );
    assertContains(contents, "Accounts:", "accounts section");
    assertContains(contents, COACH_EMAIL, "coach address");
  });
});

describe("discardCredentialsFile", () => {
  let directory;
  let file;

  beforeEach(async () => {
    directory = await mkdtemp(join(tmpdir(), "local-demo-credentials-"));
    file = join(directory, "credentials.txt");
  });

  afterEach(async () => {
    await rm(directory, { recursive: true, force: true });
  });

  it("removes a stale credential file and every run's temporary file", async () => {
    await writeFile(file, "stale", "utf8");
    await writeFile(`${file}.${process.pid}.tmp`, "partial", "utf8");
    await writeFile(`${file}.${process.pid + 1}.tmp`, "partial", "utf8");
    await writeFile(`${file}.999999.tmp`, "partial", "utf8");

    await discardCredentialsFile({ directory, file });

    assert.equal(existsSync(file), false);
    assert.deepEqual(await readdir(directory), []);
  });

  it("stays inside the ignored directory", async () => {
    const outside = await mkdtemp(join(tmpdir(), "local-demo-outside-"));

    try {
      await writeFile(join(outside, "credentials.txt.123.tmp"), "x", "utf8");
      await writeFile(file, "stale", "utf8");

      await discardCredentialsFile({ directory, file });

      // A file of exactly the temporary shape, one directory away, is untouched.
      assert.deepEqual(await readdir(outside), ["credentials.txt.123.tmp"]);
    } finally {
      await rm(outside, { recursive: true, force: true });
    }
  });

  it("is a no-op when nothing is there", async () => {
    await discardCredentialsFile({ file });

    assert.equal(existsSync(file), false);
  });
});

describe("CREDENTIALS_DISPLAY_PATH", () => {
  // Decision 7: only a safe path is printed, and it is repository-relative so it
  // discloses nothing about the machine.
  it("is repository-relative, not absolute", () => {
    assert.equal(
      CREDENTIALS_DISPLAY_PATH,
      "platform/.local-demo/credentials.txt",
    );
    assert.ok(!CREDENTIALS_DISPLAY_PATH.includes(":"));
    assert.ok(!CREDENTIALS_DISPLAY_PATH.startsWith("/"));
  });
});

describe("buildDemoEnv", () => {
  const publishableKey = [
    "sb",
    "publishable",
    "synthetic-local-key-for-tests",
  ].join("_");

  const env = buildDemoEnv({
    baseEnv: {
      PATH: "/usr/bin",
      EXPO_PUBLIC_SUPABASE_URL: "https://hosted.example",
    },
    surfaceUrl: "http://127.0.0.1:54321",
    publishableKey,
  });

  // Decision 3.
  it("sets EXPO_NO_DOTENV so no dotenv file is ever read", () => {
    assert.equal(env.EXPO_NO_DOTENV, "1");
  });

  it("declares local mode explicitly", () => {
    assert.equal(env.EXPO_PUBLIC_SUPABASE_ENVIRONMENT, "local");
  });

  it("overrides an inherited hosted URL rather than deferring to it", () => {
    assert.equal(env.EXPO_PUBLIC_SUPABASE_URL, "http://127.0.0.1:54321");
  });

  it("passes the validated publishable key through", () => {
    assert.equal(env.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY, publishableKey);
  });

  it("preserves the rest of the parent environment", () => {
    assert.equal(env.PATH, "/usr/bin");
  });

  it("is process-scoped: it returns an object and writes no file", () => {
    assert.equal(typeof env, "object");
  });
});
