#!/usr/bin/env python3
"""ตรวจ coverage, schema drift, partial snapshots และค่าผิดช่วงแบบ read-only โดยปริยาย.

Scheduled Task ใช้ ``--record-deep-status`` เพื่อบันทึกเฉพาะผลล้มเหลวลง deep.json
แบบ atomic; ถ้าไม่ใส่ flag นี้สคริปต์จะไม่เขียนไฟล์ใด ๆ.

ใช้:
    python scripts/check_drift.py
    python scripts/check_drift.py --athlete p'kao
    python scripts/check_drift.py --json

exit code: 1 เมื่อพบข้อมูลน่าสงสัย, 0 เมื่อไม่พบ.  ฟิลด์ที่อุปกรณ์ไม่เคยส่งจะ
ไม่ถูกเตือน เพราะ drift เทียบกับประวัติของนักกีฬาแต่ละคนเอง.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sqlite3
import sys
from datetime import date
from pathlib import Path

try:  # ``python scripts/check_drift.py``
    import data_quality as dq
except ModuleNotFoundError:  # loaded directly by importlib from any cwd
    _dq_spec = importlib.util.spec_from_file_location(
        "garmin_data_quality", Path(__file__).with_name("data_quality.py")
    )
    dq = importlib.util.module_from_spec(_dq_spec)
    _dq_spec.loader.exec_module(dq)

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("GARMIN_DATA_DIR", PROJECT_ROOT / "data"))
DB_PATH = DATA_DIR / "garmin.db"

# Backward-compatible public constants/helpers used by existing operational
# notes and ad-hoc imports.
GOOD_RATE = dq.GOOD_RATE
BAD_RATE = dq.BAD_RATE
MIN_SAMPLE = dq.MIN_SAMPLE
WELLNESS_FIELDS = list(dq.WELLNESS_FIELDS)
ACTIVITY_FIELDS = list(dq.ACTIVITY_FIELDS)


def use_data_dir(path) -> Path:
    """Point the checker at an isolated data directory (primarily for tests)."""
    global DATA_DIR, DB_PATH
    previous = DATA_DIR
    DATA_DIR = Path(path)
    DB_PATH = DATA_DIR / "garmin.db"
    return previous


def _rate(cur, sql, params):
    """Compatibility helper: return ``(COUNT(field), COUNT(*))``."""
    row = cur.execute(sql, params).fetchone()
    return int(row[0] or 0), int(row[1] or 0)


def _judge(table, field, recent, prior):
    """Compatibility wrapper for the original 30-day drift rule."""
    return dq.judge_drift(table, field, recent, prior, horizon_days=30)


def check_athlete(conn, slug, athlete_id, *, today=None):
    """Return findings only, preserving the original public function shape."""
    findings, _coverage = dq.check_athlete(
        conn, slug, athlete_id, today=today,
    )
    return findings


def _coverage_line(item: dict) -> str:
    recent_nn, recent_total = item["recent"]
    prior_nn, prior_total = item["prior"]
    unit = "วันปฏิทิน" if item["table"] == "wellness" else "แถวกิจกรรม"
    return (
        f"   {item['table']}.{item['field']}: "
        f"ล่าสุด {recent_nn}/{recent_total} {unit} ({_percent(recent_nn, recent_total)})"
        f" | ก่อนหน้า {prior_nn}/{prior_total} ({_percent(prior_nn, prior_total)})"
    )


def _percent(non_null: int, total: int) -> str:
    return f"{non_null / total:.0%}" if total else "n/a"


def _finding_message(finding: dict) -> str:
    kind = finding["kind"]
    if kind == "drift":
        return (
            f"{finding['table']}.{finding['field']} ({finding['horizon_days']} วัน): "
            f"เคยมี {finding['prior_rate']:.0%} ({finding['prior'][0]}/{finding['prior'][1]}) "
            f"→ ล่าสุด {finding['recent_rate']:.0%} ({finding['recent'][0]}/{finding['recent'][1]})"
        )
    if kind == "partial_snapshot":
        return (
            f"wellness {finding['calendar_date']} เป็น partial snapshot: "
            f"มี {', '.join(finding['present'])}; ขาด {', '.join(finding['missing'])}"
        )
    if kind == "missing_snapshot":
        state = "ไม่มีแถว" if finding.get("reason") == "row_missing" else "มีแถวแต่ค่าที่คาดว่างทั้งหมด"
        return (
            f"wellness {finding['calendar_date']} ขาดทั้ง snapshot ({state}): "
            f"ขาด {', '.join(finding['missing'])}"
        )
    if kind == "range":
        low, high = finding["bounds"]
        examples = ", ".join(f"{day}={value}" for day, value in finding["examples"])
        return (
            f"wellness.{finding['field']} นอกช่วงตรวจ {low}–{high} "
            f"จำนวน {finding['count']} จุด ({examples})"
        )
    if kind == "relation":
        examples = ", ".join(
            f"{row[0]}={row[1]}/{row[2]}" for row in finding["examples"]
        )
        return (
            f"wellness relation {finding['field']} ผิด {finding['count']} จุด "
            f"({examples})"
        )
    return str(finding)


def collect(conn: sqlite3.Connection, rows, *, today=None):
    athletes = []
    all_findings = []
    for slug, athlete_id in rows:
        findings, coverage = dq.check_athlete(
            conn, slug, athlete_id, today=today,
        )
        athletes.append({
            "slug": slug,
            "athlete_id": athlete_id,
            "coverage": coverage,
            "findings": findings,
        })
        all_findings.extend(findings)
    return athletes, all_findings


def record_deep_lane_failure(findings: list) -> None:
    """Persist data-quality/drift failure in the deep lane atomically."""
    path = DATA_DIR / "sync_lane" / "deep.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("lane") != "deep":
        raise ValueError("deep lane status is missing or malformed")
    results = payload.get("results")
    if not isinstance(results, list) or not results or not all(
        isinstance(item, dict) and type(item.get("ok")) is bool
        for item in results
    ):
        raise ValueError("deep lane results are missing or malformed")

    results = [item for item in results if item.get("reason") != "drift"]
    results.append({
        "slug": "data quality/schema drift",
        "ok": False,
        "reason": "drift",
        "warnings": [f"พบข้อมูลน่าสงสัย {len(findings)} จุด; ดู deepsync log"],
    })
    payload["results"] = results
    tmp = path.with_suffix(".json.tmp")
    try:
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--athlete", default=None, help="slug เจาะจง (ไม่ใส่ = ทุกคน)")
    parser.add_argument("--json", action="store_true", help="พิมพ์ผลเป็น JSON")
    parser.add_argument(
        "--today",
        type=date.fromisoformat,
        default=None,
        help="วันไทย YYYY-MM-DD สำหรับตรวจย้อนหลังแบบทำซ้ำได้ (ค่าเริ่มต้น = วันนี้ Asia/Bangkok)",
    )
    parser.add_argument(
        "--record-deep-status",
        action="store_true",
        help="บันทึก finding ลง sync_lane/deep.json แบบ atomic (ใช้โดย Scheduled Task)",
    )
    args = parser.parse_args(argv)

    if not DB_PATH.exists():
        message = f"ไม่พบฐานข้อมูล {DB_PATH}"
        if args.json:
            print(json.dumps({"ok": False, "error": message}, ensure_ascii=False))
        else:
            print(f"❌ {message}")
        return 1

    uri = f"file:{DB_PATH.resolve().as_posix()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        else:
            print(f"❌ เปิดฐานข้อมูลแบบ read-only ไม่ได้: {exc}")
        return 1

    try:
        if args.athlete:
            rows = conn.execute(
                "SELECT slug, athlete_id FROM dim_athlete WHERE slug = ?",
                (args.athlete,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT slug, athlete_id FROM dim_athlete ORDER BY slug"
            ).fetchall()
        athletes, findings = collect(conn, rows, today=args.today)
    except sqlite3.Error as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        else:
            print(f"❌ ตรวจข้อมูลไม่ได้: {exc}")
        return 1
    finally:
        conn.close()

    if args.athlete and not rows:
        message = f"ไม่พบนักกีฬา slug={args.athlete!r}"
        if args.json:
            print(json.dumps({
                "ok": False,
                "error": message,
                "today_bangkok": dq.bangkok_today(args.today).isoformat(),
            }, ensure_ascii=False))
        else:
            print(f"❌ {message}")
        return 1

    lane_status_error = None
    if args.record_deep_status and findings:
        try:
            record_deep_lane_failure(findings)
        except Exception as exc:
            lane_status_error = str(exc)

    if args.json:
        payload = {
            "ok": not findings,
            "today_bangkok": dq.bangkok_today(args.today).isoformat(),
            "athletes": athletes,
            "findings": findings,
            "summary": {
                "athletes": len(athletes),
                "findings": len(findings),
                "warnings": sum(f["level"] == "WARNING" for f in findings),
                "errors": sum(f["level"] == "ERROR" for f in findings),
            },
        }
        if lane_status_error:
            payload["lane_status_error"] = lane_status_error
        print(json.dumps(
            dq.json_safe(payload), ensure_ascii=False, indent=2, allow_nan=False,
        ))
        return 1 if findings else 0

    print("=" * 72)
    print("  GARMIN DATA QUALITY — coverage / drift / partial / range")
    print(f"  วันอ้างอิง Asia/Bangkok: {dq.bangkok_today(args.today).isoformat()}")
    print("=" * 72)
    if not rows:
        print("⚠️  ไม่พบนักกีฬาตามเงื่อนไข")
    for athlete in athletes:
        print(f"\n{athlete['slug']} — coverage 30 วันเต็มล่าสุด")
        for item in athlete["coverage"]:
            print(_coverage_line(item))
        if athlete["findings"]:
            print(f"   🚩 พบ {len(athlete['findings'])} จุดน่าสงสัย")
            for finding in athlete["findings"]:
                print(f"      - [{finding['level']}] {_finding_message(finding)}")
        else:
            print("   ✅ ไม่พบ drift, partial snapshot หรือค่าผิดช่วง")

    print("\n" + "=" * 72)
    if lane_status_error:
        print(f"❌ บันทึกสถานะ deep lane ไม่สำเร็จ: {lane_status_error}")
    if findings:
        print(f"⚠️  รวมพบ {len(findings)} จุดน่าสงสัย — ตรวจ Garmin Cloud/parser ก่อนแก้ข้อมูล")
    else:
        print("✅ ไม่พบความผิดปกติจากกฎ data-quality ปัจจุบัน")
    print("=" * 72)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
