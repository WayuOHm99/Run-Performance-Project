import datetime as dt
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from dashboard_freshness import format_gap_ranges, load_freshness, read_sync_summary, summarize_dates
import run_demo
from dashboard_tab_harness import LAST_DAY, SYSTEM_PAGE, page_text, render_page


class CoverageTests(unittest.TestCase):
    def test_internal_and_trailing_gaps_exclude_today_and_before_first_receipt(self):
        today = dt.date(2026, 10, 4)
        result = summarize_dates(["2026-10-01", "2026-10-03"], dt.date(2026, 9, 1), today, today)
        self.assertEqual(result["latest"], dt.date(2026, 10, 3))
        self.assertEqual(result["gaps"], [dt.date(2026, 10, 2)])

    def test_future_and_invalid_dates_cannot_claim_current_data(self):
        today = dt.date(2026, 10, 4)
        result = summarize_dates(["invalid", None, "2027-01-01"], today, today, today)
        self.assertIsNone(result["latest"])
        self.assertFalse(result["has_history"])
        self.assertEqual(result["gaps"], [])

    def test_new_athlete_is_no_history_instead_of_a_month_of_failures(self):
        result = summarize_dates([], LAST_DAY - dt.timedelta(days=29), LAST_DAY, LAST_DAY)
        self.assertFalse(result["has_history"])
        self.assertEqual(result["gaps"], [])

    def test_selected_historical_end_limits_gap_check(self):
        start = dt.date(2026, 10, 1)
        result = summarize_dates(["2026-10-01"], start, start, dt.date(2026, 10, 4))
        self.assertEqual(result["gaps"], [])

    def test_gap_ranges_keep_year_at_year_boundary(self):
        self.assertEqual(format_gap_ranges([dt.date(2025, 12, 31), dt.date(2026, 1, 1)]),
                         "31/12/2025–01/01/2026")

    def test_coverage_ignores_empty_daily_rows_and_deleted_activity(self):
        import streamlit as st
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            path = run_demo.create_demo_database(directory, LAST_DAY)
            with sqlite3.connect(path) as conn:
                conn.execute("INSERT INTO fact_daily_wellness (athlete_id, calendar_date) VALUES (3, ?)",
                             (LAST_DAY.isoformat(),))
                conn.execute("INSERT INTO fact_activity (activity_id, athlete_id, fetched_at, deleted_at)"
                             " VALUES (999, 3, ?, 'deleted')", (f"{LAST_DAY}T01:00:00Z",))
            with patch.dict(os.environ, {"GARMIN_DATA_DIR": directory}):
                st.cache_data.clear()
                result = load_freshness(3, LAST_DAY - dt.timedelta(days=29), LAST_DAY, LAST_DAY)
            self.assertFalse(result["has_history"])
            self.assertEqual(result["received_at"], "–")
            st.cache_data.clear()

    def test_selected_athlete_has_own_date_and_gaps(self):
        import streamlit as st
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            run_demo.create_demo_database(directory, LAST_DAY)
            with patch.dict(os.environ, {"GARMIN_DATA_DIR": directory}):
                st.cache_data.clear()
                a = load_freshness(1, LAST_DAY - dt.timedelta(days=29), LAST_DAY, LAST_DAY)
                b = load_freshness(2, LAST_DAY - dt.timedelta(days=29), LAST_DAY, LAST_DAY)
            self.assertEqual(a["latest"], LAST_DAY)
            self.assertEqual(a["gaps"], [])
            self.assertEqual(b["latest"], LAST_DAY - dt.timedelta(days=2))
            self.assertEqual(b["gaps"], [LAST_DAY - dt.timedelta(days=5), LAST_DAY - dt.timedelta(days=1)])
            st.cache_data.clear()


class SyncSummaryTests(unittest.TestCase):
    def read(self, payload):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "sync_status"
            target.mkdir()
            (target / "demo.json").write_text(json.dumps(payload), encoding="utf-8")
            with patch.dict(os.environ, {"GARMIN_DATA_DIR": directory}):
                return read_sync_summary("demo")

    def test_malformed_shapes_and_non_boolean_success_are_not_success(self):
        for value in [[], None, "text", {"ok": "false"}, {"ok": 1}]:
            with self.subTest(value=value):
                self.assertEqual(self.read(value)["result"], "ไม่มีบันทึกที่อ่านได้")

    def test_partial_result_is_not_full_success(self):
        result = self.read({"ok": True, "endpoint_failures": [{"endpoint": "sleep"}]})
        self.assertEqual(result["result"], "สำเร็จบางส่วน")
        self.assertIn("รอบถัดไป", result["action"])

    def test_token_failure_has_action_without_raw_credentials(self):
        result = self.read({"ok": False, "reason": "token", "error": "secret-value"})
        self.assertIn("ขอ token ใหม่", result["action"])
        self.assertNotIn("secret-value", str(result))

    def test_unknown_reason_and_error_do_not_render_raw_text(self):
        result = self.read({"ok": False, "reason": "secret-value", "error": "secret-value"})
        self.assertNotIn("secret-value", str(result))

    def test_utc_and_naive_finished_times_are_not_confused(self):
        self.assertEqual(self.read({"ok": True, "finished_at": "2026-10-04T01:00:00Z"})["finished"],
                         "04/10/2026 08:00")
        self.assertEqual(self.read({"ok": True, "finished_at": "2026-10-04T08:00:00"})["finished"],
                         "04/10/2026 08:00")


class DemoTests(unittest.TestCase):
    def test_demo_child_does_not_open_a_new_windows_console_and_preserves_flags(self):
        with patch.object(run_demo.win_process.os, "name", "nt"), \
                patch.object(run_demo.win_process.subprocess, "Popen") as spawn:
            run_demo.win_process.popen(["python", "-m", "streamlit"], creationflags=0x200)
            self.assertEqual(spawn.call_args.kwargs["creationflags"], 0x200 | 0x08000000)

    def test_existing_database_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "garmin.db"
            target.write_bytes(b"production-canary")
            with self.assertRaises(FileExistsError):
                run_demo.create_demo_database(directory)
            self.assertEqual(target.read_bytes(), b"production-canary")

    def test_launcher_overrides_child_only_and_cleans_temporary_data(self):
        with tempfile.TemporaryDirectory() as production:
            canary = Path(production) / "garmin.db"
            canary.write_bytes(b"production-canary")
            process = MagicMock()
            process.wait.return_value = 0
            process.poll.return_value = 0
            with patch.dict(os.environ, {"GARMIN_DATA_DIR": production}), \
                    patch.object(sys, "argv", ["run_demo.py", "--port", "8509"]), \
                    patch.object(run_demo.subprocess, "Popen", return_value=process) as spawn:
                self.assertEqual(run_demo.main(), 0)
                child_env = spawn.call_args.kwargs["env"]
                self.assertNotEqual(child_env["GARMIN_DATA_DIR"], production)
                self.assertEqual(child_env["GARMIN_DASHBOARD_DEMO"], "1")
                self.assertEqual(os.environ["GARMIN_DATA_DIR"], production)
                self.assertFalse(Path(child_env["GARMIN_DATA_DIR"]).exists())
            self.assertEqual(canary.read_bytes(), b"production-canary")

    def test_demo_system_page_skips_machine_checks_and_labels_synthetic_data(self):
        with patch.dict(os.environ, {"GARMIN_DASHBOARD_DEMO": "1"}), \
                patch("health_report.run_all_checks", side_effect=AssertionError("Demo must not inspect machine")) as checks:
            main, _ = render_page(SYSTEM_PAGE, lambda conn: run_demo.seed_demo_data(conn, LAST_DAY))
            checks.assert_not_called()
        text = page_text(main)
        self.assertIn("โหมด Demo", text)
        self.assertIn("ข้อมูลจำลอง", text)
        self.assertIn("ไม่ได้ซิงก์จริง (Demo)", text)
        self.assertIn("วันไม่มีข้อมูลสุขภาพ", text)


if __name__ == "__main__":
    unittest.main()
