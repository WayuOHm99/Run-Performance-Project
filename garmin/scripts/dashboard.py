import datetime
import html
import math
import os
import sqlite3
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st
from plotly.subplots import make_subplots

# โมดูลของ dashboard เอง — ต้อง import ก่อนบรรทัดแรกที่ใช้ค่าจากมัน
# (เคยวางไว้กลางไฟล์แล้ว NameError ตอนบูตจริง แม้ py_compile จะเขียว)
# helper บริสุทธิ์ย้ายไป dashboard_domain.py / dashboard_view.py แล้ว
# ที่นี่เหลือเฉพาะของที่เรียก st. จริง: loader ที่ติด cache และสคริปต์วาดหน้า
from dashboard_domain import (
    HRV_ALERT,
    HRV_TREND_LOOKBACK_DAYS,
    READINESS_ALERT,
    SLEEP_LOW,
    EASY_MAX_PCT,
    EF_BASELINE_DAYS,
    EF_BASELINE_MIN_DAYS,
    EF_MIN_DISTANCE_M,
    EF_RECENT_DAYS,
    EF_STALE_DAYS,
    GRAY_MAX_PCT,
    HRV_TREND_BASELINE_DAYS,
    HRV_TREND_CURRENT_DAYS,
    HRV_TREND_MIN_BASELINE_DAYS,
    HRV_TREND_MIN_CURRENT_DAYS,
    HRV_TREND_STALE_DAYS,
    INTENSITY_ORDER,
    LTHR_BY_SLUG,
    LTHR_SOURCE_BY_SLUG,
    PACE_TICK_MAX,
    PACE_TICK_STEPS_MIN,
    STATUS_SHAPES,
    TEAM_URGENCY_ORDER,
    _num_text,
    _pace_ticks_at,
    aggregate_pace_min_per_km,
    analyze_distance_halves,
    available_series,
    bangkok_date,
    baseline_median,
    body_battery_snapshots,
    calendar_aligned_frame,
    chart_title,
    classify_intensity,
    compute_load_windows,
    device_inventory_labels,
    easy_run_efficiency,
    easy_share_pct,
    efficiency_change_pct,
    efficiency_display,
    efficiency_factor,
    efficiency_recent_value,
    efficiency_status,
    efficiency_windows,
    field_age_days,
    field_freshness,
    fmt_num,
    fmt_pace,
    fmt_recovery_time,
    fmt_sec,
    fmt_signed_delta,
    fmt_text,
    get_lthr,
    get_recovery_minutes,
    has_any_value,
    hr_zone_coverage,
    hrv_trend_pct,
    hrv_trend_status,
    hrv_trend_summary,
    intensity_minutes,
    latest_field,
    load_context_line,
    load_session_scope,
    load_volume_display,
    pace_axis_ticks,
    period_metric,
    personal_record_label,
    personal_record_rows,
    prepare_session_candidates,
    readiness_when,
    recovery_minutes_series,
    status_parts,
    summarize_metric_group,
    team_status,
    team_urgency_rank,
    tile_note,
    to_bangkok_timestamp,
    usable_hr_zone_rows,
    wellness_quality_flags,
)
from dashboard_view import (
    BLUE_RAMP_3,
    BLUE_RAMP_5,
    C_NEUTRAL,
    C_SECOND,
    INTENSITY_COLORS,
    SERIES_COLORS,
    NUMBER_FONT_CSS,
    TEAM_CARD_CSS,
    TODAY_PANEL_CSS,
    C_BLUE,
    C_CONTEXT,
    C_CRIT,
    C_GOOD,
    C_WARN,
    INTENSITY_CHIP_COLORS,
    STATUS_COLORS,
    STATUS_TEXT_COLORS,
    TREND_KEY_BY_LABEL,
    css_key,
    mark_partial_today,
    render_load_strip,
    render_session_row,
    render_team_card,
    render_today_tile,
    render_today_verdict,
    session_intensity_chip,
    sparkline_svg,
    status_shape_svg,
)
# ชั้นข้อมูลย้ายไป dashboard_data.py แล้ว — หน้าแต่ละหน้าต้องเรียก loader ตัวเดียวกัน
# (แคชของ Streamlit ผูกกับตัวฟังก์ชัน สำเนาต่อหน้าจะได้แคชคนละก้อน)
from dashboard_context import set_page_context
from dashboard_data import (
    load_daily_workload,
    DATA_AVAILABILITY_GROUPS,
    data_dir,
    db_path,
    LOAD_CURRENCY_SAMPLE,
    PROJECT_ROOT,
    RUN_TYPES,
    _ACTIVITY_TEXT,
    _WELLNESS_TEXT,
    athlete_has_load,
    athlete_has_training_readiness,
    athlete_load_is_current,
    connect_db,
    load_activity_data,
    load_athlete_devices,
    load_athletes,
    load_body_composition,
    load_daily_load,
    load_daily_run_km,
    load_data_availability,
    load_easy_runs,
    load_first_dashboard_date,
    load_first_load_date,
    load_first_run_date,
    load_last_data_dates,
    load_latest_lt,
    load_personal_records,
    load_race_predictions,
    load_splits,
    load_wellness_data,
)

# --- PRODUCT POLICY (อนุมัติ 27 ส.ค. 69) ---
# Garmin-only dashboard: filters/navigation are allowed, but the app must not collect manual
# pain/illness/fatigue/RPE data, create a custom composite freshness score, or automatically
# prescribe rest/load changes. A verbal symptom check remains outside the dashboard.

# --- CONFIGURATION ---
st.set_page_config(page_title="Run Performance Dashboard", page_icon="🏃‍♂️", layout="wide")

# --- PRINT CSS ---
# แดชบอร์ดตั้งเป็นธีม "สว่าง" ถาวรแล้ว (ดู .streamlit/config.toml) — พื้นขาว/ตัวเข้ม
# ทั้งกราฟ Plotly และตาราง st.dataframe (canvas) จึงพิมพ์สะอาดโดยไม่ต้องบังคับสีทับ
# บล็อกนี้เหลือหน้าที่: ซ่อน UI chrome, รักษาสัดส่วนแบบ desktop ตอนลง A4,
# กันตัดกลางหน้า และบังคับพิมพ์สีจริงให้กราฟ/สถานะ/ขอบการ์ดออกสีครบ
st.markdown("""
<style>
@media print {
    :root {
        /*
         * A4 landscape (ขอบ 8 mm) กว้างประมาณ 1,062 CSS px
         * วาง dashboard บน canvas 1,280 px แล้ว scale เหลือ 82%
         * เพื่อรักษาสัดส่วนเดียวกับหน้าเว็บแทนการบีบ layout ให้เหลือ 100% ของกระดาษ
         */
        --print-canvas-width: 1280px;
        --print-scale: 0.82;
    }

    /* ===== ซ่อน UI chrome และ navigation ที่ไม่จำเป็นบนกระดาษ ===== */
    [data-testid="stSidebar"],
    [data-testid="stHeader"],
    [data-testid="stToolbar"],
    [data-testid="stTabs"] [role="tablist"],
    header, footer,
    .stDeployButton,
    button[kind="header"],
    [data-testid="stStatusWidget"],
    [data-testid="stDecoration"],
    .stApp > header {
        display: none !important;
    }

    /* ===== บังคับพิมพ์ "สีจริง" ทุก element — กันเบราว์เซอร์ตัด/จางสีพื้นและสี SVG ===== */
    * {
        -webkit-print-color-adjust: exact !important;
        print-color-adjust: exact !important;
    }

    /* ===== ปล่อยโครงหน้าหลักให้ต่อหลายหน้าได้โดยไม่ตัด overflow ===== */
    html, body,
    [data-testid="stAppViewContainer"],
    section[data-testid="stMain"],
    .main,
    .stApp {
        width: 100% !important;
        max-width: none !important;
        padding: 0 !important;
        margin: 0 !important;
        overflow: visible !important;
        background: #ffffff !important;
    }

    /*
     * คง canvas ระดับ desktop แล้ว scale ทั้งก้อนลง A4
     * การ์ด KPI จึงไม่เปลี่ยนสัดส่วนหรือ wrap ต่างจากตอนดูบนเว็บ
     */
    .block-container,
    [data-testid="stMainBlockContainer"] {
        box-sizing: border-box !important;
        width: var(--print-canvas-width) !important;
        max-width: var(--print-canvas-width) !important;
        padding: 0.75rem 1.25rem 1rem !important;
        margin: 0 auto !important;
        zoom: var(--print-scale);
        overflow: visible !important;
    }

    /* Firefox รุ่นเก่าที่ไม่รองรับ zoom: ให้ย่อ typography แทนและไม่ปล่อยล้นกระดาษ */
    @supports not (zoom: 1) {
        .block-container,
        [data-testid="stMainBlockContainer"] {
            width: 100% !important;
            max-width: 100% !important;
            font-size: 82% !important;
        }
    }

    /* ===== ป้องกันของเล็กถูกหั่นกลาง โดยไม่ล็อก container ใหญ่ทั้ง section ===== */
    /* ห้าม avoid บน stVerticalBlock / stHorizontalBlock เพราะมันรวม section ทั้งยวง
       → ลงหน้าไม่หมด browser ดันทั้งก้อนไปหน้าถัดไป = ช่องว่างมหึมา */
    [data-testid="stMetric"],
    [data-testid="stMetric"] > div,
    [data-testid="stAlert"] {
        break-inside: avoid !important;
        page-break-inside: avoid !important;
    }

    h1, h2, h3 {
        break-after: avoid-page !important;
        page-break-after: avoid !important;
    }

    p, li {
        orphans: 3;
        widows: 3;
    }

    /* ปุ่มบนกระดาษกดไม่ได้ — พิมพ์ออกมาเป็นกล่องเทาที่ไม่ได้ทำอะไร กินที่เปล่า ๆ
       (ตั้งแต่มีปุ่ม "ดูรายละเอียดของ X" ใต้การ์ดทุกใบบนแท็บทีม) */
    [data-testid="stButton"] {
        display: none !important;
    }

    /* รักษาแถว KPI เป็นหนึ่งชุด และย้ายกราฟทั้งก้อนไปหน้าใหม่เมื่อพื้นที่ไม่พอ */
    [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]),
    .stPlotlyChart,
    .js-plotly-plot {
        break-inside: avoid-page !important;
        page-break-inside: avoid !important;
    }

    /* table/expander ยาวสามารถต่อข้ามหน้าได้ ป้องกันหน้าว่างขนาดใหญ่ */
    [data-testid="stDataFrame"],
    [data-testid="stTable"],
    [data-testid="stExpander"] {
        overflow: visible !important;
    }

    /* ===== พิมพ์เฉพาะแท็บที่เปิดอยู่ ===== */
    [data-testid="stTabs"] [role="tabpanel"][aria-hidden="true"] {
        display: none !important;
    }
    [data-testid="stTabs"] [role="tabpanel"]:not([aria-hidden="true"]) {
        display: block !important;
        overflow: visible !important;
    }

    /* รักษาความกว้างกราฟ/สื่อ แต่ไม่บังคับความสูงใหม่จนสัดส่วนเพี้ยน */
    .stPlotlyChart,
    .js-plotly-plot,
    .plot-container,
    .svg-container,
    iframe {
        width: 100% !important;
        max-width: 100% !important;
    }

    /* ===== ตั้งค่าหน้ากระดาษ ===== */
    @page {
        size: A4 landscape;
        margin: 8mm;
    }
}
</style>
""", unsafe_allow_html=True)

st.markdown(NUMBER_FONT_CSS, unsafe_allow_html=True)

# --- LAYOUT TWEAK (จอปกติ): ดันเนื้อหา sidebar ขึ้นให้ชิดบนเหมาะสม + ลดช่องว่างบนหน้าหลัก ---
st.markdown("""
<style>
  [data-testid="stSidebarUserContent"] { padding-top: 1.5rem !important; }
  section[data-testid="stMain"] .block-container { padding-top: 2.5rem !important; }
</style>
""", unsafe_allow_html=True)












# --- PLOTLY DEFAULT TEMPLATE ---
# ธีมสว่าง: พื้น transparent (โชว์พื้นขาวของหน้า) + ฟอนต์สีเข้ม อ่านได้ทั้งบนจอและตอนพิมพ์
# ต้องอยู่หลังค่าคงที่สี เพราะ colorway ใช้ token เดียวกับที่กราฟใช้ — ระบบดีไซน์อยู่ที่นี่
# ที่เดียว กราฟไหนไม่ได้ตั้งสีเองจะได้ลำดับนี้แทนสีเริ่มต้นสิบสีของ plotly
_print_friendly = pio.templates["plotly"]
_print_friendly.layout.paper_bgcolor = "rgba(0,0,0,0)"
_print_friendly.layout.plot_bgcolor = "rgba(0,0,0,0)"
_print_friendly.layout.font = dict(
    color="#31333F",  # เทาเข้ม (ตรงกับ text ธีม light ของ Streamlit)
    family="'IBM Plex Sans Thai', 'IBM Plex Sans', sans-serif",
)
_print_friendly.layout.colorway = [C_BLUE, C_SECOND, "#104281", "#86b6ef", C_CONTEXT]
# `colorway` คุมเฉพาะเส้น/แท่งที่แยกกันเป็นชุด — กราฟที่ระบายสีตาม *ค่าต่อเนื่อง*
# (เช่น จุดที่ระบายตาม HR) อ่านจาก `colorscale` คนละตัวกัน ไม่ตั้งไว้มันจะตกไปใช้
# Plasma ของ plotly คือรุ้งม่วง→ส้ม→เหลือง ซึ่งขัดกฎ 02 (ค่ามีลำดับใช้สีเดียวไล่เฉด)
# และหยิบสีที่กฎ 03 จองไว้ให้สถานะไปใช้กับข้อมูลธรรมดา
_print_friendly.layout.colorscale.sequential = BLUE_RAMP_5
_print_friendly.layout.colorscale.sequentialminus = BLUE_RAMP_5
for _axis in (_print_friendly.layout.xaxis, _print_friendly.layout.yaxis):
    _axis.gridcolor = "#e4e1da"   # เท่ากับ borderColor ใน .streamlit/config.toml
    _axis.linecolor = "#e4e1da"
    _axis.zerolinecolor = "#e4e1da"
pio.templates.default = _print_friendly










































































































# --- แท็บ "วันนี้": สรุปสัญญาณ ไทล์ค่าเดี่ยว แถบโหลด และแถวเซสชัน ---
# หน้าเรียงจากสัญญาณที่ต้องคุยต่อ → ค่าจากอุปกรณ์ → บริบทโหลด → เซสชันจริง


# คีย์ของ selectbox นักกีฬา — ปุ่มบนการ์ดทีมเขียนค่าลงคีย์นี้เพื่อสลับคนที่กำลังดู
ATHLETE_STATE_KEY = "selected_athlete"









































# --- DB LOADERS ---
# แคชสั้นกว่ารอบ sync ที่ถี่ที่สุด (fast activity 15 นาที / fast wellness 30 นาที) ไม่งั้น
# ข้อมูลลง DB แล้วแต่หน้าจอยังค้างของเก่าโดยไม่มีเหตุผล
#
# ต้อง **สั้นกว่า `AUTO_REFRESH_SEC`** ไม่งั้นรอบรีเฟรชอัตโนมัติจะหยิบค่าเดิมจาก cache
# มาแสดงซ้ำ = หน้าจอดูเหมือนรีเฟรชแล้วแต่ตัวเลขไม่ขยับ ซึ่งหลอกตากว่าไม่รีเฟรชเลย
# วัดแล้ว 26 ส.ค. 69: cache miss หนึ่งครั้งราคา 0.23 วิ (cold 1.175 vs warm 0.945)
# ถูกพอที่จะเลือกความสดมากกว่าประหยัด query
CACHE_TTL_SEC = 30
AUTO_REFRESH_SEC = 60
# เพดานสายงาน sync ใช้ตรวจความสอดคล้องกับ watchdog/health report หลังบ้านเท่านั้น
# ไม่แสดง operational diagnostics บน Dashboard สำหรับพัฒนานักกีฬา
LANE_STALE_LIMIT_MIN = {
    "full": 900, "fast": 75, "wellness": 90,
    "reconcile": 12240, "deep": 44640, "backup": 1800,
}




@st.cache_data(ttl=CACHE_TTL_SEC)





@st.cache_data(ttl=CACHE_TTL_SEC)


@st.cache_data(ttl=CACHE_TTL_SEC)


@st.cache_data(ttl=CACHE_TTL_SEC)


@st.cache_data(ttl=CACHE_TTL_SEC)


@st.cache_data(ttl=CACHE_TTL_SEC)


@st.cache_data(ttl=CACHE_TTL_SEC)


@st.cache_data(ttl=CACHE_TTL_SEC)




@st.cache_data(ttl=CACHE_TTL_SEC)


@st.cache_data(ttl=CACHE_TTL_SEC)


@st.cache_data(ttl=CACHE_TTL_SEC)


@st.cache_data(ttl=CACHE_TTL_SEC)




@st.cache_data(ttl=CACHE_TTL_SEC)


@st.cache_data(ttl=CACHE_TTL_SEC)


@st.cache_data(ttl=CACHE_TTL_SEC)


@st.cache_data(ttl=CACHE_TTL_SEC)




@st.cache_data(ttl=CACHE_TTL_SEC)


@st.cache_data(ttl=CACHE_TTL_SEC)


@st.cache_data(ttl=CACHE_TTL_SEC)


@st.cache_data(ttl=CACHE_TTL_SEC)




@st.fragment(run_every=AUTO_REFRESH_SEC)
def auto_refresh_dashboard():
    """Rerun the full dashboard once per interval so the numbers stay current.

    ไม่ล้าง cache เอง — loader ทุกตัวมี ``ttl=CACHE_TTL_SEC`` ที่สั้นกว่ารอบนี้อยู่แล้ว
    จึงหมดอายุทันเสมอ ส่วน ``st.cache_data.clear()`` ล้าง loader ทั้ง 21 ตัวและทุก
    session พร้อมกัน = cold rerun ทุกนาที ราคา 0.23 วิ โดยไม่ได้ความสดเพิ่มเลย
    (ปุ่มรีเฟรชที่ผู้ใช้กดเองยังล้างทั้งกระดาน — ตรงนั้นตั้งใจ)
    """
    now = time.monotonic()
    last_refresh = st.session_state.get("_dashboard_auto_refresh_at")
    if last_refresh is None:
        st.session_state["_dashboard_auto_refresh_at"] = now
        return
    if now - last_refresh >= AUTO_REFRESH_SEC:
        st.session_state["_dashboard_auto_refresh_at"] = now
        st.rerun(scope="app")


# --- UI START ---
# Business date is always Thailand time, independent of the server/Windows timezone.
today = bangkok_date()
st.title("Run Performance Dashboard")
st.caption(f"ภาพรวมการฝึกซ้อมและการฟื้นตัว · ข้อมูลวันนี้ {today.strftime('%d/%m/%Y')}")

if not db_path().exists():
    st.error(f"Database not found at {db_path()}. Please run the sync scripts first.")
    st.stop()

athletes_df = load_athletes()
if athletes_df.empty:
    st.warning("No athletes found in the database. Please add athletes first.")
    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.subheader("ตัวควบคุม")

    # ปุ่มรีเฟรช: ล้าง cache (loaders ใช้ @st.cache_data ttl CACHE_TTL_SEC) + rerun → ดึงข้อมูลสดจาก DB ทันที
    # จำเป็นเพราะหลังรัน garmin-sync-auto ข้อมูลใหม่จะไม่ขึ้นจนกว่า cache หมดอายุ/ล้าง (reload หน้าไม่ช่วย)
    if st.button(
        "รีเฟรชข้อมูลล่าสุด",
        icon=":material/refresh:",
        type="primary",
        width="stretch",
    ):
        st.cache_data.clear()
        st.rerun()
    _c = connect_db()
    _la = _c.execute("SELECT MAX(start_time_local) FROM fact_activity WHERE deleted_at IS NULL").fetchone()[0]
    # ต้องกรองแถวที่ยังไม่มีค่าจริง — full sync สร้างแถวของวันใหม่ไว้ก่อนแม้ทุกช่องเป็น NULL
    # ถ้านับแถวเปล่าด้วย บรรทัดนี้จะโชว์ "วันนี้" ตลอดทั้งที่ข้อมูลจริงหยุดไปแล้ว
    # (เกณฑ์เดียวกับ load_last_data_dates — เคยหลอกมาแล้วเคสพี่เก้า 22 ก.ค. 69)
    # fetched_at เป็น UTC (ทั้ง ISO Z ใหม่และ legacy naive UTC) — แปลงใน Python เป็น
    # Asia/Bangkok โดยชัดเจน ห้ามพึ่ง timezone ของเครื่องผ่าน SQLite 'localtime'
    _lw, _lw_fetched = _c.execute(
        """SELECT MAX(calendar_date), MAX(fetched_at)
           FROM fact_daily_wellness
           WHERE resting_hr IS NOT NULL OR sleep_score IS NOT NULL
              OR body_battery_high IS NOT NULL OR hrv_last_night IS NOT NULL""").fetchone()
    _c.close()
    _lw_fetched_bkk = to_bangkok_timestamp(_lw_fetched)
    _lw_txt = (
        f"{_lw} (ดึงล่าสุด {_lw_fetched_bkk.strftime('%H:%M')} น. เวลาไทย)"
        if _lw and pd.notna(_lw_fetched_bkk) else (_lw or "—")
    )
    st.caption(f"ข้อมูลล่าสุด — กิจกรรม: {_la or '—'} · สุขภาพ: {_lw_txt}")
    st.caption("ข้อมูลจะรีเฟรชอัตโนมัติทุก 60 วินาที หรือกดรีเฟรชหลังนาฬิกา sync")

    athlete_options = dict(zip(athletes_df["display_name"], athletes_df["athlete_id"]))
    selected_name = st.selectbox(
        "นักกีฬา", options=list(athlete_options.keys()), key=ATHLETE_STATE_KEY
    )
    athlete_id = athlete_options[selected_name]
    selected_slug = athletes_df.loc[athletes_df["athlete_id"] == athlete_id, "slug"].iloc[0]
    selected_anchor = "".join(
        character if character.isalnum() or character in "-_" else "-"
        for character in str(selected_slug).lower()
    ).strip("-")

    st.markdown("**ช่วงข้อมูลสำหรับหน้าวิเคราะห์ย้อนหลัง**")
    history_period = st.segmented_control(
        "ช่วงย้อนหลัง",
        options=["7 วัน", "30 วัน", "90 วัน", "ทั้งหมด", "กำหนดเอง"],
        default="30 วัน",
        required=True,
        key="history_period",
        label_visibility="collapsed",
        width="stretch",
    )
    if history_period == "7 วัน":
        start_date, end_date = today - datetime.timedelta(days=6), today
    elif history_period == "90 วัน":
        start_date, end_date = today - datetime.timedelta(days=89), today
    elif history_period == "ทั้งหมด":
        start_date = load_first_dashboard_date(athlete_id) or today
        end_date = today
    elif history_period == "กำหนดเอง":
        custom_range = st.date_input(
            "เลือกช่วงวันที่",
            value=(today - datetime.timedelta(days=29), today),
            max_value=today,
            key="custom_history_range",
        )
        if isinstance(custom_range, (tuple, list)) and len(custom_range) == 2:
            start_date, end_date = custom_range
        else:
            start_date = end_date = custom_range[0] if isinstance(custom_range, (tuple, list)) else custom_range
    else:
        start_date, end_date = today - datetime.timedelta(days=29), today

    if start_date > end_date:
        st.error("วันเริ่มต้นต้องไม่อยู่หลังวันสิ้นสุด")
        st.stop()

    st.caption("หน้า “วันนี้” และ “ทีม” ใช้ข้อมูลล่าสุดเสมอ ไม่อิงช่วงย้อนหลัง")

# --- LOAD DATA (นักกีฬาที่เลือก) ---
wellness_df = load_wellness_data(athlete_id, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
activity_df = load_activity_data(athlete_id, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))

if not wellness_df.empty:
    wellness_df["calendar_date"] = pd.to_datetime(wellness_df["calendar_date"])
wellness_plot_df = calendar_aligned_frame(
    wellness_df, "calendar_date", start_date, end_date
)
if not activity_df.empty:
    activity_df["start_time_local"] = pd.to_datetime(activity_df["start_time_local"])
    activity_df["distance_km"] = activity_df["distance_m"] / 1000

# สรุปความพร้อมจากหลักฐานทั้งประวัติ ไม่ตีความ NULL ว่า sync ล้ม และไม่เดา capability
# จากชื่อรุ่นนาฬิกาเพียงอย่างเดียว.
availability_stats = load_data_availability(
    athlete_id, start_date.isoformat(), end_date.isoformat()
)
availability_by_key = {}
availability_rows = []
_availability_labels = {
    "available": ("พร้อม", "มีข้อมูลในช่วงที่เลือก"),
    "partial": ("บางส่วน", "Garmin Connect ส่งมาเฉพาะบางเมตริก"),
    "outside_range": ("นอกช่วง", "มีประวัติ แต่นอกช่วงที่เลือก"),
    "never_received": ("ยังไม่เคยได้รับ", "Garmin Connect ยังไม่เคยส่ง"),
}
for group in DATA_AVAILABILITY_GROUPS:
    table_stats = availability_stats[group["table"]]
    summary = summarize_metric_group(
        group["fields"],
        {field: table_stats[field]["history_count"] for field in group["fields"]},
        {field: table_stats[field]["selected_count"] for field in group["fields"]},
        {field: table_stats[field]["latest_date"] for field in group["fields"]},
    )
    availability_by_key[group["key"]] = summary
    status_label, meaning = _availability_labels[summary["state"]]
    availability_rows.append({
        "ชุดข้อมูล": group["label"],
        "สถานะ": status_label,
        "เมตริกที่เคยได้รับ": f'{summary["history_available"]}/{summary["total_fields"]}',
        "เมตริกในช่วงนี้": f'{summary["selected_available"]}/{summary["total_fields"]}',
        "ล่าสุด": (summary["latest_date"].strftime("%d/%m/%Y")
                   if summary["latest_date"] else "—"),
        "ความหมาย": meaning,
    })

with st.sidebar:
    with st.popover(
        "สถานะข้อมูล Garmin",
        icon=":material/database:",
        width="stretch",
    ):
        st.markdown("**ความพร้อมของข้อมูลจาก Garmin**")
        st.caption(
            "ตรวจจากประวัติทั้งหมดของนักกีฬาคนนี้ · ตัวเลขคือจำนวนชนิดเมตริกที่ Garmin "
            "เคยส่งจริง ไม่ใช่คะแนนคุณภาพและไม่ใช่สถานะระบบ"
        )
        st.dataframe(
            pd.DataFrame(availability_rows),
            hide_index=True,
            width="stretch",
            column_config={
                "ชุดข้อมูล": st.column_config.TextColumn(pinned=True),
                "สถานะ": st.column_config.TextColumn(),
                "เมตริกที่เคยได้รับ": st.column_config.TextColumn(),
                "เมตริกในช่วงนี้": st.column_config.TextColumn(),
                "ล่าสุด": st.column_config.TextColumn(),
                "ความหมาย": st.column_config.TextColumn(),
            },
        )
        _availability_devices = load_athlete_devices(athlete_id)
        st.caption(
            "อุปกรณ์ที่พบใน 90 วัน: "
            + (", ".join(_availability_devices) if _availability_devices else "ยังไม่มีทะเบียนอุปกรณ์")
            + " · ค่าว่างยังไม่ถูกใช้ฟันธงว่ารุ่นไม่รองรับ"
        )



# --- MAIN DASHBOARD TABS ---

# --- ส่งค่าที่หน้าเปลือกเตรียมไว้ให้ทุกหน้า ---
# หน้าแต่ละหน้าเป็นสคริปต์คนละไฟล์ จึงส่งตัวแปรให้กันตรง ๆ ไม่ได้ ต้องผ่าน session_state
set_page_context(
    athlete_id=athlete_id,
    athletes_df=athletes_df,
    start_date=start_date,
    end_date=end_date,
    wellness_df=wellness_df,
    activity_df=activity_df,
    wellness_plot_df=wellness_plot_df,
    today=today,
    selected_name=selected_name,
    selected_slug=selected_slug,
    selected_anchor=selected_anchor,
    availability_by_key=availability_by_key,
)


# --- NAVIGATION ---
# เดิมเป็น st.tabs 6 แท็บในสคริปต์เดียว ทุกครั้งที่กดแท็บจะรันทั้งไฟล์ใหม่ จึงต้องแฮ็ก
# `if tab_x.open:` ครอบทุกแท็บไม่ให้สร้างกราฟครบทุกใบทุกรอบ และ team snapshot ต้องอยู่
# นอก `with tab_x:` แต่ในเงื่อนไข ไม่งั้นแท็บวันนี้ NameError เมื่อเปิดโดยไม่ผ่านแท็บทีม
#
# `st.navigation` รันเฉพาะไฟล์ของหน้าที่เปิดอยู่จริง เงื่อนไขทั้งชุดจึงหายไปเอง
# และ team snapshot กลายเป็นฟังก์ชันที่หน้าไหนต้องใช้ก็เรียก (dashboard_team.py)
page = st.navigation(
    [
        st.Page("app_pages/today.py", title="วันนี้", icon=":material/today:", default=True),
        st.Page("app_pages/team.py", title="ทีม", icon=":material/groups:"),
        st.Page("app_pages/recovery.py", title="การฟื้นตัว", icon=":material/bedtime:"),
        st.Page("app_pages/training.py", title="การซ้อม", icon=":material/directions_run:"),
        st.Page("app_pages/progress.py", title="ความก้าวหน้า",
                icon=":material/trending_up:"),
        st.Page("app_pages/session.py", title="รายละเอียดเซสชัน",
                icon=":material/query_stats:"),
    ],
    position="top",
)
page.run()

# แท็บอื่นจะไม่ลงทะเบียนเลย = ค้างข้อมูลเดิมเงียบ ๆ โดยไม่มี error (เกิดจริงใน c9f4b07
# ตอนใส่ lazy tabs แล้วบรรทัดนี้ถูกเยื้องตามไปด้วย ผู้ใช้เจอก่อนเทส)
auto_refresh_dashboard()
