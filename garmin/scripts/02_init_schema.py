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

import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "garmin.db"

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
    ("fetched_at", "TEXT DEFAULT (datetime('now'))"),
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
    ("acute_load", "REAL"),
    ("acwr_percent", "REAL"),
    ("hrv_factor_pct", "REAL"),
    ("recovery_time_hrs", "REAL"),
    ("stress_history_pct", "REAL"),
    ("training_status", "TEXT"),
    ("fetched_at", "TEXT DEFAULT (datetime('now'))"),
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


def init_schema(db_path: Path = DB_PATH):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
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

    _create(cur, "fact_activity", ACTIVITY_COLUMNS, ",\n        UNIQUE(activity_id) ON CONFLICT REPLACE")
    _create(cur, "fact_activity_split", SPLIT_COLUMNS,
            ",\n        PRIMARY KEY (activity_id, split_num) ON CONFLICT REPLACE")
    _create(cur, "fact_daily_wellness", WELLNESS_COLUMNS,
            ",\n        PRIMARY KEY (athlete_id, calendar_date) ON CONFLICT REPLACE")

    # migration สำหรับ DB ที่มีอยู่แล้ว (เพิ่มคอลัมน์ใหม่)
    added_a = _migrate(cur, "fact_activity", ACTIVITY_COLUMNS)
    added_s = _migrate(cur, "fact_activity_split", SPLIT_COLUMNS)
    added_w = _migrate(cur, "fact_daily_wellness", WELLNESS_COLUMNS)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_activity_athlete_date ON fact_activity(athlete_id, start_time_local)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_wellness_athlete_date ON fact_daily_wellness(athlete_id, calendar_date)")

    conn.commit()
    conn.close()

    print(f"✅ Schema initialized: {db_path}")
    if added_a:
        print(f"   + fact_activity เพิ่ม {len(added_a)} คอลัมน์: {', '.join(added_a)}")
    if added_s:
        print(f"   + fact_activity_split เพิ่ม {len(added_s)} คอลัมน์: {', '.join(added_s)}")
    if added_w:
        print(f"   + fact_daily_wellness เพิ่ม {len(added_w)} คอลัมน์: {', '.join(added_w)}")
    if not (added_a or added_s or added_w):
        print("   (ไม่มีคอลัมน์ใหม่ต้องเพิ่ม)")
    print("Tables: dim_athlete | fact_activity | fact_activity_split | fact_daily_wellness")


if __name__ == "__main__":
    init_schema()
