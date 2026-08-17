"""Read-only, application-aware SQLite validation for backup recovery."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


GARMIN_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PATH = GARMIN_ROOT / "scripts" / "dashboard.py"
BANGKOK = ZoneInfo("Asia/Bangkok")
DEFAULT_MAX_AGE_DAYS = 7
ESSENTIAL_TABLES = {
    "dim_athlete",
    "dim_athlete_device",
    "fact_activity",
    "fact_activity_split",
    "fact_daily_wellness",
    "fact_race_prediction",
    "fact_personal_record",
    "fact_gear",
    "fact_body_composition",
}
ESSENTIAL_COLUMNS = {
    "dim_athlete": {"athlete_id", "slug"},
    "fact_activity": {
        "activity_id", "athlete_id", "start_time_local", "deleted_at",
    },
    "fact_daily_wellness": {"athlete_id", "calendar_date"},
}


def _base(database: Path) -> dict:
    return {
        "ok": False,
        "reason": "unknown",
        "quick_check": "not_run",
        "size_bytes": database.stat().st_size if database.is_file() else 0,
    }


def _parse_now(value: datetime | str | None) -> datetime:
    if value is None:
        parsed = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("now_timezone_missing")
    return parsed


def _dashboard_startup_probe(database: Path, timeout: int = 30) -> dict:
    """Launch the real Streamlit app against a disposable copy of the restore."""
    try:
        from streamlit.testing.v1 import AppTest
    except ImportError:
        return {"ok": False, "reason": "dashboard_dependency_missing"}

    previous = os.environ.get("GARMIN_DATA_DIR")
    try:
        with tempfile.TemporaryDirectory(
            prefix="run-performance-dashboard-probe-"
        ) as raw:
            isolated = Path(raw)
            shutil.copy2(database, isolated / "garmin.db")
            os.environ["GARMIN_DATA_DIR"] = str(isolated)
            app = AppTest.from_file(str(DASHBOARD_PATH)).run(timeout=timeout)
            if list(app.exception):
                return {"ok": False, "reason": "dashboard_exception"}
    except Exception as exc:
        return {
            "ok": False,
            "reason": f"dashboard_probe_error:{type(exc).__name__}",
        }
    finally:
        if previous is None:
            os.environ.pop("GARMIN_DATA_DIR", None)
        else:
            os.environ["GARMIN_DATA_DIR"] = previous
    return {"ok": True, "reason": "ok"}


def validate(
    path: str | Path,
    *,
    now: datetime | str | None = None,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    dashboard_probe: bool = False,
) -> dict:
    database = Path(path)
    result = _base(database)
    if not database.is_file():
        result.update(reason="missing", quick_check="missing")
        return result
    if isinstance(max_age_days, bool) or not isinstance(max_age_days, int) or max_age_days < 1:
        result["reason"] = "max_age_invalid"
        return result
    try:
        current = _parse_now(now)
    except (TypeError, ValueError):
        result["reason"] = "now_invalid"
        return result

    uri = f"file:{database.resolve().as_posix()}?mode=ro&immutable=1"
    try:
        connection = sqlite3.connect(uri, uri=True)
        try:
            messages = [
                str(row[0]) for row in connection.execute("PRAGMA quick_check")
            ]
            result["quick_check"] = "; ".join(messages)
            if messages != ["ok"]:
                result["reason"] = "quick_check_failed"
                return result

            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            missing_tables = ESSENTIAL_TABLES - tables
            if missing_tables:
                result.update(
                    reason="schema_missing",
                    schema_table_count=len(ESSENTIAL_TABLES - missing_tables),
                )
                return result
            for table, required in ESSENTIAL_COLUMNS.items():
                columns = {
                    row[1] for row in connection.execute(f"PRAGMA table_info({table})")
                }
                if not required.issubset(columns):
                    result.update(reason="schema_columns_missing")
                    return result

            athlete_count = connection.execute(
                "SELECT COUNT(*) FROM dim_athlete "
                "WHERE slug IS NOT NULL AND trim(slug) <> ''"
            ).fetchone()[0]
            active_activity_count = connection.execute(
                "SELECT COUNT(*) FROM fact_activity a "
                "JOIN dim_athlete d ON d.athlete_id = a.athlete_id "
                "WHERE a.deleted_at IS NULL"
            ).fetchone()[0]
            wellness_count = connection.execute(
                "SELECT COUNT(*) FROM fact_daily_wellness w "
                "JOIN dim_athlete d ON d.athlete_id = w.athlete_id"
            ).fetchone()[0]
            result.update(
                schema_table_count=len(ESSENTIAL_TABLES),
                athlete_count=athlete_count,
                active_activity_count=active_activity_count,
                wellness_count=wellness_count,
            )
            if min(athlete_count, active_activity_count, wellness_count) < 1:
                result["reason"] = "content_empty"
                return result

            activity_date = connection.execute(
                "SELECT MAX(substr(a.start_time_local, 1, 10)) "
                "FROM fact_activity a "
                "JOIN dim_athlete d ON d.athlete_id = a.athlete_id "
                "WHERE a.deleted_at IS NULL"
            ).fetchone()[0]
            wellness_date = connection.execute(
                "SELECT MAX(w.calendar_date) FROM fact_daily_wellness w "
                "JOIN dim_athlete d ON d.athlete_id = w.athlete_id"
            ).fetchone()[0]
        finally:
            connection.close()
    except (OSError, sqlite3.Error) as exc:
        result.update(
            reason="sqlite_error",
            quick_check=f"error: {exc}",
            size_bytes=database.stat().st_size,
        )
        return result

    try:
        latest_activity = date.fromisoformat(str(activity_date)[:10])
        latest_wellness = date.fromisoformat(str(wellness_date)[:10])
    except (TypeError, ValueError):
        result["reason"] = "freshness_invalid"
        return result
    today = current.astimezone(BANGKOK).date()
    activity_age_days = (today - latest_activity).days
    wellness_age_days = (today - latest_wellness).days
    result.update(
        latest_activity_date=latest_activity.isoformat(),
        latest_wellness_date=latest_wellness.isoformat(),
        data_age_days=max(activity_age_days, wellness_age_days),
    )
    if min(activity_age_days, wellness_age_days) < -1:
        result["reason"] = "data_future"
        return result
    if max(activity_age_days, wellness_age_days) > max_age_days:
        result["reason"] = "data_stale"
        return result

    if dashboard_probe:
        probe = _dashboard_startup_probe(database)
        result["dashboard_probe"] = probe["reason"]
        if not probe["ok"]:
            result["reason"] = "dashboard_probe_failed"
            return result

    result.update(ok=True, reason="ok")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit one JSON object")
    parser.add_argument("--now", help="aware ISO timestamp (test/recovery seam)")
    parser.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS)
    parser.add_argument("--dashboard-probe", action="store_true")
    parser.add_argument("database", type=Path)
    args = parser.parse_args(argv)

    result = validate(
        args.database,
        now=args.now,
        max_age_days=args.max_age_days,
        dashboard_probe=args.dashboard_probe,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    elif result["ok"]:
        print(
            "OK: Garmin schema/content/freshness/dashboard recovery proof passed "
            f"({result['size_bytes']} bytes)"
        )
    else:
        print(f"ERROR: {result['reason']} ({result['quick_check']})")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
