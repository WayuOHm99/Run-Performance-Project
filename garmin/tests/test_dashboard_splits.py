"""เทสหน้า 📉 Splits ของ dashboard — ใช้ temp DB + ข้อมูลสังเคราะห์ล้วน ไม่แตะ
garmin/data ของจริง (อ่าน dashboard.py จริงแบบ read-only เพื่อพิสูจน์ว่าโค้ดที่ deploy
อยู่จริงไม่ตัดรอบสั้นทิ้ง — ตามข้อยกเว้นเดียวกับ LaneStaleLimitTests)

dashboard.py import ตรง ๆ ไม่ได้ (มันรัน streamlit ทั้งไฟล์) จึงแกะ `load_splits`
กับช่วงโค้ดระหว่าง load_splits() กับการเช็ค `splits.empty` ออกมา exec เดี่ยว ๆ
"""

import ast
import importlib.util
import re
import shutil
import sqlite3
import tempfile
import textwrap
import unittest
from pathlib import Path

import pandas as pd

GARMIN_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_SRC = (GARMIN_ROOT / "scripts" / "dashboard.py").read_text(encoding="utf-8")


def load_script(name, filename):
    spec = importlib.util.spec_from_file_location(
        name, GARMIN_ROOT / "scripts" / filename
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


schema = load_script("garmin_schema_under_test", "02_init_schema.py")


class _FakeStreamlit:
    """st ปลอมที่ทำหน้าที่แค่ปล่อย @st.cache_data ผ่าน — พอสำหรับ exec load_splits เดี่ยว ๆ"""

    @staticmethod
    def cache_data(**_kwargs):
        return lambda fn: fn


def extract_load_splits(db_path):
    tree = ast.parse(DASHBOARD_SRC)
    picked = [n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "load_splits"]
    assert len(picked) == 1, "ไม่พบ load_splits ใน dashboard.py"
    ns = {"st": _FakeStreamlit, "sqlite3": sqlite3, "pd": pd,
          "DB_PATH": str(db_path), "CACHE_TTL_SEC": 0}
    exec(compile(ast.Module(body=picked, type_ignores=[]), "dashboard.py", "exec"), ns)
    return ns["load_splits"]


def extract_session_candidates():
    """ใช้ฟังก์ชันคัดตัวเลือกจริงจาก dashboard เพื่อกันตัวกรองระยะกลับมาอีก"""
    tree = ast.parse(DASHBOARD_SRC)
    picked = [n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "prepare_session_candidates"]
    assert len(picked) == 1, "ไม่พบ prepare_session_candidates ใน dashboard.py"
    ns = {}
    exec(compile(ast.Module(body=picked, type_ignores=[]), "dashboard.py", "exec"), ns)
    return ns["prepare_session_candidates"]


def extract_prep_block():
    """โค้ดที่แท็บ Splits ทำกับ splits ระหว่าง load_splits() กับ `if splits.empty:`

    ตัวกรองที่ทำให้บั๊กนี้เกิด (`splits[splits["distance_m"] >= 100]`) เคยอยู่ตรงนี้ —
    เทสจึงรันช่วงนี้กับข้อมูลจริงแทนการ grep หาตัวกรองแบบใดแบบหนึ่ง
    """
    block = re.search(
        r"^[ \t]*splits = load_splits\(chosen_id\)\n(.*?)^[ \t]*if splits\.empty:",
        DASHBOARD_SRC, re.S | re.M)
    assert block, "ไม่พบบล็อก load_splits(chosen_id) → if splits.empty: ใน dashboard.py"
    return textwrap.dedent(block.group(1))


def run_splits_tab(splits):
    """เดินโค้ดของแท็บจนถึงจุดตัดสินว่า "ยังไม่ได้ดึง splits" ไหม"""
    ns = {"splits": splits, "pd": pd}
    exec(compile(extract_prep_block(), "dashboard.py", "exec"), ns)
    return ns["splits"]


class ShortSplitDisplayTests(unittest.TestCase):
    """เซสชัน interval ที่ทุกรอบสั้นกว่า 100 ม. ต้องไม่ถูกอ่านว่า "ยังไม่ได้ดึง splits".

    ของจริงที่พัง (ต้อง 6 ส.ค. 69, activity 23885677442): วิ่ง 0.85 กม. 12 รอบ
    ยาว 12.4–92.5 ม. — fact_activity_split มีครบ 12 แถว แต่ตัวกรอง >= 100 ม.
    ลบทิ้งหมดแล้วหน้าเว็บบอกว่ายังไม่ได้ดึง (ตอนนั้นมี 6 เซสชันใน DB ที่โดนแบบเดียวกัน)
    """

    ACTIVITY_ID = 23885677442
    # (split_num, distance_m, duration_sec, avg_hr, avg_cadence, avg_pace_min_km)
    TONG_SPLITS = [
        (1, 83.07, 18.897, 119.0, 178.78, 3.79),
        (2, 60.27, 53.019, 139.0, 120.34, 14.66),
        (3, 92.52, 20.855, 127.0, 151.19, 3.76),
        (4, 61.69, 51.170, 138.0, 68.78, 13.82),
        (5, 86.07, 19.565, 135.0, 177.84, 3.79),
        (6, 61.18, 44.775, 146.0, 100.73, 12.20),
        (7, 86.79, 19.003, 143.0, 178.11, 3.65),
        (8, 53.13, 49.621, 145.0, 97.55, 15.57),
        (9, 89.02, 18.614, 133.0, 159.42, 3.48),
        (10, 68.40, 52.489, 143.0, 127.16, 12.79),
        (11, 90.49, 20.797, 141.0, 175.95, 3.83),
        (12, 12.44, 6.888, 157.0, 151.38, 9.23),
    ]

    def setUp(self):
        tmp = Path(tempfile.mkdtemp(prefix="dashboard-splits-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        self.db_path = tmp / "garmin.db"
        conn = sqlite3.connect(self.db_path)
        self.addCleanup(conn.close)
        columns = ", ".join(f"{name} {kind}" for name, kind in schema.SPLIT_COLUMNS)
        conn.execute(f"""CREATE TABLE fact_activity_split (
            {columns},
            PRIMARY KEY (activity_id, split_num) ON CONFLICT REPLACE
        )""")
        conn.executemany(
            """INSERT INTO fact_activity_split
               (activity_id, split_num, distance_m, duration_sec, avg_hr,
                avg_cadence, elevation_gain_m, intensity_type, avg_pace_min_km)
               VALUES (?, ?, ?, ?, ?, ?, 0.0, 'ACTIVE', ?)""",
            [(self.ACTIVITY_ID,) + row for row in self.TONG_SPLITS])
        conn.commit()
        self.load_splits = extract_load_splits(self.db_path)

    def test_every_short_lap_survives_to_the_charts(self):
        splits = run_splits_tab(self.load_splits(self.ACTIVITY_ID))

        self.assertFalse(splits.empty,
                         "เซสชัน interval รอบสั้นถูกอ่านว่า 'ยังไม่ได้ดึง splits' ทั้งที่ดึงมาครบ")
        # นับให้ครบทุกรอบ — ตัวกรองความยาวใด ๆ (แม้ต่ำกว่า 100 ม.) จะทำให้รอบท้าย 12.4 ม. หาย
        self.assertEqual(list(splits["split_num"]), [n for n, *_ in self.TONG_SPLITS])
        self.assertAlmostEqual(splits["distance_m"].sum(), 845.07, places=1)

    def test_pace_hr_cadence_of_the_shortest_lap_are_kept(self):
        splits = run_splits_tab(self.load_splits(self.ACTIVITY_ID))
        last = splits[splits["split_num"] == 12].iloc[0]

        self.assertAlmostEqual(last["distance_m"], 12.44, places=2)
        self.assertAlmostEqual(last["avg_pace_min_km"], 9.23, places=2)
        self.assertEqual(last["avg_hr"], 157.0)
        self.assertAlmostEqual(last["avg_cadence"], 151.38, places=2)

    def test_missing_message_only_when_the_activity_has_no_split_rows(self):
        # กิจกรรมที่ยังไม่ถูกดึง splits จริง ๆ = แถวว่าง → ข้อความ "ยังไม่ได้ดึง" ถูกต้อง
        splits = run_splits_tab(self.load_splits(self.ACTIVITY_ID + 1))
        self.assertTrue(splits.empty)


class SessionCandidateTests(unittest.TestCase):
    """หน้าเจาะลึกต้องไม่ซ่อนทั้งเซสชันเพียงเพราะระยะสั้นหรือไม่มีระยะ"""

    def test_tab_passes_the_unfiltered_activity_frame_to_candidate_preparation(self):
        self.assertRegex(
            DASHBOARD_SRC,
            r"candidates\s*=\s*prepare_session_candidates\(activity_df\)",
            "หน้าเจาะลึกไม่ได้ส่ง activity_df ทั้งก้อนเข้าตัวเลือกกิจกรรม",
        )

    def test_short_and_zero_distance_activities_remain_selectable(self):
        candidates = extract_session_candidates()(pd.DataFrame({
            "activity_id": [1, 2, 3, 4, 5],
            "start_time_local": pd.to_datetime([
                "2026-08-01 06:00:00",
                "2026-08-02 06:00:00",
                "2026-08-03 06:00:00",
                "2026-08-04 06:00:00",
                "2026-08-05 06:00:00",
            ]),
            # 2/3 คือเคสจริงของ Tong ที่ตัวกรอง >500 ม. เคยซ่อน;
            # 0/None ต้องยังดูรายละเอียดเวลา/HR/Training Load ของ cross-training ได้
            "distance_m": [5000.0, 378.39, 202.89, 0.0, None],
        }))

        self.assertEqual(list(candidates["activity_id"]), [5, 4, 3, 2, 1])
        self.assertEqual(len(candidates), 5)


if __name__ == "__main__":
    unittest.main()
