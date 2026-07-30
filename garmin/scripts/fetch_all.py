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
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
import json
import os
import subprocess
import sys
import time
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
LOCK_FILE = PROJECT_ROOT / "data" / "sync.lock"


@contextmanager
def run_lock(timeout_seconds):
    """กัน fast/full/reconcile sync เขียน DB พร้อมกันข้าม Scheduled Task."""
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    handle = LOCK_FILE.open("a+b")
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()

    deadline = time.monotonic() + timeout_seconds
    acquired = False
    while True:
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
            break
        except OSError:
            if time.monotonic() >= deadline:
                break
            time.sleep(1)

    try:
        yield acquired
    finally:
        if acquired:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


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


def run_athlete(slug, args, passthrough, run_started):
    """รัน sync หนึ่งบัญชีและคืนผลแบบมาตรฐาน โดยไม่ให้ความล้มเหลวลามไปบัญชีอื่น."""
    print(f"\n▶ {slug}")
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
            return {"slug": slug, "ok": True, "reason": "ok",
                    "warnings": (status or {}).get("warnings", [])}
        reason = (status or {}).get("reason") or \
            ("token" if proc.returncode == 2 else "error")
        return {"slug": slug, "ok": False, "reason": reason, "warnings": []}
    except subprocess.TimeoutExpired:
        print(f"   ❌ {slug}: เกิน 20 นาที — ยกเลิกแล้ว")
        return {"slug": slug, "ok": False, "reason": "timeout", "warnings": []}
    except Exception as e:
        print(f"   ❌ {slug}: {type(e).__name__}: {e}")
        return {"slug": slug, "ok": False, "reason": "error", "warnings": []}


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
    parser.add_argument("--activities-only", action="store_true",
                        help="fast sync: ดึงเฉพาะ activity summary ล่าสุด")
    parser.add_argument("--max-workers", type=int, default=3,
                        help="จำนวนบัญชีที่ดึงพร้อมกัน (ค่าเริ่มต้น 3, ขั้นต่ำ 1)")
    parser.add_argument("--lock-timeout", type=int, default=600,
                        help="วินาทีที่รอ sync รอบอื่น (fast path ใช้ 0 แล้วข้าม)")
    args = parser.parse_args()
    if args.days < 0:
        parser.error("--days ต้องไม่น้อยกว่า 0")
    if args.max_workers < 1:
        parser.error("--max-workers ต้องไม่น้อยกว่า 1")
    if args.lock_timeout < 0:
        parser.error("--lock-timeout ต้องไม่น้อยกว่า 0")
    if args.activities_only and (args.skip_activities or args.reconcile):
        parser.error("--activities-only ใช้ร่วมกับ --skip-activities/--reconcile ไม่ได้")

    # ธงที่ส่งต่อให้ subprocess 03_backfill ต่อคน
    passthrough = []
    if args.skip_activities:
        passthrough.append("--skip-activities")
    if args.reconcile:
        passthrough.append("--reconcile")
    if args.activities_only:
        passthrough.append("--activities-only")

    athletes = [args.athlete] if args.athlete else list_athletes()

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("=" * 60)
    print(f"  FETCH ALL — {stamp}")
    print(f"  นักกีฬา: {', '.join(athletes) if athletes else '(ไม่พบ token)'}")
    _mode = "reconcile (เช็คกิจกรรมถูกลบ)" if args.reconcile else \
            ("fast activity summary" if args.activities_only else
             ("deep resync wellness (ข้ามกิจกรรม)" if args.skip_activities else "ปกติ"))
    print(f"  ช่วง: {args.days} วันล่าสุด | โหมด: {_mode}")
    print("=" * 60)

    if not athletes:
        print("⚠️  ไม่พบ token ใน tokens/ — ยังไม่มีใครให้ดึง")
        sys.exit(0)

    with run_lock(args.lock_timeout) as acquired:
        if not acquired:
            print("⏭️  มี Garmin sync อีกรอบทำงานอยู่ — ข้ามรอบนี้")
            sys.exit(75)

        # truncate microseconds เพราะไฟล์สถานะบันทึก finished_at ความละเอียดวินาที
        run_started = datetime.now().replace(microsecond=0)
        workers = min(args.max_workers, len(athletes))
        by_slug = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(run_athlete, slug, args, passthrough, run_started): slug
                for slug in athletes
            }
            for future in as_completed(futures):
                result = future.result()
                by_slug[result["slug"]] = result

        # คงลำดับ deterministic ตาม list_athletes แม้งานจบไม่พร้อมกัน
        results = [by_slug[slug] for slug in athletes]
        ok = [r["slug"] for r in results if r["ok"]]
        failed = [r["slug"] for r in results if not r["ok"]]

        # เขียน aggregate ก่อนปล่อย cross-task lock กันรอบถัดไปแข่งเขียนสถานะ
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
