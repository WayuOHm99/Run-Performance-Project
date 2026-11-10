"""หน้า "ร่างกาย" — ค่า wellness ของนักกีฬาหนึ่งคน ตามที่ Garmin ส่งมา

แถวบนคือค่าล่าสุด เส้นเล็กคือค่าดิบในช่วงที่เลือก ด้านล่างเป็นกราฟรายวันของแต่ละเรื่อง
วันที่ไม่มีข้อมูลเว้นว่างไว้ ไม่ลากเส้นข้าม และไม่มีเส้นฐานหรือเกณฑ์ของระบบเอง
"""

import pandas as pd
import streamlit as st

from dashboard_charts import (
    daily_line_frame_and_spec,
    intraday_frame_and_spec,
    sleep_stage_bar_frame_and_spec,
)
from dashboard_context import page_context
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
    value_of,
)

ctx = page_context()
today = ctx.today
wellness = ctx.wellness_df
CHART_HEIGHT = 220

st.title(f"ร่างกาย · {ctx.selected_name}")
st.caption(f"{ctx.start_date.strftime('%d/%m/%Y')} – {ctx.end_date.strftime('%d/%m/%Y')} · "
           "ค่าทั้งหมดจาก Garmin ตามที่ส่งมา")

if wellness.empty or not wellness.drop(columns=["athlete_id", "calendar_date", "fetched_at"],
                                        errors="ignore").notna().any().any():
    st.info("ยังไม่มีข้อมูลสุขภาพจาก Garmin ในช่วงนี้ — ลองเลือกช่วงวันที่ให้กว้างขึ้น",
            icon=":material/info:")
    st.stop()

daily = calendar_aligned_frame(wellness, "calendar_date", ctx.start_date, ctx.end_date)
# ชื่อคอลัมน์โผล่ในกล่อง tooltip ของกราฟ — ตั้งเป็นภาษาคนก่อนส่งเข้ากราฟ
daily["วันที่"] = daily["calendar_date"]


def has(*columns):
    return any(column in wellness and wellness[column].notna().any() for column in columns)


def spark(column):
    if column not in wellness:
        return None
    values = pd.to_numeric(wellness[column], errors="coerce").dropna().tolist()
    return values if len(values) >= 2 else None


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

with st.container(horizontal=True):
    tiles = [
        ("Sleep score", sleep, fmt_num(sleep["value"]) if sleep else "–",
         field_when(sleep, today), "sleep_score"),
        ("HRV คืนล่าสุด", hrv, fmt_num(hrv["value"], " ms") if hrv else "–",
         " · ".join(filter(None, [garmin_label(hrv["row"].get("hrv_status")) if hrv else "",
                                  field_when(hrv, today)])), "hrv_last_night"),
        ("RHR", rhr, fmt_num(rhr["value"], " bpm") if rhr else "–",
         field_when(rhr, today), "resting_hr"),
        ("Body Battery ล่าสุด", battery, fmt_num(battery["value"]) if battery else "–",
         battery_note, "bb_most_recent"),
        ("Stress เฉลี่ย", stress, fmt_num(stress["value"]) if stress else "–",
         field_when(stress, today), "stress_avg"),
    ]
    if recovery:
        tiles.append((
            "Recovery Time", recovery, fmt_recovery_time(recovery["value"]),
            field_when(recovery, today), "recovery_time_min",
        ))
    if readiness:
        tiles.append((
            "Training Readiness", readiness, fmt_num(readiness["value"]),
            " · ".join(filter(None, [garmin_label(readiness["row"].get("readiness_level")),
                                     readiness_when(readiness, today)])),
            "training_readiness"))
    for label, snapshot, value, note, column in tiles:
        st.metric(label, value, note, delta_color="off", delta_arrow="off",
                  border=True, chart_data=spark(column) if snapshot else None)

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
        with st.expander("รายละเอียด Training Readiness ล่าสุดจาก Garmin", icon=":material/insights:"):
            if short_fb or long_fb:
                st.caption(" · ".join(filter(None, [short_fb, long_fb, readiness_when(readiness, today)])))
            if factor_items:
                with st.container(horizontal=True):
                    for f_label, f_val, f_note in factor_items:
                        st.metric(f_label, f_val, f_note, delta_color="off", delta_arrow="off", border=True)


def chart_card(title, caption=None):
    card = st.container(border=True)
    card.markdown(f"**{title}**")
    if caption:
        card.caption(caption)
    return card


def line(card, columns, labels, y_label):
    frame, spec = daily_line_frame_and_spec(daily, columns, labels, y_label=y_label, height=CHART_HEIGHT)
    card.vega_lite_chart(frame, spec, width="stretch")


left, right = st.columns(2)
with left:
    if has("sleep_score"):
        line(chart_card("คะแนนการนอน", "Garmin Sleep Score รายคืน"),
             ["sleep_score"], ["Sleep score"], "คะแนน")
    if has("hrv_last_night", "hrv_weekly_avg"):
        line(chart_card("HRV", "คืนล่าสุด และค่าเฉลี่ย 7 วันที่ Garmin คำนวณเอง"),
             ["hrv_last_night", "hrv_weekly_avg"], ["คืนล่าสุด", "เฉลี่ย 7 วัน (Garmin)"], "ms")
    if has("body_battery_high", "body_battery_low"):
        line(chart_card("Body Battery", "สูงสุดและต่ำสุดของแต่ละวัน"),
             ["body_battery_high", "body_battery_low"], ["สูงสุด", "ต่ำสุด"], "")
    if has("bb_charged", "bb_drained"):
        line(chart_card("Body Battery ที่ได้/ใช้ไป", "ชาร์จเข้าและใช้ไปของแต่ละวันตามที่ Garmin นับ"),
             ["bb_charged", "bb_drained"], ["ชาร์จ", "ใช้ไป"], "")
    if has("avg_sleep_respiration", "avg_waking_respiration"):
        line(chart_card("การหายใจ", "ครั้งต่อนาที ตอนหลับและตอนตื่น"),
             ["avg_sleep_respiration", "avg_waking_respiration"], ["ตอนหลับ", "ตอนตื่น"],
             "ครั้ง/นาที")
with right:
    if has("deep_sleep_sec", "light_sleep_sec", "rem_sleep_sec", "awake_sec"):
        card = chart_card("ระยะการนอน", "ชั่วโมงในแต่ละระยะที่ Garmin แยกให้")
        stages = daily[["วันที่"]].copy()
        for column, label in (("deep_sleep_sec", "Deep"), ("light_sleep_sec", "Light"),
                              ("rem_sleep_sec", "REM"), ("awake_sec", "ตื่น")):
            stages[label] = pd.to_numeric(daily.get(column), errors="coerce") / 3600
        # หลับลึกเข้มสุดไล่ไปหลับตื้นอ่อนสุด ส่วนช่วงตื่นเป็นสีส้มให้เด่นแยกออกมา
        stage_frame, stage_spec = sleep_stage_bar_frame_and_spec(
            stages,
            labels=("Deep", "REM", "Light", "ตื่น"),
            colors=("#104281", "#3987e5", "#aed0f7", "#eb6834"),
            y_label="ชั่วโมง",
            height=CHART_HEIGHT,
        )
        card.vega_lite_chart(stage_frame, stage_spec, width="stretch")
    if has("resting_hr"):
        line(chart_card("Resting HR"), ["resting_hr"], ["RHR"], "bpm")
    if has("stress_avg", "max_stress"):
        line(chart_card("Stress", "ค่าเฉลี่ยและสูงสุดของวัน"),
             ["stress_avg", "max_stress"], ["เฉลี่ย", "สูงสุด"], "")
    if has("training_readiness"):
        line(chart_card("Training Readiness"), ["training_readiness"], ["Readiness"], "คะแนน")

st.subheader("ระหว่างวัน", anchor=False)
if "body_intraday_day" in st.session_state and st.session_state["body_intraday_day"] > today:
    st.session_state["body_intraday_day"] = today
intraday_day = st.date_input("วันที่", value=today, max_value=today, format="DD/MM/YYYY",
                             key="body_intraday_day", width=170)
intraday_word = "วันนี้" if intraday_day == today else "วันนั้น"
points = load_intraday(intraday_day, [ctx.athlete_id])
if points.empty:
    st.caption(f"ยังไม่มีข้อมูลระหว่างวันของ{intraday_word} — ระบบเริ่มเก็บ HR/Stress/Body Battery รายจุด"
               "ตั้งแต่ 30 ก.ย. 69 และเก็บย้อนหลัง 180 วัน")
else:
    st.caption("จุดละ 2–3 นาทีตามที่นาฬิกาส่งมา · เส้นขาด = ช่วงที่ไม่มีข้อมูล "
               "(ไม่ได้ใส่นาฬิกา / Stress วัดไม่ได้ระหว่างออกกำลังกาย)")
    for metric, (label, unit) in INTRADAY_METRICS.items():
        series = intraday_series(points, metric)
        if series["ค่า"].notna().any():
            with st.container(border=True):
                st.markdown(f"**{label}**")
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


with st.expander("ตารางค่ารายวันทั้งหมด", icon=":material/table_view:"):
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
