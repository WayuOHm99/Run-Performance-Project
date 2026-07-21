#!/usr/bin/env python3
"""Incremental daily fetch สำหรับนักกีฬา "ทุกคน" ที่มี token.

ใช้รันอัตโนมัติทุกวัน (ผ่าน Task Scheduler) — ดึงข้อมูลย้อนหลังช่วงสั้น ๆ
(ค่าเริ่มต้น 3 วัน) เพื่อเก็บกิจกรรมใหม่ + เติม wellness ที่มาช้า
เนื่องจาก 03_backfill ใช้ INSERT OR REPLACE จึงรันซ้ำได้ไม่เกิดข้อมูลซ้ำ

วิธีใช้:
    python scripts/fetch_all.py [--days 3] [--athlete tong]

- ไม่ใส่ --athlete → วนทุกโฟลเดอร์ใน tokens/
- เรียก 03_backfill.py เป็น subprocess ต่อคน (โค้ดดึงข้อมูลชุดเดียว ไม่ซ้ำ)
"""

import argparse
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
    args = parser.parse_args()

    athletes = [args.athlete] if args.athlete else list_athletes()

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("=" * 60)
    print(f"  FETCH ALL — {stamp}")
    print(f"  นักกีฬา: {', '.join(athletes) if athletes else '(ไม่พบ token)'}")
    print(f"  ช่วง: {args.days} วันล่าสุด")
    print("=" * 60)

    if not athletes:
        print("⚠️  ไม่พบ token ใน tokens/ — ยังไม่มีใครให้ดึง")
        sys.exit(0)

    ok, failed = [], []
    for slug in athletes:
        print(f"\n▶ {slug}")
        # เพดานเวลา 20 นาที/คน (daily --days 3 ปกติเสร็จใน <1 นาที เพราะมี socket timeout 30 วิ
        # ใน 03_backfill) — กันเผื่อลูกกระบวนการค้าง ไม่ให้คนเดียวลากทั้งทีมค้างข้ามวัน
        try:
            proc = subprocess.run(
                [sys.executable, str(BACKFILL), "--athlete", slug, "--days", str(args.days)],
                cwd=str(PROJECT_ROOT),
                env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
                timeout=1200,
            )
            (ok if proc.returncode == 0 else failed).append(slug)
        except subprocess.TimeoutExpired:
            print(f"   ❌ {slug}: เกิน 20 นาที — ยกเลิกแล้วไปคนถัดไป")
            failed.append(slug)

    print("\n" + "=" * 60)
    print(f"  เสร็จ: {len(ok)} สำเร็จ ({', '.join(ok) or '-'})"
          f" | ล้มเหลว: {len(failed)} ({', '.join(failed) or '-'})")
    print("=" * 60)
    # exit code != 0 ถ้ามีคนล้มเหลว เพื่อให้ log/Task เห็นสถานะ
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
