import ast
import importlib.util
import io
import os
import types
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


GARMIN_ROOT = Path(__file__).resolve().parents[1]


def load_script(name, filename):
    spec = importlib.util.spec_from_file_location(
        name, GARMIN_ROOT / "scripts" / filename
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backfill = load_script("garmin_backfill_under_test", "03_backfill.py")
schema = load_script("garmin_schema_under_test", "02_init_schema.py")
fetch_all = load_script("garmin_fetch_all_under_test", "fetch_all.py")

# โฟลเดอร์ข้อมูลจริงของเครื่องนี้ — ห้ามมีเทสตัวไหนแตะ ใช้เทียบใน ProductionDataIsolationTests
PRODUCTION_DATA_DIR = GARMIN_ROOT / "data"


class IsolatedDataDirMixin:
    """ชี้ไฟล์สถานะ/DB ของโมดูลที่กำลังเทสไปที่ temp dir ตลอดอายุเคส.

    เทสที่เรียก fetch_all.main() หรือ backfill.write_status() ต้อง mixin ตัวนี้เสมอ —
    ไม่ใช่ไล่ patch ทีละ path เพราะวิธีนั้นพังมาแล้ว (ลืม LANE_STATUS_DIR ตัวเดียว
    ก็เขียนทับ data/sync_lane/fast.json ของจริงด้วยนักกีฬาปลอม แล้ว dashboard โชว์ตามนั้น)
    """

    def setUp(self):
        super().setUp()
        self.data_dir = Path(tempfile.mkdtemp(prefix="garmin-data-"))
        self.addCleanup(shutil.rmtree, self.data_dir, True)
        for module in (fetch_all, backfill):
            previous = module.use_data_dir(self.data_dir)
            self.addCleanup(module.use_data_dir, previous)


def create_activity_db():
    conn = sqlite3.connect(":memory:")
    activity_columns = ", ".join(
        f"{name} {kind}" for name, kind in schema.ACTIVITY_COLUMNS
    )
    split_columns = ", ".join(
        f"{name} {kind}" for name, kind in schema.SPLIT_COLUMNS
    )
    conn.execute(f"CREATE TABLE fact_activity ({activity_columns})")
    conn.execute(
        f"""CREATE TABLE fact_activity_split (
            {split_columns},
            PRIMARY KEY (activity_id, split_num) ON CONFLICT REPLACE
        )"""
    )
    return conn


class SyntheticGarmin:
    def __init__(self, activities):
        self.activities = activities
        self.detail_calls = 0
        self.weather_calls = 0
        self.split_calls = 0

    def get_activities_by_date(self, _start, _end):
        return self.activities

    def get_activity(self, _activity_id):
        self.detail_calls += 1
        return {
            "summaryDTO": {
                "minHR": 88,
                "impactLoad": 12,
                "beginPotentialStamina": 90,
                "endPotentialStamina": 45,
            }
        }

    def get_activity_weather(self, _activity_id):
        self.weather_calls += 1
        return {
            "temp": 86,
            "apparentTemp": 88,
            "relativeHumidity": 70,
            "windSpeed": 4,
        }

    def get_activity_splits(self, _activity_id):
        self.split_calls += 1
        return [{"distance": 1000, "duration": 300, "averageHR": 150}]


class RecordingGarmin(SyntheticGarmin):
    """SyntheticGarmin ที่จำว่ามีใครแตะ endpoint ฝั่ง wellness/extras บ้าง.

    ยามเฝ้ากฎต้องแดงเมื่อ --skip-wellness เผลอยิง endpoint รายวันหรือ extras
    ดังนั้นทุกตัวบันทึกชื่อแล้วค่อยคืนค่า ไม่ใช่ raise (raise ทำให้แยกไม่ออกว่า
    โค้ดไม่เรียก หรือเรียกแล้วพังเงียบ)
    """

    _WELLNESS_ENDPOINTS = (
        "get_stats", "get_hrv_data", "get_sleep_data", "get_respiration_data",
        "get_training_readiness", "get_training_status", "get_max_metrics",
        "get_endurance_score", "get_hill_score",
    )
    _EXTRAS_ENDPOINTS = (
        "get_lactate_threshold", "get_fitnessage_data", "get_race_predictions",
        "get_body_composition", "get_personal_record", "get_user_profile",
        "get_gear", "get_gear_stats", "get_devices",
    )

    def __init__(self, activities):
        super().__init__(activities)
        self.wellness_calls = []

    def login(self, _token_dir):
        return None

    def get_full_name(self):
        return "Probe"

    def __getattr__(self, name):
        if name in self._WELLNESS_ENDPOINTS or name in self._EXTRAS_ENDPOINTS:
            def _record(*_args, **_kwargs):
                self.wellness_calls.append(name)
                return {}
            return _record
        raise AttributeError(name)


def synthetic_activity(activity_id=101, distance=5000):
    return {
        "activityId": activity_id,
        "activityType": {"typeKey": "running"},
        "activityName": "Synthetic morning run",
        "startTimeLocal": "2030-01-02 06:00:00",
        "startTimeGMT": "2030-01-01 23:00:00",
        "duration": 1500,
        "distance": distance,
        "averageHR": 150,
        "maxHR": 170,
        "startLatitude": 1.0,
    }


class FastActivityTests(unittest.TestCase):
    def test_activity_id_normalizer_rejects_non_sqlite_integer_values(self):
        for value in (True, 1.5, 2**63, str(2**63)):
            with self.subTest(value=value):
                self.assertIsNone(backfill._normalize_activity_id(value))

    def test_invalid_activity_collection_never_reconciles_existing_rows(self):
        conn = create_activity_db()
        self.addCleanup(conn.close)
        conn.execute(
            """INSERT INTO fact_activity (
                   activity_id, athlete_id, activity_type, start_time_local,
                   duration_sec, deleted_at
               ) VALUES (99, 1, 'running', '2030-01-02 06:00:00', 600, NULL)"""
        )
        garmin = SyntheticGarmin({})

        with self.assertRaises(RuntimeError):
            backfill.fetch_and_insert_activities(
                garmin,
                conn,
                1,
                backfill.date(2030, 1, 2),
                backfill.date(2030, 1, 2),
            )

        deleted_at = conn.execute(
            "SELECT deleted_at FROM fact_activity WHERE activity_id = 99"
        ).fetchone()[0]
        self.assertIsNone(deleted_at)

    def test_string_activity_id_is_canonicalized_before_reconcile(self):
        conn = create_activity_db()
        self.addCleanup(conn.close)
        activity = synthetic_activity(activity_id="123", distance=0)
        activity["activityType"] = {"typeKey": "cycling"}
        garmin = SyntheticGarmin([activity])

        backfill.fetch_and_insert_activities(
            garmin,
            conn,
            1,
            backfill.date(2030, 1, 2),
            backfill.date(2030, 1, 2),
        )

        row = conn.execute(
            "SELECT typeof(activity_id), deleted_at FROM fact_activity WHERE activity_id = 123"
        ).fetchone()
        self.assertEqual(row, ("integer", None))

    def test_reconcile_keeps_offset_timestamp_on_its_local_calendar_date(self):
        conn = create_activity_db()
        self.addCleanup(conn.close)
        conn.execute(
            """INSERT INTO fact_activity (
                   activity_id, athlete_id, start_time_local, deleted_at
               ) VALUES (123, 1, '2030-01-02T00:30:00+07:00', NULL)"""
        )

        marked, restored = backfill.reconcile_activities(
            conn,
            1,
            backfill.date(2030, 1, 2),
            backfill.date(2030, 1, 2),
            set(),
        )

        self.assertEqual((marked, restored), ([123], []))

    def test_partial_split_refresh_preserves_existing_metrics(self):
        conn = create_activity_db()
        self.addCleanup(conn.close)
        conn.execute(
            "INSERT INTO fact_activity (activity_id, athlete_id) VALUES (20, 1)"
        )
        conn.execute(
            """INSERT INTO fact_activity_split (
                   activity_id, split_num, distance_m, duration_sec,
                   avg_hr, avg_cadence, avg_power
               ) VALUES (20, 1, 1000, 300, 155, 170, 250)"""
        )
        garmin = mock.Mock()
        garmin.get_activity_splits.return_value = [
            {"distance": 1000, "duration": 299}
        ]

        backfill.fetch_and_insert_splits(garmin, conn, 20)

        metrics = conn.execute(
            """SELECT avg_hr, avg_cadence, avg_power
                 FROM fact_activity_split
                WHERE activity_id = 20 AND split_num = 1"""
        ).fetchone()
        self.assertEqual(metrics, (155.0, 170.0, 250.0))

    def test_split_refresh_removes_laps_no_longer_returned_by_garmin(self):
        conn = create_activity_db()
        self.addCleanup(conn.close)
        conn.execute(
            "INSERT INTO fact_activity (activity_id, athlete_id) VALUES (20, 1)"
        )
        conn.executemany(
            """INSERT INTO fact_activity_split (
                   activity_id, split_num, distance_m, duration_sec, avg_hr
               ) VALUES (20, ?, 1000, 300, 155)""",
            [(1,), (2,)],
        )
        garmin = mock.Mock()
        garmin.get_activity_splits.return_value = [
            {"distance": 1000, "duration": 299, "averageHR": 156}
        ]

        backfill.fetch_and_insert_splits(garmin, conn, 20)

        split_numbers = conn.execute(
            """SELECT split_num FROM fact_activity_split
                WHERE activity_id = 20 ORDER BY split_num"""
        ).fetchall()
        self.assertEqual(split_numbers, [(1,)])

    def test_empty_split_list_clears_all_stale_laps(self):
        conn = create_activity_db()
        self.addCleanup(conn.close)
        conn.execute(
            "INSERT INTO fact_activity (activity_id, athlete_id) VALUES (20, 1)"
        )
        conn.execute(
            """INSERT INTO fact_activity_split (
                   activity_id, split_num, distance_m, duration_sec
               ) VALUES (20, 1, 1000, 300)"""
        )
        garmin = mock.Mock()
        garmin.get_activity_splits.return_value = []

        backfill.fetch_and_insert_splits(garmin, conn, 20)

        remaining = conn.execute(
            "SELECT COUNT(*) FROM fact_activity_split WHERE activity_id = 20"
        ).fetchone()[0]
        self.assertEqual(remaining, 0)

    def test_empty_lap_dto_collection_clears_all_stale_laps(self):
        conn = create_activity_db()
        self.addCleanup(conn.close)
        conn.execute(
            "INSERT INTO fact_activity (activity_id, athlete_id) VALUES (20, 1)"
        )
        conn.execute(
            """INSERT INTO fact_activity_split (
                   activity_id, split_num, distance_m, duration_sec
               ) VALUES (20, 1, 1000, 300)"""
        )
        garmin = mock.Mock()
        garmin.get_activity_splits.return_value = {"lapDTOs": []}

        backfill.fetch_and_insert_splits(garmin, conn, 20)

        remaining = conn.execute(
            "SELECT COUNT(*) FROM fact_activity_split WHERE activity_id = 20"
        ).fetchone()[0]
        self.assertEqual(remaining, 0)

    def test_fast_sync_preserves_enrichment_and_fetches_missing_splits_once(self):
        conn = create_activity_db()
        self.addCleanup(conn.close)
        conn.execute(
            """INSERT INTO fact_activity (
                activity_id, athlete_id, start_time_local, distance_m, min_hr,
                impact_load, begin_stamina, end_stamina, weather_temp_c,
                weather_apparent_temp_c, weather_humidity, weather_wind_kph,
                training_load, hr_zone4_sec, deleted_at
            ) VALUES (101, 1, '2030-01-02 06:00:00', 4000, 77, 9, 80, 40,
                      25, 26, 60, 3, 120, 300, '2030-01-03T00:00:00')"""
        )
        # A missing activity in the same day must not be reconciled by the fast path.
        conn.execute(
            """INSERT INTO fact_activity (
                activity_id, athlete_id, start_time_local, duration_sec
            ) VALUES (202, 1, '2030-01-02 07:00:00', 600)"""
        )
        garmin = SyntheticGarmin([synthetic_activity(distance=5100)])

        with mock.patch.object(backfill.time, "sleep"):
            count = backfill.fetch_and_insert_activities(
                garmin,
                conn,
                1,
                backfill.date(2030, 1, 2),
                backfill.date(2030, 1, 2),
                fast=True,
            )
            # รอบ 15 นาทีถัดไปเห็น split ใน DB แล้ว ต้องไม่ยิง endpoint ซ้ำ
            backfill.fetch_and_insert_activities(
                garmin,
                conn,
                1,
                backfill.date(2030, 1, 2),
                backfill.date(2030, 1, 2),
                fast=True,
            )

        row = conn.execute(
            """SELECT distance_m, min_hr, impact_load, begin_stamina, end_stamina,
                      weather_temp_c, weather_humidity, training_load,
                      hr_zone4_sec, deleted_at
               FROM fact_activity WHERE activity_id = 101"""
        ).fetchone()
        missing_deleted_at = conn.execute(
            "SELECT deleted_at FROM fact_activity WHERE activity_id = 202"
        ).fetchone()[0]
        split_count = conn.execute(
            "SELECT count(*) FROM fact_activity_split WHERE activity_id = 101"
        ).fetchone()[0]
        self.assertEqual(count, 1)
        self.assertEqual(
            row,
            (5100.0, 77.0, 9.0, 80.0, 40.0, 25.0, 60.0, 120.0, 300.0, None),
        )
        self.assertIsNone(missing_deleted_at)
        self.assertEqual(split_count, 1)
        self.assertEqual(
            (garmin.detail_calls, garmin.weather_calls, garmin.split_calls),
            (0, 0, 1),
        )

    def test_fast_sync_skips_splits_for_zero_distance_activity(self):
        conn = create_activity_db()
        self.addCleanup(conn.close)
        garmin = SyntheticGarmin([synthetic_activity(distance=0)])

        with mock.patch.object(backfill.time, "sleep"):
            backfill.fetch_and_insert_activities(
                garmin,
                conn,
                1,
                backfill.date(2030, 1, 2),
                backfill.date(2030, 1, 2),
                fast=True,
            )

        self.assertEqual(garmin.split_calls, 0)

    def test_full_sync_still_fetches_enrichment_splits_and_reconciles(self):
        conn = create_activity_db()
        self.addCleanup(conn.close)
        garmin = SyntheticGarmin([synthetic_activity()])

        with mock.patch.object(backfill.time, "sleep"):
            count = backfill.fetch_and_insert_activities(
                garmin,
                conn,
                1,
                backfill.date(2030, 1, 2),
                backfill.date(2030, 1, 2),
            )

        activity = conn.execute(
            """SELECT min_hr, impact_load, weather_temp_c
               FROM fact_activity WHERE activity_id = 101"""
        ).fetchone()
        split_count = conn.execute(
            "SELECT count(*) FROM fact_activity_split WHERE activity_id = 101"
        ).fetchone()[0]
        self.assertEqual(count, 1)
        self.assertEqual(activity, (88.0, 12.0, 30.0))
        self.assertEqual(split_count, 1)
        self.assertEqual(
            (garmin.detail_calls, garmin.weather_calls, garmin.split_calls),
            (1, 1, 1),
        )

    def test_reconcile_imports_only_remote_activities_missing_from_sqlite(self):
        """Weekly reconcile is the bounded self-healing path for old uploads.

        The missing activity is eight days old, so the normal three-day full
        sync cannot see it.  Existing activities must not pay the detail API
        cost again merely because the wider reconciliation window runs.
        """
        conn = create_activity_db()
        self.addCleanup(conn.close)
        conn.execute(
            """INSERT INTO fact_activity (
                   activity_id, athlete_id, activity_type, start_time_local,
                   distance_m, duration_sec, deleted_at
               ) VALUES (101, 1, 'running', '2030-01-02 06:00:00',
                         5000, 1500, NULL)"""
        )
        old_missing = synthetic_activity(activity_id=202)
        old_missing["startTimeLocal"] = "2030-01-02 07:00:00"
        garmin = SyntheticGarmin([synthetic_activity(), old_missing])

        with mock.patch.object(backfill.time, "sleep"):
            marked, restored, imported = backfill.reconcile_only(
                garmin,
                conn,
                1,
                backfill.date(2030, 1, 1),
                backfill.date(2030, 1, 10),
            )

        row = conn.execute(
            """SELECT activity_id, deleted_at
                 FROM fact_activity
                WHERE activity_id = 202"""
        ).fetchone()
        split_count = conn.execute(
            "SELECT COUNT(*) FROM fact_activity_split WHERE activity_id = 202"
        ).fetchone()[0]
        self.assertEqual((marked, restored, imported), ([], [], [202]))
        self.assertEqual(row, (202, None))
        self.assertEqual(split_count, 1)
        self.assertEqual(
            (garmin.detail_calls, garmin.weather_calls, garmin.split_calls),
            (1, 1, 1),
        )


def create_wellness_db():
    conn = sqlite3.connect(":memory:")
    columns = ", ".join(f"{name} {kind}" for name, kind in schema.WELLNESS_COLUMNS)
    conn.execute(
        f"""CREATE TABLE fact_daily_wellness (
            {columns},
            PRIMARY KEY (athlete_id, calendar_date) ON CONFLICT REPLACE
        )"""
    )
    return conn


class SyntheticWellnessGarmin:
    """คืน payload ตามรูปทรงจริงของ Garmin + นับว่า endpoint ไหนถูกเรียกบ้าง."""

    def __init__(self, empty=False):
        self.calls = []
        self.empty = empty

    def _record(self, name, payload):
        self.calls.append(name)
        return None if self.empty else payload

    def get_stats(self, _d):
        return self._record("stats", {
            "restingHeartRate": 48, "totalSteps": 8000, "averageStressLevel": 30,
            "bodyBatteryHighestValue": 95, "bodyBatteryLowestValue": 20,
            "bodyBatteryMostRecentValue": 62, "avgWakingRespirationValue": 14,
        })

    def get_hrv_data(self, _d):
        return self._record("hrv", {
            "hrvSummary": {"weeklyAvg": 70, "lastNightAvg": 66, "status": "BALANCED"}
        })

    def get_sleep_data(self, _d):
        return self._record("sleep", {
            "dailySleepDTO": {
                "sleepTimeSeconds": 27000, "deepSleepSeconds": 4000,
                "sleepScores": {"overall": {"value": 82}},
            }
        })

    def get_training_readiness(self, _d):
        return self._record("readiness", [{
            "score": 74, "level": "READY", "feedbackShort": "GOOD",
            "acuteLoad": 420, "acwrFactorPercent": 95,
        }])

    def get_respiration_data(self, _d):
        return self._record("respiration", {"avgSleepRespirationValue": 13})

    def get_training_status(self, _d):
        return self._record("training_status", {
            "mostRecentTrainingStatus": {
                "latestTrainingStatusData": {"dev1": {"trainingStatusFeedbackPhrase": "PRODUCTIVE"}}
            }
        })

    def get_max_metrics(self, _d):
        return self._record("max_metrics", [{"generic": {"vo2MaxPreciseValue": 52.5, "fitnessAge": 24}}])

    def get_endurance_score(self, _d):
        return self._record("endurance", {"overallScore": 6100})

    def get_hill_score(self, _d):
        return self._record("hill", {"overallScore": 55, "strengthScore": 50, "enduranceScore": 60})


class FastWellnessTests(unittest.TestCase):
    DAY = "2030-01-02"

    def _run_fast(self, garmin, conn):
        with mock.patch.object(backfill.time, "sleep"):
            return backfill.fetch_and_update_wellness_fast(
                garmin, conn, 1, backfill.date(2030, 1, 2), backfill.date(2030, 1, 2)
            )

    def test_fast_wellness_updates_intraday_fields_without_wiping_full_sync_data(self):
        conn = create_wellness_db()
        self.addCleanup(conn.close)
        # ค่าที่ full sync/extras เก็บไว้แล้ว — fast wellness ต้องไม่ล้างทิ้ง
        conn.execute(
            """INSERT INTO fact_daily_wellness (
                athlete_id, calendar_date, lactate_threshold_hr, vo2max_trend,
                training_status, endurance_score, avg_sleep_respiration, body_battery_low
            ) VALUES (1, ?, 184, 51.0, 'PRODUCTIVE', 6000, 13, 11)""",
            (self.DAY,),
        )
        garmin = SyntheticWellnessGarmin()

        count = self._run_fast(garmin, conn)

        row = conn.execute(
            """SELECT resting_hr, body_battery_high, body_battery_low, bb_most_recent,
                      hrv_last_night, sleep_score, training_readiness, acwr_percent,
                      lactate_threshold_hr, vo2max_trend, training_status,
                      endurance_score, avg_sleep_respiration
               FROM fact_daily_wellness WHERE athlete_id = 1 AND calendar_date = ?""",
            (self.DAY,),
        ).fetchone()
        self.assertEqual(count, 1)
        self.assertEqual(
            row,
            (48.0, 95.0, 20.0, 62.0, 66.0, 82.0, 74.0, 95.0,
             184.0, 51.0, "PRODUCTIVE", 6000.0, 13.0),
        )
        # แตะแค่ 4 endpoint ที่ค่าขยับระหว่างวัน ที่เหลือปล่อยให้ full sync
        self.assertEqual(garmin.calls, ["stats", "hrv", "sleep", "readiness"])

    def test_fast_wellness_never_overwrites_existing_value_with_null(self):
        conn = create_wellness_db()
        self.addCleanup(conn.close)
        conn.execute(
            """INSERT INTO fact_daily_wellness (athlete_id, calendar_date, resting_hr, sleep_score)
               VALUES (1, ?, 47, 80)""",
            (self.DAY,),
        )
        garmin = SyntheticWellnessGarmin(empty=True)   # Garmin ตอบว่าง (นาฬิกายังไม่ sync)

        count = self._run_fast(garmin, conn)

        row = conn.execute(
            "SELECT resting_hr, sleep_score FROM fact_daily_wellness WHERE athlete_id = 1",
            (),
        ).fetchone()
        self.assertEqual(count, 0)
        self.assertEqual(row, (47.0, 80.0))

    def test_fast_wellness_fails_when_every_core_endpoint_errors(self):
        conn = create_wellness_db()
        self.addCleanup(conn.close)

        class FailedCoreGarmin:
            def __getattr__(self, name):
                if name in {
                    "get_stats", "get_hrv_data", "get_sleep_data",
                    "get_training_readiness",
                }:
                    return lambda _date: (_ for _ in ()).throw(
                        RuntimeError("HTTP 503 Service Unavailable")
                    )
                raise AttributeError(name)

        with (
            mock.patch.object(backfill.time, "sleep"),
            self.assertRaises(backfill.CoreWellnessUnavailableError),
        ):
            backfill.fetch_and_update_wellness_fast(
                FailedCoreGarmin(),
                conn,
                1,
                backfill.date(2030, 1, 2),
                backfill.date(2030, 1, 2),
            )

    def test_fast_wellness_continues_later_days_before_reporting_failure(self):
        conn = create_wellness_db()
        self.addCleanup(conn.close)

        class FirstDayFails(SyntheticWellnessGarmin):
            def _core(self, date_str, payload):
                if date_str == "2030-01-02":
                    raise RuntimeError("HTTP 503 Service Unavailable")
                return payload

            def get_stats(self, date_str):
                return self._core(date_str, {"restingHeartRate": 48})

            def get_hrv_data(self, date_str):
                return self._core(date_str, {"hrvSummary": {"lastNightAvg": 66}})

            def get_sleep_data(self, date_str):
                return self._core(
                    date_str,
                    {"dailySleepDTO": {"sleepScores": {"overall": {"value": 82}}}},
                )

            def get_training_readiness(self, date_str):
                return self._core(date_str, [{"score": 74}])

        with (
            mock.patch.object(backfill.time, "sleep"),
            self.assertRaises(backfill.CoreWellnessUnavailableError),
        ):
            backfill.fetch_and_update_wellness_fast(
                FirstDayFails(),
                conn,
                1,
                backfill.date(2030, 1, 2),
                backfill.date(2030, 1, 3),
            )

        row = conn.execute(
            """SELECT resting_hr, hrv_last_night, sleep_score, training_readiness
                 FROM fact_daily_wellness
                WHERE athlete_id = 1 AND calendar_date = '2030-01-03'"""
        ).fetchone()
        self.assertEqual(row, (48.0, 66.0, 82.0, 74.0))

    def test_fast_wellness_reports_partial_endpoint_failures_without_raw_errors(self):
        conn = create_wellness_db()
        self.addCleanup(conn.close)

        class PartialGarmin(SyntheticWellnessGarmin):
            def get_hrv_data(self, _date):
                raise RuntimeError("HTTP 503 private-upstream-details")

            def get_sleep_data(self, _date):
                raise RuntimeError("HTTP 503 private-upstream-details")

            def get_training_readiness(self, _date):
                raise RuntimeError("HTTP 503 private-upstream-details")

        failures = []
        count = self._run_fast_with_failures(PartialGarmin(), conn, failures)

        self.assertEqual(count, 1)
        self.assertEqual(
            failures,
            [
                {"endpoint": "get_hrv_data", "reason": "network"},
                {"endpoint": "get_sleep_data", "reason": "network"},
                {"endpoint": "get_training_readiness", "reason": "network"},
            ],
        )
        self.assertNotIn("private-upstream-details", repr(failures))

    def _run_fast_with_failures(self, garmin, conn, failures):
        with mock.patch.object(backfill.time, "sleep"):
            return backfill.fetch_and_update_wellness_fast(
                garmin,
                conn,
                1,
                backfill.date(2030, 1, 2),
                backfill.date(2030, 1, 2),
                endpoint_failures=failures,
            )

    def test_full_wellness_still_writes_every_field_group(self):
        conn = create_wellness_db()
        self.addCleanup(conn.close)
        garmin = SyntheticWellnessGarmin()

        with mock.patch.object(backfill.time, "sleep"):
            count = backfill.fetch_and_insert_wellness(
                garmin, conn, 1, backfill.date(2030, 1, 2), backfill.date(2030, 1, 2)
            )

        # fitness_age ไม่อยู่ในชุดนี้แล้ว (4 ส.ค. 69) — maxmetrics คืน fitnessAge = None
        # เสมอ ค่าจริงมาจาก get_fitnessage_data() ที่ fetch_extras เป็นคนดึง
        # ดูเทสถัดไปที่คุมว่ารอบรายวันต้องไม่เขียนทับคอลัมน์นี้
        row = conn.execute(
            """SELECT resting_hr, hrv_status, sleep_score, deep_sleep_sec, acute_load,
                      avg_waking_respiration, avg_sleep_respiration, training_status,
                      vo2max_trend, endurance_score, hill_score_strength
               FROM fact_daily_wellness WHERE athlete_id = 1 AND calendar_date = ?""",
            (self.DAY,),
        ).fetchone()
        self.assertEqual(count, 1)
        self.assertEqual(
            row,
            (48.0, "BALANCED", 82.0, 4000.0, 420.0, 14.0, 13.0, "PRODUCTIVE",
             52.5, 6100.0, 50.0),
        )

    def test_full_wellness_persists_optional_fields_before_core_failure(self):
        conn = create_wellness_db()
        self.addCleanup(conn.close)

        class PartialFullGarmin(SyntheticWellnessGarmin):
            def get_stats(self, _date):
                raise RuntimeError("HTTP 503 Service Unavailable")

            def get_hrv_data(self, _date):
                raise RuntimeError("HTTP 503 Service Unavailable")

            def get_sleep_data(self, _date):
                raise RuntimeError("HTTP 503 Service Unavailable")

            def get_training_readiness(self, _date):
                raise RuntimeError("HTTP 503 Service Unavailable")

        with (
            mock.patch.object(backfill.time, "sleep"),
            self.assertRaises(backfill.CoreWellnessUnavailableError),
        ):
            backfill.fetch_and_insert_wellness(
                PartialFullGarmin(),
                conn,
                1,
                backfill.date(2030, 1, 2),
                backfill.date(2030, 1, 2),
            )

        row = conn.execute(
            """SELECT avg_sleep_respiration, training_status, vo2max_trend,
                      endurance_score, hill_score_strength
                 FROM fact_daily_wellness
                WHERE athlete_id = 1 AND calendar_date = ?""",
            (self.DAY,),
        ).fetchone()
        self.assertEqual(row, (13.0, "PRODUCTIVE", 52.5, 6100.0, 50.0))

    def test_full_wellness_continues_later_days_before_reporting_failure(self):
        conn = create_wellness_db()
        self.addCleanup(conn.close)

        class FirstDayFails(SyntheticWellnessGarmin):
            def _core(self, date_str, payload):
                if date_str == "2030-01-02":
                    raise RuntimeError("HTTP 503 Service Unavailable")
                return payload

            def get_stats(self, date_str):
                return self._core(date_str, super().get_stats(date_str))

            def get_hrv_data(self, date_str):
                return self._core(date_str, super().get_hrv_data(date_str))

            def get_sleep_data(self, date_str):
                return self._core(date_str, super().get_sleep_data(date_str))

            def get_training_readiness(self, date_str):
                return self._core(
                    date_str, super().get_training_readiness(date_str)
                )

        with (
            mock.patch.object(backfill.time, "sleep"),
            self.assertRaises(backfill.CoreWellnessUnavailableError),
        ):
            backfill.fetch_and_insert_wellness(
                FirstDayFails(),
                conn,
                1,
                backfill.date(2030, 1, 2),
                backfill.date(2030, 1, 3),
            )

        row = conn.execute(
            """SELECT resting_hr, training_status, endurance_score
                 FROM fact_daily_wellness
                WHERE athlete_id = 1 AND calendar_date = '2030-01-03'"""
        ).fetchone()
        self.assertEqual(row, (48.0, "PRODUCTIVE", 6100.0))

    def test_mixed_core_failures_default_to_network_not_token(self):
        failures = [
            {"endpoint": "get_stats", "reason": "token"},
            {"endpoint": "get_hrv_data", "reason": "network"},
            {"endpoint": "get_sleep_data", "reason": "network"},
            {"endpoint": "get_training_readiness", "reason": "network"},
        ]

        error = backfill.CoreWellnessUnavailableError(failures)

        self.assertEqual(error.status_reason, "network")

    def test_multi_day_failure_classification_considers_every_failure(self):
        network_then_token = [
            *(
                {"endpoint": endpoint, "reason": "network"}
                for endpoint in backfill.CORE_WELLNESS_ENDPOINT_ORDER
            ),
            *(
                {"endpoint": endpoint, "reason": "token"}
                for endpoint in backfill.CORE_WELLNESS_ENDPOINT_ORDER
            ),
        ]

        error = backfill.CoreWellnessUnavailableError(network_then_token)

        self.assertEqual(error.status_reason, "network")

    def test_full_wellness_keeps_columns_the_daily_fetch_does_not_own(self):
        conn = create_wellness_db()
        self.addCleanup(conn.close)
        # lactate threshold เขียนโดย fetch_extras เฉพาะ "วันล่าสุด" วันเดียว ไม่ได้ดึงรายวัน
        # → รอบ wellness ของวันเดียวกันต้องไม่ล้างมันทิ้ง ไม่งั้น deep resync 45 วันจะลบ
        # LT ย้อนหลังทั้งหมด (เจอจริง 3 ส.ค. 69: ของพี่เก้า 16 ก.ค. HR 184 หายไปทั้งค่า
        # เพราะ PRIMARY KEY ของตารางเป็น ON CONFLICT REPLACE = เขียนทับทั้งแถว)
        conn.execute(
            """INSERT INTO fact_daily_wellness (
                athlete_id, calendar_date, lactate_threshold_hr,
                lactate_threshold_pace_min_km, fetched_at
            ) VALUES (1, ?, 184, 5.04, '2020-01-01 00:00:00')""",
            (self.DAY,),
        )
        garmin = SyntheticWellnessGarmin()

        with mock.patch.object(backfill.time, "sleep"):
            backfill.fetch_and_insert_wellness(
                garmin, conn, 1, backfill.date(2030, 1, 2), backfill.date(2030, 1, 2)
            )

        row = conn.execute(
            """SELECT lactate_threshold_hr, lactate_threshold_pace_min_km,
                      resting_hr, sleep_score, fetched_at
               FROM fact_daily_wellness WHERE athlete_id = 1 AND calendar_date = ?""",
            (self.DAY,),
        ).fetchone()
        self.assertEqual(row[:4], (184.0, 5.04, 48.0, 82.0))
        # ยังต้องเลื่อน fetched_at ให้ด้วย — dashboard ใช้ค่านี้ตัดสินความสดของข้อมูล
        self.assertNotEqual(row[4], "2020-01-01 00:00:00")

    def test_full_wellness_does_not_wipe_fitness_age(self):
        # fitness_age ย้ายมาเป็นของ fetch_extras (4 ส.ค. 69) เพราะ maxmetrics คืน None เสมอ
        # → รอบ wellness รายวันต้องไม่แตะคอลัมน์นี้ ไม่งั้นจะซ้ำรอยบั๊ก LT: extras เขียน
        # ค่าให้วันล่าสุด แล้วรอบรายวันถัดไปเขียน None ทับ = ไม่มีวันเห็นค่าบน dashboard
        conn = create_wellness_db()
        self.addCleanup(conn.close)
        conn.execute(
            """INSERT INTO fact_daily_wellness (athlete_id, calendar_date, fitness_age, fetched_at)
               VALUES (1, ?, 22.1, '2020-01-01 00:00:00')""",
            (self.DAY,),
        )
        garmin = SyntheticWellnessGarmin()

        with mock.patch.object(backfill.time, "sleep"):
            backfill.fetch_and_insert_wellness(
                garmin, conn, 1, backfill.date(2030, 1, 2), backfill.date(2030, 1, 2)
            )

        row = conn.execute(
            """SELECT fitness_age, resting_hr FROM fact_daily_wellness
               WHERE athlete_id = 1 AND calendar_date = ?""",
            (self.DAY,),
        ).fetchone()
        self.assertEqual(row, (22.1, 48.0))


class BackfillStatusTests(IsolatedDataDirMixin, unittest.TestCase):
    def test_activity_list_endpoint_failure_marks_the_sync_failed(self):
        schema.init_schema(self.data_dir / "garmin.db")
        project_root = self.data_dir / "project"
        (project_root / "tokens" / "probe").mkdir(parents=True)

        class FailingGarmin:
            def login(self, _token_dir):
                return None

            def get_full_name(self):
                return "Probe"

            def get_activities_by_date(self, _start, _end):
                raise RuntimeError("HTTP 503 Service Unavailable")

        fake_garminconnect = types.ModuleType("garminconnect")
        fake_garminconnect.Garmin = FailingGarmin
        argv = ["03_backfill.py", "--athlete", "probe", "--days", "0",
                "--activities-only"]

        with (
            mock.patch.object(backfill, "PROJECT_ROOT", project_root),
            mock.patch.object(backfill.time, "sleep"),
            mock.patch.dict(sys.modules, {"garminconnect": fake_garminconnect}),
            mock.patch.object(sys, "argv", argv),
            self.assertRaises(SystemExit) as raised,
        ):
            backfill.main()

        payload = backfill.json.loads(
            (backfill.STATUS_DIR / "probe.json").read_text(encoding="utf-8")
        )
        self.assertEqual(raised.exception.code, 1)
        self.assertEqual((payload["ok"], payload["reason"]), (False, "network"))

    def test_malformed_activity_payload_is_reported_as_payload_failure(self):
        schema.init_schema(self.data_dir / "garmin.db")
        project_root = self.data_dir / "project"
        (project_root / "tokens" / "probe").mkdir(parents=True)

        class MalformedGarmin:
            def login(self, _token_dir):
                return None

            def get_full_name(self):
                return "Probe"

            def get_activities_by_date(self, _start, _end):
                return {}

        fake_garminconnect = types.ModuleType("garminconnect")
        fake_garminconnect.Garmin = MalformedGarmin
        argv = ["03_backfill.py", "--athlete", "probe", "--days", "0",
                "--activities-only"]

        with (
            mock.patch.object(backfill, "PROJECT_ROOT", project_root),
            mock.patch.object(backfill.time, "sleep"),
            mock.patch.dict(sys.modules, {"garminconnect": fake_garminconnect}),
            mock.patch.object(sys, "argv", argv),
            self.assertRaises(SystemExit) as raised,
        ):
            backfill.main()

        payload = backfill.json.loads(
            (backfill.STATUS_DIR / "probe.json").read_text(encoding="utf-8")
        )
        self.assertEqual(raised.exception.code, 1)
        self.assertEqual((payload["ok"], payload["reason"]), (False, "payload"))

    def test_all_core_wellness_errors_write_a_failed_privacy_safe_status(self):
        schema.init_schema(self.data_dir / "garmin.db")
        project_root = self.data_dir / "project"
        (project_root / "tokens" / "probe").mkdir(parents=True)

        class FailingGarmin:
            def login(self, _token_dir):
                return None

            def get_full_name(self):
                return "Probe"

            def get_respiration_data(self, _date):
                return None

            def __getattr__(self, name):
                if name in {
                    "get_stats", "get_hrv_data", "get_sleep_data",
                    "get_training_readiness",
                }:
                    return lambda _date: (_ for _ in ()).throw(
                        RuntimeError("HTTP 503 private-upstream-details")
                    )
                raise AttributeError(name)

        fake_garminconnect = types.ModuleType("garminconnect")
        fake_garminconnect.Garmin = FailingGarmin
        argv = ["03_backfill.py", "--athlete", "probe", "--days", "0",
                "--wellness-fast"]

        with (
            mock.patch.object(backfill, "PROJECT_ROOT", project_root),
            mock.patch.object(backfill.time, "sleep"),
            mock.patch.dict(sys.modules, {"garminconnect": fake_garminconnect}),
            mock.patch.object(sys, "argv", argv),
            self.assertRaises(SystemExit) as raised,
        ):
            backfill.main()

        payload = backfill.json.loads(
            (backfill.STATUS_DIR / "probe.json").read_text(encoding="utf-8")
        )
        self.assertEqual(raised.exception.code, 1)
        self.assertEqual((payload["ok"], payload["reason"]), (False, "network"))
        self.assertEqual(
            payload["error"],
            "all core wellness endpoints failed: get_stats, get_hrv_data, "
            "get_sleep_data, get_training_readiness",
        )
        self.assertEqual(
            payload["endpoint_failures"],
            [
                {"endpoint": "get_stats", "reason": "network"},
                {"endpoint": "get_hrv_data", "reason": "network"},
                {"endpoint": "get_sleep_data", "reason": "network"},
                {"endpoint": "get_training_readiness", "reason": "network"},
            ],
        )
        self.assertNotIn("private-upstream-details", repr(payload))

    def test_full_wellness_failure_still_runs_extras_before_failed_status(self):
        schema.init_schema(self.data_dir / "garmin.db")
        project_root = self.data_dir / "project"
        (project_root / "tokens" / "probe").mkdir(parents=True)

        class FailingGarmin:
            def login(self, _token_dir):
                return None

            def get_full_name(self):
                return "Probe"

            def __getattr__(self, name):
                if name in backfill.CORE_WELLNESS_ENDPOINTS:
                    return lambda _date: (_ for _ in ()).throw(
                        RuntimeError("HTTP 503 Service Unavailable")
                    )
                if name in {
                    "get_respiration_data", "get_training_status",
                    "get_max_metrics", "get_endurance_score", "get_hill_score",
                }:
                    return lambda _date: None
                raise AttributeError(name)

        fake_garminconnect = types.ModuleType("garminconnect")
        fake_garminconnect.Garmin = FailingGarmin
        argv = ["03_backfill.py", "--athlete", "probe", "--days", "0",
                "--skip-activities"]

        with (
            mock.patch.object(backfill, "PROJECT_ROOT", project_root),
            mock.patch.object(backfill.time, "sleep"),
            mock.patch.dict(sys.modules, {"garminconnect": fake_garminconnect}),
            mock.patch.object(backfill, "fetch_and_insert_extras") as extras,
            mock.patch.object(sys, "argv", argv),
            self.assertRaises(SystemExit) as raised,
        ):
            backfill.main()

        self.assertEqual(raised.exception.code, 1)
        extras.assert_called_once()

    def test_multi_day_mixed_failures_publish_network_and_all_causes(self):
        schema.init_schema(self.data_dir / "garmin.db")
        project_root = self.data_dir / "project"
        (project_root / "tokens" / "probe").mkdir(parents=True)
        end_day = backfill.datetime.now(backfill.BANGKOK_TZ).date()
        token_day = (end_day - backfill.timedelta(days=1)).isoformat()

        class MixedGarmin:
            def login(self, _token_dir):
                return None

            def get_full_name(self):
                return "Probe"

            def __getattr__(self, name):
                if name in backfill.CORE_WELLNESS_ENDPOINTS:
                    def fail(date_str):
                        message = (
                            "401 Unauthorized"
                            if date_str == token_day
                            else "HTTP 503 Service Unavailable"
                        )
                        raise RuntimeError(message)
                    return fail
                if name in {
                    "get_respiration_data", "get_training_status",
                    "get_max_metrics", "get_endurance_score", "get_hill_score",
                }:
                    return lambda _date: None
                raise AttributeError(name)

        fake_garminconnect = types.ModuleType("garminconnect")
        fake_garminconnect.Garmin = MixedGarmin
        argv = ["03_backfill.py", "--athlete", "probe", "--days", "1",
                "--skip-activities"]

        with (
            mock.patch.object(backfill, "PROJECT_ROOT", project_root),
            mock.patch.object(backfill.time, "sleep"),
            mock.patch.dict(sys.modules, {"garminconnect": fake_garminconnect}),
            mock.patch.object(backfill, "fetch_and_insert_extras"),
            mock.patch.object(sys, "argv", argv),
            self.assertRaises(SystemExit) as raised,
        ):
            backfill.main()

        payload = backfill.json.loads(
            (backfill.STATUS_DIR / "probe.json").read_text(encoding="utf-8")
        )
        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(payload["reason"], "network")
        self.assertEqual(
            {item["reason"] for item in payload["endpoint_failures"]},
            {"token", "network"},
        )


class FetchAllOrchestrationTests(IsolatedDataDirMixin, unittest.TestCase):
    def test_main_uses_bounded_concurrency_and_keeps_status_order(self):
        athletes = ["athlete-a", "athlete-b", "athlete-c"]
        active = 0
        max_active = 0
        guard = threading.Lock()

        timeouts = []

        def fake_run(slug, _args, _passthrough, _started, timeout_sec):
            nonlocal active, max_active
            timeouts.append(timeout_sec)
            with guard:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.03)
            with guard:
                active -= 1
            return {"slug": slug, "ok": True, "reason": "ok", "warnings": []}

        @contextmanager
        def fake_lock(_timeout):
            yield True

        argv = [
            "fetch_all.py",
            "--days",
            "0",
            "--activities-only",
            "--max-workers",
            "2",
        ]
        with (
            mock.patch.object(fetch_all, "list_athletes", return_value=athletes),
            mock.patch.object(fetch_all, "run_athlete", side_effect=fake_run),
            mock.patch.object(fetch_all, "run_lock", side_effect=fake_lock),
            mock.patch.object(sys, "argv", argv),
            self.assertRaises(SystemExit) as exited,
        ):
            fetch_all.main()

        # อ่านไฟล์ที่เขียนจริงใน temp dir แทนการดัก write_text ด้วย MagicMock —
        # mock ตัวเดียวปิดตาเทสจากไฟล์ปลายทางอีกตัว (สายงาน) ที่หลุดไปเขียนของจริง
        payload = fetch_all.json.loads(
            fetch_all.STATUS_FILE.read_text(encoding="utf-8")
        )
        lane_payload = fetch_all.json.loads(
            (fetch_all.LANE_STATUS_DIR / "fast.json").read_text(encoding="utf-8")
        )
        self.assertEqual(lane_payload, payload)
        self.assertEqual(exited.exception.code, 0)
        self.assertEqual(max_active, 2)
        self.assertEqual(
            [result["slug"] for result in payload["results"]],
            athletes,
        )
        # สายถี่ต้องยอมแพ้เร็ว ไม่กอด sync.lock ไว้จนสายอื่นอดทั้งชั่วโมง
        self.assertEqual(set(timeouts), {fetch_all.ATHLETE_TIMEOUT_SEC["fast"]})

    def test_status_write_failure_makes_the_round_fail(self):
        @contextmanager
        def fake_lock(_timeout):
            yield True

        result = {"slug": "probe", "ok": True, "reason": "ok", "warnings": []}
        argv = ["fetch_all.py", "--days", "0", "--activities-only"]
        with (
            mock.patch.object(fetch_all, "list_athletes", return_value=["probe"]),
            mock.patch.object(fetch_all, "run_athlete", return_value=result),
            mock.patch.object(fetch_all, "run_lock", side_effect=fake_lock),
            mock.patch.object(Path, "write_text", side_effect=OSError("disk full")),
            mock.patch.object(sys, "argv", argv),
            self.assertRaises(SystemExit) as exited,
        ):
            fetch_all.main()

        self.assertEqual(exited.exception.code, 1)


class RunAthleteDiagnosticsTests(IsolatedDataDirMixin, unittest.TestCase):
    def test_windowless_worker_output_is_forwarded_and_secrets_are_redacted(self):
        args = types.SimpleNamespace(days=0)
        output = io.StringIO()
        child = subprocess.CompletedProcess(
            args=["python", "03_backfill.py"],
            returncode=0,
            stdout=(
                "Logged in as: Probe\n"
                "API error: HTTP 503 Service Unavailable\n"
                "Authorization: Bearer super-secret-token\n"
                "Authorization: Basic basic-secret\n"
                "email=athlete@example.com password=hunter2\n"
                '{"access_token":"json-secret","client_secret":"client-secret",'
                '"oauth_consumer_secret":"oauth-secret"}\n'
                '{"Authorization":"Basic quoted-basic-secret"}\n'
                "headers={'Authorization': 'Bearer quoted-bearer-secret'}\n"
                "authorization = Bearer assigned-bearer-secret\n"
                "Set-Cookie: session-cookie-secret\n"
            ),
        )

        with (
            mock.patch.object(fetch_all.win_process, "run", return_value=child) as run,
            mock.patch.object(
                fetch_all,
                "read_athlete_status",
                return_value={"ok": True, "warnings": []},
            ),
            mock.patch("sys.stdout", output),
        ):
            result = fetch_all.run_athlete(
                "probe", args, ["--activities-only"], datetime.now(), 60
            )

        kwargs = run.call_args.kwargs
        self.assertEqual(result["ok"], True)
        self.assertEqual(kwargs["stdout"], subprocess.PIPE)
        self.assertEqual(kwargs["stderr"], subprocess.STDOUT)
        self.assertTrue(kwargs["text"])
        logged = output.getvalue()
        self.assertIn("Logged in as: Probe", logged)
        self.assertIn("HTTP 503 Service Unavailable", logged)
        self.assertIn("[REDACTED]", logged)
        for secret in (
            "super-secret-token", "athlete@example.com", "hunter2",
            "basic-secret", "json-secret", "client-secret", "oauth-secret",
            "quoted-basic-secret", "quoted-bearer-secret", "session-cookie-secret",
            "assigned-bearer-secret",
        ):
            self.assertNotIn(secret, logged)

    def test_zero_exit_without_fresh_worker_status_is_not_green(self):
        args = types.SimpleNamespace(days=0)
        child = subprocess.CompletedProcess(
            args=["python", "03_backfill.py"], returncode=0, stdout="done\n"
        )
        with (
            mock.patch.object(fetch_all.win_process, "run", return_value=child),
            mock.patch.object(fetch_all, "read_athlete_status", return_value=None),
        ):
            result = fetch_all.run_athlete(
                "probe", args, ["--activities-only"], datetime.now(), 60
            )

        self.assertEqual(
            result,
            {"slug": "probe", "ok": False, "reason": "status_missing", "warnings": []},
        )

    def test_future_status_cannot_make_worker_without_new_status_green(self):
        args = types.SimpleNamespace(days=0)
        fetch_all.STATUS_DIR.mkdir(parents=True, exist_ok=True)
        (fetch_all.STATUS_DIR / "probe.json").write_text(
            fetch_all.json.dumps({
                "finished_at": "2099-01-01T00:00:00",
                "ok": True,
                "warnings": [],
            }),
            encoding="utf-8",
        )
        child = subprocess.CompletedProcess(
            args=["python", "03_backfill.py"], returncode=0, stdout="done\n"
        )
        with mock.patch.object(fetch_all.win_process, "run", return_value=child):
            result = fetch_all.run_athlete(
                "probe", args, ["--activities-only"], datetime.now(), 60
            )

        self.assertEqual(result["ok"], False)
        self.assertEqual(result["reason"], "status_missing")


class DeepActivityBackfillTests(IsolatedDataDirMixin, unittest.TestCase):
    """--skip-wellness: ดึงกิจกรรมย้อนลึกโดยไม่ลาก wellness ทั้งช่วงมาด้วย.

    2 ก.ย. 69 พบว่าแดนมีกิจกรรมบน Garmin 2,526 รายการก่อนวันที่ DB เริ่มเก็บ
    (ย้อนถึง 9 เม.ย. 2023) แต่ `--days` ผูก activities กับ wellness ไว้ด้วยกัน
    → จะเอากิจกรรมครบต้องยิง wellness 1,238 วัน (~9 endpoint/วัน) ทิ้งเปล่า
    ธงนี้แยกสองอย่างออกจากกัน โดยยังเก็บ enrichment (detail/weather/splits) ครบ
    """

    def _run_main(self, extra_argv, garmin):
        schema.init_schema(self.data_dir / "garmin.db")
        project_root = self.data_dir / "project"
        (project_root / "tokens" / "probe").mkdir(parents=True)
        fake_garminconnect = types.ModuleType("garminconnect")
        fake_garminconnect.Garmin = lambda: garmin
        argv = ["03_backfill.py", "--athlete", "probe", "--days", "0", *extra_argv]
        with (
            mock.patch.object(backfill, "PROJECT_ROOT", project_root),
            mock.patch.object(backfill.time, "sleep"),
            mock.patch.dict(sys.modules, {"garminconnect": fake_garminconnect}),
            mock.patch.object(sys, "argv", argv),
        ):
            backfill.main()
        return backfill.json.loads(
            (backfill.STATUS_DIR / "probe.json").read_text(encoding="utf-8")
        )

    def test_skip_wellness_keeps_full_activity_enrichment(self):
        garmin = RecordingGarmin([synthetic_activity()])
        payload = self._run_main(["--skip-wellness"], garmin)

        self.assertEqual(payload["ok"], True)
        self.assertEqual(payload["activities"], 1)
        self.assertEqual(
            (garmin.detail_calls, garmin.weather_calls, garmin.split_calls),
            (1, 1, 1),
        )

    def test_skip_wellness_never_touches_a_wellness_or_extras_endpoint(self):
        garmin = RecordingGarmin([synthetic_activity()])
        payload = self._run_main(["--skip-wellness"], garmin)

        self.assertEqual(garmin.wellness_calls, [])
        self.assertIsNone(payload["wellness_days"])

    def test_skip_wellness_cannot_be_combined_with_another_lane_flag(self):
        """ต้องแดงด้วยข้อความ "ใช้ร่วมกันไม่ได้" เท่านั้น.

        เช็กแค่ exit code 2 ไม่พอ — main() ออกด้วย 2 ตอน token dir
        หายด้วย เทสจึงเขียวได้ทั้งที่กฎถูกถอนออก (พิสูจน์แล้ว 2 ก.ย. 69)
        """
        for other in ("--skip-activities", "--activities-only",
                      "--wellness-fast", "--reconcile"):
            with self.subTest(other=other):
                stderr = io.StringIO()
                with (
                    mock.patch.object(
                        sys, "argv",
                        ["03_backfill.py", "--athlete", "probe", "--days", "0",
                         "--skip-wellness", other],
                    ),
                    mock.patch.object(sys, "stderr", stderr),
                    self.assertRaises(SystemExit) as raised,
                ):
                    backfill.main()
                self.assertEqual(raised.exception.code, 2)
                self.assertIn("--skip-wellness", stderr.getvalue())
                self.assertIn(other, stderr.getvalue())


class CatchUpSlotTests(IsolatedDataDirMixin, unittest.TestCase):
    """--catch-up-slots: Task ยิงทุกชั่วโมง แต่ต้องทำงานจริงแค่ช่องละครั้ง."""

    def setUp(self):
        super().setUp()
        self.slots = fetch_all.parse_slots("08:00,21:00")

    def write_lane(self, run_at, results=None):
        fetch_all.LANE_STATUS_DIR.mkdir(parents=True, exist_ok=True)
        payload = {"run_at": run_at.isoformat(timespec="seconds")}
        if results is not None:
            payload["results"] = results
        (fetch_all.LANE_STATUS_DIR / "full.json").write_text(
            fetch_all.json.dumps(payload),
            encoding="utf-8",
        )

    def test_slots_are_parsed_and_sorted(self):
        self.assertEqual(
            fetch_all.parse_slots("21:00, 08:00"),
            [fetch_all.dtime(8, 0), fetch_all.dtime(21, 0)],
        )
        with self.assertRaises(ValueError):
            fetch_all.parse_slots(" , ")

    def test_skips_when_the_current_slot_already_ran(self):
        now = datetime(2030, 5, 6, 9, 0)
        self.write_lane(datetime(2030, 5, 6, 8, 0, 30))
        self.assertEqual(
            fetch_all.slot_already_done("full", self.slots, now),
            datetime(2030, 5, 6, 8, 0),
        )

    def test_runs_when_the_machine_missed_the_slot(self):
        # เครื่องหลับตอน 08:00 ตื่น 09:40 — รอบล่าสุดยังเป็นของเมื่อคืน ต้องได้รันตามเก็บ
        now = datetime(2030, 5, 6, 9, 40)
        self.write_lane(datetime(2030, 5, 5, 21, 3))
        self.assertIsNone(fetch_all.slot_already_done("full", self.slots, now))

    def test_failed_round_does_not_consume_the_slot(self):
        now = datetime(2030, 5, 6, 9, 0)
        self.write_lane(
            datetime(2030, 5, 6, 8, 1),
            results=[{"slug": "probe", "ok": False, "reason": "network"}],
        )

        self.assertEqual(
            fetch_all.pending_slots("full", self.slots, now),
            [
                datetime(2030, 5, 4, 21, 0),
                datetime(2030, 5, 5, 8, 0),
                datetime(2030, 5, 5, 21, 0),
                datetime(2030, 5, 6, 8, 0),
            ],
        )

    def test_before_the_first_slot_falls_back_to_last_night(self):
        now = datetime(2030, 5, 6, 2, 0)
        self.write_lane(datetime(2030, 5, 5, 21, 3))
        self.assertEqual(
            fetch_all.slot_already_done("full", self.slots, now),
            datetime(2030, 5, 5, 21, 0),
        )

    def test_runs_when_no_lane_status_exists_yet(self):
        self.assertIsNone(
            fetch_all.slot_already_done("full", self.slots, datetime(2030, 5, 6, 9, 0))
        )

    def test_main_exits_75_without_touching_the_lock(self):
        self.write_lane(datetime.now())
        argv = ["fetch_all.py", "--days", "3", "--catch-up-slots", "08:00,21:00"]
        lock = mock.MagicMock()
        with (
            mock.patch.object(fetch_all, "list_athletes", return_value=["a"]),
            mock.patch.object(fetch_all, "run_lock", lock),
            mock.patch.object(sys, "argv", argv),
            self.assertRaises(SystemExit) as exited,
        ):
            fetch_all.main()
        self.assertEqual(exited.exception.code, 75)
        lock.assert_not_called()

    def test_slot_missed_overnight_is_still_pending_the_next_morning(self):
        # เครื่องหลับ 15:00 → ข้ามช่อง 21:00 ทั้งคืน → ตื่น 08:14 วันรุ่งขึ้น
        # ต้องเห็นช่อง 21:00 ของเมื่อวานว่า "ค้าง" ด้วย ไม่ใช่เห็นแค่ช่อง 08:00 ของวันนี้
        now = datetime(2030, 5, 6, 8, 14)
        self.write_lane(datetime(2030, 5, 5, 8, 14, 34))
        self.assertEqual(
            fetch_all.pending_slots("full", self.slots, now),
            [datetime(2030, 5, 5, 21, 0), datetime(2030, 5, 6, 8, 0)],
        )
        self.assertIsNone(fetch_all.slot_already_done("full", self.slots, now))

    def test_one_round_clears_every_slot_it_caught_up(self):
        # รอบตามเก็บรอบเดียวครอบทุกช่องที่ค้าง (--days ดึงย้อนคลุมอยู่แล้ว) — รอบถัดไป
        # ของ Task รายชั่วโมงต้องไม่รันช่องเดิมซ้ำ ไม่งั้นกลายเป็นยิง API ฟรีทุกชั่วโมง
        self.write_lane(datetime(2030, 5, 6, 8, 14, 20))
        for hour in (9, 12, 20):
            now = datetime(2030, 5, 6, hour, 0)
            self.assertEqual(fetch_all.pending_slots("full", self.slots, now), [])
            self.assertEqual(
                fetch_all.slot_already_done("full", self.slots, now),
                datetime(2030, 5, 6, 8, 0),
            )

    def test_catch_up_never_reaches_further_back_than_the_lookback_window(self):
        # เครื่องปิดยาว 5 วัน — ตามเก็บได้แค่ช่องในหน้าต่าง 48 ชม. ที่เหลือหมดอายุแล้ว
        # (ข้อมูลของช่องเก่ากว่านั้นเป็นงานของ deep resync ไม่ใช่ full sync รอบเดียว)
        now = datetime(2030, 5, 6, 9, 0)
        self.write_lane(datetime(2030, 5, 1, 8, 5))
        pending = fetch_all.pending_slots("full", self.slots, now)
        self.assertEqual(
            pending,
            [datetime(2030, 5, 4, 21, 0), datetime(2030, 5, 5, 8, 0),
             datetime(2030, 5, 5, 21, 0), datetime(2030, 5, 6, 8, 0)],
        )
        self.assertGreaterEqual(min(pending), now - timedelta(hours=48))
        self.assertIsNone(fetch_all.slot_already_done("full", self.slots, now))

    def test_a_slot_that_has_not_arrived_yet_is_not_pending(self):
        # 20:00 ยังไม่ถึงช่อง 21:00 — ห้ามนับเป็นค้างแล้วรันดักหน้า
        now = datetime(2030, 5, 6, 20, 0)
        self.write_lane(datetime(2030, 5, 6, 8, 14))
        self.assertEqual(fetch_all.pending_slots("full", self.slots, now), [])
        self.assertEqual(
            fetch_all.slot_already_done("full", self.slots, now),
            datetime(2030, 5, 6, 8, 0),
        )

    def test_future_lane_timestamp_cannot_suppress_catch_up(self):
        now = datetime(2030, 5, 6, 9, 0)
        self.write_lane(
            now + timedelta(days=1),
            results=[{"slug": "probe", "ok": True, "reason": "ok"}],
        )

        self.assertEqual(
            fetch_all.pending_slots("full", self.slots, now),
            [
                datetime(2030, 5, 4, 21, 0),
                datetime(2030, 5, 5, 8, 0),
                datetime(2030, 5, 5, 21, 0),
                datetime(2030, 5, 6, 8, 0),
            ],
        )

    def test_aware_future_lane_timestamp_also_fails_open(self):
        now = datetime(2030, 5, 6, 9, 0)
        self.write_lane(
            datetime(2030, 5, 7, 9, 0, tzinfo=timezone(timedelta(hours=7))),
            results=[{"slug": "probe", "ok": True, "reason": "ok"}],
        )

        self.assertEqual(
            fetch_all.pending_slots("full", self.slots, now),
            fetch_all.passed_slots(self.slots, now),
        )


class LaneStaleLimitTests(unittest.TestCase):
    """เพดาน "สายเงียบเกินคาบ" ของ dashboard ต้องตรงกับ watchdog เป๊ะ.

    dashboard.py import ตรง ๆ ไม่ได้ (มันรัน streamlit ทั้งไฟล์) จึงอ่านค่าคงที่จาก
    source ด้วย ast แทน — สิ่งที่ต้องคุ้มครองคือ "ตัวเลขสองที่ตรงกัน" ไม่ใช่ตัวโค้ด
    """

    EXPECTED_LANES = {"full", "fast", "wellness", "reconcile", "deep", "backup"}

    @staticmethod
    def dashboard_constant(name):
        tree = ast.parse((GARMIN_ROOT / "scripts" / "dashboard.py")
                         .read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == name for t in node.targets):
                return ast.literal_eval(node.value)
        raise AssertionError(f"ไม่พบค่าคงที่ {name} ใน dashboard.py")

    @staticmethod
    def watchdog_limits():
        src = (GARMIN_ROOT / "scripts" / "notify_sync.ps1").read_text(encoding="utf-8-sig")
        block = re.search(r"\$STALE_LIMIT_MIN\s*=\s*\[ordered\]@\{(.+?)\}", src, re.S)
        assert block, "ไม่พบ $STALE_LIMIT_MIN ใน notify_sync.ps1"
        return {k: int(v) for k, v in re.findall(r"(\w+)\s*=\s*(\d+)", block.group(1))}

    def test_dashboard_and_watchdog_agree_on_every_lane(self):
        # สายที่หล่นจาก dashboard จะโชว์ ✅ ค้างตลอดกาลแม้ตายไปแล้ว — เดิมหล่น
        # reconcile/deep ซึ่งนาน ๆ เดินที = สายที่ตายเงียบแล้วสังเกตยากที่สุด
        dash = self.dashboard_constant("LANE_STALE_LIMIT_MIN")
        self.assertEqual(set(dash), self.EXPECTED_LANES)
        self.assertEqual(dash, self.watchdog_limits())

class SentinelValueTest(unittest.TestCase):
    """-1 ของ Garmin = "ไม่มีข้อมูล" ห้ามเก็บเป็นค่าที่วัดได้ (dashboard เอาไปเฉลี่ยตรง ๆ)"""

    def test_negative_stress_becomes_null(self):
        parsed = backfill._parse_stats({"averageStressLevel": -1, "maxStressLevel": -1})
        self.assertIsNone(parsed["stress_avg"])
        self.assertIsNone(parsed["max_stress"])

    def test_real_values_survive(self):
        parsed = backfill._parse_stats({
            "averageStressLevel": 31, "restingHeartRate": 51, "totalSteps": 10692,
        })
        self.assertEqual(parsed["stress_avg"], 31)
        self.assertEqual(parsed["resting_hr"], 51)
        self.assertEqual(parsed["steps"], 10692)

    def test_zero_is_a_real_value_not_a_sentinel(self):
        # ก้าว 0 / แคลอรี 0 ของวันที่เพิ่งเริ่มเป็นค่าจริง ต้องไม่ถูกตัดทิ้ง
        parsed = backfill._parse_stats({"totalSteps": 0, "activeKilocalories": 0})
        self.assertEqual(parsed["steps"], 0)
        self.assertEqual(parsed["active_kilocalories"], 0)

    def test_missing_keys_stay_none(self):
        parsed = backfill._parse_stats({})
        self.assertIsNone(parsed["stress_avg"])


class LoginErrorClassificationTest(unittest.TestCase):
    """"token เสีย" ต้องแปลว่าสิทธิ์พังจริง ๆ เท่านั้น

    เดาผิดเป็น token = ส่งผู้จัดการทีมไปขอรหัสผ่าน Garmin ของนักกีฬามากรอกใหม่
    โดยไม่จำเป็น ส่วนเดาผิดเป็น network เสียแค่รอรอบหน้า (ยังมี toast เตือนอยู่ดี)
    """

    def test_garmin_origin_down_is_not_a_token_problem(self):
        # เคสจริง 4 ส.ค. 69: garminconnect ห่อ HTTP 521 ไว้ใต้ AuthenticationError
        # ที่ข้อความอ่านแล้วเหมือน token เสีย → ระบบเคยสั่งให้ไปขอ token ใหม่ฟรี ๆ
        cause = RuntimeError(
            "API Error 521 - {'title': 'Error 521: Web server is down', "
            "'error_name': 'origin_down', 'retryable': True, 'retry_after': 120}"
        )
        outer = RuntimeError("Failed to retrieve social profile")
        outer.__cause__ = cause
        self.assertEqual(backfill.classify_login_error(outer), "network")

    def test_bare_social_profile_error_defaults_to_network(self):
        # ไม่มีเบาะแสอะไรเลย → เลือกทางที่เสียหายน้อยกว่า
        self.assertEqual(
            backfill.classify_login_error(RuntimeError("Failed to retrieve social profile")),
            "network",
        )

    def test_rate_limit_is_network(self):
        self.assertEqual(
            backfill.classify_login_error(RuntimeError("API Error 429 - Too Many Requests")),
            "network",
        )

    def test_real_auth_failure_is_still_token(self):
        for msg in ("401 Unauthorized", "invalid_grant: refresh token expired",
                    "403 Forbidden", "Bad credentials"):
            with self.subTest(msg=msg):
                self.assertEqual(backfill.classify_login_error(RuntimeError(msg)), "token")

    def test_network_outage_is_network(self):
        self.assertEqual(
            backfill.classify_login_error(OSError("getaddrinfo failed")), "network"
        )

    def test_walks_a_cycle_without_hanging(self):
        a = RuntimeError("outer")
        b = RuntimeError("401 Unauthorized")
        a.__cause__ = b
        b.__context__ = a          # วนกลับ — ต้องไม่ค้าง
        self.assertEqual(backfill.classify_login_error(a), "token")


WELLNESS_GAP_OLD_DAYS = backfill.WELLNESS_GAP_WARN_DAYS + 3


class SanityWellnessGapTests(unittest.TestCase):
    """วัน wellness ว่างเตือนได้เฉพาะช่วงที่ยังตามเก็บทัน — ไม่งั้น deep resync (45 วัน)
    ขุดวันเดิมเมื่อเดือนก่อนมาแปะแถบเหลืองค้างหน้า dashboard ทุกรอบ (เจอจริง 3 ส.ค. 69: tong)."""

    def _db_with_empty_days(self, days):
        conn = create_wellness_db()
        self.addCleanup(conn.close)
        for day in days:
            conn.execute(
                "INSERT INTO fact_daily_wellness (athlete_id, calendar_date, steps)"
                " VALUES (1, ?, 0)",
                (day.isoformat(),),
            )
        return conn

    def _check(self, conn, start, end):
        return backfill.sanity_check(conn, 1, start, end,
                                     include_activities=False, include_wellness=True)

    def test_recent_empty_day_still_warns(self):
        today = backfill.date.today()
        gap = today - backfill.timedelta(days=2)
        warns = self._check(self._db_with_empty_days([gap]),
                            today - backfill.timedelta(days=45), today)
        self.assertEqual(len(warns), 1)
        self.assertIn(gap.isoformat(), warns[0])

    def test_old_empty_day_is_not_worth_a_warning(self):
        today = backfill.date.today()
        gap = today - backfill.timedelta(days=WELLNESS_GAP_OLD_DAYS)
        warns = self._check(self._db_with_empty_days([gap]),
                            today - backfill.timedelta(days=45), today)
        self.assertEqual(warns, [])

    def test_long_gap_list_is_summarised(self):
        today = backfill.date.today()
        days = [today - backfill.timedelta(days=n) for n in range(1, 11)]
        warns = self._check(self._db_with_empty_days(days),
                            today - backfill.timedelta(days=45), today)
        self.assertEqual(len(warns), 1)
        self.assertIn("และอีก", warns[0])
        self.assertLessEqual(warns[0].count("-"), 2 * backfill.WELLNESS_GAP_DAYS_LISTED)


class SoftDeleteFilterTests(unittest.TestCase):
    def test_sanity_check_ignores_deleted_activities(self):
        conn = create_activity_db()
        self.addCleanup(conn.close)
        conn.execute(
            """INSERT INTO fact_activity (
                   activity_id, athlete_id, activity_type, start_time_local,
                   duration_sec, deleted_at
               ) VALUES (
                   44, 1, 'running', '2030-01-02 06:00:00',
                   0, '2030-01-03T00:00:00'
               )"""
        )

        warnings = backfill.sanity_check(
            conn,
            1,
            backfill.date(2030, 1, 2),
            backfill.date(2030, 1, 2),
            include_wellness=False,
        )

        self.assertEqual(warnings, [])

    def test_sanity_check_keeps_offset_timestamp_on_its_local_calendar_date(self):
        conn = create_activity_db()
        self.addCleanup(conn.close)
        conn.execute(
            """INSERT INTO fact_activity (
                   activity_id, athlete_id, activity_type, start_time_local,
                   duration_sec, deleted_at
               ) VALUES (
                   45, 1, 'running', '2030-01-02T00:30:00+07:00',
                   0, NULL
               )"""
        )

        warnings = backfill.sanity_check(
            conn,
            1,
            backfill.date(2030, 1, 2),
            backfill.date(2030, 1, 2),
            include_wellness=False,
        )

        self.assertEqual(len(warnings), 1)
        self.assertIn("เวลารวมเป็น 0", warnings[0])


class ProductionDataIsolationTests(IsolatedDataDirMixin, unittest.TestCase):
    """รัน unittest แล้วต้องไม่แตะ garmin/data ของจริงเลยสักไฟล์.

    ทำไมไม่เทียบ hash ก่อน/หลังตรง ๆ: เครื่องนี้มี Scheduled Task เขียนไฟล์พวกนี้อยู่จริง
    ทุก 15 นาที (fast) / 30 นาที (wellness) — เทียบ byte จะแดงเพราะ sync ของจริงเดินคาบเกี่ยว
    ไม่ใช่เพราะเทสรั่ว. จึงจับ "ลายนิ้วมือของเทส" แทน: slug สังเคราะห์ที่มีแต่ในเทสเท่านั้น
    ต้องไม่โผล่ในไฟล์จริงสักไฟล์ — เงื่อนไขนี้ deterministic และตรงกับอาการที่เคยเกิดจริง
    (6 ส.ค. 69: data/sync_lane/fast.json ของจริงกลายเป็น athlete-a/b/c)
    """

    SENTINEL = "zz-synthetic-athlete-do-not-persist"

    # path ที่อ่านอย่างเดียว — อยู่นอก DATA_DIR ได้ ที่เหลือต้องแตกจาก DATA_DIR ทั้งหมด
    READ_ONLY_PATHS = {"PROJECT_ROOT", "SCRIPTS_DIR", "TOKENS_DIR", "BACKFILL"}

    @staticmethod
    def production_files():
        """ไฟล์สถานะจริงที่เทสอาจเผลอไปเขียน (ข้าม garmin.db/-wal/sync.lock ที่ sync
        ของจริงอาจถือ handle อยู่ — เปิดอ่านตอนนั้นจะโดน PermissionError บน Windows
        แล้วเทสแดงเพราะเรื่องที่ไม่เกี่ยวกับการรั่ว. DB ถูกคุ้มครองด้วยเทสโครงสร้างแทน)"""
        if not PRODUCTION_DATA_DIR.exists():
            return []
        return sorted(
            p for p in PRODUCTION_DATA_DIR.rglob("*")
            if p.is_file() and p.suffix in {".json", ".txt"}
        )

    @staticmethod
    def read_safe(path):
        try:
            return path.read_bytes()
        except OSError:      # sync ของจริงถือไฟล์อยู่พอดี — ไม่ใช่หลักฐานการรั่ว
            return None

    def test_isolation_is_actually_engaged(self):
        # ถ้า mixin หยุดทำงานเงียบ ๆ เทสอื่นจะไปเขียนของจริงโดยไม่มีใครรู้
        for module in (fetch_all, backfill):
            with self.subTest(module=module.__name__):
                self.assertEqual(module.DATA_DIR, self.data_dir)
                self.assertNotEqual(module.DATA_DIR, PRODUCTION_DATA_DIR)

    def test_schema_default_database_follows_garmin_data_dir(self):
        expected_data_dir = self.data_dir / "schema-isolated"
        with mock.patch.dict(
            os.environ, {"GARMIN_DATA_DIR": str(expected_data_dir)}
        ):
            isolated_schema = load_script(
                "garmin_schema_isolation_probe", "02_init_schema.py"
            )

        self.assertEqual(isolated_schema.DB_PATH, expected_data_dir / "garmin.db")

    def test_every_writable_path_derives_from_the_data_dir(self):
        # กันกรณีเพิ่มไฟล์สถานะใหม่แล้วลืมให้มันแตกจาก DATA_DIR — ตัวที่หลุดจะรอดการ
        # isolate ทั้งหมดแล้วไปเขียนของจริงเวลารันเทส เหมือนที่ LANE_STATUS_DIR เคยเป็น
        for module in (fetch_all, backfill):
            for name in dir(module):
                if name in self.READ_ONLY_PATHS or name.startswith("_"):
                    continue
                value = getattr(module, name)
                if not isinstance(value, Path):
                    continue
                with self.subTest(module=module.__name__, constant=name):
                    self.assertEqual(
                        value.parts[: len(self.data_dir.parts)],
                        self.data_dir.parts,
                        f"{module.__name__}.{name} ไม่ได้แตกจาก DATA_DIR "
                        f"→ เทสจะเขียนทับของจริงที่ {value}",
                    )

    def test_a_full_orchestration_round_leaves_production_untouched(self):
        before = {p: self.read_safe(p) for p in self.production_files()}

        @contextmanager
        def fake_lock(_timeout):
            yield True

        def fake_run(slug, *_args, **_kwargs):
            return {"slug": slug, "ok": True, "reason": "ok", "warnings": []}

        argv = ["fetch_all.py", "--days", "0", "--activities-only"]
        with (
            mock.patch.object(fetch_all, "list_athletes", return_value=[self.SENTINEL]),
            mock.patch.object(fetch_all, "run_athlete", side_effect=fake_run),
            mock.patch.object(fetch_all, "run_lock", side_effect=fake_lock),
            mock.patch.object(sys, "argv", argv),
            self.assertRaises(SystemExit),
        ):
            fetch_all.main()

        # รอบนี้เขียนจริง (ไม่ใช่ no-op ที่ผ่านเทสฟรี ๆ) แต่เขียนลง temp dir เท่านั้น
        self.assertIn(self.SENTINEL, fetch_all.STATUS_FILE.read_text(encoding="utf-8"))
        self.assertTrue((fetch_all.LANE_STATUS_DIR / "fast.json").exists())

        for path in self.production_files():
            after = self.read_safe(path)
            if after is None:
                continue
            with self.subTest(path=path.name):
                self.assertNotIn(
                    self.SENTINEL,
                    after.decode("utf-8", errors="ignore"),
                    f"เทสรั่วไปเขียน {path}",
                )
                # ไฟล์ที่มีอยู่ก่อนต้องไม่ถูกแตะ (ไฟล์ที่ sync จริงเพิ่งเขียนระหว่างเทส
                # จะไม่อยู่ใน before — ข้ามไป เพราะนั่นคือของจริงไม่ใช่ฝีมือเทส)
                if before.get(path) is not None:
                    self.assertEqual(before[path], after)


class CheckDbCliTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="garmin-check-db-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.script_root = self.temp_dir / "copy"
        (self.script_root / "scripts").mkdir(parents=True)
        (self.script_root / "data").mkdir()
        shutil.copy2(
            GARMIN_ROOT / "scripts" / "check_db.py",
            self.script_root / "scripts" / "check_db.py",
        )

    def test_missing_isolated_database_is_not_created_in_any_location(self):
        isolated_data = self.temp_dir / "isolated-data"
        isolated_data.mkdir()
        env = {**os.environ, "GARMIN_DATA_DIR": str(isolated_data)}

        result = subprocess.run(
            [sys.executable, str(self.script_root / "scripts" / "check_db.py")],
            env=env,
            text=True,
            capture_output=True,
            timeout=10,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((isolated_data / "garmin.db").exists())
        self.assertFalse((self.script_root / "data" / "garmin.db").exists())

    def test_activity_sample_excludes_soft_deleted_rows(self):
        isolated_data = self.temp_dir / "isolated-data"
        db_path = isolated_data / "garmin.db"
        schema.init_schema(db_path)
        conn = sqlite3.connect(db_path)
        self.addCleanup(conn.close)
        conn.execute(
            """INSERT INTO dim_athlete (
                   athlete_id, slug, display_name
               ) VALUES (1, 'probe', 'Probe')"""
        )
        conn.execute(
            """INSERT INTO fact_activity (
                   activity_id, athlete_id, activity_type, start_time_local,
                   duration_sec, deleted_at
               ) VALUES (1, 1, 'active_probe', '2030-01-01 06:00:00', 60, NULL)"""
        )
        conn.execute(
            """INSERT INTO fact_activity (
                   activity_id, athlete_id, activity_type, start_time_local,
                   duration_sec, deleted_at
               ) VALUES (
                   2, 1, 'deleted_probe', '2030-01-02 06:00:00',
                   60, '2030-01-03T00:00:00'
               )"""
        )
        conn.commit()
        env = {**os.environ, "GARMIN_DATA_DIR": str(isolated_data)}

        result = subprocess.run(
            [sys.executable, str(self.script_root / "scripts" / "check_db.py")],
            env=env,
            text=True,
            capture_output=True,
            timeout=10,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("active_probe", result.stdout)
        self.assertNotIn("deleted_probe", result.stdout)


if __name__ == "__main__":
    unittest.main()
