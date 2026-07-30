/**
 * The daily check-in domain type and its strict runtime validation.
 *
 * Three values, all protected health data: overall session RPE, overall feeling,
 * and a binary pain status. Nothing else is collected — no location, free text,
 * severity, image, diagnosis, or interpretation — so unstructured health
 * disclosure is impossible by construction rather than by review.
 *
 * The validation here is **fail-closed and total**. A `DailyCheckIn` value
 * cannot be constructed except through a parse that checked all three fields, so
 * a partially valid server row can never be displayed or cached: the row is
 * either fully valid or it is rejected outright. Nothing is coerced. A number
 * that is fractional, out of range, `NaN`, or not a number at all is a rejection,
 * not a value to round.
 *
 * The ranges mirror the TASK-012 `CHECK` constraints. Duplicating them
 * client-side is a UX and integrity measure, never the authorization boundary —
 * PostgreSQL grants, RLS, and those constraints remain that.
 *
 * Nothing in this module logs, formats, or stringifies a health value.
 */

export const PAIN_STATUSES = ["none", "present"] as const;

export type PainStatus = (typeof PAIN_STATUSES)[number];

export const RPE_MIN = 0;
export const RPE_MAX = 10;
export const OVERALL_FEELING_MIN = 1;
export const OVERALL_FEELING_MAX = 5;

/** The eleven selectable RPE values, in ascending order. */
export const RPE_VALUES: readonly number[] = Array.from(
  { length: RPE_MAX - RPE_MIN + 1 },
  (_unused, index) => RPE_MIN + index,
);

/** The five selectable overall-feeling values, in ascending order. */
export const OVERALL_FEELING_VALUES: readonly number[] = Array.from(
  { length: OVERALL_FEELING_MAX - OVERALL_FEELING_MIN + 1 },
  (_unused, index) => OVERALL_FEELING_MIN + index,
);

export type DailyCheckIn = {
  readonly rpe: number;
  readonly overallFeeling: number;
  readonly painStatus: PainStatus;
};

/**
 * The exact three-column payload of an approved UPDATE.
 *
 * `authenticated` holds `UPDATE (rpe, overall_feeling, pain_status)` only, so
 * naming a fourth column fails `42501` at the privilege layer. Pinning the shape
 * in a type keeps that from being discovered at runtime.
 */
export type CheckInWriteColumns = {
  readonly rpe: number;
  readonly overall_feeling: number;
  readonly pain_status: PainStatus;
};

/**
 * A parse result rather than a thrown error or a nullable value.
 *
 * `null` is a meaningful answer elsewhere in this feature ("no row for today"),
 * so an invalid row must not also be `null`. Callers decide what a rejection
 * means; this module only decides validity.
 */
export type CheckInParse =
  { readonly ok: true; readonly value: DailyCheckIn } | { readonly ok: false };

const REJECTED: CheckInParse = { ok: false };

function isIntegerInRange(
  value: unknown,
  min: number,
  max: number,
): value is number {
  // `Number.isInteger` rejects NaN, Infinity, and every fractional value, which
  // is why there is no separate check for those.
  return (
    typeof value === "number" &&
    Number.isInteger(value) &&
    value >= min &&
    value <= max
  );
}

export function isRpe(value: unknown): value is number {
  return isIntegerInRange(value, RPE_MIN, RPE_MAX);
}

export function isOverallFeeling(value: unknown): value is number {
  return isIntegerInRange(value, OVERALL_FEELING_MIN, OVERALL_FEELING_MAX);
}

export function isPainStatus(value: unknown): value is PainStatus {
  // Case-sensitive and exact, matching the database CHECK constraint. "None",
  // "mild", and "" are all unknown values, not values to normalize.
  return (
    typeof value === "string" &&
    (PAIN_STATUSES as readonly string[]).includes(value)
  );
}

function readField(source: unknown, field: string): unknown {
  if (typeof source !== "object" || source === null) {
    return undefined;
  }

  return (source as Record<string, unknown>)[field];
}

function buildCheckIn(
  rpe: unknown,
  overallFeeling: unknown,
  painStatus: unknown,
): CheckInParse {
  // All three are checked before anything is built, so a row with two good
  // fields and one bad one produces no value at all.
  if (
    !isRpe(rpe) ||
    !isOverallFeeling(overallFeeling) ||
    !isPainStatus(painStatus)
  ) {
    return REJECTED;
  }

  return { ok: true, value: { rpe, overallFeeling, painStatus } };
}

/**
 * Validates a row as returned by the database, in its column naming.
 *
 * Applied to every server read. The database already constrains these columns,
 * but the app must not trust that a response reached it unaltered, and a client
 * that renders whatever arrives has no way to fail closed.
 */
export function parseCheckInRow(row: unknown): CheckInParse {
  return buildCheckIn(
    readField(row, "rpe"),
    readField(row, "overall_feeling"),
    readField(row, "pain_status"),
  );
}

/**
 * Validates a complete input assembled by the UI, in domain naming.
 *
 * Applied again inside the repository before any write, so a caller that skipped
 * validation cannot send an out-of-range value and rely on the database to
 * refuse it.
 */
export function parseCheckInInput(input: unknown): CheckInParse {
  return buildCheckIn(
    readField(input, "rpe"),
    readField(input, "overallFeeling"),
    readField(input, "painStatus"),
  );
}

/** The three mutable health columns, and nothing else. */
export function toWriteColumns(checkIn: DailyCheckIn): CheckInWriteColumns {
  return {
    rpe: checkIn.rpe,
    overall_feeling: checkIn.overallFeeling,
    pain_status: checkIn.painStatus,
  };
}
