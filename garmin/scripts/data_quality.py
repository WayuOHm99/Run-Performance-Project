#!/usr/bin/env python3
"""Read-only data-quality checks shared by drift and health monitoring.

All calendar windows are calculated in Asia/Bangkok.  SQLite's ``date('now')``
is UTC, which moves the boundary to 07:00 in Thailand and can accidentally put
an unfinished local day into a completed-day comparison.
"""

from __future__ import annotations

import math
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone


# Thailand has used UTC+07:00 without daylight-saving transitions since 1920.
# A fixed offset avoids a runtime dependency on the optional Windows ``tzdata``
# package for a monitor that must also work before the project venv is activated.
BANGKOK = timezone(timedelta(hours=7), name="Asia/Bangkok")

GOOD_RATE = 0.80
BAD_RATE = 0.20
MATERIAL_BAD_RATE = 0.60
MATERIAL_DROP = 0.30
SHORT_BAD_RATE = 0.50
MIN_SAMPLE = 5

# Optional/device-dependent fields are safe to include: drift is judged against
# that athlete's own history, so a field which has never existed is not flagged.
WELLNESS_FIELDS = (
    "resting_hr",
    "hrv_weekly_avg",
    "hrv_last_night",
    "hrv_status",
    "sleep_score",
    "sleep_duration_sec",
    "deep_sleep_sec",
    "light_sleep_sec",
    "rem_sleep_sec",
    "awake_sec",
    "body_battery_high",
    "body_battery_low",
    "bb_at_wake",
    "bb_charged",
    "bb_drained",
    "bb_during_sleep",
    "bb_most_recent",
    "stress_avg",
    "max_stress",
    "steps",
    "steps_goal",
    "floors_ascended",
    "active_kilocalories",
    "bmr_kilocalories",
    "active_seconds",
    "avg_waking_respiration",
    "avg_sleep_respiration",
    "highest_respiration",
    "lowest_respiration",
    "training_readiness",
    "readiness_level",
    "readiness_feedback",
    "readiness_feedback_long",
    "readiness_timestamp_utc",
    "readiness_timestamp_local",
    "readiness_input_context",
    "readiness_sleep_factor_pct",
    "acute_load",
    "acwr_percent",
    "acwr_factor_feedback",
    "hrv_factor_pct",
    "recovery_time_min",
    # Kept while old databases migrate.  Despite its old name, stored values
    # are raw Garmin minutes and the dashboard treats it as a fallback only.
    "recovery_time_hrs",
    "recovery_time_factor_pct",
    "recovery_time_change_phrase",
    "stress_history_pct",
    "training_status",
    "vo2max_trend",
    "fitness_age",
    "endurance_score",
    "hill_score_overall",
    "hill_score_strength",
    "hill_score_endurance",
    "lactate_threshold_hr",
    "lactate_threshold_pace_min_km",
)

ACTIVITY_FIELDS = (
    "duration_sec", "distance_m", "avg_hr", "max_hr", "calories",
    "training_load", "training_effect_aerobic", "training_effect_anaerobic",
    "avg_cadence",
    "avg_power", "normalized_power", "elevation_gain_m",
)

WELLNESS_METADATA_FIELDS = {
    "athlete_id", "calendar_date", "fetched_at", "repair_attempted_at_utc",
    # Internal Garmin identifier retained for correlation only; it is not a
    # physiological metric and must never appear in field-coverage reports.
    "readiness_device_id",
}

# Fields which establish that a wellness row contains a real partial snapshot,
# rather than being a placeholder row created solely for an extras endpoint.
ACTIVE_WELLNESS_FIELDS = (
    "resting_hr",
    "sleep_score",
    "body_battery_high",
    "hrv_last_night",
    "stress_avg",
    "steps",
    "avg_waking_respiration",
    "avg_sleep_respiration",
)

PARTIAL_SNAPSHOT_FIELDS = (
    "resting_hr",
    "body_battery_high",
    "stress_avg",
    "steps",
    "sleep_score",
    "hrv_last_night",
    "avg_sleep_respiration",
)

# Monitoring bounds are intentionally conservative.  They flag records for
# review; ingestion owns the stricter decision about whether to discard input.
RANGE_RULES = {
    "resting_hr": (25, 120),
    "hrv_weekly_avg": (1, 300),
    "hrv_last_night": (1, 300),
    "sleep_score": (0, 100),
    "sleep_duration_sec": (0, 86_400),
    "deep_sleep_sec": (0, 86_400),
    "light_sleep_sec": (0, 86_400),
    "rem_sleep_sec": (0, 86_400),
    "awake_sec": (0, 86_400),
    "body_battery_high": (5, 100),
    "body_battery_low": (5, 100),
    "bb_at_wake": (5, 100),
    # Charged/drained are cumulative deltas and can legitimately exceed the
    # instantaneous 5–100 Body Battery scale.
    "bb_charged": (0, 1_000),
    "bb_drained": (0, 1_000),
    "bb_during_sleep": (0, 1_000),
    "bb_most_recent": (5, 100),
    "stress_avg": (0, 100),
    "max_stress": (0, 100),
    "steps": (0, 200_000),
    "steps_goal": (0, 200_000),
    "floors_ascended": (0, 1_000),
    "active_kilocalories": (0, 30_000),
    "bmr_kilocalories": (0, 30_000),
    "active_seconds": (0, 86_400),
    "avg_waking_respiration": (4, 80),
    "avg_sleep_respiration": (4, 80),
    "highest_respiration": (4, 100),
    "lowest_respiration": (4, 80),
    "training_readiness": (0, 100),
    "hrv_factor_pct": (0, 100),
    "stress_history_pct": (0, 100),
    "recovery_time_min": (0, 5_760),
    "recovery_time_hrs": (0, 5_760),
}


def bangkok_today(now: datetime | date | None = None) -> date:
    """Return the Thailand calendar date for an aware or naive timestamp.

    A naive value supplied by a caller is treated as Bangkok wall time.  An
    aware value is converted by instant, which is the important case for UTC
    timestamps in tests and monitoring integrations.
    """
    if now is None:
        return datetime.now(BANGKOK).date()
    if isinstance(now, date) and not isinstance(now, datetime):
        return now
    if now.tzinfo is None:
        now = now.replace(tzinfo=BANGKOK)
    return now.astimezone(BANGKOK).date()


def completed_window(today: date, days: int, offset_days: int = 0) -> tuple[str, str]:
    """Inclusive date bounds ending before today.

    ``offset_days=0`` is the latest completed window; ``offset_days=days`` is
    the equally-sized window immediately preceding it.
    """
    end = today - timedelta(days=1 + offset_days)
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _identifier(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(f"unsafe SQL identifier: {name!r}")
    return f'"{name}"'


def json_safe(value):
    """Return a strict-JSON-safe representation of diagnostic data.

    Range checks intentionally encounter non-finite numbers and occasionally
    malformed SQLite values.  Python's default JSON encoder writes NaN/Infinity
    tokens, which are not valid JSON, so normalize them before CLI serialization.
    """
    if isinstance(value, float) and not math.isfinite(value):
        if math.isnan(value):
            return "NaN"
        return "Infinity" if value > 0 else "-Infinity"
    if isinstance(value, (bytes, bytearray, memoryview)):
        return repr(bytes(value))
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return value


def _rate(
    conn: sqlite3.Connection,
    *,
    table: str,
    field: str,
    athlete_id: int,
    date_field: str,
    start: str,
    end: str,
    active_fields: tuple[str, ...] = (),
    extra_condition: str = "",
    denominator_days: int | None = None,
    normalize_date: bool = False,
) -> tuple[int, int]:
    field_sql = _identifier(field)
    date_sql = _identifier(date_field)
    if normalize_date:
        # start_time_local is already a wall-clock value.  Taking its YYYY-MM-DD
        # prefix accepts both ``T`` and space separators without SQLite date()
        # converting an optional +07:00 suffix to UTC and shifting the day.
        date_sql = f"substr({date_sql}, 1, 10)"
    active = ""
    if active_fields:
        active = " AND (" + " OR ".join(
            f"{_identifier(name)} IS NOT NULL" for name in active_fields
        ) + ")"
    row = conn.execute(
        f"SELECT COUNT({field_sql}), COUNT(*) FROM {_identifier(table)} "
        f"WHERE athlete_id = ? AND {date_sql} BETWEEN ? AND ?"
        f"{extra_condition}{active}",
        (athlete_id, start, end),
    ).fetchone()
    non_null = int(row[0] or 0)
    total = int(row[1] or 0) if denominator_days is None else denominator_days
    return non_null, total


def coverage_for_athlete(
    conn: sqlite3.Connection,
    athlete_id: int,
    *,
    today: datetime | date | None = None,
) -> list[dict]:
    """Return per-field 30-day/previous-30-day and 7-day coverage."""
    local_today = bangkok_today(today)
    recent_start, recent_end = completed_window(local_today, 30)
    prior_start, prior_end = completed_window(local_today, 30, 30)
    short_start, short_end = completed_window(local_today, 7)
    short_base_start, short_base_end = completed_window(local_today, 30, 7)
    rows: list[dict] = []

    wellness_columns = table_columns(conn, "fact_daily_wellness")
    # `recovery_time_hrs` is a retired, misleading legacy name.  Once the
    # correctly named minute column exists, monitoring it would create a planned
    # 100% -> 0% drift alert because new ingestion intentionally stops writing it.
    legacy_exclusions = (
        {"recovery_time_hrs"} if "recovery_time_min" in wellness_columns else set()
    )
    wellness_fields = [
        field for field in WELLNESS_FIELDS if field not in legacy_exclusions
    ]
    wellness_fields.extend(sorted(
        wellness_columns - set(wellness_fields) - WELLNESS_METADATA_FIELDS
        - legacy_exclusions
    ))
    for field in wellness_fields:
        if field not in wellness_columns:  # supports pre-migration databases
            continue
        rows.append({
            "table": "wellness",
            "field": field,
            "recent": _rate(
                conn, table="fact_daily_wellness", field=field,
                athlete_id=athlete_id, date_field="calendar_date",
                start=recent_start, end=recent_end, denominator_days=30,
            ),
            "prior": _rate(
                conn, table="fact_daily_wellness", field=field,
                athlete_id=athlete_id, date_field="calendar_date",
                start=prior_start, end=prior_end, denominator_days=30,
            ),
            "short": _rate(
                conn, table="fact_daily_wellness", field=field,
                athlete_id=athlete_id, date_field="calendar_date",
                start=short_start, end=short_end, denominator_days=7,
            ),
            "short_baseline": _rate(
                conn, table="fact_daily_wellness", field=field,
                athlete_id=athlete_id, date_field="calendar_date",
                start=short_base_start, end=short_base_end, denominator_days=30,
            ),
            "calendar_days": 30,
        })

    activity_columns = table_columns(conn, "fact_activity")
    deleted_filter = " AND deleted_at IS NULL" if "deleted_at" in activity_columns else ""
    for field in ACTIVITY_FIELDS:
        if field not in activity_columns:
            continue
        rows.append({
            "table": "activity",
            "field": field,
            "recent": _rate(
                conn, table="fact_activity", field=field,
                athlete_id=athlete_id, date_field="start_time_local",
                start=recent_start, end=recent_end,
                extra_condition=deleted_filter, normalize_date=True,
            ),
            "prior": _rate(
                conn, table="fact_activity", field=field,
                athlete_id=athlete_id, date_field="start_time_local",
                start=prior_start, end=prior_end,
                extra_condition=deleted_filter, normalize_date=True,
            ),
            "short": _rate(
                conn, table="fact_activity", field=field,
                athlete_id=athlete_id, date_field="start_time_local",
                start=short_start, end=short_end,
                extra_condition=deleted_filter, normalize_date=True,
            ),
            "short_baseline": _rate(
                conn, table="fact_activity", field=field,
                athlete_id=athlete_id, date_field="start_time_local",
                start=short_base_start, end=short_base_end,
                extra_condition=deleted_filter, normalize_date=True,
            ),
            "calendar_days": 30,
        })
    return rows


def judge_drift(table: str, field: str, recent: tuple[int, int], prior: tuple[int, int], *,
                horizon_days: int = 30) -> dict | None:
    """Judge a coverage drop while avoiding unsupported-device false alarms."""
    recent_nn, recent_total = recent
    prior_nn, prior_total = prior
    if recent_total < MIN_SAMPLE or prior_total < MIN_SAMPLE:
        return None
    recent_rate = recent_nn / recent_total
    prior_rate = prior_nn / prior_total
    catastrophic = prior_rate >= GOOD_RATE and recent_rate <= BAD_RATE
    material = (
        prior_rate >= GOOD_RATE
        and recent_rate <= (SHORT_BAD_RATE if horizon_days <= 7 else MATERIAL_BAD_RATE)
        and prior_rate - recent_rate >= MATERIAL_DROP
    )
    if not (catastrophic or material):
        return None
    return {
        "kind": "drift",
        "level": "ERROR" if catastrophic else "WARNING",
        "table": table,
        "field": field,
        "prior_rate": prior_rate,
        "recent_rate": recent_rate,
        "recent": recent,
        "prior": prior,
        "horizon_days": horizon_days,
    }


def drift_findings(coverage: list[dict]) -> list[dict]:
    findings = []
    for item in coverage:
        monthly = judge_drift(
            item["table"], item["field"], item["recent"], item["prior"],
            horizon_days=30,
        )
        short = judge_drift(
            item["table"], item["field"], item["short"], item["short_baseline"],
            horizon_days=7,
        )
        # A short-window finding is more actionable and subsumes the same
        # monthly symptom.  Keep one line per field to avoid alert fatigue.
        if short:
            findings.append(short)
        elif monthly:
            findings.append(monthly)
    return findings


def partial_snapshot_findings(
    conn: sqlite3.Connection,
    athlete_id: int,
    *,
    today: datetime | date | None = None,
) -> list[dict]:
    """Detect a missing, empty, or partial completed-yesterday snapshot."""
    columns = table_columns(conn, "fact_daily_wellness")
    monitored = tuple(f for f in PARTIAL_SNAPSHOT_FIELDS if f in columns)
    if len(monitored) < 4:
        return []
    local_today = bangkok_today(today)
    yesterday = (local_today - timedelta(days=1)).isoformat()
    baseline_start = (local_today - timedelta(days=31)).isoformat()
    baseline_end = (local_today - timedelta(days=2)).isoformat()
    expected = []
    for field in monitored:
        nn, total = _rate(
            conn, table="fact_daily_wellness", field=field,
            athlete_id=athlete_id, date_field="calendar_date",
            start=baseline_start, end=baseline_end, denominator_days=30,
        )
        if total >= MIN_SAMPLE and nn / total >= GOOD_RATE:
            expected.append(field)

    # Do not call a new/sparse/unsupported athlete broken until its own completed
    # 30-day baseline establishes at least one regularly delivered field.
    if not expected:
        return []

    selected = ", ".join(_identifier(f) for f in monitored)
    row = conn.execute(
        f"SELECT {selected} FROM fact_daily_wellness "
        "WHERE athlete_id = ? AND calendar_date = ?",
        (athlete_id, yesterday),
    ).fetchone()
    row_missing = row is None
    if row_missing:
        values = {field: None for field in monitored}
    else:
        values = dict(zip(monitored, row, strict=True))

    present = [field for field in expected if values[field] is not None]
    missing = [field for field in expected if values[field] is None]
    if not present:
        return [{
            "kind": "missing_snapshot",
            "level": "ERROR",
            "table": "wellness",
            "field": ",".join(missing),
            "calendar_date": yesterday,
            "missing": missing,
            "present": [],
            "reason": "row_missing" if row_missing else "row_empty",
        }]

    nightly_missing = {
        "sleep_score", "hrv_last_night", "avg_sleep_respiration"
    }.intersection(missing)
    daytime_present = {
        "resting_hr", "body_battery_high", "stress_avg", "steps"
    }.intersection(present)
    if len(missing) < 2 or len(nightly_missing) < 2 or not daytime_present:
        return []
    return [{
        "kind": "partial_snapshot",
        "level": "WARNING",
        "table": "wellness",
        "field": ",".join(missing),
        "calendar_date": yesterday,
        "missing": missing,
        "present": present,
    }]


def range_findings(
    conn: sqlite3.Connection,
    athlete_id: int,
    *,
    today: datetime | date | None = None,
    lookback_days: int = 90,
) -> list[dict]:
    """Find sentinels, non-finite values, invalid ranges and row relations."""
    columns = table_columns(conn, "fact_daily_wellness")
    local_today = bangkok_today(today)
    start = (local_today - timedelta(days=lookback_days - 1)).isoformat()
    end = local_today.isoformat()
    findings: list[dict] = []
    for field, (low, high) in RANGE_RULES.items():
        if field not in columns:
            continue
        rows = conn.execute(
            f"SELECT calendar_date, {_identifier(field)} FROM fact_daily_wellness "
            f"WHERE athlete_id = ? AND calendar_date BETWEEN ? AND ? "
            f"AND {_identifier(field)} IS NOT NULL",
            (athlete_id, start, end),
        ).fetchall()
        bad = []
        for day, value in rows:
            try:
                number = float(value)
            except (TypeError, ValueError):
                bad.append((day, value))
                continue
            if not math.isfinite(number) or number < low or number > high:
                bad.append((day, value))
        if bad:
            findings.append({
                "kind": "range",
                "level": "WARNING",
                "table": "wellness",
                "field": field,
                "bounds": (low, high),
                "count": len(bad),
                "examples": bad[:5],
            })

    relations = (
        ("body_battery_high", "body_battery_low", ">="),
        ("highest_respiration", "lowest_respiration", ">="),
    )
    for upper, lower, relation in relations:
        if upper not in columns or lower not in columns:
            continue
        bad = conn.execute(
            f"SELECT calendar_date, {_identifier(upper)}, {_identifier(lower)} "
            "FROM fact_daily_wellness WHERE athlete_id = ? "
            "AND calendar_date BETWEEN ? AND ? "
            f"AND {_identifier(upper)} IS NOT NULL AND {_identifier(lower)} IS NOT NULL "
            f"AND {_identifier(upper)} < {_identifier(lower)}",
            (athlete_id, start, end),
        ).fetchall()
        if bad:
            findings.append({
                "kind": "relation",
                "level": "WARNING",
                "table": "wellness",
                "field": f"{upper}{relation}{lower}",
                "count": len(bad),
                "examples": bad[:5],
            })
    return findings


def check_athlete(
    conn: sqlite3.Connection,
    slug: str,
    athlete_id: int,
    *,
    today: datetime | date | None = None,
) -> tuple[list[dict], list[dict]]:
    """Return ``(findings, coverage)`` for one athlete."""
    coverage = coverage_for_athlete(conn, athlete_id, today=today)
    findings = drift_findings(coverage)
    findings += partial_snapshot_findings(conn, athlete_id, today=today)
    findings += range_findings(conn, athlete_id, today=today)
    for finding in findings:
        finding["slug"] = slug
    return findings, coverage
