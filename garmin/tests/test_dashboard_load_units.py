"""โหลด 7 วันของสามคนอยู่คอลัมน์เดียว แต่มาคนละหน่วยตามรุ่นนาฬิกา

วัดจริง 27 ส.ค. 69: Tong 32.7 km · Dan 92.6 km · P'kao 323 TL — หน่วยกำกับครบและ
ไม่มีตัวเลขไหนผิด แต่ 92.6 กับ 323 วางติดกันในคอลัมน์เดียว ตาอ่านว่า "P'kao หนักกว่า
Dan 3.5 เท่า" ทั้งที่คนละมาตรวัด (Garmin ``training_load`` vs ระยะวิ่ง)

หลัง audit 27 ส.ค. ระบบไม่หาร 7/28 วันเป็น ACWR-like percent อีก จึงคุมให้แสดงค่าดิบ
สองช่วงแยกกันพร้อมหน่วย และไม่ทำให้วันที่ไม่มี ``training_load`` หายเงียบ
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


# การคำนวณกับชิ้นส่วนหน้าตาอยู่ใน dashboard_domain.py / dashboard_view.py แล้ว
# จึง import ได้ตรง ๆ ไม่ต้อง ast.parse + exec ทีละ node เหมือนเดิม
from dashboard_modules import HELPERS  # noqa: E402

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


class SessionCountMeansDifferentThingsPerAthlete(unittest.TestCase):
    """คนที่ fallback เป็นระยะวิ่งนับเฉพาะการวิ่ง คนที่ใช้ TL นับทุกกิจกรรม"""

    def test_scope_names_what_the_session_count_actually_counted(self):
        scope = HELPERS["load_session_scope"]

        self.assertEqual(scope("training_load"), "ทุกกิจกรรม")
        self.assertEqual(scope("ระยะวิ่ง"), "วิ่ง")


class ContextLineKeepsTheTwoWindowsSeparate(unittest.TestCase):
    def test_current_and_rolling_load_are_both_named_with_units(self):
        line = HELPERS["load_context_line"]("92.6 km", "85.0 km/สัปดาห์", 15, "วิ่ง")

        self.assertIn("92.6 km", line)
        self.assertIn("เฉลี่ย 28 วัน 85.0 km/สัปดาห์", line)
        self.assertNotIn("%", line)
        self.assertIn("15 เซสชัน", line)
        self.assertIn("วิ่ง", line)

    def test_a_missing_rolling_window_says_so(self):
        line = HELPERS["load_context_line"]("92.6 km", "–", 15, "ทุกกิจกรรม")

        self.assertIn("ยังไม่มีค่าเฉลี่ย 28 วัน", line)
        self.assertIn("92.6 km", line)


class TeamCardShowsBothNumbersInTheRightOrder(unittest.TestCase):
    ROW = {
        "นักกีฬา": "Tong",
        "สถานะ": "🟡 ควรทบทวนก่อนซ้อม",
        "pace–HR trend": "+2% จากฐาน 28 วัน",
        "สถานะ pace–HR": "🔵 แนวโน้มประกอบ",
        "โหลด 7 วัน": "32.6 km",
        "ค่าเฉลี่ยโหลด 28 วัน": "29.4 km/สัปดาห์",
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

    def test_the_card_shows_both_windows_without_a_ratio(self):
        line = self._load_line(self.ROW)

        self.assertIn("32.6 km", line)
        self.assertIn("29.4 km/สัปดาห์", line)
        self.assertNotIn("%", line)

    def test_the_card_says_which_sessions_it_counted(self):
        # 5 เซสชันของคนที่นับเฉพาะวิ่ง ไม่ใช่ของเดียวกับ 5 เซสชันของคนที่นับทุกกิจกรรม
        self.assertIn("วิ่ง", self._load_line(self.ROW))
        self.assertIn(
            "ทุกกิจกรรม",
            self._load_line(dict(self.ROW, **{"ขอบเขตโหลด": "ทุกกิจกรรม"})),
        )

    def test_the_card_says_it_does_not_compute_a_risk_ratio(self):
        self.assertIn("ไม่คำนวณอัตราส่วนเสี่ยง", self._load_line(self.ROW))


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
        self.assertIn("ไม่หารเป็น ACWR", notes[0])


def seed_watch_dropped(conn):
    """นักกีฬาที่ **เลิกใช้** นาฬิกาที่ให้ ``training_load`` เมื่อ 7 วันก่อน

    ทิศตรงข้ามของ ``seed_watch_change`` — วิ่งเท่ากันทุกวันตลอด 42 วันเหมือนกัน
    แต่ 7 วันหลังสุดไม่มี TL ติดมา ถ้าระบบยังยืนยันจะรวมเฉพาะแถวที่มี TL
    ผลรวม 7 วันจะเป็น 0 แล้วหน้าจอขึ้นว่า "หยุดซ้อม" ทั้งที่ซ้อมทุกวัน
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
        load = None if (LAST_DAY - day).days <= 6 else 90
        conn.execute(
            "INSERT INTO fact_activity ("
            " activity_id, athlete_id, activity_type, start_time_local, distance_m,"
            " duration_sec, avg_hr, max_hr, avg_pace_min_per_km, training_load,"
            " training_effect_aerobic)"
            " VALUES (?, 1, 'running', ?, 8000, 2880, 132, 150, 6.0, ?, 2.5)",
            (7100 + offset, f"{day.isoformat()} 06:00:00", load),
        )


class LoadFollowsTheWatchTheAthleteUsesNow(unittest.TestCase):
    """เลิกใช้นาฬิกาที่ให้ TL แล้วต้องถอยไปใช้ระยะวิ่ง ไม่ใช่รายงานว่าหยุดซ้อม"""

    @classmethod
    def setUpClass(cls):
        cls.tab, _ = render_tab(TEAM_TAB_LABEL, seed_watch_dropped)

    def _card(self):
        for element in self.tab.get("markdown"):
            # ต้องเจาะจงถึง markup ของการ์ด ไม่งั้นไปแมตช์สไตล์ชีตที่ประกาศคลาสเดียวกัน
            if element.value and 'class="team-card__load"' in element.value:
                return element.value
        raise AssertionError("ไม่เจอการ์ดทีม — ข้อมูลทดสอบไม่พอ")

    def _load_line(self):
        return LOAD_LINE.search(self._card()).group(1)

    def test_a_watch_that_stopped_reporting_does_not_read_as_a_stopped_athlete(self):
        # ซ้อมทุกวันตลอด 42 วัน ตัวเลขที่ถูกคือปริมาณจริง ไม่ใช่ 0 และไม่ใช่ -100%
        line = self._load_line()
        self.assertNotIn("0 TL", line)
        self.assertNotIn("-100%", line)
        self.assertNotIn("0 เซสชัน", line)

    def test_the_load_falls_back_to_the_distance_every_watch_reports(self):
        line = self._load_line()
        self.assertIn("km", line)
        self.assertIn("วิ่ง", line)

    def test_the_status_does_not_drop_to_missing_data_while_the_runs_are_there(self):
        card = self._card()
        self.assertNotIn("ข้อมูลไม่พอ", card)
        self.assertNotIn("ไม่มีข้อมูล", card)


if __name__ == "__main__":
    unittest.main()
