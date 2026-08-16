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

Healthchecks.io (pilot เฉพาะสายนี้ — 6 ส.ค. 69): production อ่าน check URL จาก
DPAPI CurrentUser file ในโฟลเดอร์ data ก่อนเสมอ; env var HEALTHCHECK_BACKUP_URL เป็น fallback
ชั่วคราวสำหรับ migration/test เท่านั้น. รอบนี้ ping /start ตอนเริ่ม, URL เปล่าตอนสำเร็จ,
และ /fail ตอนล้มเหลว — ไม่ตั้งค่าไว้ = ไม่ ping. ping เป็น best-effort ล้วน ๆ และไม่มี
ทางเปลี่ยน exit code ของงาน backup หลัก
"""

import argparse
import json
import os
import shutil
import sqlite3
import sys
import urllib.request
from urllib.parse import urlsplit
from datetime import datetime
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent      # ...\garmin
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "garmin.db"
LANE_STATUS = DATA_DIR / "sync_lane" / "backup.json"
KEEP_DAILY = 7


def use_data_dir(path) -> Path:
    """ชี้ DB ต้นทางและสถานะ backup ไป data dir เดียวกัน แล้วคืนค่าเดิม.

    ปลายทางสำรองยังมาจาก ``--dest``/``--daily`` ตามเดิม; จุดฉีดนี้ครอบเฉพาะ
    ไฟล์ต้นทางที่เป็นของ Garmin pipeline เพื่อให้เทสและงานซ้อมไม่แตะข้อมูลจริง.
    """
    global DATA_DIR, DB_PATH, LANE_STATUS
    previous = DATA_DIR
    DATA_DIR = Path(path)
    DB_PATH = DATA_DIR / "garmin.db"
    LANE_STATUS = DATA_DIR / "sync_lane" / "backup.json"
    return previous


if os.environ.get("GARMIN_DATA_DIR"):
    use_data_dir(os.environ["GARMIN_DATA_DIR"])

# ── Healthchecks.io pilot (สาย backup เท่านั้น — 6 ส.ค. 69) ──────────────────
# ตรวจแค่ "Backup Task เริ่ม/จบ/ล้มเหลวตรงเวลาไหม" จากภายนอกเครื่อง — เสริมจาก
# sync_lane/backup.json ที่มีอยู่แล้ว (อันนั้นดูได้เฉพาะตอนเปิด dashboard เอง)
#
# กติกาที่ต้องคุ้มครองเสมอ (ห้ามฝ่าฝืน):
#   1) ห้ามส่งข้อมูลนักกีฬา/Garmin payload/token/path ภายใน/ข้อมูลสุขภาพออกไปเด็ดขาด —
#      ยิง GET เปล่า ๆ ไปที่ URL ใน DPAPI (หรือ migration env fallback) ไม่มี body/query
#   2) URL เป็น bearer secret: ผู้ที่รู้ค่าสามารถ spoof สถานะ backup ได้ จึงห้าม log หรือ
#      แสดงค่าเด็ดขาด — ข้อความที่พิมพ์บอกแค่ผลสำเร็จ/ไม่สำเร็จของการ ping
#   3) Healthchecks.io ล่ม/เน็ตขาด ต้องไม่ทำให้ backup ล้มตาม — ทุก error ในนี้ถูกกลืน
#      เงียบเสมอ ไม่มีทาง exception หลุดออกจากฟังก์ชันพวกนี้ได้เลย
#   4) ไม่เปลี่ยน exit code หลักของ backup_db.py — การ ping เป็นแค่ผลข้างเคียง (best-effort)
HEALTHCHECK_ENV_VAR = "HEALTHCHECK_BACKUP_URL"
HEALTHCHECK_TIMEOUT_SEC = 5
HEALTHCHECK_DPAPI_FILE = ".healthcheck-backup-url.dpapi"


def _dpapi_unprotect(ciphertext: bytes) -> str:
    """Decrypt a Windows DPAPI CurrentUser blob without spawning a shell."""
    if os.name != "nt":
        raise OSError("Windows DPAPI is unavailable")
    import ctypes
    from ctypes import wintypes

    class DataBlob(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
        ]

    raw = (ctypes.c_ubyte * len(ciphertext)).from_buffer_copy(ciphertext)
    input_blob = DataBlob(len(ciphertext), raw)
    output_blob = DataBlob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.POINTER(DataBlob),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    if not crypt32.CryptUnprotectData(
        ctypes.byref(input_blob), None, None, None, None, 0,
        ctypes.byref(output_blob),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        plaintext = ctypes.string_at(output_blob.pbData, output_blob.cbData)
        return plaintext.decode("utf-8")
    finally:
        kernel32.LocalFree(output_blob.pbData)


def get_healthcheck_url() -> str:
    """Resolve the URL from process env or a CurrentUser-DPAPI protected file."""
    if os.name == "nt":
        secret_path = DATA_DIR / HEALTHCHECK_DPAPI_FILE
        try:
            protected = _dpapi_unprotect(secret_path.read_bytes()).strip()
            if protected:
                return protected
        except Exception:
            pass
    return os.environ.get(HEALTHCHECK_ENV_VAR, "").strip()


def _valid_healthcheck_url(url: str) -> bool:
    """Allow only credential-like HTTPS path URLs without side channels."""
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and parsed.query == ""
            and parsed.fragment == ""
            and parsed.port in (None, 443)
        )
    except (TypeError, ValueError):
        return False


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

    อ่าน DPAPI CurrentUser file ทุกครั้งก่อน แล้วจึง fallback ไป env สำหรับ migration/test
    — ไม่พบทั้งคู่ = เงียบ ข้ามไปเฉย ๆ ไม่ error/ไม่ print
    """
    try:
        base = get_healthcheck_url()
        if not base:
            return
        if not _valid_healthcheck_url(base):
            print("   ⚠️  healthcheck config ไม่ปลอดภัย/ผิดรูปแบบ (ต้องเป็น HTTPS)")
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
    src = Path(src)
    dest = Path(dest)
    if not src.is_file():
        raise FileNotFoundError(f"ไม่พบฐานข้อมูลต้นทาง: {src}")
    if src.resolve() == dest.resolve():
        raise ValueError("ต้นทางและปลายทาง garmin.db ต้องเป็นคนละไฟล์")

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".db.tmp")
    tmp.unlink(missing_ok=True)

    source_uri = src.resolve().as_uri() + "?mode=rw"
    source = sqlite3.connect(source_uri, uri=True, timeout=60)
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
    tmp = today.with_suffix(".db.tmp")
    tmp.unlink(missing_ok=True)
    try:
        shutil.copyfile(snapshot_path, tmp)
        check = sqlite3.connect(str(tmp))
        try:
            if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("สำเนารายวัน integrity_check ไม่ผ่าน")
        finally:
            check.close()
        tmp.replace(today)
    finally:
        tmp.unlink(missing_ok=True)

    # Delete old generations only after today's verified file is atomically visible.
    # ต้องลบ sidecar ของ WAL (-wal/-shm) ไปพร้อมกันด้วย: ทุกครั้งที่มีใครเปิดสำเนา
    # ตรวจ (validate/quick_check ของ health report และ offsite backup) SQLite จะสร้าง
    # `-shm` ทิ้งไว้ข้างไฟล์ — ถ้าลบแต่ `.db` ไฟล์กำพร้าจะกองสะสมไปเรื่อย ๆ ตลอดกาล
    # (เจอจริง 16 ส.ค. 69: เหลือ sidecar ของ 4–7 ส.ค. ทั้งที่ .db ถูกหมุนทิ้งไปแล้ว)
    for old in sorted(daily_dir.glob("garmin-*.db"))[:-KEEP_DAILY]:
        for path in (old, *daily_dir.glob(f"{old.name}-*")):
            path.unlink(missing_ok=True)


def write_status(run_at: datetime, ok: bool, reason: str, warnings: list) -> bool:
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
        return True
    except Exception as e:
        print(f"⚠️  เขียน backup.json ไม่สำเร็จ: {e}")
        return False


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
        warnings.append(
            f"robocopy mirror ล้มเหลว (exit {args.robocopy_exit}) — "
            "ดู C:\\Backup\\run-performance-logs\\backup-log.txt"
        )

    print(f"📦 สำรอง {DB_PATH} → {dest_dir}")
    try:
        rows = snapshot(DB_PATH, dest_dir / "garmin.db")
    except Exception as e:
        print(f"❌ สำรอง garmin.db ไม่สำเร็จ: {e}")
        write_status(run_at, False, "db", warnings + [str(e)])
        notify_healthcheck("fail")  # ผลสุดท้ายของรอบนี้ — จบตรงนี้ ไม่ส่งซ้ำที่ปลายฟังก์ชันอีก
        return 1

    print(f"   ✅ garmin.db snapshot สำเร็จ ({rows} กิจกรรม)")
    daily_ok = True
    if args.daily:
        try:
            rotate_daily(Path(args.daily), dest_dir / "garmin.db")
            print(f"   ✅ สำเนารายวัน → {args.daily} (เก็บ {KEEP_DAILY} ชุดล่าสุด)")
        except Exception as e:
            daily_ok = False
            warnings.append(f"หมุนสำเนารายวันไม่สำเร็จ: {e}")
            print(f"   ❌ {warnings[-1]}")

    # A configured daily generation is part of the backup contract, not a warning:
    # reporting external success would otherwise hide the loss of restore history.
    ok = args.robocopy_exit < 8 and daily_ok
    reason = "ok" if ok else ("robocopy" if args.robocopy_exit >= 8 else "daily")
    status_written = write_status(run_at, ok, reason, warnings)
    if not status_written:
        ok = False
    notify_healthcheck("success" if ok else "fail")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
