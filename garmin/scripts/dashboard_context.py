"""ค่าที่หน้าเปลือกเตรียมไว้ให้ทุกหน้าใช้ร่วมกัน

``st.navigation`` รันสคริปต์หลักก่อนทุกหน้าเสมอ หน้าเปลือกจึงเป็นที่เดียวที่อ่าน
sidebar และดึงข้อมูลตามช่วงที่เลือก แล้ววางผลไว้ที่นี่ — หน้าแต่ละหน้าเป็นสคริปต์
คนละไฟล์ จึงส่งค่าให้กันผ่านตัวแปรธรรมดาไม่ได้ ต้องผ่าน ``st.session_state``
"""

from types import SimpleNamespace

import streamlit as st

CONTEXT_KEY = "_dashboard_context"
ATHLETE_STATE_KEY = "selected_athlete"  # ต้องตรงกับ key ของ selectbox ใน sidebar
TODAY_PAGE = "app_pages/today.py"


def set_page_context(**values):
    """หน้าเปลือกเรียกทุกรอบ ก่อน ``page.run()``"""
    st.session_state[CONTEXT_KEY] = SimpleNamespace(**values)


def page_context():
    """หน้าใดหน้าหนึ่งเรียกเพื่อรับค่าที่หน้าเปลือกเตรียมไว้

    ถ้าไม่มี แปลว่ามีคนเปิดไฟล์หน้าตรง ๆ แทนที่จะผ่าน ``dashboard.py`` —
    บอกให้ชัดดีกว่าปล่อยให้ NameError ที่บรรทัดไหนก็ไม่รู้
    """
    context = st.session_state.get(CONTEXT_KEY)
    if context is None:
        st.error("เปิดหน้านี้ตรง ๆ ไม่ได้ — ต้องเปิดผ่าน run_dashboard.bat (dashboard.py)")
        st.stop()
    return context


def focus_athlete(name):
    """ปุ่มบนการ์ดทีม: เลือกนักกีฬาคนนั้นแล้วพาไปหน้า "วันนี้" ในคลิกเดียว

    ตั้งแค่ชื่อจะเปลี่ยนคนแต่ค้างหน้าเดิม ตั้งแค่หน้าจะย้ายหน้าแต่ยังเป็นคนเดิม
    ทั้งสองอย่างอ่านเหมือนปุ่มเสียพอ ๆ กัน จึงต้องทำครบทั้งคู่ที่นี่ที่เดียว
    """
    st.session_state[ATHLETE_STATE_KEY] = name
    st.switch_page(TODAY_PAGE)
