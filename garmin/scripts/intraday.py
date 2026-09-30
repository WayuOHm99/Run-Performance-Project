"""Intraday wellness (heart rate / stress / body battery ทุก 2-3 นาที) → fact_wellness_intraday.

แยกจาก 03_backfill.py โดยตั้งใจ (ไฟล์นั้นถือ logic เขียน DB หลัก) — 03_backfill เรียกแค่
`fetch_and_store_day()` กับ `prune()` ผ่าน hook เล็ก ๆ จุดเดียว

ปริมาณข้อมูล (ประมาณ): HR ~720 จุด/วัน (ทุก ~2 นาที) + stress ~480 (ทุก ~3 นาที)
  + body battery ~480 ≈ 1,700 จุด/นักกีฬา/วัน → 180 วัน ≈ 306,000 แถว/คน (~15-20 MB/คน)
  จึงเก็บแค่ INTRADAY_RETENTION_DAYS วัน; สรุปรายวันใน fact_daily_wellness ไม่ถูกแตะ

ภาระ API: lane --wellness-fast ทุก 30 นาที × 2 call (get_heart_rates + get_stress_data)
  = 96 call/นักกีฬา/วัน  + full sync ดึงเมื่อวานอีก 2 call/รอบ

หลักความปลอดภัย: หาตำแหน่งคอลัมน์จาก descriptor key เสมอ (ไม่ hard-code index) —
ถ้า key ที่ต้องใช้หาย = schema ของ Garmin เปลี่ยน → ไม่เก็บ metric นั้นและบันทึกเป็น failure
(reason "payload") แทนการเดา. ห้ามพิมพ์ค่าสุขภาพลง log.
"""

from __future__ import annotations

import math
import time
from datetime import date, datetime, timedelta, timezone

INTRADAY_RETENTION_DAYS = 180
METRICS = ("heart_rate", "stress", "body_battery")
HEART_RATE_ENDPOINT = "get_heart_rates"
STRESS_ENDPOINT = "get_stress_data"


class IntradaySchemaDrift(ValueError):
    """payload มีข้อมูลแต่ไม่มี descriptor key ที่คาดไว้ (Garmin เปลี่ยนรูปแบบ)."""


def _iso_utc(ms):
    if isinstance(ms, bool) or not isinstance(ms, (int, float)):
        return None
    if not math.isfinite(ms) or ms <= 0:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    except (OverflowError, OSError, ValueError):
        return None


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        return None
    return value


def _calendar_date(payload, fallback):
    raw = payload.get("calendarDate") if isinstance(payload, dict) else None
    for candidate in (raw, fallback):
        if isinstance(candidate, str):
            try:
                return date.fromisoformat(candidate[:10]).isoformat()
            except ValueError:
                continue
    return None


def _positions(descriptors, index_name, key_name):
    """{key: ตำแหน่งใน array} จากรายการ descriptor; ไม่ใช่ list → {}."""
    found = {}
    if not isinstance(descriptors, list):
        return found
    for item in descriptors:
        if not isinstance(item, dict):
            continue
        key, index = item.get(key_name), item.get(index_name)
        if isinstance(key, str) and isinstance(index, int) and not isinstance(index, bool):
            found[key] = index
    return found


def _points(values, descriptors, index_name, key_name, ts_key, value_key):
    """ดึง (ts_iso, ค่าดิบ) ตาม descriptor. array ว่าง/ไม่มี = ไม่มีข้อมูล ([]) ไม่ใช่ failure."""
    if not isinstance(values, list) or not values:
        return []
    pos = _positions(descriptors, index_name, key_name)
    if ts_key not in pos or value_key not in pos:
        raise IntradaySchemaDrift("missing descriptor key")
    ts_pos, val_pos = pos[ts_key], pos[value_key]
    points = []
    for row in values:
        if not isinstance(row, (list, tuple)) or max(ts_pos, val_pos) >= len(row):
            continue
        ts = _iso_utc(row[ts_pos])
        if ts is not None:
            points.append((ts, row[val_pos]))
    return points


def parse_heart_rate(payload, date_str=None):
    """get_heart_rates → แถว metric='heart_rate'. bpm ที่ไม่ใช่จำนวนบวก → value NULL (ไม่ใช่ 0)."""
    if not isinstance(payload, dict):
        return []
    cal = _calendar_date(payload, date_str)
    if cal is None:
        return []
    rows = []
    for ts, raw in _points(
        payload.get("heartRateValues"), payload.get("heartRateValueDescriptors"),
        "index", "key", "timestamp", "heartrate",
    ):
        bpm = _number(raw)
        rows.append({
            "calendar_date": cal, "metric": "heart_rate", "ts_utc": ts,
            "value": float(bpm) if bpm is not None and bpm > 0 else None,
            "source_code": None,
        })
    return rows


def parse_stress(payload, date_str=None):
    """get_stress_data → แถว metric='stress'. ค่าลบ = รหัสของ Garmin (วัดไม่ได้/กำลังทำกิจกรรม)
    → value NULL + เก็บรหัสดิบใน source_code."""
    if not isinstance(payload, dict):
        return []
    cal = _calendar_date(payload, date_str)
    if cal is None:
        return []
    rows = []
    for ts, raw in _points(
        payload.get("stressValuesArray"), payload.get("stressValueDescriptorsDTOList"),
        "index", "key", "timestamp", "stressLevel",
    ):
        level = _number(raw)
        value, code = None, None
        if level is not None:
            if level < 0:
                code = int(level)
            else:
                value = float(level)
        rows.append({
            "calendar_date": cal, "metric": "stress", "ts_utc": ts,
            "value": value, "source_code": code,
        })
    return rows


def parse_body_battery(payload, date_str=None):
    """get_stress_data (ส่วน bodyBattery*) → แถว metric='body_battery' (ค่า 0-100 เท่านั้น)."""
    if not isinstance(payload, dict):
        return []
    cal = _calendar_date(payload, date_str)
    if cal is None:
        return []
    rows = []
    for ts, raw in _points(
        payload.get("bodyBatteryValuesArray"),
        payload.get("bodyBatteryValueDescriptorsDTOList"),
        "bodyBatteryValueDescriptorIndex", "bodyBatteryValueDescriptorKey",
        "timestamp", "bodyBatteryLevel",
    ):
        level = _number(raw)
        rows.append({
            "calendar_date": cal, "metric": "body_battery", "ts_utc": ts,
            "value": float(level) if level is not None and 0 <= level <= 100 else None,
            "source_code": None,
        })
    return rows


_UPSERT_SQL = """
INSERT INTO fact_wellness_intraday
    (athlete_id, calendar_date, metric, ts_utc, value, source_code, fetched_at)
VALUES (?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))
ON CONFLICT(athlete_id, metric, ts_utc) DO UPDATE SET
    calendar_date = excluded.calendar_date,
    value         = excluded.value,
    source_code   = excluded.source_code,
    fetched_at    = excluded.fetched_at
"""


def _record(failures, endpoint):
    if failures is not None:
        failures.append({"endpoint": endpoint, "reason": "payload"})


def store_intraday(conn, athlete_id, payloads, *, failures=None, date_str=None):
    """upsert payload → fact_wellness_intraday แล้วคืนจำนวนแถวต่อ metric.

    payloads: {"heart_rate": <get_heart_rates>, "stress": <get_stress_data>} — key ที่ไม่มี/None = ข้าม
    (ไม่แตะแถวเดิม). metric ที่ schema เพี้ยน → ไม่เก็บ + failures.append({endpoint, reason:"payload"})
    ส่วน metric อื่นยังเก็บตามปกติ. ไม่ commit เอง — ผู้เรียก commit.
    """
    counts = {m: 0 for m in METRICS}
    jobs = (
        ("heart_rate", "heart_rate", parse_heart_rate, HEART_RATE_ENDPOINT),
        ("stress", "stress", parse_stress, STRESS_ENDPOINT),
        ("stress", "body_battery", parse_body_battery, STRESS_ENDPOINT),
    )
    for source, metric, parser, endpoint in jobs:
        payload = payloads.get(source)
        if payload is None:
            continue
        try:
            rows = parser(payload, date_str)
        except IntradaySchemaDrift:
            _record(failures, endpoint)
            continue
        conn.executemany(
            _UPSERT_SQL,
            [
                (athlete_id, r["calendar_date"], r["metric"], r["ts_utc"],
                 r["value"], r["source_code"])
                for r in rows
            ],
        )
        counts[metric] += len(rows)
    return counts


def fetch_and_store_day(garmin, conn, athlete_id, date_str, *, call, failures=None):
    """ดึง HR + stress ของวันเดียว (2 call) แล้วเก็บ.

    call = wrapper แบบ safe_call ของ 03_backfill (ส่งเข้ามาเพื่อกัน import วน) — endpoint ที่ล้ม
    ถูกบันทึกใน failures และคืน None → ข้าม metric นั้น (แถวเดิมไม่ถูกแตะ) แล้วทำต่อ
    """
    payloads = {}
    for source, endpoint in (("heart_rate", HEART_RATE_ENDPOINT), ("stress", STRESS_ENDPOINT)):
        method = getattr(garmin, endpoint, None)
        if method is None:   # ไลบรารี/นาฬิกานี้ไม่มี endpoint — ข้ามเงียบ ไม่ใช่ schema drift
            continue
        payloads[source] = call(
            method, date_str, _failures=failures, _endpoint=endpoint
        )
        time.sleep(0.3)
    counts = store_intraday(
        conn, athlete_id, payloads, failures=failures, date_str=date_str
    )
    conn.commit()
    return counts


def prune(conn, *, now=None, retention_days=INTRADAY_RETENTION_DAYS):
    """ลบจุด intraday ที่เก่ากว่า retention_days (อิง ts_utc) คืนจำนวนแถวที่ลบ."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    cutoff = (now - timedelta(days=retention_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    cur = conn.execute("DELETE FROM fact_wellness_intraday WHERE ts_utc < ?", (cutoff,))
    conn.commit()
    return max(cur.rowcount, 0)
