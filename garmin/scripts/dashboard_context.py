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
PENDING_PAGE_KEY = "_dashboard_pending_page"


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
    ทั้งสองอย่างอ่านเหมือนปุ่มเสียพอ ๆ กัน จึงต้องทำครบทั้งคู่

    **เรียก ``st.switch_page()`` ตรงนี้ไม่ได้** — ซอร์สของมันจบด้วย ``st.empty()``
    เพื่อบังคับให้ ScriptRunner ยอมสลับหน้า ซึ่งได้ผลเฉพาะตอน *สคริปต์กำลังรัน*
    คอลแบ็กของปุ่มทำงานก่อนหน้านั้น ผลคือค่าถูกเขียนลง session_state สำเร็จ
    แต่หน้าไม่ย้าย และไม่มี error ให้เห็นเลย (จับได้ด้วย CDP ในเบราว์เซอร์จริง
    เท่านั้น — ทั้งเทสและ AppTest มองไม่เห็น) จึงฝากคำขอไว้ให้หน้าเปลือกทำแทน
    """
    st.session_state[ATHLETE_STATE_KEY] = name
    st.session_state[PENDING_PAGE_KEY] = TODAY_PAGE


def honour_pending_page():
    """หน้าเปลือกเรียกหลัง ``st.navigation()`` และก่อน ``page.run()``

    ต้องอยู่หลัง ``st.navigation`` เพราะ ``switch_page`` ตรวจว่าหน้าปลายทาง
    ลงทะเบียนไว้แล้วหรือยัง — เรียกก่อนหน้านั้นจะได้ StreamlitAPIException
    """
    pending = st.session_state.pop(PENDING_PAGE_KEY, None)
    if pending:
        st.switch_page(pending)
