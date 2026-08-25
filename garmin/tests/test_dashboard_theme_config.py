"""ธีมใน `.streamlit/config.toml` ต้องถูก Streamlit รับไปใช้จริง ไม่ใช่แค่ parse ผ่าน

ที่มา (26 ส.ค. 69): `chartSequentialColors` ถูกใส่ไว้ 7 ค่า แต่ Streamlit บังคับ
**10 ค่าพอดี** มันจึงทิ้งค่าทั้งชุดแล้ว log error ทุกครั้งที่ผู้ใช้เปิดหน้า —
ผู้ใช้เห็นก่อน agent เพราะเทสทุกชั้นที่มีอยู่ตอนนั้นมองไม่เห็น:

- `tomllib.load()` ผ่าน — TOML ถูกต้องตามไวยากรณ์
- `config.get_option()` คืนค่ากลับมาครบ — Streamlit อ่านไฟล์เจอ
- `AppTest` ไม่มี exception — สคริปต์รันจบปกติ

**ด่านที่ขาดคือด่านสุดท้าย: ค่าถูกส่งต่อไปหน้าเว็บจริงไหม** ซึ่งเกิดใน
`_populate_theme_msg()` ตอนเปิด session และเป็นที่ที่ค่าผิดกติกาถูกโยนทิ้งเงียบ ๆ
พร้อม log error เทสชุดนี้เรียกฟังก์ชันนั้นตรง ๆ แล้วดักทั้ง log และค่าที่รอดเข้าไป
จึงจับได้โดยไม่ต้องเปิดเบราว์เซอร์

ถ้าเพิ่มตัวเลือกธีมใหม่แล้วเทสนี้แดง แปลว่าผู้ใช้กำลังจะเห็น error ในจอดำทุกวัน
"""

import logging
import os
import unittest
from pathlib import Path

GARMIN_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = GARMIN_ROOT / ".streamlit" / "config.toml"


class _CaptureLogs(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


def build_theme_message():
    """สร้าง theme message แบบเดียวกับที่ Streamlit ทำตอนเปิด session

    คืน ``(msg, warnings)`` โดย warnings คือข้อความระดับ WARNING ขึ้นไปที่ Streamlit
    บ่นออกมา — ซึ่งคือสิ่งที่ผู้ใช้เห็นในจอดำของ `run_dashboard.bat`
    """
    from streamlit import config
    from streamlit.proto.NewSession_pb2 import CustomThemeConfig
    from streamlit.runtime.app_session import _populate_theme_msg

    handler = _CaptureLogs()
    loggers = [logging.getLogger()] + [
        logging.getLogger(name)
        for name in list(logging.root.manager.loggerDict)
        if name.startswith("streamlit")
    ]
    previous = os.getcwd()
    try:
        os.chdir(GARMIN_ROOT)          # config.toml ถูกอ่านจาก CWD
        for logger in loggers:
            logger.addHandler(handler)
        config.get_config_options(force_reparse=True)
        message = CustomThemeConfig()
        _populate_theme_msg(message)
    finally:
        for logger in loggers:
            logger.removeHandler(handler)
        os.chdir(previous)

    # getMessage() ใส่ args ให้เรียบร้อยแล้ว — เอาไป % ซ้ำจะระเบิดและกลายเป็น ERROR
    # แทนที่จะเป็น FAIL ที่อ่านออก (พลาดมาแล้วตอนเขียนเทสนี้เอง)
    warnings = [
        record.getMessage()
        for record in handler.records
        if record.levelno >= logging.WARNING
    ]
    return message, warnings


class ThemeReachesTheBrowserTests(unittest.TestCase):
    def setUp(self):
        self.message, self.warnings = build_theme_message()

    def test_streamlit_accepts_the_theme_without_complaining(self):
        # ข้อความพวกนี้โผล่ในจอดำของ run_dashboard.bat ทุกครั้งที่เปิดหน้า
        self.assertEqual(
            self.warnings, [],
            "Streamlit ไม่ยอมรับค่าธีมบางตัว ผู้ใช้จะเห็น error ทุกครั้งที่เปิดแดชบอร์ด",
        )

    def test_the_chart_palettes_actually_survive_into_the_message(self):
        # "ไม่มี error" อย่างเดียวไม่พอ — โหมดพังจริงคือค่าถูกโยนทิ้งเงียบ ๆ
        # แล้วหน้าเว็บถอยไปใช้สีเริ่มต้นของ Streamlit โดยที่ config.toml ยังดูถูกต้อง
        self.assertEqual(
            len(self.message.chart_sequential_colors), 10,
            "sequential palette ไม่ได้ถูกส่งไปหน้าเว็บ — Streamlit บังคับ 10 ค่าพอดี",
        )
        self.assertGreater(len(self.message.chart_categorical_colors), 0)

    def test_every_declared_font_face_is_handed_over(self):
        # ฟอนต์ไทยต้องมีทั้ง subset ไทยและละตินต่อหนึ่งน้ำหนัก ไม่งั้นตัวอีกชุดตกไปฟอนต์สำรอง
        declared = CONFIG_PATH.read_text(encoding="utf-8").count("[[theme.fontFaces]]")
        self.assertGreater(declared, 0, "ไม่มี fontFaces ในไฟล์แล้ว — เทสนี้หมดหน้าที่")
        self.assertEqual(
            len(self.message.font_faces), declared,
            "จำนวนฟอนต์ที่ Streamlit รับไปไม่ตรงกับที่ประกาศไว้",
        )

    def test_the_light_theme_lock_is_still_in_place(self):
        # ล็อกธีมสว่างไว้เพื่อให้ตาราง st.dataframe (วาดบน canvas) พิมพ์ลง A4 ได้สะอาด
        # แก้ด้วย print CSS ไม่ได้เพราะแก้พิกเซลใน canvas ไม่ได้
        self.assertEqual(self.message.base, self.message.BaseTheme.LIGHT)


if __name__ == "__main__":
    unittest.main()
