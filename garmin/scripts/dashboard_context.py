"""ค่าที่หน้าเปลือกเตรียมไว้ให้ทุกหน้าใช้ร่วมกัน

``st.navigation`` รันสคริปต์หลักก่อนทุกหน้าเสมอ หน้าเปลือกจึงเป็นที่เดียวที่อ่าน
sidebar และดึงข้อมูลตามช่วงที่เลือก แล้ววางผลไว้ที่นี่ — หน้าแต่ละหน้าเป็นสคริปต์
คนละไฟล์ จึงส่งค่าให้กันผ่านตัวแปรธรรมดาไม่ได้ ต้องผ่าน ``st.session_state``
"""

import html
from types import SimpleNamespace

import streamlit as st

CONTEXT_KEY = "_dashboard_context"
ATHLETE_STATE_KEY = "selected_athlete"  # ต้องตรงกับ key ของ selectbox ใน sidebar
ATHLETE_PAGE = "app_pages/body.py"
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


def focus_athlete(athlete_id):
    """ปุ่มบนการ์ดทีม: เลือกนักกีฬาคนนั้นแล้วพาไปหน้า "ร่างกาย" ของคนนั้นในคลิกเดียว

    ตั้งแค่ ID จะเปลี่ยนคนแต่ค้างหน้าเดิม ตั้งแค่หน้าจะย้ายหน้าแต่ยังเป็นคนเดิม
    ทั้งสองอย่างอ่านเหมือนปุ่มเสียพอ ๆ กัน จึงต้องทำครบทั้งคู่

    **เรียก ``st.switch_page()`` ตรงนี้ไม่ได้** — ซอร์สของมันจบด้วย ``st.empty()``
    เพื่อบังคับให้ ScriptRunner ยอมสลับหน้า ซึ่งได้ผลเฉพาะตอน *สคริปต์กำลังรัน*
    คอลแบ็กของปุ่มทำงานก่อนหน้านั้น ผลคือค่าถูกเขียนลง session_state สำเร็จ
    แต่หน้าไม่ย้าย และไม่มี error ให้เห็นเลย (จับได้ด้วย CDP ในเบราว์เซอร์จริง
    เท่านั้น — ทั้งเทสและ AppTest มองไม่เห็น) จึงฝากคำขอไว้ให้หน้าเปลือกทำแทน
    """
    st.session_state[ATHLETE_STATE_KEY] = athlete_id
    st.session_state[PENDING_PAGE_KEY] = ATHLETE_PAGE


def request_page(page_path: str):
    """ฝากคำขอย้ายหน้าจาก callback ของปุ่ม ให้ ``honour_pending_page()`` สลับหน้าจริงรอบถัดไป"""
    st.session_state[PENDING_PAGE_KEY] = page_path


def _esc(text: str) -> str:
    return html.escape(str(text), quote=False)


def page_lead(text: str):
    """คำอธิบายสั้นใต้หัวเรื่องหลัก บอกขอบเขตและช่วงเวลาของหน้าในบรรทัดเดียว"""
    st.markdown(f'<p class="rp-page-lead">{_esc(text)}</p>', unsafe_allow_html=True)


def section_heading(title: str, subtitle: str | None = None):
    """หัวข้อหมวดหมู่สไตล์ Editorial แยกกลุ่มข้อมูลชัดเจนโดยไม่ใช้สัญลักษณ์รกสายตา"""
    sub_html = f'<span class="rp-sec-sub">{_esc(subtitle)}</span>' if subtitle else ""
    st.markdown(
        f'<div class="rp-sec-head"><span class="rp-sec-title">{_esc(title)}</span>{sub_html}</div>',
        unsafe_allow_html=True,
    )


def chart_header(holder, title: str, guide: str | None = None, stat: str | None = None):
    """หัวการ์ดกราฟมาตรฐาน: ชื่อเรื่อง + ค่าสรุปดิบมุมขวา + คำอธิบายวิธีอ่าน 1 บรรทัด"""
    stat_html = f'<span class="rp-chart-stat rp-num">{_esc(stat)}</span>' if stat else ""
    guide_html = f'<div class="rp-chart-guide">{_esc(guide)}</div>' if guide else ""
    holder.markdown(
        f'<div class="rp-chart-head">'
        f'<div class="rp-chart-top"><span class="rp-chart-title">{_esc(title)}</span>{stat_html}</div>'
        f'{guide_html}</div>',
        unsafe_allow_html=True,
    )


def render_metric_grid(items, *, cols_per_row: int = 4, border: bool = True, holder=None):
    """วาง st.metric บนกริดความกว้างคงที่ ป้องกันการ์ดใบเดียวถูกยืดเต็มจอ 100%"""
    target = holder if holder is not None else st
    for row_idx in range(0, len(items), cols_per_row):
        chunk = items[row_idx:row_idx + cols_per_row]
        cols = target.columns(cols_per_row, gap="small")
        for col, item in zip(cols, chunk, strict=False):
            label, val_text = item[0], item[1]
            note_text = item[2] if len(item) > 2 else None
            help_text = item[3] if len(item) > 3 else None
            with col:
                st.metric(
                    label, val_text, note_text,
                    delta_color="off", delta_arrow="off",
                    border=border, width="stretch", help=help_text,
                )


def honour_pending_page():
    """หน้าเปลือกเรียกหลัง ``st.navigation()`` และก่อน ``page.run()``

    ต้องอยู่หลัง ``st.navigation`` เพราะ ``switch_page`` ตรวจว่าหน้าปลายทาง
    ลงทะเบียนไว้แล้วหรือยัง — เรียกก่อนหน้านั้นจะได้ StreamlitAPIException
    """
    pending = st.session_state.pop(PENDING_PAGE_KEY, None)
    if pending:
        st.switch_page(pending)
