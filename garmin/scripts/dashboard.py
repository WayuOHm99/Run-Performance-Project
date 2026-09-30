"""Run Performance Dashboard — หน้าเปลือกของแอป

**Garmin-only (30 ก.ย. 69):** ทุกตัวเลขบนจอคือค่าที่ Garmin ส่งมาตรง ๆ จัดรูปแบบ
แล้วเท่านั้น ไม่มีสูตร เกณฑ์ หรือคะแนนของระบบเอง ดู ``dashboard_domain.py``

หน้าเปลือกรันก่อนทุกหน้า: ตั้งค่าหน้า วาด sidebar (นักกีฬา + ช่วงวันที่) โหลดข้อมูล
ตามที่เลือก แล้วส่งให้หน้าที่เปิดอยู่ผ่าน ``set_page_context``
"""

import datetime
import time

import pandas as pd
import streamlit as st

from dashboard_context import honour_pending_page, set_page_context
from dashboard_data import (
    DATA_AVAILABILITY_GROUPS,
    db_path,
    load_activity_data,
    load_athlete_devices,
    load_athletes,
    load_data_availability,
    load_first_dashboard_date,
    load_latest_fetch,
    load_wellness_data,
)
from dashboard_domain import bangkok_date, summarize_metric_group, to_bangkok_timestamp

AUTO_REFRESH_SEC = 60

# เพดาน "สายเงียบเกินคาบ" (นาที) ของแต่ละสาย sync — health_report.py และ
# tests/test_fast_sync.py อ่านค่านี้ด้วย ast เพื่อยืนยันว่าตรงกับ $STALE_LIMIT_MIN
# ใน notify_sync.ps1 ครบทั้ง 6 สาย แก้ที่นี่ต้องแก้ที่นั่นด้วย
LANE_STALE_LIMIT_MIN = {
    "full": 900, "fast": 75, "wellness": 90,
    "reconcile": 12240, "deep": 44640, "backup": 1800,
}

st.set_page_config(
    page_title="Run Performance",
    page_icon=":material/directions_run:",
    layout="wide",
)

# CSS ที่เหลืออยู่มีแค่สองเรื่องที่ธีมทำให้ไม่ได้ ของที่เหลือใช้ component ของ Streamlit ตรง ๆ
# 1) ตัวเลขใน st.metric เป็นฟอนต์ mono ความกว้างเท่ากันทุกหลัก — codeFont ในธีมลงไม่ถึง
# 2) พิมพ์ A4 แนวนอน: ซ่อน sidebar/แถบเมนู/ปุ่ม และบังคับพิมพ์สีจริง
st.html("""
<style>
[data-testid="stMetricValue"] {
  font-family: 'IBM Plex Mono', 'IBM Plex Sans Thai', monospace;
  font-variant-numeric: tabular-nums;
}
@media print {
  [data-testid="stSidebar"], [data-testid="stHeader"], [data-testid="stToolbar"],
  [data-testid="stButton"], [data-testid="stDecoration"], header, footer { display: none !important; }
  * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
  [data-testid="stMetric"], [data-testid="stVerticalBlockBorderWrapper"] { break-inside: avoid; }
  @page { size: A4 landscape; margin: 8mm; }
}
</style>
""")


@st.fragment(run_every=AUTO_REFRESH_SEC)
def auto_refresh_dashboard():
    """รันทั้งแอปใหม่ทุก 60 วินาทีให้ตัวเลขสดอยู่เสมอไม่ว่าจะค้างหน้าไหน

    ไม่ล้าง cache เอง — loader ทุกตัวมี ttl 30 วิ ซึ่งสั้นกว่ารอบนี้อยู่แล้ว
    **ต้องเรียกนอกทุกเงื่อนไขท้ายไฟล์** เคยถูกเยื้องเข้าไปใต้แท็บเดียวแล้ว
    อีกห้าแท็บค้างข้อมูลเดิมเงียบ ๆ (c9f4b07)
    """
    now = time.monotonic()
    last_refresh = st.session_state.get("_dashboard_auto_refresh_at")
    if last_refresh is None:
        st.session_state["_dashboard_auto_refresh_at"] = now
        return
    if now - last_refresh >= AUTO_REFRESH_SEC:
        st.session_state["_dashboard_auto_refresh_at"] = now
        st.rerun(scope="app")


today = bangkok_date()

if not db_path().exists():
    st.error(f"ไม่พบฐานข้อมูลที่ {db_path()} — ต้องรัน sync ก่อน")
    st.stop()

athletes_df = load_athletes()
if athletes_df.empty:
    st.warning("ยังไม่มีนักกีฬาในฐานข้อมูล — เพิ่มด้วย garmin\\เพิ่มนักกีฬา.bat")
    st.stop()

PERIODS = {"7 วัน": 7, "30 วัน": 30, "90 วัน": 90, "ทั้งหมด": None, "กำหนดเอง": None}

with st.sidebar:
    st.markdown("### Run Performance")
    fetched = to_bangkok_timestamp(load_latest_fetch())
    st.caption(
        f"วันนี้ {today.strftime('%d/%m/%Y')} · ดึงจาก Garmin ล่าสุด "
        + (fetched.strftime("%d/%m %H:%M น.") if pd.notna(fetched) else "–")
    )
    if st.button("รีเฟรชข้อมูล", icon=":material/refresh:", width="stretch",
                 help="ข้อมูลรีเฟรชเองทุก 60 วินาที กดเมื่ออยากเห็นทันทีหลังนาฬิกา sync"):
        st.cache_data.clear()
        st.rerun()

    athlete_options = dict(zip(athletes_df["display_name"], athletes_df["athlete_id"]))
    selected_name = st.selectbox(
        "นักกีฬา", options=list(athlete_options), key="selected_athlete",
    )
    athlete_id = athlete_options[selected_name]
    selected_slug = athletes_df.loc[athletes_df["athlete_id"] == athlete_id, "slug"].iloc[0]

    period = st.segmented_control(
        "ช่วงวันที่", options=list(PERIODS), default="30 วัน", required=True,
        key="history_period", width="stretch",
    )
    if period == "ทั้งหมด":
        start_date, end_date = load_first_dashboard_date(athlete_id) or today, today
    elif period == "กำหนดเอง":
        picked = st.date_input(
            "เลือกช่วงวันที่", value=(today - datetime.timedelta(days=29), today),
            max_value=today, key="custom_history_range",
        )
        picked = picked if isinstance(picked, (tuple, list)) else (picked,)
        start_date, end_date = (picked[0], picked[-1]) if picked else (today, today)
    else:
        start_date, end_date = today - datetime.timedelta(days=PERIODS[period] - 1), today
    st.caption("หน้าทีมแสดงค่าล่าสุดเสมอ ไม่ขึ้นกับนักกีฬาหรือช่วงวันที่ที่เลือก")

    availability = load_data_availability(athlete_id, start_date.isoformat(), end_date.isoformat())
    with st.popover("ข้อมูลที่ Garmin ส่งมา", icon=":material/database:", width="stretch"):
        state_text = {
            "available": "มีครบในช่วงนี้", "partial": "มีบางค่า",
            "outside_range": "มีแต่นอกช่วงนี้", "never_received": "ยังไม่เคยได้รับ",
        }
        rows = []
        for group in DATA_AVAILABILITY_GROUPS:
            stats = availability[group["table"]]
            summary = summarize_metric_group(
                group["fields"],
                {field: stats[field]["history_count"] for field in group["fields"]},
                {field: stats[field]["selected_count"] for field in group["fields"]},
                {field: stats[field]["latest_date"] for field in group["fields"]},
            )
            rows.append({
                "ชุดข้อมูล": group["label"],
                "สถานะ": state_text[summary["state"]],
                "ช่องที่เคยได้รับ": f'{summary["history_available"]}/{summary["total_fields"]}',
                "ล่าสุด": summary["latest_date"].strftime("%d/%m/%Y")
                          if summary["latest_date"] else "–",
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        devices = load_athlete_devices(athlete_id)
        st.caption("นาฬิกาที่พบใน 90 วัน: " + (", ".join(devices) if devices else "ยังไม่มีข้อมูล")
                   + " · ช่องที่ยังไม่เคยได้รับ = Garmin ไม่ได้ส่งมา ไม่ใช่ระบบขัดข้อง")

wellness_df = load_wellness_data(athlete_id, start_date.isoformat(), end_date.isoformat())
activity_df = load_activity_data(athlete_id, start_date.isoformat(), end_date.isoformat())
if not activity_df.empty:
    activity_df["start_time_local"] = pd.to_datetime(activity_df["start_time_local"])

set_page_context(
    today=today,
    athletes_df=athletes_df,
    athlete_id=athlete_id,
    selected_name=selected_name,
    selected_slug=selected_slug,
    start_date=start_date,
    end_date=end_date,
    wellness_df=wellness_df,
    activity_df=activity_df,
)

# st.navigation รันเฉพาะไฟล์ของหน้าที่เปิดอยู่ หน้าอื่นไม่เสียเวลาสร้างกราฟ
page = st.navigation(
    [
        st.Page("app_pages/team.py", title="ทีม", icon=":material/groups:", default=True),
        st.Page("app_pages/body.py", title="ร่างกาย", icon=":material/favorite:"),
        st.Page("app_pages/training.py", title="การซ้อม", icon=":material/directions_run:"),
        st.Page("app_pages/estimates.py", title="ค่าประเมิน Garmin",
                icon=":material/insights:"),
        st.Page("app_pages/session.py", title="เซสชัน", icon=":material/timer:"),
        st.Page("app_pages/system.py", title="สถานะระบบ", icon=":material/monitor_heart:"),
    ],
    position="top",
)
# ปุ่มบนการ์ดทีมฝากคำขอย้ายหน้าไว้ — คอลแบ็กของปุ่มสั่งย้ายหน้าเองไม่ได้ (ดู dashboard_context)
honour_pending_page()
# ต้องลงทะเบียน *ก่อน* page.run() — หน้าที่ไม่มีข้อมูลเรียก st.stop() ซึ่งหยุดทั้งสคริปต์
# ถ้าอยู่หลังจากนั้น หน้าว่างจะไม่รีเฟรชเองอีกเลยแม้ข้อมูลเข้ามาแล้ว
auto_refresh_dashboard()
page.run()
