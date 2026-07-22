#!/usr/bin/env python3
"""ดูข้อมูล Garmin ของนักกีฬา "รายวัน" แบบอ่านง่าย — สำหรับโค้ชคัดกรองก่อนขึ้น Notion.

ใช้ตอน workflow ประจำ: อ่านตัวเลขจาก garmin.db (แทนรูป) → เอาไปประกอบกับ
RPE/ความรู้สึก/คำสั่งจากไลน์ → คัดกรอง → เขียน Training Log ใน Notion

วิธีใช้:
    python scripts/day.py --athlete tong                 # วันนี้
    python scripts/day.py --athlete tong --date 2026-07-19
    python scripts/day.py --athlete tong --date 2026-07-19 --splits   # โชว์ splits ทุก km
"""

import argparse
import sqlite3
import sys
from datetime import date
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "garmin.db"


def fmt_pace(p):
    return f"{int(p)}:{int((p % 1) * 60):02d}" if p else "—"


def fmt_hms(sec):
    if not sec:
        return "—"
    sec = int(sec)
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def main():
    ap = argparse.ArgumentParser(description="ดูข้อมูล Garmin รายวัน")
    ap.add_argument("--athlete", required=True, help="slug เช่น tong")
    ap.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD (ค่าเริ่มต้น=วันนี้)")
    ap.add_argument("--splits", action="store_true", help="โชว์ splits ทุก km")
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT athlete_id, garmin_full_name, display_name FROM dim_athlete WHERE slug=?",
        (args.athlete,),
    ).fetchone()
    if not row:
        print(f"❌ ไม่พบนักกีฬา slug='{args.athlete}' ใน garmin.db")
        sys.exit(1)
    aid, name = row[0], row[1] or row[2]

    print("=" * 60)
    print(f"  {name}  ({args.athlete})  —  {args.date}")
    print("=" * 60)

    # ── กิจกรรมของวันนั้น ──
    acts = conn.execute("""
        SELECT activity_id, activity_type, activity_name, start_time_local,
               duration_sec, distance_m, avg_hr, max_hr, avg_pace_min_per_km,
               avg_cadence, elevation_gain_m, avg_power, training_load,
               training_effect_aerobic, training_effect_anaerobic, calories
        FROM fact_activity
        WHERE athlete_id=? AND date(start_time_local)=? AND deleted_at IS NULL
        ORDER BY start_time_local
    """, (aid, args.date)).fetchall()

    if not acts:
        print("\n  (ไม่มีกิจกรรมวันนี้)")
    for a in acts:
        km = (a[5] or 0) / 1000
        print(f"\n▶ {a[2] or a[1]}  [{a[1]}]  {a[3][11:16] if a[3] else ''}")
        print(f"   ระยะ {km:.2f} km | เวลา {fmt_hms(a[4])} | เพซ {fmt_pace(a[8])}/km")
        cad = f"{a[9]:.0f}" if a[9] else "—"
        print(f"   HR เฉลี่ย {a[6] or '—'} / สูงสุด {a[7] or '—'} | cadence {cad} spm"
              f" | ต่าง {a[10] or 0:.0f} m")
        extra = []
        if a[11]:
            extra.append(f"power {a[11]:.0f}W")
        if a[12]:
            extra.append(f"load {a[12]:.0f}")
        if a[13] or a[14]:
            extra.append(f"TE aero {a[13] or 0:.1f}/anaero {a[14] or 0:.1f}")
        if a[15]:
            extra.append(f"{a[15]:.0f} kcal")
        if extra:
            print("   " + " | ".join(extra))

        if args.splits:
            splits = conn.execute("""
                SELECT split_num, distance_m, duration_sec, avg_hr, avg_pace_min_km
                FROM fact_activity_split WHERE activity_id=? ORDER BY split_num
            """, (a[0],)).fetchall()
            if splits:
                print(f"   {'#':>2} {'km':>5} {'เพซ':>7} {'HR':>5}")
                for s in splits:
                    print(f"   {s[0]:>2} {(s[1] or 0)/1000:>5.2f} {fmt_pace(s[4]):>7} {s[3] or '—':>5}")

    # ── wellness ของวันนั้น ──
    w = conn.execute("""
        SELECT resting_hr, hrv_last_night, hrv_status, sleep_score,
               sleep_duration_sec, deep_sleep_sec, rem_sleep_sec,
               body_battery_high, body_battery_low, stress_avg,
               training_readiness, training_status,
               vo2max_trend, endurance_score, hill_score_overall,
               lactate_threshold_hr, lactate_threshold_pace_min_km
        FROM fact_daily_wellness WHERE athlete_id=? AND calendar_date=?
    """, (aid, args.date)).fetchone()

    print("\n" + "-" * 60)
    print("  Wellness")
    print("-" * 60)
    if not w:
        print("  (ไม่มีข้อมูล wellness วันนี้)")
    else:
        print(f"   RHR {w[0] or '—'} bpm | HRV {w[1] or '—'} ms ({w[2] or '—'})")
        print(f"   นอน: score {w[3] or '—'} | รวม {fmt_hms(w[4])}"
              f" | deep {fmt_hms(w[5])} | REM {fmt_hms(w[6])}")
        print(f"   Body Battery {w[8] or '—'}→{w[7] or '—'} | stress {w[9] or '—'}")
        print(f"   Readiness {w[10] or '—'} | สถานะซ้อม {w[11] or '—'}")
        form = []
        if w[12]:
            form.append(f"VO2max {w[12]:.1f}")
        if w[13]:
            form.append(f"endurance {w[13]:.0f}")
        if w[14]:
            form.append(f"hill {w[14]:.0f}")
        if w[15] or w[16]:
            form.append(f"Garmin LT {w[15] or '—'} bpm @{fmt_pace(w[16])}/km")
        if form:
            print("   ฟอร์ม: " + " | ".join(form))

    # ── Garmin คาดการณ์เวลาแข่ง ณ วันนั้น (จาก fact_race_prediction) ──
    rp = conn.execute("""
        SELECT time_5k_sec, time_10k_sec, time_half_sec, time_full_sec
        FROM fact_race_prediction WHERE athlete_id=? AND calendar_date=?
    """, (aid, args.date)).fetchone()
    if rp and any(rp):
        print(f"   คาดการณ์แข่ง: 5K {fmt_hms(rp[0])} | 10K {fmt_hms(rp[1])}"
              f" | HM {fmt_hms(rp[2])} | FM {fmt_hms(rp[3])}")

    conn.close()
    print()


if __name__ == "__main__":
    main()
