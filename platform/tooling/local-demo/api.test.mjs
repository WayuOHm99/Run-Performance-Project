// What the API layer does when the local stack answers badly.
//
// The happy paths are exercised for real by `demo:reset` and
// `demo:verify:consent`. These tests cover the paths that only appear when
// something is wrong, which is exactly when a leak would happen and exactly when
// nobody is watching for one: a truncated body, an HTML error page from a
// half-started PostgREST, a GoTrue error document quoting a database error.
//
// Every assertion is about what the failure output does **not** contain.

import assert from "node:assert/strict";
import { randomInt } from "node:crypto";
import { afterEach, describe, it } from "node:test";

import {
  callSharingRpc,
  countRows,
  DemoApiError,
  insertCheckIn,
  signIn,
  signUp,
} from "./api.mjs";
import { LOCAL_SUPABASE_URL } from "./endpoint.mjs";

// Synthetic stand-ins, assembled from fragments so no line in this file looks
// like a real credential to a secret scanner.
const publishableKey = [
  "sb",
  "publishable",
  "synthetic-local-key-for-tests",
].join("_");
const accessToken = ["ey", "Jsynthetic-access-token-for-tests"].join("");

// A body of the shape that actually shows up on a failure: a database error
// string, a hint naming a column, and a session fragment.
//
// The failing row's contents are deliberately *not* reproduced. A
// realistic-looking check-in row would be an exact health value living in a
// committed file, which is the thing this tooling exists to avoid. What is being
// tested is whether the body reaches the message at all, and a redacted
// stand-in proves that just as well.
const MALFORMED_BODY = `{"code":"23514","message":"new row for relation \\"daily_check_ins\\" violates check constraint","detail":"Failing row contains synthetic-redacted-row","hint":"synthetic-hint-naming-a-column","access_token":"${accessToken}",`;

const FORBIDDEN_FRAGMENTS = [
  accessToken,
  "23514",
  "violates check constraint",
  "synthetic-redacted-row",
  "synthetic-hint-naming-a-column",
  "access_token",
];

// Values inside the schema's declared domain, chosen at run time so no reading
// is committed. See `demo-verify-consent.mjs` for the same rule.
function syntheticCheckIn() {
  return {
    rpe: randomInt(0, 11),
    overallFeeling: randomInt(1, 6),
    painStatus: ["none", "present"][randomInt(0, 2)],
  };
}

const base = { apiUrl: LOCAL_SUPABASE_URL, publishableKey };
const session = Object.freeze({ accessToken, userId: "synthetic-user-id" });

const realFetch = globalThis.fetch;

// The module calls the global `fetch`, so the global is what the tests replace.
// Restored after every test, including a failing one.
function stubFetch(response) {
  globalThis.fetch = async () => response;
}

function textResponse({ ok = true, status = 200, body = "" }) {
  return {
    ok,
    status,
    async text() {
      return body;
    },
    async arrayBuffer() {
      return new ArrayBuffer(0);
    },
    async json() {
      // Present so a regression that reverts to `response.json()` is caught by
      // the assertions rather than by a TypeError that looks like a test bug.
      return JSON.parse(body);
    },
  };
}

afterEach(() => {
  globalThis.fetch = realFetch;
});

// Serialized so nothing that could carry the body can hide in a stack frame or a
// cause chain.
function serializeError(error) {
  return [
    error?.message ?? "",
    error?.stack ?? "",
    error?.cause?.message ?? "",
    JSON.stringify(error, Object.getOwnPropertyNames(error ?? {})),
  ].join("\n");
}

function assertLeaksNothing(error) {
  const serialized = serializeError(error);

  for (const fragment of FORBIDDEN_FRAGMENTS) {
    assert.ok(
      !serialized.includes(fragment),
      `the failure output leaked a response-body fragment: ${fragment.slice(0, 16)}`,
    );
  }
}

describe("a malformed response body", () => {
  // `JSON.parse` quotes its input in its own error message. `response.json()`
  // surfaces that verbatim, which is the leak this rejects.
  it("does not reach the sign-in failure message or stack", async () => {
    stubFetch(textResponse({ body: MALFORMED_BODY }));

    await assert.rejects(
      signIn({ ...base, email: "athlete-a@example.test", password: "pw" }),
      (error) => {
        assert.ok(error instanceof DemoApiError);
        assertLeaksNothing(error);

        return true;
      },
    );
  });

  it("does not reach the read failure message or stack", async () => {
    stubFetch(textResponse({ body: MALFORMED_BODY }));

    await assert.rejects(
      countRows({ ...base, session, table: "daily_check_ins" }),
      (error) => {
        assert.ok(error instanceof DemoApiError);
        assertLeaksNothing(error);

        return true;
      },
    );
  });

  it("is reported as malformed rather than as an unusable session", async () => {
    stubFetch(textResponse({ body: "<html>502 Bad Gateway</html>" }));

    await assert.rejects(
      signIn({ ...base, email: "athlete-a@example.test", password: "pw" }),
      (error) => {
        assert.ok(error.message.includes("malformed"));
        assert.ok(!error.message.includes("502 Bad Gateway"));
        assert.ok(!error.message.includes("html"));

        return true;
      },
    );
  });

  it("names the table it was reading, and nothing from the body", async () => {
    stubFetch(textResponse({ body: MALFORMED_BODY }));

    await assert.rejects(
      countRows({ ...base, session, table: "team_memberships" }),
      (error) => {
        assert.ok(error.message.includes("team_memberships"));
        assertLeaksNothing(error);

        return true;
      },
    );
  });

  it("leaks nothing when the body cannot be read at all", async () => {
    stubFetch({
      ok: true,
      status: 200,
      async text() {
        throw new Error(MALFORMED_BODY);
      },
      async arrayBuffer() {
        throw new Error(MALFORMED_BODY);
      },
    });

    await assert.rejects(
      signIn({ ...base, email: "athlete-a@example.test", password: "pw" }),
      (error) => {
        assert.ok(error instanceof DemoApiError);
        assertLeaksNothing(error);

        return true;
      },
    );
  });
});

describe("a well-formed body of the wrong shape", () => {
  it("rejects a sign-in with no access token without echoing the payload", async () => {
    stubFetch(
      textResponse({
        body: JSON.stringify({
          error: "invalid_grant",
          error_description: "synthetic-hint-naming-a-column",
          access_token: null,
        }),
      }),
    );

    await assert.rejects(
      signIn({ ...base, email: "athlete-a@example.test", password: "pw" }),
      (error) => {
        assert.ok(error instanceof DemoApiError);
        assertLeaksNothing(error);

        return true;
      },
    );
  });

  it("rejects a read that did not return an array", async () => {
    stubFetch(
      textResponse({
        body: JSON.stringify({ message: "synthetic-hint-naming-a-column" }),
      }),
    );

    await assert.rejects(
      countRows({ ...base, session, table: "daily_check_ins" }),
      (error) => {
        assert.ok(error.message.includes("unexpected shape"));
        assertLeaksNothing(error);

        return true;
      },
    );
  });

  // A successful read returns a count, never the rows themselves.
  it("returns only a row count on success", async () => {
    stubFetch(
      textResponse({
        body: JSON.stringify([{ id: "a" }, { id: "b" }, { id: "c" }]),
      }),
    );

    const count = await countRows({
      ...base,
      session,
      table: "daily_check_ins",
    });

    assert.equal(count, 3);
    assert.equal(typeof count, "number");
  });
});

describe("a non-ok response", () => {
  const cases = [
    [
      "signup",
      () =>
        signUp({ ...base, email: "athlete-a@example.test", password: "pw" }),
    ],
    [
      "sign-in",
      () =>
        signIn({ ...base, email: "athlete-a@example.test", password: "pw" }),
    ],
    ["read", () => countRows({ ...base, session, table: "daily_check_ins" })],
    [
      "insert",
      () =>
        insertCheckIn({
          ...base,
          session,
          checkInDate: "2026-08-01",
          // Generated, not written down — the same rule the consent
          // verification follows. The values are irrelevant to this assertion;
          // the request never leaves the stub.
          ...syntheticCheckIn(),
        }),
    ],
    [
      "sharing rpc",
      () =>
        callSharingRpc({
          ...base,
          session,
          fn: "grant_team_data_sharing",
          teamId: "00000000-0000-4000-8000-000000000017",
          dataCategory: "check_in",
        }),
    ],
  ];

  for (const [what, call] of cases) {
    it(`reports only the status for a failing ${what}`, async () => {
      stubFetch(textResponse({ ok: false, status: 400, body: MALFORMED_BODY }));

      await assert.rejects(call(), (error) => {
        assert.ok(error instanceof DemoApiError);
        assert.equal(error.status, 400);
        assert.ok(error.message.includes("400"));
        assertLeaksNothing(error);

        return true;
      });
    });
  }
});

describe("the endpoint assertion runs before anything is sent", () => {
  it("refuses a non-canonical URL without calling fetch", async () => {
    let called = false;
    globalThis.fetch = async () => {
      called = true;

      return textResponse({ body: "[]" });
    };

    await assert.rejects(
      signIn({
        apiUrl: "https://synthetic-project.example",
        publishableKey,
        email: "athlete-a@example.test",
        password: "pw",
      }),
    );

    assert.equal(called, false);
  });
});
