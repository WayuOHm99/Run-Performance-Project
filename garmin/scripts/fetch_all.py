#!/usr/bin/env python3
"""Incremental daily fetch สำหรับนักกีฬา "ทุกคน" ที่มี token.

ใช้รันอัตโนมัติทุกวัน (ผ่าน Task Scheduler) — ดึงข้อมูลย้อนหลังช่วงสั้น ๆ
(ค่าเริ่มต้น 3 วัน) เพื่อเก็บกิจกรรมใหม่ + เติม wellness ที่มาช้า
เนื่องจาก 03_backfill ใช้ INSERT OR REPLACE จึงรันซ้ำได้ไม่เกิดข้อมูลซ้ำ

วิธีใช้:
    python scripts/fetch_all.py [--days 3] [--athlete tong]
    python scripts/fetch_all.py --days 45 --skip-activities   # deep resync wellness รายเดือน
    python scripts/fetch_all.py --days 90 --reconcile         # เช็คกิจกรรมถูกลบ รายสัปดาห์

- ไม่ใส่ --athlete → วนทุกโฟลเดอร์ใน tokens/
- เรียก 03_backfill.py เป็น subprocess ต่อคน (โค้ดดึงข้อมูลชุดเดียว ไม่ซ้ำ)
- --skip-activities / --reconcile ส่งต่อให้ 03_backfill ทุกคน (ดู help ของ 03_backfill)
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# บังคับ UTF-8 กันปัญหา console cp1252 พิมพ์ไทย/emoji ไม่ได้ (Task Scheduler)
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent      # D:\Run-Performance\garmin
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
TOKENS_DIR = PROJECT_ROOT / "tokens"
BACKFILL = SCRIPTS_DIR / "03_backfill.py"
STATUS_DIR = PROJECT_ROOT / "data" / "sync_status"          # สถานะรายคน (03_backfill เขียน)
STATUS_FILE = PROJECT_ROOT / "data" / "sync_status.json"    # สถานะรวมรอบล่าสุด (ไฟล์นี้เขียน)


def read_athlete_status(slug: str, not_before: datetime) -> dict | None:
    """อ่าน data/sync_status/<slug>.json เฉพาะเมื่อเขียน "ในรอบนี้" (กันหยิบไฟล์เก่าค้าง
    จากรอบก่อนมาปนเมื่อ 03_backfill ตายก่อนเขียนสถานะ)."""
    p = STATUS_DIR / f"{slug}.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if datetime.fromisoformat(data["finished_at"]) >= not_before:
            return data
    except Exception:
        pass
    return None


def list_athletes() -> list[str]:
    """คืนรายชื่อ slug ของนักกีฬาที่มี token พร้อมใช้."""
    if not TOKENS_DIR.exists():
        return []
    result = []
    for d in sorted(TOKENS_DIR.iterdir()):
        if d.is_dir() and (d / "garmin_tokens.json").exists():
            result.append(d.name)
    return result


def main():
    parser = argparse.ArgumentParser(description="ดึงข้อมูล Garmin ทุกคน (incremental)")
    parser.add_argument("--days", type=int, default=3,
                        help="จำนวนวันย้อนหลัง (ค่าเริ่มต้น 3)")
    parser.add_argument("--athlete", default=None,
                        help="เจาะจงคนเดียว (ไม่ใส่ = ทุกคน)")
    parser.add_argument("--skip-activities", action="store_true",
                        help="ส่งต่อให้ 03_backfill — ดึงเฉพาะ wellness/extras "
                             "(ใช้ทำ deep resync รายเดือน ดักค่าที่ Garmin คำนวณย้อนหลัง)")
    parser.add_argument("--reconcile", action="store_true",
                        help="ส่งต่อให้ 03_backfill — โหมดเช็คกิจกรรมถูกลบฝั่ง Garmin "
                             "(ใช้ทำ reconciliation รายสัปดาห์ เช่น --days 90 --reconcile)")
    args = parser.parse_args()

    # ธงที่ส่งต่อให้ subprocess 03_backfill ต่อคน
    passthrough = []
    if args.skip_activities:
        passthrough.append("--skip-activities")
    if args.reconcile:
        passthrough.append("--reconcile")

    athletes = [args.athlete] if args.athlete else list_athletes()

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("=" * 60)
    print(f"  FETCH ALL — {stamp}")
    print(f"  นักกีฬา: {', '.join(athletes) if athletes else '(ไม่พบ token)'}")
    _mode = "reconcile (เช็คกิจกรรมถูกลบ)" if args.reconcile else \
            ("deep resync wellness (ข้ามกิจกรรม)" if args.skip_activities else "ปกติ")
    print(f"  ช่วง: {args.days} วันล่าสุด | โหมด: {_mode}")
    print("=" * 60)

    if not athletes:
        print("⚠️  ไม่พบ token ใน tokens/ — ยังไม่มีใครให้ดึง")
        sys.exit(0)

    run_started = datetime.now()
    ok, failed = [], []
    results = []            # สถานะละเอียดรายคน → data/sync_status.json (toast/dashboard อ่าน)
    for slug in athletes:
        print(f"\n▶ {slug}")
        # เพดานเวลา 20 นาที/คน (daily --days 3 ปกติเสร็จใน <1 นาที เพราะมี socket timeout 30 วิ
        # ใน 03_backfill) — กันเผื่อลูกกระบวนการค้าง ไม่ให้คนเดียวลากทั้งทีมค้างข้ามวัน
        try:
            proc = subprocess.run(
                [sys.executable, str(BACKFILL), "--athlete", slug,
                 "--days", str(args.days), *passthrough],
                cwd=str(PROJECT_ROOT),
                env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
                timeout=1200,
            )
            status = read_athlete_status(slug, run_started)
            if proc.returncode == 0:
                ok.append(slug)
                results.append({"slug": slug, "ok": True, "reason": "ok",
                                "warnings": (status or {}).get("warnings", [])})
            else:
                failed.append(slug)
                # exit 2 = token เสีย (03_backfill แยกให้แล้ว) — บอกวิธีแก้ได้ตรงจุด
                reason = (status or {}).get("reason") or \
                    ("token" if proc.returncode == 2 else "error")
                results.append({"slug": slug, "ok": False, "reason": reason,
                                "warnings": []})
        except subprocess.TimeoutExpired:
            print(f"   ❌ {slug}: เกิน 20 นาที — ยกเลิกแล้วไปคนถัดไป")
            failed.append(slug)
            results.append({"slug": slug, "ok": False, "reason": "timeout", "warnings": []})
        except Exception as e:
            # คนเดียวพังต้องไม่ลากทั้งทีม — log แล้วไปคนถัดไป (เคยเกิด 21 ก.ค. 69:
            # dan พังกลางทางทำให้ tong/p'kao ในคิวเดียวกันไม่ถูกดึงเลยทั้งรอบ)
            print(f"   ❌ {slug}: {type(e).__name__}: {e} — ข้ามไปคนถัดไป")
            failed.append(slug)
            results.append({"slug": slug, "ok": False, "reason": "error", "warnings": []})

    # สรุปรวมรอบนี้ให้ notify_sync.ps1 (toast) กับ dashboard อ่าน
    try:
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATUS_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({
            "run_at": run_started.isoformat(timespec="seconds"),
            "days": args.days,
            "results": results,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(STATUS_FILE)
    except Exception as e:
        print(f"⚠️  เขียน sync_status.json ไม่สำเร็จ: {e}")

    n_warn = sum(len(r["warnings"]) for r in results)
    print("\n" + "=" * 60)
    print(f"  เสร็จ: {len(ok)} สำเร็จ ({', '.join(ok) or '-'})"
          f" | ล้มเหลว: {len(failed)} ({', '.join(failed) or '-'})"
          f" | ข้อมูลน่าสงสัย: {n_warn} จุด")
    print("=" * 60)
    # exit code != 0 ถ้ามีคนล้มเหลว เพื่อให้ log/Task เห็นสถานะ
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
