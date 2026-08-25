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


def extract_helpers(*names):
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
    # `focus_athlete` เขียนลง st.session_state — ให้ตัวปลอมที่เก็บค่าจริงไว้ตรวจได้
    class _FakeStreamlit:
        session_state = {}

    namespace = {"pd": pd, "float": float, "html": html, "st": _FakeStreamlit}
    exec(
        compile(ast.Module(body=nodes, type_ignores=[]), "dashboard.py", "exec"),
        namespace,
    )
    return namespace


HELPERS = extract_helpers(
    "STATUS_SHAPES",
    "status_parts",
    "status_shape_svg",
    "render_team_card",
    "STATUS_COLORS",
    "STATUS_TEXT_COLORS",
    "C_CRIT",
    "C_WARN",
    "C_GOOD",
    "C_BLUE",
    "_num_text",
    "TEAM_URGENCY_ORDER",
    "team_urgency_rank",
    "team_status",
)


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
        # "ข้อมูลไม่พอ" มาก่อน "พร้อมซ้อม" เพราะช่องว่างของหลักฐานต้องถูกเห็น
        # ไม่ใช่ถูกกลบไว้ท้ายรายการหลังคนที่ไม่มีอะไรต้องทำ
        rank = HELPERS["team_urgency_rank"]
        shuffled = [
            "🟢 พร้อมซ้อม",
            "⚪ ข้อมูลไม่พอ",
            "🔴 ต้องพัก/ลดโหลด",
            "🟡 เฝ้าระวัง",
        ]
        self.assertEqual(
            sorted(shuffled, key=rank),
            [
                "🔴 ต้องพัก/ลดโหลด",
                "🟡 เฝ้าระวัง",
                "⚪ ข้อมูลไม่พอ",
                "🟢 พร้อมซ้อม",
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
        "สถานะ": "🟡 เฝ้าระวัง",
        "ประสิทธิภาพการวิ่งเบา (EF)": "+2% จากฐาน 28 วัน",
        "โซน EF": "🟢 ปกติ",
        "โหลด 7 วัน": "32.6 km · -12% จากฐาน 28 วัน",
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
        # BB, Sleep, RHR, HRV คือ 4 ค่าที่นับเป็น fresh_core_count ซึ่งตัดสินว่าเขียวได้ไหม
        # และ BB<40 ยังเป็นเงื่อนไขธง — โชว์วันที่ของมันในบรรทัดความสดแต่ไม่โชว์ค่า
        # ทำให้อ่านเหมือนลืม ไม่เหมือนเลือก
        markup = HELPERS["render_team_card"](dict(self.ROW))
        for label in ("BODY BAT.", "SLEEP", "RHR", "HRV"):
            self.assertIn(label, markup, f"การ์ดไม่ได้แสดง {label}")
        self.assertIn(">89<", markup, "ค่า Body Battery ไม่ได้ขึ้นบนการ์ด")

    def test_blank_efficiency_says_why_instead_of_reading_like_a_broken_sync(self):
        # เคสจริงของ P'kao: ซ้อม cross-training เป็นหลัก จึงแทบไม่มีรัน easy ให้คำนวณ
        # ถ้าปล่อยเป็นขีดเปล่า ๆ โค้ชจะอ่านว่า sync พังแล้วไปไล่แก้ระบบที่ไม่ได้เสีย
        row = dict(self.ROW, **{
            "ประสิทธิภาพการวิ่งเบา (EF)": "–",
            "โซน EF": "⚪ ข้อมูลไม่พอ",
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

    แท็บทีมได้โควตาบรรทัดเดียว — บรรทัดที่บอกว่าอะไรคือตัวตัดสิน ที่เหลือพับเก็บ
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
        namespace = extract_helpers(
            "focus_athlete", "ATHLETE_STATE_KEY", "MAIN_TABS_KEY",
            "TAB_TODAY_LABEL", "MAIN_TAB_LABELS",
        )
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

    def test_cross_tab_state_is_computed_outside_the_tab_blocks(self):
        # แท็บวันนี้อ่าน `team_df` ที่มาจากลูปของแท็บทีม ตราบใดที่ลูปนั้นยังอยู่ใน
        # `with tab_team:` การรันเฉพาะแท็บที่เปิดอยู่จะทำให้แท็บวันนี้ NameError ทันที
        # ย้ายออกมานอกบล็อกแท็บแล้ว `.open` จึงปลอดภัย — เทสนี้กันไม่ให้ย้ายกลับเข้าไป
        tabs_at = DASHBOARD_SRC.index("st.tabs(")
        self.assertLess(
            DASHBOARD_SRC.index("team_rows = []"), tabs_at,
            "การคำนวณ team_rows ย้ายกลับเข้าไปในบล็อกแท็บแล้ว — lazy จะพังเงียบ ๆ",
        )
        self.assertLess(DASHBOARD_SRC.index("team_df = pd.DataFrame(team_rows)"), tabs_at)

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
