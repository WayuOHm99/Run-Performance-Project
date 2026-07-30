/**
 * The device-local calendar date, and detection of a rollover.
 *
 * `check_in_date` is the athlete's own calendar day, which is a local-civil
 * concept, not an instant. `toISOString()` and every other UTC conversion are
 * therefore **prohibited** here: for a user in UTC+07:00, an 06:30 check-in is
 * still 23:30 of the previous day in UTC, so a UTC-derived date would file the
 * answers under yesterday. The date is assembled by hand from the local year,
 * month, and day instead.
 *
 * A stamp also carries the local UTC offset. A user who crosses a timezone can
 * keep the same calendar date while the meaning of "today" moves under them, and
 * a stale form must not be submitted in that case either, so the offset is part
 * of the identity of "the day this form was created for".
 *
 * Nothing here reads or emits a health value.
 */

export type LocalDateStamp = {
  /** `YYYY-MM-DD`, built from local parts only. */
  readonly date: string;
  /** `Date#getTimezoneOffset()` at capture time, in minutes. */
  readonly offsetMinutes: number;
};

const LOCAL_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

function pad(value: number, length: number): string {
  return String(value).padStart(length, "0");
}

/**
 * Formats a `Date` as the local calendar date.
 *
 * An invalid `Date` yields a string that `isLocalDateString` rejects, so the
 * failure surfaces as a refused write rather than as a wrongly dated row.
 */
export function formatLocalDate(now: Date): string {
  return [
    pad(now.getFullYear(), 4),
    pad(now.getMonth() + 1, 2),
    pad(now.getDate(), 2),
  ].join("-");
}

export function readLocalDateStamp(now: Date = new Date()): LocalDateStamp {
  return {
    date: formatLocalDate(now),
    offsetMinutes: now.getTimezoneOffset(),
  };
}

/** Proleptic Gregorian leap year: every 4th, except centuries, except every 400th. */
function isLeapYear(year: number): boolean {
  return (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
}

const MONTH_LENGTHS: readonly number[] = [
  31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31,
];

/** Days in a 1-based month, or 0 for a month outside 1–12. */
function daysInMonth(year: number, month: number): number {
  if (month === 2 && isLeapYear(year)) {
    return 29;
  }

  return MONTH_LENGTHS[month - 1] ?? 0;
}

/**
 * Whether a value is a real calendar date string.
 *
 * Guards the repository boundary: a date this rejects never reaches a query, so
 * a malformed value cannot be sent as a filter or written as a row.
 *
 * The month length is computed arithmetically rather than by round-tripping
 * through `Date`, because every `Date`-based check available here — `Date.UTC`,
 * `toISOString`, a UTC getter, or locale formatting — is a UTC-derived path that
 * decision 2 prohibits in this module, and a local `new Date(y, m, d)`
 * round-trip silently rolls an impossible day over into the next month instead
 * of reporting it.
 *
 * The accepted contract is year 1 through 9999. Year 0 is rejected: it is not a
 * year in the Gregorian calendar as people use it, and no real check-in can
 * carry it, so accepting it would only widen what a malformed clock can write.
 */
export function isLocalDateString(value: unknown): value is string {
  if (typeof value !== "string" || !LOCAL_DATE_PATTERN.test(value)) {
    return false;
  }

  const year = Number(value.slice(0, 4));
  const month = Number(value.slice(5, 7));
  const day = Number(value.slice(8, 10));

  if (year < 1 || month < 1 || month > 12) {
    return false;
  }

  return day >= 1 && day <= daysInMonth(year, month);
}

/**
 * Whether the local day a form was created for is no longer the current one.
 *
 * True when the calendar date changed (midnight passed) or the offset changed
 * (the device moved timezone, or a DST transition altered the day boundary).
 */
export function localDateStampChanged(
  captured: LocalDateStamp,
  current: LocalDateStamp,
): boolean {
  return (
    captured.date !== current.date ||
    captured.offsetMinutes !== current.offsetMinutes
  );
}
