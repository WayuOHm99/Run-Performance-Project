"""ชั้นข้อมูลของ Dashboard — อ่าน SQLite แล้วแคชด้วย ``st.cache_data``

แยกออกจากสคริปต์หน้าเว็บเพราะหน้าแต่ละหน้าใน ``st.navigation`` ต้องเรียก loader
ชุดเดียวกัน แคชของ Streamlit ผูกกับตัวฟังก์ชัน จึงต้องเป็นฟังก์ชันตัวเดียวกันทุกหน้า
ไม่ใช่สำเนาต่อหน้า
"""

import datetime
import os
import sqlite3
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard_domain import device_inventory_labels


PROJECT_ROOT = Path(__file__).resolve().parent.parent

# อ่าน env ทุกครั้งที่เรียก ไม่ใช่ตอน import — โมดูลนี้ถูก import ครั้งเดียวต่อโปรเซส
# แต่เทสสลับ GARMIN_DATA_DIR ระหว่างเคส และ AppTest หลายตัวก็อยู่โปรเซสเดียวกัน
# ถ้าจำค่าไว้ตอน import เคสที่สองจะไปอ่าน DB ของเคสแรกเงียบ ๆ
def data_dir():
    return Path(os.environ.get("GARMIN_DATA_DIR", PROJECT_ROOT / "data"))


def db_path():
    return data_dir() / "garmin.db"

# ประเภทกิจกรรมที่นับเป็น "วิ่ง" (ใช้คำนวณโหลด / pace-HR trend / intensity distribution)
RUN_TYPES = ("running", "track_running", "trail_running", "treadmill_running")

def connect_db():
    """Open the dashboard database read-only without creating a missing file."""
    uri = f"{db_path().resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5.0)
    conn.execute("PRAGMA query_only = ON")
    return conn

def load_athletes():
    conn = connect_db()
    df = pd.read_sql_query("SELECT athlete_id, display_name, slug FROM dim_athlete", conn)
    conn.close()
    return df

# คอลัมน์ที่เป็นข้อความ (ที่เหลือ coerce เป็นตัวเลขทั้งหมด กัน object dtype ตอนคอลัมน์ NULL ล้วน)
_WELLNESS_TEXT = {
    "calendar_date", "hrv_status", "training_status", "readiness_level",
    "readiness_feedback", "readiness_feedback_long", "fetched_at",
    "repair_attempted_at_utc",
    "readiness_timestamp_utc", "readiness_timestamp_local",
    "readiness_input_context", "readiness_device_id",
    "readiness_sleep_factor_feedback", "recovery_time_factor_feedback",
    "recovery_time_change_phrase", "acwr_factor_feedback",
    "hrv_factor_feedback", "stress_history_factor_feedback",
}

_ACTIVITY_TEXT = {"activity_type", "activity_name", "start_time_local", "start_time_utc",
                  "training_effect_label", "location_name", "fetched_at"}

# แต่ละกลุ่มวัดจากประวัติจริงทั้งบัญชีและช่วงวันที่ที่ผู้ใช้เลือก ไม่ผูก capability
# กับชื่อรุ่นนาฬิกา เพราะ firmware/account/API อาจให้ข้อมูลต่างกันได้.
DATA_AVAILABILITY_GROUPS = (
    {
        "key": "core_wellness", "label": "สุขภาพพื้นฐาน", "table": "fact_daily_wellness",
        "fields": ("resting_hr", "sleep_score", "body_battery_high", "stress_avg",
                   "hrv_last_night", "avg_sleep_respiration"),
    },
    {
        "key": "readiness", "label": "ความพร้อมและการฟื้นตัว", "table": "fact_daily_wellness",
        "fields": ("training_readiness", "recovery_time_min", "acute_load", "training_status"),
    },
    {
        "key": "advanced", "label": "สมรรถนะขั้นสูง", "table": "fact_daily_wellness",
        "fields": ("vo2max_trend", "fitness_age", "endurance_score", "hill_score_overall",
                   "lactate_threshold_hr"),
    },
    {
        "key": "activity_detail", "label": "รายละเอียดกิจกรรม", "table": "fact_activity",
        "fields": ("avg_hr", "avg_cadence", "avg_power", "training_load",
                   "avg_ground_contact_time_ms", "begin_stamina"),
    },
    {
        "key": "body", "label": "องค์ประกอบร่างกาย", "table": "fact_body_composition",
        "fields": ("weight_kg", "bmi", "body_fat_pct"),
    },
    {
        "key": "race", "label": "คาดการณ์เวลาแข่ง", "table": "fact_race_prediction",
        "fields": ("time_5k_sec", "time_10k_sec", "time_half_sec", "time_full_sec"),
    },
)

def load_wellness_data(athlete_id, start_date, end_date):
    conn = connect_db()
    query = """
        SELECT * FROM fact_daily_wellness
        WHERE athlete_id = ? AND calendar_date >= ? AND calendar_date <= ?
        ORDER BY calendar_date ASC
    """
    df = pd.read_sql_query(query, conn, params=(athlete_id, start_date, end_date))
    conn.close()
    for col in df.columns:
        if col not in _WELLNESS_TEXT:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

def load_activity_data(athlete_id, start_date, end_date):
    conn = connect_db()
    query = """
        SELECT * FROM fact_activity
        WHERE athlete_id = ? AND start_time_local >= ? AND start_time_local <= ?
          AND deleted_at IS NULL
        ORDER BY start_time_local ASC
    """
    df = pd.read_sql_query(query, conn, params=(athlete_id, start_date, f"{end_date} 23:59:59"))
    conn.close()
    for col in df.columns:
        if col not in _ACTIVITY_TEXT:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

def load_data_availability(athlete_id, start_date, end_date):
    """Return all-history and selected-range evidence for Dashboard metric groups."""
    conn = connect_db()
    result = {}
    try:
        for table in {group["table"] for group in DATA_AVAILABILITY_GROUPS}:
            fields = tuple(
                field
                for group in DATA_AVAILABILITY_GROUPS if group["table"] == table
                for field in group["fields"]
            )
            date_expr = (
                "SUBSTR(start_time_local, 1, 10)"
                if table == "fact_activity" else "calendar_date"
            )
            expressions = []
            for field in fields:
                expressions.extend((
                    f'COUNT({field}) AS "{field}__history"',
                    f'COUNT(CASE WHEN {date_expr} >= ? AND {date_expr} <= ? '
                    f'THEN {field} END) AS "{field}__selected"',
                    f'MAX(CASE WHEN {field} IS NOT NULL THEN {date_expr} END) '
                    f'AS "{field}__latest"',
                ))
            active_filter = " AND deleted_at IS NULL" if table == "fact_activity" else ""
            params = []
            for _ in fields:
                params.extend((start_date, end_date))
            params.append(athlete_id)
            cursor = conn.execute(
                f"SELECT {', '.join(expressions)} FROM {table} "
                f"WHERE athlete_id = ?{active_filter}",
                tuple(params),
            )
            columns = [description[0] for description in cursor.description]
            row = cursor.fetchone()
            values = dict(zip(columns, row))
            result[table] = {
                field: {
                    "history_count": values[f"{field}__history"],
                    "selected_count": values[f"{field}__selected"],
                    "latest_date": values[f"{field}__latest"],
                }
                for field in fields
            }
    finally:
        conn.close()
    return result

def load_daily_run_km(athlete_id, start_date, end_date):
    """ระยะวิ่งรวมรายวัน (เฉพาะประเภทวิ่ง) สำหรับโหลดสะสม"""
    conn = connect_db()
    placeholders = ",".join("?" for _ in RUN_TYPES)
    query = f"""
        SELECT SUBSTR(start_time_local, 1, 10) AS date, SUM(distance_m) / 1000.0 AS km, COUNT(*) AS sessions
        FROM fact_activity
        WHERE athlete_id = ? AND activity_type IN ({placeholders})
          AND start_time_local >= ? AND start_time_local <= ?
          AND deleted_at IS NULL
        GROUP BY SUBSTR(start_time_local, 1, 10)
        ORDER BY date ASC
    """
    df = pd.read_sql_query(query, conn, params=(athlete_id, *RUN_TYPES, start_date, f"{end_date} 23:59:59"))
    conn.close()
    df["date"] = pd.to_datetime(df["date"])
    df["km"] = pd.to_numeric(df["km"], errors="coerce").fillna(0.0)
    return df

def load_first_run_date(athlete_id):
    """วันแรกที่มีข้อมูลวิ่ง — ใช้ตัดสินว่าประวัติพอคำนวณ chronic 28 วันหรือยัง"""
    conn = connect_db()
    placeholders = ",".join("?" for _ in RUN_TYPES)
    row = conn.execute(
        f"SELECT MIN(SUBSTR(start_time_local, 1, 10)) FROM fact_activity "
        f"WHERE athlete_id = ? AND activity_type IN ({placeholders}) AND deleted_at IS NULL",
        (athlete_id, *RUN_TYPES)).fetchone()
    conn.close()
    return datetime.date.fromisoformat(row[0]) if row and row[0] else None

def load_easy_runs(athlete_id, start_date, end_date):
    """รันที่มี HR + ระยะ + เวลา ครบพอคำนวณ EF (คัด easy ทีหลังด้วย LTHR ของแต่ละคน)"""
    conn = connect_db()
    placeholders = ",".join("?" for _ in RUN_TYPES)
    query = f"""
        SELECT SUBSTR(start_time_local, 1, 10) AS date, distance_m, duration_sec, avg_hr
        FROM fact_activity
        WHERE athlete_id = ? AND activity_type IN ({placeholders})
          AND start_time_local >= ? AND start_time_local <= ?
          AND deleted_at IS NULL
          AND avg_hr IS NOT NULL AND distance_m IS NOT NULL AND duration_sec > 0
        ORDER BY start_time_local ASC
    """
    df = pd.read_sql_query(
        query, conn, params=(athlete_id, *RUN_TYPES, start_date, f"{end_date} 23:59:59")
    )
    conn.close()
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df

def athlete_has_load(athlete_id):
    """นาฬิกาคนนี้ให้ค่า training_load ไหม (บางรุ่นไม่ให้ → ต้อง fallback เป็นระยะวิ่ง)"""
    conn = connect_db()
    n = conn.execute(
        "SELECT COUNT(*) FROM fact_activity "
        "WHERE athlete_id = ? AND training_load IS NOT NULL AND deleted_at IS NULL",
        (athlete_id,)).fetchone()[0]
    conn.close()
    return n > 0

LOAD_CURRENCY_SAMPLE = 5   # กี่กิจกรรมล่าสุดที่ใช้ตอบว่า "นาฬิกาตอนนี้ยังส่ง TL อยู่ไหม"

def athlete_load_is_current(athlete_id):
    """นาฬิกาที่คนนี้ใช้ **อยู่ตอนนี้** ยังส่ง ``training_load`` อยู่ไหม

    ``athlete_has_load()`` ตอบจากประวัติทั้งหมด ซึ่งใช้ตอบคำถาม "เคยได้รับไหม" ได้ถูก
    แต่ใช้เลือกหน่วยของโหลดไม่ได้ — คนที่เลิกใช้นาฬิการุ่นที่ให้ TL จะยังถูกรวมเฉพาะ
    แถวที่มี TL กิจกรรมหลังเปลี่ยนจึงหายจากผลรวมทั้งที่อยู่ใน DB ผลคือ 0 TL · -100%
    อ่านได้ว่า "หยุดซ้อม" และถ้าเกิน 42 วันจะไม่เหลือโหลดในกรอบเลยจน ``has_workload``
    เป็นเท็จ แล้วสถานะการ์ดตกไปเป็น "ข้อมูลไม่พอ" ทั้งที่ซ้อมทุกวัน

    ต้องมี TL ครบทุกกิจกรรมใน sample ไม่ใช่เพียงหนึ่งรายการ มิฉะนั้นการเลือก TL จะทำให้
    กิจกรรมที่ค่าเป็น NULL หายจาก workload โดยเงียบ ๆ; กรณี coverage ไม่ครบใช้ระยะวิ่ง
    ซึ่งแคบกว่าแต่มีนิยามตรงและไม่แสร้งว่าครอบคลุมกิจกรรมทั้งหมด
    """
    conn = connect_db()
    rows = conn.execute(
        "SELECT training_load IS NOT NULL FROM fact_activity "
        "WHERE athlete_id = ? AND deleted_at IS NULL "
        "ORDER BY start_time_local DESC LIMIT ?",
        (athlete_id, LOAD_CURRENCY_SAMPLE)).fetchall()
    conn.close()
    return len(rows) == LOAD_CURRENCY_SAMPLE and all(row[0] for row in rows)

def athlete_has_training_readiness(athlete_id):
    """บัญชีนี้เคยได้รับ Training Readiness หรือไม่ (ไม่ใช้ฟันธงรุ่นนาฬิกา)."""
    conn = connect_db()
    n = conn.execute(
        "SELECT COUNT(*) FROM fact_daily_wellness "
        "WHERE athlete_id = ? AND training_readiness IS NOT NULL",
        (athlete_id,)).fetchone()[0]
    conn.close()
    return n > 0

def load_athlete_devices(athlete_id):
    """Load recently seen device labels when the optional inventory table exists."""
    conn = connect_db()
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='dim_athlete_device'"
        ).fetchone()
        if not exists:
            return []
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(dim_athlete_device)").fetchall()
        }
        name_columns = [
            column for column in ("product_display_name", "display_name") if column in columns
        ]
        if not name_columns or "athlete_id" not in columns:
            return []
        selected_columns = list(name_columns)
        if "last_seen_at_utc" in columns:
            selected_columns.append("last_seen_at_utc")
        select_columns = ", ".join(selected_columns)
        order = " ORDER BY is_primary_training_device DESC, is_primary_device DESC" \
            if {"is_primary_training_device", "is_primary_device"}.issubset(columns) else ""
        rows = conn.execute(
            f"SELECT {select_columns} FROM dim_athlete_device WHERE athlete_id = ?{order}",
            (athlete_id,),
        ).fetchall()
    finally:
        conn.close()

    records = []
    for row in rows:
        records.append(dict(zip(selected_columns, row)))
    return device_inventory_labels(records, stale_days=90)

def load_daily_load(athlete_id, start_date, end_date):
    """ผลรวม Garmin training_load รายวัน — ทุกกิจกรรม (รวม cross-training: HIIT/เวท/มวย)"""
    conn = connect_db()
    query = """
        SELECT SUBSTR(start_time_local, 1, 10) AS date, SUM(training_load) AS value, COUNT(*) AS sessions
        FROM fact_activity
        WHERE athlete_id = ? AND training_load IS NOT NULL
          AND start_time_local >= ? AND start_time_local <= ?
          AND deleted_at IS NULL
        GROUP BY SUBSTR(start_time_local, 1, 10)
        ORDER BY date ASC
    """
    df = pd.read_sql_query(query, conn, params=(athlete_id, start_date, f"{end_date} 23:59:59"))
    conn.close()
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce").fillna(0.0)
    return df

def load_first_load_date(athlete_id):
    """วันแรกที่ **นาฬิกาเริ่มส่ง** ``training_load`` — ไม่ใช่วันแรกที่มีกิจกรรม

    ``athlete_has_load()`` ตอบว่า "มี TL" ถ้าเจอแถวเดียวในประวัติทั้งหมด ถ้าใครเปลี่ยน
    นาฬิกากลางคัน วันก่อนเปลี่ยนจะไม่มี TL แล้วถูกนับเป็น 0 ในฐาน 28 วัน = ฐานต่ำเกินจริง
    หน้าจอจะขึ้นว่าซ้อมหนักขึ้นมหาศาลทั้งที่ทำเท่าเดิม **โดยไม่มี error สักตัว**
    ฐานจึงต้องเริ่มนับที่นี่ แล้วปล่อยให้เกณฑ์ "ประวัติ ≥ 28 วัน" เงียบไว้จนกว่าจะพอจริง
    """
    conn = connect_db()
    row = conn.execute(
        "SELECT MIN(SUBSTR(start_time_local, 1, 10)) FROM fact_activity "
        "WHERE athlete_id = ? AND training_load IS NOT NULL AND deleted_at IS NULL",
        (athlete_id,)).fetchone()
    conn.close()
    return datetime.date.fromisoformat(row[0]) if row and row[0] else None

def load_first_dashboard_date(athlete_id):
    """วันแรกที่มีข้อมูลซึ่งอยู่ภายใต้ตัวกรองช่วงย้อนหลังของ Dashboard.

    รวม activity, wellness และ race prediction; PR/body composition มีตรรกะโหลด
    ทั้งประวัติแยกอยู่แล้ว จึงไม่ดึงวันเก่ามากของสองตารางนั้นมาขยายกราฟสุขภาพให้ว่าง.
    """
    conn = connect_db()
    row = conn.execute(
        """SELECT MIN(calendar_date) FROM (
               SELECT SUBSTR(start_time_local, 1, 10) AS calendar_date
               FROM fact_activity
               WHERE athlete_id = ? AND deleted_at IS NULL
               UNION ALL
               SELECT calendar_date FROM fact_daily_wellness WHERE athlete_id = ?
               UNION ALL
               SELECT calendar_date FROM fact_race_prediction WHERE athlete_id = ?
           )
           WHERE calendar_date IS NOT NULL""",
        (athlete_id, athlete_id, athlete_id),
    ).fetchone()
    conn.close()
    return datetime.date.fromisoformat(row[0]) if row and row[0] else None

def load_last_data_dates(athlete_id):
    """วันล่าสุดที่มี activity / wellness — ใช้ทำแถบเตือนถ้า sync ค้าง (token หมด/Task ล้ม)

    wellness ต้องนับเฉพาะวันที่ "มีข้อมูลจริง" — ระบบ sync insert แถวของวันใหม่ไว้ก่อน
    แม้ค่าทุกช่องเป็น NULL (นักกีฬายังไม่ sync นาฬิกา) ถ้านับแถวเปล่าด้วย แถบจะโชว์
    🟢 "วันนี้" ทั้งที่ข้อมูลจริงหยุดไปแล้ว (เคสพี่เก้า 22 ก.ค. 69)"""
    conn = connect_db()
    la = conn.execute("SELECT MAX(SUBSTR(start_time_local, 1, 10)) FROM fact_activity "
                      "WHERE athlete_id = ? AND deleted_at IS NULL",
                      (athlete_id,)).fetchone()[0]
    lw = conn.execute(
        """SELECT MAX(calendar_date) FROM fact_daily_wellness
           WHERE athlete_id = ? AND (resting_hr IS NOT NULL OR sleep_score IS NOT NULL
                                     OR body_battery_high IS NOT NULL OR hrv_last_night IS NOT NULL)""",
        (athlete_id,)).fetchone()[0]
    conn.close()
    return la, lw

def load_splits(activity_id):
    conn = connect_db()
    df = pd.read_sql_query(
        "SELECT * FROM fact_activity_split WHERE activity_id = ? ORDER BY split_num ASC",
        conn, params=(activity_id,))
    conn.close()
    for col in df.columns:
        if col not in ("intensity_type",):  # text
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

def load_race_predictions(athlete_id, start_date, end_date):
    """Garmin ทำนายเวลาแข่ง 5K/10K/HM/FM รายวัน (จาก fact_race_prediction)"""
    conn = connect_db()
    df = pd.read_sql_query(
        """SELECT calendar_date, time_5k_sec, time_10k_sec, time_half_sec, time_full_sec
           FROM fact_race_prediction
           WHERE athlete_id = ? AND calendar_date >= ? AND calendar_date <= ?
           ORDER BY calendar_date ASC""",
        conn, params=(athlete_id, start_date, end_date))
    conn.close()
    for col in df.columns:
        if col != "calendar_date":
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["calendar_date"] = pd.to_datetime(df["calendar_date"])
    return df

def load_personal_records(athlete_id):
    conn = connect_db()
    df = pd.read_sql_query(
        """SELECT record_type_id, record_label, value, achieved_date
           FROM fact_personal_record WHERE athlete_id = ? ORDER BY record_type_id ASC""",
        conn, params=(athlete_id,))
    conn.close()
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df

def load_body_composition(athlete_id):
    """น้ำหนัก/BMI/ไขมันที่ Garmin เคยส่ง — โหลดทั้งประวัติเพื่อไม่ซ่อนค่าล่าสุด
    เพียงเพราะอยู่นอกช่วงวิเคราะห์ 30 วันที่เลือกใน sidebar."""
    conn = connect_db()
    df = pd.read_sql_query(
        """SELECT calendar_date, weight_kg, bmi, body_fat_pct
           FROM fact_body_composition
           WHERE athlete_id = ?
           ORDER BY calendar_date ASC""",
        conn,
        params=(athlete_id,),
    )
    conn.close()
    if not df.empty:
        df["calendar_date"] = pd.to_datetime(df["calendar_date"], errors="coerce")
        for column in ("weight_kg", "bmi", "body_fat_pct"):
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df

def load_latest_lt(athlete_id):
    """Garmin Lactate Threshold ล่าสุด (hr, pace, วันที่) — None ถ้านาฬิกาไม่ให้"""
    conn = connect_db()
    row = conn.execute(
        """SELECT calendar_date, lactate_threshold_hr, lactate_threshold_pace_min_km
           FROM fact_daily_wellness
           WHERE athlete_id = ? AND (lactate_threshold_hr IS NOT NULL
                                     OR lactate_threshold_pace_min_km IS NOT NULL)
           ORDER BY calendar_date DESC LIMIT 1""", (athlete_id,)).fetchone()
    conn.close()
    return row


# --- ย้ายมาจาก dashboard.py ตอนแยกหน้า (st.navigation) ---
def load_daily_workload(athlete_id, start_date, end_date):
    """คืน (df[date,value,sessions], metric, unit) สำหรับโหลดสะสม
    ใช้ training_load ถ้านาฬิกาให้ (จับ cross-training ครบ) ไม่งั้น fallback ระยะวิ่ง (กม.)"""
    if athlete_load_is_current(athlete_id):
        return load_daily_load(athlete_id, start_date, end_date), "training_load", "TL"
    df = load_daily_run_km(athlete_id, start_date, end_date).rename(columns={"km": "value"})
    return df, "ระยะวิ่ง", "km"
