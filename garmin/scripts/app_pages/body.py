"""หน้า "ร่างกาย" — ค่า wellness ของนักกีฬาหนึ่งคน ตามที่ Garmin ส่งมา

แถวบนคือค่าล่าสุดรายช่อง ด้านล่างเป็นกราฟรายวันพร้อมคำอธิบายวิธีอ่านและกรอบค่าจริงของช่วงที่เลือก
วันที่ไม่มีข้อมูลเว้นว่างไว้ ไม่ลากเส้นข้าม และไม่มีเส้นฐานหรือเกณฑ์ของระบบเอง
"""

import datetime

import pandas as pd
import streamlit as st
from dashboard_charts import (
    daily_line_frame_and_spec,
    intraday_frame_and_spec,
    sleep_stage_bar_frame_and_spec,
)
from dashboard_context import (
    chart_header,
    page_context,
    page_lead,
    render_metric_grid,
    section_heading,
)
from dashboard_data import load_intraday
from dashboard_domain import (
    INTRADAY_METRICS,
    calendar_aligned_frame,
    field_when,
    fmt_hours,
    fmt_num,
    fmt_recovery_time,
    garmin_label,
    intraday_series,
    latest_field,
    readiness_when,
    series_range_stat,
    value_of,
)

ctx = page_context()
today = ctx.today
wellness = ctx.wellness_df
CHART_HEIGHT = 225

BODY_INTRADAY_GUIDES = {
    "heart_rate": (
        "ชีพจรตลอดวัน (Heart Rate)",
        "หน่วย bpm บนแกนเวลา 00:00–24:00 น. · ยอดแหลมตรงกับช่วงออกกำลังกาย · เส้นขาดคือช่วงถอดนาฬิกา",
    ),
    "stress": (
        "ความเครียดทางสรีรวิทยาตลอดวัน (Stress)",
        "คะแนน 0–100 · Garmin งดวัด Stress ขณะวิ่งหรือออกกำลังกาย เส้นจึงเว้นว่างช่วงซ้อมตามปกติ",
    ),
    "body_battery": (
        "ระดับพลังงานตลอดวัน (Body Battery)",
        "คะแนน 5–100 · เพิ่มขึ้นขณะนอนหลับพักฟื้น และลดลงตามการใช้พลังงานระหว่างวัน",
    ),
}

st.title(f"ร่างกาย · {ctx.selected_name}")
span_days = max(1, (ctx.end_date - ctx.start_date).days + 1)
page_lead(
    f"ค่าสุขภาพและการฟื้นตัวรายวันจากนาฬิกา Garmin · ช่วงวันที่ "
    f"{ctx.start_date:%d/%m/%Y} – {ctx.end_date:%d/%m/%Y} ({span_days} วัน)"
)

if wellness.empty or not wellness.drop(columns=["athlete_id", "calendar_date", "fetched_at"],
                                        errors="ignore").notna().any().any():
    st.info("ยังไม่มีข้อมูลสุขภาพจาก Garmin ในช่วงนี้ — ลองเลือกช่วงวันที่ให้กว้างขึ้น",
            icon=":material/info:")
    st.stop()

section_heading("ค่าล่าสุดของแต่ละตัวชี้วัด", "แสดงค่าล่าสุดที่มีข้อมูลจริงแยกตามช่อง พร้อมระบุวันเวลาของค่านั้น")

daily = calendar_aligned_frame(wellness, "calendar_date", ctx.start_date, ctx.end_date)
daily["วันที่"] = daily["calendar_date"]


def has(*columns):
    return any(column in wellness and wellness[column].notna().any() for column in columns)


# ---- ค่าล่าสุด ----
sleep = latest_field(wellness, "sleep_score")
hrv = latest_field(wellness, "hrv_last_night")
rhr = latest_field(wellness, "resting_hr")
battery = latest_field(wellness, "bb_most_recent")
stress = latest_field(wellness, "stress_avg")
recovery = latest_field(wellness, "recovery_time_min")
readiness = latest_field(wellness, "training_readiness",
                         ("readiness_timestamp_local", "readiness_timestamp_utc"))

battery_wake = value_of(battery["row"], "bb_at_wake") if battery else None
battery_note = " · ".join(filter(None, [
    f"ตื่น {fmt_num(battery_wake)}" if battery_wake is not None else "",
    field_when(battery, today),
]))

tiles = [
    ("Sleep score", fmt_num(sleep["value"]) if sleep else "–", field_when(sleep, today)),
    ("HRV คืนล่าสุด", fmt_num(hrv["value"], " ms") if hrv else "–",
     " · ".join(filter(None, [garmin_label(hrv["row"].get("hrv_status")) if hrv else "",
                              field_when(hrv, today)]))),
    ("RHR", fmt_num(rhr["value"], " bpm") if rhr else "–", field_when(rhr, today)),
    ("Body Battery ล่าสุด", fmt_num(battery["value"]) if battery else "–", battery_note),
    ("Stress เฉลี่ย", fmt_num(stress["value"]) if stress else "–", field_when(stress, today)),
]
if recovery:
    tiles.append(("Recovery Time", fmt_recovery_time(recovery["value"]), field_when(recovery, today)))
if readiness:
    tiles.append((
        "Training Readiness", fmt_num(readiness["value"]),
        " · ".join(filter(None, [garmin_label(readiness["row"].get("readiness_level")),
                                 readiness_when(readiness, today)])),
    ))

render_metric_grid(tiles, cols_per_row=4, border=True)

if readiness:
    r_row = readiness["row"]
    factor_items = []
    for pct_col, fb_col, label in (
        ("readiness_sleep_factor_pct", "readiness_sleep_factor_feedback", "ปัจจัยการนอน (Garmin)"),
        ("recovery_time_factor_pct", "recovery_time_factor_feedback", "ปัจจัย Recovery Time (Garmin)"),
        ("hrv_factor_pct", "hrv_factor_feedback", "ปัจจัย HRV (Garmin)"),
        ("stress_history_pct", "stress_history_factor_feedback", "ปัจจัย Stress สะสม (Garmin)"),
    ):
        pct_val = value_of(r_row, pct_col)
        if pct_val is not None:
            factor_items.append((label, fmt_num(pct_val, "%"), garmin_label(value_of(r_row, fb_col)) or None))
    acute_val = value_of(r_row, "acute_load")
    if acute_val is not None:
        factor_items.append(("Acute Load (Garmin)", fmt_num(acute_val), None))
    short_fb = garmin_label(value_of(r_row, "readiness_feedback"))
    long_fb = garmin_label(value_of(r_row, "readiness_feedback_long"))
    if factor_items or short_fb or long_fb:
        with st.expander("องค์ประกอบคะแนน Training Readiness ล่าสุดจาก Garmin", icon=":material/insights:"):
            if short_fb or long_fb:
                st.caption(" · ".join(filter(None, [short_fb, long_fb, readiness_when(readiness, today)])))
            if factor_items:
                render_metric_grid(factor_items, cols_per_row=4, border=True)


def _dual_latest_stat(col_a, label_a, col_b, label_b, unit=""):
    snap_a = latest_field(wellness, col_a)
    snap_b = latest_field(wellness, col_b)
    parts = []
    if snap_a:
        parts.append(f"{label_a} {fmt_num(snap_a['value'], unit)}")
    if snap_b:
        parts.append(f"{label_b} {fmt_num(snap_b['value'], unit)}")
    return " · ".join(parts) if parts else None


def render_line_panel(holder, key_suffix, title, guide, columns, labels, y_label, stat=None):
    card = holder.container(border=True, key=f"surface-body-{key_suffix}")
    chart_header(card, title, guide, stat)
    frame, spec = daily_line_frame_and_spec(daily, columns, labels, y_label=y_label, height=CHART_HEIGHT)
    card.vega_lite_chart(frame, spec, width="stretch")


def render_sleep_stages(holder):
    card = holder.container(border=True, key="surface-body-sleep-stage")
    sleep_dur = latest_field(wellness, "sleep_duration_sec")
    sleep_stat = f"คืนล่าสุด {fmt_hours(sleep_dur['value'])}" if sleep_dur else None
    chart_header(
        card,
        "โครงสร้างการนอนแต่ละคืน (Sleep Stages)",
        "หน่วยชั่วโมง · แท่งสูง = เวลานอนรวมมาก · สีน้ำเงินเข้มคือหลับลึก สีส้มด้านบนคือช่วงตื่นกลางดึก",
        sleep_stat,
    )
    stages = daily[["วันที่"]].copy()
    stage_defs = (
        ("deep_sleep_sec", "หลับลึก (Deep)"),
        ("rem_sleep_sec", "ฝัน (REM)"),
        ("light_sleep_sec", "หลับตื้น (Light)"),
        ("awake_sec", "ตื่นกลางดึก"),
    )
    for column, label in stage_defs:
        stages[label] = pd.to_numeric(daily.get(column), errors="coerce") / 3600
    stage_frame, stage_spec = sleep_stage_bar_frame_and_spec(
        stages,
        labels=tuple(label for _, label in stage_defs),
        colors=("#0b2545", "#155eef", "#93c5fd", "#d95d24"),
        y_label="ชั่วโมง",
        height=CHART_HEIGHT,
    )
    card.vega_lite_chart(stage_frame, stage_spec, width="stretch")


def render_chart_grid(panels):
    """จัดเรียงกราฟที่มีข้อมูลจริงเป็นแถวละ 2 ใบเคียงกัน ไม่ปล่อยคอลัมน์ว่าง"""
    for idx in range(0, len(panels), 2):
        pair = panels[idx:idx + 2]
        cols = st.columns(2) if len(pair) == 2 else [st.container()]
        for col, panel_fn in zip(cols, pair, strict=False):
            panel_fn(col)


recovery_panels = []
if has("sleep_score"):
    recovery_panels.append(
        lambda h: render_line_panel(
            h, "sleep",
            "คะแนนการนอนรายคืน (Sleep Score)",
            "คะแนน 0–100 จากเวลานอนและความต่อเนื่องของการหลับ · ยิ่งสูงแปลว่าคุณภาพการนอนดี",
            ["sleep_score"], ["Sleep score"], "คะแนน",
            stat=series_range_stat(daily.get("sleep_score")),
        )
    )
if has("deep_sleep_sec", "light_sleep_sec", "rem_sleep_sec", "awake_sec"):
    recovery_panels.append(render_sleep_stages)
if has("hrv_last_night", "hrv_weekly_avg"):
    recovery_panels.append(
        lambda h: render_line_panel(
            h, "hrv",
            "ความแปรผันหัวใจขณะหลับ (HRV)",
            "หน่วย ms · เส้นน้ำเงิน = ค่าเฉลี่ยคืนล่าสุด · เส้นส้ม = ค่าเฉลี่ย 7 วันที่นาฬิกาคำนวณ",
            ["hrv_last_night", "hrv_weekly_avg"],
            ["คืนล่าสุด", "เฉลี่ย 7 วัน (Garmin)"], "ms",
            stat=series_range_stat(daily.get("hrv_last_night"), " ms"),
        )
    )
if has("resting_hr"):
    recovery_panels.append(
        lambda h: render_line_panel(
            h, "rhr",
            "ชีพจรขณะพัก (Resting HR)",
            "หน่วย bpm · วัดช่วงพักนิ่งของแต่ละวัน (แกนตั้งซูมตามกรอบค่าจริงเพื่อให้เห็นการเปลี่ยนแปลงชัด)",
            ["resting_hr"], ["RHR"], "bpm",
            stat=series_range_stat(daily.get("resting_hr"), " bpm"),
        )
    )
if recovery_panels:
    section_heading("การนอนหลับและระบบประสาทอัตโนมัติ", "วันที่ไม่มีข้อมูลจะเว้นช่องว่างตามจริง ไม่ลากเส้นเชื่อมข้ามวัน")
    render_chart_grid(recovery_panels)

energy_panels = []
if has("body_battery_high", "body_battery_low"):
    energy_panels.append(
        lambda h: render_line_panel(
            h, "bb-range",
            "กรอบพลังงานรายวัน (Body Battery สูงสุด / ต่ำสุด)",
            "คะแนน 5–100 · เส้นน้ำเงิน = จุดสูงสุดหลังพักผ่อน · เส้นส้ม = จุดต่ำสุดก่อนพักรอบถัดไป",
            ["body_battery_high", "body_battery_low"],
            ["สูงสุดของวัน", "ต่ำสุดของวัน"], "คะแนน",
            stat=_dual_latest_stat("body_battery_high", "สูงสุด", "body_battery_low", "ต่ำสุด"),
        )
    )
if has("bb_charged", "bb_drained"):
    energy_panels.append(
        lambda h: render_line_panel(
            h, "bb-flow",
            "พลังงานที่ชาร์จเพิ่มเทียบกับที่ใช้ไป (Body Battery Flow)",
            "คะแนนพลังงานที่ฟื้นจากการนอน/พัก (สีน้ำเงิน) เทียบกับที่ใช้ไปตลอดวัน (สีส้ม)",
            ["bb_charged", "bb_drained"],
            ["ชาร์จเพิ่ม", "ใช้ไป"], "คะแนน",
            stat=_dual_latest_stat("bb_charged", "ชาร์จ +", "bb_drained", "ใช้ -"),
        )
    )
if has("stress_avg", "max_stress"):
    energy_panels.append(
        lambda h: render_line_panel(
            h, "stress",
            "ความเครียดทางสรีรวิทยารายวัน (Stress)",
            "คะแนน 0–100 ขณะไม่ได้ออกกำลังกาย · เส้นน้ำเงิน = เฉลี่ยทั้งวัน · เส้นส้ม = สูงสุดของวัน",
            ["stress_avg", "max_stress"],
            ["เฉลี่ยทั้งวัน", "สูงสุดของวัน"], "คะแนน",
            stat=series_range_stat(daily.get("stress_avg")),
        )
    )
if has("training_readiness"):
    energy_panels.append(
        lambda h: render_line_panel(
            h, "readiness",
            "ความพร้อมซ้อมรายวัน (Training Readiness)",
            "คะแนน 1–100 ที่ Garmin ประเมินจากคุณภาพการนอน เวลาพักฟื้น HRV และโหลดสะสม",
            ["training_readiness"], ["Readiness"], "คะแนน",
            stat=series_range_stat(daily.get("training_readiness")),
        )
    )
if has("avg_sleep_respiration", "avg_waking_respiration"):
    energy_panels.append(
        lambda h: render_line_panel(
            h, "resp",
            "อัตราการหายใจเฉลี่ย (Respiration)",
            "หน่วย ครั้ง/นาที · เปรียบเทียบอัตราการหายใจขณะนอนหลับ (สีน้ำเงิน) กับขณะตื่น (สีส้ม)",
            ["avg_sleep_respiration", "avg_waking_respiration"],
            ["ขณะหลับ", "ขณะตื่น"], "ครั้ง/นาที",
            stat=series_range_stat(daily.get("avg_sleep_respiration"), " ครั้ง/นาที"),
        )
    )
if energy_panels:
    section_heading("พลังงาน ความเครียด และการหายใจ", f"แนวโน้มรายวันในช่วง {span_days} วันที่เลือก")
    render_chart_grid(energy_panels)

INTRADAY_DAY_KEY = "body_intraday_day"
if INTRADAY_DAY_KEY not in st.session_state or st.session_state[INTRADAY_DAY_KEY] > today:
    st.session_state[INTRADAY_DAY_KEY] = today


def _shift_intraday_day(days):
    st.session_state[INTRADAY_DAY_KEY] = min(
        today, st.session_state[INTRADAY_DAY_KEY] + datetime.timedelta(days=days)
    )


def _intraday_today():
    st.session_state[INTRADAY_DAY_KEY] = today


section_heading("กราฟละเอียดระหว่างวัน (00:00–24:00 น.)", "ข้อมูลราย 2–3 นาทีจากนาฬิกา เฉพาะวันที่เลือกด้านล่าง")
with st.container(border=True, key="surface-body-intraday-section"):
    with st.container(horizontal=True, vertical_alignment="center"):
        st.button("วันก่อนหน้า", icon=":material/chevron_left:", on_click=_shift_intraday_day,
                  args=(-1,), key="body-prev-day")
        intraday_day = st.date_input("วันที่", max_value=today, format="DD/MM/YYYY",
                                     key=INTRADAY_DAY_KEY, width=155, label_visibility="collapsed")
        st.button("วันถัดไป", icon=":material/chevron_right:", on_click=_shift_intraday_day,
                  args=(1,), key="body-next-day", disabled=st.session_state[INTRADAY_DAY_KEY] >= today)
        st.button("วันนี้", icon=":material/today:", on_click=_intraday_today,
                  key="body-today", disabled=st.session_state[INTRADAY_DAY_KEY] == today)
        st.caption(f"กำลังดูวันที่ {intraday_day:%d/%m/%Y}")
    intraday_word = "วันนี้" if intraday_day == today else "วันนั้น"
    points = load_intraday(intraday_day, [ctx.athlete_id])
    if points.empty:
        st.caption(f"ยังไม่มีข้อมูลระหว่างวันของ{intraday_word} (ระบบเก็บข้อมูลรายจุดย้อนหลัง 180 วัน)")
    else:
        for metric, (label, unit) in INTRADAY_METRICS.items():
            series = intraday_series(points, metric)
            if series["ค่า"].notna().any():
                m_title, m_guide = BODY_INTRADAY_GUIDES[metric]
                m_stat = series_range_stat(series["ค่า"], f" {unit}" if unit else "")
                chart_header(st, m_title, m_guide, m_stat)
                in_frame, in_spec = intraday_frame_and_spec(
                    series, intraday_day, y_title=unit, names={ctx.athlete_id: ctx.selected_name},
                )
                st.vega_lite_chart(in_frame, in_spec, width="stretch")


def _formatted_or_none(frame, column, formatter):
    if column not in frame:
        return None
    return frame[column].map(
        lambda v: None if v is None or pd.isna(v) else (
            None if (out := formatter(v)) in ("", "–") else out
        )
    )


with st.expander("ดูตารางข้อมูลสุขภาพรายวันทั้งหมด", icon=":material/table_view:"):
    table = wellness.sort_values("calendar_date", ascending=False)
    shown = pd.DataFrame({
        "วันที่": table["calendar_date"].astype(str).str[:10],
        "Sleep": table.get("sleep_score"),
        "นอน": _formatted_or_none(table, "sleep_duration_sec", fmt_hours),
        "HRV (ms)": table.get("hrv_last_night"),
        "HRV status": _formatted_or_none(table, "hrv_status", garmin_label),
        "RHR": table.get("resting_hr"),
        "BB ตอนตื่น": table.get("bb_at_wake"),
        "BB ชาร์จตอนนอน": table.get("bb_during_sleep"),
        "BB สูงสุด": table.get("body_battery_high"),
        "BB ต่ำสุด": table.get("body_battery_low"),
        "Stress": table.get("stress_avg"),
        "Recovery Time": _formatted_or_none(table, "recovery_time_min", fmt_recovery_time),
        "Readiness": table.get("training_readiness"),
        "Training Status": _formatted_or_none(table, "training_status", garmin_label),
        "หายใจหลับ": table.get("avg_sleep_respiration"),
        "หายใจตื่น": table.get("avg_waking_respiration"),
        "ก้าว": table.get("steps"),
        "เป้าก้าว": table.get("steps_goal"),
        "Active kcal": table.get("active_kilocalories"),
        "ชั้นที่ขึ้น": table.get("floors_ascended"),
    })
    st.dataframe(shown.dropna(axis=1, how="all"), hide_index=True, width="stretch")
