"""Guardrails for the Garmin-only dashboard policy approved on 27 Aug 2026."""

import ast
import unittest
from pathlib import Path


import sys

GARMIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dashboard_modules import ALL_SRC as DASHBOARD_SRC  # noqa: E402

# นโยบายนี้คุมทั้ง dashboard ไม่ใช่แค่ไฟล์เดียว — การคำนวณอยู่ dashboard_domain.py
# และชิ้นส่วนหน้าตาอยู่ dashboard_view.py ตั้งแต่แยกโมดูล ยามจึงต้องอ่านครบทั้งสาม
DASHBOARD_PATH = GARMIN_ROOT / "scripts" / "dashboard.py"
PROJECT_SRC = (GARMIN_ROOT.parent / "docs" / "PROJECT.md").read_text(encoding="utf-8")


class GarminOnlyDashboardPolicyTests(unittest.TestCase):
    def test_policy_is_recorded_as_the_approved_source_of_truth(self):
        for statement in (
            "นโยบาย Garmin-only ที่อนุมัติ 27 ส.ค. 69",
            "ไม่มีแบบฟอร์ม",
            "ไม่สร้างคะแนนความสด/readiness รวมของตัวเอง",
            "ไม่สั่งพัก ลดโหลด เพิ่มโหลด",
            "ถามปากเปล่า",
        ):
            self.assertIn(statement, PROJECT_SRC)

    def test_dashboard_has_no_manual_health_or_training_entry_widgets(self):
        """Selection/date controls are filters; free-form/editable widgets are not allowed."""
        forbidden = {
            "form", "form_submit_button", "data_editor", "text_input", "text_area",
            "number_input", "slider", "toggle", "checkbox",
        }
        calls = []
        for node in ast.walk(ast.parse(DASHBOARD_SRC)):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "st" and node.func.attr in forbidden):
                calls.append((node.func.attr, node.lineno))
        self.assertEqual([], calls, f"พบ widget สำหรับกรอกข้อมูล: {calls}")

    def test_dashboard_database_connection_is_read_only(self):
        self.assertIn("?mode=ro", DASHBOARD_SRC)
        for sql_write in ("INSERT INTO", "UPDATE fact_", "DELETE FROM", "CREATE TABLE"):
            self.assertNotIn(sql_write, DASHBOARD_SRC)

    def test_no_custom_composite_freshness_score_is_defined(self):
        identifiers = {
            node.id.lower() for node in ast.walk(ast.parse(DASHBOARD_SRC))
            if isinstance(node, ast.Name)
        }
        forbidden = {
            "freshness_score", "readiness_score", "composite_readiness",
            "daily_readiness_score", "recovery_score",
        }
        self.assertEqual(set(), identifiers & forbidden)

    def test_team_status_never_returns_an_automatic_training_instruction(self):
        tree = ast.parse(DASHBOARD_SRC)
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "team_status"
        )
        returned = [
            node.value.value for node in ast.walk(function)
            if (isinstance(node, ast.Return) and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str))
        ]
        joined = " ".join(returned)
        for instruction in ("ต้องพัก", "ลดโหลด", "เพิ่มโหลด", "พร้อมซ้อม"):
            self.assertNotIn(instruction, joined)

    def test_dashboard_tells_the_coach_to_check_symptoms_verbally(self):
        self.assertIn("ถามปากเปล่าเรื่องอาการเจ็บ ป่วย", DASHBOARD_SRC)
        self.assertIn("ไม่ใช่คำอนุญาตให้ซ้อม", DASHBOARD_SRC)


if __name__ == "__main__":
    unittest.main()
