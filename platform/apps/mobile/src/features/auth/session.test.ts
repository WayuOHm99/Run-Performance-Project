import { describe, expect, it } from "vitest";

import { identityChanged, readSessionCandidate } from "./session";

const VALID_SESSION = {
  access_token: "synthetic-access-token",
  refresh_token: "synthetic-refresh-token",
  user: { id: "00000000-0000-4000-9000-000000000001" },
};

describe("readSessionCandidate", () => {
  it("reads the unverified user id from a well-formed session", () => {
    expect(readSessionCandidate(VALID_SESSION)).toEqual({
      unverifiedUserId: "00000000-0000-4000-9000-000000000001",
    });
  });

  it("names the value as unverified so it cannot be used as an identity", () => {
    const candidate = readSessionCandidate(VALID_SESSION);

    // The field is deliberately not called userId: a stored session proves
    // nothing about the JWT, so this must not be assignable where a verified
    // AuthenticatedIdentity is expected.
    expect(Object.keys(candidate ?? {})).toEqual(["unverifiedUserId"]);
  });

  it("never returns the access or refresh token", () => {
    const serialized = JSON.stringify(readSessionCandidate(VALID_SESSION));

    expect(serialized).not.toContain("synthetic-access-token");
    expect(serialized).not.toContain("synthetic-refresh-token");
  });

  it("fails closed for null", () => {
    expect(readSessionCandidate(null)).toBeNull();
  });

  it("fails closed for undefined", () => {
    expect(readSessionCandidate(undefined)).toBeNull();
  });

  it("fails closed for a primitive", () => {
    expect(readSessionCandidate("a string")).toBeNull();
    expect(readSessionCandidate(42)).toBeNull();
    expect(readSessionCandidate(true)).toBeNull();
  });

  it("fails closed for an empty object", () => {
    expect(readSessionCandidate({})).toBeNull();
  });

  it("fails closed when the access token is missing", () => {
    expect(readSessionCandidate({ user: { id: "user-1" } })).toBeNull();
  });

  it("fails closed when the access token is blank", () => {
    expect(
      readSessionCandidate({ ...VALID_SESSION, access_token: "   " }),
    ).toBeNull();
  });

  it("fails closed when the user object is missing", () => {
    expect(
      readSessionCandidate({ access_token: "synthetic-access-token" }),
    ).toBeNull();
  });

  it("fails closed when the user object is null", () => {
    expect(readSessionCandidate({ ...VALID_SESSION, user: null })).toBeNull();
  });

  it("fails closed when the user id is missing", () => {
    expect(readSessionCandidate({ ...VALID_SESSION, user: {} })).toBeNull();
  });

  it("fails closed when the user id is blank", () => {
    expect(
      readSessionCandidate({ ...VALID_SESSION, user: { id: "  " } }),
    ).toBeNull();
  });

  it("fails closed when the user id is not a string", () => {
    expect(
      readSessionCandidate({ ...VALID_SESSION, user: { id: 12345 } }),
    ).toBeNull();
  });

  it("fails closed for an array", () => {
    expect(readSessionCandidate([VALID_SESSION])).toBeNull();
  });

  it("fails closed for a truncated stored blob", () => {
    // What a half-written AsyncStorage entry actually looks like.
    expect(readSessionCandidate({ access_token: "synthetic-acce" })).toBeNull();
  });
});

describe("identityChanged", () => {
  const userA = { userId: "user-a" };
  const userB = { userId: "user-b" };

  it("is false when both are signed out", () => {
    expect(identityChanged(null, null)).toBe(false);
  });

  it("is false for the same user", () => {
    expect(identityChanged(userA, { userId: "user-a" })).toBe(false);
  });

  it("is true on sign-in", () => {
    expect(identityChanged(null, userA)).toBe(true);
  });

  it("is true on sign-out", () => {
    expect(identityChanged(userA, null)).toBe(true);
  });

  it("is true when the account switches", () => {
    expect(identityChanged(userA, userB)).toBe(true);
  });
});
