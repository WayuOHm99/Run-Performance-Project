/**
 * Sanitized sharing failures.
 *
 * Nothing from a server error object crosses this module. `classifyDataError`
 * reduces an unknown thrown value to one of three categories by reading only its
 * `code`/`status` and its constructor name; the message the athlete sees is then
 * chosen from the fixed tables below. A Supabase message, SQLSTATE, `DETAIL`,
 * `HINT`, constraint name, policy name, function name, RPC argument, or row
 * representation therefore cannot reach the UI, and none is stored on the error
 * either — no `cause`, no retained field.
 *
 * The three intents are separated because they are three different situations for
 * the athlete: a failed load means nothing is known and the section must be
 * retried; a failed grant means sharing is still **off**; a failed revoke means
 * sharing is still **on**. Conflating them would let the wording imply a state
 * change that did not happen, which is the one thing decision 7 forbids.
 *
 * Nothing here logs, and nothing here reads a health value.
 */

import { classifyDataError, type DataFailure } from "../auth/errors";

export type SharingIntent = "load" | "grant" | "revoke";

const LOAD_MESSAGES: Record<DataFailure, string> = {
  offline: "เชื่อมต่อไม่สำเร็จ กรุณาตรวจสอบอินเทอร์เน็ตแล้วลองใหม่",
  denied: "ไม่มีสิทธิ์ดูการตั้งค่าการแชร์นี้",
  unknown: "โหลดการตั้งค่าการแชร์ไม่สำเร็จ กรุณาลองใหม่อีกครั้ง",
};

const GRANT_MESSAGES: Record<DataFailure, string> = {
  offline:
    "เชื่อมต่อไม่สำเร็จ ยังไม่ได้เริ่มแชร์ กรุณาตรวจสอบอินเทอร์เน็ตแล้วกดอนุญาตอีกครั้ง",
  denied: "ไม่มีสิทธิ์อนุญาตการแชร์ให้ทีมนี้ ยังไม่ได้เริ่มแชร์",
  unknown: "อนุญาตการแชร์ไม่สำเร็จ ยังไม่ได้เริ่มแชร์ กรุณาลองใหม่อีกครั้ง",
};

const REVOKE_MESSAGES: Record<DataFailure, string> = {
  offline:
    "เชื่อมต่อไม่สำเร็จ การแชร์ยังไม่ถูกหยุด กรุณาตรวจสอบอินเทอร์เน็ตแล้วกดหยุดแชร์อีกครั้ง",
  denied: "ไม่มีสิทธิ์หยุดการแชร์นี้ การแชร์ยังไม่ถูกหยุด",
  unknown: "หยุดการแชร์ไม่สำเร็จ การแชร์ยังไม่ถูกหยุด กรุณาลองใหม่อีกครั้ง",
};

const MESSAGES: Record<SharingIntent, Record<DataFailure, string>> = {
  load: LOAD_MESSAGES,
  grant: GRANT_MESSAGES,
  revoke: REVOKE_MESSAGES,
};

/** The wording used when a thrown value is not a `SharingDataError` at all. */
export const UNEXPECTED_SHARING_MESSAGE =
  "ทำรายการไม่สำเร็จ การตั้งค่าการแชร์ยังไม่เปลี่ยน กรุณาลองใหม่อีกครั้ง";

export class SharingDataError extends Error {
  override readonly name = "SharingDataError";
  readonly intent: SharingIntent;
  readonly failure: DataFailure;

  constructor(intent: SharingIntent, failure: DataFailure) {
    // Only ever a fixed string from the tables above. The original error is not
    // passed to `super`, not assigned to a field, and not kept as a `cause`.
    super(MESSAGES[intent][failure]);
    this.intent = intent;
    this.failure = failure;
  }
}

/** Classifies an unknown failure without retaining anything from it. */
export function sharingErrorFrom(
  intent: SharingIntent,
  error: unknown,
): SharingDataError {
  return new SharingDataError(intent, classifyDataError(error));
}

/**
 * The message to show for an unknown thrown value.
 *
 * A value that is not a `SharingDataError` has not been through sanitization, so
 * its own message is discarded rather than displayed.
 */
export function sharingErrorMessage(error: unknown): string {
  return error instanceof SharingDataError
    ? error.message
    : UNEXPECTED_SHARING_MESSAGE;
}

/** Every message a sanitized sharing error is allowed to carry. */
export function fixedSharingMessages(): ReadonlySet<string> {
  return new Set<string>([
    ...(["load", "grant", "revoke"] as const).flatMap((intent) =>
      (["offline", "denied", "unknown"] as const).map(
        (failure) => new SharingDataError(intent, failure).message,
      ),
    ),
    UNEXPECTED_SHARING_MESSAGE,
  ]);
}
