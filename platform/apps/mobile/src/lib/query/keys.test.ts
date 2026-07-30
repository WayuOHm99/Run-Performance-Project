import { describe, expect, it } from "vitest";

import { authScopedKeys, authScopedUserId, isAuthScopedKey } from "./keys";

const USER_A = "00000000-0000-4000-9000-00000000000a";
const USER_B = "00000000-0000-4000-9000-00000000000b";
const LOCAL_DATE = "2026-07-30";

describe("authScopedKeys", () => {
  it("includes the user id in every key", () => {
    // Without the user id, a cache entry written for one account could be read
    // by the next account signed in on the same device.
    expect(authScopedKeys.profile(USER_A)).toContain(USER_A);
    expect(authScopedKeys.memberships(USER_A)).toContain(USER_A);
    expect(authScopedKeys.account(USER_A)).toContain(USER_A);
    expect(authScopedKeys.user(USER_A)).toContain(USER_A);
    expect(authScopedKeys.dailyCheckIn(USER_A, LOCAL_DATE)).toContain(USER_A);
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
      authScopedKeys.dailyCheckIn(USER_A, LOCAL_DATE),
    ]) {
      expect(isAuthScopedKey(key)).toBe(true);
    }
  });
});

describe("authScopedKeys.dailyCheckIn", () => {
  it("carries the user id and the local date", () => {
    expect(authScopedKeys.dailyCheckIn(USER_A, LOCAL_DATE)).toEqual([
      "auth-scoped",
      USER_A,
      "daily-check-in",
      LOCAL_DATE,
    ]);
  });

  it("holds no health value", () => {
    // The check-in's three protected values live in the cached data, never in
    // the key. Pinning the key to four strings is what keeps that true.
    const key = authScopedKeys.dailyCheckIn(USER_A, LOCAL_DATE);

    expect(key.length).toBe(4);
    expect(key.every((part) => typeof part === "string")).toBe(true);
  });

  it("separates dates so crossing midnight cannot reuse yesterday's entry", () => {
    expect(authScopedKeys.dailyCheckIn(USER_A, LOCAL_DATE)).not.toEqual(
      authScopedKeys.dailyCheckIn(USER_A, "2026-07-31"),
    );
  });

  it("separates users on the same date", () => {
    expect(authScopedKeys.dailyCheckIn(USER_A, LOCAL_DATE)).not.toEqual(
      authScopedKeys.dailyCheckIn(USER_B, LOCAL_DATE),
    );
  });

  it("is owned by the user it names", () => {
    expect(
      authScopedUserId(authScopedKeys.dailyCheckIn(USER_A, LOCAL_DATE)),
    ).toBe(USER_A);
  });

  it("does not collide with the account key", () => {
    expect(authScopedKeys.dailyCheckIn(USER_A, LOCAL_DATE)).not.toEqual(
      authScopedKeys.account(USER_A),
    );
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
