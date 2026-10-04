"""Read-only data coverage and safe sync summaries, independent of health scores."""

import datetime as dt
import json
from contextlib import closing

import pandas as pd
import streamlit as st

from dashboard_data import CACHE_TTL_SEC, connect_db, data_dir, load_latest_fetch
from dashboard_domain import to_bangkok_timestamp

# Coverage means at least one displayed body metric, never completeness of every field.
BODY_FIELDS = (
    "resting_hr", "hrv_last_night", "hrv_weekly_avg", "hrv_status", "sleep_score",
    "sleep_duration_sec", "body_battery_high", "body_battery_low", "bb_most_recent",
    "stress_avg", "avg_waking_respiration", "avg_sleep_respiration",
    "training_readiness", "recovery_time_min",
)


def summarize_dates(values, start, end, today):
    dates = set()
    for value in values:
        try:
            day = dt.date.fromisoformat(value)
        except (TypeError, ValueError):
            continue
        if day <= today:
            dates.add(day)
    latest = max(dates) if dates else None
    # Don't call today's unfinished day or dates before first receipt a gap.
    lower = max(start, min(dates)) if dates else start
    upper = min(end, today - dt.timedelta(days=1))
    gaps = []
    if dates:
        while lower <= upper:
            if lower not in dates:
                gaps.append(lower)
            lower += dt.timedelta(days=1)
    return {"latest": latest, "gaps": gaps, "has_history": bool(dates)}


def format_gap_ranges(days):
    if not days:
        return "ไม่มี"
    ranges = []
    start = previous = days[0]
    for day in [*days[1:], None]:
        if day is not None and day == previous + dt.timedelta(days=1):
            previous = day
            continue
        ranges.append(start.strftime("%d/%m/%Y") if start == previous else
                      f"{start:%d/%m/%Y}–{previous:%d/%m/%Y}")
        start = previous = day
    # Large historical selections must not create an unreadable wall of dates.
    return ", ".join(ranges[:6]) + (f" · รวม {len(days)} วัน (แสดง 6 ช่วงแรก)"
                                     if len(ranges) > 6 else "")


@st.cache_data(ttl=CACHE_TTL_SEC, show_spinner=False)
def load_freshness(athlete_id, start, end, today):
    present = " OR ".join(f"{field} IS NOT NULL" for field in BODY_FIELDS)
    with closing(connect_db()) as conn:
        values = [row[0] for row in conn.execute(
            f"SELECT calendar_date FROM fact_daily_wellness WHERE athlete_id = ? AND ({present})",
            (athlete_id,),
        )]
    result = summarize_dates(values, start, end, today)
    stamp = to_bangkok_timestamp(load_latest_fetch(athlete_id))
    result["received_at"] = stamp.strftime("%d/%m/%Y %H:%M น.") if pd.notna(stamp) else "–"
    result["latest_text"] = result["latest"].strftime("%d/%m/%Y") if result["latest"] else "ยังไม่มี"
    result["gaps_text"] = format_gap_ranges(result["gaps"]) if result["has_history"] else "ยังไม่มีประวัติให้ตรวจ"
    return result


def read_sync_summary(slug):
    """Allowlist user-facing fields; malformed files and raw errors aren't rendered."""
    try:
        payload = json.loads((data_dir() / "sync_status" / f"{slug}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = None
    if not isinstance(payload, dict) or type(payload.get("ok")) is not bool:
        return {"result": "ไม่มีบันทึกที่อ่านได้", "finished": "–", "action":
                "ตรวจหน้าสถานะระบบและคู่มือเริ่มซิงก์ หากยังไม่เชื่อมบัญชีให้ตั้งค่าบนเครื่องใช้งาน"}
    failures = payload.get("endpoint_failures")
    partial = isinstance(failures, list) and bool(failures)
    result = "สำเร็จบางส่วน" if payload["ok"] and partial else "สำเร็จ" if payload["ok"] else "ล้มเหลว"
    finished = "–"
    try:
        stamp = dt.datetime.fromisoformat(payload["finished_at"])
        # Legacy records use the syncing machine's local time, not UTC.
        if stamp.tzinfo is not None:
            stamp = to_bangkok_timestamp(stamp)
        finished = stamp.strftime("%d/%m/%Y %H:%M")
    except (KeyError, TypeError, ValueError):
        pass
    action = {
        "token": "ขอ token ใหม่บนเครื่องใช้งานผ่าน เพิ่มนักกีฬา.bat แล้วลองซิงก์อีกครั้ง",
        "network": "ตรวจอินเทอร์เน็ตและ Garmin Connect แล้วรอรอบถัดไปหรือลองซิงก์ด้วยมือ",
    }.get(payload.get("reason") if isinstance(payload.get("reason"), str) else None)
    if payload["ok"]:
        action = "รอรอบถัดไปเพื่อลองช่องที่ล้มอีกครั้ง" if partial else "หากวันยังว่าง ให้ตรวจวันเดียวกันใน Garmin Connect"
    elif not action:
        action = "ตรวจ log บนเครื่องใช้งานและทำตามคู่มือซิงก์ โดยไม่ส่ง token หรือรหัสผ่าน"
    return {"result": result, "finished": finished, "action": action}
