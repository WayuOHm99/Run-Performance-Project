"""Pure-helper regression tests for Today/Team/Recovery dashboard behavior."""

import ast
import datetime
import unittest
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


GARMIN_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PATH = GARMIN_ROOT / "scripts" / "dashboard.py"
DASHBOARD_SRC = DASHBOARD_PATH.read_text(encoding="utf-8")


def extract_helpers(*names):
    tree = ast.parse(DASHBOARD_SRC)
    wanted = set(names)
    nodes = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in wanted
    ]
    found = {node.name for node in nodes}
    missing = wanted - found
    if missing:
        raise AssertionError(f"dashboard.py missing helper(s): {sorted(missing)}")
    namespace = {"pd": pd, "datetime": datetime, "ZoneInfo": ZoneInfo}
    exec(
        compile(ast.Module(body=nodes, type_ignores=[]), "dashboard.py", "exec"),
        namespace,
    )
    return namespace


HELPERS = extract_helpers(
    "fmt_num",
    "has_any_value",
    "available_series",
    "latest_field",
    "period_metric",
    "fmt_recovery_time",
    "get_recovery_minutes",
    "recovery_minutes_series",
    "bangkok_date",
    "to_bangkok_timestamp",
    "device_inventory_labels",
    "field_freshness",
    "readiness_when",
    "wellness_quality_flags",
    "team_status",
)


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


class FormattingAndVisibilityTests(unittest.TestCase):
    def test_integer_metrics_do_not_show_dot_zero(self):
        self.assertEqual(HELPERS["fmt_num"](93.0), "93")
        self.assertEqual(HELPERS["fmt_num"](44.6, " bpm"), "44.6 bpm")

    def test_recovery_minutes_are_formatted_as_hours_and_minutes(self):
        self.assertEqual(HELPERS["fmt_recovery_time"](5_425), "90 ชม. 25 นาที")
        self.assertEqual(HELPERS["fmt_recovery_time"](4_320), "72 ชม.")
        self.assertEqual(HELPERS["fmt_recovery_time"](1), "1 นาที")
        self.assertEqual(HELPERS["fmt_recovery_time"](0), "0 นาที")

    def test_new_recovery_column_wins_and_legacy_raw_minutes_remain_usable(self):
        self.assertEqual(
            HELPERS["get_recovery_minutes"](
                pd.Series({"recovery_time_min": 30, "recovery_time_hrs": 999})
            ),
            30,
        )
        self.assertEqual(
            HELPERS["get_recovery_minutes"](
                pd.Series({"recovery_time_min": None, "recovery_time_hrs": 90})
            ),
            90,
        )

    def test_recovery_trend_preserves_middle_null_and_falls_back_per_row(self):
        frame = pd.DataFrame({
            "calendar_date": ["2026-08-07", "2026-08-08", "2026-08-09"],
            "recovery_time_min": [60, None, None],
            "recovery_time_hrs": [999, None, 90],
        })

        values = HELPERS["recovery_minutes_series"](frame)

        self.assertEqual(values.iloc[0], 60)  # new schema wins
        self.assertTrue(pd.isna(values.iloc[1]))  # calendar gap must survive
        self.assertEqual(values.iloc[2], 90)  # legacy raw-minute fallback

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

    def test_team_cannot_be_green_when_acwr_or_core_wellness_is_missing(self):
        status = HELPERS["team_status"](
            float("nan"), [], has_workload=True, wellness_core_count=0
        )
        self.assertEqual(status, "⚪ ข้อมูลไม่พอ")

        status = HELPERS["team_status"](
            1.0, [], has_workload=True, wellness_core_count=2
        )
        self.assertEqual(status, "⚪ ข้อมูลไม่พอ")

        status = HELPERS["team_status"](
            1.0, [], has_workload=True, wellness_core_count=4
        )
        self.assertEqual(status, "🟢 พร้อมซ้อม")

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
            "สถานะโหลดต้องเตือนแม้ wellness วันนี้ยังไม่มา",
            DASHBOARD_SRC,
        )

    def test_recovery_averages_use_period_metric_instead_of_silent_mean(self):
        self.assertIn("average_results = {", DASHBOARD_SRC)
        self.assertIn("period_metric(\n                wellness_df", DASHBOARD_SRC)
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
        for assignment in (
            "health_series = available_series",
            "stress_ready_series = available_series",
            "rhr_hrv_series = available_series",
            "respiration_series = available_series",
        ):
            self.assertIn(assignment, DASHBOARD_SRC)
        self.assertGreaterEqual(DASHBOARD_SRC.count("connectgaps=False"), 6)
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
            "recovery_minutes = recovery_minutes_series(wellness_df)",
            DASHBOARD_SRC,
        )
        self.assertIn('x=wellness_df["calendar_date"]', DASHBOARD_SRC)
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


if __name__ == "__main__":
    unittest.main()
