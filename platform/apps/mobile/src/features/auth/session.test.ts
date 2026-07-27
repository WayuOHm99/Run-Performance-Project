import { describe, expect, it } from "vitest";

import { identityChanged, readAuthenticatedIdentity } from "./session";

const VALID_SESSION = {
  access_token: "synthetic-access-token",
  refresh_token: "synthetic-refresh-token",
  user: { id: "00000000-0000-4000-9000-000000000001" },
};

describe("readAuthenticatedIdentity", () => {
  it("reads the user id from a well-formed session", () => {
    expect(readAuthenticatedIdentity(VALID_SESSION)).toEqual({
      userId: "00000000-0000-4000-9000-000000000001",
    });
  });

  it("never returns the access or refresh token", () => {
    const identity = readAuthenticatedIdentity(VALID_SESSION);

    expect(identity).not.toBeNull();
    expect(Object.keys(identity ?? {})).toEqual(["userId"]);
  });

  it("fails closed for null", () => {
    expect(readAuthenticatedIdentity(null)).toBeNull();
  });

  it("fails closed for undefined", () => {
    expect(readAuthenticatedIdentity(undefined)).toBeNull();
  });

  it("fails closed for a primitive", () => {
    expect(readAuthenticatedIdentity("a string")).toBeNull();
    expect(readAuthenticatedIdentity(42)).toBeNull();
    expect(readAuthenticatedIdentity(true)).toBeNull();
  });

  it("fails closed for an empty object", () => {
    expect(readAuthenticatedIdentity({})).toBeNull();
  });

  it("fails closed when the access token is missing", () => {
    expect(readAuthenticatedIdentity({ user: { id: "user-1" } })).toBeNull();
  });

  it("fails closed when the access token is blank", () => {
    expect(
      readAuthenticatedIdentity({ ...VALID_SESSION, access_token: "   " }),
    ).toBeNull();
  });

  it("fails closed when the user object is missing", () => {
    expect(
      readAuthenticatedIdentity({ access_token: "synthetic-access-token" }),
    ).toBeNull();
  });

  it("fails closed when the user object is null", () => {
    expect(
      readAuthenticatedIdentity({ ...VALID_SESSION, user: null }),
    ).toBeNull();
  });

  it("fails closed when the user id is missing", () => {
    expect(
      readAuthenticatedIdentity({ ...VALID_SESSION, user: {} }),
    ).toBeNull();
  });

  it("fails closed when the user id is blank", () => {
    expect(
      readAuthenticatedIdentity({ ...VALID_SESSION, user: { id: "  " } }),
    ).toBeNull();
  });

  it("fails closed when the user id is not a string", () => {
    expect(
      readAuthenticatedIdentity({ ...VALID_SESSION, user: { id: 12345 } }),
    ).toBeNull();
  });

  it("fails closed for an array", () => {
    expect(readAuthenticatedIdentity([VALID_SESSION])).toBeNull();
  });

  it("fails closed for a truncated stored blob", () => {
    // What a half-written AsyncStorage entry actually looks like.
    expect(
      readAuthenticatedIdentity({ access_token: "synthetic-acce" }),
    ).toBeNull();
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
