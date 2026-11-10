"""Launch the dashboard with disposable synthetic data; never connect to Garmin."""

import argparse
from contextlib import closing, contextmanager
import datetime as dt
import importlib.util
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time

from dashboard_domain import bangkok_date
import win_process

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

GARMIN_ROOT = Path(__file__).resolve().parent.parent


def seed_demo_data(conn, today):
    conn.executemany(
        "INSERT INTO dim_athlete (athlete_id, slug, display_name) VALUES (?, ?, ?)",
        [(1, "demo-a", "นักกีฬาทดลอง A"), (2, "demo-b", "นักกีฬาทดลอง B"),
         (3, "demo-new", "นักกีฬาทดลองใหม่")],
    )
    for athlete_id, rhr in [(1, 48), (2, 62)]:
        for offset in range(30):
            if athlete_id == 2 and offset in (0, 1, 5):
                continue
            day = today - dt.timedelta(days=offset)
            conn.execute(
                "INSERT INTO fact_daily_wellness (athlete_id, calendar_date, resting_hr,"
                " hrv_last_night, hrv_weekly_avg, hrv_status, sleep_score, sleep_duration_sec,"
                " bb_most_recent, body_battery_high, stress_avg, training_readiness,"
                " recovery_time_min, vo2max_trend, lactate_threshold_hr,"
                " lactate_threshold_pace_min_km, endurance_score, hill_score_overall,"
                " fitness_age, fetched_at) VALUES (?, ?, ?, ?, 58, 'BALANCED', ?,"
                " 25200, 70, 90, 30, 75, 480, ?, 172, 4.65, 6200, 58, 28, ?)",
                (athlete_id, day.isoformat(), rhr + offset % 3, 55 + offset % 8,
                 80 + offset % 5, 52 - (athlete_id - 1) * 4 + (offset % 3) * 0.2,
                 f"{day}T01:00:00Z"),
            )
            if offset == 0 or offset % 4 == 2:
                activity_id = athlete_id * 100 + offset
                conn.execute(
                    "INSERT INTO fact_activity (activity_id, athlete_id, activity_type,"
                    " activity_name, start_time_local, distance_m, duration_sec, avg_hr,"
                    " avg_pace_min_per_km, hr_zone1_sec, hr_zone2_sec, vo2max_value, fetched_at)"
                    " VALUES (?, ?, 'running', 'วิ่งทดลอง', ?, 6000, 2160, 140, 6, 360, 1800, 50, ?)",
                    (activity_id, athlete_id, f"{day} 06:00:00", f"{day}T01:00:00Z"),
                )
                for lap in range(1, 7):
                    conn.execute(
                        "INSERT INTO fact_activity_split (activity_id, split_num, distance_m,"
                        " duration_sec, avg_hr) VALUES (?, ?, 1000, 360, 140)", (activity_id, lap),
                    )
            if offset % 7 == 2:
                conn.execute(
                    "INSERT INTO fact_race_prediction (athlete_id, calendar_date, time_5k_sec,"
                    " time_10k_sec, time_half_sec, time_full_sec) VALUES (?, ?, 1500, 3120, 7200, 15000)",
                    (athlete_id, day.isoformat()),
                )
                conn.execute(
                    "INSERT INTO fact_body_composition (athlete_id, calendar_date, weight_kg,"
                    " bmi, body_fat_pct) VALUES (?, ?, 65, 22, 18)", (athlete_id, day.isoformat()),
                )
        conn.executemany(
            "INSERT INTO fact_personal_record (athlete_id, record_type_id, record_label, value, achieved_date)"
            " VALUES (?, ?, ?, ?, ?)",
            [
                (athlete_id, 3, "วิ่ง 5 กม. (วินาที)", 1320.0 + athlete_id * 60, today.isoformat()),
                (athlete_id, 4, "วิ่ง 10 กม. (วินาที)", 2790.0 + athlete_id * 120, today.isoformat()),
                (athlete_id, 7, "วิ่งไกลสุด (เมตร)", 21100.0, today.isoformat()),
            ],
        )
    base_utc = dt.datetime.combine(today, dt.time(6, 0), tzinfo=dt.timezone.utc) - dt.timedelta(hours=7)
    intraday_rows = []
    for step in range(24):
        stamp = (base_utc + dt.timedelta(minutes=step * 15)).strftime("%Y-%m-%dT%H:%M:%SZ")
        intraday_rows.extend((
            (1, today.isoformat(), "heart_rate", stamp, 56 + (step % 6) * 4),
            (1, today.isoformat(), "stress", stamp, 22 + (step % 5) * 6),
            (1, today.isoformat(), "body_battery", stamp, max(25, 92 - step * 2)),
        ))
    conn.executemany(
        "INSERT INTO fact_wellness_intraday (athlete_id, calendar_date, metric, ts_utc, value)"
        " VALUES (?, ?, ?, ?, ?)",
        intraday_rows,
    )
    conn.commit()


def create_demo_database(directory, today=None):
    path = Path(directory) / "garmin.db"
    if path.exists():
        raise FileExistsError("Demo refuses to overwrite an existing database")
    spec = importlib.util.spec_from_file_location("demo_schema", GARMIN_ROOT / "scripts" / "02_init_schema.py")
    schema = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(schema)
    schema.init_schema(path)
    with closing(sqlite3.connect(path)) as conn:
        seed_demo_data(conn, today or bangkok_date())
    return path


@contextmanager
def shutdown_signals():
    def stop_demo(_signal, _frame):
        raise KeyboardInterrupt

    signals = [signal.SIGTERM]
    if hasattr(signal, "SIGBREAK"):
        signals.append(signal.SIGBREAK)
    previous = {sig: signal.signal(sig, stop_demo) for sig in signals}
    try:
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8501)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    # No user-supplied output directory: production paths cannot be selected accidentally.
    with shutdown_signals(), tempfile.TemporaryDirectory(
            prefix="run-performance-demo-", ignore_cleanup_errors=True) as directory:
        create_demo_database(directory)
        environment = dict(os.environ, GARMIN_DATA_DIR=directory, GARMIN_DASHBOARD_DEMO="1")
        print(f"กำลังเปิด Demo ที่ http://127.0.0.1:{args.port} (กด Ctrl+C เพื่อปิด)...", flush=True)
        process = win_process.popen(
            [sys.executable, "-m", "streamlit", "run", "scripts/dashboard.py",
             "--server.address=127.0.0.1", f"--server.port={args.port}",
             "--server.headless=true", "--browser.gatherUsageStats=false"],
            cwd=GARMIN_ROOT, env=environment, stdout=sys.stdout, stderr=sys.stderr,
        )
        try:
            return process.wait()
        except KeyboardInterrupt:
            return 0
        finally:
            if process.poll() is None:
                if os.name == "nt":
                    win_process.run(
                        ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                    )
                else:
                    process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
            for _ in range(10):
                if not Path(directory).exists():
                    break
                shutil.rmtree(directory, ignore_errors=True)
                if Path(directory).exists():
                    time.sleep(0.1)


if __name__ == "__main__":
    raise SystemExit(main())
