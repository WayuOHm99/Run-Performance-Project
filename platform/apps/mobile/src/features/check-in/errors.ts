/**
 * Sanitized check-in failures.
 *
 * Nothing from a server error object crosses this module. `classifyDataError`
 * reduces an unknown thrown value to one of three categories by reading only its
 * `code`/`status` and its constructor name; the message shown to the athlete is
 * then chosen from the fixed table below. A Supabase message, SQLSTATE, `DETAIL`,
 * `HINT`, constraint name, column name, request payload, or row representation
 * can therefore never reach the UI, and none is stored on the error either.
 *
 * Load and save are separated because they are different user situations: a
 * failed load leaves nothing done, while a failed save leaves the athlete's
 * answers unsent and needing a retry. Both wordings avoid database terminology.
 *
 * Nothing here logs, and nothing here reads a health value.
 */

import { classifyDataError, type DataFailure } from "../auth/errors";

export type CheckInIntent = "load" | "save";

const LOAD_MESSAGES: Record<DataFailure, string> = {
  offline: "เชื่อมต่อไม่สำเร็จ กรุณาตรวจสอบอินเทอร์เน็ตแล้วลองใหม่",
  denied: "ไม่มีสิทธิ์เข้าถึงข้อมูลนี้",
  unknown: "โหลดการเช็กอินไม่สำเร็จ กรุณาลองใหม่อีกครั้ง",
};

const SAVE_MESSAGES: Record<DataFailure, string> = {
  offline: "เชื่อมต่อไม่สำเร็จ กรุณาตรวจสอบอินเทอร์เน็ตแล้วลองใหม่",
  denied: "ไม่มีสิทธิ์บันทึกข้อมูลนี้",
  unknown: "บันทึกการเช็กอินไม่สำเร็จ กรุณาลองใหม่อีกครั้ง",
};

const MESSAGES: Record<CheckInIntent, Record<DataFailure, string>> = {
  load: LOAD_MESSAGES,
  save: SAVE_MESSAGES,
};

/** The wording used when a thrown value is not a `CheckInDataError` at all. */
export const UNEXPECTED_CHECK_IN_MESSAGE = SAVE_MESSAGES.unknown;

export class CheckInDataError extends Error {
  override readonly name = "CheckInDataError";
  readonly intent: CheckInIntent;
  readonly failure: DataFailure;

  constructor(intent: CheckInIntent, failure: DataFailure) {
    // Only ever a fixed string from the table above. The original error is not
    // passed to `super`, not assigned to a field, and not kept as a `cause`.
    super(MESSAGES[intent][failure]);
    this.intent = intent;
    this.failure = failure;
  }
}

/** Classifies an unknown failure without retaining anything from it. */
export function checkInErrorFrom(
  intent: CheckInIntent,
  error: unknown,
): CheckInDataError {
  return new CheckInDataError(intent, classifyDataError(error));
}

/**
 * The message to show for an unknown thrown value.
 *
 * A value that is not a `CheckInDataError` has not been through sanitization, so
 * its own message is discarded rather than displayed.
 */
export function checkInErrorMessage(error: unknown): string {
  return error instanceof CheckInDataError
    ? error.message
    : UNEXPECTED_CHECK_IN_MESSAGE;
}
