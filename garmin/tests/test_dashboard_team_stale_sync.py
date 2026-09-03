"""การ์ดทีมต้องบอกเองเมื่อนาฬิกาของใครยังไม่ส่งข้อมูลของวันนี้มาเลย

เคสจริง 3 ก.ย. 69: ต้องอัปโหลดครั้งสุดท้ายเมื่อ 2 ก.ย. 09:15 น. แถว wellness ของ
วันที่ 3 มีอยู่แต่ว่างทั้งแถว (ยิง Garmin API ยืนยันแล้วว่าฝั่งต้นทางก็ไม่มี)
ค่าหลักทั้งสี่จึงเป็นของเมื่อวานทั้งชุด — ซึ่งเกณฑ์ "สด" ของการ์ด (อายุ ≤1 วัน)
ยังนับว่าสด การ์ดจึงขึ้นเขียวเท่ากับคนที่ sync มาแล้วเช้านี้ ต่างกันแค่บรรทัด
วันที่ตัวเล็กสีเทา โค้ชที่กวาดตาผ่านหน้าทีมตอนบ่ายจึงมองไม่เห็นว่ามีคนหายไปทั้งวัน

ป้ายนี้ **ไม่เปลี่ยนสถานะ** — สถานะยังตอบคำถามเดิมว่าอุปกรณ์เจอสัญญาณให้ทบทวนไหม
ป้ายตอบคนละคำถาม: ตัวเลขที่กำลังอ่านอยู่นี้เป็นของวันไหน
"""

import datetime
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dashboard_tab_harness import (  # noqa: E402
    LAST_DAY,
    TEAM_TAB_LABEL,
    render_tab,
)

YESTERDAY = LAST_DAY - datetime.timedelta(days=1)


def _seed_athlete(conn, athlete_id, name, last_wellness_day):
    """นักกีฬาหนึ่งคนที่มีทั้งการวิ่งและ wellness ครบ จนถึง ``last_wellness_day``

    ต้องมี workload ด้วย ไม่งั้น ``team_status`` ตกไปเป็น "ข้อมูลไม่พอ" แล้วเทส
    จะพิสูจน์ไม่ได้ว่าป้ายขึ้นโดยที่สถานะยังเขียวอยู่
    """
    conn.execute(
        "INSERT INTO dim_athlete (athlete_id, slug, display_name) VALUES (?, ?, ?)",
        (athlete_id, name.lower(), name),
    )
    day = last_wellness_day - datetime.timedelta(days=29)
    while day <= last_wellness_day:
        conn.execute(
            "INSERT INTO fact_daily_wellness ("
            " athlete_id, calendar_date, resting_hr, hrv_last_night, hrv_weekly_avg,"
            " hrv_status, sleep_score, body_battery_high, bb_most_recent, stress_avg,"
            " fetched_at)"
            " VALUES (?, ?, 50, 62, 60, 'BALANCED', 80, 85, 70, 30, ?)",
            (athlete_id, day.isoformat(), day.isoformat() + "T08:00:00Z"),
        )
        day += datetime.timedelta(days=1)
    for offset in range(12):
        run_day = LAST_DAY - datetime.timedelta(days=25 - offset * 2)
        conn.execute(
            "INSERT INTO fact_activity ("
            " activity_id, athlete_id, activity_type, start_time_local, distance_m,"
            " duration_sec, avg_hr, max_hr, avg_pace_min_per_km, training_load,"
            " training_effect_aerobic)"
            " VALUES (?, ?, 'running', ?, 8000, 2880, 132, 150, 6.0, 90, 2.5)",
            (athlete_id * 1000 + offset, athlete_id, f"{run_day.isoformat()} 06:00:00"),
        )


def seed_mixed_team(conn):
    """ทีมจริงมีหลายคน — คนที่ sync แล้วกับคนที่ยังไม่ sync อยู่ในหน้าเดียวกัน

    ต้องปั้นทั้งสองคนในรอบเดียว ไม่ใช่คนละ DB: ``team_rows`` ถูกยัดเข้า
    ``pd.DataFrame`` ซึ่ง **แปลง None เป็น NaN เมื่อคอลัมน์นั้นมีทั้งค่าว่างและสตริง**
    DB ที่มีคนเดียวจึงไม่มีทางเจอบั๊กนั้นเลย
    """
    _seed_athlete(conn, 1, "Synced", LAST_DAY)
    _seed_athlete(conn, 2, "Stale", YESTERDAY)


def _cards(tab):
    # กรองด้วย *มาร์กอัปของการ์ด* ไม่ใช่ชื่อคลาสเปล่า ๆ — บล็อก CSS ของหน้าเดียวกัน
    # ก็มีชื่อคลาสครบทุกตัวในนั้น แล้วเทสจะไปอ่าน <style> แทนการ์ดจริง
    cards = [element.value for element in tab.get("markdown")
             if element.value and '<div class="team-card"' in element.value]
    assert cards, "ไม่เจอการ์ดนักกีฬาบนหน้าทีม — ข้อมูลทดสอบไม่พอ"
    by_name = {}
    for card in cards:
        name = re.search(r'class="team-card__name">([^<]+)<', card).group(1)
        by_name[name] = card
    return by_name


class WatchThatStoppedSyncingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cards = _cards(render_tab(TEAM_TAB_LABEL, seed_mixed_team)[0])
        cls.stale, cls.fresh = cards["Stale"], cards["Synced"]

    def test_the_card_says_the_watch_has_not_synced_today(self):
        self.assertIn("ยังไม่ sync วันนี้", self.stale)

    def test_it_names_the_day_the_numbers_actually_came_from(self):
        # "ยังไม่ sync" อย่างเดียวยังตอบไม่ได้ว่าตัวเลขบนการ์ดเก่าแค่ไหน
        self.assertIn(f"ล่าสุด {YESTERDAY.strftime('%d/%m')}", self.stale)

    def test_a_watch_that_synced_today_stays_silent(self):
        # ไม่ใช่แค่ "ไม่มีข้อความนั้น" แต่ต้องไม่มีป้ายเลย — `pd.DataFrame` แปลง None
        # เป็น NaN ซึ่ง *truthy* ป้ายจึงถูกวาดขึ้นมาว่า "nan" ทั้งที่นาฬิกา sync ปกติ
        # (จับได้ในเบราว์เซอร์จริงเท่านั้น 3 ก.ย. 69 — เทสเดิมที่หาแต่คำว่า
        # "ยังไม่ sync" ผ่านฉลุยเพราะ "nan" ไม่มีคำนั้นอยู่)
        self.assertNotIn("ยังไม่ sync", self.fresh)
        self.assertNotIn("team-card__stale", self.fresh)
        self.assertNotIn("nan", self.fresh.lower())

    def test_the_note_does_not_change_the_status_verdict(self):
        # ป้ายตอบคำถาม "ตัวเลขเป็นของวันไหน" ไม่ใช่ "ซ้อมได้ไหม" — ทั้งสองการ์ด
        # ไม่มี Garmin signal ให้ทบทวน จึงต้องอ่านว่าไม่พบสัญญาณเตือนเหมือนกัน
        for card in (self.stale, self.fresh):
            self.assertIn("ไม่พบสัญญาณเตือนจากอุปกรณ์", card)


if __name__ == "__main__":
    unittest.main()
