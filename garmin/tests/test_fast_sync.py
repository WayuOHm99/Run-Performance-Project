import importlib.util
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from datetime import datetime
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
            PRIMARY KEY (activity_id, split_num)
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

    def test_full_wellness_still_writes_every_field_group(self):
        conn = create_wellness_db()
        self.addCleanup(conn.close)
        garmin = SyntheticWellnessGarmin()

        with mock.patch.object(backfill.time, "sleep"):
            count = backfill.fetch_and_insert_wellness(
                garmin, conn, 1, backfill.date(2030, 1, 2), backfill.date(2030, 1, 2)
            )

        row = conn.execute(
            """SELECT resting_hr, hrv_status, sleep_score, deep_sleep_sec, acute_load,
                      avg_waking_respiration, avg_sleep_respiration, training_status,
                      vo2max_trend, fitness_age, endurance_score, hill_score_strength
               FROM fact_daily_wellness WHERE athlete_id = 1 AND calendar_date = ?""",
            (self.DAY,),
        ).fetchone()
        self.assertEqual(count, 1)
        self.assertEqual(
            row,
            (48.0, "BALANCED", 82.0, 4000.0, 420.0, 14.0, 13.0, "PRODUCTIVE",
             52.5, 24.0, 6100.0, 50.0),
        )


class FetchAllOrchestrationTests(unittest.TestCase):
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

        captured = {}
        status_path = mock.MagicMock()
        temp_status_path = mock.MagicMock()
        status_path.with_suffix.return_value = temp_status_path
        temp_status_path.write_text.side_effect = (
            lambda text, **_kwargs: captured.update(text=text)
        )
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
            mock.patch.object(fetch_all, "STATUS_FILE", status_path),
            mock.patch.object(sys, "argv", argv),
            self.assertRaises(SystemExit) as exited,
        ):
            fetch_all.main()

        payload = fetch_all.json.loads(captured["text"])
        self.assertEqual(exited.exception.code, 0)
        self.assertEqual(max_active, 2)
        self.assertEqual(
            [result["slug"] for result in payload["results"]],
            athletes,
        )
        # สายถี่ต้องยอมแพ้เร็ว ไม่กอด sync.lock ไว้จนสายอื่นอดทั้งชั่วโมง
        self.assertEqual(set(timeouts), {fetch_all.ATHLETE_TIMEOUT_SEC["fast"]})


class CatchUpSlotTests(unittest.TestCase):
    """--catch-up-slots: Task ยิงทุกชั่วโมง แต่ต้องทำงานจริงแค่ช่องละครั้ง."""

    def setUp(self):
        self.lane_dir = Path(
            tempfile.mkdtemp(prefix="lane-", dir=None)
        )
        self.addCleanup(shutil.rmtree, self.lane_dir, True)
        patcher = mock.patch.object(fetch_all, "LANE_STATUS_DIR", self.lane_dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.slots = fetch_all.parse_slots("08:00,21:00")

    def write_lane(self, run_at):
        (self.lane_dir / "full.json").write_text(
            fetch_all.json.dumps({"run_at": run_at.isoformat(timespec="seconds")}),
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


if __name__ == "__main__":
    unittest.main()
