"""ยามของนโยบาย Garmin-only

อนุมัติ 27 ส.ค. 69 (ไม่มีแบบฟอร์ม ไม่มีคะแนนรวม ไม่สั่งซ้อม) และขยาย 30 ก.ย. 69:
**ไม่มีสูตรคำนวณของระบบเองเลย** — ไม่มี LTHR/VDOT, ไม่มี pace–HR, ไม่มีเทรนด์เทียบฐาน,
ไม่มีธงสถานะที่ระบบตัดสิน ค่าบนจอคือค่าที่ Garmin ส่งมา จัดรูปแบบแล้วเท่านั้น
ข้อความบนจอตรวจที่ ``test_dashboard_pages.py`` ส่วนไฟล์นี้ตรวจซอร์ส
"""

import ast
import sys
import unittest
from pathlib import Path

GARMIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dashboard_modules import ALL_SRC as DASHBOARD_SRC  # noqa: E402

PROJECT_SRC = (GARMIN_ROOT.parent / "docs" / "PROJECT.md").read_text(encoding="utf-8")
TREE = ast.parse(DASHBOARD_SRC)

FORBIDDEN_NAMES = {
    "lthr_by_slug", "get_lthr", "easy_max_pct", "gray_max_pct", "classify_intensity",
    "efficiency_factor", "easy_run_efficiency", "hrv_trend_summary", "baseline_median",
    "compute_load_windows", "team_status", "freshness_score", "readiness_score",
    "composite_readiness", "recovery_score", "vdot",
}


def invented_names(source):
    """ชื่อตัวแปร/ฟังก์ชันใน ``source`` ที่ตรงกับสูตรที่ถูกถอดออก"""
    tree = ast.parse(source)
    names = {node.id.lower() for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names |= {node.name.lower() for node in ast.walk(tree)
              if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return names & FORBIDDEN_NAMES


class GarminOnlyDashboardPolicyTests(unittest.TestCase):
    def test_policy_is_recorded_as_the_approved_source_of_truth(self):
        for statement in (
            "นโยบาย Garmin-only ที่อนุมัติ 27 ส.ค. 69",
            "ไม่มีแบบฟอร์ม",
            "ไม่มีสูตรคำนวณของระบบเอง",
            "ถามปากเปล่า",
        ):
            self.assertIn(statement, PROJECT_SRC)

    def test_dashboard_has_no_manual_health_or_training_entry_widgets(self):
        """ตัวเลือกนักกีฬา/ช่วงวันที่คือ filter — ช่องกรอกข้อมูลไม่อนุญาต"""
        forbidden = {
            "form", "form_submit_button", "data_editor", "text_input", "text_area",
            "number_input", "slider", "toggle", "checkbox", "chat_input", "file_uploader",
        }
        calls = [
            (node.func.attr, node.lineno) for node in ast.walk(TREE)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "st"
            and node.func.attr in forbidden
        ]
        self.assertEqual([], calls, f"พบ widget สำหรับกรอกข้อมูล: {calls}")

    def test_dashboard_database_connection_is_read_only(self):
        self.assertIn("?mode=ro", DASHBOARD_SRC)
        for sql_write in ("INSERT INTO", "UPDATE fact_", "DELETE FROM", "CREATE TABLE"):
            self.assertNotIn(sql_write, DASHBOARD_SRC)

    def test_no_model_or_threshold_of_our_own_is_defined(self):
        """ชื่อของสูตรที่ถูกถอดออก — ถ้ากลับมาต้องผ่านการอนุมัติใหม่ ไม่ใช่เล็ดลอดเข้ามา"""
        self.assertEqual(set(), invented_names(DASHBOARD_SRC))

    def test_the_guard_above_actually_catches_a_reintroduced_formula(self):
        """ยามที่แดงไม่เป็นคือยามที่ไม่มีอยู่ (CLAUDE.md) — ลองใส่สูตรกลับเข้าไปแล้วต้องจับได้"""
        planted = DASHBOARD_SRC + (
            "\nLTHR_BY_SLUG = {}\n"
            "def classify_intensity(hr, lthr):\n"
            "    pass\n"
        )
        self.assertEqual({"lthr_by_slug", "classify_intensity"}, invented_names(planted))

    def test_dashboard_tells_the_coach_to_ask_the_athlete(self):
        self.assertIn("ก่อนซ้อมต้องถามอาการเจ็บ ป่วย และความล้าจากนักกีฬาเอง", DASHBOARD_SRC)


if __name__ == "__main__":
    unittest.main()
