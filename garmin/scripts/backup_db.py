#!/usr/bin/env python3
"""สำรอง garmin.db แบบ "อ่านได้จริง" + เขียนสถานะสาย backup ให้ระบบเตือนเห็น

ทำไมต้องมีไฟล์นี้ (แทนที่จะปล่อยให้ robocopy copy garmin.db ไปเฉย ๆ)
--------------------------------------------------------------------
garmin.db เป็น WAL mode ถาวร → งานเขียนไปกองอยู่ใน sidecar `garmin.db-wal`
ตัวไฟล์หลักจะขยับก็ต่อเมื่อมี checkpoint. robocopy มองเห็นแค่ "ไฟล์ไม่เปลี่ยน
ขนาด/เวลาเท่าเดิม" แล้ว **ข้าม** → สำเนาที่ได้คือ DB ณ checkpoint ล่าสุด
โดยไม่มี -wal ติดไปด้วย = ข้อมูลหลายวันหายไปจากไฟล์สำรองแบบเงียบสนิท
(เจอจริง 4 ส.ค. 69: สำเนาใน C:\\Backup ค้างอยู่ที่ 2 ส.ค. 21:50 ทั้งที่ backup
รันทุกคืน — และนี่คือสำเนาเดียวของข้อมูลสุขภาพทั้งทีม เพราะ data\\ ถูก git ignore)

sqlite3 backup API อ่านผ่าน connection จริง → ได้ภาพที่ merge WAL แล้ว
consistent แม้ dashboard เปิดค้าง/sync กำลังเขียนอยู่ ไม่ต้องหยุดอะไรเลย

นอกจากนี้ยังหมุนสำเนารายวันเก็บไว้ 7 ชุด — สำเนาชุดเดียวที่ถูกทับทุกคืน
แปลว่า DB เสียหาย 1 คืนแล้วไม่มีใครทันสังเกต = สำเนาดี ๆ ถูกทับหายไปด้วย

วิธีใช้ (เรียกจาก สำรองข้อมูล.bat หลัง robocopy):
    python scripts/backup_db.py --dest "C:\\Backup\\Run-Performance\\garmin\\data" \\
        --robocopy-exit %ROBO_EXIT%

exit code: 0 = สำเร็จ | 1 = สำรองไม่สำเร็จ (bat จะเรียก notify ให้เด้ง toast)

Healthchecks.io (pilot เฉพาะสายนี้ — 6 ส.ค. 69): ตั้ง env var HEALTHCHECK_BACKUP_URL
เป็น check URL ของ Healthchecks.io แล้วรอบนี้จะ ping /start ตอนเริ่ม, ping URL เปล่า
ตอนสำเร็จ, ping /fail ตอนล้มเหลว — ไม่ตั้งค่าไว้ = ไม่ ping เลย (เงียบ ไม่ error)
ping เป็น best-effort ล้วน ๆ ไม่มีทางเปลี่ยน exit code ข้างต้นได้
"""

import argparse
import json
import os
import sqlite3
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent      # ...\garmin
DB_PATH = PROJECT_ROOT / "data" / "garmin.db"
LANE_STATUS = PROJECT_ROOT / "data" / "sync_lane" / "backup.json"
KEEP_DAILY = 7

# ── Healthchecks.io pilot (สาย backup เท่านั้น — 6 ส.ค. 69) ──────────────────
# ตรวจแค่ "Backup Task เริ่ม/จบ/ล้มเหลวตรงเวลาไหม" จากภายนอกเครื่อง — เสริมจาก
# sync_lane/backup.json ที่มีอยู่แล้ว (อันนั้นดูได้เฉพาะตอนเปิด dashboard เอง)
#
# กติกาที่ต้องคุ้มครองเสมอ (ห้ามฝ่าฝืน):
#   1) ห้ามส่งข้อมูลนักกีฬา/Garmin payload/token/path ภายใน/ข้อมูลสุขภาพออกไปเด็ดขาด —
#      ยิง GET เปล่า ๆ ไปที่ URL ที่ผู้ใช้ตั้งเองผ่าน env var เท่านั้น ไม่มี body/query
#   2) ห้าม log หรือแสดง URL เอง (ผู้ใช้เป็นคนตั้งค่าเอง ไม่ใช่ความลับของเรา แต่ก็ไม่มี
#      เหตุผลต้องพิมพ์ซ้ำ) — ข้อความที่พิมพ์บอกแค่ผลสำเร็จ/ไม่สำเร็จของการ ping
#   3) Healthchecks.io ล่ม/เน็ตขาด ต้องไม่ทำให้ backup ล้มตาม — ทุก error ในนี้ถูกกลืน
#      เงียบเสมอ ไม่มีทาง exception หลุดออกจากฟังก์ชันพวกนี้ได้เลย
#   4) ไม่เปลี่ยน exit code หลักของ backup_db.py — การ ping เป็นแค่ผลข้างเคียง (best-effort)
HEALTHCHECK_ENV_VAR = "HEALTHCHECK_BACKUP_URL"
HEALTHCHECK_TIMEOUT_SEC = 5


def _healthcheck_ping(url: str, timeout: float = HEALTHCHECK_TIMEOUT_SEC) -> bool:
    """ยิง HTTP GET เปล่า ๆ ไปที่ url หนึ่งครั้ง — best-effort ล้วน ๆ

    ไม่มี body/query/header พิเศษใด ๆ ที่มีข้อมูลของระบบเราติดไปด้วย และไม่มีทางที่
    exception (timeout/DNS/connection refused/HTTP error ฯลฯ) จะหลุดออกจากฟังก์ชันนี้
    ได้เลย — คืน True/False ไว้ให้ผู้เรียกพิมพ์สถานะเฉย ๆ ไม่ได้ใช้ตัดสินอะไรต่อ
    """
    try:
        with urllib.request.urlopen(url, timeout=timeout):
            pass
        return True
    except Exception:
        return False


def notify_healthcheck(kind: str) -> None:
    """ping Healthchecks.io ของสาย backup — kind: "start" | "success" | "fail"

    อ่าน URL จาก env var ทุกครั้งที่เรียก (ไม่ใช่ค่าคงที่ตอน import) เพื่อให้เทส inject
    ผ่าน os.environ ได้ตรง ๆ — ไม่ตั้ง env var ไว้ = เงียบ ข้ามไปเฉย ๆ ไม่ error/ไม่ print
    """
    try:
        base = os.environ.get(HEALTHCHECK_ENV_VAR, "").strip()
        if not base:
            return
        base = base.rstrip("/")
        suffix = {"start": "/start", "fail": "/fail", "success": ""}.get(kind, "")
        ok = _healthcheck_ping(base + suffix)
        icon = "✅" if ok else "⚠️ "
        status = "ส่งสำเร็จ" if ok else "ส่งไม่สำเร็จ (ไม่กระทบผลของ backup)"
        print(f"   {icon} healthcheck ping ({kind}): {status}")
    except Exception:
        # ชั้นป้องกันสุดท้าย — ห้ามให้การแจ้งเตือนภายนอกทำให้ backup ล้มตามเด็ดขาด
        pass


def snapshot(src: Path, dest: Path) -> int:
    """คัดลอก DB ผ่าน sqlite3 backup API — ได้ภาพที่รวม WAL แล้วและไม่ฉีกกลางธุรกรรม

    เปิดต้นทางแบบปกติ (ไม่ใช่ mode=ro) ตั้งใจ: DB เป็น WAL — connection แบบ read-only
    ต้องสร้าง/แมป sidecar -shm ให้ได้ ไม่งั้นเด้ง "unable to open database file"
    เราเขียนโฟลเดอร์นั้นได้อยู่แล้ว และคำสั่งในนี้อ่านอย่างเดียวล้วน
    ต้องปิด connection ให้ครบก่อน replace เสมอ — Windows ไม่ให้ rename ไฟล์ที่ยังเปิดค้าง
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".db.tmp")
    tmp.unlink(missing_ok=True)

    source = sqlite3.connect(str(src), timeout=60)
    try:
        target = sqlite3.connect(str(tmp))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()

    # สำเนาที่เปิดไม่ได้แย่กว่าไม่มีสำเนา — ตรวจก่อนเอาไปทับของเดิม
    check = sqlite3.connect(str(tmp))
    try:
        if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("สำเนาที่ได้ integrity_check ไม่ผ่าน")
        rows = check.execute("SELECT count(*) FROM fact_activity").fetchone()[0]
    finally:
        check.close()

    tmp.replace(dest)
    return rows


def rotate_daily(daily_dir: Path, snapshot_path: Path) -> None:
    """เก็บสำเนารายวันไว้ KEEP_DAILY ชุด (ไฟล์เล็กมาก ~1MB ต่อชุด)

    ต้องอยู่ "นอก" โฟลเดอร์ที่ robocopy /MIR ดูแล ไม่งั้นรอบถัดไปจะเห็นเป็นโฟลเดอร์ส่วนเกิน
    แล้วลบทิ้งให้ทุกคืน (mirror = ปลายทางต้องเหมือนต้นทางเป๊ะ)
    """
    daily_dir.mkdir(parents=True, exist_ok=True)
    today = daily_dir / f"garmin-{datetime.now():%Y%m%d}.db"
    today.write_bytes(snapshot_path.read_bytes())
    old = sorted(daily_dir.glob("garmin-*.db"))[:-KEEP_DAILY]
    for f in old:
        f.unlink(missing_ok=True)


def write_status(run_at: datetime, ok: bool, reason: str, warnings: list) -> None:
    """รูปแบบเดียวกับที่ fetch_all.py เขียน — dashboard/notify_sync อ่านไฟล์เดียวกันได้เลย
    (slug ใช้ชื่อสายแทนชื่อนักกีฬา เพราะสายนี้ไม่ได้แยกรายคน)"""
    payload = json.dumps({
        "run_at": run_at.isoformat(timespec="seconds"),
        "days": 0,
        "lane": "backup",
        "mode": "robocopy + sqlite snapshot",
        "results": [{"slug": "สำรองข้อมูล", "ok": ok, "reason": reason, "warnings": warnings}],
    }, ensure_ascii=False, indent=1)
    try:
        LANE_STATUS.parent.mkdir(parents=True, exist_ok=True)
        tmp = LANE_STATUS.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(LANE_STATUS)
    except Exception as e:
        print(f"⚠️  เขียน backup.json ไม่สำเร็จ: {e}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", required=True, help=r"โฟลเดอร์ปลายทาง เช่น C:\Backup\Run-Performance\garmin\data")
    ap.add_argument("--daily", default="", help=r"โฟลเดอร์เก็บสำเนารายวัน (ต้องอยู่นอกเงา robocopy /MIR)")
    ap.add_argument("--robocopy-exit", type=int, default=0,
                    help="exit code ของ robocopy (>=8 = mirror มีปัญหา) — รวมเข้าสถานะสายเดียวกัน")
    args = ap.parse_args()

    # ping "เริ่มงาน" จุดเดียวต่อรอบ ก่อนทำงานจริงใด ๆ — best-effort ล้วน ไม่กระทบ flow ต่อไป
    notify_healthcheck("start")

    run_at = datetime.now()
    dest_dir = Path(args.dest)
    warnings = []

    # robocopy: 0-7 = ปกติ (0 ไม่มีอะไรเปลี่ยน, 1 คัดลอกแล้ว, 2/4 มี extra/mismatch) | >=8 = ล้มเหลว
    if args.robocopy_exit >= 8:
        warnings.append(f"robocopy mirror ล้มเหลว (exit {args.robocopy_exit}) — ดู C:\\Backup\\backup-log.txt")

    print(f"📦 สำรอง {DB_PATH} → {dest_dir}")
    try:
        rows = snapshot(DB_PATH, dest_dir / "garmin.db")
    except Exception as e:
        print(f"❌ สำรอง garmin.db ไม่สำเร็จ: {e}")
        write_status(run_at, False, "db", warnings + [str(e)])
        notify_healthcheck("fail")  # ผลสุดท้ายของรอบนี้ — จบตรงนี้ ไม่ส่งซ้ำที่ปลายฟังก์ชันอีก
        return 1

    print(f"   ✅ garmin.db snapshot สำเร็จ ({rows} กิจกรรม)")
    if args.daily:
        try:
            rotate_daily(Path(args.daily), dest_dir / "garmin.db")
            print(f"   ✅ สำเนารายวัน → {args.daily} (เก็บ {KEEP_DAILY} ชุดล่าสุด)")
        except Exception as e:
            # หมุนไฟล์รายวันพลาดไม่ใช่เรื่องคอขาดบาดตาย — สำเนาหลักได้แล้ว บอกไว้เฉย ๆ
            # (ไม่กระทบเกณฑ์ success/fail ของ healthcheck — snapshot+verification+robocopy
            # ผ่านครบคือเกณฑ์เดียว ตามที่ตกลงไว้)
            warnings.append(f"หมุนสำเนารายวันไม่สำเร็จ: {e}")
            print(f"   ⚠️  {warnings[-1]}")

    # success/fail ที่นี่คือ "ผลสุดท้ายของรอบ" จุดเดียว (snapshot+verification ผ่านแล้ว
    # จากด้านบน เหลือแค่ตัดสินจาก robocopy) — ไม่มีทางถูกเรียกซ้ำกับ path ข้างบน
    ok = args.robocopy_exit < 8
    write_status(run_at, ok, "ok" if ok else "robocopy", warnings)
    notify_healthcheck("success" if ok else "fail")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
