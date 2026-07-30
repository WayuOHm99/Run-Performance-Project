/**
 * Every string the check-in card shows.
 *
 * Collected in one module so the wording rules are reviewable in one place:
 *
 * - No database terminology. The athlete never sees "row", "table", "insert",
 *   "RLS", a SQLSTATE, or a column name.
 * - No raw error. Failure wording comes from `errors.ts`, which builds it from a
 *   fixed table and never from a server message.
 * - The pain copy is fixed, non-diagnostic, and offers no interpretation. It says
 *   what the check-in is not, and where to go for urgent or concerning symptoms.
 * - RPE is defined as the whole day's exertion, with the recommendation to fill
 *   it in after the last session or in the evening, so the number means the same
 *   thing every day.
 */

import { OVERALL_FEELING_VALUES, type PainStatus } from "./domain";

export const CHECK_IN_COPY = {
  label: "เช็กอิน",
  title: "เช็กอินวันนี้",
  intro:
    "ตอบสามข้อสั้น ๆ เกี่ยวกับวันนี้ ใช้เวลาประมาณ 30 วินาที ข้อมูลนี้เป็นของคุณ และจะแชร์ให้โค้ชได้เมื่อคุณอนุญาตเท่านั้น",
  dateLabel: "วันที่",

  rpeLegend: "ความเหนื่อยรวมของวันนี้ (RPE)",
  rpeHint:
    "ให้คะแนนความเหนื่อยรวมจากการซ้อมทั้งหมดของวันนี้ 0 = พัก ไม่ได้ออกแรง, 10 = เหนื่อยที่สุด แนะนำให้กรอกหลังซ้อมเสร็จหรือช่วงเย็น",

  feelingLegend: "ความรู้สึกโดยรวมวันนี้",
  feelingHint: "เลือกระดับที่ตรงกับความรู้สึกโดยรวมของคุณมากที่สุด",

  painLegend: "อาการเจ็บวันนี้",
  painSafety:
    "การเช็กอินนี้ไม่ใช่การวินิจฉัยทางการแพทย์ และไม่ได้ประเมินหรือแปลผลอาการของคุณ หากมีอาการรุนแรง เฉียบพลัน หรือน่ากังวล กรุณาปรึกษาแพทย์หรือผู้เชี่ยวชาญด้านสุขภาพ",

  loading: "กำลังโหลดการเช็กอินของวันนี้…",
  loadErrorTitle: "โหลดไม่สำเร็จ",
  retry: "ลองโหลดอีกครั้ง",

  emptyState: "วันนี้ยังไม่ได้เช็กอิน เลือกคำตอบทั้งสามข้อแล้วกดบันทึก",
  editState: "วันนี้เช็กอินแล้ว แก้ไขคำตอบได้ถ้าต้องการ",
  incompleteHint: "เลือกคำตอบให้ครบทั้งสามข้อก่อนบันทึก",

  save: "บันทึกการเช็กอิน",
  saving: "กำลังบันทึก…",
  savedTitle: "บันทึกแล้ว",
  savedMessage: "เก็บการเช็กอินของวันนี้เรียบร้อยแล้ว",
  saveErrorTitle: "บันทึกไม่สำเร็จ",

  rolloverTitle: "ข้ามไปวันใหม่แล้ว",
  rolloverMessage:
    "วันที่ของเครื่องเปลี่ยนไปแล้ว ระบบจึงยังไม่บันทึกคำตอบเดิม กรุณาตรวจสอบและตอบแบบฟอร์มของวันปัจจุบันอีกครั้ง",
} as const;

const OVERALL_FEELING_LABELS = new Map<number, string>([
  [1, "แย่มาก"],
  [2, "แย่"],
  [3, "ปกติ"],
  [4, "ดี"],
  [5, "ดีมาก"],
]);

export function overallFeelingLabel(value: number): string {
  return OVERALL_FEELING_LABELS.get(value) ?? String(value);
}

/** Every feeling value has a label, so no choice can render as a bare number. */
export function hasLabelForEveryOverallFeeling(): boolean {
  return OVERALL_FEELING_VALUES.every((value) =>
    OVERALL_FEELING_LABELS.has(value),
  );
}

export const PAIN_STATUS_LABELS: Record<PainStatus, string> = {
  none: "ไม่มีอาการเจ็บ",
  present: "มีอาการเจ็บ",
};

/** Spoken labels, so a screen reader announces the meaning, not just a digit. */
export function rpeAccessibilityLabel(value: number): string {
  return `ความเหนื่อยระดับ ${String(value)} จาก 10`;
}

export function overallFeelingAccessibilityLabel(value: number): string {
  return `ความรู้สึก ${overallFeelingLabel(value)}`;
}
