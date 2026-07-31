/**
 * Sanitized coach-review failures.
 *
 * Nothing from a server error object crosses this module. `classifyDataError`
 * reduces an unknown thrown value to one of three categories by reading only its
 * `code`/`status` and its constructor name; the wording the coach sees is then
 * chosen from the fixed table below. A Supabase message, SQLSTATE, `DETAIL`,
 * `HINT`, constraint name, policy name, table name, or row representation
 * therefore cannot reach the UI, and none is stored on the error either — no
 * `cause`, no retained field.
 *
 * There is one intent, `load`, because this feature has exactly one operation:
 * decision 10 forbids any coach write path, so there is no grant, revoke, or save
 * to distinguish. The fourth failure, `capacity`, is deliberately *not* a
 * `DataFailure`: it is not a server refusal at all but this client's own refusal to
 * render more than the approved 100 pairs, and conflating it with `unknown` would
 * tell the coach to retry a load that will fail identically every time.
 *
 * Nothing here logs, and nothing here reads a health value.
 */

import { classifyDataError, type DataFailure } from "../auth/errors";

/** The only operation this feature performs. */
export type CoachReviewIntent = "load";

/**
 * Every failure category, including the one this client raises itself.
 *
 * `capacity` is client-side. It means the response was larger than the approved
 * maximum scope, so nothing is shown rather than a silently truncated list.
 */
export type CoachReviewFailure = DataFailure | "capacity";

const LOAD_MESSAGES: Record<CoachReviewFailure, string> = {
  offline: "เชื่อมต่อไม่สำเร็จ กรุณาตรวจสอบอินเทอร์เน็ตแล้วลองใหม่",
  denied: "ไม่มีสิทธิ์ดูข้อมูลนี้",
  unknown: "โหลดข้อมูลไม่สำเร็จ กรุณาลองใหม่อีกครั้ง",
  capacity:
    "ทีมของคุณมีนักกีฬาที่แชร์ข้อมูลมากเกินกว่าที่หน้านี้รองรับ ระบบจึงไม่แสดงข้อมูลบางส่วน กรุณาแจ้งผู้ดูแลระบบ",
};

/** The wording used when a thrown value is not a `CoachReviewDataError` at all. */
export const UNEXPECTED_COACH_REVIEW_MESSAGE =
  "เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง";

export class CoachReviewDataError extends Error {
  override readonly name = "CoachReviewDataError";
  readonly intent: CoachReviewIntent;
  readonly failure: CoachReviewFailure;

  constructor(intent: CoachReviewIntent, failure: CoachReviewFailure) {
    // Only ever a fixed string from the table above. The original error is not
    // passed to `super`, not assigned to a field, and not kept as a `cause`.
    super(LOAD_MESSAGES[failure]);
    this.intent = intent;
    this.failure = failure;
  }
}

/** Classifies an unknown failure without retaining anything from it. */
export function coachReviewErrorFrom(
  intent: CoachReviewIntent,
  error: unknown,
): CoachReviewDataError {
  return new CoachReviewDataError(intent, classifyDataError(error));
}

/**
 * The message to show for an unknown thrown value.
 *
 * A value that is not a `CoachReviewDataError` has not been through sanitization,
 * so its own message is discarded rather than displayed.
 */
export function coachReviewErrorMessage(error: unknown): string {
  return error instanceof CoachReviewDataError
    ? error.message
    : UNEXPECTED_COACH_REVIEW_MESSAGE;
}

/** True when the failure is this client's own capacity refusal. */
export function isCapacityFailure(error: unknown): boolean {
  return error instanceof CoachReviewDataError && error.failure === "capacity";
}

/** Every message a sanitized coach-review error is allowed to carry. */
export function fixedCoachReviewMessages(): ReadonlySet<string> {
  return new Set<string>([
    ...(["offline", "denied", "unknown", "capacity"] as const).map(
      (failure) => new CoachReviewDataError("load", failure).message,
    ),
    UNEXPECTED_COACH_REVIEW_MESSAGE,
  ]);
}
