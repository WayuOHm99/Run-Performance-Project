"""Regression tests for Garmin wellness parsing and non-destructive ingestion."""

import ast
import importlib.util
import sqlite3
import unittest
from datetime import date, datetime, timezone
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


backfill = load_script("garmin_wellness_backfill_under_test", "03_backfill.py")
schema = load_script("garmin_wellness_schema_under_test", "02_init_schema.py")


def wellness_db():
    conn = sqlite3.connect(":memory:")
    columns = ", ".join(f"{name} {kind}" for name, kind in schema.WELLNESS_COLUMNS)
    conn.execute(
        f"""CREATE TABLE fact_daily_wellness (
            {columns},
            PRIMARY KEY (athlete_id, calendar_date) ON CONFLICT REPLACE
        )"""
    )
    return conn


def device_db():
    conn = sqlite3.connect(":memory:")
    columns = ", ".join(
        f"{name} {kind}" for name, kind in schema.ATHLETE_DEVICE_COLUMNS
    )
    conn.execute(
        f"""CREATE TABLE dim_athlete_device (
            {columns},
            PRIMARY KEY (athlete_id, device_id)
        )"""
    )
    return conn


class TrainingReadinessParserTests(unittest.TestCase):
    def test_latest_snapshot_is_selected_by_timestamp_not_list_position(self):
        parsed = backfill._parse_readiness([
            {
                "timestamp": "2026-08-09T01:00:00Z",
                "timestampLocal": "2026-08-09T08:00:00+07:00",
                "score": 32,
                "level": "LOW",
            },
            {
                "timestamp": "2026-08-09T04:30:00Z",
                "timestampLocal": "2026-08-09T11:30:00+07:00",
                "score": 78,
                "level": "HIGH",
            },
        ])

        self.assertEqual(parsed["training_readiness"], 78)
        self.assertEqual(parsed["readiness_level"], "HIGH")
        self.assertEqual(parsed["readiness_timestamp_utc"], "2026-08-09T04:30:00Z")
        self.assertEqual(
            parsed["readiness_timestamp_local"], "2026-08-09T11:30:00+07:00"
        )

    def test_score_zero_is_a_real_value_not_a_missing_fallback(self):
        parsed = backfill._parse_readiness({
            "timestamp": 1_786_248_000_000,
            "score": 0,
            "trainingReadinessScore": 88,
        })

        self.assertEqual(parsed["training_readiness"], 0)

    def test_recovery_time_is_stored_as_minutes(self):
        parsed = backfill._parse_readiness({
            "timestamp": "2026-08-09T04:30:00Z",
            "recoveryTime": 5_425,
        })

        self.assertEqual(parsed["recovery_time_min"], 5_425)
        self.assertNotIn("recovery_time_hrs", parsed)

    def test_reached_zero_phrase_wins_over_stale_numeric_value(self):
        parsed = backfill._parse_readiness({
            "timestamp": "2026-08-09T04:30:00Z",
            "recoveryTime": 180,
            "recoveryTimeChangePhrase": "REACHED_ZERO",
        })

        self.assertEqual(parsed["recovery_time_min"], 0)
        self.assertEqual(parsed["recovery_time_change_phrase"], "REACHED_ZERO")

    def test_device_identifier_is_preserved_for_metadata_correlation(self):
        parsed = backfill._parse_readiness({
            "timestamp": "2026-08-09T04:30:00Z",
            "deviceId": 123456789,
            "score": 78,
        })

        self.assertEqual(parsed["readiness_device_id"], "123456789")


class ParserValidationTests(unittest.TestCase):
    def test_hrv_falls_back_per_field_without_losing_nested_last_night(self):
        parsed = backfill._parse_hrv({
            "hrvSummary": {"lastNightAvg": 82, "status": "LOW"},
            "weeklyAvg": 75,
            "lastNightAvg": None,
            "status": None,
        })

        self.assertEqual(parsed["hrv_weekly_avg"], 75)
        self.assertEqual(parsed["hrv_last_night"], 82)
        self.assertEqual(parsed["hrv_status"], "LOW")

    def test_negative_and_non_finite_sentinels_are_removed_in_every_parser_group(self):
        stats = backfill._parse_stats({
            "restingHeartRate": -1,
            "averageStressLevel": float("nan"),
            "bodyBatteryHighestValue": 0,
            "bodyBatteryLowestValue": 20,
        })
        sleep = backfill._parse_sleep({
            "dailySleepDTO": {
                "sleepTimeSeconds": -1,
                "sleepScores": {"overall": {"value": -1}},
            }
        })
        respiration = backfill._parse_respiration({
            "avgSleepRespirationValue": -1,
            "highestRespirationValue": float("inf"),
        })
        readiness = backfill._parse_readiness({
            "trainingReadinessScore": -1,
            "recoveryTime": -1,
            "hrvFactorPercent": 101,
        })

        self.assertIsNone(stats["resting_hr"])
        self.assertIsNone(stats["stress_avg"])
        self.assertIsNone(stats["body_battery_high"])
        self.assertIsNone(sleep["sleep_duration_sec"])
        self.assertIsNone(sleep["sleep_score"])
        self.assertIsNone(respiration["avg_sleep_respiration"])
        self.assertIsNone(respiration["highest_respiration"])
        self.assertIsNone(readiness["training_readiness"])
        self.assertIsNone(readiness["recovery_time_min"])
        self.assertIsNone(readiness["hrv_factor_pct"])

    def test_body_battery_high_low_are_rejected_together_when_one_half_is_missing(self):
        missing_low = backfill._parse_stats({
            "bodyBatteryHighestValue": 80,
        })
        invalid_high = backfill._parse_stats({
            "bodyBatteryHighestValue": 0,
            "bodyBatteryLowestValue": 20,
        })

        self.assertIsNone(missing_low["body_battery_high"])
        self.assertIsNone(missing_low["body_battery_low"])
        self.assertIsNone(invalid_high["body_battery_high"])
        self.assertIsNone(invalid_high["body_battery_low"])


class NullPreservingWellnessMergeTests(unittest.TestCase):
    DAY = "2026-08-08"

    def setUp(self):
        self.conn = wellness_db()
        self.addCleanup(self.conn.close)
        self.conn.execute(
            """INSERT INTO fact_daily_wellness
               (athlete_id, calendar_date, sleep_score, hrv_last_night,
                body_battery_high, body_battery_low, stress_avg, fetched_at)
               VALUES (1, ?, 80, 72, 75, 20, 30, '2026-08-08T03:00:00.000Z')""",
            (self.DAY,),
        )
        self.conn.commit()

    def test_full_upsert_does_not_replace_good_values_with_endpoint_nulls(self):
        changed = backfill._insert_wellness_row(
            self.conn.cursor(),
            1,
            self.DAY,
            {
                "sleep_score": None,
                "hrv_last_night": None,
                "body_battery_high": 48,
                "body_battery_low": 5,
                "stress_avg": 43,
            },
        )
        self.conn.commit()

        row = self.conn.execute(
            """SELECT sleep_score, hrv_last_night, body_battery_high,
                      body_battery_low, stress_avg
               FROM fact_daily_wellness WHERE athlete_id = 1 AND calendar_date = ?""",
            (self.DAY,),
        ).fetchone()
        self.assertEqual(changed, 3)
        self.assertEqual(row, (80.0, 72.0, 48.0, 5.0, 43.0))

    def test_invalid_or_half_body_battery_pair_cannot_mix_with_stored_pair(self):
        self.conn.execute(
            """UPDATE fact_daily_wellness
               SET body_battery_high = 10, body_battery_low = 5
               WHERE athlete_id = 1 AND calendar_date = ?""",
            (self.DAY,),
        )
        parsed = backfill._parse_stats({
            "bodyBatteryHighestValue": 0,
            "bodyBatteryLowestValue": 20,
        })

        changed = backfill._update_wellness_fields(
            self.conn.cursor(), 1, self.DAY, parsed,
        )
        half_changed = backfill._update_wellness_fields(
            self.conn.cursor(), 1, self.DAY, {"body_battery_low": 80},
        )
        self.conn.commit()
        pair = self.conn.execute(
            """SELECT body_battery_high, body_battery_low
               FROM fact_daily_wellness WHERE athlete_id = 1 AND calendar_date = ?""",
            (self.DAY,),
        ).fetchone()

        self.assertEqual(changed, 0)
        self.assertEqual(half_changed, 0)
        self.assertEqual(pair, (10.0, 5.0))

    def test_all_null_full_snapshot_is_a_noop_for_existing_row(self):
        before = self.conn.execute(
            "SELECT * FROM fact_daily_wellness WHERE athlete_id = 1"
        ).fetchone()

        changed = backfill._insert_wellness_row(
            self.conn.cursor(), 1, self.DAY,
            {"sleep_score": None, "hrv_last_night": None},
        )
        self.conn.commit()
        after = self.conn.execute(
            "SELECT * FROM fact_daily_wellness WHERE athlete_id = 1"
        ).fetchone()

        self.assertEqual(changed, 0)
        self.assertEqual(after, before)


class PreviousDayRepairTests(unittest.TestCase):
    DAY = "2026-08-08"
    NOW = datetime(2026, 8, 9, 4, 30, tzinfo=timezone.utc)

    class Garmin:
        def __init__(self, empty=False):
            self.empty = empty
            self.calls = []

        def _value(self, name, payload):
            self.calls.append(name)
            return None if self.empty else payload

        def get_stats(self, _day):
            return self._value("stats", {
                "restingHeartRate": 40,
                "averageStressLevel": 43,
                "totalSteps": 10_318,
                "bodyBatteryHighestValue": 48,
                "bodyBatteryLowestValue": 5,
            })

        def get_hrv_data(self, _day):
            return self._value("hrv", {
                "hrvSummary": {"lastNightAvg": 82, "status": "LOW"}
            })

        def get_sleep_data(self, _day):
            return self._value("sleep", {
                "dailySleepDTO": {
                    "sleepTimeSeconds": 25_000,
                    "sleepScores": {"overall": {"value": 57}},
                }
            })

        def get_respiration_data(self, _day):
            return self._value("respiration", {"avgSleepRespirationValue": 14})

        def get_training_readiness(self, _day):
            return self._value("readiness", [])

    def setUp(self):
        self.conn = wellness_db()
        self.addCleanup(self.conn.close)

    def insert_partial(self, attempted=None):
        self.conn.execute(
            """INSERT INTO fact_daily_wellness
               (athlete_id, calendar_date, resting_hr, stress_avg, steps,
                body_battery_high, body_battery_low, repair_attempted_at_utc)
               VALUES (1, ?, 40, 50, 1347, 5, 5, ?)""",
            (self.DAY, attempted),
        )
        self.conn.commit()

    def test_partial_yesterday_is_due_for_a_targeted_repair(self):
        self.insert_partial()

        due, reasons = backfill._previous_day_repair_due(
            self.conn, 1, self.DAY, now_utc=self.NOW
        )

        self.assertTrue(due)
        self.assertIn("sleep_missing", reasons)
        self.assertIn("hrv_missing", reasons)
        self.assertIn("sleep_respiration_missing", reasons)

    def test_repair_fetches_five_endpoints_and_fills_the_late_cloud_values(self):
        self.insert_partial()
        garmin = self.Garmin()

        with mock.patch.object(backfill.time, "sleep"):
            changed = backfill.fetch_and_repair_previous_day_wellness(
                garmin, self.conn, 1, self.DAY, now_utc=self.NOW
            )

        row = self.conn.execute(
            """SELECT sleep_score, hrv_last_night, body_battery_high,
                      stress_avg, steps, avg_sleep_respiration,
                      repair_attempted_at_utc
               FROM fact_daily_wellness WHERE athlete_id = 1 AND calendar_date = ?""",
            (self.DAY,),
        ).fetchone()
        self.assertEqual(changed, 1)
        self.assertEqual(garmin.calls, [
            "stats", "hrv", "sleep", "respiration", "readiness"
        ])
        self.assertEqual(row[:6], (57.0, 82.0, 48.0, 43.0, 10318.0, 14.0))
        self.assertEqual(row[6], "2026-08-09T04:30:00Z")

    def test_empty_cloud_response_is_throttled_after_one_attempt(self):
        self.insert_partial()
        garmin = self.Garmin(empty=True)

        with mock.patch.object(backfill.time, "sleep"):
            changed = backfill.fetch_and_repair_previous_day_wellness(
                garmin, self.conn, 1, self.DAY, now_utc=self.NOW
            )
        due, reasons = backfill._previous_day_repair_due(
            self.conn,
            1,
            self.DAY,
            now_utc=datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(changed, 0)
        self.assertFalse(due)
        self.assertEqual(reasons, ["cooldown"])

    def test_complete_yesterday_does_not_consume_extra_api_calls(self):
        self.conn.execute(
            """INSERT INTO fact_daily_wellness
               (athlete_id, calendar_date, resting_hr, stress_avg, steps,
                body_battery_high, body_battery_low, sleep_score,
                hrv_last_night, avg_sleep_respiration)
               VALUES (1, ?, 40, 43, 10318, 48, 5, 57, 82, 14)""",
            (self.DAY,),
        )
        self.conn.commit()
        garmin = self.Garmin()

        with mock.patch.object(backfill.time, "sleep"):
            changed = backfill.fetch_and_repair_previous_day_wellness(
                garmin, self.conn, 1, self.DAY, now_utc=self.NOW
            )

        self.assertEqual(changed, 0)
        self.assertEqual(garmin.calls, [])


class RecoverySchemaMigrationTests(unittest.TestCase):
    def test_legacy_raw_minutes_are_copied_without_dividing_by_sixty(self):
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        conn.execute(
            """CREATE TABLE fact_daily_wellness (
                recovery_time_hrs REAL,
                recovery_time_min REAL
            )"""
        )
        conn.execute(
            "INSERT INTO fact_daily_wellness VALUES (5425, NULL)"
        )

        migrated = schema._migrate_recovery_minutes(conn.cursor())

        self.assertEqual(migrated, 1)
        self.assertEqual(
            conn.execute(
                "SELECT recovery_time_hrs, recovery_time_min FROM fact_daily_wellness"
            ).fetchone(),
            (5425.0, 5425.0),
        )


class DeviceInventoryTests(unittest.TestCase):
    class Garmin:
        def __init__(self, payload):
            self.payload = payload
            self.calls = 0

        def get_devices(self):
            self.calls += 1
            return self.payload

    def setUp(self):
        self.conn = device_db()
        self.addCleanup(self.conn.close)

    def test_only_whitelisted_model_names_and_primary_flags_are_stored(self):
        garmin = self.Garmin([{
            "deviceId": 123456789,
            "productDisplayName": "Forerunner Synthetic",
            "displayName": "Morning watch",
            "isPrimaryDevice": True,
            "isPrimaryActivityTracker": "yes",
            "isPrimaryTrainingDevice": 1,
            "serialNumber": "must-not-be-stored",
            "wifiPassword": "must-not-be-stored",
        }])

        count = backfill.fetch_and_upsert_devices(garmin, self.conn, 1)

        self.assertEqual(count, 1)
        self.assertEqual(garmin.calls, 1)
        columns = {
            row[1] for row in self.conn.execute("PRAGMA table_info(dim_athlete_device)")
        }
        self.assertNotIn("serialNumber", columns)
        self.assertNotIn("wifiPassword", columns)
        row = self.conn.execute(
            """SELECT device_id, product_display_name, display_name,
                      is_primary_device, is_primary_activity_tracker,
                      is_primary_training_device
                 FROM dim_athlete_device"""
        ).fetchone()
        self.assertEqual(
            row,
            ("123456789", "Forerunner Synthetic", "Morning watch", 1, 1, 1),
        )

    def test_partial_refresh_does_not_erase_a_previously_known_model_name(self):
        backfill.fetch_and_upsert_devices(
            self.Garmin([{
                "deviceId": "dev-1",
                "productDisplayName": "Forerunner Stable",
                "displayName": "Runner",
                "isPrimaryDevice": True,
            }]),
            self.conn,
            1,
        )

        backfill.fetch_and_upsert_devices(
            self.Garmin([{"deviceId": "dev-1", "isPrimaryDevice": False}]),
            self.conn,
            1,
        )

        row = self.conn.execute(
            """SELECT product_display_name, display_name, is_primary_device
                 FROM dim_athlete_device WHERE athlete_id = 1 AND device_id = 'dev-1'"""
        ).fetchone()
        self.assertEqual(row, ("Forerunner Stable", "Runner", 0))

    def test_invalid_or_duplicate_device_ids_are_skipped(self):
        count = backfill.fetch_and_upsert_devices(
            self.Garmin([
                {"deviceId": True, "productDisplayName": "boolean"},
                {"deviceId": "bad id/with spaces", "productDisplayName": "bad"},
                {"deviceId": "ok-1", "productDisplayName": "first"},
                {"deviceId": "ok-1", "productDisplayName": "duplicate"},
            ]),
            self.conn,
            1,
        )

        self.assertEqual(count, 1)
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM dim_athlete_device").fetchone()[0],
            1,
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT product_display_name FROM dim_athlete_device"
            ).fetchone()[0],
            "first",
        )

    def test_device_inventory_is_only_called_from_full_extras_not_fast_wellness(self):
        source = (GARMIN_ROOT / "scripts" / "03_backfill.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        callers = set()
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            if any(
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "fetch_and_upsert_devices"
                for child in ast.walk(node)
            ):
                callers.add(node.name)

        self.assertEqual(callers, {"fetch_and_insert_extras"})


class SanityPartialSnapshotTests(unittest.TestCase):
    class FrozenDateTime(datetime):
        """09 Aug in Bangkok, while the UTC calendar date is still 08 Aug."""

        @classmethod
        def now(cls, tz=None):
            instant = cls(2026, 8, 8, 18, 30, tzinfo=timezone.utc)
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)

    def setUp(self):
        self.conn = wellness_db()
        self.addCleanup(self.conn.close)

    def _insert(self, day, *, sleep=None, hrv=None, sleep_resp=None):
        self.conn.execute(
            """INSERT INTO fact_daily_wellness
               (athlete_id, calendar_date, resting_hr, stress_avg, steps,
                body_battery_high, sleep_score, hrv_last_night,
                avg_sleep_respiration)
               VALUES (1, ?, 40, 43, 10318, 48, ?, ?, ?)""",
            (day, sleep, hrv, sleep_resp),
        )
        self.conn.commit()

    def _check(self, start="2026-08-07", end="2026-08-09"):
        with mock.patch.object(backfill, "datetime", self.FrozenDateTime):
            return backfill.sanity_check(
                self.conn,
                1,
                date.fromisoformat(start),
                date.fromisoformat(end),
                include_activities=False,
                include_wellness=True,
            )

    def test_bangkok_yesterday_partial_snapshot_warns_even_while_utc_is_previous_date(self):
        self._insert("2026-08-08")

        warnings = self._check()

        partial = [message for message in warnings if "partial snapshot" in message]
        self.assertEqual(len(partial), 1)
        self.assertIn("2026-08-08", partial[0])
        self.assertIn("Sleep/HRV/sleep respiration", partial[0])

    def test_unfinished_bangkok_today_is_not_reported_as_partial(self):
        self._insert("2026-08-09")

        warnings = self._check()

        self.assertFalse(any("partial snapshot" in message for message in warnings))

    def test_one_missing_nightly_field_does_not_trigger_partial_warning(self):
        self._insert("2026-08-08", sleep=80, hrv=70, sleep_resp=None)

        warnings = self._check()

        self.assertFalse(any("partial snapshot" in message for message in warnings))


if __name__ == "__main__":
    unittest.main()
