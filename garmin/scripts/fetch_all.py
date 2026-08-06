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

exit code: 0 = ครบทุกคน | 1 = มีคนล้มเหลว | 75 = ข้ามรอบนี้ตั้งใจ (sync อื่นถือ lock อยู่
หรือช่องเวลาของ --catch-up-slots ทำไปแล้ว) — 75 ไม่ใช่ความล้มเหลว bat จึงไม่ต้องเตือน
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
import json
import os
import subprocess
import sys
import time
from datetime import datetime, time as dtime, timedelta
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
# สถานะรอบล่าสุด "แยกตามสายงาน" — จำเป็นตั้งแต่มีหลายสาย (full/fast/wellness) เพราะทุกสาย
# เขียน sync_status.json ทับกัน: full sync 21:00 ล้มแล้ว wellness 21:08 ผ่าน จะกลบร่องรอยหมด
LANE_STATUS_DIR = PROJECT_ROOT / "data" / "sync_lane"
# เพดานเวลาต่อคน: สายถี่ต้องยอมแพ้เร็ว ไม่งั้นคนที่ค้างจะกอด sync.lock ไว้จนสายอื่นอดทั้งชั่วโมง
# (Task ของสายถี่ถูก Windows ฆ่าที่ 10/20 นาทีอยู่แล้ว — ตัดเองก่อนดีกว่าโดนฆ่ากลางเขียน DB)
ATHLETE_TIMEOUT_SEC = {"fast": 240, "wellness": 300}
DEFAULT_ATHLETE_TIMEOUT_SEC = 1200
# หน้าต่างตามเก็บช่องเวลาย้อนหลังของ --catch-up-slots: ช่องที่ค้างเกิน 48 ชม. ถือว่าหมดอายุ
# ข้อมูลของช่องนั้นถูกรอบถัดไปกวาดครอบไปแล้วด้วย --days อยู่ดี ตามเก็บย้อนไกลกว่านี้ไม่ได้อะไร
# เพิ่ม แถมทำให้ log อ่านไม่รู้เรื่อง (เครื่องปิดยาว 2 สัปดาห์แล้วโชว์ช่องค้าง 28 ช่อง)
CATCH_UP_LOOKBACK_HOURS = 48


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


def parse_slots(raw: str) -> list[dtime]:
    """แปลง "08:00,21:00" เป็น list ของเวลา (ช่องเวลาที่ full sync ควรได้รันวันละครั้ง)."""
    slots = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        hh, _, mm = chunk.partition(":")
        slots.append(dtime(int(hh), int(mm or 0)))
    if not slots:
        raise ValueError("ต้องมีอย่างน้อย 1 ช่องเวลา")
    return sorted(slots)


def passed_slots(slots: list[dtime], now: datetime,
                 lookback_hours: int = CATCH_UP_LOOKBACK_HOURS) -> list[datetime]:
    """ช่องเวลาที่ "ผ่านมาแล้ว" ทั้งหมดในหน้าต่างตามเก็บ เรียงเก่า→ใหม่.

    ต้องกวาดหลายวัน ไม่ใช่แค่ของวันนี้ — เครื่องหลับข้ามคืนแล้วตื่นสายวันรุ่งขึ้น
    ช่องที่ค้างอยู่คือช่องของ "เมื่อวาน" ซึ่งมองไม่เห็นเลยถ้าดูแค่ปฏิทินวันนี้
    """
    earliest = now - timedelta(hours=lookback_hours)
    out = []
    day = earliest.date()
    while day <= now.date():
        out.extend(datetime.combine(day, s) for s in slots)
        day += timedelta(days=1)
    return sorted(c for c in out if earliest <= c <= now)


def pending_slots(lane: str, slots: list[dtime], now: datetime,
                  lookback_hours: int = CATCH_UP_LOOKBACK_HOURS) -> list[datetime]:
    """ช่องที่ยัง "ค้าง" = ผ่านมาแล้วแต่ไม่มีรอบของสายนี้เดินหลังจากนั้น.

    ใช้ทำ catch-up: ตั้ง Task ให้ยิงทุกชั่วโมงได้เลย แล้วให้ตัวนี้ตัดสินว่ารอบไหนของจริง
    → เครื่องหลับตอน 08:00 แล้วตื่น 09:40 ก็ยังได้ full sync ของช่อง 08:00 ไม่ข้ามทั้งวัน
    (พึ่ง StartWhenAvailable ของ Windows อย่างเดียวไม่พอ — ยิงครั้งเดียว พลาดแล้วพลาดเลย)

    "ทำสำเร็จแล้ว" ตัดสินจาก run_at ของสาย: รอบที่เดินหลังช่องไหน = ครอบช่องนั้นไปแล้ว
    (รอบเดียวครอบได้หลายช่องที่ค้าง เพราะ --days ดึงย้อนคลุมอยู่แล้ว — ไล่รันทีละช่อง
    คือยิง API ซ้ำฟรี) จึงไม่มีทางรันช่องเดิมซ้ำสองครั้ง
    """
    candidates = passed_slots(slots, now, lookback_hours)
    try:
        data = json.loads((LANE_STATUS_DIR / f"{lane}.json").read_text(encoding="utf-8"))
        last_run = datetime.fromisoformat(data["run_at"])
    except Exception:
        # ไม่เคยรัน/ไฟล์เสีย → ถือว่าค้างทั้งหมด ให้รันเลย
        return candidates or [now]
    return [c for c in candidates if c > last_run]


def slot_already_done(lane: str, slots: list[dtime], now: datetime,
                      lookback_hours: int = CATCH_UP_LOOKBACK_HOURS) -> datetime | None:
    """คืนเวลาช่องล่าสุดถ้าไม่มีช่องค้างแล้ว (= ข้ามรอบนี้), คืน None ถ้ายังมีค้าง (= ต้องรัน)."""
    if pending_slots(lane, slots, now, lookback_hours):
        return None
    candidates = passed_slots(slots, now, lookback_hours)
    return candidates[-1] if candidates else None


def run_athlete(slug, args, passthrough, run_started, timeout_sec):
    """รัน sync หนึ่งบัญชีและคืนผลแบบมาตรฐาน โดยไม่ให้ความล้มเหลวลามไปบัญชีอื่น."""
    print(f"\n▶ {slug}")
    try:
        proc = subprocess.run(
            [sys.executable, str(BACKFILL), "--athlete", slug,
             "--days", str(args.days), *passthrough],
            cwd=str(PROJECT_ROOT),
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
            timeout=timeout_sec,
        )
        status = read_athlete_status(slug, run_started)
        if proc.returncode == 0:
            return {"slug": slug, "ok": True, "reason": "ok",
                    "warnings": (status or {}).get("warnings", [])}
        reason = (status or {}).get("reason") or \
            ("token" if proc.returncode == 2 else "error")
        return {"slug": slug, "ok": False, "reason": reason, "warnings": []}
    except subprocess.TimeoutExpired:
        print(f"   ❌ {slug}: เกิน {timeout_sec // 60} นาที — ยกเลิกแล้ว")
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
                        help="fast sync: ดึง activity summary ล่าสุด + splits ที่ยังขาด")
    parser.add_argument("--wellness-fast", action="store_true",
                        help="fast wellness: ดึงเฉพาะค่าที่ขยับระหว่างวัน "
                             "(body battery/RHR/stress/HRV/นอน/readiness) ไม่แตะกิจกรรม/extras")
    parser.add_argument("--max-workers", type=int, default=3,
                        help="จำนวนบัญชีที่ดึงพร้อมกัน (ค่าเริ่มต้น 3, ขั้นต่ำ 1)")
    parser.add_argument("--lock-timeout", type=int, default=600,
                        help="วินาทีที่รอ sync รอบอื่น (fast path ใช้ 0 แล้วข้าม)")
    parser.add_argument("--catch-up-slots", default=None, metavar="HH:MM,HH:MM",
                        help="รันเฉพาะเมื่อ 'ช่องเวลาล่าสุดที่ผ่านมา' ยังไม่มีรอบของสายนี้เดิน "
                             "(เช่น 08:00,21:00) — ตั้ง Task ให้ยิงถี่ ๆ ได้ แล้วรอบส่วนเกิน "
                             "จะข้ามเอง (exit 75). ใช้ตาม missed run ตอนเครื่องหลับ/ปิด")
    args = parser.parse_args()
    if args.days < 0:
        parser.error("--days ต้องไม่น้อยกว่า 0")
    if args.max_workers < 1:
        parser.error("--max-workers ต้องไม่น้อยกว่า 1")
    if args.lock_timeout < 0:
        parser.error("--lock-timeout ต้องไม่น้อยกว่า 0")
    slots = None
    if args.catch_up_slots:
        try:
            slots = parse_slots(args.catch_up_slots)
        except ValueError as e:
            parser.error(f"--catch-up-slots ผิดรูปแบบ (ต้องเป็น HH:MM คั่นด้วย ,): {e}")
    # ธงที่ส่งต่อให้ subprocess 03_backfill ต่อคน (ใช้ร่วมกันไม่ได้ — โหมดละสายงาน)
    passthrough = [flag for flag, on in (
        ("--skip-activities", args.skip_activities),
        ("--reconcile", args.reconcile),
        ("--activities-only", args.activities_only),
        ("--wellness-fast", args.wellness_fast),
    ) if on]
    if len(passthrough) > 1:
        parser.error(f"ใช้ร่วมกันไม่ได้: {', '.join(passthrough)}")

    athletes = [args.athlete] if args.athlete else list_athletes()

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lane, _mode = (
        ("reconcile", "reconcile (เช็คกิจกรรมถูกลบ)") if args.reconcile else
        ("fast", "fast activity + missing splits") if args.activities_only else
        ("wellness", "fast wellness (ค่าที่ขยับระหว่างวัน)") if args.wellness_fast else
        ("deep", "deep resync wellness (ข้ามกิจกรรม)") if args.skip_activities else
        ("full", "ปกติ")
    )
    print("=" * 60)
    print(f"  FETCH ALL — {stamp}")
    print(f"  นักกีฬา: {', '.join(athletes) if athletes else '(ไม่พบ token)'}")
    print(f"  ช่วง: {args.days} วันล่าสุด | โหมด: {_mode}")
    print("=" * 60)

    if not athletes:
        print("⚠️  ไม่พบ token ใน tokens/ — ยังไม่มีใครให้ดึง")
        sys.exit(0)

    # เช็คก่อนแย่ง lock: ถ้าไม่มีช่องเวลาไหนค้าง รอบนี้เป็นรอบส่วนเกินของ Task รายชั่วโมง
    if slots is not None:
        now = datetime.now()
        pending = pending_slots(lane, slots, now)
        if not pending:
            done_at = passed_slots(slots, now)[-1]
            print(f"⏭️  ช่อง {done_at:%H:%M} ({done_at:%d/%m}) sync ไปแล้ว — ข้ามรอบนี้")
            sys.exit(75)
        # บอกให้ชัดว่ารอบนี้กำลังตามเก็บของค้าง ไม่ใช่รอบตามตารางปกติ — ไม่งั้นเวลาไล่ log
        # ย้อนหลังจะแยกไม่ออกว่า "ช่อง 21:00 หายไปไหน" กับ "ช่อง 21:00 ถูกกวาดรวมมาแล้ว"
        if len(pending) > 1 or pending[0].date() != now.date():
            print("⏰ ตามเก็บช่องที่ค้างไว้: "
                  + ", ".join(f"{p:%d/%m %H:%M}" for p in pending)
                  + " — รอบนี้รอบเดียวครอบให้ทั้งหมด")

    with run_lock(args.lock_timeout) as acquired:
        if not acquired:
            print("⏭️  มี Garmin sync อีกรอบทำงานอยู่ — ข้ามรอบนี้")
            sys.exit(75)

        # truncate microseconds เพราะไฟล์สถานะบันทึก finished_at ความละเอียดวินาที
        run_started = datetime.now().replace(microsecond=0)
        workers = min(args.max_workers, len(athletes))
        athlete_timeout = ATHLETE_TIMEOUT_SEC.get(lane, DEFAULT_ATHLETE_TIMEOUT_SEC)
        by_slug = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(run_athlete, slug, args, passthrough,
                            run_started, athlete_timeout): slug
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
        payload = json.dumps({
            "run_at": run_started.isoformat(timespec="seconds"),
            "days": args.days,
            "lane": lane,
            "mode": _mode,
            "results": results,
        }, ensure_ascii=False, indent=1)
        # ไฟล์รวม (notify + dashboard อ่าน) + สำเนาแยกสายงาน (dashboard โชว์ว่าสายไหน
        # เดินล่าสุดเมื่อไหร่ — สายที่ล้มจะไม่ถูกสายอื่นที่ผ่านมาทับจนมองไม่เห็น)
        for target in (STATUS_FILE, LANE_STATUS_DIR / f"{lane}.json"):
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_suffix(".json.tmp")
                tmp.write_text(payload, encoding="utf-8")
                tmp.replace(target)
            except Exception as e:
                print(f"⚠️  เขียน {target.name} ไม่สำเร็จ: {e}")

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
