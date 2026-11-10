"""จัดรูปค่าที่ Garmin ส่งมาให้คนอ่าน — ไม่มี Streamlit ไม่มี HTML และไม่มีสูตร

**นโยบาย Garmin-only (30 ก.ย. 69):** Dashboard แสดงเฉพาะค่าที่ Garmin ส่งมา
ไม่มีเกณฑ์หรือโมเดลของเราเอง (ไม่มี LTHR, VDOT, pace–HR, เทรนด์เทียบฐาน, ธงสถานะ)
ของที่อยู่ในไฟล์นี้จึงมีแค่สามแบบ:

1. เปลี่ยนหน่วย/รูปแบบ — วินาทีเป็น ชม.:นาที, เมตรเป็น km, UTC เป็นเวลาไทย
2. เลือกค่าล่าสุดของแต่ละช่อง พร้อมบอกว่าเป็นของวันไหน
3. ผลรวมตรง ๆ ในช่วงที่เลือก — ระยะรวม เวลารวม วินาทีในโซน HR ที่ Garmin นับไว้

ถ้าจะเพิ่มอะไรที่ไม่เข้าสามข้อนี้ ต้องได้รับอนุมัติจากผู้จัดการทีมก่อน
"""

import datetime
import math
from zoneinfo import ZoneInfo

import pandas as pd

BANGKOK = ZoneInfo("Asia/Bangkok")

HR_ZONE_COLUMNS = ("hr_zone1_sec", "hr_zone2_sec", "hr_zone3_sec",
                   "hr_zone4_sec", "hr_zone5_sec")
HR_ZONE_LABELS = ("Z1", "Z2", "Z3", "Z4", "Z5")


def _bad_num(value):
    """True เมื่อค่าเป็น NULL, NaN, bool หรือ Inf/-Inf ที่แปลงเป็นตัวเลขปกติไม่ได้"""
    if value is None or isinstance(value, bool) or pd.isna(value):
        return True
    try:
        return not math.isfinite(float(value))
    except (TypeError, ValueError):
        return True


def _to_datetime(values, *, utc=False):
    """แปลงวันที่/เวลาแบบผสม (' ', 'T', '.0', โซนเวลา) โดยไม่ล้มบน pandas 3"""
    try:
        return pd.to_datetime(values, format="ISO8601", errors="coerce", utc=utc)
    except (TypeError, ValueError):
        return pd.to_datetime(values, errors="coerce", utc=utc)


# ---------------------------------------------------------------- รูปแบบค่า

def fmt_num(value, suffix="", decimals=None):
    """ตัวเลขที่ไม่โชว์ ``.0`` เกินจำเป็น และไม่รั่ว NaN/Inf ออกไปหน้าเว็บ"""
    if _bad_num(value):
        return "–"
    number = float(value)
    if decimals is None:
        decimals = 0 if number.is_integer() else 1
    return f"{number:.{decimals}f}{suffix}"


def fmt_text(value, fallback=""):
    """ข้อความสะอาด ไม่ปล่อย NaN ของ pandas ขึ้นจอ"""
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def fmt_pace(pace_min_per_km):
    """เพซนาทีทศนิยมเป็น M:SS เช่น 5.75 -> 5:45"""
    if _bad_num(pace_min_per_km) or float(pace_min_per_km) <= 0:
        return "–"
    pace = float(pace_min_per_km)
    minutes = int(pace)
    seconds = int(round((pace - minutes) * 60))
    if seconds == 60:
        minutes, seconds = minutes + 1, 0
    return f"{minutes}:{seconds:02d}"


def fmt_sec(sec):
    """วินาทีเป็น M:SS หรือ H:MM:SS เช่น 1323 -> 22:03, 14023 -> 3:53:43"""
    if _bad_num(sec) or float(sec) < 0:
        return "–"
    s = int(round(float(sec)))
    if s >= 3600:
        return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"
    return f"{s // 60}:{s % 60:02d}"


def fmt_hours(sec):
    """ระยะเวลายาว ๆ เช่นเวลานอน 27000 -> 7 ชม. 30 นาที"""
    if _bad_num(sec):
        return "–"
    total_minutes = max(0, int(round(float(sec) / 60)))
    hours, minutes = divmod(total_minutes, 60)
    if hours and minutes:
        return f"{hours} ชม. {minutes} นาที"
    if hours:
        return f"{hours} ชม."
    return f"{minutes} นาที"


def fmt_recovery_time(minutes):
    """Garmin Recovery Time — หน่วยดิบจาก API คือนาที"""
    if _bad_num(minutes):
        return "–"
    return fmt_hours(float(minutes) * 60)


def garmin_label(value):
    """คำของ Garmin ให้อ่านง่ายโดยไม่แปลความหมายเอง

    Garmin ส่งค่าอย่าง ``PRODUCTIVE_1`` / ``STRAINED_5`` — ตัวเลขท้ายเป็นรหัสภายใน
    ของ Garmin ไม่ได้มีความหมายต่อโค้ช จึงตัดทิ้งแล้วคงคำเดิมของ Garmin ไว้
    """
    text = fmt_text(value)
    if not text:
        return ""
    base = text.rsplit("_", 1)[0] if text.rsplit("_", 1)[-1].isdigit() else text
    return base.replace("_", " ").title()


# ---------------------------------------------------------------- เวลาไทย

def bangkok_date(now_utc=None):
    """วันทำการของ dashboard ตามเวลาไทยเสมอ ไม่ขึ้นกับ timezone ของเครื่อง"""
    if now_utc is None:
        now_utc = datetime.datetime.now(datetime.timezone.utc)
    elif isinstance(now_utc, pd.Timestamp):
        now_utc = now_utc.to_pydatetime()
    if now_utc.tzinfo is None:
        # สัญญาสำหรับเทส: เวลาไม่มีโซนที่ส่งเข้ามาคือ UTC ไม่ใช่เวลาเครื่อง
        now_utc = now_utc.replace(tzinfo=datetime.timezone.utc)
    return now_utc.astimezone(BANGKOK).date()


def to_bangkok_timestamp(value):
    """เวลา UTC ใน DB (รวมรูปแบบเก่าที่ไม่มีโซน) เป็นเวลาไทย"""
    stamp = _to_datetime(value, utc=True)
    if pd.isna(stamp):
        return pd.NaT
    return stamp.tz_convert(BANGKOK)


def calendar_aligned_frame(df, date_column, period_start, period_end):
    """เติมวันที่ไม่มีข้อมูลให้เป็นแถวว่าง — เส้นกราฟจะขาดตรงนั้นแทนการลากข้าม"""
    index = pd.date_range(pd.Timestamp(period_start), pd.Timestamp(period_end), freq="D")
    if df is None or date_column not in getattr(df, "columns", ()):
        return pd.DataFrame({date_column: index})
    aligned = df.copy()
    aligned[date_column] = _to_datetime(aligned[date_column]).dt.normalize()
    aligned = aligned.dropna(subset=[date_column]).drop_duplicates(date_column, keep="last")
    return (
        aligned.set_index(date_column)
        .reindex(index)
        .rename_axis(date_column)
        .reset_index()
    )


# ---------------------------------------------------------------- ค่าล่าสุดรายช่อง

def _parse_source_timestamp_utc(series, column_name):
    """แปลงเวลาต้นทางเป็น UTC โดยตีความคอลัมน์ ``*_local`` ที่ไม่มีโซนเป็นเวลาไทย"""
    is_local = str(column_name).endswith("_local")
    default_tz = BANGKOK if is_local else datetime.timezone.utc
    values = []
    for raw in series:
        if raw is None or pd.isna(raw):
            values.append(pd.NaT)
            continue
        stamp = _to_datetime(raw)
        if pd.isna(stamp):
            values.append(pd.NaT)
            continue
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize(default_tz)
        values.append(stamp.tz_convert(datetime.timezone.utc))
    return pd.Series(values, index=series.index, dtype="datetime64[ns, UTC]")


def latest_field(df, column, timestamp_columns=()):
    """ค่าล่าสุดที่ไม่ใช่ NULL ของช่องเดียว เลือกแยกจากช่องอื่น

    แถว wellness หนึ่งวันประกอบจากหลาย endpoint ของ Garmin การหยิบ "แถวล่าสุด"
    แถวเดียวจะซ่อน Sleep/HRV ที่ยังใช้ได้ของเมื่อวาน เมื่อแถววันนี้มีแค่ Body Battery
    จึงเลือกทีละช่อง ภายในวันเดียวกันให้ timestamp ของต้นทาง (เช่น Readiness) ชนะ
    """
    if (df is None or df.empty or column not in df.columns
            or "calendar_date" not in df.columns):
        return None
    candidates = df[df[column].notna()].copy()
    if candidates.empty:
        return None

    candidates["_sort_calendar"] = _to_datetime(candidates["calendar_date"], utc=True)
    candidates["_sort_source"] = pd.Series(
        pd.NaT, index=candidates.index, dtype="datetime64[ns, UTC]"
    )
    candidates["_source_column_used"] = None
    for name in timestamp_columns:
        if name not in candidates.columns:
            continue
        parsed = _parse_source_timestamp_utc(candidates[name], name)
        fill = candidates["_sort_source"].isna() & parsed.notna()
        candidates.loc[fill, "_sort_source"] = parsed[fill]
        candidates.loc[fill, "_source_column_used"] = name
    candidates["_sort_fetched"] = (
        _to_datetime(candidates["fetched_at"], utc=True)
        if "fetched_at" in candidates.columns else pd.NaT
    )

    row = candidates.sort_values(
        ["_sort_calendar", "_sort_source", "_sort_fetched"], na_position="first"
    ).iloc[-1]
    source_column = row.get("_source_column_used")
    calendar = _to_datetime(row.get("calendar_date"))
    return {
        "value": row[column],
        "date": calendar.date() if pd.notna(calendar) else None,
        "fetched_at": _to_datetime(row.get("fetched_at"), utc=True),
        "source_timestamp": (_to_datetime(row.get(source_column))
                             if source_column else pd.NaT),
        "source_column": source_column,
        "row": row,
    }


def day_row(df, day):
    """แถว wellness ของวันปฏิทินที่เลือกพอดี (วันตามที่ Garmin ระบุ) หรือ None

    หน้าแรกยึดวันที่เลือก ค่าทุกช่องบนการ์ดจึงต้องมาจากแถวนี้แถวเดียว ไม่หยิบ
    "ค่าล่าสุดของแต่ละช่อง" จากคนละวันมาประกอบกัน (ข้อบกพร่อง 4.4 ของ Codex)
    """
    if df is None or df.empty or "calendar_date" not in df.columns:
        return None
    dates = _to_datetime(df["calendar_date"]).dt.date
    rows = df.loc[dates == pd.Timestamp(day).date()]
    return rows.iloc[-1] if not rows.empty else None


def value_of(row, column):
    """ค่าของช่องในแถว หรือ None — ไม่เปลี่ยน NULL/Inf เป็นศูนย์"""
    if row is None or column not in row.index:
        return None
    value = row[column]
    if value is None or pd.isna(value):
        return None
    if not isinstance(value, (str, bytes, bool)):
        try:
            if not math.isfinite(float(value)):
                return None
        except (TypeError, ValueError):
            pass
    return value


def last_before(df, column, day):
    """ค่าล่าสุดของช่องนี้ที่อยู่ *ก่อน* วันที่เลือก — ใช้แสดงแยก พร้อมวันที่ของมันเอง"""
    if df is None or df.empty or "calendar_date" not in df.columns:
        return None
    dates = _to_datetime(df["calendar_date"]).dt.date
    return latest_field(df.loc[dates < pd.Timestamp(day).date()], column)


def field_age_days(snapshot, today_date):
    """อายุเป็นวันปฏิทินของค่าที่ได้จาก ``latest_field`` หรือ None ถ้าไม่มี"""
    if not snapshot or not snapshot.get("date"):
        return None
    return (pd.Timestamp(today_date).date() - snapshot["date"]).days


def field_when(snapshot, today_date):
    """บอกว่าค่านี้เป็นของวันไหน — "วันนี้" / "เมื่อวาน" / "28/09" """
    age = field_age_days(snapshot, today_date)
    if age is None:
        return "ไม่มีข้อมูล"
    if age == 0:
        return "วันนี้"
    if age == 1:
        return "เมื่อวาน"
    return snapshot["date"].strftime("%d/%m")


def readiness_when(snapshot, today_date):
    """Training Readiness อัปเดตระหว่างวัน — ใช้เวลาของ Garmin ถ้ามี"""
    if not snapshot:
        return "ไม่มีข้อมูล"
    stamp = snapshot.get("source_timestamp")
    if stamp is not None and pd.notna(stamp):
        suffix = " UTC" if snapshot.get("source_column") == "readiness_timestamp_utc" else " น."
        return f"{stamp.strftime('%d/%m %H:%M')}{suffix}"
    return field_when(snapshot, today_date)


CORE_DAILY_FIELDS = ("sleep_score", "hrv_last_night", "resting_hr", "bb_most_recent",
                     "body_battery_high", "stress_avg", "steps")


def day_status(row, day, today_date):
    """สถานะข้อมูลของวันที่เลือก — บอกสิ่งที่รู้ ไม่เดาสาเหตุ

    คืน ``(key, ข้อความ)`` โดย key เป็น
    ``partial_today`` (วันนี้ยังไม่จบ ค่าระหว่างวันยังขยับ) · ``complete_day`` ·
    ``no_data`` (ยังไม่ได้รับของวันนั้นเลย — อาจยังไม่ sync หรือไม่ได้ใส่นาฬิกา)
    เคสจริง 3 ก.ย. 69: นาฬิกาไม่ sync ทั้งวัน การ์ดต้องบอกเอง ไม่ใช่ให้โค้ชไล่ดูวันที่
    """
    has_any = row is not None and any(value_of(row, field) is not None
                                      for field in CORE_DAILY_FIELDS)
    if not has_any:
        return "no_data", ("ยังไม่ได้รับข้อมูลของวันนี้" if day == today_date
                           else "ไม่มีข้อมูลของวันนั้น")
    if day == today_date:
        return "partial_today", "ระหว่างวัน · ยังไม่ครบวัน"
    return "complete_day", "มีข้อมูลของวันนั้น"


# ---------------------------------------------------------------- ผลรวมตรง ๆ

def weekly_totals(activity_df, period_start, period_end):
    """ผลรวมรายสัปดาห์ (เริ่มวันจันทร์) ของระยะวิ่ง เวลาซ้อม และวินาทีในโซน HR

    ทุกค่าเป็นผลบวกของตัวเลขที่ Garmin ส่งมาต่อกิจกรรม ไม่มีการถ่วงหรือเทียบฐาน
    สัปดาห์ที่ไม่มีกิจกรรมเลย ระยะ/เวลาเป็นศูนย์จริง (ไม่ได้ซ้อม) แต่นาทีในโซนเป็น
    NaN เมื่อไม่มีกิจกรรมไหนในสัปดาห์นั้นที่ Garmin ส่งโซนมา — "ไม่รู้" ต้องไม่กลายเป็น 0
    """
    start = pd.Timestamp(period_start).normalize()
    weeks = pd.date_range(start - pd.Timedelta(days=start.weekday()),
                          pd.Timestamp(period_end), freq="7D")
    columns = ["week", "run_km", "hours", *HR_ZONE_LABELS]
    result = pd.DataFrame({"week": weeks, "run_km": 0.0, "hours": 0.0})
    for label in HR_ZONE_LABELS:
        result[label] = float("nan")
    if activity_df is None or activity_df.empty:
        return result

    frame = activity_df.copy()
    when = _to_datetime(frame["start_time_local"])
    frame["week"] = (when - pd.to_timedelta(when.dt.day_of_week, unit="D")).dt.normalize()
    is_run = frame.get("activity_type", pd.Series(index=frame.index, dtype=object)).isin(RUN_TYPES)
    frame["run_km"] = pd.to_numeric(frame.get("distance_m"), errors="coerce").where(is_run) / 1000
    frame["hours"] = pd.to_numeric(frame.get("duration_sec"), errors="coerce") / 3600
    for column, label in zip(HR_ZONE_COLUMNS, HR_ZONE_LABELS, strict=True):
        frame[label] = (pd.to_numeric(frame[column], errors="coerce") / 60
                        if column in frame.columns else float("nan"))
    sums = frame.groupby("week")[columns[1:]].sum(min_count=1)
    sums[["run_km", "hours"]] = sums[["run_km", "hours"]].fillna(0.0)
    result = result.set_index("week")
    # update() ข้าม NaN จึงคง NaN เดิมของสัปดาห์ที่ไม่รู้โซนไว้
    result.update(sums)
    return result.reset_index()


def duplicate_suspects(activity_df):
    """กิจกรรมที่ **อาจ** ซ้ำ: คนเดียวกัน เริ่มเวลาเดียวกัน ชนิดเดียวกัน แต่คนละ activity_id

    ไม่ลบ ไม่รวม และไม่หักออกจากยอด — Garmin เก็บไว้ทั้งสองรายการจริง (เช่นบันทึก
    จากสองอุปกรณ์) คนต้องไปดูใน Garmin Connect เอง คืน set ของ activity_id ที่ควรตรวจ
    (เคสจริง: P'kao 29/09/2026 20:08:32 treadmill 6.46 km สองรายการ)
    """
    if activity_df is None or activity_df.empty:
        return set()
    keys = ["athlete_id", "start_time_local", "activity_type"]
    if not set(keys + ["activity_id"]).issubset(activity_df.columns):
        return set()
    groups = activity_df.groupby(keys)["activity_id"].transform("nunique")
    return set(activity_df.loc[groups > 1, "activity_id"].astype("int64"))


RUN_TYPES = ("running", "track_running", "trail_running", "treadmill_running")


# ---------------------------------------------------------------- อุปกรณ์ / ความพร้อมข้อมูล

def device_inventory_labels(records, now_utc=None, stale_days=90):
    """รายชื่อนาฬิกาที่เห็นล่าสุด ตัดตัวที่ไม่เห็นเกิน 90 วัน"""
    now = pd.to_datetime(now_utc, errors="coerce", utc=True) if now_utc is not None else pd.NaT
    if pd.isna(now):
        now = pd.Timestamp.now(tz="UTC")

    by_name = {}
    for record in records or []:
        name = next(
            (value.strip() for value in (record.get("product_display_name"),
                                         record.get("display_name"))
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
            labels.append(f"{name} (พบล่าสุด {seen.tz_convert(BANGKOK).strftime('%d/%m/%Y')})")
        else:
            labels.append(f"{name} (เคยพบ; ไม่มีเวลา last_seen)")
    return labels


def summarize_metric_group(fields, history_counts, selected_counts, latest_dates):
    """สถานะของกลุ่มเมตริกจากข้อมูลที่ Garmin เคยส่งจริง ไม่เดาจากรุ่นนาฬิกา"""
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


# ---------------------------------------------------------------- สถิติส่วนตัว / เซสชัน

def personal_record_label(record_type_id, record_label):
    """ชื่อรายการ PR — บอกตรง ๆ เมื่อ Garmin ไม่ได้ระบุชื่อ

    Garmin คืน ``prTypeLabelKey`` เป็น null ทุกแถว (ยืนยันจาก payload จริง 18 ส.ค. 69)
    ชื่อจึงมาจาก PR_LABELS ใน 03_backfill.py ซึ่งครอบแค่ typeId 1-9, 12-14
    """
    if isinstance(record_label, str) and record_label:
        return record_label
    return f"รายการที่ Garmin ไม่ได้ระบุชื่อ (รหัส {record_type_id})"


def personal_record_rows(records):
    """แถวตาราง PR ตามหน่วยของชนิดสถิติ — ชนิดที่ไม่รู้จักแสดงค่าดิบโดยไม่เดาหน่วย"""
    time_ids, km_ids, meter_ids, step_ids = {1, 2, 3, 4, 5, 6}, {7, 8}, {9}, {12, 13, 14}
    rows = []
    for _, record in records.iterrows():
        type_id, value = int(record["record_type_id"]), record["value"]
        valid = not _bad_num(value)
        if type_id in time_ids:
            shown = fmt_sec(value)
        elif type_id in km_ids:
            shown = f"{float(value) / 1000:.2f} km" if valid else "–"
        elif type_id in meter_ids:
            shown = f"{float(value):,.0f} m" if valid else "–"
        elif type_id in step_ids:
            shown = f"{float(value):,.0f} ก้าว" if valid else "–"
        else:
            shown = f"{float(value):,.0f}" if valid else "–"
        achieved = record["achieved_date"]
        rows.append({
            "รายการ": personal_record_label(type_id, record["record_label"]),
            "สถิติ": shown,
            "ทำได้เมื่อ": str(achieved)[:10] if isinstance(achieved, str) and achieved else "–",
        })
    return rows


def activity_title(activity):
    """ชื่อกิจกรรมตามที่ Garmin ตั้ง ถ้าไม่มีใช้ชนิดกิจกรรม"""
    return fmt_text(activity.get("activity_name"),
                    garmin_label(activity.get("activity_type")) or "กิจกรรม")


def activity_rows(activity_df):
    """ตารางกิจกรรมสำหรับคนอ่าน — ค่าทุกช่องมาจาก Garmin ตรง ๆ แค่จัดรูปแบบ

    ไม่กรองด้วยระยะขั้นต่ำ: warm-up/cool-down และ interval สั้นกว่า 500 ม. เป็นของจริง
    """
    if activity_df is None or activity_df.empty:
        return pd.DataFrame()
    frame = activity_df.copy()
    frame["_when"] = _to_datetime(frame["start_time_local"])
    frame = frame.sort_values("_when", ascending=False, na_position="last", kind="stable")
    when = frame["_when"]
    distance = pd.to_numeric(frame["distance_m"], errors="coerce")
    return pd.DataFrame({
        "วันเวลา": when.dt.strftime("%d/%m %H:%M").fillna("–"),
        "กิจกรรม": [activity_title(row) for _, row in frame.iterrows()],
        "ระยะ (km)": (distance / 1000).where(distance > 0).round(2),
        "เวลา": frame["duration_sec"].map(fmt_sec),
        "เพซ /km": frame["avg_pace_min_per_km"].map(fmt_pace),
        "HR เฉลี่ย": pd.to_numeric(frame["avg_hr"], errors="coerce"),
        "HR สูงสุด": pd.to_numeric(frame["max_hr"], errors="coerce"),
        "Training Effect": pd.to_numeric(frame.get("training_effect_aerobic"), errors="coerce"),
        "Training Load": pd.to_numeric(frame.get("training_load"), errors="coerce"),
    }).reset_index(drop=True)


INTRADAY_METRICS = {"heart_rate": ("HR", "bpm"), "stress": ("Stress", ""),
                    "body_battery": ("Body Battery", "")}
INTRADAY_GAP_MINUTES = 15  # จุดห่างกว่านี้ถือว่าข้อมูลขาด (ต้นทางส่งทุก 2–3 นาที)


def intraday_series(points, metric):
    """จุดของ metric เดียวเรียงตามเวลา พร้อมแทรกแถวว่างตรงช่วงที่ข้อมูลขาด

    ไม่สร้างจุดใหม่จากค่าเฉลี่ย — แค่เติม NaN ระหว่างสองจุดที่ห่างเกิน 15 นาที
    เพื่อให้เส้นกราฟขาดตรงนั้นแทนการลากเชื่อมข้ามเหมือนมีข้อมูล
    คืนคอลัมน์ ``athlete_id, เวลา, ค่า`` บนแกน 00:00–24:00 ของวันนั้น
    """
    columns = ["athlete_id", "เวลา", "ค่า"]
    if points is None or points.empty:
        return pd.DataFrame(columns=columns)
    frame = points[points["metric"] == metric].sort_values(["athlete_id", "ts"])
    rows = []
    gap = pd.Timedelta(minutes=INTRADAY_GAP_MINUTES)
    for athlete_id, group in frame.groupby("athlete_id"):
        previous = None
        for ts, value in zip(group["ts"], group["value"], strict=True):
            if previous is not None and ts - previous > gap:
                rows.append((athlete_id, previous + gap / 2, float("nan")))
            rows.append((athlete_id, ts, value))
            previous = ts
    return pd.DataFrame(rows, columns=columns)
