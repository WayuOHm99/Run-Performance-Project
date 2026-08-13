#!/usr/bin/env python3
"""health_report.py — ตรวจ 6 sync lanes + off-site durability แบบ READ-ONLY เท่านั้น

กฎเหล็ก (ห้ามฝ่าฝืนแม้แต่บรรทัดเดียว):
  - ห้ามเขียนหรือแก้ garmin.db (เปิดแบบ mode=ro เท่านั้น)
  - ห้ามเขียน status/marker ไฟล์ใด ๆ ใน data\\ (อ่านอย่างเดียว)
  - ห้าม restart หรือ "ซ่อม" อะไรทั้งสิ้น — เป็นเครื่องมือรายงาน ไม่ใช่เครื่องมือแก้ปัญหา
  - ห้ามแก้ Scheduled Task ใด ๆ (query อย่างเดียวผ่าน schtasks)
  - แสดงผลทาง stdout เท่านั้น ไม่เขียนไฟล์ผลลัพธ์ลงดิสก์

ใช้:
    garmin\\.venv\\Scripts\\python.exe scripts\\health_report.py
    garmin\\.venv\\Scripts\\python.exe scripts\\health_report.py --json

Path override (ไม่ต้องแก้โค้ด):
    GARMIN_DATA_DIR    ค่าเริ่มต้น garmin\\data (ตรงกับ fetch_all.py/03_backfill.py)
    GARMIN_BACKUP_DIR  ค่าเริ่มต้น C:\\Backup\\garmin-db-daily (ตรงกับ สำรองข้อมูล.bat)

exit code: 0 = ไม่มี ERROR (อาจมี WARNING) | 1 = พบ ERROR อย่างน้อย 1 จุด
"""

import argparse
import ast
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:  # ``python scripts/health_report.py``
    import data_quality as dq
except ModuleNotFoundError:  # loaded directly by importlib from any cwd
    _dq_spec = importlib.util.spec_from_file_location(
        "garmin_data_quality", Path(__file__).with_name("data_quality.py")
    )
    dq = importlib.util.module_from_spec(_dq_spec)
    _dq_spec.loader.exec_module(dq)

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # ...\garmin
ACL_SCRIPT = PROJECT_ROOT.parent / "scripts" / "harden_private_acl.ps1"
HEALTHCHECK_ENV_VAR = "HEALTHCHECK_BACKUP_URL"
HEALTHCHECK_DPAPI_FILE = ".healthcheck-backup-url.dpapi"

# ⚠️ path ที่ "อ่านได้" ต้องแตกจาก DATA_DIR/BACKUP_DIR เดียว — pattern เดียวกับ
# fetch_all.py (use_data_dir) กัน CI/เทสอ่านผิดโฟลเดอร์ (เทสนี้ไม่เขียนอะไรอยู่แล้ว
# แต่การแตก path รวมที่เดียวทำให้ mock/ย้ายทั้งชุดในเทสไม่มีจุดตกหล่นเหมือนบทเรียน 6 ส.ค. 69)
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "garmin.db"
BACKUP_DIR = Path(r"C:\Backup\garmin-db-daily")


def use_data_dir(path) -> Path:
    global DATA_DIR, DB_PATH
    previous = DATA_DIR
    DATA_DIR = Path(path)
    DB_PATH = DATA_DIR / "garmin.db"
    return previous


def use_backup_dir(path) -> Path:
    global BACKUP_DIR
    previous = BACKUP_DIR
    BACKUP_DIR = Path(path)
    return previous


if os.environ.get("GARMIN_DATA_DIR"):
    use_data_dir(os.environ["GARMIN_DATA_DIR"])
if os.environ.get("GARMIN_BACKUP_DIR"):
    use_backup_dir(os.environ["GARMIN_BACKUP_DIR"])


# ── Datetime normalization (แก้ 6 ส.ค. 69 — crash จริงบน Windows) ────────────────
# ต้นเหตุ: marker เขียนโดย prep_log.ps1 ด้วย (Get-Date).ToString("o") ซึ่งเป็น
# ISO 8601 "แบบมี timezone offset" (เช่น 2026-08-06T08:14:22.1234567+07:00) ส่วน
# run_at ใน sync_lane/*.json เขียนโดย Python ด้วย datetime.now().isoformat() ซึ่ง
# เป็น naive (ไม่มี offset) — เทียบ aware กับ naive ตรง ๆ ทำให้ TypeError ทันที
#
# ทางแก้ที่ถูกต้อง: normalize ทุก datetime ให้เป็น "aware ใน UTC" ก่อนเทียบเสมอ
# ผ่านจุดเดียว (_to_utc) ห้ามลบ tzinfo ทิ้ง (dt.replace(tzinfo=None)) เพราะจะได้
# เลขนาฬิกาเดิมที่ตีความผิดโซนเวลา เทียบกันแล้วคลาดหลายชั่วโมงแบบเงียบ ๆ
#
# datetime.astimezone(tz) ของ Python มีพฤติกรรมตรงตามที่ต้องการอยู่แล้ว (มาตรฐาน
# มาตั้งแต่ 3.6): ถ้า self มี tzinfo อยู่แล้ว -> แปลงเป็น tz เป้าหมายตรง ๆ (เคารพ
# โซนเวลาเดิม) | ถ้า self เป็น naive -> "ถือว่าเป็นเวลาท้องถิ่นของเครื่องนี้" ตาม
# platform แล้วค่อยแปลงเป็น tz เป้าหมาย — ตรงกับกติกาที่ต้องการเป๊ะทั้งสองเงื่อนไข
def _to_utc(dt):
    if dt is None:
        return None
    return dt.astimezone(timezone.utc)


def _fmt_local(dt) -> str:
    """แปลงกลับเป็นเวลาท้องถิ่นสำหรับแสดงผลให้คนอ่าน (เทียบ/คำนวณใช้ UTC เสมอ
    แต่ข้อความที่โชว์บนจอควรเป็นเวลาที่คนดูอ่านคุ้นตา ไม่ใช่ UTC ดิบ)"""
    if dt is None:
        return "?"
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


class _Unparseable:
    """sentinel: มีข้อมูล/ไฟล์อยู่จริงแต่ parse เป็นเวลาไม่ได้ — ต้องแยกจาก None
    (= ไม่มีข้อมูลเลย) เพื่อให้รายงาน finding ที่ตรงสาเหตุ ไม่ใช่เงียบเฉย ๆ"""

    def __repr__(self):
        return "<unparseable timestamp>"


UNPARSEABLE = _Unparseable()


def _parse_iso(text: str):
    """parse ISO datetime ให้รองรับทั้ง naive/aware แล้ว normalize เป็น UTC เสมอ
    คืน UNPARSEABLE (ไม่ใช่ None) ถ้ารูปแบบผิด — กัน crash และไม่กลืนเงียบเป็น
    "ไม่มีข้อมูล" ที่จริงมันคือ "มีข้อมูลแต่เสีย"""
    try:
        return _to_utc(datetime.fromisoformat(text.strip()))
    except Exception:
        return UNPARSEABLE


def _resolve_now(now):
    """normalize พารามิเตอร์ now ของทุกฟังก์ชันให้เป็น UTC-aware เสมอ (idempotent —
    เรียกซ้ำกับค่าที่ normalize แล้วไม่มีผลข้างเคียง)"""
    return _to_utc(now) if now is not None else _to_utc(datetime.now())


# ── ค่าคงที่ที่ต้องตรงกับ dashboard.py / notify_sync.ps1 เสมอ (เช็ค 8 ยืนยันสด ๆ ตอนรัน) ──
LANE_STALE_LIMIT_MIN = {
    "full": 900, "fast": 75, "wellness": 90,
    "reconcile": 12240, "deep": 44640, "backup": 1800,
}
LANE_LABEL = {
    "full": "sync เต็ม (08:00/21:00)",
    "fast": "กิจกรรม (ทุก 15 นาที)",
    "wellness": "wellness (ทุก 30 นาที)",
    "reconcile": "เช็คกิจกรรมถูกลบ (ทุกอาทิตย์)",
    "deep": "deep resync (ทุก 4 สัปดาห์)",
    "backup": "สำรองข้อมูล (ทุกคืน 22:00)",
}
STALE_MARKER = {
    "full": "sync_run_start.txt", "fast": "sync_fast_run_start.txt",
    "wellness": "sync_wellness_run_start.txt", "reconcile": "sync_reconcile_run_start.txt",
    "deep": "sync_deep_run_start.txt", "backup": "sync_backup_run_start.txt",
}
RUN_GRACE_MIN = {"full": 30, "fast": 10, "wellness": 10, "reconcile": 60, "deep": 90, "backup": 60}
EXPECTED_LANES = {"full", "fast", "wellness", "reconcile", "deep", "backup"}

# งาน durability อยู่นอก 6 sync lanes ด้านบน จึงไม่เอาไปปนกับค่าที่ต้องตรงกับ
# dashboard/notify_sync แต่ health report ต้องเฝ้าให้เหมือนกัน ไม่เช่นนั้น off-site
# backup ล้มแล้ว external heartbeat ยังเขียวได้
RECOVERY_STALE_LIMIT_MIN = {
    "offsite_backup": 30 * 60,
    "restore_drill": 35 * 24 * 60,
}
RECOVERY_LABEL = {
    "offsite_backup": "สำรองข้อมูลเข้ารหัสนอกเครื่อง (ทุกคืน 22:30)",
    "restore_drill": "ทดสอบกู้คืนจริง (ทุก 4 สัปดาห์)",
}

SCHEDULED_TASKS = [
    "Run-Performance-Garmin-Fast",
    "Run-Performance-Garmin-Wellness",
    "Run-Performance-Garmin",
    "Run-Performance-Backup",
    "Run-Performance-Garmin-Reconcile",
    "Run-Performance-Garmin-DeepSync",
    "Run-Performance-OffsiteBackup",
    "Run-Performance-RestoreDrill",
]
TASK_LANE = {
    "Run-Performance-Garmin-Fast": "fast",
    "Run-Performance-Garmin-Wellness": "wellness",
    "Run-Performance-Garmin": "full",
    "Run-Performance-Backup": "backup",
    "Run-Performance-Garmin-Reconcile": "reconcile",
    "Run-Performance-Garmin-DeepSync": "deep",
    "Run-Performance-OffsiteBackup": "offsite_backup",
    "Run-Performance-RestoreDrill": "restore_drill",
}

BACKUP_WARN_HOURS = 30    # ตรงกับ LANE_STALE_LIMIT_MIN["backup"] (1800 นาที)
BACKUP_ERROR_HOURS = 54   # เผื่อรอบตามเก็บ 1 คืนเต็ม ก่อนตีว่า ERROR จริงจัง
BACKUP_MIN_BYTES = 10_000  # snapshot จริงต้องหลาย MB — ต่ำกว่านี้แปลว่าคัดลอกไม่สำเร็จ

DISK_ERROR_FREE_GB = 2
DISK_WARN_FREE_GB = 5
DISK_ERROR_FREE_PCT = 3
DISK_WARN_FREE_PCT = 10

OK, WARNING, ERROR = "OK", "WARNING", "ERROR"


@dataclass
class Finding:
    check: str
    level: str  # OK | WARNING | ERROR
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


# ── ตัวช่วยอ่านสถานะ (อ่านอย่างเดียวล้วน) ────────────────────────────

def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _lane_status_path(lane: str) -> Path:
    return DATA_DIR / "sync_lane" / f"{lane}.json"


def _lane_run_at(lane: str):
    """คืน datetime UTC-aware | None (ไม่มีข้อมูลเลย) | UNPARSEABLE (มีแต่ parse ไม่ได้)"""
    data = _read_json(_lane_status_path(lane))
    if not data or "run_at" not in data:
        return None
    return _parse_iso(data["run_at"])


def _lane_ok(lane: str):
    """คืน (ok: bool, failed_results: list) หรือ None ถ้าไม่มีสถานะให้ดู"""
    data = _read_json(_lane_status_path(lane))
    if not isinstance(data, dict):
        return None

    # งาน off-site/restore เป็น operation เดียว จึงเขียน ``ok`` ที่ระดับบนแทน
    # results รายคนแบบ Garmin lanes
    if type(data.get("ok")) is bool:
        if data["ok"]:
            return (True, [])
        return (False, [{"reason": str(data.get("reason") or "unknown")}])

    results = data.get("results")
    if not isinstance(results, list) or not results:
        return None
    if not all(
        isinstance(item, dict) and type(item.get("ok")) is bool
        for item in results
    ):
        return None
    failed = [r for r in results if not r.get("ok", True)]
    return (len(failed) == 0, failed)


def _read_marker(name: str):
    """คืน datetime UTC-aware | None (ไม่มี marker เลย = ปกติ) | UNPARSEABLE (marker
    เสีย/อ่านรูปแบบเวลาไม่ได้)"""
    p = DATA_DIR / name
    if not p.exists():
        return None
    return _parse_iso(p.read_text(encoding="utf-8"))


# ── 1+2. Scheduled Tasks: LastRunTime / LastTaskResult ──────────────
# แยก "ตัวเรียกระบบจริง" (provider) ออกจาก logic การตัดสิน — เทสทั้งหมด mock provider
# แทนที่จะเรียก schtasks จริง ทำให้รันบนเครื่องไหนก็ได้ (รวมเครื่องที่ไม่ใช่ Windows)

class SchtasksUnavailable(Exception):
    """schtasks ใช้ไม่ได้ (ไม่ใช่ Windows / หา executable ไม่เจอ / timeout)
    — ไม่ใช่สัญญาณว่าระบบเสีย แค่ตรวจสายนี้ไม่ได้บนเครื่องนี้"""


class ScheduledTaskQueryFailed(Exception):
    """Windows ตอบ query ของ task ที่คาดว่าต้องมีไม่สำเร็จ."""


def default_schtasks_provider(task_name: str) -> str:
    """เรียก schtasks จริง คืน stdout ดิบ — จุดเดียวในไฟล์นี้ที่แตะระบบจริง (query อย่างเดียว)"""
    if os.name != "nt":
        raise SchtasksUnavailable("ไม่ใช่ Windows")
    try:
        result = subprocess.run(
            ["schtasks", "/Query", "/TN", task_name, "/V", "/FO", "LIST"],
            # Capture bytes deliberately.  On Thai Windows, schtasks may emit
            # CP874 bytes while Python's preferred text codec is CP1252; using
            # text=True then crashes its reader thread before we can report a
            # finding.  The parser only needs ASCII field names, but preserve
            # Thai task/path text for diagnostics too.
            capture_output=True, text=False, timeout=15,
        )
    except FileNotFoundError as e:
        raise SchtasksUnavailable(f"ไม่พบคำสั่ง schtasks: {e}") from e
    except subprocess.TimeoutExpired as e:
        raise SchtasksUnavailable(f"schtasks ค้าง: {e}") from e
    if result.returncode != 0:
        detail = (
            _decode_windows_output(result.stderr).strip()
            or _decode_windows_output(result.stdout).strip()
            or "schtasks คืน error"
        )
        raise ScheduledTaskQueryFailed(detail)
    return _decode_windows_output(result.stdout)


def _decode_windows_output(raw) -> str:
    """Decode Windows command output without trusting the process code page."""
    if isinstance(raw, str):
        return raw
    if not isinstance(raw, (bytes, bytearray)):
        return ""
    raw = bytes(raw)
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return raw.decode("utf-16")
        except UnicodeDecodeError:
            pass
    for encoding in ("utf-8-sig", "cp874", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


# ── Private Windows ACLs (read-only verification) ───────────────────

class PrivateAclUnavailable(Exception):
    """The exact Windows DACL cannot be inspected on this platform."""


def default_private_acl_provider() -> dict:
    """Run the repository ACL verifier in check-only mode and return its JSON."""
    if os.name != "nt":
        raise PrivateAclUnavailable("not Windows")
    if not ACL_SCRIPT.is_file():
        raise RuntimeError("ACL verifier script is missing")

    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ACL_SCRIPT),
                "-Scope",
                "All",
                "-CheckOnly",
                "-Recurse",
                "-CheckTaskPrincipals",
                "-Json",
            ],
            capture_output=True,
            text=False,
            timeout=180,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("powershell.exe is unavailable") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("ACL verification timed out") from exc

    output = _decode_windows_output(result.stdout).strip()
    try:
        payload = json.loads(output)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("ACL verifier returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("ACL verifier JSON is not an object")
    if result.returncode != 0 and payload.get("ok"):
        payload["ok"] = False
        payload.setdefault("problems", []).append({"code": "verifier_exit_code"})
    return payload


def check_private_acls(provider=None) -> list:
    """Verify the five private roots without leaking athlete/file names."""
    provider = provider or default_private_acl_provider
    try:
        payload = provider()
    except PrivateAclUnavailable as exc:
        return [Finding("private_acl", WARNING, f"ตรวจไม่ได้ (skipped): {exc}")]
    except Exception as exc:
        return [Finding("private_acl", ERROR, f"ตัวตรวจ Windows ACL ล้มเหลว: {exc}")]

    if not isinstance(payload, dict):
        return [Finding("private_acl", ERROR, "ตัวตรวจ Windows ACL คืนข้อมูลผิดรูปแบบ")]
    scanned = int(payload.get("scanned") or 0)
    if payload.get("ok") is True and payload.get("available") is not False:
        return [Finding(
            "private_acl", OK,
            f"ACL ส่วนตัวถูกต้องครบ {scanned} paths (รวม Scheduled Task principals)",
        )]

    problems = payload.get("problems") or []
    codes = sorted({
        str(item.get("code", "unknown"))
        for item in problems if isinstance(item, dict)
    })
    code_text = ", ".join(codes) if codes else "unknown"
    return [Finding(
        "private_acl", ERROR,
        f"พบ ACL/Task principal ไม่ปลอดภัย {len(problems)} จุดใน {scanned} paths "
        f"(ประเภท: {code_text})",
    )]


class HealthcheckStorageUnavailable(Exception):
    """Presence-only registry inspection is unavailable on this platform."""


def _machine_environment_value_present(name: str) -> bool:
    """Query only registry value metadata; never read the bearer value bytes."""
    import ctypes
    from ctypes import wintypes
    import winreg

    subkey = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey, 0, winreg.KEY_QUERY_VALUE) as key:
        value_type = wintypes.DWORD()
        size = wintypes.DWORD()
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        advapi32.RegQueryValueExW.argtypes = [
            wintypes.HKEY, wintypes.LPCWSTR, ctypes.c_void_p,
            ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
            ctypes.POINTER(wintypes.DWORD),
        ]
        advapi32.RegQueryValueExW.restype = wintypes.LONG
        result = advapi32.RegQueryValueExW(
            wintypes.HKEY(int(key)), name, None,
            ctypes.byref(value_type), None, ctypes.byref(size),
        )
    if result == 0:
        return True
    if result == 2:  # ERROR_FILE_NOT_FOUND
        return False
    raise ctypes.WinError(result)


def default_healthcheck_storage_provider() -> dict:
    if os.name != "nt":
        raise HealthcheckStorageUnavailable("not Windows")
    secret_path = DATA_DIR / HEALTHCHECK_DPAPI_FILE
    dpapi_present = secret_path.is_file() and secret_path.stat().st_size > 0
    return {
        "dpapi_present": dpapi_present,
        "machine_value_present": _machine_environment_value_present(
            HEALTHCHECK_ENV_VAR
        ),
    }


def check_healthcheck_secret_storage(provider=None) -> list:
    """Report storage posture without exposing or decrypting the bearer URL."""
    provider = provider or default_healthcheck_storage_provider
    try:
        state = provider()
    except HealthcheckStorageUnavailable as exc:
        return [Finding(
            "healthcheck_secret_storage", WARNING,
            f"ตรวจไม่ได้ (skipped): {exc}",
        )]
    except Exception as exc:
        return [Finding(
            "healthcheck_secret_storage", ERROR,
            f"ตรวจที่เก็บ Healthchecks secret ไม่สำเร็จ: {exc}",
        )]

    dpapi_present = state.get("dpapi_present") is True
    machine_present = state.get("machine_value_present") is True
    if machine_present:
        return [Finding(
            "healthcheck_secret_storage", ERROR,
            "ยังมี machine-scope Healthchecks bearer ที่ผู้ใช้เครื่องอื่นอ่านได้; "
            "ให้รัน migrate_healthcheck_secret.ps1 -RemoveMachineValue แบบ Administrator",
        )]
    if not dpapi_present:
        return [Finding(
            "healthcheck_secret_storage", WARNING,
            "ไม่พบ DPAPI CurrentUser Healthchecks config (external backup monitor ปิดอยู่)",
        )]
    return [Finding(
        "healthcheck_secret_storage", OK,
        "Healthchecks config อยู่ใน DPAPI CurrentUser และไม่มี machine-scope copy",
    )]


def parse_schtasks_output(raw: str) -> dict:
    """แยก field จากผล `/FO LIST /V` (บรรทัดแบบ 'Key:    Value')"""
    fields = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return {
        "last_run_time": fields.get("Last Run Time"),
        "last_result": fields.get("Last Result"),
        "status": fields.get("Status"),
    }


def _parse_task_result(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() in {"N/A", "NEVER"}:
        return None
    try:
        return int(text, 0)
    except ValueError:
        try:
            return int(text)
        except ValueError:
            return None


def check_scheduled_tasks(provider=None, now=None) -> list:
    provider = provider or default_schtasks_provider
    findings = []
    for task_name in SCHEDULED_TASKS:
        lane = TASK_LANE[task_name]
        try:
            raw = provider(task_name)
        except ScheduledTaskQueryFailed as e:
            findings.append(Finding(
                f"scheduled_task:{task_name}", ERROR,
                f"query Scheduled Task ที่ระบบต้องมีไม่สำเร็จ: {e}",
            ))
            continue
        except SchtasksUnavailable as e:
            findings.append(Finding(f"scheduled_task:{task_name}", WARNING,
                                     f"ตรวจไม่ได้ (skipped): {e} — ไม่ถือว่าระบบเสีย"))
            continue

        info = parse_schtasks_output(raw)
        last_run = info.get("last_run_time")
        last_result = info.get("last_result")
        status = (info.get("status") or "").strip()
        result_code = _parse_task_result(last_result)
        never_run = (
            not last_run
            or last_run.strip().upper() in ("N/A", "NEVER", "")
            or result_code == 0x41303  # Task Scheduler: task has not yet run
        )

        if status.casefold() == "disabled":
            findings.append(Finding(
                f"scheduled_task:{task_name}", ERROR,
                f"Scheduled Task ถูกปิด (Status={status})",
            ))
            continue

        if never_run:
            findings.append(Finding(f"scheduled_task:{task_name}", WARNING,
                                     f"ยังไม่เคยรัน (Last Run Time = {last_run or 'N/A'})"))
            continue

        # Wrappers propagate the worker result all the way through .bat + .vbs, while
        # sync_lane confirms the application-level result.  Both signals must agree.
        lane_status = _lane_ok(lane)
        note = " (cross-check กับ sync_lane)"
        if lane_status is not None and lane_status[0] is False:
            reasons = ", ".join(r.get("reason", "?") for r in lane_status[1]) or "ไม่ทราบสาเหตุ"
            findings.append(Finding(
                f"scheduled_task:{task_name}", ERROR,
                f"LastRunTime={last_run} LastTaskResult={last_result} "
                f"แต่สถานะสาย '{lane}' รายงานล้มเหลว ({reasons}){note}",
            ))
        elif result_code is None:
            findings.append(Finding(
                f"scheduled_task:{task_name}", WARNING,
                f"LastTaskResult อ่านไม่ได้ ({last_result or 'N/A'}){note}",
            ))
        elif result_code != 0 and not (
                result_code == 0x41301 and status.casefold() == "running"):
            findings.append(Finding(
                f"scheduled_task:{task_name}", ERROR,
                f"LastRunTime={last_run} LastTaskResult={last_result} "
                f"(ตัว worker/launcher คืน non-zero){note}",
            ))
        elif lane_status is None:
            findings.append(Finding(
                f"scheduled_task:{task_name}", WARNING,
                f"LastRunTime={last_run} LastTaskResult={last_result} "
                f"แต่ไม่มี sync_lane status ที่สมบูรณ์ให้ยืนยัน{note}",
            ))
        else:
            findings.append(Finding(
                f"scheduled_task:{task_name}", OK,
                f"LastRunTime={last_run} LastTaskResult={last_result}{note}",
            ))
    return findings


# ── 3. อายุของ sync_lane/*.json ──────────────────────────────────────

def check_lane_freshness(now=None) -> list:
    now = _resolve_now(now)
    findings = []
    for lane, limit_min in LANE_STALE_LIMIT_MIN.items():
        label = LANE_LABEL.get(lane, lane)
        run_at = _lane_run_at(lane)
        if run_at is UNPARSEABLE:
            findings.append(Finding(f"lane_freshness:{lane}", WARNING,
                                     f"{label}: sync_lane/{lane}.json มี run_at แต่รูปแบบเวลาอ่านไม่ได้"))
            continue
        if run_at is None:
            findings.append(Finding(f"lane_freshness:{lane}", WARNING,
                                     f"{label}: ยังไม่เคยมีสถานะ (sync_lane/{lane}.json ไม่พบ)"))
            continue
        age_min = (now - run_at).total_seconds() / 60
        if age_min > limit_min:
            findings.append(Finding(f"lane_freshness:{lane}", ERROR,
                                     f"{label}: เงียบมา {age_min / 60:.1f} ชม. (เกินเพดาน {limit_min / 60:.1f} ชม.)"))
        elif age_min > limit_min * 0.8:
            findings.append(Finding(f"lane_freshness:{lane}", WARNING,
                                     f"{label}: เงียบมา {age_min / 60:.1f} ชม. (ใกล้เพดาน {limit_min / 60:.1f} ชม.)"))
        else:
            findings.append(Finding(f"lane_freshness:{lane}", OK,
                                     f"{label}: รอบล่าสุดเมื่อ {age_min:.0f} นาทีก่อน"))
    return findings


def check_recovery_freshness(now=None) -> list:
    """เฝ้า off-site backup และ restore drill โดยไม่ปน inventory 6 sync lanes."""
    now = _resolve_now(now)
    findings = []
    for operation, limit_min in RECOVERY_STALE_LIMIT_MIN.items():
        label = RECOVERY_LABEL[operation]
        run_at = _lane_run_at(operation)
        status = _lane_ok(operation)
        check = f"recovery:{operation}"

        if run_at is None:
            findings.append(Finding(
                check, ERROR,
                f"{label}: ยังไม่มีผลพิสูจน์ใน sync_lane/{operation}.json",
            ))
            continue
        if run_at is UNPARSEABLE:
            findings.append(Finding(
                check, ERROR,
                f"{label}: run_at อ่านรูปแบบเวลาไม่ได้",
            ))
            continue
        if status is None:
            findings.append(Finding(
                check, ERROR,
                f"{label}: ไฟล์สถานะเสียหรือไม่มีค่า ok แบบ boolean",
            ))
            continue
        if not status[0]:
            reasons = ", ".join(str(item.get("reason", "?")) for item in status[1])
            findings.append(Finding(
                check, ERROR,
                f"{label}: รอบล่าสุดล้มเหลว ({reasons or 'ไม่ทราบสาเหตุ'})",
            ))
            continue

        age_min = (now - run_at).total_seconds() / 60
        if age_min > limit_min:
            findings.append(Finding(
                check, ERROR,
                f"{label}: ผลพิสูจน์ล่าสุดเก่า {age_min / 1440:.1f} วัน "
                f"(เกินเพดาน {limit_min / 1440:.0f} วัน)",
            ))
        elif age_min > limit_min * 0.8:
            findings.append(Finding(
                check, WARNING,
                f"{label}: ผลพิสูจน์ใกล้หมดอายุ ({age_min / 1440:.1f} วัน)",
            ))
        else:
            findings.append(Finding(
                check, OK,
                f"{label}: พิสูจน์สำเร็จล่าสุด {_fmt_local(run_at)}",
            ))
    return findings


# ── 4. งานที่เริ่มแล้วไม่จบ ────────────────────────────────────────

def check_unfinished_runs(now=None) -> list:
    now = _resolve_now(now)
    findings = []
    for lane, marker_name in STALE_MARKER.items():
        started_at = _read_marker(marker_name)
        if started_at is None:
            continue  # ไม่มี marker ค้าง = ปกติ (ไม่เคยเริ่ม หรือ .bat ลบทิ้งแล้วตอนข้ามรอบ)

        label = LANE_LABEL.get(lane, lane)
        if started_at is UNPARSEABLE:
            findings.append(Finding(f"unfinished_run:{lane}", WARNING,
                                     f"{label}: marker {marker_name} อ่านรูปแบบเวลาไม่ได้"))
            continue

        run_at = _lane_run_at(lane)
        # run_at/started_at ผ่าน _to_utc มาแล้วทั้งคู่ (aware UTC เสมอ) เทียบกันได้ตรง ๆ
        # โดยไม่มีทาง TypeError จาก naive-vs-aware อีก — นี่คือจุดที่เคย crash จริงบน Windows
        finished = (run_at is not None and run_at is not UNPARSEABLE
                    and run_at >= started_at - timedelta(seconds=5))
        if finished:
            continue

        grace = RUN_GRACE_MIN.get(lane, 60)
        elapsed_min = (now - started_at).total_seconds() / 60
        if elapsed_min > grace:
            findings.append(Finding(f"unfinished_run:{lane}", ERROR,
                                     f"{label}: เริ่มรอบ {_fmt_local(started_at)} แล้วไม่จบ "
                                     f"(เกิน grace {grace} นาที — โดนปิด/เครื่องดับกลางทาง)"))
        else:
            findings.append(Finding(f"unfinished_run:{lane}", OK,
                                     f"{label}: รอบกำลังรันอยู่ (เริ่มมา {elapsed_min:.0f} นาที ยังอยู่ในช่วง grace)"))
    if not findings:
        findings.append(Finding("unfinished_run", OK, "ไม่มีรอบไหนเริ่มแล้วไม่จบ"))
    return findings


# ── ตัวช่วยเปิด sqlite แบบ read-only ล้วนแล้วรัน quick_check (ใช้ทั้งเช็ค 5 และ 6) ──

def _quick_check_sqlite_file(path: Path):
    """เปิดไฟล์ sqlite แบบ read-only เท่านั้นแล้วรัน PRAGMA quick_check
    คืน (ok: bool, detail: str) — ไม่มีทางเขียน/แก้ไฟล์เป้าหมายได้เลยจากฟังก์ชันนี้"""
    uri = f"file:{Path(path).as_posix()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.OperationalError as e:
        # DB เป็น WAL ถาวรได้ — เปิด mode=ro ต้องมี sidecar -shm ให้แมปอยู่แล้ว (ดู backup_db.py)
        return False, f"เปิด read-only ไม่ได้ ({e}) — อาจเป็นเพราะ WAL sidecar (-shm) ยังไม่พร้อม"
    try:
        rows = conn.execute("PRAGMA quick_check").fetchall()
    except sqlite3.DatabaseError as e:
        return False, f"quick_check ล้มเหลว: {e}"
    finally:
        conn.close()
    if rows == [("ok",)]:
        return True, "quick_check = ok"
    return False, "quick_check พบปัญหา: " + "; ".join(str(r[0]) for r in rows)


# ── 5. Backup ล่าสุดและขนาดไฟล์ ──────────────────────────────────────

def check_backup(now=None) -> list:
    now = _resolve_now(now)
    findings = []

    lane_run_at = _lane_run_at("backup")
    lane_status = _lane_ok("backup")
    if lane_status is not None and lane_status[0] is False:
        reasons = ", ".join(r.get("reason", "?") for r in lane_status[1]) or "ไม่ทราบสาเหตุ"
        findings.append(Finding("backup:lane_status", ERROR, f"สาย backup รายงานล้มเหลว ({reasons})"))
    elif lane_run_at is UNPARSEABLE:
        findings.append(Finding("backup:lane_status", WARNING, "sync_lane/backup.json มี run_at แต่รูปแบบเวลาอ่านไม่ได้"))
    elif lane_run_at is None:
        findings.append(Finding("backup:lane_status", WARNING, "ยังไม่เคยมีสถานะสาย backup"))
    else:
        findings.append(Finding("backup:lane_status", OK,
                                 f"สาย backup รายงานสำเร็จล่าสุด {_fmt_local(lane_run_at)}"))

    if not BACKUP_DIR.exists():
        findings.append(Finding("backup:daily_files", WARNING,
                                 f"ไม่พบโฟลเดอร์สำรองรายวัน {BACKUP_DIR} "
                                 f"(ตั้ง GARMIN_BACKUP_DIR ถ้าไม่ใช่เครื่อง production)"))
        return findings

    files = sorted(BACKUP_DIR.glob("garmin-*.db"))
    if not files:
        findings.append(Finding("backup:daily_files", ERROR, f"ไม่พบไฟล์สำรองรายวันเลยใน {BACKUP_DIR}"))
        return findings

    latest = files[-1]
    size = latest.stat().st_size
    mtime = _to_utc(datetime.fromtimestamp(latest.stat().st_mtime))
    age_hours = (now - mtime).total_seconds() / 3600
    # ขนาดไฟล์อย่างเดียวไม่พอ — ไฟล์ขนาดปกติก็เสียได้ (ตัด/คัดลอกครึ่งเดียวแล้วพอดีขนาดใกล้เคียง)
    # ต้องเปิดจริงด้วย quick_check ยืนยันว่าเป็น sqlite ที่สมบูรณ์ ไม่ใช่แค่ "ไฟล์ไม่เล็กเกินไป"
    integrity_ok, integrity_detail = _quick_check_sqlite_file(latest)

    if not integrity_ok:
        findings.append(Finding("backup:daily_files", ERROR,
                                 f"{latest.name} เปิด/ตรวจสอบไม่ผ่าน: {integrity_detail} "
                                 f"({size / 1024:.0f} KB, {age_hours:.1f} ชม.ที่แล้ว)"))
    elif size < BACKUP_MIN_BYTES:
        findings.append(Finding("backup:daily_files", ERROR,
                                 f"{latest.name} เล็กผิดปกติ ({size} bytes) — สงสัยคัดลอกไม่สำเร็จ"))
    elif age_hours > BACKUP_ERROR_HOURS:
        findings.append(Finding("backup:daily_files", ERROR,
                                 f"{latest.name} เก่ามาก ({age_hours:.1f} ชม., {size / 1024:.0f} KB, {integrity_detail})"))
    elif age_hours > BACKUP_WARN_HOURS:
        findings.append(Finding("backup:daily_files", WARNING,
                                 f"{latest.name} เก่ากว่าปกติ ({age_hours:.1f} ชม., {size / 1024:.0f} KB, {integrity_detail})"))
    else:
        findings.append(Finding("backup:daily_files", OK,
                                 f"{latest.name} สดอยู่ ({age_hours:.1f} ชม.ที่แล้ว, "
                                 f"{size / 1024:.0f} KB, {integrity_detail}, เก็บ {len(files)} ชุด)"))
    return findings


# ── 6. SQLite PRAGMA quick_check (read-only เท่านั้น) ────────────────

def check_db_integrity() -> list:
    if not DB_PATH.exists():
        return [Finding("db_integrity", ERROR, f"ไม่พบไฟล์ DB ที่ {DB_PATH}")]
    ok, detail = _quick_check_sqlite_file(DB_PATH)
    return [Finding("db_integrity", OK if ok else ERROR, detail)]


# ── 7. คุณภาพข้อมูลต่อ field (read-only, วันตัดตาม Asia/Bangkok) ─────────────

def _data_quality_message(finding: dict) -> str:
    kind = finding.get("kind")
    if kind == "drift":
        return (
            f"{finding['field']} coverage ลดในช่วง {finding['horizon_days']} วัน: "
            f"{finding['prior'][0]}/{finding['prior'][1]} "
            f"({finding['prior_rate']:.0%}) → {finding['recent'][0]}/{finding['recent'][1]} "
            f"({finding['recent_rate']:.0%})"
        )
    if kind == "partial_snapshot":
        return (
            f"{finding['calendar_date']} เป็น partial snapshot — "
            f"มี {', '.join(finding['present'])}; ขาด {', '.join(finding['missing'])}"
        )
    if kind == "missing_snapshot":
        state = "ไม่มีแถว" if finding.get("reason") == "row_missing" else "มีแถวแต่ค่าที่คาดว่างทั้งหมด"
        return (
            f"{finding['calendar_date']} ขาด wellness ทั้ง snapshot ({state}) — "
            f"ขาด {', '.join(finding['missing'])}"
        )
    if kind == "range":
        examples = ", ".join(f"{d}={v}" for d, v in finding["examples"])
        return (
            f"{finding['field']} นอกช่วง {finding['bounds'][0]}–{finding['bounds'][1]} "
            f"{finding['count']} จุด ({examples})"
        )
    if kind == "relation":
        examples = ", ".join(
            f"{row[0]}={row[1]}/{row[2]}" for row in finding["examples"]
        )
        return f"relation {finding['field']} ผิด {finding['count']} จุด ({examples})"
    return str(finding)


def check_data_quality(now=None) -> list:
    """Check field coverage, partial rows and values without modifying SQLite."""
    if not DB_PATH.exists():
        return [Finding("data_quality", ERROR, f"ไม่พบไฟล์ DB ที่ {DB_PATH}")]
    uri = f"file:{DB_PATH.resolve().as_posix()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        return [Finding("data_quality", ERROR, f"เปิด DB แบบ read-only ไม่ได้: {exc}")]

    findings = []
    try:
        athletes = conn.execute(
            "SELECT slug, athlete_id FROM dim_athlete ORDER BY slug"
        ).fetchall()
        for slug, athlete_id in athletes:
            anomalies, coverage = dq.check_athlete(
                conn, slug, athlete_id, today=now,
            )
            wellness = {
                item["field"]: item["recent"][0]
                for item in coverage if item["table"] == "wellness"
            }
            summary_fields = (
                "resting_hr", "sleep_score", "body_battery_high", "stress_avg",
                "hrv_last_night", "avg_sleep_respiration", "training_readiness",
            )
            summary = ", ".join(
                f"{field}={wellness[field]}/30"
                for field in summary_fields if field in wellness
            ) or "ไม่มี wellness field ที่รองรับ"
            core_fields = (
                "resting_hr", "sleep_score", "body_battery_high",
                "stress_avg", "hrv_last_night",
            )
            core_counts = [wellness[field] for field in core_fields if field in wellness]
            very_low_core = (
                not core_counts
                or max(core_counts) <= int(30 * dq.BAD_RATE)
            )
            coverage_level = WARNING if very_low_core else OK
            coverage_note = (
                " — coverage ค่าหลักต่ำมาก; ตรวจว่าเป็นนักกีฬาใหม่/ไม่ได้ sync "
                "หรือ wellness endpoint ขาดทั้งวัน"
                if very_low_core else ""
            )
            findings.append(Finding(
                f"data_quality_coverage:{slug}", coverage_level,
                f"coverage วันเต็มล่าสุด (Asia/Bangkok): {summary}{coverage_note}",
            ))
            for anomaly in anomalies:
                findings.append(Finding(
                    f"data_quality:{slug}:{anomaly['kind']}:{anomaly['field']}",
                    ERROR if anomaly["level"] == "ERROR" else WARNING,
                    _data_quality_message(anomaly),
                ))
    except sqlite3.Error as exc:
        return [Finding("data_quality", ERROR, f"query ตรวจคุณภาพข้อมูลล้มเหลว: {exc}")]
    finally:
        conn.close()

    if not findings:
        findings.append(Finding("data_quality", WARNING, "ไม่พบนักกีฬาใน dim_athlete"))
    return findings


# ── 8. พื้นที่ว่างของไดรฟ์ ────────────────────────────────────────

def check_disk_space(disk_usage=None) -> list:
    disk_usage = disk_usage or shutil.disk_usage
    findings = []
    for label, path in (("data", DATA_DIR), ("backup", BACKUP_DIR)):
        anchor = path if path.exists() else Path(path.anchor or ".")
        try:
            usage = disk_usage(str(anchor))
        except OSError as e:
            findings.append(Finding(
                f"disk_space:{label}", WARNING,
                f"เช็คพื้นที่ดิสก์ของ {label} ไม่ได้ ({e})",
            ))
            continue

        free_gb = usage.free / (1024 ** 3)
        total_gb = usage.total / (1024 ** 3) if usage.total else 0
        free_pct = (usage.free / usage.total * 100) if usage.total else 0
        msg = (
            f"{label}: เหลือ {free_gb:.1f} GB ({free_pct:.1f}%) "
            f"จากทั้งหมด {total_gb:.0f} GB"
        )

        if free_gb < DISK_ERROR_FREE_GB or free_pct < DISK_ERROR_FREE_PCT:
            level = ERROR
        elif free_gb < DISK_WARN_FREE_GB or free_pct < DISK_WARN_FREE_PCT:
            level = WARNING
        else:
            level = OK
        findings.append(Finding(f"disk_space:{label}", level, msg))
    return findings


# ── 9. ความสอดคล้องของ 6 สาย: dashboard.py เทียบ notify_sync.ps1 ─────
# เทคนิคเดียวกับ tests/test_fast_sync.py::LaneStaleLimitTests (ast อ่าน python,
# regex อ่าน powershell) — ต่างกันตรงนี้คือรันสด ๆ ตอน health check จริง ไม่ใช่แค่ตอน CI

def _dashboard_lane_limits(path=None) -> dict:
    path = path or (PROJECT_ROOT / "scripts" / "dashboard.py")
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "LANE_STALE_LIMIT_MIN" for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError(f"ไม่พบ LANE_STALE_LIMIT_MIN ใน {path}")


def _watchdog_lane_limits(path=None) -> dict:
    path = path or (PROJECT_ROOT / "scripts" / "notify_sync.ps1")
    src = Path(path).read_text(encoding="utf-8-sig")
    block = re.search(r"\$STALE_LIMIT_MIN\s*=\s*\[ordered\]@\{(.+?)\}", src, re.S)
    if not block:
        raise ValueError(f"ไม่พบ $STALE_LIMIT_MIN ใน {path}")
    return {k: int(v) for k, v in re.findall(r"(\w+)\s*=\s*(\d+)", block.group(1))}


def check_lane_limit_consistency(dashboard_path=None, watchdog_path=None) -> list:
    try:
        dash = _dashboard_lane_limits(dashboard_path)
        watch = _watchdog_lane_limits(watchdog_path)
    except (ValueError, OSError) as e:
        return [Finding("lane_limit_consistency", ERROR, f"อ่านค่าคงที่ไม่ได้: {e}")]

    problems = []
    if set(dash) != EXPECTED_LANES:
        problems.append(f"dashboard.py มีสายไม่ครบ 6 สาย: {sorted(dash)}")
    if set(watch) != EXPECTED_LANES:
        problems.append(f"notify_sync.ps1 มีสายไม่ครบ 6 สาย: {sorted(watch)}")
    if dash != watch:
        diff = {k: (dash.get(k), watch.get(k)) for k in set(dash) | set(watch) if dash.get(k) != watch.get(k)}
        problems.append(f"ค่าไม่ตรงกัน: {diff}")

    if problems:
        return [Finding("lane_limit_consistency", ERROR, " | ".join(problems))]
    return [Finding("lane_limit_consistency", OK, "dashboard.py กับ notify_sync.ps1 ตรงกันครบ 6 สาย")]


# ── รวมทุกเช็ค + CLI ─────────────────────────────────────────────

def run_all_checks(*, now=None, schtasks_provider=None, disk_usage=None,
                    dashboard_path=None, watchdog_path=None,
                    acl_provider=None, healthcheck_storage_provider=None) -> list:
    now = _resolve_now(now)
    findings = []
    findings += check_scheduled_tasks(provider=schtasks_provider, now=now)
    findings += check_lane_freshness(now=now)
    findings += check_recovery_freshness(now=now)
    findings += check_unfinished_runs(now=now)
    findings += check_backup(now=now)
    findings += check_db_integrity()
    findings += check_data_quality(now=now)
    findings += check_disk_space(disk_usage=disk_usage)
    findings += check_lane_limit_consistency(dashboard_path=dashboard_path, watchdog_path=watchdog_path)
    findings += check_private_acls(provider=acl_provider)
    findings += check_healthcheck_secret_storage(
        provider=healthcheck_storage_provider
    )
    return findings


_ICON = {"OK": "✅", "WARNING": "⚠️ ", "ERROR": "❌"}


def _print_text_report(findings: list) -> None:
    print("=" * 60)
    print("  GARMIN SYNC HEALTH REPORT (read-only)")
    print(f"  {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 60)
    for f in findings:
        print(f"{_ICON.get(f.level, '?')} [{f.level}] {f.check}: {f.message}")
    n_err = sum(1 for f in findings if f.level == ERROR)
    n_warn = sum(1 for f in findings if f.level == WARNING)
    n_ok = len(findings) - n_err - n_warn
    print("=" * 60)
    print(f"  รวม {len(findings)} เช็ค | OK={n_ok} WARNING={n_warn} ERROR={n_err}")
    print("=" * 60)


def _print_json_report(findings: list) -> None:
    n_err = sum(1 for f in findings if f.level == ERROR)
    n_warn = sum(1 for f in findings if f.level == WARNING)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "findings": [f.to_dict() for f in findings],
        "summary": {
            "ok": len(findings) - n_err - n_warn,
            "warning": n_warn,
            "error": n_err,
            "total": len(findings),
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true",
                     help="พิมพ์ผลเป็น JSON แทนข้อความ (เตรียมไว้ต่อ Healthchecks.io ขั้นถัดไป)")
    args = ap.parse_args(argv)

    findings = run_all_checks()

    if args.json:
        _print_json_report(findings)
    else:
        _print_text_report(findings)

    return 1 if any(f.level == ERROR for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
