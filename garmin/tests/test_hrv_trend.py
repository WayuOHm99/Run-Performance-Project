"""HRV รายคืน 7 คืนเทียบฐาน 28 คืนก่อนหน้า — trend ประกอบ ไม่ใช่ freshness score.

สองหน้าต่างไม่ซ้อนกัน ใช้ median และไม่มี cutoff จาก SD ของทีม จึงไม่สร้าง
green/yellow/red status ซ้ำกับ Garmin HRV Status/Training Readiness
"""

import ast
import datetime
import math
import sqlite3
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

GARMIN_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_SRC = (GARMIN_ROOT / "scripts" / "dashboard.py").read_text(encoding="utf-8")


def extract(*names):
    tree = ast.parse(DASHBOARD_SRC)
    wanted = set(names)
    nodes, found = [], set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in wanted:
            nodes.append(node)
            found.add(node.name)
        elif isinstance(node, ast.Assign):
            targets = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if targets & wanted:
                nodes.append(node)
                found |= targets & wanted
    missing = wanted - found
    if missing:
        raise AssertionError(f"dashboard.py ไม่มี: {sorted(missing)}")
    namespace = {"pd": pd, "math": math, "datetime": datetime,
                 "ZoneInfo": ZoneInfo, "Path": Path, "sqlite3": sqlite3}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "dashboard.py", "exec"), namespace)
    return namespace


H = extract(
    "hrv_trend_summary",
    "hrv_trend_pct",
    "hrv_trend_status",
    "HRV_TREND_CURRENT_DAYS",
    "HRV_TREND_MIN_CURRENT_DAYS",
    "HRV_TREND_BASELINE_DAYS",
    "HRV_TREND_MIN_BASELINE_DAYS",
    "HRV_TREND_STALE_DAYS",
    "HRV_TREND_LOOKBACK_DAYS",
)

TODAY = datetime.date(2026, 8, 26)


def frame(values, end=TODAY):
    """สร้าง wellness ย้อนหลังวันละแถวจากค่ารายคืน (ตัวสุดท้าย = วันล่าสุด)"""
    days = [end - datetime.timedelta(days=len(values) - 1 - i) for i in range(len(values))]
    return pd.DataFrame({
        "calendar_date": [d.isoformat() for d in days],
        "hrv_last_night": values,
    })


class HrvTrendTests(unittest.TestCase):
    def test_summary_exposes_actual_nights_in_both_non_overlapping_windows(self):
        data = frame([53.0] * 35)
        data.loc[2, "hrv_last_night"] = None
        data.loc[31, "hrv_last_night"] = None

        summary = H["hrv_trend_summary"](data, TODAY)

        self.assertEqual(summary["current_n"], 6)
        self.assertEqual(summary["baseline_n"], 27)
        self.assertEqual(H["HRV_TREND_LOOKBACK_DAYS"], 35)

    def test_a_steady_hrv_reads_as_no_change(self):
        pct = H["hrv_trend_pct"](frame([55.0] * 35), TODAY)
        self.assertAlmostEqual(pct, 0.0, places=6)

    def test_a_drop_against_the_athletes_own_baseline_is_measured(self):
        """ฐาน 53 → ล่าสุด 46 คือเคสจริงของ P'kao เมื่อ 26 ส.ค. 69 (-13.2%)"""
        pct = H["hrv_trend_pct"](frame([53.0] * 28 + [46.0] * 7), TODAY)
        self.assertAlmostEqual(pct, (46 / 53 - 1) * 100, places=6)

    def test_too_little_history_is_not_a_verdict(self):
        """ฐานสั้นกว่าครึ่งเดือนตอบไม่ได้ ต้องคืน NaN ไม่ใช่ 0 ซึ่งอ่านว่า "ปกติ" """
        pct = H["hrv_trend_pct"](frame([55.0] * 12), TODAY)
        self.assertTrue(math.isnan(pct))

    def test_a_stale_last_reading_is_not_reported_as_today(self):
        """นาฬิกาเงียบไปนานแล้วห้ามเอาค่าสุดท้ายมารายงานเป็นความสดวันนี้"""
        old_end = TODAY - datetime.timedelta(days=H["HRV_TREND_STALE_DAYS"] + 1)
        pct = H["hrv_trend_pct"](frame([55.0] * 35, end=old_end), TODAY)
        self.assertTrue(math.isnan(pct))

    def test_empty_input_is_not_a_verdict(self):
        self.assertTrue(math.isnan(H["hrv_trend_pct"](None, TODAY)))
        self.assertTrue(math.isnan(H["hrv_trend_pct"](pd.DataFrame(), TODAY)))

    def test_every_available_trend_is_informational_not_a_readiness_colour(self):
        cases = [(-25.0, "gain"), (-13.2, "gain"), (-2.0, "gain"),
                 (12.0, "gain"), (float("nan"), "unknown")]
        for pct, expected_key in cases:
            key, text = H["hrv_trend_status"](pct)
            self.assertEqual(expected_key, key, f"{pct} ควรได้คีย์ {expected_key}")
            self.assertTrue(text.strip(), f"{pct} ไม่มีข้อความกำกับ")

    def test_a_gap_in_the_middle_does_not_break_the_baseline(self):
        """Garmin ไม่ส่งทุกวันเสมอไป — วันที่ขาดต้องถูกข้าม ไม่ใช่ทำให้ตอบไม่ได้"""
        values = [53.0] * 35
        data = frame(values)
        data.loc[5:9, "hrv_last_night"] = None
        pct = H["hrv_trend_pct"](data, TODAY)
        self.assertFalse(math.isnan(pct))

    def test_current_and_baseline_windows_do_not_overlap(self):
        data = frame([53.0] * 28 + [46.0] * 7)
        pct = H["hrv_trend_pct"](data, TODAY)
        self.assertAlmostEqual(pct, (46 / 53 - 1) * 100, places=6)


if __name__ == "__main__":
    unittest.main()
