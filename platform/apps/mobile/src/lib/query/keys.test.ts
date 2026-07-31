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
    expect(authScopedKeys.checkInSharing(USER_A)).toContain(USER_A);
    expect(authScopedKeys.coachCheckInReview(USER_A)).toContain(USER_A);
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
      authScopedKeys.checkInSharing(USER_A),
      authScopedKeys.coachCheckInReview(USER_A),
    ]) {
      expect(isAuthScopedKey(key)).toBe(true);
    }
  });
});

/**
 * The coach-review key.
 *
 * This is the only key in the application whose cached value carries protected
 * health data belonging to **someone other than the caller**, so its assertions are
 * the strictest here. Every one is reduced to a fixed literal, an owner *label*, a
 * count, or a boolean, so a failure prints `auth-scoped|owner-a|coach-check-in-review|3`
 * and never an identifier.
 */
describe("authScopedKeys.coachCheckInReview", () => {
  const OWNER_LABELS = new Map<unknown, string>([
    [USER_A, "owner-a"],
    [USER_B, "owner-b"],
  ]);

  const describeKey = (key: readonly unknown[]): string =>
    `${String(key[0])}|${OWNER_LABELS.get(key[1]) ?? "unknown"}|${String(
      key[2],
    )}|${String(key.length)}`;

  it("carries the coach's user id and the resource, and nothing else", () => {
    expect(describeKey(authScopedKeys.coachCheckInReview(USER_A))).toBe(
      "auth-scoped|owner-a|coach-check-in-review|3",
    );
  });

  it("holds no health value, no team id, and no athlete id", () => {
    // One entry covers the whole review, so neither a team nor an athlete belongs
    // in the key. Pinning it to three strings is what keeps that true.
    const key = authScopedKeys.coachCheckInReview(USER_A);

    expect(key.length).toBe(3);
    expect(key.every((part) => typeof part === "string")).toBe(true);

    const serialized = JSON.stringify(key);
    const leaks = [
      "rpe",
      "pain",
      "feeling",
      "date",
      "team",
      "athlete",
      "grant",
    ].filter((fragment) => serialized.includes(fragment));

    // Fragment names only.
    expect(leaks).toEqual([]);
  });

  it("names the coach, so one coach cannot read another's entry", () => {
    expect(describeKey(authScopedKeys.coachCheckInReview(USER_A))).not.toBe(
      describeKey(authScopedKeys.coachCheckInReview(USER_B)),
    );
    expect(
      authScopedUserId(authScopedKeys.coachCheckInReview(USER_A)) === USER_A,
    ).toBe(true);
  });

  it("is removable by the auth-scope predicate", () => {
    // Sign-out and account switch both drop this entry through
    // `clearAuthScopedQueries`, which matches on the shared prefix alone.
    expect(isAuthScopedKey(authScopedKeys.coachCheckInReview(USER_A))).toBe(
      true,
    );
  });

  it("does not collide with the athlete-side keys of the same user", () => {
    // A dual-role user holds both. They must never be the same entry: one is the
    // user's own check-in, the other is other people's.
    const distinct = new Set(
      [
        authScopedKeys.profile(USER_A),
        authScopedKeys.memberships(USER_A),
        authScopedKeys.account(USER_A),
        authScopedKeys.dailyCheckIn(USER_A, LOCAL_DATE),
        authScopedKeys.checkInSharing(USER_A),
        authScopedKeys.coachCheckInReview(USER_A),
      ].map((key) => JSON.stringify(key)),
    );

    // A count only.
    expect(distinct.size).toBe(6);
  });

  it("is stable across calls", () => {
    expect(
      JSON.stringify(authScopedKeys.coachCheckInReview(USER_A)) ===
        JSON.stringify(authScopedKeys.coachCheckInReview(USER_A)),
    ).toBe(true);
  });
});

/**
 * The check-in-sharing key.
 *
 * Assertions are reduced to fixed literals, an owner *label*, and a length, so a
 * failure prints `auth-scoped|owner-a|check-in-sharing|3` rather than an
 * identifier. Sharing metadata is not a health measurement but it is sensitive
 * authorization data, so it gets the same discipline.
 */
describe("authScopedKeys.checkInSharing", () => {
  const OWNER_LABELS = new Map<unknown, string>([
    [USER_A, "owner-a"],
    [USER_B, "owner-b"],
  ]);

  const describeKey = (key: readonly unknown[]): string =>
    `${String(key[0])}|${OWNER_LABELS.get(key[1]) ?? "unknown"}|${String(
      key[2],
    )}|${String(key.length)}`;

  it("carries the user id and the resource, and nothing else", () => {
    expect(describeKey(authScopedKeys.checkInSharing(USER_A))).toBe(
      "auth-scoped|owner-a|check-in-sharing|3",
    );
  });

  it("holds no health value and no team identifier", () => {
    // One entry covers the whole list, so no team id belongs in the key. This
    // feature never reads a check-in value at all, so none can appear here either.
    const key = authScopedKeys.checkInSharing(USER_A);

    expect(key.length).toBe(3);
    expect(key.every((part) => typeof part === "string")).toBe(true);

    const serialized = JSON.stringify(key);
    const leaks = ["rpe", "pain", "feeling", "team", "grant"].filter(
      (fragment) => serialized.includes(fragment),
    );

    // Fragment names only.
    expect(leaks).toEqual([]);
  });

  it("separates users", () => {
    expect(describeKey(authScopedKeys.checkInSharing(USER_A))).not.toBe(
      describeKey(authScopedKeys.checkInSharing(USER_B)),
    );
  });

  it("is owned by the user it names", () => {
    expect(
      authScopedUserId(authScopedKeys.checkInSharing(USER_A)) === USER_A,
    ).toBe(true);
  });

  it("does not collide with the other keys of one user", () => {
    const distinct = new Set(
      [
        authScopedKeys.profile(USER_A),
        authScopedKeys.memberships(USER_A),
        authScopedKeys.account(USER_A),
        authScopedKeys.dailyCheckIn(USER_A, LOCAL_DATE),
        authScopedKeys.checkInSharing(USER_A),
      ].map((key) => JSON.stringify(key)),
    );

    // A count only.
    expect(distinct.size).toBe(5);
  });

  it("is stable across calls", () => {
    expect(
      JSON.stringify(authScopedKeys.checkInSharing(USER_A)) ===
        JSON.stringify(authScopedKeys.checkInSharing(USER_A)),
    ).toBe(true);
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
