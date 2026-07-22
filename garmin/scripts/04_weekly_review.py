#!/usr/bin/env python3
"""Weekly Review Analysis — Garmin Team Data Pipeline.

Generates a comprehensive weekly review report from garmin.db.

Usage:
    python scripts/04_weekly_review.py [--athlete tong] [--weeks 4]
"""

import argparse
import sqlite3
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "garmin.db"


def print_header(title: str):
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_section(title: str):
    print(f"\n--- {title} ---")


# ══════════════════════════════════════════════════════════════
# 1. Weekly Training Summary
# ══════════════════════════════════════════════════════════════

def weekly_training_summary(conn, athlete_id, weeks):
    print_header("WEEKLY TRAINING SUMMARY")

    rows = conn.execute("""
        SELECT
            strftime('%Y-W%W', start_time_local)                    AS week,
            MIN(date(start_time_local))                             AS week_start,
            COUNT(*)                                                AS sessions,
            ROUND(SUM(distance_m) / 1000.0, 1)                     AS total_km,
            ROUND(SUM(duration_sec) / 3600.0, 1)                   AS total_hrs,
            ROUND(AVG(avg_hr), 0)                                   AS avg_hr,
            ROUND(AVG(CASE WHEN avg_pace_min_per_km IS NOT NULL
                            THEN avg_pace_min_per_km END), 2)       AS avg_pace,
            ROUND(SUM(elevation_gain_m), 0)                         AS total_elev,
            ROUND(SUM(calories), 0)                                 AS total_cal,
            ROUND(AVG(training_effect_aerobic), 1)                  AS avg_te_aero,
            ROUND(SUM(COALESCE(training_load, 0)), 0)               AS total_load
        FROM fact_activity
        WHERE athlete_id = ?
          AND activity_type = 'running'
          AND start_time_local >= date('now', ?)
          AND deleted_at IS NULL
        GROUP BY week
        ORDER BY week DESC
    """, (athlete_id, f'-{weeks * 7} days')).fetchall()

    if not rows:
        print("  No running data found.")
        return

    print(f"  {'Week':<10} {'Runs':>4} {'Dist(km)':>9} {'Time(h)':>8} {'Avg HR':>7} {'Pace':>6} {'Elev':>6} {'TE':>4} {'Load':>6}")
    print("  " + "-" * 68)
    for r in rows:
        pace_str = f"{int(r[6])}:{int((r[6] % 1) * 60):02d}" if r[6] else "  -  "
        print(f"  {r[0]:<10} {r[2]:>4} {r[3]:>9} {r[4]:>8} {r[5]:>7.0f} {pace_str:>6} {r[7] or 0:>6.0f} {r[9] or 0:>4.1f} {r[10] or 0:>6.0f}")

    # Week-over-week change
    if len(rows) >= 2:
        curr_km, prev_km = rows[0][3], rows[1][3]
        if prev_km and prev_km > 0:
            pct = ((curr_km - prev_km) / prev_km) * 100
            arrow = "+" if pct > 0 else ""
            print(f"\n  Week-over-week distance change: {arrow}{pct:.1f}%")
            if pct > 15:
                print("  !! Ramp rate > 15% — watch for overload risk")


# ══════════════════════════════════════════════════════════════
# 2. Long Run Tracker
# ══════════════════════════════════════════════════════════════

def long_run_tracker(conn, athlete_id, weeks):
    print_section("LONG RUNS (>= 10 km)")

    rows = conn.execute("""
        SELECT
            date(start_time_local)                          AS run_date,
            activity_name,
            ROUND(distance_m / 1000.0, 2)                   AS km,
            ROUND(duration_sec / 60.0, 1)                    AS mins,
            ROUND(avg_pace_min_per_km, 2)                    AS pace,
            avg_hr,
            max_hr,
            ROUND(elevation_gain_m, 0)                       AS elev
        FROM fact_activity
        WHERE athlete_id = ?
          AND activity_type = 'running'
          AND distance_m >= 10000
          AND start_time_local >= date('now', ?)
          AND deleted_at IS NULL
        ORDER BY start_time_local DESC
        LIMIT 10
    """, (athlete_id, f'-{weeks * 7} days')).fetchall()

    if not rows:
        print("  No long runs found in this period.")
        return

    print(f"  {'Date':<12} {'Dist':>6} {'Time':>7} {'Pace':>6} {'Avg HR':>7} {'Max HR':>7} {'Elev':>5}")
    print("  " + "-" * 56)
    for r in rows:
        pace_str = f"{int(r[4])}:{int((r[4] % 1) * 60):02d}" if r[4] else "  -  "
        print(f"  {r[0]:<12} {r[2]:>6.1f} {r[3]:>6.0f}m {pace_str:>6} {r[5] or 0:>7.0f} {r[6] or 0:>7.0f} {r[7] or 0:>5.0f}")


# ══════════════════════════════════════════════════════════════
# 3. VDOT Estimation from Recent Fast Efforts
# ══════════════════════════════════════════════════════════════

def vdot_estimation(conn, athlete_id):
    print_section("VDOT ESTIMATION (from recent fast efforts)")

    # Use Daniels' VDOT approximation for common distances
    # Simplified: VDOT ~ 132.853 - 96.021 * e^(-0.007546 * v) + ...
    # We'll use a lookup approach for common distances
    rows = conn.execute("""
        SELECT
            date(start_time_local)                     AS run_date,
            activity_name,
            ROUND(distance_m / 1000.0, 2)              AS km,
            duration_sec,
            ROUND(avg_pace_min_per_km, 2)               AS pace,
            vo2max_value
        FROM fact_activity
        WHERE athlete_id = ?
          AND activity_type = 'running'
          AND distance_m >= 3000
          AND avg_pace_min_per_km IS NOT NULL
          AND deleted_at IS NULL
        ORDER BY avg_pace_min_per_km ASC
        LIMIT 5
    """, (athlete_id,)).fetchall()

    if not rows:
        print("  Not enough data for VDOT estimation.")
        return

    print("  Fastest efforts (potential race-pace indicators):")
    print(f"  {'Date':<12} {'Name':<25} {'Dist':>6} {'Pace':>6} {'Garmin VO2':>10}")
    print("  " + "-" * 65)
    for r in rows:
        pace_str = f"{int(r[4])}:{int((r[4] % 1) * 60):02d}" if r[4] else "  -  "
        vo2 = f"{r[5]:.1f}" if r[5] else "  -  "
        name = (r[1] or "")[:24]
        print(f"  {r[0]:<12} {name:<25} {r[2]:>5.1f}k {pace_str:>6} {vo2:>10}")

    # Garmin VO2Max if available
    latest_vo2 = conn.execute("""
        SELECT vo2max_value FROM fact_activity
        WHERE athlete_id = ? AND vo2max_value IS NOT NULL AND deleted_at IS NULL
        ORDER BY start_time_local DESC LIMIT 1
    """, (athlete_id,)).fetchone()

    if latest_vo2:
        vo2 = latest_vo2[0]
        print(f"\n  Latest Garmin VO2Max: {vo2:.1f}")
        # Rough equivalent race times from VO2Max
        print(f"  Estimated race paces (Daniels approx):")
        # Very rough approximations based on VDOT tables
        if vo2 >= 30:
            easy_pace = 7.5 - (vo2 - 30) * 0.05
            tempo_pace = 6.0 - (vo2 - 30) * 0.05
            print(f"    Easy:  ~{easy_pace:.1f} min/km")
            print(f"    Tempo: ~{tempo_pace:.1f} min/km")


# ══════════════════════════════════════════════════════════════
# 4. HRV & Resting HR Trend
# ══════════════════════════════════════════════════════════════

def hrv_rhr_trend(conn, athlete_id, weeks):
    print_header("HRV & RESTING HR TREND")

    rows = conn.execute("""
        SELECT
            strftime('%Y-W%W', calendar_date)               AS week,
            ROUND(AVG(resting_hr), 1)                       AS avg_rhr,
            ROUND(MIN(resting_hr), 0)                       AS min_rhr,
            ROUND(MAX(resting_hr), 0)                       AS max_rhr,
            ROUND(AVG(hrv_last_night), 1)                   AS avg_hrv,
            ROUND(MIN(hrv_last_night), 0)                   AS min_hrv,
            ROUND(MAX(hrv_last_night), 0)                   AS max_hrv,
            COUNT(*)                                        AS days
        FROM fact_daily_wellness
        WHERE athlete_id = ?
          AND calendar_date >= date('now', ?)
        GROUP BY week
        ORDER BY week DESC
    """, (athlete_id, f'-{weeks * 7} days')).fetchall()

    if not rows:
        print("  No wellness data found.")
        return

    print(f"  {'Week':<10} {'Avg RHR':>8} {'Range':>10} {'Avg HRV':>8} {'Range':>10} {'Days':>5}")
    print("  " + "-" * 56)
    for r in rows:
        rhr_range = f"{r[2]:.0f}-{r[3]:.0f}" if r[2] else "-"
        hrv_range = f"{r[5]:.0f}-{r[6]:.0f}" if r[5] else "-"
        print(f"  {r[0]:<10} {r[1] or 0:>8.1f} {rhr_range:>10} {r[4] or 0:>8.1f} {hrv_range:>10} {r[7]:>5}")

    # 7-day rolling average for latest
    latest_7d = conn.execute("""
        SELECT
            ROUND(AVG(resting_hr), 1),
            ROUND(AVG(hrv_last_night), 1)
        FROM fact_daily_wellness
        WHERE athlete_id = ?
          AND calendar_date >= date('now', '-7 days')
    """, (athlete_id,)).fetchone()

    if latest_7d[0]:
        print(f"\n  7-day rolling avg:  RHR = {latest_7d[0]} bpm  |  HRV = {latest_7d[1]} ms")


# ══════════════════════════════════════════════════════════════
# 5. Sleep Quality Trend
# ══════════════════════════════════════════════════════════════

def sleep_trend(conn, athlete_id, weeks):
    print_section("SLEEP QUALITY")

    rows = conn.execute("""
        SELECT
            strftime('%Y-W%W', calendar_date)               AS week,
            ROUND(AVG(sleep_score), 1)                      AS avg_score,
            ROUND(AVG(sleep_duration_sec) / 3600.0, 1)      AS avg_hrs,
            ROUND(AVG(deep_sleep_sec) / 60.0, 0)            AS avg_deep_min,
            ROUND(AVG(rem_sleep_sec) / 60.0, 0)             AS avg_rem_min,
            ROUND(AVG(body_battery_high), 0)                AS avg_bb_high,
            ROUND(AVG(body_battery_low), 0)                 AS avg_bb_low
        FROM fact_daily_wellness
        WHERE athlete_id = ?
          AND calendar_date >= date('now', ?)
        GROUP BY week
        ORDER BY week DESC
    """, (athlete_id, f'-{weeks * 7} days')).fetchall()

    if not rows:
        print("  No sleep data found.")
        return

    print(f"  {'Week':<10} {'Score':>6} {'Hours':>6} {'Deep':>6} {'REM':>6} {'BB Hi':>6} {'BB Lo':>6}")
    print("  " + "-" * 52)
    for r in rows:
        print(f"  {r[0]:<10} {r[1] or 0:>6.1f} {r[2] or 0:>6.1f} {r[3] or 0:>5.0f}m {r[4] or 0:>5.0f}m {r[5] or 0:>6.0f} {r[6] or 0:>6.0f}")


# ══════════════════════════════════════════════════════════════
# 6. Readiness & Recovery Score
# ══════════════════════════════════════════════════════════════

def readiness_check(conn, athlete_id):
    print_section("READINESS SNAPSHOT (last 7 days)")

    rows = conn.execute("""
        SELECT
            calendar_date,
            resting_hr,
            hrv_last_night,
            sleep_score,
            body_battery_high,
            body_battery_low,
            stress_avg,
            training_readiness
        FROM fact_daily_wellness
        WHERE athlete_id = ?
        ORDER BY calendar_date DESC
        LIMIT 7
    """, (athlete_id,)).fetchall()

    if not rows:
        print("  No data.")
        return

    print(f"  {'Date':<12} {'RHR':>5} {'HRV':>5} {'Sleep':>6} {'BB Hi':>6} {'BB Lo':>6} {'Stress':>7}")
    print("  " + "-" * 52)
    for r in rows:
        print(f"  {r[0]:<12} {r[1] or 0:>5.0f} {r[2] or 0:>5.0f} {r[3] or 0:>6.0f} {r[4] or 0:>6} {r[5] or 0:>6} {r[6] or 0:>7.0f}")

    # Simple readiness heuristic
    # (lower RHR + higher HRV + higher sleep + higher BB = better recovery)
    latest = rows[0]
    avg_7 = conn.execute("""
        SELECT AVG(resting_hr), AVG(hrv_last_night), AVG(sleep_score), AVG(body_battery_high)
        FROM fact_daily_wellness
        WHERE athlete_id = ? AND calendar_date >= date('now', '-30 days')
    """, (athlete_id,)).fetchone()

    if latest[1] and avg_7[0]:
        rhr_vs_avg = latest[1] - avg_7[0] if latest[1] else 0
        hrv_vs_avg = latest[2] - avg_7[1] if latest[2] and avg_7[1] else 0

        print(f"\n  Today vs 30-day avg:")
        print(f"    RHR:   {latest[1]:.0f} vs avg {avg_7[0]:.0f}  ({'+' if rhr_vs_avg > 0 else ''}{rhr_vs_avg:.0f})")
        if latest[2] and avg_7[1]:
            print(f"    HRV:   {latest[2]:.0f} vs avg {avg_7[1]:.0f}  ({'+' if hrv_vs_avg > 0 else ''}{hrv_vs_avg:.0f})")

        # Simple traffic light
        signals = []
        if latest[1] and avg_7[0] and latest[1] > avg_7[0] + 5:
            signals.append("RHR elevated")
        if latest[2] and avg_7[1] and latest[2] < avg_7[1] * 0.8:
            signals.append("HRV suppressed")
        if latest[3] and latest[3] < 40:
            signals.append("Low sleep score")
        if latest[4] and latest[4] < 50:
            signals.append("Low body battery")

        if signals:
            print(f"\n  !! Recovery flags: {', '.join(signals)}")
        else:
            print(f"\n  All recovery signals normal")


# ══════════════════════════════════════════════════════════════
# 7. Activity Split Analysis (recent long run)
# ══════════════════════════════════════════════════════════════

def split_analysis(conn, athlete_id):
    print_section("SPLIT ANALYSIS (latest long run)")

    # Find most recent long run
    activity = conn.execute("""
        SELECT activity_id, activity_name, date(start_time_local),
               ROUND(distance_m / 1000.0, 2), ROUND(duration_sec / 60.0, 1)
        FROM fact_activity
        WHERE athlete_id = ? AND activity_type = 'running' AND distance_m >= 8000
          AND deleted_at IS NULL
        ORDER BY start_time_local DESC LIMIT 1
    """, (athlete_id,)).fetchone()

    if not activity:
        print("  No long run with splits found.")
        return

    print(f"  {activity[2]} — {activity[1] or 'Run'} | {activity[3]} km | {activity[4]:.0f} min")
    print()

    splits = conn.execute("""
        SELECT split_num, ROUND(distance_m / 1000.0, 2), ROUND(duration_sec, 0),
               avg_hr, avg_pace_min_km
        FROM fact_activity_split
        WHERE activity_id = ?
        ORDER BY split_num
    """, (activity[0],)).fetchall()

    if not splits:
        print("  No split data available.")
        return

    print(f"  {'Split':>5} {'Dist':>6} {'Pace':>7} {'HR':>5}")
    print("  " + "-" * 28)
    paces = []
    for s in splits:
        pace = s[4]
        if pace:
            paces.append(pace)
            pace_str = f"{int(pace)}:{int((pace % 1) * 60):02d}"
        else:
            pace_str = "  -  "
        print(f"  {s[0]:>5} {s[1] or 0:>5.1f}k {pace_str:>7} {s[3] or 0:>5.0f}")

    if len(paces) >= 4:
        first_half = paces[:len(paces)//2]
        second_half = paces[len(paces)//2:]
        avg_first = sum(first_half) / len(first_half)
        avg_second = sum(second_half) / len(second_half)
        diff = avg_second - avg_first
        if diff < 0:
            print(f"\n  Negative split! 2nd half {abs(diff)*60:.0f}s/km faster")
        else:
            print(f"\n  Positive split: 2nd half {diff*60:.0f}s/km slower")


# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Weekly review analysis")
    parser.add_argument("--athlete", default="tong", help="Athlete slug (default: tong)")
    parser.add_argument("--weeks", type=int, default=4, help="Weeks to analyze (default: 4)")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)

    # Get athlete_id
    row = conn.execute(
        "SELECT athlete_id, display_name, garmin_full_name FROM dim_athlete WHERE slug = ?",
        (args.athlete,)
    ).fetchone()

    if not row:
        print(f"Athlete '{args.athlete}' not found in database.")
        return

    athlete_id = row[0]
    print()
    print("*" * 60)
    print(f"  WEEKLY REVIEW — {row[2] or row[1]}")
    print(f"  Period: last {args.weeks} weeks  |  Generated: {date.today()}")
    print("*" * 60)

    weekly_training_summary(conn, athlete_id, args.weeks)
    long_run_tracker(conn, athlete_id, args.weeks)
    vdot_estimation(conn, athlete_id)
    hrv_rhr_trend(conn, athlete_id, args.weeks)
    sleep_trend(conn, athlete_id, args.weeks)
    readiness_check(conn, athlete_id)
    split_analysis(conn, athlete_id)

    print("\n" + "=" * 60)
    print("  END OF REPORT")
    print("=" * 60)

    conn.close()


if __name__ == "__main__":
    main()
