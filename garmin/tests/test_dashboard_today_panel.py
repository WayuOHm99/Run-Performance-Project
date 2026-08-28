"""แท็บ "วันนี้" — แผงตัดสินแทน st.metric 17 ช่อง (เฟส 3 ของใบงาน #18)

ที่มา: แท็บนี้เคยวางตัวเลข 17 ช่องเรียงเท่ากันหมด โค้ชที่เปิดตอนเช้าจึงต้องอ่าน
ทุกช่องก่อนจะรู้ว่า "วันนี้มีสัญญาณอะไร" และเคยให้น้ำหนัก EF เกินหลักฐาน

แผงใหม่เรียงตามลำดับอ่าน: สัญญาณ → ธงจากอุปกรณ์ → ค่าประกอบ → บริบทโหลด
→ เซสชันจริง  ส่วนคำอธิบายที่เคยเห็นตลอดถูกพับเข้า
expander ตามเกณฑ์วัดผลของใบงาน

กับดักที่เทสชุดนี้ต้องกัน: แท็บนี้เคยตัดสินชนิดกล่องเตือนด้วย
`status_text.startswith("🔴")` จากสตริงอีโมจิตรง ๆ ถ้าแท็บทีมถอดอีโมจิออกจาก
ค่าที่ `team_status()` คืน กล่องเตือนจะเงียบไปทั้งอันโดยไม่มีอะไรฟ้อง
"""

import ast
import html
import unittest
from pathlib import Path

import pandas as pd

DASHBOARD_PATH = Path(__file__).resolve().parent.parent / "scripts" / "dashboard.py"
DASHBOARD_SRC = DASHBOARD_PATH.read_text(encoding="utf-8")


def today_tab_source():
    """ซอร์สของหน้า "วันนี้" — ตั้งแต่แยกหน้า มันคือไฟล์ของตัวเอง ไม่ต้องตัดจากไฟล์รวม"""
    return (Path(__file__).resolve().parent.parent
            / "scripts" / "app_pages" / "today.py").read_text(encoding="utf-8")


# การคำนวณกับชิ้นส่วนหน้าตาอยู่ใน dashboard_domain.py / dashboard_view.py แล้ว
# จึง import ได้ตรง ๆ ไม่ต้อง ast.parse + exec ทีละ node เหมือนเดิม
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent))

from dashboard_modules import HELPERS  # noqa: E402


def wellness_frame(values, end_date="2026-08-25", column="sleep_score"):
    """แถว wellness ย้อนหลังวันละแถว จบที่ end_date (ค่าสุดท้ายคือวัน end_date)"""
    dates = pd.date_range(end=end_date, periods=len(values), freq="D")
    return pd.DataFrame({
        "calendar_date": [d.date().isoformat() for d in dates],
        column: values,
    })


class BaselineMedianTests(unittest.TestCase):
    """ตัวเลขวันนี้อ่านไม่ได้ความถ้าไม่รู้ว่าปกติของคนนี้อยู่ตรงไหน"""

    def test_baseline_uses_only_days_before_the_value_being_compared(self):
        # ถ้าเอาค่าของวันนั้นเองมารวมในฐาน ค่าจะดึงฐานเข้าหาตัวเองจนส่วนต่างหด
        frame = wellness_frame([50.0] * 13 + [90.0])
        baseline = HELPERS["baseline_median"](
            frame, "sleep_score", pd.Timestamp("2026-08-25").date()
        )
        self.assertEqual(baseline, 50.0)

    def test_baseline_ignores_days_older_than_the_window(self):
        frame = wellness_frame([10.0] * 20 + [80.0] * 5 + [99.0])
        baseline = HELPERS["baseline_median"](
            frame, "sleep_score", pd.Timestamp("2026-08-25").date(), days=5
        )
        self.assertEqual(baseline, 80.0)

    def test_too_few_days_returns_nan_instead_of_a_confident_looking_number(self):
        # ฐานจาก 2 วันไม่ใช่ฐาน แต่ถ้าคืนตัวเลขออกไป หน้าจอจะแสดงเหมือนมันเชื่อถือได้
        frame = wellness_frame([70.0, 72.0, 74.0])
        baseline = HELPERS["baseline_median"](
            frame, "sleep_score", pd.Timestamp("2026-08-25").date()
        )
        self.assertTrue(pd.isna(baseline))

    def test_missing_days_do_not_count_towards_the_minimum(self):
        frame = wellness_frame([70.0, None, None, None, None, None, 74.0, 99.0])
        baseline = HELPERS["baseline_median"](
            frame, "sleep_score", pd.Timestamp("2026-08-25").date()
        )
        self.assertTrue(pd.isna(baseline))

    def test_empty_or_unknown_column_is_not_an_error(self):
        baseline_median = HELPERS["baseline_median"]
        anchor = pd.Timestamp("2026-08-25").date()
        self.assertTrue(pd.isna(baseline_median(None, "sleep_score", anchor)))
        self.assertTrue(pd.isna(baseline_median(pd.DataFrame(), "sleep_score", anchor)))
        self.assertTrue(pd.isna(
            baseline_median(wellness_frame([1.0] * 20), "not_a_column", anchor)
        ))


class TileNoteTests(unittest.TestCase):
    """บรรทัดใต้ตัวเลขบอกส่วนต่างจากฐาน ไม่ตัดสินแทนเกณฑ์ที่โปรเจกต์มีอยู่แล้ว"""

    def test_note_states_the_gap_with_an_explicit_sign(self):
        self.assertIn("+6", HELPERS["tile_note"](89.0, 83.0))

    def test_note_says_the_baseline_is_missing_rather_than_showing_a_dash(self):
        # ขีดเปล่าอ่านได้ว่าระบบพัง ทั้งที่แปลว่าประวัติยังสั้นเกินจะมีฐาน
        note = HELPERS["tile_note"](89.0, float("nan"))
        self.assertIn("ฐาน", note)
        self.assertNotIn("nan", note.lower())

    def test_no_value_yields_no_note_at_all(self):
        self.assertEqual(HELPERS["tile_note"](float("nan"), 83.0), "")


class SparklineTests(unittest.TestCase):
    """เส้นเล็กบอกทิศทาง 14 วันโดยไม่กินที่เท่ากราฟเต็ม"""

    def test_two_points_draw_nothing_because_a_line_of_two_has_no_trend(self):
        self.assertEqual(HELPERS["sparkline_svg"]([50.0, 60.0]), "")

    def test_points_stay_inside_the_drawing_box(self):
        svg = HELPERS["sparkline_svg"]([10.0, 90.0, 50.0, 70.0], width=100, height=20)
        points = svg.split('points="')[1].split('"')[0].split()
        xs = [float(p.split(",")[0]) for p in points]
        ys = [float(p.split(",")[1]) for p in points]
        self.assertTrue(all(0 <= x <= 100 for x in xs), xs)
        self.assertTrue(all(0 <= y <= 20 for y in ys), ys)

    def test_a_flat_series_draws_a_flat_line_instead_of_dividing_by_zero(self):
        svg = HELPERS["sparkline_svg"]([50.0, 50.0, 50.0, 50.0], height=20)
        ys = {p.split(",")[1] for p in svg.split('points="')[1].split('"')[0].split()}
        self.assertEqual(len(ys), 1)

    def test_gaps_are_dropped_rather_than_drawn_as_zero(self):
        # วันที่นาฬิกาไม่ส่งค่าไม่ใช่วันที่ค่าเป็นศูนย์ — ลากลงพื้นคือการโกหก
        svg = HELPERS["sparkline_svg"]([80.0, None, 82.0, float("nan"), 84.0])
        points = svg.split('points="')[1].split('"')[0].split()
        self.assertEqual(len(points), 3)


class VerdictTests(unittest.TestCase):
    """สรุปสัญญาณต้องอ่านได้ก่อนตัวเลขใด ๆ และต้องไม่พึ่งอีโมจิ"""

    ROW = {
        "นักกีฬา": "Tong",
        "สถานะ": "🟡 ควรทบทวนก่อนซ้อม",
        "pace–HR trend": "+2% จากฐาน 28 วัน",
        "สถานะ pace–HR": "🔵 แนวโน้มประกอบ",
        "โหลด 7 วัน": "32.6 km",
        "ค่าเฉลี่ยโหลด 28 วัน": "29.4 km/สัปดาห์",
        "ขอบเขตโหลด": "วิ่ง",
        "เซสชัน 7 วัน": 5,
        "ธงเฝ้าระวัง": "HRV UNBALANCED",
    }

    def test_the_verdict_reads_as_a_sentence_about_the_athlete(self):
        markup = HELPERS["render_today_verdict"](dict(self.ROW))
        self.assertIn("Tong", markup)
        self.assertIn("ควรทบทวนก่อนซ้อม", markup)

    def test_status_arrives_as_a_drawn_shape_so_it_survives_black_and_white_print(self):
        markup = HELPERS["render_today_verdict"](dict(self.ROW))
        self.assertIn("<svg", markup)
        for emoji in HELPERS["STATUS_SHAPES"]:
            self.assertNotIn(emoji, markup, f"ยังมีอีโมจิ {emoji} หลุดเข้าแผงคำตัดสิน")

    def test_each_flag_is_shown_separately_instead_of_one_run_on_string(self):
        row = dict(self.ROW, **{"ธงเฝ้าระวัง": "HRV UNBALANCED | นอนแย่ (52)"})
        markup = HELPERS["render_today_verdict"](row)
        self.assertIn("HRV UNBALANCED", markup)
        self.assertIn("นอนแย่ (52)", markup)
        self.assertNotIn("|", markup)

    def test_verdict_says_device_data_is_not_training_clearance(self):
        row = dict(self.ROW)
        markup = HELPERS["render_today_verdict"](row)
        self.assertIn("ไม่ใช่คำอนุญาตให้ซ้อม", markup)
        self.assertIn("อาการเจ็บ", markup)

    def test_no_flags_reads_as_none_rather_than_an_empty_box(self):
        row = dict(self.ROW, **{
            "สถานะ": "🟢 ไม่พบสัญญาณเตือนจากอุปกรณ์", "ธงเฝ้าระวัง": "—"
        })
        markup = HELPERS["render_today_verdict"](row)
        self.assertIn("ไม่มีธงเฝ้าระวัง", markup)

    def test_athlete_name_is_escaped_so_stored_text_cannot_inject_markup(self):
        row = dict(self.ROW, **{"นักกีฬา": "<script>x</script>"})
        markup = HELPERS["render_today_verdict"](row)
        self.assertNotIn("<script>", markup)
        self.assertIn("&lt;script&gt;", markup)

    def test_load_windows_are_shown_separately_without_a_ratio(self):
        markup = HELPERS["render_today_verdict"](dict(self.ROW))
        self.assertIn("32.6 km", markup)
        self.assertIn("29.4 km/สัปดาห์", markup)
        self.assertIn("ค่าเฉลี่ยโหลด 28 วัน", markup)
        self.assertNotIn("เทียบฐานตัวเอง", markup)

    def test_the_session_count_says_what_it_counted(self):
        # 5 เซสชันของคนที่นับเฉพาะวิ่ง ไม่ใช่ของเดียวกับ 5 เซสชันของคนที่นับทุกกิจกรรม
        self.assertIn("5 (วิ่ง)", HELPERS["render_today_verdict"](dict(self.ROW)))
        self.assertIn(
            "5 (ทุกกิจกรรม)",
            HELPERS["render_today_verdict"](
                dict(self.ROW, **{"ขอบเขตโหลด": "ทุกกิจกรรม"})),
        )


class TileTests(unittest.TestCase):
    def test_tile_shows_value_unit_and_note_together(self):
        markup = HELPERS["render_today_tile"](
            "BODY BATTERY", "89", "สูงสุดคืนนี้", "เทียบฐาน 14 วัน +6"
        )
        for part in ("BODY BATTERY", "89", "สูงสุดคืนนี้", "เทียบฐาน 14 วัน +6"):
            self.assertIn(part, markup)

    def test_a_flagged_tile_is_marked_by_border_and_words_not_colour_alone(self):
        # ตาบอดสีและกระดาษขาวดำอ่านสีไม่ได้ ข้อความจึงต้องบอกเองว่ามีธง
        flagged = HELPERS["render_today_tile"](
            "HRV คืนล่าสุด", "123", "ms", "Garmin: UNBALANCED", alert="watch"
        )
        plain = HELPERS["render_today_tile"]("HRV คืนล่าสุด", "123", "ms", "ปกติ")
        self.assertIn("Garmin: UNBALANCED", flagged)
        self.assertNotEqual(flagged, plain)
        self.assertIn("<svg", flagged)

    def test_values_are_escaped(self):
        markup = HELPERS["render_today_tile"]("<b>x</b>", "<i>1</i>", "", "")
        self.assertNotIn("<b>", markup)
        self.assertNotIn("<i>", markup)


class SessionRowTests(unittest.TestCase):
    """เซสชันเป็นของจริงที่นักกีฬาทำ — ต้องอ่านได้เป็นแถวเดียวจบ"""

    def test_row_carries_every_column_a_coach_scans(self):
        markup = HELPERS["render_session_row"](
            "21/08 17:25", "เมืองนครราชสีมา วิ่ง", 6.54, 3024, 7.7, 137.0,
            HELPERS["INTENSITY_ORDER"][0],
        )
        for part in ("21/08 17:25", "เมืองนครราชสีมา วิ่ง", "6.54", "50:24", "137"):
            self.assertIn(part, markup)

    def test_missing_distance_shows_a_dash_not_zero_km(self):
        # เวทเทรนนิ่งไม่มีระยะ การเขียน 0.00 กม. คือการรายงานตัวเลขที่ไม่มีอยู่จริง
        markup = HELPERS["render_session_row"](
            "21/08 18:34", "ความแข็งแกร่ง", float("nan"), 768, float("nan"), 108.0, None,
        )
        self.assertNotIn("0.00", markup)
        self.assertIn("–", markup)

    def test_activity_name_is_escaped(self):
        markup = HELPERS["render_session_row"](
            "21/08", "<img src=x>", 1.0, 60, 5.0, 120.0, None
        )
        self.assertNotIn("<img", markup)


class IntensityChipTests(unittest.TestCase):
    """ความหนักเป็นค่ามีลำดับ — ต้องไล่เฉดเดียว ไม่ยืมสีสถานะมาใช้"""

    def test_ordinal_intensity_never_borrows_the_status_palette(self):
        status_colours = {
            HELPERS["C_GOOD"].lower(), HELPERS["C_WARN"].lower(), HELPERS["C_CRIT"].lower(),
        }
        for label in HELPERS["INTENSITY_ORDER"]:
            chip = HELPERS["session_intensity_chip"](label).lower()
            for colour in status_colours:
                self.assertNotIn(colour, chip,
                                 f"ชิป {label} ใช้สีสถานะ {colour} ซึ่งจองไว้ให้สถานะเท่านั้น")

    def test_every_intensity_gets_a_distinct_shade(self):
        chips = {HELPERS["session_intensity_chip"](label)
                 for label in HELPERS["INTENSITY_ORDER"]}
        self.assertEqual(len(chips), len(HELPERS["INTENSITY_ORDER"]))

    def test_unknown_intensity_draws_nothing_rather_than_guessing_easy(self):
        # ไม่มี HR = ไม่รู้ความหนัก การเดาว่า "เบา" ทำให้สรุป 80-20 ผิด
        self.assertEqual(HELPERS["session_intensity_chip"](None), "")


class TodayTabSourceTests(unittest.TestCase):
    """กับดักเฉพาะของแท็บนี้ ตรวจที่ระดับซอร์สเพราะบล็อกแท็บรันนอก AppTest ไม่ได้"""

    def test_status_is_never_decided_by_matching_an_emoji_prefix(self):
        # ถ้าแท็บทีมถอดอีโมจิออกจากค่าที่ team_status() คืน เงื่อนไขแบบนี้จะเงียบ
        # ไปทั้งอันโดยไม่มีอะไรฟ้อง — ต้องผ่าน status_parts() ที่เดียว
        today_tab = today_tab_source()
        for emoji in HELPERS["STATUS_SHAPES"]:
            self.assertFalse(
                f'startswith("{emoji}")' in today_tab,
                f"แท็บวันนี้ยังตัดสินจากอีโมจิ {emoji} ตรง ๆ",
            )
        self.assertTrue("status_parts" in today_tab,
                        "แท็บวันนี้ยังไม่ได้อ่านสถานะผ่าน status_parts()")

    def test_always_visible_captions_stay_within_the_ticket_budget(self):
        # เกณฑ์วัดผลของใบงาน #18: ข้อความที่เห็นตลอดต้องลดลง คำอธิบายที่อ่านครั้งเดียว
        # แล้วไม่ต้องอ่านอีกให้พับเข้า expander
        today_tab = today_tab_source()
        self.assertLessEqual(
            today_tab.count("st.caption("), 1,
            "แท็บวันนี้มีคำอธิบายที่เห็นตลอดเกินโควตา — ย้ายเข้า expander",
        )

    def test_the_decision_panel_replaced_the_wall_of_equal_sized_metrics(self):
        today_tab = today_tab_source()
        self.assertLessEqual(
            today_tab.count("st.metric("), 5,
            "แท็บวันนี้ยังวางตัวเลขเรียงเท่ากันหมด สัญญาณหลักจึงจมอยู่ในนั้น",
        )
        self.assertTrue("render_today_verdict" in today_tab)
        self.assertTrue("render_today_tile" in today_tab)

    def test_sessions_are_still_reachable_when_today_is_empty(self):
        # วันพักไม่ได้แปลว่าไม่มีอะไรให้ดู — ของที่ทำมาสามครั้งก่อนหน้าคือบริบทของวันนี้
        today_tab = today_tab_source()
        self.assertTrue("render_session_row" in today_tab)
        self.assertTrue("recent_activities" in today_tab)


if __name__ == "__main__":
    unittest.main()
