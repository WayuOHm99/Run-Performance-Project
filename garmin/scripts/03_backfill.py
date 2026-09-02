#!/usr/bin/env python3
"""Backfill 90 days of Garmin data into SQLite.

Usage:
    python scripts/03_backfill.py [--athlete wayuo] [--days 90]

Fetches activities + daily wellness data and inserts into garmin.db.
Requires token to already exist in tokens/<athlete>/.
"""

import argparse
import json
import math
import os
import socket
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# ⚠️ path ที่เขียนได้ต้องแตกจาก DATA_DIR ที่เดียว (เหมือน fetch_all.py) — เทสจะได้ย้าย
# ทั้งชุดไป temp dir ได้ด้วยคำสั่งเดียว ไม่ใช่ไล่ patch ทีละตัวแล้วลืมตัวใดตัวหนึ่ง
# ไฟล์นี้ถือ garmin.db ซึ่งเป็นสำเนาเดียวของข้อมูลสุขภาพทั้งทีม — เขียนพลาดแปลว่าข้อมูลจริงเสีย
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "garmin.db"
# สถานะรายคนของรอบ sync ล่าสุด — fetch_all.py อ่านไปรวมเป็น data/sync_status.json
# เพื่อให้ toast/dashboard บอกได้ว่าใครพังเพราะอะไร (token/เน็ต) และข้อมูลมีจุดน่าสงสัยไหม
STATUS_DIR = DATA_DIR / "sync_status"
UTC_NOW_SQL = "strftime('%Y-%m-%dT%H:%M:%fZ','now')"
PREVIOUS_DAY_REPAIR_COOLDOWN_HOURS = 6
BANGKOK_TZ = timezone(timedelta(hours=7))
SQLITE_MAX_INTEGER = 2**63 - 1


def use_data_dir(path) -> Path:
    """ชี้ DB + ไฟล์สถานะไปโฟลเดอร์ใหม่ คืนโฟลเดอร์เดิม (จุดฉีดจุดเดียวของไฟล์นี้).

    fetch_all เรียก 03_backfill เป็น subprocess พร้อม os.environ ทั้งก้อน →
    ตั้ง GARMIN_DATA_DIR ที่ตัวแม่แล้วลูกย้ายตามเอง ไม่มีใครหลุดไปเขียนของจริง
    """
    global DATA_DIR, DB_PATH, STATUS_DIR
    previous = DATA_DIR
    DATA_DIR = Path(path)
    DB_PATH = DATA_DIR / "garmin.db"
    STATUS_DIR = DATA_DIR / "sync_status"
    return previous


if os.environ.get("GARMIN_DATA_DIR"):
    use_data_dir(os.environ["GARMIN_DATA_DIR"])

# กันการเชื่อมต่อค้างไม่รู้จบ: เคยเจอ SSL recv ค้างจน Task แขวนข้ามวัน (21 ก.ค. 69)
# requests/urllib3 ไม่ตั้ง timeout เอง → ตั้ง default ให้ทุก socket แทน
# อ่าน/เชื่อมต่อนานเกิน 30 วิ = โยน timeout ให้ safe_call จับแล้ว retry (ไม่แขวนยาว)
socket.setdefaulttimeout(30)


# คำที่ยืนยันว่า "ปัญหาอยู่ที่สิทธิ์จริง ๆ" — มีแค่กลุ่มนี้เท่านั้นที่ควรสั่งให้ไปขอ token ใหม่
_AUTH_MARKERS = (
    "401", "403", "unauthorized", "forbidden", "invalid_grant", "invalid grant",
    "invalid_token", "invalid token", "token expired", "expired token",
    "refresh token", "re-authenticate", "reauthenticate", "login required",
    "bad credentials", "invalid credentials", "mfa", "consent",
)


def classify_login_error(exc: BaseException) -> str:
    """ตัดสินว่า login ล้มเพราะ 'token' หรือ 'network' — อ่านทั้ง exception chain

    ทำไมต้องไล่ chain: garminconnect ห่อทุกอย่างที่ทำให้ดึงโปรไฟล์ไม่ได้เป็น
    GarminConnectAuthenticationError("Failed to retrieve social profile") ซึ่ง
    "อ่านแล้วเหมือน token เสีย" ทั้งที่ตัวจริงอยู่ใน __cause__ — เจอจริง 4 ส.ค. 69:
    ข้างในคือ **HTTP 521 Web server is down** (Cloudflare บอกเองว่า retryable,
    retry_after 120) แต่ระบบเราไปเด้ง toast ว่า "TOKEN ใช้ไม่ได้ → รัน เพิ่มนักกีฬา.bat"
    = ไล่ผู้จัดการทีมไปขอ token ใหม่ทั้งที่ token ปกติดีและ Garmin แค่ล่มชั่วคราว

    ตั้งใจ default เป็น "network": เดาผิดเป็น network เสียแค่รอรอบหน้าที่ลองใหม่เอง
    (และยังมี toast + แถบแดงบน dashboard เตือนอยู่ดี) แต่เดาผิดเป็น token
    = สั่งให้คนไปกรอกรหัสผ่าน Garmin ของนักกีฬาใหม่โดยไม่จำเป็น
    """
    parts = []
    seen = set()
    cur = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        parts.append(str(cur))
        resp = getattr(cur, "response", None)
        if resp is not None:
            parts.append(str(getattr(resp, "status_code", "")))
            parts.append(str(getattr(resp, "text", ""))[:500])
        cur = cur.__cause__ or cur.__context__
    blob = " ".join(parts).lower()

    # เจอสัญญาณ 5xx/429/retryable ก่อน = ฝั่งเซิร์ฟเวอร์ ไม่ใช่สิทธิ์ของเรา
    # (เช็คก่อน auth marker เพราะตัวห่อชั้นนอกมักพูดเหมือนปัญหา auth)
    transient = (
        "429", "too many requests", "rate limit", "retryable", "retry_after",
        "500", "502", "503", "504", "521", "522", "523", "524",
        "web server is down", "origin_down", "bad gateway", "service unavailable",
        "gateway timeout", "cloudflare", "internal server error",
        "timed out", "timeout", "connection", "resolve", "getaddrinfo",
        "unreachable", "temporary failure", "ssl",
    )
    if any(s in blob for s in transient):
        return "network"
    if any(s in blob for s in _AUTH_MARKERS):
        return "token"
    return "network"


def get_athlete_id(conn: sqlite3.Connection, slug: str) -> int:
    """Get or create athlete, return athlete_id."""
    cur = conn.cursor()
    cur.execute("SELECT athlete_id FROM dim_athlete WHERE slug = ?", (slug,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "INSERT INTO dim_athlete (slug, display_name) VALUES (?, ?)",
        (slug, slug.capitalize()),
    )
    conn.commit()
    return cur.lastrowid


def safe_get(data: dict, *keys, default=None):
    """Safely traverse nested dict keys."""
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key, default)
        else:
            return default
    return current


def _record_endpoint_failure(failures, api_method, exc, endpoint=None):
    """Keep a privacy-safe failure fact without persisting response bodies."""
    if failures is None:
        return
    failures.append({
        "endpoint": endpoint or getattr(api_method, "__name__", "garmin_endpoint"),
        "reason": classify_login_error(exc),
    })


def safe_call(api_method, *args, _failures=None, _endpoint=None, **kwargs):
    """Call an optional Garmin endpoint and record terminal failures when asked."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return api_method(*args, **kwargs)
        except Exception as e:
            error_str = str(e)
            # timeout/เน็ตค้าง (จาก socket.setdefaulttimeout) — ลองใหม่สั้น ๆ ก่อนยอมแพ้
            is_timeout = (
                isinstance(e, (socket.timeout, TimeoutError))
                or "timed out" in error_str.lower()
                or "read timeout" in error_str.lower()
            )
            if "429" in error_str or "Too Many" in error_str:
                if attempt == max_retries - 1:
                    _record_endpoint_failure(
                        _failures, api_method, e, endpoint=_endpoint
                    )
                    print("   ❌ Max retries exceeded.")
                    return None
                wait = 60 * (attempt + 1)
                print(f"   ⚠️  Rate limited! Waiting {wait}s before retry...")
                time.sleep(wait)
            elif "404" in error_str or "204" in error_str:
                endpoint = getattr(api_method, "__name__", "Garmin endpoint")
                print(f"   ℹ️  {endpoint}: ไม่มีข้อมูล (HTTP 404/204)")
                return None  # No data for this endpoint/date
            elif is_timeout and attempt < max_retries - 1:
                print(f"   ⚠️  เน็ตค้าง/timeout ({e}) — ลองใหม่ครั้งที่ {attempt + 2}...")
                time.sleep(5 * (attempt + 1))
            else:
                _record_endpoint_failure(
                    _failures, api_method, e, endpoint=_endpoint
                )
                print(f"   ⚠️  API error: {e}")
                return None
    return None


# ── Activity Fetching ────────────────────────────────────────


class RequiredEndpointError(RuntimeError):
    """A mandatory Garmin response was unavailable."""

    status_reason = "network"


class InvalidEndpointPayloadError(RequiredEndpointError):
    """A mandatory Garmin response arrived but is unsafe to reconcile."""

    status_reason = "payload"


CORE_WELLNESS_ENDPOINT_ORDER = (
    "get_stats", "get_hrv_data", "get_sleep_data", "get_training_readiness",
)
CORE_WELLNESS_ENDPOINTS = frozenset(CORE_WELLNESS_ENDPOINT_ORDER)


class CoreWellnessUnavailableError(RequiredEndpointError):
    """Every core wellness endpoint failed for one requested day."""

    def __init__(self, failures):
        all_failures = list(failures)
        by_endpoint = {item["endpoint"]: item for item in all_failures}
        self.failures = [
            by_endpoint[name]
            for name in CORE_WELLNESS_ENDPOINT_ORDER
            if name in by_endpoint
        ]
        self.status_reason = (
            "token"
            if all_failures
            and all(item["reason"] == "token" for item in all_failures)
            else "network"
        )
        super().__init__(
            "all core wellness endpoints failed: "
            + ", ".join(item["endpoint"] for item in self.failures)
        )

def _raise_if_all_core_wellness_failed(failures):
    failed = {item["endpoint"] for item in failures}
    if CORE_WELLNESS_ENDPOINTS.issubset(failed):
        raise CoreWellnessUnavailableError(failures)


def _core_wellness_error(failures):
    """Return the terminal core error, or None when the day is usable."""
    try:
        _raise_if_all_core_wellness_failed(failures)
    except CoreWellnessUnavailableError as exc:
        return exc
    return None


def _publish_deferred_wellness_errors(errors, collector):
    """Let orchestration finish recoverable work before publishing failure."""
    if not errors:
        return
    if collector is None:
        raise errors[0]
    collector.extend(errors)


def _unique_endpoint_failures(failures):
    """Deduplicate structured failure facts while preserving call order."""
    unique = []
    seen = set()
    for item in failures or []:
        key = (item.get("endpoint"), item.get("reason"))
        if key in seen:
            continue
        seen.add(key)
        unique.append({"endpoint": key[0], "reason": key[1]})
    return unique


def _call_wellness_endpoint(garmin, endpoint, date_str, failures):
    """Call one named wellness endpoint with stable, privacy-safe telemetry."""
    return safe_call(
        getattr(garmin, endpoint),
        date_str,
        _failures=failures,
        _endpoint=endpoint,
    )


def _normalize_activity_id(value):
    """Return one canonical positive SQLite INTEGER activity id."""
    if isinstance(value, bool):
        return None
    try:
        normalized = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    return normalized if 1 <= normalized <= SQLITE_MAX_INTEGER else None


def _validated_activities(payload):
    """Validate the authoritative activity collection before any reconciliation.

    An empty list is a valid "no activities" response.  Any other top-level
    shape, malformed item, or unusable id means the response is not safe to use
    as evidence that rows disappeared from Garmin.
    """
    if payload is None:
        raise RequiredEndpointError("activity list unavailable")
    if not isinstance(payload, list):
        raise InvalidEndpointPayloadError(
            f"activity list unavailable/invalid ({type(payload).__name__})"
        )
    validated = []
    for index, activity in enumerate(payload):
        if not isinstance(activity, dict):
            raise InvalidEndpointPayloadError(
                f"activity item {index} is {type(activity).__name__}, expected object"
            )
        activity_id = _normalize_activity_id(activity.get("activityId"))
        if activity_id is None:
            raise InvalidEndpointPayloadError(
                f"activity item {index} has invalid activityId"
            )
        validated.append((activity, activity_id))
    return validated


ACTIVITY_WRITE_COLUMNS = (
    "activity_id", "athlete_id", "activity_type", "activity_name",
    "start_time_local", "start_time_utc", "duration_sec", "moving_duration_sec",
    "distance_m", "avg_hr", "max_hr", "min_hr", "avg_pace_min_per_km",
    "avg_speed_mps", "max_speed_mps", "avg_grade_adjusted_speed_mps",
    "calories", "bmr_calories", "training_effect_aerobic",
    "training_effect_anaerobic", "training_effect_label", "vo2max_value",
    "avg_cadence", "max_cadence", "avg_stride_length_cm",
    "avg_ground_contact_time_ms", "avg_vertical_oscillation_cm",
    "avg_vertical_ratio", "elevation_gain_m", "elevation_loss_m",
    "min_elevation_m", "max_elevation_m", "avg_power", "max_power",
    "normalized_power", "training_load", "impact_load", "begin_stamina",
    "end_stamina", "hr_zone1_sec", "hr_zone2_sec", "hr_zone3_sec",
    "hr_zone4_sec", "hr_zone5_sec", "steps", "moderate_intensity_min",
    "vigorous_intensity_min", "diff_body_battery", "sweat_loss_ml",
    "start_latitude", "start_longitude", "location_name", "weather_temp_c",
    "weather_apparent_temp_c", "weather_humidity", "weather_wind_kph",
)

def _f_to_c(f):
    """แปลงองศา F → C (Garmin คืนอุณหภูมิเป็น Fahrenheit)"""
    return round((f - 32) * 5.0 / 9.0, 1) if isinstance(f, (int, float)) else None


def fetch_weather(garmin, activity_id):
    """สภาพอากาศตอนซ้อม (เฉพาะกิจกรรม outdoor) → (temp_c, apparent_c, humidity, wind)"""
    w = safe_call(garmin.get_activity_weather, activity_id)
    if not isinstance(w, dict):
        return (None, None, None, None)
    return (_f_to_c(w.get("temp")), _f_to_c(w.get("apparentTemp")),
            w.get("relativeHumidity"), w.get("windSpeed"))


def fetch_activity_detail(garmin, activity_id):
    """รายละเอียดเพิ่ม (get_activity.summaryDTO) → (min_hr, impact_load, begin_stamina, end_stamina)"""
    d = safe_call(garmin.get_activity, activity_id)
    s = safe_get(d, "summaryDTO") if isinstance(d, dict) else None
    if not isinstance(s, dict):
        return (None, None, None, None)
    return (s.get("minHR"), s.get("impactLoad"),
            s.get("beginPotentialStamina"), s.get("endPotentialStamina"))


def fetch_and_insert_activities(
    garmin, conn, athlete_id, start_date, end_date, *, fast=False,
    _validated_source=None, reconcile=True,
):
    """Fetch activities by date range and insert into fact_activity (ละเอียด: running dynamics,
    HR time-in-zone, weather, stamina/impact load สำหรับกิจกรรมวิ่ง).

    fast=True ใช้กับ polling ถี่: ดึง activity summary และเติม splits เฉพาะกิจกรรม
    ที่มีระยะทางแต่ยังไม่มี splits ใน DB; ไม่ดึง detail/weather และไม่ reconcile.
    ถ้า activity มีอยู่แล้ว จะเก็บ enrichment จาก full sync เดิมไว้ ไม่เขียน NULL ทับ."""
    print(f"\n📊 Fetching activities from {start_date} to {end_date}...")

    if _validated_source is None:
        activities = safe_call(
            garmin.get_activities_by_date,
            start_date.isoformat(),
            end_date.isoformat(),
        )
        # Only a validated list is authoritative enough for reconciliation.  In
        # particular, an empty mapping/string must never be mistaken for [] and
        # soft-delete every activity in the requested window.
        activities = _validated_activities(activities)
    else:
        # Internal seam used by reconcile_only after it validated the single
        # authoritative collection.  This avoids a second list request.
        activities = list(_validated_source)

    cur = conn.cursor()
    count = 0
    present_ids = set()   # activityId ทั้งหมดที่ Garmin คืนช่วงนี้ — ใช้ reconcile ตอนจบ

    for act, activity_id in activities:
        present_ids.add(activity_id)

        duration = act.get("duration")
        distance = act.get("distance")
        avg_pace = None
        if duration and distance and distance > 0:
            avg_pace = round((duration / 60) / (distance / 1000), 2)

        type_key = safe_get(act, "activityType", "typeKey") or ""
        is_run = "running" in type_key
        has_dist = bool(distance and distance > 0)

        # ── เรียกข้อมูลเสริมเฉพาะกิจกรรม "วิ่ง" (คุม API load — cross-training ไม่ต้อง) ──
        min_hr = impact_load = begin_stamina = end_stamina = None
        w_temp = w_apparent = w_humidity = w_wind = None
        if fast:
            existing = cur.execute(
                """SELECT min_hr, impact_load, begin_stamina, end_stamina,
                          weather_temp_c, weather_apparent_temp_c,
                          weather_humidity, weather_wind_kph
                   FROM fact_activity WHERE activity_id = ?""",
                (activity_id,),
            ).fetchone()
            if existing:
                (min_hr, impact_load, begin_stamina, end_stamina,
                 w_temp, w_apparent, w_humidity, w_wind) = existing
        elif is_run:
            time.sleep(0.3)
            min_hr, impact_load, begin_stamina, end_stamina = fetch_activity_detail(garmin, activity_id)
            if act.get("startLatitude") is not None:  # outdoor เท่านั้นถึงมี weather
                time.sleep(0.3)
                w_temp, w_apparent, w_humidity, w_wind = fetch_weather(garmin, activity_id)

        values = (
            activity_id, athlete_id, type_key, act.get("activityName"),
            act.get("startTimeLocal"), act.get("startTimeGMT"),
            duration, act.get("movingDuration"),
            distance, act.get("averageHR"), act.get("maxHR"), min_hr, avg_pace,
            act.get("averageSpeed"), act.get("maxSpeed"), act.get("avgGradeAdjustedSpeed"),
            act.get("calories"), act.get("bmrCalories"),
            act.get("aerobicTrainingEffect"), act.get("anaerobicTrainingEffect"),
            act.get("trainingEffectLabel"), act.get("vO2MaxValue"),
            act.get("averageRunningCadenceInStepsPerMinute"),
            act.get("maxRunningCadenceInStepsPerMinute"),
            act.get("avgStrideLength"), act.get("avgGroundContactTime"),
            act.get("avgVerticalOscillation"), act.get("avgVerticalRatio"),
            act.get("elevationGain"), act.get("elevationLoss"),
            act.get("minElevation"), act.get("maxElevation"),
            act.get("avgPower"), act.get("maxPower"), act.get("normPower"),
            act.get("activityTrainingLoad"), impact_load, begin_stamina, end_stamina,
            act.get("hrTimeInZone_1"), act.get("hrTimeInZone_2"), act.get("hrTimeInZone_3"),
            act.get("hrTimeInZone_4"), act.get("hrTimeInZone_5"),
            act.get("steps"), act.get("moderateIntensityMinutes"), act.get("vigorousIntensityMinutes"),
            act.get("differenceBodyBattery"), act.get("waterEstimated"),
            act.get("startLatitude"), act.get("startLongitude"), act.get("locationName"),
            w_temp, w_apparent, w_humidity, w_wind,
        )
        columns_sql = ", ".join(ACTIVITY_WRITE_COLUMNS)
        placeholders = ", ".join("?" for _ in ACTIVITY_WRITE_COLUMNS)
        # Garmin can return a partial summary while an activity is still being
        # processed, and enrichment endpoint failures are represented by None.
        # Both fast and full/deep paths therefore merge per field instead of
        # REPLACE-ing the row and destroying a previously good value.
        updates = ", ".join(
            f"{column}=COALESCE(excluded.{column}, fact_activity.{column})"
            for column in ACTIVITY_WRITE_COLUMNS
            if column not in ("activity_id", "athlete_id")
        )
        sql = (
            f"INSERT INTO fact_activity ({columns_sql}, fetched_at) "
            f"VALUES ({placeholders}, {UTC_NOW_SQL}) "
            f"ON CONFLICT(activity_id) DO UPDATE SET athlete_id=excluded.athlete_id, "
            f"{updates}, deleted_at=NULL, fetched_at=excluded.fetched_at"
        )
        cur.execute(sql, values)
        # ปล่อย SQLite write lock ก่อนยิง endpoint ถัดไป เพื่อให้ subprocess
        # ของนักกีฬาคนอื่นเขียนแทรกได้เมื่อ fetch_all รันแบบขนาน
        conn.commit()
        count += 1

        # full sync ดึง splits ตามเดิมเพื่อ reconciliation; fast sync เติมเฉพาะกิจกรรม
        # ที่ยังไม่มี split สักแถว จึงเสีย 1 call ต่อกิจกรรมใหม่ครั้งเดียว ไม่ยิงซ้ำทุก 15 นาที.
        # กิจกรรมระยะ 0 (เช่น HIIT/indoor cardio) ไม่มี split ที่มีความหมายและต้องข้าม.
        has_splits = cur.execute(
            "SELECT 1 FROM fact_activity_split WHERE activity_id = ? LIMIT 1",
            (activity_id,),
        ).fetchone()
        if has_dist and (not fast or not has_splits):
            time.sleep(0.5)
            fetch_and_insert_splits(garmin, conn, activity_id)
            conn.commit()

    conn.commit()
    print(f"   ✅ Inserted {count} activities")
    # reconcile ช่วงที่เพิ่งดึง (ฟรี — ใช้รายการที่ดึงมาแล้ว): กิจกรรมใน DB ช่วงนี้ที่ไม่อยู่
    # ในรายการจริงของ Garmin = ถูกลบฝั่งแอป → mark deleted_at (daily 3 วันจับการลบล่าสุดได้เอง)
    if not fast and reconcile:
        reconcile_activities(conn, athlete_id, start_date, end_date, present_ids)
    return count


def fetch_and_insert_splits(garmin, conn, activity_id):
    """Fetch the authoritative ordered lap/split snapshot for one activity."""
    splits_data = safe_call(garmin.get_activity_splits, activity_id)
    if splits_data is None:
        return

    # The splits structure varies.  A valid empty collection is authoritative
    # and must clear old rows; an absent/malformed response is not evidence that
    # Garmin removed every lap, so preserve the existing snapshot in that case.
    if isinstance(splits_data, list):
        laps = splits_data
    elif isinstance(splits_data, dict):
        known = [
            splits_data[key]
            for key in ("lapDTOs", "splitSummaries")
            if key in splits_data
        ]
        if not known or not all(isinstance(value, list) for value in known):
            print("   ⚠️  split payload ผิดรูปแบบ — เก็บข้อมูลเดิมไว้")
            return
        laps = next((value for value in known if value), known[0])
    else:
        print("   ⚠️  split payload ผิดรูปแบบ — เก็บข้อมูลเดิมไว้")
        return

    if not all(isinstance(lap, dict) for lap in laps):
        print("   ⚠️  split payload ผิดรูปแบบ — เก็บข้อมูลเดิมไว้")
        return

    cur = conn.cursor()
    for i, lap in enumerate(laps, 1):
        duration = lap.get("duration") or lap.get("elapsedDuration")
        distance = lap.get("distance")
        avg_pace = None
        if duration and distance and distance > 0:
            avg_pace = round((duration / 60) / (distance / 1000), 2)

        cur.execute("""
            INSERT INTO fact_activity_split (
                activity_id, split_num, distance_m, duration_sec,
                avg_hr, max_hr, avg_cadence, max_cadence,
                avg_power, max_power, normalized_power, avg_speed_mps,
                avg_stride_length_cm, ground_contact_time_ms,
                vertical_oscillation_cm, vertical_ratio,
                elevation_gain_m, elevation_loss_m, intensity_type, avg_pace_min_km
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(activity_id, split_num) DO UPDATE SET
                distance_m = COALESCE(excluded.distance_m, fact_activity_split.distance_m),
                duration_sec = COALESCE(excluded.duration_sec, fact_activity_split.duration_sec),
                avg_hr = COALESCE(excluded.avg_hr, fact_activity_split.avg_hr),
                max_hr = COALESCE(excluded.max_hr, fact_activity_split.max_hr),
                avg_cadence = COALESCE(excluded.avg_cadence, fact_activity_split.avg_cadence),
                max_cadence = COALESCE(excluded.max_cadence, fact_activity_split.max_cadence),
                avg_power = COALESCE(excluded.avg_power, fact_activity_split.avg_power),
                max_power = COALESCE(excluded.max_power, fact_activity_split.max_power),
                normalized_power = COALESCE(
                    excluded.normalized_power, fact_activity_split.normalized_power),
                avg_speed_mps = COALESCE(
                    excluded.avg_speed_mps, fact_activity_split.avg_speed_mps),
                avg_stride_length_cm = COALESCE(
                    excluded.avg_stride_length_cm, fact_activity_split.avg_stride_length_cm),
                ground_contact_time_ms = COALESCE(
                    excluded.ground_contact_time_ms, fact_activity_split.ground_contact_time_ms),
                vertical_oscillation_cm = COALESCE(
                    excluded.vertical_oscillation_cm, fact_activity_split.vertical_oscillation_cm),
                vertical_ratio = COALESCE(
                    excluded.vertical_ratio, fact_activity_split.vertical_ratio),
                elevation_gain_m = COALESCE(
                    excluded.elevation_gain_m, fact_activity_split.elevation_gain_m),
                elevation_loss_m = COALESCE(
                    excluded.elevation_loss_m, fact_activity_split.elevation_loss_m),
                intensity_type = COALESCE(
                    excluded.intensity_type, fact_activity_split.intensity_type),
                avg_pace_min_km = COALESCE(
                    excluded.avg_pace_min_km, fact_activity_split.avg_pace_min_km)
        """, (
            activity_id, i,
            distance,
            duration,
            lap.get("averageHR"),
            lap.get("maxHR"),
            lap.get("averageRunCadence") or lap.get("averageRunningCadenceInStepsPerMinute") or lap.get("averageCadence"),
            lap.get("maxRunCadence") or lap.get("maxRunningCadenceInStepsPerMinute"),
            lap.get("averagePower"),
            lap.get("maxPower"),
            lap.get("normalizedPower") or lap.get("normPower"),
            lap.get("averageSpeed"),
            lap.get("strideLength"),
            lap.get("groundContactTime"),
            lap.get("verticalOscillation"),
            lap.get("verticalRatio"),
            lap.get("elevationGain"),
            lap.get("elevationLoss"),
            lap.get("intensityType"),
            avg_pace,
        ))

    # The endpoint is a complete ordered snapshot.  Remove tail rows left by a
    # previous version of an activity after Garmin reprocesses/edits its laps.
    cur.execute(
        "DELETE FROM fact_activity_split WHERE activity_id = ? AND split_num > ?",
        (activity_id, len(laps)),
    )


# ── Reconciliation (กิจกรรมถูกลบฝั่ง Garmin) ──────────────────

def reconcile_activities(conn, athlete_id, start_date, end_date, present_ids):
    """เทียบกิจกรรมใน DB ช่วง [start,end] กับ activityId จริงจาก Garmin (present_ids):
      - อยู่ DB แต่ไม่อยู่ Garmin = ถูกลบฝั่งแอป → set deleted_at (soft delete ไม่ลบแถวจริง)
      - เคยมาร์ค deleted แต่กลับมาอยู่ Garmin = กู้คืน → clear deleted_at (self-healing)

    ⚠️ เรียกเฉพาะเมื่อ present_ids มาจาก collection ที่ตรวจรูปแบบครบแล้วเท่านั้น —
    ถ้าดึงพลาดแล้วส่ง set ว่างเข้ามาจะ mark กิจกรรมที่ยังอยู่จริงทั้งหมดว่าถูกลบ"""
    cur = conn.cursor()
    db_rows = cur.execute(
        """SELECT activity_id, deleted_at FROM fact_activity
           WHERE athlete_id = ?
             AND substr(start_time_local, 1, 10) BETWEEN ? AND ?""",
        (athlete_id, str(start_date), str(end_date))).fetchall()
    now = datetime.now().isoformat(timespec="seconds")
    marked, restored = [], []
    for act_id, deleted_at in db_rows:
        present = act_id in present_ids
        if not present and deleted_at is None:
            cur.execute("UPDATE fact_activity SET deleted_at = ? WHERE activity_id = ?",
                        (now, act_id))
            marked.append(act_id)
        elif present and deleted_at is not None:
            cur.execute("UPDATE fact_activity SET deleted_at = NULL WHERE activity_id = ?",
                        (act_id,))
            restored.append(act_id)
    conn.commit()
    if marked:
        print(f"   🗑️  กิจกรรมถูกลบฝั่ง Garmin {len(marked)} รายการ → mark deleted (id: {marked})")
    if restored:
        print(f"   ♻️  กิจกรรมกลับมา {len(restored)} รายการ → เคลียร์ deleted (id: {restored})")
    return marked, restored


def reconcile_only(garmin, conn, athlete_id, start_date, end_date):
    """Reconcile a bounded wide window and selectively import remote-only rows.

    Existing rows cost no detail calls.  Garmin-only rows are enriched once,
    which lets the weekly 90-day lane repair old uploads missed by daily sync.
    """
    print(f"\n🔍 Reconcile (เช็คกิจกรรมถูกลบ) {start_date} → {end_date}...")
    activities = safe_call(garmin.get_activities_by_date,
                           start_date.isoformat(), end_date.isoformat())
    activities = _validated_activities(activities)
    present_ids = {activity_id for _activity, activity_id in activities}
    local_ids = {
        row[0] for row in conn.execute(
            """SELECT activity_id FROM fact_activity
               WHERE athlete_id = ?
                 AND substr(start_time_local, 1, 10) BETWEEN ? AND ?""",
            (athlete_id, str(start_date), str(end_date)),
        ).fetchall()
    }
    missing = []
    seen_missing = set()
    for activity, activity_id in activities:
        if activity_id not in local_ids and activity_id not in seen_missing:
            missing.append((activity, activity_id))
            seen_missing.add(activity_id)
    if missing:
        fetch_and_insert_activities(
            garmin,
            conn,
            athlete_id,
            start_date,
            end_date,
            _validated_source=missing,
            reconcile=False,
        )
    marked, restored = reconcile_activities(conn, athlete_id, start_date, end_date, present_ids)
    print(f"   ✅ Reconcile เสร็จ — Garmin มี {len(present_ids)} กิจกรรม | "
          f"นำเข้าที่ขาด {len(missing)} | mark deleted {len(marked)} | "
          f"กู้คืน {len(restored)}")
    return marked, restored, [activity_id for _activity, activity_id in missing]


# ── Daily Wellness Fetching ──────────────────────────────────

# ── Wellness parsers ────────────────────────────────────────
# แยกออกมาเป็นฟังก์ชันเพราะใช้ 2 ทาง: full sync (เขียนทั้งแถว) กับ fast wellness
# (อัปเดตเฉพาะฟิลด์ที่ขยับระหว่างวัน) — คีย์ของ dict = ชื่อคอลัมน์ใน fact_daily_wellness


def _first_not_none(*values):
    """Return the first actual value; unlike ``or`` this preserves numeric zero."""
    return next((value for value in values if value is not None), None)


def _bounded_number(value, minimum=0, maximum=None):
    """Validate a Garmin numeric field and turn sentinels/garbage into NULL.

    Garmin uses negative numbers (commonly -1) as "not available" in more than
    just the stats endpoint.  Reject bools and non-finite floats too so NaN/Inf
    cannot poison SQLite aggregates.  Callers provide the documented/physical
    range for scores whose bounds are known.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(float(value)):
        return None
    if minimum is not None and value < minimum:
        return None
    if maximum is not None and value > maximum:
        return None
    return value


def _clean_text(value, max_length=500):
    """Keep a small printable text value from an API payload, or return NULL."""
    if not isinstance(value, str):
        return None
    value = "".join(ch for ch in value.strip() if ch.isprintable())
    return value[:max_length] or None


def _calendar_date(value):
    """Return a canonical YYYY-MM-DD API date, rejecting malformed keys."""
    if not isinstance(value, str):
        return None
    candidate = value.strip()[:10]
    try:
        return date.fromisoformat(candidate).isoformat()
    except ValueError:
        return None


def _api_datetime(value):
    """Parse Garmin ISO/epoch timestamps as an aware datetime for ordering.

    ``timestamp`` is UTC in the Training Readiness contract.  Numeric values are
    accepted in seconds or milliseconds.  Naive strings are treated as UTC;
    ``timestampLocal`` is only used as a fallback and snapshots for one response
    are from the same athlete/timezone, so their ordering remains correct.
    """
    try:
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        if isinstance(value, (int, float)):
            if not math.isfinite(float(value)):
                return None
            seconds = float(value)
            if abs(seconds) >= 100_000_000_000:
                seconds /= 1000.0
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        if not isinstance(value, str) or not value.strip():
            return None
        raw = value.strip()
        if raw.replace(".", "", 1).isdigit():
            return _api_datetime(float(raw))
        if raw.endswith(("Z", "z")):
            raw = raw[:-1] + "+00:00"
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (OverflowError, OSError, TypeError, ValueError):
        return None


def _utc_timestamp_text(value):
    parsed = _api_datetime(value)
    if parsed is None:
        return None
    return parsed.isoformat(timespec="seconds").replace("+00:00", "Z")


def _readiness_snapshot(readiness):
    """Choose the newest Training Readiness snapshot without trusting list order."""
    items = readiness if isinstance(readiness, list) else [readiness]
    candidates = [item for item in items if isinstance(item, dict)]
    if not candidates:
        return None

    def sort_key(item):
        moment = _first_not_none(
            _api_datetime(item.get("timestamp")),
            _api_datetime(item.get("timestampLocal")),
            _api_datetime(item.get("calendarDate")),
        )
        epoch = moment.timestamp() if moment is not None else float("-inf")
        # Canonical payload is a stable final tie-breaker, so equal/missing
        # timestamps do not silently make the result depend on list order.
        canonical = json.dumps(item, sort_keys=True, ensure_ascii=True, default=str)
        return (moment is not None, epoch, canonical)

    return max(candidates, key=sort_key)


def _parse_stats(stats):
    """RHR / steps / stress / kcal / floors / body battery ละเอียด / respiration ตื่น."""
    def _s(*keys, minimum=0, maximum=None):
        raw = safe_get(stats, *keys) if isinstance(stats, dict) else None
        return _bounded_number(raw, minimum, maximum)
    parsed = {
        "resting_hr": _s("restingHeartRate", minimum=1, maximum=300),
        "steps": _s("totalSteps", maximum=1_000_000),
        "steps_goal": _s("dailyStepGoal", maximum=1_000_000),
        "stress_avg": _s("averageStressLevel", maximum=100),
        "max_stress": _s("maxStressLevel", maximum=100),
        "floors_ascended": _s("floorsAscended", maximum=10_000),
        "active_kilocalories": _s("activeKilocalories", maximum=100_000),
        "bmr_kilocalories": _s("bmrKilocalories", maximum=100_000),
        "active_seconds": _s("activeSeconds", maximum=86_400),
        "avg_waking_respiration": _s(
            "avgWakingRespirationValue", minimum=1, maximum=100),
        "body_battery_high": _s("bodyBatteryHighestValue", minimum=5, maximum=100),
        "body_battery_low": _s("bodyBatteryLowestValue", minimum=5, maximum=100),
        "bb_at_wake": _s("bodyBatteryAtWakeTime", minimum=5, maximum=100),
        # These three are cumulative/change amounts, not instantaneous 5–100
        # levels (a valid daily charged value of 102 exists in production).
        "bb_charged": _s("bodyBatteryChargedValue", maximum=1_000),
        "bb_drained": _s("bodyBatteryDrainedValue", maximum=1_000),
        "bb_during_sleep": _s("bodyBatteryDuringSleep", maximum=1_000),
        "bb_most_recent": _s("bodyBatteryMostRecentValue", minimum=5, maximum=100),
    }
    # Treat the daily high/low levels as one atomic observation.  Garmin can
    # occasionally return a sentinel for only one half of the pair.  Updating
    # the other half alone could combine it with yesterday's/earlier snapshot
    # and manufacture an impossible high < low relation in SQLite.
    bb_pair = (parsed["body_battery_high"], parsed["body_battery_low"])
    if (
        (bb_pair[0] is None) != (bb_pair[1] is None)
        or (bb_pair[0] is not None and bb_pair[0] < bb_pair[1])
    ):
        parsed["body_battery_high"] = None
        parsed["body_battery_low"] = None
    return parsed


def _parse_hrv(hrv):
    out = {"hrv_weekly_avg": None, "hrv_last_night": None, "hrv_status": None}
    if isinstance(hrv, dict):
        summary = safe_get(hrv, "hrvSummary")
        if not isinstance(summary, dict):
            summary = {}
        # Fall back independently.  Previously a missing nested weeklyAvg also
        # replaced a perfectly good nested lastNightAvg/status with top-level NULL.
        weekly = _first_not_none(summary.get("weeklyAvg"), hrv.get("weeklyAvg"))
        last_night = _first_not_none(summary.get("lastNightAvg"), hrv.get("lastNightAvg"))
        status = _first_not_none(summary.get("status"), hrv.get("status"))
        out["hrv_weekly_avg"] = _bounded_number(weekly, 1, 1_000)
        out["hrv_last_night"] = _bounded_number(last_night, 1, 1_000)
        out["hrv_status"] = _clean_text(status, 100)
    return out


def _parse_sleep(sleep):
    out = {"sleep_score": None, "sleep_duration_sec": None, "deep_sleep_sec": None,
           "light_sleep_sec": None, "rem_sleep_sec": None, "awake_sec": None}
    if sleep and isinstance(sleep, dict):
        daily_sleep = safe_get(sleep, "dailySleepDTO")
        if isinstance(daily_sleep, dict):
            out["sleep_duration_sec"] = _bounded_number(
                safe_get(daily_sleep, "sleepTimeSeconds"), 0, 172_800)
            out["deep_sleep_sec"] = _bounded_number(
                safe_get(daily_sleep, "deepSleepSeconds"), 0, 172_800)
            out["light_sleep_sec"] = _bounded_number(
                safe_get(daily_sleep, "lightSleepSeconds"), 0, 172_800)
            out["rem_sleep_sec"] = _bounded_number(
                safe_get(daily_sleep, "remSleepSeconds"), 0, 172_800)
            out["awake_sec"] = _bounded_number(
                safe_get(daily_sleep, "awakeSleepSeconds"), 0, 172_800)
            # sleepScores lives INSIDE dailySleepDTO, not at the top level
            out["sleep_score"] = _bounded_number(
                safe_get(daily_sleep, "sleepScores", "overall", "value"), 0, 100)
        # Fallback for older payload shapes
        if out["sleep_score"] is None:
            out["sleep_score"] = _bounded_number(_first_not_none(
                safe_get(sleep, "overallScore"),
                safe_get(sleep, "sleepScores", "overall", "value"),
            ), 0, 100)
    return out


def _parse_respiration(respiration):
    out = {"avg_sleep_respiration": None, "highest_respiration": None,
           "lowest_respiration": None, "avg_waking_respiration": None}
    if isinstance(respiration, dict):
        out["avg_sleep_respiration"] = _bounded_number(
            respiration.get("avgSleepRespirationValue"), 1, 100)
        out["highest_respiration"] = _bounded_number(
            respiration.get("highestRespirationValue"), 1, 100)
        out["lowest_respiration"] = _bounded_number(
            respiration.get("lowestRespirationValue"), 1, 100)
        out["avg_waking_respiration"] = _bounded_number(
            respiration.get("avgWakingRespirationValue"), 1, 100)
    return out


def _parse_readiness(readiness):
    """readiness score/level/feedback + acute load + ACWR ของ Garmin เอง + ปัจจัยย่อย.
    API คืน LIST อาจว่างถ้านาฬิกาไม่ให้"""
    out = {
        "training_readiness": None,
        "readiness_level": None,
        "readiness_feedback": None,
        "readiness_feedback_long": None,
        "readiness_timestamp_utc": None,
        "readiness_timestamp_local": None,
        "readiness_input_context": None,
        "readiness_device_id": None,
        "readiness_sleep_factor_pct": None,
        "readiness_sleep_factor_feedback": None,
        "acute_load": None,
        "acwr_percent": None,
        "acwr_factor_feedback": None,
        "hrv_factor_pct": None,
        "hrv_factor_feedback": None,
        "recovery_time_min": None,
        "recovery_time_factor_pct": None,
        "recovery_time_factor_feedback": None,
        "recovery_time_change_phrase": None,
        "stress_history_pct": None,
        "stress_history_factor_feedback": None,
    }
    obj = _readiness_snapshot(readiness)
    if isinstance(obj, dict):
        out["training_readiness"] = _bounded_number(
            _first_not_none(obj.get("score"), obj.get("trainingReadinessScore")), 0, 100)
        out["readiness_level"] = _clean_text(obj.get("level"), 100)
        out["readiness_feedback"] = _clean_text(obj.get("feedbackShort"), 500)
        out["readiness_feedback_long"] = _clean_text(obj.get("feedbackLong"), 2_000)
        out["readiness_timestamp_utc"] = _utc_timestamp_text(obj.get("timestamp"))
        out["readiness_timestamp_local"] = _clean_text(obj.get("timestampLocal"), 100)
        out["readiness_input_context"] = _clean_text(obj.get("inputContext"), 200)
        device_id = obj.get("deviceId")
        if isinstance(device_id, (str, int)) and not isinstance(device_id, bool):
            out["readiness_device_id"] = _clean_text(str(device_id), 100)
        out["readiness_sleep_factor_pct"] = _bounded_number(
            obj.get("sleepScoreFactorPercent"), 0, 100)
        out["readiness_sleep_factor_feedback"] = _clean_text(
            obj.get("sleepScoreFactorFeedback"), 500)
        out["acute_load"] = _bounded_number(obj.get("acuteLoad"), 0, 100_000)
        out["acwr_percent"] = _bounded_number(obj.get("acwrFactorPercent"), 0, 100)
        out["acwr_factor_feedback"] = _clean_text(obj.get("acwrFactorFeedback"), 500)
        out["hrv_factor_pct"] = _bounded_number(obj.get("hrvFactorPercent"), 0, 100)
        out["hrv_factor_feedback"] = _clean_text(obj.get("hrvFactorFeedback"), 500)
        phrase = _clean_text(obj.get("recoveryTimeChangePhrase"), 200)
        recovery_minutes = _bounded_number(obj.get("recoveryTime"), 0, 5_760)
        if phrase and phrase.upper() == "REACHED_ZERO":
            recovery_minutes = 0
        out["recovery_time_min"] = recovery_minutes
        out["recovery_time_factor_pct"] = _bounded_number(
            obj.get("recoveryTimeFactorPercent"), 0, 100)
        out["recovery_time_factor_feedback"] = _clean_text(
            obj.get("recoveryTimeFactorFeedback"), 500)
        out["recovery_time_change_phrase"] = phrase
        out["stress_history_pct"] = _bounded_number(
            obj.get("stressHistoryFactorPercent"), 0, 100)
        out["stress_history_factor_feedback"] = _clean_text(
            obj.get("stressHistoryFactorFeedback"), 500)
    return out


def _parse_training_status(training_status):
    """payload ซ้อนอยู่ใต้ mostRecentTrainingStatus.latestTrainingStatusData.<deviceId>."""
    value = None
    if isinstance(training_status, dict):
        latest = safe_get(training_status, "mostRecentTrainingStatus", "latestTrainingStatusData")
        if isinstance(latest, dict):
            for device_data in latest.values():
                if isinstance(device_data, dict):
                    value = _first_not_none(
                        device_data.get("trainingStatusFeedbackPhrase"),
                        device_data.get("trainingStatus"),
                    )
                    if value is not None:
                        break
        # Fallback to older top-level shapes
        if value is None:
            value = _first_not_none(
                safe_get(training_status, "trainingStatus"),
                safe_get(training_status, "currentDayTrainingStatus"),
            )
    return {"training_status": _clean_text(value, 500)}


def _parse_max_metrics(max_metrics):
    """payload เป็น list ต่อ device — เอาตัวแรกที่มีค่า generic.

    **ห้ามอ่าน fitness_age จากตรงนี้** (เอาออก 4 ส.ค. 69): `generic` มีคีย์ `fitnessAge`
    อยู่จริงแต่ Garmin คืน `None` เสมอทั้ง 3 คน — ค่าจริงอยู่คนละ endpoint
    (`get_fitnessage_data()` → แดน 18.0 / พี่เก้า 22.1) ซึ่ง `fetch_and_insert_extras`
    เป็นคนดึง. ถ้าปล่อยคีย์นี้ไว้ในทางรายวัน มันจะเขียน None ทับของที่ extras เพิ่งเก็บ
    ทุกรอบ — บั๊กแบบเดียวกับที่เคยล้าง lactate_threshold ย้อนหลังทิ้ง (3 ส.ค. 69)
    """
    out = {"vo2max_trend": None}
    items = max_metrics if isinstance(max_metrics, list) else [max_metrics]
    for item in items:
        if not isinstance(item, dict):
            continue
        generic = item.get("generic")
        if isinstance(generic, dict):
            out["vo2max_trend"] = _bounded_number(_first_not_none(
                generic.get("vo2MaxPreciseValue"), generic.get("vo2MaxValue")
            ), 1, 150)
            if out["vo2max_trend"] is not None:
                break
    return out


def _parse_endurance(endurance):
    return {"endurance_score": _bounded_number(
        endurance.get("overallScore") if isinstance(endurance, dict) else None,
        0, 100_000,
    )}


def _parse_hill(hill):
    hill = hill if isinstance(hill, dict) else {}
    return {
        "hill_score_overall": _bounded_number(hill.get("overallScore"), 0, 100),
        "hill_score_strength": _bounded_number(hill.get("strengthScore"), 0, 100),
        "hill_score_endurance": _bounded_number(hill.get("enduranceScore"), 0, 100),
    }


def _fill_missing(target: dict, extra: dict) -> dict:
    """เติมเฉพาะคีย์ที่ target ยังว่าง (ใช้กับ waking respiration ที่มาได้ 2 ทาง)."""
    for key, value in extra.items():
        if target.get(key) is None:
            target[key] = value
    return target


def _wellness_columns(cur):
    """Return deployed columns so new ingestion remains safe during rollout."""
    return {row[1] for row in cur.execute("PRAGMA table_info(fact_daily_wellness)")}


def _atomic_body_battery_values(values: dict) -> dict:
    """Return merge values with daily Body Battery high/low kept atomic.

    Parsers normally provide both keys, but this guard lives at the write
    boundary as well so a future caller cannot update just one half and create
    an incoherent pair with a value already stored in the row.
    """
    prepared = dict(values)
    pair = ("body_battery_high", "body_battery_low")
    if not any(key in prepared for key in pair):
        return prepared
    high = _bounded_number(prepared.get(pair[0]), 5, 100)
    low = _bounded_number(prepared.get(pair[1]), 5, 100)
    if high is None or low is None or high < low:
        prepared.pop(pair[0], None)
        prepared.pop(pair[1], None)
    else:
        prepared[pair[0]] = high
        prepared[pair[1]] = low
    return prepared


def _insert_wellness_row(cur, athlete_id, date_str, values: dict):
    """เขียนแถวของวันนั้น — ต้อง upsert ระบุคอลัมน์เอง **ห้ามปล่อยให้ PK ของตาราง
    (ON CONFLICT REPLACE) ทำงาน**: REPLACE = ลบแถวเดิมทิ้งแล้วใส่ใหม่ คอลัมน์ที่รอบนี้
    ไม่ได้ดึงจะกลายเป็น NULL ทั้งหมด

    เจอจริง 3 ส.ค. 69: deep resync 45 วัน ล้าง lactate_threshold ย้อนหลังของพี่เก้าทิ้ง
    (16 ก.ค. HR 184 / pace 5:02 จากค่า 5.04 นาที/กม. — ค่าที่ LTHR_BY_SLUG ใน
    dashboard อ้างอิงอยู่) เพราะ LT
    ไม่ได้ดึงรายวัน แต่ fetch_extras เขียนให้เฉพาะ "วันล่าสุด" วันเดียว → ทุกวันที่ถูก
    เขียนซ้ำจะเสีย LT ไป เหลือแค่วันล่าสุดวันเดียว
    (ชื่อคอลัมน์มาจาก parser ในไฟล์นี้เท่านั้น ไม่ได้มาจาก input ภายนอก)"""
    # Endpoint absence/temporary failure is represented by None.  Full/deep sync
    # must follow the same non-destructive rule as fast sync: only fields with a
    # fresh valid value are allowed to replace the existing snapshot.
    allowed = _wellness_columns(cur)
    values = _atomic_body_battery_values(values)
    fresh = {
        key: value for key, value in values.items()
        if value is not None and key in allowed
    }
    cols = list(fresh)
    if not cols:
        cur.execute(
            "INSERT OR IGNORE INTO fact_daily_wellness "
            f"(athlete_id, calendar_date, fetched_at) VALUES (?, ?, {UTC_NOW_SQL})",
            (athlete_id, date_str),
        )
        return 0
    placeholders = ", ".join(["?"] * (len(cols) + 2))
    assignments = ", ".join(f"{c} = excluded.{c}" for c in cols)
    # fetched_at ต้องเลื่อนเอง: ปกติมันได้ค่า DEFAULT ตอน insert แถวใหม่ แต่ทาง DO UPDATE
    # ไม่มีใครแตะ → dashboard (ที่ใช้ fetched_at ตัดสินความสดของข้อมูล) จะอ่านผิด
    cur.execute(
        f"INSERT INTO fact_daily_wellness "
        f"(athlete_id, calendar_date, {', '.join(cols)}, fetched_at) "
        f"VALUES ({placeholders}, {UTC_NOW_SQL}) "
        f"ON CONFLICT(athlete_id, calendar_date) DO UPDATE SET {assignments}, "
        f"fetched_at = {UTC_NOW_SQL}",
        (athlete_id, date_str, *(fresh[c] for c in cols)),
    )
    return len(fresh)


def _update_wellness_fields(cur, athlete_id, date_str, values: dict) -> int:
    """อัปเดตเฉพาะคอลัมน์ที่มีค่า (ห้าม INSERT OR REPLACE — จะล้างคอลัมน์อื่นของวันนั้นทิ้ง
    เช่น sleep/VO2max/LT ที่ full sync เก็บไว้แล้ว). คืนจำนวนคอลัมน์ที่เขียนจริง"""
    allowed = _wellness_columns(cur)
    values = _atomic_body_battery_values(values)
    fresh = {
        key: value for key, value in values.items()
        if value is not None and key in allowed
    }
    if not fresh:
        return 0
    cur.execute(
        "INSERT OR IGNORE INTO fact_daily_wellness "
        f"(athlete_id, calendar_date, fetched_at) VALUES (?, ?, {UTC_NOW_SQL})",
        (athlete_id, date_str),
    )
    # ต้องเลื่อน fetched_at ด้วย ไม่งั้นมันจะค้างที่เวลา insert แถวแรกของวัน แล้ว dashboard
    # (ที่ใช้ fetched_at ตัดสินว่า "ค่าครบวันแล้วหรือยัง") จะอ่านความสดของข้อมูลผิด
    assignments = ", ".join(f"{c} = ?" for c in fresh)
    cur.execute(
        f"UPDATE fact_daily_wellness SET {assignments}, fetched_at = {UTC_NOW_SQL} "
        f"WHERE athlete_id = ? AND calendar_date = ?",
        (*fresh.values(), athlete_id, date_str),
    )
    return len(fresh)


def fetch_and_update_wellness_fast(
    garmin, conn, athlete_id, start_date, end_date, *, endpoint_failures=None,
    terminal_errors=None,
):
    """fast wellness: ดึงเฉพาะค่าที่ "ขยับระหว่างวัน" ของช่วงสั้น ๆ แล้วอัปเดตทับเป็นราย
    คอลัมน์ (ไม่ล้างของเดิม) — 4 endpoint ต่อวันแทน 9 ของ full sync

    เอาเข้า: stats (body battery/RHR/stress/steps/kcal), HRV, sleep, training readiness
    ไม่เอา: respiration / training status / VO2max trend / endurance / hill / extras
            — Garmin คำนวณวันละครั้ง รอ full sync 08:00/21:00 เติมได้ ไม่ต้องยิงถี่
    """
    print(f"\n⚡ Fast wellness {start_date} → {end_date} (เฉพาะค่าที่ขยับระหว่างวัน)...")

    cur = conn.cursor()
    current = start_date
    count = 0
    deferred_errors = []

    while current <= end_date:
        date_str = current.isoformat()
        print(f"   {date_str}", end="", flush=True)
        day_failures = []

        stats = _call_wellness_endpoint(
            garmin, "get_stats", date_str, day_failures
        )
        time.sleep(0.3)
        hrv = _call_wellness_endpoint(
            garmin, "get_hrv_data", date_str, day_failures
        )
        time.sleep(0.3)
        sleep = _call_wellness_endpoint(
            garmin, "get_sleep_data", date_str, day_failures
        )
        time.sleep(0.3)
        readiness = _call_wellness_endpoint(
            garmin, "get_training_readiness", date_str, day_failures
        )
        if endpoint_failures is not None:
            endpoint_failures.extend(day_failures)
        error = _core_wellness_error(day_failures)
        if error is not None:
            deferred_errors.append(error)

        values = {
            **_parse_stats(stats),
            **_parse_hrv(hrv),
            **_parse_sleep(sleep),
            **_parse_readiness(readiness),
        }
        n_fields = _update_wellness_fields(cur, athlete_id, date_str, values)
        # ไม่ถือ write transaction ค้างระหว่าง network calls ของวันถัดไป
        conn.commit()
        if n_fields:
            count += 1
        print(f" ✓ ({n_fields} ฟิลด์)")

        time.sleep(1.0)
        current += timedelta(days=1)

    print(f"   ✅ อัปเดต wellness {count} วัน")
    _publish_deferred_wellness_errors(deferred_errors, terminal_errors)
    return count


_REPAIR_CHECK_FIELDS = (
    "repair_attempted_at_utc",
    "resting_hr", "stress_avg", "steps",
    "sleep_score", "hrv_last_night",
    "body_battery_high", "body_battery_low",
    "avg_waking_respiration", "avg_sleep_respiration",
)


def _previous_day_repair_due(conn, athlete_id, repair_date, *, now_utc=None):
    """Return ``(due, reasons)`` for a throttled previous-day wellness repair."""
    cur = conn.cursor()
    columns = _wellness_columns(cur)
    if not set(_REPAIR_CHECK_FIELDS).issubset(columns):
        return False, ["schema_missing_repair_metadata"]

    row = cur.execute(
        f"SELECT {', '.join(_REPAIR_CHECK_FIELDS)} FROM fact_daily_wellness "
        "WHERE athlete_id = ? AND calendar_date = ?",
        (athlete_id, str(repair_date)),
    ).fetchone()
    now_utc = _api_datetime(now_utc or datetime.now(timezone.utc))
    if row is None:
        return True, ["row_missing"]

    values = dict(zip(_REPAIR_CHECK_FIELDS, row))
    attempted = _api_datetime(values["repair_attempted_at_utc"])
    if attempted is not None:
        elapsed = now_utc - attempted
        if timedelta(0) <= elapsed < timedelta(hours=PREVIOUS_DAY_REPAIR_COOLDOWN_HOURS):
            return False, ["cooldown"]

    reasons = []
    if values["sleep_score"] is None:
        reasons.append("sleep_missing")
    if values["hrv_last_night"] is None:
        reasons.append("hrv_missing")

    core_fields = ("resting_hr", "stress_avg", "steps", "body_battery_high")
    if any(values[field] is None for field in core_fields):
        reasons.append("core_stats_partial")

    bb_high = values["body_battery_high"]
    bb_low = values["body_battery_low"]
    if (
        (bb_high is not None and _bounded_number(bb_high, 5, 100) is None)
        or (bb_low is not None and _bounded_number(bb_low, 5, 100) is None)
        or (bb_high is not None and bb_low is not None and bb_high < bb_low)
    ):
        reasons.append("body_battery_invalid")

    has_daytime_or_core = any(
        values[field] is not None
        for field in (*core_fields, "avg_waking_respiration", "sleep_score")
    )
    if values["avg_sleep_respiration"] is None and has_daytime_or_core:
        reasons.append("sleep_respiration_missing")
    return bool(reasons), reasons


def fetch_and_repair_previous_day_wellness(
    garmin, conn, athlete_id, repair_date, *, now_utc=None,
    endpoint_failures=None, terminal_errors=None,
):
    """Repair a partial yesterday snapshot without doubling every fast poll.

    Only a partial/invalid row that is outside the cooldown triggers calls.  The
    extra respiration endpoint is included because overnight values commonly
    arrive after the first post-wakeup sync.  Every write is NULL-safe.
    """
    due, reasons = _previous_day_repair_due(
        conn, athlete_id, repair_date, now_utc=now_utc)
    if not due:
        if reasons != ["cooldown"]:
            print(f"   ℹ️  ข้ามซ่อม {repair_date}: ข้อมูลเมื่อวานครบหรือ schema ยังไม่พร้อม")
        return 0

    date_str = str(repair_date)
    print(f"\n🩹 ซ่อม wellness เมื่อวาน {date_str} ({', '.join(reasons)})...")
    failures = []
    stats = _call_wellness_endpoint(garmin, "get_stats", date_str, failures)
    time.sleep(0.3)
    hrv = _call_wellness_endpoint(garmin, "get_hrv_data", date_str, failures)
    time.sleep(0.3)
    sleep = _call_wellness_endpoint(garmin, "get_sleep_data", date_str, failures)
    time.sleep(0.3)
    respiration = _call_wellness_endpoint(
        garmin, "get_respiration_data", date_str, failures
    )
    time.sleep(0.3)
    readiness = _call_wellness_endpoint(
        garmin, "get_training_readiness", date_str, failures
    )
    if endpoint_failures is not None:
        endpoint_failures.extend(failures)

    values = {
        **_parse_stats(stats),
        **_parse_hrv(hrv),
        **_parse_sleep(sleep),
        **_parse_readiness(readiness),
    }
    _fill_missing(values, _parse_respiration(respiration))
    cur = conn.cursor()
    n_fields = _update_wellness_fields(cur, athlete_id, date_str, values)
    conn.commit()
    # Preserve any valid respiration value, but do not consume the repair
    # cooldown when every core endpoint errored; the next lane must retry.
    error = _core_wellness_error(failures)
    if error is not None:
        if terminal_errors is None:
            raise error
        terminal_errors.append(error)
        return int(n_fields > 0)

    # Record the attempt even if Garmin still returned nothing.  A real
    # no-night-data case will therefore retry only after the cooldown.
    attempted_at = _utc_timestamp_text(now_utc or datetime.now(timezone.utc))
    if "repair_attempted_at_utc" in _wellness_columns(cur):
        cur.execute(
            "INSERT OR IGNORE INTO fact_daily_wellness "
            f"(athlete_id, calendar_date, repair_attempted_at_utc, fetched_at) "
            f"VALUES (?, ?, ?, {UTC_NOW_SQL})",
            (athlete_id, date_str, attempted_at),
        )
        cur.execute(
            "UPDATE fact_daily_wellness SET repair_attempted_at_utc = ? "
            "WHERE athlete_id = ? AND calendar_date = ?",
            (attempted_at, athlete_id, date_str),
        )
    conn.commit()
    print(f"   ✅ ซ่อมเมื่อวานแล้ว ({n_fields} ฟิลด์ที่ Garmin ส่งกลับ)")
    return int(n_fields > 0)


def fetch_and_insert_wellness(
    garmin, conn, athlete_id, start_date, end_date, *, endpoint_failures=None,
    terminal_errors=None,
):
    """Fetch daily wellness metrics day-by-day."""
    print(f"\n🩺 Fetching daily wellness from {start_date} to {end_date}...")

    cur = conn.cursor()
    current = start_date
    count = 0
    deferred_errors = []
    total_days = (end_date - start_date).days + 1

    while current <= end_date:
        date_str = current.isoformat()
        day_num = (current - start_date).days + 1
        print(f"   Day {day_num}/{total_days}: {date_str}", end="", flush=True)
        day_failures = []

        # ── Stats (steps, resting HR, stress) ──
        stats = _call_wellness_endpoint(
            garmin, "get_stats", date_str, day_failures
        )
        time.sleep(0.3)

        # ── HRV ──
        hrv = _call_wellness_endpoint(
            garmin, "get_hrv_data", date_str, day_failures
        )
        time.sleep(0.3)

        # ── Sleep ──
        sleep = _call_wellness_endpoint(
            garmin, "get_sleep_data", date_str, day_failures
        )
        time.sleep(0.3)

        # ── Respiration (Body Battery ดึงจาก get_stats แล้ว ไม่ต้องเรียกแยก) ──
        respiration = _call_wellness_endpoint(
            garmin, "get_respiration_data", date_str, day_failures
        )
        time.sleep(0.3)

        # ── Training Readiness ──
        readiness = _call_wellness_endpoint(
            garmin, "get_training_readiness", date_str, day_failures
        )
        time.sleep(0.3)

        # ── Training Status ──
        training_status = _call_wellness_endpoint(
            garmin, "get_training_status", date_str, day_failures
        )
        time.sleep(0.3)

        # ── Max metrics (VO2max trend + fitness age — เทรนด์รายวัน ไม่ใช่แค่วันเทส) ──
        max_metrics = _call_wellness_endpoint(
            garmin, "get_max_metrics", date_str, day_failures
        )
        time.sleep(0.3)

        # ── Endurance score (device-dependent — นาฬิการุ่นเก่าได้ None) ──
        endurance = _call_wellness_endpoint(
            garmin, "get_endurance_score", date_str, day_failures
        )
        time.sleep(0.3)

        # ── Hill score (device-dependent) ──
        hill = _call_wellness_endpoint(
            garmin, "get_hill_score", date_str, day_failures
        )
        time.sleep(0.3)
        if endpoint_failures is not None:
            endpoint_failures.extend(day_failures)

        values = {
            **_parse_stats(stats),
            **_parse_hrv(hrv),
            **_parse_sleep(sleep),
            **_parse_readiness(readiness),
            **_parse_training_status(training_status),
            **_parse_max_metrics(max_metrics),
            **_parse_endurance(endurance),
            **_parse_hill(hill),
        }
        # waking respiration มาได้ทั้งจาก stats และ respiration — stats มาก่อน แล้วค่อยเติมที่ขาด
        _fill_missing(values, _parse_respiration(respiration))

        _insert_wellness_row(cur, athlete_id, date_str, values)
        # ไม่ถือ write transaction ค้างระหว่าง network calls ของวันถัดไป
        conn.commit()
        # Optional endpoint values above are still valid and must survive even
        # though the round itself is failed because every core source errored.
        error = _core_wellness_error(day_failures)
        if error is not None:
            deferred_errors.append(error)
        count += 1
        print(" ✓")

        # Longer pause between days to avoid rate limit
        time.sleep(1.5)
        current += timedelta(days=1)

    conn.commit()
    print(f"   ✅ Inserted {count} wellness records")
    _publish_deferred_wellness_errors(deferred_errors, terminal_errors)
    return count


# ── Extras (range/snapshot — เรียกครั้งเดียวต่อรอบ ไม่วนรายวัน) ──────────────

# Garmin PR typeId → ป้ายอ่านง่าย (เฉพาะตัวที่ยืนยันความหมายแล้ว — ตัวอื่นเก็บ typeId ดิบ)
PR_LABELS = {
    1: "วิ่ง 1 กม. (วินาที)",
    2: "วิ่ง 1 ไมล์ (วินาที)",
    3: "วิ่ง 5 กม. (วินาที)",
    4: "วิ่ง 10 กม. (วินาที)",
    5: "Half Marathon (วินาที)",
    6: "Marathon (วินาที)",
    7: "วิ่งไกลสุด (เมตร)",
    8: "ปั่นไกลสุด (เมตร)",
    9: "ไต่สะสมสูงสุด/กิจกรรม (เมตร)",
    12: "ก้าวมากสุด/วัน",
    13: "ก้าวมากสุด/สัปดาห์",
    14: "ก้าวมากสุด/เดือน",
}


def _clean_identifier(value, max_length=128):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    value = str(value).strip()
    allowed = set("-_.:")
    if not value or len(value) > max_length:
        return None
    if any(not (ch.isalnum() or ch in allowed) for ch in value):
        return None
    return value


def _bool_flag(value):
    """Normalize API boolean variants without turning missing into false."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)) and value in (0, 1):
        return int(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "y", "1"}:
            return 1
        if normalized in {"false", "no", "n", "0"}:
            return 0
    return None


def fetch_and_upsert_devices(garmin, conn, athlete_id):
    """Refresh the account's device models once per full sync.

    Store only the whitelist needed for capability-aware UI.  Device identifiers
    are keys but are deliberately never included in logs.
    """
    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='dim_athlete_device'"
    ).fetchone()
    if not table_exists:
        print("   ⚠️  ข้าม device inventory: กรุณารัน 02_init_schema.py")
        return 0
    method = getattr(garmin, "get_devices", None)
    if not callable(method):
        return 0
    payload = safe_call(method)
    if isinstance(payload, dict):
        payload = payload.get("devices")
    devices = payload if isinstance(payload, list) else []
    cur = conn.cursor()
    seen = set()
    for device in devices:
        if not isinstance(device, dict):
            continue
        device_id = _clean_identifier(_first_not_none(
            device.get("deviceId"), device.get("unitId")))
        if not device_id or device_id in seen:
            continue
        seen.add(device_id)
        product_name = _clean_text(_first_not_none(
            device.get("productDisplayName"), device.get("productName")), 200)
        display_name = _clean_text(device.get("displayName"), 200)
        is_primary = _bool_flag(_first_not_none(
            device.get("isPrimaryDevice"), device.get("primaryDevice"),
            device.get("primary")))
        is_activity = _bool_flag(_first_not_none(
            device.get("isPrimaryActivityTracker"),
            device.get("primaryActivityTracker")))
        is_training = _bool_flag(_first_not_none(
            device.get("isPrimaryTrainingDevice"),
            device.get("primaryTrainingDevice")))
        cur.execute(
            f"""INSERT INTO dim_athlete_device (
                    athlete_id, device_id, product_display_name, display_name,
                    is_primary_device, is_primary_activity_tracker,
                    is_primary_training_device, last_seen_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, {UTC_NOW_SQL})
                ON CONFLICT(athlete_id, device_id) DO UPDATE SET
                    product_display_name = COALESCE(
                        excluded.product_display_name,
                        dim_athlete_device.product_display_name),
                    display_name = COALESCE(
                        excluded.display_name, dim_athlete_device.display_name),
                    is_primary_device = COALESCE(
                        excluded.is_primary_device,
                        dim_athlete_device.is_primary_device),
                    is_primary_activity_tracker = COALESCE(
                        excluded.is_primary_activity_tracker,
                        dim_athlete_device.is_primary_activity_tracker),
                    is_primary_training_device = COALESCE(
                        excluded.is_primary_training_device,
                        dim_athlete_device.is_primary_training_device),
                    last_seen_at_utc = excluded.last_seen_at_utc""",
            (athlete_id, device_id, product_name, display_name,
             is_primary, is_activity, is_training),
        )
    conn.commit()
    if seen:
        print(f"   ✅ Device inventory: {len(seen)} เครื่อง")
    return len(seen)


def fetch_and_insert_extras(garmin, conn, athlete_id, start_date, end_date):
    """ข้อมูลเสริมที่ API ให้แบบ range/snapshot (ไม่ต้องวนรายวัน — ประหยัด request):
    lactate threshold ล่าสุดจากนาฬิกา, race predictions รายวันทั้งช่วง,
    body composition (น้ำหนัก/BMI/ไขมัน), personal records, gear (รองเท้า)"""
    print("\n🎯 Fetching extras (LT / race predictions / body comp / PR / gear)...")
    cur = conn.cursor()

    # One lightweight account-level call per full sync; never part of fast lanes.
    fetch_and_upsert_devices(garmin, conn, athlete_id)
    time.sleep(0.3)

    # ── Lactate Threshold ล่าสุด (Garmin ประเมินจาก HR+pace ระหว่างวิ่ง) ──
    lt = safe_call(garmin.get_lactate_threshold, latest=True)
    if isinstance(lt, dict):
        shr = lt.get("speed_and_heart_rate") or {}
        lt_date = _calendar_date(shr.get("calendarDate"))
        lt_hr = _bounded_number(shr.get("heartRate"), 1, 300)
        lt_speed = _bounded_number(shr.get("speed"), 0.01, 20)
        # API คืน speed สเกล 0.1 m/s (เจอจริง: พี่เก้าได้ 0.3306 = 3.306 m/s) —
        # LT ของนักวิ่งอยู่ช่วง 2.5-6 m/s ถ้าค่า < 1 แปลว่ามาแบบสเกลย่อ คูณ 10 ก่อน
        if lt_speed is not None and lt_speed < 1.0:
            lt_speed *= 10
        lt_pace = _bounded_number(
            round(1000.0 / lt_speed / 60.0, 2) if lt_speed else None, 1, 30)
        if lt_date and (lt_hr is not None or lt_pace is not None):
            _update_wellness_fields(cur, athlete_id, lt_date, {
                "lactate_threshold_hr": lt_hr,
                "lactate_threshold_pace_min_km": lt_pace,
            })
            print(f"   ✅ LT ล่าสุด ({lt_date}): HR {lt_hr}, pace {lt_pace} นาที/กม.")
    conn.commit()
    time.sleep(0.3)

    # ── Fitness Age (คนละ endpoint กับ maxmetrics — เจอ 4 ส.ค. 69) ──
    # `maxmetrics.generic.fitnessAge` มีคีย์แต่เป็น None เสมอทั้ง 3 คน ค่าจริงต้องเรียก
    # endpoint นี้ (แดน 18.0 / พี่เก้า 22.1) ส่วนต้นตอบ {"invalidReason":"USER_UNDER_AGE"}
    # = Garmin ไม่คำนวณให้คนอายุน้อย ซึ่งไม่ใช่ความผิดพลาด ปล่อย NULL ไว้ถูกแล้ว
    fa = safe_call(garmin.get_fitnessage_data, end_date.isoformat())
    if isinstance(fa, dict):
        fitness_age = None
        if fa.get("invalidReason"):
            print(f"   ℹ️  Fitness Age: Garmin ไม่คำนวณให้ ({fa['invalidReason']})")
        else:
            fitness_age = _bounded_number(fa.get("fitnessAge"), 1, 120)
        if not fa.get("invalidReason") and fitness_age is not None:
            fa_date = end_date.isoformat()
            fitness_age = round(float(fitness_age), 1)
            _update_wellness_fields(cur, athlete_id, fa_date, {
                "fitness_age": fitness_age,
            })
            print(f"   ✅ Fitness Age ({fa_date}): {fitness_age} "
                  f"(อายุจริง {fa.get('chronologicalAge')})")
    conn.commit()
    time.sleep(0.3)

    # ── Race predictions รายวันทั้งช่วง (call เดียวครอบทุกวัน) ──
    preds = safe_call(garmin.get_race_predictions,
                      start_date.isoformat(), end_date.isoformat(), "daily")
    n_pred = 0
    for p in preds if isinstance(preds, list) else []:
        if not isinstance(p, dict):
            continue
        prediction_date = _calendar_date(p.get("calendarDate"))
        if not prediction_date:
            continue
        times = tuple(_bounded_number(value, 1, 604_800) for value in (
            p.get("time5K"), p.get("time10K"),
            p.get("timeHalfMarathon"), p.get("timeMarathon"),
        ))
        if not any(t is not None for t in times):
            continue  # วันปัจจุบัน Garmin มักคืนแถวว่าง (ยังไม่คำนวณ) — ไม่เก็บแถวขยะ
        cur.execute(f"""INSERT INTO fact_race_prediction
            (athlete_id, calendar_date, time_5k_sec, time_10k_sec,
             time_half_sec, time_full_sec, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, {UTC_NOW_SQL})
            ON CONFLICT(athlete_id, calendar_date) DO UPDATE SET
                time_5k_sec = COALESCE(excluded.time_5k_sec, fact_race_prediction.time_5k_sec),
                time_10k_sec = COALESCE(excluded.time_10k_sec, fact_race_prediction.time_10k_sec),
                time_half_sec = COALESCE(excluded.time_half_sec, fact_race_prediction.time_half_sec),
                time_full_sec = COALESCE(excluded.time_full_sec, fact_race_prediction.time_full_sec),
                fetched_at = excluded.fetched_at""",
            (athlete_id, prediction_date, *times))
        n_pred += 1
    if n_pred:
        print(f"   ✅ Race predictions: {n_pred} วัน")
    conn.commit()
    time.sleep(0.3)

    # ── Body composition ทั้งช่วง (call เดียว) — มีค่าเฉพาะคนที่ชั่ง/กรอกน้ำหนัก ──
    body = safe_call(garmin.get_body_composition,
                     start_date.isoformat(), end_date.isoformat())
    n_body = 0
    if isinstance(body, dict):
        for entry in body.get("dateWeightList") or []:
            if not isinstance(entry, dict):
                continue
            cal = _calendar_date(entry.get("calendarDate"))
            if not cal and isinstance(entry.get("date"), (int, float)):
                try:
                    cal = datetime.fromtimestamp(
                        entry["date"] / 1000, tz=timezone.utc).date().isoformat()
                except (OverflowError, OSError, ValueError):
                    cal = None
            if not cal:
                continue
            weight_g = _bounded_number(entry.get("weight"), 1_000, 500_000)
            values = (
                round(weight_g / 1000.0, 2) if weight_g is not None else None,
                _bounded_number(entry.get("bmi"), 5, 100),
                _bounded_number(entry.get("bodyFat"), 0, 100),
            )
            if not any(value is not None for value in values):
                continue
            cur.execute(f"""INSERT INTO fact_body_composition
                (athlete_id, calendar_date, weight_kg, bmi, body_fat_pct, fetched_at)
                VALUES (?, ?, ?, ?, ?, {UTC_NOW_SQL})
                ON CONFLICT(athlete_id, calendar_date) DO UPDATE SET
                    weight_kg = COALESCE(excluded.weight_kg, fact_body_composition.weight_kg),
                    bmi = COALESCE(excluded.bmi, fact_body_composition.bmi),
                    body_fat_pct = COALESCE(
                        excluded.body_fat_pct, fact_body_composition.body_fat_pct),
                    fetched_at = excluded.fetched_at""",
                (athlete_id, cal, *values))
            n_body += 1
    if n_body:
        print(f"   ✅ Body composition: {n_body} รายการ")
    conn.commit()
    time.sleep(0.3)

    # ── Personal records (snapshot ทั้งบัญชี — ทับของเก่าด้วยค่าปัจจุบันเสมอ) ──
    prs = safe_call(garmin.get_personal_record)
    if isinstance(prs, dict):
        prs = prs.get("personalRecords") or []
    n_pr = 0
    for pr in prs if isinstance(prs, list) else []:
        if not isinstance(pr, dict):
            continue
        record_type_id = _bounded_number(pr.get("typeId"), 1, 1_000_000)
        value = _bounded_number(pr.get("value"), 0, 1_000_000_000)
        if record_type_id is None or value is None:
            continue
        achieved = _first_not_none(
            pr.get("prStartTimeGmtFormatted"), pr.get("prStartTimeGmt"))
        if isinstance(achieved, (int, float)):
            try:
                achieved = datetime.fromtimestamp(
                    achieved / 1000, tz=timezone.utc).date().isoformat()
            except (OverflowError, OSError, ValueError):
                achieved = None
        else:
            achieved = _calendar_date(achieved)
        activity_id = _bounded_number(pr.get("activityId"), 1, None)
        cur.execute(f"""INSERT INTO fact_personal_record
            (athlete_id, record_type_id, record_label, value, activity_id,
             achieved_date, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, {UTC_NOW_SQL})
            ON CONFLICT(athlete_id, record_type_id) DO UPDATE SET
                record_label = COALESCE(
                    excluded.record_label, fact_personal_record.record_label),
                value = COALESCE(excluded.value, fact_personal_record.value),
                activity_id = COALESCE(
                    excluded.activity_id, fact_personal_record.activity_id),
                achieved_date = COALESCE(
                    excluded.achieved_date, fact_personal_record.achieved_date),
                fetched_at = excluded.fetched_at""",
            (athlete_id, record_type_id, PR_LABELS.get(record_type_id), value,
             activity_id, achieved))
        n_pr += 1
    if n_pr:
        print(f"   ✅ Personal records: {n_pr} รายการ")
    conn.commit()
    time.sleep(0.3)

    # ── Gear (รองเท้า) — ระยะสะสมต่อคู่ ไว้เตือนรองเท้าหมดสภาพ ──
    profile = safe_call(garmin.get_user_profile)
    profile_pk = None
    if isinstance(profile, dict):
        profile_pk = (profile.get("profileId") or profile.get("id")
                      or profile.get("userProfileId"))
    n_gear = 0
    if profile_pk:
        gear_list = safe_call(garmin.get_gear, str(profile_pk))
        if isinstance(gear_list, dict):
            gear_list = gear_list.get("gear") or []
        for g in gear_list if isinstance(gear_list, list) else []:
            if not isinstance(g, dict):
                continue
            gear_uuid = _clean_identifier(g.get("uuid"))
            if not gear_uuid:
                continue
            time.sleep(0.3)
            stats = safe_call(garmin.get_gear_stats, gear_uuid)
            stats = stats if isinstance(stats, dict) else {}
            gear_status = _clean_text(g.get("gearStatusName"), 100)
            retired = None if gear_status is None else int(gear_status.lower() == "retired")
            cur.execute(f"""INSERT INTO fact_gear
                (athlete_id, gear_uuid, gear_name, gear_type, custom_make_model,
                 date_begin, retired, total_distance_m, total_activities, fetched_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, {UTC_NOW_SQL})
                 ON CONFLICT(athlete_id, gear_uuid) DO UPDATE SET
                    gear_name = COALESCE(excluded.gear_name, fact_gear.gear_name),
                    gear_type = COALESCE(excluded.gear_type, fact_gear.gear_type),
                    custom_make_model = COALESCE(
                        excluded.custom_make_model, fact_gear.custom_make_model),
                    date_begin = COALESCE(excluded.date_begin, fact_gear.date_begin),
                    retired = COALESCE(excluded.retired, fact_gear.retired),
                    total_distance_m = COALESCE(
                        excluded.total_distance_m, fact_gear.total_distance_m),
                    total_activities = COALESCE(
                        excluded.total_activities, fact_gear.total_activities),
                    fetched_at = excluded.fetched_at""",
                (athlete_id, gear_uuid,
                 _clean_text(_first_not_none(
                     g.get("displayName"), g.get("customMakeModel")), 200),
                 _clean_text(g.get("gearTypeName"), 100),
                 _clean_text(g.get("customMakeModel"), 200),
                 _calendar_date(g.get("dateBegin")), retired,
                 _bounded_number(stats.get("totalDistance"), 0, 1_000_000_000),
                 _bounded_number(stats.get("totalActivities"), 0, 10_000_000)))
            conn.commit()
            n_gear += 1
    if n_gear:
        print(f"   ✅ Gear: {n_gear} ชิ้น")

    conn.commit()
    print("   ✅ Extras done")


# ── Sync status + sanity check ───────────────────────────────

def write_status(slug, ok, reason="ok", error=None,
                 activities=None, wellness_days=None, warnings=None,
                 endpoint_failures=None):
    """เขียนสถานะรอบนี้ลง data/sync_status/<slug>.json (เขียน tmp แล้ว rename กันไฟล์ครึ่งเดียว)."""
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "slug": slug,
        "ok": ok,
        "reason": reason,          # ok | token | network | error
        "error": error,
        "activities": activities,
        "wellness_days": wellness_days,
        "warnings": warnings or [],
        "endpoint_failures": _unique_endpoint_failures(endpoint_failures),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
    tmp = STATUS_DIR / f"{slug}.json.tmp"
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(STATUS_DIR / f"{slug}.json")


# วัน wellness ที่ว่าง "เตือนแล้วต้องทำอะไรได้" — เกิน 14 วันไปแล้วตามเก็บไม่ได้
# (นาฬิกาเก็บข้อมูลรายวันย้อนหลังได้ไม่กี่สัปดาห์ ส่วนวันที่ไม่ได้ใส่นาฬิกาก็ว่างถาวรอยู่ดี)
# ไม่มีเพดานนี้ = สายที่มองย้อนไกล (deep 45 วัน / reconcile 90 วัน) ขุดวันเดิมมาเตือนซ้ำทุกรอบ
WELLNESS_GAP_WARN_DAYS = 14
WELLNESS_GAP_DAYS_LISTED = 6      # วันที่ว่างเยอะ ๆ ไม่ต้องไล่ทั้งหมด — สรุปท้ายพอ


def sanity_check(conn, athlete_id, start_date, end_date, *,
                 include_wellness=True, include_activities=True):
    """ตรวจความสมบูรณ์ของข้อมูลช่วงที่เพิ่งดึง — คืน list ข้อความเตือน (ว่าง = ปกติ).

    หลักการ: Garmin ส่ง response แปลก ๆ มาได้ (ค่าหลักหาย/เป็นศูนย์) แล้วระบบจะเก็บเงียบ ๆ
    เช็คหลังดึงทุกรอบดีกว่ามารู้ตอนวิเคราะห์ — เตือนอย่างเดียว ไม่ลบ/ไม่แก้ข้อมูล
    """
    warns = []

    # 1) กิจกรรมที่ค่าหลักหาย/เพี้ยน — เวลารวมเป็น 0, วิ่งแต่ไม่มีระยะ/ไม่มี HR
    #    (รอบที่ไม่ได้ดึงกิจกรรมเลย เช่น fast wellness ไม่ต้องเช็ค — จะเตือนซ้ำทุก 30 นาที)
    if include_activities:
        rows = conn.execute(
            """SELECT activity_id, activity_type, start_time_local, duration_sec, distance_m, avg_hr
               FROM fact_activity
               WHERE athlete_id = ? AND deleted_at IS NULL
                 AND substr(start_time_local, 1, 10) BETWEEN ? AND ?""",
            (athlete_id, str(start_date), str(end_date))).fetchall()
        for act_id, atype, started, dur, dist, hr in rows:
            day = (started or "?")[:10]
            if not dur or dur <= 0:
                warns.append(f"กิจกรรม {day} ({atype}) เวลารวมเป็น 0/ว่าง (id {act_id})")
            elif atype == "running":
                if not dist or dist <= 0:
                    warns.append(f"วิ่ง {day} ไม่มีระยะทาง (id {act_id})")
                elif hr is None:
                    warns.append(f"วิ่ง {day} ไม่มี HR — เช็คนาฬิกา/สายวัด (id {act_id})")

    # 2) วัน wellness ที่ว่างทั้งแถว เฉพาะวันที่จบไปแล้วและยังอยู่ในหน้าต่างที่ตามเก็บทัน
    #    (ปกติ = นักกีฬายังไม่เปิดแอป Garmin ให้นาฬิกา sync ขึ้น cloud — ตามคนได้ตรงจุด)
    #    วันนี้ยังไม่จบวัน ค่าอาจยังไม่มา ไม่นับ / เก่าเกิน WELLNESS_GAP_WARN_DAYS ก็ไม่นับ
    #    เพราะเตือนแล้วทำอะไรไม่ได้ กลายเป็นแถบเหลืองค้างหน้า dashboard จนคนเลิกอ่านคำเตือน
    if include_wellness:
        thai_today = datetime.now(BANGKOK_TZ).date()
        recent_start = thai_today - timedelta(days=WELLNESS_GAP_WARN_DAYS)
        rows = conn.execute(
            """SELECT calendar_date FROM fact_daily_wellness
               WHERE athlete_id = ? AND calendar_date BETWEEN ? AND ?
                  AND calendar_date < ?
                  AND calendar_date >= ?
                  AND resting_hr IS NULL AND sleep_score IS NULL AND body_battery_high IS NULL
               ORDER BY calendar_date""",
            (athlete_id, str(start_date), str(end_date),
             thai_today.isoformat(), recent_start.isoformat())).fetchall()
        if rows:
            days = ", ".join(r[0] for r in rows[:WELLNESS_GAP_DAYS_LISTED])
            if len(rows) > WELLNESS_GAP_DAYS_LISTED:
                days += f" และอีก {len(rows) - WELLNESS_GAP_DAYS_LISTED} วัน"
            warns.append(f"wellness ว่างทั้งวัน: {days} — นักกีฬาอาจยังไม่ได้ sync นาฬิกาเข้าแอป")

        # A partial post-wakeup snapshot is more subtle than an empty row: day
        # metrics have arrived, but at least two of the nightly bundle have not.
        # This caught Tong 8 Aug immediately whereas the old all-empty check did not.
        partial_rows = conn.execute(
            """SELECT calendar_date, sleep_score, hrv_last_night,
                      avg_sleep_respiration
                 FROM fact_daily_wellness
                WHERE athlete_id = ? AND calendar_date BETWEEN ? AND ?
                  AND calendar_date < ?
                  AND calendar_date >= ?
                  AND (resting_hr IS NOT NULL OR stress_avg IS NOT NULL
                       OR steps IS NOT NULL OR body_battery_high IS NOT NULL
                       OR avg_waking_respiration IS NOT NULL)
                  AND NOT (resting_hr IS NULL AND sleep_score IS NULL
                           AND body_battery_high IS NULL)
                  AND ((sleep_score IS NULL) + (hrv_last_night IS NULL)
                       + (avg_sleep_respiration IS NULL)) >= 2
                ORDER BY calendar_date""",
            (athlete_id, str(start_date), str(end_date),
             thai_today.isoformat(), recent_start.isoformat()),
        ).fetchall()
        if partial_rows:
            details = []
            for day, sleep_score, hrv_last_night, sleep_resp in partial_rows[
                    :WELLNESS_GAP_DAYS_LISTED]:
                missing = []
                if sleep_score is None:
                    missing.append("Sleep")
                if hrv_last_night is None:
                    missing.append("HRV")
                if sleep_resp is None:
                    missing.append("sleep respiration")
                details.append(f"{day} ({'/'.join(missing)})")
            if len(partial_rows) > WELLNESS_GAP_DAYS_LISTED:
                details.append(f"อีก {len(partial_rows) - WELLNESS_GAP_DAYS_LISTED} วัน")
            warns.append(
                "wellness เป็น partial snapshot: " + ", ".join(details)
                + " — เปิด Garmin Connect/sync นาฬิกาแล้วให้ fast sync ซ่อมย้อนหลัง")

    return warns


# ── Main ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Backfill Garmin data")
    parser.add_argument("--athlete", default="wayuo", help="Athlete slug (default: wayuo)")
    parser.add_argument("--days", type=int, default=90, help="Days to backfill (default: 90)")
    parser.add_argument("--skip-activities", action="store_true",
                        help="ข้ามการดึงกิจกรรม+splits (ใช้ตอน re-backfill เฉพาะ wellness/extras "
                             "ของช่วงที่มีกิจกรรมครบแล้ว — กันยิง API ซ้ำของเดิม เสี่ยงโดน rate limit)")
    parser.add_argument("--reconcile", action="store_true",
                        help="โหมดเช็คกิจกรรมถูกลบฝั่ง Garmin (ดึงแค่รายชื่อ ไม่ดึงรายละเอียด/ไม่ insert) "
                             "→ mark deleted_at ตัวที่หายไป. ใช้รันรายสัปดาห์ (เช่น --days 90 --reconcile)")
    parser.add_argument("--activities-only", action="store_true",
                        help="fast sync: ดึง activity summary + splits เฉพาะกิจกรรมที่มีระยะและ"
                             "ยังไม่มี splits; ไม่ดึง detail/weather/wellness/extras หรือ reconcile")
    parser.add_argument("--skip-wellness", action="store_true",
                        help="ดึงกิจกรรม+splits+detail/weather และ reconcile ตามปกติ แต่ข้าม "
                             "wellness/extras ทั้งช่วง — ใช้ backfill กิจกรรมย้อนลึกหลายปี "
                             "โดยไม่ยิง 9 endpoint/วันของ wellness ที่ไม่ต้องการทิ้งเปล่า")
    parser.add_argument("--wellness-fast", action="store_true",
                        help="fast wellness: ดึงเฉพาะค่าที่ขยับระหว่างวัน (body battery/RHR/stress/"
                             "steps/HRV/นอน/readiness) แล้วอัปเดตทับเป็นรายคอลัมน์ — ไม่ดึงกิจกรรม/"
                             "extras และไม่ล้างค่าที่ full sync เก็บไว้")
    args = parser.parse_args()
    if args.days < 0:
        parser.error("--days ต้องไม่น้อยกว่า 0")
    _exclusive = [name for name, on in (
        ("--activities-only", args.activities_only),
        ("--wellness-fast", args.wellness_fast),
        ("--skip-activities", args.skip_activities),
        ("--skip-wellness", args.skip_wellness),
        ("--reconcile", args.reconcile),
    ) if on]
    if len(_exclusive) > 1:
        parser.error(f"ใช้ร่วมกันไม่ได้: {', '.join(_exclusive)}")

    # Set up token path
    token_dir = PROJECT_ROOT / "tokens" / args.athlete
    if not token_dir.exists():
        print(f"❌ Token directory not found: {token_dir}")
        print("   Run 01_generate_token.py first.")
        write_status(args.athlete, ok=False, reason="token", error="token directory not found")
        sys.exit(2)

    # Login with saved token
    print(f"🔐 Loading token for '{args.athlete}'...")
    from garminconnect import Garmin
    garmin = Garmin()
    try:
        garmin.login(str(token_dir))
    except Exception as e:
        if classify_login_error(e) == "token":
            print(f"❌ TOKEN ใช้ไม่ได้ (หมดอายุ/ถูก revoke): {e}")
            print(f"   → รัน garmin\\เพิ่มนักกีฬา.bat เพื่อขอ token ใหม่ของ '{args.athlete}'")
            write_status(args.athlete, ok=False, reason="token", error=str(e))
            sys.exit(2)
        print(f"❌ Login ล้มเหลวจากปัญหาเน็ต/เซิร์ฟเวอร์: {e}")
        print("   ไม่ใช่ปัญหา token — รอบถัดไปจะลองใหม่เอง")
        print("   (ถ้าขึ้นแบบนี้ติดกันหลายวัน ค่อยลองรัน เพิ่มนักกีฬา.bat)")
        write_status(args.athlete, ok=False, reason="network", error=str(e))
        sys.exit(1)

    full_name = garmin.get_full_name()
    print(f"✅ Logged in as: {full_name}")

    # Connect to database — busy_timeout 30 วิ + WAL (idempotent) กัน "database is locked"
    # ตอน dashboard เปิดค้างอ่านพร้อมกัน (เจอจริง 22 ก.ค. 69 รอบ 21:43 ล้มทั้ง 3 คน)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    athlete_id = get_athlete_id(conn, args.athlete)

    # Update garmin_full_name
    conn.execute(
        "UPDATE dim_athlete SET garmin_full_name = ? WHERE athlete_id = ?",
        (full_name, athlete_id),
    )
    conn.commit()

    # Date range
    # Business dates are Thai calendar days regardless of the Windows/Task
    # Scheduler host timezone.  Thailand has no daylight-saving transition.
    end_date = datetime.now(BANGKOK_TZ).date()
    start_date = end_date - timedelta(days=args.days)

    print(f"\n🗓️  Backfill range: {start_date} → {end_date} ({args.days} days)")
    print(f"👤 Athlete: {args.athlete} (id={athlete_id})")

    # โหมด reconcile อย่างเดียว (ไม่ดึงกิจกรรม/wellness ใหม่) — สำหรับ task รายสัปดาห์
    if args.reconcile:
        try:
            result = reconcile_only(garmin, conn, athlete_id, start_date, end_date)
        except RequiredEndpointError as exc:
            conn.close()
            print(f"   ❌ Reconcile ใช้ response นี้ไม่ได้: {exc}")
            write_status(
                args.athlete, ok=False, reason=exc.status_reason, error=str(exc)
            )
            sys.exit(1)
        conn.close()
        marked, restored, imported = result
        write_status(args.athlete, ok=True, reason="ok",
                     activities=len(imported),
                     warnings=([f"reconcile: mark กิจกรรมถูกลบ {len(marked)} รายการ"] if marked else []))
        print("\n" + "=" * 50)
        print(f"🎉 Reconcile complete! imported +{len(imported)} | "
              f"deleted +{len(marked)} | restored +{len(restored)}")
        print("=" * 50)
        return

    # Fetch data.  A mandatory collection which is unavailable or malformed is
    # a failed sync, never a successful zero-row round.
    wellness_endpoint_failures = []
    wellness_terminal_errors = []
    try:
        if args.skip_activities or args.wellness_fast:
            _why = "--skip-activities" if args.skip_activities else "--wellness-fast"
            print(f"\n📊 (ข้ามการดึงกิจกรรม — {_why})")
            activity_count = 0
        else:
            # reconcile ที่หน้าต่างกว้างหลายปีคือกับดัก ไม่ใช่การกู้คืน (2 ก.ย. 69):
            # `present_ids` ถูกเก็บจาก list ครั้งเดียวตอนเริ่ม แล้วลูปเดินต่ออีกเป็นชั่วโมง
            # (แดน 2,738 รายการ × sleep 0.8 วิ/รายการ) — กิจกรรมที่ fast sync
            # ทุก 15 นาทีใส่เข้าระหว่างทางจึงไม่อยู่ใน `present_ids` แล้วโดน mark ว่าถูกลบ
            # สาย `--reconcile` รายสัปดาห์ (90 วัน) คุมการลบอยู่แล้ว ตัดกิ่งนี้ทิ้งจึงไม่เสียอะไร
            activity_count = fetch_and_insert_activities(
                garmin, conn, athlete_id, start_date, end_date,
                fast=args.activities_only,
                reconcile=not args.skip_wellness,
            )

        if args.activities_only:
            wellness_count = None
            print("\n⚡ Fast sync: ข้าม wellness/extras (full sync จะเติมตามรอบเดิม)")
        elif args.skip_wellness:
            wellness_count = None
            print("\n⚡ ข้าม wellness/extras (--skip-wellness) — สั่ง --skip-activities อีกรอบเพื่อเติมช่วงที่ต้องการ")
        elif args.wellness_fast:
            wellness_count = fetch_and_update_wellness_fast(
                garmin, conn, athlete_id, start_date, end_date,
                endpoint_failures=wellness_endpoint_failures,
                terminal_errors=wellness_terminal_errors,
            )
            # The scheduled lane uses --days 0.  A manual wider fast range already
            # fetched yesterday in the loop, so do not duplicate those calls.
            if start_date == end_date:
                wellness_count += fetch_and_repair_previous_day_wellness(
                    garmin, conn, athlete_id, end_date - timedelta(days=1),
                    endpoint_failures=wellness_endpoint_failures,
                    terminal_errors=wellness_terminal_errors,
                )
        else:
            wellness_count = fetch_and_insert_wellness(
                garmin, conn, athlete_id, start_date, end_date,
                endpoint_failures=wellness_endpoint_failures,
                terminal_errors=wellness_terminal_errors,
            )
            fetch_and_insert_extras(garmin, conn, athlete_id, start_date, end_date)
        if wellness_terminal_errors:
            raise CoreWellnessUnavailableError(
                failure
                for error in wellness_terminal_errors
                for failure in error.failures
            )
    except RequiredEndpointError as exc:
        conn.close()
        print(f"\n❌ Sync ใช้ response จาก Garmin ไม่ได้: {exc}")
        write_status(
            args.athlete,
            ok=False,
            reason=exc.status_reason,
            error=str(exc),
            endpoint_failures=(
                wellness_endpoint_failures or getattr(exc, "failures", None)
            ),
        )
        sys.exit(2 if exc.status_reason == "token" else 1)

    sanity_start_date = (
        min(start_date, end_date - timedelta(days=1))
        if args.wellness_fast else start_date
    )
    warnings = sanity_check(
        conn, athlete_id, sanity_start_date, end_date,
        include_wellness=not args.activities_only,
        include_activities=not args.wellness_fast,
    )
    unique_endpoint_failures = _unique_endpoint_failures(
        wellness_endpoint_failures
    )
    if unique_endpoint_failures:
        summary = ", ".join(
            f"{item['endpoint']}:{item['reason']}"
            for item in unique_endpoint_failures
        )
        warnings.append(f"wellness endpoint degraded: {summary}")
    if warnings:
        print("\n⚠️  Sanity check พบจุดน่าสงสัย:")
        for w in warnings:
            print(f"   - {w}")

    conn.close()
    write_status(args.athlete, ok=True, reason="ok",
                 activities=activity_count, wellness_days=wellness_count,
                 warnings=warnings,
                 endpoint_failures=unique_endpoint_failures)

    print("\n" + "=" * 50)
    print("🎉 Backfill complete!")
    print(f"   Activities: {activity_count}")
    print(f"   Wellness days: {wellness_count}")
    print(f"   Database: {DB_PATH}")
    print("=" * 50)


if __name__ == "__main__":
    main()
