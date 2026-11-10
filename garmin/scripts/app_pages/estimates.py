"""หน้า "ค่าประเมิน Garmin" — ตัวเลขที่ Garmin คำนวณจาก algorithm ของตัวเอง

VO2max, เวลาคาดการณ์แข่ง, Lactate Threshold, Endurance/Hill Score, สถิติส่วนตัว
ทุกค่าเป็นค่าประมาณของผู้ผลิต (black box) ไม่ใช่ผลเทสจริง จึงอยู่แยกหน้าและบอกวันที่เสมอ
นาฬิกาแต่ละรุ่นส่งไม่เท่ากัน ช่องที่ไม่เคยได้รับจะไม่ถูกวาด
"""

import pandas as pd
import streamlit as st

from dashboard_charts import daily_line_frame_and_spec
from dashboard_context import page_context
from dashboard_data import (
    load_body_composition,
    load_personal_records,
    load_race_predictions,
    load_wellness_data,
)
from dashboard_domain import (
    _to_datetime,
    calendar_aligned_frame,
    field_when,
    fmt_num,
    fmt_pace,
    fmt_sec,
    latest_field,
    personal_record_rows,
    value_of,
)

ctx = page_context()
today = ctx.today
CHART_HEIGHT = 220

st.title(f"ค่าประเมิน Garmin · {ctx.selected_name}")
st.caption("ค่าประมาณจาก algorithm ของ Garmin ไม่ใช่ผลเทสจริง · "
           "ค่าล่าสุดดึงจากประวัติทั้งหมด กราฟใช้ช่วงวันที่ที่เลือก")

# ค่าล่าสุดต้องไม่หายเพียงเพราะอยู่นอกช่วงที่เลือก — Garmin อัปเดตบางค่าห่างเป็นเดือน
history = load_wellness_data(ctx.athlete_id, "1900-01-01", today.isoformat())
shown_any = False

tiles = []
for column, label, render in (
    ("vo2max_trend", "VO2max", lambda v: fmt_num(v)),
    ("lactate_threshold_hr", "Lactate Threshold HR", lambda v: fmt_num(v, " bpm")),
    ("lactate_threshold_pace_min_km", "Lactate Threshold เพซ", lambda v: fmt_pace(v) + " /km"),
    ("endurance_score", "Endurance Score", lambda v: fmt_num(v)),
    ("hill_score_overall", "Hill Score", lambda v: fmt_num(v)),
    ("fitness_age", "Fitness Age", lambda v: fmt_num(v, " ปี")),
):
    snapshot = latest_field(history, column)
    if snapshot:
        note_parts = []
        if column == "hill_score_overall":
            strength = value_of(snapshot["row"], "hill_score_strength")
            endurance = value_of(snapshot["row"], "hill_score_endurance")
            if strength is not None:
                note_parts.append(f"Strength {fmt_num(strength)}")
            if endurance is not None:
                note_parts.append(f"Endurance {fmt_num(endurance)}")
        note_parts.append(field_when(snapshot, today))
        tiles.append((label, render(snapshot["value"]), " · ".join(note_parts)))
if tiles:
    shown_any = True
    with st.container(horizontal=True):
        for label, value, note in tiles:
            st.metric(label, value, note, delta_color="off", delta_arrow="off", border=True)

predictions = load_race_predictions(ctx.athlete_id, "1900-01-01", today.isoformat())
distances = (("time_5k_sec", "5K"), ("time_10k_sec", "10K"),
             ("time_half_sec", "Half"), ("time_full_sec", "Marathon"))
if not predictions.empty:
    shown_any = True
    st.subheader("เวลาคาดการณ์แข่ง (Garmin Race Predictor)", anchor=False)
    with st.container(horizontal=True):
        for column, label in distances:
            snapshot = latest_field(predictions, column)
            if snapshot:
                st.metric(label, fmt_sec(snapshot["value"]),
                          snapshot["date"].strftime("%d/%m/%Y"),
                          delta_color="off", delta_arrow="off", border=True)
    in_range = predictions[
        (predictions["calendar_date"] >= pd.Timestamp(ctx.start_date))
        & (predictions["calendar_date"] <= pd.Timestamp(ctx.end_date))
    ]
    if any(in_range[col].notna().sum() >= 2 for col in ("time_5k_sec", "time_10k_sec")):
        chart = calendar_aligned_frame(in_range, "calendar_date", ctx.start_date, ctx.end_date)
        chart["วันที่"] = chart["calendar_date"]
        with st.container(border=True):
            st.markdown("**5K และ 10K ที่ Garmin คาดการณ์ในช่วงนี้**")
            st.caption("หน่วยเป็นนาที · ค่าที่ต่ำลงคือ Garmin คาดว่าวิ่งได้เร็วขึ้น")
            left, right = st.columns(2)
            for column, label, holder in (("time_5k_sec", "5K", left),
                                          ("time_10k_sec", "10K", right)):
                if in_range[column].notna().sum() >= 2:
                    mins = chart[["วันที่"]].assign(**{column: chart[column] / 60})
                    frame, spec = daily_line_frame_and_spec(
                        mins, [column], [label], y_label="นาที", height=CHART_HEIGHT,
                    )
                    holder.vega_lite_chart(frame, spec, width="stretch")
                else:
                    holder.caption(f"ยังไม่มีข้อมูล {label} พอวาดกราฟในช่วงนี้")

if "vo2max_trend" in history and history["vo2max_trend"].notna().any():
    history_dates = _to_datetime(history["calendar_date"])
    in_range = history[
        (history_dates >= pd.Timestamp(ctx.start_date))
        & (history_dates <= pd.Timestamp(ctx.end_date))
    ]
    if in_range["vo2max_trend"].notna().sum() >= 2:
        chart = calendar_aligned_frame(in_range, "calendar_date", ctx.start_date, ctx.end_date)
        chart["วันที่"] = chart["calendar_date"]
        with st.container(border=True):
            st.markdown("**VO2max รายวันในช่วงนี้**")
            frame, spec = daily_line_frame_and_spec(
                chart, ["vo2max_trend"], ["VO2max"], y_label="ml/kg/min", height=CHART_HEIGHT,
            )
            st.vega_lite_chart(frame, spec, width="stretch")

records = load_personal_records(ctx.athlete_id)
if not records.empty:
    shown_any = True
    st.subheader("สถิติส่วนตัว (Garmin Personal Records)", anchor=False)
    st.caption("Garmin หาเองจากทุกกิจกรรม รวมช่วงหนึ่งของการวิ่งที่ยาวกว่า · "
               "ถ้า GPS กระโดด ค่าที่ได้อาจเร็วเกินจริง แก้ได้ในแอป Garmin Connect")
    st.dataframe(pd.DataFrame(personal_record_rows(records)), hide_index=True, width="stretch")

body = load_body_composition(ctx.athlete_id)
if not body.empty and body[["weight_kg", "bmi", "body_fat_pct"]].notna().any().any():
    shown_any = True
    st.subheader("องค์ประกอบร่างกาย", anchor=False)
    # ค่าล่าสุด "รายช่อง" พร้อมวันที่ของช่องนั้น — แถวล่าสุดอาจมีแค่น้ำหนักไม่มีไขมัน
    # การหยิบแถวเดียวจะซ่อนค่าไขมันครั้งก่อนที่ยังเป็นค่าล่าสุดจริงของมัน
    with st.container(horizontal=True):
        for column, label, unit in (("weight_kg", "น้ำหนัก", " kg"), ("bmi", "BMI", ""),
                                    ("body_fat_pct", "ไขมัน", "%")):
            snapshot = latest_field(body, column)
            if snapshot:
                st.metric(label, fmt_num(snapshot["value"], unit),
                          snapshot["date"].strftime("%d/%m/%Y"),
                          delta_color="off", delta_arrow="off", border=True)

if not shown_any:
    st.info("Garmin ยังไม่เคยส่งค่าประเมินของนักกีฬาคนนี้มา", icon=":material/info:")
