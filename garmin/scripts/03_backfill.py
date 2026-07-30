#!/usr/bin/env python3
"""Backfill 90 days of Garmin data into SQLite.

Usage:
    python scripts/03_backfill.py [--athlete wayuo] [--days 90]

Fetches activities + daily wellness data and inserts into garmin.db.
Requires token to already exist in tokens/<athlete>/.
"""

import argparse
import json
import os
import socket
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "garmin.db"
# สถานะรายคนของรอบ sync ล่าสุด — fetch_all.py อ่านไปรวมเป็น data/sync_status.json
# เพื่อให้ toast/dashboard บอกได้ว่าใครพังเพราะอะไร (token/เน็ต) และข้อมูลมีจุดน่าสงสัยไหม
STATUS_DIR = PROJECT_ROOT / "data" / "sync_status"

# กันการเชื่อมต่อค้างไม่รู้จบ: เคยเจอ SSL recv ค้างจน Task แขวนข้ามวัน (21 ก.ค. 69)
# requests/urllib3 ไม่ตั้ง timeout เอง → ตั้ง default ให้ทุก socket แทน
# อ่าน/เชื่อมต่อนานเกิน 30 วิ = โยน timeout ให้ safe_call จับแล้ว retry (ไม่แขวนยาว)
socket.setdefaulttimeout(30)


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


def safe_call(api_method, *args, **kwargs):
    """Call Garmin API with retry on 429 and transient network timeouts."""
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
                wait = 60 * (attempt + 1)
                print(f"   ⚠️  Rate limited! Waiting {wait}s before retry...")
                time.sleep(wait)
            elif "404" in error_str or "204" in error_str:
                return None  # No data for this endpoint/date
            elif is_timeout and attempt < max_retries - 1:
                print(f"   ⚠️  เน็ตค้าง/timeout ({e}) — ลองใหม่ครั้งที่ {attempt + 2}...")
                time.sleep(5 * (attempt + 1))
            else:
                print(f"   ⚠️  API error: {e}")
                return None
    print("   ❌ Max retries exceeded.")
    return None


# ── Activity Fetching ────────────────────────────────────────

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
    garmin, conn, athlete_id, start_date, end_date, *, fast=False
):
    """Fetch activities by date range and insert into fact_activity (ละเอียด: running dynamics,
    HR time-in-zone, weather, stamina/impact load สำหรับกิจกรรมวิ่ง).

    fast=True ใช้กับ polling ถี่: ดึง activity summary เพียง endpoint เดียว ไม่ดึง
    detail/weather/splits และไม่ reconcile. ถ้า activity มีอยู่แล้ว จะเก็บ enrichment
    จาก full sync เดิมไว้ ไม่เขียน NULL ทับ."""
    print(f"\n📊 Fetching activities from {start_date} to {end_date}...")

    activities = safe_call(
        garmin.get_activities_by_date,
        start_date.isoformat(),
        end_date.isoformat(),
    )
    # แยก None (ดึงไม่สำเร็จ) ออกจาก [] (ไม่มีกิจกรรมจริง) — สำคัญมากสำหรับ reconcile:
    # ถ้าดึงพลาดแล้วเข้าใจว่า "ไม่มีกิจกรรม" จะ mark ทุกกิจกรรมในช่วงว่าถูกลบ (ผิด)
    if activities is None:
        print("   ⚠️  ดึงรายการกิจกรรมไม่สำเร็จ — ข้ามรอบนี้ (ไม่แตะข้อมูลเดิม/ไม่ reconcile)")
        return 0

    cur = conn.cursor()
    count = 0
    present_ids = set()   # activityId ทั้งหมดที่ Garmin คืนช่วงนี้ — ใช้ reconcile ตอนจบ

    for act in activities:
        activity_id = act.get("activityId")
        if not activity_id:
            continue
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
        if fast:
            # Garmin อาจส่ง summary บาง field เป็น NULL ชั่วคราวระหว่างประมวลผล.
            # COALESCE ป้องกัน fast polling ล้างค่าที่ full sync เคยเติมไว้
            # (รวม running dynamics, HR zones, load และ weather).
            updates = ", ".join(
                f"{column}=COALESCE(excluded.{column}, fact_activity.{column})"
                for column in ACTIVITY_WRITE_COLUMNS
                if column not in ("activity_id", "athlete_id")
            )
            sql = (
                f"INSERT INTO fact_activity ({columns_sql}) VALUES ({placeholders}) "
                f"ON CONFLICT(activity_id) DO UPDATE SET athlete_id=excluded.athlete_id, "
                f"{updates}, deleted_at=NULL, fetched_at=datetime('now')"
            )
        else:
            sql = (
                f"INSERT OR REPLACE INTO fact_activity ({columns_sql}) "
                f"VALUES ({placeholders})"
            )
        cur.execute(sql, values)
        # ปล่อย SQLite write lock ก่อนยิง endpoint ถัดไป เพื่อให้ subprocess
        # ของนักกีฬาคนอื่นเขียนแทรกได้เมื่อ fetch_all รันแบบขนาน
        conn.commit()
        count += 1

        # ดึง splits เฉพาะกิจกรรมที่มีระยะทาง (วิ่ง/เดิน) — cross-training ไม่มี split ที่มีความหมาย
        if has_dist and not fast:
            time.sleep(0.5)
            fetch_and_insert_splits(garmin, conn, activity_id)
            conn.commit()

    conn.commit()
    print(f"   ✅ Inserted {count} activities")
    # reconcile ช่วงที่เพิ่งดึง (ฟรี — ใช้รายการที่ดึงมาแล้ว): กิจกรรมใน DB ช่วงนี้ที่ไม่อยู่
    # ในรายการจริงของ Garmin = ถูกลบฝั่งแอป → mark deleted_at (daily 3 วันจับการลบล่าสุดได้เอง)
    if not fast:
        reconcile_activities(conn, athlete_id, start_date, end_date, present_ids)
    return count


def fetch_and_insert_splits(garmin, conn, activity_id):
    """Fetch per-km splits for a single activity."""
    splits_data = safe_call(garmin.get_activity_splits, activity_id)
    if not splits_data:
        return

    # The splits structure varies — look for lapDTOs or splitSummaries
    laps = []
    if isinstance(splits_data, dict):
        laps = splits_data.get("lapDTOs", [])
        if not laps:
            laps = splits_data.get("splitSummaries", [])
    elif isinstance(splits_data, list):
        laps = splits_data

    cur = conn.cursor()
    for i, lap in enumerate(laps, 1):
        if not isinstance(lap, dict):
            continue

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


# ── Reconciliation (กิจกรรมถูกลบฝั่ง Garmin) ──────────────────

def reconcile_activities(conn, athlete_id, start_date, end_date, present_ids):
    """เทียบกิจกรรมใน DB ช่วง [start,end] กับ activityId จริงจาก Garmin (present_ids):
      - อยู่ DB แต่ไม่อยู่ Garmin = ถูกลบฝั่งแอป → set deleted_at (soft delete ไม่ลบแถวจริง)
      - เคยมาร์ค deleted แต่กลับมาอยู่ Garmin = กู้คืน → clear deleted_at (self-healing)

    ⚠️ เรียกเฉพาะเมื่อ present_ids มาจากการดึงที่ "สำเร็จ" เท่านั้น — ถ้าดึงพลาดแล้วส่ง set ว่าง
    เข้ามาจะ mark กิจกรรมที่ยังอยู่จริงทั้งหมดว่าถูกลบ (ผู้เรียกต้องกันกรณี None ก่อน)"""
    cur = conn.cursor()
    db_rows = cur.execute(
        """SELECT activity_id, deleted_at FROM fact_activity
           WHERE athlete_id = ? AND date(start_time_local) BETWEEN ? AND ?""",
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
    """โหมด --reconcile: ดึงแค่ "รายชื่อ activityId" ช่วงกว้าง (ไม่ดึงรายละเอียด/ไม่ insert)
    แล้วมาร์คกิจกรรมที่ถูกลบ — เบา API พอสำหรับรันรายสัปดาห์ช่วง 90 วัน.
    คืน (marked, restored) หรือ None ถ้าดึงรายการไม่สำเร็จ (ห้าม reconcile)."""
    print(f"\n🔍 Reconcile (เช็คกิจกรรมถูกลบ) {start_date} → {end_date}...")
    activities = safe_call(garmin.get_activities_by_date,
                           start_date.isoformat(), end_date.isoformat())
    if activities is None:
        print("   ⚠️  ดึงรายการจาก Garmin ไม่สำเร็จ — ข้าม reconcile (กัน mark ผิด)")
        return None
    present_ids = {a.get("activityId") for a in activities if a.get("activityId")}
    marked, restored = reconcile_activities(conn, athlete_id, start_date, end_date, present_ids)
    print(f"   ✅ Reconcile เสร็จ — Garmin มี {len(present_ids)} กิจกรรม | "
          f"mark deleted {len(marked)} | กู้คืน {len(restored)}")
    return marked, restored


# ── Daily Wellness Fetching ──────────────────────────────────

def fetch_and_insert_wellness(garmin, conn, athlete_id, start_date, end_date):
    """Fetch daily wellness metrics day-by-day."""
    print(f"\n🩺 Fetching daily wellness from {start_date} to {end_date}...")

    cur = conn.cursor()
    current = start_date
    count = 0
    total_days = (end_date - start_date).days + 1

    while current <= end_date:
        date_str = current.isoformat()
        day_num = (current - start_date).days + 1
        print(f"   Day {day_num}/{total_days}: {date_str}", end="", flush=True)

        # ── Stats (steps, resting HR, stress) ──
        stats = safe_call(garmin.get_stats, date_str)
        time.sleep(0.3)

        # ── HRV ──
        hrv = safe_call(garmin.get_hrv_data, date_str)
        time.sleep(0.3)

        # ── Sleep ──
        sleep = safe_call(garmin.get_sleep_data, date_str)
        time.sleep(0.3)

        # ── Respiration (Body Battery ดึงจาก get_stats แล้ว ไม่ต้องเรียกแยก) ──
        respiration = safe_call(garmin.get_respiration_data, date_str)
        time.sleep(0.3)

        # ── Training Readiness ──
        readiness = safe_call(garmin.get_training_readiness, date_str)
        time.sleep(0.3)

        # ── Training Status ──
        training_status = safe_call(garmin.get_training_status, date_str)
        time.sleep(0.3)

        # ── Max metrics (VO2max trend + fitness age — เทรนด์รายวัน ไม่ใช่แค่วันเทส) ──
        max_metrics = safe_call(garmin.get_max_metrics, date_str)
        time.sleep(0.3)

        # ── Endurance score (device-dependent — นาฬิการุ่นเก่าได้ None) ──
        endurance = safe_call(garmin.get_endurance_score, date_str)
        time.sleep(0.3)

        # ── Hill score (device-dependent) ──
        hill = safe_call(garmin.get_hill_score, date_str)
        time.sleep(0.3)

        # Parse stats (RHR, steps, stress, kcal, floors, body battery ละเอียด, respiration ตื่น)
        def _s(*keys):
            return safe_get(stats, *keys) if stats else None
        resting_hr = _s("restingHeartRate")
        steps = _s("totalSteps")
        stress_avg = _s("averageStressLevel")
        max_stress = _s("maxStressLevel")
        steps_goal = _s("dailyStepGoal")
        floors_ascended = _s("floorsAscended")
        active_kcal = _s("activeKilocalories")
        bmr_kcal = _s("bmrKilocalories")
        active_seconds = _s("activeSeconds")
        waking_resp = _s("avgWakingRespirationValue")
        bb_high = _s("bodyBatteryHighestValue")
        bb_low = _s("bodyBatteryLowestValue")
        bb_at_wake = _s("bodyBatteryAtWakeTime")
        bb_charged = _s("bodyBatteryChargedValue")
        bb_drained = _s("bodyBatteryDrainedValue")
        bb_during_sleep = _s("bodyBatteryDuringSleep")
        bb_most_recent = _s("bodyBatteryMostRecentValue")

        # Parse HRV
        hrv_weekly = None
        hrv_last_night = None
        hrv_status = None
        if hrv and isinstance(hrv, dict):
            hrv_summary = safe_get(hrv, "hrvSummary")
            if hrv_summary:
                hrv_weekly = safe_get(hrv_summary, "weeklyAvg")
                hrv_last_night = safe_get(hrv_summary, "lastNightAvg")
                hrv_status = safe_get(hrv_summary, "status")
            # Alternative structure
            if hrv_weekly is None:
                hrv_weekly = safe_get(hrv, "weeklyAvg")
                hrv_last_night = safe_get(hrv, "lastNightAvg")
                hrv_status = safe_get(hrv, "status")

        # Parse sleep
        sleep_score = None
        sleep_dur = None
        deep_sleep = None
        light_sleep = None
        rem_sleep = None
        awake_dur = None
        if sleep and isinstance(sleep, dict):
            daily_sleep = safe_get(sleep, "dailySleepDTO")
            if daily_sleep:
                sleep_dur = safe_get(daily_sleep, "sleepTimeSeconds")
                deep_sleep = safe_get(daily_sleep, "deepSleepSeconds")
                light_sleep = safe_get(daily_sleep, "lightSleepSeconds")
                rem_sleep = safe_get(daily_sleep, "remSleepSeconds")
                awake_dur = safe_get(daily_sleep, "awakeSleepSeconds")
                # sleepScores lives INSIDE dailySleepDTO, not at the top level
                sleep_score = safe_get(daily_sleep, "sleepScores", "overall", "value")
            # Fallback for older payload shapes
            if sleep_score is None:
                sleep_score = safe_get(sleep, "overallScore") or safe_get(sleep, "sleepScores", "overall", "value")

        # Parse respiration (waking จาก stats ไว้แล้ว — เติม sleep/high/low)
        sleep_resp = high_resp = low_resp = None
        if isinstance(respiration, dict):
            sleep_resp = respiration.get("avgSleepRespirationValue")
            high_resp = respiration.get("highestRespirationValue")
            low_resp = respiration.get("lowestRespirationValue")
            if waking_resp is None:
                waking_resp = respiration.get("avgWakingRespirationValue")

        # Parse training readiness + ปัจจัยละเอียด (score/level/acute load/ACWR ของ Garmin เอง/
        # HRV factor/recovery time/stress history) — API คืน LIST อาจว่างถ้านาฬิกาไม่ให้
        readiness_score = readiness_level = readiness_feedback = None
        acute_load = acwr_pct = hrv_factor = recovery_time = stress_hist = None
        if isinstance(readiness, list):
            readiness_obj = readiness[0] if readiness else None
        elif isinstance(readiness, dict):
            readiness_obj = readiness
        else:
            readiness_obj = None
        if isinstance(readiness_obj, dict):
            readiness_score = readiness_obj.get("score") or readiness_obj.get("trainingReadinessScore")
            readiness_level = readiness_obj.get("level")
            readiness_feedback = readiness_obj.get("feedbackShort")
            acute_load = readiness_obj.get("acuteLoad")
            acwr_pct = readiness_obj.get("acwrFactorPercent")
            hrv_factor = readiness_obj.get("hrvFactorPercent")
            recovery_time = readiness_obj.get("recoveryTime")
            stress_hist = readiness_obj.get("stressHistoryFactorPercent")

        # Parse training status (nested per-device under
        # mostRecentTrainingStatus.latestTrainingStatusData.<deviceId>)
        training_status_val = None
        if isinstance(training_status, dict):
            latest = safe_get(training_status, "mostRecentTrainingStatus", "latestTrainingStatusData")
            if isinstance(latest, dict):
                for _device_data in latest.values():
                    if isinstance(_device_data, dict):
                        training_status_val = (
                            _device_data.get("trainingStatusFeedbackPhrase")
                            or _device_data.get("trainingStatus")
                        )
                        if training_status_val is not None:
                            break
            # Fallback to older top-level shapes
            if training_status_val is None:
                training_status_val = (
                    safe_get(training_status, "trainingStatus")
                    or safe_get(training_status, "currentDayTrainingStatus")
                )

        # Parse max metrics (payload เป็น list ต่อ device — เอาตัวแรกที่มีค่า generic)
        vo2max_trend = fitness_age = None
        mm_items = max_metrics if isinstance(max_metrics, list) else [max_metrics]
        for item in mm_items:
            if not isinstance(item, dict):
                continue
            generic = item.get("generic")
            if isinstance(generic, dict):
                vo2max_trend = generic.get("vo2MaxPreciseValue") or generic.get("vo2MaxValue")
                if fitness_age is None:
                    fitness_age = generic.get("fitnessAge")
                if vo2max_trend is not None:
                    break

        # Parse endurance score
        endurance_score = None
        if isinstance(endurance, dict):
            endurance_score = endurance.get("overallScore")

        # Parse hill score
        hill_overall = hill_strength = hill_endurance = None
        if isinstance(hill, dict):
            hill_overall = hill.get("overallScore")
            hill_strength = hill.get("strengthScore")
            hill_endurance = hill.get("enduranceScore")

        cur.execute("""
            INSERT INTO fact_daily_wellness (
                athlete_id, calendar_date, resting_hr,
                hrv_weekly_avg, hrv_last_night, hrv_status,
                sleep_score, sleep_duration_sec,
                deep_sleep_sec, light_sleep_sec, rem_sleep_sec, awake_sec,
                body_battery_high, body_battery_low,
                bb_at_wake, bb_charged, bb_drained, bb_during_sleep, bb_most_recent,
                stress_avg, max_stress, steps, steps_goal, floors_ascended,
                active_kilocalories, bmr_kilocalories, active_seconds,
                avg_waking_respiration, avg_sleep_respiration, highest_respiration, lowest_respiration,
                training_readiness, readiness_level, readiness_feedback,
                acute_load, acwr_percent, hrv_factor_pct, recovery_time_hrs, stress_history_pct,
                training_status,
                vo2max_trend, fitness_age, endurance_score,
                hill_score_overall, hill_score_strength, hill_score_endurance
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            athlete_id, date_str, resting_hr,
            hrv_weekly, hrv_last_night, hrv_status,
            sleep_score, sleep_dur,
            deep_sleep, light_sleep, rem_sleep, awake_dur,
            bb_high, bb_low,
            bb_at_wake, bb_charged, bb_drained, bb_during_sleep, bb_most_recent,
            stress_avg, max_stress, steps, steps_goal, floors_ascended,
            active_kcal, bmr_kcal, active_seconds,
            waking_resp, sleep_resp, high_resp, low_resp,
            readiness_score, readiness_level, readiness_feedback,
            acute_load, acwr_pct, hrv_factor, recovery_time, stress_hist,
            training_status_val,
            vo2max_trend, fitness_age, endurance_score,
            hill_overall, hill_strength, hill_endurance,
        ))
        # ไม่ถือ write transaction ค้างระหว่าง network calls ของวันถัดไป
        conn.commit()
        count += 1
        print(" ✓")

        # Longer pause between days to avoid rate limit
        time.sleep(1.5)
        current += timedelta(days=1)

    conn.commit()
    print(f"   ✅ Inserted {count} wellness records")
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


def fetch_and_insert_extras(garmin, conn, athlete_id, start_date, end_date):
    """ข้อมูลเสริมที่ API ให้แบบ range/snapshot (ไม่ต้องวนรายวัน — ประหยัด request):
    lactate threshold ล่าสุดจากนาฬิกา, race predictions รายวันทั้งช่วง,
    body composition (น้ำหนัก/BMI/ไขมัน), personal records, gear (รองเท้า)"""
    print("\n🎯 Fetching extras (LT / race predictions / body comp / PR / gear)...")
    cur = conn.cursor()

    # ── Lactate Threshold ล่าสุด (Garmin ประเมินจาก HR+pace ระหว่างวิ่ง) ──
    lt = safe_call(garmin.get_lactate_threshold, latest=True)
    if isinstance(lt, dict):
        shr = lt.get("speed_and_heart_rate") or {}
        lt_date = shr.get("calendarDate")
        if isinstance(lt_date, str):
            lt_date = lt_date[:10]  # API คืน timestamp เต็ม — ตัดเหลือวันที่ให้ตรงคีย์ wellness
        lt_hr = shr.get("heartRate")
        lt_speed = shr.get("speed")
        # API คืน speed สเกล 0.1 m/s (เจอจริง: พี่เก้าได้ 0.3306 = 3.306 m/s) —
        # LT ของนักวิ่งอยู่ช่วง 2.5-6 m/s ถ้าค่า < 1 แปลว่ามาแบบสเกลย่อ คูณ 10 ก่อน
        if isinstance(lt_speed, (int, float)) and 0 < lt_speed < 1.0:
            lt_speed *= 10
        lt_pace = round(1000.0 / lt_speed / 60.0, 2) if lt_speed else None
        if lt_date and (lt_hr is not None or lt_pace is not None):
            # สร้าง row โครงถ้ายังไม่มี แล้ว UPDATE เฉพาะคอลัมน์ LT
            # (ห้าม INSERT OR REPLACE — จะล้างคอลัมน์ wellness อื่นของวันนั้นทิ้ง)
            cur.execute(
                "INSERT OR IGNORE INTO fact_daily_wellness (athlete_id, calendar_date) VALUES (?, ?)",
                (athlete_id, lt_date))
            cur.execute("""UPDATE fact_daily_wellness
                           SET lactate_threshold_hr = ?, lactate_threshold_pace_min_km = ?
                           WHERE athlete_id = ? AND calendar_date = ?""",
                        (lt_hr, lt_pace, athlete_id, lt_date))
            print(f"   ✅ LT ล่าสุด ({lt_date}): HR {lt_hr}, pace {lt_pace} นาที/กม.")
    conn.commit()
    time.sleep(0.3)

    # ── Race predictions รายวันทั้งช่วง (call เดียวครอบทุกวัน) ──
    preds = safe_call(garmin.get_race_predictions,
                      start_date.isoformat(), end_date.isoformat(), "daily")
    n_pred = 0
    for p in preds if isinstance(preds, list) else []:
        if not isinstance(p, dict) or not p.get("calendarDate"):
            continue
        times = (p.get("time5K"), p.get("time10K"), p.get("timeHalfMarathon"), p.get("timeMarathon"))
        if not any(t is not None for t in times):
            continue  # วันปัจจุบัน Garmin มักคืนแถวว่าง (ยังไม่คำนวณ) — ไม่เก็บแถวขยะ
        cur.execute("""INSERT OR REPLACE INTO fact_race_prediction
            (athlete_id, calendar_date, time_5k_sec, time_10k_sec, time_half_sec, time_full_sec)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (athlete_id, p["calendarDate"], *times))
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
            cal = entry.get("calendarDate")
            if not cal and isinstance(entry.get("date"), (int, float)):
                cal = datetime.fromtimestamp(entry["date"] / 1000).date().isoformat()
            if not cal:
                continue
            weight_g = entry.get("weight")  # Garmin คืนเป็นกรัม
            cur.execute("""INSERT OR REPLACE INTO fact_body_composition
                (athlete_id, calendar_date, weight_kg, bmi, body_fat_pct)
                VALUES (?, ?, ?, ?, ?)""",
                (athlete_id, cal,
                 round(weight_g / 1000.0, 2) if isinstance(weight_g, (int, float)) else None,
                 entry.get("bmi"), entry.get("bodyFat")))
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
        if not isinstance(pr, dict) or pr.get("typeId") is None:
            continue
        achieved = pr.get("prStartTimeGmtFormatted") or pr.get("prStartTimeGmt")
        if isinstance(achieved, (int, float)):
            achieved = datetime.fromtimestamp(achieved / 1000).date().isoformat()
        cur.execute("""INSERT OR REPLACE INTO fact_personal_record
            (athlete_id, record_type_id, record_label, value, activity_id, achieved_date)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (athlete_id, pr["typeId"], PR_LABELS.get(pr["typeId"]), pr.get("value"),
             pr.get("activityId"), achieved))
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
            if not isinstance(g, dict) or not g.get("uuid"):
                continue
            time.sleep(0.3)
            stats = safe_call(garmin.get_gear_stats, g["uuid"]) or {}
            retired = 1 if (g.get("gearStatusName") or "").lower() == "retired" else 0
            cur.execute("""INSERT OR REPLACE INTO fact_gear
                (athlete_id, gear_uuid, gear_name, gear_type, custom_make_model,
                 date_begin, retired, total_distance_m, total_activities)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (athlete_id, g["uuid"], g.get("displayName") or g.get("customMakeModel"),
                 g.get("gearTypeName"), g.get("customMakeModel"), g.get("dateBegin"),
                 retired, stats.get("totalDistance"), stats.get("totalActivities")))
            conn.commit()
            n_gear += 1
    if n_gear:
        print(f"   ✅ Gear: {n_gear} ชิ้น")

    conn.commit()
    print("   ✅ Extras done")


# ── Sync status + sanity check ───────────────────────────────

def write_status(slug, ok, reason="ok", error=None,
                 activities=None, wellness_days=None, warnings=None):
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
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
    tmp = STATUS_DIR / f"{slug}.json.tmp"
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(STATUS_DIR / f"{slug}.json")


def sanity_check(conn, athlete_id, start_date, end_date, *, include_wellness=True):
    """ตรวจความสมบูรณ์ของข้อมูลช่วงที่เพิ่งดึง — คืน list ข้อความเตือน (ว่าง = ปกติ).

    หลักการ: Garmin ส่ง response แปลก ๆ มาได้ (ค่าหลักหาย/เป็นศูนย์) แล้วระบบจะเก็บเงียบ ๆ
    เช็คหลังดึงทุกรอบดีกว่ามารู้ตอนวิเคราะห์ — เตือนอย่างเดียว ไม่ลบ/ไม่แก้ข้อมูล
    """
    warns = []

    # 1) กิจกรรมที่ค่าหลักหาย/เพี้ยน — เวลารวมเป็น 0, วิ่งแต่ไม่มีระยะ/ไม่มี HR
    rows = conn.execute(
        """SELECT activity_id, activity_type, start_time_local, duration_sec, distance_m, avg_hr
           FROM fact_activity
           WHERE athlete_id = ? AND date(start_time_local) BETWEEN ? AND ?""",
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

    # 2) วัน wellness ที่ว่างทั้งแถว เฉพาะวันที่จบไปแล้ว — วันนี้ยังไม่จบวัน ค่าอาจยังไม่มา ไม่นับ
    #    (ปกติ = นักกีฬายังไม่เปิดแอป Garmin ให้นาฬิกา sync ขึ้น cloud — ตามคนได้ตรงจุด)
    if include_wellness:
        rows = conn.execute(
            """SELECT calendar_date FROM fact_daily_wellness
               WHERE athlete_id = ? AND calendar_date BETWEEN ? AND ?
                 AND calendar_date < date('now', 'localtime')
                 AND resting_hr IS NULL AND sleep_score IS NULL AND body_battery_high IS NULL
               ORDER BY calendar_date""",
            (athlete_id, str(start_date), str(end_date))).fetchall()
        if rows:
            days = ", ".join(r[0] for r in rows)
            warns.append(f"wellness ว่างทั้งวัน: {days} — นักกีฬาอาจยังไม่ได้ sync นาฬิกาเข้าแอป")

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
                        help="fast sync: ดึง activity summary เท่านั้น ไม่ดึง detail/weather/splits, "
                             "wellness, extras หรือ reconcile")
    args = parser.parse_args()
    if args.days < 0:
        parser.error("--days ต้องไม่น้อยกว่า 0")
    if args.activities_only and (args.skip_activities or args.reconcile):
        parser.error("--activities-only ใช้ร่วมกับ --skip-activities/--reconcile ไม่ได้")

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
        # แยกให้ชัดว่า "token เสีย" หรือ "เน็ตล่ม" — token เสียจะพังเงียบทุกรอบจนกว่าจะขอใหม่
        # จึงต้องแจ้งแบบเจาะจง (exit 2) ให้ fetch_all/toast บอกได้ทันทีว่าต้องรัน เพิ่มนักกีฬา.bat
        err = str(e).lower()
        is_network = any(s in err for s in (
            "timed out", "timeout", "connection", "resolve", "getaddrinfo",
            "unreachable", "temporary failure"))
        if is_network:
            print(f"❌ Login ล้มเหลวจากปัญหาเน็ต/เซิร์ฟเวอร์: {e}")
            print("   ไม่ใช่ปัญหา token — รอบถัดไปจะลองใหม่เอง")
            write_status(args.athlete, ok=False, reason="network", error=str(e))
            sys.exit(1)
        print(f"❌ TOKEN ใช้ไม่ได้ (หมดอายุ/ถูก revoke): {e}")
        print(f"   → รัน garmin\\เพิ่มนักกีฬา.bat เพื่อขอ token ใหม่ของ '{args.athlete}'")
        write_status(args.athlete, ok=False, reason="token", error=str(e))
        sys.exit(2)

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
    end_date = date.today()
    start_date = end_date - timedelta(days=args.days)

    print(f"\n🗓️  Backfill range: {start_date} → {end_date} ({args.days} days)")
    print(f"👤 Athlete: {args.athlete} (id={athlete_id})")

    # โหมด reconcile อย่างเดียว (ไม่ดึงกิจกรรม/wellness ใหม่) — สำหรับ task รายสัปดาห์
    if args.reconcile:
        result = reconcile_only(garmin, conn, athlete_id, start_date, end_date)
        conn.close()
        if result is None:
            write_status(args.athlete, ok=False, reason="network",
                         error="reconcile: ดึงรายการกิจกรรมไม่สำเร็จ")
            sys.exit(1)
        marked, restored = result
        write_status(args.athlete, ok=True, reason="ok",
                     warnings=([f"reconcile: mark กิจกรรมถูกลบ {len(marked)} รายการ"] if marked else []))
        print("\n" + "=" * 50)
        print(f"🎉 Reconcile complete! deleted +{len(marked)} | restored +{len(restored)}")
        print("=" * 50)
        return

    # Fetch data
    if args.skip_activities:
        print("\n📊 (ข้ามการดึงกิจกรรม — --skip-activities)")
        activity_count = 0
    else:
        activity_count = fetch_and_insert_activities(
            garmin, conn, athlete_id, start_date, end_date,
            fast=args.activities_only,
        )

    if args.activities_only:
        wellness_count = None
        print("\n⚡ Fast sync: ข้าม wellness/extras (full sync จะเติมตามรอบเดิม)")
    else:
        wellness_count = fetch_and_insert_wellness(
            garmin, conn, athlete_id, start_date, end_date
        )
        fetch_and_insert_extras(garmin, conn, athlete_id, start_date, end_date)

    warnings = sanity_check(
        conn, athlete_id, start_date, end_date,
        include_wellness=not args.activities_only,
    )
    if warnings:
        print("\n⚠️  Sanity check พบจุดน่าสงสัย:")
        for w in warnings:
            print(f"   - {w}")

    conn.close()
    write_status(args.athlete, ok=True, reason="ok",
                 activities=activity_count, wellness_days=wellness_count,
                 warnings=warnings)

    print("\n" + "=" * 50)
    print("🎉 Backfill complete!")
    print(f"   Activities: {activity_count}")
    print(f"   Wellness days: {wellness_count}")
    print(f"   Database: {DB_PATH}")
    print("=" * 50)


if __name__ == "__main__":
    main()
