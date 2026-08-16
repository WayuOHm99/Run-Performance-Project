"""Regression tests for read-only field-level data-quality monitoring."""

import importlib.util
import io
import json
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


GARMIN_ROOT = Path(__file__).resolve().parents[1]


def load_script(name, filename):
    spec = importlib.util.spec_from_file_location(
        name, GARMIN_ROOT / "scripts" / filename
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dq = load_script("garmin_data_quality_under_test", "data_quality.py")
drift = load_script("garmin_check_drift_under_test", "check_drift.py")
health = load_script("garmin_health_data_quality_under_test", "health_report.py")


def create_db(path=":memory:"):
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE dim_athlete (athlete_id INTEGER PRIMARY KEY, slug TEXT)"
    )
    conn.execute("INSERT INTO dim_athlete VALUES (1, 'synthetic')")
    conn.execute(
        """CREATE TABLE fact_daily_wellness (
            athlete_id INTEGER NOT NULL,
            calendar_date TEXT NOT NULL,
            resting_hr REAL,
            hrv_weekly_avg REAL,
            hrv_last_night REAL,
            sleep_score REAL,
            sleep_duration_sec REAL,
            deep_sleep_sec REAL,
            light_sleep_sec REAL,
            rem_sleep_sec REAL,
            awake_sec REAL,
            body_battery_high REAL,
            body_battery_low REAL,
            bb_at_wake REAL,
            bb_charged REAL,
            bb_drained REAL,
            bb_during_sleep REAL,
            bb_most_recent REAL,
            stress_avg REAL,
            max_stress REAL,
            steps REAL,
            steps_goal REAL,
            floors_ascended REAL,
            active_kilocalories REAL,
            bmr_kilocalories REAL,
            active_seconds REAL,
            avg_waking_respiration REAL,
            avg_sleep_respiration REAL,
            highest_respiration REAL,
            lowest_respiration REAL,
            readiness_device_id TEXT,
            training_readiness REAL,
            acute_load REAL,
            acwr_percent REAL,
            hrv_factor_pct REAL,
            recovery_time_min REAL,
            recovery_time_hrs REAL,
            stress_history_pct REAL,
            training_status TEXT,
            fetched_at TEXT,
            PRIMARY KEY (athlete_id, calendar_date)
        )"""
    )
    conn.execute(
        """CREATE TABLE fact_activity (
            activity_id INTEGER PRIMARY KEY,
            athlete_id INTEGER,
            start_time_local TEXT,
            training_load REAL,
            avg_hr REAL,
            training_effect_aerobic REAL,
            training_effect_anaerobic REAL,
            deleted_at TEXT
        )"""
    )
    conn.commit()
    return conn


def insert_complete_day(conn, day, **overrides):
    values = {
        "resting_hr": 50,
        "hrv_last_night": 70,
        "sleep_score": 80,
        "body_battery_high": 85,
        "body_battery_low": 20,
        "stress_avg": 30,
        "steps": 10_000,
        "avg_sleep_respiration": 14,
        "recovery_time_min": 90,
    }
    values.update(overrides)
    columns = ["athlete_id", "calendar_date", *values]
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO fact_daily_wellness ({', '.join(columns)}) VALUES ({placeholders})",
        (1, day.isoformat(), *values.values()),
    )


class BangkokWindowTests(unittest.TestCase):
    def test_utc_evening_is_already_the_next_bangkok_date(self):
        instant = datetime(2026, 8, 8, 18, 30, tzinfo=timezone.utc)

        self.assertEqual(dq.bangkok_today(instant), date(2026, 8, 9))
        self.assertEqual(
            dq.completed_window(dq.bangkok_today(instant), 30),
            ("2026-07-10", "2026-08-08"),
        )

    def test_coverage_excludes_unfinished_bangkok_today(self):
        conn = create_db()
        self.addCleanup(conn.close)
        insert_complete_day(conn, date(2026, 8, 8))
        insert_complete_day(conn, date(2026, 8, 9), sleep_score=None)
        conn.commit()

        coverage = dq.coverage_for_athlete(
            conn, 1, today=datetime(2026, 8, 8, 18, 30, tzinfo=timezone.utc)
        )
        sleep = next(item for item in coverage if item["field"] == "sleep_score")
        self.assertEqual(sleep["recent"], (1, 30))
        self.assertEqual(sleep["short"], (1, 7))


class DriftAndPartialSnapshotTests(unittest.TestCase):
    def test_material_seven_day_drop_is_caught_before_it_reaches_twenty_percent(self):
        finding = dq.judge_drift(
            "wellness", "sleep_score", (3, 7), (27, 30), horizon_days=7
        )

        self.assertIsNotNone(finding)
        self.assertEqual(finding["level"], "WARNING")

    def test_field_never_supported_by_this_athlete_is_not_drift(self):
        self.assertIsNone(
            dq.judge_drift(
                "wellness", "training_readiness", (0, 7), (0, 30),
                horizon_days=7,
            )
        )

    def test_yesterday_daytime_only_row_is_reported_as_partial_snapshot(self):
        conn = create_db()
        self.addCleanup(conn.close)
        today = date(2026, 8, 9)
        for offset in range(2, 32):
            insert_complete_day(conn, today - timedelta(days=offset))
        insert_complete_day(
            conn,
            today - timedelta(days=1),
            sleep_score=None,
            hrv_last_night=None,
            avg_sleep_respiration=None,
        )
        conn.commit()

        findings = dq.partial_snapshot_findings(conn, 1, today=today)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["calendar_date"], "2026-08-08")
        self.assertIn("sleep_score", findings[0]["missing"])
        self.assertIn("steps", findings[0]["present"])

    def test_whole_day_outage_is_counted_as_zero_of_seven_calendar_days(self):
        conn = create_db()
        self.addCleanup(conn.close)
        today = date(2026, 8, 9)
        for offset in range(8, 38):
            insert_complete_day(conn, today - timedelta(days=offset))
        conn.commit()

        findings, coverage = dq.check_athlete(conn, "synthetic", 1, today=today)
        sleep = next(item for item in coverage if item["field"] == "sleep_score")
        sleep_drift = next(
            finding for finding in findings
            if finding["kind"] == "drift" and finding["field"] == "sleep_score"
        )

        self.assertEqual(sleep["short"], (0, 7))
        self.assertEqual(sleep["short_baseline"], (30, 30))
        self.assertEqual(sleep_drift["level"], "ERROR")

    def test_single_silent_day_without_device_signal_is_only_a_warning(self):
        """นาฬิกาไม่ได้ sync 1 วัน = เรื่องปกติของนักกีฬา ไม่ใช่ระบบพัง

        ตี ERROR ทุกครั้งจะทำให้ health report/heartbeat แดงค้างจนกว่านักกีฬาจะ
        เปิดแอป — แล้วสีแดงก็เลิกมีความหมาย (บทเรียน 5 ส.ค. 69 เรื่อง noise)
        """
        conn = create_db()
        self.addCleanup(conn.close)
        today = date(2026, 8, 9)
        for offset in range(2, 32):
            insert_complete_day(conn, today - timedelta(days=offset))
        conn.commit()

        findings = dq.partial_snapshot_findings(conn, 1, today=today)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["kind"], "missing_snapshot")
        self.assertEqual(findings[0]["level"], "WARNING")
        self.assertEqual(findings[0]["reason"], "row_missing")
        self.assertFalse(findings[0]["device_signal"])
        self.assertEqual(findings[0]["silent_days"], 1)

    def test_missing_wellness_on_a_day_that_had_activities_is_an_error(self):
        """มีกิจกรรมเข้ามาแต่ wellness หายทั้งชุด = นาฬิกา sync แล้วแต่เราเก็บไม่ครบ."""
        conn = create_db()
        self.addCleanup(conn.close)
        today = date(2026, 8, 9)
        for offset in range(2, 32):
            insert_complete_day(conn, today - timedelta(days=offset))
        conn.execute(
            """INSERT INTO fact_activity (activity_id, athlete_id, start_time_local)
               VALUES (99, 1, ?)""",
            (f"{(today - timedelta(days=1)).isoformat()} 06:15:00",),
        )
        conn.commit()

        findings = dq.partial_snapshot_findings(conn, 1, today=today)

        self.assertEqual(findings[0]["level"], "ERROR")
        self.assertTrue(findings[0]["device_signal"])

    def test_deleted_activity_does_not_count_as_a_device_signal(self):
        conn = create_db()
        self.addCleanup(conn.close)
        today = date(2026, 8, 9)
        for offset in range(2, 32):
            insert_complete_day(conn, today - timedelta(days=offset))
        conn.execute(
            """INSERT INTO fact_activity
                   (activity_id, athlete_id, start_time_local, deleted_at)
               VALUES (99, 1, ?, '2026-08-09T00:00:00Z')""",
            (f"{(today - timedelta(days=1)).isoformat()} 06:15:00",),
        )
        conn.commit()

        findings = dq.partial_snapshot_findings(conn, 1, today=today)

        self.assertEqual(findings[0]["level"], "WARNING")
        self.assertFalse(findings[0]["device_signal"])

    def test_three_silent_days_in_a_row_escalate_back_to_error(self):
        conn = create_db()
        self.addCleanup(conn.close)
        today = date(2026, 8, 9)
        for offset in range(4, 34):
            insert_complete_day(conn, today - timedelta(days=offset))
        conn.commit()

        findings = dq.partial_snapshot_findings(conn, 1, today=today)

        self.assertEqual(findings[0]["level"], "ERROR")
        self.assertEqual(findings[0]["silent_days"], dq.DEVICE_SILENT_ERROR_DAYS)

    def test_all_empty_yesterday_row_is_error_when_baseline_expects_wellness(self):
        conn = create_db()
        self.addCleanup(conn.close)
        today = date(2026, 8, 9)
        for offset in range(2, 32):
            insert_complete_day(conn, today - timedelta(days=offset))
        conn.execute(
            "INSERT INTO fact_daily_wellness (athlete_id, calendar_date) VALUES (1, ?)",
            ((today - timedelta(days=1)).isoformat(),),
        )
        conn.commit()

        findings = dq.partial_snapshot_findings(conn, 1, today=today)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["kind"], "missing_snapshot")
        self.assertEqual(findings[0]["reason"], "row_empty")

    def test_one_daytime_field_still_counts_as_severe_partial_snapshot(self):
        conn = create_db()
        self.addCleanup(conn.close)
        today = date(2026, 8, 9)
        for offset in range(2, 32):
            insert_complete_day(conn, today - timedelta(days=offset))
        conn.execute(
            """INSERT INTO fact_daily_wellness (athlete_id, calendar_date, steps)
               VALUES (1, ?, 1234)""",
            ((today - timedelta(days=1)).isoformat(),),
        )
        conn.commit()

        findings = dq.partial_snapshot_findings(conn, 1, today=today)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["kind"], "partial_snapshot")
        self.assertEqual(findings[0]["present"], ["steps"])
        self.assertIn("sleep_score", findings[0]["missing"])
        self.assertIn("hrv_last_night", findings[0]["missing"])

    def test_new_sparse_athlete_does_not_trigger_missing_snapshot(self):
        conn = create_db()
        self.addCleanup(conn.close)

        self.assertEqual(
            dq.partial_snapshot_findings(conn, 1, today=date(2026, 8, 9)), []
        )

    def test_legacy_recovery_and_device_id_are_not_coverage_metrics(self):
        conn = create_db()
        self.addCleanup(conn.close)
        insert_complete_day(conn, date(2026, 8, 8))
        conn.execute(
            """UPDATE fact_daily_wellness
               SET recovery_time_hrs = 90, readiness_device_id = 'private-device'
               WHERE athlete_id = 1 AND calendar_date = '2026-08-08'"""
        )
        conn.commit()

        fields = {
            item["field"] for item in dq.coverage_for_athlete(
                conn, 1, today=date(2026, 8, 9)
            ) if item["table"] == "wellness"
        }

        self.assertIn("recovery_time_min", fields)
        self.assertNotIn("recovery_time_hrs", fields)
        self.assertNotIn("readiness_device_id", fields)


class ActivityCoverageTests(unittest.TestCase):
    def test_training_effect_columns_are_monitored_under_their_schema_names(self):
        conn = create_db()
        self.addCleanup(conn.close)

        fields = {
            item["field"] for item in dq.coverage_for_athlete(
                conn, 1, today=date(2030, 2, 1)
            ) if item["table"] == "activity"
        }

        self.assertIn("training_effect_aerobic", fields)
        self.assertIn("training_effect_anaerobic", fields)
        self.assertNotIn("aerobic_te", fields)
        self.assertNotIn("anaerobic_te", fields)

    def test_iso_t_activity_on_window_end_is_included_in_coverage(self):
        conn = create_db()
        self.addCleanup(conn.close)
        conn.execute(
            """INSERT INTO fact_activity (
                   activity_id, athlete_id, start_time_local, training_load,
                   deleted_at
               ) VALUES (1, 1, '2030-01-31T08:00:00', 42, NULL)"""
        )
        conn.commit()

        coverage = dq.coverage_for_athlete(conn, 1, today=date(2030, 2, 1))
        training_load = next(
            item for item in coverage
            if item["table"] == "activity" and item["field"] == "training_load"
        )

        self.assertEqual(training_load["recent"], (1, 1))

    def test_activity_offset_does_not_shift_its_local_calendar_date(self):
        conn = create_db()
        self.addCleanup(conn.close)
        conn.execute(
            """INSERT INTO fact_activity (
                   activity_id, athlete_id, start_time_local, training_load,
                   deleted_at
               ) VALUES (1, 1, '2030-01-02T00:30:00+07:00', 42, NULL)"""
        )
        conn.commit()

        coverage = dq.coverage_for_athlete(conn, 1, today=date(2030, 2, 1))
        training_load = next(
            item for item in coverage
            if item["table"] == "activity" and item["field"] == "training_load"
        )

        # start_time_local is a wall-clock timestamp.  Applying SQLite date()
        # would convert +07:00 to UTC and incorrectly move this row to Jan 1.
        self.assertEqual(training_load["recent"], (1, 1))


class SentinelAndRangeTests(unittest.TestCase):
    def test_invalid_sentinels_ranges_and_relations_are_reported(self):
        conn = create_db()
        self.addCleanup(conn.close)
        day = date(2026, 8, 8)
        insert_complete_day(
            conn,
            day,
            resting_hr=136,
            body_battery_high=0,
            body_battery_low=4,
            stress_avg=-1,
            recovery_time_min=5_425,
            recovery_time_hrs=5_425,
        )
        conn.commit()

        findings = dq.range_findings(conn, 1, today=date(2026, 8, 9))
        fields = {finding["field"] for finding in findings}

        self.assertIn("resting_hr", fields)
        self.assertIn("body_battery_high", fields)
        self.assertIn("body_battery_low", fields)
        self.assertIn("stress_avg", fields)
        self.assertNotIn("recovery_time_min", fields)
        self.assertNotIn("recovery_time_hrs", fields)

    def test_body_battery_high_below_low_is_reported(self):
        conn = create_db()
        self.addCleanup(conn.close)
        insert_complete_day(
            conn, date(2026, 8, 8), body_battery_high=30, body_battery_low=40
        )
        conn.commit()

        findings = dq.range_findings(conn, 1, today=date(2026, 8, 9))

        self.assertIn(
            "body_battery_high>=body_battery_low",
            {finding["field"] for finding in findings},
        )


class MonitoringIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="data-quality-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.db_path = self.temp_dir / "garmin.db"
        conn = create_db(self.db_path)
        insert_complete_day(conn, date(2026, 8, 8))
        conn.commit()
        conn.close()

    def test_health_data_quality_check_is_read_only_and_reports_coverage(self):
        previous = health.use_data_dir(self.temp_dir)
        self.addCleanup(health.use_data_dir, previous)
        before = self.db_path.read_bytes()

        findings = health.check_data_quality(
            now=datetime(2026, 8, 9, 1, 0, tzinfo=timezone.utc)
        )

        self.assertEqual(before, self.db_path.read_bytes())
        coverage = [f for f in findings if f.check == "data_quality_coverage:synthetic"]
        self.assertEqual(len(coverage), 1)
        self.assertIn("sleep_score=1/30", coverage[0].message)
        self.assertEqual(coverage[0].level, health.WARNING)

    def test_check_drift_json_uses_isolated_db_and_machine_readable_coverage(self):
        previous = drift.use_data_dir(self.temp_dir)
        self.addCleanup(drift.use_data_dir, previous)
        output = io.StringIO()
        before = self.db_path.read_bytes()

        with redirect_stdout(output):
            exit_code = drift.main(["--athlete", "synthetic", "--today", "2026-08-09", "--json"])

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["today_bangkok"], "2026-08-09")
        self.assertEqual(payload["athletes"][0]["slug"], "synthetic")
        self.assertTrue(payload["athletes"][0]["coverage"])
        self.assertEqual(before, self.db_path.read_bytes())

    def test_check_drift_json_normalizes_non_finite_examples_to_strict_json(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """UPDATE fact_daily_wellness SET resting_hr = ?
               WHERE athlete_id = 1 AND calendar_date = '2026-08-08'""",
            (float("inf"),),
        )
        conn.commit()
        conn.close()
        previous = drift.use_data_dir(self.temp_dir)
        self.addCleanup(drift.use_data_dir, previous)
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = drift.main([
                "--athlete", "synthetic", "--today", "2026-08-09", "--json"
            ])

        payload = json.loads(
            output.getvalue(),
            parse_constant=lambda token: self.fail(f"non-standard JSON token: {token}"),
        )
        resting = next(
            finding for finding in payload["findings"]
            if finding["kind"] == "range" and finding["field"] == "resting_hr"
        )
        self.assertEqual(exit_code, 1)
        self.assertEqual(resting["examples"][0][1], "Infinity")

    def test_check_drift_atomically_persists_deep_lane_failure(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """UPDATE fact_daily_wellness SET resting_hr = ?
               WHERE athlete_id = 1 AND calendar_date = '2026-08-08'""",
            (float("inf"),),
        )
        conn.commit()
        conn.close()
        lane_dir = self.temp_dir / "sync_lane"
        lane_dir.mkdir()
        lane_path = lane_dir / "deep.json"
        lane_path.write_text(
            json.dumps({
                "run_at": "2026-08-09T10:30:00",
                "lane": "deep",
                "results": [{"slug": "synthetic", "ok": True, "reason": "ok", "warnings": []}],
            }),
            encoding="utf-8",
        )
        previous = drift.use_data_dir(self.temp_dir)
        self.addCleanup(drift.use_data_dir, previous)

        with redirect_stdout(io.StringIO()):
            exit_code = drift.main([
                "--today", "2026-08-09", "--json", "--record-deep-status"
            ])

        payload = json.loads(lane_path.read_text(encoding="utf-8"))
        durable = [r for r in payload["results"] if r.get("reason") == "drift"]
        self.assertEqual(exit_code, 1)
        self.assertEqual(len(durable), 1)
        self.assertFalse(durable[0]["ok"])
        self.assertEqual(list(lane_dir.glob("*.tmp")), [])

    def test_silent_watch_does_not_fail_the_monthly_deep_lane(self):
        """สาย deep รันเดือนละครั้ง — ตีว่า failed เพราะนักกีฬาไม่ได้ sync
        = ธงแดงค้างบน dashboard 4 สัปดาห์โดยไม่มีอะไรให้แก้"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM fact_daily_wellness")
        conn.execute("DELETE FROM fact_activity")
        today = date(2026, 8, 9)
        for offset in range(2, 32):
            insert_complete_day(conn, today - timedelta(days=offset))
        conn.commit()
        conn.close()
        lane_dir = self.temp_dir / "sync_lane"
        lane_dir.mkdir(exist_ok=True)
        lane_path = lane_dir / "deep.json"
        lane_path.write_text(
            json.dumps({
                "run_at": "2026-08-09T10:30:00",
                "lane": "deep",
                "results": [{"slug": "synthetic", "ok": True, "reason": "ok", "warnings": []}],
            }),
            encoding="utf-8",
        )
        previous = drift.use_data_dir(self.temp_dir)
        self.addCleanup(drift.use_data_dir, previous)
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = drift.main([
                "--today", "2026-08-09", "--json", "--record-deep-status"
            ])

        payload = json.loads(output.getvalue())
        lane = json.loads(lane_path.read_text(encoding="utf-8"))
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["summary"]["athlete_side"], 1)
        self.assertEqual(payload["summary"]["system"], 0)
        self.assertTrue(all(item["ok"] for item in lane["results"]))

    def test_check_drift_unknown_explicit_athlete_is_an_error(self):
        previous = drift.use_data_dir(self.temp_dir)
        self.addCleanup(drift.use_data_dir, previous)
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = drift.main([
                "--athlete", "typo-does-not-exist", "--today", "2026-08-09", "--json"
            ])

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertFalse(payload["ok"])
        self.assertIn("ไม่พบนักกีฬา", payload["error"])

    def _missing_snapshot_finding(self, today):
        previous = health.use_data_dir(self.temp_dir)
        self.addCleanup(health.use_data_dir, previous)
        return next(
            finding for finding in health.check_data_quality(now=today)
            if ":missing_snapshot:" in finding.check
        )

    def test_health_reports_a_silent_watch_as_an_actionable_warning(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM fact_daily_wellness")
        conn.execute("DELETE FROM fact_activity")
        today = date(2026, 8, 9)
        for offset in range(2, 32):
            insert_complete_day(conn, today - timedelta(days=offset))
        conn.commit()
        conn.close()

        missing = self._missing_snapshot_finding(today)

        self.assertEqual(missing.level, health.WARNING)
        self.assertIn("ขาด wellness ทั้ง snapshot", missing.message)
        self.assertIn("เปิดแอป Garmin sync", missing.message)

    def test_health_reports_missing_snapshot_as_error_when_the_watch_did_sync(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM fact_daily_wellness")
        conn.execute("DELETE FROM fact_activity")
        today = date(2026, 8, 9)
        for offset in range(2, 32):
            insert_complete_day(conn, today - timedelta(days=offset))
        conn.execute(
            """INSERT INTO fact_activity (activity_id, athlete_id, start_time_local)
               VALUES (4242, 1, ?)""",
            (f"{(today - timedelta(days=1)).isoformat()} 18:02:00",),
        )
        conn.commit()
        conn.close()

        missing = self._missing_snapshot_finding(today)

        self.assertEqual(missing.level, health.ERROR)
        self.assertIn("ตรวจ endpoint/parser", missing.message)


if __name__ == "__main__":
    unittest.main()
