"""แท็บการฟื้นตัวต้องซื่อกับสิ่งที่วาดจริง (ใบงาน #18 เฟส 3)

เทสชุดนี้เรนเดอร์แท็บจริงผ่าน ``AppTest`` บน DB ที่ปั้นขึ้นเอง แล้วอ่าน **สิ่งที่ถูกส่ง
ออกไปหน้าเว็บ** — หัวข้อกราฟ จำนวนแกน y และข้อความที่โค้ชต้องอ่าน — ไม่ใช่รูปร่างของโค้ด
จึงรอดการจัดโครงใหม่ แต่แดงทันทีที่พฤติกรรมเพี้ยน

ที่มาของแต่ละกฎอยู่ที่ ``docs`` และคอมเมนต์ในใบงาน #18:

- **หัวข้อห้ามสัญญาของที่ไม่มี** — Forerunner 165 (Tong, Dan) ไม่ส่ง ``training_readiness``
  เลยสักวันใน 128 วัน ส่วน fenix 8 (P'kao) ส่งครบ 127/127 กราฟจึงมีเส้นเดียวบ่อย ๆ
  แต่หัวข้อยังเขียนว่า "Stress เทียบ Training Readiness"
- **แกนเดียวต่อกราฟ (กฎกราฟ 01)** — แกนขวาทำให้เส้นสองเส้นตัดกันโดยไม่มีความหมาย
- **ห้ามกำแพงตัวหนังสือ** — caption ยาว ๆ ใต้ทุกกราฟทำให้หาค่าที่ต้องดูไม่เจอ
"""

import datetime
import sys
import unittest
from pathlib import Path

# harness เป็นไฟล์พี่น้องในโฟลเดอร์เดียวกัน — `unittest discover -s tests` ใส่ path นี้ให้เอง
# แต่การเรียกแบบ `python -m unittest tests.<module>` ไม่ใส่ จึงต้องบอกเองเพื่อให้รันได้ทั้งสองท่า
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dashboard_tab_harness import (
    LAST_DAY,
    RECOVERY_TAB_LABEL,
    is_missing,
    render_tab,
    y_values,
)


def seed_wellness(conn, *, readiness):
    """ใส่นักกีฬาคนเดียวกับ wellness 30 วัน (เว้นวันจริงหนึ่งวัน)

    ``readiness=False`` จำลองนาฬิกาที่ไม่ส่ง Training Readiness/Recovery Time
    ซึ่งเป็นเคสของนักกีฬาสองในสามคนจริงในโปรเจกต์นี้
    """
    conn.execute(
        "INSERT INTO dim_athlete (athlete_id, slug, display_name) "
        "VALUES (1, 'tester', 'Tester')"
    )
    for offset in range(30):
        if offset == 10:
            # เว้นวันจริงหนึ่งวัน — Garmin ไม่ส่งข้อมูลทุกวันเสมอไป และช่องว่างนี้
            # คือของที่ทำให้เทส "ห้ามลากเส้นข้ามวันที่ไม่มีค่า" มีอะไรให้จับ
            continue
        day = (LAST_DAY - datetime.timedelta(days=29 - offset)).isoformat()
        conn.execute(
            "INSERT INTO fact_daily_wellness ("
            " athlete_id, calendar_date, resting_hr, hrv_last_night,"
            " hrv_weekly_avg, sleep_score, body_battery_high, stress_avg,"
            " training_readiness, recovery_time_min, fetched_at)"
            " VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                day,
                48 + offset % 4,
                60 + offset % 9,
                62,
                70 + offset % 10,
                85,
                30 + offset % 12,
                (55 + offset % 20) if readiness else None,
                (600 + offset * 5) if readiness else None,
                day + "T08:00:00Z",
            ),
        )


class RecoveryTabRenderTests(unittest.TestCase):
    """เรนเดอร์แท็บการฟื้นตัวจริงแล้วอ่านสิ่งที่ออกไปหน้าเว็บ"""

    @staticmethod
    def render(*, readiness):
        return render_tab(
            RECOVERY_TAB_LABEL, lambda conn: seed_wellness(conn, readiness=readiness)
        )

    def test_chart_titles_name_only_the_series_actually_drawn(self):
        """นาฬิกาที่ไม่ส่ง Readiness ต้องไม่เห็นหัวข้อที่พูดถึง Readiness

        เดิมกราฟชื่อ "Stress เทียบ Training Readiness" ถูกวาดด้วยเส้น Stress เส้นเดียว
        โค้ชอ่านแล้วเข้าใจว่าข้อมูลหาย ทั้งที่นาฬิการุ่นนี้ไม่เคยมีค่านี้เลย
        """
        _, charts = self.render(readiness=False)

        self.assertTrue(charts, "แท็บการฟื้นตัวไม่ได้วาดกราฟสักใบ")
        for chart in charts:
            title = chart.layout.title.text or ""
            drawn = " ".join(trace.name or "" for trace in chart.data)
            for word in ("Readiness", "Recovery Time"):
                if word in title:
                    self.assertIn(
                        word, drawn,
                        f"หัวข้อ {title!r} เอ่ยถึง {word} แต่ไม่มีเส้นไหนวาดค่านั้นเลย",
                    )

    def test_every_chart_draws_on_a_single_y_axis(self):
        """กฎกราฟ 01 — แกนขวาทำให้จุดตัดของสองเส้นดูมีความหมายทั้งที่ไม่มี

        Stress กับ Readiness เป็นคะแนน 0–100 เหมือนกัน จึงใช้แกนเดียวกันได้ตรง ๆ
        ส่วน Resting HR (bpm) กับ HRV (ms) คนละหน่วยจริง ต้องแยกเป็นคนละกราฟ
        """
        for readiness in (False, True):
            with self.subTest(readiness=readiness):
                _, charts = self.render(readiness=readiness)
                for chart in charts:
                    layout = chart.layout.to_plotly_json()
                    title = (layout.get("title") or {}).get("text", "")
                    extra_axes = sorted(
                        key for key in layout
                        if key.startswith("yaxis") and key != "yaxis"
                    )
                    self.assertEqual(
                        [], extra_axes,
                        f"กราฟ {title!r} ยังมีแกนที่สอง {extra_axes}",
                    )

    def test_resting_hr_and_hrv_are_two_charts_with_their_own_units(self):
        """แยกแล้วต้องยังเห็นครบทั้งสองเรื่อง ไม่ใช่หายไปข้างหนึ่ง"""
        _, charts = self.render(readiness=False)

        axis_titles = [chart.layout.yaxis.title.text or "" for chart in charts]
        drawn = [[trace.name for trace in chart.data] for chart in charts]
        self.assertTrue(
            any("bpm" in title for title in axis_titles),
            f"ไม่มีกราฟไหนมีแกนหน่วย bpm — แกน y ที่เจอ: {axis_titles}",
        )
        self.assertTrue(
            any("ms" in title for title in axis_titles),
            f"ไม่มีกราฟไหนมีแกนหน่วย ms — แกน y ที่เจอ: {axis_titles}",
        )
        for chart_traces in drawn:
            self.assertFalse(
                any("Resting HR" in (name or "") for name in chart_traces)
                and any("HRV" in (name or "") for name in chart_traces),
                f"Resting HR กับ HRV ยังอยู่กราฟเดียวกัน: {chart_traces}",
            )

    def test_no_chart_draws_an_empty_line_or_bridges_a_missing_day(self):
        """เส้นที่ไม่มีค่าเลยต้องไม่ถูกวาด และวันที่ Garmin ไม่ส่งต้องเป็นช่องว่างจริง

        เดิมกฎนี้ถูกเฝ้าด้วยการหาชื่อตัวแปร ``rhr_hrv_series = available_series``
        ในซอร์ส ซึ่งแดงทันทีที่จัดโครงใหม่ทั้งที่เจตนายังถูก — ตอนนี้อ่านจากกราฟที่วาดจริง
        """
        for readiness in (False, True):
            with self.subTest(readiness=readiness):
                _, charts = self.render(readiness=readiness)
                for chart in charts:
                    title = chart.layout.title.text or ""
                    for trace in chart.data:
                        name = trace.name or title
                        values = y_values(trace)
                        self.assertTrue(
                            any(not is_missing(value) for value in values),
                            f"เส้น {name!r} ถูกวาดทั้งที่ไม่มีค่าสักจุด",
                        )
                        self.assertIs(
                            trace.connectgaps, False,
                            f"เส้น {name!r} ลากข้ามวันที่ไม่มีค่า ทำให้ช่องว่างหายไปจากสายตา",
                        )
                    self.assertTrue(
                        any(
                            is_missing(value)
                            for trace in chart.data
                            for value in y_values(trace)
                        ),
                        f"กราฟ {title!r} ไม่มีช่องว่างเลยทั้งที่ข้อมูลทดสอบขาดไปหนึ่งวัน",
                    )

    def test_a_watch_that_never_reports_readiness_is_told_so_plainly(self):
        """ไม่ซ่อนหัวข้อที่นาฬิกาไม่รองรับ แต่บอกตรง ๆ ว่าทำไมไม่มีค่า

        เดิมเฝ้าด้วยการหาข้อความดิบในซอร์ส ซึ่งแดงทุกครั้งที่แก้คำ — ตอนนี้อ่านจากกล่อง
        ที่ถูกวาดจริง และยืนยันแค่ว่ามันพูดถึงสิ่งที่โค้ชต้องรู้
        """
        tab, _ = self.render(readiness=False)

        messages = [element.value for element in tab.get("info")]
        self.assertTrue(
            any("Training Readiness" in message for message in messages),
            f"ไม่มีกล่องไหนอธิบายว่าทำไมไม่มี Training Readiness — กล่องที่เจอ: {messages}",
        )
        self.assertTrue(
            any("Recovery Time" in message for message in messages),
            f"ไม่มีกล่องไหนอธิบายเรื่อง Recovery Time — กล่องที่เจอ: {messages}",
        )

    def test_the_tab_is_not_a_wall_of_text(self):
        """โค้ชต้องเห็นตัวเลข ไม่ใช่ย่อหน้าอธิบายใต้ทุกกราฟ

        ``AppTest`` แผ่ caption ที่อยู่ใน ``st.expander`` ออกมาปนกับที่เห็นตลอด
        เพดาน 4 จึงเผื่อไว้ให้ caption ในกล่องพับ 2 อัน — ที่เห็นตลอดเหลือ 2
        ส่วนเพดานความยาวคือตัวที่ฆ่า "ย่อหน้า 5 บรรทัดใต้การ์ด" โดยตรง
        """
        for readiness in (False, True):
            with self.subTest(readiness=readiness):
                tab, _ = self.render(readiness=readiness)
                captions = [element.value for element in tab.get("caption")]

                self.assertLessEqual(
                    len(captions), 4,
                    "แท็บการฟื้นตัวมี caption "
                    f"{len(captions)} อัน:\n" + "\n".join(f"- {c}" for c in captions),
                )
                for caption in captions:
                    self.assertLessEqual(
                        len(caption), 120,
                        f"caption ยาว {len(caption)} ตัวอักษร = ย่อหน้า ไม่ใช่คำกำกับ:\n{caption}",
                    )


if __name__ == "__main__":
    unittest.main()
