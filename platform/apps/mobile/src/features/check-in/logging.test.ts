import { describe, expect, it, vi } from "vitest";

import { loadDailyCheckIn, saveDailyCheckIn } from "./check-in-repository";
import { parseCheckInInput, parseCheckInRow } from "./domain";
import { checkInErrorFrom, checkInErrorMessage } from "./errors";
import { formatLocalDate, readLocalDateStamp } from "./local-date";
import { EMPTY_DRAFT, planSubmission } from "./submission";

/**
 * Proves at runtime that nothing in the feature writes to a console channel.
 *
 * The source scan in `source-safety.test.ts` shows no log call is written; this
 * shows none happens, including on the failure paths — a refused read, a lost
 * insert race, and an invalid input — which are exactly where a careless edit
 * would add one "just for debugging" and put `rpe`, `overall_feeling`, or
 * `pain_status` into a log, a crash report, or session replay.
 *
 * Only a call count is asserted, so a failure reveals nothing.
 */

const USER_ID = "00000000-0000-4000-9000-000000000013";
const LOCAL_DATE = "2026-07-30";

/** Synthetic. Chosen to be a complete, valid answer set. */
const VALID_INPUT = { rpe: 6, overallFeeling: 3, painStatus: "none" } as const;

const CHANNELS = ["log", "info", "warn", "error", "debug", "trace"] as const;

/**
 * A client double whose read is refused and whose insert loses a creation race,
 * so the load, the update, the insert, and the retry all run.
 */
function failingClient() {
  return {
    from: () => ({
      select: () => ({
        eq: () => ({
          eq: () => ({
            maybeSingle: () =>
              Promise.resolve({ data: null, error: { code: "42501" } }),
          }),
        }),
      }),
      update: () => ({
        eq: () => ({
          eq: () => ({
            select: () => ({
              maybeSingle: () => Promise.resolve({ data: null, error: null }),
            }),
          }),
        }),
      }),
      insert: () => Promise.resolve({ data: null, error: { code: "23505" } }),
    }),
  } as never;
}

async function countConsoleCalls(run: () => Promise<void>): Promise<number> {
  const spies = CHANNELS.map((channel) =>
    vi.spyOn(console, channel).mockImplementation(() => undefined),
  );

  try {
    await run();

    // Counted here, before the `finally` restores the spies. `mockRestore` also
    // resets the mock, which clears `mock.calls` — reading the totals after it
    // made this helper report zero unconditionally, so the whole file passed
    // vacuously. Returning from inside the `try` evaluates the count first.
    return spies.reduce((total, spy) => total + spy.mock.calls.length, 0);
  } finally {
    for (const spy of spies) {
      spy.mockRestore();
    }
  }
}

describe("no health value reaches a log", () => {
  it("stays silent across the pure paths", async () => {
    const calls = await countConsoleCalls(async () => {
      parseCheckInRow({ rpe: 6, overall_feeling: 3, pain_status: "none" });
      parseCheckInRow({ rpe: 99, overall_feeling: null, pain_status: "mild" });
      parseCheckInInput(VALID_INPUT);
      parseCheckInInput(null);
      formatLocalDate(new Date(2026, 6, 30));
      planSubmission({
        captured: readLocalDateStamp(),
        current: readLocalDateStamp(),
        draft: EMPTY_DRAFT,
      });
      checkInErrorMessage(checkInErrorFrom("save", { code: "42501" }));

      await Promise.resolve();
    });

    expect(calls).toBe(0);
  });

  it("stays silent when a read is refused", async () => {
    const calls = await countConsoleCalls(async () => {
      await loadDailyCheckIn(failingClient(), USER_ID, LOCAL_DATE).catch(
        () => undefined,
      );
    });

    expect(calls).toBe(0);
  });

  it("stays silent through an insert race and a failed retry", async () => {
    const calls = await countConsoleCalls(async () => {
      await saveDailyCheckIn(
        failingClient(),
        USER_ID,
        LOCAL_DATE,
        VALID_INPUT,
      ).catch(() => undefined);
    });

    expect(calls).toBe(0);
  });

  it("stays silent when an invalid input is refused before any write", async () => {
    const calls = await countConsoleCalls(async () => {
      await saveDailyCheckIn(failingClient(), USER_ID, LOCAL_DATE, {
        rpe: 99,
        overallFeeling: 3,
        painStatus: "none",
      }).catch(() => undefined);
    });

    expect(calls).toBe(0);
  });

  it("stays silent when the date has gone stale", async () => {
    const calls = await countConsoleCalls(async () => {
      await saveDailyCheckIn(
        failingClient(),
        USER_ID,
        "not-a-date",
        VALID_INPUT,
      ).catch(() => undefined);
    });

    expect(calls).toBe(0);
  });
});
