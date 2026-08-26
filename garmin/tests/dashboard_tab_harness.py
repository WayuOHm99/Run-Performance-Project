"""เรนเดอร์ *แท็บเดียว* ของ dashboard จริงแล้วอ่านสิ่งที่ถูกส่งออกไปหน้าเว็บ

ไม่ใช่ไฟล์เทส — เป็นเครื่องมือที่ ``test_dashboard_*_tab.py`` ใช้ร่วมกัน
เทสที่สร้างจากที่นี่อ่าน **ผลลัพธ์** (หัวข้อกราฟ สี แกน caption) ไม่ใช่รูปร่างของโค้ด
จึงรอดการจัดโครงใหม่ แต่แดงทันทีที่พฤติกรรมเพี้ยน

**สองกับดักที่เคยทำให้เทสเขียวโดยไม่ได้ดูข้อมูลเลย — ปิดไว้ในนี้แล้วทั้งคู่**

1. ``st.cache_data`` อยู่ข้ามอินสแตนซ์ ``AppTest`` ในโปรเซสเดียวกัน ไม่ล้างก่อน
   เคสที่สองจะได้ข้อมูลของเคสแรก (เจอตอน readiness=True ให้ผลเท่ากับ readiness=False เป๊ะ)
2. ``proto.spec`` ย่อ ``y`` เป็น typed array base64 และ ``pio.from_json`` ก็ไม่ถอดให้
   เทสที่วนบน ``trace.y`` ตรง ๆ จึงวนบน "ชื่อคีย์สองตัว" แล้วผ่านฉลุย — ใช้ ``y_values()``
"""

import base64
import datetime
import importlib.util
import math
import os
import sqlite3
import tempfile
from pathlib import Path

import numpy as np
import plotly.io as pio

GARMIN_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PATH = GARMIN_ROOT / "scripts" / "dashboard.py"

MAIN_TABS_KEY = "main_tabs"
RECOVERY_TAB_LABEL = ":material/bedtime: การฟื้นตัว"
TRAINING_TAB_LABEL = ":material/directions_run: การซ้อม"

# วันสุดท้ายของข้อมูลที่ปั้น — ใช้วันจริงเพื่อให้ช่วงเวลาเริ่มต้นของหน้าครอบข้อมูลนี้
LAST_DAY = datetime.date.today()


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


def is_missing(value):
    """ช่องว่างบนเส้นกราฟมาถึงเทสในรูป ``None`` หรือ ``NaN`` แล้วแต่ชนิดคอลัมน์"""
    return value is None or (isinstance(value, float) and math.isnan(value))


def y_values(trace):
    """คืนค่าบนแกน y เป็นตัวเลขจริง แม้ถูกย่อเป็น typed array base64"""
    raw = trace.y
    if raw is None:
        return []
    if isinstance(raw, dict):
        return np.frombuffer(
            base64.b64decode(raw["bdata"]), dtype=raw["dtype"]
        ).tolist()
    return list(raw)


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


def render_tab(tab_label, seed):
    """คืน ``(tab, charts)`` ของแท็บที่ขอ หลังเรนเดอร์ dashboard จริงบน DB ที่ ``seed`` ปั้น

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
            app.session_state[MAIN_TABS_KEY] = tab_label
            app.run(timeout=90)
        finally:
            if previous is None:
                os.environ.pop("GARMIN_DATA_DIR", None)
            else:
                os.environ["GARMIN_DATA_DIR"] = previous

    if list(app.exception):
        raise AssertionError(
            f"แท็บ {tab_label!r} โยน exception: "
            + " | ".join(item.value for item in app.exception)
        )
    tab = next(item for item in app.get("tab") if item.label == tab_label)
    charts = [pio.from_json(el.proto.spec) for el in tab.get("plotly_chart")]
    return tab, charts
