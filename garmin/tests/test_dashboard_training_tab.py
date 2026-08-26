"""แท็บการซ้อมต้องอยู่ในระบบดีไซน์และอ่านได้โดยไม่ต้องฝ่ากำแพงตัวหนังสือ (ใบงาน #18 เฟส 3)

วัดจากของจริงก่อนลงมือ (26 ส.ค. 69, เบราว์เซอร์จริงผ่าน CDP, นักกีฬา P'kao):
16 `st.metric` · caption ที่เห็นตลอด 5 อันรวม 738 ตัวอักษร · กราฟ 5 ใบ
**แกนเดียวหมดแล้ว** กฎกราฟ 01 จึงไม่ใช่ปัญหาของแท็บนี้ ปัญหาคือความหนาแน่นกับสี

สีที่หลุดระบบดีไซน์อยู่ที่กราฟ "เพซเทียบความหนัก" ซึ่งระบายสีจุดตาม HR แบบไล่ระดับ
`test_dashboard_chart_tokens.py` จับไม่ได้เพราะมันสแกนหา hex ในซอร์ส แต่สีชุดนี้
ไม่ได้เขียนไว้ในซอร์ส — มันมาจาก template ของ plotly ตอนรันไทม์
"""

import datetime
import re
import sys
import unittest
from pathlib import Path

# harness เป็นไฟล์พี่น้องในโฟลเดอร์เดียวกัน — `unittest discover -s tests` ใส่ path นี้ให้เอง
# แต่การเรียกแบบ `python -m unittest tests.<module>` ไม่ใส่ จึงต้องบอกเองเพื่อให้รันได้ทั้งสองท่า
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dashboard_tab_harness import (  # noqa: E402
    LAST_DAY,
    TRAINING_TAB_LABEL,
    render_tab,
    visible,
)

# โทเคนสีของระบบดีไซน์ (อาร์ตบอร์ด "ระบบดีไซน์" ใบงาน #18) — น้ำเงินไล่เฉดเดียว
# บวกเทาบริบท ตัวเดียวกับที่ `test_dashboard_chart_tokens.py` บังคับกับเส้นกราฟ
DESIGN_BLUES = {"#cde2fb", "#86b6ef", "#2a78d6", "#1a5aa8", "#104281"}
DESIGN_CONTEXT_GREY = "#8a8d94"

# ช่วงอีโมจิที่หายตอนพิมพ์ขาวดำ — ไม่รวมลูกศร/สัญลักษณ์ที่เป็น glyph ปกติ
EMOJI = re.compile(
    "[🌀-🫿☀-➿⬀-⯿️]"
)


def seed_training(conn):
    """นักกีฬาหนึ่งคนกับการวิ่ง easy 20 ครั้งใน 30 วัน — พอให้ทุกหัวข้อของแท็บวาดครบ

    ต้องมี HR, ระยะ และ training_load ครบ ไม่งั้นกราฟเพซเทียบความหนักจะไม่ถูกวาด
    และเทสสีจะเขียวเพราะไม่มีกราฟให้ตรวจ ไม่ใช่เพราะสีถูก · running dynamics ก็ต้องครบ
    ไม่งั้นหัวข้อนั้นหายไปทั้งบล็อกและเทสความหนาแน่นจะนับไม่ตรงกับของจริง
    """
    conn.execute(
        "INSERT INTO dim_athlete (athlete_id, slug, display_name) "
        "VALUES (1, 'tester', 'Tester')"
    )
    for offset in range(20):
        day = LAST_DAY - datetime.timedelta(days=28 - offset)
        conn.execute(
            "INSERT INTO fact_activity ("
            " activity_id, athlete_id, activity_type, start_time_local,"
            " distance_m, duration_sec, avg_hr, max_hr, avg_pace_min_per_km,"
            " training_load, training_effect_aerobic, avg_cadence,"
            " avg_stride_length_cm, avg_ground_contact_time_ms,"
            " avg_vertical_oscillation_cm, avg_vertical_ratio,"
            " hr_zone1_sec, hr_zone2_sec, hr_zone3_sec, hr_zone4_sec, hr_zone5_sec)"
            " VALUES (?, 1, 'running', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                1000 + offset,
                f"{day.isoformat()} 06:00:00",
                8000 + (offset % 5) * 1000,
                2700 + offset * 30,
                132 + offset % 8,
                160 + offset % 8,
                5.6 + (offset % 5) * 0.1,
                90 + offset * 3,
                2.5,
                168 + offset % 4,
                118 + offset % 5,
                240 + offset % 10,
                7.8,
                6.6,
                900, 1500, 240, 60, 0,
            ),
        )
    # cross-training ที่หนักกว่าการวิ่งชัด ๆ — จำลองโปรไฟล์ผสมโหมดแบบ P'kao
    # (19 indoor cardio + 16 HIIT + 5 มวย ใน 90 วัน) ถ้าไม่มีของพวกนี้ เทสสองวง
    # จะเขียวเพราะไม่มีอะไรให้แยก ไม่ใช่เพราะแยกถูก
    for offset in range(12):
        day = LAST_DAY - datetime.timedelta(days=27 - offset * 2)
        conn.execute(
            "INSERT INTO fact_activity ("
            " activity_id, athlete_id, activity_type, start_time_local,"
            " duration_sec, avg_hr, max_hr, training_load, training_effect_aerobic,"
            " hr_zone1_sec, hr_zone2_sec, hr_zone3_sec, hr_zone4_sec, hr_zone5_sec)"
            " VALUES (?, 1, 'hiit', ?, 2400, 150, 180, 110, 3.2, 300, 600, 600, 600, 300)",
            (2000 + offset, f"{day.isoformat()} 18:00:00"),
        )


class TrainingTabDesignTests(unittest.TestCase):
    """เรนเดอร์แท็บการซ้อมจริงแล้วอ่านสิ่งที่ออกไปหน้าเว็บ"""

    @classmethod
    def setUpClass(cls):
        cls.tab, cls.charts = render_tab(TRAINING_TAB_LABEL, seed_training)

    def test_continuous_colour_comes_from_the_blue_ramp_not_a_rainbow(self):
        """กฎกราฟ 02 — ค่าที่มีลำดับใช้สีเดียวไล่ระดับ

        กราฟเพซเทียบความหนักระบายจุดตาม HR โดยไม่ได้ตั้ง colorscale เอง จึงตกไปใช้
        Plasma ของ plotly (ม่วง → ส้ม → เหลือง) ซึ่งอ่านว่า "ร้อน = อันตราย"
        ทั้งที่ HR สูงในเซสชันหนักเป็นเรื่องปกติ และสีเหลือง/แดงถูกจองไว้ให้สถานะ (กฎ 03)
        """
        scaled = [
            chart for chart in self.charts
            if chart.layout.coloraxis is not None and chart.layout.coloraxis.colorscale
        ]
        self.assertTrue(
            scaled,
            "ไม่มีกราฟไหนใช้สีไล่ระดับเลย — ข้อมูลทดสอบไม่พอ เทสนี้จะเขียวหลอก",
        )
        allowed = DESIGN_BLUES | {DESIGN_CONTEXT_GREY}
        for chart in scaled:
            title = chart.layout.title.text or ""
            used = {
                colour.lower()
                for _, colour in chart.layout.coloraxis.colorscale
                if isinstance(colour, str)
            }
            self.assertTrue(
                used <= allowed,
                f"กราฟ {title!r} ใช้สีไล่ระดับนอกระบบดีไซน์: "
                f"{sorted(used - allowed)}",
            )

    def test_the_tab_is_not_a_wall_of_text(self):
        """โค้ชต้องเห็นตัวเลข ไม่ใช่ย่อหน้าอธิบายใต้ทุกหัวข้อ

        วัดจากเบราว์เซอร์จริงก่อนแก้: caption ที่เห็นตลอด 5 อัน รวม 738 ตัวอักษร
        ยาวสุด 298 ตัวอักษร (ข้อจำกัดของ EF) — ทั้งหมดเป็นเหตุผลประกอบตัวเลขที่อยู่
        เหนือมัน จึงควรอยู่ใน ``help`` ของการ์ดนั้น ไม่ใช่ย่อหน้าคั่นกลางหน้า
        """
        captions = [element.value for element in self.tab.get("caption")]

        self.assertLessEqual(
            len(captions), 2,
            f"แท็บการซ้อมมี caption {len(captions)} อัน:\n"
            + "\n".join(f"- {c}" for c in captions),
        )
        for caption in captions:
            self.assertLessEqual(
                len(caption), 120,
                f"caption ยาว {len(caption)} ตัวอักษร = ย่อหน้า ไม่ใช่คำกำกับ:\n{caption}",
            )

    def test_every_number_still_carries_its_own_reasoning(self):
        """ย้ายเหตุผลเข้า ``help`` ได้ แต่ห้ามทิ้ง — ตัวเลขที่ไม่มีที่มาคือตัวเลขที่เชื่อไม่ได้

        ยามคู่กับข้อบน: ถ้าใครแก้ให้ caption หายโดยการลบเนื้อหาทิ้งเฉย ๆ ข้อนี้จะแดง
        """
        helps = [
            element.proto.help for element in self.tab.get("metric")
            if element.proto.help
        ]
        joined = " ".join(helps)
        for topic in ("SD", "โซนปลอดภัย", "โซน HR จริง"):
            self.assertIn(
                topic, joined,
                f"ที่มาของตัวเลขเรื่อง {topic!r} หายไปจากหน้าโดยไม่มีที่อยู่ใหม่",
            )

    def test_the_first_screenful_is_decisions_not_every_number_at_once(self):
        """16 ตัวเลขพร้อมกันคือแท็บที่หนาแน่นที่สุดในไฟล์ — โค้ชหาค่าที่ต้องดูไม่เจอ

        Running dynamics (cadence, stride, GCT, vertical oscillation, ratio) เป็น
        รายละเอียดฟอร์มที่ดูตอนสงสัย ไม่ใช่ค่าที่ต้องเห็นทุกครั้งที่เปิดหน้า จึงย้ายลง
        กล่องพับ — เกณฑ์นับเฉพาะของที่เห็นโดยไม่ต้องกางอะไร
        """
        shown = visible(self.tab, "metric")
        self.assertLessEqual(
            len(shown), 11,
            f"เปิดแท็บมาเห็น {len(shown)} ตัวเลขพร้อมกัน: "
            + " · ".join(element.label for element in shown),
        )

    def test_moving_a_number_into_a_drawer_does_not_delete_it(self):
        """ยามคู่กับข้อบน — ตัวเลขที่ย้ายเข้ากล่องพับต้องยังอยู่บนหน้า ไม่ใช่หายไป"""
        every_label = {element.label for element in self.tab.get("metric")}
        for label in ("Ground Contact", "Vertical Ratio", "Cadence เฉลี่ย"):
            self.assertIn(
                label, every_label,
                f"ตัวเลข {label!r} หายไปจากแท็บ ไม่ใช่แค่ถูกพับเก็บ",
            )

    def test_no_meaning_is_carried_by_an_emoji(self):
        """ทิศทาง A — อีโมจิหายตอนพิมพ์ขาวดำ ความหมายจึงห้ามฝากไว้กับมัน

        การ์ด EF ส่งคำตัดสินผ่าน ``delta`` ซึ่งเป็นข้อความที่โค้ชอ่าน ไม่ใช่คีย์ภายใน
        """
        texts = []
        for element in self.tab.get("metric"):
            texts += [element.label, element.value, element.proto.delta]
        offenders = [text for text in texts if text and EMOJI.search(text)]
        self.assertEqual(
            [], offenders,
            "ยังมีอีโมจิบนหน้าจอ:\n" + "\n".join(f"- {t}" for t in offenders),
        )

    def test_the_ef_verdict_still_says_what_happened(self):
        """ยามคู่กับข้อบน — ตัดอีโมจิได้ แต่คำตัดสินของ EF ต้องยังอ่านออก"""
        ef_cards = [
            element for element in self.tab.get("metric")
            if element.label.startswith("EF ล่าสุด")
        ]
        self.assertTrue(ef_cards, "ไม่มีการ์ด EF เลย — ข้อมูลทดสอบไม่พอ เทสจะเขียวหลอก")
        self.assertTrue(
            (ef_cards[0].proto.delta or "").strip(),
            "คำตัดสิน EF หายไปพร้อมอีโมจิ",
        )

    def test_intensity_split_separates_running_from_cross_training(self):
        """โดนัทต้องแยกวงการวิ่งออกจากวงทั้งหมดเมื่อ cross-training มีน้ำหนักจริง

        ที่มา: P'kao ทำ HIIT/มวย/indoor cardio 49 ครั้งใน 90 วัน วงเดียวที่รวมทุกอย่าง
        แสดงสัดส่วนเบา 33% ขณะที่ **เฉพาะการวิ่งเบาแค่ 22% และหนักถึง 53%** —
        ตัวเลขที่โค้ชใช้ตัดสินโปรแกรมวิ่งจึงถูกเจือจางด้วยงานคนละชนิด
        """
        pies = [
            chart for chart in self.charts
            if any(trace.type == "pie" for trace in chart.data)
        ]
        self.assertTrue(pies, "ไม่มีโดนัทความหนักเลย — ข้อมูลทดสอบไม่พอ เทสจะเขียวหลอก")

        rings = [trace for chart in pies for trace in chart.data if trace.type == "pie"]
        self.assertGreaterEqual(
            len(rings), 2,
            "มีวงเดียว — การวิ่งกับ cross-training ยังถูกรวมเป็นตัวเลขเดียว",
        )
        names = " ".join((ring.name or "") + (ring.title.text or "" if ring.title else "")
                         for ring in rings)
        self.assertIn("วิ่ง", names, f"ไม่มีวงที่ระบุว่าเป็นการวิ่ง: {names!r}")

    def test_the_headline_easy_share_is_the_running_one(self):
        """การ์ดสัดส่วนเบาต้องอ่านจากการวิ่ง ไม่ใช่ตัวเลขที่เจือจางแล้ว

        ข้อมูลทดสอบ: วิ่ง 20 ครั้ง เบา 2,400 วิ/ครั้ง · HIIT 12 ครั้ง หนักกว่ามาก
        ถ้าการ์ดยังอ่านจากทุกกิจกรรม ตัวเลขจะต่ำกว่าความจริงของโปรแกรมวิ่ง
        """
        cards = [
            element for element in self.tab.get("metric")
            if "สัดส่วน" in element.label
        ]
        self.assertTrue(cards, "ไม่มีการ์ดสัดส่วนความหนัก")
        self.assertIn(
            "วิ่ง", cards[0].label,
            f"การ์ดไม่ได้บอกว่านับเฉพาะการวิ่ง: {cards[0].label!r}",
        )


if __name__ == "__main__":
    unittest.main()
