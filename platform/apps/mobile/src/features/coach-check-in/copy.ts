/**
 * Every string the coach review shows.
 *
 * Collected in one module so the wording rules are reviewable in one place:
 *
 * - **No database terminology.** The coach never sees "row", "table", "RLS", a
 *   SQLSTATE, a policy name, or a column name.
 * - **No raw error.** Failure wording comes from `errors.ts`, which builds it from
 *   a fixed table and never from a server message.
 * - **The recorded date is never called "today".** `dateLabel` says "วันที่บันทึก"
 *   (the date recorded), because the athlete's civil date is not necessarily the
 *   coach's current day and no UTC conversion is performed anywhere.
 * - **Nothing is a diagnosis.** `safetyNote` states plainly that these are the
 *   athlete's own self-reported numbers, that the screen offers no interpretation,
 *   and where to go for urgent or concerning symptoms.
 * - **Absence is never a statement about a person.** `noConsentTitle` describes the
 *   team, not any athlete. Decision 3 forbids listing who has not shared and
 *   forbids wording that reads as a refusal.
 * - **A failure never reads as "no data".** The error wording says the load failed;
 *   it never says an athlete has not checked in.
 */

import {
  RPE_MAX,
  OVERALL_FEELING_MAX,
  type PainStatus,
} from "../check-in/domain";

export const COACH_REVIEW_COPY = {
  label: "ทีม",
  title: "เช็กอินล่าสุดที่แชร์กับทีม",
  intro:
    "แสดงเฉพาะนักกีฬาที่อยู่ในทีมของคุณและกดอนุญาตแชร์ข้อมูลเช็กอินให้ทีมนั้นเท่านั้น และแสดงเพียงรายการล่าสุดหนึ่งรายการต่อคน",
  safetyNote:
    "ตัวเลขทั้งหมดเป็นการประเมินตนเองของนักกีฬา ไม่ใช่การวินิจฉัยทางการแพทย์ และหน้านี้ไม่ได้แปลผลหรือประเมินอาการให้ หากมีอาการรุนแรง เฉียบพลัน หรือน่ากังวล กรุณาแนะนำให้ปรึกษาแพทย์หรือผู้เชี่ยวชาญด้านสุขภาพ",

  dateLabel: "วันที่บันทึก",
  rpeLabel: "ความเหนื่อยรวม (RPE)",
  feelingLabel: "ความรู้สึกโดยรวม",
  painLabel: "อาการเจ็บ",

  loading: "กำลังโหลดข้อมูลที่แชร์กับทีม…",
  refreshing: "กำลังตรวจสอบสิทธิ์และโหลดข้อมูลใหม่…",
  refresh: "โหลดข้อมูลใหม่",

  /** The caller holds no active coach membership at all. */
  noTeamTitle: "ยังไม่มีทีมที่คุณเป็นโค้ช",
  noTeamMessage: "เมื่อคุณได้รับสิทธิ์เป็นโค้ชของทีม รายชื่อทีมจะแสดงที่นี่",

  /** Teams exist, but no athlete in them actively shares check-in data. */
  noConsentTitle: "ยังไม่มีข้อมูลที่แชร์กับทีมนี้",
  noConsentMessage:
    "ทีมนี้ยังไม่มีข้อมูลเช็กอินที่แชร์ให้ดู การแชร์เป็นสิทธิ์ของนักกีฬาและเปิดหรือปิดเมื่อใดก็ได้",

  /** An active grant, a valid athlete, and no check-in row yet. */
  noCheckIn: "ยังไม่ได้เช็กอิน",

  loadErrorTitle: "โหลดไม่สำเร็จ",
  capacityErrorTitle: "ข้อมูลเกินขนาดที่รองรับ",
  retry: "ลองโหลดอีกครั้ง",
} as const;

const OVERALL_FEELING_LABELS = new Map<number, string>([
  [1, "แย่มาก"],
  [2, "แย่"],
  [3, "ปกติ"],
  [4, "ดี"],
  [5, "ดีมาก"],
]);

/**
 * The feeling label, always paired with its number by the caller.
 *
 * Falls back to the bare number rather than throwing: the value has already been
 * validated as 1–5 by `parseCheckInRow`, so this branch is unreachable from a
 * validated row, and failing to render is worse than rendering the digit.
 */
export function overallFeelingLabel(value: number): string {
  return OVERALL_FEELING_LABELS.get(value) ?? String(value);
}

/** `7 / 10`, so the scale is never left to the reader to guess. */
export function rpeText(value: number): string {
  return `${String(value)} / ${String(RPE_MAX)}`;
}

/** `4 / 5 · ดี`, for the same reason. */
export function overallFeelingText(value: number): string {
  return `${String(value)} / ${String(OVERALL_FEELING_MAX)} · ${overallFeelingLabel(value)}`;
}

/**
 * The pain wording: the two fixed strings, and nothing between them.
 *
 * Worded identically to the athlete-side labels on purpose — the coach must read
 * exactly what the athlete recorded — but declared here rather than imported,
 * because `features/check-in/copy.ts` is outside this task's read-only dependency
 * set. `pain_status` is binary in the TASK-012 `CHECK` constraint and stays binary
 * here: there is no severity, no scale, and no adjective a coach could read as a
 * clinical grading.
 */
const PAIN_LABELS: Record<PainStatus, string> = {
  none: "ไม่มีอาการเจ็บ",
  present: "มีอาการเจ็บ",
};

export function painText(status: PainStatus): string {
  return PAIN_LABELS[status];
}

/** Every feeling value has a label, so no reading can render as a bare number. */
export function hasLabelForEveryOverallFeeling(): boolean {
  return [1, 2, 3, 4, 5].every((value) => OVERALL_FEELING_LABELS.has(value));
}
