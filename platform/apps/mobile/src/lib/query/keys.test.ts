import { describe, expect, it } from "vitest";

import { authScopedKeys, authScopedUserId, isAuthScopedKey } from "./keys";

const USER_A = "00000000-0000-4000-9000-00000000000a";
const USER_B = "00000000-0000-4000-9000-00000000000b";

describe("authScopedKeys", () => {
  it("includes the user id in every key", () => {
    // Without the user id, a cache entry written for one account could be read
    // by the next account signed in on the same device.
    expect(authScopedKeys.profile(USER_A)).toContain(USER_A);
    expect(authScopedKeys.memberships(USER_A)).toContain(USER_A);
    expect(authScopedKeys.account(USER_A)).toContain(USER_A);
    expect(authScopedKeys.user(USER_A)).toContain(USER_A);
  });

  it("produces different keys for different users", () => {
    expect(authScopedKeys.account(USER_A)).not.toEqual(
      authScopedKeys.account(USER_B),
    );
    expect(authScopedKeys.profile(USER_A)).not.toEqual(
      authScopedKeys.profile(USER_B),
    );
  });

  it("produces different keys for different resources of one user", () => {
    expect(authScopedKeys.profile(USER_A)).not.toEqual(
      authScopedKeys.memberships(USER_A),
    );
  });

  it("is stable across calls", () => {
    expect(authScopedKeys.account(USER_A)).toEqual(
      authScopedKeys.account(USER_A),
    );
  });

  it("shares a prefix so the whole scope can be matched at once", () => {
    for (const key of [
      authScopedKeys.profile(USER_A),
      authScopedKeys.memberships(USER_A),
      authScopedKeys.account(USER_A),
    ]) {
      expect(isAuthScopedKey(key)).toBe(true);
    }
  });
});

describe("isAuthScopedKey", () => {
  it("rejects an unrelated key", () => {
    expect(isAuthScopedKey(["app-config"])).toBe(false);
    expect(isAuthScopedKey([])).toBe(false);
  });
});

describe("authScopedUserId", () => {
  it("reads the owner of a scoped key", () => {
    expect(authScopedUserId(authScopedKeys.account(USER_A))).toBe(USER_A);
  });

  it("returns null for an unscoped key", () => {
    expect(authScopedUserId(["app-config"])).toBeNull();
  });

  it("returns null when the id slot is not a string", () => {
    expect(authScopedUserId(["auth-scoped", 42])).toBeNull();
  });
});
