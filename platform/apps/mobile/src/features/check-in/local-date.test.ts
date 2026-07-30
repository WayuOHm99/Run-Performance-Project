import { describe, expect, it } from "vitest";

import {
  formatLocalDate,
  isLocalDateString,
  localDateStampChanged,
  readLocalDateStamp,
} from "./local-date";

/**
 * A `Date` stand-in that reports local parts and a deliberately different UTC
 * instant.
 *
 * This is what makes "local, not UTC" provable on any machine, including one
 * running at UTC+00:00 where a real `Date` would make the two agree and the test
 * would pass vacuously.
 */
function localPartsDate(parts: {
  readonly year: number;
  readonly month: number;
  readonly day: number;
  readonly iso: string;
}): Date {
  return {
    getFullYear: () => parts.year,
    getMonth: () => parts.month - 1,
    getDate: () => parts.day,
    getTimezoneOffset: () => 0,
    toISOString: () => parts.iso,
  } as unknown as Date;
}

describe("formatLocalDate", () => {
  it("formats from the local year, month, and day", () => {
    expect(
      formatLocalDate(
        localPartsDate({
          year: 2026,
          month: 7,
          day: 30,
          iso: "2026-07-30T04:00:00.000Z",
        }),
      ),
    ).toBe("2026-07-30");
  });

  it("zero-pads a single-digit month and day", () => {
    expect(
      formatLocalDate(
        localPartsDate({
          year: 2026,
          month: 1,
          day: 5,
          iso: "2026-01-05T00:00:00.000Z",
        }),
      ),
    ).toBe("2026-01-05");
  });

  it("keeps the local date when the UTC date is a day behind", () => {
    // A user at UTC+07:00 just after midnight: still yesterday in UTC. A
    // toISOString-derived date would file the check-in under the wrong day.
    const justAfterLocalMidnight = localPartsDate({
      year: 2026,
      month: 7,
      day: 30,
      iso: "2026-07-29T17:05:00.000Z",
    });

    expect(formatLocalDate(justAfterLocalMidnight)).toBe("2026-07-30");
    expect(formatLocalDate(justAfterLocalMidnight)).not.toBe(
      justAfterLocalMidnight.toISOString().slice(0, 10),
    );
  });

  it("keeps the local date when the UTC date is a day ahead", () => {
    // A user at UTC-06:00 late in the evening: already tomorrow in UTC.
    const lateLocalEvening = localPartsDate({
      year: 2026,
      month: 7,
      day: 29,
      iso: "2026-07-30T03:40:00.000Z",
    });

    expect(formatLocalDate(lateLocalEvening)).toBe("2026-07-29");
    expect(formatLocalDate(lateLocalEvening)).not.toBe(
      lateLocalEvening.toISOString().slice(0, 10),
    );
  });

  it("crosses a month and a year boundary by local parts", () => {
    const localNewYear = localPartsDate({
      year: 2027,
      month: 1,
      day: 1,
      iso: "2026-12-31T17:30:00.000Z",
    });

    expect(formatLocalDate(localNewYear)).toBe("2027-01-01");
  });

  it("holds the same local date across a whole real local day", () => {
    // Real `Date` objects this time. Both ends of the local day must format to
    // the same calendar date; a UTC-derived implementation cannot do that
    // anywhere the machine offset is not zero.
    const startOfLocalDay = new Date(2026, 6, 30, 0, 0, 0, 0);
    const endOfLocalDay = new Date(2026, 6, 30, 23, 59, 59, 999);

    expect(formatLocalDate(startOfLocalDay)).toBe("2026-07-30");
    expect(formatLocalDate(endOfLocalDay)).toBe("2026-07-30");
  });

  it("produces a value the date guard rejects for an invalid Date", () => {
    // Fail-closed: the malformed value is refused at the repository boundary
    // rather than written as a wrongly dated row.
    expect(isLocalDateString(formatLocalDate(new Date(Number.NaN)))).toBe(
      false,
    );
  });
});

describe("readLocalDateStamp", () => {
  it("captures the local date together with the local offset", () => {
    const now = new Date(2026, 6, 30, 9, 15, 0);
    const stamp = readLocalDateStamp(now);

    expect(stamp.date).toBe("2026-07-30");
    expect(stamp.offsetMinutes).toBe(now.getTimezoneOffset());
  });

  it("produces a well-formed date for the real current instant", () => {
    expect(isLocalDateString(readLocalDateStamp().date)).toBe(true);
  });
});

describe("isLocalDateString", () => {
  it("accepts a well-formed calendar date", () => {
    expect(isLocalDateString("2026-07-30")).toBe(true);
  });

  it("rejects everything malformed", () => {
    const rejected: readonly [string, unknown][] = [
      ["empty", ""],
      ["null", null],
      ["undefined", undefined],
      ["a number", 20260730],
      ["single-digit month", "2026-7-30"],
      ["single-digit day", "2026-07-3"],
      ["slashes", "2026/07/30"],
      ["a full timestamp", "2026-07-30T00:00:00.000Z"],
      ["month zero", "2026-00-30"],
      ["month thirteen", "2026-13-30"],
      ["day zero", "2026-07-00"],
      ["day thirty-two", "2026-07-32"],
      ["NaN parts", "NaN-NaN-NaN"],
      ["trailing space", "2026-07-30 "],
      ["two-digit year", "26-07-30"],
    ];

    const wronglyAccepted = rejected
      .filter(([, value]) => isLocalDateString(value))
      .map(([name]) => name);

    expect(wronglyAccepted).toEqual([]);
  });

  it("accepts every real month-end date", () => {
    const accepted: readonly [string, string][] = [
      ["January 31", "2026-01-31"],
      ["February 28 in a common year", "2026-02-28"],
      ["February 29 in a leap year", "2024-02-29"],
      ["February 29 in a 400-divisible year", "2000-02-29"],
      ["March 31", "2026-03-31"],
      ["April 30", "2026-04-30"],
      ["May 31", "2026-05-31"],
      ["June 30", "2026-06-30"],
      ["July 31", "2026-07-31"],
      ["August 31", "2026-08-31"],
      ["September 30", "2026-09-30"],
      ["October 31", "2026-10-31"],
      ["November 30", "2026-11-30"],
      ["December 31", "2026-12-31"],
      ["first day of the first accepted year", "0001-01-01"],
      ["last day of the last four-digit year", "9999-12-31"],
    ];

    const wronglyRejected = accepted
      .filter(([, value]) => !isLocalDateString(value))
      .map(([name]) => name);

    expect(wronglyRejected).toEqual([]);
  });

  it("rejects impossible calendar dates", () => {
    // A pattern check alone accepted all of these, which meant a broken clock
    // could have sent a date the database would then have stored.
    const impossible: readonly [string, string][] = [
      ["February 29 in a common year", "2026-02-29"],
      ["February 29 in a century year", "1900-02-29"],
      ["February 30", "2026-02-30"],
      ["February 31", "2026-02-31"],
      ["February 30 in a leap year", "2024-02-30"],
      ["April 31", "2026-04-31"],
      ["June 31", "2026-06-31"],
      ["September 31", "2026-09-31"],
      ["November 31", "2026-11-31"],
      ["year zero", "0000-01-01"],
      ["year zero month end", "0000-12-31"],
    ];

    const wronglyAccepted = impossible
      .filter(([, value]) => isLocalDateString(value))
      .map(([name]) => name);

    expect(wronglyAccepted).toEqual([]);
  });

  it("applies the century and 400-year leap rules, not just divisibility by four", () => {
    const leapDayAccepted = (year: string) =>
      isLocalDateString(`${year}-02-29`);

    expect(leapDayAccepted("2024")).toBe(true);
    expect(leapDayAccepted("2000")).toBe(true);
    expect(leapDayAccepted("1900")).toBe(false);
    expect(leapDayAccepted("2100")).toBe(false);
    expect(leapDayAccepted("2026")).toBe(false);
  });

  it("agrees with a local Date round-trip on every day of a leap year", () => {
    // An independent cross-check of the arithmetic, using local getters only.
    // `new Date(y, m, d)` rolls an impossible day into the next month, which is
    // exactly why it cannot be the validator — but it is a fine oracle.
    const disagreements: string[] = [];

    for (let month = 1; month <= 12; month += 1) {
      for (let day = 1; day <= 31; day += 1) {
        const text = `2024-${String(month).padStart(2, "0")}-${String(
          day,
        ).padStart(2, "0")}`;
        const probe = new Date(2024, month - 1, day);
        const real =
          probe.getFullYear() === 2024 &&
          probe.getMonth() === month - 1 &&
          probe.getDate() === day;

        if (isLocalDateString(text) !== real) {
          disagreements.push(text);
        }
      }
    }

    // Date strings only; these carry no health value.
    expect(disagreements).toEqual([]);
  });
});

describe("localDateStampChanged", () => {
  const stamp = { date: "2026-07-30", offsetMinutes: -420 };

  it("is false for the same day in the same timezone", () => {
    expect(localDateStampChanged(stamp, { ...stamp })).toBe(false);
  });

  it("is true after midnight passes", () => {
    expect(localDateStampChanged(stamp, { ...stamp, date: "2026-07-31" })).toBe(
      true,
    );
  });

  it("is true when the timezone offset changes on the same calendar date", () => {
    // Travel or a DST transition moves the day boundary even though the printed
    // date is unchanged, so the captured form is still stale.
    expect(
      localDateStampChanged(stamp, { ...stamp, offsetMinutes: -300 }),
    ).toBe(true);
  });
});
