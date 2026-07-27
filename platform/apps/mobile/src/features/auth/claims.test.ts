import { describe, expect, it } from "vitest";

import { readVerifiedIdentity, verifiedIdentityMatches } from "./claims";

const USER_ID = "00000000-0000-4000-9000-000000000001";
const NOW = 1_760_000_000_000;
const NOW_SECONDS = Math.floor(NOW / 1000);

function claimsResult(overrides: Record<string, unknown> = {}) {
  return {
    data: {
      claims: {
        iss: "http://127.0.0.1:54321/auth/v1",
        sub: USER_ID,
        aud: "authenticated",
        exp: NOW_SECONDS + 3600,
        iat: NOW_SECONDS - 60,
        role: "authenticated",
        aal: "aal1",
        session_id: "00000000-0000-4000-9000-0000000000f1",
        ...overrides,
      },
      header: { alg: "ES256", kid: "synthetic-kid", typ: "JWT" },
      signature: new Uint8Array([1, 2, 3]),
    },
    error: null,
  };
}

describe("readVerifiedIdentity", () => {
  it("returns the identity from verified claims", () => {
    expect(readVerifiedIdentity(claimsResult(), { now: NOW })).toEqual({
      userId: USER_ID,
    });
  });

  it("takes the identity from sub, not from any other field", () => {
    const result = readVerifiedIdentity(
      claimsResult({ sub: "verified-subject" }),
      { now: NOW },
    );

    expect(result).toEqual({ userId: "verified-subject" });
  });

  it("returns only the user id", () => {
    const identity = readVerifiedIdentity(claimsResult(), { now: NOW });

    // No token, session id, email, or raw claim escapes this boundary.
    expect(Object.keys(identity ?? {})).toEqual(["userId"]);
  });

  describe("fails closed", () => {
    it("when verification reported an error", () => {
      const result = { ...claimsResult(), error: { code: "bad_jwt" } };

      expect(readVerifiedIdentity(result, { now: NOW })).toBeNull();
    });

    it("when verification reported an error and no data", () => {
      expect(
        readVerifiedIdentity(
          { data: null, error: { code: "bad_jwt" } },
          { now: NOW },
        ),
      ).toBeNull();
    });

    it("when there is no data", () => {
      expect(
        readVerifiedIdentity({ data: null, error: null }, { now: NOW }),
      ).toBeNull();
    });

    it("when claims are missing", () => {
      expect(
        readVerifiedIdentity({ data: {}, error: null }, { now: NOW }),
      ).toBeNull();
    });

    it("when claims are null", () => {
      expect(
        readVerifiedIdentity(
          { data: { claims: null }, error: null },
          {
            now: NOW,
          },
        ),
      ).toBeNull();
    });

    it("when sub is missing", () => {
      const result = claimsResult();

      delete (result.data.claims as Record<string, unknown>).sub;

      expect(readVerifiedIdentity(result, { now: NOW })).toBeNull();
    });

    it("when sub is blank", () => {
      expect(
        readVerifiedIdentity(claimsResult({ sub: "   " }), { now: NOW }),
      ).toBeNull();
    });

    it("when sub is not a string", () => {
      expect(
        readVerifiedIdentity(claimsResult({ sub: 12345 }), { now: NOW }),
      ).toBeNull();
    });

    it("when the token has expired", () => {
      expect(
        readVerifiedIdentity(claimsResult({ exp: NOW_SECONDS - 1 }), {
          now: NOW,
        }),
      ).toBeNull();
    });

    it("when the token expires exactly now", () => {
      expect(
        readVerifiedIdentity(claimsResult({ exp: NOW_SECONDS }), { now: NOW }),
      ).toBeNull();
    });

    it("when exp is not a finite number", () => {
      expect(
        readVerifiedIdentity(claimsResult({ exp: "soon" }), { now: NOW }),
      ).toBeNull();
      expect(
        readVerifiedIdentity(claimsResult({ exp: Number.NaN }), { now: NOW }),
      ).toBeNull();
    });

    it("when the role is not authenticated", () => {
      expect(
        readVerifiedIdentity(claimsResult({ role: "anon" }), { now: NOW }),
      ).toBeNull();
      expect(
        readVerifiedIdentity(claimsResult({ role: "service_role" }), {
          now: NOW,
        }),
      ).toBeNull();
    });

    it("when the token is anonymous", () => {
      expect(
        readVerifiedIdentity(claimsResult({ is_anonymous: true }), {
          now: NOW,
        }),
      ).toBeNull();
    });

    it("for a non-object result", () => {
      for (const input of [null, undefined, "a string", 42, true, []]) {
        expect(readVerifiedIdentity(input, { now: NOW })).toBeNull();
      }
    });

    it("for an empty object", () => {
      expect(readVerifiedIdentity({}, { now: NOW })).toBeNull();
    });
  });

  it("accepts a token that is still valid one second from expiry", () => {
    expect(
      readVerifiedIdentity(claimsResult({ exp: NOW_SECONDS + 1 }), {
        now: NOW,
      }),
    ).toEqual({ userId: USER_ID });
  });

  it("accepts claims with no exp, since getClaims already enforces expiry", () => {
    const result = claimsResult();

    delete (result.data.claims as Record<string, unknown>).exp;

    expect(readVerifiedIdentity(result, { now: NOW })).toEqual({
      userId: USER_ID,
    });
  });
});

describe("verifiedIdentityMatches", () => {
  it("accepts a matching stored id", () => {
    expect(verifiedIdentityMatches(USER_ID, { userId: USER_ID })).toBe(true);
  });

  it("rejects a mismatched stored id", () => {
    expect(verifiedIdentityMatches("someone-else", { userId: USER_ID })).toBe(
      false,
    );
  });
});
