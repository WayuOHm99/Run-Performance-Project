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


if __name__ == "__main__":
    unittest.main()
