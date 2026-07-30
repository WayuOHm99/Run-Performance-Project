/**
 * Every string the sharing section shows.
 *
 * Collected in one module so the wording rules are reviewable in one place:
 *
 * - **No database terminology.** The athlete never sees "row", "table", "grant",
 *   "RLS", "RPC", a SQLSTATE, a policy name, a function name, or a column name.
 * - **No raw error.** Failure wording comes from `errors.ts`, which builds it from
 *   fixed tables and never from a server message.
 * - **No team id.** A team is always named. There is no string here into which an
 *   identifier is interpolated.
 * - **The scope of consent is stated, not implied.** `teamScope` says in plain
 *   Thai that consent goes to the team and covers its current *and future* active
 *   coaches, because TASK-011 decision 1 makes that true and an athlete who
 *   believed they had consented to one named person would have been misled.
 * - **What is shared is stated concretely.** `contents` names the three check-in
 *   values so consent is informed. Naming the fields is not disclosing a value:
 *   no measurement is read, transported, or cached by this feature.
 * - **Failure wording never implies a state change.** "ยังไม่ได้เริ่มแชร์" and
 *   "การแชร์ยังไม่ถูกหยุด" in `errors.ts` say what did *not* happen.
 */

export const SHARING_COPY = {
  label: "การแชร์ข้อมูล",
  title: "การแชร์เช็กอินรายวัน",
  contents:
    "การเช็กอินรายวันของคุณประกอบด้วยสามอย่าง คือ ความเหนื่อยรวมของวัน (RPE) ความรู้สึกโดยรวม และสถานะว่ามีอาการเจ็บหรือไม่",
  teamScope:
    "การอนุญาตเป็นการให้สิทธิ์แก่ทีม ไม่ใช่โค้ชคนใดคนหนึ่ง เมื่ออนุญาตแล้ว โค้ชทุกคนที่อยู่ในทีมนั้นจะดูข้อมูลได้ รวมถึงโค้ชที่เข้าร่วมทีมในภายหลัง",
  defaultOff:
    "ค่าเริ่มต้นคือไม่แชร์ ระบบจะไม่เปิดการแชร์ให้อัตโนมัติ และคุณหยุดแชร์เมื่อไหร่ก็ได้",
  perTeamHint: "ถ้าคุณอยู่หลายทีม สามารถเลือกอนุญาตแยกกันแต่ละทีมได้",

  loading: "กำลังโหลดการตั้งค่าการแชร์…",

  loadErrorTitle: "โหลดไม่สำเร็จ",
  retry: "ลองโหลดอีกครั้ง",

  emptyTitle: "ยังไม่มีทีมที่ตั้งค่าได้",
  emptyMessage:
    "ตอนนี้คุณยังไม่ได้เป็นนักกีฬาในทีมใด จึงยังไม่มีการแชร์ที่ต้องตั้งค่า เมื่อเข้าร่วมทีมในฐานะนักกีฬาแล้ว ทีมนั้นจะปรากฏที่นี่",

  stateOn: "กำลังแชร์กับทีมนี้",
  stateOff: "ไม่ได้แชร์กับทีมนี้",

  grantAction: "อนุญาตให้ทีมนี้ดูข้อมูล",
  revokeAction: "หยุดแชร์กับทีมนี้",
  working: "กำลังดำเนินการ…",
  waitHint: "กำลังดำเนินการอยู่ กรุณารอให้เสร็จก่อนกดรายการอื่น",

  grantedTitle: "เริ่มแชร์แล้ว",
  grantedMessage:
    "บันทึกการอนุญาตเรียบร้อย สถานะด้านบนแสดงค่าที่ยืนยันจากเซิร์ฟเวอร์แล้ว",
  revokedTitle: "หยุดแชร์แล้ว",
  revokedMessage:
    "หยุดการแชร์เรียบร้อย สถานะด้านบนแสดงค่าที่ยืนยันจากเซิร์ฟเวอร์แล้ว",
  grantErrorTitle: "อนุญาตไม่สำเร็จ",
  revokeErrorTitle: "หยุดแชร์ไม่สำเร็จ",
} as const;

/**
 * The spoken label for a team's action control.
 *
 * A screen reader otherwise hears "อนุญาตให้ทีมนี้ดูข้อมูล" repeated once per
 * team with nothing to tell them apart. The team **name** is spoken, never its
 * identifier.
 */
export function sharingActionAccessibilityLabel(args: {
  readonly teamName: string;
  readonly sharing: boolean;
}): string {
  return args.sharing
    ? `หยุดแชร์การเช็กอินรายวันกับทีม ${args.teamName}`
    : `อนุญาตให้ทีม ${args.teamName} ดูการเช็กอินรายวันของคุณ`;
}

/** The spoken current state, so the row is understandable without the visual. */
export function sharingStateAccessibilityLabel(args: {
  readonly teamName: string;
  readonly sharing: boolean;
}): string {
  return args.sharing
    ? `ทีม ${args.teamName}: กำลังแชร์การเช็กอินรายวัน`
    : `ทีม ${args.teamName}: ไม่ได้แชร์การเช็กอินรายวัน`;
}
