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

# --- ตัวเลขของ st.metric = IBM Plex Mono (อาร์ตบอร์ด "ระบบดีไซน์" คลาส .num) ---
# ``codeFont`` ใน .streamlit/config.toml ไปไม่ถึง st.metric — Streamlit เอาไปลงเฉพาะ
# st.code / st.dataframe (ตรวจในเบราว์เซอร์ 26 ส.ค. 69: 0 element เป็น Plex Mono
# และ FontFace ของมันยัง unloaded) จึงต้องชี้เอง
# บล็อกนี้ต้องอยู่ระดับบนสุดของสคริปต์ ไม่ใช่ในบล็อกแท็บ เพราะ st.metric กระจายอยู่ทุกแท็บ
# และแท็บที่ไม่ได้เปิดไม่ถูกรัน (lazy `tab.open`) — ฉีดในแท็บเดียวแท็บอื่นจะไม่ได้ฟอนต์เลย
NUMBER_FONT_CSS = """
<style>
[data-testid="stMetricValue"],
[data-testid="stMetricDelta"] {
  font-family: "IBM Plex Mono", "IBM Plex Sans Thai", monospace;
  font-variant-numeric: tabular-nums;
}
</style>
"""
st.markdown(NUMBER_FONT_CSS, unsafe_allow_html=True)

# --- LAYOUT TWEAK (จอปกติ): ดันเนื้อหา sidebar ขึ้นให้ชิดบนเหมาะสม + ลดช่องว่างบนหน้าหลัก ---
st.markdown("""
<style>
  [data-testid="stSidebarUserContent"] { padding-top: 1.5rem !important; }
  section[data-testid="stMain"] .block-container { padding-top: 2.5rem !important; }
</style>
""", unsafe_allow_html=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("GARMIN_DATA_DIR", PROJECT_ROOT / "data"))
DB_PATH = DATA_DIR / "garmin.db"

# ประเภทกิจกรรมที่นับเป็น "วิ่ง" (ใช้คำนวณโหลด / pace-HR trend / intensity distribution)
RUN_TYPES = ("running", "track_running", "trail_running", "treadmill_running")

# helper บริสุทธิ์ย้ายไป dashboard_domain.py / dashboard_view.py แล้ว
# ที่นี่เหลือเฉพาะของที่เรียก st. จริง: loader ที่ติด cache และสคริปต์วาดหน้า
from dashboard_domain import (  # noqa: E402
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
from dashboard_view import (  # noqa: E402
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



HRV_TREND_LOOKBACK_DAYS = HRV_TREND_CURRENT_DAYS + HRV_TREND_BASELINE_DAYS

C_NEUTRAL = "#c3c9d2"  # เทาอมฟ้าอ่อน — เห็นได้บนพื้นขาว
C_SECOND = "#eb6834" # เส้นที่สองในกราฟเดียวกัน (ตรวจ CVD แล้ว ΔE 24.7 จาก C_BLUE)


# กฎกราฟ 02: ค่าที่มีลำดับใช้สีเดียวไล่อ่อน→เข้ม ไม่ใช่รุ้ง — เขียว-เหลือง-แดงทำให้ "เบา"
# อ่านว่าดี และ "หนัก" อ่านว่าอันตราย ทั้งที่เป็นแค่ระดับความหนัก ไม่ใช่คำตัดสิน
# และมันยังไปชนสีสถานะซึ่งจองไว้ให้สถานะอย่างเดียว (กฎกราฟ 03)
BLUE_RAMP_3 = ["#cde2fb", C_BLUE, "#104281"]
BLUE_RAMP_5 = ["#cde2fb", "#86b6ef", C_BLUE, "#1a5aa8", "#104281"]

INTENSITY_COLORS = dict(zip(INTENSITY_ORDER, BLUE_RAMP_3))

# กฎกราฟ 07: ค่าเดียวกันใช้สีเดียวกันทุกแท็บ — ตารางนี้คือที่เดียวที่ตัดสินว่าค่าไหนสีอะไร
# เดิมแต่ละกราฟเลือกสีเอง ทำให้ HR เป็นแดงในกราฟหนึ่ง แต่ Readiness เป็นเขียวในอีกกราฟ
# ทั้งที่ทั้งคู่ไม่ใช่สถานะ · หลักที่ใช้: หัวเรื่องของกราฟ = น้ำเงิน · ค่าที่สอง = ส้ม ·
# เส้นฐาน/ค่าเฉลี่ยเคลื่อนที่ = เทา
SERIES_COLORS = {
    "sleep_score": C_BLUE,
    "body_battery_high": C_SECOND,
    "stress_avg": C_SECOND,
    "training_readiness": C_BLUE,
    "resting_hr": C_SECOND,
    "hrv_last_night": C_BLUE,
    "hrv_weekly_avg": C_CONTEXT,
    "avg_sleep_respiration": C_BLUE,
    "avg_waking_respiration": C_SECOND,
    "recovery_time": C_BLUE,
    "avg_hr": C_SECOND,
    "avg_pace_min_per_km": C_BLUE,
    "avg_cadence": C_BLUE,
    "avg_power": C_SECOND,
    "elevation_gain_m": C_CONTEXT,
    "distance_km": C_BLUE,
    "vo2max_trend": C_BLUE,
    "time_5k_sec": C_BLUE,
    "time_10k_sec": C_SECOND,
}

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


































































































TEAM_CARD_CSS = """
<style>
.team-card { display: grid; grid-template-columns: 232px minmax(0, 1fr) 500px;
  border: 1px solid #e4e1da; border-left-width: 4px; border-radius: 2px;
  background: #ffffff; }
.team-card > div { padding: 14px 18px; }
.team-card__flags, .team-card__nums { border-left: 1px solid #f4f2ee; }
.team-card__who { display: flex; flex-direction: column; gap: 5px; }
.team-card__head { display: flex; align-items: center; gap: 9px; }
.team-card__name { font-size: 19px; font-weight: 700; }
.team-card__status { font-size: 14px; font-weight: 600; }
.team-card__fresh { font-size: 11px; color: #8a8d94; line-height: 1.45; }
.team-card__lbl { font-size: 11px; letter-spacing: .06em; color: #8a8d94;
  font-weight: 500; margin-bottom: 7px; }
.team-card__chips { display: flex; flex-wrap: wrap; gap: 7px; }
.team-card__chip { display: inline-flex; align-items: center; gap: 6px;
  padding: 3px 9px; border-radius: 2px; font-size: 12px; font-weight: 500; }
.team-card__load { font-size: 12px; color: #55585f; margin-top: 9px; }
.team-card__nums { display: grid; grid-template-columns: 132px repeat(4, minmax(0, 1fr));
  gap: 10px; }
.team-card__sub { flex-wrap: wrap; }
.team-card__val { font-size: 21px; font-weight: 600; line-height: 1.2;
  font-variant-numeric: tabular-nums; }
/* ตัวเลข = IBM Plex Mono ตามอาร์ตบอร์ด "ระบบดีไซน์" (คลาส .num) — ทุกหลักกว้างเท่ากัน
   ตัวเลขคนละแถวจึงเรียงตรงคอลัมน์  ``codeFont`` ใน config.toml ทำแทนไม่ได้
   Streamlit เอาไปลงเฉพาะ st.code / st.dataframe เท่านั้น
   Plex Mono ไม่มีตัวไทย ป้ายที่ปนไทยจึงต้องตกไปที่ Plex Sans Thai ก่อนถึง monospace ของระบบ */
.team-card__val { font-family: "IBM Plex Mono", "IBM Plex Sans Thai", monospace; }
.team-card__sub { display: flex; align-items: center; gap: 5px; font-size: 12px;
  margin-top: 2px; }
/* ---- การ์ดทั้งใบคือปุ่ม ----
   HTML ที่ฉีดผ่าน st.markdown คุยกลับหา Python ไม่ได้ จึงวาง "ปุ่มจริง" ทับทั้งใบ
   แบบโปร่งใสแทน วิธีนี้ได้ทั้งการกดด้วยเมาส์ โฟกัสคีย์บอร์ด และสถานะครบทั้งหก
   โดยไม่ต้องเขียน custom component  เจาะจงได้เพราะ Streamlit ติดคลาส st-key-<key>
   ให้ทุก container/widget ที่มี key
   ถ้าเบราว์เซอร์ไม่รับ CSS ชุดนี้ ปุ่มจะกลับไปเป็นปุ่มธรรมดาใต้การ์ด — หน้าตาเสีย
   แต่ยังกดได้ ไม่ใช่ฟีเจอร์ที่หายไปเงียบ ๆ */
[class*="st-key-teamcard-"] { position: relative; margin-bottom: 10px; }
/* Streamlit ใส่ margin-bottom: -1rem ให้กล่องเนื้อหาของ st.markdown เพื่อหักลบ margin
   ของ <p> ตัวสุดท้าย การ์ดของเราไม่มี <p> ท้าย ค่าลบนั้นจึงหดกล่องลงเฉย ๆ แล้วปุ่มที่
   ทาบไว้เตี้ยกว่าการ์ด เหลือแถบล่างที่กดไม่โดน (วัดจริง 26 ส.ค. 69: การ์ด 501.34px
   ปุ่ม 495.34px = 10px margin ของการ์ด ลบ 16px ของ Streamlit) → ล้างค่าลบตรงกล่องที่
   ห่อการ์ดอยู่ แล้วย้ายระยะห่างระหว่างการ์ดไปไว้ที่ container ซึ่งอยู่นอกกล่องนั้น */
[class*="st-key-teamcard-"] .stMarkdown div:has(> .team-card) { margin-bottom: 0; }
[class*="st-key-teamcard-"] > div:last-child:has(.stButton) {
  position: absolute; inset: 0; margin: 0; padding: 0; }
[class*="st-key-teamcard-"] .stButton,
[class*="st-key-teamcard-"] .stButton > button { height: 100%; width: 100%; }
[class*="st-key-teamcard-"] .stButton > button {
  opacity: 0; border: none; background: transparent; cursor: pointer; }
/* เส้นโฟกัสวาดเอง ห้ามใช้ของเบราว์เซอร์ซึ่งหายไปบนพื้นขาว (กฎในระบบดีไซน์)
   และต้องวาดที่ "การ์ด" ไม่ใช่ที่ปุ่ม — ของเดิมใช้ opacity: 1 ปลุกปุ่มทั้งใบขึ้นมา
   ข้อความ "ดูรายละเอียดของ ..." จึงลอยทับกลางการ์ดทุกครั้งที่กด Tab (เจอ 26 ส.ค. 69)
   ปุ่มยังโปร่งใสตลอดเวลา ข้อความยังอยู่ใน DOM ให้ screen reader อ่านเหมือนเดิม */
[class*="st-key-teamcard-"]:has(.stButton > button:focus-visible) .team-card {
  outline: 2px solid #184f95; outline-offset: 2px; }
[class*="st-key-teamcard-"]:hover .team-card {
  border-color: #184f95; transition: border-color 140ms ease-out; }
[class*="st-key-teamcard-"]:active .team-card { background: #f4f2ee; }

/* ---- ที่แคบ ----
   สามคอลัมน์ของการ์ดเรียกร้องความกว้างตายตัว 232 + 500 = 732px ก่อนนับ padding
   ได้น้อยกว่านั้นตัวเลข BB/Sleep/RHR/HRV ฝั่งขวาจะถูกบีบจนอ่านไม่ออกหรือตัดหายไปเลย
   แคบกว่าเกณฑ์ให้ยุบเป็นแถวซ้อนกัน เส้นคั่นซ้ายกลายเป็นเส้นคั่นบน

   เกณฑ์ต้องวัดจากพื้นที่ของการ์ดเอง ไม่ใช่ความกว้างหน้าต่าง — @media (max-width: 900px)
   ของเดิมพลาดเคสหน้าต่าง 1000px ที่ sidebar กิน 300px ไป: การ์ดเหลือ 535px แต่ยังวาด
   สามคอลัมน์แล้วล้น (scrollWidth 732 vs clientWidth 535 วัดจริง 26 ส.ค. 69)
   container query อ่านความกว้างของ container ตรง ๆ จึงตัดถูกทั้งตอน sidebar เปิดและปิด */
[class*="st-key-teamcard-"] { container-type: inline-size; }

@container (max-width: 800px) {
  .team-card { grid-template-columns: minmax(0, 1fr); }
  .team-card > div { padding: 12px 14px; }
  .team-card__flags, .team-card__nums {
    border-left: none; border-top: 1px solid #f4f2ee; }
  .team-card__nums { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

/* การ์ดต้องไม่ถูกหั่นกลางใบตอนพิมพ์ A4 — ครึ่งใบอ่านไม่ได้ความ */
@media print { .team-card { break-inside: avoid; page-break-inside: avoid; } }
</style>
"""








# --- แท็บ "วันนี้": สรุปสัญญาณ ไทล์ค่าเดี่ยว แถบโหลด และแถวเซสชัน ---
# หน้าเรียงจากสัญญาณที่ต้องคุยต่อ → ค่าจากอุปกรณ์ → บริบทโหลด → เซสชันจริง

# ใช้เฉพาะหมวดที่ Garmin ระบุเองเป็น poor/low/unbalanced เป็นสัญญาณให้ทบทวน
# ไม่สร้าง cutoff Body Battery/RHR ในระบบเอง และไม่นับจำนวนธงเป็นคะแนนโหวต
SLEEP_LOW = 60        # ขอบหมวด Poor ของ Garmin; เป็น vendor signal ไม่ใช่ clinical cutoff
HRV_ALERT = {"LOW": "rest", "UNBALANCED": "watch"}
READINESS_ALERT = ("POOR", "LOW")

# คีย์ของ selectbox นักกีฬา — ปุ่มบนการ์ดทีมเขียนค่าลงคีย์นี้เพื่อสลับคนที่กำลังดู
ATHLETE_STATE_KEY = "selected_athlete"



















TODAY_PANEL_CSS = """
<style>
.today-lbl { font-size: 11px; letter-spacing: .06em; color: #8a8d94; font-weight: 500; }
.today-verdict { display: grid; grid-template-columns: minmax(0, 1fr) auto;
  gap: 26px; align-items: center; background: #ffffff; border: 1px solid #e4e1da;
  border-top-width: 3px; border-radius: 2px; padding: 16px 20px; margin-bottom: 12px; }
.today-verdict__head { display: flex; align-items: center; gap: 11px; }
.today-verdict__title { font-size: 26px; font-weight: 700; line-height: 1.2; }
.today-verdict__note { font-size: 12px; color: #8a8d94; margin-top: 7px; }
.today-verdict__figs { display: flex; gap: 26px; padding-left: 24px;
  border-left: 1px solid #e4e1da; }
.today-verdict__fig { font-size: 18px; font-weight: 600; line-height: 1.35;
  font-variant-numeric: tabular-nums; }
.today-chips { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 9px; }
.today-chip { display: inline-flex; align-items: center; gap: 6px; padding: 3px 9px;
  border-radius: 2px; font-size: 12px; font-weight: 500; }
.today-chip--zone { border: none; }
.today-none { font-size: 13px; color: #55585f; margin-top: 9px; }
.today-tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(168px, 1fr));
  gap: 10px; margin-bottom: 12px; }
.today-tile { background: #ffffff; border: 1px solid #e4e1da; border-radius: 2px;
  padding: 12px 14px 10px; }
.today-tile__val { font-size: 26px; font-weight: 600; line-height: 1.15; margin-top: 5px;
  font-variant-numeric: tabular-nums; }
.today-tile__unit { font-size: 12px; color: #8a8d94; font-weight: 400; margin-left: 5px; }
.today-tile__note { display: flex; align-items: center; gap: 5px; font-size: 12px;
  margin-top: 4px; }
.today-spark { display: block; margin-top: 8px; }
.today-panel { background: #ffffff; border: 1px solid #e4e1da; border-radius: 2px;
  padding: 15px 20px 18px; margin-bottom: 12px; }
.today-panel__head { display: flex; align-items: baseline; justify-content: space-between;
  gap: 16px; margin-bottom: 13px; }
.today-panel__title { font-size: 15px; font-weight: 600; }
.today-panel__hint { font-size: 12px; color: #8a8d94; }
.today-ef__val { font-size: 34px; font-weight: 600; line-height: 1;
  font-variant-numeric: tabular-nums; }
.today-strip { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 6px; }
.today-strip__col { text-align: center; }
.today-strip__plot { display: flex; align-items: flex-end; justify-content: center;
  height: 54px; }
.today-strip__bar { width: 60%; background: #2a78d6; border-radius: 1px; min-height: 2px; }
.today-strip__rest { width: 60%; height: 2px; background: #e4e1da; }
.today-strip__val { font-size: 13px; font-weight: 600; margin-top: 5px;
  font-variant-numeric: tabular-nums; }
.today-strip__day { font-size: 11px; color: #8a8d94; font-variant-numeric: tabular-nums; }
.today-sess__row, .today-sess__head { display: grid;
  grid-template-columns: 108px minmax(0, 1fr) 92px 78px 72px 62px 104px;
  gap: 8px; align-items: center; padding: 9px 0; border-bottom: 1px solid #f4f2ee; }
.today-sess__head { border-bottom: 1px solid #e4e1da; padding-bottom: 7px; }
.today-sess__when { font-size: 13px; color: #55585f; font-variant-numeric: tabular-nums; }
.today-sess__name { font-size: 14px; overflow-wrap: anywhere; }
.today-sess__num { font-size: 14px; text-align: right; font-variant-numeric: tabular-nums; }
.today-sess__zone { text-align: right; }
/* ตัวเลขทุกตัวบนแผงนี้เป็น mono ด้วยเหตุผลเดียวกับการ์ดทีมข้างบน */
.today-verdict__fig, .today-tile__val, .today-ef__val,
.today-strip__val, .today-strip__day,
.today-sess__when, .today-sess__num { font-family: "IBM Plex Mono", "IBM Plex Sans Thai", monospace; }
/* แผงต้องไม่ถูกหั่นกลางใบตอนพิมพ์ A4 — ครึ่งใบอ่านไม่ได้ความ */
@media print {
  .today-verdict, .today-tile, .today-panel { break-inside: avoid; page-break-inside: avoid; }
}
</style>
"""






















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


def connect_db():
    """Open the dashboard database read-only without creating a missing file."""
    uri = f"{DB_PATH.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5.0)
    conn.execute("PRAGMA query_only = ON")
    return conn


@st.cache_data(ttl=CACHE_TTL_SEC)
def load_athletes():
    conn = connect_db()
    df = pd.read_sql_query("SELECT athlete_id, display_name, slug FROM dim_athlete", conn)
    conn.close()
    return df


# คอลัมน์ที่เป็นข้อความ (ที่เหลือ coerce เป็นตัวเลขทั้งหมด กัน object dtype ตอนคอลัมน์ NULL ล้วน)
_WELLNESS_TEXT = {
    "calendar_date", "hrv_status", "training_status", "readiness_level",
    "readiness_feedback", "readiness_feedback_long", "fetched_at",
    "repair_attempted_at_utc",
    "readiness_timestamp_utc", "readiness_timestamp_local",
    "readiness_input_context", "readiness_device_id",
    "readiness_sleep_factor_feedback", "recovery_time_factor_feedback",
    "recovery_time_change_phrase", "acwr_factor_feedback",
    "hrv_factor_feedback", "stress_history_factor_feedback",
}
_ACTIVITY_TEXT = {"activity_type", "activity_name", "start_time_local", "start_time_utc",
                  "training_effect_label", "location_name", "fetched_at"}

# แต่ละกลุ่มวัดจากประวัติจริงทั้งบัญชีและช่วงวันที่ที่ผู้ใช้เลือก ไม่ผูก capability
# กับชื่อรุ่นนาฬิกา เพราะ firmware/account/API อาจให้ข้อมูลต่างกันได้.
DATA_AVAILABILITY_GROUPS = (
    {
        "key": "core_wellness", "label": "สุขภาพพื้นฐาน", "table": "fact_daily_wellness",
        "fields": ("resting_hr", "sleep_score", "body_battery_high", "stress_avg",
                   "hrv_last_night", "avg_sleep_respiration"),
    },
    {
        "key": "readiness", "label": "ความพร้อมและการฟื้นตัว", "table": "fact_daily_wellness",
        "fields": ("training_readiness", "recovery_time_min", "acute_load", "training_status"),
    },
    {
        "key": "advanced", "label": "สมรรถนะขั้นสูง", "table": "fact_daily_wellness",
        "fields": ("vo2max_trend", "fitness_age", "endurance_score", "hill_score_overall",
                   "lactate_threshold_hr"),
    },
    {
        "key": "activity_detail", "label": "รายละเอียดกิจกรรม", "table": "fact_activity",
        "fields": ("avg_hr", "avg_cadence", "avg_power", "training_load",
                   "avg_ground_contact_time_ms", "begin_stamina"),
    },
    {
        "key": "body", "label": "องค์ประกอบร่างกาย", "table": "fact_body_composition",
        "fields": ("weight_kg", "bmi", "body_fat_pct"),
    },
    {
        "key": "race", "label": "คาดการณ์เวลาแข่ง", "table": "fact_race_prediction",
        "fields": ("time_5k_sec", "time_10k_sec", "time_half_sec", "time_full_sec"),
    },
)


@st.cache_data(ttl=CACHE_TTL_SEC)
def load_wellness_data(athlete_id, start_date, end_date):
    conn = connect_db()
    query = """
        SELECT * FROM fact_daily_wellness
        WHERE athlete_id = ? AND calendar_date >= ? AND calendar_date <= ?
        ORDER BY calendar_date ASC
    """
    df = pd.read_sql_query(query, conn, params=(athlete_id, start_date, end_date))
    conn.close()
    for col in df.columns:
        if col not in _WELLNESS_TEXT:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=CACHE_TTL_SEC)
def load_activity_data(athlete_id, start_date, end_date):
    conn = connect_db()
    query = """
        SELECT * FROM fact_activity
        WHERE athlete_id = ? AND start_time_local >= ? AND start_time_local <= ?
          AND deleted_at IS NULL
        ORDER BY start_time_local ASC
    """
    df = pd.read_sql_query(query, conn, params=(athlete_id, start_date, f"{end_date} 23:59:59"))
    conn.close()
    for col in df.columns:
        if col not in _ACTIVITY_TEXT:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=CACHE_TTL_SEC)
def load_data_availability(athlete_id, start_date, end_date):
    """Return all-history and selected-range evidence for Dashboard metric groups."""
    conn = connect_db()
    result = {}
    try:
        for table in {group["table"] for group in DATA_AVAILABILITY_GROUPS}:
            fields = tuple(
                field
                for group in DATA_AVAILABILITY_GROUPS if group["table"] == table
                for field in group["fields"]
            )
            date_expr = (
                "SUBSTR(start_time_local, 1, 10)"
                if table == "fact_activity" else "calendar_date"
            )
            expressions = []
            for field in fields:
                expressions.extend((
                    f'COUNT({field}) AS "{field}__history"',
                    f'COUNT(CASE WHEN {date_expr} >= ? AND {date_expr} <= ? '
                    f'THEN {field} END) AS "{field}__selected"',
                    f'MAX(CASE WHEN {field} IS NOT NULL THEN {date_expr} END) '
                    f'AS "{field}__latest"',
                ))
            active_filter = " AND deleted_at IS NULL" if table == "fact_activity" else ""
            params = []
            for _ in fields:
                params.extend((start_date, end_date))
            params.append(athlete_id)
            cursor = conn.execute(
                f"SELECT {', '.join(expressions)} FROM {table} "
                f"WHERE athlete_id = ?{active_filter}",
                tuple(params),
            )
            columns = [description[0] for description in cursor.description]
            row = cursor.fetchone()
            values = dict(zip(columns, row))
            result[table] = {
                field: {
                    "history_count": values[f"{field}__history"],
                    "selected_count": values[f"{field}__selected"],
                    "latest_date": values[f"{field}__latest"],
                }
                for field in fields
            }
    finally:
        conn.close()
    return result


@st.cache_data(ttl=CACHE_TTL_SEC)
def load_daily_run_km(athlete_id, start_date, end_date):
    """ระยะวิ่งรวมรายวัน (เฉพาะประเภทวิ่ง) สำหรับโหลดสะสม"""
    conn = connect_db()
    placeholders = ",".join("?" for _ in RUN_TYPES)
    query = f"""
        SELECT SUBSTR(start_time_local, 1, 10) AS date, SUM(distance_m) / 1000.0 AS km, COUNT(*) AS sessions
        FROM fact_activity
        WHERE athlete_id = ? AND activity_type IN ({placeholders})
          AND start_time_local >= ? AND start_time_local <= ?
          AND deleted_at IS NULL
        GROUP BY SUBSTR(start_time_local, 1, 10)
        ORDER BY date ASC
    """
    df = pd.read_sql_query(query, conn, params=(athlete_id, *RUN_TYPES, start_date, f"{end_date} 23:59:59"))
    conn.close()
    df["date"] = pd.to_datetime(df["date"])
    df["km"] = pd.to_numeric(df["km"], errors="coerce").fillna(0.0)
    return df


@st.cache_data(ttl=CACHE_TTL_SEC)
def load_first_run_date(athlete_id):
    """วันแรกที่มีข้อมูลวิ่ง — ใช้ตัดสินว่าประวัติพอคำนวณ chronic 28 วันหรือยัง"""
    conn = connect_db()
    placeholders = ",".join("?" for _ in RUN_TYPES)
    row = conn.execute(
        f"SELECT MIN(SUBSTR(start_time_local, 1, 10)) FROM fact_activity "
        f"WHERE athlete_id = ? AND activity_type IN ({placeholders}) AND deleted_at IS NULL",
        (athlete_id, *RUN_TYPES)).fetchone()
    conn.close()
    return datetime.date.fromisoformat(row[0]) if row and row[0] else None


@st.cache_data(ttl=CACHE_TTL_SEC)
def load_easy_runs(athlete_id, start_date, end_date):
    """รันที่มี HR + ระยะ + เวลา ครบพอคำนวณ EF (คัด easy ทีหลังด้วย LTHR ของแต่ละคน)"""
    conn = connect_db()
    placeholders = ",".join("?" for _ in RUN_TYPES)
    query = f"""
        SELECT SUBSTR(start_time_local, 1, 10) AS date, distance_m, duration_sec, avg_hr
        FROM fact_activity
        WHERE athlete_id = ? AND activity_type IN ({placeholders})
          AND start_time_local >= ? AND start_time_local <= ?
          AND deleted_at IS NULL
          AND avg_hr IS NOT NULL AND distance_m IS NOT NULL AND duration_sec > 0
        ORDER BY start_time_local ASC
    """
    df = pd.read_sql_query(
        query, conn, params=(athlete_id, *RUN_TYPES, start_date, f"{end_date} 23:59:59")
    )
    conn.close()
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


@st.cache_data(ttl=CACHE_TTL_SEC)
def athlete_has_load(athlete_id):
    """นาฬิกาคนนี้ให้ค่า training_load ไหม (บางรุ่นไม่ให้ → ต้อง fallback เป็นระยะวิ่ง)"""
    conn = connect_db()
    n = conn.execute(
        "SELECT COUNT(*) FROM fact_activity "
        "WHERE athlete_id = ? AND training_load IS NOT NULL AND deleted_at IS NULL",
        (athlete_id,)).fetchone()[0]
    conn.close()
    return n > 0


LOAD_CURRENCY_SAMPLE = 5   # กี่กิจกรรมล่าสุดที่ใช้ตอบว่า "นาฬิกาตอนนี้ยังส่ง TL อยู่ไหม"


@st.cache_data(ttl=CACHE_TTL_SEC)
def athlete_load_is_current(athlete_id):
    """นาฬิกาที่คนนี้ใช้ **อยู่ตอนนี้** ยังส่ง ``training_load`` อยู่ไหม

    ``athlete_has_load()`` ตอบจากประวัติทั้งหมด ซึ่งใช้ตอบคำถาม "เคยได้รับไหม" ได้ถูก
    แต่ใช้เลือกหน่วยของโหลดไม่ได้ — คนที่เลิกใช้นาฬิการุ่นที่ให้ TL จะยังถูกรวมเฉพาะ
    แถวที่มี TL กิจกรรมหลังเปลี่ยนจึงหายจากผลรวมทั้งที่อยู่ใน DB ผลคือ 0 TL · -100%
    อ่านได้ว่า "หยุดซ้อม" และถ้าเกิน 42 วันจะไม่เหลือโหลดในกรอบเลยจน ``has_workload``
    เป็นเท็จ แล้วสถานะการ์ดตกไปเป็น "ข้อมูลไม่พอ" ทั้งที่ซ้อมทุกวัน

    ต้องมี TL ครบทุกกิจกรรมใน sample ไม่ใช่เพียงหนึ่งรายการ มิฉะนั้นการเลือก TL จะทำให้
    กิจกรรมที่ค่าเป็น NULL หายจาก workload โดยเงียบ ๆ; กรณี coverage ไม่ครบใช้ระยะวิ่ง
    ซึ่งแคบกว่าแต่มีนิยามตรงและไม่แสร้งว่าครอบคลุมกิจกรรมทั้งหมด
    """
    conn = connect_db()
    rows = conn.execute(
        "SELECT training_load IS NOT NULL FROM fact_activity "
        "WHERE athlete_id = ? AND deleted_at IS NULL "
        "ORDER BY start_time_local DESC LIMIT ?",
        (athlete_id, LOAD_CURRENCY_SAMPLE)).fetchall()
    conn.close()
    return len(rows) == LOAD_CURRENCY_SAMPLE and all(row[0] for row in rows)


@st.cache_data(ttl=CACHE_TTL_SEC)
def athlete_has_training_readiness(athlete_id):
    """บัญชีนี้เคยได้รับ Training Readiness หรือไม่ (ไม่ใช้ฟันธงรุ่นนาฬิกา)."""
    conn = connect_db()
    n = conn.execute(
        "SELECT COUNT(*) FROM fact_daily_wellness "
        "WHERE athlete_id = ? AND training_readiness IS NOT NULL",
        (athlete_id,)).fetchone()[0]
    conn.close()
    return n > 0


@st.cache_data(ttl=CACHE_TTL_SEC)
def load_athlete_devices(athlete_id):
    """Load recently seen device labels when the optional inventory table exists."""
    conn = connect_db()
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='dim_athlete_device'"
        ).fetchone()
        if not exists:
            return []
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(dim_athlete_device)").fetchall()
        }
        name_columns = [
            column for column in ("product_display_name", "display_name") if column in columns
        ]
        if not name_columns or "athlete_id" not in columns:
            return []
        selected_columns = list(name_columns)
        if "last_seen_at_utc" in columns:
            selected_columns.append("last_seen_at_utc")
        select_columns = ", ".join(selected_columns)
        order = " ORDER BY is_primary_training_device DESC, is_primary_device DESC" \
            if {"is_primary_training_device", "is_primary_device"}.issubset(columns) else ""
        rows = conn.execute(
            f"SELECT {select_columns} FROM dim_athlete_device WHERE athlete_id = ?{order}",
            (athlete_id,),
        ).fetchall()
    finally:
        conn.close()

    records = []
    for row in rows:
        records.append(dict(zip(selected_columns, row)))
    return device_inventory_labels(records, stale_days=90)


@st.cache_data(ttl=CACHE_TTL_SEC)
def load_daily_load(athlete_id, start_date, end_date):
    """ผลรวม Garmin training_load รายวัน — ทุกกิจกรรม (รวม cross-training: HIIT/เวท/มวย)"""
    conn = connect_db()
    query = """
        SELECT SUBSTR(start_time_local, 1, 10) AS date, SUM(training_load) AS value, COUNT(*) AS sessions
        FROM fact_activity
        WHERE athlete_id = ? AND training_load IS NOT NULL
          AND start_time_local >= ? AND start_time_local <= ?
          AND deleted_at IS NULL
        GROUP BY SUBSTR(start_time_local, 1, 10)
        ORDER BY date ASC
    """
    df = pd.read_sql_query(query, conn, params=(athlete_id, start_date, f"{end_date} 23:59:59"))
    conn.close()
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce").fillna(0.0)
    return df


def load_daily_workload(athlete_id, start_date, end_date):
    """คืน (df[date,value,sessions], metric, unit) สำหรับโหลดสะสม
    ใช้ training_load ถ้านาฬิกาให้ (จับ cross-training ครบ) ไม่งั้น fallback ระยะวิ่ง (กม.)"""
    if athlete_load_is_current(athlete_id):
        return load_daily_load(athlete_id, start_date, end_date), "training_load", "TL"
    df = load_daily_run_km(athlete_id, start_date, end_date).rename(columns={"km": "value"})
    return df, "ระยะวิ่ง", "km"


@st.cache_data(ttl=CACHE_TTL_SEC)
def load_first_load_date(athlete_id):
    """วันแรกที่ **นาฬิกาเริ่มส่ง** ``training_load`` — ไม่ใช่วันแรกที่มีกิจกรรม

    ``athlete_has_load()`` ตอบว่า "มี TL" ถ้าเจอแถวเดียวในประวัติทั้งหมด ถ้าใครเปลี่ยน
    นาฬิกากลางคัน วันก่อนเปลี่ยนจะไม่มี TL แล้วถูกนับเป็น 0 ในฐาน 28 วัน = ฐานต่ำเกินจริง
    หน้าจอจะขึ้นว่าซ้อมหนักขึ้นมหาศาลทั้งที่ทำเท่าเดิม **โดยไม่มี error สักตัว**
    ฐานจึงต้องเริ่มนับที่นี่ แล้วปล่อยให้เกณฑ์ "ประวัติ ≥ 28 วัน" เงียบไว้จนกว่าจะพอจริง
    """
    conn = connect_db()
    row = conn.execute(
        "SELECT MIN(SUBSTR(start_time_local, 1, 10)) FROM fact_activity "
        "WHERE athlete_id = ? AND training_load IS NOT NULL AND deleted_at IS NULL",
        (athlete_id,)).fetchone()
    conn.close()
    return datetime.date.fromisoformat(row[0]) if row and row[0] else None


@st.cache_data(ttl=CACHE_TTL_SEC)
def load_first_dashboard_date(athlete_id):
    """วันแรกที่มีข้อมูลซึ่งอยู่ภายใต้ตัวกรองช่วงย้อนหลังของ Dashboard.

    รวม activity, wellness และ race prediction; PR/body composition มีตรรกะโหลด
    ทั้งประวัติแยกอยู่แล้ว จึงไม่ดึงวันเก่ามากของสองตารางนั้นมาขยายกราฟสุขภาพให้ว่าง.
    """
    conn = connect_db()
    row = conn.execute(
        """SELECT MIN(calendar_date) FROM (
               SELECT SUBSTR(start_time_local, 1, 10) AS calendar_date
               FROM fact_activity
               WHERE athlete_id = ? AND deleted_at IS NULL
               UNION ALL
               SELECT calendar_date FROM fact_daily_wellness WHERE athlete_id = ?
               UNION ALL
               SELECT calendar_date FROM fact_race_prediction WHERE athlete_id = ?
           )
           WHERE calendar_date IS NOT NULL""",
        (athlete_id, athlete_id, athlete_id),
    ).fetchone()
    conn.close()
    return datetime.date.fromisoformat(row[0]) if row and row[0] else None


@st.cache_data(ttl=CACHE_TTL_SEC)
def load_last_data_dates(athlete_id):
    """วันล่าสุดที่มี activity / wellness — ใช้ทำแถบเตือนถ้า sync ค้าง (token หมด/Task ล้ม)

    wellness ต้องนับเฉพาะวันที่ "มีข้อมูลจริง" — ระบบ sync insert แถวของวันใหม่ไว้ก่อน
    แม้ค่าทุกช่องเป็น NULL (นักกีฬายังไม่ sync นาฬิกา) ถ้านับแถวเปล่าด้วย แถบจะโชว์
    🟢 "วันนี้" ทั้งที่ข้อมูลจริงหยุดไปแล้ว (เคสพี่เก้า 22 ก.ค. 69)"""
    conn = connect_db()
    la = conn.execute("SELECT MAX(SUBSTR(start_time_local, 1, 10)) FROM fact_activity "
                      "WHERE athlete_id = ? AND deleted_at IS NULL",
                      (athlete_id,)).fetchone()[0]
    lw = conn.execute(
        """SELECT MAX(calendar_date) FROM fact_daily_wellness
           WHERE athlete_id = ? AND (resting_hr IS NOT NULL OR sleep_score IS NOT NULL
                                     OR body_battery_high IS NOT NULL OR hrv_last_night IS NOT NULL)""",
        (athlete_id,)).fetchone()[0]
    conn.close()
    return la, lw


@st.cache_data(ttl=CACHE_TTL_SEC)
def load_splits(activity_id):
    conn = connect_db()
    df = pd.read_sql_query(
        "SELECT * FROM fact_activity_split WHERE activity_id = ? ORDER BY split_num ASC",
        conn, params=(activity_id,))
    conn.close()
    for col in df.columns:
        if col not in ("intensity_type",):  # text
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df




@st.cache_data(ttl=CACHE_TTL_SEC)
def load_race_predictions(athlete_id, start_date, end_date):
    """Garmin ทำนายเวลาแข่ง 5K/10K/HM/FM รายวัน (จาก fact_race_prediction)"""
    conn = connect_db()
    df = pd.read_sql_query(
        """SELECT calendar_date, time_5k_sec, time_10k_sec, time_half_sec, time_full_sec
           FROM fact_race_prediction
           WHERE athlete_id = ? AND calendar_date >= ? AND calendar_date <= ?
           ORDER BY calendar_date ASC""",
        conn, params=(athlete_id, start_date, end_date))
    conn.close()
    for col in df.columns:
        if col != "calendar_date":
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["calendar_date"] = pd.to_datetime(df["calendar_date"])
    return df


@st.cache_data(ttl=CACHE_TTL_SEC)
def load_personal_records(athlete_id):
    conn = connect_db()
    df = pd.read_sql_query(
        """SELECT record_type_id, record_label, value, achieved_date
           FROM fact_personal_record WHERE athlete_id = ? ORDER BY record_type_id ASC""",
        conn, params=(athlete_id,))
    conn.close()
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


@st.cache_data(ttl=CACHE_TTL_SEC)
def load_body_composition(athlete_id):
    """น้ำหนัก/BMI/ไขมันที่ Garmin เคยส่ง — โหลดทั้งประวัติเพื่อไม่ซ่อนค่าล่าสุด
    เพียงเพราะอยู่นอกช่วงวิเคราะห์ 30 วันที่เลือกใน sidebar."""
    conn = connect_db()
    df = pd.read_sql_query(
        """SELECT calendar_date, weight_kg, bmi, body_fat_pct
           FROM fact_body_composition
           WHERE athlete_id = ?
           ORDER BY calendar_date ASC""",
        conn,
        params=(athlete_id,),
    )
    conn.close()
    if not df.empty:
        df["calendar_date"] = pd.to_datetime(df["calendar_date"], errors="coerce")
        for column in ("weight_kg", "bmi", "body_fat_pct"):
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


@st.cache_data(ttl=CACHE_TTL_SEC)
def load_latest_lt(athlete_id):
    """Garmin Lactate Threshold ล่าสุด (hr, pace, วันที่) — None ถ้านาฬิกาไม่ให้"""
    conn = connect_db()
    row = conn.execute(
        """SELECT calendar_date, lactate_threshold_hr, lactate_threshold_pace_min_km
           FROM fact_daily_wellness
           WHERE athlete_id = ? AND (lactate_threshold_hr IS NOT NULL
                                     OR lactate_threshold_pace_min_km IS NOT NULL)
           ORDER BY calendar_date DESC LIMIT 1""", (athlete_id,)).fetchone()
    conn.close()
    return row




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

if not DB_PATH.exists():
    st.error(f"Database not found at {DB_PATH}. Please run the sync scripts first.")
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
# ป้ายแท็บเป็นค่าคงที่เพราะปุ่มบนการ์ดทีมสลับแท็บด้วยการเขียนป้ายลง session_state
# ถ้าปล่อยเป็นสตริงลอยสองที่ วันที่ใครแก้ป้าย ปุ่มจะเงียบไปโดยไม่มีอะไรฟ้อง
TAB_TODAY_LABEL = ":material/today: วันนี้"
MAIN_TAB_LABELS = [
    TAB_TODAY_LABEL,
    ":material/groups: ทีม",
    ":material/bedtime: การฟื้นตัว",
    ":material/directions_run: การซ้อม",
    ":material/trending_up: ความก้าวหน้า",
    ":material/query_stats: รายละเอียดเซสชัน",
]
MAIN_TABS_KEY = "main_tabs"


def focus_athlete(name):
    """การ์ดบนแท็บทีมคือประตูไปหน้ารายคน — เลือกนักกีฬาแล้วพาไปแท็บ "วันนี้" เลย

    ต้องตั้งสองคีย์คู่กันเสมอ: ตั้งแค่ชื่อจะเปลี่ยนคนแต่ค้างอยู่แท็บเดิม ตั้งแค่แท็บจะย้าย
    หน้าแต่ยังเป็นคนเดิม — ทั้งสองอย่างอ่านเหมือนปุ่มเสียพอ ๆ กัน
    """
    st.session_state[ATHLETE_STATE_KEY] = name
    st.session_state[MAIN_TABS_KEY] = TAB_TODAY_LABEL


# `on_change` คือสิ่งที่ทำให้แท็บมี state จริง ไม่ใช่ `key` — ในซอร์สของ Streamlit 1.61
# `is_stateful = on_change != "ignore"` ถ้าไม่ส่ง `on_change` มันจะไม่เรียก `register_widget`
# เลย แท็บที่ `focus_athlete()` เขียนลง session_state จะไม่มีใครอ่านกลับ = ปุ่มเงียบ
# และ `on_change` ยังเปิดทางให้เช็ค `.open` เพื่อรันเฉพาะแท็บที่เปิดอยู่ — รวมถึงตัว
# team snapshot เองที่อยู่ใต้บรรทัดนี้ เพราะมันต้องรู้ก่อนว่าแท็บไหนเปิดอยู่
tab_today, tab_team, tab_health, tab_train, tab_progress, tab_splits = st.tabs(
    MAIN_TAB_LABELS, key=MAIN_TABS_KEY, on_change="rerun"
)


# --- TEAM SNAPSHOT (state ข้ามแท็บ) ---
# สองแท็บใช้ค่าชุดนี้ร่วมกัน — แท็บทีมวาดการ์ดทุกคน แท็บวันนี้อ่านแถวของคนที่เลือก
# จึงคำนวณที่เดียวตรงนี้แล้วครอบด้วยเงื่อนไข "แท็บใดแท็บหนึ่งในสองนั้นเปิดอยู่"
#
# ต้องอยู่ *นอก* `with tab_x:` แต่ *ใน* เงื่อนไข — ถ้าย้ายกลับเข้าไปใน `with tab_team:`
# แท็บวันนี้จะ NameError ทันทีที่เปิดโดยไม่ผ่านแท็บทีมก่อน ส่วนถ้าปล่อยไว้นอกเงื่อนไข
# อีกสี่แท็บจะจ่ายค่าคำนวณย้อนหลัง 42 วันของนักกีฬาทุกคนทุกครั้งที่กดแท็บ ทั้งที่ไม่ได้ใช้
if tab_today.open or tab_team.open:
    team_rows = []
    for _, ath in athletes_df.iterrows():
        aid, name = ath["athlete_id"], ath["display_name"]

        # โหลดย้อน 42 วัน (training_load ถ้านาฬิกาให้ = จับ cross-training ครบ ไม่งั้นระยะวิ่ง)
        daily, metric, unit = load_daily_workload(
            aid, (today - datetime.timedelta(days=42)).isoformat(), today.isoformat())
        acute = chronic_wk = float("nan")
        sessions_7d = 0
        if not daily.empty:
            win7 = daily[daily["date"] >= pd.Timestamp(today - datetime.timedelta(days=6))]
            win28 = daily[daily["date"] >= pd.Timestamp(today - datetime.timedelta(days=27))]
            acute = win7["value"].sum()
            sessions_7d = int(win7["sessions"].sum())
            first = load_first_load_date(aid) if metric == "training_load" else load_first_run_date(aid)
            days_of_history = (today - first).days + 1 if first else 0
            if days_of_history >= 28 and win28["value"].sum() > 0:
                chronic_wk = win28["value"].sum() / 4

        # pace-HR trend ของรันเบา — บริบทประกอบเท่านั้น ไม่ใช้ตัดสินพร้อมซ้อม
        ath_lthr, _ = get_lthr(ath["slug"], aid)
        easy_ef = easy_run_efficiency(
            load_easy_runs(aid, (today - datetime.timedelta(days=70)).isoformat(),
                           today.isoformat()),
            ath_lthr,
        )
        ef_pct = efficiency_change_pct(easy_ef, today)

        # Wellness แต่ละ endpoint อาจมาคนละรอบ จึงเลือก "ล่าสุดแยกทีละ field"
        # แทนการใช้แถวเดียวแล้วทำให้ Sleep/HRV ที่ยังใช้ได้ถูกซ่อนโดย snapshot บางส่วนของวันนี้
        w = load_wellness_data(
            aid,
            (today - datetime.timedelta(days=HRV_TREND_LOOKBACK_DAYS - 1)).isoformat(),
            today.isoformat(),
        )
        sleep_snap = latest_field(w, "sleep_score")
        rhr_snap = latest_field(w, "resting_hr")
        hrv_snap = latest_field(w, "hrv_last_night")
        bb_display_snap, bb_completed_snap = body_battery_snapshots(w, today)
        ready_snap = latest_field(
            w,
            "training_readiness",
            ("readiness_timestamp_local", "readiness_timestamp_utc"),
        )
        train_snap = latest_field(w, "training_status")

        # วันนี้แสดงระดับล่าสุดระหว่างวัน; ธงใช้ high ล่าสุดของวันที่จบแล้วแยกกัน
        bb = bb_completed_snap["value"] if bb_completed_snap else float("nan")
        bb_now = bb_display_snap["value"] if bb_display_snap else float("nan")
        sleep = sleep_snap["value"] if sleep_snap else float("nan")
        rhr = rhr_snap["value"] if rhr_snap else float("nan")
        hrv_ms = hrv_snap["value"] if hrv_snap else float("nan")
        ready = ready_snap["value"] if ready_snap else float("nan")
        hrv_stat = fmt_text(hrv_snap["row"].get("hrv_status")) if hrv_snap else ""
        ready_level = fmt_text(ready_snap["row"].get("readiness_level")) if ready_snap else ""
        train_stat = fmt_text(train_snap["value"]) if train_snap else ""

        rhr_delta = float("nan")
        if rhr_snap and "resting_hr" in w:
            rhr_dates = pd.to_datetime(w["calendar_date"], errors="coerce").dt.date
            baseline = pd.to_numeric(
                w.loc[rhr_dates < rhr_snap["date"], "resting_hr"], errors="coerce"
            ).dropna()
            if pd.notna(rhr) and len(baseline) >= 7:
                rhr_delta = rhr - baseline.mean()

        core_snaps = [bb_display_snap, sleep_snap, rhr_snap, hrv_snap]
        fresh_core_count = sum(
            1 for snapshot in core_snaps
            if field_age_days(snapshot, today) is not None
            and 0 <= field_age_days(snapshot, today) <= 1
        )

        # สัญญาณให้ทบทวน — เก็บคู่กับค่าเพื่อให้แท็บวันนี้ตีกรอบไทล์ตรงกัน
        # ถ้าแท็บนั้นคำนวณเกณฑ์เองซ้ำ สองหน้าจะขัดกันเงียบ ๆ ทันทีที่เกณฑ์ฝั่งใดฝั่งหนึ่งขยับ
        flags = []
        flag_fields = []
        if pd.notna(sleep) and sleep < SLEEP_LOW and field_age_days(sleep_snap, today) <= 1:
            flags.append(f"Garmin Sleep อยู่หมวด Poor ({sleep:.0f})")
            flag_fields.append("sleep")
        if (hrv_stat in HRV_ALERT
                and field_age_days(hrv_snap, today) <= 1):
            flags.append(f"Garmin HRV {hrv_stat}")
            flag_fields.append("hrv")
        # Training Status ขึ้นกับอุปกรณ์/บัญชีและ endpoint; ใช้ค่าที่เคยได้รับจริงโดยไม่
        # เหมารวมกับ respiration หรือสรุปจาก NULL ว่าอุปกรณ์ไม่รองรับ
        # ค่าดิบมี suffix ตัวเลข เช่น STRAINED_1 / UNPRODUCTIVE_5 → ตัดเหลือคำหลักก่อนเทียบ
        _ts_base = (train_stat or "").split("_")[0]
        _ts_flag = {"STRAINED": "ล้าสะสม (Strained)",
                    "OVERREACHING": "โหลดเกินตัว (Overreaching)",
                    "UNPRODUCTIVE": "ซ้อมไม่ขึ้น (Unproductive)"}
        if (_ts_base in _ts_flag and train_snap
                and field_age_days(train_snap, today) <= 1):
            flags.append(f"Garmin: {_ts_flag[_ts_base]}")
        # Training Readiness: ประวัติปัจจุบันมีเฉพาะ P'kao ส่วน Tong/Dan ยังไม่เคยได้รับค่า;
        # นี่คือสถานะข้อมูล ไม่ใช่ข้อสรุปความสามารถของรุ่นนาฬิกา และค่าอัปเดตได้ระหว่างวัน
        if (ready_level in READINESS_ALERT and ready_snap
                and field_age_days(ready_snap, today) <= 1):
            flags.append(f"Readiness ต่ำ ({ready:.0f} {ready_level.title()})"
                         if pd.notna(ready) else f"Readiness {ready_level.title()}")
            flag_fields.append("readiness")

        # สรุปการมี/ไม่มีสัญญาณจากอุปกรณ์เท่านั้น ไม่ใช่ training clearance
        status = team_status(
            flags, not daily.empty, fresh_core_count,
            any(snapshot is not None for snapshot in core_snaps),
        )

        coverage_notes = []
        if fresh_core_count < 3:
            coverage_notes.append(f"wellness สด {fresh_core_count}/4 ค่า")
        freshness_note = " · ".join(
            f"{label} {snapshot['date'].strftime('%d/%m')}"
            for label, snapshot in (
                ("BB", bb_display_snap), ("Sleep", sleep_snap),
                ("RHR", rhr_snap), ("HRV", hrv_snap), ("Readiness", ready_snap),
            )
            if snapshot and snapshot.get("date")
        ) or "ไม่มี wellness"

        emoji, ef_txt = efficiency_status(ef_pct)
        # HRV trend เป็นตัวเลขประกอบแยกจาก Garmin HRV Status ไม่สร้างธงซ้ำ
        hrv_summary = hrv_trend_summary(w, today)
        hrv_pct = hrv_summary["pct"]
        hrv_trend_key, hrv_trend_txt = hrv_trend_status(hrv_pct)
        team_rows.append({
            "นักกีฬา": name,
            "สถานะ": status,
            # อยู่ต้นตาราง (ไม่ใช่ท้ายสุด) เพราะตารางนี้มี 13 คอลัมน์ กว้างเกินจอปกติ —
            # วางไว้ท้ายก่อนหน้านี้ทำให้มองข้ามว่า "ไม่ขึ้น" ทั้งที่จริงมีข้อมูล แค่ต้องเลื่อนดู
            "สถานะซ้อม (Garmin)": _ts_base.title() if _ts_base else "–",
            "pace–HR trend": efficiency_display(ef_pct),
            "สถานะ pace–HR": f"{emoji} {ef_txt}",
            "เทรนด์ HRV 7 คืน (%)": (f"{hrv_pct:+.1f}%" if pd.notna(hrv_pct) else "–"),
            "จำนวนคืน HRV ที่ใช้": (
                f'{hrv_summary["current_n"]}/{HRV_TREND_CURRENT_DAYS} คืน · '
                f'ฐาน {hrv_summary["baseline_n"]}/{HRV_TREND_BASELINE_DAYS} คืน'
            ),
            "สถานะเทรนด์ HRV": hrv_trend_txt if pd.notna(hrv_pct) else "",
            "โหลด 7 วัน": load_volume_display(acute, metric, unit),
            "ค่าเฉลี่ยโหลด 28 วัน": load_volume_display(
                chronic_wk, metric, f"{unit}/สัปดาห์"
            ),
            "เซสชัน 7 วัน": sessions_7d,
            "ขอบเขตโหลด": load_session_scope(metric),
            "Body Battery ตอนนี้/ล่าสุด": bb_now if pd.notna(bb_now) else None,
            "Sleep": sleep if pd.notna(sleep) else None,
            "RHR": rhr if pd.notna(rhr) else None,
            "ΔRHR": f"{rhr_delta:+.0f}" if pd.notna(rhr_delta) else "–",
            "HRV คืนล่าสุด": ((f"{hrv_ms:.0f} ms" + (f" · {hrv_stat}" if hrv_stat else ""))
                              if pd.notna(hrv_ms) else "–"),
            "Readiness": ready if pd.notna(ready) else None,
            "ความสดรายค่า": freshness_note,
            "ธงเฝ้าระวัง": (" | ".join(flags) if flags else "—")
                           + ((" · ข้อมูลไม่พอ: " + ", ".join(coverage_notes))
                              if status.startswith("⚪") and coverage_notes else ""),
            # สองคีย์ล่างนี้ไม่ได้ไว้อ่านบนตาราง — แท็บวันนี้ใช้ต่อ จึงถูกซ่อนจาก
            # "ดูตัวเลขทีมทั้งหมด" แต่ต้องอยู่ใน team_rows เพื่อให้สองแท็บใช้ค่าเดียวกัน
            "ธงเฝ้าระวังรายค่า": flag_fields,
            "pace–HR จากฐาน (%)": ef_pct,
        })

    team_df = pd.DataFrame(team_rows)
    TEAM_INTERNAL_COLUMNS = ["ธงเฝ้าระวังรายค่า", "pace–HR จากฐาน (%)", "สถานะเทรนด์ HRV",
                             "ขอบเขตโหลด"]


# =====================================================================
# TAB 2: TEAM OVERVIEW
# =====================================================================
# แท็บที่ไม่ได้เปิดอยู่ไม่ต้องสร้างกราฟ — plotly คือตัวกินเวลาหลักของหนึ่งรอบรัน
if tab_team.open:
    with tab_team:
        st.header("สัญญาณทีมวันนี้")
        st.caption(
            f"ข้อมูล ณ {today.isoformat()} — สรุปสิ่งที่อุปกรณ์ตรวจพบ ไม่ใช่คำสั่งพร้อมซ้อม/ต้องพัก · "
            "pace–HR และโหลดเป็นแนวโน้มประกอบ ต้องคุยอาการเจ็บ ป่วย ความล้า และบริบทกับนักกีฬา"
        )


        # การ์ดต่อคนแทนตารางสรุป 10 คอลัมน์ที่กว้างเกินจอ — คอลัมน์ท้าย ๆ เคยถูกมองข้าม
        # ทั้งที่มีข้อมูล แค่ต้องเลื่อนดู. เรียงตามความเร่งด่วน เพราะคำถามแรกของเช้าคือ
        # "ใครต้องดูก่อน" ไม่ใช่ "เรียงตามชื่อแล้วใครอยู่บนสุด"
        st.markdown(TEAM_CARD_CSS, unsafe_allow_html=True)
        ordered_team = sorted(team_rows, key=lambda item: team_urgency_rank(item["สถานะ"]))
        for order, row in enumerate(ordered_team):
            # การ์ดทั้งใบเป็นปุ่ม: ปุ่มจริงถูกวางทับทั้งใบแบบโปร่งใสด้วย CSS ที่เจาะจงผ่าน
            # คลาส st-key-* ซึ่ง Streamlit ติดให้ทุก container/widget ที่มี key
            # ถ้า CSS ไม่ทำงาน ปุ่มจะกลับไปอยู่ใต้การ์ดตามเดิม — เสียหน้าตา แต่ยังกดได้
            # ต่อลำดับท้ายคีย์เสมอ เพราะชื่อไทยสองชื่อที่ต่างกันแค่วรรณยุกต์จะถูกล้างเหลือ
            # สลักเดียวกัน แล้ว Streamlit จะโยน StreamlitDuplicateElementKey ทั้งหน้า
            slug = f"{css_key(row['นักกีฬา'])}-{order}"
            with st.container(key=f"teamcard-{slug}"):
                st.markdown(render_team_card(row), unsafe_allow_html=True)
                st.button(
                    f"ดูรายละเอียดของ {row['นักกีฬา']}",
                    key=f"open-athlete-{slug}",
                    on_click=focus_athlete,
                    args=(row["นักกีฬา"],),
                    width="stretch",
                )

        with st.expander("ดูตัวเลขทีมทั้งหมด", icon=":material/table_view:"):
            st.dataframe(
                # "สถานะ" กับ "สถานะ pace–HR" เก็บอีโมจิไว้เป็น *คีย์* ให้การ์ดแปลงเป็นรูปทรง
                # (การ์ดอ่านจาก `team_df` ก่อนบรรทัดนี้ จึงยังได้คีย์ครบ) — ตารางนี้เป็น
                # ข้อความล้วนที่คนอ่าน จึงต้องถอดคีย์ออกก่อน ไม่งั้นอีโมจิถึงตาโค้ชตรง ๆ
                team_df.drop(columns=TEAM_INTERNAL_COLUMNS).assign(
                    **{
                        column: (lambda frame, name=column: frame[name].map(
                            lambda value: status_parts(value)[1]))
                        for column in ("สถานะ", "สถานะ pace–HR")
                    }
                ),
                hide_index=True,
                column_config={
                    "นักกีฬา": st.column_config.TextColumn("นักกีฬา", pinned=True),
                    "pace–HR trend": st.column_config.TextColumn(
                        "แนวโน้ม pace–HR รันเบา"),
                    "Body Battery ตอนนี้/ล่าสุด": st.column_config.NumberColumn(
                        "Body Battery ตอนนี้/ล่าสุด", format="%.0f"),
                    "Sleep": st.column_config.NumberColumn("Sleep", format="%.0f"),
                    "RHR": st.column_config.NumberColumn("RHR", format="%.0f"),
                    "Readiness": st.column_config.NumberColumn("Readiness", format="%.0f"),
                    "สถานะซ้อม (Garmin)": st.column_config.TextColumn(
                        "สถานะซ้อม (Garmin)",
                        help="สถานะที่ Garmin คำนวณเองและขึ้นกับรุ่นนาฬิกา"),
                    "โหลด 7 วัน": st.column_config.TextColumn(
                        "โหลด 7 วัน",
                        help="ปริมาณดิบพร้อมหน่วยของตัวเอง — TL จาก Garmin ถ้านาฬิกาให้ "
                             "ไม่งั้นเป็นระยะวิ่ง (km) เทียบข้ามคนไม่ได้"),
                    "ค่าเฉลี่ยโหลด 28 วัน": st.column_config.TextColumn(
                        "ค่าเฉลี่ยโหลด 28 วัน",
                        help="แสดงแยกจากโหลด 7 วัน ไม่หารเป็น ACWR และไม่ใช้เป็นเส้นเสี่ยง"),
                    "เซสชัน 7 วัน": st.column_config.NumberColumn(
                        "เซสชัน 7 วัน", format="%d",
                        help="คนที่โหลดมาจาก TL นับทุกกิจกรรม "
                             "ส่วนคนที่ใช้ระยะวิ่งนับเฉพาะการวิ่ง"),
                },
            )

        with st.expander("เกณฑ์ที่ใช้ประเมิน", icon=":material/info:"):
            # คำอธิบายต้องใช้สัญลักษณ์เดียวกับที่การ์ดวาดจริง — เดิมเป็นอีโมจิ
            # ทั้งที่การ์ดเป็นรูปทรงวาดมาตั้งแต่ PR #32 โค้ชจึงเห็นคนละภาษาในหน้าเดียว
            # และบนกระดาษขาวดำคำอธิบายเหลือช่องว่างส่วนการ์ดยังอ่านได้
            def _legend_mark(key):
                return status_shape_svg(key, 11)

            st.markdown(
                "**สรุปสัญญาณจากอุปกรณ์:** "
                + _legend_mark("watch") + " ควรทบทวนก่อนซ้อม = มี Garmin signal อย่างน้อย 1 ข้อ · "
                + _legend_mark("ready")
                + " ไม่พบสัญญาณเตือนจากอุปกรณ์ = ไม่มี signal ในข้อมูลที่มี (ไม่ใช่ training clearance) · "
                + _legend_mark("unknown")
                + " ข้อมูลไม่พอ = ยังไม่มีข้อมูลซ้อม หรือ wellness สดน้อยกว่า 3/4 ค่า · "
                + _legend_mark("unknown")
                + " ไม่มีข้อมูล = ยังไม่มีทั้ง workload และ wellness",
                unsafe_allow_html=True,
            )
            # หน่วยของโหลดขึ้นกับรุ่นนาฬิกา ทีมนี้จึงมีทั้ง TL และ km พร้อมกัน
            # (วัดจริง 27 ส.ค. 69: 32.7 km · 92.6 km · 323 TL) — ถ้าไม่บอกไว้ตรงนี้
            # ตัวเลขดิบที่วางเรียงกันจะถูกอ่านว่าเทียบกันได้
            st.markdown(
                "**โหลด 7 วัน:** หน่วยขึ้นกับ**รุ่นนาฬิกา** — ได้ Garmin Training Load (TL) "
                "ถ้านาฬิกาส่งมา ไม่งั้นคิดจากระยะวิ่ง (km) **ตัวเลขดิบจึงเทียบข้ามคนไม่ได้** "
                "ระบบแสดงโหลด 7 วันกับค่าเฉลี่ย 28 วันแยกกันและไม่หารเป็น ACWR · "
                "จำนวนเซสชันก็คนละนิยาม: โหลดจาก TL นับทุกกิจกรรม ส่วนโหลดจากระยะวิ่งนับเฉพาะการวิ่ง"
            )
            st.markdown(r"""

    **นโยบาย Garmin-only:** ไม่มีแบบฟอร์มและไม่รวมค่าเป็นคะแนนความสดใหม่ของระบบ
    ก่อนซ้อมต้องถามปากเปล่าเรื่องอาการเจ็บ ป่วย และความล้าผิดปกติ

    **Garmin signals ที่แสดงให้ทบทวน:** Sleep อยู่หมวด Poor · HRV LOW/UNBALANCED ·
    Training Readiness LOW/POOR · Training Status Strained/Overreaching/Unproductive
    ค่ากลุ่มนี้สัมพันธ์และซ้อนองค์ประกอบกัน จึงไม่นับจำนวนเป็นคะแนนโหวต

    **แนวโน้ม pace–HR รันเบา** = ความเร็ว (ม./นาที) ÷ HR เฉลี่ย นับเฉพาะข้อมูลวิ่ง easy
    (HR ≤ 89% LTHR, ระยะรวม ≥ 3 กม.) โดยรวมหลาย activity ในวันเดียวเป็นหนึ่งค่ารายวัน
    แล้วเทียบ median 3 วันล่าสุดกับฐาน 28 วันก่อนหน้าที่ไม่ซ้อนกัน
    ค่านี้ไวต่อเพซ เส้นทาง ความชัน อากาศ การหยุด และ HR sensor จึงเป็นบริบทเท่านั้น
    ไม่ใช่ running economy หรือความสด และไม่มีเกณฑ์สั่งพัก/เพิ่มโหลด

    **ก่อนเปลี่ยนตาราง:** ต้องถามอาการเจ็บเฉพาะจุด/วิ่งเสียฟอร์ม อาการป่วย ไข้ เจ็บหน้าอก
    เวียนหัว ความล้า/ปวดกล้ามเนื้อ คุณภาพการนอน ความเครียด และเป้าหมายของเซสชัน
    หากมีอาการทางการแพทย์หรืออาการเจ็บที่เปลี่ยนการวิ่ง ให้หยุดประเมินโดยโค้ชอย่างเดียว
    และส่งต่อผู้เชี่ยวชาญที่เหมาะสม

    _โหลด 7 วันและค่าเฉลี่ย 28 วันเป็นบริบทแยกกัน ไม่ดันสถานะและไม่สร้าง ACWR ในชื่อใหม่_
    """)


    # =====================================================================
    # TAB 1: TODAY — เปิดมาเห็นข้อมูลของวันนี้ทันที
    # =====================================================================
# แท็บที่ไม่ได้เปิดอยู่ไม่ต้องสร้างกราฟ — plotly คือตัวกินเวลาหลักของหนึ่งรอบรัน
if tab_today.open:
    with tab_today:
        st.header(f"วันนี้ของ {selected_name}", anchor=f"today-{selected_anchor}")
        st.caption(
            f"{today.strftime('%d/%m/%Y')} · สรุปสัญญาณจากอุปกรณ์ ไม่ใช่คำอนุญาตให้ซ้อม · "
            "ค่าที่ยังไม่มาของวันนี้แสดงค่าล่าสุดพร้อมวันที่กำกับ"
        )

        selected_team = team_df[team_df["นักกีฬา"] == selected_name]
        team_row = selected_team.iloc[0] if not selected_team.empty else None
        # ค่าไหนเป็นคนจุดธง มาจากแท็บทีมโดยตรง ไม่ได้คำนวณเกณฑ์ซ้ำที่นี่
        flagged_fields = set(team_row["ธงเฝ้าระวังรายค่า"]) if team_row is not None else set()

        recent_wellness = load_wellness_data(
            athlete_id,
            (today - datetime.timedelta(days=HRV_TREND_LOOKBACK_DAYS - 1)).isoformat(),
            today.isoformat(),
        )
        today_wellness = load_wellness_data(athlete_id, today.isoformat(), today.isoformat())
        # ดึงย้อน 14 วันเพราะวันพักต้องยังมีของให้ดู — วันที่ไม่มีกิจกรรมไม่ใช่วันที่ไม่มีบริบท
        recent_activities = load_activity_data(
            athlete_id, (today - datetime.timedelta(days=13)).isoformat(), today.isoformat()
        )
        if not recent_activities.empty:
            recent_activities = recent_activities.copy()
            recent_activities["start_time_local"] = pd.to_datetime(
                recent_activities["start_time_local"]
            )
            recent_activities["distance_km"] = recent_activities["distance_m"] / 1000
            recent_activities = recent_activities.sort_values(
                "start_time_local", ascending=False
            )
            today_activities = recent_activities[
                recent_activities["start_time_local"].dt.date == today
            ]
        else:
            today_activities = recent_activities

        readiness_supported = athlete_has_training_readiness(athlete_id)
        training_load_supported = athlete_has_load(athlete_id)
        device_names = load_athlete_devices(athlete_id)

        st.markdown(TODAY_PANEL_CSS, unsafe_allow_html=True)

        # ---- สรุปสัญญาณ: อ่านก่อนตัวเลขรายละเอียด ----
        # สถานะโหลดต้องเตือนแม้ wellness วันนี้ยังไม่มา จึงวาดก่อนอ่านค่า wellness ทั้งหมด
        # และไม่ผูกอยู่กับเงื่อนไขใด ๆ ของ wellness
        if team_row is not None:
            st.markdown(render_today_verdict(team_row), unsafe_allow_html=True)

        # ---- ค่าจากอุปกรณ์ที่ใช้เป็นบริบท ----
        bb_snap, bb_completed_snap = body_battery_snapshots(recent_wellness, today)
        sleep_snap = latest_field(recent_wellness, "sleep_score")
        rhr_snap = latest_field(recent_wellness, "resting_hr")
        hrv_snap = latest_field(recent_wellness, "hrv_last_night")
        ready_snap = latest_field(
            recent_wellness,
            "training_readiness",
            ("readiness_timestamp_local", "readiness_timestamp_utc"),
        )
        hrv_status = fmt_text(hrv_snap["row"].get("hrv_status")) if hrv_snap else ""
        readiness_level = fmt_text(ready_snap["row"].get("readiness_level")) if ready_snap else ""

        wellness_history = (
            recent_wellness.sort_values("calendar_date")
            if not recent_wellness.empty else recent_wellness
        )

        def recent_series(column):
            """ค่า 14 วันล่าสุดของฟิลด์เดียว สำหรับเส้นแนวโน้มเล็กใต้ไทล์"""
            if wellness_history.empty or column not in wellness_history.columns:
                return []
            return list(wellness_history[column].tail(14))

        def fresh_short(snapshot):
            """"วันนี้" / "เมื่อวาน" / "3 วันก่อน" — วันที่เต็มอยู่ใน expander ด้านล่าง"""
            return field_freshness(snapshot, today).split(" · ")[-1]

        def snapshot_value(snapshot):
            return snapshot["value"] if snapshot else float("nan")

        def snapshot_anchor(snapshot):
            return snapshot["date"] if snapshot and snapshot.get("date") else today

        # Body Battery: ตัวเลขใหญ่คือระดับล่าสุดระหว่างวัน แต่ฐานเทียบได้เฉพาะ high ของวันที่
        # จบแล้ว — สองอย่างนี้คนละหน่วยความหมาย จึงเขียนแยกให้เห็น ไม่เอามาลบกันเงียบ ๆ
        bb_completed_value = snapshot_value(bb_completed_snap)
        bb_note = tile_note(
            bb_completed_value,
            baseline_median(recent_wellness, "body_battery_high",
                            snapshot_anchor(bb_completed_snap)),
        )
        if pd.notna(bb_completed_value) and bb_note:
            bb_note = f"high วันล่าสุด {fmt_num(bb_completed_value)} · {bb_note}"

        hrv_note = tile_note(
            snapshot_value(hrv_snap),
            baseline_median(recent_wellness, "hrv_last_night", snapshot_anchor(hrv_snap)),
        )
        if hrv_status:
            hrv_note = f"Garmin: {hrv_status.replace('_', ' ')}" + (f" · {hrv_note}" if hrv_note else "")

        ready_note = tile_note(
            snapshot_value(ready_snap),
            baseline_median(recent_wellness, "training_readiness", snapshot_anchor(ready_snap)),
        )
        if readiness_level:
            ready_note = f"Garmin: {readiness_level.replace('_', ' ')}" + (
                f" · {ready_note}" if ready_note else ""
            )

        tile_specs = [
            # ตัวเลขใหญ่คือระดับ ณ ตอนนี้ (ตกลงตลอดวันตามปกติ) ป้ายจึงต้องบอกเองว่านี่ไม่ใช่
            # ค่าสูงสุดของวัน ไม่งั้น "5" ตอนสี่ทุ่มอ่านเหมือนสัญญาณอันตราย
            ("BODY BATTERY ตอนนี้/ล่าสุด", bb_snap, "body_battery_high", "", bb_note,
             "bb", "watch"),
            ("SLEEP SCORE", sleep_snap, "sleep_score", "",
             tile_note(snapshot_value(sleep_snap),
                       baseline_median(recent_wellness, "sleep_score",
                                       snapshot_anchor(sleep_snap))),
             "sleep", "watch"),
            ("RESTING HR", rhr_snap, "resting_hr", " bpm",
             tile_note(snapshot_value(rhr_snap),
                       baseline_median(recent_wellness, "resting_hr",
                                       snapshot_anchor(rhr_snap))),
             "rhr", "watch"),
            ("HRV คืนล่าสุด", hrv_snap, "hrv_last_night", " ms", hrv_note, "hrv",
             HRV_ALERT.get(hrv_status, "watch")),
        ]
        # ไทล์ความพร้อมซ้อมขึ้นเฉพาะนักกีฬาที่บัญชีเคยส่งค่านี้จริง — ช่องว่างถาวรของคนที่
        # นาฬิกาไม่ส่ง อ่านได้ว่าระบบพัง ทั้งที่คำอธิบายอยู่ใน expander ด้านล่างแล้ว
        if readiness_supported or ready_snap:
            tile_specs.append(
                ("ความพร้อมซ้อม (Garmin)", ready_snap, "training_readiness", "", ready_note,
                 "readiness", "watch")
            )

        st.markdown(
            '<div class="today-tiles">'
            + "".join(
                render_today_tile(
                    label,
                    fmt_num(snapshot_value(snapshot), suffix),
                    fresh_short(snapshot),
                    note,
                    sparkline_svg(recent_series(column)),
                    alert_key if field in flagged_fields else None,
                )
                for label, snapshot, column, suffix, note, field, alert_key in tile_specs
            )
            + "</div>",
            unsafe_allow_html=True,
        )

        # ---- pace-HR trend กับบริบทโหลดข้างกัน ----
        if team_row is not None:
            ef_zone_key, ef_zone_label = status_parts(team_row["สถานะ pace–HR"])
            ef_pct_value = team_row["pace–HR จากฐาน (%)"]
            ef_color = STATUS_TEXT_COLORS.get(ef_zone_key, STATUS_TEXT_COLORS["unknown"])

            left, right = st.columns([1.05, 1.35], gap="large")
            with left:
                # ค่าว่างต้องบอกเหตุผลตรงจุดที่มันว่าง ไม่งั้นโค้ชอ่านว่า sync พัง
                ef_body = (
                    f'<div style="display:flex;align-items:baseline;gap:10px">'
                    f'<div class="today-ef__val" style="color:{ef_color}">'
                    f'{ef_pct_value:+.1f}%</div>'
                    f'<div style="font-size:13px;color:#55585f">จากฐานก่อนหน้าที่ไม่ซ้อนกัน</div></div>'
                    f'<div style="font-size:12px;color:#55585f;margin-top:5px">'
                    f'{status_shape_svg(ef_zone_key, 9)} {html.escape(ef_zone_label)}</div>'
                    '<div style="font-size:12px;color:#55585f;margin-top:7px;line-height:1.6">'
                    'ไม่ใช่ running economy หรือความสด; เส้นทาง เพซ ความชัน อากาศ การหยุด '
                    'และ HR sensor ทำให้ค่าเปลี่ยนได้</div>'
                    if pd.notna(ef_pct_value) else
                    '<div class="today-ef__val" style="color:#8a8d94">–</div>'
                    '<div style="font-size:12px;color:#55585f;margin-top:5px;line-height:1.6">'
                    'ต้องมีข้อมูลวิ่ง easy 3 วันภายใน 14 วัน และฐานอย่างน้อย 5 วันใน 28 วันก่อนหน้า '
                    '— ยังไม่ครบตามนี้ ไม่ใช่ระบบขัดข้อง</div>'
                )
                st.markdown(
                    '<div class="today-panel"><div class="today-panel__head">'
                    '<div class="today-panel__title">แนวโน้ม pace–HR ของรันเบา</div>'
                    '<div class="today-panel__hint">บริบทประกอบ</div></div>'
                    + ef_body + "</div>",
                    unsafe_allow_html=True,
                )
            with right:
                strip_daily, strip_metric, strip_unit = load_daily_workload(
                    athlete_id, (today - datetime.timedelta(days=6)).isoformat(),
                    today.isoformat(),
                )
                by_date = {}
                if not strip_daily.empty:
                    by_date = {
                        row["date"].date(): row["value"]
                        for _, row in strip_daily.iterrows()
                    }
                strip_days = [
                    (
                        (today - datetime.timedelta(days=offset)).strftime("%d/%m"),
                        by_date.get(today - datetime.timedelta(days=offset)),
                    )
                    for offset in range(6, -1, -1)
                ]
                st.markdown(
                    '<div class="today-panel"><div class="today-panel__head">'
                    f'<div class="today-panel__title">โหลดรายวัน 7 วัน ({html.escape(strip_unit)})</div>'
                    '<div class="today-panel__hint">บริบท ไม่ได้ตัดสินสถานะ</div></div>'
                    + render_load_strip(
                        strip_days, digits=0 if strip_metric == "training_load" else 1
                    )
                    + '<div style="font-size:13px;color:#55585f;margin-top:12px">รวม 7 วัน '
                    f'{html.escape(str(team_row["โหลด 7 วัน"] or "–"))} · '
                    f'เฉลี่ย 28 วัน {html.escape(str(team_row["ค่าเฉลี่ยโหลด 28 วัน"] or "–"))} · '
                    f'{html.escape(str(team_row["เซสชัน 7 วัน"] or 0))} เซสชัน'
                    f' ({html.escape(str(team_row["ขอบเขตโหลด"] or "วิ่ง"))})</div></div>',
                    unsafe_allow_html=True,
                )

        # ---- เซสชันจริง ----
        lthr_today, _ = get_lthr(selected_slug, athlete_id)
        if not today_activities.empty:
            session_rows, session_hint = today_activities, "กิจกรรมของวันนี้"
        else:
            # วันพักไม่ได้แปลว่าไม่มีอะไรให้ดู — ของสามครั้งก่อนหน้าคือบริบทของวันนี้
            session_rows = recent_activities.head(3)
            session_hint = "วันนี้ยังไม่มีกิจกรรม · แสดง 3 ครั้งก่อนหน้า"

        if session_rows.empty:
            st.markdown(
                '<div class="today-panel"><div class="today-panel__title">เซสชัน</div>'
                '<div style="font-size:13px;color:#55585f;margin-top:8px">'
                'ยังไม่มีกิจกรรมที่บันทึกใน 14 วันล่าสุด</div></div>',
                unsafe_allow_html=True,
            )
        else:
            header = "".join(
                f'<div class="today-lbl" style="{align}">{title}</div>'
                for title, align in (
                    ("วันที่", ""), ("รายการ", ""), ("ระยะ", "text-align:right"),
                    ("เวลา", "text-align:right"), ("เพซ", "text-align:right"),
                    ("HR", "text-align:right"), ("ความหนัก", "text-align:right"),
                )
            )
            body = "".join(
                render_session_row(
                    activity["start_time_local"].strftime("%d/%m %H:%M")
                    if pd.notna(activity["start_time_local"]) else "ไม่ทราบเวลา",
                    fmt_text(activity.get("activity_name"),
                             fmt_text(activity.get("activity_type"), "กิจกรรม")),
                    activity.get("distance_km"),
                    activity.get("duration_sec"),
                    activity.get("avg_pace_min_per_km"),
                    activity.get("avg_hr"),
                    classify_intensity(activity.get("avg_hr"), lthr_today),
                )
                for _, activity in session_rows.iterrows()
            )
            st.markdown(
                '<div class="today-panel"><div class="today-panel__head">'
                '<div class="today-panel__title">เซสชัน</div>'
                f'<div class="today-panel__hint">{html.escape(session_hint)}</div></div>'
                f'<div class="today-sess__head">{header}</div>{body}</div>',
                unsafe_allow_html=True,
            )

        # ---- คำอธิบายที่อ่านครั้งเดียวแล้วไม่ต้องอ่านอีก ----
        with st.expander("วันที่ของแต่ละค่า และค่าที่นาฬิกายังไม่ส่ง", icon=":material/info:"):
            st.markdown(
                "**วันที่ของแต่ละค่า** — "
                + " · ".join(
                    f"{label}: "
                    + (readiness_when(snapshot, today) if label == "Readiness"
                       else field_freshness(snapshot, today))
                    for label, snapshot in (
                        ("BB", bb_snap), ("Sleep", sleep_snap), ("RHR", rhr_snap),
                        ("HRV", hrv_snap), ("Readiness", ready_snap),
                    )
                )
            )

            pending_today = []
            for label, column in (("Sleep", "sleep_score"), ("HRV", "hrv_last_night")):
                if latest_field(today_wellness, column) is None:
                    pending_today.append(label)
            if readiness_supported and latest_field(today_wellness, "training_readiness") is None:
                pending_today.append("Training Readiness")
            if not has_any_value(
                today_wellness,
                ["resting_hr", "sleep_score", "body_battery_high", "bb_most_recent",
                 "hrv_last_night"],
            ):
                st.markdown(
                    "ยังไม่มีข้อมูลสุขภาพของวันนี้จากนาฬิกา "
                    "จึงแสดงค่าล่าสุดที่ยังใช้ได้พร้อมวันที่กำกับ"
                )
            if pending_today:
                st.markdown(
                    "Garmin ยังไม่มีค่า " + ", ".join(pending_today)
                    + " ของวันนี้ ระบบจะลองเติมในรอบ sync ถัดไป; ค่าที่แสดงจากวันก่อนมีวันที่กำกับ "
                      "และไม่ได้ถูกคาดเดา"
                )
            if not readiness_supported:
                models = ", ".join(device_names) if device_names else "ยังไม่มีทะเบียนอุปกรณ์ที่สดพอ"
                st.markdown(
                    "ยังไม่เคยได้รับ Training Readiness จากบัญชีนี้ในประวัติที่เก็บไว้ "
                    f"(อุปกรณ์ที่เคยพบ: {models}; กรองรายการที่ยืนยันว่า last_seen เกิน 90 วัน) "
                    "อาจเกิดจากความสามารถของอุปกรณ์ การตั้งค่าบัญชี "
                    "หรือ endpoint ไม่ส่งข้อมูล จึงยังไม่สรุปจากค่าว่างเพียงอย่างเดียวว่า ‘รุ่นไม่รองรับ’"
                )
            if not training_load_supported:
                st.markdown(
                    "ยังไม่เคยได้รับ Garmin Training Load จากกิจกรรมที่เก็บไว้; "
                    "โหลดสะสมของระบบจึงคำนวณจากระยะวิ่งและระบุแหล่งที่มาชัดเจน"
                )


    # =====================================================================
    # TAB 3: HEALTH & RECOVERY (นักกีฬาที่เลือก)
    # =====================================================================
# แท็บที่ไม่ได้เปิดอยู่ไม่ต้องสร้างกราฟ — plotly คือตัวกินเวลาหลักของหนึ่งรอบรัน
if tab_health.open:
    with tab_health:
        st.header(f"การฟื้นตัว — {selected_name}", anchor=f"recovery-{selected_anchor}")
        st.caption(f"ค่าเฉลี่ยและแนวโน้มระหว่าง {start_date.strftime('%d/%m/%Y')}–{end_date.strftime('%d/%m/%Y')}")

        if wellness_df.empty:
            st.info("ไม่มีข้อมูลสุขภาพในช่วงเวลานี้")
        else:
            # Sleep/RHR เป็นค่าหลังคืนสิ้นสุดและใช้ของวันนี้ได้; BB-high/Stress เป็น
            # intraday aggregates ที่ยังเปลี่ยนถึงเที่ยงคืน จึงไม่นับวันนี้เฉพาะสองค่านั้น
            average_specs = [
                ("Sleep score เฉลี่ย", "sleep_score", "", False),
                ("Body Battery สูงสุดเฉลี่ย", "body_battery_high", "", True),
                ("Resting HR เฉลี่ย", "resting_hr", " bpm", False),
                ("Stress เฉลี่ย", "stress_avg", "", True),
            ]
            average_results = {
                column: period_metric(
                    wellness_df, column, today, exclude_today, start_date, end_date
                )
                for _, column, _, exclude_today in average_specs
            }
            # เหตุผลว่าทำไม denominator ของแต่ละการ์ดไม่เท่ากันอยู่ใน help ของการ์ดนั้นเอง
            # ไม่ใช่ย่อหน้าใต้แถว — คนที่สงสัยการ์ดไหนจะจิ้มการ์ดนั้น
            with st.container(horizontal=True):
                for label, column, unit, exclude_today_metric in average_specs:
                    result = average_results[column]
                    sample_note = (
                        f"{result['count']}/{result['total_days']} วันมีข้อมูล"
                        if result["total_days"] else "ไม่มีวันเต็มในช่วง"
                    )
                    st.metric(
                        label, fmt_num(result["mean"], unit), delta=sample_note,
                        delta_color="off", border=True,
                        help=(
                            "mean() ใช้เฉพาะวันที่มีค่าจริง; วันที่ว่างไม่ถูกแทนด้วยศูนย์ · "
                            + ("ไม่นับวันนี้ซึ่งค่ายังเปลี่ยนถึงเที่ยงคืน"
                               if exclude_today_metric
                               else "นับวันนี้ได้เพราะค่าสรุปหลังจบคืนแล้ว")
                            + " · กราฟและตารางยังแสดงวันนี้พร้อมเส้นประ"
                        ),
                    )

            quality_flags = wellness_quality_flags(wellness_df)
            if quality_flags:
                st.warning(
                    f"พบ {len(quality_flags)} กลุ่มค่าที่ควรตรวจเทียบนาฬิกา — "
                    "ยังคงค่าดิบไว้และรวมในค่าเฉลี่ย ไม่ตัด outlier อัตโนมัติ",
                    icon=":material/data_alert:",
                )
                with st.expander("ดูค่าที่ควรตรวจทาน", icon=":material/troubleshoot:"):
                    for note in quality_flags:
                        st.markdown(f"- {note}")

            # --- Sleep / Body Battery: สร้างเฉพาะ trace ที่มีข้อมูลและใช้ชื่อที่คนอ่านเข้าใจ ---
            health_series = available_series(wellness_df, {
                "sleep_score": "คะแนนการนอน",
                "body_battery_high": "Body Battery สูงสุดของวัน",
            })
            if health_series:
                fig_health = go.Figure()
                for column, label in health_series:
                    # จำนวนจุดที่มีจริงอยู่ใน legend ข้าง ๆ เส้นนั้นเอง แทน caption ใต้กราฟ
                    # ที่ไล่ทุกเส้นรวดเดียว — ช่องว่างบนเส้นคือวันที่ Garmin ไม่มีค่า
                    filled = int(wellness_plot_df[column].notna().sum())
                    fig_health.add_trace(go.Scatter(
                        x=wellness_plot_df["calendar_date"], y=wellness_plot_df[column],
                        mode="lines+markers", connectgaps=False,
                        name=f"{label} ({filled}/{len(wellness_plot_df)} วัน)",
                        line=dict(color=SERIES_COLORS[column]),
                        hovertemplate=f"%{{x|%d %b}}<br>{label}: %{{y:.0f}}<extra></extra>",
                    ))
                fig_health.update_layout(
                    title="แนวโน้มคะแนนการนอนและ Body Battery สูงสุดของวัน",
                    xaxis_title="วันที่", yaxis_title="คะแนน", hovermode="x unified",
                )
                mark_partial_today(fig_health, today, start_date, end_date)
                st.plotly_chart(fig_health, width="stretch")

            # --- Stress กับ Readiness มีทิศทางความหมายตรงข้าม จึงแยกแกนและบอกชัด ---
            stress_ready_series = available_series(wellness_df, {
                "stress_avg": "Stress เฉลี่ย (สูง = แย่)",
                "training_readiness": "Training Readiness (สูง = ดี)",
            })
            if stress_ready_series:
                # ทั้งคู่เป็นคะแนน 0–100 จึงอยู่แกนเดียวกันได้ตรง ๆ (กฎกราฟ 01)
                # แกนขวาเดิมไม่ได้เพิ่มอะไรนอกจากทำให้จุดตัดของสองเส้นดูมีความหมาย
                fig_stress = go.Figure()
                for column, label in stress_ready_series:
                    fig_stress.add_trace(go.Scatter(
                        x=wellness_plot_df["calendar_date"], y=wellness_plot_df[column],
                        mode="lines+markers", name=label, connectgaps=False,
                        line=dict(color=SERIES_COLORS[column]),
                        hovertemplate=f"%{{x|%d %b}}<br>{label}: %{{y:.0f}}<extra></extra>",
                    ))
                fig_stress.update_layout(
                    title=chart_title(stress_ready_series, {
                        frozenset({"stress_avg", "training_readiness"}):
                            "Stress เทียบ Training Readiness",
                        frozenset({"stress_avg"}): "แนวโน้ม Stress เฉลี่ย",
                        frozenset({"training_readiness"}): "แนวโน้ม Training Readiness",
                    }),
                    xaxis_title="วันที่",
                    hovermode="x unified",
                )
                # ทิศทางการอ่านอยู่บนแกน ไม่ต้องมี caption ใต้กราฟมาอธิบายซ้ำ
                fig_stress.update_yaxes(
                    title_text=(
                        "คะแนน 0–100 · Stress สูง = แย่ · Readiness สูง = ดี"
                        if len(stress_ready_series) > 1
                        else "คะแนน 0–100 · " + (
                            "สูง = แย่"
                            if stress_ready_series[0][0] == "stress_avg" else "สูง = ดี"
                        )
                    ),
                    range=[0, 100],
                )
                mark_partial_today(fig_stress, today, start_date, end_date)
                st.plotly_chart(fig_stress, width="stretch")
            # เดิมมี caption อธิบายว่าทำไมไม่มีเส้น Readiness ตรงนี้ — ตัดออกแล้วเพราะ
            # หัวข้อกราฟไม่เอ่ยถึงค่าที่ไม่ได้วาดอีกต่อไป (`chart_title`) จึงไม่มีอะไรให้แก้ต่าง
            # และหัวข้อ "ความพร้อมซ้อม" ด้านล่างบอกเรื่องอุปกรณ์ไว้ที่เดียวแล้ว

            # --- RHR / HRV recovery trends ---
            # bpm กับ ms เป็นคนละหน่วยจริง จึงเป็นคนละกราฟ ไม่ใช่แกนขวา (กฎกราฟ 01)
            recovery_trend_specs = [
                (
                    {"resting_hr": "Resting HR"},
                    "แนวโน้ม Resting HR", "ครั้ง/นาที (bpm)",
                ),
                (
                    {
                        "hrv_last_night": "HRV คืนล่าสุด",
                        "hrv_weekly_avg": "HRV เฉลี่ย 7 วัน",
                    },
                    "แนวโน้ม HRV", "มิลลิวินาที (ms)",
                ),
            ]
            for label_map, figure_title, axis_title in recovery_trend_specs:
                trend_series = available_series(wellness_df, label_map)
                if not trend_series:
                    continue
                fig_trend = go.Figure()
                for column, label in trend_series:
                    fig_trend.add_trace(go.Scatter(
                        x=wellness_plot_df["calendar_date"], y=wellness_plot_df[column],
                        mode="lines+markers", name=label, connectgaps=False,
                        line=dict(color=SERIES_COLORS[column],
                                  dash="dot" if column == "hrv_weekly_avg" else "solid"),
                        hovertemplate=f"%{{x|%d %b}}<br>{label}: %{{y:.0f}}<extra></extra>",
                    ))
                fig_trend.update_layout(
                    title=figure_title, xaxis_title="วันที่", yaxis_title=axis_title,
                    hovermode="x unified", showlegend=len(trend_series) > 1,
                )
                mark_partial_today(fig_trend, today, start_date, end_date)
                st.plotly_chart(fig_trend, width="stretch")

            # --- ค่าเฉลี่ยเสริม พร้อม sample count เหมือนการ์ดหลัก ---
            extra_specs = [
                ("หายใจตอนตื่น", "avg_waking_respiration", " brpm", True),
                ("หายใจตอนนอน", "avg_sleep_respiration", " brpm", False),
                ("Stress สูงสุดเฉลี่ย", "max_stress", "", True),
                ("Floors/วัน", "floors_ascended", "", True),
                ("Active kcal/วัน", "active_kilocalories", " kcal", True),
            ]
            extra_results = []
            for label, column, unit, exclude_today in extra_specs:
                result = period_metric(
                    wellness_df, column, today, exclude_today, start_date, end_date
                )
                if pd.notna(result["mean"]):
                    extra_results.append((label, unit, result))
            if extra_results:
                with st.container(horizontal=True):
                    for label, unit, result in extra_results:
                        st.metric(
                            label, fmt_num(result["mean"], unit),
                            delta=f"{result['count']}/{result['total_days']} วันมีข้อมูล",
                            delta_color="off", border=True,
                        )

            # --- Respiration trend: เปิดเมื่อมีค่าตอนตื่นหรือตอนนอนอย่างใดอย่างหนึ่ง ---
            respiration_series = available_series(wellness_df, {
                "avg_sleep_respiration": "ขณะนอน",
                "avg_waking_respiration": "ขณะตื่น",
            })
            if respiration_series:
                fig_resp = go.Figure()
                for column, label in respiration_series:
                    fig_resp.add_trace(go.Scatter(
                        x=wellness_plot_df["calendar_date"], y=wellness_plot_df[column],
                        mode="lines+markers", name=label, connectgaps=False,
                        hovertemplate=f"%{{x|%d %b}}<br>{label}: %{{y:.1f}} brpm<extra></extra>",
                    ))
                fig_resp.update_layout(
                    title="อัตราการหายใจ — ขณะนอนเทียบขณะตื่น",
                    xaxis_title="วันที่", yaxis_title="ครั้ง/นาที (brpm)", hovermode="x unified",
                )
                mark_partial_today(fig_resp, today, start_date, end_date)
                st.plotly_chart(fig_resp, width="stretch")

            # --- Garmin Readiness / Recovery: เปิดเมื่อ field ใด field หนึ่งมีค่า ไม่ผูกกับ ACWR factor ---
            readiness_section_fields = [
                "training_readiness", "recovery_time_min",
                "acute_load", "acwr_percent", "hrv_factor_pct", "stress_history_pct",
                "readiness_sleep_factor_pct", "recovery_time_factor_pct",
                "training_status",
            ]
            if has_any_value(wellness_df, readiness_section_fields):
                st.subheader("ความพร้อมซ้อมและเวลาฟื้นตัวจาก Garmin")
                ready_snap = latest_field(
                    wellness_df, "training_readiness",
                    ("readiness_timestamp_local", "readiness_timestamp_utc"),
                )
                recovery_snap = latest_field(wellness_df, "recovery_time_min")
                acute_snap = latest_field(wellness_df, "acute_load")
                acwr_factor_snap = latest_field(wellness_df, "acwr_percent")
                ready_level = fmt_text(ready_snap["row"].get("readiness_level")) if ready_snap else ""
                with st.container(horizontal=True):
                    st.metric(
                        "Readiness ล่าสุด",
                        fmt_num(ready_snap["value"] if ready_snap else float("nan")),
                        delta=ready_level.replace("_", " ") or None,
                        delta_color="off", border=True,
                        help=readiness_when(ready_snap, today),
                    )
                    st.metric(
                        "Recovery Time",
                        fmt_recovery_time(get_recovery_minutes(recovery_snap["row"])
                                          if recovery_snap else float("nan")),
                        border=True,
                        help=("Garmin ส่งหน่วยเป็นนาที; Dashboard แปลงเป็นชั่วโมง+นาที · "
                              + field_freshness(recovery_snap, today)),
                    )
                    st.metric(
                        "Acute Load ล่าสุด",
                        fmt_num(acute_snap["value"] if acute_snap else float("nan")),
                        border=True, help=field_freshness(acute_snap, today),
                    )
                    st.metric(
                        "ปัจจัย Acute Load ต่อ Readiness",
                        (f"{fmt_num(acwr_factor_snap['value'])}%" if acwr_factor_snap else "–"),
                        help=("คะแนนองค์ประกอบที่ Garmin ใช้คำนวณ Training Readiness; "
                              "เป็นคะแนนปัจจัยของ Garmin Readiness ไม่ใช่โหลดสะสมที่ Dashboard คำนวณในแท็บการซ้อม · "
                              + field_freshness(acwr_factor_snap, today)),
                        border=True,
                    )

                # ความสดของแต่ละค่าอยู่ใน help ของการ์ดนั้นแล้ว จึงไม่ต้องมี caption
                # ไล่ทั้งสี่ค่าซ้ำอีกรอบ · ส่วนคำบรรยายของ Garmin เป็นคำของ Garmin
                # ไม่ใช่ตัวเลขที่ต้องตัดสินใจ จึงลงไปอยู่ในกล่องพับด้านล่างที่เดียว
                garmin_notes = []
                if ready_snap:
                    ready_row = ready_snap["row"]
                    feedback = (fmt_text(ready_row.get("readiness_feedback_long"))
                                or fmt_text(ready_row.get("readiness_feedback")))
                    if feedback:
                        garmin_notes.append(("Garmin feedback ล่าสุด", feedback))
                    input_context = fmt_text(ready_row.get("readiness_input_context"))
                    if input_context:
                        garmin_notes.append(("Readiness input context", input_context))
                if recovery_snap:
                    change_phrase = fmt_text(recovery_snap["row"].get("recovery_time_change_phrase"))
                    if change_phrase:
                        garmin_notes.append(("สถานะ Recovery Time", change_phrase))

                if has_any_value(wellness_df, ["training_readiness"]):
                    fig_ready = go.Figure(go.Scatter(
                        x=wellness_plot_df["calendar_date"], y=wellness_plot_df["training_readiness"],
                        mode="lines+markers", name="Training Readiness", connectgaps=False,
                        line=dict(color=SERIES_COLORS["training_readiness"]),
                        hovertemplate="%{x|%d %b}<br>Readiness: %{y:.0f}<extra></extra>",
                    ))
                    fig_ready.add_hrect(y0=0, y1=50, fillcolor=C_CRIT, opacity=0.08, line_width=0)
                    fig_ready.update_layout(
                        title="แนวโน้ม Training Readiness (0–100)",
                        xaxis_title="วันที่", yaxis_title="Readiness (สูง = ดี)", showlegend=False,
                    )
                    mark_partial_today(fig_ready, today, start_date, end_date)
                    st.plotly_chart(fig_ready, width="stretch")

                recovery_minutes = recovery_minutes_series(wellness_plot_df)
                if recovery_minutes.notna().any():
                    recovery_labels = recovery_minutes.map(
                        lambda value: fmt_recovery_time(value) if pd.notna(value) else "ไม่มีข้อมูล"
                    )
                    fig_recovery = go.Figure(go.Scatter(
                        # Keep every calendar row: NaN in y now creates the intended
                        # visible gap because connectgaps=False instead of being masked out.
                        x=wellness_plot_df["calendar_date"],
                        y=recovery_minutes / 60,
                        customdata=recovery_labels,
                        mode="lines+markers", name="Recovery Time", connectgaps=False,
                        line=dict(color=SERIES_COLORS["recovery_time"]),
                        hovertemplate="%{x|%d %b}<br>Recovery Time: %{customdata}<extra></extra>",
                    ))
                    fig_recovery.update_layout(
                        title="แนวโน้ม Recovery Time", xaxis_title="วันที่",
                        yaxis_title="ชั่วโมง (ค่าต้นทางเป็นนาที)", showlegend=False,
                    )
                    mark_partial_today(fig_recovery, today, start_date, end_date)
                    st.plotly_chart(fig_recovery, width="stretch")

                factor_specs = [
                    ("ปัจจัย Acute Load", "acwr_percent", "acwr_factor_feedback"),
                    ("ปัจจัย HRV", "hrv_factor_pct", "hrv_factor_feedback"),
                    ("ปัจจัยประวัติ Stress", "stress_history_pct", "stress_history_factor_feedback"),
                    ("ปัจจัยการนอน", "readiness_sleep_factor_pct", "readiness_sleep_factor_feedback"),
                    ("ปัจจัย Recovery Time", "recovery_time_factor_pct", "recovery_time_factor_feedback"),
                ]
                factor_rows = []
                for label, column, feedback_column in factor_specs:
                    snapshot = latest_field(wellness_df, column)
                    if snapshot:
                        factor_rows.append({
                            "องค์ประกอบ Readiness": label,
                            "คะแนนองค์ประกอบ": f"{fmt_num(snapshot['value'])}%",
                            "Garmin feedback": fmt_text(snapshot["row"].get(feedback_column), "–").replace("_", " "),
                            "วันที่/ความสด": field_freshness(snapshot, today),
                        })
                for note_label, note_value in garmin_notes:
                    factor_rows.append({
                        "องค์ประกอบ Readiness": note_label,
                        "คะแนนองค์ประกอบ": "–",
                        "Garmin feedback": note_value.replace("_", " "),
                        "วันที่/ความสด": "–",
                    })
                if factor_rows:
                    with st.expander("ดูองค์ประกอบที่ Garmin ใช้คำนวณ Readiness", icon=":material/tune:"):
                        st.dataframe(pd.DataFrame(factor_rows), hide_index=True)
                        st.caption("เป็น factor ของ Readiness ไม่ใช่โหลดสะสมของระบบ")
            else:
                st.subheader("ความพร้อมซ้อมและเวลาฟื้นตัวจาก Garmin")
                readiness_summary = availability_by_key["readiness"]
                if readiness_summary["state"] == "outside_range":
                    readiness_missing_message = (
                        "บัญชีนี้เคยมีข้อมูลความพร้อม/การฟื้นตัว แต่ไม่มีค่าในช่วงวันที่ที่เลือก "
                        "ลองเลือก ‘ทั้งหมด’ หรือช่วงที่ยาวขึ้น"
                    )
                else:
                    models = ", ".join(load_athlete_devices(athlete_id))
                    readiness_missing_message = (
                        "Garmin Connect ยังไม่เคยส่ง Training Readiness, Recovery Time, Acute Load "
                        "หรือ Training Status ให้บัญชีนี้ — นาฬิกาบางรุ่นแสดง Recovery Time "
                        "บนหน้าปัดแต่ไม่ส่งขึ้น Connect Dashboard จะไม่เดาหรือคำนวณค่าทดแทน"
                        + (f" (อุปกรณ์ที่พบใน 90 วัน: {models})" if models else "")
                    )
                st.info(readiness_missing_message, icon=":material/watch:")

            # --- รายละเอียดที่เก็บแล้ว: collapsed เพื่อให้ตรวจเทียบนาฬิกาได้โดยไม่ทำหน้าหลักแน่น ---
            detail_specs = [
                ("HRV", "HRV เฉลี่ย 7 วัน", "hrv_weekly_avg", " ms"),
                ("การนอน", "ระยะเวลานอน", "sleep_duration_sec", "duration"),
                ("การนอน", "Deep sleep", "deep_sleep_sec", "duration"),
                ("การนอน", "Light sleep", "light_sleep_sec", "duration"),
                ("การนอน", "REM sleep", "rem_sleep_sec", "duration"),
                ("การนอน", "Awake", "awake_sec", "duration"),
                ("Body Battery", "ต่ำสุดของวัน", "body_battery_low", ""),
                ("Body Battery", "ตอนตื่น", "bb_at_wake", ""),
                ("Body Battery", "ชาร์จ", "bb_charged", ""),
                ("Body Battery", "ใช้ไป", "bb_drained", ""),
                ("Body Battery", "ระหว่างนอน", "bb_during_sleep", ""),
                ("กิจวัตร", "Steps", "steps", " ก้าว"),
                ("กิจวัตร", "เป้า Steps", "steps_goal", " ก้าว"),
                ("กิจวัตร", "BMR", "bmr_kilocalories", " kcal"),
                ("กิจวัตร", "Active time", "active_seconds", "duration"),
                ("การหายใจ", "สูงสุด", "highest_respiration", " brpm"),
                ("การหายใจ", "ต่ำสุด", "lowest_respiration", " brpm"),
                ("การซ้อม", "Training Status", "training_status", "text"),
                ("สมรรถนะ", "Endurance Score", "endurance_score", ""),
                ("สมรรถนะ", "Hill Score", "hill_score_overall", ""),
                ("สมรรถนะ", "Hill Strength", "hill_score_strength", ""),
                ("สมรรถนะ", "Hill Endurance", "hill_score_endurance", ""),
            ]
            detail_rows = []
            for category, label, column, unit in detail_specs:
                snapshot = latest_field(wellness_df, column)
                if not snapshot:
                    continue
                if unit == "duration":
                    display_value = fmt_sec(snapshot["value"])
                elif unit == "text":
                    display_value = fmt_text(snapshot["value"], "–").replace("_", " ")
                else:
                    display_value = fmt_num(snapshot["value"], unit)
                detail_rows.append({
                    "หมวด": category, "รายการ": label, "ค่าล่าสุด": display_value,
                    "วันที่/ความสด": field_freshness(snapshot, today),
                })
            if detail_rows:
                with st.expander("ดูข้อมูลสุขภาพเพิ่มเติมล่าสุด", icon=":material/monitor_heart:"):
                    st.dataframe(pd.DataFrame(detail_rows), hide_index=True)
                    st.caption(
                        "แต่ละแถวเลือกค่าล่าสุดของ field นั้นเอง — fetched_at เป็นเวลาระดับแถว"
                    )

            history_labels = {
                "calendar_date": "วันที่",
                "resting_hr": "Resting HR",
                "hrv_weekly_avg": "HRV 7 วัน",
                "hrv_last_night": "HRV คืนล่าสุด",
                "hrv_status": "สถานะ HRV",
                "sleep_score": "Sleep score",
                "sleep_duration_sec": "เวลานอน", "deep_sleep_sec": "Deep",
                "light_sleep_sec": "Light", "rem_sleep_sec": "REM", "awake_sec": "Awake",
                "body_battery_high": "BB สูงสุด", "body_battery_low": "BB ต่ำสุด",
                "stress_avg": "Stress เฉลี่ย", "max_stress": "Stress สูงสุด",
                "bb_at_wake": "BB ตอนตื่น",
                "bb_charged": "BB ชาร์จ", "bb_drained": "BB ใช้ไป",
                "bb_during_sleep": "BB ระหว่างนอน", "bb_most_recent": "BB ล่าสุด",
                "steps": "Steps", "steps_goal": "เป้า Steps", "floors_ascended": "Floors",
                "active_kilocalories": "Active kcal", "bmr_kilocalories": "BMR kcal",
                "active_seconds": "Active time",
                "avg_waking_respiration": "หายใจเฉลี่ยตอนตื่น",
                "avg_sleep_respiration": "หายใจเฉลี่ยตอนนอน",
                "highest_respiration": "หายใจสูงสุด", "lowest_respiration": "หายใจต่ำสุด",
                "training_readiness": "Readiness", "readiness_level": "Readiness level",
                "readiness_feedback": "Readiness feedback",
                "readiness_feedback_long": "Readiness feedback ละเอียด",
                "readiness_timestamp_utc": "เวลา Readiness (UTC)",
                "readiness_timestamp_local": "เวลา Readiness (local)",
                "readiness_input_context": "Readiness context",
                "acute_load": "Acute Load", "acwr_percent": "Readiness: Acute Load factor %",
                "acwr_factor_feedback": "Acute Load feedback",
                "hrv_factor_pct": "Readiness: HRV factor %",
                "hrv_factor_feedback": "HRV factor feedback",
                "stress_history_pct": "Readiness: Stress factor %",
                "stress_history_factor_feedback": "Stress factor feedback",
                "readiness_sleep_factor_pct": "Readiness: Sleep factor %",
                "readiness_sleep_factor_feedback": "Sleep factor feedback",
                "recovery_time_min": "Recovery Time (นาที)",
                "recovery_time_factor_pct": "Readiness: Recovery factor %",
                "recovery_time_factor_feedback": "Recovery factor feedback",
                "recovery_time_change_phrase": "สถานะ Recovery Time",
                "training_status": "Training Status",
                "vo2max_trend": "VO2max",
                "fitness_age": "Fitness Age",
                "endurance_score": "Endurance Score", "hill_score_overall": "Hill Score",
                "hill_score_strength": "Hill Strength", "hill_score_endurance": "Hill Endurance",
                "lactate_threshold_hr": "LT Heart Rate",
                "lactate_threshold_pace_min_km": "LT Pace",
            }
            history_columns = [
                column for column in history_labels
                if column in wellness_df.columns
                and (column == "calendar_date" or wellness_df[column].notna().any())
            ]
            if len(history_columns) > 1:
                with st.expander("ดูประวัติสุขภาพรายวัน", icon=":material/table_chart:"):
                    history = wellness_df[history_columns].copy().sort_values("calendar_date", ascending=False)
                    history["calendar_date"] = pd.to_datetime(
                        history["calendar_date"], errors="coerce"
                    ).dt.date
                    for column in (
                        "sleep_duration_sec", "deep_sleep_sec", "light_sleep_sec",
                        "rem_sleep_sec", "awake_sec", "active_seconds",
                    ):
                        if column in history:
                            history[column] = history[column].map(fmt_sec)
                    if "lactate_threshold_pace_min_km" in history:
                        history["lactate_threshold_pace_min_km"] = history[
                            "lactate_threshold_pace_min_km"
                        ].map(lambda value: (
                            f"{fmt_pace(value)} /km" if pd.notna(value) else "–"
                        ))
                    text_history_columns = (
                        "hrv_status", "training_status", "readiness_level",
                        "readiness_feedback", "readiness_feedback_long",
                        "readiness_input_context", "acwr_factor_feedback",
                        "hrv_factor_feedback", "stress_history_factor_feedback",
                        "readiness_sleep_factor_feedback", "recovery_time_factor_feedback",
                        "recovery_time_change_phrase",
                    )
                    for column in text_history_columns:
                        if column in history:
                            history[column] = history[column].map(
                                lambda value: (value.replace("_", " ")
                                               if isinstance(value, str) else value)
                            )
                    history = history.rename(columns=history_labels)
                    st.dataframe(history, hide_index=True)


    # =====================================================================
    # TAB 4: TRAINING — workload context + pace-HR trend + intensity distribution
    # =====================================================================
# แท็บที่ไม่ได้เปิดอยู่ไม่ต้องสร้างกราฟ — plotly คือตัวกินเวลาหลักของหนึ่งรอบรัน
if tab_train.open:
    with tab_train:
        st.header(f"การซ้อม — {selected_name}", anchor=f"training-{selected_anchor}")
        st.caption(f"สรุประหว่าง {start_date.strftime('%d/%m/%Y')}–{end_date.strftime('%d/%m/%Y')}")

        if activity_df.empty:
            st.info("ไม่มีข้อมูลการวิ่งในช่วงเวลานี้")
        else:
            runs_df = activity_df[activity_df["activity_type"].isin(RUN_TYPES)]

            total_distance = runs_df["distance_km"].sum()
            avg_pace_raw = aggregate_pace_min_per_km(runs_df)
            total_hours = runs_df["duration_sec"].sum() / 3600

            with st.container(horizontal=True):
                st.metric("ระยะวิ่งรวม", f"{total_distance:.2f} km", border=True)
                # Tong/Dan บันทึก warm-up / งานหลัก / cool-down เป็นคนละรายการ
                # (2.3 และ 2.1 รายการต่อวันที่ซ้อม) "44 ครั้ง" จึงอ่านเป็น 44 เซสชันไม่ได้
                run_days = (runs_df["start_time_local"].astype(str).str[:10].nunique()
                            if not runs_df.empty else 0)
                st.metric("รายการวิ่ง", f"{len(runs_df)}",
                          delta=f"{run_days} วันที่ซ้อม", delta_color="off", border=True,
                          help="นาฬิกาบันทึก warm-up / งานหลัก / cool-down เป็นคนละรายการ "
                               "จำนวนรายการจึงมากกว่าจำนวนเซสชันจริง")
                st.metric("เพซเฉลี่ย", f"{fmt_pace(avg_pace_raw)} /km" if pd.notna(avg_pace_raw) else "–", border=True)
                st.metric("เวลาวิ่งรวม", f"{total_hours:.1f} ชม.", border=True)

            # ---------------- pace-HR trend ของรันเบา — บริบทประกอบ ----------------
            st.subheader("แนวโน้ม pace–HR ของรันเบา")
            ef_lookback = start_date - datetime.timedelta(days=EF_BASELINE_DAYS)
            lthr_for_tab, _ = get_lthr(selected_slug, athlete_id)
            ef_all = easy_run_efficiency(
                load_easy_runs(athlete_id, ef_lookback.isoformat(), end_date.isoformat()),
                lthr_for_tab,
            )
            ef_windows_tab = efficiency_windows(ef_all, end_date)
            ef_pct_tab = efficiency_change_pct(ef_all, end_date)
            ef_view = ef_all[ef_all["date"] >= pd.Timestamp(start_date)]

            if ef_view.empty:
                st.info(
                    "ยังมีรัน easy ไม่พอในช่วงนี้ที่จะคำนวณ pace–HR trend "
                    f"(ต้องมี HR, ระยะ ≥ {EF_MIN_DISTANCE_M / 1000:.0f} กม. และ HR ≤ "
                    f"{EASY_MAX_PCT * 100:.0f}% ของ LTHR"
                    + (f" = {lthr_for_tab * EASY_MAX_PCT:.0f} bpm)" if lthr_for_tab else ")")
                    + " — เป็นเรื่องปกติของคนที่ซ้อม cross-training เป็นหลัก ไม่ใช่ระบบขัดข้อง",
                    icon=":material/info:",
                )
            else:
                _, txt = efficiency_status(ef_pct_tab)
                ef_baseline_median = (
                    ef_windows_tab["baseline_median"]
                    if ef_windows_tab is not None else float("nan")
                )
                with st.container(horizontal=True):
                    _ef_now = efficiency_recent_value(ef_all, end_date)
                    st.metric("pace–HR ล่าสุด (median 3 วัน)",
                              f"{_ef_now:.3f}" if pd.notna(_ef_now) else "–",
                              delta=txt, delta_color="off", border=True,
                              help="รวมรายการวิ่ง easy ที่ Garmin แยกบันทึกในวันเดียวกันก่อน "
                                   "แล้วคำนวณความเร็ว (ม./นาที) ÷ HR เฉลี่ยถ่วงเวลา; "
                                   "ไม่ใช่ running economy หรือ readiness test")
                    st.metric("เทียบฐานก่อนหน้า", efficiency_display(ef_pct_tab), border=True,
                              help="ฐาน 28 วันก่อนสามวันล่าสุดและไม่ซ้อนกับค่าปัจจุบัน; "
                                   "ไม่มีเกณฑ์พร้อมซ้อม/ต้องพัก")
                    st.metric("จำนวนวันที่มีข้อมูลวิ่ง easy", f"{len(ef_view)} วัน", border=True,
                              help=f"จะสรุปได้ต้องมีข้อมูลวิ่ง easy {EF_RECENT_DAYS} วัน"
                                   f"ภายใน {EF_STALE_DAYS} วัน และมีฐานอย่างน้อย "
                                   f"{EF_BASELINE_MIN_DAYS} วันใน {EF_BASELINE_DAYS} "
                                   "วันก่อนหน้า — ไม่ครบแล้วขึ้น 'ข้อมูลไม่พอ' คือวันวิ่ง easy "
                                   "ไม่พอ ไม่ใช่ระบบขัดข้อง")

                fig_ef = go.Figure()
                fig_ef.add_trace(go.Scatter(
                    x=ef_view["date"], y=ef_view["ef"], mode="lines+markers",
                    line=dict(color=C_BLUE, width=2), marker=dict(size=6), name="pace–HR ต่อวัน",
                    connectgaps=False,
                    hovertemplate="%{x|%d %b}<br>pace–HR %{y:.3f}<extra></extra>",
                ))
                if pd.notna(ef_baseline_median):
                    fig_ef.add_trace(go.Scatter(
                        x=ef_view["date"],
                        y=[ef_baseline_median] * len(ef_view),
                        mode="lines", line=dict(color=C_CONTEXT, width=2, dash="dash"),
                        name="ฐานของตัวเอง",
                        hovertemplate="ฐาน %{y:.3f}<extra></extra>",
                    ))
                fig_ef.update_layout(
                    title="ความเร็ว ÷ HR ในรัน easy — ดูทิศทาง ไม่ใช้แทน running economy/ความสด",
                    yaxis=dict(title="เมตร/นาที ต่อ 1 bpm"),
                    xaxis=dict(title="วันที่"),
                    showlegend=True, hovermode="x unified",
                )
                st.plotly_chart(fig_ef, width="stretch")

            # ---------------- โหลดสะสม (บริบท ไม่ใช่คำตัดสิน) ----------------
            st.subheader("โหลดสะสม (บริบท)")
            load_start = start_date - datetime.timedelta(days=56)
            daily_wl, wl_metric, wl_unit = load_daily_workload(athlete_id, load_start.isoformat(), end_date.isoformat())
            first_workload_date = (
                load_first_load_date(athlete_id)
                if wl_metric == "training_load"
                else load_first_run_date(athlete_id)
            )
            history_start = max(load_start, first_workload_date) if first_workload_date else load_start
            load_df = compute_load_windows(daily_wl, end_date, history_start=history_start)
            load_view = load_df[load_df["date"] >= pd.Timestamp(start_date)]
            load_valid = load_view.dropna(subset=["acute"])
            _src = "Garmin training_load (รวม cross-training)" if wl_metric == "training_load" else "ระยะทางวิ่ง"
            _afmt = ".0f" if wl_metric == "training_load" else ".1f"

            if load_valid.empty:
                st.info("ยังไม่มีข้อมูลครบ 7 วันพอสรุปโหลดสะสม")
            else:
                latest_load = load_valid.iloc[-1]
                with st.container(horizontal=True):
                    st.metric("โหลด 7 วัน", f"{latest_load['acute']:{_afmt}} {wl_unit}", border=True)
                    st.metric("ค่าเฉลี่ย 28 วัน",
                              f"{latest_load['chronic']:{_afmt}} {wl_unit}/สัปดาห์"
                              if pd.notna(latest_load["chronic"]) else "–", border=True)

                fig_load = go.Figure()
                fig_load.add_trace(go.Scatter(
                    x=load_view["date"], y=load_view["acute"], mode="lines",
                    line=dict(color=C_BLUE, width=2), name=f"โหลด 7 วัน ({wl_unit})",
                    connectgaps=False,
                    hovertemplate="%{x|%d %b}<br>7 วัน %{y:,.1f}<extra></extra>",
                ))
                fig_load.add_trace(go.Scatter(
                    x=load_view["date"], y=load_view["chronic"], mode="lines",
                    line=dict(color=C_CONTEXT, width=2, dash="dash"),
                    name=f"ฐาน 28 วัน ({wl_unit}/สัปดาห์)", connectgaps=False,
                    hovertemplate="%{x|%d %b}<br>ฐาน %{y:,.1f}<extra></extra>",
                ))
                fig_load.update_layout(
                    title=f"ปริมาณที่ทำไปเทียบฐานของตัวเอง (จาก {_src})",
                    yaxis=dict(title=wl_unit), xaxis=dict(title="วันที่"),
                    showlegend=True, hovermode="x unified",
                )
                # แสดง 7 วันและค่าเฉลี่ย 28 วันแยกกันเพื่อให้เห็นบริบท โดยไม่หารเป็น
                # acute:chronic ratio หรือวางเส้นปลอดภัย/เสี่ยงที่หลักฐานรองรับไม่พอ
                st.plotly_chart(fig_load, width="stretch")

            # ---------------- training-intensity distribution ----------------
            st.subheader("สัดส่วนความหนักการซ้อม (3 โซน)")
            zone_cols = ["hr_zone1_sec", "hr_zone2_sec", "hr_zone3_sec", "hr_zone4_sec", "hr_zone5_sec"]
            have_zone_cols = set(zone_cols).issubset(activity_df.columns)
            zdf = usable_hr_zone_rows(activity_df, zone_cols) if have_zone_cols else activity_df.iloc[0:0]

            if not zdf.empty:
                # สัดส่วนของโปรแกรมวิ่งควรดูการวิ่งแยกจาก HIIT/มวย/indoor cardio
                # เพราะงานคนละชนิดเจือจางตัวเลขจนอ่านผิด (วัดจริง 26 ส.ค. 69:
                # P'kao เห็นเบา 33% ทั้งที่เฉพาะการวิ่งเบาแค่ 22% และหนักถึง 53%)
                # จึงวาดสองวง และให้การ์ดอ่านจากวงการวิ่ง
                run_zdf = zdf[zdf["activity_type"].isin(RUN_TYPES)]
                run_buckets = intensity_minutes(run_zdf, zone_cols)
                all_buckets = intensity_minutes(zdf, zone_cols)
                run_coverage = hr_zone_coverage(runs_df, zone_cols)
                all_coverage = hr_zone_coverage(activity_df, zone_cols)
                headline = run_buckets or all_buckets
                headline_is_run = run_buckets is not None
                headline_coverage = run_coverage if headline_is_run else all_coverage
                easy_pct = easy_share_pct(headline)

                # วงที่สองมีความหมายต่อเมื่อ cross-training กินเวลาจริง — ไม่งั้นสองวง
                # จะเหมือนกันเป๊ะ (เคสของ Tong/Dan ที่วิ่งเกือบ 100%) แล้วกลายเป็นสิ่งรบกวน
                cross_share = 0.0
                if run_buckets and all_buckets:
                    cross_share = 1 - sum(run_buckets.values()) / sum(all_buckets.values())
                rings = [("การวิ่ง", run_buckets)] if headline_is_run else []
                if cross_share >= 0.10 and all_buckets:
                    rings.append(("ทั้งหมด (รวม cross-training)", all_buckets))
                if not rings:
                    rings = [("ทั้งหมด", all_buckets)]

                col_pie, col_info = st.columns([3, 2])
                with col_pie:
                    fig_pie = go.Figure()
                    for index, (ring_name, ring_buckets) in enumerate(rings):
                        span = 1 / len(rings)
                        fig_pie.add_trace(go.Pie(
                            labels=INTENSITY_ORDER,
                            values=[ring_buckets[name] for name in INTENSITY_ORDER],
                            name=ring_name, hole=0.55, sort=False,
                            marker=dict(colors=[INTENSITY_COLORS[n] for n in INTENSITY_ORDER]),
                            domain=dict(x=[index * span, (index + 1) * span]),
                            title=dict(text=ring_name),
                            textinfo="percent",
                            hovertemplate=(f"{ring_name}<br>%{{label}}<br>"
                                           "%{value:.0f} นาที (%{percent})<extra></extra>"),
                        ))
                    fig_pie.update_layout(
                        title="สัดส่วนเฉพาะเวลาที่ Garmin จัด HR zone ได้",
                        legend=dict(orientation="h", yanchor="bottom", y=-0.12),
                    )
                    st.plotly_chart(fig_pie, width="stretch")
                with col_info:
                    label = ("สัดส่วนเบาของการวิ่ง (Z1-2 ตามเวลาจริง)" if headline_is_run
                             else "สัดส่วนเบา (Z1-2 ตามเวลาจริง)")
                    all_pct = easy_share_pct(all_buckets)
                    unclassified_min = headline_coverage["unclassified_sec"] / 60
                    coverage_pct = headline_coverage["coverage_pct"]
                    coverage_note = (
                        f"ครอบคลุม {coverage_pct:.1f}% ของ duration · "
                        f"ไม่ได้จัดโซน {unclassified_min:.1f} นาที"
                    )
                    st.metric(label, f"{easy_pct:.0f}%", delta=coverage_note,
                              delta_color="off", border=True,
                              help=("นับจากเวลาในโซน HR จริงที่นาฬิกาเก็บวินาทีต่อโซน "
                                    f"({len(run_zdf) if headline_is_run else len(zdf)} กิจกรรม) · "
                                    "เปอร์เซ็นต์ในวงใช้เฉพาะเวลาที่จัดโซนได้; coverage "
                                    "เทียบกับ duration ของทุกกิจกรรม Garmin ในขอบเขต · "
                                    "เป็นคำอธิบายสัดส่วน ไม่ได้มีเป้า 80% สากล · "
                                    + (f"รวม cross-training ทั้งหมดได้ {all_pct:.0f}%"
                                       if headline_is_run and pd.notna(all_pct)
                                       else "ยังไม่มีการวิ่งที่มีเวลาในโซนในช่วงนี้")))
                    for name in INTENSITY_ORDER:
                        st.markdown(f"- **{name}** — {headline[name]:.0f} นาที")
            else:
                # fallback วิธีเดิม (avg HR ต่อเซสชัน) เมื่อไม่มี time-in-zone
                lthr, lthr_source = get_lthr(selected_slug, athlete_id)
                hr_runs = runs_df.dropna(subset=["avg_hr", "duration_sec"]).copy()
                if not lthr or hr_runs.empty:
                    st.info("ไม่มีข้อมูล HR zones หรือ LTHR สำหรับจำแนกความหนัก")
                else:
                    hr_runs["intensity"] = hr_runs["avg_hr"].map(lambda h: classify_intensity(h, lthr))
                    dist = (hr_runs.groupby("intensity")
                            .agg(minutes=("duration_sec", lambda s: s.sum() / 60), sessions=("duration_sec", "size"))
                            .reindex(INTENSITY_ORDER).dropna(how="all").reset_index())
                    easy_pct = 0.0
                    if dist["minutes"].sum() > 0:
                        easy_pct = (dist[dist["intensity"] == INTENSITY_ORDER[0]]["minutes"].sum()
                                    / dist["minutes"].sum()) * 100
                    col_pie, col_info = st.columns([3, 2])
                    with col_pie:
                        fig_pie = px.pie(dist, values="minutes", names="intensity", hole=0.55,
                                         color="intensity", color_discrete_map=INTENSITY_COLORS,
                                         category_orders={"intensity": INTENSITY_ORDER},
                                         title="สัดส่วนเวลาซ้อมตามโซนความหนัก (จาก avg HR)")
                        fig_pie.update_traces(textinfo="percent+label", sort=False,
                                              hovertemplate="%{label}<br>%{value:.0f} นาที (%{percent})<extra></extra>")
                        st.plotly_chart(fig_pie, width="stretch")
                    with col_info:
                        st.metric("สัดส่วนวิ่งเบา (ตามเวลา)", f"{easy_pct:.0f}%", border=True,
                                  help="ไม่มีเวลาในโซน HR จริง จึงจำแนกจาก avg HR "
                                       f"ต่อเซสชันเทียบ LTHR {lthr} bpm ({lthr_source}) "
                                       "ซึ่งหยาบกว่าและใช้กับ interval ได้ไม่ดี; "
                                       "เป็นคำอธิบาย ไม่ใช่เป้า 80% สากล")
                        for _, r in dist.iterrows():
                            st.markdown(f"- **{r['intensity']}** — {r['minutes']:.0f} นาที · {int(r['sessions'])} เซสชัน")

            # ---------------- Running Dynamics (สรุปช่วงที่เลือก) ----------------
            dyn_cols = {
                "avg_cadence": ("Cadence เฉลี่ย", "spm", "%.0f"),
                "avg_stride_length_cm": ("Stride Length", "cm", "%.0f"),
                "avg_ground_contact_time_ms": ("Ground Contact", "ms", "%.0f"),
                "avg_vertical_oscillation_cm": ("Vertical Oscillation", "cm", "%.1f"),
                "avg_vertical_ratio": ("Vertical Ratio", "%", "%.1f"),
            }
            run_dyn = runs_df[runs_df.get("avg_ground_contact_time_ms").notna()] if "avg_ground_contact_time_ms" in runs_df else runs_df.iloc[0:0]
            if not run_dyn.empty:
                # รายละเอียดฟอร์มเป็นของที่ดูตอนสงสัย ไม่ใช่ค่าที่ต้องเห็นทุกครั้งที่เปิดหน้า
                # ห้าตัวนี้เคยดันแท็บนี้ให้เป็นแท็บที่มีตัวเลขพร้อมกันมากที่สุดในไฟล์ (16 ตัว)
                dyn_drawer = st.expander(
                    "ดู Running dynamics เฉลี่ย", icon=":material/podiatry:"
                )
                with dyn_drawer, st.container(horizontal=True):
                    for col, (label, unit, fmt) in dyn_cols.items():
                        val = pd.to_numeric(run_dyn[col], errors="coerce").mean() if col in run_dyn else float("nan")
                        st.metric(label, (fmt % val + f" {unit}") if pd.notna(val) else "–",
                                  border=True,
                                  help="จากเซสชันวิ่งที่นาฬิกาเก็บ running dynamics — "
                                       "ใช้ดูคนเดิมที่เพซ/พื้นผิว/ความชัน/อุปกรณ์ใกล้กัน; "
                                       "GCT หรือ vertical ratio ต่ำไม่ได้แปลว่าประหยัดแรงหรือเสี่ยงเจ็บน้อยโดยลำพัง")

            # ---------------- กราฟเดิม ----------------
            fig_dist = px.bar(activity_df, x="start_time_local", y="distance_km",
                              title="ระยะทางของแต่ละกิจกรรม",
                              labels={"distance_km": "ระยะทาง (km)", "start_time_local": "วันที่และเวลา"})
            fig_dist.update_traces(marker_color=SERIES_COLORS["distance_km"])
            st.plotly_chart(fig_dist, width="stretch")

            # ขนาดวงกลม = ความหนัก: ใช้ training_load ถ้านาฬิกาให้ ไม่งั้น Training Effect aerobic (ทุกคนมีครบ)
            if activity_df["training_load"].notna().any():
                size_col, size_label = "training_load", "Training Load"
            else:
                size_col, size_label = "training_effect_aerobic", "Training Effect (แอโรบิก)"
            clean_activity = activity_df.dropna(subset=["avg_pace_min_per_km", size_col]).copy()
            if clean_activity.empty:
                st.info("ยังไม่มีข้อมูล Pace + ความหนักครบพอสำหรับกราฟนี้ในช่วงเวลาที่เลือก")
            else:
                clean_activity["_size"] = clean_activity[size_col].clip(lower=0.1)  # กัน 0 ทำวงกลมหาย
                fig_perf = px.scatter(clean_activity, x="start_time_local", y="avg_pace_min_per_km",
                                      size="_size", color="avg_hr",
                                      title=f"เพซเทียบความหนัก ({size_label} = ขนาดวงกลม)",
                                      labels={"avg_pace_min_per_km": "Pace (นาที/กม.)",
                                              "start_time_local": "วันที่",
                                              "avg_hr": "หัวใจเฉลี่ย (bpm)"})
                fig_perf.update_yaxes(autorange="reversed")
                st.plotly_chart(fig_perf, width="stretch")


    # =====================================================================
    # TAB 5: PROGRESS — ความก้าวหน้า (VO2max / คาดการณ์แข่ง / PR / LT)
    # =====================================================================
# แท็บที่ไม่ได้เปิดอยู่ไม่ต้องสร้างกราฟ — plotly คือตัวกินเวลาหลักของหนึ่งรอบรัน
if tab_progress.open:
    with tab_progress:
        st.header(f"ความก้าวหน้า — {selected_name}", anchor=f"progress-{selected_anchor}")
        st.caption(
            f"แนวโน้มระหว่าง {start_date.strftime('%d/%m/%Y')}–{end_date.strftime('%d/%m/%Y')} · "
            "ใช้ค่าจาก Garmin ดูทิศทาง ส่วนค่าสัมบูรณ์ให้ยึดผลเทสจริง"
        )

        advanced_summary = availability_by_key["advanced"]
        advanced_performance_missing_message = None
        if advanced_summary["state"] == "never_received":
            advanced_performance_missing_message = (
                "Garmin Connect ยังไม่เคยส่ง VO2max, Fitness Age, Endurance/Hill Score "
                "หรือ Lactate Threshold ให้บัญชีนี้"
            )
        elif advanced_summary["state"] == "outside_range":
            advanced_performance_missing_message = (
                "มีประวัติเมตริกสมรรถนะขั้นสูง แต่ไม่มีค่าในช่วงวันที่ที่เลือก"
            )
        elif advanced_summary["state"] == "partial":
            advanced_performance_missing_message = (
                f"Garmin Connect เคยส่งเมตริกสมรรถนะขั้นสูง "
                f"{advanced_summary['history_available']}/{advanced_summary['total_fields']} ชนิด; "
                "ส่วนที่ไม่แสดงคือค่าที่บัญชีนี้ยังไม่เคยได้รับ"
            )
        # หนึ่งหน้า หนึ่งกล่อง "ของที่ยังไม่มี" — จองที่ไว้บนสุดแล้วเติมตอนจบ
        # เดิมทุกหัวข้อที่ว่างขึ้นกล่องของตัวเอง นาฬิกาที่ไม่ส่งเมตริกขั้นสูงจึงเจอ
        # กล่องสีหกใบพูดเรื่องเดียวกัน ทั้งที่กล่องบนสุดสรุปไว้หมดแล้ว
        data_gap_slot = st.empty()
        missing_here = []

        # ---------------- VO2max trend ----------------
        vo2 = (wellness_df.dropna(subset=["vo2max_trend"])
               if "vo2max_trend" in wellness_df else wellness_df.iloc[0:0])
        # Fitness Age อ่านจาก wellness_df เต็ม ไม่ใช่จาก vo2 ที่กรอง vo2max_trend มาแล้ว —
        # คนละ endpoint กัน (extras เขียน fitness_age ให้วันล่าสุดวันเดียว ส่วน vo2max_trend
        # ขึ้นเฉพาะวันที่มีวิ่ง outdoor) ถ้าอ่านจาก vo2 ค่าจะหายทุกครั้งที่วันล่าสุดไม่ได้วิ่ง
        _fit_age = (wellness_df["fitness_age"].dropna()
                    if "fitness_age" in wellness_df else pd.Series(dtype=float))
        if not vo2.empty or not _fit_age.empty:
            with st.container(horizontal=True):
                if not vo2.empty:
                    # Garmin คำนวณ VO2max ใหม่เฉพาะวันที่วิ่ง GPS นอกลู่ นักกีฬาที่วิ่งลู่
                    # เป็นหลักจึงเห็นค่าเดิมค้างเป็นเดือน (P'kao ค้าง 26 วันเมื่อ 26 ส.ค. 69)
                    # การ์ดต้องบอกวันที่ของค่านั้น และห้ามเทียบกับตัวเองแล้วขึ้น +0.0
                    first_v, last_v = vo2["vo2max_trend"].iloc[0], vo2["vo2max_trend"].iloc[-1]
                    vo2_snap = latest_field(wellness_df, "vo2max_trend")
                    vo2_delta = (f"{last_v - first_v:+.1f} เทียบต้นช่วง"
                                 if len(vo2) > 1 else "มีค่าเดียวในช่วงนี้")
                    st.metric("VO2max ล่าสุด (Garmin)", f"{last_v:.1f}",
                              delta=vo2_delta,
                              delta_color="normal" if len(vo2) > 1 else "off",
                              border=True,
                              help=("Garmin อัปเดตเฉพาะวันที่มีวิ่ง GPS นอกลู่ · "
                                    + field_freshness(vo2_snap, today)))
                if not _fit_age.empty:
                    st.metric("Fitness Age", fmt_num(_fit_age.iloc[-1]), border=True)
        if not vo2.empty:
            # ต่างจากกราฟสุขภาพรายวันตรงที่ connectgaps=True: Garmin คำนวณ VO2max ใหม่เฉพาะ
            # วันที่มีวิ่ง GPS เข้าเกณฑ์ (get_max_metrics ตอบว่างเปล่าในวันอื่น — ตรวจแล้ว
            # 18 ส.ค. 69) ค่าไม่ได้หายไปในวันที่ไม่ได้คำนวณ เส้นขาดเป็นท่อนจึงสื่อผิด
            # marker ยังอยู่เฉพาะวันที่ Garmin วัดจริง เส้นแค่เชื่อมจุดที่มีจริงเข้าด้วยกัน
            fig_vo2 = go.Figure(go.Scatter(
                x=wellness_plot_df["calendar_date"], y=wellness_plot_df["vo2max_trend"],
                mode="lines+markers", name="VO2max", connectgaps=True,
                hovertemplate="%{x|%d %b}<br>VO2max: %{y:.1f}<extra></extra>",
            ))
            fig_vo2.update_layout(
                title="แนวโน้ม VO2max (Garmin อัปเดตเฉพาะวันที่มีวิ่ง GPS)",
                xaxis_title="วันที่", yaxis_title="VO2max", showlegend=False,
            )
            st.plotly_chart(fig_vo2, width="stretch")
        else:
            missing_here.append("VO2max (Garmin อัปเดตเฉพาะวันที่มีวิ่ง GPS)")

        # ---------------- Body composition ----------------
        # endpoint นี้มักมีข้อมูลห่าง ๆ และอาจอยู่นอกช่วง 30 วันที่เลือก จึงแสดงค่าล่าสุด
        # จากประวัติทั้งหมด พร้อมวันที่จริงของแต่ละ field แทนการทำให้ค่าหายจาก dashboard.
        body_composition = load_body_composition(athlete_id)
        body_fields = [
            ("weight_kg", "น้ำหนัก", " kg", "{:.1f}"),
            ("bmi", "BMI", "", "{:.1f}"),
            ("body_fat_pct", "ไขมันในร่างกาย", "%", "{:.1f}"),
        ]
        body_latest = []
        if not body_composition.empty:
            for column, label, unit, number_format in body_fields:
                valid = body_composition.dropna(subset=[column])
                if not valid.empty:
                    row = valid.iloc[-1]
                    body_latest.append((
                        label,
                        number_format.format(row[column]) + unit,
                        row["calendar_date"],
                    ))
        if not body_latest:
            missing_here.append("น้ำหนัก, BMI และเปอร์เซ็นต์ไขมัน")
        else:
            st.subheader("องค์ประกอบร่างกายจาก Garmin")
            with st.container(horizontal=True):
                for label, value, measured_at in body_latest:
                    st.metric(
                        label,
                        value,
                        delta=(measured_at.strftime("%d/%m/%Y")
                               if pd.notna(measured_at) else None),
                        delta_color="off",
                        border=True,
                    )
            body_history = body_composition.rename(columns={
                "calendar_date": "วันที่",
                "weight_kg": "น้ำหนัก (kg)",
                "bmi": "BMI",
                "body_fat_pct": "ไขมัน (%)",
            })
            with st.expander("ประวัติองค์ประกอบร่างกาย", icon=":material/monitor_weight:"):
                st.dataframe(
                    body_history,
                    hide_index=True,
                    column_config={
                        "วันที่": st.column_config.DateColumn(format="DD/MM/YYYY"),
                        "น้ำหนัก (kg)": st.column_config.NumberColumn(format="%.1f"),
                        "BMI": st.column_config.NumberColumn(format="%.1f"),
                        "ไขมัน (%)": st.column_config.NumberColumn(format="%.1f"),
                    },
                )

        # ---------------- Race predictions ----------------
        preds = load_race_predictions(athlete_id, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
        if preds.empty:
            missing_here.append("เวลาการแข่งขันที่ Garmin คาดการณ์")
        else:
            st.subheader("เวลาการแข่งขันที่ Garmin คาดการณ์")
            race_cols = [("time_5k_sec", "5K"), ("time_10k_sec", "10K"),
                         ("time_half_sec", "Half"), ("time_full_sec", "Marathon")]
            with st.container(horizontal=True):
                for col, label in race_cols:
                    # ใช้ค่าล่าสุด "ที่มีจริง" ต่อคอลัมน์ — แถววันปัจจุบันมักเป็น NULL
                    # (Garmin ยังไม่คำนวณของวันใหม่ตอน sync เช้า)
                    s = preds[col].dropna()
                    cur = s.iloc[-1] if not s.empty else float("nan")
                    base = s.iloc[0] if len(s) >= 2 else float("nan")
                    delta_s = cur - base if pd.notna(cur) and pd.notna(base) else float("nan")
                    st.metric(label, fmt_sec(cur),
                              delta=(f"{delta_s:+.0f} วิ เทียบต้นช่วง" if pd.notna(delta_s) else None),
                              delta_color="inverse", border=True)  # เวลาลด = ดีขึ้น (เขียว)
            fig_pred = go.Figure()
            for col, label, color in [("time_5k_sec", "5K", SERIES_COLORS["time_5k_sec"]),
                                     ("time_10k_sec", "10K", SERIES_COLORS["time_10k_sec"])]:
                if preds[col].notna().any():
                    fig_pred.add_trace(go.Scatter(
                        x=preds["calendar_date"], y=preds[col], mode="lines", name=label,
                        line=dict(color=color, width=2),
                        customdata=[fmt_sec(v) for v in preds[col]],
                        hovertemplate="%{x|%d %b}<br>" + label + ": %{customdata}<extra></extra>"))
            fig_pred.update_layout(
                title="แนวโน้มคาดการณ์ 5K / 10K (ยิ่งต่ำยิ่งเร็ว)",
                yaxis=dict(title="เวลา"), xaxis=dict(title="วันที่"), hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02))
            # แกน Y เป็น M:SS อ่านง่าย (แทนวินาทีดิบ) — step ปรับตามช่วงข้อมูล
            all_t = pd.concat([preds["time_5k_sec"], preds["time_10k_sec"]]).dropna()
            if not all_t.empty:
                lo, hi = float(all_t.min()), float(all_t.max())
                rng = max(hi - lo, 1.0)
                step = 30 if rng <= 300 else (60 if rng <= 900 else 300)
                start = int(lo // step) * step
                tickvals = list(range(start, int(hi) + step + 1, step))
                fig_pred.update_yaxes(tickvals=tickvals, ticktext=[fmt_sec(v) for v in tickvals])
            st.plotly_chart(fig_pred, width="stretch")
            st.caption("Garmin Race Predictor เป็นค่าประมาณจากโมเดลของผู้ผลิต — "
                       "ใช้ดูแนวโน้มและเทียบข้อผิดพลาดกับ race/time trial จริงของคนเดิม ไม่ใช้แทนผลงานจริง")

        # ---------------- Lactate Threshold (Garmin) ----------------
        lt_row = load_latest_lt(athlete_id)
        if lt_row:
            lt_date, lt_hr, lt_pace = lt_row
            st.subheader("Lactate threshold จาก Garmin")
            with st.container(horizontal=True):
                st.metric("LT Heart Rate", f"{lt_hr:.0f} bpm" if lt_hr is not None else "–", border=True)
                st.metric("LT Pace", f"{fmt_pace(lt_pace)} /km" if lt_pace is not None else "–", border=True)
                st.metric("วันที่วัด", lt_date, border=True)
            st.caption("ค่าประเมินจากอัลกอริทึม Garmin — เทียบกับผลเทสแลบ/field test "
                       "และดูวันที่วัดก่อนใช้ปรับโซน")
        else:
            missing_here.append(
                "Lactate Threshold (ต้องใช้อุปกรณ์/กิจกรรมที่เข้าเงื่อนไขของ Garmin)"
            )
        # ---------------- Endurance / Hill score (device-dependent) ----------------
        eh_cols = [c for c in ("endurance_score", "hill_score_overall") if c in wellness_df]
        eh = wellness_df.dropna(subset=eh_cols, how="all") if eh_cols else wellness_df.iloc[0:0]
        if not eh.empty and any(eh[c].notna().any() for c in eh_cols):
            st.subheader("Endurance และ Hill score")
            with st.container(horizontal=True):
                if eh["endurance_score"].notna().any():
                    e_last = eh["endurance_score"].dropna()
                    st.metric("Endurance Score ล่าสุด", f"{e_last.iloc[-1]:.0f}",
                              delta=f"{e_last.iloc[-1] - e_last.iloc[0]:+.0f} เทียบต้นช่วง", border=True)
                if "hill_score_overall" in eh and eh["hill_score_overall"].notna().any():
                    h_last = eh["hill_score_overall"].dropna()
                    st.metric("Hill Score ล่าสุด", f"{h_last.iloc[-1]:.0f}", border=True)
            if eh["endurance_score"].notna().any():
                fig_end = go.Figure(go.Scatter(
                    x=wellness_plot_df["calendar_date"],
                    y=wellness_plot_df["endurance_score"],
                    mode="lines+markers", name="Endurance Score", connectgaps=False,
                    hovertemplate="%{x|%d %b}<br>Endurance Score: %{y:.0f}<extra></extra>",
                ))
                fig_end.update_layout(
                    title="แนวโน้ม Endurance Score (ความอึดสะสม)",
                    xaxis_title="วันที่", yaxis_title="Endurance Score", showlegend=False,
                )
                st.plotly_chart(fig_end, width="stretch")
        else:
            missing_here.append("Endurance Score และ Hill Score (ขึ้นกับรุ่นอุปกรณ์)")
        # ---------------- Personal records ----------------
        prs = load_personal_records(athlete_id)
        if prs.empty:
            missing_here.append("สถิติส่วนตัว (PR)")
        else:
            st.subheader("สถิติส่วนตัวจาก Garmin")
            st.dataframe(pd.DataFrame(personal_record_rows(prs)), hide_index=True)
            st.caption("PR นับตามที่นาฬิกาบันทึกอัตโนมัติ — ระยะที่ GPS วัดไม่ถึงเกณฑ์ (เช่น 4.98 กม.) จะไม่ถูกนับเป็น 5K")

        # เติมกล่องเดียวที่จองไว้บนสุด — ตอนนี้รู้ครบแล้วว่าหัวข้อไหนไม่มีของ
        if missing_here or advanced_performance_missing_message:
            lines = []
            if advanced_performance_missing_message:
                lines.append(advanced_performance_missing_message)
            if missing_here:
                lines.append(
                    "ยังไม่มีข้อมูลให้แสดงในช่วงนี้: " + " · ".join(missing_here)
                )
            data_gap_slot.info("\n\n".join(lines), icon=":material/insights:")


    # =====================================================================
    # TAB 6: SPLITS — เจาะลึกรายเซสชัน
    # =====================================================================
# แท็บที่ไม่ได้เปิดอยู่ไม่ต้องสร้างกราฟ — plotly คือตัวกินเวลาหลักของหนึ่งรอบรัน
if tab_splits.open:
    with tab_splits:
        st.header(f"รายละเอียดเซสชัน — {selected_name}", anchor=f"sessions-{selected_anchor}")
        st.caption(
            f"เลือกกิจกรรมระหว่าง {start_date.strftime('%d/%m/%Y')}–{end_date.strftime('%d/%m/%Y')} · "
            "เครื่องหมาย – หมายถึง Garmin ไม่ได้ส่งเมตริกนั้นมากับกิจกรรมที่เลือก ไม่ใช่ค่า 0"
        )

        if activity_df.empty:
            st.info("ไม่มีกิจกรรมในช่วงเวลานี้")
        else:
            # แสดงทุกกิจกรรม — ตัวกรอง >500 ม. เดิมซ่อน warm-up/cool-down ของ Tong ทั้งเซสชัน
            # ทั้งที่ fact_activity_split มีข้อมูลครบ และทำให้ดูเหมือนระบบ sync มาไม่ครบ
            candidates = prepare_session_candidates(activity_df)
            if candidates.empty:
                st.info("ไม่มีกิจกรรมในช่วงเวลานี้")
            else:
                label_map = {}
                for _, r in candidates.iterrows():
                    distance_label = (f"{r['distance_km']:.2f} km"
                                      if pd.notna(r.get("distance_km")) else "ไม่มีระยะทาง")
                    label_map[int(r["activity_id"])] = (
                        f"{r['start_time_local']:%d %b %Y %H:%M} · "
                        f"{fmt_text(r['activity_name'], fmt_text(r['activity_type'], 'กิจกรรม'))} · "
                        f"{distance_label}"
                    )
                chosen_id = st.selectbox(
                    "กิจกรรมที่ต้องการวิเคราะห์",
                    options=list(label_map.keys()),
                    format_func=lambda i: label_map[i],
                )

                # --- การ์ดรายละเอียดเซสชัน (ข้อมูลเต็มจากนาฬิกา) ---
                arow = activity_df[activity_df["activity_id"] == chosen_id].iloc[0]

                def _fmt(v, unit="", fmt="{:.0f}"):
                    return (fmt.format(v) + unit) if pd.notna(v) else "–"

                st.subheader("ภาพรวมเซสชัน")

                def _dur(sec):
                    if pd.isna(sec):
                        return "–"
                    s = int(sec)
                    return (f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}" if s >= 3600
                            else f"{s // 60}:{s % 60:02d}")

                # แถวภาพรวมหลัก (แบบหน้าสรุปในแอป Garmin)
                o1 = st.columns(4)
                o1[0].metric("ระยะทาง", _fmt(arow.get("distance_km"), " km", "{:.2f}"), border=True)
                o1[1].metric("เวลา", _dur(arow.get("duration_sec")), border=True)
                o1[2].metric("เพซเฉลี่ย",
                             (fmt_pace(arow.get("avg_pace_min_per_km")) + " /km")
                             if pd.notna(arow.get("avg_pace_min_per_km")) else "–", border=True)
                o1[3].metric("HR เฉลี่ย", _fmt(arow.get("avg_hr"), " bpm"), border=True)

                with st.expander("ตัวเลขเพิ่มเติมจากนาฬิกา", icon=":material/monitor_heart:"):
                    o2 = st.columns(4)
                    o2[0].metric("Cadence เฉลี่ย", _fmt(arow.get("avg_cadence"), " spm"), border=True)
                    o2[1].metric("แคลอรี่", _fmt(arow.get("calories"), " kcal"), border=True)
                    o2[2].metric("ไต่ระดับรวม", _fmt(arow.get("elevation_gain_m"), " m"), border=True)
                    o2[3].metric("Power เฉลี่ย", _fmt(arow.get("avg_power"), " W"), border=True)

                    r1 = st.columns(4)
                    r1[0].metric("TE แอโรบิก", _fmt(arow.get("training_effect_aerobic"), "", "{:.1f}"), border=True)
                    r1[1].metric("TE แอนแอโรบิก", _fmt(arow.get("training_effect_anaerobic"), "", "{:.1f}"), border=True)
                    r1[2].metric("Training Load", _fmt(arow.get("training_load")), border=True)
                    r1[3].metric("Impact Load", _fmt(arow.get("impact_load")), border=True)

                    r2 = st.columns(4)
                    r2[0].metric("HR ต่ำสุด", _fmt(arow.get("min_hr"), " bpm"), border=True)
                    r2[1].metric("HR สูงสุด", _fmt(arow.get("max_hr"), " bpm"), border=True)
                    r2[2].metric("เหงื่อ (ประมาณ)", _fmt(arow.get("sweat_loss_ml"), " ml"), border=True)
                    r2[3].metric("Δ Body Battery", _fmt(arow.get("diff_body_battery")), border=True)

                    if pd.notna(arow.get("begin_stamina")) or pd.notna(arow.get("end_stamina")):
                        b, e = arow.get("begin_stamina"), arow.get("end_stamina")
                        sc = st.columns(4)
                        sc[0].metric("Stamina เริ่ม", _fmt(b, "%"), border=True)
                        sc[1].metric("Stamina จบ", _fmt(e, "%"), border=True)
                        sc[2].metric(
                            "Stamina ใช้ไป",
                            _fmt((b - e) if (pd.notna(b) and pd.notna(e)) else float("nan"), "%"),
                            border=True,
                        )

                    if pd.notna(arow.get("avg_ground_contact_time_ms")):
                        dc = st.columns(4)
                        dc[0].metric("Ground Contact", _fmt(arow.get("avg_ground_contact_time_ms"), " ms"), border=True)
                        dc[1].metric(
                            "Vertical Osc",
                            _fmt(arow.get("avg_vertical_oscillation_cm"), " cm", "{:.1f}"),
                            border=True,
                        )
                        dc[2].metric(
                            "Vertical Ratio",
                            _fmt(arow.get("avg_vertical_ratio"), " %", "{:.1f}"),
                            border=True,
                        )
                        dc[3].metric("Stride Length", _fmt(arow.get("avg_stride_length_cm"), " cm"), border=True)

                    if pd.notna(arow.get("weather_temp_c")):
                        wc = st.columns(4)
                        wc[0].metric("อุณหภูมิ", _fmt(arow.get("weather_temp_c"), " °C", "{:.1f}"), border=True)
                        wc[1].metric(
                            "รู้สึกเหมือน",
                            _fmt(arow.get("weather_apparent_temp_c"), " °C", "{:.1f}"),
                            border=True,
                        )
                        wc[2].metric("ความชื้น", _fmt(arow.get("weather_humidity"), " %"), border=True)
                        wc[3].metric("ลม", _fmt(arow.get("weather_wind_kph"), " km/h"), border=True)

                    # ฟิลด์ต่อไปนี้ถูกเก็บใน fact_activity มาตลอด แต่หน้าเดิมไม่เคยแสดง
                    # ทำให้ดูเหมือน sync มาไม่ครบ ทั้งที่ข้อมูลจริงอยู่ใน SQLite แล้ว.
                    def _has_any(*fields):
                        return any(pd.notna(arow.get(field)) for field in fields)

                    if _has_any(
                        "moving_duration_sec", "steps", "moderate_intensity_min",
                        "vigorous_intensity_min",
                    ):
                        st.markdown("**เวลาและกิจกรรม**")
                        tc = st.columns(4)
                        tc[0].metric("เวลาที่เคลื่อนไหว", _dur(arow.get("moving_duration_sec")), border=True)
                        tc[1].metric("จำนวนก้าวในกิจกรรม", _fmt(arow.get("steps"), " ก้าว"), border=True)
                        tc[2].metric(
                            "Intensity ปานกลาง",
                            _fmt(arow.get("moderate_intensity_min"), " นาที"),
                            border=True,
                        )
                        tc[3].metric(
                            "Intensity หนัก",
                            _fmt(arow.get("vigorous_intensity_min"), " นาที"),
                            border=True,
                        )

                    if _has_any(
                        "avg_speed_mps", "max_speed_mps", "avg_grade_adjusted_speed_mps",
                    ):
                        st.markdown("**ความเร็วจาก Garmin**")

                        def _speed_kph(value):
                            return (_fmt(value * 3.6, " km/h", "{:.1f}")
                                    if pd.notna(value) else "–")

                        vc = st.columns(3)
                        vc[0].metric("ความเร็วเฉลี่ย", _speed_kph(arow.get("avg_speed_mps")), border=True)
                        vc[1].metric("ความเร็วสูงสุด", _speed_kph(arow.get("max_speed_mps")), border=True)
                        vc[2].metric(
                            "Grade-adjusted speed",
                            _speed_kph(arow.get("avg_grade_adjusted_speed_mps")),
                            border=True,
                        )

                    if _has_any("vo2max_value", "normalized_power", "max_power", "max_cadence"):
                        st.markdown("**สมรรถนะในกิจกรรม**")
                        pc = st.columns(4)
                        pc[0].metric(
                            "VO2max จากกิจกรรม",
                            _fmt(arow.get("vo2max_value"), "", "{:.1f}"),
                            border=True,
                        )
                        pc[1].metric("Normalized Power", _fmt(arow.get("normalized_power"), " W"), border=True)
                        pc[2].metric("Power สูงสุด", _fmt(arow.get("max_power"), " W"), border=True)
                        pc[3].metric("Cadence สูงสุด", _fmt(arow.get("max_cadence"), " spm"), border=True)

                    if _has_any(
                        "elevation_loss_m", "min_elevation_m", "max_elevation_m", "bmr_calories",
                    ):
                        st.markdown("**ระดับความสูงและพลังงานเพิ่มเติม**")
                        ec = st.columns(4)
                        ec[0].metric("ลงระดับรวม", _fmt(arow.get("elevation_loss_m"), " m"), border=True)
                        ec[1].metric("ระดับต่ำสุด", _fmt(arow.get("min_elevation_m"), " m"), border=True)
                        ec[2].metric("ระดับสูงสุด", _fmt(arow.get("max_elevation_m"), " m"), border=True)
                        ec[3].metric("BMR calories", _fmt(arow.get("bmr_calories"), " kcal"), border=True)

                    activity_meta = []
                    if pd.notna(arow.get("activity_type")):
                        activity_meta.append(f"ประเภท: {arow.get('activity_type')}")
                    if pd.notna(arow.get("training_effect_label")):
                        activity_meta.append(f"Training effect: {arow.get('training_effect_label')}")
                    if pd.notna(arow.get("location_name")):
                        activity_meta.append(f"สถานที่: {arow.get('location_name')}")
                    if activity_meta:
                        st.caption(" · ".join(activity_meta))
                    if _has_any("start_latitude", "start_longitude"):
                        latitude = arow.get("start_latitude")
                        longitude = arow.get("start_longitude")
                        coordinate = (
                            f"{latitude:.6f}, {longitude:.6f}"
                            if pd.notna(latitude) and pd.notna(longitude) else "พิกัดไม่ครบ"
                        )
                        st.caption(f"พิกัดเริ่มกิจกรรม: {coordinate}")

                zc = ["hr_zone1_sec", "hr_zone2_sec", "hr_zone3_sec", "hr_zone4_sec", "hr_zone5_sec"]
                if set(zc).issubset(activity_df.columns) and arow[zc].notna().any():
                    zvals = [float(arow.get(c)) / 60 if pd.notna(arow.get(c)) else 0.0 for c in zc]
                    if sum(zvals) > 0:
                        zbar = pd.DataFrame({"โซน": ["Z1", "Z2", "Z3", "Z4", "Z5"], "นาที": zvals})
                        fig_z = px.bar(zbar, x="โซน", y="นาที", color="โซน",
                                       title="เวลาในโซน HR ของเซสชันนี้ (นาที)",
                                       color_discrete_sequence=BLUE_RAMP_5)
                        fig_z.update_layout(showlegend=False)
                        st.plotly_chart(fig_z, width="stretch")

                # ⚠️ ห้ามกรอง splits ตามความยาวรอบ (แก้ 7 ส.ค. 69) — แถวใน fact_activity_split
                # คือ "lap ที่นาฬิกาบันทึก" ไม่ใช่ "ทุก 1 กม." เซสชัน interval สั้น ๆ จึงมีรอบ
                # หลักสิบเมตรเป็นเรื่องปกติ. ตัวกรอง `distance_m >= 100` เดิมลบทั้งเซสชันทิ้ง
                # แล้วหน้าเว็บขึ้น "ยังไม่ได้ดึง splits" ทั้งที่ดึงมาครบ (ต้อง activity 23885677442:
                # 0.85 กม. 12 รอบ 12–92 ม. — รวม 6 เซสชันใน DB ที่โดนแบบเดียวกัน)
                # → ข้อความ "ยังไม่ได้ดึง" ต้องผูกกับ "load_splits ไม่คืนแถวเลย" เท่านั้น
                splits = load_splits(chosen_id)

                if splits.empty:
                    if pd.isna(arow.get("distance_m")) or arow.get("distance_m") <= 0:
                        st.info("กิจกรรมนี้ไม่มีระยะทางจาก Garmin จึงไม่มี splits โดยปกติ "
                                "แต่ตัวเลขเวลา, HR และ Training Load ด้านบนยังแสดงครบตามที่นาฬิกาส่ง")
                    else:
                        st.info("ยังไม่ได้ดึง splits — fast sync จะลองเติมให้อัตโนมัติในรอบถัดไป "
                                "และ full sync 21:00 จะตรวจซ้ำ")
                else:
                    # --- ครึ่งแรก vs ครึ่งหลัง: แสดงเลขดิบ ไม่ตัดสินโดยไม่รู้เป้าหมายเซสชัน ---
                    if len(splits) >= 2:
                        p1, p2, hr1, hr2 = analyze_distance_halves(splits)

                        split_pct = (p2 - p1) / p1 * 100 if pd.notna(p1) and pd.notna(p2) and p1 > 0 else float("nan")

                        with st.container(horizontal=True):
                            st.metric("ครึ่งแรก", f"{fmt_pace(p1)} /km", border=True)
                            st.metric("ครึ่งหลัง", f"{fmt_pace(p2)} /km", border=True)
                            st.metric(
                                "เพซครึ่งหลังเทียบครึ่งแรก",
                                f"{split_pct:+.1f}%" if pd.notna(split_pct) else "–",
                                delta_color="off", border=True,
                                help="ค่าบวก = ครึ่งหลังช้ากว่า; ต้องอ่านตามเป้าหมายเซสชัน "
                                     "เส้นทาง และความชัน ไม่ใช้เส้นตัด ±2% สากล",
                            )
                            if pd.notna(hr1) and pd.notna(hr2):
                                st.metric("HR ครึ่งแรก → หลัง", f"{hr1:.0f} → {hr2:.0f} bpm",
                                          delta=fmt_signed_delta(hr2 - hr1, " bpm"),
                                          delta_color="off", border=True)

                    # --- กราฟ pace + HR (แกน x ร่วม สองแถว — ไม่ใช้ dual-axis) ---
                    x_labels = [f"{int(n)}" for n in splits["split_num"]]
                    pace_txt = [fmt_pace(p) for p in splits["avg_pace_min_km"]]
                    dist_km = (splits["distance_m"] / 1000).round(2)

                    fig_sp = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                           vertical_spacing=0.07, row_heights=[0.55, 0.45])
                    fig_sp.add_trace(go.Scatter(
                        x=x_labels, y=splits["avg_pace_min_km"], mode="lines+markers",
                        line=dict(color=C_BLUE, width=2), marker=dict(size=8), name="เพซ",
                        customdata=list(zip(pace_txt, dist_km)),
                        hovertemplate="รอบที่ %{x} (%{customdata[1]} กม.)<br>เพซ %{customdata[0]} /กม.<extra></extra>",
                    ), row=1, col=1)
                    if splits["avg_hr"].notna().any():
                        fig_sp.add_trace(go.Scatter(
                            x=x_labels, y=splits["avg_hr"], mode="lines+markers",
                            line=dict(color=SERIES_COLORS["avg_hr"], width=2),
                            marker=dict(size=8), name="HR เฉลี่ย",
                            hovertemplate="รอบที่ %{x}<br>HR %{y:.0f} bpm<extra></extra>",
                        ), row=2, col=1)

                    pace_clean = splits["avg_pace_min_km"].dropna()
                    pace_axis_kwargs = {}
                    if not pace_clean.empty:
                        tickvals, ticktext = pace_axis_ticks(pace_clean)
                        pace_axis_kwargs = {"tickvals": tickvals, "ticktext": ticktext}
                    fig_sp.update_yaxes(title_text="เพซ (นาที/กม.)", autorange="reversed",
                                        row=1, col=1, **pace_axis_kwargs)
                    fig_sp.update_yaxes(title_text="HR (bpm)", row=2, col=1)
                    fig_sp.update_xaxes(title_text="รอบที่ (Split)", row=2, col=1)
                    fig_sp.update_layout(title="เพซและ HR ราย Split (เพซ: ยิ่งสูง = ยิ่งเร็ว)",
                                         showlegend=True, hovermode="x unified",
                                         legend=dict(orientation="h", yanchor="bottom", y=1.02))
                    st.plotly_chart(fig_sp, width="stretch")

                    # --- กราฟ Cadence + Power + Elevation ราย Split ---
                    extra_rows = []
                    if splits["avg_cadence"].notna().any():
                        extra_rows.append(("avg_cadence", "Cadence (spm)", SERIES_COLORS["avg_cadence"]))
                    if "avg_power" in splits and splits["avg_power"].notna().any():
                        extra_rows.append(("avg_power", "Power (W)", SERIES_COLORS["avg_power"]))
                    if splits["elevation_gain_m"].notna().any():
                        extra_rows.append(("elevation_gain_m", "Elevation Gain (m)", SERIES_COLORS["elevation_gain_m"]))

                    if extra_rows:
                        fig_extra = make_subplots(
                            rows=len(extra_rows), cols=1, shared_xaxes=True,
                            vertical_spacing=0.12,
                            subplot_titles=[t for _, t, _ in extra_rows])
                        for i, (col, title, color) in enumerate(extra_rows, 1):
                            fig_extra.add_trace(go.Bar(
                                x=x_labels, y=splits[col], name=title,
                                marker_color=color,
                                hovertemplate=f"รอบที่ %{{x}}<br>{title}: %{{y:.0f}}<extra></extra>",
                            ), row=i, col=1)
                        fig_extra.update_xaxes(title_text="รอบที่ (Split)", row=len(extra_rows), col=1)
                        fig_extra.update_layout(showlegend=False, title="Cadence และ Elevation ราย Split")
                        st.plotly_chart(fig_extra, width="stretch")

                    # --- ตาราง splits รายรอบ เต็ม (แสดงตรง ไม่ซ่อนใน expander) ---
                    st.subheader("ตาราง Splits (ผลต่อรอบ)")
                    num0 = st.column_config.NumberColumn(format="%.0f")
                    table_data = {
                        "รอบที่": splits["split_num"].astype(int),
                        "ระยะ (km)": dist_km,
                        # เวลาต่อรอบคือค่าที่นาฬิกาวัดตรง ๆ ส่วนเพซเป็นค่าที่หารมาอีกที —
                        # เซสชัน interval (เที่ยว ~19 วิ สลับพัก ~50 วิ) อ่านจากเพซไม่ได้เลย
                        # เพราะเพซของเที่ยวพักกลายเป็น 14:40 ทั้งที่ duration_sec มีครบทุกแถว
                        "เวลา": [fmt_sec(value) for value in splits["duration_sec"]],
                        "เพซ": pace_txt,
                        "HR เฉลี่ย": splits["avg_hr"],
                        "HR สูงสุด": splits["max_hr"],
                        "Cadence": splits["avg_cadence"],
                    }
                    cfg = {"HR เฉลี่ย": num0, "HR สูงสุด": num0, "Cadence": num0}

                    def _add(colname, label, fmt=num0):
                        if colname in splits and splits[colname].notna().any():
                            table_data[label] = splits[colname]
                            if fmt is not None:
                                cfg[label] = fmt

                    _add("avg_power", "Power (W)")
                    _add("max_power", "Power สูงสุด (W)")
                    _add("normalized_power", "Normalized Power (W)")
                    _add("avg_stride_length_cm", "Stride (cm)")
                    _add("ground_contact_time_ms", "GCT (ms)")
                    _add("vertical_oscillation_cm", "Vert Osc (cm)",
                         st.column_config.NumberColumn(format="%.1f"))
                    _add("vertical_ratio", "Vertical Ratio (%)",
                         st.column_config.NumberColumn(format="%.1f"))
                    _add("max_cadence", "Cadence สูงสุด")
                    if "avg_speed_mps" in splits and splits["avg_speed_mps"].notna().any():
                        table_data["ความเร็วเฉลี่ย (km/h)"] = splits["avg_speed_mps"] * 3.6
                        cfg["ความเร็วเฉลี่ย (km/h)"] = st.column_config.NumberColumn(format="%.1f")
                    table_data["ไต่ (m)"] = splits["elevation_gain_m"]
                    cfg["ไต่ (m)"] = num0
                    _add("elevation_loss_m", "ลง (m)")
                    _add("intensity_type", "ประเภท", None)  # text

                    st.dataframe(pd.DataFrame(table_data), hide_index=True, column_config=cfg)


# --- AUTO REFRESH ---
# **ต้องอยู่ระดับบนสุด ห้ามเยื้องเข้าไปในบล็อกแท็บใด ๆ** — มันเป็น
# `@st.fragment(run_every=...)` การเรียกคือการ *ลงทะเบียน* ถ้าอยู่ใต้ `if tab_x.open:`
# แท็บอื่นจะไม่ลงทะเบียนเลย = ค้างข้อมูลเดิมเงียบ ๆ โดยไม่มี error (เกิดจริงใน c9f4b07
# ตอนใส่ lazy tabs แล้วบรรทัดนี้ถูกเยื้องตามไปด้วย ผู้ใช้เจอก่อนเทส)
auto_refresh_dashboard()
