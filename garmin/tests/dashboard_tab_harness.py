"""เรนเดอร์ *หน้าเดียว* ของ dashboard จริงแล้วอ่านสิ่งที่ถูกส่งออกไปหน้าเว็บ

ไม่ใช่ไฟล์เทส — เป็นเครื่องมือที่ ``test_dashboard_pages.py`` ใช้
เทสที่สร้างจากที่นี่อ่าน **ผลลัพธ์** (ข้อความ ตัวเลข ตาราง) ไม่ใช่รูปร่างของโค้ด
จึงรอดการจัดโครงใหม่ แต่แดงทันทีที่พฤติกรรมเพี้ยน

**กับดักที่เคยทำให้เทสเขียวโดยไม่ได้ดูข้อมูลเลย — ปิดไว้ในนี้แล้ว:**
``st.cache_data`` อยู่ข้ามอินสแตนซ์ ``AppTest`` ในโปรเซสเดียวกัน ไม่ล้างก่อน
เคสที่สองจะได้ข้อมูลของเคสแรก (เจอตอน readiness=True ให้ผลเท่ากับ readiness=False เป๊ะ)
"""

import datetime
import importlib.util
import math
import os
import sqlite3
import tempfile
from pathlib import Path


GARMIN_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PATH = GARMIN_ROOT / "scripts" / "dashboard.py"

# path ของแต่ละหน้าที่ส่งให้ AppTest.switch_page
TEAM_PAGE = "app_pages/team.py"
BODY_PAGE = "app_pages/body.py"
TRAINING_PAGE = "app_pages/training.py"
ESTIMATES_PAGE = "app_pages/estimates.py"
SESSION_PAGE = "app_pages/session.py"
SYSTEM_PAGE = "app_pages/system.py"
ALL_PAGES = (TEAM_PAGE, BODY_PAGE, TRAINING_PAGE, ESTIMATES_PAGE, SESSION_PAGE)



def load_script(name, filename):
    spec = importlib.util.spec_from_file_location(
        name, GARMIN_ROOT / "scripts" / filename
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# schema มาจากสคริปต์ที่สร้าง DB จริง ไม่ใช่จาก `data/garmin.db` — ไฟล์นั้นเป็นข้อมูล
# ของเครื่องนี้ ไม่ได้อยู่ในรีโป เทสที่อ่านมันจึงพังทั้งชุดบน CI (เจอจริง PR #47)
# และการอ่านจากที่นี่ยังทำให้เทสแดงเองเมื่อ schema ขยับ แทนที่จะเงียบไปเฉย ๆ
schema = load_script("garmin_schema_for_dashboard_tabs", "02_init_schema.py")

# วันสุดท้ายของข้อมูลที่ปั้น — ใช้วันจริงเพื่อให้ช่วงเวลาเริ่มต้นของหน้าครอบข้อมูลนี้
#
# ต้องเป็น "วันตามเวลาไทย" ตัวเดียวกับที่ dashboard ใช้ (``bangkok_date()``) ไม่ใช่
# ``date.today()`` ของเครื่อง — CI สาย Linux รันด้วย TZ=UTC ช่วง 17:00-24:00 UTC
# วันของเครื่องจะช้ากว่าวันไทยหนึ่งวัน ข้อมูลที่ปั้นเลื่อนไปทั้งชุด แล้วหน้าต่างย้อนหลัง
# นับได้ 27/28 คืนแทน 28/28 (CI แดงจริง 29 ส.ค. 69 ตอน 21:13 UTC)
LAST_DAY = load_script("garmin_dashboard_domain_for_tests", "dashboard_domain.py").bangkok_date()


def is_missing(value):
    """ช่องว่างบนเส้นกราฟมาถึงเทสในรูป ``None`` หรือ ``NaN`` แล้วแต่ชนิดคอลัมน์"""
    return value is None or (isinstance(value, float) and math.isnan(value))


def visible(block, kind):
    """คืนของชนิด ``kind`` ที่โค้ชเห็นทันทีโดยไม่ต้องกางอะไร

    ``tab.get(kind)`` แผ่ของที่อยู่ใน ``st.expander`` ออกมาปนด้วย ทำให้นับ "ของที่เห็น
    ตอนเปิดหน้า" ไม่ได้ — ตัวที่พับอยู่โผล่มาเป็น block ชนิด ``Status`` ในผัง element
    ของ Streamlit 1.61 ฟังก์ชันนี้จึงเดินผังเองแล้วหยุดที่ block นั้น
    """
    found = []

    def walk(node):
        children = getattr(node, "children", None)
        if isinstance(children, dict):
            children = list(children.values())
        for child in children or []:
            if type(child).__name__ in ("Status", "Expander"):
                continue
            if type(child).__name__.lower() == kind.lower():
                found.append(child)
            walk(child)

    walk(block)
    return found


def new_test_db(directory):
    """สร้าง garmin.db ว่างด้วย schema จริง แล้วคืน connection ที่เปิดค้างไว้"""
    destination = Path(directory) / "garmin.db"
    schema.init_schema(destination)
    return sqlite3.connect(destination)


def render_page(page, seed, athlete=None, state=None):
    """คืน ``(main, app)`` ของหน้าที่ขอ หลังเรนเดอร์ dashboard จริงบน DB ที่ ``seed`` ปั้น

    ``main`` คือผังของเนื้อหาหน้า ไม่รวม sidebar ที่หน้าเปลือกวาด

    ``seed`` รับ connection ของ DB เปล่าที่มี schema ครบแล้ว และใส่ข้อมูลที่เคสนั้นต้องการ
    """
    import streamlit as st
    from streamlit.testing.v1 import AppTest

    st.cache_data.clear()
    st.cache_resource.clear()

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        conn = new_test_db(tmp)
        try:
            seed(conn)
            conn.commit()
        finally:
            conn.close()

        previous = os.environ.get("GARMIN_DATA_DIR")
        os.environ["GARMIN_DATA_DIR"] = tmp
        try:
            app = AppTest.from_file(str(DASHBOARD_PATH))
            app.switch_page(page)
            # ค่า widget ต้องตั้งก่อนรัน — หลังออกจาก with นี้ DB ชั่วคราวถูกลบไปแล้ว
            # การ set_value().run() ทีหลังจะอ่าน DB ไม่เจอ
            for key, value in (state or {}).items():
                app.session_state[key] = value
            app.run(timeout=90)
            if athlete is not None:
                app.sidebar.selectbox(key="selected_athlete").set_value(athlete).run(timeout=90)
        finally:
            if previous is None:
                os.environ.pop("GARMIN_DATA_DIR", None)
            else:
                os.environ["GARMIN_DATA_DIR"] = previous

    if list(app.exception):
        raise AssertionError(
            f"หน้า {page!r} โยน exception: "
            + " | ".join(item.value for item in app.exception)
        )
    # คืน ``app.main`` ไม่ใช่ ``app`` — รากของผังรวม sidebar ที่หน้าเปลือกวาดไว้ด้วย
    # เทสที่นับ "ข้อความที่เห็นตอนเปิดหน้า" จะนับ caption ของ sidebar ปนเข้ามาทันที
    # (เจอจริงตอนแยกหน้า: แท็บการฟื้นตัวรายงาน caption 8 อันแทนที่จะเป็น 4)
    return app.main, app


def page_text(block):
    """ทุกข้อความที่หน้าส่งออกไปให้คนอ่าน — markdown, caption, หัวข้อ, ป้าย/ค่า/หมายเหตุของ metric"""
    parts = []

    def walk(node):
        children = getattr(node, "children", None)
        if isinstance(children, dict):
            children = list(children.values())
        for child in children or []:
            kind = type(child).__name__
            if kind == "Metric":
                parts.extend([child.label, child.value, child.proto.delta, child.proto.help])
            elif kind in ("Markdown", "Caption", "Title", "Subheader", "Header", "Alert",
                          "Info", "Warning", "Error"):
                parts.append(child.value)
            elif kind == "Dataframe":
                parts.extend(str(column) for column in child.value.columns)
                parts.append(child.value.to_string())
            walk(child)

    walk(block)
    return chr(10).join(str(part) for part in parts if part)
