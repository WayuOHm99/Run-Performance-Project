#!/usr/bin/env python3
"""Validate the privacy-safe local heartbeat used by GitHub monitoring."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


MAX_FUTURE_MINUTES = 10


class ValidationError(ValueError):
    pass


def _aware_datetime(value, field):
    if not isinstance(value, str):
        raise ValidationError(f"{field}_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"{field}_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValidationError(f"{field}_timezone_missing")
    return parsed


def _clock(value):
    try:
        parsed = time.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("offline_window_invalid") from exc
    if parsed.tzinfo is not None:
        raise ValidationError("offline_window_invalid")
    return parsed


def _inside_window(current, start, end):
    if start < end:
        return start <= current < end
    return current >= start or current < end


def _window_start(current, start, end):
    local_clock = current.time().replace(tzinfo=None)
    start_date = current.date()
    if start >= end and local_clock < end:
        start_date -= timedelta(days=1)
    return datetime.combine(start_date, start).replace(tzinfo=current.tzinfo)


def _validated_summary(payload):
    if not isinstance(payload, dict):
        raise ValidationError("payload_invalid")
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise ValidationError("summary_invalid")
    values = {}
    for key in ("ok", "warning", "error", "total"):
        value = summary.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValidationError("summary_invalid")
        values[key] = value
    if values["ok"] + values["warning"] + values["error"] != values["total"]:
        raise ValidationError("summary_invalid")
    if payload.get("status") not in {"ok", "error"}:
        raise ValidationError("status_invalid")
    return values


def validate(
    payload,
    *,
    now,
    local_timezone,
    offline_start,
    offline_end,
    max_age_hours=3,
):
    summary = _validated_summary(payload)
    generated = _aware_datetime(payload.get("generated_at"), "generated_at")
    now = _aware_datetime(now, "now") if isinstance(now, str) else now
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValidationError("now_timezone_missing")

    age = now.astimezone(timezone.utc) - generated.astimezone(timezone.utc)
    age_minutes = round(age.total_seconds() / 60, 1)
    base = {"age_minutes": age_minutes, "summary": summary}
    if age_minutes < -MAX_FUTURE_MINUTES:
        return {"ok": False, "reason": "future", **base}
    if summary["error"] > 0 or payload["status"] != "ok":
        return {"ok": False, "reason": "unhealthy", **base}
    if age.total_seconds() <= max_age_hours * 3600:
        return {"ok": True, "reason": "fresh", **base}

    local_clock = now.astimezone(local_timezone).time().replace(tzinfo=None)
    if _inside_window(local_clock, offline_start, offline_end):
        local_now = now.astimezone(local_timezone)
        earliest_expected = _window_start(
            local_now, offline_start, offline_end
        ) - timedelta(hours=max_age_hours)
        if generated.astimezone(local_timezone) >= earliest_expected:
            return {"ok": True, "reason": "planned_offline", **base}
    return {"ok": False, "reason": "stale", **base}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("heartbeat", type=Path)
    parser.add_argument("--now", default=datetime.now(timezone.utc).isoformat())
    parser.add_argument("--timezone", default="Asia/Bangkok")
    parser.add_argument("--offline-start", default="01:00")
    parser.add_argument("--offline-end", default="08:00")
    parser.add_argument("--max-age-hours", type=float, default=3)
    args = parser.parse_args(argv)

    try:
        if args.max_age_hours <= 0:
            raise ValidationError("max_age_invalid")
        payload = json.loads(args.heartbeat.read_text(encoding="utf-8"))
        result = validate(
            payload,
            now=args.now,
            local_timezone=ZoneInfo(args.timezone),
            offline_start=_clock(args.offline_start),
            offline_end=_clock(args.offline_end),
            max_age_hours=args.max_age_hours,
        )
    except (
        OSError, json.JSONDecodeError, ValidationError, ZoneInfoNotFoundError
    ):
        result = {"ok": False, "reason": "invalid"}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
