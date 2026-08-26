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
            (day, 50 + offset % 3, 80, 50.0 + (offset % 6) * 0.2, day + "T08:00:00Z"),
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


if __name__ == "__main__":
    unittest.main()
