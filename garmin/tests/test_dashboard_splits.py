"""เทสหน้า 📉 Splits ของ dashboard — ใช้ temp DB + ข้อมูลสังเคราะห์ล้วน ไม่แตะ
garmin/data ของจริง (อ่าน dashboard.py จริงแบบ read-only เพื่อพิสูจน์ว่าโค้ดที่ deploy
อยู่จริงไม่ตัดรอบสั้นทิ้ง — ตามข้อยกเว้นเดียวกับ LaneStaleLimitTests)

dashboard.py import ตรง ๆ ไม่ได้ (มันรัน streamlit ทั้งไฟล์) จึงแกะ `load_splits`
กับช่วงโค้ดระหว่าง load_splits() กับการเช็ค `splits.empty` ออกมา exec เดี่ยว ๆ
"""

import ast
import importlib.util
import math
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
              if isinstance(n, ast.FunctionDef)
              and n.name in {"connect_db", "load_splits"}]
    assert {node.name for node in picked} == {"connect_db", "load_splits"}, \
        "ไม่พบ connect_db/load_splits ใน dashboard.py"
    ns = {"st": _FakeStreamlit, "sqlite3": sqlite3, "pd": pd,
          "DB_PATH": Path(db_path), "CACHE_TTL_SEC": 0}
    exec(compile(ast.Module(body=picked, type_ignores=[]), "dashboard.py", "exec"), ns)
    return ns["load_splits"]


import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from dashboard_modules import helpers as _helpers  # noqa: E402


def extract_session_candidates():
    """ใช้ฟังก์ชันคัดตัวเลือกจริงจาก dashboard เพื่อกันตัวกรองระยะกลับมาอีก"""
    return _helpers("prepare_session_candidates")["prepare_session_candidates"]


def extract_distance_half_analysis():
    return _helpers("analyze_distance_halves")["analyze_distance_halves"]


def extract_helper(name):
    """ดึง helper ตัวเดียว — เทสจึงใช้ตัวจัดรูปแบบตัวจริง ไม่เขียนซ้ำเอง"""
    return _helpers(name)[name]


def extract_pace_axis_ticks():
    """แกนเพซตัวจริงพร้อมค่าคงที่ของมัน — วัดเพดานที่ deploy อยู่จริง"""
    return _helpers("fmt_pace", "_pace_ticks_at", "pace_axis_ticks",
                    "PACE_TICK_MAX", "PACE_TICK_STEPS_MIN")


class _FakeColumnConfig:
    """column_config ปลอม — บล็อกตารางเรียกแค่เพื่อประกอบ cfg ไม่ได้ render จริง"""

    @staticmethod
    def NumberColumn(**kwargs):
        return kwargs


class _FakeStreamlitTable:
    column_config = _FakeColumnConfig


def extract_split_table_block():
    """โค้ดที่ประกอบ table_data/cfg ของตาราง Splits จนถึงก่อน st.dataframe()"""
    block = re.search(
        r"(^[ \t]*num0 = st\.column_config\.NumberColumn.*?)"
        r"^[ \t]*st\.dataframe\(pd\.DataFrame\(table_data\)",
        DASHBOARD_SRC, re.S | re.M)
    assert block, "ไม่พบบล็อกสร้างตาราง Splits ใน dashboard.py"
    return textwrap.dedent(block.group(1))


def build_split_table(splits):
    """ประกอบตาราง Splits ด้วยโค้ดจริงของ dashboard แล้วคืน (DataFrame, cfg)"""
    fmt_pace = extract_helper("fmt_pace")
    ns = {
        "st": _FakeStreamlitTable,
        "pd": pd,
        "splits": splits,
        "dist_km": (splits["distance_m"] / 1000).round(2),
        "pace_txt": [fmt_pace(p) for p in splits["avg_pace_min_km"]],
        "fmt_pace": fmt_pace,
        "fmt_sec": extract_helper("fmt_sec"),
    }
    exec(compile(extract_split_table_block(), "dashboard.py", "exec"), ns)
    return pd.DataFrame(ns["table_data"]), ns["cfg"]


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


class SplitLapTimeTests(unittest.TestCase):
    """ตาราง Splits ต้องบอกเวลาต่อรอบ — เซสชัน interval อ่านจากเพซอย่างเดียวไม่ได้

    ของจริง (Tong activity 23885677442): เที่ยววิ่ง ~19–21 วิ สลับเที่ยวพัก ~45–53 วิ
    แต่ตารางแสดงเพซ 3:47 สลับ 14:40 ซึ่งบอกไม่ได้ว่ารักษาเที่ยวได้ไหม
    ขณะที่ `fact_activity_split.duration_sec` มีค่าครบทุกแถวใน DB อยู่แล้ว
    """

    def make_splits(self):
        rows = ShortSplitDisplayTests.TONG_SPLITS
        return pd.DataFrame({
            "split_num": [row[0] for row in rows],
            "distance_m": [row[1] for row in rows],
            "duration_sec": [row[2] for row in rows],
            "avg_hr": [row[3] for row in rows],
            "avg_cadence": [row[4] for row in rows],
            "avg_pace_min_km": [row[5] for row in rows],
            "max_hr": [None] * len(rows),
            "elevation_gain_m": [0.0] * len(rows),
        })

    def test_each_lap_shows_the_time_the_watch_recorded(self):
        table, _ = build_split_table(self.make_splits())

        self.assertIn("เวลา", table.columns, "ตาราง Splits ไม่มีคอลัมน์เวลาต่อรอบ")
        # เวลาจริงจาก Garmin ของ 6 เที่ยววิ่ง (รอบคี่) ปัดเป็นวินาทีเต็มตามรูปแบบ M:SS
        self.assertEqual(
            [table.loc[table["รอบที่"] == n, "เวลา"].iloc[0] for n in (1, 3, 5, 7, 9, 11)],
            ["0:19", "0:21", "0:20", "0:19", "0:19", "0:21"],
        )

    def test_lap_without_pace_still_reports_its_time(self):
        # ใน DB มี 54 แถวที่มี duration_sec แต่ Garmin ไม่ได้ให้ avg_pace_min_km
        # ถ้าเวลาผูกกับเพซ รอบพวกนี้จะกลายเป็นแถวว่างทั้งที่นาฬิกาจับเวลาไว้แล้ว
        splits = self.make_splits()
        splits.loc[splits["split_num"] == 12, "avg_pace_min_km"] = None

        table, _ = build_split_table(splits)
        row = table[table["รอบที่"] == 12].iloc[0]

        self.assertEqual(row["เพซ"], "–")
        self.assertEqual(row["เวลา"], "0:07")

    def test_time_is_read_before_pace_because_the_watch_measures_it_directly(self):
        table, _ = build_split_table(self.make_splits())

        self.assertEqual(
            list(table.columns)[:4],
            ["รอบที่", "ระยะ (km)", "เวลา", "เพซ"],
        )


class EqualDistanceHalfTests(unittest.TestCase):
    def test_midpoint_crossing_lap_is_fractionally_allocated_by_distance(self):
        splits = pd.DataFrame({
            "distance_m": [800.0, 400.0],
            "duration_sec": [240.0, 240.0],
            "avg_hr": [160.0, None],
        })

        p1, p2, hr1, hr2 = extract_distance_half_analysis()(splits)

        self.assertAlmostEqual(p1, 5.0)
        self.assertAlmostEqual(p2, 8.3333333333)
        self.assertAlmostEqual(hr1, 160.0)
        # Only the 200 m portion with a real HR contributes to this denominator.
        self.assertAlmostEqual(hr2, 160.0)

    def test_missing_hr_duration_does_not_dilute_the_other_half(self):
        splits = pd.DataFrame({
            "distance_m": [500.0, 500.0],
            "duration_sec": [150.0, 300.0],
            "avg_hr": [160.0, None],
        })

        _, _, hr1, hr2 = extract_distance_half_analysis()(splits)

        self.assertAlmostEqual(hr1, 160.0)
        self.assertTrue(pd.isna(hr2))

    def test_non_positive_hr_values_are_treated_as_missing(self):
        splits = pd.DataFrame({
            "distance_m": [500.0, 500.0],
            "duration_sec": [150.0, 300.0],
            "avg_hr": [0.0, -1.0],
        })

        _, _, hr1, hr2 = extract_distance_half_analysis()(splits)

        self.assertTrue(pd.isna(hr1))
        self.assertTrue(pd.isna(hr2))

    def test_splits_tab_uses_equal_distance_analysis(self):
        self.assertIn(
            "p1, p2, hr1, hr2 = analyze_distance_halves(splits)",
            DASHBOARD_SRC,
        )


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


class PaceAxisTests(unittest.TestCase):
    """แกนเพซต้องอ่านได้และวาดทัน ไม่ว่าจะเจอ lap แบบไหน

    ที่มา (26 ส.ค. 69): เซสชัน 25 ส.ค. ของ P'kao มี lap ท้าย 16.97 ม. / 791.96 วิ
    = เพซ 777.81 นาที/กม. เกณฑ์เดิมใส่ tick ทุก 1 นาทีจึงได้แกนละ 774 จุด
    วัดจากเบราว์เซอร์จริง: หัวข้อขึ้นใน 0.37 วิ แต่กราฟเสร็จที่ 11.96 วิ (settle 12.26 วิ)
    ตัวเลขดิบของ lap นั้นยังต้องอยู่ครบในตาราง Splits — เทสเรื่องนั้นอยู่ใน
    SplitLapTimeTests เทสชุดนี้ถามแค่ว่าแกนวาดกี่จุด และคลุมข้อมูลครบไหม
    """

    # เพดานเขียนเป็นตัวเลขตรงนี้ ไม่อ่าน PACE_TICK_MAX จาก dashboard.py — ยามที่อ่าน
    # ค่าที่มันเฝ้าอยู่ จะเขียวตามทุกครั้งที่ค่านั้นถูกดันขึ้น (ลองแล้ว 26 ส.ค. 69:
    # ตั้ง PACE_TICK_MAX = 100000 คืนบั๊กเดิมเป๊ะ ๆ แล้วเทสยังเขียวทั้งชุด)
    READABLE_TICK_LIMIT = 12

    # เพซจริงทั้ง 16 lap ของเซสชันนั้น (อ่านจาก fact_activity_split 26 ส.ค. 69)
    STANDING_LAP_SESSION = [11.73, 5.59, 10.65, 5.35, 10.93, 5.28, 10.91, 5.14,
                            11.11, 5.08, 11.57, 5.03, 37.65, 17.74, 11.49, 777.81]

    def setUp(self):
        self.ns = extract_pace_axis_ticks()
        self.ticks = self.ns["pace_axis_ticks"]

    def test_a_standing_lap_cannot_explode_the_axis(self):
        values, labels = self.ticks(pd.Series(self.STANDING_LAP_SESSION))
        self.assertEqual(len(values), len(labels))
        self.assertLessEqual(
            len(values), self.READABLE_TICK_LIMIT,
            f"lap ที่ยืนนิ่งดันแกนไปถึง {len(values)} จุด — กราฟจะวาดนานเป็นสิบวินาที",
        )

    def test_the_axis_still_reaches_every_pace_it_is_asked_to_show(self):
        cases = {
            "easy run": [5.05, 5.2, 5.4, 5.33, 5.61],
            "interval": [4.1, 6.8, 4.05, 7.2, 4.2],
            "long slow": [6.4, 6.9, 7.8, 9.2, 12.6],
            "standing lap": self.STANDING_LAP_SESSION,
        }
        for name, paces in cases.items():
            with self.subTest(session=name):
                series = pd.Series(paces)
                values, _ = self.ticks(series)
                self.assertLessEqual(values[0], series.min(),
                                     "tick แรกอยู่ใต้เพซที่เร็วที่สุด — จุดข้อมูลจะหลุดแกน")
                self.assertGreaterEqual(values[-1], series.max(),
                                        "tick สุดท้ายไม่ถึงเพซที่ช้าที่สุด — จุดข้อมูลจะหลุดแกน")
                self.assertLessEqual(len(values), self.READABLE_TICK_LIMIT)

    def test_an_ordinary_session_keeps_its_quarter_minute_marks(self):
        """เพดาน tick ต้องไม่ทำให้กราฟปกติหยาบลง — 45 วินาทีของช่วงยังต้องละเอียด 15 วิ"""
        values, labels = self.ticks(pd.Series([5.05, 5.2, 5.4, 5.33, 5.61, 5.75]))
        self.assertIn("5:15", labels)
        self.assertAlmostEqual(values[1] - values[0], 0.25, places=4)


if __name__ == "__main__":
    unittest.main()
