"""Regression tests for athlete fields that used to exist only in SQLite."""

import ast
import datetime
import sqlite3
import tempfile
import unittest
from pathlib import Path

import pandas as pd


GARMIN_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_SRC = (GARMIN_ROOT / "scripts" / "dashboard.py").read_text(encoding="utf-8")


class _FakeStreamlit:
    @staticmethod
    def cache_data(**_kwargs):
        return lambda function: function


def extract_body_composition_loader(db_path):
    tree = ast.parse(DASHBOARD_SRC)
    functions = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"connect_db", "load_body_composition"}
    ]
    namespace = {
        "DB_PATH": Path(db_path),
        "CACHE_TTL_SEC": 0,
        "pd": pd,
        "sqlite3": sqlite3,
        "st": _FakeStreamlit,
    }
    exec(
        compile(ast.Module(body=functions, type_ignores=[]), "dashboard.py", "exec"),
        namespace,
    )
    return namespace["load_body_composition"]


def extract_first_dashboard_date_loader(db_path):
    tree = ast.parse(DASHBOARD_SRC)
    functions = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"connect_db", "load_first_dashboard_date"}
    ]
    namespace = {
        "DB_PATH": Path(db_path),
        "CACHE_TTL_SEC": 0,
        "datetime": datetime,
        "sqlite3": sqlite3,
        "st": _FakeStreamlit,
    }
    exec(
        compile(ast.Module(body=functions, type_ignores=[]), "dashboard.py", "exec"),
        namespace,
    )
    return namespace["load_first_dashboard_date"]


class BodyCompositionLoaderTests(unittest.TestCase):
    def test_loads_full_history_instead_of_hiding_values_outside_sidebar_period(self):
        with tempfile.TemporaryDirectory(prefix="dashboard-body-") as temp_dir:
            db_path = Path(temp_dir) / "garmin.db"
            connection = sqlite3.connect(db_path)
            connection.execute(
                """CREATE TABLE fact_body_composition (
                       athlete_id INTEGER,
                       calendar_date TEXT,
                       weight_kg REAL,
                       bmi REAL,
                       body_fat_pct REAL
                   )"""
            )
            connection.executemany(
                "INSERT INTO fact_body_composition VALUES (?, ?, ?, ?, ?)",
                [
                    (1, "2026-01-01", 62.0, 20.1, 14.2),
                    (1, "2026-08-01", 61.5, 19.9, 13.8),
                    (2, "2026-08-01", 70.0, 22.0, 15.0),
                ],
            )
            connection.commit()
            connection.close()

            frame = extract_body_composition_loader(db_path)(1)

        self.assertEqual(len(frame), 2)
        self.assertEqual(list(frame["weight_kg"]), [62.0, 61.5])
        self.assertEqual(list(frame["body_fat_pct"]), [14.2, 13.8])
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(frame["calendar_date"]))


class FullHistoryLoaderTests(unittest.TestCase):
    def test_uses_earliest_visible_dashboard_record_and_ignores_deleted_activity(self):
        with tempfile.TemporaryDirectory(prefix="dashboard-history-") as temp_dir:
            db_path = Path(temp_dir) / "garmin.db"
            connection = sqlite3.connect(db_path)
            connection.execute(
                "CREATE TABLE fact_activity "
                "(athlete_id INTEGER, start_time_local TEXT, deleted_at TEXT)"
            )
            connection.execute(
                "CREATE TABLE fact_daily_wellness "
                "(athlete_id INTEGER, calendar_date TEXT)"
            )
            connection.execute(
                "CREATE TABLE fact_race_prediction "
                "(athlete_id INTEGER, calendar_date TEXT)"
            )
            connection.executemany(
                "INSERT INTO fact_activity VALUES (?, ?, ?)",
                [
                    (1, "2025-01-01 06:00:00", "2025-01-02 00:00:00"),
                    (1, "2026-03-01 06:00:00", None),
                    (2, "2024-01-01 06:00:00", None),
                ],
            )
            connection.execute(
                "INSERT INTO fact_daily_wellness VALUES (?, ?)",
                (1, "2026-02-01"),
            )
            connection.execute(
                "INSERT INTO fact_race_prediction VALUES (?, ?)",
                (1, "2026-04-01"),
            )
            connection.commit()
            connection.close()

            first_date = extract_first_dashboard_date_loader(db_path)(1)

        self.assertEqual(first_date, datetime.date(2026, 2, 1))


class DashboardCompletenessSourceTests(unittest.TestCase):
    def test_sidebar_offers_complete_history(self):
        self.assertIn(
            'options=["7 วัน", "30 วัน", "90 วัน", "ทั้งหมด", "กำหนดเอง"]',
            DASHBOARD_SRC,
        )
        self.assertIn('elif history_period == "ทั้งหมด":', DASHBOARD_SRC)
        self.assertIn("start_date = load_first_dashboard_date(athlete_id) or today", DASHBOARD_SRC)

    def test_session_details_render_previously_hidden_activity_fields(self):
        for field in (
            "moving_duration_sec",
            "steps",
            "moderate_intensity_min",
            "vigorous_intensity_min",
            "avg_speed_mps",
            "max_speed_mps",
            "avg_grade_adjusted_speed_mps",
            "vo2max_value",
            "normalized_power",
            "max_power",
            "max_cadence",
            "elevation_loss_m",
            "min_elevation_m",
            "max_elevation_m",
            "bmr_calories",
            "training_effect_label",
            "location_name",
            "start_latitude",
            "start_longitude",
        ):
            self.assertIn(f'arow.get("{field}")', DASHBOARD_SRC, field)

    def test_split_table_renders_all_stored_per_lap_performance_fields(self):
        for snippet in (
            '_add("max_power", "Power สูงสุด (W)")',
            '_add("normalized_power", "Normalized Power (W)")',
            '_add("vertical_ratio", "Vertical Ratio (%)"',
            '_add("max_cadence", "Cadence สูงสุด")',
            'splits["avg_speed_mps"] * 3.6',
            '_add("elevation_loss_m", "ลง (m)")',
        ):
            self.assertIn(snippet, DASHBOARD_SRC)

    def test_progress_tab_loads_and_renders_body_composition(self):
        self.assertIn("body_composition = load_body_composition(athlete_id)", DASHBOARD_SRC)
        self.assertIn('("weight_kg", "น้ำหนัก", " kg", "{:.1f}")', DASHBOARD_SRC)
        self.assertIn('("bmi", "BMI", "", "{:.1f}")', DASHBOARD_SRC)
        self.assertIn(
            '("body_fat_pct", "ไขมันในร่างกาย", "%", "{:.1f}")',
            DASHBOARD_SRC,
        )

    def test_daily_health_history_includes_core_and_detailed_fields(self):
        for snippet in (
            '"resting_hr": "Resting HR"',
            '"hrv_last_night": "HRV คืนล่าสุด"',
            '"sleep_score": "Sleep score"',
            '"body_battery_high": "BB สูงสุด"',
            '"stress_avg": "Stress เฉลี่ย"',
            '"training_readiness": "Readiness"',
            '"vo2max_trend": "VO2max"',
            '"lactate_threshold_pace_min_km": "LT Pace"',
        ):
            self.assertIn(snippet, DASHBOARD_SRC)

    def test_red_athlete_status_is_not_presented_as_a_system_failure(self):
        self.assertIn("สถานะนักกีฬา:", DASHBOARD_SRC)
        self.assertIn("ไม่ใช่ข้อผิดพลาดของระบบ", DASHBOARD_SRC)
        status_branch = DASHBOARD_SRC.split('if status_text.startswith("🔴"):', 1)[1]
        status_branch = status_branch.split('elif status_text.startswith("🟡"):', 1)[0]
        self.assertIn("st.warning(", status_branch)
        self.assertNotIn("st.error(", status_branch)


if __name__ == "__main__":
    unittest.main()
