"""แท็บความก้าวหน้าต้องบอก "ของที่ยังไม่มี" ที่เดียว (ใบงาน #18 เฟส 3)

วัดจากของจริงก่อนลงมือ (26 ส.ค. 69, เบราว์เซอร์จริงผ่าน CDP):

| | Tong (Forerunner 165) | P'kao (fenix 8) |
|---|---|---|
| `st.metric` | 6 | 11 |
| caption | 3 (ยาวสุด 119 ตัวอักษร) | 4 |
| กราฟ | 2 · แกนเดียว · สีตรง token | 3 · เหมือนกัน |
| **กล่องแจ้งว่าไม่มีข้อมูล** | **3 กล่องซ้อนกันถาวร** | 0 |

ความหนาแน่นกับสีของแท็บนี้ผ่านเกณฑ์อยู่แล้ว ปัญหาเดียวคือกล่องซ้ำ — นาฬิกาที่ไม่ส่ง
เมตริกขั้นสูงทำให้โค้ชเจอกล่องสีสามใบพูดเรื่องเดียวกันสามแบบทุกครั้งที่เปิดหน้า
ทั้งที่กล่องบนสุดสรุปไว้หมดแล้วว่า "ส่วนที่ไม่แสดงคือค่าที่บัญชีนี้ยังไม่เคยได้รับ"
"""

import datetime
import sys
import unittest
from pathlib import Path

# harness เป็นไฟล์พี่น้องในโฟลเดอร์เดียวกัน — `unittest discover -s tests` ใส่ path นี้ให้เอง
# แต่การเรียกแบบ `python -m unittest tests.<module>` ไม่ใส่ จึงต้องบอกเองเพื่อให้รันได้ทั้งสองท่า
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dashboard_tab_harness import (  # noqa: E402
    LAST_DAY,
    PROGRESS_TAB_LABEL,
    render_tab,
    visible,
)


def seed_basic_watch(conn):
    """นาฬิการุ่นที่ส่ง VO2max ได้แต่ไม่ส่งเมตริกขั้นสูงอื่นเลย — เคสของสองในสามคนจริง

    ไม่มี Lactate Threshold, Endurance Score, Hill Score, องค์ประกอบร่างกาย
    หรือคาดการณ์เวลาแข่ง = หัวข้อที่เหลือไม่มีข้อมูลให้วาด
    """
    conn.execute(
        "INSERT INTO dim_athlete (athlete_id, slug, display_name) "
        "VALUES (1, 'tester', 'Tester')"
    )
    for offset in range(30):
        day = (LAST_DAY - datetime.timedelta(days=29 - offset)).isoformat()
        conn.execute(
            "INSERT INTO fact_daily_wellness ("
            " athlete_id, calendar_date, resting_hr, sleep_score, vo2max_trend, fetched_at)"
            " VALUES (1, ?, ?, ?, ?, ?)",
            # VO2max มีค่าเดียวเมื่อ 26 วันก่อน — เคสจริงของ P'kao ที่วิ่งลู่เป็นหลัก
            # Garmin คำนวณ VO2max ใหม่เฉพาะวันที่วิ่ง GPS นอกลู่ ค่าจึงค้างเงียบ ๆ
            (day, 50 + offset % 3, 80,
             52.8 if offset == 3 else None, day + "T08:00:00Z"),
        )


class ProgressTabGapReportingTests(unittest.TestCase):
    """เรนเดอร์แท็บความก้าวหน้าจริงแล้วอ่านกล่องที่โค้ชต้องอ่าน"""

    @classmethod
    def setUpClass(cls):
        cls.tab, cls.charts = render_tab(PROGRESS_TAB_LABEL, seed_basic_watch)

    def test_missing_data_is_reported_once_not_once_per_section(self):
        """กล่อง "ยังไม่มีข้อมูล" ต้องมีใบเดียว ไม่ใช่ใบละหัวข้อ

        นาฬิกาที่ไม่ส่งเมตริกขั้นสูงทำให้ทุกหัวข้อว่างพร้อมกัน แล้วแต่ละหัวข้อก็ขึ้นกล่อง
        ของตัวเอง — โค้ชอ่านสามรอบเพื่อรู้เรื่องเดียว
        """
        boxes = [element.value for element in visible(self.tab, "info")]

        self.assertLessEqual(
            len(boxes), 1,
            f"แท็บความก้าวหน้าขึ้นกล่องแจ้งว่าไม่มีข้อมูล {len(boxes)} ใบ:\n"
            + "\n".join(f"- {b}" for b in boxes),
        )

    def test_the_one_box_names_what_is_actually_missing(self):
        """ยามคู่กับข้อบน — ยุบให้เหลือใบเดียวได้ แต่ห้ามยุบจนบอกไม่ได้ว่าขาดอะไร

        ถ้าใครแก้ด้วยการลบกล่องทิ้ง หรือเหลือข้อความกว้าง ๆ ที่ไม่ระบุค่า ข้อนี้จะแดง
        """
        boxes = [element.value for element in visible(self.tab, "info")]
        self.assertTrue(boxes, "ไม่มีกล่องบอกเลยว่าอะไรขาด — โค้ชไม่รู้ว่าหัวข้อหายไปไหน")

        joined = " ".join(boxes)
        for name in ("Lactate Threshold", "Endurance"):
            self.assertIn(
                name, joined,
                f"กล่องไม่ได้บอกว่า {name!r} คือค่าที่ขาด — กล่องเดียวต้องระบุให้ครบ",
            )

    def test_a_stale_vo2max_says_how_old_it_is(self):
        """ค่าที่ค้างมา 26 วันห้ามอ่านว่าเป็นของวันนี้

        Garmin คำนวณ VO2max ใหม่เฉพาะวันที่มีวิ่ง GPS นอกลู่ นักกีฬาที่วิ่งลู่เป็นหลัก
        จึงเห็นค่าเดิมค้างเป็นเดือน (วัดจริง 26 ส.ค. 69: P'kao ค้างที่ 31 ก.ค. = 26 วัน)
        การ์ดเดิมเขียนว่า "ล่าสุด" โดยไม่มีวันที่กำกับเลย
        """
        cards = [
            element for element in self.tab.get("metric")
            if "VO2max" in element.label
        ]
        self.assertTrue(cards, "ไม่มีการ์ด VO2max — ข้อมูลทดสอบไม่พอ เทสจะเขียวหลอก")
        note = (cards[0].proto.help or "") + " " + (cards[0].proto.delta or "")
        self.assertRegex(
            note, r"\d{2}/\d{2}/\d{4}",
            "การ์ด VO2max ไม่ได้บอกวันที่ของค่านั้น: "
            f"help={cards[0].proto.help!r} delta={cards[0].proto.delta!r}",
        )

    def test_a_single_reading_is_not_reported_as_no_change(self):
        """มีจุดเดียวในช่วง = เทียบกับอะไรไม่ได้ ห้ามขึ้น +0.0 ซึ่งอ่านว่า "นิ่ง" """
        cards = [
            element for element in self.tab.get("metric")
            if "VO2max" in element.label
        ]
        delta = cards[0].proto.delta or ""
        self.assertNotIn(
            "+0.0", delta,
            f"มีค่าเดียวในช่วงแต่การ์ดขึ้น {delta!r} ซึ่งอ่านว่าไม่มีการเปลี่ยนแปลง",
        )


if __name__ == "__main__":
    unittest.main()
