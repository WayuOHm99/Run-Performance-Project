import { describe, expect, it } from "vitest";

import { authScopedKeys, isAuthScopedKey } from "../../lib/query/keys";

import type { DailyCheckIn } from "./domain";
import {
  ANONYMOUS_KEY_USER_ID,
  checkInQueryOptions,
  saveCheckInMutationOptions,
} from "./query-options";

/**
 * The cache contract, tested without a renderer.
 *
 * Health literals are synthetic. Assertions are keys, counts, dates, and
 * booleans; no health-bearing object is compared or snapshotted.
 */

const USER_ID = "00000000-0000-4000-9000-000000000013";
const LOCAL_DATE = "2026-07-30";

const VALID_INPUT: DailyCheckIn = {
  rpe: 6,
  overallFeeling: 3,
  painStatus: "none",
};

function noopLoad(): Promise<DailyCheckIn | null> {
  return Promise.resolve(null);
}

describe("checkInQueryOptions", () => {
  it("keys the query by the verified user and the local date", () => {
    const options = checkInQueryOptions({
      userId: USER_ID,
      localDate: LOCAL_DATE,
      load: noopLoad,
    });

    expect(options.queryKey).toEqual(
      authScopedKeys.dailyCheckIn(USER_ID, LOCAL_DATE),
    );
    expect(options.queryKey).toContain(USER_ID);
    expect(options.queryKey).toContain(LOCAL_DATE);
  });

  it("puts no health value in the key", () => {
    const options = checkInQueryOptions({
      userId: USER_ID,
      localDate: LOCAL_DATE,
      load: noopLoad,
    });

    // The three protected values are numbers and two fixed words. The key is
    // pinned to exactly four string parts, so none of them can be present.
    expect(options.queryKey).toEqual([
      "auth-scoped",
      USER_ID,
      "daily-check-in",
      LOCAL_DATE,
    ]);
    expect(options.queryKey.every((part) => typeof part === "string")).toBe(
      true,
    );

    const serialized = JSON.stringify(options.queryKey);
    const leaks = ["none", "present", "rpe", "feeling", "pain"].filter(
      (fragment) => serialized.includes(fragment),
    );

    expect(leaks).toEqual([]);
  });

  it("stays inside the auth scope so a user change clears it", () => {
    expect(
      isAuthScopedKey(
        checkInQueryOptions({
          userId: USER_ID,
          localDate: LOCAL_DATE,
          load: noopLoad,
        }).queryKey,
      ),
    ).toBe(true);
  });

  it("produces a different entry per user and per date", () => {
    const key = (userId: string, localDate: string) =>
      checkInQueryOptions({ userId, localDate, load: noopLoad }).queryKey;

    expect(key(USER_ID, LOCAL_DATE)).not.toEqual(
      key("00000000-0000-4000-9000-0000000000ff", LOCAL_DATE),
    );
    // Crossing midnight must not serve yesterday's answers as today's.
    expect(key(USER_ID, LOCAL_DATE)).not.toEqual(key(USER_ID, "2026-07-31"));
  });

  it("is disabled and placeholder-keyed while no identity exists", () => {
    const options = checkInQueryOptions({
      userId: undefined,
      localDate: LOCAL_DATE,
      load: noopLoad,
    });

    expect(options.enabled).toBe(false);
    expect(options.queryKey).toContain(ANONYMOUS_KEY_USER_ID);
  });

  it("is enabled once an identity exists", () => {
    expect(
      checkInQueryOptions({
        userId: USER_ID,
        localDate: LOCAL_DATE,
        load: noopLoad,
      }).enabled,
    ).toBe(true);
  });

  it("loads with the exact user and date the key was built from", async () => {
    const seen: string[] = [];

    await checkInQueryOptions({
      userId: USER_ID,
      localDate: LOCAL_DATE,
      load: (userId, localDate) => {
        seen.push(`${userId}|${localDate}`);
        return Promise.resolve(null);
      },
    }).queryFn();

    expect(seen).toEqual([`${USER_ID}|${LOCAL_DATE}`]);
  });
});

describe("saveCheckInMutationOptions", () => {
  function build() {
    const savedDates: string[] = [];
    const invalidatedDates: string[] = [];
    let inputMatched = false;

    const options = saveCheckInMutationOptions({
      save: (localDate, input) => {
        savedDates.push(localDate);
        // Compared here so only a boolean is ever asserted.
        inputMatched =
          input.rpe === VALID_INPUT.rpe &&
          input.overallFeeling === VALID_INPUT.overallFeeling &&
          input.painStatus === VALID_INPUT.painStatus;

        return Promise.resolve();
      },
      invalidate: (localDate) => {
        invalidatedDates.push(localDate);
      },
    });

    return {
      options,
      savedDates,
      invalidatedDates,
      inputMatched: () => inputMatched,
    };
  }

  it("disables automatic retries", () => {
    // A failed health-bearing write is never resent without the athlete asking.
    expect(build().options.retry).toBe(0);
  });

  it("uses no optimistic update", () => {
    // No `onMutate`, so an unconfirmed health value never enters the cache.
    expect("onMutate" in build().options).toBe(false);
  });

  it("sends the captured date and the validated input", async () => {
    const harness = build();

    await harness.options.mutationFn({
      localDate: LOCAL_DATE,
      input: VALID_INPUT,
    });

    expect(harness.savedDates).toEqual([LOCAL_DATE]);
    expect(harness.inputMatched()).toBe(true);
  });

  it("returns the date it wrote, not the health values", async () => {
    const harness = build();

    const returned = await harness.options.mutationFn({
      localDate: LOCAL_DATE,
      input: VALID_INPUT,
    });

    expect(returned).toBe(LOCAL_DATE);
  });

  it("invalidates exactly the date that was written", async () => {
    const harness = build();

    harness.options.onSuccess(
      await harness.options.mutationFn({
        localDate: LOCAL_DATE,
        input: VALID_INPUT,
      }),
    );

    expect(harness.invalidatedDates).toEqual([LOCAL_DATE]);
  });

  it("invalidates the submitted date even if the device day has since moved", async () => {
    const harness = build();

    // The date travels through the variables and back out of `mutationFn`, so a
    // rollover mid-flight cannot redirect the invalidation to another day.
    harness.options.onSuccess(
      await harness.options.mutationFn({
        localDate: "2026-07-29",
        input: VALID_INPUT,
      }),
    );

    expect(harness.savedDates).toEqual(["2026-07-29"]);
    expect(harness.invalidatedDates).toEqual(["2026-07-29"]);
  });

  it("does not invalidate when the write failed", async () => {
    const invalidatedDates: string[] = [];
    const options = saveCheckInMutationOptions({
      save: () => Promise.reject(new Error("refused")),
      invalidate: (localDate) => {
        invalidatedDates.push(localDate);
      },
    });

    await expect(
      options.mutationFn({ localDate: LOCAL_DATE, input: VALID_INPUT }),
    ).rejects.toThrow();

    expect(invalidatedDates).toEqual([]);
  });
});
