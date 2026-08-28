"""pace-HR trend ของรันเบา — คุมให้เป็นบริบท ไม่กลายเป็น readiness veto.

สูตรความเร็ว/HR ยังใช้ดูแนวโน้มคนเดิมได้ แต่รันทั่วไปไม่ได้มาตรฐานและไม่วัด oxygen cost
จึงไม่ใช่ running economy หรือความสด. ACWR-like ratio และ cutoff EF ถูกถอดออกทั้งหมด.
"""

import ast
import datetime
import inspect
import unittest
from pathlib import Path

import pandas as pd

DASHBOARD_PATH = Path(__file__).resolve().parent.parent / "scripts" / "dashboard.py"
DASHBOARD_SRC = DASHBOARD_PATH.read_text(encoding="utf-8")


def extract_helpers(*names):
    """รันเฉพาะ constant กับ def ที่ต้องใช้ โดยไม่ต้องแตะ streamlit หรือฐานข้อมูล"""
    tree = ast.parse(DASHBOARD_SRC)
    wanted = set(names)
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in wanted:
            nodes.append(node)
        elif isinstance(node, ast.Assign):
            targets = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if targets & wanted:
                nodes.append(node)
    namespace = {"pd": pd, "datetime": datetime, "float": float}
    exec(
        compile(ast.Module(body=nodes, type_ignores=[]), "dashboard.py", "exec"),
        namespace,
    )
    return namespace


HELPERS = extract_helpers(
    "EASY_MAX_PCT",
    "EF_MIN_DISTANCE_M",
    "EF_RECENT_DAYS",
    "EF_BASELINE_DAYS",
    "EF_BASELINE_MIN_DAYS",
    "EF_STALE_DAYS",
    "efficiency_factor",
    "easy_run_efficiency",
    "efficiency_windows",
    "efficiency_change_pct",
    "efficiency_recent_value",
    "efficiency_status",
    "efficiency_display",
    "load_volume_display",
    "load_context_line",
    "compute_load_windows",
    "team_status",
)


def easy_runs(rows):
    """rows = [(วันที่, ระยะเมตร, วินาที, HR เฉลี่ย)]"""
    return pd.DataFrame(
        [
            {"date": pd.Timestamp(day), "distance_m": dist,
             "duration_sec": dur, "avg_hr": hr}
            for day, dist, dur, hr in rows
        ]
    )


class EfficiencyFactorTests(unittest.TestCase):
    def test_efficiency_factor_is_speed_per_heart_beat(self):
        # 10 กม. ใน 50 นาที = 200 ม./นาที ที่ HR 140 -> 1.4286
        value = HELPERS["efficiency_factor"](10000.0, 3000.0, 140.0)
        self.assertAlmostEqual(value, 200.0 / 140.0, places=6)

    def test_efficiency_factor_refuses_to_invent_a_value_without_heart_rate(self):
        for distance, duration, hr in (
            (10000.0, 3000.0, None),
            (10000.0, 3000.0, 0.0),
            (10000.0, 0.0, 140.0),
            (None, 3000.0, 140.0),
        ):
            self.assertTrue(pd.isna(HELPERS["efficiency_factor"](distance, duration, hr)))


class EasyRunSelectionTests(unittest.TestCase):
    def test_only_easy_runs_long_enough_to_be_stable_are_kept(self):
        lthr = 170  # easy = HR <= 89% ของ 170 = 151.3
        runs = easy_runs([
            ("2026-08-01", 10000.0, 3000.0, 140.0),   # easy + ยาวพอ -> เก็บ
            ("2026-08-02", 10000.0, 3000.0, 160.0),   # หนักเกิน easy -> ทิ้ง
            ("2026-08-03", 2000.0, 600.0, 140.0),     # สั้นกว่า 3 กม. -> ทิ้ง
            ("2026-08-04", 8000.0, 2400.0, None),     # ไม่มี HR -> ทิ้ง
        ])

        result = HELPERS["easy_run_efficiency"](runs, lthr)

        self.assertEqual(list(result["date"].dt.strftime("%Y-%m-%d")), ["2026-08-01"])
        self.assertAlmostEqual(result.iloc[0]["ef"], 200.0 / 140.0, places=6)

    def test_no_lthr_means_no_easy_runs_rather_than_a_guessed_threshold(self):
        runs = easy_runs([("2026-08-01", 10000.0, 3000.0, 140.0)])

        self.assertTrue(HELPERS["easy_run_efficiency"](runs, None).empty)

    def test_multiple_garmin_records_on_one_day_contribute_one_daily_value(self):
        """Warm-up/main/cool-down records must not count as three independent days."""
        runs = easy_runs([
            ("2026-08-01", 2000.0, 600.0, 120.0),
            ("2026-08-01", 4000.0, 1200.0, 140.0),
            ("2026-08-01", 2000.0, 600.0, 130.0),
        ])

        result = HELPERS["easy_run_efficiency"](runs, lthr=170)

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["date"], pd.Timestamp("2026-08-01"))
        # 8 km / 40 min = 200 m/min; duration-weighted HR = 132.5 bpm.
        self.assertAlmostEqual(result.iloc[0]["ef"], 200.0 / 132.5, places=6)


class EfficiencyChangeTests(unittest.TestCase):
    @staticmethod
    def _series(pairs):
        return pd.DataFrame(
            [{"date": pd.Timestamp(day), "ef": ef} for day, ef in pairs]
        )

    def test_change_compares_three_recent_runs_against_the_28_day_baseline(self):
        baseline = [(f"2026-07-{day:02d}", 1.00) for day in (10, 12, 14, 16, 18)]
        recent = [("2026-08-01", 0.90), ("2026-08-03", 0.90), ("2026-08-05", 0.90)]

        pct = HELPERS["efficiency_change_pct"](
            self._series(baseline + recent), today=datetime.date(2026, 8, 6)
        )

        self.assertAlmostEqual(pct, -10.0, places=6)

    def test_chart_baseline_window_excludes_older_history(self):
        rows = [
            ("2026-06-01", 9.0), ("2026-06-03", 9.0),
            ("2026-07-10", 1.0), ("2026-07-12", 1.0),
            ("2026-07-14", 1.0), ("2026-07-16", 1.0),
            ("2026-07-18", 1.0),
            ("2026-08-01", 0.9), ("2026-08-03", 0.9),
            ("2026-08-05", 0.9),
        ]

        windows = HELPERS["efficiency_windows"](
            self._series(rows), today=datetime.date(2026, 8, 6)
        )

        self.assertIsNotNone(windows)
        self.assertEqual(len(windows["baseline"]), 5)
        self.assertAlmostEqual(windows["baseline_median"], 1.0, places=6)

    def test_baseline_does_not_include_any_of_the_three_recent_runs(self):
        baseline = [(f"2026-07-{day:02d}", 1.00) for day in (10, 12, 14, 16, 18)]
        recent = [("2026-07-30", 0.80), ("2026-08-02", 0.80), ("2026-08-05", 0.80)]

        pct = HELPERS["efficiency_change_pct"](
            self._series(baseline + recent), today=datetime.date(2026, 8, 6)
        )

        self.assertAlmostEqual(pct, -20.0, places=6)

    def test_not_enough_baseline_runs_reports_missing_instead_of_zero(self):
        rows = [("2026-08-01", 1.0), ("2026-08-03", 1.0), ("2026-08-05", 1.0),
                ("2026-07-20", 1.0)]

        pct = HELPERS["efficiency_change_pct"](
            self._series(rows), today=datetime.date(2026, 8, 6)
        )

        self.assertTrue(pd.isna(pct))

    def test_fewer_than_three_easy_runs_at_all_reports_missing(self):
        rows = [("2026-08-01", 1.0), ("2026-08-05", 1.0)]

        pct = HELPERS["efficiency_change_pct"](
            self._series(rows), today=datetime.date(2026, 8, 6)
        )

        self.assertTrue(pd.isna(pct))

    def test_three_recent_runs_spread_too_far_apart_are_not_called_current(self):
        # รันล่าสุดสดจริง แต่ต้องยืมรันกลางเดือนก่อนมาครบ 3 — นั่นไม่ใช่ "ตอนนี้"
        rows = [(f"2026-07-{day:02d}", 1.0) for day in (10, 12, 14, 16, 18)]
        rows.append(("2026-08-05", 0.9))

        pct = HELPERS["efficiency_change_pct"](
            self._series(rows), today=datetime.date(2026, 8, 6)
        )

        self.assertTrue(pd.isna(pct))

    def test_stale_easy_runs_do_not_keep_reporting_yesterdays_freshness(self):
        rows = [(f"2026-06-{day:02d}", 1.00) for day in (10, 12, 14, 16, 18)]
        rows += [("2026-06-20", 1.0), ("2026-06-22", 1.0), ("2026-06-24", 1.0)]

        pct = HELPERS["efficiency_change_pct"](
            self._series(rows), today=datetime.date(2026, 8, 25)
        )

        self.assertTrue(pd.isna(pct))


class EfficiencyRecentValueTests(unittest.TestCase):
    """ตัวเลข EF ที่โชว์ต้องผ่านเกณฑ์ 'ตอนนี้' เดียวกับที่ใช้ตัดสิน

    พี่เก้ามีข้อมูลวิ่ง easy 3 วันล่าสุดห่างกัน 16 วัน (26/07 · 29/07 · 11/08) — median
    ของสามค่านั้นคำนวณได้ก็จริง แต่ `efficiency_change_pct` ตัดสินแล้วว่าไม่ใช่
    ความสดปัจจุบัน แท็บซ้อมจึงต้องไม่โชว์ตัวเลขนั้นคู่กับป้าย "ข้อมูลไม่พอ"
    """

    @staticmethod
    def _series(pairs):
        return pd.DataFrame(
            [{"date": pd.Timestamp(day), "ef": ef} for day, ef in pairs]
        )

    def test_recent_value_is_shown_when_the_three_runs_count_as_current(self):
        rows = [(f"2026-07-{day:02d}", 1.00) for day in (10, 12, 14, 16, 18)]
        rows += [("2026-08-01", 0.90), ("2026-08-03", 0.90), ("2026-08-05", 0.90)]

        value = HELPERS["efficiency_recent_value"](
            self._series(rows), today=datetime.date(2026, 8, 6)
        )

        self.assertAlmostEqual(value, 0.90, places=6)

    def test_recent_value_is_withheld_when_the_change_cannot_be_trusted(self):
        rows = [(f"2026-07-{day:02d}", 1.00) for day in (10, 12, 14, 16, 18)]
        rows += [("2026-07-26", 1.07), ("2026-07-29", 0.93), ("2026-08-11", 1.09)]

        value = HELPERS["efficiency_recent_value"](
            self._series(rows), today=datetime.date(2026, 8, 25)
        )

        self.assertTrue(pd.isna(value))


class EfficiencyStatusTests(unittest.TestCase):
    def test_every_available_value_is_information_not_a_readiness_colour(self):
        status = HELPERS["efficiency_status"]

        self.assertEqual(status(float("nan"))[1], "ข้อมูลไม่พอ")
        for value in (8.0, 0.0, -2.9, -3.1, -6.9, -7.1):
            self.assertEqual(status(value), ("🔵", "แนวโน้มประกอบ"))

    def test_display_shows_direction_and_never_a_bare_ratio(self):
        display = HELPERS["efficiency_display"]

        self.assertEqual(display(float("nan")), "–")
        self.assertEqual(display(-7.4), "-7% จากฐาน 28 วัน")
        self.assertEqual(display(4.2), "+4% จากฐาน 28 วัน")


class LoadTrendDisplayTests(unittest.TestCase):
    """โหลด 7 วันและค่าเฉลี่ย 28 วันต้องอยู่คนละตัวเลข ไม่หารเป็น ratio."""

    def test_seven_day_load_is_shown_raw_with_its_own_unit(self):
        volume = HELPERS["load_volume_display"]

        self.assertEqual(volume(64.1, "ระยะวิ่ง", "km"), "64.1 km")
        self.assertEqual(volume(711.0, "training_load", "TL"), "711 TL")

    def test_load_without_a_baseline_still_shows_the_raw_number(self):
        volume = HELPERS["load_volume_display"]

        self.assertEqual(volume(64.1, "ระยะวิ่ง", "km"), "64.1 km")
        self.assertEqual(volume(float("nan"), "ระยะวิ่ง", "km"), "–")

    def test_context_keeps_current_and_rolling_values_separate(self):
        line = HELPERS["load_context_line"]("64.1 km", "54.3 km/สัปดาห์", 5, "วิ่ง")

        self.assertEqual(line, "64.1 km · เฉลี่ย 28 วัน 54.3 km/สัปดาห์ · 5 เซสชัน (วิ่ง)")
        self.assertNotIn("%", line)


class LoadWindowsTests(unittest.TestCase):
    def test_windows_report_raw_load_without_dividing_them_into_a_ratio(self):
        end = datetime.date(2026, 8, 9)
        daily = pd.DataFrame({"date": [pd.Timestamp(end)], "value": [10.0]})

        result = HELPERS["compute_load_windows"](
            daily, end, history_start=end - datetime.timedelta(days=27)
        )

        self.assertEqual(len(result), 28)
        self.assertAlmostEqual(result.iloc[-1]["acute"], 10.0)
        self.assertAlmostEqual(result.iloc[-1]["chronic"], 2.5)
        self.assertNotIn("acwr", result.columns)


class TeamStatusTests(unittest.TestCase):
    def test_pace_hr_never_calls_for_rest_because_status_cannot_see_it(self):
        """เดิมข้อนี้ส่ง EF = -9% เข้าไปแล้วดูว่ายังเขียวไหม ตอนนี้แรงกว่านั้น:
        ``team_status()`` ไม่รับค่า pace-HR เข้ามาเลย จึงเอาไปตัดสินไม่ได้แม้จะอยากทำ

        ถ้าใครต่อ pace-HR กลับเข้าคำตัดสิน ต้องเพิ่มพารามิเตอร์ก่อน ซึ่งข้อนี้จะแดงทันที
        """
        params = inspect.signature(HELPERS["team_status"]).parameters

        self.assertEqual(
            [], [name for name in params
                 if any(word in name.lower() for word in ("ef", "efficiency", "pace"))],
        )

    def test_missing_efficiency_does_not_block_green_when_training_data_exists(self):
        # พี่เก้าซ้อม HIIT/indoor เป็นหลัก จึงแทบไม่มีรัน easy ให้คำนวณ pace-HR
        # ขาดค่านั้นต้องไม่ทำให้เขาค้างที่ "ข้อมูลไม่พอ" ตลอดกาลทั้งที่ข้อมูลซ้อมครบ
        status = HELPERS["team_status"](
            [], has_workload=True, wellness_core_count=4
        )

        self.assertEqual(status, "🟢 ไม่พบสัญญาณเตือนจากอุปกรณ์")

    def test_thin_wellness_or_no_training_evidence_still_refuses_to_go_green(self):
        team_status = HELPERS["team_status"]

        self.assertEqual(
            team_status([], has_workload=True, wellness_core_count=2),
            "⚪ ข้อมูลไม่พอ",
        )
        self.assertEqual(
            team_status([], has_workload=False, wellness_core_count=4),
            "⚪ ข้อมูลไม่พอ",
        )
        self.assertEqual(
            team_status([], has_workload=False, wellness_core_count=0),
            "⚪ ไม่มีข้อมูล",
        )

    def test_correlated_flags_do_not_vote_the_athlete_into_an_automatic_rest_order(self):
        team_status = HELPERS["team_status"]

        self.assertEqual(
            team_status(["นอนแย่ (52)"], has_workload=True, wellness_core_count=4),
            "🟡 ควรทบทวนก่อนซ้อม",
        )
        self.assertEqual(
            team_status(["นอนแย่ (52)", "HRV LOW"],
                        has_workload=True, wellness_core_count=4),
            "🟡 ควรทบทวนก่อนซ้อม",
        )


class AcwrIsGoneTests(unittest.TestCase):
    def test_dashboard_no_longer_computes_an_acute_chronic_ratio(self):
        # `acwr_percent` ของ Garmin Readiness เป็นคนละค่าและยังอยู่ได้
        self.assertNotIn("compute_acwr", DASHBOARD_SRC)
        self.assertNotIn("acwr_status", DASHBOARD_SRC)
        self.assertNotIn("acwr_display", DASHBOARD_SRC)
        self.assertNotIn("Acute:Chronic Workload Ratio", DASHBOARD_SRC)
        self.assertNotIn("(acute / chronic_wk", DASHBOARD_SRC)

    def test_the_training_tab_no_longer_paints_ratio_risk_bands(self):
        self.assertNotIn("เสี่ยงบาดเจ็บ > 1.5", DASHBOARD_SRC)
        self.assertNotIn("ปลอดภัย 0.8–1.3", DASHBOARD_SRC)


if __name__ == "__main__":
    unittest.main()
