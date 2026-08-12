"""Read-only quick health check on garmin.db."""
import os
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("GARMIN_DATA_DIR", PROJECT_ROOT / "data"))
DB = DATA_DIR / "garmin.db"


def use_data_dir(path) -> Path:
    global DATA_DIR, DB
    previous = DATA_DIR
    DATA_DIR = Path(path)
    DB = DATA_DIR / "garmin.db"
    return previous


def main() -> int:
    if not DB.exists():
        print(f"❌ Database not found: {DB}")
        return 1

    uri = f"file:{DB.resolve().as_posix()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        print(f"❌ Open database read-only failed: {exc}")
        return 1

    try:
        print("=" * 50)
        print(f"Database: {DB}")
        print(f"Size: {DB.stat().st_size / 1024:.1f} KB")
        print("=" * 50)

        tables = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        for (table,) in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            count = conn.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
            print(f"  {table}: {count} rows")

        print("\nAthletes:")
        for row in conn.execute(
            "SELECT athlete_id, slug, display_name, garmin_full_name FROM dim_athlete"
        ).fetchall():
            print(f"  #{row[0]} {row[1]} ({row[2]}) - Garmin: {row[3]}")

        print("\nActivity sample (last 5):")
        for row in conn.execute(
            "SELECT a.slug, f.activity_type, f.start_time_local, "
            "f.distance_m, f.duration_sec "
            "FROM fact_activity f "
            "JOIN dim_athlete a ON f.athlete_id = a.athlete_id "
            "WHERE f.deleted_at IS NULL "
            "ORDER BY f.start_time_local DESC LIMIT 5"
        ).fetchall():
            dist_km = round(row[3] / 1000, 2) if row[3] else 0
            dur_min = round(row[4] / 60, 1) if row[4] else 0
            print(
                f"  {row[0]} | {row[1]} | {row[2]} | "
                f"{dist_km} km | {dur_min} min"
            )

        print("\nWellness sample (last 5):")
        for row in conn.execute(
            "SELECT a.slug, w.calendar_date, w.resting_hr, w.hrv_last_night, "
            "w.sleep_score, w.body_battery_high, w.training_readiness "
            "FROM fact_daily_wellness w "
            "JOIN dim_athlete a ON w.athlete_id = a.athlete_id "
            "ORDER BY w.calendar_date DESC LIMIT 5"
        ).fetchall():
            print(
                f"  {row[0]} | {row[1]} | RHR:{row[2]} | HRV:{row[3]} "
                f"| Sleep:{row[4]} | BB:{row[5]} | Ready:{row[6]}"
            )
    except (OSError, sqlite3.Error) as exc:
        print(f"❌ Database check failed: {exc}")
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
