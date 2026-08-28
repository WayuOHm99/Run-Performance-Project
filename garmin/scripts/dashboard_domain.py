"""การคำนวณและการจัดรูปค่าของ Dashboard — ไม่มี Streamlit ไม่มี HTML

แยกออกมาเพื่อให้แต่ละหน้าและเทส import ได้ตรง ๆ เดิมเทส 12 ไฟล์ต้อง
``ast.parse`` แล้ว ``exec`` ทีละฟังก์ชัน เพราะ import ทั้งไฟล์จะไปรัน
สคริปต์ Streamlit ทั้งหน้า
"""

from zoneinfo import ZoneInfo
import datetime
import math

import pandas as pd


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

# ขอบเขตใช้งานของทีมตาม %LTHR (Friel): เป็น coach heuristic สำหรับสรุปภาพรวม
# ไม่ใช่เส้นแบ่ง physiological domain ที่ผ่านการวัด LT1/LT2 ของนักกีฬาแต่ละคน
EASY_MAX_PCT = 0.89

GRAY_MAX_PCT = 0.94

# --- pace-HR trend ของรันเบา (สูตรเดิมเรียก EF) ---
# ค่านี้คือความเร็ว/HR จากรันทั่วไป ไม่ใช่ running economy (ซึ่งต้องวัด oxygen/energy cost)
# และไม่ใช่ readiness test เพราะไม่ได้ตรึงเพซ เส้นทาง ความชัน อากาศ เวลา และการหยุดพัก
# จึงเก็บไว้เป็นแนวโน้มประกอบเท่านั้น ห้ามใช้สั่งพัก/เพิ่มโหลดหรือจัดโซนแดง-เหลือง-เขียว
EF_MIN_DISTANCE_M = 3000.0

EF_RECENT_DAYS = 3

EF_BASELINE_DAYS = 28

EF_BASELINE_MIN_DAYS = 5

EF_STALE_DAYS = 14

# HRV 7 คืนเทียบฐานของตัวเองเป็นแนวโน้มประกอบ ไม่ใช่คะแนนความสดหรือคำสั่งซ้อม
# ใช้ hrv_last_night สองหน้าต่างที่ไม่ซ้อนกัน แทนการเทียบ Garmin moving-average ที่ซ้อนกัน
# และห้ามนับซ้ำกับ Garmin HRV Status/Training Readiness
HRV_TREND_CURRENT_DAYS = 7

HRV_TREND_MIN_CURRENT_DAYS = 5

HRV_TREND_BASELINE_DAYS = 28

HRV_TREND_MIN_BASELINE_DAYS = 14   # ฐานสั้นกว่าครึ่งเดือนตอบไม่ได้

HRV_TREND_STALE_DAYS = 3

INTENSITY_ORDER = ["เบา (Z1–2)", "กลาง (Z3)", "หนัก (Z4–5)"]

# --- HELPERS ---
def fmt_num(value, suffix="", decimals=None):
    """Format a metric without showing a misleading ``.0`` for integer values."""
    if pd.isna(value):
        return "–"
    number = float(value)
    if decimals is None:
        decimals = 0 if number.is_integer() else 1
    return f"{number:.{decimals}f}{suffix}"

def fmt_signed_delta(value, suffix="", decimals=0):
    """Format a signed delta while normalizing rounded ``-0`` to plain zero."""
    if pd.isna(value):
        return "–"
    rounded = round(float(value), decimals)
    if rounded == 0:
        return f"{0:.{decimals}f}{suffix}"
    return f"{rounded:+.{decimals}f}{suffix}"

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

def hrv_trend_summary(wellness_rows, today_date):
    """สรุป HRV สองหน้าต่างไม่ซ้อน พร้อมจำนวนคืนที่มีข้อมูลจริง."""
    result = {
        "pct": float("nan"), "current_n": 0, "baseline_n": 0,
        "current_median": float("nan"), "baseline_median": float("nan"),
    }
    if wellness_rows is None or len(wellness_rows) == 0:
        return result
    if "hrv_last_night" not in wellness_rows or "calendar_date" not in wellness_rows:
        return result
    frame = wellness_rows[["calendar_date", "hrv_last_night"]].copy()
    frame["hrv_last_night"] = pd.to_numeric(frame["hrv_last_night"], errors="coerce")
    frame["calendar_date"] = pd.to_datetime(frame["calendar_date"], errors="coerce")
    frame = frame.dropna().sort_values("calendar_date")
    if frame.empty:
        return result

    anchor = frame["calendar_date"].iloc[-1]
    if (pd.Timestamp(today_date) - anchor).days > HRV_TREND_STALE_DAYS:
        return result
    current_start = anchor - pd.Timedelta(days=HRV_TREND_CURRENT_DAYS - 1)
    current = frame[
        (frame["calendar_date"] >= current_start)
        & (frame["calendar_date"] <= anchor)
    ]["hrv_last_night"]
    baseline = frame[
        (frame["calendar_date"] < current_start)
        & (frame["calendar_date"] >= current_start - pd.Timedelta(days=HRV_TREND_BASELINE_DAYS))
    ]["hrv_last_night"]
    result.update({
        "current_n": len(current),
        "baseline_n": len(baseline),
        "current_median": current.median(),
        "baseline_median": baseline.median(),
    })
    if (len(current) < HRV_TREND_MIN_CURRENT_DAYS
            or len(baseline) < HRV_TREND_MIN_BASELINE_DAYS):
        return result
    if (pd.isna(result["current_median"]) or pd.isna(result["baseline_median"])
            or result["current_median"] <= 0 or result["baseline_median"] <= 0):
        return result
    result["pct"] = (
        result["current_median"] / result["baseline_median"] - 1
    ) * 100.0
    return result

def hrv_trend_pct(wellness_rows, today_date):
    """% ที่ median HRV 7 คืนล่าสุดต่างจาก median 28 คืนก่อนหน้าแบบไม่ซ้อน

    ค่านี้ใช้ดูทิศทางของคนเดิมเท่านั้น ไม่ใช่คะแนน readiness และไม่สร้าง cutoff เอง
    ใช้ค่ารายคืนที่ Garmin ส่ง ไม่ใช้ ``hrv_weekly_avg`` ซึ่งจุดติดกันซ้อนข้อมูลกัน

    คืน NaN เมื่อหลักฐานไม่พอ: ไม่มีค่า, ฐานน้อยกว่าครึ่งเดือน, หรือค่าล่าสุดเก่าเกิน
    ``HRV_TREND_STALE_DAYS`` — ค่าเก่าต้องไม่ถูกรายงานเป็นความสดวันนี้
    """
    return hrv_trend_summary(wellness_rows, today_date)["pct"]

def hrv_trend_status(pct):
    """ให้ HRV trend ใช้สีน้ำเงินเชิงข้อมูล ไม่แปลงเป็นสถานะพร้อม/ไม่พร้อม"""
    if pd.isna(pct):
        return "unknown", "ข้อมูลไม่พอ"
    return "gain", "แนวโน้มประกอบ"

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

def load_volume_display(acute, metric, unit):
    """ปริมาณ 7 วันแบบดิบพร้อมหน่วยของมันเอง — **อ่านได้เฉพาะเทียบกับตัวเอง**

    หน่วยขึ้นกับรุ่นนาฬิกา: ได้ Garmin ``training_load`` (TL) ถ้านาฬิกาให้ ไม่งั้น
    fallback เป็นระยะวิ่ง (km) วัดจริง 27 ส.ค. 69 ทีมนี้มีทั้งสองแบบพร้อมกัน
    (32.7 km · 92.6 km · 323 TL) จึงห้ามเอาตัวเลขดิบของสองคนมาเทียบกัน
    ปริมาณนี้ใช้เทียบตามเวลาในคนเดิมเท่านั้น ไม่ใช้จัดอันดับข้ามคน
    """
    if pd.isna(acute):
        return "–"
    digits = 0 if metric == "training_load" else 1
    return f"{acute:.{digits}f} {unit}"

def load_session_scope(metric):
    """"เซสชัน 7 วัน" ของคนนี้นับอะไรบ้าง — คนละนิยามตามที่มาของโหลด

    โหลดจาก ``training_load`` นับทุกกิจกรรม (รวม HIIT/เวท/มวย) ส่วนโหลดที่ fallback
    เป็นระยะวิ่งนับเฉพาะการวิ่ง สองค่านี้เคยวางเรียงกันโดยไม่มีอะไรบอกว่าต่างกัน
    """
    return "ทุกกิจกรรม" if metric == "training_load" else "วิ่ง"

def load_context_line(volume, rolling_28d, sessions, scope):
    """แสดงโหลด 7 วันและค่าเฉลี่ย 28 วันแยกกัน โดยไม่สร้าง ACWR กลับมาในชื่อใหม่"""
    baseline = ("ยังไม่มีค่าเฉลี่ย 28 วัน" if rolling_28d in ("–", "-", "", None)
                else f"เฉลี่ย 28 วัน {rolling_28d}")
    return f"{volume} · {baseline} · {sessions} เซสชัน ({scope})"

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
    """pace-HR รายวันจากรายการวิ่งเบา (HR <= 89% LTHR; รวมระยะ >= 3 กม.).

    Garmin อาจบันทึก warm-up / งานหลัก / cool-down เป็นหลาย activity ในวันเดียวกัน
    จึงรวมรายการเบาตามวันก่อนคำนวณ เพื่อไม่ให้วันเดียวมีน้ำหนักเท่าหลายวัน ค่า HR
    รายวันถ่วงด้วยเวลา และไม่มี LTHR = ไม่เดาเส้นแบ่ง easy.
    """
    columns = ["date", "ef"]
    if runs is None or runs.empty or not lthr:
        return pd.DataFrame(columns=columns)
    easy_max_hr = lthr * EASY_MAX_PCT
    rows = []
    for _, run in runs.iterrows():
        heart_rate = pd.to_numeric(run.get("avg_hr"), errors="coerce")
        distance = pd.to_numeric(run.get("distance_m"), errors="coerce")
        duration = pd.to_numeric(run.get("duration_sec"), errors="coerce")
        if pd.isna(heart_rate) or heart_rate > easy_max_hr:
            continue
        if (pd.isna(distance) or pd.isna(duration)
                or distance <= 0 or duration <= 0 or heart_rate <= 0):
            continue
        rows.append({
            "date": pd.Timestamp(run["date"]).normalize(),
            "distance_m": distance,
            "duration_sec": duration,
            "hr_seconds": heart_rate * duration,
        })
    if not rows:
        return pd.DataFrame(columns=columns)
    daily = pd.DataFrame(rows).groupby("date", as_index=False).sum(numeric_only=True)
    daily = daily[daily["distance_m"] >= EF_MIN_DISTANCE_M].copy()
    if daily.empty:
        return pd.DataFrame(columns=columns)
    daily["avg_hr"] = daily["hr_seconds"] / daily["duration_sec"]
    daily["ef"] = daily.apply(
        lambda row: efficiency_factor(
            row["distance_m"], row["duration_sec"], row["avg_hr"]
        ),
        axis=1,
    )
    return daily[columns].dropna(subset=["ef"]).sort_values("date").reset_index(drop=True)

def efficiency_windows(easy_ef, today):
    """คืนหน้าต่าง pace-HR ปัจจุบัน/ฐานที่ผ่านเกณฑ์เดียวกัน หรือ ``None``.

    จุดเดียวนี้เป็นแหล่งข้อมูลให้ทั้งเปอร์เซ็นต์ การ์ด และเส้นฐานในกราฟ เพื่อไม่ให้
    แต่ละส่วนเผลอใช้ฐานคนละช่วงเวลา.
    """
    if easy_ef is None or easy_ef.empty:
        return None
    frame = easy_ef.sort_values("date")
    anchor = frame["date"].iloc[-1]
    if (pd.Timestamp(today) - anchor).days > EF_STALE_DAYS:
        return None
    recent = frame.tail(EF_RECENT_DAYS)
    if len(recent) < EF_RECENT_DAYS:
        return None
    # 3 วันล่าสุดต้องอยู่ใกล้กันพอจะเรียกว่า "ตอนนี้" — ไม่งั้นวันวิ่งเดือนก่อนจะถูกดึงมา
    # เฉลี่ยรวมกับรันเมื่อวานแล้วรายงานเป็นความสดปัจจุบัน
    if (anchor - recent["date"].iloc[0]).days > EF_STALE_DAYS:
        return None
    recent_start = recent["date"].iloc[0]
    baseline = frame[
        (frame["date"] < recent_start)
        & (frame["date"] >= recent_start - pd.Timedelta(days=EF_BASELINE_DAYS))
    ]
    if len(baseline) < EF_BASELINE_MIN_DAYS:
        return None
    baseline_median = baseline["ef"].median()
    if pd.isna(baseline_median) or baseline_median <= 0:
        return None
    return {
        "recent": recent,
        "baseline": baseline,
        "recent_median": recent["ef"].median(),
        "baseline_median": baseline_median,
    }

def efficiency_change_pct(easy_ef, today):
    """% ที่ median ของ 3 วันวิ่ง easy ล่าสุดต่างจากฐาน 28 วันแบบไม่ซ้อน."""
    windows = efficiency_windows(easy_ef, today)
    if windows is None:
        return float("nan")
    return (windows["recent_median"] / windows["baseline_median"] - 1) * 100.0

def efficiency_recent_value(easy_ef, today):
    """median pace-HR ของ 3 วันล่าสุด — คืน NaN เมื่อข้อมูลไม่ผ่านเกณฑ์เดียวกัน

    ใช้เงื่อนไขข้อมูลชุดเดียวกับ trend เพื่อไม่ให้ตัวเลขเก่าปรากฏเหมือนเป็นค่าปัจจุบัน
    """
    windows = efficiency_windows(easy_ef, today)
    return float("nan") if windows is None else windows["recent_median"]

def efficiency_status(pct):
    """แสดง pace-HR เป็นข้อมูลประกอบสีน้ำเงิน ไม่แปลงเป็น readiness status"""
    if pd.isna(pct):
        return "⚪", "ข้อมูลไม่พอ"
    return "🔵", "แนวโน้มประกอบ"

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
    """จำแนกจาก avg HR ตาม working zones ของทีม; เป็น coach heuristic แบบหยาบ"""
    if pd.isna(avg_hr) or not lthr:
        return None
    ratio = avg_hr / lthr
    if ratio <= EASY_MAX_PCT:
        return INTENSITY_ORDER[0]
    if ratio < GRAY_MAX_PCT:
        return INTENSITY_ORDER[1]
    return INTENSITY_ORDER[2]

def team_status(flags, has_workload, wellness_core_count,
                has_any_wellness=None):
    """สรุปสิ่งที่อุปกรณ์ตรวจพบ โดยไม่ออกคำสั่งพร้อมซ้อม/ต้องพักอัตโนมัติ

    ``flags`` อาจเป็นค่าที่สัมพันธ์หรือเป็นองค์ประกอบของ Garmin composite เดียวกัน
    จำนวนธงจึงไม่ใช่จำนวนหลักฐานอิสระ และ pace-HR trend ไม่ได้เป็น readiness test
    """
    flags = list(flags or [])
    if has_any_wellness is None:
        has_any_wellness = wellness_core_count > 0
    if not has_workload and not has_any_wellness:
        return "⚪ ไม่มีข้อมูล"
    if flags:
        return "🟡 ควรทบทวนก่อนซ้อม"
    if not has_workload or wellness_core_count < 3:
        return "⚪ ข้อมูลไม่พอ"
    return "🟢 ไม่พบสัญญาณเตือนจากอุปกรณ์"

# team_status() คืนสตริงเดียว "อีโมจิ + ข้อความ" เพราะแท็บ "วันนี้" ยังใช้รูปแบบนั้นอยู่
# การ์ดบนแท็บทีมต้องการรูปทรงวาดแทนอีโมจิ (อีโมจิเรนเดอร์ไม่เหมือนกันข้ามเครื่องและ
# หายตอนพิมพ์ขาวดำ) จึงแยกออกเป็น (คีย์, ข้อความ) ที่นี่ที่เดียว แทนการ parse ซ้ำหลายที่
STATUS_SHAPES = {"🔴": "rest", "🟡": "watch", "🟢": "ready",
                 "🔵": "gain", "⚪": "unknown"}

def status_parts(status):
    """แยกสัญลักษณ์นำหน้าออกเป็นคีย์รูปทรงและข้อความ"""
    text = str(status or "").strip()
    for emoji, key in STATUS_SHAPES.items():
        if text.startswith(emoji):
            return key, text[len(emoji):].strip()
    return "unknown", text

# ลำดับการ์ดบนแท็บทีม — "ข้อมูลไม่พอ" มาก่อน "ไม่พบสัญญาณ" เพราะช่องว่างของหลักฐาน
# ต้องถูกเห็น ไม่ใช่ถูกกลบไว้ท้ายรายการหลังคนที่ไม่มีอะไรต้องทำ
TEAM_URGENCY_ORDER = ("rest", "watch", "unknown", "ready")

def team_urgency_rank(status):
    """ลำดับความเร่งด่วนของสถานะ — คนที่ต้องตัดสินใจก่อนได้เลขน้อยสุด"""
    key, _ = status_parts(status)
    if key in TEAM_URGENCY_ORDER:
        return TEAM_URGENCY_ORDER.index(key)
    return len(TEAM_URGENCY_ORDER)

def _num_text(value, digits=0):
    return "–" if value is None or pd.isna(value) else f"{value:.{digits}f}"

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

def hr_zone_coverage(activity_rows, zone_columns):
    """เทียบวินาทีที่ Garmin จัด HR zone ได้กับ ``duration_sec`` ที่ Garmin ส่ง.

    แถวที่ไม่มี zone seconds ยังอยู่ในตัวหาร และจำกัดเวลาที่จัดโซนได้ไม่ให้เกิน
    duration ของแต่ละกิจกรรม เพื่อไม่รายงาน coverage เกิน 100% เมื่อข้อมูลต้นทางคลาดกัน.
    """
    empty = {
        "duration_sec": 0.0, "classified_sec": 0.0,
        "unclassified_sec": 0.0, "coverage_pct": float("nan"),
        "activity_n": 0, "zoned_activity_n": 0, "excess_zone_sec": 0.0,
    }
    if (activity_rows is None or activity_rows.empty
            or "duration_sec" not in activity_rows
            or not set(zone_columns).issubset(activity_rows.columns)):
        return empty
    duration = pd.to_numeric(activity_rows["duration_sec"], errors="coerce")
    valid = duration.notna() & duration.gt(0)
    if not valid.any():
        return empty
    duration = duration.loc[valid]
    zones = activity_rows.loc[valid, list(zone_columns)].apply(
        pd.to_numeric, errors="coerce"
    ).clip(lower=0).fillna(0)
    zone_total = zones.sum(axis=1)
    classified = pd.concat([zone_total, duration], axis=1).min(axis=1)
    total_duration = float(duration.sum())
    classified_sec = float(classified.sum())
    return {
        "duration_sec": total_duration,
        "classified_sec": classified_sec,
        "unclassified_sec": max(total_duration - classified_sec, 0.0),
        "coverage_pct": classified_sec / total_duration * 100.0,
        "activity_n": int(valid.sum()),
        "zoned_activity_n": int(zone_total.gt(0).sum()),
        "excess_zone_sec": float((zone_total - duration).clip(lower=0).sum()),
    }

def intensity_minutes(activity_rows, zone_columns):
    """รวมเวลาในโซน HR เป็นสามถัง เบา/กลาง/หนัก (นาที)

    คืน ``None`` เมื่อไม่มีวินาทีในโซนเลย — ผู้เรียกจะได้ไม่ต้องวาดวงเปล่า
    """
    rows = usable_hr_zone_rows(activity_rows, zone_columns)
    if rows is None or rows.empty:
        return None
    zones = rows[list(zone_columns)].apply(pd.to_numeric, errors="coerce")
    zones = zones.clip(lower=0).fillna(0).sum()
    buckets = {
        INTENSITY_ORDER[0]: (zones[zone_columns[0]] + zones[zone_columns[1]]) / 60,
        INTENSITY_ORDER[1]: zones[zone_columns[2]] / 60,
        INTENSITY_ORDER[2]: (zones[zone_columns[3]] + zones[zone_columns[4]]) / 60,
    }
    return buckets if sum(buckets.values()) > 0 else None

def easy_share_pct(buckets):
    """สัดส่วนเวลาเบาเป็น % — คืน NaN เมื่อไม่มีเวลาเลย แทนการคืน 0 ที่อ่านว่า "หนักหมด" """
    if not buckets:
        return float("nan")
    total = sum(buckets.values())
    return (buckets[INTENSITY_ORDER[0]] / total * 100) if total > 0 else float("nan")

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

def prepare_session_candidates(activity_df):
    """กิจกรรมทุกเซสชันที่ Garmin บันทึก สำหรับหน้าเจาะลึก

    ห้ามกรองด้วยระยะขั้นต่ำ: warm-up/cool-down และ interval ของ Tong มีทั้งเซสชัน
    สั้นกว่า 500 ม. แต่มี splits ที่ถูกต้องครบถ้วน ส่วนกิจกรรมระยะ 0 ก็ยังมีตัวเลข
    เวลา/HR/Training Load ที่ควรดูได้ แม้ไม่มี splits ก็ตาม
    """
    return activity_df.sort_values("start_time_local", ascending=False)

def get_lthr(slug, athlete_id):
    """คืน (LTHR, ที่มา) เฉพาะค่าที่มีผลเทส/แหล่งที่ระบุไว้ ไม่เดาจาก HRmax"""
    if slug in LTHR_BY_SLUG:
        return LTHR_BY_SLUG[slug], LTHR_SOURCE_BY_SLUG.get(slug, "จากผลเทสล่าสุด")
    return None, "ยังไม่มี LTHR ที่ยืนยันจากการทดสอบ — ไม่ประมาณจาก HR สูงสุด"
