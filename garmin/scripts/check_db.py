"""Quick health check on garmin.db"""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "garmin.db"
conn = sqlite3.connect(DB)

# List tables and row counts
print("=" * 50)
print(f"Database: {DB}")
print(f"Size: {DB.stat().st_size / 1024:.1f} KB")
print("=" * 50)

tables = conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
).fetchall()

for (tbl,) in tables:
    count = conn.execute(f"SELECT COUNT(*) FROM [{tbl}]").fetchone()[0]
    print(f"  {tbl}: {count} rows")

# Athletes
print("\nAthletes:")
for row in conn.execute("SELECT athlete_id, slug, display_name, garmin_full_name FROM dim_athlete").fetchall():
    print(f"  #{row[0]} {row[1]} ({row[2]}) - Garmin: {row[3]}")

# Activity summary
print("\nActivity sample (last 5):")
for row in conn.execute(
    "SELECT a.slug, f.activity_type, f.start_time_local, f.distance_m, f.duration_sec "
    "FROM fact_activity f JOIN dim_athlete a ON f.athlete_id = a.athlete_id "
    "ORDER BY f.start_time_local DESC LIMIT 5"
).fetchall():
    dist_km = round(row[3] / 1000, 2) if row[3] else 0
    dur_min = round(row[4] / 60, 1) if row[4] else 0
    print(f"  {row[0]} | {row[1]} | {row[2]} | {dist_km} km | {dur_min} min")

# Wellness summary
print("\nWellness sample (last 5):")
for row in conn.execute(
    "SELECT a.slug, w.calendar_date, w.resting_hr, w.hrv_last_night, w.sleep_score, w.body_battery_high, w.training_readiness "
    "FROM fact_daily_wellness w JOIN dim_athlete a ON w.athlete_id = a.athlete_id "
    "ORDER BY w.calendar_date DESC LIMIT 5"
).fetchall():
    print(f"  {row[0]} | {row[1]} | RHR:{row[2]} | HRV:{row[3]} | Sleep:{row[4]} | BB:{row[5]} | Ready:{row[6]}")

conn.close()
