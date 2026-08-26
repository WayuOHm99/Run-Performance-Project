"""แท็บรายละเอียดเซสชันต้องไม่พึ่งอีโมจิบอกความหมาย (ใบงาน #18 เฟส 3)

วัดจากของจริงก่อนลงมือ (26 ส.ค. 69, เบราว์เซอร์จริงผ่าน CDP, P'kao):
43 `st.metric` แต่ **35 อยู่ในกล่องพับ = เห็นจริง 8** · กราฟ 3 ใบ · caption 3 อัน ·
เพซกับ HR **แยกสองแถวไปแล้ว ไม่ได้ซ้อนแกน** — ความหนาแน่นและกฎกราฟ 01 ผ่านหมด

เหลือกฎเดียวจากทิศทาง A ที่แท็บนี้ไม่เคยได้รับ: **อีโมจิเรนเดอร์ไม่เหมือนกันข้ามเครื่อง
และหายตอนพิมพ์ขาวดำ** ซึ่งเป็นเหตุผลเดียวกับที่ dashboard ล็อกธีมสว่างไว้ แท็บทีมกับ
แท็บวันนี้ถูกแปลงเป็นรูปทรงวาดผ่าน ``status_shape_svg()`` ไปแล้ว แต่แท็บนี้ยังมี
อีโมจิคนละชุด (🔻 🚀 ✅ 📊) ที่ไม่เคยอยู่ใน ``STATUS_SHAPES`` เลย

``st.metric`` รับ SVG ไม่ได้ (ค่าเป็นข้อความล้วน) รูปทรงวาดจึงไม่ใช่ทางออกที่นี่ —
คำที่เขียนไว้บอกความหมายครบอยู่แล้ว ส่วนทิศทางให้ Streamlit วาดลูกศรของมันเองผ่าน
``delta`` ซึ่งเป็น glyph ที่พิมพ์ติด
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
    SPLITS_TAB_LABEL,
    render_tab,
)

# ช่วงอีโมจิที่หายตอนพิมพ์ขาวดำ — ไม่รวมลูกศร/สัญลักษณ์คณิตศาสตร์ที่เป็น glyph ปกติ
EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF\U0000FE0F]"
)


def seed_session_with_splits(conn):
    """กิจกรรมเดียวที่มี splits 8 รอบและแผ่วปลายชัด — พอให้การ์ด Pacing ถูกวาด

    ครึ่งหลังช้ากว่าครึ่งแรกเกิน 2% ซึ่งเป็นเงื่อนไขของคำตัดสิน "แผ่วปลาย"
    ถ้าไม่แผ่วจริง การ์ดจะขึ้นคำอื่นและเทสจะตรวจไม่ตรงเคสที่ตั้งใจ
    """
    conn.execute(
        "INSERT INTO dim_athlete (athlete_id, slug, display_name) "
        "VALUES (1, 'tester', 'Tester')"
    )
    day = LAST_DAY - datetime.timedelta(days=2)
    conn.execute(
        "INSERT INTO fact_activity ("
        " activity_id, athlete_id, activity_type, start_time_local, distance_m,"
        " duration_sec, avg_hr, max_hr, avg_pace_min_per_km, training_load,"
        " training_effect_aerobic)"
        " VALUES (5001, 1, 'running', ?, 8000, 2880, 140, 165, 6.0, 120, 2.5)",
        (f"{day.isoformat()} 06:00:00",),
    )
    for split_num in range(1, 9):
        # ครึ่งแรกเพซ 5.7 ครึ่งหลัง 6.3 = ช้าลง ~10.5% → "แผ่วปลาย"
        pace = 5.7 if split_num <= 4 else 6.3
        conn.execute(
            "INSERT INTO fact_activity_split ("
            " activity_id, split_num, distance_m, duration_sec, avg_hr, max_hr,"
            " avg_cadence, elevation_gain_m, avg_pace_min_km)"
            " VALUES (5001, ?, 1000, ?, ?, ?, 172, 4, ?)",
            (split_num, int(pace * 60), 135 + split_num, 150 + split_num, pace),
        )


class SplitsTabPrintsInBlackAndWhiteTests(unittest.TestCase):
    """เรนเดอร์แท็บรายละเอียดเซสชันจริงแล้วอ่านข้อความที่โค้ชเห็น"""

    @classmethod
    def setUpClass(cls):
        cls.tab, cls.charts = render_tab(SPLITS_TAB_LABEL, seed_session_with_splits)

    def test_no_meaning_is_carried_by_an_emoji(self):
        """ทิศทาง A — อีโมจิหายตอนพิมพ์ขาวดำ ความหมายจึงห้ามฝากไว้กับมัน"""
        texts = (
            [element.label for element in self.tab.get("metric")]
            + [element.value for element in self.tab.get("metric")]
            + [element.value for element in self.tab.get("subheader")]
            + [element.value for element in self.tab.get("caption")]
        )
        offenders = [text for text in texts if text and EMOJI.search(text)]
        self.assertEqual(
            [], offenders,
            "ยังมีอีโมจิบนหน้าจอ:\n" + "\n".join(f"- {t}" for t in offenders),
        )

    def test_the_pacing_verdict_still_says_what_happened(self):
        """ยามคู่กับข้อบน — ตัดอีโมจิได้ แต่คำตัดสินต้องยังอ่านออกว่าเกิดอะไรขึ้น"""
        pacing = [
            element for element in self.tab.get("metric")
            if element.label == "Pacing"
        ]
        self.assertTrue(pacing, "ไม่มีการ์ด Pacing เลย — ข้อมูลทดสอบไม่พอ เทสจะเขียวหลอก")
        self.assertIn(
            "แผ่วปลาย", pacing[0].value,
            f"คำตัดสินหายไปพร้อมอีโมจิ: {pacing[0].value!r}",
        )


if __name__ == "__main__":
    unittest.main()
