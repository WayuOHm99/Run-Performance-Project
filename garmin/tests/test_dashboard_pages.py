"""เรนเดอร์ทั้ง 5 หน้าจริงผ่าน ``AppTest`` บน DB ที่ปั้นเอง แล้วอ่านสิ่งที่ออกไปหน้าเว็บ

``AppTest`` เขียว = สคริปต์รันจบและ element ออกมาครบ **แค่นั้น** (CLAUDE.md ชั้นที่ 2)
หน้าย้ายจริงไหม ฟอนต์ถูกวาดไหม ต้องดูในเบราว์เซอร์ (ชั้นที่ 4–5)
"""

import datetime
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dashboard_tab_harness import (  # noqa: E402
    ALL_PAGES,
    BODY_PAGE,
    ESTIMATES_PAGE,
    LAST_DAY,
    SESSION_PAGE,
    TEAM_PAGE,
    TRAINING_PAGE,
    page_text,
    render_page,
)

TODAY = LAST_DAY
YESTERDAY = TODAY - datetime.timedelta(days=1)


def seed_team(conn):
    """Tong sync วันนี้แล้ว · Dan นาฬิกาเงียบมาสองวัน · P'kao ยังไม่มีข้อมูลเลย"""
    conn.executemany(
        "INSERT INTO dim_athlete (athlete_id, slug, display_name) VALUES (?, ?, ?)",
        [(1, "tong", "Tong"), (2, "dan", "Dan"), (3, "p'kao", "P'kao")])
    for offset in range(20):
        day = TODAY - datetime.timedelta(days=offset)
        conn.execute(
            "INSERT INTO fact_daily_wellness (athlete_id, calendar_date, resting_hr,"
            " hrv_last_night, hrv_weekly_avg, hrv_status, sleep_score, body_battery_high,"
            " body_battery_low, bb_most_recent, stress_avg, deep_sleep_sec, light_sleep_sec,"
            " rem_sleep_sec, awake_sec, sleep_duration_sec, training_status, fetched_at)"
            " VALUES (1, ?, 48, 60, 58, 'BALANCED', 80, 90, 20, 70, 30, 5400, 14400, 5400,"
            " 600, 25200, 'PRODUCTIVE_1', ?)",
            (day.isoformat(), f"{day.isoformat()}T01:00:00Z"))
        if offset >= 2:
            conn.execute(
                "INSERT INTO fact_daily_wellness (athlete_id, calendar_date, resting_hr,"
                " hrv_last_night, sleep_score, body_battery_high, fetched_at)"
                " VALUES (2, ?, 50, 70, 75, 85, ?)",
                (day.isoformat(), f"{day.isoformat()}T01:00:00Z"))
    # กิจกรรมของ Tong: รันยาว, warm-up สั้น 300 ม., เวทไม่มีระยะ (ต้องอยู่ครบทุกหน้า)
    activities = [
        (101, 1, "running", "Long run", f"{YESTERDAY} 06:00:00", 3600, 10000, 150, 170, 6.0,
         600, 1800, 900, 300, 0),
        (102, 1, "running", "Warm up", f"{YESTERDAY} 17:00:00", 120, 300, 120, 130, 6.6,
         120, 0, 0, 0, 0),
        (103, 1, "strength_training", None, f"{TODAY} 07:00:00", 1800, 0, 100, 140, None,
         1500, 300, 0, 0, 0),
        (201, 2, "running", "Dan easy", f"{YESTERDAY} 06:00:00", 2700, 8000, 140, 160, 5.6,
         0, 2700, 0, 0, 0),
        # สองรายการที่ Garmin เก็บไว้จริงทั้งคู่ — เคส P'kao 29/09/2026 (สองอุปกรณ์?)
        (301, 3, "treadmill_running", "Treadmill", f"{YESTERDAY} 20:08:32", 2193, 6460,
         156, 171, 5.66, 0, 0, 2193, 0, 0),
        (302, 3, "treadmill_running", "Treadmill", f"{YESTERDAY} 20:08:32", 2193, 6460,
         157, 171, 5.66, 0, 0, 2193, 0, 0),
    ]
    conn.executemany(
        "INSERT INTO fact_activity (activity_id, athlete_id, activity_type, activity_name,"
        " start_time_local, duration_sec, distance_m, avg_hr, max_hr, avg_pace_min_per_km,"
        " hr_zone1_sec, hr_zone2_sec, hr_zone3_sec, hr_zone4_sec, hr_zone5_sec)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", activities)
    # กิจกรรมที่ถูกลบฝั่ง Garmin ต้องไม่โผล่ที่ไหนเลย
    conn.execute(
        "INSERT INTO fact_activity (activity_id, athlete_id, activity_type, activity_name,"
        " start_time_local, duration_sec, distance_m, deleted_at)"
        " VALUES (299, 2, 'running', 'Deleted in Garmin', ?, 600, 2000, ?)",
        (f"{YESTERDAY} 19:00:00", f"{TODAY}T00:00:00Z"))
    # lap ของรันยาว มี lap 0 m ปนอยู่ — แสดงตาม Garmin (ตัดสิน 7 ส.ค. 69)
    conn.executemany(
        "INSERT INTO fact_activity_split (activity_id, split_num, distance_m, duration_sec,"
        " avg_hr, max_hr, avg_pace_min_km) VALUES (101, ?, ?, ?, ?, ?, ?)",
        [(1, 5000, 1800, 148, 160, 6.0), (2, 5000, 1790, 152, 170, 5.97),
         (3, 0, 10, 150, 150, None)])
    # ค่าประเมินที่ Garmin อัปเดตห่าง ๆ — อยู่นอกช่วง 30 วันแต่ต้องยังเห็นค่าล่าสุด
    old = TODAY - datetime.timedelta(days=60)
    conn.execute(
        "INSERT INTO fact_daily_wellness (athlete_id, calendar_date, vo2max_trend, fitness_age)"
        " VALUES (1, ?, 51, 25)", (old.isoformat(),))
    conn.execute(
        "INSERT INTO fact_race_prediction (athlete_id, calendar_date, time_5k_sec, time_10k_sec,"
        " time_half_sec, time_full_sec) VALUES (1, ?, 1305, 2753, 6208, 13861)",
        (YESTERDAY.isoformat(),))


def seed_nothing_for_tong(conn):
    conn.execute("INSERT INTO dim_athlete (athlete_id, slug, display_name) "
                 "VALUES (1, 'tong', 'Tong')")


class EveryPageRendersTests(unittest.TestCase):
    def test_every_page_renders_for_an_athlete_with_data(self):
        for page in ALL_PAGES:
            with self.subTest(page=page):
                render_page(page, seed_team)

    def test_every_page_renders_for_an_athlete_with_no_data_yet(self):
        # นักกีฬาใหม่ที่เพิ่งได้ token ยังไม่มีอะไรเลย — หน้าต้องบอก ไม่ใช่พัง
        for page in ALL_PAGES:
            with self.subTest(page=page):
                main, _ = render_page(page, seed_nothing_for_tong)
                self.assertTrue(page_text(main))


class GarminOnlyOnScreenTests(unittest.TestCase):
    """สิ่งที่ถูกถอดออก 30 ก.ย. 69 ต้องไม่กลับมาบนจอ ไม่ว่าจะผ่านหน้าไหน"""

    REMOVED = ("LTHR", "VDOT", "pace–HR", "pace-HR", "ACWR", "จากฐาน", "เบา (Z1",
               "กลาง (Z3", "หนัก (Z4", "สัดส่วนเบา", "ควรทบทวน", "ไม่พบสัญญาณเตือน")

    def test_no_page_shows_a_metric_the_system_invented(self):
        for page in ALL_PAGES:
            with self.subTest(page=page):
                main, _ = render_page(page, seed_team)
                text = page_text(main)
                for word in self.REMOVED:
                    self.assertNotIn(word, text, f"{page} ยังแสดง {word!r}")

    def test_garmin_words_reach_the_screen_as_garmin_wrote_them(self):
        main, _ = render_page(TEAM_PAGE, seed_team)
        text = page_text(main)
        self.assertIn("Balanced", text)
        self.assertIn("Productive", text)


class TeamPageTests(unittest.TestCase):
    """หน้าแรกยึดวันที่เลือก (ค่าเริ่มต้น = วันนี้ตามเวลาไทย)"""

    @classmethod
    def setUpClass(cls):
        cls.main, _ = render_page(TEAM_PAGE, seed_team)
        cls.text = page_text(cls.main)
        cls.yesterday_main, _ = render_page(TEAM_PAGE, seed_team,
                                            state={"team_day": YESTERDAY})
        cls.yesterday_text = page_text(cls.yesterday_main)

    def test_each_card_says_what_it_has_for_the_selected_day(self):
        # เคส 3 ก.ย. 69 — การ์ดของคนที่นาฬิกาเงียบต้องบอกเอง ไม่ใช่ให้โค้ชไล่ดูวันที่
        badges = [m.value for m in self.main.get("markdown") if "-badge[" in m.value]
        self.assertTrue(any("ระหว่างวัน" in badge for badge in badges), badges)
        self.assertEqual(sum("ยังไม่ได้รับข้อมูลของวันนี้" in badge for badge in badges), 2)

    def test_a_value_from_another_day_is_labelled_with_its_own_date(self):
        # ข้อบกพร่อง 4.4: เดิมการ์ดหนึ่งใบประกอบจากค่าคนละวันโดยไม่บอก
        metrics = {(m.label, m.proto.delta) for m in self.main.get("metric")}
        stale = (TODAY - datetime.timedelta(days=2)).strftime("%d/%m")
        self.assertIn(("RHR", f"ไม่มีของวันนี้ · ครั้งก่อน 50 bpm ({stale})"), metrics)

    def test_activities_follow_the_selected_day_not_a_seven_day_total(self):
        self.assertNotIn("Long run", self.text)          # เป็นของเมื่อวาน
        self.assertIn("Long run", self.yesterday_text)

    def test_possible_duplicates_are_flagged_but_still_listed(self):
        self.assertEqual(self.yesterday_text.count("อาจซ้ำ") >= 2, True)
        self.assertIn("ยังนับรวมอยู่ในยอด", self.yesterday_text)

    def test_activity_deleted_in_garmin_is_not_listed(self):
        self.assertNotIn("Deleted in Garmin", self.yesterday_text)

    def test_every_athlete_has_a_button_to_open_their_page(self):
        labels = [button.label for button in self.main.get("button")]
        for name in ("Tong", "Dan", "P'kao"):
            self.assertIn(f"ดูข้อมูลของ {name}", labels)


class SessionPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main, cls.app = render_page(SESSION_PAGE, seed_team)

    def test_short_and_distance_less_activities_are_selectable(self):
        options = self.app.selectbox(key="session_activity").options
        self.assertEqual(len(options), 3)  # ของ Tong: รันยาว warm-up เวท
        self.assertTrue(any("Warm up" in option and "0.30 km" in option for option in options))

    def test_a_zero_metre_lap_is_shown_as_garmin_recorded_it(self):
        main, _ = render_page(SESSION_PAGE, seed_team, state={"session_activity": 101})
        laps = [frame.value for frame in main.get("dataframe")][-1]
        self.assertEqual(list(laps["Lap"]), [1, 2, 3])
        self.assertEqual(laps["ระยะ (m)"].iloc[-1], 0)


class EstimatesPageTests(unittest.TestCase):
    def test_latest_estimate_outside_the_selected_period_is_still_shown(self):
        # VO2max ของ 60 วันก่อนคือค่าล่าสุดที่ Garmin มี ซ่อนเพราะอยู่นอกช่วง 30 วัน = โกหก
        main, _ = render_page(ESTIMATES_PAGE, seed_team)
        metrics = {m.label: m.value for m in main.get("metric")}
        self.assertEqual(metrics.get("VO2max"), "51")
        self.assertEqual(metrics.get("5K"), "21:45")


class TrainingPageTests(unittest.TestCase):
    def test_totals_are_plain_sums_of_garmin_activities(self):
        main, _ = render_page(TRAINING_PAGE, seed_team)
        metrics = {m.label: m.value for m in main.get("metric")}
        self.assertEqual(metrics["ระยะวิ่งรวม"], "10.3 km")      # 10 km + 0.3 km วิ่ง
        self.assertEqual(metrics["จำนวนกิจกรรม"], "3")          # รวมเวท


class BodyPageTests(unittest.TestCase):
    def test_athlete_whose_watch_stopped_still_sees_their_last_values(self):
        main, _ = render_page(BODY_PAGE, seed_team, athlete="Dan")
        metrics = {m.label: (m.value, m.proto.delta) for m in main.get("metric")}
        self.assertEqual(metrics["RHR"][0], "50 bpm")
        self.assertEqual(metrics["RHR"][1],
                         (TODAY - datetime.timedelta(days=2)).strftime("%d/%m"))


if __name__ == "__main__":
    unittest.main()
