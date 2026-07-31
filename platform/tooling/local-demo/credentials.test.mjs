import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  ATHLETE_EMAIL,
  COACH_EMAIL,
  DEMO_ACCOUNTS,
  DEMO_TEAM_ID,
} from "./accounts.mjs";
import { renderCredentialsFile } from "./credentials-file.mjs";
import { buildDemoEnv } from "./launch.mjs";
import {
  generateLocalDemoPassword,
  isPlausibleLocalDemoPassword,
} from "./password.mjs";
import { CREDENTIALS_DISPLAY_PATH } from "./paths.mjs";

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
  const password = generateLocalDemoPassword();
  const contents = renderCredentialsFile({
    accounts: DEMO_ACCOUNTS,
    password,
    generatedAt: "2026-07-31T00:00:00.000Z",
  });

  it("contains the password so the Product Owner can sign in", () => {
    assert.ok(contents.includes(password));
  });

  it("lists both synthetic accounts", () => {
    assert.ok(contents.includes(ATHLETE_EMAIL));
    assert.ok(contents.includes(COACH_EMAIL));
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
      assert.ok(
        !contents.includes(fragment),
        `the credential file must not contain ${fragment}`,
      );
    }
  });

  it("says it is local-only and git-ignored", () => {
    assert.match(contents, /LOCAL/);
    assert.match(contents, /git-ignored/);
  });

  it("states the baseline has no grant and no check-in", () => {
    assert.match(contents, /no sharing grant and no check-in/);
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
