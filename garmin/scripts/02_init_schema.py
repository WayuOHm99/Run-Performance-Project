#!/usr/bin/env python3
"""Initialize / migrate SQLite schema for Garmin Team Data Pipeline.

Creates star-schema tables in data/garmin.db:
  - dim_athlete        (dimension)
  - fact_activity       (fact — activity summaries, รวม running dynamics + HR zones + weather)
  - fact_activity_split (fact — per-km/mi splits)
  - fact_daily_wellness (fact — daily health metrics, รวม respiration + readiness factors)

Idempotent: safe to run multiple times. ยังทำ migration — เพิ่มคอลัมน์ใหม่ให้ DB เดิมโดยไม่ลบข้อมูล
(20 ก.ค. เก็บฟิลด์พื้นฐาน | 21 ก.ค. ขยายเก็บ "ทุกอย่างที่นาฬิกามี" ละเอียดสุด)
"""

import os
import sqlite3
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("GARMIN_DATA_DIR", PROJECT_ROOT / "data"))
DB_PATH = DATA_DIR / "garmin.db"
UTC_NOW_DEFAULT = "TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))"


def use_data_dir(path) -> Path:
    """Point every schema write at one isolated data directory."""
    global DATA_DIR, DB_PATH
    previous = DATA_DIR
    DATA_DIR = Path(path)
    DB_PATH = DATA_DIR / "garmin.db"
    return previous


# ── รายการคอลัมน์เต็ม (ชื่อ, ชนิด) — ใช้ทั้งตอน CREATE และ migration ──────────
ACTIVITY_COLUMNS = [
    ("activity_id", "INTEGER PRIMARY KEY"),
    ("athlete_id", "INTEGER NOT NULL REFERENCES dim_athlete(athlete_id)"),
    ("activity_type", "TEXT"),
    ("activity_name", "TEXT"),
    ("start_time_local", "TEXT"),
    ("start_time_utc", "TEXT"),
    ("duration_sec", "REAL"),
    ("moving_duration_sec", "REAL"),
    ("distance_m", "REAL"),
    ("avg_hr", "REAL"),
    ("max_hr", "REAL"),
    ("min_hr", "REAL"),
    ("avg_pace_min_per_km", "REAL"),
    ("avg_speed_mps", "REAL"),
    ("max_speed_mps", "REAL"),
    ("avg_grade_adjusted_speed_mps", "REAL"),
    ("calories", "REAL"),
    ("bmr_calories", "REAL"),
    ("training_effect_aerobic", "REAL"),
    ("training_effect_anaerobic", "REAL"),
    ("training_effect_label", "TEXT"),
    ("vo2max_value", "REAL"),
    ("avg_cadence", "REAL"),
    ("max_cadence", "REAL"),
    ("avg_stride_length_cm", "REAL"),
    ("avg_ground_contact_time_ms", "REAL"),
    ("avg_vertical_oscillation_cm", "REAL"),
    ("avg_vertical_ratio", "REAL"),
    ("elevation_gain_m", "REAL"),
    ("elevation_loss_m", "REAL"),
    ("min_elevation_m", "REAL"),
    ("max_elevation_m", "REAL"),
    ("avg_power", "REAL"),
    ("max_power", "REAL"),
    ("normalized_power", "REAL"),
    ("training_load", "REAL"),
    ("impact_load", "REAL"),
    ("begin_stamina", "REAL"),
    ("end_stamina", "REAL"),
    ("hr_zone1_sec", "REAL"),
    ("hr_zone2_sec", "REAL"),
    ("hr_zone3_sec", "REAL"),
    ("hr_zone4_sec", "REAL"),
    ("hr_zone5_sec", "REAL"),
    ("steps", "INTEGER"),
    ("moderate_intensity_min", "INTEGER"),
    ("vigorous_intensity_min", "INTEGER"),
    ("diff_body_battery", "INTEGER"),
    ("sweat_loss_ml", "REAL"),
    ("start_latitude", "REAL"),
    ("start_longitude", "REAL"),
    ("location_name", "TEXT"),
    ("weather_temp_c", "REAL"),
    ("weather_apparent_temp_c", "REAL"),
    ("weather_humidity", "REAL"),
    ("weather_wind_kph", "REAL"),
    # ตั้งค่าเมื่อ reconciliation พบว่ากิจกรรมนี้ถูกลบฝั่ง Garmin แล้ว (soft delete —
    # ไม่ลบแถวจริง กันเข้าใจผิด/กู้คืนได้). NULL = ยังมีอยู่จริง. ทุก query ที่คิดสถิติ
    # (ACWR/ระยะรวม) ต้องกรอง deleted_at IS NULL เสมอ
    ("deleted_at", "TEXT"),
    ("fetched_at", UTC_NOW_DEFAULT),
]

SPLIT_COLUMNS = [
    ("activity_id", "INTEGER NOT NULL REFERENCES fact_activity(activity_id)"),
    ("split_num", "INTEGER NOT NULL"),
    ("distance_m", "REAL"),
    ("duration_sec", "REAL"),
    ("avg_hr", "REAL"),
    ("max_hr", "REAL"),
    ("avg_cadence", "REAL"),
    ("max_cadence", "REAL"),
    ("avg_power", "REAL"),
    ("max_power", "REAL"),
    ("normalized_power", "REAL"),
    ("avg_speed_mps", "REAL"),
    ("avg_stride_length_cm", "REAL"),
    ("ground_contact_time_ms", "REAL"),
    ("vertical_oscillation_cm", "REAL"),
    ("vertical_ratio", "REAL"),
    ("elevation_gain_m", "REAL"),
    ("elevation_loss_m", "REAL"),
    ("intensity_type", "TEXT"),
    ("avg_pace_min_km", "REAL"),
]

WELLNESS_COLUMNS = [
    ("athlete_id", "INTEGER NOT NULL REFERENCES dim_athlete(athlete_id)"),
    ("calendar_date", "TEXT NOT NULL"),
    ("resting_hr", "REAL"),
    ("hrv_weekly_avg", "REAL"),
    ("hrv_last_night", "REAL"),
    ("hrv_status", "TEXT"),
    ("sleep_score", "REAL"),
    ("sleep_duration_sec", "REAL"),
    ("deep_sleep_sec", "REAL"),
    ("light_sleep_sec", "REAL"),
    ("rem_sleep_sec", "REAL"),
    ("awake_sec", "REAL"),
    ("body_battery_high", "INTEGER"),
    ("body_battery_low", "INTEGER"),
    ("bb_at_wake", "INTEGER"),
    ("bb_charged", "INTEGER"),
    ("bb_drained", "INTEGER"),
    ("bb_during_sleep", "INTEGER"),
    ("bb_most_recent", "INTEGER"),
    ("stress_avg", "REAL"),
    ("max_stress", "REAL"),
    ("steps", "INTEGER"),
    ("steps_goal", "INTEGER"),
    ("floors_ascended", "REAL"),
    ("active_kilocalories", "REAL"),
    ("bmr_kilocalories", "REAL"),
    ("active_seconds", "REAL"),
    ("avg_waking_respiration", "REAL"),
    ("avg_sleep_respiration", "REAL"),
    ("highest_respiration", "REAL"),
    ("lowest_respiration", "REAL"),
    ("training_readiness", "REAL"),
    ("readiness_level", "TEXT"),
    ("readiness_feedback", "TEXT"),
    ("readiness_feedback_long", "TEXT"),
    ("readiness_timestamp_utc", "TEXT"),
    ("readiness_timestamp_local", "TEXT"),
    ("readiness_input_context", "TEXT"),
    ("readiness_device_id", "TEXT"),
    ("readiness_sleep_factor_pct", "REAL"),
    ("readiness_sleep_factor_feedback", "TEXT"),
    ("acute_load", "REAL"),
    ("acwr_percent", "REAL"),
    ("acwr_factor_feedback", "TEXT"),
    ("hrv_factor_pct", "REAL"),
    ("hrv_factor_feedback", "TEXT"),
    ("recovery_time_min", "REAL"),
    ("recovery_time_factor_pct", "REAL"),
    ("recovery_time_factor_feedback", "TEXT"),
    ("recovery_time_change_phrase", "TEXT"),
    ("stress_history_pct", "REAL"),
    ("stress_history_factor_feedback", "TEXT"),
    ("training_status", "TEXT"),
    ("vo2max_trend", "REAL"),
    ("fitness_age", "REAL"),
    ("endurance_score", "REAL"),
    ("hill_score_overall", "REAL"),
    ("hill_score_strength", "REAL"),
    ("hill_score_endurance", "REAL"),
    ("lactate_threshold_hr", "REAL"),
    ("lactate_threshold_pace_min_km", "REAL"),
    # Throttle metadata for the fast lane's conditional previous-day repair.
    # It records an attempt, not proof that every metric was returned.
    ("repair_attempted_at_utc", "TEXT"),
    ("fetched_at", UTC_NOW_DEFAULT),
]

ATHLETE_DEVICE_COLUMNS = [
    ("athlete_id", "INTEGER NOT NULL REFERENCES dim_athlete(athlete_id)"),
    # Device IDs are identifiers, not quantities. TEXT avoids integer-width and
    # leading-zero surprises while keeping the raw identifier out of logs/UI.
    ("device_id", "TEXT NOT NULL"),
    ("product_display_name", "TEXT"),
    ("display_name", "TEXT"),
    ("is_primary_device", "INTEGER"),
    ("is_primary_activity_tracker", "INTEGER"),
    ("is_primary_training_device", "INTEGER"),
    ("last_seen_at_utc", UTC_NOW_DEFAULT),
]

# ── ตารางใหม่ 21 ก.ค. 69 (รอบขยาย extras): range/snapshot endpoints ──────────
RACE_PREDICTION_COLUMNS = [
    ("athlete_id", "INTEGER NOT NULL REFERENCES dim_athlete(athlete_id)"),
    ("calendar_date", "TEXT NOT NULL"),
    ("time_5k_sec", "REAL"),
    ("time_10k_sec", "REAL"),
    ("time_half_sec", "REAL"),
    ("time_full_sec", "REAL"),
    ("fetched_at", UTC_NOW_DEFAULT),
]

PERSONAL_RECORD_COLUMNS = [
    ("athlete_id", "INTEGER NOT NULL REFERENCES dim_athlete(athlete_id)"),
    ("record_type_id", "INTEGER NOT NULL"),
    ("record_label", "TEXT"),
    ("value", "REAL"),
    ("activity_id", "INTEGER"),
    ("achieved_date", "TEXT"),
    ("fetched_at", UTC_NOW_DEFAULT),
]

GEAR_COLUMNS = [
    ("athlete_id", "INTEGER NOT NULL REFERENCES dim_athlete(athlete_id)"),
    ("gear_uuid", "TEXT NOT NULL"),
    ("gear_name", "TEXT"),
    ("gear_type", "TEXT"),
    ("custom_make_model", "TEXT"),
    ("date_begin", "TEXT"),
    ("retired", "INTEGER"),
    ("total_distance_m", "REAL"),
    ("total_activities", "INTEGER"),
    ("fetched_at", UTC_NOW_DEFAULT),
]

BODY_COMPOSITION_COLUMNS = [
    ("athlete_id", "INTEGER NOT NULL REFERENCES dim_athlete(athlete_id)"),
    ("calendar_date", "TEXT NOT NULL"),
    ("weight_kg", "REAL"),
    ("bmi", "REAL"),
    ("body_fat_pct", "REAL"),
    ("fetched_at", UTC_NOW_DEFAULT),
]


def _create(cur, table, columns, extra=""):
    cols_sql = ",\n        ".join(f"{name} {typ}" for name, typ in columns)
    cur.execute(f"CREATE TABLE IF NOT EXISTS {table} (\n        {cols_sql}{extra}\n    )")


def _migrate(cur, table, columns):
    """เพิ่มคอลัมน์ที่ยังไม่มีให้ตารางเดิม (ALTER TABLE ADD COLUMN) — ไม่แตะข้อมูลเก่า"""
    existing = {row[1] for row in cur.execute(f"PRAGMA table_info({table})")}
    added = []
    for name, typ in columns:
        if name in existing:
            continue
        # ALTER ADD COLUMN ไม่รับ PRIMARY KEY / DEFAULT ที่ไม่คงที่ — ตัดออกเหลือชนิดล้วน
        simple = typ.split(" REFERENCES")[0].replace("PRIMARY KEY", "").replace("NOT NULL", "")
        simple = simple.split(" DEFAULT")[0].strip() or "TEXT"
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {simple}")
        added.append(name)
    return added


def _migrate_recovery_minutes(cur):
    """Copy legacy recovery values into the correctly named minute column.

    `recovery_time_hrs` historically received Garmin's raw `recoveryTime`
    unchanged.  The raw value is minutes, so this is a rename/copy, not a unit
    conversion.  The live database no longer has the legacy column (dropped
    2026-08-16 after every value was migrated), and the schema never creates it
    again — but a database restored from an older backup still carries it, so
    this one-way copy stays as a safety net and simply reports 0 otherwise.
    """
    columns = {row[1] for row in cur.execute("PRAGMA table_info(fact_daily_wellness)")}
    if not {"recovery_time_hrs", "recovery_time_min"}.issubset(columns):
        return 0
    cur.execute(
        """UPDATE fact_daily_wellness
              SET recovery_time_min = recovery_time_hrs
            WHERE recovery_time_min IS NULL
              AND recovery_time_hrs IS NOT NULL
              AND recovery_time_hrs BETWEEN 0 AND 5760"""
    )
    return max(cur.rowcount, 0)


def init_schema(db_path: Path | None = None):
    if db_path is None:
        db_path = DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    # WAL mode: อ่าน (dashboard) กับ เขียน (sync) ทำพร้อมกันได้ ไม่ล็อกกัน —
    # เป็นคุณสมบัติของไฟล์ ตั้งครั้งเดียวติดถาวร (แก้อาการ "database is locked"
    # ตอนเปิด dashboard ค้างแล้ว sync อัตโนมัติเขียนไม่ได้ 22 ก.ค. 69)
    wal_mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
    conn.execute("PRAGMA busy_timeout=30000")   # ถ้าล็อกจริง รอ 30 วิ แทนล้มทันที
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS dim_athlete (
        athlete_id       INTEGER PRIMARY KEY AUTOINCREMENT,
        slug             TEXT    NOT NULL UNIQUE,
        display_name     TEXT    NOT NULL,
        garmin_full_name TEXT,
        created_at       TEXT    DEFAULT (datetime('now'))
    )
    """)

    _create(cur, "dim_athlete_device", ATHLETE_DEVICE_COLUMNS,
            ",\n        PRIMARY KEY (athlete_id, device_id)")
    _create(cur, "fact_activity", ACTIVITY_COLUMNS, ",\n        UNIQUE(activity_id) ON CONFLICT REPLACE")
    _create(cur, "fact_activity_split", SPLIT_COLUMNS,
            ",\n        PRIMARY KEY (activity_id, split_num) ON CONFLICT REPLACE")
    _create(cur, "fact_daily_wellness", WELLNESS_COLUMNS,
            ",\n        PRIMARY KEY (athlete_id, calendar_date) ON CONFLICT REPLACE")
    _create(cur, "fact_race_prediction", RACE_PREDICTION_COLUMNS,
            ",\n        PRIMARY KEY (athlete_id, calendar_date) ON CONFLICT REPLACE")
    _create(cur, "fact_personal_record", PERSONAL_RECORD_COLUMNS,
            ",\n        PRIMARY KEY (athlete_id, record_type_id) ON CONFLICT REPLACE")
    _create(cur, "fact_gear", GEAR_COLUMNS,
            ",\n        PRIMARY KEY (athlete_id, gear_uuid) ON CONFLICT REPLACE")
    _create(cur, "fact_body_composition", BODY_COMPOSITION_COLUMNS,
            ",\n        PRIMARY KEY (athlete_id, calendar_date) ON CONFLICT REPLACE")

    # migration สำหรับ DB ที่มีอยู่แล้ว (เพิ่มคอลัมน์ใหม่)
    added_a = _migrate(cur, "fact_activity", ACTIVITY_COLUMNS)
    added_s = _migrate(cur, "fact_activity_split", SPLIT_COLUMNS)
    added_w = _migrate(cur, "fact_daily_wellness", WELLNESS_COLUMNS)
    added_d = _migrate(cur, "dim_athlete_device", ATHLETE_DEVICE_COLUMNS)
    migrated_recovery = _migrate_recovery_minutes(cur)
    for table, cols in (("fact_race_prediction", RACE_PREDICTION_COLUMNS),
                        ("fact_personal_record", PERSONAL_RECORD_COLUMNS),
                        ("fact_gear", GEAR_COLUMNS),
                        ("fact_body_composition", BODY_COMPOSITION_COLUMNS)):
        _migrate(cur, table, cols)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_activity_athlete_date ON fact_activity(athlete_id, start_time_local)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_wellness_athlete_date ON fact_daily_wellness(athlete_id, calendar_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_device_athlete ON dim_athlete_device(athlete_id)")

    conn.commit()
    conn.close()

    print(f"✅ Schema initialized: {db_path}")
    print(f"   journal_mode = {wal_mode} (WAL = อ่าน/เขียนพร้อมกันได้)")
    if added_a:
        print(f"   + fact_activity เพิ่ม {len(added_a)} คอลัมน์: {', '.join(added_a)}")
    if added_s:
        print(f"   + fact_activity_split เพิ่ม {len(added_s)} คอลัมน์: {', '.join(added_s)}")
    if added_w:
        print(f"   + fact_daily_wellness เพิ่ม {len(added_w)} คอลัมน์: {', '.join(added_w)}")
    if added_d:
        print(f"   + dim_athlete_device เพิ่ม {len(added_d)} คอลัมน์: {', '.join(added_d)}")
    if migrated_recovery:
        print(f"   ↪ ย้าย Recovery Time เดิมเป็นหน่วยนาที {migrated_recovery} แถว")
    if not (added_a or added_s or added_w or added_d or migrated_recovery):
        print("   (ไม่มีคอลัมน์ใหม่ต้องเพิ่ม)")
    print("Tables: dim_athlete | dim_athlete_device | fact_activity | fact_activity_split | fact_daily_wellness"
          " | fact_race_prediction | fact_personal_record | fact_gear | fact_body_composition")


if __name__ == "__main__":
    init_schema()
