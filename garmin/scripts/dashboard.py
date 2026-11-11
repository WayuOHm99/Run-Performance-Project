"""Run Performance Dashboard — หน้าเปลือกของแอป

**Garmin-only (30 ก.ย. 69):** ทุกตัวเลขบนจอคือค่าที่ Garmin ส่งมาตรง ๆ จัดรูปแบบ
แล้วเท่านั้น ไม่มีสูตร เกณฑ์ หรือคะแนนของระบบเอง ดู ``dashboard_domain.py``

หน้าเปลือกรันก่อนทุกหน้า: ตั้งค่าหน้า วาด sidebar (นักกีฬา + ช่วงวันที่) โหลดข้อมูล
ตามที่เลือก แล้วส่งให้หน้าที่เปิดอยู่ผ่าน ``set_page_context``
"""

import datetime
import os

import pandas as pd
import streamlit as st
from dashboard_context import honour_pending_page, request_page, set_page_context
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
from dashboard_domain import (
    _to_datetime,
    bangkok_date,
    summarize_metric_group,
    to_bangkok_timestamp,
)
from dashboard_freshness import load_freshness
from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx

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

# CSS ระดับเปลือก:
# 1) ตัวเลขใน st.metric เป็นฟอนต์ mono ความกว้างเท่ากันทุกหลัก และข้อความประกอบไม่ถูกตัดท้าย "..."
# 2) พื้นหลังหน้าจอหลักโทนสว่างนุ่ม (#f8fafc) เพื่อให้การ์ดสีขาว (#ffffff) แยกชั้นชัดเจนโดยไม่กระทบสีขาวของตารางตอนสั่งพิมพ์
# 3) แถบเมนูบน การ์ดทีมความสูงเท่ากัน และการจัดหน้าสำหรับการพิมพ์ A4 แนวนอน
DASHBOARD_CSS = """
<style>
[data-testid="stMetricValue"] {
  font-family: 'IBM Plex Mono', 'IBM Plex Sans Thai', monospace;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  letter-spacing: -0.03em;
  color: #0b1220;
}
[data-testid="stMetricValue"] div {
  white-space: normal !important;
  overflow: visible !important;
  text-overflow: clip !important;
  line-height: 1.25 !important;
}
.rp-num {
  font-family: 'IBM Plex Mono', 'IBM Plex Sans Thai', monospace;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}
[data-testid="stMetricLabel"],
[data-testid="stMetricLabel"] div,
[data-testid="stMetricLabel"] p {
  color: #475467 !important;
  font-weight: 600 !important;
  font-size: 0.8rem !important;
  letter-spacing: 0.005em !important;
  white-space: normal !important;
  overflow: visible !important;
  text-overflow: clip !important;
  line-height: 1.35 !important;
}
[data-testid="stMetricDelta"],
[data-testid="stMetricDelta"] div,
[data-testid="stMetricDelta"] p {
  color: #667085 !important;
  background: transparent !important;
  padding-left: 0 !important;
  padding-right: 0 !important;
  font-size: 0.76rem !important;
  font-weight: 400 !important;
  white-space: normal !important;
  overflow: visible !important;
  text-overflow: clip !important;
  overflow-wrap: anywhere !important;
  line-height: 1.38 !important;
}
header[data-testid="stHeader"] {
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid #e4e7ec;
}
a[data-testid="stTopNavLink"] {
  border-radius: 0.5rem !important;
  padding: 0.38rem 0.82rem !important;
  font-weight: 500 !important;
  color: #475467 !important;
  transition: background-color 120ms ease, color 120ms ease;
}
a[data-testid="stTopNavLink"]:hover {
  background-color: #f2f4f7 !important;
  color: #0b1220 !important;
}
a[data-testid="stTopNavLink"][aria-current="page"],
a[data-testid="stTopNavLink"][aria-current="page"] * {
  background-color: #0b1220 !important;
  color: #ffffff !important;
  font-weight: 600 !important;
}
[data-testid="stMainBlockContainer"] {
  max-width: 1440px;
}
[data-testid="stMain"] h1 {
  letter-spacing: -0.02em;
  padding-bottom: 0.25rem;
}
.rp-page-lead {
  margin: -0.35rem 0 0.75rem;
  font-size: 0.86rem;
  color: #526075;
  line-height: 1.45;
}
.rp-sec-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 0.35rem 0.75rem;
  margin: 1.15rem 0 0.4rem;
  padding-bottom: 0.38rem;
  border-bottom: 1px solid #e4e7ec;
}
.rp-sec-title {
  font-size: 0.98rem;
  font-weight: 700;
  color: #0b1220;
  letter-spacing: -0.01em;
}
.rp-sec-sub {
  font-size: 0.79rem;
  color: #667085;
}
.rp-chart-head {
  margin-bottom: 0.35rem;
  padding-bottom: 0.45rem;
  border-bottom: 1px solid #f2f4f7;
}
.rp-chart-top {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 0.4rem;
}
.rp-chart-title {
  font-size: 0.95rem;
  font-weight: 700;
  color: #0b1220;
  letter-spacing: -0.01em;
}
.rp-chart-stat {
  font-size: 0.75rem;
  color: #344054;
  background: #f8f9fb;
  border: 1px solid #e4e7ec;
  border-radius: 0.38rem;
  padding: 0.1rem 0.5rem;
}
.rp-chart-guide {
  font-size: 0.79rem;
  color: #667085;
  margin-top: 0.16rem;
  line-height: 1.4;
}
.rp-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin: 0.15rem 0 0.3rem;
}
.rp-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.28rem;
  background: #f9fafb;
  border: 1px solid #e4e7ec;
  border-radius: 0.4rem;
  padding: 0.16rem 0.55rem;
  font-size: 0.76rem;
  color: #475467;
  line-height: 1.35;
}
.rp-chip strong {
  color: #0b1220;
  font-weight: 600;
}
.rp-chip-blue {
  background: #eff4ff;
  border-color: #d1e0ff;
  color: #155eef;
}
.rp-act-box {
  background: #f9fafb;
  border: 1px solid #eaecf0;
  border-radius: 0.55rem;
  padding: 0.5rem 0.7rem;
  margin-top: 0.15rem;
  max-height: 175px;
  overflow-y: auto;
}
.rp-act-item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.3rem 0.5rem;
  padding: 0.28rem 0;
  font-size: 0.8rem;
  color: #1d2939;
  border-bottom: 1px solid #eaecf0;
}
.rp-act-item:last-child {
  border-bottom: none;
  padding-bottom: 0;
}
.rp-act-item:first-child {
  padding-top: 0;
}
.rp-act-empty {
  font-size: 0.79rem;
  color: #667085;
  padding: 0.12rem 0;
}
.rp-warn-tag {
  background: #fffaeb;
  color: #b54708;
  border: 1px solid #fedf89;
  border-radius: 0.35rem;
  padding: 0.04rem 0.42rem;
  font-size: 0.72rem;
  font-weight: 600;
}
@media screen {
  section[data-testid="stMain"] {
    background-color: #f5f6f8;
  }
  [data-testid="stMain"] [data-testid="stMetric"],
  [class*="st-key-surface-"],
  [class*="st-key-team-card-"],
  [data-testid="stExpander"] {
    background-color: #ffffff;
    box-shadow: 0 1px 2px rgba(11, 18, 32, 0.04), 0 1px 3px rgba(11, 18, 32, 0.02);
  }
  [class*="st-key-sidebar-"] {
    background-color: #ffffff;
    box-shadow: 0 1px 2px rgba(11, 18, 32, 0.03);
  }
  [class*="st-key-surface-"] [data-testid="stMetric"] {
    background-color: #f9fafb !important;
    border: 1px solid #eaecf0 !important;
    border-radius: 0.55rem !important;
    padding: 0.65rem 0.85rem !important;
    box-shadow: none !important;
  }
  [class*="st-key-team-card-"] {
    transition: box-shadow 140ms ease, border-color 140ms ease;
  }
  [class*="st-key-team-card-"][class*="-complete_day"] {
    border-top: 2px solid #0d9488 !important;
  }
  [class*="st-key-team-card-"][class*="-partial_today"] {
    border-top: 2px solid #155eef !important;
  }
  [class*="st-key-team-card-"][class*="-no_data"] {
    border-top: 2px solid #d97706 !important;
  }
  [class*="st-key-team-card-"]:hover {
    border-color: #d0d5dd !important;
    box-shadow: 0 6px 16px rgba(11, 18, 32, 0.06), 0 1px 3px rgba(11, 18, 32, 0.03);
  }
  [class*="st-key-team-card-"] [data-testid="stMetric"] {
    background-color: #f9fafb;
    border: 1px solid #eaecf0;
    border-radius: 0.55rem;
    padding: 0.6rem 0.78rem;
    box-shadow: none;
  }
  [class*="st-key-team-card-"] [data-testid="stMetricValue"] {
    font-size: 1.34rem !important;
  }
  [class*="st-key-sys-kpi-err-active"] [data-testid="stMetric"] {
    border-left: 3px solid #dc2626 !important;
    background-color: #fef3f2 !important;
  }
  [class*="st-key-sys-kpi-warn-active"] [data-testid="stMetric"] {
    border-left: 3px solid #d97706 !important;
    background-color: #fffaeb !important;
  }
  [class*="st-key-sys-kpi-ok"] [data-testid="stMetric"] {
    border-left: 3px solid #0d9488 !important;
    background-color: #f9fafb !important;
  }
}
[data-testid="stHorizontalBlock"]:has([class*="st-key-team-card-"]) > [data-testid="stColumn"] > div,
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > [data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"]:only-child > [data-testid="stMetric"]),
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:only-child:has(> [data-testid="stMetric"]),
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:only-child > [data-testid="stMetric"] {
  height: 100%;
}
[class*="st-key-team-card-"] {
  height: 100%;
  display: flex;
  flex-direction: column;
}
[class*="st-key-open-athlete-"] {
  margin-top: auto;
  padding-top: 0.55rem;
  border-top: 1px solid #f2f4f7;
}
[class*="st-key-open-athlete-"] button {
  width: 100%;
  justify-content: space-between;
  font-weight: 600 !important;
  color: #0b1220 !important;
  background-color: #ffffff !important;
  border: 1px solid #d0d5dd !important;
  border-radius: 0.5rem !important;
  padding: 0.42rem 0.8rem !important;
  transition: background-color 120ms ease, border-color 120ms ease, color 120ms ease;
}
[class*="st-key-open-athlete-"] button:hover {
  background-color: #0b1220 !important;
  border-color: #0b1220 !important;
  color: #ffffff !important;
}
[class*="st-key-team-toolbar"],
[class*="st-key-sess-nav"] {
  background-color: #ffffff;
  border: 1px solid #e4e7ec;
  border-radius: 0.75rem;
  padding: 0.65rem 0.95rem;
  box-shadow: 0 1px 2px rgba(11, 18, 32, 0.03);
}
@media (max-width: 640px) {
  [data-testid="stMainBlockContainer"] {
    padding-left: 0.85rem !important;
    padding-right: 0.85rem !important;
  }
  [data-testid="stMain"] h1 {
    font-size: 1.35rem !important;
    line-height: 1.25 !important;
  }
  a[data-testid="stTopNavLink"] {
    padding: 0.3rem 0.6rem !important;
    font-size: 0.82rem !important;
  }
}
@media print {
  [data-testid="stSidebar"], [data-testid="stHeader"], [data-testid="stToolbar"],
  [data-testid="stButton"], [data-testid="stDecoration"], header, footer { display: none !important; }
  * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
  .rp-act-box { max-height: none !important; overflow: visible !important; }
  [data-testid="stMetric"], [class*="st-key-surface-"], [class*="st-key-team-card-"] { break-inside: avoid; }
  @page { size: A4 landscape; margin: 8mm; }
}
</style>
"""
st.html(DASHBOARD_CSS)

demo_mode = os.environ.get("GARMIN_DASHBOARD_DEMO") == "1"
if demo_mode:
    st.info("โหมด Demo · ทุกชื่อและตัวเลขเป็นข้อมูลจำลอง ไม่ได้เชื่อมบัญชี Garmin · "
            "ลองเลือกนักกีฬา เปลี่ยนวันที่ และเปิดทั้ง 6 หน้าได้ ข้อมูลทดลองถูกลบเมื่อปิด Demo ตามปกติ",
            icon=":material/science:")


@st.fragment(run_every=AUTO_REFRESH_SEC)
def auto_refresh_dashboard():
    """รันทั้งแอปใหม่ทุก 60 วินาทีให้ตัวเลขสดอยู่เสมอไม่ว่าจะค้างหน้าไหน

    ไม่ล้าง cache เอง — loader ทุกตัวมี ttl 30 วิ ซึ่งสั้นกว่ารอบนี้อยู่แล้ว
    สั่ง rerun เฉพาะตอนที่ถูกปลุกจากรอบ fragment timer (`fragment_ids_this_run`)
    เพื่อไม่ให้คลิกของผู้ใช้หลังครบ 60 วิเกิด double-rerun และไม่ข้ามรอบเพราะ jitter มิลลิวินาที
    **ต้องเรียกนอกทุกเงื่อนไขท้ายไฟล์** เคยถูกเยื้องเข้าไปใต้แท็บเดียวแล้ว
    อีกห้าแท็บค้างข้อมูลเดิมเงียบ ๆ (c9f4b07)
    """
    ctx = get_script_run_ctx()
    if ctx is not None and ctx.fragment_ids_this_run:
        st.rerun(scope="app")


today = bangkok_date()

if not db_path().exists():
    st.error(f"ไม่พบฐานข้อมูลที่ {db_path()} — ต้องรัน sync ก่อน")
    st.info("ลองหน้าจอโดยไม่ใช้บัญชี Garmin: จากโฟลเดอร์ garmin รันคำสั่งด้านล่าง")
    st.code("uv run --frozen python scripts/run_demo.py", language="bash")
    st.stop()

athletes_df = load_athletes()
if athletes_df.empty:
    st.warning("ยังไม่มีนักกีฬาในฐานข้อมูล — เพิ่มด้วย garmin\\เพิ่มนักกีฬา.bat")
    st.code("uv run --frozen python scripts/run_demo.py", language="bash")
    st.stop()

PERIODS = {"7 วัน": 7, "30 วัน": 30, "90 วัน": 90, "ทั้งหมด": None, "กำหนดเอง": None}

# ลงทะเบียน st.navigation ก่อนวาด sidebar เพื่อให้ sidebar รู้ว่าผู้ใช้อยู่หน้าไหน
# แล้วแสดงคำแนะนำ/ปุ่มลัดได้ตรงกับบริบทหน้าปัจจุบัน (st.navigation รันไฟล์เฉพาะตอน page.run())
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
team_wide_page = page.title in ("ทีม", "สถานะระบบ")

with st.sidebar:
    with st.container(border=True, key="sidebar-brand"):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown("### Run Performance")
            st.badge("Demo" if demo_mode else "Garmin",
                     icon=":material/science:" if demo_mode else ":material/watch:",
                     color="orange" if demo_mode else "blue")
        fetched = to_bangkok_timestamp(load_latest_fetch())
        st.caption(
            f"วันนี้ {today.strftime('%d/%m/%Y')} · "
            + ("ข้อมูลจำลองทั้งทีม " if demo_mode else "ซิงก์ล่าสุด ")
            + (fetched.strftime("%d/%m %H:%M น.") if pd.notna(fetched) else "–")
        )
        if st.button("รีเฟรชข้อมูลทันที", icon=":material/refresh:", width="stretch",
                     help="หน้ารีเฟรชเองทุก 60 วินาที กดปุ่มนี้เมื่อเพิ่งซิงก์นาฬิกาเสร็จแล้วอยากเห็นทันที"):
            st.cache_data.clear()
            st.rerun()

    athlete_options = {int(row["athlete_id"]): row for row in athletes_df.to_dict("records")}
    duplicate_names = set(athletes_df.loc[
        athletes_df["display_name"].duplicated(keep=False), "display_name",
    ])
    athlete_labels = {
        aid: f'{row["display_name"]} ({row["slug"]})'
             if row["display_name"] in duplicate_names else row["display_name"]
        for aid, row in athlete_options.items()
    }
    # session เดิมใช้ชื่อเป็นค่า widget; รักษาคนที่เลือกไว้เมื่อเปลี่ยนมาใช้ ID
    previous_athlete = st.session_state.get("selected_athlete")
    if isinstance(previous_athlete, str):
        matches = [aid for aid, row in athlete_options.items()
                   if row["display_name"] == previous_athlete]
        if matches:
            st.session_state["selected_athlete"] = matches[-1]
        else:
            st.session_state.pop("selected_athlete", None)
    elif previous_athlete is not None and previous_athlete not in athlete_options:
        st.session_state.pop("selected_athlete", None)

    with st.container(border=True, key="sidebar-filters"):
        st.markdown("**เลือกนักกีฬาและช่วงเวลา**")
        athlete_id = st.selectbox(
            "นักกีฬา", options=list(athlete_options),
            format_func=athlete_labels.__getitem__, key="selected_athlete",
        )
        selected_name = athlete_labels[athlete_id]
        selected_slug = athlete_options[athlete_id]["slug"]

        period = st.segmented_control(
            "ช่วงวันที่", options=list(PERIODS), default="30 วัน", required=True,
            key="history_period", width="stretch",
        )
        if period == "ทั้งหมด":
            start_date, end_date = load_first_dashboard_date(athlete_id) or today, today
        elif period == "กำหนดเอง":
            existing_range = st.session_state.get("custom_history_range")
            if isinstance(existing_range, (tuple, list)):
                clamped = tuple(min(today, d) for d in existing_range if isinstance(d, datetime.date))
                if clamped:
                    st.session_state["custom_history_range"] = clamped
            elif isinstance(existing_range, datetime.date) and existing_range > today:
                st.session_state["custom_history_range"] = today
            picked = st.date_input(
                "เลือกช่วงวันที่", value=(today - datetime.timedelta(days=29), today),
                max_value=today, key="custom_history_range",
            )
            picked = picked if isinstance(picked, (tuple, list)) else (picked,)
            start_date, end_date = (picked[0], picked[-1]) if picked else (today, today)
        else:
            start_date, end_date = today - datetime.timedelta(days=PERIODS[period] - 1), today

        span_days = max(1, (end_date - start_date).days + 1)
        st.caption(f"{start_date:%d/%m/%Y} – {end_date:%d/%m/%Y} ({span_days} วัน)")
        if team_wide_page:
            st.button(
                f"เปิดหน้ารายคนของ {selected_name}",
                icon=":material/arrow_forward:",
                key="sidebar-open-selected",
                on_click=request_page,
                args=("app_pages/body.py",),
                width="stretch",
            )

    freshness = load_freshness(athlete_id, start_date, end_date, today)
    with st.container(border=True, key="sidebar-freshness"):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(f"**{selected_name}**")
            if not freshness["has_history"]:
                st.badge("ยังไม่มีประวัติ", color="gray", icon=":material/hourglass_empty:")
            elif freshness["gaps"]:
                st.badge(f"ว่าง {len(freshness['gaps'])} วัน", color="orange", icon=":material/event_busy:")
            else:
                st.badge("ข้อมูลต่อเนื่อง", color="green", icon=":material/check_circle:")
        st.caption(f"สุขภาพล่าสุด {freshness['latest_text']} · ดึงล่าสุด {freshness['received_at']}")
        if freshness["gaps"]:
            st.caption(f"วันไม่มีข้อมูลสุขภาพในช่วงที่เลือก: {len(freshness['gaps'])} วัน · "
                       "ดูวันที่และขั้นตอนตรวจในหน้าสถานะระบบ")
        elif not freshness["has_history"]:
            st.caption("ยังไม่มีข้อมูลสุขภาพรายวัน · ดูขั้นตอนเริ่มต้นในหน้าสถานะระบบ")

        availability = load_data_availability(athlete_id, start_date.isoformat(), end_date.isoformat())
        with st.popover("ข้อมูลที่ Garmin ส่งมา", icon=":material/database:", width="stretch"):
            state_text = {
                "available": "ได้รับครบทุกช่องอย่างน้อยหนึ่งครั้งในช่วงนี้",
                "partial": "ได้รับบางช่องในช่วงนี้",
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

    if page.title == "ทีม":
        st.caption(":material/info: หน้าทีมเลือกวันที่แยกบนตัวหน้าเองเพื่อดูทั้งทีมพร้อมกัน")

wellness_df = load_wellness_data(athlete_id, start_date.isoformat(), end_date.isoformat())
activity_df = load_activity_data(athlete_id, start_date.isoformat(), end_date.isoformat())
if not activity_df.empty:
    activity_df["start_time_local"] = _to_datetime(activity_df["start_time_local"])

set_page_context(
    demo_mode=demo_mode,
    today=today,
    athletes_df=athletes_df,
    athlete_labels=athlete_labels,
    athlete_id=athlete_id,
    selected_name=selected_name,
    selected_slug=selected_slug,
    start_date=start_date,
    end_date=end_date,
    wellness_df=wellness_df,
    activity_df=activity_df,
)

# ปุ่มบนการ์ดทีมฝากคำขอย้ายหน้าไว้ — คอลแบ็กของปุ่มสั่งย้ายหน้าเองไม่ได้ (ดู dashboard_context)
honour_pending_page()
# ต้องลงทะเบียน *ก่อน* page.run() — หน้าที่ไม่มีข้อมูลเรียก st.stop() ซึ่งหยุดทั้งสคริปต์
# ถ้าอยู่หลังจากนั้น หน้าว่างจะไม่รีเฟรชเองอีกเลยแม้ข้อมูลเข้ามาแล้ว
auto_refresh_dashboard()
page.run()
