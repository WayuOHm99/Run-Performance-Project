"""Pure-helper regression tests for Today/Team/Recovery dashboard behavior."""

import ast
import datetime
import math
import os
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd
from streamlit.testing.v1 import AppTest


GARMIN_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PATH = GARMIN_ROOT / "scripts" / "dashboard.py"
DASHBOARD_SRC = DASHBOARD_PATH.read_text(encoding="utf-8")


# การคำนวณกับชิ้นส่วนหน้าตาอยู่ใน dashboard_domain.py / dashboard_view.py แล้ว
# จึง import ได้ตรง ๆ ไม่ต้อง ast.parse + exec ทีละ node เหมือนเดิม
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent))

from dashboard_modules import HELPERS  # noqa: E402


class DataAvailabilitySummaryTests(unittest.TestCase):
    def test_distinguishes_available_partial_outside_range_and_never_received(self):
        summarize = HELPERS["summarize_metric_group"]
        fields = ("score", "recovery", "load")

        available = summarize(
            fields,
            history_counts={"score": 10, "recovery": 10, "load": 10},
            selected_counts={"score": 3, "recovery": 3, "load": 3},
            latest_dates={"score": "2026-08-17", "recovery": "2026-08-17"},
        )
        partial = summarize(
            fields,
            history_counts={"score": 10, "recovery": 0, "load": 0},
            selected_counts={"score": 3, "recovery": 0, "load": 0},
            latest_dates={"score": "2026-08-16"},
        )
        outside = summarize(
            fields,
            history_counts={"score": 10, "recovery": 10, "load": 10},
            selected_counts={"score": 0, "recovery": 0, "load": 0},
            latest_dates={"score": "2026-06-01"},
        )
        missing = summarize(
            fields,
            history_counts={field: 0 for field in fields},
            selected_counts={field: 0 for field in fields},
            latest_dates={},
        )

        self.assertEqual(available["state"], "available")
        self.assertEqual(partial["state"], "partial")
        self.assertEqual(partial["history_available"], 1)
        self.assertEqual(outside["state"], "outside_range")
        self.assertEqual(missing["state"], "never_received")
        self.assertEqual(missing["latest_date"], None)

    def test_latest_date_is_taken_only_from_fields_that_have_real_values(self):
        result = HELPERS["summarize_metric_group"](
            ("score", "recovery"),
            history_counts={"score": 2, "recovery": 0},
            selected_counts={"score": 1, "recovery": 0},
            latest_dates={"score": "2026-08-15", "recovery": "2099-01-01"},
        )

        self.assertEqual(result["latest_date"], date(2026, 8, 15))


class DataAvailabilitySourceIntegrationTests(unittest.TestCase):
    def test_dashboard_puts_availability_in_a_sidebar_popover(self):
        self.assertIn("def load_data_availability(athlete_id, start_date, end_date):", DASHBOARD_SRC)
        self.assertIn("ความพร้อมของข้อมูลจาก Garmin", DASHBOARD_SRC)
        self.assertIn('with st.sidebar:\n    with st.popover(', DASHBOARD_SRC)
        self.assertNotIn(
            'with st.expander(\n    "ความพร้อมของข้อมูลจาก Garmin"',
            DASHBOARD_SRC,
        )
        self.assertIn("Garmin Connect ยังไม่เคยส่ง", DASHBOARD_SRC)
        self.assertIn("มีประวัติ แต่นอกช่วงที่เลือก", DASHBOARD_SRC)
        self.assertIn("AND deleted_at IS NULL", DASHBOARD_SRC)

    def test_recovery_and_progress_do_not_hide_unsupported_sections(self):
        # เดิมข้อนี้เฝ้าด้วยประโยคดิบ "Garmin อาจแสดง Recovery Time เฉพาะบนนาฬิกา"
        # ซึ่งแดงทุกครั้งที่ขัดคำใหม่ ทั้งที่หัวข้อยังไม่ถูกซ่อน — ข้อความที่โค้ชเห็นจริง
        # ถูกเฝ้าจากกล่องที่เรนเดอร์แล้วใน `test_dashboard_recovery_tab.py`
        self.assertIn("readiness_missing_message", DASHBOARD_SRC)
        self.assertIn("advanced_performance_missing_message", DASHBOARD_SRC)


class LatestPerFieldTests(unittest.TestCase):
    def test_partial_latest_row_does_not_hide_yesterdays_sleep_and_hrv(self):
        frame = pd.DataFrame({
            "calendar_date": ["2026-08-08", "2026-08-09"],
            "fetched_at": ["2026-08-08T04:00:00Z", "2026-08-09T04:00:00Z"],
            "sleep_score": [57, None],
            "hrv_last_night": [82, None],
            "bb_most_recent": [48, 93],
        })

        sleep = HELPERS["latest_field"](frame, "sleep_score")
        hrv = HELPERS["latest_field"](frame, "hrv_last_night")
        body_battery = HELPERS["latest_field"](frame, "bb_most_recent")

        self.assertEqual((sleep["value"], sleep["date"]), (57, date(2026, 8, 8)))
        self.assertEqual((hrv["value"], hrv["date"]), (82, date(2026, 8, 8)))
        self.assertEqual(
            (body_battery["value"], body_battery["date"]),
            (93, date(2026, 8, 9)),
        )

    def test_readiness_uses_source_timestamp_within_the_same_calendar_date(self):
        frame = pd.DataFrame({
            "calendar_date": ["2026-08-09", "2026-08-09"],
            "training_readiness": [32, 78],
            "readiness_timestamp_local": [
                "2026-08-09T08:00:00+07:00",
                "2026-08-09T11:30:00+07:00",
            ],
            "fetched_at": ["2026-08-09T01:05:00Z", "2026-08-09T04:35:00Z"],
        })

        latest = HELPERS["latest_field"](
            frame,
            "training_readiness",
            timestamp_columns=(
                "readiness_timestamp_local", "readiness_timestamp_utc"
            ),
        )

        self.assertEqual(latest["value"], 78)
        self.assertEqual(latest["source_column"], "readiness_timestamp_local")
        self.assertIn(
            "11:30",
            HELPERS["readiness_when"](latest, date(2026, 8, 9)),
        )

    def test_body_battery_keeps_intraday_display_separate_from_completed_alert_value(self):
        frame = pd.DataFrame({
            "calendar_date": ["2026-08-08", "2026-08-09"],
            "body_battery_high": [30, 55],
            "bb_most_recent": [8, 50],
        })

        display, completed = HELPERS["body_battery_snapshots"](
            frame, date(2026, 8, 9)
        )

        self.assertEqual((display["value"], display["date"]), (50, date(2026, 8, 9)))
        self.assertEqual((completed["value"], completed["date"]), (30, date(2026, 8, 8)))

    def test_body_battery_fallback_uses_completed_daily_high_not_prior_intraday_low(self):
        frame = pd.DataFrame({
            "calendar_date": ["2026-08-08"],
            "body_battery_high": [75],
            "bb_most_recent": [12],
        })

        display, completed = HELPERS["body_battery_snapshots"](
            frame, date(2026, 8, 9)
        )

        self.assertEqual(display["value"], 75)
        self.assertEqual(completed["value"], 75)


class PeriodAverageTests(unittest.TestCase):
    def test_mean_excludes_unfinished_today_and_discloses_true_sample_count(self):
        frame = pd.DataFrame({
            "calendar_date": pd.to_datetime([
                "2026-08-07", "2026-08-08", "2026-08-09"
            ]),
            "body_battery_high": [60, None, 100],
        })

        metric = HELPERS["period_metric"](
            frame,
            "body_battery_high",
            date(2026, 8, 9),
            period_start=date(2026, 8, 7),
            period_end=date(2026, 8, 9),
        )

        self.assertEqual(metric["mean"], 60)
        self.assertEqual(metric["count"], 1)
        self.assertEqual(metric["total_days"], 2)
        self.assertTrue(metric["excluded_today"])

    def test_empty_field_still_reports_the_period_denominator(self):
        metric = HELPERS["period_metric"](
            pd.DataFrame({"calendar_date": [], "sleep_score": []}),
            "sleep_score",
            date(2026, 8, 9),
            period_start=date(2026, 7, 11),
            period_end=date(2026, 8, 9),
        )

        self.assertTrue(pd.isna(metric["mean"]))
        self.assertEqual(metric["count"], 0)
        self.assertEqual(metric["total_days"], 29)

    def test_finalized_overnight_metric_includes_today_and_uses_full_denominator(self):
        frame = pd.DataFrame({
            "calendar_date": pd.to_datetime([
                "2026-08-07", "2026-08-08", "2026-08-09"
            ]),
            "sleep_score": [60, None, 90],
        })

        metric = HELPERS["period_metric"](
            frame,
            "sleep_score",
            date(2026, 8, 9),
            exclude_partial_today=False,
            period_start=date(2026, 8, 7),
            period_end=date(2026, 8, 9),
        )

        self.assertEqual(metric["mean"], 75)
        self.assertEqual(metric["count"], 2)
        self.assertEqual(metric["total_days"], 3)
        self.assertFalse(metric["excluded_today"])


class TrainingMathTests(unittest.TestCase):
    def test_period_pace_is_total_duration_over_total_valid_distance(self):
        activities = pd.DataFrame({
            "distance_m": [1_000, 9_000, 0, 5_000, None],
            "duration_sec": [240, 3_240, 600, None, 1_800],
            # Deliberately misleading session means: this column must not be averaged.
            "avg_pace_min_per_km": [4, 6, 10, 10, 10],
        })

        pace = HELPERS["aggregate_pace_min_per_km"](activities)

        self.assertAlmostEqual(pace, 5.8)

    def test_load_windows_count_known_rest_days_before_the_first_recent_workload(self):
        end = date(2026, 8, 9)
        daily = pd.DataFrame({"date": [pd.Timestamp(end)], "value": [10.0]})

        result = HELPERS["compute_load_windows"](
            daily, end, history_start=end - datetime.timedelta(days=27)
        )

        self.assertEqual(len(result), 28)
        self.assertAlmostEqual(result.iloc[-1]["acute"], 10.0)
        self.assertAlmostEqual(result.iloc[-1]["chronic"], 2.5)

    def test_zero_only_hr_zone_rows_are_not_treated_as_measurements(self):
        columns = [f"hr_zone{i}_sec" for i in range(1, 6)]
        activities = pd.DataFrame([
            {"activity_id": 1, **dict.fromkeys(columns, 0)},
            {"activity_id": 2, **dict.fromkeys(columns, None)},
            {"activity_id": 3, **dict.fromkeys(columns, 0), "hr_zone2_sec": 900},
        ])

        usable = HELPERS["usable_hr_zone_rows"](activities, columns)

        self.assertEqual(usable["activity_id"].tolist(), [3])

    def test_hr_zone_coverage_uses_all_garmin_duration_as_the_denominator(self):
        columns = [f"hr_zone{i}_sec" for i in range(1, 6)]
        activities = pd.DataFrame([
            {"duration_sec": 600, **dict.fromkeys(columns, 0), "hr_zone2_sec": 480},
            {"duration_sec": 300, **dict.fromkeys(columns, None)},
        ])

        coverage = HELPERS["hr_zone_coverage"](activities, columns)

        self.assertEqual(coverage["duration_sec"], 900)
        self.assertEqual(coverage["classified_sec"], 480)
        self.assertEqual(coverage["unclassified_sec"], 420)
        self.assertAlmostEqual(coverage["coverage_pct"], 480 / 900 * 100)


class CalendarTests(unittest.TestCase):
    def test_calendar_alignment_inserts_an_explicit_nan_for_a_missing_day(self):
        frame = pd.DataFrame({
            "calendar_date": ["2026-08-07", "2026-08-09"],
            "vo2max_trend": [48, 49],
        })

        aligned = HELPERS["calendar_aligned_frame"](
            frame, "calendar_date", date(2026, 8, 7), date(2026, 8, 9)
        )

        self.assertEqual(len(aligned), 3)
        self.assertEqual(aligned.loc[1, "calendar_date"].date(), date(2026, 8, 8))
        self.assertTrue(pd.isna(aligned.loc[1, "vo2max_trend"]))

class FormattingAndVisibilityTests(unittest.TestCase):
    def test_integer_metrics_do_not_show_dot_zero(self):
        self.assertEqual(HELPERS["fmt_num"](93.0), "93")
        self.assertEqual(HELPERS["fmt_num"](44.6, " bpm"), "44.6 bpm")

    def test_rounded_zero_delta_never_displays_a_negative_zero(self):
        fmt = HELPERS["fmt_signed_delta"]

        self.assertEqual(fmt(-0.4, " bpm"), "0 bpm")
        self.assertEqual(fmt(1.2, " bpm"), "+1 bpm")
        self.assertEqual(fmt(-1.2, " bpm"), "-1 bpm")

    def test_recovery_minutes_are_formatted_as_hours_and_minutes(self):
        self.assertEqual(HELPERS["fmt_recovery_time"](5_425), "90 ชม. 25 นาที")
        self.assertEqual(HELPERS["fmt_recovery_time"](4_320), "72 ชม.")
        self.assertEqual(HELPERS["fmt_recovery_time"](1), "1 นาที")
        self.assertEqual(HELPERS["fmt_recovery_time"](0), "0 นาที")

    def test_recovery_reads_only_the_minute_column(self):
        """คอลัมน์ legacy `recovery_time_hrs` ถูกลบทิ้งแล้ว (16 ส.ค. 69) — ถ้ามันโผล่มา
        จาก DB เก่าที่ restore มา ต้องไม่ถูกอ่านปนเข้ามาเงียบ ๆ อีก"""
        self.assertEqual(
            HELPERS["get_recovery_minutes"](pd.Series({"recovery_time_min": 30})), 30
        )
        self.assertTrue(pd.isna(
            HELPERS["get_recovery_minutes"](
                pd.Series({"recovery_time_min": None, "recovery_time_hrs": 90})
            )
        ))

    def test_recovery_trend_preserves_middle_null_and_falls_back_per_row(self):
        frame = pd.DataFrame({
            "calendar_date": ["2026-08-07", "2026-08-08", "2026-08-09"],
            "recovery_time_min": [60, None, 90],
            "recovery_time_hrs": [999, 999, 999],
        })

        values = HELPERS["recovery_minutes_series"](frame)

        self.assertEqual(values.iloc[0], 60)
        self.assertTrue(pd.isna(values.iloc[1]))  # calendar gap must survive
        self.assertEqual(values.iloc[2], 90)
        # คอลัมน์ legacy ต้องไม่ถูกดึงมาอุดช่องว่างอีก
        self.assertEqual(len(values), 3)

    def test_dashboard_business_date_and_db_timestamp_are_bangkok_pinned(self):
        utc_evening = datetime.datetime(
            2026, 8, 8, 18, 30, tzinfo=datetime.timezone.utc
        )

        self.assertEqual(
            HELPERS["bangkok_date"](utc_evening),
            date(2026, 8, 9),
        )
        local = HELPERS["to_bangkok_timestamp"]("2026-08-08T18:30:00Z")
        self.assertEqual((local.date(), local.hour, str(local.tzinfo)), (
            date(2026, 8, 9), 1, "Asia/Bangkok"
        ))

    def test_device_inventory_filters_stale_and_discloses_last_seen(self):
        records = [
            {"product_display_name": "Fresh Watch", "display_name": None,
             "last_seen_at_utc": "2026-08-01T00:00:00Z"},
            {"product_display_name": "Old Watch", "display_name": None,
             "last_seen_at_utc": "2026-01-01T00:00:00Z"},
            {"product_display_name": None, "display_name": "Legacy Watch",
             "last_seen_at_utc": None},
        ]

        labels = HELPERS["device_inventory_labels"](
            records, now_utc="2026-08-09T00:00:00Z", stale_days=90
        )

        self.assertTrue(any("Fresh Watch" in label and "พบล่าสุด" in label for label in labels))
        self.assertFalse(any("Old Watch" in label for label in labels))
        self.assertTrue(any("Legacy Watch" in label and "เคยพบ" in label for label in labels))

    def test_visibility_accepts_either_respiration_field(self):
        waking_only = pd.DataFrame({
            "avg_sleep_respiration": [None, None],
            "avg_waking_respiration": [14, 15],
        })
        empty = pd.DataFrame({
            "avg_sleep_respiration": [None],
            "avg_waking_respiration": [None],
        })

        self.assertTrue(HELPERS["has_any_value"](
            waking_only, ["avg_sleep_respiration", "avg_waking_respiration"]
        ))
        self.assertFalse(HELPERS["has_any_value"](
            empty, ["avg_sleep_respiration", "avg_waking_respiration"]
        ))

    def test_null_only_plotly_series_are_omitted_and_legends_are_human_readable(self):
        frame = pd.DataFrame({
            "sleep_score": [42, None, 93],
            "body_battery_high": [54, 48, 96],
            "training_readiness": [None, None, None],
        })

        series = HELPERS["available_series"](frame, {
            "sleep_score": "คะแนนการนอน",
            "body_battery_high": "Body Battery สูงสุด",
            "training_readiness": "ความพร้อมซ้อม",
        })

        self.assertEqual(series, [
            ("sleep_score", "คะแนนการนอน"),
            ("body_battery_high", "Body Battery สูงสุด"),
        ])

    def test_team_cannot_be_green_when_training_or_core_wellness_is_missing(self):
        status = HELPERS["team_status"](
            [], has_workload=True, wellness_core_count=0
        )
        self.assertEqual(status, "⚪ ข้อมูลไม่พอ")

        status = HELPERS["team_status"](
            [], has_workload=True, wellness_core_count=2
        )
        self.assertEqual(status, "⚪ ข้อมูลไม่พอ")

        status = HELPERS["team_status"](
            [], has_workload=False, wellness_core_count=4
        )
        self.assertEqual(status, "⚪ ข้อมูลไม่พอ")

        status = HELPERS["team_status"](
            [], has_workload=True, wellness_core_count=4
        )
        self.assertEqual(status, "🟢 ไม่พบสัญญาณเตือนจากอุปกรณ์")

    def test_anomaly_copy_flags_values_for_review_without_mutating_frame(self):
        frame = pd.DataFrame({
            "calendar_date": ["2026-05-15", "2026-04-21", "2026-08-01"],
            "resting_hr": [136, 50, 48],
            "body_battery_high": [80, 0, 75],
            "body_battery_low": [20, 0, 25],
            "sleep_duration_sec": [8 * 3600, 7 * 3600, 36 * 60],
        })
        before = frame.copy(deep=True)

        flags = HELPERS["wellness_quality_flags"](frame)

        pd.testing.assert_frame_equal(frame, before)
        self.assertTrue(any("RHR" in flag and "136" in flag for flag in flags))
        self.assertTrue(any("Body Battery" in flag for flag in flags))
        self.assertTrue(any("3 ชม." in flag for flag in flags))


class DashboardDatabaseIsolationTests(unittest.TestCase):
    @staticmethod
    def _connect_function(db_path):
        tree = ast.parse(DASHBOARD_SRC)
        node = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "connect_db"
        )
        namespace = {"DB_PATH": Path(db_path), "sqlite3": sqlite3}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "dashboard.py", "exec"), namespace)
        return namespace["connect_db"]

    def test_read_only_connection_does_not_create_a_missing_database(self):
        with tempfile.TemporaryDirectory(prefix="dashboard db # ") as tmp:
            missing = Path(tmp) / "missing # database.db"

            with self.assertRaises(sqlite3.OperationalError):
                self._connect_function(missing)()

            self.assertFalse(missing.exists())

    def test_connection_handles_quoted_windows_paths_and_rejects_writes(self):
        with tempfile.TemporaryDirectory(prefix="dashboard db # ") as tmp:
            db_path = Path(tmp) / "garmin # test.db"
            writer = sqlite3.connect(db_path)
            writer.execute("CREATE TABLE marker (value INTEGER)")
            writer.execute("INSERT INTO marker VALUES (7)")
            writer.commit()
            writer.close()

            conn = self._connect_function(db_path)()
            try:
                self.assertEqual(conn.execute("SELECT value FROM marker").fetchone()[0], 7)
                self.assertEqual(conn.execute("PRAGMA query_only").fetchone()[0], 1)
                with self.assertRaises(sqlite3.OperationalError):
                    conn.execute("INSERT INTO marker VALUES (8)")
            finally:
                conn.close()

    def test_app_respects_garmin_data_dir_and_does_not_create_missing_db(self):
        with tempfile.TemporaryDirectory(prefix="dashboard-app-") as tmp:
            expected_db = Path(tmp) / "garmin.db"
            with patch.dict(os.environ, {"GARMIN_DATA_DIR": tmp}, clear=False):
                app = AppTest.from_file(str(DASHBOARD_PATH)).run(timeout=15)

            self.assertFalse(expected_db.exists())
            self.assertFalse(list(app.exception))
            self.assertTrue(any(str(expected_db) in item.value for item in app.error))


class DashboardSourceIntegrationTests(unittest.TestCase):
    """Prove the tested helpers are wired into the deployed Streamlit script."""

    def test_today_uses_a_recent_window_and_latest_per_field_fallbacks(self):
        self.assertIn("recent_wellness = load_wellness_data(", DASHBOARD_SRC)
        for column in ("sleep_score", "resting_hr", "hrv_last_night"):
            self.assertIn(
                f'latest_field(recent_wellness, "{column}")',
                DASHBOARD_SRC,
            )
        self.assertIn(
            "bb_snap, bb_completed_snap = body_battery_snapshots(recent_wellness, today)",
            DASHBOARD_SRC,
        )
        self.assertIn(
            "bb_display_snap, bb_completed_snap = body_battery_snapshots(w, today)",
            DASHBOARD_SRC,
        )

        # สรุปสัญญาณต้องวาดแม้ wellness วันนี้ยังไม่มา และต้องมาก่อนรายละเอียดค่าเดี่ยว
        # จึงเป็นไปไม่ได้ที่มันจะไปห้อยอยู่ใต้เงื่อนไข "วันนี้มี wellness ไหม"
        today_tab = DASHBOARD_SRC.split("with tab_today:", 1)[1]
        today_tab = today_tab.split("with tab_health:", 1)[0]
        self.assertLess(
            today_tab.index("render_today_verdict("),
            today_tab.index('latest_field(recent_wellness, "sleep_score")'),
            "แผงสรุปสัญญาณถูกวาดหลังอ่าน wellness — เสี่ยงเงียบเมื่อวันนี้ยังไม่มีค่า",
        )

    def test_recovery_averages_use_period_metric_instead_of_silent_mean(self):
        self.assertIn("average_results = {", DASHBOARD_SRC)
        # เดิม assert ติดจำนวนช่องอินเดนต์ ซึ่งขยับทุกครั้งที่บล็อกแท็บถูกครอบเพิ่ม
        # เจตนาคือ "ค่าเฉลี่ยมาจาก period_metric บน wellness_df" ไม่ใช่รูปร่างการจัดบรรทัด
        self.assertRegex(DASHBOARD_SRC, r"period_metric\(\s*\n\s*wellness_df")
        self.assertNotIn('wellness_df["sleep_score"].mean()', DASHBOARD_SRC)
        self.assertIn("วันมีข้อมูล", DASHBOARD_SRC)
        self.assertIn(
            '("Sleep score เฉลี่ย", "sleep_score", "", False)',
            DASHBOARD_SRC,
        )
        self.assertIn(
            '("Resting HR เฉลี่ย", "resting_hr", " bpm", False)',
            DASHBOARD_SRC,
        )
        self.assertIn(
            '("Body Battery สูงสุดเฉลี่ย", "body_battery_high", "", True)',
            DASHBOARD_SRC,
        )
        self.assertIn(
            '("Stress เฉลี่ย", "stress_avg", "", True)',
            DASHBOARD_SRC,
        )

    def test_charts_use_filtered_human_named_series_and_do_not_bridge_nulls(self):
        # `rhr_hrv_series` เคยอยู่ในลิสต์นี้ด้วย แต่ RHR กับ HRV ถูกแยกเป็นคนละกราฟ
        # (กฎกราฟ 01 หน่วย bpm กับ ms) ชื่อตัวแปรจึงหายไปทั้งที่เจตนายังถูก
        # พฤติกรรมจริง — ไม่วาดเส้นที่ไม่มีค่า และไม่ลากข้ามวันที่ขาด — ถูกเฝ้าจากกราฟที่
        # เรนเดอร์จริงใน `test_dashboard_recovery_tab.py` แทน
        for assignment in (
            "health_series = available_series",
            "stress_ready_series = available_series",
            "respiration_series = available_series",
        ):
            self.assertIn(assignment, DASHBOARD_SRC)
        self.assertGreaterEqual(DASHBOARD_SRC.count("connectgaps=False"), 6)
        self.assertIn("wellness_plot_df = calendar_aligned_frame(", DASHBOARD_SRC)
        self.assertIn('x=wellness_plot_df["calendar_date"]', DASHBOARD_SRC)
        self.assertIn('"sleep_score": "คะแนนการนอน"', DASHBOARD_SRC)
        self.assertIn('"body_battery_high": "Body Battery สูงสุดของวัน"', DASHBOARD_SRC)

    def test_sections_are_not_hidden_by_an_unrelated_single_field(self):
        self.assertIn(
            "if has_any_value(wellness_df, readiness_section_fields):",
            DASHBOARD_SRC,
        )
        self.assertNotIn(
            'if "acwr_percent" in wellness_df and wellness_df["acwr_percent"].notna().any():',
            DASHBOARD_SRC,
        )
        self.assertNotIn(
            'if "avg_sleep_respiration" in wellness_df and wellness_df["avg_sleep_respiration"].notna().any():',
            DASHBOARD_SRC,
        )

    def test_recovery_time_render_uses_minutes_and_dynamic_athlete_anchors(self):
        self.assertIn(
            "fmt_recovery_time(get_recovery_minutes(recovery_snap[\"row\"])",
            DASHBOARD_SRC,
        )
        self.assertIn('anchor=f"recovery-{selected_anchor}"', DASHBOARD_SRC)
        self.assertNotIn('anchor="tong"', DASHBOARD_SRC)

    def test_recovery_trend_keeps_null_calendar_rows_for_real_plotly_gaps(self):
        self.assertIn(
            "recovery_minutes = recovery_minutes_series(wellness_plot_df)",
            DASHBOARD_SRC,
        )
        self.assertIn('x=wellness_plot_df["calendar_date"]', DASHBOARD_SRC)
        self.assertIn("y=recovery_minutes / 60", DASHBOARD_SRC)
        self.assertNotIn("wellness_df.loc[recovery_mask", DASHBOARD_SRC)

    def test_dashboard_date_and_sidebar_freshness_are_explicitly_bangkok(self):
        self.assertIn("today = bangkok_date()", DASHBOARD_SRC)
        self.assertNotIn("datetime.date.today()", DASHBOARD_SRC)
        self.assertIn("SELECT MAX(calendar_date), MAX(fetched_at)", DASHBOARD_SRC)
        self.assertNotIn("datetime(MAX(fetched_at), 'localtime')", DASHBOARD_SRC)
        self.assertIn("to_bangkok_timestamp(_lw_fetched)", DASHBOARD_SRC)
        self.assertIn("เวลาไทย", DASHBOARD_SRC)

    def test_device_inventory_discloses_freshness_and_filters_stale_entries(self):
        self.assertIn('selected_columns.append("last_seen_at_utc")', DASHBOARD_SRC)
        self.assertIn("device_inventory_labels(records, stale_days=90)", DASHBOARD_SRC)
        self.assertIn("กรองรายการที่ยืนยันว่า last_seen เกิน 90 วัน", DASHBOARD_SRC)

    def test_training_math_and_hr_zone_fallbacks_use_valid_measurements(self):
        self.assertIn("avg_pace_raw = aggregate_pace_min_per_km(runs_df)", DASHBOARD_SRC)
        self.assertIn("history_start=history_start", DASHBOARD_SRC)
        self.assertIn("zdf = usable_hr_zone_rows(activity_df, zone_cols)", DASHBOARD_SRC)
        self.assertIn('load_valid = load_view.dropna(subset=["acute"])', DASHBOARD_SRC)
        self.assertNotIn(
            'load_df[(load_df["date"] >= pd.Timestamp(start_date)) & load_df["acute"].notna()]',
            DASHBOARD_SRC,
        )

    def test_fitness_age_is_not_conditioned_on_vo2_availability(self):
        self.assertIn("if not vo2.empty or not _fit_age.empty:", DASHBOARD_SRC)
        self.assertNotIn("if not vo2.empty:\n        first_v", DASHBOARD_SRC)

    def test_operational_diagnostics_are_not_rendered_on_the_athlete_dashboard(self):
        for operational_text in (
            "sync ล่าสุด (wellness)",
            "sanity check (sync",
            "รอบ sync ล่าสุดของแต่ละสายงาน",
            "ผลตรวจ sanity จากรอบเก่า",
            "_lane_paths",
        ):
            self.assertNotIn(operational_text, DASHBOARD_SRC)
        self.assertIn('st.header("สัญญาณทีมวันนี้")', DASHBOARD_SRC)

    def test_sleep_respiration_is_treated_as_a_finalized_overnight_metric(self):
        self.assertIn(
            '("หายใจตอนนอน", "avg_sleep_respiration", " brpm", False)',
            DASHBOARD_SRC,
        )

    def test_database_access_is_environment_scoped_and_read_only(self):
        self.assertIn('os.environ.get("GARMIN_DATA_DIR"', DASHBOARD_SRC)
        self.assertIn('?mode=ro', DASHBOARD_SRC)
        self.assertEqual(DASHBOARD_SRC.count("sqlite3.connect("), 1)


if __name__ == "__main__":
    unittest.main()
