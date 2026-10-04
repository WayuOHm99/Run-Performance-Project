"""Exercise the real dashboard in Chromium using an isolated synthetic database.

Run from garmin/ with: uv run --frozen --group ci python tests/browser_smoke.py
Use --chromium-path when Chromium is already installed locally.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from dashboard_tab_harness import GARMIN_ROOT, LAST_DAY, new_test_db


def seed_browser_data(directory):
    conn = new_test_db(directory)
    try:
        conn.executemany(
            "INSERT INTO dim_athlete (athlete_id, slug, display_name) VALUES (?, ?, ?)",
            [(1, "synthetic-a", "Same name"), (2, "synthetic-b", "Same name"),
             (3, "synthetic-new", "New athlete")],
        )
        for athlete_id, rhr in [(1, 48), (2, 65)]:
            for offset in range(10):
                day = LAST_DAY - datetime.timedelta(days=offset)
                conn.execute(
                    "INSERT INTO fact_daily_wellness (athlete_id, calendar_date,"
                    " resting_hr, hrv_last_night, hrv_status, sleep_score,"
                    " sleep_duration_sec, bb_most_recent, stress_avg, fetched_at)"
                    " VALUES (?, ?, ?, 60, 'BALANCED', 80, 25200, 70, 30, ?)",
                    (athlete_id, day.isoformat(), rhr, f"{day}T01:00:00Z"),
                )
            conn.execute(
                "INSERT INTO fact_activity (activity_id, athlete_id, activity_type,"
                " activity_name, start_time_local, distance_m, duration_sec, avg_hr,"
                " avg_pace_min_per_km, hr_zone1_sec, hr_zone2_sec)"
                " VALUES (?, ?, 'running', ?, ?, 6000, 2160, 140, 6, 360, 1800)",
                (athlete_id, athlete_id, f"Synthetic run {athlete_id}", f"{LAST_DAY} 06:00:00"),
            )
        conn.commit()
    finally:
        conn.close()


def wait_for_server(process, url):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Streamlit exited before startup: {process.returncode}")
        try:
            with urllib.request.urlopen(f"{url}/_stcore/health", timeout=1) as response:
                if response.read() == b"ok":
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.1)
    raise TimeoutError("Streamlit did not become healthy within 30 seconds")


def exercise_browser(url, artifacts, chromium_path=None):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=chromium_path, headless=True, args=["--disable-dev-shm-usage"],
        )
        errors = []
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))

        def settled():
            expect(page.get_by_test_id("stApp")).to_have_attribute(
                "data-test-script-state", "notRunning", timeout=30000,
            )
            expect(page.get_by_test_id("stException")).to_have_count(0)

        def navigate(label, heading):
            page.get_by_role("link", name=re.compile(re.escape(label) + "$")).click()
            page.get_by_role("heading", name=heading, exact=False).first.wait_for(timeout=30000)
            settled()

        def assert_body(slug, rhr):
            expect(page.get_by_role("heading", name=f"ร่างกาย · Same name ({slug})",
                                    exact=True)).to_be_visible(timeout=30000)
            settled()
            metric = page.get_by_test_id("stMetric").filter(
                has=page.get_by_test_id("stMetricLabel").get_by_text("RHR", exact=True),
            )
            expect(metric.get_by_test_id("stMetricValue")).to_have_text(f"{rhr} bpm")

        try:
            page.goto(url, wait_until="domcontentloaded")
            page.get_by_role("heading", name="ภาพรวมสุขภาพทีม", exact=True).wait_for(timeout=30000)
            settled()
            for slug, rhr in [("synthetic-a", 48), ("synthetic-b", 65)]:
                navigate("ทีม", "ภาพรวมสุขภาพทีม")
                page.get_by_role("button", name=re.compile(
                    re.escape(f"ดูข้อมูลของ Same name ({slug})") + "$",
                )).click()
                assert_body(slug, rhr)
                print(f"TEAM_CARD_OK {slug}", flush=True)

            for slug, rhr in [("synthetic-a", 48), ("synthetic-b", 65), ("synthetic-a", 48)]:
                page.get_by_role("combobox").first.click()
                page.get_by_role("option", name=f"Same name ({slug})", exact=True).click()
                assert_body(slug, rhr)
                print(f"DROPDOWN_OK {slug}", flush=True)

            for label in ["ทีม", "ร่างกาย", "การซ้อม", "ค่าประเมิน Garmin", "เซสชัน", "สถานะระบบ"]:
                navigate(label, "ภาพรวมสุขภาพทีม" if label == "ทีม" else label)
                print(f"PAGE_OK {label}", flush=True)

            navigate("ทีม", "ภาพรวมสุขภาพทีม")
            page.screenshot(path=str(artifacts / "desktop-team.png"), full_page=True)
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(url, wait_until="domcontentloaded")
            page.get_by_role("heading", name="ภาพรวมสุขภาพทีม", exact=True).wait_for(timeout=30000)
            settled()
            expect(page.get_by_test_id("stMetricValue").first).to_have_text("80")
            page.screenshot(path=str(artifacts / "mobile-team.png"), full_page=True)
            dimensions = page.evaluate(
                "({width: innerWidth, scroll: document.documentElement.scrollWidth})",
            )
            if dimensions["scroll"] > dimensions["width"]:
                raise AssertionError(f"Mobile page overflows horizontally: {dimensions}")
            page.get_by_role("button", name=re.compile(
                re.escape("ดูข้อมูลของ Same name (synthetic-b)") + "$",
            )).click()
            assert_body("synthetic-b", 65)
            if errors:
                raise AssertionError(f"Browser errors: {errors}")
            print("MOBILE_CARD_OK", json.dumps(dimensions), flush=True)
        except Exception:
            page.screenshot(path=str(artifacts / "failure.png"), full_page=True)
            raise
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chromium-path")
    parser.add_argument("--artifacts-dir", type=Path,
                        default=GARMIN_ROOT.parent / ".tmp" / "dashboard-smoke")
    args = parser.parse_args()
    artifacts = args.artifacts_dir.resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dashboard-browser-") as directory:
        seed_browser_data(directory)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        url = f"http://127.0.0.1:{port}"
        environment = dict(os.environ, GARMIN_DATA_DIR=directory, TZ="Asia/Bangkok", PYTHONUTF8="1")
        with (artifacts / "streamlit.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [sys.executable, "-m", "streamlit", "run", "scripts/dashboard.py",
                 "--server.address=127.0.0.1", f"--server.port={port}",
                 "--server.headless=true", "--server.fileWatcherType=none",
                 "--browser.gatherUsageStats=false"],
                cwd=GARMIN_ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT,
            )
            try:
                wait_for_server(process, url)
                exercise_browser(url, artifacts, args.chromium_path)
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
    print("DASHBOARD_BROWSER_OK", flush=True)
    check_demo(artifacts, args.chromium_path)


def check_demo(artifacts, chromium_path):
    """Boot the user-facing Demo launcher, not a separate test-only seed path."""
    from playwright.sync_api import expect, sync_playwright

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    with (artifacts / "demo-streamlit.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "-u", "scripts/run_demo.py", "--port", str(port)],
            cwd=GARMIN_ROOT, stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            wait_for_server(process, url)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=chromium_path, headless=True)
                try:
                    page = browser.new_page(viewport={"width": 1440, "height": 1000})
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(url, wait_until="domcontentloaded")
                    for label in ["ทีม", "ร่างกาย", "การซ้อม", "ค่าประเมิน Garmin", "เซสชัน", "สถานะระบบ"]:
                        page.get_by_role("link", name=re.compile(re.escape(label) + "$")).click()
                        heading = "ภาพรวมสุขภาพทีม" if label == "ทีม" else label
                        expect(page.get_by_role("heading", name=re.compile(
                            "^" + re.escape(heading))).first).to_be_visible(timeout=30000)
                        expect(page.get_by_test_id("stApp")).to_have_attribute(
                            "data-test-script-state", "notRunning", timeout=30000,
                        )
                        expect(page.get_by_test_id("stException")).to_have_count(0)
                        expect(page.get_by_text(re.compile("โหมด Demo · ทุกชื่อและตัวเลข"))).to_be_visible()
                        print(f"DEMO_PAGE_OK {label}", flush=True)
                    expect(page.get_by_test_id("stDataFrame")).to_have_count(2)
                    page.screenshot(path=str(artifacts / "desktop-demo-system.png"), full_page=True)
                    page.get_by_role("link", name=re.compile("ร่างกาย$")).click()
                    page.get_by_role("combobox").first.click()
                    page.get_by_role("option", name="นักกีฬาทดลอง B", exact=True).click()
                    expect(page.get_by_role("heading", name="ร่างกาย · นักกีฬาทดลอง B", exact=True)).to_be_visible()
                    expect(page.get_by_test_id("stSidebar").get_by_text(re.compile(
                        "วันไม่มีข้อมูลสุขภาพในช่วงที่เลือก: 2 วัน"))).to_be_visible()
                    page.get_by_role("combobox").first.click()
                    page.get_by_role("option", name="นักกีฬาทดลองใหม่", exact=True).click()
                    expect(page.get_by_test_id("stSidebar").get_by_text(re.compile(
                        "ยังไม่มีข้อมูลสุขภาพรายวัน"))).to_be_visible()
                    expect(page.get_by_test_id("stException")).to_have_count(0)
                    page.set_viewport_size({"width": 390, "height": 844})
                    page.screenshot(path=str(artifacts / "mobile-demo-new.png"), full_page=True)
                    dimensions = page.evaluate("({width: innerWidth, scroll: document.documentElement.scrollWidth})")
                    if dimensions["scroll"] > dimensions["width"]:
                        raise AssertionError(f"Demo mobile overflow: {dimensions}")
                    if errors:
                        raise AssertionError(f"Demo browser errors: {errors}")
                finally:
                    browser.close()
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
    log_text = (artifacts / "demo-streamlit.log").read_text(encoding="utf-8")
    directory_match = re.search(r"Schema initialized: (.+)[/\\]garmin\.db", log_text)
    if not directory_match or Path(directory_match.group(1)).exists():
        raise AssertionError("Demo did not clean up its temporary database")
    print("DEMO_BROWSER_AND_CLEANUP_OK", flush=True)


if __name__ == "__main__":
    main()
