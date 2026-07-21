#!/usr/bin/env python3
"""Backfill 90 days of Garmin data into SQLite.

Usage:
    python scripts/03_backfill.py [--athlete wayuo] [--days 90]

Fetches activities + daily wellness data and inserts into garmin.db.
Requires token to already exist in tokens/<athlete>/.
"""

import argparse
import os
import socket
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "garmin.db"

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


def fetch_and_insert_activities(garmin, conn, athlete_id, start_date, end_date):
    """Fetch activities by date range and insert into fact_activity (ละเอียด: running dynamics,
    HR time-in-zone, weather, stamina/impact load สำหรับกิจกรรมวิ่ง)."""
    print(f"\n📊 Fetching activities from {start_date} to {end_date}...")

    activities = safe_call(
        garmin.get_activities_by_date,
        start_date.isoformat(),
        end_date.isoformat(),
    )
    if not activities:
        print("   No activities found.")
        return 0

    cur = conn.cursor()
    count = 0

    for act in activities:
        activity_id = act.get("activityId")
        if not activity_id:
            continue

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
        if is_run:
            time.sleep(0.3)
            min_hr, impact_load, begin_stamina, end_stamina = fetch_activity_detail(garmin, activity_id)
            if act.get("startLatitude") is not None:  # outdoor เท่านั้นถึงมี weather
                time.sleep(0.3)
                w_temp, w_apparent, w_humidity, w_wind = fetch_weather(garmin, activity_id)

        cur.execute("""
            INSERT OR REPLACE INTO fact_activity (
                activity_id, athlete_id, activity_type, activity_name,
                start_time_local, start_time_utc, duration_sec, moving_duration_sec,
                distance_m, avg_hr, max_hr, min_hr, avg_pace_min_per_km,
                avg_speed_mps, max_speed_mps, avg_grade_adjusted_speed_mps,
                calories, bmr_calories, training_effect_aerobic, training_effect_anaerobic,
                training_effect_label, vo2max_value, avg_cadence, max_cadence,
                avg_stride_length_cm, avg_ground_contact_time_ms,
                avg_vertical_oscillation_cm, avg_vertical_ratio,
                elevation_gain_m, elevation_loss_m, min_elevation_m, max_elevation_m,
                avg_power, max_power, normalized_power, training_load,
                impact_load, begin_stamina, end_stamina,
                hr_zone1_sec, hr_zone2_sec, hr_zone3_sec, hr_zone4_sec, hr_zone5_sec,
                steps, moderate_intensity_min, vigorous_intensity_min,
                diff_body_battery, sweat_loss_ml, start_latitude, start_longitude, location_name,
                weather_temp_c, weather_apparent_temp_c, weather_humidity, weather_wind_kph
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?, ?, ?)
        """, (
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
        ))
        count += 1

        # ดึง splits เฉพาะกิจกรรมที่มีระยะทาง (วิ่ง/เดิน) — cross-training ไม่มี split ที่มีความหมาย
        if has_dist:
            time.sleep(0.5)
            fetch_and_insert_splits(garmin, conn, activity_id)

    conn.commit()
    print(f"   ✅ Inserted {count} activities")
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
                training_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        ))
        count += 1
        print(" ✓")

        # Longer pause between days to avoid rate limit
        time.sleep(1.5)
        current += timedelta(days=1)

    conn.commit()
    print(f"   ✅ Inserted {count} wellness records")
    return count


# ── Main ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Backfill Garmin data")
    parser.add_argument("--athlete", default="wayuo", help="Athlete slug (default: wayuo)")
    parser.add_argument("--days", type=int, default=90, help="Days to backfill (default: 90)")
    args = parser.parse_args()

    # Set up token path
    token_dir = PROJECT_ROOT / "tokens" / args.athlete
    if not token_dir.exists():
        print(f"❌ Token directory not found: {token_dir}")
        print("   Run 01_generate_token.py first.")
        sys.exit(1)

    # Login with saved token
    print(f"🔐 Loading token for '{args.athlete}'...")
    from garminconnect import Garmin
    garmin = Garmin()
    try:
        garmin.login(str(token_dir))
    except Exception as e:
        print(f"❌ Token login failed: {e}")
        print("   Re-run 01_generate_token.py to refresh.")
        sys.exit(1)

    full_name = garmin.get_full_name()
    print(f"✅ Logged in as: {full_name}")

    # Connect to database
    conn = sqlite3.connect(DB_PATH)
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

    # Fetch data
    activity_count = fetch_and_insert_activities(garmin, conn, athlete_id, start_date, end_date)
    wellness_count = fetch_and_insert_wellness(garmin, conn, athlete_id, start_date, end_date)

    conn.close()

    print("\n" + "=" * 50)
    print("🎉 Backfill complete!")
    print(f"   Activities: {activity_count}")
    print(f"   Wellness days: {wellness_count}")
    print(f"   Database: {DB_PATH}")
    print("=" * 50)


if __name__ == "__main__":
    main()
