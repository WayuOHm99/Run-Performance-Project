"""แท็บรวมทีม — การ์ดต่อคนแทนตาราง 10 คอลัมน์ (เฟส 3 ของใบงาน #18)

ที่มา: ตารางเดิมกว้างเกินจอ ทำให้คอลัมน์ท้าย ๆ ถูกมองข้ามทั้งที่มีข้อมูล และ
สถานะสื่อด้วยอีโมจิ 🔴🟡🟢⚪ ซึ่งเรนเดอร์ไม่เหมือนกันข้ามเครื่องและหายตอนพิมพ์ขาวดำ
— ซึ่งขัดกับเหตุผลที่โปรเจกต์ล็อกธีมสว่างไว้เพื่อให้พิมพ์ A4 ได้

การ์ดต่อคนเรียงตามความเร่งด่วน + รูปทรงวาด (วงกลม/สี่เหลี่ยม/สามเหลี่ยม/วงว่าง)
คู่กับข้อความกำกับเสมอ จึงอ่านได้ทั้งบนจอ บนกระดาษขาวดำ และสำหรับคนตาบอดสี

`team_status()` กับ `efficiency_status()` ยังคืนค่าเดิมไม่เปลี่ยน เพราะแท็บ "วันนี้"
ยังใช้อยู่ — แท็บนั้นรื้อทีหลังตามกฎ "ทีละแท็บ ห้ามรื้อพร้อมกัน"
"""

import ast
import html
import re
import types
import unittest
from pathlib import Path

import pandas as pd

DASHBOARD_PATH = Path(__file__).resolve().parent.parent / "scripts" / "dashboard.py"
DASHBOARD_SRC = DASHBOARD_PATH.read_text(encoding="utf-8")


PAGES_DIR = Path(__file__).resolve().parent.parent / "scripts" / "app_pages"


def team_tab_source():
    """ซอร์สของหน้า "ทีม" — ตั้งแต่แยกหน้า มันคือไฟล์ของตัวเอง ไม่ต้องตัดจากไฟล์รวมแล้ว"""
    return (PAGES_DIR / "team.py").read_text(encoding="utf-8")


def tabs_around(*names, when):
    """ชื่อแท็บที่ครอบการ *อ่าน* (``when="read"``) หรือการ *กำหนดค่า* (``when="assign"``)
    ของชื่อตัวแปรที่ระบุ อยู่ในเส้นทางที่สคริปต์รันจริง

    ใช้ตอบคำถามเดียว: "ค่าที่แท็บหนึ่งต้องใช้ ถูกคำนวณในเงื่อนไขที่ครอบถึงมันไหม"
    ถ้าคำนวณแคบกว่าที่ใช้ = NameError · ถ้ากว้างกว่า = คำนวณทิ้งให้แท็บที่ไม่ได้ใช้
    """
    wanted, found = set(names), set()

    def scan(body, tabs):
        for node in body:
            if isinstance(node, ast.If):
                inner = tabs | set(re.findall(r"tab_(\w+)\.open", ast.unparse(node.test)))
                scan(node.body, inner)
                scan(node.orelse, tabs)
                continue
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue  # นิยาม ไม่ใช่การรัน
            if isinstance(node, (ast.With, ast.For, ast.While, ast.Try)):
                for field in ("body", "orelse", "finalbody"):
                    scan(getattr(node, field, None) or [], tabs)
                for handler in getattr(node, "handlers", []):
                    scan(handler.body, tabs)
                if isinstance(node, ast.For):
                    scan([ast.Expr(value=node.iter)], tabs)
                continue
            targets = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            for sub in ast.walk(node):
                if not (isinstance(sub, ast.Name) and sub.id in wanted):
                    continue
                assigning = any(sub is t for t in targets)
                if (when == "assign") == assigning:
                    found.update(tabs)

    scan(ast.parse(DASHBOARD_SRC).body, set())
    return found


# การคำนวณกับชิ้นส่วนหน้าตาอยู่ใน dashboard_domain.py / dashboard_view.py แล้ว
# จึง import ได้ตรง ๆ ไม่ต้อง ast.parse + exec ทีละ node เหมือนเดิม
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent))

from dashboard_modules import ALL_SRC, HELPERS, helpers as _helpers  # noqa: E402

def css_rules(stylesheet):
    """``(หัว at-rule หรือ None, selector, ประกาศ)`` ทีละกฎ ตามลำดับในไฟล์

    รองรับ at-rule ซ้อนชั้นเดียว (``@media``, ``@container``) ซึ่งพอสำหรับสไตล์ชีตนี้
    และตัดคอมเมนต์ทิ้งก่อน เพราะคอมเมนต์อธิบายยาว ๆ จะถูกนับเป็นส่วนหนึ่งของ selector
    หัว at-rule คืนมาทั้งก้อน (เช่น ``@container (max-width: 800px)``) เพราะผู้เรียก
    ต้องแยกให้ออกว่าเงื่อนไขวัดจากอะไร — หน้าต่าง หรือพื้นที่ของตัว container เอง
    """
    body = stylesheet.split("<style>")[1].split("</style>")[0]
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.DOTALL)
    rules, position, at_rule = [], 0, None
    while (opening := body.find("{", position)) != -1:
        head = body[position:opening].strip()
        if head.startswith("@"):
            at_rule = head
            position = opening + 1
            continue
        closing = body.find("}", opening)
        for selector in body[position:opening].split(","):
            rules.append((at_rule, selector.strip().splitlines()[-1].strip(),
                          body[opening + 1:closing]))
        position = closing + 1
        if at_rule and body[position:].lstrip().startswith("}"):
            at_rule, position = None, body.find("}", position) + 1
    return rules


def columns_at(selector, card_px):
    """``grid-template-columns`` ที่มีผลจริง เมื่อ *ตัวการ์ด* ได้พื้นที่ ``card_px``

    จำลอง cascade แบบง่าย: กฎนอก at-rule ใช้เสมอ · ``@container (max-width: N)``
    ใช้เมื่อ ``card_px <= N`` · กฎหลังทับกฎก่อน

    ``@media (max-width: N)`` ถือว่า **ตอบคำถามนี้ไม่ได้** จึงไม่ถูกนับ — การ์ดกว้าง
    ``card_px`` เกิดได้ที่หน้าต่างกว้างเท่าไหร่ก็ได้ที่ ≥ ``card_px`` (sidebar 300px
    ของ Streamlit กินไปเท่าไหร่ก็ขยับตัวเลขนั้น) ซึ่งคือบั๊กที่เจอ 26 ส.ค. 69 เป๊ะ ๆ:
    หน้าต่าง 1000px ผ่าน @media (max-width: 900px) ไปได้ แต่การ์ดเหลือ 535px แล้วล้น
    """
    tracks = None
    for at_rule, rule_selector, declarations in css_rules(HELPERS["TEAM_CARD_CSS"]):
        if rule_selector != selector:
            continue
        if at_rule is not None:
            if not at_rule.startswith("@container"):
                continue
            limit = re.search(r"max-width:\s*(\d+)px", at_rule)
            if not limit or card_px > int(limit.group(1)):
                continue
        match = re.search(r"grid-template-columns:\s*([^;}]+)", declarations)
        if match:
            tracks = match.group(1)
    assert tracks is not None, f"ไม่พบ grid-template-columns ของ {selector} แล้ว"
    return tracks


def fixed_width_at(selector, card_px):
    """ความกว้างที่ selector นี้ "เรียกร้อง" ตายตัว — มากกว่าที่ได้ = เนื้อหาถูกบีบหรือล้น"""
    return sum(int(value) for value in re.findall(r"(\d+)px", columns_at(selector, card_px)))


def split_tracks(tracks):
    """แยก track ตามช่องว่างระดับบนสุด — ``minmax(0, 1fr)`` ต้องนับเป็นหนึ่งช่อง"""
    parts, depth, current = [], 0, ""
    for character in tracks:
        depth += (character == "(") - (character == ")")
        if character.isspace() and depth == 0:
            if current:
                parts.append(current)
            current = ""
        else:
            current += character
    return parts + ([current] if current else [])


def column_count_at(selector, card_px):
    """จำนวนคอลัมน์ที่ประกาศ โดยกาง ``repeat(N, ...)`` ออกเป็น N ช่อง

    คืน ``None`` เมื่อใช้ ``auto-fit``/``auto-fill`` ซึ่งเบราว์เซอร์คำนวณจำนวนช่อง
    ให้เองตามที่ว่าง = ไหลตามจอโดยไม่ต้องมี breakpoint
    """
    total = 0
    for track in split_tracks(columns_at(selector, card_px)):
        repeat = re.match(r"repeat\(\s*([^,]+),", track)
        if not repeat:
            total += 1
        elif repeat.group(1).strip() in ("auto-fit", "auto-fill"):
            return None
        else:
            total += int(repeat.group(1))
    return total


class StatusPartsTests(unittest.TestCase):
    """สถานะที่ team_status คืนมาเป็นสตริงเดียว — การ์ดต้องแยกรูปทรงกับข้อความออกจากกัน"""

    def test_splits_the_emoji_away_from_the_words(self):
        status_parts = HELPERS["status_parts"]
        self.assertEqual(
            status_parts("🔴 ต้องพัก/ลดโหลด"), ("rest", "ต้องพัก/ลดโหลด")
        )


class TeamOrderTests(unittest.TestCase):
    """คำถามแรกของเช้าคือ "ใครต้องดูก่อน" — การ์ดจึงเรียงตามความเร่งด่วน ไม่ใช่ตามชื่อ"""

    def test_the_athlete_who_needs_a_decision_comes_first(self):
        # "ข้อมูลไม่พอ" มาก่อน "ไม่พบสัญญาณ" เพราะช่องว่างของหลักฐานต้องถูกเห็น
        # ไม่ใช่ถูกกลบไว้ท้ายรายการหลังคนที่ไม่มีอะไรต้องทำ
        rank = HELPERS["team_urgency_rank"]
        shuffled = [
            "🟢 ไม่พบสัญญาณเตือนจากอุปกรณ์",
            "⚪ ข้อมูลไม่พอ",
            "🔴 ต้องพัก/ลดโหลด",
            "🟡 ควรทบทวนก่อนซ้อม",
        ]
        self.assertEqual(
            sorted(shuffled, key=rank),
            [
                "🔴 ต้องพัก/ลดโหลด",
                "🟡 ควรทบทวนก่อนซ้อม",
                "⚪ ข้อมูลไม่พอ",
                "🟢 ไม่พบสัญญาณเตือนจากอุปกรณ์",
            ],
        )


class TeamCardRenderTests(unittest.TestCase):
    def test_summary_is_cards_ordered_by_urgency_not_a_table_wider_than_the_screen(self):
        # ตารางสรุปเดิมมี 10 คอลัมน์ กว้างเกินจอ ทำให้คอลัมน์ท้าย ๆ ถูกมองข้าม
        # ทั้งที่มีข้อมูล — การ์ดต่อคนจึงมาแทน และต้องเรียงตามความเร่งด่วน
        team_tab = team_tab_source()
        self.assertTrue("team_urgency_rank" in team_tab,
                        "แท็บทีมยังไม่ได้เรียงการ์ดตามความเร่งด่วน")
        self.assertFalse("team_summary_columns" in team_tab,
                         "ตารางสรุป 10 คอลัมน์ยังอยู่ ควรถูกแทนด้วยการ์ดต่อคน")


class CardMarkupTests(unittest.TestCase):
    """การ์ดต้องสื่อสถานะด้วยรูปทรง ไม่ใช่อีโมจิ และไม่หลุด HTML จากชื่อนักกีฬา"""

    ROW = {
        "นักกีฬา": "Tong",
        "สถานะ": "🟡 ควรทบทวนก่อนซ้อม",
        "pace–HR trend": "+2% จากฐาน 28 วัน",
        "สถานะ pace–HR": "🔵 แนวโน้มประกอบ",
        "โหลด 7 วัน": "32.6 km",
        "ค่าเฉลี่ยโหลด 28 วัน": "29.4 km/สัปดาห์",
        "ขอบเขตโหลด": "วิ่ง",
        "เซสชัน 7 วัน": 5,
        "Sleep": 78.0,
        "RHR": 41.0,
        "ΔRHR": "-5",
        "HRV คืนล่าสุด": "123 ms · UNBALANCED",
        "Body Battery ตอนนี้/ล่าสุด": 89.0,
        "ความสดรายค่า": "BB 25/08 · Sleep 25/08",
        "ธงเฝ้าระวัง": "HRV UNBALANCED",
    }

    def test_status_reaches_the_card_as_a_drawn_shape_not_an_emoji(self):
        # อีโมจิเรนเดอร์ต่างกันข้ามเครื่องและหายตอนพิมพ์ขาวดำ ซึ่งเป็นเหตุผลเดียวกับ
        # ที่โปรเจกต์ล็อกธีมสว่างไว้เพื่อให้พิมพ์ A4 ได้
        markup = HELPERS["render_team_card"](dict(self.ROW))
        self.assertIn("<svg", markup)
        for emoji in ("🔴", "🟡", "🟢", "🔵", "⚪"):
            self.assertNotIn(emoji, markup, f"ยังมีอีโมจิ {emoji} หลุดเข้าการ์ด")

    def test_shape_differs_per_status_so_colour_is_never_the_only_cue(self):
        shape = HELPERS["status_shape_svg"]
        drawn = {key: shape(key) for key in ("rest", "watch", "ready", "unknown")}
        self.assertIn("<path", drawn["rest"])       # สามเหลี่ยม
        self.assertIn("<rect", drawn["watch"])      # สี่เหลี่ยม
        self.assertIn("<circle", drawn["ready"])    # วงกลมทึบ
        self.assertIn("stroke", drawn["unknown"])   # วงว่าง
        self.assertEqual(len({v for v in drawn.values()}), 4)

    def test_athlete_name_is_escaped_so_stored_text_cannot_inject_markup(self):
        row = dict(self.ROW, **{"นักกีฬา": "<script>x</script>"})
        markup = HELPERS["render_team_card"](row)
        self.assertNotIn("<script>", markup)
        self.assertIn("&lt;script&gt;", markup)

    def test_every_core_freshness_value_the_status_depends_on_is_shown(self):
        # BB, Sleep, RHR, HRV คือ 4 ค่าที่ใช้บอกความครบของข้อมูลอุปกรณ์
        # จึงต้องแสดงค่าจริง ไม่ใช่เพียงวันที่ซึ่งอ่านเหมือนระบบลืมข้อมูล
        markup = HELPERS["render_team_card"](dict(self.ROW))
        for label in ("BODY BAT.", "SLEEP", "RHR", "HRV"):
            self.assertIn(label, markup, f"การ์ดไม่ได้แสดง {label}")
        self.assertIn(">89<", markup, "ค่า Body Battery ไม่ได้ขึ้นบนการ์ด")

    def test_blank_efficiency_says_why_instead_of_reading_like_a_broken_sync(self):
        # เคสจริงของ P'kao: ซ้อม cross-training เป็นหลัก จึงแทบไม่มีรัน easy ให้คำนวณ
        # ถ้าปล่อยเป็นขีดเปล่า ๆ โค้ชจะอ่านว่า sync พังแล้วไปไล่แก้ระบบที่ไม่ได้เสีย
        row = dict(self.ROW, **{
            "pace–HR trend": "–",
            "สถานะ pace–HR": "⚪ ข้อมูลไม่พอ",
        })
        markup = HELPERS["render_team_card"](row)
        self.assertIn("ไม่ใช่ระบบขัดข้อง", markup)

    def test_missing_numbers_render_as_a_dash_not_nan(self):
        row = dict(self.ROW, **{"Sleep": None, "RHR": float("nan")})
        markup = HELPERS["render_team_card"](row)
        self.assertNotIn("nan", markup.lower())


class CrossTabContractTests(unittest.TestCase):
    """แท็บ "วันนี้" อ่าน team_df ที่แท็บทีมสร้าง — เปลี่ยนชื่อคีย์เมื่อไหร่พังเงียบ

    เทสนี้เป็นตาข่ายกันพลาด ไม่ใช่ red-green slice: มันคุม invariant ที่มีอยู่ก่อนแล้ว
    ซึ่งการรื้อแท็บทีมมีโอกาสทำแตกโดยที่แท็บทีมเองยังดูปกติดี
    """

    def test_every_key_the_today_tab_reads_is_still_produced_by_the_team_tab(self):
        # team_rows ถูกสร้างใน dashboard_team.py ส่วนคนอ่านอยู่ app_pages/today.py
        # จึงต้องมองซอร์สทั้งชุด ไม่ใช่ dashboard.py ไฟล์เดียวเหมือนตอนยังรวมกัน
        tree = ast.parse(ALL_SRC)

        produced = set()
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "append"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "team_rows"
                    and node.args and isinstance(node.args[0], ast.Dict)):
                produced |= {
                    key.value for key in node.args[0].keys
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                }
        self.assertTrue(produced, "หา dict ที่ต่อเข้า team_rows ไม่เจอ")

        consumed = {
            node.slice.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == "team_row"
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        }
        self.assertTrue(consumed, "แท็บวันนี้ไม่ได้อ่าน team_row เลย — เทสนี้หมดหน้าที่แล้ว")
        self.assertEqual(
            consumed - produced, set(),
            "แท็บวันนี้อ่านคีย์ที่แท็บทีมไม่ได้สร้างแล้ว จะ KeyError ตอนเปิดหน้า",
        )


class AlwaysOnTextBudgetTests(unittest.TestCase):
    """เกณฑ์วัดผลของใบงาน #18: ข้อความที่เห็นตลอดต้องลดจาก 22 เหลือ <= 5 ทั้งหน้า

    แท็บทีมได้โควตาบรรทัดเดียว — บรรทัดที่บอกขอบเขตของสัญญาณ ที่เหลือพับเก็บ
    """

    def test_team_tab_keeps_one_always_visible_caption(self):
        team_tab = team_tab_source()
        self.assertEqual(
            team_tab.count("st.caption("), 1,
            "แท็บทีมมีคำอธิบายที่เห็นตลอดเกินโควตา — ย้ายเข้า expander เกณฑ์ที่ใช้ประเมิน",
        )


class CardIsADoorTests(unittest.TestCase):
    """การ์ดต้องพาไปหน้ารายคนได้ ไม่ใช่จอแสดงผลอย่างเดียว

    ข้อจำกัดจริงของ Streamlit: HTML ที่ฉีดผ่าน `st.markdown` คุยกลับหา Python ไม่ได้
    การ์ดเองจึงกดไม่ได้ ทางที่เหลือคือปุ่มจริงใต้การ์ด ซึ่งได้โฟกัสคีย์บอร์ดมาด้วยฟรี
    """

    def test_one_click_sets_both_the_athlete_and_the_page_to_go_to(self):
        """ตั้งแค่ชื่อจะเปลี่ยนคนแต่ค้างหน้าเดิม ตั้งแค่หน้าจะย้ายหน้าแต่ยังเป็นคนเดิม
        ทั้งสองอย่างอ่านเหมือนปุ่มเสียพอ ๆ กัน ปุ่มเดียวจึงต้องทำครบทั้งคู่
        """
        import dashboard_context

        state = {}
        original = dashboard_context.st.session_state
        dashboard_context.st.session_state = state
        try:
            dashboard_context.focus_athlete("Dan")
        finally:
            dashboard_context.st.session_state = original

        self.assertEqual(state[dashboard_context.ATHLETE_STATE_KEY], "Dan")
        self.assertEqual(state[dashboard_context.PENDING_PAGE_KEY],
                         dashboard_context.TODAY_PAGE)

    def test_the_callback_does_not_try_to_switch_pages_by_itself(self):
        """``st.switch_page`` ในคอลแบ็กของปุ่ม **เขียนค่าสำเร็จแต่หน้าไม่ย้าย**

        ซอร์สของมันจบด้วย ``st.empty()`` เพื่อบังคับ ScriptRunner ให้ยอมสลับหน้า
        ซึ่งได้ผลเฉพาะตอนสคริปต์กำลังรัน คอลแบ็กทำงานก่อนหน้านั้น ผลคือปุ่มเงียบ
        โดยไม่มี error เลย — เทสกับ AppTest มองไม่เห็น จับได้ด้วย CDP ในเบราว์เซอร์จริง
        เท่านั้น (29 ส.ค. 69) ข้อนี้จึงเฝ้าที่ *รูปแบบ* แทน: คอลแบ็กแค่ฝากคำขอไว้
        แล้วหน้าเปลือกเป็นคนสั่งย้ายหลัง st.navigation
        """
        import inspect
        import textwrap

        import dashboard_context

        def calls_switch_page(function):
            """ดูที่ *การเรียกจริง* ใน AST ไม่ใช่ข้อความในไฟล์

            เขียนแบบค้นข้อความไม่ได้ เพราะคอมเมนต์ของฟังก์ชันนี้อธิบายเรื่อง
            ``st.switch_page`` อยู่ — ยามจะแดงเพราะคำอธิบาย ไม่ใช่เพราะโค้ด
            """
            tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
            return any(
                isinstance(node, ast.Attribute) and node.attr == "switch_page"
                and isinstance(node.value, ast.Name) and node.value.id == "st"
                for node in ast.walk(tree)
            )

        self.assertFalse(calls_switch_page(dashboard_context.focus_athlete),
                         "คอลแบ็กสั่งย้ายหน้าเองไม่ได้ — ต้องฝากไว้ให้หน้าเปลือกทำ")
        self.assertTrue(calls_switch_page(dashboard_context.honour_pending_page))

        shell = (Path(__file__).resolve().parent.parent
                 / "scripts" / "dashboard.py").read_text(encoding="utf-8")
        self.assertLess(
            shell.index("st.navigation("), shell.index("honour_pending_page()"),
            "ต้องเรียกหลัง st.navigation ไม่งั้น switch_page หาหน้าปลายทางไม่เจอ",
        )
        self.assertLess(
            shell.index("honour_pending_page()"), shell.index("page.run()"),
            "ต้องเรียกก่อน page.run() ไม่งั้นหน้าเดิมถูกวาดไปแล้วหนึ่งรอบ",
        )

    def test_the_button_switches_to_a_page_navigation_actually_registers(self):
        """ปุ่มพาไปหน้าที่ ``st.navigation`` ไม่รู้จัก = StreamlitAPIException ตอนกด

        เดิมความเสี่ยงคือป้ายแท็บใน session_state ดริฟต์จากป้ายที่ st.tabs สร้าง
        ตอนนี้ความเสี่ยงย้ายมาที่ path — รูปแบบต่างกัน แต่เป็นความพังแบบเดียวกัน
        """
        import dashboard_context

        shell = (Path(__file__).resolve().parent.parent
                 / "scripts" / "dashboard.py").read_text(encoding="utf-8")
        registered = set(re.findall(r'st\.Page\("([^"]+)"', shell))

        self.assertTrue(registered, "หา st.Page ใน dashboard.py ไม่เจอ")
        self.assertIn(dashboard_context.TODAY_PAGE, registered)
        self.assertIn("key=ATHLETE_STATE_KEY", shell,
                      "selectbox ไม่ได้ใช้คีย์เดียวกับที่ focus_athlete เขียนลงไป")

    def test_the_team_snapshot_is_built_by_exactly_the_pages_that_read_it(self):
        """หน้าไหนอ่าน ``team_df`` ต้องเรียก ``team_snapshot()`` เอง

        เดิม team_df ถูกสร้างกลางสคริปต์แล้วครอบด้วยเงื่อนไข "แท็บใดแท็บหนึ่งเปิดอยู่"
        ซึ่งแคบไปแล้ว NameError กว้างไปแล้วอีกสี่แท็บจ่ายค่าคำนวณย้อนหลัง 42 วันฟรี ๆ
        แยกหน้าแล้วความเสี่ยงเปลี่ยนรูป: หน้าที่อ่านแต่ไม่ได้เรียกจะ NameError เหมือนเดิม
        """
        readers, builders = set(), set()
        for path in sorted(PAGES_DIR.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            if re.search(r"\bteam_df\b|\bteam_rows\b", text):
                readers.add(path.name)
            if "team_snapshot(" in text:
                builders.add(path.name)

        self.assertEqual(
            readers, builders,
            f"หน้าที่อ่าน team_df คือ {sorted(readers)} แต่หน้าที่เรียก team_snapshot() "
            f"คือ {sorted(builders)} — ส่วนต่างคือหน้าที่จะ NameError ตอนเปิด",
        )
        self.assertEqual(readers, {"today.py", "team.py"}, sorted(readers))

    def test_only_the_open_page_runs_and_no_page_is_orphaned(self):
        """กราฟ plotly คือตัวกินเวลาหลักของหนึ่งรอบรัน (วัดแล้ว ~0.7 จาก 1.1 วินาที)

        เดิมต้องแฮ็ก ``if tab_x.open:`` ครอบทุกแท็บ ไม่งั้นทุกแท็บสร้างกราฟใหม่ทุกรอบ
        ``st.navigation`` รันเฉพาะไฟล์ของหน้าที่เปิดอยู่ เงื่อนไขนั้นจึงไม่ต้องมี —
        แต่เกิดความพังแบบใหม่แทน: ไฟล์หน้าที่ไม่ได้ลงทะเบียนจะไม่มีทางเปิดถึงเลย
        """
        shell = (Path(__file__).resolve().parent.parent
                 / "scripts" / "dashboard.py").read_text(encoding="utf-8")
        registered = {Path(p).name for p in re.findall(r'st\.Page\("([^"]+)"', shell)}
        on_disk = {path.name for path in PAGES_DIR.glob("*.py")}

        self.assertEqual(registered, on_disk,
                         f"ลงทะเบียน {sorted(registered)} แต่มีไฟล์ {sorted(on_disk)}")
        self.assertNotIn("st.tabs(", shell, "ยังมี st.tabs ค้างอยู่ — แท็บกับหน้าซ้อนกัน")
        self.assertNotIn("tab_today.open", shell, "ยังมีการแฮ็ก .open ค้างอยู่")

    def test_buttons_do_not_print(self):
        # โปรเจกต์ล็อกธีมสว่างไว้เพื่อให้พิมพ์ A4 ได้ — ปุ่มบนกระดาษกดไม่ได้
        # พิมพ์ออกมาเป็นกล่องเทาใต้การ์ดทุกใบ กินที่เปล่า ๆ
        print_css = DASHBOARD_SRC.split("@media print {", 1)[1]
        self.assertTrue('[data-testid="stButton"]' in print_css,
                        "ปุ่มยังไม่ถูกซ่อนตอนพิมพ์")

    def test_every_card_gets_its_own_button(self):
        team_tab = team_tab_source()
        self.assertTrue("on_click=focus_athlete" in team_tab,
                        "การ์ดยังไม่มีปุ่มพาไปหน้ารายคน")
        self.assertTrue('key=f"open-athlete-' in team_tab,
                        "ปุ่มต้องมี key แยกต่อคน ไม่งั้น Streamlit ทับกันเอง")


class NarrowScreenTests(unittest.TestCase):
    """การ์ดต้องอ่านได้บนจอแคบ ไม่ใช่แค่บนจอโน้ตบุ๊กของคนเขียน

    ที่มา (26 ส.ค. 69): รีวิวเปิดที่ viewport 390px แล้ววัดได้ว่าตัวการ์ดกว้าง 353px
    แต่เนื้อหาข้างในเรียกร้อง 732px — EF กับตัวเลข BB/Sleep/RHR/HRV ฝั่งขวาถูกบีบ
    หรือตัดหายไปเลย เพราะ `.team-card` ประกาศคอลัมน์ตายตัว `232px ... 500px`
    โดยไม่มี breakpoint ใด ๆ (ในไฟล์มี @media แค่ของ print)

    เทสนี้จำลอง cascade แล้วถามคำถามเดียว: **ที่จอกว้างเท่านี้ การ์ดเรียกร้องกี่ px**
    ไม่ผูกกับวิธีแก้ — จะใช้ media query, repeat(auto-fit) หรืออะไรก็ได้ที่ทำให้
    ตัวเลขไม่เกินความกว้างจอ
    """

    # ความกว้างที่ *ตัวการ์ด* ได้จริง วัดจาก headless Chrome 26 ส.ค. 69
    #   353px = หน้าต่าง 390px ไม่มี sidebar (มือถือแนวตั้ง)
    #   535px = หน้าต่าง 1000px + sidebar 300px ← เคสที่ breakpoint ตามหน้าต่างพลาด
    #   815px = หน้าต่าง 1280px + sidebar 300px (โน้ตบุ๊กที่ใช้อยู่ทุกวัน)
    CARD_WIDTHS = (353, 535, 815)

    # ตัวเลขอย่าง "78" กับป้าย "Sleep" ต้องอยู่บรรทัดเดียวกันได้โดยไม่ตัดคำ
    MIN_COLUMN_PX = 110

    def test_the_card_never_demands_more_width_than_it_is_given(self):
        for card_px in self.CARD_WIDTHS:
            with self.subTest(card_px=card_px):
                demanded = fixed_width_at(".team-card", card_px)
                self.assertLessEqual(
                    demanded, card_px,
                    f"เมื่อการ์ดได้พื้นที่ {card_px}px มันยังเรียกร้องคอลัมน์ตายตัวรวม "
                    f"{demanded}px — ตัวเลขฝั่งขวาจะถูกบีบหรือตัดหาย",
                )

    def test_each_number_keeps_enough_room_to_read_on_a_phone(self):
        # แถวตัวเลขเป็น grid ซ้อนใน grid ต่อให้การ์ดยุบเป็นคอลัมน์เดียวแล้ว
        # ถ้าแถวนี้ยังยืนกราน 5 คอลัมน์ ตัวเลขจะเหลือความกว้างละไม่ถึง 80px
        phone = self.CARD_WIDTHS[0]
        columns = column_count_at(".team-card__nums", phone)
        if columns is None:
            return  # auto-fit: เบราว์เซอร์จัดจำนวนช่องให้เองตามที่ว่าง
        self.assertGreaterEqual(
            phone / columns, self.MIN_COLUMN_PX,
            f"บนการ์ดกว้าง {phone}px แถวตัวเลขยังแบ่ง {columns} คอลัมน์ = "
            f"{phone / columns:.0f}px ต่อค่า อ่านไม่ออก",
        )


class OverlayButtonTests(unittest.TestCase):
    """ปุ่มโปร่งใสที่ทาบทั้งใบต้องมองไม่เห็น และต้องสูงเท่าการ์ดเป๊ะ ๆ

    ที่มา (26 ส.ค. 69) วัดจาก headless Chrome ทั้งสองข้อ:
    · กด Tab แล้ว ``opacity: 1`` ปลุกปุ่มขึ้นมา ข้อความ "ดูรายละเอียดของ P'kao"
      จึงลอยทับกลางการ์ด
    · การ์ดสูง 501.34px แต่ปุ่มสูง 495.34px เหลือแถบล่างที่กดไม่โดน เพราะ Streamlit
      ใส่ ``margin-bottom: -1rem`` ให้กล่องเนื้อหาของ st.markdown แล้วกลืน
      ``margin-bottom: 10px`` ของการ์ดไปพร้อมกัน (10 - 16 = -6)
    """

    def card_declarations(self, selector):
        return [declarations for _, rule_selector, declarations
                in css_rules(HELPERS["TEAM_CARD_CSS"]) if rule_selector == selector]

    def test_the_overlay_button_never_becomes_visible(self):
        for at_rule, selector, declarations in css_rules(HELPERS["TEAM_CARD_CSS"]):
            if "st-key-teamcard-" not in selector or "button" not in selector:
                continue
            opacity = re.search(r"opacity:\s*([\d.]+)", declarations)
            if opacity is None:
                continue
            with self.subTest(selector=selector, at_rule=at_rule):
                self.assertEqual(
                    opacity.group(1), "0",
                    f"{selector} ตั้ง opacity เป็น {opacity.group(1)} — ข้อความบนปุ่ม "
                    "จะโผล่ทับการ์ด ต้องบอกสถานะด้วยเส้นรอบการ์ดแทน",
                )

    def test_keyboard_focus_still_leaves_a_visible_mark_on_the_card(self):
        marked = [selector for _, selector, declarations
                  in css_rules(HELPERS["TEAM_CARD_CSS"])
                  if "focus-visible" in selector and "outline:" in declarations]
        self.assertTrue(
            marked, "ไม่มีกฎไหนวาดเส้นตอนโฟกัสด้วยคีย์บอร์ด — คนใช้คีย์บอร์ดจะไม่รู้ว่าอยู่ใบไหน")
        self.assertTrue(
            all(".team-card" in selector for selector in marked),
            f"เส้นโฟกัสถูกวาดที่ {marked} ไม่ใช่ที่ตัวการ์ด")

    def test_the_card_declares_no_vertical_margin_of_its_own(self):
        """ระยะห่างระหว่างการ์ดต้องอยู่ที่ container ไม่ใช่ที่ตัวการ์ด

        ทุก px ที่การ์ดกาง margin แนวตั้งออกมา จะถูก ``margin-bottom: -1rem``
        ของ Streamlit หักกลับ = กล่องเตี้ยกว่าการ์ด = ปุ่มที่ทาบไว้เตี้ยตาม
        """
        for declarations in self.card_declarations(".team-card"):
            offenders = re.findall(r"(margin(?:-top|-bottom)?):\s*([^;}]+)", declarations)
            self.assertEqual(
                offenders, [],
                f".team-card ยังประกาศ {offenders} — ปุ่มที่ทาบทั้งใบจะเตี้ยกว่าการ์ด "
                "เท่าที่ margin นั้นโดนหักกลับ ให้ย้ายไปไว้ที่ [class*=\"st-key-teamcard-\"]",
            )
        spacing = []
        for _, selector, declarations in css_rules(HELPERS["TEAM_CARD_CSS"]):
            gap = re.search(r"margin-bottom:\s*([^;}]+)", declarations)
            if "st-key-teamcard-" in selector and gap and gap.group(1).strip() not in ("0", "0px"):
                spacing.append(selector)
        self.assertTrue(spacing, "ย้าย margin ออกจากการ์ดแล้วแต่ไม่มีใครเว้นระยะระหว่างการ์ดแทน")
