/**
 * Loading and saving the caller's own check-in for one local calendar date.
 *
 * The client is injected, so every path below is unit-tested against a
 * hand-written double with no network and no local database.
 *
 * Four rules this module exists to hold:
 *
 * 1. **A failure is not an empty result.** "No row for today" and "the read was
 *    refused" both produce no usable row, but the first is the normal empty form
 *    and the second must be a retry. `null` is returned only for a genuine
 *    absence; every failure raises `CheckInDataError`.
 *
 * 2. **The athlete id is never taken from the UI.** Both entry points require the
 *    verified authenticated user id from the auth provider, and every statement
 *    is filtered to it as well as to the exact captured date. The filter is not
 *    the security control — `daily_check_ins_select_own`, `_insert_own`, and
 *    `_update_own` are — but a query written as if it were unscoped must not rely
 *    on a policy to scope it.
 *
 * 3. **Update-first, never `.upsert()`.** `authenticated` holds
 *    `UPDATE (rpe, overall_feeling, pain_status)` and
 *    `INSERT (athlete_profile_id, check_in_date, rpe, overall_feeling,
 *    pain_status)` only, and a conflict target would have to name the unique
 *    index. An update that matches nothing is followed by the narrow insert; if
 *    that insert loses a creation race it fails `23505` and the same scoped
 *    update is retried exactly once. The race is detected by SQLSTATE alone —
 *    never by matching error text, which is neither stable nor safe to read.
 *
 * 4. **No health value crosses the boundary outward on a write.** The update
 *    returns `id`, a non-health sentinel used only to tell "matched" from "did
 *    not match"; the insert returns no representation at all; and both entry
 *    points resolve to `void` or to a validated domain value. Nothing here logs.
 */

import type { AppSupabaseClient } from "../../lib/supabase/app-client";

import {
  parseCheckInInput,
  parseCheckInRow,
  toWriteColumns,
  type DailyCheckIn,
} from "./domain";
import { CheckInDataError, checkInErrorFrom } from "./errors";
import { isLocalDateString } from "./local-date";

export type { AppSupabaseClient };

const TABLE = "daily_check_ins";

/** The only columns ever read. `id`, timestamps, and the owner are not needed. */
const HEALTH_COLUMNS = "rpe, overall_feeling, pain_status";

/** A non-health sentinel, returned purely to detect whether a row matched. */
const MATCH_SENTINEL = "id";

const UNIQUE_VIOLATION = "23505";

/**
 * Reads an error's SQLSTATE without touching its message.
 *
 * Deliberately narrow: only `code`. Branching on message text would be unstable
 * across Supabase versions and would put a database string into control flow,
 * one step away from putting it into a log.
 */
function errorCode(error: unknown): string {
  if (typeof error !== "object" || error === null) {
    return "";
  }

  const code = (error as { code?: unknown }).code;

  return typeof code === "string" ? code : "";
}

function isVerifiedUserId(userId: unknown): userId is string {
  return typeof userId === "string" && userId.length > 0;
}

/**
 * Loads the caller's check-in for one local date.
 *
 * Returns `null` only when the row genuinely does not exist, and a fully
 * validated value otherwise. A row that fails validation is a closed failure,
 * not a value to render partially.
 */
export async function loadDailyCheckIn(
  client: AppSupabaseClient,
  userId: string,
  localDate: string,
): Promise<DailyCheckIn | null> {
  if (!isVerifiedUserId(userId) || !isLocalDateString(localDate)) {
    // Refused before any client call, so a malformed identifier or date is never
    // sent as a filter.
    throw new CheckInDataError("load", "unknown");
  }

  const { data, error } = await client
    .from(TABLE)
    .select(HEALTH_COLUMNS)
    .eq("athlete_profile_id", userId)
    .eq("check_in_date", localDate)
    .maybeSingle();

  if (error) {
    throw checkInErrorFrom("load", error);
  }

  if (data === null) {
    // A real answer: the athlete has not checked in today. RLS filters rather
    // than raising, so this is also what a mismatched user id would look like —
    // and an empty form is the correct, harmless outcome in both cases.
    return null;
  }

  const parsed = parseCheckInRow(data);

  if (!parsed.ok) {
    throw new CheckInDataError("load", "unknown");
  }

  return parsed.value;
}

/**
 * Runs the scoped, three-column update.
 *
 * Resolves true when a row matched and false when none did. `select(id)` is what
 * makes that distinction available: an update refused by RLS or aimed at a date
 * with no row succeeds while affecting nothing.
 */
async function updateOwnCheckIn(
  client: AppSupabaseClient,
  userId: string,
  localDate: string,
  checkIn: DailyCheckIn,
): Promise<boolean> {
  const { data, error } = await client
    .from(TABLE)
    .update(toWriteColumns(checkIn))
    .eq("athlete_profile_id", userId)
    .eq("check_in_date", localDate)
    .select(MATCH_SENTINEL)
    .maybeSingle();

  if (error) {
    throw checkInErrorFrom("save", error);
  }

  return data !== null;
}

/**
 * Runs the five-column insert and returns its error, or null on success.
 *
 * No `.select()`: the caller needs no representation, and not requesting one
 * keeps the stored health values from travelling back over the wire.
 */
async function insertOwnCheckIn(
  client: AppSupabaseClient,
  userId: string,
  localDate: string,
  checkIn: DailyCheckIn,
): Promise<unknown> {
  const { error } = await client.from(TABLE).insert({
    athlete_profile_id: userId,
    check_in_date: localDate,
    ...toWriteColumns(checkIn),
  });

  return error;
}

/**
 * Creates or updates the caller's check-in for one local date.
 *
 * Resolves to `void`. The input is re-validated here even though the UI already
 * validated it, so a caller that skipped that step cannot send an out-of-range
 * value and leave the database to refuse it.
 */
export async function saveDailyCheckIn(
  client: AppSupabaseClient,
  userId: string,
  localDate: string,
  input: unknown,
): Promise<void> {
  const parsed = parseCheckInInput(input);

  if (
    !parsed.ok ||
    !isVerifiedUserId(userId) ||
    !isLocalDateString(localDate)
  ) {
    throw new CheckInDataError("save", "unknown");
  }

  if (await updateOwnCheckIn(client, userId, localDate, parsed.value)) {
    return;
  }

  const insertError = await insertOwnCheckIn(
    client,
    userId,
    localDate,
    parsed.value,
  );

  if (!insertError) {
    return;
  }

  if (errorCode(insertError) !== UNIQUE_VIOLATION) {
    // Anything else — refused, offline, malformed — is a sanitized failure. No
    // retry: repeating a rejected health-bearing write is decision 10's
    // prohibition on automatic retries.
    throw checkInErrorFrom("save", insertError);
  }

  // Lost a creation race: another writer inserted today's row between the update
  // and the insert, so the row now exists and the same scoped update applies.
  // Exactly once — a loop here would be an automatic retry.
  if (await updateOwnCheckIn(client, userId, localDate, parsed.value)) {
    return;
  }

  // The unique constraint says the row exists, yet the scoped update matched
  // nothing. That is either a refusal or a deletion between the two statements;
  // either way the athlete's answers were not stored, so it must not read as
  // success.
  throw new CheckInDataError("save", "unknown");
}
