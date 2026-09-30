"""Settle review: เมื่อวานที่ข้อมูลครบแล้วยังต้องถูกตรวจทานซ้ำเพื่อรับค่าที่ Garmin แก้ย้อนหลัง."""

import importlib.util
import sqlite3
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

GARMIN_ROOT = Path(__file__).resolve().parents[1]


def load_script(name, filename):
    spec = importlib.util.spec_from_file_location(
        name, GARMIN_ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backfill = load_script("garmin_settle_backfill", "03_backfill.py")
schema = load_script("garmin_settle_schema", "02_init_schema.py")


def at(month, day, hour, minute=0):
    return datetime(2026, month, day, hour, minute, tzinfo=timezone.utc)


class SettleReviewTests(unittest.TestCase):
    DAY = "2026-09-29"  # วันจบ 2026-09-30 00:00 Bangkok = 09-29 17:00Z
    OLD_FETCH = "2026-09-29T16:42:00.000Z"

    class Garmin:
        def __init__(self, steps=23_564, fail=()):
            self.steps = steps
            self.fail = set(fail)
            self.calls = []

        def _call(self, name, payload):
            self.calls.append(name)
            if name in self.fail:
                raise RuntimeError("HTTP 500 boom")
            return payload

        def get_stats(self, _d):
            return self._call("stats", {
                "restingHeartRate": 40, "averageStressLevel": 31,
                "totalSteps": self.steps,
                "bodyBatteryHighestValue": 48, "bodyBatteryLowestValue": 5})

        def get_hrv_data(self, _d):
            return self._call("hrv", {"hrvSummary": {"lastNightAvg": 82}})

        def get_sleep_data(self, _d):
            return self._call("sleep", {"dailySleepDTO": {
                "sleepTimeSeconds": 25_000,
                "sleepScores": {"overall": {"value": 57}}}})

        def get_respiration_data(self, _d):
            return self._call("respiration", {"avgSleepRespirationValue": 14})

        def get_training_readiness(self, _d):
            return self._call("readiness", [])

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.addCleanup(self.conn.close)
        cols = ", ".join(f"{n} {k}" for n, k in schema.WELLNESS_COLUMNS)
        self.conn.execute(
            f"CREATE TABLE fact_daily_wellness ({cols}, "
            "PRIMARY KEY (athlete_id, calendar_date) ON CONFLICT REPLACE)")
        self.conn.execute(
            """INSERT INTO fact_daily_wellness
               (athlete_id, calendar_date, resting_hr, stress_avg, steps,
                body_battery_high, body_battery_low, sleep_score,
                hrv_last_night, avg_sleep_respiration, fetched_at)
               VALUES (1, ?, 40, 29, 22517, 48, 6, 57, 82, 14, ?)""",
            (self.DAY, self.OLD_FETCH))
        self.conn.commit()

    def run_lane(self, garmin, now, terminal=None):
        with mock.patch.object(backfill.time, "sleep"):
            return backfill.fetch_and_repair_previous_day_wellness(
                garmin, self.conn, 1, self.DAY, now_utc=now,
                terminal_errors=terminal)

    def row(self):
        return self.conn.execute(
            "SELECT steps, stress_avg, body_battery_low, fetched_at, "
            "settle_reviewed_at_utc FROM fact_daily_wellness").fetchone()

    def test_complete_row_in_window_is_reviewed_and_revision_merged(self):
        garmin = self.Garmin()
        changed = self.run_lane(garmin, at(9, 30, 0, 46))  # 07:46 Bangkok
        steps, stress, bb_low, fetched, reviewed = self.row()
        self.assertEqual(changed, 1)
        self.assertEqual((steps, stress, bb_low), (23564, 31, 5))
        self.assertEqual(len(garmin.calls), 5)
        self.assertGreater(fetched, self.OLD_FETCH)
        self.assertEqual(reviewed, "2026-09-30T00:46:00Z")

    def test_unchanged_review_keeps_fetched_at(self):
        self.run_lane(self.Garmin(), at(9, 30, 0, 46))
        fetched_after_first = self.row()[3]
        # ผ่าน interval แล้ว Garmin ตอบค่าเดิม → ไม่เลื่อน fetched_at
        changed = self.run_lane(self.Garmin(), at(9, 30, 4, 0))
        self.assertEqual(changed, 0)
        self.assertEqual(self.row()[3], fetched_after_first)
        self.assertEqual(self.row()[4], "2026-09-30T04:00:00Z")

    def test_inside_interval_makes_no_calls(self):
        self.conn.execute(
            "UPDATE fact_daily_wellness SET settle_reviewed_at_utc = ?",
            ("2026-09-30T00:00:00Z",))
        garmin = self.Garmin()
        self.assertEqual(self.run_lane(garmin, at(9, 30, 2, 59)), 0)
        self.assertEqual(garmin.calls, [])
        self.assertEqual(self.row()[0], 22517)

    def test_outside_36h_window_makes_no_calls(self):
        garmin = self.Garmin()
        # วันจบ 09-29 17:00Z + 36 ชม. = 10-01 05:00Z
        self.assertEqual(self.run_lane(garmin, at(10, 1, 5, 1)), 0)
        self.assertEqual(garmin.calls, [])
        # ก่อนวันจบก็ไม่ตรวจทาน
        self.assertEqual(self.run_lane(garmin, at(9, 29, 16, 0)), 0)
        self.assertEqual(garmin.calls, [])

    def test_failed_endpoint_does_not_blank_values(self):
        garmin = self.Garmin(fail={"stats"})
        self.run_lane(garmin, at(9, 30, 0, 46))
        steps, stress, bb_low, _, reviewed = self.row()
        self.assertEqual((steps, stress, bb_low), (22517, 29, 6))
        self.assertIsNotNone(reviewed)

    def test_all_core_endpoints_failing_does_not_consume_review(self):
        garmin = self.Garmin(fail={"stats", "hrv", "sleep", "readiness"})
        self.run_lane(garmin, at(9, 30, 0, 46), terminal=[])
        self.assertIsNone(self.row()[4])          # ไม่ประทับ = รอบถัดไปลองใหม่
        self.assertEqual(self.row()[0], 22517)    # ค่าเดิมไม่ถูกลบ

    def test_a_failed_review_never_fails_the_lane_or_raises_an_alert(self):
        """ข้อมูลเมื่อวานครบอยู่แล้ว การตรวจทานซ้ำเป็นของแถม — ล้มแล้วต้องเงียบ

        ถ้านับเป็นความล้มเหลวของสาย แจ้งเตือนจะขึ้นทุกครั้งที่ Garmin สะดุดชั่วคราว
        ทั้งที่ไม่มีอะไรให้เจ้าของทำ (ผู้ใช้เจอปัญหาเตือนถี่มาแล้ว)
        """
        garmin = self.Garmin(fail={"stats", "hrv", "sleep", "readiness"})
        terminal, failures = [], []
        with mock.patch.object(backfill.time, "sleep"):
            backfill.fetch_and_repair_previous_day_wellness(
                garmin, self.conn, 1, self.DAY, now_utc=at(9, 30, 0, 46),
                endpoint_failures=failures, terminal_errors=terminal)
        self.assertEqual((terminal, failures), ([], []))

    def test_partial_row_still_takes_repair_path(self):
        self.conn.execute(
            "UPDATE fact_daily_wellness SET sleep_score = NULL, hrv_last_night = NULL")
        self.run_lane(self.Garmin(), at(9, 30, 0, 46))
        stamped = self.conn.execute(
            "SELECT repair_attempted_at_utc FROM fact_daily_wellness").fetchone()[0]
        self.assertEqual(stamped, "2026-09-30T00:46:00Z")
        # ซ่อมแล้วเข้า cooldown: รอบถัดไปไม่ยิงซ้ำ
        garmin2 = self.Garmin()
        self.run_lane(garmin2, at(9, 30, 1, 16))
        self.assertEqual(garmin2.calls, [])


if __name__ == "__main__":
    unittest.main()
