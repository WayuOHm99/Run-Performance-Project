"""ตัวเลขบนหน้าจอต้องเป็น IBM Plex Mono ตามระบบดีไซน์ใบงาน #18 (อาร์ตบอร์ด "ระบบดีไซน์")

อาร์ตบอร์ดนิยามไว้ว่า
``.num { font-family: 'IBM Plex Mono', 'IBM Plex Sans Thai', monospace;
font-variant-numeric: tabular-nums; }`` — ความกว้างเท่ากันทุกหลักเพื่อให้ตัวเลขเรียงตรงคอลัมน์

`codeFont` ใน `.streamlit/config.toml` **ทำข้อนี้ให้ไม่ได้** — Streamlit เอาไปลงเฉพาะ
`st.code` / `st.dataframe` ไม่ถึง `st.metric` หรือการ์ด HTML ของเรา (ตรวจในเบราว์เซอร์
26 ส.ค. 69: 0 element ที่ computed เป็น Plex Mono และ FontFace ยัง `unloaded`)
ชุดนี้จึงเป็น *ยามเฝ้ากฎ* ว่าทุกที่ที่ประกาศ `tabular-nums` ได้ฟอนต์ mono ไปด้วยจริง
"""

import ast
import re
import tomllib
import unittest
from pathlib import Path

GARMIN_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_PATH = GARMIN_ROOT / "scripts" / "dashboard.py"
DASHBOARD_SRC = DASHBOARD_PATH.read_text(encoding="utf-8")
CONFIG_PATH = GARMIN_ROOT / ".streamlit" / "config.toml"

MONO_FAMILY = "IBM Plex Mono"
THAI_FAMILY = "IBM Plex Sans Thai"

# กฎ CSS หนึ่งข้อ = "ตัวเลือก { ประกาศ }" ที่ในวงเล็บปีกกาไม่มีปีกกาซ้อนอีก
# (@media ที่ห่ออยู่ข้างนอกจึงไม่ถูกจับ แต่กฎข้างในถูกจับครบ)
CSS_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
# คอมเมนต์ CSS และแท็ก <style> ค้างอยู่หน้าตัวเลือกของกฎแรกในแต่ละบล็อก ถ้าไม่ตัดออก
# ตัวเลือกจะกลายเป็น "<style> [data-testid=...]" ซึ่งไม่ตรงกับอะไรเลย
CSS_TEXT = CSS_COMMENT.sub(" ", DASHBOARD_SRC).replace("<style>", " ")


def css_rules():
    """คืน (ตัวเลือกหนึ่งตัว, ประกาศทั้งก้อน) ของทุกกฎ CSS ที่ฝังอยู่ใน dashboard.py"""
    for selectors, body in CSS_RULE.findall(CSS_TEXT):
        # กฎแรกของแต่ละบล็อกมีหัวสตริงของ Python ค้างอยู่หน้าตัวเลือก
        selectors = selectors.rsplit("{", 1)[-1].rsplit('"""', 1)[-1]
        for selector in selectors.split(","):
            selector = " ".join(selector.split())
            if selector and not selector.startswith("@"):
                yield selector, body


def font_family(body):
    match = re.search(r"font-family\s*:([^;]+)", body)
    if not match:
        return []
    return [part.strip().strip("\"'") for part in match.group(1).split(",")]


class NumbersUseMonoTests(unittest.TestCase):
    def test_every_tabular_nums_rule_also_asks_for_mono(self):
        """ที่ไหนบอกว่า "ตัวเลขต้องเรียงตรงคอลัมน์" ที่นั่นต้องได้ฟอนต์ mono ไปด้วย

        `font-variant-numeric: tabular-nums` อย่างเดียวพึ่งฟีเจอร์ `tnum` ของฟอนต์ที่กำลังใช้
        ซึ่งเป็นฟอนต์ข้อความ ไม่ใช่ mono — เจตนา "เรียงตรงคอลัมน์" จึงยังไม่ถึงหน้าจอ
        """
        mono_selectors = {
            selector
            for selector, body in css_rules()
            if MONO_FAMILY in font_family(body)
        }
        naked = sorted(
            selector
            for selector, body in css_rules()
            if "tabular-nums" in body and selector not in mono_selectors
        )
        self.assertEqual(
            [], naked, f"ประกาศ tabular-nums แต่ไม่ได้ฟอนต์ mono: {naked}"
        )

    def test_metric_values_are_covered(self):
        """`st.metric` เป็นที่อยู่ของตัวเลขส่วนใหญ่ในไฟล์ ต้องถูกครอบด้วย"""
        covered = {
            selector
            for selector, body in css_rules()
            if MONO_FAMILY in font_family(body)
        }
        self.assertIn('[data-testid="stMetricValue"]', covered)

    def test_thai_falls_back_before_generic_monospace(self):
        """Plex Mono ไม่มีตัวไทย — ป้ายที่ปนไทยต้องตกไปที่ Plex Sans Thai ไม่ใช่ฟอนต์ระบบ"""
        stacks = [
            font_family(body)
            for _, body in css_rules()
            if MONO_FAMILY in font_family(body)
        ]
        self.assertTrue(stacks, "ไม่มีกฎไหนใช้ IBM Plex Mono เลย")
        for stack in stacks:
            self.assertEqual([MONO_FAMILY, THAI_FAMILY, "monospace"], stack)

    def test_mono_rule_for_metrics_runs_outside_the_tab_blocks(self):
        """`st.metric` กระจายอยู่ทุกแท็บ และแท็บที่ไม่ได้เปิดไม่รัน (lazy `tab.open`)

        ถ้า CSS ของ metric ถูกฉีดอยู่ในบล็อกแท็บใดแท็บหนึ่ง แท็บอื่นจะไม่ได้ฟอนต์เลย
        ข้อนี้จึงยืนยันว่ามันเป็นคำสั่งระดับบนสุดของสคริปต์ = รันทุกรอบไม่ว่าเปิดแท็บไหน
        """
        tree = ast.parse(DASHBOARD_SRC)
        top_level_names = set()
        for node in tree.body:
            if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
                continue
            call = node.value
            func = call.func
            if not (isinstance(func, ast.Attribute) and func.attr == "markdown"):
                continue
            for arg in call.args:
                if isinstance(arg, ast.Name):
                    top_level_names.add(arg.id)
                elif isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    top_level_names.add(arg.value)

        module_css = "\n".join(
            value
            for value in (
                _string_value(node, tree) for node in top_level_names
            )
            if value
        )
        self.assertIn(
            '[data-testid="stMetricValue"]',
            module_css,
            "CSS ตัวเลขของ st.metric ไม่ได้ถูกฉีดที่ระดับบนสุดของสคริปต์",
        )
        self.assertIn(MONO_FAMILY, module_css)

    def test_numbers_only_ask_for_weights_the_font_actually_ships(self):
        """ขอน้ำหนักที่ไม่ได้ประกาศไว้ = เบราว์เซอร์ปลอมตัวหนาขึ้นเอง ตัวเลขจะดูเลอะ"""
        config = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        available = {
            int(face["weight"])
            for face in config["theme"]["fontFaces"]
            if face["family"] == MONO_FAMILY
        }
        for selector, body in css_rules():
            if MONO_FAMILY not in font_family(body):
                continue
            for weight in re.findall(r"font-weight\s*:\s*(\d+)", body):
                self.assertIn(
                    int(weight),
                    available,
                    f"{selector} ขอน้ำหนัก {weight} แต่ config.toml ไม่ได้โหลดมา",
                )


def _string_value(name, tree):
    """ค่าสตริงของตัวแปรระดับโมดูลชื่อ ``name`` (ถ้า ``name`` เป็นสตริงอยู่แล้วก็คืนเลย)"""
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            if any(
                isinstance(t, ast.Name) and t.id == name for t in node.targets
            ) and isinstance(node.value.value, str):
                return node.value.value
    return name if isinstance(name, str) else ""


if __name__ == "__main__":
    unittest.main()
