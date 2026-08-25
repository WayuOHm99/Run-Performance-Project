"""กราฟทุกใบต้องอยู่ในระบบดีไซน์ของใบงาน #18 (อาร์ตบอร์ด "ระบบดีไซน์" กฎกราฟ 02/03/04/07)

กฎที่ชุดนี้บังคับ:
- **02** ค่าที่มีลำดับ (โซน 1–5, เบา/กลาง/หนัก) ใช้สีเดียวไล่อ่อน→เข้ม ไม่ใช่รุ้ง
  เขียว-เหลือง-แดงทำให้ "เบา" อ่านว่าดีและ "หนัก" อ่านว่าอันตราย ทั้งที่เป็นแค่ระดับ
- **03** สีสถานะ (เขียว/เหลือง/แดง) จองไว้ให้สถานะเท่านั้น ห้ามเป็นสีเส้นข้อมูล
- **04** บริบท (เส้นฐาน เส้นตาราง วันที่ไม่ได้ซ้อม) เป็นสีเทา ถอยไปข้างหลัง
- **07** ค่าเดียวกันใช้สีเดียวกันทุกแท็บ

เทสนี้เป็น *ยามเฝ้ากฎ* ไม่ใช่การเทียบค่าคงที่กับตัวเอง — มันสแกนซอร์สหาสีดิบที่ไม่ผ่าน
token และตรวจว่าไม่มีกราฟไหนหยิบสีสถานะไปใช้เป็นสีข้อมูล
"""

import ast
import re
import unittest
from pathlib import Path

import pandas as pd

DASHBOARD_PATH = Path(__file__).resolve().parent.parent / "scripts" / "dashboard.py"
DASHBOARD_SRC = DASHBOARD_PATH.read_text(encoding="utf-8")

# ทุกอย่างหลัง "# --- DB LOADERS ---" คือส่วนที่วาดหน้าจอจริง รวมบล็อกแท็บทุกแท็บ
CHART_SRC = DASHBOARD_SRC.split("# --- DB LOADERS ---", 1)[1]

HEX = re.compile(r"#[0-9a-fA-F]{6}\b")


def extract_helpers(*names):
    tree = ast.parse(DASHBOARD_SRC)
    wanted = set(names)
    nodes = []
    found = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if targets & wanted:
                nodes.append(node)
                found |= targets & wanted
        elif isinstance(node, ast.FunctionDef) and node.name in wanted:
            nodes.append(node)
            found.add(node.name)
    missing = wanted - found
    if missing:
        raise AssertionError(f"dashboard.py ไม่มี: {sorted(missing)}")
    namespace = {"pd": pd, "float": float, "zip": zip, "dict": dict}
    exec(
        compile(ast.Module(body=nodes, type_ignores=[]), "dashboard.py", "exec"),
        namespace,
    )
    return namespace


TOKENS = extract_helpers(
    "BLUE_RAMP_3",
    "BLUE_RAMP_5",
    "C_BLUE",
    "C_CONTEXT",
    "C_CRIT",
    "C_GOOD",
    "C_NEUTRAL",
    "C_SECOND",
    "C_WARN",
    "INTENSITY_COLORS",
    "INTENSITY_ORDER",
    "SERIES_COLORS",
)

STATUS_COLOURS = {
    TOKENS["C_GOOD"].lower(),
    TOKENS["C_WARN"].lower(),
    TOKENS["C_CRIT"].lower(),
}


class StatusColourIsReservedTests(unittest.TestCase):
    """กฎ 03 — เขียว/เหลือง/แดงบอกสถานะ ถ้าเป็นสีเส้นกราฟด้วย สีเดียวจะแปลสองความหมาย"""

    def test_no_chart_series_is_drawn_in_a_status_colour(self):
        # จับทั้งแบบอ้าง token (C_GOOD) และแบบเขียน hex ตรง ๆ ในตำแหน่งที่เป็นสีข้อมูล
        offenders = []
        for match in re.finditer(
            r"(line=dict\(color=|marker_color=|color_discrete_sequence=|"
            r"color_discrete_map=|colorway=)([^\n]*)",
            CHART_SRC,
        ):
            fragment = match.group(2)
            for colour in HEX.findall(fragment):
                if colour.lower() in STATUS_COLOURS:
                    offenders.append(match.group(0)[:90])
            for token in ("C_GOOD", "C_WARN", "C_CRIT"):
                if token in fragment:
                    offenders.append(match.group(0)[:90])
        self.assertEqual(offenders, [], "สีสถานะถูกใช้เป็นสีข้อมูล")

    def test_status_colours_are_still_defined_for_status(self):
        # กันการ "แก้" ด้วยการลบ token ทิ้งแล้วเขียน hex กระจายแทน
        self.assertEqual(len(STATUS_COLOURS), 3)

    def test_a_status_band_behind_a_chart_is_not_a_series_and_stays_allowed(self):
        # add_hrect ที่ระบายโซน Readiness ต่ำเป็นการบอก *สถานะ* บนกราฟ ไม่ใช่เส้นข้อมูล
        # จึงใช้สีสถานะได้ถูกต้อง — เขียนไว้เพื่อไม่ให้ใครไป "แก้" มันในภายหลัง
        self.assertIn("add_hrect(y0=0, y1=50, fillcolor=C_CRIT", DASHBOARD_SRC)


class OrdinalRampTests(unittest.TestCase):
    """กฎ 02 — ค่าที่มีลำดับใช้สีเดียวไล่ระดับ"""

    def test_intensity_uses_one_hue_from_light_to_dark(self):
        colours = [TOKENS["INTENSITY_COLORS"][label] for label in TOKENS["INTENSITY_ORDER"]]
        self.assertEqual(colours, TOKENS["BLUE_RAMP_3"])
        for colour in colours:
            self.assertNotIn(colour.lower(), STATUS_COLOURS)

    def test_the_ramp_gets_darker_at_every_step_so_order_survives_greyscale(self):
        # พิมพ์ขาวดำแล้วต้องยังอ่านลำดับออก — ความสว่างต้องลดลงทุกขั้น ไม่ใช่แค่สีต่างกัน
        for ramp in (TOKENS["BLUE_RAMP_3"], TOKENS["BLUE_RAMP_5"]):
            luminance = [
                0.299 * int(c[1:3], 16) + 0.587 * int(c[3:5], 16) + 0.114 * int(c[5:7], 16)
                for c in ramp
            ]
            self.assertEqual(luminance, sorted(luminance, reverse=True), ramp)

    def test_hr_zone_bars_stopped_using_a_rainbow(self):
        self.assertNotIn("#7ac043", DASHBOARD_SRC, "ยังมีสีเขียวอ่อนของแถบโซนเดิมอยู่")
        self.assertNotIn("#e8743b", DASHBOARD_SRC, "ยังมีสีส้มแดงของแถบโซนเดิมอยู่")
        self.assertIn("color_discrete_sequence=BLUE_RAMP_5", DASHBOARD_SRC)


class SeriesColourConsistencyTests(unittest.TestCase):
    """กฎ 07 — ค่าเดียวกันใช้สีเดียวกันทุกแท็บ จึงต้องมีแผนที่เดียว ไม่ใช่ตัดสินในกราฟ"""

    def test_every_series_colour_comes_from_the_design_tokens(self):
        allowed = {
            TOKENS["C_BLUE"].lower(), TOKENS["C_SECOND"].lower(),
            TOKENS["C_CONTEXT"].lower(), TOKENS["C_NEUTRAL"].lower(),
            *(c.lower() for c in TOKENS["BLUE_RAMP_5"]),
        }
        for name, colour in TOKENS["SERIES_COLORS"].items():
            self.assertIn(colour.lower(), allowed, f"{name} ใช้สีนอกระบบดีไซน์")

    def test_charts_read_the_map_instead_of_choosing_colours_inline(self):
        # เดิมแต่ละกราฟเลือกเอง จึงเกิด HR แดงในกราฟหนึ่ง Readiness เขียวในอีกกราฟ
        self.assertGreaterEqual(
            CHART_SRC.count("SERIES_COLORS["), 8,
            "กราฟส่วนใหญ่ยังไม่ได้อ่านสีจากแผนที่กลาง",
        )
        self.assertNotIn("health_colors", DASHBOARD_SRC,
                         "ยังมีแผนที่สีเฉพาะกิจของกราฟเดียวหลงเหลือ")

    def test_no_raw_hex_is_smuggled_into_a_chart_colour(self):
        # สีดิบที่ไม่ผ่าน token คือสีที่ไม่มีใครรู้ว่ามาจากไหนและแก้ที่เดียวไม่ได้
        offenders = [
            match.group(0)[:90]
            for match in re.finditer(r"(marker_color|line=dict\(color)=\"#[0-9a-fA-F]{6}\"", CHART_SRC)
        ]
        self.assertEqual(offenders, [], "มีสีดิบในตำแหน่งสีกราฟ")
        self.assertNotIn("rgb(55, 83, 109)", DASHBOARD_SRC)


class ContextIsGreyTests(unittest.TestCase):
    """กฎ 04 — เส้นฐานและเครื่องหมายบริบทต้องถอยไปข้างหลัง ไม่แย่งสายตากับข้อมูล"""

    def test_baselines_are_context_grey_not_a_second_data_colour(self):
        # เส้นฐาน 28 วันเคยเป็นสีส้ม ซึ่งเป็น "ข้อมูลเส้นที่สอง" ทำให้ฐานดังเท่าค่าจริง
        self.assertTrue('name="ฐานของตัวเอง"' in DASHBOARD_SRC,
                        "หากราฟที่มีเส้นฐานไม่เจอ — เทสนี้หมดหน้าที่แล้ว")
        self.assertEqual(
            CHART_SRC.count('line=dict(color=C_CONTEXT, width=2, dash="dash")'), 2,
            "เส้นฐานทั้งสองเส้น (EF และโหลด) ต้องเป็นสีบริบท ไม่ใช่สีข้อมูลเส้นที่สอง",
        )
        self.assertFalse(
            'dash="dash"' in CHART_SRC and 'color=C_SECOND, width=2, dash="dash"' in CHART_SRC,
            "ยังมีเส้นฐานที่ใช้สีข้อมูลเส้นที่สองอยู่",
        )

    def test_the_partial_today_marker_uses_the_context_token(self):
        self.assertTrue('line=dict(color=C_CONTEXT, dash="dot", width=1)' in DASHBOARD_SRC,
                        "เส้นบอก 'วันนี้ยังไม่จบ' ยังไม่ได้ใช้ token สีบริบท")


class PlotlyTemplateTests(unittest.TestCase):
    """template คือที่ที่กราฟซึ่งไม่ได้ตั้งสีเองจะไปหยิบสี — ต้องเป็นของระบบดีไซน์"""

    def test_template_is_defined_after_the_tokens_it_uses(self):
        # ถ้า template ถูกตั้งก่อนค่าคงที่สี จะ NameError ตอน import
        self.assertLess(
            DASHBOARD_SRC.index("C_SECOND = "),
            DASHBOARD_SRC.index("_print_friendly.layout.colorway"),
        )

    def test_template_carries_the_design_system_not_plotly_defaults(self):
        for snippet in (
            "_print_friendly.layout.colorway = [C_BLUE, C_SECOND",
            "IBM Plex Sans Thai",
            "_axis.gridcolor",
        ):
            self.assertIn(snippet, DASHBOARD_SRC, snippet)

    def test_gridlines_match_the_border_colour_in_the_streamlit_theme(self):
        config = (DASHBOARD_PATH.parent.parent / ".streamlit" / "config.toml").read_text(
            encoding="utf-8"
        )
        self.assertIn('borderColor = "#e4e1da"', config)
        self.assertIn('_axis.gridcolor = "#e4e1da"', DASHBOARD_SRC)


class ThemeConfigTests(unittest.TestCase):
    def test_metric_numbers_are_toned_below_the_verdict_numbers(self):
        config = (DASHBOARD_PATH.parent.parent / ".streamlit" / "config.toml").read_text(
            encoding="utf-8"
        )
        self.assertIn("metricValueFontSize", config)
        self.assertIn("metricValueFontWeight", config)

    def test_the_streamlit_chart_palette_avoids_status_colours_too(self):
        # ค่าพวกนี้ทาทับกราฟฝั่งหน้าเว็บได้ ถ้ามีเขียว/เหลืองอยู่ในลำดับ กราฟที่ไม่ได้ตั้งสีเอง
        # อาจได้สีสถานะมาโดยที่ไม่มีใครเขียนไว้ในโค้ดเลย
        config = (DASHBOARD_PATH.parent.parent / ".streamlit" / "config.toml").read_text(
            encoding="utf-8"
        )
        line = next(l for l in config.splitlines() if l.startswith("chartCategoricalColors"))
        for colour in HEX.findall(line):
            self.assertNotIn(colour.lower(), STATUS_COLOURS, line)


if __name__ == "__main__":
    unittest.main()
