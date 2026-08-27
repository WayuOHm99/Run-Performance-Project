"""โหลด 7 วันของสามคนอยู่คอลัมน์เดียว แต่มาคนละหน่วยตามรุ่นนาฬิกา

วัดจริง 27 ส.ค. 69: Tong 32.7 km · Dan 92.6 km · P'kao 323 TL — หน่วยกำกับครบและ
ไม่มีตัวเลขไหนผิด แต่ 92.6 กับ 323 วางติดกันในคอลัมน์เดียว ตาอ่านว่า "P'kao หนักกว่า
Dan 3.5 เท่า" ทั้งที่คนละมาตรวัด (Garmin ``training_load`` vs ระยะวิ่ง)

ตัวที่เทียบข้ามคนได้จริงคือ **% เทียบฐาน 28 วันของตัวเอง** เพราะแต่ละคนเทียบกับตัวเอง
ไฟล์นี้จึงคุมสองข้อ: ตัวเทียบได้ต้องมาก่อนตัวดิบ · และฐานที่เอามาหารต้องไม่ถูกเจือจาง
ด้วยวันก่อนที่นาฬิกาจะเริ่มให้ ``training_load``
"""

import ast
import datetime
import html
import re
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dashboard_tab_harness import (  # noqa: E402
    LAST_DAY,
    TEAM_TAB_LABEL,
    render_tab,
)

DASHBOARD_PATH = Path(__file__).resolve().parent.parent / "scripts" / "dashboard.py"
DASHBOARD_SRC = DASHBOARD_PATH.read_text(encoding="utf-8")


def extract_helpers(*names):
    """รันเฉพาะ constant กับ def ที่ต้องใช้ โดยไม่ต้องแตะ streamlit หรือฐานข้อมูล"""
    tree = ast.parse(DASHBOARD_SRC)
    wanted = set(names)
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in wanted:
            nodes.append(node)
        elif isinstance(node, ast.Assign):
            targets = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if targets & wanted:
                nodes.append(node)
    namespace = {"pd": pd, "datetime": datetime, "html": html, "float": float}
    exec(
        compile(ast.Module(body=nodes, type_ignores=[]), "dashboard.py", "exec"),
        namespace,
    )
    return namespace


HELPERS = extract_helpers(
    "load_volume_display",
    "load_baseline_display",
    "load_session_scope",
    "load_context_line",
    "STATUS_COLORS",
    "STATUS_TEXT_COLORS",
    "TREND_KEY_BY_LABEL",
    "STATUS_SHAPES",
    "C_CRIT",
    "C_WARN",
    "C_GOOD",
    "C_BLUE",
    "status_parts",
    "status_shape_svg",
    "_num_text",
    "render_team_card",
)

LOAD_LINE = re.compile(r'<div class="team-card__load">(.*?)</div>', re.S)


class LoadVolumeIsOnlyReadableAgainstItself(unittest.TestCase):
    """ตัวเลขดิบต้องพกหน่วยของตัวเองเสมอ — หน่วยคือสิ่งเดียวที่กันการเทียบข้ามคน"""

    def test_volume_keeps_the_unit_the_watch_actually_gave(self):
        volume = HELPERS["load_volume_display"]

        self.assertEqual(volume(711.0, "training_load", "TL"), "711 TL")
        self.assertEqual(volume(64.1, "ระยะวิ่ง", "km"), "64.1 km")

    def test_missing_volume_shows_a_dash_instead_of_a_number_it_never_had(self):
        volume = HELPERS["load_volume_display"]

        self.assertEqual(volume(float("nan"), "ระยะวิ่ง", "km"), "–")


class BaselineIsTheOnlyCrossAthleteNumber(unittest.TestCase):
    """% เทียบฐานตัวเองอ่านข้ามคนได้ เพราะทุกคนหารด้วยฐานของตัวเอง"""

    def test_baseline_reports_the_direction_without_any_unit(self):
        baseline = HELPERS["load_baseline_display"]

        self.assertEqual(baseline(711.0, 515.0), "+38%")
        self.assertEqual(baseline(64.1, 54.3), "+18%")
        self.assertEqual(baseline(40.0, 50.0), "-20%")

    def test_no_baseline_yet_is_a_dash_not_a_zero_percent(self):
        # 0% แปลว่า "ทำเท่าฐานเป๊ะ" ซึ่งคนละเรื่องกับ "ยังไม่มีฐานให้เทียบ"
        baseline = HELPERS["load_baseline_display"]

        self.assertEqual(baseline(64.1, float("nan")), "–")
        self.assertEqual(baseline(64.1, 0.0), "–")
        self.assertEqual(baseline(float("nan"), 54.3), "–")


class SessionCountMeansDifferentThingsPerAthlete(unittest.TestCase):
    """คนที่ fallback เป็นระยะวิ่งนับเฉพาะการวิ่ง คนที่ใช้ TL นับทุกกิจกรรม"""

    def test_scope_names_what_the_session_count_actually_counted(self):
        scope = HELPERS["load_session_scope"]

        self.assertEqual(scope("training_load"), "ทุกกิจกรรม")
        self.assertEqual(scope("ระยะวิ่ง"), "วิ่ง")


class ContextLineLeadsWithTheComparableNumber(unittest.TestCase):
    def test_the_baseline_percent_comes_before_the_raw_volume(self):
        line = HELPERS["load_context_line"]("+25%", "92.6 km", 15, "วิ่ง")

        self.assertLess(line.index("+25%"), line.index("92.6 km"))
        self.assertIn("15 เซสชัน", line)
        self.assertIn("วิ่ง", line)

    def test_a_missing_baseline_says_so_instead_of_leading_with_a_dash(self):
        line = HELPERS["load_context_line"]("–", "92.6 km", 15, "ทุกกิจกรรม")

        self.assertIn("ยังไม่มีฐาน 28 วัน", line)
        self.assertIn("92.6 km", line)
        self.assertNotIn("– จากฐาน", line)


class TeamCardShowsBothNumbersInTheRightOrder(unittest.TestCase):
    ROW = {
        "นักกีฬา": "Tong",
        "สถานะ": "🟡 เฝ้าระวัง",
        "ประสิทธิภาพการวิ่งเบา (EF)": "+2% จากฐาน 28 วัน",
        "โซน EF": "🟢 ปกติ",
        "โหลด 7 วัน": "32.6 km",
        "เทียบฐานตัวเอง": "-12%",
        "ขอบเขตโหลด": "วิ่ง",
        "เซสชัน 7 วัน": 5,
        "Sleep": 78.0,
        "RHR": 41.0,
        "ΔRHR": "-5",
        "HRV คืนล่าสุด": "123 ms · UNBALANCED",
        "Body Battery ตอนนี้/ล่าสุด": 89.0,
        "ความสดรายค่า": "BB 25/08 · Sleep 25/08",
        "ธงเฝ้าระวัง": "HRV UNBALANCED",
    }

    def _load_line(self, row):
        markup = HELPERS["render_team_card"](dict(row))
        found = LOAD_LINE.search(markup)
        self.assertIsNotNone(found, "การ์ดไม่มีบรรทัดโหลด 7 วันแล้ว")
        return found.group(1)

    def test_the_card_leads_with_the_number_that_survives_a_cross_athlete_read(self):
        line = self._load_line(self.ROW)

        self.assertLess(line.index("-12%"), line.index("32.6 km"))

    def test_the_card_says_which_sessions_it_counted(self):
        # 5 เซสชันของคนที่นับเฉพาะวิ่ง ไม่ใช่ของเดียวกับ 5 เซสชันของคนที่นับทุกกิจกรรม
        self.assertIn("วิ่ง", self._load_line(self.ROW))
        self.assertIn(
            "ทุกกิจกรรม",
            self._load_line(dict(self.ROW, **{"ขอบเขตโหลด": "ทุกกิจกรรม"})),
        )

    def test_the_card_still_calls_the_load_line_context_not_a_verdict(self):
        # ยามของกฎเดิม: ตัวเลขนี้ไม่ตัดสินสถานะ และบรรทัดนี้ต้องพูดแบบนั้นต่อไป
        self.assertIn("บริบท", self._load_line(self.ROW))


def seed_watch_change(conn):
    """นักกีฬาที่เพิ่งเปลี่ยนมาใช้นาฬิกาที่ให้ ``training_load`` เมื่อ 13 วันก่อน

    วิ่งสม่ำเสมอมา 42 วันเท่ากันทุกวัน แต่ 29 วันแรกไม่มี TL ติดมาด้วย
    ถ้าฐาน 28 วันไปเริ่มนับที่กิจกรรมแรก วันก่อนเปลี่ยนนาฬิกาจะถูกอ่านเป็น "วันพัก"
    แล้วฐานจะต่ำเกินจริง → หน้าจอขึ้นว่าซ้อมหนักขึ้นมหาศาลทั้งที่ทำเท่าเดิมทุกวัน
    """
    conn.execute(
        "INSERT INTO dim_athlete (athlete_id, slug, display_name) "
        "VALUES (1, 'tester', 'Tester')"
    )
    for offset in range(35):
        day = LAST_DAY - datetime.timedelta(days=34 - offset)
        conn.execute(
            "INSERT INTO fact_daily_wellness ("
            " athlete_id, calendar_date, resting_hr, hrv_last_night, hrv_weekly_avg,"
            " sleep_score, body_battery_high, stress_avg, fetched_at)"
            " VALUES (1, ?, 50, 62, 62, 80, 85, 30, ?)",
            (day.isoformat(), day.isoformat() + "T08:00:00Z"),
        )
    for offset in range(42):
        day = LAST_DAY - datetime.timedelta(days=41 - offset)
        days_ago = (LAST_DAY - day).days
        load = 90 if days_ago <= 13 else None
        conn.execute(
            "INSERT INTO fact_activity ("
            " activity_id, athlete_id, activity_type, start_time_local, distance_m,"
            " duration_sec, avg_hr, max_hr, avg_pace_min_per_km, training_load,"
            " training_effect_aerobic)"
            " VALUES (?, 1, 'running', ?, 8000, 2880, 132, 150, 6.0, ?, 2.5)",
            (7000 + offset, f"{day.isoformat()} 06:00:00", load),
        )


class BaselineIsNotDilutedByDaysTheWatchNeverReported(unittest.TestCase):
    """เรนเดอร์แท็บทีมจริงกับนักกีฬาที่เพิ่งเปลี่ยนนาฬิกากลางคัน"""

    @classmethod
    def setUpClass(cls):
        cls.tab, _ = render_tab(TEAM_TAB_LABEL, seed_watch_change)

    def _load_line(self):
        for element in self.tab.get("markdown"):
            found = LOAD_LINE.search(element.value or "")
            if found:
                return found.group(1)
        raise AssertionError("ไม่เจอบรรทัดโหลดบนการ์ดทีม — ข้อมูลทดสอบไม่พอ")

    def test_a_watch_change_does_not_invent_a_training_spike(self):
        # ซ้อมเท่ากันทุกวันตลอด 42 วัน ทิศทางที่ถูกคือ "เท่าเดิม" หรือ "ยังไม่มีฐาน"
        # ห้ามเป็นบวกสองหลักขึ้นไป ซึ่งคือสิ่งที่ได้ถ้าฐานนับวันก่อนเปลี่ยนนาฬิกาเป็น 0
        line = self._load_line()
        spikes = [value for value in re.findall(r"\+(\d+)%", line) if int(value) >= 10]
        self.assertEqual(
            [], spikes,
            f"ฐาน 28 วันถูกเจือจางด้วยวันที่นาฬิกายังไม่ให้ TL: {line!r}",
        )

    def test_the_legend_warns_that_the_raw_numbers_are_not_comparable(self):
        # โค้ชที่กางกล่องเกณฑ์ต้องอ่านเจอว่าหน่วยมาจากไหน ไม่งั้นตัวเลขดิบสองคน
        # ที่วางเรียงกันจะถูกอ่านว่าเทียบกันได้
        notes = [
            element.value for element in self.tab.get("markdown")
            if element.value and "โหลด 7 วัน" in element.value
            and "รุ่นนาฬิกา" in element.value
        ]
        self.assertTrue(
            notes,
            "แท็บทีมไม่ได้บอกว่าหน่วยของโหลดขึ้นกับรุ่นนาฬิกา",
        )
        self.assertIn("เทียบฐานตัวเอง", notes[0])


if __name__ == "__main__":
    unittest.main()
