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


def team_tab_source():
    """เฉพาะบล็อกของแท็บทีม — กันไม่ให้ assert ไปโดนแท็บอื่นที่ยังไม่ได้รื้อ"""
    start = DASHBOARD_SRC.index("with tab_team:")
    end = DASHBOARD_SRC.index("with tab_today:")
    assert start < end
    return DASHBOARD_SRC[start:end]


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

from dashboard_modules import HELPERS, helpers as _helpers  # noqa: E402

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
        tree = ast.parse(DASHBOARD_SRC)

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

    def helpers(self):
        """``focus_athlete`` เขียนลง ``st.session_state`` จึงต้องยัด st ปลอมให้มันก่อน

        เดิม extractor ของไฟล์นี้ประกอบ namespace เองแล้วใส่ st ปลอมไว้ข้างใน
        ตอนนี้ตัวกลางรับ ``extras`` แทน — เทสจึงถือ st ตัวเดียวกับที่ฟังก์ชันมองเห็น
        """
        fake_streamlit = types.SimpleNamespace(session_state={})
        namespace = _helpers(
            "focus_athlete", "ATHLETE_STATE_KEY", "MAIN_TABS_KEY",
            "TAB_TODAY_LABEL", "MAIN_TAB_LABELS",
            extras={"st": fake_streamlit},
        )
        namespace["st"] = fake_streamlit
        return namespace

    def test_one_click_switches_both_the_athlete_and_the_tab(self):
        # ตั้งแค่ชื่อจะเปลี่ยนคนแต่ค้างอยู่แท็บเดิม ตั้งแค่แท็บจะย้ายหน้าแต่ยังเป็นคนเดิม
        # ทั้งสองอย่างอ่านเหมือนปุ่มเสียพอ ๆ กัน
        namespace = self.helpers()
        state = {}
        namespace["st"].session_state = state
        namespace["focus_athlete"]("Dan")
        self.assertEqual(state[namespace["ATHLETE_STATE_KEY"]], "Dan")
        self.assertEqual(state[namespace["MAIN_TABS_KEY"]], namespace["TAB_TODAY_LABEL"])

    def test_the_tab_label_written_to_state_is_one_streamlit_actually_renders(self):
        # ป้ายแท็บถูกใช้สองที่ (สร้างแท็บ กับเขียนลง session_state) ถ้าดริฟต์จากกัน
        # ปุ่มจะเงียบไปโดยไม่มี error — สลับคนสำเร็จแต่ไม่ย้ายหน้า
        namespace = self.helpers()
        self.assertIn(namespace["TAB_TODAY_LABEL"], namespace["MAIN_TAB_LABELS"])

    def test_tabs_track_state_or_the_button_writes_into_a_void(self):
        # `key` อย่างเดียว **ไม่พอ** — ในซอร์ส Streamlit 1.61 `is_stateful = on_change != "ignore"`
        # ถ้าไม่ส่ง on_change มันไม่เรียก register_widget เลย ป้ายแท็บที่ focus_athlete()
        # เขียนลง session_state จะไม่มีใครอ่านกลับ ปุ่มเงียบโดยไม่มี error
        # (วัดมาแล้ว: key อย่างเดียว tab.open = None ทุกตัว · ใส่ on_change แล้วเป็น True/False)
        self.assertTrue("key=MAIN_TABS_KEY" in DASHBOARD_SRC,
                        "st.tabs ไม่มี key แล้ว ปุ่มบนการ์ดจะสลับแท็บไม่ได้")
        self.assertTrue('on_change="rerun"' in DASHBOARD_SRC,
                        "st.tabs ไม่มี on_change แล้ว แท็บจะไม่ track state ปุ่มจะเงียบ")
        self.assertTrue("key=ATHLETE_STATE_KEY" in DASHBOARD_SRC,
                        "selectbox ไม่ได้ใช้คีย์เดียวกับที่ focus_athlete เขียนลงไป")

    def test_the_team_snapshot_is_built_for_exactly_the_tabs_that_read_it(self):
        # `team_df` ถูกสร้างที่เดียวแต่มีสองแท็บใช้ — แท็บทีมวาดการ์ด แท็บวันนี้อ่านแถว
        # ของนักกีฬาที่เลือก การคำนวณจึงต้องครอบ "พอดี" กับแท็บที่ใช้:
        #   แคบไป -> เปิดแท็บที่ใช้แล้ว NameError ทันที (ผู้ใช้เห็นจอแดง)
        #   กว้างไป -> อีกสี่แท็บจ่ายค่าคำนวณย้อนหลัง 42 วันของนักกีฬาทุกคนฟรี ๆ
        # เดิมเทสนี้ยืนยันด้วย "ตำแหน่งในซอร์สต้องอยู่ก่อน st.tabs(" ซึ่งผูกกับรูปร่างโค้ด
        # และแดงทันทีที่จัดโครงใหม่ทั้งที่เจตนายังถูก — เปลี่ยนมาถามเงื่อนไขจริงแทน
        readers = tabs_around("team_df", "team_rows", when="read")
        builders = tabs_around("team_df", "team_rows", when="assign")
        self.assertEqual(
            readers, builders,
            f"แท็บที่อ่าน team_df คือ {sorted(readers)} แต่คำนวณให้ {sorted(builders)} — "
            "ส่วนต่างคือแท็บที่จะ NameError หรือแท็บที่จ่ายค่าคำนวณโดยไม่ได้ใช้",
        )
        self.assertEqual(
            readers, {"today", "team"},
            f"คาดว่ามีแท็บวันนี้กับแท็บทีมเท่านั้นที่ใช้ team_df แต่เจอ {sorted(readers)}",
        )

    def test_every_tab_body_only_runs_when_that_tab_is_open(self):
        # กราฟ plotly คือตัวกินเวลาหลักของหนึ่งรอบรัน (วัดแล้ว ~0.7 จาก 1.1 วินาที)
        # แท็บไหนหลุดการ์ดนี้ไปจะสร้างกราฟใหม่ทุกครั้งที่หน้าจอ rerun แม้ไม่มีใครเปิดดู
        for name in ("tab_today", "tab_team", "tab_health", "tab_train",
                     "tab_progress", "tab_splits"):
            self.assertTrue(
                f"if {name}.open:" in DASHBOARD_SRC,
                f"{name} ไม่ได้ถูกครอบด้วย .open — มันจะรันทุกครั้งแม้ไม่ได้เปิดอยู่",
            )

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
