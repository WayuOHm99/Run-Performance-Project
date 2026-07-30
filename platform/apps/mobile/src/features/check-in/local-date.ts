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

/**
 * Whether a value is a well-formed calendar date string.
 *
 * Guards the repository boundary: a date this rejects never reaches a query, so
 * a malformed value cannot be sent as a filter or written as a row.
 */
export function isLocalDateString(value: unknown): value is string {
  if (typeof value !== "string" || !LOCAL_DATE_PATTERN.test(value)) {
    return false;
  }

  const month = Number(value.slice(5, 7));
  const day = Number(value.slice(8, 10));

  return month >= 1 && month <= 12 && day >= 1 && day <= 31;
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
