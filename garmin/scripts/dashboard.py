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

# ประเภทกิจกรรมที่นับเป็น "วิ่ง" (ใช้คำนวณโหลด / EF / 80-20)
RUN_TYPES = ("running", "track_running", "trail_running", "treadmill_running")

# LTHR จากผลเทสเป็นทางการ — ตารางนักกีฬาใน docs/PROJECT.md คือที่เก็บผลเทส อัปเดตทั้งสองที่ให้ตรงกัน
# tong: 5K TT 14 ก.ค. 69 | dan: VCR30 8 ก.ค. 69
# p'kao: เทสแลบ Lactate ไม่มีค่า HR → ใช้ Garmin LT จากนาฬิกา แทนค่าเดา 89%
#        อัปเดต 4 ส.ค. 69: นาฬิกาตรวจ LT ใหม่ 31 ก.ค. = HR 181 / pace 4:41 (เดิม 16 ก.ค. HR 184 / 5:02)
LTHR_BY_SLUG = {"tong": 171, "dan": 178, "p'kao": 181}
LTHR_SOURCE_BY_SLUG = {
    "tong": "จากผลเทสล่าสุด (5K TT 14 ก.ค.)",
    "dan": "จากผลเทสล่าสุด (VCR30 8 ก.ค.)",
    "p'kao": "จาก Garmin LT ล่าสุด 31 ก.ค. (เทสแลบไม่มีค่า HR)",
}

# ขอบเขตโซนตาม %LTHR (Friel): เบา Z1-2 <= 89%, กลาง Z3 90-93%, หนัก Z4-5 >= 94%
EASY_MAX_PCT = 0.89
GRAY_MAX_PCT = 0.94

# --- ประสิทธิภาพการวิ่งเบา (EF) — ตัวตัดสินความสด แทน ACWR ที่ถอดออก 25 ส.ค. 69 ---
# ACWR ถูกถอดเพราะหลักฐานตีตก: Garmin-RUNSAFE (Br J Sports Med 2025;59:1203-1210,
# 5,205 นักวิ่ง / 588,071 เซสชัน) พบว่า ACWR สัมพันธ์กับการบาดเจ็บ "ในทิศตรงข้าม"
# (HRR 0.75, 95% CI 0.59-0.96) ส่วน week-to-week ratio ไม่สัมพันธ์เลย และ
# Impellizzeri 2020 (IJSPP 15(6):907) ชี้ปัญหา mathematical coupling ของอัตราส่วนนี้
#
# EF = ความเร็ว (เมตร/นาที) ÷ HR เฉลี่ย ในรัน easy — วิ่งเร็วขึ้นที่หัวใจเท่าเดิม = สดขึ้น
# แนวคิดมาจากระบบ green/yellow/red light ของ Marius Bakken (Norwegian model) ที่ใช้
# "HR ตอนวอร์มอัพที่เพซเดิม" เป็นตัวชี้ความสด ต่างจาก ACWR ตรงที่วัดการตอบสนองของร่างกาย
# ไม่ใช่ปริมาณงานที่ทำไป
EF_MIN_DISTANCE_M = 3000.0   # รันสั้นกว่านี้ EF แกว่งจนใช้ตัดสินไม่ได้
EF_RECENT_RUNS = 3           # ค่าปัจจุบัน = median 3 รันล่าสุด (รันเดี่ยว SD 6.5-7.9%)
EF_BASELINE_DAYS = 28
EF_BASELINE_MIN_RUNS = 5
EF_STALE_DAYS = 14           # ไม่มีรัน easy นานกว่านี้ = เลิกรายงานความสดของเมื่อวาน
# เกณฑ์ % วัดจาก SD ของข้อมูลจริงใน garmin.db หลังปรับเรียบ 3 รัน
# (ต้อง SD 4.4% n=22 · แดน SD 3.5% n=94) → เฝ้าระวัง ~1 SD, ต้องพัก ~2 SD
EF_WATCH_PCT = -3.0
EF_REST_PCT = -7.0
EF_GAIN_PCT = 5.0

# สีสถานะ (ผ่าน CVD validation) — ใช้คู่กับข้อความกำกับเสมอ ไม่สื่อด้วยสีอย่างเดียว
C_GOOD = "#0ca30c"
C_WARN = "#fab219"
C_CRIT = "#d03b3b"
C_NEUTRAL = "#c3c9d2"  # เทาอมฟ้าอ่อน — เห็นได้บนพื้นขาว
C_BLUE = "#2a78d6"   # เส้นข้อมูลหลัก
C_SECOND = "#eb6834" # เส้นที่สองในกราฟเดียวกัน (ตรวจ CVD แล้ว ΔE 24.7 จาก C_BLUE)

C_CONTEXT = "#8a8d94"  # เส้นฐาน เส้นตาราง วันพัก — บริบทต้องถอยไปข้างหลัง (กฎกราฟ 04)

# กฎกราฟ 02: ค่าที่มีลำดับใช้สีเดียวไล่อ่อน→เข้ม ไม่ใช่รุ้ง — เขียว-เหลือง-แดงทำให้ "เบา"
# อ่านว่าดี และ "หนัก" อ่านว่าอันตราย ทั้งที่เป็นแค่ระดับความหนัก ไม่ใช่คำตัดสิน
# และมันยังไปชนสีสถานะซึ่งจองไว้ให้สถานะอย่างเดียว (กฎกราฟ 03)
BLUE_RAMP_3 = ["#cde2fb", C_BLUE, "#104281"]
BLUE_RAMP_5 = ["#cde2fb", "#86b6ef", C_BLUE, "#1a5aa8", "#104281"]

INTENSITY_ORDER = ["เบา (Z1–2)", "กลาง (Z3)", "หนัก (Z4–5)"]
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


# --- HELPERS ---
def fmt_num(value, suffix="", decimals=None):
    """Format a metric without showing a misleading ``.0`` for integer values."""
    if pd.isna(value):
        return "–"
    number = float(value)
    if decimals is None:
        decimals = 0 if number.is_integer() else 1
    return f"{number:.{decimals}f}{suffix}"


def fmt_text(value, fallback=""):
    """Return clean text without leaking Pandas NaN into the UI."""
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def has_any_value(df, columns):
    """Return True when at least one existing column contains a real value."""
    if df is None or df.empty:
        return False
    existing = [column for column in columns if column in df.columns]
    return bool(existing) and bool(df[existing].notna().any().any())


def available_series(df, label_map):
    """Return ``[(column, human label), ...]`` only for non-empty chart traces."""
    if df is None or df.empty:
        return []
    return [
        (column, label)
        for column, label in label_map.items()
        if column in df.columns and df[column].notna().any()
    ]


def chart_title(series, titles, fallback=""):
    """หัวข้อกราฟต้องเอ่ยเฉพาะเส้นที่ถูกวาดจริง

    ``series`` คือผลของ ``available_series()`` ซึ่งตัดคอลัมน์ที่ Garmin ไม่เคยส่งค่า
    ออกไปแล้ว ``titles`` จึง map จาก **ชุดคอลัมน์ที่เหลือ** (frozenset) → หัวข้อ
    ไม่ใช่หัวข้อคงที่ตามที่ตั้งใจจะวาด — นาฬิกาบางรุ่นไม่ส่ง Training Readiness เลย
    หัวข้อที่เอ่ยถึงมันจึงกลายเป็นคำสัญญาที่กราฟไม่มีเส้นรองรับ
    """
    drawn = frozenset(column for column, _ in series)
    return titles.get(drawn, fallback)


def latest_field(df, column, timestamp_columns=()):
    """Return the newest non-null value of one field, independently of other fields.

    A daily wellness row is assembled from several Garmin endpoints.  Picking one
    "latest row" can therefore hide yesterday's valid Sleep/HRV when today's row
    only contains Body Battery.  This helper deliberately selects each field on
    its own.  A source timestamp (notably Training Readiness) wins within a day;
    calendar date and row ``fetched_at`` remain backward-compatible fallbacks.
    """
    if (df is None or df.empty or column not in df.columns
            or "calendar_date" not in df.columns):
        return None
    candidates = df[df[column].notna()].copy()
    if candidates.empty:
        return None

    candidates["_sort_calendar"] = pd.to_datetime(
        candidates.get("calendar_date"), errors="coerce", utc=True
    )
    candidates["_sort_source"] = pd.Series(
        pd.NaT, index=candidates.index, dtype="datetime64[ns, UTC]"
    )
    candidates["_source_column_used"] = None
    for name in timestamp_columns:
        if name not in candidates.columns:
            continue
        parsed = pd.to_datetime(candidates[name], errors="coerce", utc=True)
        fill = candidates["_sort_source"].isna() & parsed.notna()
        candidates.loc[fill, "_sort_source"] = parsed[fill]
        candidates.loc[fill, "_source_column_used"] = name
    if "fetched_at" in candidates.columns:
        candidates["_sort_fetched"] = pd.to_datetime(
            candidates["fetched_at"], errors="coerce", utc=True
        )
    else:
        candidates["_sort_fetched"] = pd.NaT

    candidates = candidates.sort_values(
        ["_sort_calendar", "_sort_source", "_sort_fetched"],
        na_position="first",
    )
    row = candidates.iloc[-1]
    source_column = row.get("_source_column_used")
    calendar = pd.to_datetime(row.get("calendar_date"), errors="coerce")
    fetched = pd.to_datetime(row.get("fetched_at"), errors="coerce", utc=True)
    source_timestamp = (
        pd.to_datetime(row.get(source_column), errors="coerce")
        if source_column else pd.NaT
    )
    return {
        "value": row[column],
        "date": calendar.date() if pd.notna(calendar) else None,
        "fetched_at": fetched,
        "source_timestamp": source_timestamp,
        "source_column": source_column,
        "row": row,
    }


def body_battery_snapshots(df, today_date):
    """Return ``(display, latest_completed_high)`` with stable day semantics.

    Body Battery has two different meanings in this dashboard: today's card is
    the most-recent intraday level, while a completed day is represented by its
    daily high.  Keeping the completed snapshot separate also prevents a
    partial ``body_battery_high`` from today from suppressing yesterday's alert.
    """
    if df is None or df.empty or "calendar_date" not in df.columns:
        return None, None
    today_date = pd.Timestamp(today_date).date()
    dates = pd.to_datetime(df["calendar_date"], errors="coerce").dt.date
    today_rows = df.loc[dates == today_date]
    completed_rows = df.loc[dates < today_date]
    current = latest_field(today_rows, "bb_most_recent")
    completed = latest_field(completed_rows, "body_battery_high")
    return current or completed, completed


def period_metric(df, column, today_date, exclude_partial_today=True,
                  period_start=None, period_end=None):
    """Calculate a period mean and expose the true sample denominator.

    Today's daily aggregates (Stress, Body Battery high, kcal, floors, etc.) are
    partial until local midnight.  They are excluded from averages by default but
    remain visible in charts and detail tables.
    """
    today_date = pd.Timestamp(today_date).date()
    start = period_start
    end = period_end
    if start is None and df is not None and not df.empty and "calendar_date" in df:
        start_ts = pd.to_datetime(df["calendar_date"], errors="coerce").min()
        start = start_ts.date() if pd.notna(start_ts) else None
    if end is None and df is not None and not df.empty and "calendar_date" in df:
        end_ts = pd.to_datetime(df["calendar_date"], errors="coerce").max()
        end = end_ts.date() if pd.notna(end_ts) else None
    start = pd.Timestamp(start).date() if start is not None else None
    end = pd.Timestamp(end).date() if end is not None else None

    selected_days = ((end - start).days + 1) if start and end and end >= start else 0
    excluded_today = bool(
        exclude_partial_today and start and end and start <= today_date <= end
    )
    total_days = max(0, selected_days - (1 if excluded_today else 0))
    if (df is None or df.empty or column not in df.columns
            or "calendar_date" not in df.columns):
        return {
            "mean": float("nan"), "count": 0, "total_days": total_days,
            "selected_days": selected_days, "excluded_today": excluded_today,
        }

    values = df[["calendar_date", column]].copy()
    values["calendar_date"] = pd.to_datetime(values["calendar_date"], errors="coerce").dt.date
    if start:
        values = values[values["calendar_date"] >= start]
    if end:
        values = values[values["calendar_date"] <= end]
    if excluded_today:
        values = values[values["calendar_date"] != today_date]
    numeric = pd.to_numeric(values[column], errors="coerce").dropna()
    return {
        "mean": numeric.mean() if not numeric.empty else float("nan"),
        "count": int(numeric.count()),
        "total_days": total_days,
        "selected_days": selected_days,
        "excluded_today": excluded_today,
    }


def calendar_aligned_frame(df, date_column, period_start, period_end):
    """Reindex daily data so a missing whole day becomes an explicit NaN row."""
    if df is None or date_column not in getattr(df, "columns", ()):
        return pd.DataFrame({date_column: pd.date_range(period_start, period_end, freq="D")})
    aligned = df.copy()
    aligned[date_column] = pd.to_datetime(aligned[date_column], errors="coerce").dt.normalize()
    aligned = aligned.dropna(subset=[date_column]).drop_duplicates(date_column, keep="last")
    index = pd.date_range(pd.Timestamp(period_start), pd.Timestamp(period_end), freq="D")
    return (
        aligned.set_index(date_column)
        .reindex(index)
        .rename_axis(date_column)
        .reset_index()
    )


def fmt_recovery_time(minutes):
    """Format Garmin Recovery Time, whose API/database raw unit is minutes."""
    if pd.isna(minutes):
        return "–"
    total_minutes = max(0, int(round(float(minutes))))
    hours, remaining = divmod(total_minutes, 60)
    if hours and remaining:
        return f"{hours} ชม. {remaining} นาที"
    if hours:
        return f"{hours} ชม."
    return f"{remaining} นาที"


def get_recovery_minutes(row):
    """Read Recovery Time in raw Garmin minutes."""
    if row is None:
        return float("nan")
    value = row.get("recovery_time_min")
    return value if pd.notna(value) else float("nan")


def recovery_minutes_series(df):
    """Return Recovery Time minutes without dropping calendar rows that are NULL.

    Keeping the original index lets Plotly render a real gap when
    ``connectgaps=False`` instead of drawing a line across a missing day.
    """
    if df is None:
        return pd.Series(dtype=float)
    if "recovery_time_min" not in df.columns:
        return pd.Series(float("nan"), index=df.index, dtype=float)
    return pd.to_numeric(df["recovery_time_min"], errors="coerce")


def bangkok_date(now_utc=None):
    """Return the dashboard business date, pinned to Asia/Bangkok."""
    if now_utc is None:
        now_utc = datetime.datetime.now(datetime.timezone.utc)
    elif isinstance(now_utc, pd.Timestamp):
        now_utc = now_utc.to_pydatetime()
    if now_utc.tzinfo is None:
        # Explicit contract for deterministic tests and legacy callers: naive
        # timestamps supplied here represent UTC, never the host machine zone.
        now_utc = now_utc.replace(tzinfo=datetime.timezone.utc)
    return now_utc.astimezone(ZoneInfo("Asia/Bangkok")).date()


def to_bangkok_timestamp(value):
    """Parse a DB UTC timestamp (including legacy naive UTC) as Bangkok time."""
    stamp = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(stamp):
        return pd.NaT
    return stamp.tz_convert(ZoneInfo("Asia/Bangkok"))


def device_inventory_labels(records, now_utc=None, stale_days=90):
    """Format recently seen devices and omit inventory entries stale >90 days."""
    if now_utc is None:
        now = pd.Timestamp.now(tz="UTC")
    else:
        now = pd.to_datetime(now_utc, errors="coerce", utc=True)
        if pd.isna(now):
            now = pd.Timestamp.now(tz="UTC")

    by_name = {}
    for record in records or []:
        product_name = record.get("product_display_name")
        display_name = record.get("display_name")
        name = next(
            (value.strip() for value in (product_name, display_name)
             if isinstance(value, str) and value.strip()),
            None,
        )
        if not name:
            continue
        seen = pd.to_datetime(record.get("last_seen_at_utc"), errors="coerce", utc=True)
        if pd.notna(seen) and (now - seen).total_seconds() > stale_days * 86400:
            continue
        previous = by_name.get(name)
        if previous is None or (pd.notna(seen) and (pd.isna(previous) or seen > previous)):
            by_name[name] = seen

    labels = []
    for name, seen in by_name.items():
        if pd.notna(seen):
            local_seen = seen.tz_convert(ZoneInfo("Asia/Bangkok"))
            labels.append(f"{name} (พบล่าสุด {local_seen.strftime('%d/%m/%Y')})")
        else:
            labels.append(f"{name} (เคยพบ; ไม่มีเวลา last_seen)")
    return labels


def summarize_metric_group(fields, history_counts, selected_counts, latest_dates):
    """Classify a metric group from observed Garmin data, never from model guesses."""
    fields = tuple(fields)
    history_available = sum(int(history_counts.get(field, 0) or 0) > 0 for field in fields)
    selected_available = sum(int(selected_counts.get(field, 0) or 0) > 0 for field in fields)
    real_dates = []
    for field in fields:
        if int(history_counts.get(field, 0) or 0) <= 0:
            continue
        parsed = pd.to_datetime(latest_dates.get(field), errors="coerce")
        if pd.notna(parsed):
            real_dates.append(parsed.date())

    if history_available == 0:
        state = "never_received"
    elif selected_available == 0:
        state = "outside_range"
    elif selected_available < len(fields):
        state = "partial"
    else:
        state = "available"
    return {
        "state": state,
        "history_available": history_available,
        "selected_available": selected_available,
        "total_fields": len(fields),
        "latest_date": max(real_dates) if real_dates else None,
    }


def field_freshness(field_snapshot, today_date):
    """Human-readable field date/freshness; never imply row freshness per field."""
    if not field_snapshot or not field_snapshot.get("date"):
        return "ไม่มีข้อมูล"
    today_date = pd.Timestamp(today_date).date()
    value_date = field_snapshot["date"]
    age = (today_date - value_date).days
    if age == 0:
        relative = "วันนี้"
    elif age == 1:
        relative = "เมื่อวาน"
    elif age > 1:
        relative = f"{age} วันก่อน"
    else:
        relative = "วันที่ในอนาคต"
    return f"{value_date.strftime('%d/%m/%Y')} · {relative}"


def field_age_days(field_snapshot, today_date):
    """Return calendar-day age for a field snapshot, or None when unavailable."""
    if not field_snapshot or not field_snapshot.get("date"):
        return None
    return (pd.Timestamp(today_date).date() - field_snapshot["date"]).days


def readiness_when(field_snapshot, today_date):
    """Prefer the Garmin snapshot timestamp and fall back to the daily date."""
    if not field_snapshot:
        return "ไม่มีข้อมูล"
    stamp = field_snapshot.get("source_timestamp")
    if pd.notna(stamp):
        # Local timestamp is preferred by caller.  UTC timestamps retain their
        # timezone marker rather than being silently presented as Thai local time.
        suffix = " UTC" if field_snapshot.get("source_column") == "readiness_timestamp_utc" else " น."
        return f"{stamp.strftime('%d/%m/%Y %H:%M')}{suffix}"
    return field_freshness(field_snapshot, today_date)


def wellness_quality_flags(df):
    """Flag plausible source anomalies without removing or rewriting raw values."""
    if df is None or df.empty:
        return []
    flags = []

    def _dated_values(mask, column, limit=4):
        rows = df.loc[mask, ["calendar_date", column]].head(limit)
        return ", ".join(
            f"{str(row['calendar_date'])[:10]}={fmt_num(row[column])}"
            for _, row in rows.iterrows()
        )

    if "resting_hr" in df:
        values = pd.to_numeric(df["resting_hr"], errors="coerce")
        mask = values.notna() & ((values < 30) | (values > 100))
        if mask.any():
            flags.append("RHR นอกช่วงตรวจทาน 30–100 bpm: " + _dated_values(mask, "resting_hr"))
    if {"body_battery_high", "body_battery_low"}.issubset(df.columns):
        high = pd.to_numeric(df["body_battery_high"], errors="coerce")
        low = pd.to_numeric(df["body_battery_low"], errors="coerce")
        mask = ((high.notna() & ~high.between(5, 100))
                | (low.notna() & ~low.between(5, 100))
                | (high.notna() & low.notna() & (high < low)))
        if mask.any():
            dates = ", ".join(str(value)[:10] for value in df.loc[mask, "calendar_date"].head(4))
            flags.append(f"Body Battery นอกช่วง 5–100 หรือ high<low: {dates}")
    if "sleep_duration_sec" in df:
        duration = pd.to_numeric(df["sleep_duration_sec"], errors="coerce")
        mask = duration.notna() & (duration > 0) & (duration < 3 * 3600)
        if mask.any():
            dates = ", ".join(str(value)[:10] for value in df.loc[mask, "calendar_date"].head(4))
            flags.append(f"เวลานอนสั้นกว่า 3 ชม. (อาจเป็นการนอนสั้นจริง/บันทึกไม่ครบ): {dates}")
    return flags


def mark_partial_today(fig, today_date, period_start, period_end):
    """Mark today's still-changing point on a Plotly date chart."""
    start = pd.Timestamp(period_start).date()
    end = pd.Timestamp(period_end).date()
    if start <= today_date <= end:
        x_value = datetime.datetime.combine(today_date, datetime.time.min)
        fig.add_shape(
            type="line", x0=x_value, x1=x_value, y0=0, y1=1,
            xref="x", yref="paper", line=dict(color=C_CONTEXT, dash="dot", width=1),
        )
        fig.add_annotation(
            x=x_value, y=1, xref="x", yref="paper", text="วันนี้ · ยังไม่ครบวัน",
            showarrow=False, xanchor="left", yanchor="bottom", font=dict(size=10, color="#61656d"),
        )
    return fig


def fmt_pace(pace_min_per_km):
    """แปลงเพซ (นาทีทศนิยม) เป็น M:SS เช่น 5.75 -> 5:45"""
    if pd.isna(pace_min_per_km):
        return "–"
    minutes = int(pace_min_per_km)
    seconds = int(round((pace_min_per_km - minutes) * 60))
    if seconds == 60:
        minutes, seconds = minutes + 1, 0
    return f"{minutes}:{seconds:02d}"


def fmt_sec(sec):
    """แปลงวินาทีเป็นเวลาอ่านง่าย เช่น 1323 -> 22:03, 14023 -> 3:53:43"""
    if pd.isna(sec):
        return "–"
    s = int(round(sec))
    if s >= 3600:
        return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"
    return f"{s // 60}:{s % 60:02d}"


def load_trend_display(acute, chronic_wk, metric, unit):
    """โหลด 7 วันแบบดิบ + ทิศทางเทียบฐาน 28 วัน — ไม่หารเป็นอัตราส่วนอีกแล้ว

    เดิมช่องนี้เป็น ACWR (โหลด 7 วัน ÷ ฐาน 28 วัน) แต่หลักฐานหาเกณฑ์ตัดที่ทำนาย
    การบาดเจ็บได้ไม่เจอ (ดูหมายเหตุที่ค่าคงที่ EF_* ด้านบน) ตัวเลขนี้จึงเป็น
    "บริบท" ว่าสัปดาห์นี้ทำไปเท่าไหร่เทียบกับที่เคยทำ ไม่ใช่คำตัดสินว่าดีหรือแย่
    """
    if pd.isna(acute):
        return "–"
    digits = 0 if metric == "training_load" else 1
    shown = f"{acute:.{digits}f} {unit}"
    if pd.isna(chronic_wk) or chronic_wk <= 0:
        return shown
    return f"{shown} · {(acute / chronic_wk - 1) * 100:+.0f}% จากฐาน 28 วัน"


def efficiency_factor(distance_m, duration_sec, avg_hr):
    """EF = ความเร็ว (เมตร/นาที) ÷ HR เฉลี่ย — คืน NaN เมื่อขาดค่าใดค่าหนึ่ง"""
    distance = pd.to_numeric(distance_m, errors="coerce")
    duration = pd.to_numeric(duration_sec, errors="coerce")
    heart_rate = pd.to_numeric(avg_hr, errors="coerce")
    if pd.isna(distance) or pd.isna(duration) or pd.isna(heart_rate):
        return float("nan")
    if duration <= 0 or heart_rate <= 0:
        return float("nan")
    return (distance / (duration / 60.0)) / heart_rate


def easy_run_efficiency(runs, lthr):
    """EF รายเซสชันของ "รัน easy" เท่านั้น (HR <= 89% LTHR และระยะ >= 3 กม.)

    ต้องคัดเฉพาะรัน easy เพราะ EF ของเซสชันหนักสะท้อนชนิดของงาน ไม่ใช่ความสด
    ไม่มี LTHR = ไม่มีเส้นแบ่ง easy จึงคืนตารางว่างแทนการเดาเกณฑ์
    """
    columns = ["date", "ef"]
    if runs is None or runs.empty or not lthr:
        return pd.DataFrame(columns=columns)
    easy_max_hr = lthr * EASY_MAX_PCT
    rows = []
    for _, run in runs.iterrows():
        heart_rate = pd.to_numeric(run.get("avg_hr"), errors="coerce")
        distance = pd.to_numeric(run.get("distance_m"), errors="coerce")
        if pd.isna(heart_rate) or heart_rate > easy_max_hr:
            continue
        if pd.isna(distance) or distance < EF_MIN_DISTANCE_M:
            continue
        value = efficiency_factor(distance, run.get("duration_sec"), heart_rate)
        if pd.isna(value):
            continue
        rows.append({"date": pd.Timestamp(run["date"]), "ef": value})
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def efficiency_change_pct(easy_ef, today):
    """% ที่ median ของ 3 รัน easy ล่าสุด ต่างจาก median ของฐาน 28 วันก่อนหน้า

    คืน NaN เมื่อหลักฐานไม่พอ — รัน easy ล่าสุดน้อยกว่า 3 ครั้ง, ฐานน้อยกว่า 5 ครั้ง,
    หรือรัน easy ล่าสุดเก่ากว่า 14 วัน (ค่าเก่าต้องไม่ถูกรายงานเป็นความสดวันนี้)
    """
    if easy_ef is None or easy_ef.empty:
        return float("nan")
    frame = easy_ef.sort_values("date")
    anchor = frame["date"].iloc[-1]
    if (pd.Timestamp(today) - anchor).days > EF_STALE_DAYS:
        return float("nan")
    recent = frame.tail(EF_RECENT_RUNS)
    if len(recent) < EF_RECENT_RUNS:
        return float("nan")
    # 3 รันล่าสุดต้องอยู่ใกล้กันพอจะเรียกว่า "ตอนนี้" — ไม่งั้นรันเดือนก่อนจะถูกดึงมา
    # เฉลี่ยรวมกับรันเมื่อวานแล้วรายงานเป็นความสดปัจจุบัน
    if (anchor - recent["date"].iloc[0]).days > EF_STALE_DAYS:
        return float("nan")
    baseline = frame[
        (frame["date"] < anchor)
        & (frame["date"] >= anchor - pd.Timedelta(days=EF_BASELINE_DAYS))
    ]
    if len(baseline) < EF_BASELINE_MIN_RUNS:
        return float("nan")
    baseline_median = baseline["ef"].median()
    if pd.isna(baseline_median) or baseline_median <= 0:
        return float("nan")
    return (recent["ef"].median() / baseline_median - 1) * 100.0


def efficiency_recent_value(easy_ef, today):
    """median EF ของ 3 รันล่าสุด — คืน NaN เมื่อสามรันนั้นไม่ผ่านเกณฑ์ "ตอนนี้"

    ห้ามโชว์ตัวเลขที่ ``efficiency_change_pct`` ตัดสินไปแล้วว่าใช้แทนความสดปัจจุบัน
    ไม่ได้ ไม่งั้นหน้าจอจะขึ้นค่า EF คู่กับป้าย "ข้อมูลไม่พอ" พร้อมกัน
    """
    if pd.isna(efficiency_change_pct(easy_ef, today)):
        return float("nan")
    return easy_ef["ef"].tail(EF_RECENT_RUNS).median()


def efficiency_status(pct):
    """แปลง % การเปลี่ยนแปลงของ EF เป็น (อิโมจิ, คำอธิบาย)"""
    if pd.isna(pct):
        return "⚪", "ข้อมูลไม่พอ"
    if pct >= EF_GAIN_PCT:
        return "🔵", "ดีขึ้นชัด"
    if pct < EF_REST_PCT:
        return "🔴", "ประสิทธิภาพตก"
    if pct < EF_WATCH_PCT:
        return "🟡", "ประสิทธิภาพลด"
    return "🟢", "ปกติ"


def efficiency_display(pct):
    """ข้อความในตาราง — บอกทิศทางเทียบฐานเสมอ ไม่ใช่ตัวเลขลอย ๆ"""
    if pd.isna(pct):
        return "–"
    return f"{pct:+.0f}% จากฐาน 28 วัน"


def personal_record_label(record_type_id, record_label):
    """ชื่อรายการ PR ที่โค้ชอ่านได้ — บอกตรง ๆ เมื่อยังไม่รู้จักชนิดสถิตินี้

    Garmin คืน `prTypeLabelKey` เป็น null ทุกแถว (ยืนยันจาก payload จริง 18 ส.ค. 69)
    ชื่อจึงมาจาก PR_LABELS ที่ตั้งเองใน 03_backfill.py ซึ่งครอบแค่ typeId 1-9, 12-14
    typeId นอกนั้น (เช่น 15-18) ถึงตารางโดยไม่มีชื่อ — ห้ามเดาความหมายให้โค้ช
    """
    if isinstance(record_label, str) and record_label:
        return record_label
    return f"รายการที่ Garmin ไม่ได้ระบุชื่อ (รหัส {record_type_id})"


def personal_record_rows(records):
    """แถวตาราง PR พร้อมหน่วยตามชนิดสถิติ — ชนิดที่ไม่รู้จักแสดงค่าดิบโดยไม่เดาหน่วย"""
    # typeId ที่ค่าเป็น "เวลา (วินาที)" / "ระยะไกล (เมตร→กม.)" / "ไต่สะสม (เมตร)" / "จำนวนก้าว"
    time_ids = {1, 2, 3, 4, 5, 6}
    km_ids = {7, 8}
    meter_ids = {9}
    step_ids = {12, 13, 14}
    rows = []
    for _, record in records.iterrows():
        type_id, value = int(record["record_type_id"]), record["value"]
        if type_id in time_ids:
            shown = fmt_sec(value)
        elif type_id in km_ids:
            shown = f"{value / 1000:.2f} km" if pd.notna(value) else "–"
        elif type_id in meter_ids:
            shown = f"{value:,.0f} m" if pd.notna(value) else "–"
        elif type_id in step_ids:
            shown = f"{value:,.0f} ก้าว" if pd.notna(value) else "–"
        else:
            shown = f"{value:,.0f}" if pd.notna(value) else "–"
        achieved_date = record["achieved_date"]
        rows.append({
            "รายการ": personal_record_label(type_id, record["record_label"]),
            "สถิติ": shown,
            "ทำได้เมื่อ": (str(achieved_date)[:10]
                          if isinstance(achieved_date, str) and achieved_date else "–"),
        })
    return rows


def classify_intensity(avg_hr, lthr):
    """จำแนกความหนักของเซสชันจาก avg HR เทียบ LTHR (โซน Friel)"""
    if pd.isna(avg_hr) or not lthr:
        return None
    ratio = avg_hr / lthr
    if ratio <= EASY_MAX_PCT:
        return INTENSITY_ORDER[0]
    if ratio < GRAY_MAX_PCT:
        return INTENSITY_ORDER[1]
    return INTENSITY_ORDER[2]


def team_status(efficiency_pct, flags, has_workload, wellness_core_count,
                has_any_wellness=None):
    """Classify team readiness without ever turning missing evidence green.

    ตัวตัดสินหลักคือ EF (การตอบสนองของร่างกาย) ไม่ใช่ปริมาณโหลดที่ทำไป — โหลด 7 วัน
    เป็นบริบทเท่านั้นและไม่ดันสถานะเป็นแดงอีกแล้ว

    ขาด EF ไม่บล็อกเขียว: นักกีฬาที่ซ้อม HIIT/indoor เป็นหลักแทบไม่มีรัน easy ให้
    คำนวณ ถ้าเอา EF เป็นเงื่อนไขจะค้าง "ข้อมูลไม่พอ" ถาวรทั้งที่ข้อมูลซ้อมครบ
    """
    flags = list(flags or [])
    if has_any_wellness is None:
        has_any_wellness = wellness_core_count > 0
    if not has_workload and not has_any_wellness:
        return "⚪ ไม่มีข้อมูล"
    if (pd.notna(efficiency_pct) and efficiency_pct < EF_REST_PCT) or len(flags) >= 2:
        return "🔴 ต้องพัก/ลดโหลด"
    if len(flags) == 1:
        return "🟡 เฝ้าระวัง"
    if not has_workload or wellness_core_count < 3:
        return "⚪ ข้อมูลไม่พอ"
    return "🟢 พร้อมซ้อม"


# team_status() คืนสตริงเดียว "อีโมจิ + ข้อความ" เพราะแท็บ "วันนี้" ยังใช้รูปแบบนั้นอยู่
# การ์ดบนแท็บทีมต้องการรูปทรงวาดแทนอีโมจิ (อีโมจิเรนเดอร์ไม่เหมือนกันข้ามเครื่องและ
# หายตอนพิมพ์ขาวดำ) จึงแยกออกเป็น (คีย์, ข้อความ) ที่นี่ที่เดียว แทนการ parse ซ้ำหลายที่
STATUS_SHAPES = {"🔴": "rest", "🟡": "watch", "🟢": "ready",
                 "🔵": "gain", "⚪": "unknown"}


def status_parts(status):
    """แยก "🔴 ต้องพัก/ลดโหลด" เป็น ("rest", "ต้องพัก/ลดโหลด")"""
    text = str(status or "").strip()
    for emoji, key in STATUS_SHAPES.items():
        if text.startswith(emoji):
            return key, text[len(emoji):].strip()
    return "unknown", text


# ลำดับการ์ดบนแท็บทีม — "ข้อมูลไม่พอ" มาก่อน "พร้อมซ้อม" เพราะช่องว่างของหลักฐาน
# ต้องถูกเห็น ไม่ใช่ถูกกลบไว้ท้ายรายการหลังคนที่ไม่มีอะไรต้องทำ
TEAM_URGENCY_ORDER = ("rest", "watch", "unknown", "ready")


def team_urgency_rank(status):
    """ลำดับความเร่งด่วนของสถานะ — คนที่ต้องตัดสินใจก่อนได้เลขน้อยสุด"""
    key, _ = status_parts(status)
    if key in TEAM_URGENCY_ORDER:
        return TEAM_URGENCY_ORDER.index(key)
    return len(TEAM_URGENCY_ORDER)


STATUS_COLORS = {"rest": C_CRIT, "watch": C_WARN, "ready": C_GOOD,
                 "gain": C_BLUE, "unknown": "#8a8d94"}
# ข้อความสีสำหรับตัวหนังสือ — สีจุดสถานะบางตัวจางเกินจะอ่านเป็นตัวอักษรบนพื้นขาว
STATUS_TEXT_COLORS = {"rest": C_CRIT, "watch": "#8a5b00", "ready": "#006300",
                      "gain": "#184f95", "unknown": "#55585f"}


def status_shape_svg(key, size=12):
    """รูปทรงประจำสถานะแทนอีโมจิ — วงกลม/สี่เหลี่ยม/สามเหลี่ยม/วงว่าง

    อีโมจิเรนเดอร์ไม่เหมือนกันข้ามเครื่องและหายตอนพิมพ์ขาวดำ ซึ่งเป็นเหตุผลเดียวกับที่
    dashboard ล็อกธีมสว่างไว้ (ดู .streamlit/config.toml) — รูปทรงวาดอ่านได้ทั้งบนจอ
    บนกระดาษขาวดำ และแยกออกโดยไม่ต้องพึ่งสีสำหรับคนตาบอดสี
    """
    color = STATUS_COLORS.get(key, STATUS_COLORS["unknown"])
    if key == "rest":
        box, body = "0 0 12 11", f'<path d="M6 0 L12 11 L0 11 Z" fill="{color}"/>'
    elif key == "watch":
        box, body = "0 0 11 11", f'<rect width="11" height="11" fill="{color}"/>'
    elif key == "unknown":
        box = "0 0 11 11"
        body = (f'<circle cx="5.5" cy="5.5" r="4.7" fill="none" '
                f'stroke="{color}" stroke-width="1.6"/>')
    else:
        box, body = "0 0 11 11", f'<circle cx="5.5" cy="5.5" r="5.5" fill="{color}"/>'
    return (f'<svg width="{size}" height="{size}" viewBox="{box}" aria-hidden="true"'
            f' style="flex-shrink:0">{body}</svg>')


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


def css_key(name):
    """ชื่อนักกีฬา -> คีย์ที่ปลอดภัยสำหรับใช้เป็นคลาส CSS

    Streamlit ติดคลาส ``st-key-<key>`` ให้ทุก container/widget ที่มี key แต่ชื่อจริง
    มีอักขระที่ใช้ในคลาสไม่ได้ — "P'kao" จะกลายเป็นเซเลกเตอร์พังและ CSS ทั้งบล็อกถูกทิ้ง
    """
    cleaned = "".join(
        character if character.isalnum() or character in "-_" else "-"
        for character in str(name).lower()
    ).strip("-")
    return cleaned or "athlete"


def _num_text(value, digits=0):
    return "–" if value is None or pd.isna(value) else f"{value:.{digits}f}"


def render_team_card(row):
    """การ์ดหนึ่งใบต่อนักกีฬาหนึ่งคน แทนหนึ่งแถวของตารางสรุปเดิม

    อ่านจาก dict เดียวกับที่ team_df ใช้ — ห้ามเปลี่ยนชื่อคีย์ เพราะแท็บ "วันนี้"
    อ่าน team_df ต่อจากที่นี่ (team_row["สถานะ"], ["โซน EF"], ["โหลด 7 วัน"] ฯลฯ)
    """
    esc = html.escape
    key, label = status_parts(row["สถานะ"])
    color = STATUS_COLORS.get(key, STATUS_COLORS["unknown"])
    text_color = STATUS_TEXT_COLORS.get(key, STATUS_TEXT_COLORS["unknown"])

    raw_flags = str(row.get("ธงเฝ้าระวัง") or "").strip()
    flags = [part.strip() for part in raw_flags.split("|")
             if part.strip() and part.strip() != "—"]
    if flags:
        flag_label = f"ธงเฝ้าระวัง {len(flags)} ข้อ"
        chips = "".join(
            f'<span class="team-card__chip" style="border:1px solid {color};'
            f'color:{text_color}">{status_shape_svg(key, 9)}{esc(flag)}</span>'
            for flag in flags
        )
    else:
        flag_label = "ธงเฝ้าระวัง"
        chips = '<div style="font-size:14px;color:#55585f">ไม่มี</div>'

    ef_key, ef_label = status_parts(row.get("โซน EF") or "")
    ef_color = STATUS_TEXT_COLORS.get(ef_key, STATUS_TEXT_COLORS["unknown"])

    hrv_raw = str(row.get("HRV คืนล่าสุด") or "–")
    hrv_val, _, hrv_note = hrv_raw.partition(" · ")
    hrv_color = {"LOW": C_CRIT, "UNBALANCED": "#8a5b00"}.get(hrv_note, "#006300")

    # ค่าว่างของ EF ต้องบอกเหตุผลตรงจุดที่มันว่าง ไม่งั้นโค้ชอ่านว่า sync พังแล้วไปไล่
    # แก้ระบบที่ไม่ได้เสีย — ข้อความนี้โผล่เฉพาะตอนสรุปไม่ได้ ไม่ใช่คำอธิบายที่เห็นตลอด
    ef_value = str(row.get("ประสิทธิภาพการวิ่งเบา (EF)") or "–")
    ef_note = (' <span style="color:#8a8d94">— ต้องมีรัน easy 3 ครั้งภายใน 14 วัน '
               'ไม่ใช่ระบบขัดข้อง</span>') if ef_value.strip() in ("–", "-", "") else ""

    cells = [
        ("ประสิทธิภาพวิ่งเบา", esc(ef_value),
         f'{status_shape_svg(ef_key, 10)}'
         f'<span style="color:{ef_color}">{esc(ef_label)}</span>{ef_note}'),
        # BB อยู่ในชุดเดียวกับอีก 3 ค่าที่ตัดสินว่าเขียวได้ไหม และเป็นเงื่อนไขธง BB<40
        # ด้วย — โชว์วันที่ในบรรทัดความสดแต่ไม่โชว์ค่า ทำให้อ่านเหมือนลืม ไม่เหมือนเลือก
        ("BODY BAT.", _num_text(row.get("Body Battery ตอนนี้/ล่าสุด")), ""),
        ("SLEEP", _num_text(row.get("Sleep")), ""),
        ("RHR", _num_text(row.get("RHR")),
         f'<span style="color:#55585f">{esc(str(row.get("ΔRHR") or "–"))}</span>'),
        ("HRV", esc(hrv_val),
         f'<span style="color:{hrv_color}">{esc(hrv_note)}</span>' if hrv_note else ""),
    ]
    numbers = "".join(
        f'<div><div class="team-card__lbl" style="margin-bottom:2px">{esc(title)}</div>'
        f'<div class="team-card__val">{value}</div>'
        + (f'<div class="team-card__sub">{sub}</div>' if sub else "")
        + "</div>"
        for title, value, sub in cells
    )

    return (
        f'<div class="team-card" style="border-left-color:{color}">'
        f'<div class="team-card__who">'
        f'<div class="team-card__head">{status_shape_svg(key, 13)}'
        f'<span class="team-card__name">{esc(str(row["นักกีฬา"]))}</span></div>'
        f'<div class="team-card__status" style="color:{text_color}">{esc(label)}</div>'
        f'<div class="team-card__fresh">{esc(str(row.get("ความสดรายค่า") or ""))}</div>'
        f'</div>'
        f'<div class="team-card__flags">'
        f'<div class="team-card__lbl">{esc(flag_label)}</div>'
        f'<div class="team-card__chips">{chips}</div>'
        f'<div class="team-card__load">โหลด 7 วัน '
        f'{esc(str(row.get("โหลด 7 วัน") or "–"))} · '
        f'{esc(str(row.get("เซสชัน 7 วัน") or 0))} เซสชัน '
        f'<span style="color:#8a8d94">— บริบท ไม่ได้ตัดสินสถานะ</span></div>'
        f'</div>'
        f'<div class="team-card__nums">{numbers}</div>'
        f'</div>'
    )


# --- แท็บ "วันนี้": แผงคำตัดสิน ไทล์ค่าเดี่ยว แถบโหลด และแถวเซสชัน ---
# แท็บนี้เคยวางตัวเลข 17 ช่องขนาดเท่ากันหมด ตัวตัดสิน (EF) จึงจมอยู่กับค่าที่ประกอบมัน
# แผงใหม่เรียงตามลำดับการตัดสินใจ: คำตัดสิน → ธงที่ทำให้ตัดสินแบบนั้น → ค่าที่ประกอบ
# → บริบทโหลด → เซสชันจริง

# เกณฑ์ธงของ wellness อยู่ที่เดียว เพราะแท็บทีมใช้ตัดสินสถานะ ส่วนแท็บวันนี้ใช้
# ตีกรอบไทล์ให้ตรงกัน — เขียนคนละที่เมื่อไหร่ หน้าจอสองแท็บจะขัดกันเองโดยไม่มีอะไรฟ้อง
BB_LOW = 40           # Body Battery high ของวันที่จบแล้ว ต่ำกว่านี้ = ธง
SLEEP_LOW = 60
RHR_RISE = 5.0        # RHR สูงกว่าฐานตั้งแต่นี้ = ธง
HRV_ALERT = {"LOW": "rest", "UNBALANCED": "watch"}
READINESS_ALERT = ("POOR", "LOW")

# คีย์ของ selectbox นักกีฬา — ปุ่มบนการ์ดทีมเขียนค่าลงคีย์นี้เพื่อสลับคนที่กำลังดู
ATHLETE_STATE_KEY = "selected_athlete"

EF_SCALE_MIN = -12.0  # กว้างกว่าเกณฑ์ทุกตัวเล็กน้อย เพื่อให้เห็นว่าค่าอยู่ใกล้ขอบแค่ไหน
EF_SCALE_MAX = 12.0

# ความหนักเป็นค่ามีลำดับ (เบา→กลาง→หนัก) จึงไล่น้ำเงินเฉดเดียว — เขียว/เหลือง/แดง
# จองไว้ให้ "สถานะ" เท่านั้น ถ้ายืมมาใช้ที่นี่ด้วย สีเดียวกันจะแปลสองความหมายในหน้าเดียว
INTENSITY_CHIP_COLORS = {
    INTENSITY_ORDER[0]: ("#cde2fb", "#104281"),
    INTENSITY_ORDER[1]: (C_BLUE, "#ffffff"),
    INTENSITY_ORDER[2]: ("#104281", "#ffffff"),
}


def baseline_median(df, column, before_date, days=14, min_points=5):
    """median ของ ``days`` วันก่อนหน้า ``before_date`` — คืน NaN เมื่อจุดไม่ถึง ``min_points``

    ตัดวันของค่านั้นเองออกเสมอ ไม่งั้นค่าจะดึงฐานเข้าหาตัวเองจนส่วนต่างหด
    และฐานจากไม่กี่วันต้องคืน NaN ไม่ใช่ตัวเลข เพราะบนหน้าจอมันจะดูน่าเชื่อถือเท่ากัน
    """
    if df is None or getattr(df, "empty", True):
        return float("nan")
    if column not in df.columns or "calendar_date" not in df.columns:
        return float("nan")
    anchor = pd.Timestamp(before_date).normalize()
    parsed = pd.to_datetime(df["calendar_date"], errors="coerce")
    window = df.loc[
        parsed.notna() & (parsed < anchor) & (parsed >= anchor - pd.Timedelta(days=days)),
        column,
    ]
    values = pd.to_numeric(window, errors="coerce").dropna()
    if len(values) < min_points:
        return float("nan")
    return float(values.median())


def tile_note(value, baseline, digits=0):
    """บรรทัดเทียบฐานใต้ตัวเลข — บอกส่วนต่างเฉย ๆ ไม่ตัดสิน

    เกณฑ์ว่าค่าไหน "แย่" อยู่ที่ธงเฝ้าระวังของแท็บทีมที่เดียว บรรทัดนี้แค่บอกว่า
    วันนี้ห่างจากปกติของคนนี้เท่าไหร่ ซึ่งเป็นคำถามที่ตัวเลขลอย ๆ ตอบไม่ได้
    """
    if value is None or pd.isna(value):
        return ""
    if baseline is None or pd.isna(baseline):
        return "ยังไม่มีฐาน 14 วัน"
    return f"เทียบฐาน 14 วัน {float(value) - float(baseline):+.{digits}f}"


def sparkline_svg(values, width=104, height=22, color=C_BLUE):
    """เส้นแนวโน้มเล็กใต้ตัวเลข — คืน "" เมื่อจุดใช้ได้น้อยกว่า 3 จุด

    วันที่นาฬิกาไม่ส่งค่าถูกข้าม ไม่ใช่ลากลงศูนย์ ซึ่งจะวาดหลุมที่ไม่มีอยู่จริง
    """
    series = pd.to_numeric(pd.Series(list(values), dtype="object"), errors="coerce")
    points = [float(value) for value in series.dropna()]
    if len(points) < 3:
        return ""
    low, high = min(points), max(points)
    span = high - low
    step = width / (len(points) - 1)
    pad = 2.0
    inner = height - pad * 2
    coords = " ".join(
        f"{index * step:.1f},{pad + inner * (1 - (0.5 if span == 0 else (value - low) / span)):.1f}"
        for index, value in enumerate(points)
    )
    return (f'<svg class="today-spark" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" aria-hidden="true">'
            f'<polyline fill="none" stroke="{color}" stroke-width="1.5" '
            f'stroke-linejoin="round" points="{coords}"/></svg>')


def ef_scale_position(pct):
    """ตำแหน่ง 0..1 ของหมุดบนแถบเกณฑ์ EF — คืน None เมื่อไม่มีค่า

    ค่าว่างต้องไม่มีตำแหน่ง: หมุดที่วางไว้กลางแถบอ่านได้ว่า "ปกติ" ซึ่งตรงข้ามกับความจริง
    """
    if pct is None or pd.isna(pct):
        return None
    span = EF_SCALE_MAX - EF_SCALE_MIN
    return min(1.0, max(0.0, (float(pct) - EF_SCALE_MIN) / span))


def render_ef_scale(pct):
    """แถบเกณฑ์ EF พร้อมหมุดค่าปัจจุบัน — เห็นทันทีว่าอยู่ห่างเส้นตัดแค่ไหน"""
    span = EF_SCALE_MAX - EF_SCALE_MIN
    widths = [
        ((EF_REST_PCT - EF_SCALE_MIN) / span, C_CRIT),
        ((EF_WATCH_PCT - EF_REST_PCT) / span, C_WARN),
        ((EF_GAIN_PCT - EF_WATCH_PCT) / span, C_GOOD),
        ((EF_SCALE_MAX - EF_GAIN_PCT) / span, C_BLUE),
    ]
    bands = "".join(
        f'<div style="width:{ratio * 100:.1f}%;background:{color}"></div>'
        for ratio, color in widths
    )
    position = ef_scale_position(pct)
    marker = ""
    if position is not None:
        marker = (
            f'<div class="today-ef__pin" style="left:{position * 100:.1f}%">'
            f'<div class="today-ef__pin-val">{float(pct):+.1f}%</div>'
            f'<div class="today-ef__pin-tip"></div></div>'
        )
    ticks = "".join(
        f'<div class="today-ef__tick" style="left:{(value - EF_SCALE_MIN) / span * 100:.1f}%">'
        f'{value:+.0f}%</div>'
        for value in (EF_REST_PCT, EF_WATCH_PCT, EF_GAIN_PCT)
    )
    return (f'<div class="today-ef__scale">{marker}'
            f'<div class="today-ef__bands">{bands}</div>'
            f'<div class="today-ef__ticks">{ticks}</div></div>')


def render_today_tile(label, value, unit="", note="", spark="", alert=None):
    """ไทล์ค่าเดียว: ชื่อ ค่า หน่วย/ที่มา ส่วนต่างจากฐาน และเส้นแนวโน้ม

    ไทล์ที่ติดธงถูกตีกรอบสีสถานะ *และ* มีรูปทรงกับข้อความกำกับ — สีอย่างเดียวอ่านไม่ได้
    บนกระดาษขาวดำ ซึ่งเป็นเหตุผลเดียวกับที่โปรเจกต์ล็อกธีมสว่างไว้
    """
    esc = html.escape
    border = STATUS_COLORS.get(alert, "#e4e1da") if alert else "#e4e1da"
    note_color = STATUS_TEXT_COLORS.get(alert, "#55585f") if alert else "#55585f"
    mark = status_shape_svg(alert, 9) if alert else ""
    note_html = (
        f'<div class="today-tile__note" style="color:{note_color}">{mark}{esc(note)}</div>'
        if note else ""
    )
    unit_html = f'<span class="today-tile__unit">{esc(unit)}</span>' if unit else ""
    return (f'<div class="today-tile" style="border-color:{border}">'
            f'<div class="today-lbl">{esc(label)}</div>'
            f'<div class="today-tile__val">{esc(str(value))}{unit_html}</div>'
            f'{note_html}{spark}</div>')


def render_today_verdict(row):
    """แผงคำตัดสินของนักกีฬาที่เลือก — อ่านจบก่อนตัวเลขใด ๆ

    เดิมเป็นกล่อง st.warning/success ที่เลือกชนิดด้วย ``status_text.startswith("🔴")``
    ซึ่งผูกกับอีโมจิในสตริงโดยตรง ถ้าแท็บทีมถอดอีโมจิออกเมื่อไหร่กล่องจะเงียบไปทั้งอัน
    ที่นี่จึงอ่านสถานะผ่าน ``status_parts()`` ที่เดียวเหมือนการ์ดของแท็บทีม
    """
    esc = html.escape
    key, label = status_parts(row["สถานะ"])
    color = STATUS_COLORS.get(key, STATUS_COLORS["unknown"])
    text_color = STATUS_TEXT_COLORS.get(key, STATUS_TEXT_COLORS["unknown"])

    raw_flags = str(row.get("ธงเฝ้าระวัง") or "").strip()
    flags = [part.strip() for part in raw_flags.split("|")
             if part.strip() and part.strip() != "—"]
    if flags:
        chips = "".join(
            f'<span class="today-chip" style="border:1px solid {color};color:{text_color}">'
            f'{status_shape_svg(key, 9)}{esc(flag)}</span>'
            for flag in flags
        )
        flag_block = f'<div class="today-chips">{chips}</div>'
    else:
        flag_block = '<div class="today-none">ไม่มีธงเฝ้าระวัง</div>'

    # "แดง" คือคำเตือนเรื่องตัวนักกีฬา ไม่ใช่ระบบพัง — ประโยคนี้เคยอยู่ในกล่อง st.warning
    # และต้องอยู่ต่อ เพราะโค้ชที่อ่านผิดจะไปไล่แก้ sync ที่ไม่ได้เสีย
    note = ('<div class="today-verdict__note">เป็นคำเตือนจากข้อมูลซ้อม/การฟื้นตัว '
            'ไม่ใช่ข้อผิดพลาดของระบบ</div>') if key == "rest" else ""

    figures = "".join(
        f'<div><div class="today-lbl">{esc(title)}</div>'
        f'<div class="today-verdict__fig">{esc(str(value))}</div></div>'
        for title, value in (
            ("ประสิทธิภาพวิ่งเบา", row.get("ประสิทธิภาพการวิ่งเบา (EF)") or "–"),
            ("โหลด 7 วัน", row.get("โหลด 7 วัน") or "–"),
            ("เซสชัน 7 วัน", row.get("เซสชัน 7 วัน") or 0),
        )
    )
    return (
        f'<div class="today-verdict" style="border-top-color:{color}">'
        f'<div class="today-verdict__main">'
        f'<div class="today-verdict__head">{status_shape_svg(key, 17)}'
        f'<span class="today-verdict__title">{esc(str(row["นักกีฬา"]))} '
        f'<span style="color:{text_color}">{esc(label)}</span></span></div>'
        f'{flag_block}{note}</div>'
        f'<div class="today-verdict__figs">{figures}</div>'
        f'</div>'
    )


def session_intensity_chip(label):
    """ชิปความหนักของเซสชัน — ค่าว่างไม่วาดอะไรเลย

    ไม่มี HR = ไม่รู้ความหนัก การเดาว่า "เบา" ทำให้สัดส่วน 80-20 ที่โค้ชอ่านผิดไปด้วย
    """
    if not label or label not in INTENSITY_CHIP_COLORS:
        return ""
    background, text = INTENSITY_CHIP_COLORS[label]
    return (f'<span class="today-chip today-chip--zone" '
            f'style="background:{background};color:{text}">{html.escape(str(label))}</span>')


def render_session_row(when, title, distance_km, duration_sec, pace, avg_hr, intensity):
    """หนึ่งเซสชันหนึ่งแถว แทนการ์ดซ้อนการ์ดที่มี st.metric ห้าช่องต่อกิจกรรม"""
    esc = html.escape
    distance = ("–" if distance_km is None or pd.isna(distance_km)
                else f"{float(distance_km):.2f} กม.")
    heart = "–" if avg_hr is None or pd.isna(avg_hr) else f"{float(avg_hr):.0f}"
    cells = "".join(
        f'<div class="today-sess__num">{esc(text)}</div>'
        for text in (distance, fmt_sec(duration_sec), fmt_pace(pace), heart)
    )
    return (f'<div class="today-sess__row">'
            f'<div class="today-sess__when">{esc(str(when))}</div>'
            f'<div class="today-sess__name">{esc(str(title))}</div>'
            f'{cells}'
            f'<div class="today-sess__zone">{session_intensity_chip(intensity)}</div>'
            f'</div>')


def render_load_strip(days, digits=1):
    """แถบโหลดรายวัน 7 ช่อง — วันพักเป็นขีด ไม่ใช่แท่งสูงศูนย์ที่อ่านเหมือนมีข้อมูล"""
    esc = html.escape
    values = [value for _, value in days
              if value is not None and not pd.isna(value) and float(value) > 0]
    peak = max(values) if values else 0.0
    columns = []
    for label, value in days:
        has_value = value is not None and not pd.isna(value) and float(value) > 0
        height = (float(value) / peak * 100) if has_value and peak > 0 else 0
        bar = (f'<div class="today-strip__bar" style="height:{height:.0f}%"></div>'
               if has_value else '<div class="today-strip__rest"></div>')
        text = f"{float(value):.{digits}f}" if has_value else "–"
        columns.append(
            f'<div class="today-strip__col">'
            f'<div class="today-strip__plot">{bar}</div>'
            f'<div class="today-strip__val">{esc(text)}</div>'
            f'<div class="today-strip__day">{esc(str(label))}</div></div>'
        )
    return f'<div class="today-strip">{"".join(columns)}</div>'


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
.today-ef__scale { position: relative; padding-top: 24px; margin-top: 16px; }
.today-ef__bands { display: flex; height: 11px; border-radius: 2px; overflow: hidden; gap: 1px; }
.today-ef__ticks { position: relative; height: 15px; margin-top: 4px; }
.today-ef__tick { position: absolute; transform: translateX(-50%); font-size: 11px;
  color: #8a8d94; font-variant-numeric: tabular-nums; }
.today-ef__pin { position: absolute; top: 0; transform: translateX(-50%);
  display: flex; flex-direction: column; align-items: center; }
.today-ef__pin-val { font-size: 13px; font-weight: 600; font-variant-numeric: tabular-nums; }
.today-ef__pin-tip { width: 0; height: 0; border-left: 4px solid transparent;
  border-right: 4px solid transparent; border-top: 5px solid #14161a; margin-top: 2px; }
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
/* แผงต้องไม่ถูกหั่นกลางใบตอนพิมพ์ A4 — ครึ่งใบอ่านไม่ได้ความ */
@media print {
  .today-verdict, .today-tile, .today-panel { break-inside: avoid; page-break-inside: avoid; }
}
</style>
"""


def compute_load_windows(daily, end_date, history_start=None):
    """โหลดสะสมรายวันจากตาราง (date, value): acute = ผลรวม 7 วัน, chronic = 28 วัน / 4

    คืนค่าดิบทั้งสองหน้าต่างโดยไม่หารเป็นอัตราส่วน — เดิมฟังก์ชันนี้คืนคอลัมน์ ``acwr``
    ด้วย แต่ถูกถอดออก 25 ส.ค. 69 (ดูหมายเหตุที่ค่าคงที่ EF_* ด้านบน)

    ``history_start`` is the first calendar day for which absence of a workload
    row is a known rest day.  Without it, a long run-free period disappears from
    the index and the training tab can incorrectly claim that 28-day history is
    unavailable even though the athlete has older records.
    """
    if daily.empty:
        return pd.DataFrame(columns=["date", "acute", "chronic"])
    first_day = pd.Timestamp(history_start) if history_start is not None else daily["date"].min()
    idx = pd.date_range(first_day, pd.Timestamp(end_date), freq="D")
    s = daily.set_index("date")["value"].reindex(idx, fill_value=0.0)
    acute = s.rolling(7, min_periods=7).sum()
    chronic = s.rolling(28, min_periods=28).sum() / 4
    return pd.DataFrame({"date": idx, "acute": acute.values, "chronic": chronic.values})


def aggregate_pace_min_per_km(activity_rows):
    """Aggregate pace from paired, positive duration and distance observations."""
    if (activity_rows is None or activity_rows.empty
            or not {"distance_m", "duration_sec"}.issubset(activity_rows.columns)):
        return float("nan")
    distance = pd.to_numeric(activity_rows["distance_m"], errors="coerce")
    duration = pd.to_numeric(activity_rows["duration_sec"], errors="coerce")
    valid = (
        distance.notna() & duration.notna()
        & distance.gt(0) & duration.gt(0)
        & distance.map(math.isfinite) & duration.map(math.isfinite)
    )
    if not valid.any():
        return float("nan")
    total_km = distance.loc[valid].sum() / 1000
    return (duration.loc[valid].sum() / 60) / total_km if total_km > 0 else float("nan")


def usable_hr_zone_rows(activity_rows, zone_columns):
    """Keep activities with at least one positive HR-zone second."""
    if (activity_rows is None or activity_rows.empty
            or not set(zone_columns).issubset(activity_rows.columns)):
        return activity_rows.iloc[0:0] if activity_rows is not None else pd.DataFrame()
    zones = activity_rows[list(zone_columns)].apply(pd.to_numeric, errors="coerce")
    return activity_rows.loc[zones.gt(0).any(axis=1)].copy()


def analyze_distance_halves(splits):
    """Return pace/HR for equal-distance halves, fractionally splitting a lap.

    Garmin laps can be very uneven (including a short final lap), so dividing by
    lap count does not represent the first and second half of the route.  A lap
    crossing the distance midpoint contributes proportional duration to each
    half.  HR denominators include only portions whose HR is actually present.
    """
    empty = (float("nan"),) * 4
    if (splits is None or splits.empty
            or not {"distance_m", "duration_sec"}.issubset(splits.columns)):
        return empty
    distance = pd.to_numeric(splits["distance_m"], errors="coerce")
    duration = pd.to_numeric(splits["duration_sec"], errors="coerce")
    hr = (pd.to_numeric(splits["avg_hr"], errors="coerce")
          if "avg_hr" in splits.columns else pd.Series(float("nan"), index=splits.index))
    valid = (
        distance.notna() & duration.notna()
        & distance.gt(0) & duration.gt(0)
        & distance.map(math.isfinite) & duration.map(math.isfinite)
    )
    if not valid.any():
        return empty

    total_distance = float(distance.loc[valid].sum())
    midpoint = total_distance / 2
    half_distance = [0.0, 0.0]
    half_duration = [0.0, 0.0]
    hr_weighted = [0.0, 0.0]
    hr_duration = [0.0, 0.0]
    traversed = 0.0

    for idx in splits.index[valid]:
        lap_distance = float(distance.loc[idx])
        lap_duration = float(duration.loc[idx])
        first_distance = max(0.0, min(lap_distance, midpoint - traversed))
        portions = (first_distance, lap_distance - first_distance)
        for half, portion_distance in enumerate(portions):
            if portion_distance <= 0:
                continue
            portion_duration = lap_duration * portion_distance / lap_distance
            half_distance[half] += portion_distance
            half_duration[half] += portion_duration
            lap_hr = float(hr.loc[idx]) if pd.notna(hr.loc[idx]) else float("nan")
            if math.isfinite(lap_hr) and lap_hr > 0:
                hr_weighted[half] += lap_hr * portion_duration
                hr_duration[half] += portion_duration
        traversed += lap_distance

    paces = [
        (half_duration[i] / 60) / (half_distance[i] / 1000)
        if half_distance[i] > 0 else float("nan")
        for i in range(2)
    ]
    hrs = [
        hr_weighted[i] / hr_duration[i] if hr_duration[i] > 0 else float("nan")
        for i in range(2)
    ]
    return paces[0], paces[1], hrs[0], hrs[1]


# แกนเพซถูกคุมด้วย "จำนวน tick" ไม่ใช่ความละเอียดของ step — lap ที่ยืนนิ่ง 17 เมตร/792 วิ
# ให้เพซ 777.81 นาที/กม. ซึ่งด้วยเกณฑ์เดิม (step 1 นาที) แปลว่าแกนเดียวมี 774 ticks:
# หัวข้อและตัวเลขขึ้นครบตั้งแต่ 0.35 วิ แต่กราฟใบนั้นเสร็จที่ 10.86 วิ (cold 23.54 วิ)
# วัดจากเบราว์เซอร์จริง 26 ส.ค. 69 — ตัวเลขดิบของทุก split ยังอยู่ครบในตาราง Splits
PACE_TICK_MAX = 12
PACE_TICK_STEPS_MIN = (2, 5, 10, 15, 30, 60)


def _pace_ticks_at(pmin, pmax, step):
    start = math.floor(pmin / step) * step
    end = math.ceil(pmax / step) * step
    return [round(start + i * step, 4) for i in range(int(round((end - start) / step)) + 1)]


def pace_axis_ticks(pace_series):
    """สร้าง tick แกนเพซเป็น M:SS ทุก 15/30/60 วิ ตามช่วงข้อมูล แต่ไม่เกิน PACE_TICK_MAX จุด"""
    pmin, pmax = float(pace_series.min()), float(pace_series.max())
    rng = max(pmax - pmin, 0.01)
    fine = 0.25 if rng <= 2 else (0.5 if rng <= 4 else 1.0)
    for step in (fine, *PACE_TICK_STEPS_MIN):
        vals = _pace_ticks_at(pmin, pmax, step)
        if len(vals) <= PACE_TICK_MAX:
            break
    else:
        # กว้างเกินกว่าที่ step 60 นาที/กม. เอาอยู่ — ปัดขึ้นเป็นชั่วโมงเต็มให้ป้ายยังกลม
        # หารด้วย PACE_TICK_MAX - 2 เพราะการปัด start ลงและ end ขึ้นเพิ่มจุดได้อีกไม่เกินสอง
        vals = _pace_ticks_at(pmin, pmax, math.ceil(rng / (PACE_TICK_MAX - 2) / 60) * 60)
    return vals, [fmt_pace(v) for v in vals]


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
    if athlete_has_load(athlete_id):
        return load_daily_load(athlete_id, start_date, end_date), "training_load", "TL"
    df = load_daily_run_km(athlete_id, start_date, end_date).rename(columns={"km": "value"})
    return df, "ระยะวิ่ง", "km"


@st.cache_data(ttl=CACHE_TTL_SEC)
def load_first_activity_date(athlete_id):
    """วันแรกที่มีกิจกรรม (ทุกประเภท) — ใช้ตัดสินความพอของประวัติเมื่อโหลดอิง training_load"""
    conn = connect_db()
    row = conn.execute(
        "SELECT MIN(SUBSTR(start_time_local, 1, 10)) FROM fact_activity "
        "WHERE athlete_id = ? AND deleted_at IS NULL",
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
def load_observed_max_hr(athlete_id):
    """HR สูงสุดที่เคยบันทึก — ใช้ประมาณ LTHR เมื่อยังไม่มีผลเทส"""
    conn = connect_db()
    row = conn.execute("SELECT MAX(max_hr) FROM fact_activity "
                       "WHERE athlete_id = ? AND deleted_at IS NULL", (athlete_id,)).fetchone()
    conn.close()
    return row[0] if row and row[0] else None


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


def prepare_session_candidates(activity_df):
    """กิจกรรมทุกเซสชันที่ Garmin บันทึก สำหรับหน้าเจาะลึก

    ห้ามกรองด้วยระยะขั้นต่ำ: warm-up/cool-down และ interval ของ Tong มีทั้งเซสชัน
    สั้นกว่า 500 ม. แต่มี splits ที่ถูกต้องครบถ้วน ส่วนกิจกรรมระยะ 0 ก็ยังมีตัวเลข
    เวลา/HR/Training Load ที่ควรดูได้ แม้ไม่มี splits ก็ตาม
    """
    return activity_df.sort_values("start_time_local", ascending=False)


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


def get_lthr(slug, athlete_id):
    """คืน (LTHR, ที่มา) — จากผลเทสก่อน ถ้าไม่มีประมาณจาก HR สูงสุดที่พบ"""
    if slug in LTHR_BY_SLUG:
        return LTHR_BY_SLUG[slug], LTHR_SOURCE_BY_SLUG.get(slug, "จากผลเทสล่าสุด")
    observed = load_observed_max_hr(athlete_id)
    if observed:
        return round(observed * 0.89), f"ประมาณ 89% ของ HR สูงสุดที่พบ ({observed:.0f}) — ควรเทสจริง"
    return None, "ไม่มีข้อมูล HR"


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
            first = load_first_activity_date(aid) if metric == "training_load" else load_first_run_date(aid)
            days_of_history = (today - first).days + 1 if first else 0
            if days_of_history >= 28 and win28["value"].sum() > 0:
                chronic_wk = win28["value"].sum() / 4

        # ประสิทธิภาพการวิ่งเบา — ต้องมองย้อนพอให้ได้ฐาน 28 วันก่อนรัน easy ล่าสุด
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
            aid, (today - datetime.timedelta(days=30)).isoformat(), today.isoformat()
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

        # ธงเฝ้าระวัง — เก็บคู่กับ "ค่าไหนเป็นคนจุดธง" เพราะแท็บวันนี้ต้องตีกรอบไทล์ให้ตรงกัน
        # ถ้าแท็บนั้นคำนวณเกณฑ์เองซ้ำ สองหน้าจะขัดกันเงียบ ๆ ทันทีที่เกณฑ์ฝั่งใดฝั่งหนึ่งขยับ
        flags = []
        flag_fields = []
        if pd.notna(ef_pct) and ef_pct < EF_REST_PCT:
            flags.append(f"ประสิทธิภาพตก {ef_pct:.0f}% จากฐาน")
            flag_fields.append("ef")
        elif pd.notna(ef_pct) and ef_pct < EF_WATCH_PCT:
            flags.append(f"ประสิทธิภาพลด {ef_pct:.0f}% จากฐาน")
            flag_fields.append("ef")
        if (pd.notna(bb) and bb < BB_LOW and bb_completed_snap
                and field_age_days(bb_completed_snap, today) is not None
                and 0 <= field_age_days(bb_completed_snap, today) <= 1):
            flags.append(f"Body Battery ต่ำ ({bb:.0f})")
            flag_fields.append("bb")
        if pd.notna(sleep) and sleep < SLEEP_LOW and field_age_days(sleep_snap, today) <= 1:
            flags.append(f"นอนแย่ ({sleep:.0f})")
            flag_fields.append("sleep")
        if (pd.notna(rhr_delta) and rhr_delta >= RHR_RISE
                and field_age_days(rhr_snap, today) <= 1):
            flags.append(f"RHR สูงกว่าฐาน +{rhr_delta:.0f}")
            flag_fields.append("rhr")
        if (hrv_stat in HRV_ALERT
                and field_age_days(hrv_snap, today) <= 1):
            flags.append(f"HRV {hrv_stat}")
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

        # ห้ามเขียวเมื่อไม่มีหลักฐานการซ้อม หรือ wellness สดมีไม่พอให้ประเมิน
        status = team_status(
            ef_pct, flags, not daily.empty, fresh_core_count,
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
        team_rows.append({
            "นักกีฬา": name,
            "สถานะ": status,
            # อยู่ต้นตาราง (ไม่ใช่ท้ายสุด) เพราะตารางนี้มี 13 คอลัมน์ กว้างเกินจอปกติ —
            # วางไว้ท้ายก่อนหน้านี้ทำให้มองข้ามว่า "ไม่ขึ้น" ทั้งที่จริงมีข้อมูล แค่ต้องเลื่อนดู
            "สถานะซ้อม (Garmin)": _ts_base.title() if _ts_base else "–",
            "ประสิทธิภาพการวิ่งเบา (EF)": efficiency_display(ef_pct),
            "โซน EF": f"{emoji} {ef_txt}",
            "โหลด 7 วัน": load_trend_display(acute, chronic_wk, metric, unit),
            "เซสชัน 7 วัน": sessions_7d,
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
            "EF จากฐาน (%)": ef_pct,
        })

    team_df = pd.DataFrame(team_rows)
    TEAM_INTERNAL_COLUMNS = ["ธงเฝ้าระวังรายค่า", "EF จากฐาน (%)"]


# =====================================================================
# TAB 2: TEAM OVERVIEW
# =====================================================================
# แท็บที่ไม่ได้เปิดอยู่ไม่ต้องสร้างกราฟ — plotly คือตัวกินเวลาหลักของหนึ่งรอบรัน
if tab_team.open:
    with tab_team:
        st.header("สถานะทีมวันนี้")
        st.caption(f"ข้อมูล ณ {today.isoformat()} — ตัวตัดสินคือ **ประสิทธิภาพการวิ่งเบา (EF)** "
                   "= ความเร็ว ÷ HR ในรัน easy เทียบฐาน 28 วันของตัวเอง · "
                   "โหลด 7 วันเป็นบริบทว่าทำไปเท่าไหร่ ไม่ใช่คำตัดสิน")


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
                team_df.drop(columns=TEAM_INTERNAL_COLUMNS),
                hide_index=True,
                column_config={
                    "นักกีฬา": st.column_config.TextColumn("นักกีฬา", pinned=True),
                    "ประสิทธิภาพการวิ่งเบา (EF)": st.column_config.TextColumn(
                        "ประสิทธิภาพการวิ่งเบา (EF)"),
                    "Body Battery ตอนนี้/ล่าสุด": st.column_config.NumberColumn(
                        "Body Battery ตอนนี้/ล่าสุด", format="%.0f"),
                    "Sleep": st.column_config.NumberColumn("Sleep", format="%.0f"),
                    "RHR": st.column_config.NumberColumn("RHR", format="%.0f"),
                    "Readiness": st.column_config.NumberColumn("Readiness", format="%.0f"),
                    "สถานะซ้อม (Garmin)": st.column_config.TextColumn(
                        "สถานะซ้อม (Garmin)",
                        help="สถานะที่ Garmin คำนวณเองและขึ้นกับรุ่นนาฬิกา"),
                },
            )

        with st.expander("เกณฑ์ที่ใช้ประเมิน", icon=":material/info:"):
            st.markdown(r"""
    **สถานะ:** 🔴 ต้องพัก = EF ตกเกิน 7% จากฐาน หรือมีธงอย่างน้อย 2 ข้อ ·
    🟡 เฝ้าระวัง = มีธง 1 ข้อ ·
    🟢 พร้อมซ้อม = ไม่มีธง พร้อมมีข้อมูลซ้อมและ wellness สดอย่างน้อย 3/4 ค่า ·
    ⚪ ข้อมูลไม่พอ = ยังไม่มีข้อมูลซ้อม หรือ wellness สดน้อยกว่า 3/4 ค่า ·
    ⚪ ไม่มีข้อมูล = ยังไม่มีทั้ง workload และ wellness

    **ธงเฝ้าระวัง:** EF ลดเกิน 3% จากฐาน · Body Battery<40 · Sleep<60 ·
    RHR สูงกว่าฐาน≥+5 · HRV LOW/UNBALANCED ·
    Training Readiness LOW/POOR · Garmin status Strained/Overreaching/Unproductive

    **Body Battery ตอนนี้:** แสดงเป็นบริบทแต่ไม่ใช้เป็นธงระหว่างวัน; ธง BB<40 ใช้กับ
    Body Battery high ของวันที่จบแล้ว เพื่อลดการเตือนจากการลดลงตามปกติระหว่างวัน

    **ประสิทธิภาพการวิ่งเบา (EF)** = ความเร็ว (ม./นาที) ÷ HR เฉลี่ย นับเฉพาะรัน easy
    (HR ≤ 89% LTHR, ระยะ ≥ 3 กม.) เทียบ median ของ 3 รันล่าสุดกับ median ฐาน 28 วัน
    ของตัวเอง เกณฑ์ −3% / −7% มาจาก SD ของข้อมูลจริงในระบบ (4.4% และ 3.5%)
    จะสรุปได้ต้องมีรัน easy 3 ครั้งภายใน 14 วัน และมีฐานอย่างน้อย 5 ครั้งใน 28 วันก่อนหน้า
    ค่าว่างแปลว่ารัน easy ยังไม่พอตามเกณฑ์นี้ ไม่ใช่ระบบขัดข้อง และไม่ใช่สถานะถาวร

    _โหลด 7 วันเป็นบริบทว่าทำไปเท่าไหร่ ไม่ดันสถานะเป็นแดง — ใช้ Garmin training\_load
    รวม cross-training ถ้านาฬิกาให้ ไม่เช่นนั้นใช้ระยะวิ่ง เดิมช่องนี้เป็น ACWR ซึ่งถอดออก
    25 ส.ค. 69 หลังหลักฐานพบว่าอัตราส่วนนี้ทำนายการบาดเจ็บไม่ได้
    (Br J Sports Med 2025;59:1203-1210 · IJSPP 2020;15(6):907)_
    """)


    # =====================================================================
    # TAB 1: TODAY — เปิดมาเห็นข้อมูลของวันนี้ทันที
    # =====================================================================
# แท็บที่ไม่ได้เปิดอยู่ไม่ต้องสร้างกราฟ — plotly คือตัวกินเวลาหลักของหนึ่งรอบรัน
if tab_today.open:
    with tab_today:
        st.header(f"วันนี้ของ {selected_name}", anchor=f"today-{selected_anchor}")
        st.caption(
            f"{today.strftime('%d/%m/%Y')} · ตัวตัดสินคือประสิทธิภาพการวิ่งเบา (EF) "
            "โหลด 7 วันเป็นบริบท · ค่าที่ยังไม่มาของวันนี้แสดงค่าล่าสุดพร้อมวันที่กำกับ"
        )

        selected_team = team_df[team_df["นักกีฬา"] == selected_name]
        team_row = selected_team.iloc[0] if not selected_team.empty else None
        # ค่าไหนเป็นคนจุดธง มาจากแท็บทีมโดยตรง ไม่ได้คำนวณเกณฑ์ซ้ำที่นี่
        flagged_fields = set(team_row["ธงเฝ้าระวังรายค่า"]) if team_row is not None else set()

        recent_wellness = load_wellness_data(
            athlete_id, (today - datetime.timedelta(days=30)).isoformat(), today.isoformat()
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

        # ---- คำตัดสิน: อ่านจบก่อนตัวเลขใด ๆ ----
        # สถานะโหลดต้องเตือนแม้ wellness วันนี้ยังไม่มา จึงวาดก่อนอ่านค่า wellness ทั้งหมด
        # และไม่ผูกอยู่กับเงื่อนไขใด ๆ ของ wellness
        if team_row is not None:
            st.markdown(render_today_verdict(team_row), unsafe_allow_html=True)

        # ---- ค่าที่ประกอบคำตัดสิน ----
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
                ("ความพร้อมซ้อม", ready_snap, "training_readiness", "", ready_note,
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

        # ---- ตัวตัดสินเต็ม ๆ กับบริบทโหลดข้างกัน ----
        if team_row is not None:
            ef_zone_key, ef_zone_label = status_parts(team_row["โซน EF"])
            ef_pct_value = team_row["EF จากฐาน (%)"]
            ef_color = STATUS_TEXT_COLORS.get(ef_zone_key, STATUS_TEXT_COLORS["unknown"])

            left, right = st.columns([1.05, 1.35], gap="large")
            with left:
                # ค่าว่างต้องบอกเหตุผลตรงจุดที่มันว่าง ไม่งั้นโค้ชอ่านว่า sync พังแล้วไปไล่แก้ระบบ
                ef_body = (
                    f'<div style="display:flex;align-items:baseline;gap:10px">'
                    f'<div class="today-ef__val" style="color:{ef_color}">'
                    f'{ef_pct_value:+.1f}%</div>'
                    f'<div style="font-size:13px;color:#55585f">จากฐาน 28 วัน</div></div>'
                    f'<div style="font-size:12px;color:#55585f;margin-top:5px">'
                    f'{status_shape_svg(ef_zone_key, 9)} {html.escape(ef_zone_label)}</div>'
                    + render_ef_scale(ef_pct_value)
                    if pd.notna(ef_pct_value) else
                    '<div class="today-ef__val" style="color:#8a8d94">–</div>'
                    '<div style="font-size:12px;color:#55585f;margin-top:5px;line-height:1.6">'
                    'ต้องมีรัน easy 3 ครั้งภายใน 14 วัน และฐานอย่างน้อย 5 ครั้งใน 28 วันก่อนหน้า '
                    '— ยังไม่ครบตามนี้ ไม่ใช่ระบบขัดข้อง</div>'
                )
                st.markdown(
                    '<div class="today-panel"><div class="today-panel__head">'
                    '<div class="today-panel__title">ประสิทธิภาพการวิ่งเบา (EF)</div>'
                    '<div class="today-panel__hint">ตัวตัดสิน</div></div>'
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
                    f'{html.escape(str(team_row["เซสชัน 7 วัน"] or 0))} เซสชัน</div></div>',
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
    # TAB 4: TRAINING (นักกีฬาที่เลือก) — โหลดสะสม + EF + 80/20 + กราฟเดิม
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
                st.metric("จำนวนครั้งที่วิ่ง", f"{len(runs_df)}", border=True)
                st.metric("เพซเฉลี่ย", f"{fmt_pace(avg_pace_raw)} /km" if pd.notna(avg_pace_raw) else "–", border=True)
                st.metric("เวลาวิ่งรวม", f"{total_hours:.1f} ชม.", border=True)

            # ---------------- ประสิทธิภาพการวิ่งเบา (EF) — ตัวตัดสิน ----------------
            st.subheader("ประสิทธิภาพการวิ่งเบา (EF)")
            ef_lookback = start_date - datetime.timedelta(days=EF_BASELINE_DAYS)
            lthr_for_tab, _ = get_lthr(selected_slug, athlete_id)
            ef_all = easy_run_efficiency(
                load_easy_runs(athlete_id, ef_lookback.isoformat(), end_date.isoformat()),
                lthr_for_tab,
            )
            ef_pct_tab = efficiency_change_pct(ef_all, end_date)
            ef_view = ef_all[ef_all["date"] >= pd.Timestamp(start_date)]

            if ef_view.empty:
                st.info(
                    "ยังมีรัน easy ไม่พอในช่วงนี้ที่จะคำนวณ EF "
                    f"(ต้องมี HR, ระยะ ≥ {EF_MIN_DISTANCE_M / 1000:.0f} กม. และ HR ≤ "
                    f"{EASY_MAX_PCT * 100:.0f}% ของ LTHR"
                    + (f" = {lthr_for_tab * EASY_MAX_PCT:.0f} bpm)" if lthr_for_tab else ")")
                    + " — เป็นเรื่องปกติของคนที่ซ้อม cross-training เป็นหลัก ไม่ใช่ระบบขัดข้อง",
                    icon=":material/info:",
                )
            else:
                emoji, txt = efficiency_status(ef_pct_tab)
                ef_baseline_median = ef_all[
                    ef_all["date"] < ef_all["date"].iloc[-1]
                ].tail(20)["ef"].median()
                # ข้อจำกัดของ EF อยู่ใน help ของการ์ดที่มันอธิบาย ไม่ใช่ย่อหน้าใต้กราฟ —
                # คนที่สงสัยตัวเลขไหนจะจิ้มตัวเลขนั้น ไม่ใช่อ่านทุกอย่างเพื่อหาบรรทัดเดียว
                with st.container(horizontal=True):
                    _ef_now = efficiency_recent_value(ef_all, end_date)
                    st.metric("EF ล่าสุด (median 3 รัน)",
                              f"{_ef_now:.3f}" if pd.notna(_ef_now) else "–",
                              delta=f"{emoji} {txt}", delta_color="off", border=True,
                              help="EF ไวต่ออากาศร้อน พื้นผิว และความชัน "
                                   "จึงต้องอ่านเป็นเทรนด์ ไม่ใช่ค่าวันเดียว")
                    st.metric("เทียบฐาน 28 วัน", efficiency_display(ef_pct_tab), border=True,
                              help="เกณฑ์ −3% / −7% มาจาก SD ของข้อมูลจริงในระบบนี้ "
                                   "(4.4% และ 3.5%)")
                    st.metric("จำนวนรัน easy ในช่วง", f"{len(ef_view)} ครั้ง", border=True,
                              help=f"จะสรุป EF ได้ต้องมีรัน easy {EF_RECENT_RUNS} ครั้ง"
                                   f"ภายใน {EF_STALE_DAYS} วัน และมีฐานอย่างน้อย "
                                   f"{EF_BASELINE_MIN_RUNS} ครั้งใน {EF_BASELINE_DAYS} "
                                   "วันก่อนหน้า — ไม่ครบแล้วขึ้น 'ข้อมูลไม่พอ' คือรัน easy "
                                   "ไม่พอ ไม่ใช่ระบบขัดข้อง")

                fig_ef = go.Figure()
                fig_ef.add_trace(go.Scatter(
                    x=ef_view["date"], y=ef_view["ef"], mode="lines+markers",
                    line=dict(color=C_BLUE, width=2), marker=dict(size=6), name="EF ต่อรัน",
                    connectgaps=False,
                    hovertemplate="%{x|%d %b}<br>EF %{y:.3f}<extra></extra>",
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
                    title="ความเร็ว ÷ HR ในรัน easy — สูงขึ้น = วิ่งเร็วขึ้นที่หัวใจเท่าเดิม",
                    yaxis=dict(title="EF (เมตร/นาที ต่อ 1 bpm)"),
                    xaxis=dict(title="วันที่"),
                    showlegend=True, hovermode="x unified",
                )
                st.plotly_chart(fig_ef, width="stretch")

            # ---------------- โหลดสะสม (บริบท ไม่ใช่คำตัดสิน) ----------------
            st.subheader("โหลดสะสม (บริบท)")
            load_start = start_date - datetime.timedelta(days=56)
            daily_wl, wl_metric, wl_unit = load_daily_workload(athlete_id, load_start.isoformat(), end_date.isoformat())
            first_workload_date = (
                load_first_activity_date(athlete_id)
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
                    st.metric("ฐาน 28 วัน",
                              f"{latest_load['chronic']:{_afmt}} {wl_unit}/สัปดาห์"
                              if pd.notna(latest_load["chronic"]) else "–", border=True)
                    st.metric("ทิศทาง",
                              load_trend_display(latest_load["acute"], latest_load["chronic"],
                                                 wl_metric, wl_unit).split(" · ")[-1]
                              if pd.notna(latest_load["chronic"]) else "–", border=True,
                              help="บอกว่าทำไปเท่าไหร่เทียบกับที่เคยทำ "
                                   "ไม่มีโซนปลอดภัย/เสี่ยง เพราะหลักฐานหาเกณฑ์ตัด"
                                   "ที่ทำนายการบาดเจ็บได้ไม่เจอ "
                                   "(Br J Sports Med 2025;59:1203-1210)")

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
                # ตัวแทนโหลด (`_src`) อยู่บนหัวข้อกราฟแล้ว ส่วนเหตุผลว่าทำไมไม่มีโซน
                # ปลอดภัย/เสี่ยงอยู่ใน help ของการ์ด "ทิศทาง" ซึ่งเป็นค่าที่คนอยากตีความ
                st.plotly_chart(fig_load, width="stretch")

            # ---------------- 80/20 (จากเวลาในโซน HR จริงของนาฬิกา) ----------------
            st.subheader("สัดส่วนความหนักการซ้อม (กฎ 80/20)")
            zone_cols = ["hr_zone1_sec", "hr_zone2_sec", "hr_zone3_sec", "hr_zone4_sec", "hr_zone5_sec"]
            have_zone_cols = set(zone_cols).issubset(activity_df.columns)
            zdf = usable_hr_zone_rows(activity_df, zone_cols) if have_zone_cols else activity_df.iloc[0:0]

            if not zdf.empty:
                z = zdf[zone_cols].apply(pd.to_numeric, errors="coerce").clip(lower=0).fillna(0).sum()
                buckets = {
                    INTENSITY_ORDER[0]: (z["hr_zone1_sec"] + z["hr_zone2_sec"]) / 60,   # Z1-2 เบา
                    INTENSITY_ORDER[1]: z["hr_zone3_sec"] / 60,                          # Z3 กลาง
                    INTENSITY_ORDER[2]: (z["hr_zone4_sec"] + z["hr_zone5_sec"]) / 60,    # Z4-5 หนัก
                }
                dist = pd.DataFrame({"intensity": list(buckets), "minutes": list(buckets.values())})
                total_min = dist["minutes"].sum()
                easy_pct = (buckets[INTENSITY_ORDER[0]] / total_min * 100) if total_min > 0 else 0.0

                col_pie, col_info = st.columns([3, 2])
                with col_pie:
                    fig_pie = px.pie(dist, values="minutes", names="intensity", hole=0.55,
                                     color="intensity", color_discrete_map=INTENSITY_COLORS,
                                     category_orders={"intensity": INTENSITY_ORDER},
                                     title="สัดส่วนเวลาซ้อมตามโซน HR จริง (Garmin zones)")
                    fig_pie.update_traces(textinfo="percent+label", sort=False,
                                          hovertemplate="%{label}<br>%{value:.0f} นาที (%{percent})<extra></extra>")
                    st.plotly_chart(fig_pie, width="stretch")
                with col_info:
                    st.metric("สัดส่วนเบา (Z1-2 ตามเวลาจริง)", f"{easy_pct:.0f}%",
                              delta=f"{easy_pct - 80:+.0f}% เทียบเป้า 80%",
                              delta_color="normal" if easy_pct >= 80 else "inverse",
                              border=True,
                              help=f"จากเวลาในโซน HR จริงของ {len(zdf)} กิจกรรม "
                                   "(รวม cross-training) — แม่นกว่าเฉลี่ยทั้งเซสชัน "
                                   "เพราะนาฬิกาเก็บวินาทีต่อโซนจริง")
                    for name in INTENSITY_ORDER:
                        st.markdown(f"- **{name}** — {buckets[name]:.0f} นาที")
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
                        st.metric("สัดส่วนวิ่งเบา (ตามเวลา)", f"{easy_pct:.0f}%",
                                  delta=f"{easy_pct - 80:+.0f}% เทียบเป้า 80%",
                                  delta_color="normal" if easy_pct >= 80 else "inverse",
                                  border=True,
                                  help="ไม่มีเวลาในโซน HR จริง จึงจำแนกจาก avg HR "
                                       f"ต่อเซสชันเทียบ LTHR {lthr} bpm ({lthr_source}) "
                                       "ซึ่งหยาบกว่า")
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
                                       "GCT ต่ำ/ratio ต่ำ = ฟอร์มประหยัดแรง")

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
        if advanced_performance_missing_message:
            st.info(advanced_performance_missing_message, icon=":material/insights:")

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
                    first_v, last_v = vo2["vo2max_trend"].iloc[0], vo2["vo2max_trend"].iloc[-1]
                    st.metric("VO2max ล่าสุด (Garmin)", f"{last_v:.1f}",
                              delta=f"{last_v - first_v:+.1f} เทียบต้นช่วง", border=True)
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
            st.info("ไม่มีข้อมูล VO2max ในช่วงที่เลือก (นาฬิกาอัปเดตเฉพาะวันที่มีวิ่ง GPS)")

        # ---------------- Body composition ----------------
        # endpoint นี้มักมีข้อมูลห่าง ๆ และอาจอยู่นอกช่วง 30 วันที่เลือก จึงแสดงค่าล่าสุด
        # จากประวัติทั้งหมด พร้อมวันที่จริงของแต่ละ field แทนการทำให้ค่าหายจาก dashboard.
        st.subheader("องค์ประกอบร่างกายจาก Garmin")
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
            st.info("Garmin ยังไม่ส่งข้อมูลน้ำหนัก, BMI หรือเปอร์เซ็นต์ไขมันสำหรับนักกีฬาคนนี้")
        else:
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
        st.subheader("เวลาการแข่งขันที่ Garmin คาดการณ์")
        preds = load_race_predictions(athlete_id, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
        if preds.empty:
            st.info("ไม่มีข้อมูลคาดการณ์ในช่วงที่เลือก")
        else:
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
            st.caption("คาดการณ์ของ Garmin มักมองโลกในแง่ดีกว่าสนามจริง ~1-3% — "
                       "ใช้ดูเทรนด์ว่าฟอร์มกำลังขึ้นหรือตก แล้วเทียบกับ VDOT จากเทสจริง")

        # ---------------- Lactate Threshold (Garmin) ----------------
        lt_row = load_latest_lt(athlete_id)
        if lt_row:
            lt_date, lt_hr, lt_pace = lt_row
            st.subheader("Lactate threshold จาก Garmin")
            with st.container(horizontal=True):
                st.metric("LT Heart Rate", f"{lt_hr:.0f} bpm" if lt_hr is not None else "–", border=True)
                st.metric("LT Pace", f"{fmt_pace(lt_pace)} /km" if lt_pace is not None else "–", border=True)
                st.metric("วันที่วัด", lt_date, border=True)
            st.caption("ค่าประเมินจากการวิ่งจริงด้วยสาย HR — เทียบกับผลเทสแลบ (ถ้ามี) ก่อนใช้ปรับโซน")
        else:
            st.info(
                "Garmin Connect ยังไม่เคยส่ง Lactate Threshold สำหรับนักกีฬาคนนี้ "
                "ค่านี้ต้องอาศัยอุปกรณ์/กิจกรรมที่เข้าเงื่อนไขของ Garmin",
                icon=":material/speed:",
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
            st.info(
                "ไม่มี Endurance Score หรือ Hill Score ในช่วงนี้; Garmin ให้เมตริกเหล่านี้ "
                "ตามความสามารถของอุปกรณ์ บัญชี และประวัติกิจกรรม",
                icon=":material/landscape:",
            )
        # ---------------- Personal records ----------------
        st.subheader("สถิติส่วนตัวจาก Garmin")
        prs = load_personal_records(athlete_id)
        if prs.empty:
            st.info("ไม่มีข้อมูล PR")
        else:
            st.dataframe(pd.DataFrame(personal_record_rows(prs)), hide_index=True)
            st.caption("PR นับตามที่นาฬิกาบันทึกอัตโนมัติ — ระยะที่ GPS วัดไม่ถึงเกณฑ์ (เช่น 4.98 กม.) จะไม่ถูกนับเป็น 5K")


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
                    # --- วิเคราะห์ครึ่งแรก vs ครึ่งหลัง (จับอาการแผ่วปลาย) ---
                    if len(splits) >= 2:
                        p1, p2, hr1, hr2 = analyze_distance_halves(splits)

                        split_pct = (p2 - p1) / p1 * 100 if pd.notna(p1) and pd.notna(p2) and p1 > 0 else float("nan")
                        if pd.isna(split_pct):
                            verdict = "–"
                        elif split_pct > 2:
                            verdict = f"🔻 แผ่วปลาย (+{split_pct:.1f}%)"
                        elif split_pct < -2:
                            verdict = f"🚀 Negative split ({split_pct:.1f}%)"
                        else:
                            verdict = f"✅ เพซนิ่ง ({split_pct:+.1f}%)"

                        with st.container(horizontal=True):
                            st.metric("ครึ่งแรก", f"{fmt_pace(p1)} /km", border=True)
                            st.metric("ครึ่งหลัง", f"{fmt_pace(p2)} /km", border=True)
                            st.metric("Pacing", verdict, border=True)
                            if pd.notna(hr1) and pd.notna(hr2):
                                st.metric("HR ครึ่งแรก → หลัง", f"{hr1:.0f} → {hr2:.0f} bpm",
                                          delta=f"{hr2 - hr1:+.0f} bpm", delta_color="off", border=True)

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
                    st.subheader("📊 ตาราง Splits (ผลต่อรอบ)")
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
