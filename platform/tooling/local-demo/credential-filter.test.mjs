import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  DemoCredentialError,
  extractLocalCredentials,
} from "./credential-filter.mjs";
import { DemoEndpointError } from "./endpoint.mjs";

// Synthetic stand-ins, assembled from fragments so no line in this file looks
// like a real credential to a secret scanner.
const publishableKey = [
  "sb",
  "publishable",
  "synthetic-local-key-for-tests",
].join("_");
const secretKey = ["sb", "secret", "synthetic-local-secret-for-tests"].join(
  "_",
);
const legacyJwt = ["ey", "Jsynthetic-legacy-jwt-for-tests-only"].join("");

// A realistic `supabase status -o json` document: every secret-bearing field the
// pinned CLI actually emits is present, so the filtering test is meaningful.
function statusDocument(overrides = {}) {
  return JSON.stringify({
    API_URL: "http://127.0.0.1:54321",
    ANON_KEY: legacyJwt,
    PUBLISHABLE_KEY: publishableKey,
    SECRET_KEY: secretKey,
    SERVICE_ROLE_KEY: legacyJwt,
    JWT_SECRET: "synthetic-jwt-secret-for-tests",
    DB_URL: "postgresql://postgres:synthetic-password@127.0.0.1:54322/postgres",
    S3_PROTOCOL_ACCESS_KEY_ID: "synthetic-s3-id",
    S3_PROTOCOL_ACCESS_KEY_SECRET: "synthetic-s3-secret",
    STUDIO_URL: "http://127.0.0.1:54323",
    ...overrides,
  });
}

// Everything in the document that must never cross the boundary.
const FORBIDDEN_VALUES = [
  secretKey,
  legacyJwt,
  "synthetic-jwt-secret-for-tests",
  "postgresql://postgres:synthetic-password@127.0.0.1:54322/postgres",
  "synthetic-password",
  "synthetic-s3-id",
  "synthetic-s3-secret",
];

describe("extractLocalCredentials", () => {
  it("returns exactly two fields and nothing else", () => {
    const result = extractLocalCredentials(statusDocument());

    assert.deepEqual(Object.keys(result).sort(), ["apiUrl", "publishableKey"]);
    assert.equal(result.apiUrl, "http://127.0.0.1:54321");
    assert.equal(result.publishableKey, publishableKey);
  });

  // The core of decision 5.
  it("lets no other credential in the document cross the boundary", () => {
    const serialized = JSON.stringify(
      extractLocalCredentials(statusDocument()),
    );

    for (const forbidden of FORBIDDEN_VALUES) {
      assert.ok(
        !serialized.includes(forbidden),
        `a forbidden value crossed the credential filter: ${forbidden.slice(0, 12)}...`,
      );
    }
  });

  it("returns a frozen object, so a caller cannot decorate it", () => {
    const result = extractLocalCredentials(statusDocument());

    assert.ok(Object.isFrozen(result));
  });

  it("rejects a non-canonical API URL", () => {
    assert.throws(
      () =>
        extractLocalCredentials(
          statusDocument({
            API_URL: "https://altlphxckxsudnuwhqfw.supabase.co",
          }),
        ),
      DemoEndpointError,
    );
  });

  it("rejects a missing publishable key rather than falling back to ANON_KEY", () => {
    const document = statusDocument();
    const withoutPublishable = JSON.parse(document);
    delete withoutPublishable.PUBLISHABLE_KEY;

    assert.throws(
      () => extractLocalCredentials(JSON.stringify(withoutPublishable)),
      DemoCredentialError,
    );
  });

  it("rejects a server-capable value in the publishable field", () => {
    for (const value of [
      secretKey,
      legacyJwt,
      "postgresql://postgres:pw@127.0.0.1:54322/postgres",
      "postgres://postgres:pw@127.0.0.1:54322/postgres",
      "service_role_synthetic",
    ]) {
      assert.throws(
        () =>
          extractLocalCredentials(statusDocument({ PUBLISHABLE_KEY: value })),
        DemoCredentialError,
      );
    }
  });

  it("rejects a malformed publishable key", () => {
    for (const value of [
      "",
      "not-a-key",
      "sb_publishable_",
      "sb_publishable_short",
    ]) {
      assert.throws(
        () =>
          extractLocalCredentials(statusDocument({ PUBLISHABLE_KEY: value })),
        DemoCredentialError,
      );
    }
  });

  it("rejects a document that is not an object", () => {
    for (const text of ["null", '"a string"', "42", "[]"]) {
      assert.throws(() => extractLocalCredentials(text), DemoCredentialError);
    }
  });

  // The most likely accidental leak: JSON.parse's own error quotes the input.
  it("never quotes the status document when the parse fails", () => {
    const malformed = `{ "SERVICE_ROLE_KEY": "${legacyJwt}", `;

    try {
      extractLocalCredentials(malformed);
      assert.fail("expected a rejection");
    } catch (error) {
      assert.ok(error instanceof DemoCredentialError);
      assert.ok(!error.message.includes(legacyJwt));
      assert.ok(!error.message.includes("SERVICE_ROLE_KEY"));
    }
  });

  it("never echoes a rejected credential value", () => {
    for (const value of [secretKey, legacyJwt, "not-a-key"]) {
      try {
        extractLocalCredentials(statusDocument({ PUBLISHABLE_KEY: value }));
        assert.fail("expected a rejection");
      } catch (error) {
        assert.ok(!error.message.includes(value));
      }
    }
  });

  it("never echoes any forbidden value on any failure path", () => {
    const inputs = [
      statusDocument({ API_URL: "https://example.supabase.co" }),
      statusDocument({ PUBLISHABLE_KEY: secretKey }),
      statusDocument({ PUBLISHABLE_KEY: "bad" }),
      "{ not json",
      "null",
    ];

    for (const input of inputs) {
      try {
        extractLocalCredentials(input);
      } catch (error) {
        for (const forbidden of FORBIDDEN_VALUES) {
          assert.ok(
            !error.message.includes(forbidden),
            "an error message carried a forbidden value",
          );
        }
      }
    }
  });
});
