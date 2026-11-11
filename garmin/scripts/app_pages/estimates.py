"""หน้า "ค่าประเมิน Garmin" — ตัวเลขที่ Garmin คำนวณจาก algorithm ของตัวเอง

VO2max, เวลาคาดการณ์แข่ง, Lactate Threshold, Endurance/Hill Score, สถิติส่วนตัว
ทุกค่าเป็นค่าประมาณของผู้ผลิต (black box) ไม่ใช่ผลเทสจริง จึงอยู่แยกหน้าและบอกวันที่เสมอ
นาฬิกาแต่ละรุ่นส่งไม่เท่ากัน ช่องที่ไม่เคยได้รับจะไม่ถูกวาด
"""

import pandas as pd
import streamlit as st
from dashboard_charts import daily_line_frame_and_spec
from dashboard_context import (
    chart_header,
    page_context,
    page_lead,
    render_metric_grid,
    section_heading,
)
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
    series_range_stat,
    value_of,
)

ctx = page_context()
today = ctx.today
CHART_HEIGHT = 225

st.title(f"ค่าประเมิน Garmin · {ctx.selected_name}")
page_lead(
    f"ค่าสมรรถนะและเวลาแข่งที่นาฬิกาประเมินจากข้อมูลซ้อมสะสม (ไม่ใช่ผลทดสอบในห้องแล็บ) · "
    f"กราฟแนวโน้มช่วง {ctx.start_date:%d/%m/%Y} – {ctx.end_date:%d/%m/%Y}"
)

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
    section_heading("ค่าประเมินสมรรถนะล่าสุด", "แสดงค่าล่าสุดที่มีในประวัติพร้อมวันอัปเดต แม้ไม่ได้เปลี่ยนทุกวัน")
    render_metric_grid(tiles, cols_per_row=4, border=True)

predictions = load_race_predictions(ctx.athlete_id, "1900-01-01", today.isoformat())
distances = (("time_5k_sec", "5K"), ("time_10k_sec", "10K"),
             ("time_half_sec", "Half"), ("time_full_sec", "Marathon"))
if not predictions.empty:
    shown_any = True
    section_heading("เวลาคาดการณ์แข่ง (Garmin Race Predictor)", "เวลาเข้าเส้นชัยที่ Garmin ประเมินต่อระยะทางจากประวัติซ้อม")
    pred_tiles = []
    for column, label in distances:
        snapshot = latest_field(predictions, column)
        if snapshot:
            pred_tiles.append((label, fmt_sec(snapshot["value"]), snapshot["date"].strftime("%d/%m/%Y")))
    if pred_tiles:
        render_metric_grid(pred_tiles, cols_per_row=4, border=True)

    pred_dates = _to_datetime(predictions["calendar_date"])
    in_range = predictions[
        (pred_dates >= pd.Timestamp(ctx.start_date))
        & (pred_dates <= pd.Timestamp(ctx.end_date))
    ].sort_values("calendar_date", kind="stable")

    race_panels = [
        (column, label)
        for column, label in (("time_5k_sec", "5K"), ("time_10k_sec", "10K"))
        if column in in_range and in_range[column].notna().sum() >= 2
    ]
    if race_panels:
        chart = calendar_aligned_frame(in_range, "calendar_date", ctx.start_date, ctx.end_date)
        chart["วันที่"] = chart["calendar_date"]
        cols = st.columns(2) if len(race_panels) == 2 else [st.container()]
        for col_holder, (column, label) in zip(cols, race_panels, strict=False):
            card = col_holder.container(border=True, key=f"surface-est-{label.lower()}")
            stat_text = series_range_stat(chart[column], formatter=fmt_sec)
            chart_header(
                card,
                f"แนวโน้มเวลา {label} ที่คาดการณ์",
                "แกนตั้ง = เวลา (นาที:วินาที) · เส้นกราฟลดลงแปลว่าคาดว่าวิ่งได้เร็วขึ้น",
                stat_text,
            )
            secs = chart[["วันที่"]].assign(
                **{
                    column: pd.to_numeric(chart[column], errors="coerce"),
                    "เวลาคาดการณ์": chart[column].map(
                        lambda v: fmt_sec(v) if pd.notna(v) else None
                    ),
                }
            )
            frame, spec = daily_line_frame_and_spec(
                secs, [column], [label],
                y_label="นาที:วินาที", height=CHART_HEIGHT, formatted_col="เวลาคาดการณ์", y_mmss=True,
            )
            card.vega_lite_chart(frame, spec, width="stretch")

if "vo2max_trend" in history and history["vo2max_trend"].notna().any():
    history_dates = _to_datetime(history["calendar_date"])
    in_range = history[
        (history_dates >= pd.Timestamp(ctx.start_date))
        & (history_dates <= pd.Timestamp(ctx.end_date))
    ]
    if in_range["vo2max_trend"].notna().sum() >= 2:
        chart = calendar_aligned_frame(in_range, "calendar_date", ctx.start_date, ctx.end_date)
        chart["วันที่"] = chart["calendar_date"]
        with st.container(border=True, key="surface-est-vo2max"):
            chart_header(
                st,
                "แนวโน้ม VO2max รายวัน",
                "หน่วย ml/kg/min · ความสามารถการใช้ออกซิเจนสูงสุดที่นาฬิกาประเมินหลังวิ่ง · ยิ่งสูงยิ่งดี",
                series_range_stat(chart["vo2max_trend"]),
            )
            frame, spec = daily_line_frame_and_spec(
                chart, ["vo2max_trend"], ["VO2max"], y_label="ml/kg/min", height=CHART_HEIGHT,
            )
            st.vega_lite_chart(frame, spec, width="stretch")

records = load_personal_records(ctx.athlete_id)
if not records.empty:
    shown_any = True
    section_heading("สถิติส่วนตัวและองค์ประกอบร่างกาย", "ข้อมูลสะสมจากบัญชี Garmin Connect")
    with st.container(border=True, key="surface-est-pr"):
        chart_header(
            st,
            "สถิติส่วนตัว (Garmin Personal Records)",
            "สถิติดีที่สุดที่ Garmin ตรวจพบจากทุกกิจกรรม · หากสัญญาณ GPS คลาดเคลื่อนสามารถแก้ไขได้ใน Garmin Connect",
            f"{len(records)} รายการ",
        )
        st.dataframe(pd.DataFrame(personal_record_rows(records)), hide_index=True, width="stretch")

body = load_body_composition(ctx.athlete_id)
if not body.empty and body[["weight_kg", "bmi", "body_fat_pct"]].notna().any().any():
    if records.empty:
        section_heading("องค์ประกอบร่างกาย", "ค่าล่าสุดที่เคยบันทึกในบัญชี Garmin Connect")
    shown_any = True
    with st.container(border=True, key="surface-est-body"):
        chart_header(st, "องค์ประกอบร่างกายล่าสุด", "ค่าล่าสุดที่ซิงก์จากเครื่องชั่งหรือบันทึกในบัญชี Garmin")
        body_tiles = []
        for column, label, unit in (("weight_kg", "น้ำหนัก", " kg"), ("bmi", "BMI", ""),
                                    ("body_fat_pct", "ไขมัน", "%")):
            snapshot = latest_field(body, column)
            if snapshot:
                body_tiles.append((label, fmt_num(snapshot["value"], unit), snapshot["date"].strftime("%d/%m/%Y")))
        if body_tiles:
            render_metric_grid(body_tiles, cols_per_row=4, border=True)

if not shown_any:
    st.info("Garmin ยังไม่เคยส่งค่าประเมินของนักกีฬาคนนี้มา", icon=":material/info:")
