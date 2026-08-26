"""ตัวชี้วัดความสดสำหรับนักกีฬาที่วิ่งน้อย — HRV 7 วัน เทียบฐาน 28 วัน

**ทำไมต้องมี** EF เป็นตัวตัดสินหลักของระบบ แต่ต้องการรัน easy อย่างน้อย 5 ครั้งใน 28 วัน
วัดจริง 26 ส.ค. 69: Tong 13 ครั้ง · Dan 28 ครั้ง · **P'kao 2 ครั้ง** เพราะ P'kao ซ้อม
HIIT/มวย/indoor cardio 49 ครั้งเทียบกับวิ่ง 19 ครั้งใน 90 วัน การ์ดของคนที่ใช้นาฬิกา
ดีที่สุดจึงขึ้น "ข้อมูลไม่พอ" ถาวร และถ้าวันไหนรัน easy พอ ค่าก็ยังผสมลู่กับนอกลู่
ที่ต่างกัน **17.2%** ขณะที่เกณฑ์เตือนคือ −3% / −7%

**ทำไมเลือก HRV เฉลี่ย 7 วัน** วัดผู้สมัครทั้งหมดจากข้อมูลจริง 90 วันของ P'kao:

| ตัวชี้วัด | ความหนาแน่น | CV |
|---|---|---|
| **HRV เฉลี่ย 7 วัน** | **90/90 วัน** | **6.4%** |
| RHR | 91/90 | 4.6% |
| HRV คืนล่าสุด | 85/90 | 11.7% |
| Readiness รายวัน | 91/90 | 50% (แกว่งเกินใช้เป็นเทรนด์) |

เซสชันที่ไม่ใช่วิ่งมีแค่ HR + training_load + เวลา ไม่มี power และ training_load
คำนวณจาก HR เอง = วนกลับหาตัวเอง ใช้วัดประสิทธิภาพไม่ได้

**เกณฑ์มาจากข้อมูลจริง ไม่ใช่เดา** — การกระจายของ "HRV 7 วัน เทียบฐาน 28 วัน" ของทั้งทีม
216 จุด ได้ SD 9.1% จึงตั้ง เฝ้าระวัง = −9% (1 SD) · ต้องพัก = −18% (2 SD)
**ข้อจำกัดที่ต้องรู้:** `hrv_weekly_avg` เป็นค่าเฉลี่ยเคลื่อนที่อยู่แล้ว SD นี้จึงไม่ใช่ของ
ตัวอย่างอิสระ — เป็นเกณฑ์เชิงปฏิบัติที่ยึดข้อมูลจริง เหมือนที่ EF ทำ ไม่ใช่ค่าทางสถิติที่พิสูจน์ได้

**ตั้งใจให้เป็นตัวเลขที่อ่าน ไม่ใช่ธงใบใหม่** — `hrv_status` ของ Garmin เป็นธงอยู่แล้ว
ถ้าให้เทรนด์จุดธงอีกใบ สัญญาณทางสรีรวิทยาตัวเดียวจะถูกนับสองครั้งแล้วดันสถานะเป็นแดง
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
    "hrv_trend_pct",
    "hrv_trend_status",
    "HRV_TREND_BASELINE_DAYS",
    "HRV_TREND_MIN_BASELINE_DAYS",
    "HRV_TREND_STALE_DAYS",
    "HRV_TREND_WATCH_PCT",
    "HRV_TREND_REST_PCT",
    "HRV_TREND_GAIN_PCT",
)

TODAY = datetime.date(2026, 8, 26)


def frame(values, end=TODAY):
    """สร้าง wellness ย้อนหลังวันละแถวจากลิสต์ค่า HRV 7 วัน (ตัวสุดท้าย = วันล่าสุด)"""
    days = [end - datetime.timedelta(days=len(values) - 1 - i) for i in range(len(values))]
    return pd.DataFrame({
        "calendar_date": [d.isoformat() for d in days],
        "hrv_weekly_avg": values,
    })


class HrvTrendTests(unittest.TestCase):
    def test_a_steady_hrv_reads_as_no_change(self):
        pct = H["hrv_trend_pct"](frame([55.0] * 30), TODAY)
        self.assertAlmostEqual(pct, 0.0, places=6)

    def test_a_drop_against_the_athletes_own_baseline_is_measured(self):
        """ฐาน 53 → ล่าสุด 46 คือเคสจริงของ P'kao เมื่อ 26 ส.ค. 69 (-13.2%)"""
        pct = H["hrv_trend_pct"](frame([53.0] * 29 + [46.0]), TODAY)
        self.assertAlmostEqual(pct, (46 / 53 - 1) * 100, places=6)

    def test_too_little_history_is_not_a_verdict(self):
        """ฐานสั้นกว่าครึ่งเดือนตอบไม่ได้ ต้องคืน NaN ไม่ใช่ 0 ซึ่งอ่านว่า "ปกติ" """
        pct = H["hrv_trend_pct"](frame([55.0] * 8), TODAY)
        self.assertTrue(math.isnan(pct))

    def test_a_stale_last_reading_is_not_reported_as_today(self):
        """นาฬิกาเงียบไปนานแล้วห้ามเอาค่าสุดท้ายมารายงานเป็นความสดวันนี้"""
        old_end = TODAY - datetime.timedelta(days=H["HRV_TREND_STALE_DAYS"] + 1)
        pct = H["hrv_trend_pct"](frame([55.0] * 30, end=old_end), TODAY)
        self.assertTrue(math.isnan(pct))

    def test_empty_input_is_not_a_verdict(self):
        self.assertTrue(math.isnan(H["hrv_trend_pct"](None, TODAY)))
        self.assertTrue(math.isnan(H["hrv_trend_pct"](pd.DataFrame(), TODAY)))

    def test_thresholds_come_from_the_measured_spread(self):
        """SD ของทั้งทีม 216 จุด = 9.1% → เฝ้าระวัง 1 SD · ต้องพัก 2 SD"""
        self.assertEqual(H["HRV_TREND_WATCH_PCT"], -9.0)
        self.assertEqual(H["HRV_TREND_REST_PCT"], -18.0)

    def test_status_words_match_the_shape_vocabulary(self):
        """ต้องคืนคีย์ชุดเดียวกับการ์ด ไม่ใช่คำศัพท์ชุดที่สอง"""
        cases = [
            (-25.0, "rest"), (-13.2, "watch"), (-2.0, "ready"),
            (12.0, "gain"), (float("nan"), "unknown"),
        ]
        for pct, expected_key in cases:
            key, text = H["hrv_trend_status"](pct)
            self.assertEqual(expected_key, key, f"{pct} ควรได้คีย์ {expected_key}")
            self.assertTrue(text.strip(), f"{pct} ไม่มีข้อความกำกับ")

    def test_a_gap_in_the_middle_does_not_break_the_baseline(self):
        """Garmin ไม่ส่งทุกวันเสมอไป — วันที่ขาดต้องถูกข้าม ไม่ใช่ทำให้ตอบไม่ได้"""
        values = [53.0] * 30
        data = frame(values)
        data.loc[5:9, "hrv_weekly_avg"] = None
        pct = H["hrv_trend_pct"](data, TODAY)
        self.assertFalse(math.isnan(pct))


if __name__ == "__main__":
    unittest.main()
