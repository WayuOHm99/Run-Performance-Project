"""คำอธิบายสถานะต้องพูดภาษาเดียวกับการ์ด (ใบงาน #18 เฟส 3)

การ์ดบนแท็บทีมใช้ **รูปทรงวาด** ตั้งแต่ PR #32 เพราะอีโมจิเรนเดอร์ไม่เหมือนกันข้ามเครื่อง
และหายตอนพิมพ์ขาวดำ แต่กล่อง "เกณฑ์ที่ใช้ประเมิน" ที่อธิบายการ์ดพวกนั้น **ยังใช้อีโมจิ**
โค้ชที่เปิดอ่านจึงเห็น 🔴 ในคำอธิบาย แล้วเห็นสามเหลี่ยมบนการ์ด — คนละภาษาในหน้าเดียว
และบนกระดาษขาวดำคำอธิบายจะเหลือช่องว่าง ส่วนการ์ดยังอ่านได้
"""

import datetime
import re
import sys
import unittest
from pathlib import Path

# harness เป็นไฟล์พี่น้องในโฟลเดอร์เดียวกัน — `unittest discover -s tests` ใส่ path นี้ให้เอง
# แต่การเรียกแบบ `python -m unittest tests.<module>` ไม่ใส่ จึงต้องบอกเองเพื่อให้รันได้ทั้งสองท่า
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dashboard_tab_harness import (  # noqa: E402
    LAST_DAY,
    TEAM_TAB_LABEL,
    render_tab,
)

FRESHNESS_LABEL = "ความสด (HRV 7 วัน)"

EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF\U0000FE0F]"
)


def seed_team(conn):
    """นักกีฬาหนึ่งคนที่มีทั้ง wellness และการวิ่ง — พอให้การ์ดทีมและกล่องเกณฑ์ถูกวาด"""
    conn.execute(
        "INSERT INTO dim_athlete (athlete_id, slug, display_name) "
        "VALUES (1, 'tester', 'Tester')"
    )
    for offset in range(30):
        day = (LAST_DAY - datetime.timedelta(days=29 - offset)).isoformat()
        conn.execute(
            "INSERT INTO fact_daily_wellness ("
            " athlete_id, calendar_date, resting_hr, hrv_last_night, sleep_score,"
            " body_battery_high, stress_avg, fetched_at)"
            " VALUES (1, ?, ?, ?, ?, ?, ?, ?)",
            (day, 50, 62, 80, 85, 30, day + "T08:00:00Z"),
        )
    for offset in range(12):
        day = LAST_DAY - datetime.timedelta(days=25 - offset * 2)
        conn.execute(
            "INSERT INTO fact_activity ("
            " activity_id, athlete_id, activity_type, start_time_local, distance_m,"
            " duration_sec, avg_hr, max_hr, avg_pace_min_per_km, training_load,"
            " training_effect_aerobic)"
            " VALUES (?, 1, 'running', ?, 8000, 2880, 132, 150, 6.0, 90, 2.5)",
            (7000 + offset, f"{day.isoformat()} 06:00:00"),
        )


def seed_low_mileage(conn):
    """โปรไฟล์แบบ P'kao — ซ้อม HIIT เป็นหลัก วิ่ง easy ไม่พอคำนวณ EF

    HRV ตกจากฐาน 53 เหลือ 46 ในสัปดาห์สุดท้าย = -13% ซึ่งเป็นเคสจริงเมื่อ 26 ส.ค. 69
    """
    conn.execute(
        "INSERT INTO dim_athlete (athlete_id, slug, display_name) "
        "VALUES (1, 'tester', 'Tester')"
    )
    for offset in range(35):
        day = LAST_DAY - datetime.timedelta(days=34 - offset)
        hrv = 46.0 if offset >= 30 else 53.0
        conn.execute(
            "INSERT INTO fact_daily_wellness ("
            " athlete_id, calendar_date, resting_hr, hrv_last_night, hrv_weekly_avg,"
            " sleep_score, body_battery_high, stress_avg, fetched_at)"
            " VALUES (1, ?, 52, ?, ?, 78, 80, 30, ?)",
            (day.isoformat(), hrv, hrv, day.isoformat() + "T08:00:00Z"),
        )
    for offset in range(14):
        day = LAST_DAY - datetime.timedelta(days=27 - offset * 2)
        conn.execute(
            "INSERT INTO fact_activity ("
            " activity_id, athlete_id, activity_type, start_time_local,"
            " duration_sec, avg_hr, max_hr, training_load, training_effect_aerobic,"
            " hr_zone1_sec, hr_zone2_sec, hr_zone3_sec, hr_zone4_sec, hr_zone5_sec)"
            " VALUES (?, 1, 'hiit', ?, 2400, 150, 180, 110, 3.2, 300, 600, 600, 600, 300)",
            (8000 + offset, f"{day.isoformat()} 18:00:00"),
        )


class TeamLegendMatchesTheCardsTests(unittest.TestCase):
    """เรนเดอร์แท็บทีมจริงแล้วอ่านคำอธิบายที่โค้ชกางออกมาอ่าน"""

    @classmethod
    def setUpClass(cls):
        cls.tab, _ = render_tab(TEAM_TAB_LABEL, seed_team)

    def _legend(self):
        blocks = [
            element.value for element in self.tab.get("markdown")
            if element.value and "**สถานะ:**" in element.value
        ]
        self.assertTrue(blocks, "ไม่เจอกล่องเกณฑ์ที่ใช้ประเมิน — ข้อมูลทดสอบไม่พอ")
        return blocks[0]

    def test_the_legend_does_not_explain_shapes_with_emoji(self):
        """คำอธิบายต้องใช้สัญลักษณ์เดียวกับที่การ์ดวาดจริง"""
        legend = self._legend()
        found = EMOJI.findall(legend)
        self.assertEqual(
            [], found,
            f"คำอธิบายยังใช้อีโมจิ {found} ขณะที่การ์ดใช้รูปทรงวาด",
        )

    def test_the_legend_still_names_every_status(self):
        """ยามคู่กับข้อบน — ตัดอีโมจิได้ แต่ต้องยังบอกครบว่ามีสถานะอะไรบ้าง"""
        legend = self._legend()
        for status in ("ต้องพัก", "เฝ้าระวัง", "พร้อมซ้อม", "ข้อมูลไม่พอ"):
            self.assertIn(
                status, legend,
                f"คำอธิบายไม่ได้พูดถึงสถานะ {status!r} แล้ว",
            )

    def test_the_team_table_shows_words_not_emoji_keys(self):
        """ตารางทีมเป็นข้อความล้วนที่คนอ่าน — คีย์ภายในต้องถูกถอดออกก่อนถึงตา

        เทสนี้ต้องใช้ ``AppTest`` เท่านั้น: ``st.dataframe`` วาดบน canvas
        การกวาด ``textContent`` ในเบราว์เซอร์จึงมองไม่เห็นเนื้อในตารางเลย
        และจะรายงานว่า "ไม่มีอีโมจิ" ทั้งที่โค้ชเห็นอยู่
        """
        frames = self.tab.get("dataframe")
        self.assertTrue(frames, "ไม่เจอตารางทีม — ข้อมูลทดสอบไม่พอ เทสจะเขียวหลอก")

        offenders = []
        for frame in frames:
            data = frame.value
            for column in data.columns:
                for cell in data[column]:
                    if isinstance(cell, str) and EMOJI.search(cell):
                        offenders.append(f"{column}: {cell}")
        self.assertEqual(
            [], offenders,
            "ตารางทีมยังโชว์อีโมจิ:\n" + "\n".join(f"- {o}" for o in offenders),
        )


def seed_runner_with_hrv(conn):
    """นักวิ่งที่มีรัน easy พอคำนวณ EF **และ** มี hrv_weekly_avg ครบ

    HR สูงสุด 190 ทำให้ LTHR ที่ระบบประมาณเป็น 169 → เพดาน easy 150 bpm
    รันที่ avg_hr 130 จึงนับเป็น easy ครบทุกครั้ง
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
            " VALUES (1, ?, 52, 55, 55, 78, 80, 30, ?)",
            (day.isoformat(), day.isoformat() + "T08:00:00Z"),
        )
    for offset in range(14):
        day = LAST_DAY - datetime.timedelta(days=26 - offset * 2)
        conn.execute(
            "INSERT INTO fact_activity ("
            " activity_id, athlete_id, activity_type, start_time_local, distance_m,"
            " duration_sec, avg_hr, max_hr, avg_pace_min_per_km, training_effect_aerobic,"
            " hr_zone1_sec, hr_zone2_sec, hr_zone3_sec, hr_zone4_sec, hr_zone5_sec)"
            " VALUES (?, 1, 'running', ?, 8000, 2880, 130, 190, 6.0, 2.5,"
            " 1200, 1200, 300, 120, 60)",
            (9000 + offset, f"{day.isoformat()} 06:00:00"),
        )


class LowMileageAthleteStillGetsAFreshnessNumberTests(unittest.TestCase):
    """นักกีฬาที่วิ่งน้อยต้องไม่ค้าง "ข้อมูลไม่พอ" ถาวรบนการ์ด

    EF ต้องการรัน easy >= 5 ครั้งใน 28 วัน — P'kao มี 2 การ์ดของคนที่ใช้นาฬิกาดีที่สุด
    จึงไม่เคยมีตัวเลขความสดให้โค้ชติดตามเลย
    """

    @classmethod
    def setUpClass(cls):
        cls.tab, _ = render_tab(TEAM_TAB_LABEL, seed_low_mileage)

    def _card_html(self):
        """HTML ของการ์ด — ไม่ใช่บล็อก CSS ที่นิยามคลาสเดียวกัน

        เทสรอบแรกเทียบกับ markdown ทุกก้อนรวมกันแล้วเขียวทันทีโดยยังไม่ได้ทำอะไร
        เพราะไปแมตช์ "โหลด 7 วัน -13% จากฐาน" ที่มีอยู่เดิม — ต้องเจาะจงถึงจะเป็นยามจริง
        """
        blocks = [
            element.value for element in self.tab.get("markdown")
            if element.value and "team-card__val" in element.value
            and "<style>" not in element.value
        ]
        self.assertTrue(blocks, "ไม่เจอ HTML ของการ์ดทีม")
        return blocks[0]

    def test_the_card_shows_an_hrv_number_when_ef_cannot_be_computed(self):
        card = self._card_html()
        self.assertIn(
            FRESHNESS_LABEL, card,
            f"การ์ดไม่มีช่อง {FRESHNESS_LABEL!r} ทั้งที่ EF คำนวณไม่ได้ — "
            "โค้ชจึงไม่มีตัวเลขความสดให้ติดตามเลย",
        )
        self.assertRegex(
            card, r"-1[23](\.[0-9])?%",
            "ช่องความสดไม่ได้แสดง % ที่ HRV ต่างจากฐาน "
            "(ข้อมูลทดสอบตั้งไว้ที่ 46 เทียบฐาน 53 = -13.2%)",
        )

    def test_an_athlete_with_enough_easy_runs_still_sees_ef(self):
        """ตัวแทนต้องขึ้นเฉพาะตอน EF เงียบ ไม่ใช่มาแทนที่ EF ของทุกคน

        ข้อมูลทดสอบต้องมี **ทั้ง** รัน easy พอคำนวณ EF และ ``hrv_weekly_avg`` ครบ —
        รอบแรกเทสนี้ผ่านทั้งที่โค้ดผิด เพราะชุดข้อมูลไม่มี ``hrv_weekly_avg`` เลย
        ตัวแทนจึงเงียบด้วยเหตุผลคนละเรื่องกับที่เทสอ้าง
        """
        tab, _ = render_tab(TEAM_TAB_LABEL, seed_runner_with_hrv)
        card = [
            element.value for element in tab.get("markdown")
            if element.value and "team-card__val" in element.value
            and "<style>" not in element.value
        ][0]
        self.assertIn(
            "ประสิทธิภาพวิ่งเบา", card,
            "คนที่มีรัน easy พอกลับไม่เห็น EF",
        )
        self.assertNotIn(
            FRESHNESS_LABEL, card,
            "คนที่มีรัน easy พอ (และมี HRV ครบ) กลับถูกเปลี่ยนไปใช้ตัวแทน",
        )


if __name__ == "__main__":
    unittest.main()
