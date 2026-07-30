import importlib.util
import sqlite3
import sys
import threading
import time
import unittest
from contextlib import contextmanager
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
    def test_fast_sync_preserves_enrichment_and_does_not_call_detail_endpoints(self):
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

        count = backfill.fetch_and_insert_activities(
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
        self.assertEqual(count, 1)
        self.assertEqual(
            row,
            (5100.0, 77.0, 9.0, 80.0, 40.0, 25.0, 60.0, 120.0, 300.0, None),
        )
        self.assertIsNone(missing_deleted_at)
        self.assertEqual(
            (garmin.detail_calls, garmin.weather_calls, garmin.split_calls),
            (0, 0, 0),
        )

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


class FetchAllOrchestrationTests(unittest.TestCase):
    def test_main_uses_bounded_concurrency_and_keeps_status_order(self):
        athletes = ["athlete-a", "athlete-b", "athlete-c"]
        active = 0
        max_active = 0
        guard = threading.Lock()

        def fake_run(slug, _args, _passthrough, _started):
            nonlocal active, max_active
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


if __name__ == "__main__":
    unittest.main()
