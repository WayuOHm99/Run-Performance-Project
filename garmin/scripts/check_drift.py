#!/usr/bin/env python3
"""ตรวจ "schema drift" ของ Garmin API — ฟิลด์สำคัญที่จู่ ๆ หายเงียบ.

ปัญหาที่แก้: garminconnect/garth เป็น API ไม่เป็นทางการ Garmin เปลี่ยนชื่อ field ได้
ทุกเมื่อโดยไม่แจ้ง → parser เราจะได้ None เงียบ ๆ ต่อเนื่อง แล้วเก็บ NULL ลง DB ไปเรื่อย ๆ
sanity_check ใน 03_backfill จับได้แค่ค่าผิดปกติสุดขั้ว "รอบเดียว" ไม่จับ field ที่หายยาว.

วิธีจับ: เทียบ "อัตรามีค่า" (non-null rate) ของแต่ละ field ระหว่าง 30 วันล่าสุด vs 30 วันก่อนหน้า
ถ้าเคยมีค่าสม่ำเสมอ (≥80%) แล้วจู่ ๆ แทบไม่มีเลย (≤20%) = ผิดปกติ อาจเป็น drift หรือ endpoint เปลี่ยน.

หลักสำคัญ — แยก "field หายเฉพาะตัว" (drift จริง) ออกจาก "นักกีฬาไม่ได้ sync ทั้งวัน":
  wellness นับอัตราเฉพาะ "วันที่มีข้อมูลบ้าง" (active days) เท่านั้น — วันว่างเปล่าทั้งแถว
  ไม่นับ (นั่นคือปัญหา sync ไม่ใช่ drift). ถ้า field เดียวหายแต่ field อื่นยังมา = drift ชัด.

วิธีใช้:
    python scripts/check_drift.py                 # ทุกคน
    python scripts/check_drift.py --athlete p'kao  # เจาะจง
exit code: 1 ถ้าพบ drift (ให้ task/toast รู้), 0 ถ้าปกติ
"""

import argparse
import sqlite3
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "garmin.db"

# ── เกณฑ์ ──
GOOD_RATE = 0.80        # เคยมีค่าสม่ำเสมอ = ≥ 80% ของ sample
BAD_RATE = 0.20         # จู่ ๆ แทบไม่มี = ≤ 20%
MIN_SAMPLE = 5          # ต้องมีอย่างน้อยเท่านี้ทั้งสองหน้าต่างถึงจะตัดสิน (กัน noise)

# ฟิลด์สำคัญ (device-dependent บางตัว — วิธีเทียบกับ "ตัวเอง" ทำให้คนที่ไม่เคยมีค่าไม่ false-flag)
WELLNESS_FIELDS = ["resting_hr", "sleep_score", "hrv_last_night",
                   "body_battery_high", "training_readiness"]
ACTIVITY_FIELDS = ["training_load", "avg_hr"]


def _rate(cur, sql, params):
    """คืน (non_null, total) จาก query ที่ SELECT 2 คอลัมน์: COUNT(field), COUNT(*)"""
    row = cur.execute(sql, params).fetchone()
    return (row[0] or 0, row[1] or 0)


def check_athlete(conn, slug, athlete_id):
    """คืน list ของ finding (dict) — ว่าง = ไม่มี drift"""
    cur = conn.cursor()
    findings = []

    # ── Wellness: นับเฉพาะ "active days" (มีข้อมูลบ้าง) เพื่อแยก drift ออกจากไม่ได้ sync ──
    active_cond = ("(resting_hr IS NOT NULL OR sleep_score IS NOT NULL "
                   "OR body_battery_high IS NOT NULL OR hrv_last_night IS NOT NULL)")
    for field in WELLNESS_FIELDS:
        recent = _rate(cur, f"""
            SELECT COUNT({field}), COUNT(*) FROM fact_daily_wellness
            WHERE athlete_id = ? AND {active_cond}
              AND calendar_date BETWEEN date('now','-30 days') AND date('now','-1 day')""",
            (athlete_id,))
        prior = _rate(cur, f"""
            SELECT COUNT({field}), COUNT(*) FROM fact_daily_wellness
            WHERE athlete_id = ? AND {active_cond}
              AND calendar_date BETWEEN date('now','-60 days') AND date('now','-31 day')""",
            (athlete_id,))
        f = _judge("wellness", field, recent, prior)
        if f:
            findings.append(f)

    # ── Activity: อัตรามีค่าต่อ "จำนวนกิจกรรม" ในช่วง (ไม่รวมที่ถูกลบ) ──
    for field in ACTIVITY_FIELDS:
        recent = _rate(cur, f"""
            SELECT COUNT({field}), COUNT(*) FROM fact_activity
            WHERE athlete_id = ? AND deleted_at IS NULL
              AND date(start_time_local) BETWEEN date('now','-30 days') AND date('now','-1 day')""",
            (athlete_id,))
        prior = _rate(cur, f"""
            SELECT COUNT({field}), COUNT(*) FROM fact_activity
            WHERE athlete_id = ? AND deleted_at IS NULL
              AND date(start_time_local) BETWEEN date('now','-60 days') AND date('now','-31 day')""",
            (athlete_id,))
        f = _judge("activity", field, recent, prior)
        if f:
            findings.append(f)

    return findings


def _judge(table, field, recent, prior):
    """ตัดสินว่า field นี้ drift ไหม — คืน finding dict หรือ None"""
    recent_nn, recent_total = recent
    prior_nn, prior_total = prior
    # sample ไม่พอทั้งสองหน้าต่าง = ตัดสินไม่ได้ (ข้าม กัน false alarm)
    if recent_total < MIN_SAMPLE or prior_total < MIN_SAMPLE:
        return None
    recent_rate = recent_nn / recent_total
    prior_rate = prior_nn / prior_total
    if prior_rate >= GOOD_RATE and recent_rate <= BAD_RATE:
        return {
            "table": table, "field": field,
            "prior_rate": prior_rate, "recent_rate": recent_rate,
            "recent": recent, "prior": prior,
        }
    return None


def main():
    ap = argparse.ArgumentParser(description="ตรวจ schema drift ของ Garmin API")
    ap.add_argument("--athlete", default=None, help="slug เจาะจง (ไม่ใส่ = ทุกคน)")
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH)
    if args.athlete:
        rows = conn.execute("SELECT slug, athlete_id FROM dim_athlete WHERE slug = ?",
                            (args.athlete,)).fetchall()
    else:
        rows = conn.execute("SELECT slug, athlete_id FROM dim_athlete ORDER BY slug").fetchall()

    print("=" * 60)
    print("  ตรวจ SCHEMA DRIFT (field สำคัญที่หายเงียบ)")
    print(f"  เกณฑ์: เคยมีค่า ≥{GOOD_RATE:.0%} → จู่ ๆ ≤{BAD_RATE:.0%} | sample ขั้นต่ำ {MIN_SAMPLE}")
    print("=" * 60)

    all_findings = []
    for slug, aid in rows:
        findings = check_athlete(conn, slug, aid)
        if findings:
            print(f"\n🚩 {slug}: พบ {len(findings)} field น่าสงสัย")
            for f in findings:
                print(f"   - {f['table']}.{f['field']}: "
                      f"เคยมี {f['prior_rate']:.0%} ({f['prior'][0]}/{f['prior'][1]}) "
                      f"→ ล่าสุด {f['recent_rate']:.0%} ({f['recent'][0]}/{f['recent'][1]})")
            all_findings.extend((slug, f) for f in findings)
        else:
            print(f"\n✅ {slug}: ปกติ (ไม่มี field หายผิดปกติ)")

    conn.close()
    print("\n" + "=" * 60)
    if all_findings:
        print(f"⚠️  รวมพบ {len(all_findings)} จุดน่าสงสัย — อาจเป็น Garmin เปลี่ยน API")
        print("   ถ้า field เดียวหายแต่ field อื่นของคนนั้นยังมา = drift จริง (เช็ค parser ใน 03_backfill)")
        print("   ถ้าหลาย field หายพร้อมกัน = อาจเป็นนาฬิกา/บัญชีหยุด sync (ไม่ใช่ drift)")
        print("=" * 60)
        sys.exit(1)
    print("✅ ไม่พบ schema drift — field สำคัญมาครบตามปกติ")
    print("=" * 60)
    sys.exit(0)


if __name__ == "__main__":
    main()
