import datetime
import json
import math
import sqlite3
import time
from pathlib import Path

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

# --- PLOTLY DEFAULT TEMPLATE ---
# ธีมสว่าง: พื้น transparent (โชว์พื้นขาวของหน้า) + ฟอนต์สีเข้ม อ่านได้ทั้งบนจอและตอนพิมพ์
_print_friendly = pio.templates["plotly"]
_print_friendly.layout.paper_bgcolor = "rgba(0,0,0,0)"
_print_friendly.layout.plot_bgcolor = "rgba(0,0,0,0)"
_print_friendly.layout.font = dict(color="#31333F")  # เทาเข้ม (ตรงกับ text ธีม light ของ Streamlit)
pio.templates.default = _print_friendly

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "garmin.db"

# ประเภทกิจกรรมที่นับเป็น "วิ่ง" (ใช้คำนวณ ACWR / 80-20)
RUN_TYPES = ("running", "track_running", "trail_running", "treadmill_running")

# LTHR จากผลเทสเป็นทางการ — ตารางนักกีฬาใน CLAUDE.md คือที่เก็บผลเทส อัปเดตทั้งสองที่ให้ตรงกัน
# tong: 5K TT 14 ก.ค. 69 | dan: VCR30 8 ก.ค. 69
# p'kao: เทสแลบ Lactate ไม่มีค่า HR → ใช้ Garmin LT จากนาฬิกา แทนค่าเดา 89%
#        อัปเดต 4 ส.ค. 69: นาฬิกาตรวจ LT ใหม่ 31 ก.ค. = HR 181 / pace 4:41 (เดิม 16 ก.ค. HR 184 / 5:04)
LTHR_BY_SLUG = {"tong": 171, "dan": 178, "p'kao": 181}
LTHR_SOURCE_BY_SLUG = {
    "tong": "จากผลเทสล่าสุด (5K TT 14 ก.ค.)",
    "dan": "จากผลเทสล่าสุด (VCR30 8 ก.ค.)",
    "p'kao": "จาก Garmin LT ล่าสุด 31 ก.ค. (เทสแลบไม่มีค่า HR)",
}

# ขอบเขตโซนตาม %LTHR (Friel): เบา Z1-2 <= 89%, กลาง Z3 90-93%, หนัก Z4-5 >= 94%
EASY_MAX_PCT = 0.89
GRAY_MAX_PCT = 0.94

# สีสถานะ (ผ่าน CVD validation) — ใช้คู่กับข้อความกำกับเสมอ ไม่สื่อด้วยสีอย่างเดียว
C_GOOD = "#0ca30c"
C_WARN = "#fab219"
C_CRIT = "#d03b3b"
C_NEUTRAL = "#c3c9d2"  # เทาอมฟ้าอ่อน — เห็นได้บนพื้นขาว (แถบ ACWR "ต่ำกว่าฐาน")
C_BLUE = "#2a78d6"   # เส้นข้อมูลหลัก
C_RED = "#e34948"    # เส้น HR
C_GREEN = "#008300"  # โดนัท: เบา
C_AMBER = "#eda100"  # โดนัท: กลาง

INTENSITY_ORDER = ["เบา (Z1–2)", "กลาง (Z3)", "หนัก (Z4–5)"]
INTENSITY_COLORS = {"เบา (Z1–2)": C_GREEN, "กลาง (Z3)": C_AMBER, "หนัก (Z4–5)": C_RED}


# --- HELPERS ---
def fmt_num(value, suffix=""):
    """Format a metric value; show a dash when the data is missing (NaN)."""
    return f"{value:.1f}{suffix}" if pd.notna(value) else "–"


def fmt_text(value, fallback=""):
    """Return clean text without leaking Pandas NaN into the UI."""
    return value.strip() if isinstance(value, str) and value.strip() else fallback


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


def acwr_status(ratio):
    """แปลงค่า ACWR เป็น (อิโมจิ, คำอธิบาย)"""
    if pd.isna(ratio):
        return "⚪", "ข้อมูลไม่พอ"
    if ratio > 1.5:
        return "🔴", "เสี่ยงบาดเจ็บ"
    if ratio > 1.3:
        return "🟡", "โหลดขาขึ้น"
    if ratio < 0.8:
        return "🔵", "ต่ำกว่าฐาน"
    return "🟢", "ปลอดภัย"


def compute_acwr(daily, end_date):
    """คำนวณ ACWR รายวันจากตาราง (date, value): acute = ผลรวม 7 วัน, chronic = ผลรวม 28 วัน / 4
    value = training_load หรือ ระยะวิ่ง(กม.) — ACWR เป็นอัตราส่วน จึงเทียบได้ทั้งสองหน่วย"""
    if daily.empty:
        return pd.DataFrame(columns=["date", "acute", "chronic", "acwr"])
    idx = pd.date_range(daily["date"].min(), pd.Timestamp(end_date), freq="D")
    s = daily.set_index("date")["value"].reindex(idx, fill_value=0.0)
    acute = s.rolling(7, min_periods=7).sum()
    chronic = s.rolling(28, min_periods=28).sum() / 4
    out = pd.DataFrame({"date": idx, "acute": acute.values, "chronic": chronic.values})
    out["acwr"] = out["acute"] / out["chronic"].where(out["chronic"] > 0)
    return out


def pace_axis_ticks(pace_series):
    """สร้าง tick แกนเพซเป็น M:SS ทุก 15/30/60 วิ ตามช่วงข้อมูล"""
    pmin, pmax = float(pace_series.min()), float(pace_series.max())
    rng = max(pmax - pmin, 0.01)
    step = 0.25 if rng <= 2 else (0.5 if rng <= 4 else 1.0)
    start = math.floor(pmin / step) * step
    end = math.ceil(pmax / step) * step
    vals = [round(start + i * step, 4) for i in range(int(round((end - start) / step)) + 1)]
    return vals, [fmt_pace(v) for v in vals]


# --- DB LOADERS ---
# แคชสั้นกว่ารอบ sync ที่ถี่ที่สุด (fast activity 15 นาที / fast wellness 30 นาที) ไม่งั้น
# ข้อมูลลง DB แล้วแต่หน้าจอยังค้างของเก่าโดยไม่มีเหตุผล — 2 นาทีพอให้ query ไม่ถี่เกิน
CACHE_TTL_SEC = 120
AUTO_REFRESH_SEC = 60
# แถบเหลือง sanity check โชว์เฉพาะรอบที่ยัง "สด" — เกิน 24 ชม. ถือเป็นประวัติ ย้ายลงกล่องพับ
# (24 ชม. ครอบสาย full ที่รันวันละ 2 รอบไว้พอดี ส่วนสายถี่กว่านั้นสดอยู่แล้ว)
SANITY_WARN_FRESH_MIN = 24 * 60

# เพดาน "สายนี้เงียบเกินคาบ" ต่อสายงาน (นาที) = คาบเดินจริง + เผื่อรอบที่ข้ามเพราะ lock
# ⚠️ ต้องมีครบทุกสายและตรงกับ $STALE_LIMIT_MIN ใน scripts\notify_sync.ps1 — สายที่ตกหล่น
# จะโชว์ ✅ ค้างตลอดกาลแม้ตายไปแล้ว (เดิมหล่น reconcile/deep ซึ่งเป็นสองสายที่อันตรายที่สุด
# เพราะนาน ๆ เดินที ตายแล้วไม่มีใครสังเกตได้เป็นสัปดาห์ — เคสเดียวกับ deepsync 2 ส.ค. 69)
# toast เตือนได้ก็จริงแต่มันหายไปกับตา ส่วนหน้านี้คือที่เดียวที่ย้อนดูได้ทีหลัง
LANE_STALE_LIMIT_MIN = {
    "full": 900, "fast": 75, "wellness": 90,
    "reconcile": 12240, "deep": 44640, "backup": 1800,
}


@st.cache_data(ttl=CACHE_TTL_SEC)
def load_athletes():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT athlete_id, display_name, slug FROM dim_athlete", conn)
    conn.close()
    return df


# คอลัมน์ที่เป็นข้อความ (ที่เหลือ coerce เป็นตัวเลขทั้งหมด กัน object dtype ตอนคอลัมน์ NULL ล้วน)
_WELLNESS_TEXT = {"calendar_date", "hrv_status", "training_status", "readiness_level",
                  "readiness_feedback", "fetched_at"}
_ACTIVITY_TEXT = {"activity_type", "activity_name", "start_time_local", "start_time_utc",
                  "training_effect_label", "location_name", "fetched_at"}


@st.cache_data(ttl=CACHE_TTL_SEC)
def load_wellness_data(athlete_id, start_date, end_date):
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
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
def load_daily_run_km(athlete_id, start_date, end_date):
    """ระยะวิ่งรวมรายวัน (เฉพาะประเภทวิ่ง) สำหรับ ACWR"""
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    placeholders = ",".join("?" for _ in RUN_TYPES)
    row = conn.execute(
        f"SELECT MIN(SUBSTR(start_time_local, 1, 10)) FROM fact_activity "
        f"WHERE athlete_id = ? AND activity_type IN ({placeholders}) AND deleted_at IS NULL",
        (athlete_id, *RUN_TYPES)).fetchone()
    conn.close()
    return datetime.date.fromisoformat(row[0]) if row and row[0] else None


@st.cache_data(ttl=CACHE_TTL_SEC)
def athlete_has_load(athlete_id):
    """นาฬิกาคนนี้ให้ค่า training_load ไหม (บางรุ่นไม่ให้ → ต้อง fallback เป็นระยะวิ่ง)"""
    conn = sqlite3.connect(DB_PATH)
    n = conn.execute(
        "SELECT COUNT(*) FROM fact_activity "
        "WHERE athlete_id = ? AND training_load IS NOT NULL AND deleted_at IS NULL",
        (athlete_id,)).fetchone()[0]
    conn.close()
    return n > 0


@st.cache_data(ttl=CACHE_TTL_SEC)
def load_daily_load(athlete_id, start_date, end_date):
    """ผลรวม Garmin training_load รายวัน — ทุกกิจกรรม (รวม cross-training: HIIT/เวท/มวย)"""
    conn = sqlite3.connect(DB_PATH)
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
    """คืน (df[date,value,sessions], metric, unit) สำหรับ ACWR
    ใช้ training_load ถ้านาฬิกาให้ (จับ cross-training ครบ) ไม่งั้น fallback ระยะวิ่ง (กม.)"""
    if athlete_has_load(athlete_id):
        return load_daily_load(athlete_id, start_date, end_date), "training_load", "TL"
    df = load_daily_run_km(athlete_id, start_date, end_date).rename(columns={"km": "value"})
    return df, "ระยะวิ่ง", "km"


@st.cache_data(ttl=CACHE_TTL_SEC)
def load_first_activity_date(athlete_id):
    """วันแรกที่มีกิจกรรม (ทุกประเภท) — ใช้ตัดสินความพอของประวัติเมื่อ ACWR อิง training_load"""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT MIN(SUBSTR(start_time_local, 1, 10)) FROM fact_activity "
        "WHERE athlete_id = ? AND deleted_at IS NULL",
        (athlete_id,)).fetchone()
    conn.close()
    return datetime.date.fromisoformat(row[0]) if row and row[0] else None


@st.cache_data(ttl=CACHE_TTL_SEC)
def load_last_data_dates(athlete_id):
    """วันล่าสุดที่มี activity / wellness — ใช้ทำแถบเตือนถ้า sync ค้าง (token หมด/Task ล้ม)

    wellness ต้องนับเฉพาะวันที่ "มีข้อมูลจริง" — ระบบ sync insert แถวของวันใหม่ไว้ก่อน
    แม้ค่าทุกช่องเป็น NULL (นักกีฬายังไม่ sync นาฬิกา) ถ้านับแถวเปล่าด้วย แถบจะโชว์
    🟢 "วันนี้" ทั้งที่ข้อมูลจริงหยุดไปแล้ว (เคสพี่เก้า 22 ก.ค. 69)"""
    conn = sqlite3.connect(DB_PATH)
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


WELLNESS_STALE_DAYS = 3  # ตั้งแต่กี่วันขึ้นไปถือว่า "ค้างจริง" ต้องไปไล่หาสาเหตุ


def wellness_freshness(days):
    """ป้ายความสดของ wellness รายคน — days = จำนวนวันนับจากข้อมูลล่าสุด (None = ไม่มีเลย)

    ข้อมูลค้าง ≠ ระบบพัง: ข้อมูลหยุดที่เมื่อวานส่วนใหญ่แปลว่าต้นทางฝั่ง Garmin ยังไม่ sync
    มา (🟠 รอ) ลำพังแค่นี้ยังไม่ใช่หลักฐานว่าสายงานฝั่งเราล้ม — ปัญหาจริงของ pipeline
    มีแถบสายงานด้านล่างจับแยกให้อยู่แล้ว
    เดิมเมื่อวานขึ้น 🟢 เหมือนวันนี้ ทำให้โค้ชอ่านตัวเลขของเมื่อวานเป็นสถานะวันนี้
    """
    if days is None:
        return "🔴", "ไม่มีข้อมูล"
    if days == 0:
        return "🟢", "ข้อมูลอัปเดตแล้ว — วันนี้"
    last = "เมื่อวาน" if days == 1 else f"{days} วันก่อน"
    icon = "🟠" if days < WELLNESS_STALE_DAYS else "🔴"
    return icon, f"รอ Garmin sync — ข้อมูลล่าสุด: {last}"


@st.cache_data(ttl=CACHE_TTL_SEC)
def load_observed_max_hr(athlete_id):
    """HR สูงสุดที่เคยบันทึก — ใช้ประมาณ LTHR เมื่อยังไม่มีผลเทส"""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT MAX(max_hr) FROM fact_activity "
                       "WHERE athlete_id = ? AND deleted_at IS NULL", (athlete_id,)).fetchone()
    conn.close()
    return row[0] if row and row[0] else None


@st.cache_data(ttl=CACHE_TTL_SEC)
def load_splits(activity_id):
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        """SELECT record_type_id, record_label, value, achieved_date
           FROM fact_personal_record WHERE athlete_id = ? ORDER BY record_type_id ASC""",
        conn, params=(athlete_id,))
    conn.close()
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


@st.cache_data(ttl=CACHE_TTL_SEC)
def load_latest_lt(athlete_id):
    """Garmin Lactate Threshold ล่าสุด (hr, pace, วันที่) — None ถ้านาฬิกาไม่ให้"""
    conn = sqlite3.connect(DB_PATH)
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
    """Clear cached data and rerun the full dashboard once per interval."""
    now = time.monotonic()
    last_refresh = st.session_state.get("_dashboard_auto_refresh_at")
    if last_refresh is None:
        st.session_state["_dashboard_auto_refresh_at"] = now
        return
    if now - last_refresh >= AUTO_REFRESH_SEC:
        st.session_state["_dashboard_auto_refresh_at"] = now
        st.cache_data.clear()
        st.rerun(scope="app")


# --- UI START ---
today = datetime.date.today()
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

    # ปุ่มรีเฟรช: ล้าง cache (loaders ใช้ @st.cache_data ttl 2 นาที) + rerun → ดึงข้อมูลสดจาก DB ทันที
    # จำเป็นเพราะหลังรัน garmin-sync-auto ข้อมูลใหม่จะไม่ขึ้นจนกว่า cache หมดอายุ/ล้าง (reload หน้าไม่ช่วย)
    if st.button(
        "รีเฟรชข้อมูลล่าสุด",
        icon=":material/refresh:",
        type="primary",
        width="stretch",
    ):
        st.cache_data.clear()
        st.rerun()
    _c = sqlite3.connect(DB_PATH)
    _la = _c.execute("SELECT MAX(start_time_local) FROM fact_activity WHERE deleted_at IS NULL").fetchone()[0]
    # ต้องกรองแถวที่ยังไม่มีค่าจริง — full sync สร้างแถวของวันใหม่ไว้ก่อนแม้ทุกช่องเป็น NULL
    # ถ้านับแถวเปล่าด้วย บรรทัดนี้จะโชว์ "วันนี้" ตลอดทั้งที่ข้อมูลจริงหยุดไปแล้ว
    # (เกณฑ์เดียวกับ load_last_data_dates — เคยหลอกมาแล้วเคสพี่เก้า 22 ก.ค. 69)
    # fetched_at เก็บเป็น UTC (datetime('now') ของ SQLite) — ให้ SQLite แปลงเป็นเวลาเครื่องเอง
    _lw, _lw_fetched = _c.execute(
        """SELECT MAX(calendar_date), datetime(MAX(fetched_at), 'localtime')
           FROM fact_daily_wellness
           WHERE resting_hr IS NOT NULL OR sleep_score IS NOT NULL
              OR body_battery_high IS NOT NULL OR hrv_last_night IS NOT NULL""").fetchone()
    _c.close()
    _lw_txt = f"{_lw} (ดึงล่าสุด {_lw_fetched[11:16]} น.)" if _lw and _lw_fetched else (_lw or "—")
    st.caption(f"ข้อมูลล่าสุด — กิจกรรม: {_la or '—'} · สุขภาพ: {_lw_txt}")
    st.caption("ข้อมูลจะรีเฟรชอัตโนมัติทุก 60 วินาที หรือกดรีเฟรชหลังนาฬิกา sync")

    athlete_options = dict(zip(athletes_df["display_name"], athletes_df["athlete_id"]))
    selected_name = st.selectbox("นักกีฬา", options=list(athlete_options.keys()), key="selected_athlete")
    athlete_id = athlete_options[selected_name]
    selected_slug = athletes_df.loc[athletes_df["athlete_id"] == athlete_id, "slug"].iloc[0]

    st.markdown("**ช่วงข้อมูลสำหรับหน้าวิเคราะห์ย้อนหลัง**")
    history_period = st.segmented_control(
        "ช่วงย้อนหลัง",
        options=["7 วัน", "30 วัน", "90 วัน", "กำหนดเอง"],
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
if not activity_df.empty:
    activity_df["start_time_local"] = pd.to_datetime(activity_df["start_time_local"])
    activity_df["distance_km"] = activity_df["distance_m"] / 1000

# --- MAIN DASHBOARD TABS ---
tab_today, tab_team, tab_health, tab_train, tab_progress, tab_splits = st.tabs([
    ":material/today: วันนี้",
    ":material/groups: ทีม",
    ":material/bedtime: การฟื้นตัว",
    ":material/directions_run: การซ้อม",
    ":material/trending_up: ความก้าวหน้า",
    ":material/query_stats: รายละเอียดเซสชัน",
])


# =====================================================================
# TAB 2: TEAM OVERVIEW
# =====================================================================
with tab_team:
    st.header("สถานะทีมวันนี้")
    st.caption(f"ข้อมูล ณ {today.isoformat()} — ACWR = โหลด 7 วัน ÷ ค่าเฉลี่ยรายสัปดาห์ของ 28 วัน "
               "(ใช้ Garmin training_load ถ้านาฬิกาให้ = รวม cross-training, ไม่งั้นใช้ระยะวิ่ง)")

    # --- แถบเตือนความสดของข้อมูล (จับ token หมดอายุ / Task sync ล้ม) ---
    fresh_parts, stale_names = [], []
    for _, ath in athletes_df.iterrows():
        _, lw = load_last_data_dates(ath["athlete_id"])
        days = (today - datetime.date.fromisoformat(lw)).days if lw else None
        icon, txt = wellness_freshness(days)
        if days is None:
            stale_names.append(f"{ath['display_name']} (ไม่มีข้อมูล)")
        elif days >= WELLNESS_STALE_DAYS:
            stale_names.append(f"{ath['display_name']} ({days} วัน)")
        fresh_parts.append(f"{icon} **{ath['display_name']}**: {txt}")
    st.markdown("**🔄 sync ล่าสุด (wellness):** &nbsp; " + " &nbsp;·&nbsp; ".join(fresh_parts))
    if stale_names:
        st.warning("⚠️ ข้อมูลค้าง ≥ 3 วัน: " + ", ".join(stale_names)
                   + " — เช็ค log `C:\\Backup\\garmin-sync-<สาย>.log` | token เสียให้รัน `เพิ่มนักกีฬา.bat` ใหม่ "
                     "| ถ้า sync รอบล่าสุดผ่าน (ไม่มีแถบแดงด้านล่าง) = นักกีฬาไม่ได้เปิดแอป Garmin ให้นาฬิกา sync")

    # --- ผลรอบ sync ล่าสุด "แยกตามสายงาน" (จาก data/sync_lane/<lane>.json ที่ fetch_all เขียน) ---
    # จับปัญหาได้ทันทีในรอบเดียว (token เสีย/ข้อมูลเพี้ยน) ไม่ต้องรอข้อมูลค้าง 3 วันแบบแถบบน
    # ต้องอ่านแยกสายงาน เพราะทุกสายเขียน sync_status.json ทับกัน — full sync 21:00 ล้มแล้ว
    # fast wellness 21:08 ผ่าน จะกลบแถบแดงหายไปทั้งที่ปัญหายังอยู่
    _LANE_LABEL = {"full": "เต็ม (08:00/21:00)", "fast": "กิจกรรม (ทุก 15 นาที)",
                   "wellness": "wellness (ทุก 30 นาที)", "reconcile": "reconcile (รายสัปดาห์)",
                   "deep": "deep resync (รายเดือน)", "backup": "สำรองข้อมูล (22:00)"}
    _reason_txt = {"token": "token เสีย → รัน เพิ่มนักกีฬา.bat",
                   "network": "เน็ต/เซิร์ฟเวอร์มีปัญหา",
                   "timeout": "ค้างเกินเวลา",
                   "db": "สำเนา garmin.db ไม่สำเร็จ → เปิด C:\\Backup\\backup-log.txt",
                   "robocopy": "robocopy mirror มีปัญหา → เปิด C:\\Backup\\backup-log.txt"}
    _lane_dir = DB_PATH.parent / "sync_lane"
    _lane_files = sorted(_lane_dir.glob("*.json")) if _lane_dir.exists() else []
    # ไฟล์รวมแบบเดิม = fallback ให้ระบบที่ยังไม่ได้รัน sync รอบใหม่หลังอัพเกรด
    if not _lane_files and (DB_PATH.parent / "sync_status.json").exists():
        _lane_files = [DB_PATH.parent / "sync_status.json"]
    _lane_lines = []
    _old_warn_lines = []
    for _f in _lane_files:
        try:
            _sync = json.loads(_f.read_text(encoding="utf-8"))
        except Exception as e:
            st.caption(f"อ่าน {_f.name} ไม่ได้: {e}")
            continue
        _label = _LANE_LABEL.get(_sync.get("lane", ""), _f.stem)
        _when = _sync["run_at"][:16].replace("T", " ")
        _fail = [r for r in _sync["results"] if not r["ok"]]
        _warn = [r for r in _sync["results"] if r["ok"] and r.get("warnings")]
        _age_min = None
        try:
            _age_min = (datetime.datetime.now()
                        - datetime.datetime.fromisoformat(_sync["run_at"])).total_seconds() / 60
        except Exception:
            pass
        if _fail:
            st.error(f"❌ sync {_label} รอบ {_when} ล้มเหลว: "
                     + " · ".join(f"**{r['slug']}** ({_reason_txt.get(r['reason'], 'ดู log')})"
                                  for r in _fail))
        # sanity warning = สภาพข้อมูล "ณ รอบนั้น" ไม่ใช่สถานะปัจจุบัน — รอบที่เก่ากว่า 1 วัน
        # คือประวัติศาสตร์ ไม่ใช่งานของวันนี้ ต้องลดชั้นลงกล่องพับ ไม่งั้นสายที่รันนาน ๆ ที
        # (deep รายเดือน / reconcile รายสัปดาห์) แปะแถบเหลืองค้างหน้าจอเป็นสัปดาห์จนคนเลิกอ่าน
        _stale_warn = _age_min is not None and _age_min > SANITY_WARN_FRESH_MIN
        for r in _warn:
            _msg = (f"🧐 **{r['slug']}** — sanity check (sync {_label} รอบ {_when}): "
                    + " | ".join(r["warnings"]))
            if _stale_warn:
                _old_warn_lines.append(_msg)
            else:
                st.warning(_msg)
        # สายที่ "เงียบหายไป" อันตรายกว่าสายที่ล้มเหลว เพราะไม่มีอะไรฟ้อง — กาไว้ให้เห็นตรงนี้
        # (เพดานเดียวกับ watchdog ใน notify_sync.ps1 — ดู LANE_STALE_LIMIT_MIN ด้านบน)
        _limit_min = LANE_STALE_LIMIT_MIN.get(_sync.get("lane", ""))
        _quiet = _limit_min is not None and _age_min is not None and _age_min > _limit_min
        _mark = "❌" if _fail else ("⏰" if _quiet else "✅")
        _lane_lines.append(f"{_mark} {_label}: {_when}"
                           + (f" (เงียบมา {_age_min / 60:.1f} ชม.)" if _quiet else ""))
    if _old_warn_lines:
        with st.expander(f"🧐 ผลตรวจ sanity จากรอบเก่า ({len(_old_warn_lines)} รายการ)"):
            for _line in _old_warn_lines:
                st.markdown("- " + _line)
    if _lane_lines:
        # st.caption ไม่รับ HTML — ใช้ตัวคั่นธรรมดา ไม่ใช่ &nbsp; แบบบรรทัด st.markdown ด้านบน
        st.caption("รอบ sync ล่าสุดของแต่ละสายงาน — " + "  ·  ".join(_lane_lines))

    team_rows = []
    for _, ath in athletes_df.iterrows():
        aid, name = ath["athlete_id"], ath["display_name"]

        # โหลดย้อน 42 วัน (training_load ถ้านาฬิกาให้ = จับ cross-training ครบ ไม่งั้นระยะวิ่ง)
        daily, metric, unit = load_daily_workload(
            aid, (today - datetime.timedelta(days=42)).isoformat(), today.isoformat())
        acute = chronic_wk = acwr = float("nan")
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
                acwr = acute / chronic_wk

        # wellness ล่าสุด + ฐาน 30 วัน
        w = load_wellness_data(aid, (today - datetime.timedelta(days=30)).isoformat(), today.isoformat())
        bb = bb_now = sleep = rhr = hrv_ms = ready = float("nan")
        rhr_delta = float("nan")
        hrv_stat = train_stat = ready_level = None
        day_complete = True
        # "ล่าสุด" = แถวล่าสุดที่มีข้อมูลจริง ไม่ใช่แถวล่าสุดตามปฏิทิน — วันใหม่ถูก insert
        # เป็น NULL ทั้งแถวได้ถ้านักกีฬายังไม่ sync นาฬิกา (เคสพี่เก้า 22 ก.ค. 69) ถ้าหยิบแถวนั้น
        # ตรงๆ การ์ดจะว่างหมดและ "ซ่อนธง" ของวันก่อนหน้า (เช่น sleep 52 ที่ควรเตือน)
        _key_cols = ["resting_hr", "sleep_score", "body_battery_high", "hrv_last_night"]
        w_data = w[w[_key_cols].notna().any(axis=1)] if not w.empty else w
        wellness_date = None          # วันที่ของแถว wellness ที่ใช้จริง (ไว้บอกในตารางถ้าไม่ใช่วันนี้)
        if not w_data.empty:
            latest = w_data.iloc[-1]
            wellness_date = datetime.date.fromisoformat(str(latest["calendar_date"])[:10])
            bb, sleep, rhr = latest["body_battery_high"], latest["sleep_score"], latest["resting_hr"]
            # ระดับ ณ ตอนนี้ (fast wellness อัปเดตทุก 30 นาที) — ต่างจาก high ที่เป็นยอดของทั้งวัน
            bb_now = latest["bb_most_recent"]
            hrv_ms, hrv_stat = latest["hrv_last_night"], latest["hrv_status"]
            ready = latest["training_readiness"]
            # อาจเป็น NaN (float) ไม่ใช่ None เมื่อ SQL คืน NULL — เช็คชนิดตรงๆ กัน .split() พัง
            _ts_raw = latest["training_status"]
            train_stat = _ts_raw if isinstance(_ts_raw, str) else None
            _rl_raw = latest["readiness_level"]
            ready_level = _rl_raw if isinstance(_rl_raw, str) else None
            baseline = w_data.iloc[:-1]["resting_hr"].dropna()
            if pd.notna(rhr) and len(baseline) >= 7:
                rhr_delta = rhr - baseline.mean()
            # แถวที่ sync ภายในวันเดียวกัน = ค่ายังไม่ครบวัน (Body Battery จุดสูงสุดยังไม่เกิด)
            fetched = pd.to_datetime(latest["fetched_at"], errors="coerce")
            if pd.notna(fetched):
                day_complete = fetched.date() > datetime.date.fromisoformat(str(latest["calendar_date"])[:10])

        # ธงเฝ้าระวัง
        flags = []
        if pd.notna(acwr) and acwr > 1.5:
            flags.append(f"โหลดพุ่ง ACWR {acwr:.2f}")
        elif pd.notna(acwr) and acwr > 1.3:
            flags.append(f"โหลดขาขึ้น ACWR {acwr:.2f}")
        if pd.notna(bb) and bb < 40 and day_complete:
            flags.append(f"Body Battery ต่ำ ({bb:.0f})")
        if pd.notna(sleep) and sleep < 60:
            flags.append(f"นอนแย่ ({sleep:.0f})")
        if pd.notna(rhr_delta) and rhr_delta >= 5:
            flags.append(f"RHR สูงกว่าฐาน +{rhr_delta:.0f}")
        if hrv_stat in ("LOW", "UNBALANCED"):
            flags.append(f"HRV {hrv_stat}")
        # training_status ของ Garmin (device-dependent — พี่เก้ามี, ต้อง/แดนเป็น NULL)
        # ค่าดิบมี suffix ตัวเลข เช่น STRAINED_1 / UNPRODUCTIVE_5 → ตัดเหลือคำหลักก่อนเทียบ
        _ts_base = (train_stat or "").split("_")[0]
        _ts_flag = {"STRAINED": "ล้าสะสม (Strained)",
                    "OVERREACHING": "โหลดเกินตัว (Overreaching)",
                    "UNPRODUCTIVE": "ซ้อมไม่ขึ้น (Unproductive)"}
        if _ts_base in _ts_flag:
            flags.append(f"Garmin: {_ts_flag[_ts_base]}")
        # Training Readiness ของ Garmin (device-dependent เช่นกัน — พี่เก้ามี, ต้อง/แดนเป็น NULL)
        # ค่าอัปเดตระหว่างวันจาก fast wellness แล้ว จึงใช้ตัดสิน "วันนี้ซ้อมหนักได้ไหม" ได้จริง
        if ready_level in ("POOR", "LOW"):
            flags.append(f"Readiness ต่ำ ({ready:.0f} {ready_level.title()})"
                         if pd.notna(ready) else f"Readiness {ready_level.title()}")

        hard_red = pd.notna(acwr) and acwr > 1.5
        no_data = daily.empty and w_data.empty
        if no_data:
            # ไม่มีทั้ง workload และ wellness เลย — ห้ามตกไปเคส 🟢 "พร้อมซ้อม" ทั้งที่ไม่รู้อะไร
            # (เกิดได้ตอนเพิ่มนักกีฬาใหม่ที่ยังไม่ backfill หรือ token เสียจนข้อมูลขาดยาว)
            status = "⚪ ไม่มีข้อมูล"
        elif hard_red or len(flags) >= 2:
            status = "🔴 ต้องพัก/ลดโหลด"
        elif len(flags) == 1:
            status = "🟡 เฝ้าระวัง"
        else:
            status = "🟢 พร้อมซ้อม"

        # ค่าบนการ์ดมาจากแถวเก่า (นักกีฬายังไม่ sync นาฬิกา) — บอกวันที่กำกับกันเข้าใจผิดว่าเป็นของวันนี้
        stale_note = ""
        if wellness_date is not None and wellness_date < today:
            stale_note = f" (wellness ล่าสุด {wellness_date.strftime('%d/%m')})"

        emoji, acwr_txt = acwr_status(acwr)
        team_rows.append({
            "นักกีฬา": name,
            "สถานะ": status,
            # อยู่ต้นตาราง (ไม่ใช่ท้ายสุด) เพราะตารางนี้มี 13 คอลัมน์ กว้างเกินจอปกติ —
            # วางไว้ท้ายก่อนหน้านี้ทำให้มองข้ามว่า "ไม่ขึ้น" ทั้งที่จริงมีข้อมูล แค่ต้องเลื่อนดู
            "สถานะซ้อม (Garmin)": _ts_base.title() if _ts_base else "–",
            "ACWR": round(acwr, 2) if pd.notna(acwr) else None,
            "โซน ACWR": f"{emoji} {acwr_txt}",
            "โหลด 7 วัน": (f"{acute:.0f} {unit}" if metric == "training_load"
                          else f"{acute:.1f} {unit}") if pd.notna(acute) else "–",
            "เซสชัน 7 วัน": sessions_7d,
            # วันที่ยังไม่จบ โชว์ระดับ "ตอนนี้" (สดจาก fast wellness) แทนยอดสูงสุดของวันที่ยังไม่เกิด
            "Body Battery": (bb_now if pd.notna(bb_now) else bb) if not day_complete
                            else (bb if pd.notna(bb) else None),
            "Sleep": sleep if pd.notna(sleep) else None,
            "RHR": rhr if pd.notna(rhr) else None,
            "ΔRHR": f"{rhr_delta:+.0f}" if pd.notna(rhr_delta) else "–",
            "HRV คืนล่าสุด": f"{hrv_ms:.0f} ms · {hrv_stat}" if pd.notna(hrv_ms) and hrv_stat else "–",
            "ธงเฝ้าระวัง": (" | ".join(flags) if flags else "—")
                           + ("" if day_complete else " (BB = ระดับตอนนี้ ยังไม่ครบวัน)") + stale_note,
        })

    team_df = pd.DataFrame(team_rows)
    team_summary_columns = [
        "นักกีฬา",
        "สถานะ",
        "ธงเฝ้าระวัง",
        "ACWR",
        "โหลด 7 วัน",
        "Body Battery",
        "Sleep",
        "HRV คืนล่าสุด",
    ]
    st.dataframe(
        team_df[team_summary_columns],
        hide_index=True,
        column_config={
            "นักกีฬา": st.column_config.TextColumn("นักกีฬา", pinned=True),
            "ACWR": st.column_config.NumberColumn("ACWR", format="%.2f",
                                                  help="โหลด 7 วัน ÷ ค่าเฉลี่ยรายสัปดาห์ 28 วัน — ปลอดภัย 0.8–1.3 | "
                                                       "TL = Garmin training_load (รวม cross-training), km = ระยะวิ่ง"),
            "Body Battery": st.column_config.NumberColumn(
                "Body Battery", format="%.0f",
                help="วันที่จบแล้ว = ยอดสูงสุดของวัน | วันนี้ = ระดับ ณ ตอนนี้ "
                     "(อัปเดตทุก 30 นาทีจาก fast wellness sync)"),
            "Sleep": st.column_config.NumberColumn("Sleep", format="%.0f"),
        },
    )

    with st.expander("ดูตัวเลขทีมทั้งหมด", icon=":material/table_view:"):
        st.dataframe(
            team_df,
            hide_index=True,
            column_config={
                "นักกีฬา": st.column_config.TextColumn("นักกีฬา", pinned=True),
                "ACWR": st.column_config.NumberColumn("ACWR", format="%.2f"),
                "Body Battery": st.column_config.NumberColumn("Body Battery", format="%.0f"),
                "Sleep": st.column_config.NumberColumn("Sleep", format="%.0f"),
                "RHR": st.column_config.NumberColumn("RHR", format="%.0f"),
                "สถานะซ้อม (Garmin)": st.column_config.TextColumn(
                    "สถานะซ้อม (Garmin)",
                    help="สถานะที่ Garmin คำนวณเองและขึ้นกับรุ่นนาฬิกา"),
            },
        )

    with st.expander("เกณฑ์ที่ใช้ประเมิน", icon=":material/info:"):
        st.markdown(r"""
**สถานะ:** 🔴 ต้องพัก = ACWR>1.5 หรือมีธงอย่างน้อย 2 ข้อ ·
🟡 เฝ้าระวัง = มีธง 1 ข้อ ·
🟢 พร้อมซ้อม = ไม่มีธง ·
⚪ ไม่มีข้อมูล = ยังไม่มีทั้ง workload และ wellness

**ธงเฝ้าระวัง:** ACWR>1.3 · Body Battery<40 · Sleep<60 ·
RHR สูงกว่าฐาน≥+5 · HRV LOW/UNBALANCED ·
Garmin status Strained/Overreaching/Unproductive

_ACWR ใช้ Garmin training\_load รวม cross-training ถ้านาฬิกาให้
ไม่เช่นนั้นใช้ระยะวิ่ง_
""")


# =====================================================================
# TAB 1: TODAY — เปิดมาเห็นข้อมูลของวันนี้ทันที
# =====================================================================
with tab_today:
    st.header(f"วันนี้ของ {selected_name}")
    st.caption(
        f"{today.strftime('%d/%m/%Y')} · แสดงเฉพาะข้อมูลวันนี้ "
        "ส่วนสถานะโหลดใช้บริบทสะสม 7–28 วันเพื่อไม่ตัดสินจากวันเดียว"
    )

    selected_team = team_df[team_df["นักกีฬา"] == selected_name]
    team_row = selected_team.iloc[0] if not selected_team.empty else None

    today_wellness = load_wellness_data(athlete_id, today.isoformat(), today.isoformat())
    today_activities = load_activity_data(athlete_id, today.isoformat(), today.isoformat())
    if not today_activities.empty:
        today_activities["start_time_local"] = pd.to_datetime(today_activities["start_time_local"])
        today_activities["distance_km"] = today_activities["distance_m"] / 1000

    wellness_keys = ["resting_hr", "sleep_score", "body_battery_high", "hrv_last_night"]
    real_today_wellness = (
        today_wellness[today_wellness[wellness_keys].notna().any(axis=1)]
        if not today_wellness.empty
        else today_wellness
    )
    wellness_today = real_today_wellness.iloc[-1] if not real_today_wellness.empty else None

    if wellness_today is None:
        st.info(
            "ยังไม่มีข้อมูลสุขภาพของวันนี้จากนาฬิกา "
            "หน้าจอจะอัปเดตอัตโนมัติหลัง Garmin sync",
            icon=":material/sync:",
        )
    elif team_row is not None:
        status_text = str(team_row["สถานะ"])
        flag_text = str(team_row["ธงเฝ้าระวัง"])
        message = f"**{status_text}**"
        if flag_text not in ("—", ""):
            message += f" · {flag_text}"
        if status_text.startswith("🔴"):
            st.error(message, icon=":material/warning:")
        elif status_text.startswith("🟡"):
            st.warning(message, icon=":material/visibility:")
        elif status_text.startswith("🟢"):
            st.success(message, icon=":material/check_circle:")
        else:
            st.info(message, icon=":material/info:")

    st.subheader("การฟื้นตัววันนี้")
    if wellness_today is None:
        st.caption("ยังไม่มีค่าของวันนี้")
    else:
        body_battery_now = wellness_today.get("bb_most_recent")
        if pd.isna(body_battery_now):
            body_battery_now = wellness_today.get("body_battery_high")
        with st.container(horizontal=True):
            st.metric(
                "Body Battery ตอนนี้",
                fmt_num(body_battery_now),
                help="ระดับล่าสุดระหว่างวัน ไม่ใช่ค่าสูงสุดของวันที่ยังไม่จบ",
                border=True,
            )
            st.metric("Sleep score", fmt_num(wellness_today.get("sleep_score")), border=True)
            st.metric(
                "Resting HR",
                fmt_num(wellness_today.get("resting_hr"), " bpm"),
                border=True,
            )
            st.metric(
                "HRV คืนล่าสุด",
                fmt_num(wellness_today.get("hrv_last_night"), " ms"),
                delta=fmt_text(wellness_today.get("hrv_status")).replace("_", " "),
                delta_color="off",
                border=True,
            )
            st.metric(
                "ความพร้อมซ้อม",
                fmt_num(wellness_today.get("training_readiness")),
                delta=fmt_text(wellness_today.get("readiness_level")).replace("_", " "),
                delta_color="off",
                border=True,
            )

    st.subheader("กิจกรรมวันนี้")
    if today_activities.empty:
        st.info("ยังไม่มีกิจกรรมที่บันทึกในวันนี้", icon=":material/event_available:")
    else:
        total_distance_today = today_activities["distance_km"].fillna(0).sum()
        total_duration_today = today_activities["duration_sec"].fillna(0).sum()
        total_load_today = today_activities["training_load"].fillna(0).sum()
        with st.container(horizontal=True):
            st.metric("กิจกรรม", f"{len(today_activities)} ครั้ง", border=True)
            st.metric("ระยะทางรวม", f"{total_distance_today:.2f} km", border=True)
            st.metric("เวลารวม", fmt_sec(total_duration_today), border=True)
            st.metric(
                "Training load",
                f"{total_load_today:.0f}" if total_load_today > 0 else "–",
                border=True,
            )

        for _, activity in today_activities.sort_values("start_time_local", ascending=False).iterrows():
            activity_time = (
                activity["start_time_local"].strftime("%H:%M")
                if pd.notna(activity["start_time_local"])
                else "ไม่ทราบเวลา"
            )
            activity_title = fmt_text(
                activity.get("activity_name"),
                fmt_text(activity.get("activity_type"), "กิจกรรม"),
            )
            with st.container(border=True):
                st.markdown(f"**{activity_title}** · {activity_time} น.")
                with st.container(horizontal=True):
                    st.metric("ระยะทาง", fmt_num(activity.get("distance_km"), " km"))
                    st.metric("เวลา", fmt_sec(activity.get("duration_sec")))
                    st.metric(
                        "เพซเฉลี่ย",
                        f"{fmt_pace(activity.get('avg_pace_min_per_km'))} /km"
                        if pd.notna(activity.get("avg_pace_min_per_km"))
                        else "–",
                    )
                    st.metric("HR เฉลี่ย", fmt_num(activity.get("avg_hr"), " bpm"))
                    st.metric("Training load", fmt_num(activity.get("training_load")))

    if team_row is not None:
        st.subheader("บริบทโหลดสะสม")
        with st.container(horizontal=True):
            st.metric("ACWR", fmt_num(team_row["ACWR"]), border=True)
            st.metric("โหลด 7 วัน", team_row["โหลด 7 วัน"], border=True)
            st.metric("จำนวนเซสชัน 7 วัน", str(team_row["เซสชัน 7 วัน"]), border=True)


# =====================================================================
# TAB 3: HEALTH & RECOVERY (นักกีฬาที่เลือก)
# =====================================================================
with tab_health:
    st.header(f"การฟื้นตัว — {selected_name}")
    st.caption(f"ค่าเฉลี่ยและแนวโน้มระหว่าง {start_date.strftime('%d/%m/%Y')}–{end_date.strftime('%d/%m/%Y')}")

    if wellness_df.empty:
        st.info("ไม่มีข้อมูลสุขภาพในช่วงเวลานี้")
    else:
        with st.container(horizontal=True):
            st.metric("Sleep score เฉลี่ย", fmt_num(wellness_df["sleep_score"].mean()), border=True)
            st.metric("Body Battery สูงสุดเฉลี่ย", fmt_num(wellness_df["body_battery_high"].mean()), border=True)
            st.metric("Resting HR เฉลี่ย", fmt_num(wellness_df["resting_hr"].mean(), " bpm"), border=True)
            st.metric("Stress เฉลี่ย", fmt_num(wellness_df["stress_avg"].mean()), border=True)

        fig_health = px.line(wellness_df, x="calendar_date", y=["sleep_score", "body_battery_high"],
                             labels={"value": "คะแนน", "calendar_date": "วันที่", "variable": "Metric"},
                             title="แนวโน้มคะแนนการนอน (Sleep) และ Body Battery",
                             markers=True)
        st.plotly_chart(fig_health, width="stretch")

        fig_stress = px.line(wellness_df, x="calendar_date", y=["stress_avg", "training_readiness"],
                             labels={"value": "ระดับ (Score)", "calendar_date": "วันที่", "variable": "Metric"},
                             title="ระดับความเครียด (Stress) และความพร้อมซ้อม (Readiness)",
                             markers=True)
        st.plotly_chart(fig_stress, width="stretch")

        # --- เมตริกเสริมที่นาฬิกาเก็บ (หายใจ/floors/kcal) ---
        extra = []
        if "avg_waking_respiration" in wellness_df:
            extra.append(("หายใจตอนตื่น", wellness_df["avg_waking_respiration"].mean(), " brpm"))
        if "avg_sleep_respiration" in wellness_df:
            extra.append(("หายใจตอนนอน", wellness_df["avg_sleep_respiration"].mean(), " brpm"))
        if "max_stress" in wellness_df:
            extra.append(("Stress สูงสุด เฉลี่ย", wellness_df["max_stress"].mean(), ""))
        if "floors_ascended" in wellness_df:
            extra.append(("Floors/วัน", wellness_df["floors_ascended"].mean(), ""))
        if "active_kilocalories" in wellness_df:
            extra.append(("Active kcal/วัน", wellness_df["active_kilocalories"].mean(), ""))
        extra = [e for e in extra if pd.notna(e[1])]
        if extra:
            with st.container(horizontal=True):
                for label, val, unit in extra:
                    st.metric(label, fmt_num(val, unit), border=True)

        # --- Respiration trend (ถ้ามี) ---
        if "avg_sleep_respiration" in wellness_df and wellness_df["avg_sleep_respiration"].notna().any():
            fig_resp = px.line(wellness_df, x="calendar_date",
                               y=[c for c in ["avg_sleep_respiration", "avg_waking_respiration"] if c in wellness_df],
                               labels={"value": "ครั้ง/นาที (brpm)", "calendar_date": "วันที่", "variable": "ช่วง"},
                               title="อัตราการหายใจ (Respiration) — นอน vs ตื่น", markers=True)
            st.plotly_chart(fig_resp, width="stretch")

        # --- Garmin Training Readiness & Recovery (เฉพาะนาฬิกาที่ให้ค่า เช่น พี่เก้า) ---
        if "acwr_percent" in wellness_df and wellness_df["acwr_percent"].notna().any():
            st.subheader("ความพร้อมซ้อมและเวลาฟื้นตัวจาก Garmin")
            rr = wellness_df.dropna(subset=["training_readiness"])
            rlast = rr.iloc[-1] if not rr.empty else wellness_df.iloc[-1]
            with st.container(horizontal=True):
                st.metric("Readiness ล่าสุด", fmt_num(rlast.get("training_readiness")),
                          delta=fmt_text(rlast.get("readiness_level")).replace("_", " "),
                          delta_color="off", border=True)
                st.metric("Recovery Time",
                          f"{rlast['recovery_time_hrs']:.0f} ชม." if pd.notna(rlast.get("recovery_time_hrs")) else "–",
                          border=True)
                st.metric("Acute Load (7 วัน)", fmt_num(rlast.get("acute_load")), border=True)
                st.metric("ACWR (Garmin คำนวณเอง)",
                          f"{rlast['acwr_percent']:.0f}%" if pd.notna(rlast.get("acwr_percent")) else "–",
                          help="≈100% = สมดุล | ต่ำ = โหลดน้อยกว่าฐาน | สูง = โหลดพุ่ง", border=True)
            fb = rlast.get("readiness_feedback")
            if isinstance(fb, str) and fb:
                st.caption(f"Garmin feedback ล่าสุด: **{fb.replace('_', ' ')}**")
            fig_ready = px.line(wellness_df, x="calendar_date", y="training_readiness",
                                labels={"training_readiness": "Readiness", "calendar_date": "วันที่"},
                                title="แนวโน้ม Training Readiness (0–100)", markers=True)
            fig_ready.add_hrect(y0=0, y1=50, fillcolor=C_CRIT, opacity=0.08, line_width=0)
            st.plotly_chart(fig_ready, width="stretch")


# =====================================================================
# TAB 4: TRAINING (นักกีฬาที่เลือก) — ACWR + 80/20 + กราฟเดิม
# =====================================================================
with tab_train:
    st.header(f"การซ้อม — {selected_name}")
    st.caption(f"สรุประหว่าง {start_date.strftime('%d/%m/%Y')}–{end_date.strftime('%d/%m/%Y')}")

    if activity_df.empty:
        st.info("ไม่มีข้อมูลการวิ่งในช่วงเวลานี้")
    else:
        runs_df = activity_df[activity_df["activity_type"].isin(RUN_TYPES)]

        total_distance = runs_df["distance_km"].sum()
        avg_pace_raw = runs_df["avg_pace_min_per_km"].mean()
        total_hours = runs_df["duration_sec"].sum() / 3600

        with st.container(horizontal=True):
            st.metric("ระยะวิ่งรวม", f"{total_distance:.2f} km", border=True)
            st.metric("จำนวนครั้งที่วิ่ง", f"{len(runs_df)}", border=True)
            st.metric("เพซเฉลี่ย", f"{fmt_pace(avg_pace_raw)} /km" if pd.notna(avg_pace_raw) else "–", border=True)
            st.metric("เวลาวิ่งรวม", f"{total_hours:.1f} ชม.", border=True)

        # ---------------- ACWR ----------------
        st.subheader("โหลดสะสมและความเสี่ยง (ACWR)")
        acwr_start = start_date - datetime.timedelta(days=56)
        daily_wl, wl_metric, wl_unit = load_daily_workload(athlete_id, acwr_start.isoformat(), end_date.isoformat())
        acwr_df = compute_acwr(daily_wl, end_date)
        acwr_view = acwr_df[(acwr_df["date"] >= pd.Timestamp(start_date)) & acwr_df["acwr"].notna()]
        _src = "Garmin training_load (รวม cross-training)" if wl_metric == "training_load" else "ระยะทางวิ่ง"
        _afmt = "%.0f" if wl_metric == "training_load" else "%.1f"

        if acwr_view.empty:
            st.info("ประวัติยังไม่ถึง 28 วัน — ยังคำนวณ ACWR ไม่ได้")
        else:
            latest_acwr = acwr_view.iloc[-1]
            emoji, txt = acwr_status(latest_acwr["acwr"])
            with st.container(horizontal=True):
                st.metric("ACWR ล่าสุด", f"{latest_acwr['acwr']:.2f}", delta=f"{emoji} {txt}",
                          delta_color="off", border=True)
                st.metric("โหลด 7 วัน (Acute)", f"{latest_acwr['acute']:{_afmt[1:]}} {wl_unit}", border=True)
                st.metric("ฐาน 28 วัน (Chronic)", f"{latest_acwr['chronic']:{_afmt[1:]}} {wl_unit}/สัปดาห์", border=True)

            y_max = max(2.0, float(acwr_view["acwr"].max()) * 1.15)
            fig_acwr = go.Figure()
            bands = [
                (0.0, 0.8, C_NEUTRAL, 0.35, "ต่ำกว่าฐาน"),
                (0.8, 1.3, C_GOOD, 0.12, "ปลอดภัย 0.8–1.3"),
                (1.3, 1.5, C_WARN, 0.15, "เฝ้าระวัง"),
                (1.5, y_max, C_CRIT, 0.12, "เสี่ยงบาดเจ็บ > 1.5"),
            ]
            for y0, y1, color, op, label in bands:
                fig_acwr.add_hrect(y0=y0, y1=y1, fillcolor=color, opacity=op, line_width=0,
                                   annotation_text=label, annotation_position="top left",
                                   annotation_font_size=11, annotation_font_color="#52514e")
            fig_acwr.add_trace(go.Scatter(
                x=acwr_view["date"], y=acwr_view["acwr"], mode="lines+markers",
                line=dict(color=C_BLUE, width=2), marker=dict(size=6), name="ACWR",
                hovertemplate="%{x|%d %b}<br>ACWR %{y:.2f}<extra></extra>",
            ))
            fig_acwr.update_layout(
                title=f"Acute:Chronic Workload Ratio (จาก {_src})",
                yaxis=dict(title="ACWR", range=[0, y_max]),
                xaxis=dict(title="วันที่"),
                showlegend=False, hovermode="x unified",
            )
            st.plotly_chart(fig_acwr, width="stretch")
            st.caption(f"ตัวแทนโหลด: {_src} — แตะโซนแดงเมื่อไหร่ = สัญญาณสั่งพัก/ลดโหลดทันที")

        # ---------------- 80/20 (จากเวลาในโซน HR จริงของนาฬิกา) ----------------
        st.subheader("สัดส่วนความหนักการซ้อม (กฎ 80/20)")
        zone_cols = ["hr_zone1_sec", "hr_zone2_sec", "hr_zone3_sec", "hr_zone4_sec", "hr_zone5_sec"]
        have_zone_cols = set(zone_cols).issubset(activity_df.columns)
        zdf = activity_df[activity_df[zone_cols].notna().any(axis=1)] if have_zone_cols else activity_df.iloc[0:0]

        if not zdf.empty:
            z = zdf[zone_cols].fillna(0).sum()
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
                          delta_color="normal" if easy_pct >= 80 else "inverse", border=True)
                for name in INTENSITY_ORDER:
                    st.markdown(f"- **{name}** — {buckets[name]:.0f} นาที")
                st.caption(f"⭐ จาก **เวลาในโซน HR จริง** ของ {len(zdf)} กิจกรรม (รวม cross-training) — "
                           "แม่นกว่าเฉลี่ยทั้งเซสชัน เพราะนาฬิกาเก็บวินาทีต่อโซนจริง")
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
                              delta_color="normal" if easy_pct >= 80 else "inverse", border=True)
                    for _, r in dist.iterrows():
                        st.markdown(f"- **{r['intensity']}** — {r['minutes']:.0f} นาที · {int(r['sessions'])} เซสชัน")
                    st.caption(f"จำแนกจาก avg HR ต่อเซสชันเทียบ LTHR {lthr} bpm ({lthr_source})")

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
            st.subheader("Running dynamics เฉลี่ย")
            with st.container(horizontal=True):
                for col, (label, unit, fmt) in dyn_cols.items():
                    val = pd.to_numeric(run_dyn[col], errors="coerce").mean() if col in run_dyn else float("nan")
                    st.metric(label, (fmt % val + f" {unit}") if pd.notna(val) else "–", border=True)
            st.caption("จากเซสชันวิ่งที่นาฬิกาเก็บ running dynamics — GCT ต่ำ/ratio ต่ำ = ฟอร์มประหยัดแรง")

        # ---------------- กราฟเดิม ----------------
        fig_dist = px.bar(activity_df, x="start_time_local", y="distance_km",
                          title="ระยะทางของแต่ละกิจกรรม",
                          labels={"distance_km": "ระยะทาง (km)", "start_time_local": "วันที่และเวลา"})
        fig_dist.update_traces(marker_color="rgb(55, 83, 109)")
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
with tab_progress:
    st.header(f"ความก้าวหน้า — {selected_name}")
    st.caption(
        f"แนวโน้มระหว่าง {start_date.strftime('%d/%m/%Y')}–{end_date.strftime('%d/%m/%Y')} · "
        "ใช้ค่าจาก Garmin ดูทิศทาง ส่วนค่าสัมบูรณ์ให้ยึดผลเทสจริง"
    )

    # ---------------- VO2max trend ----------------
    vo2 = (wellness_df.dropna(subset=["vo2max_trend"])
           if "vo2max_trend" in wellness_df else wellness_df.iloc[0:0])
    # Fitness Age อ่านจาก wellness_df เต็ม ไม่ใช่จาก vo2 ที่กรอง vo2max_trend มาแล้ว —
    # คนละ endpoint กัน (extras เขียน fitness_age ให้วันล่าสุดวันเดียว ส่วน vo2max_trend
    # ขึ้นเฉพาะวันที่มีวิ่ง outdoor) ถ้าอ่านจาก vo2 ค่าจะหายทุกครั้งที่วันล่าสุดไม่ได้วิ่ง
    _fit_age = (wellness_df["fitness_age"].dropna()
                if "fitness_age" in wellness_df else pd.Series(dtype=float))
    if not vo2.empty:
        first_v, last_v = vo2["vo2max_trend"].iloc[0], vo2["vo2max_trend"].iloc[-1]
        with st.container(horizontal=True):
            st.metric("VO2max ล่าสุด (Garmin)", f"{last_v:.1f}",
                      delta=f"{last_v - first_v:+.1f} เทียบต้นช่วง", border=True)
            if not _fit_age.empty:
                st.metric("Fitness Age", fmt_num(_fit_age.iloc[-1]), border=True)
        fig_vo2 = px.line(vo2, x="calendar_date", y="vo2max_trend", markers=True,
                          labels={"vo2max_trend": "VO2max", "calendar_date": "วันที่"},
                          title="แนวโน้ม VO2max (ค่าประเมินรายวันของ Garmin)")
        st.plotly_chart(fig_vo2, width="stretch")
    else:
        st.info("ไม่มีข้อมูล VO2max ในช่วงที่เลือก (นาฬิกาอัปเดตเฉพาะวันที่มีวิ่ง GPS)")

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
        for col, label, color in [("time_5k_sec", "5K", C_BLUE), ("time_10k_sec", "10K", C_GREEN)]:
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
            fig_end = px.line(eh, x="calendar_date", y="endurance_score", markers=True,
                              labels={"endurance_score": "Endurance Score", "calendar_date": "วันที่"},
                              title="แนวโน้ม Endurance Score (ความอึดสะสม)")
            st.plotly_chart(fig_end, width="stretch")
    # ---------------- Personal records ----------------
    st.subheader("สถิติส่วนตัวจาก Garmin")
    prs = load_personal_records(athlete_id)
    # typeId ที่ค่าเป็น "เวลา (วินาที)" / "ระยะไกล (เมตร→กม.)" / "ไต่สะสม (เมตร)" / "จำนวนก้าว"
    _PR_TIME_IDS = {1, 2, 3, 4, 5, 6}
    _PR_KM_IDS = {7, 8}
    _PR_METER_IDS = {9}
    _PR_STEP_IDS = {12, 13, 14}
    if prs.empty:
        st.info("ไม่มีข้อมูล PR")
    else:
        rows = []
        for _, pr in prs.iterrows():
            tid, val = int(pr["record_type_id"]), pr["value"]
            if tid in _PR_TIME_IDS:
                shown = fmt_sec(val)
            elif tid in _PR_KM_IDS:
                shown = f"{val / 1000:.2f} km" if pd.notna(val) else "–"
            elif tid in _PR_METER_IDS:
                shown = f"{val:,.0f} m" if pd.notna(val) else "–"
            elif tid in _PR_STEP_IDS:
                shown = f"{val:,.0f} ก้าว" if pd.notna(val) else "–"
            else:
                shown = f"{val:,.0f}" if pd.notna(val) else "–"
            # ห้ามใช้ `label or default` — record_label ที่ว่างมาเป็น NaN ซึ่ง truthy ใน Python
            label_val = pr["record_label"]
            label_txt = label_val if (isinstance(label_val, str) and label_val) else f"ประเภท {tid}"
            date_val = pr["achieved_date"]
            rows.append({
                "รายการ": label_txt,
                "สถิติ": shown,
                "ทำได้เมื่อ": str(date_val)[:10] if isinstance(date_val, str) and date_val else "–",
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True)
        st.caption("PR นับตามที่นาฬิกาบันทึกอัตโนมัติ — ระยะที่ GPS วัดไม่ถึงเกณฑ์ (เช่น 4.98 กม.) จะไม่ถูกนับเป็น 5K")


# =====================================================================
# TAB 6: SPLITS — เจาะลึกรายเซสชัน
# =====================================================================
with tab_splits:
    st.header(f"รายละเอียดเซสชัน — {selected_name}")
    st.caption(f"เลือกกิจกรรมระหว่าง {start_date.strftime('%d/%m/%Y')}–{end_date.strftime('%d/%m/%Y')}")

    if activity_df.empty:
        st.info("ไม่มีกิจกรรมในช่วงเวลานี้")
    else:
        candidates = activity_df[activity_df["distance_m"] > 500].sort_values("start_time_local", ascending=False)
        if candidates.empty:
            st.info("ไม่มีกิจกรรมที่มีระยะทางพอสำหรับดู splits — กิจกรรมระยะ 0 เช่น "
                    "indoor cardio หรือ HIIT ไม่มี splits โดยตั้งใจ")
        else:
            label_map = {
                int(r["activity_id"]): (f"{r['start_time_local']:%d %b %Y %H:%M} · "
                                        f"{fmt_text(r['activity_name'], fmt_text(r['activity_type'], 'กิจกรรม'))} · "
                                        f"{r['distance_km']:.2f} km")
                for _, r in candidates.iterrows()
            }
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

            zc = ["hr_zone1_sec", "hr_zone2_sec", "hr_zone3_sec", "hr_zone4_sec", "hr_zone5_sec"]
            if set(zc).issubset(activity_df.columns) and arow[zc].notna().any():
                zvals = [float(arow.get(c)) / 60 if pd.notna(arow.get(c)) else 0.0 for c in zc]
                if sum(zvals) > 0:
                    zbar = pd.DataFrame({"โซน": ["Z1", "Z2", "Z3", "Z4", "Z5"], "นาที": zvals})
                    fig_z = px.bar(zbar, x="โซน", y="นาที", color="โซน",
                                   title="เวลาในโซน HR ของเซสชันนี้ (นาที)",
                                   color_discrete_sequence=[C_GREEN, "#7ac043", C_AMBER, "#e8743b", C_RED])
                    fig_z.update_layout(showlegend=False)
                    st.plotly_chart(fig_z, width="stretch")

            splits = load_splits(chosen_id)
            splits = splits[splits["distance_m"] >= 100]

            if splits.empty:
                st.info("ยังไม่ได้ดึง splits — fast sync จะลองเติมให้อัตโนมัติในรอบถัดไป "
                        "และ full sync 21:00 จะตรวจซ้ำ")
            else:
                # --- วิเคราะห์ครึ่งแรก vs ครึ่งหลัง (จับอาการแผ่วปลาย) ---
                if len(splits) >= 2:
                    half = len(splits) // 2
                    h1, h2 = splits.iloc[:half], splits.iloc[half:]

                    def _weighted_pace(part):
                        km = part["distance_m"].sum() / 1000
                        return (part["duration_sec"].sum() / 60) / km if km > 0 else float("nan")

                    p1, p2 = _weighted_pace(h1), _weighted_pace(h2)
                    hr1 = (h1["avg_hr"] * h1["duration_sec"]).sum() / h1["duration_sec"].sum() if h1["avg_hr"].notna().any() else float("nan")
                    hr2 = (h2["avg_hr"] * h2["duration_sec"]).sum() / h2["duration_sec"].sum() if h2["avg_hr"].notna().any() else float("nan")

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
                    hovertemplate="กม.ที่ %{x} (%{customdata[1]} กม.)<br>เพซ %{customdata[0]} /กม.<extra></extra>",
                ), row=1, col=1)
                if splits["avg_hr"].notna().any():
                    fig_sp.add_trace(go.Scatter(
                        x=x_labels, y=splits["avg_hr"], mode="lines+markers",
                        line=dict(color=C_RED, width=2), marker=dict(size=8), name="HR เฉลี่ย",
                        hovertemplate="กม.ที่ %{x}<br>HR %{y:.0f} bpm<extra></extra>",
                    ), row=2, col=1)

                pace_clean = splits["avg_pace_min_km"].dropna()
                pace_axis_kwargs = {}
                if not pace_clean.empty:
                    tickvals, ticktext = pace_axis_ticks(pace_clean)
                    pace_axis_kwargs = {"tickvals": tickvals, "ticktext": ticktext}
                fig_sp.update_yaxes(title_text="เพซ (นาที/กม.)", autorange="reversed",
                                    row=1, col=1, **pace_axis_kwargs)
                fig_sp.update_yaxes(title_text="HR (bpm)", row=2, col=1)
                fig_sp.update_xaxes(title_text="กิโลเมตรที่", row=2, col=1)
                fig_sp.update_layout(title="เพซและ HR รายกิโลเมตร (เพซ: ยิ่งสูง = ยิ่งเร็ว)",
                                     showlegend=True, hovermode="x unified",
                                     legend=dict(orientation="h", yanchor="bottom", y=1.02))
                st.plotly_chart(fig_sp, width="stretch")

                # --- กราฟ Cadence + Power + Elevation รายกิโลเมตร ---
                extra_rows = []
                if splits["avg_cadence"].notna().any():
                    extra_rows.append(("avg_cadence", "Cadence (spm)", C_GREEN))
                if "avg_power" in splits and splits["avg_power"].notna().any():
                    extra_rows.append(("avg_power", "Power (W)", C_BLUE))
                if splits["elevation_gain_m"].notna().any():
                    extra_rows.append(("elevation_gain_m", "Elevation Gain (m)", C_AMBER))

                if extra_rows:
                    fig_extra = make_subplots(
                        rows=len(extra_rows), cols=1, shared_xaxes=True,
                        vertical_spacing=0.12,
                        subplot_titles=[t for _, t, _ in extra_rows])
                    for i, (col, title, color) in enumerate(extra_rows, 1):
                        fig_extra.add_trace(go.Bar(
                            x=x_labels, y=splits[col], name=title,
                            marker_color=color,
                            hovertemplate=f"กม.ที่ %{{x}}<br>{title}: %{{y:.0f}}<extra></extra>",
                        ), row=i, col=1)
                    fig_extra.update_xaxes(title_text="กิโลเมตรที่", row=len(extra_rows), col=1)
                    fig_extra.update_layout(showlegend=False, title="Cadence และ Elevation รายกิโลเมตร")
                    st.plotly_chart(fig_extra, width="stretch")

                # --- ตาราง splits รายรอบ เต็ม (แสดงตรง ไม่ซ่อนใน expander) ---
                st.subheader("📊 ตาราง Splits (ผลต่อรอบ)")
                num0 = st.column_config.NumberColumn(format="%.0f")
                table_data = {
                    "กม.ที่": splits["split_num"].astype(int),
                    "ระยะ (km)": dist_km,
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
                _add("avg_stride_length_cm", "Stride (cm)")
                _add("ground_contact_time_ms", "GCT (ms)")
                _add("vertical_oscillation_cm", "Vert Osc (cm)",
                     st.column_config.NumberColumn(format="%.1f"))
                table_data["เนิน (m)"] = splits["elevation_gain_m"]
                cfg["เนิน (m)"] = num0
                _add("intensity_type", "ประเภท", None)  # text

                st.dataframe(pd.DataFrame(table_data), hide_index=True, column_config=cfg)


auto_refresh_dashboard()
