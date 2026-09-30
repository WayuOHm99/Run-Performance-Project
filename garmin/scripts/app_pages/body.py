"""หน้า "ร่างกาย" — ค่า wellness ของนักกีฬาหนึ่งคน ตามที่ Garmin ส่งมา

แถวบนคือค่าล่าสุด เส้นเล็กคือค่าดิบในช่วงที่เลือก ด้านล่างเป็นกราฟรายวันของแต่ละเรื่อง
วันที่ไม่มีข้อมูลเว้นว่างไว้ ไม่ลากเส้นข้าม และไม่มีเส้นฐานหรือเกณฑ์ของระบบเอง
"""

import pandas as pd
import streamlit as st

from dashboard_context import page_context
from dashboard_domain import (
    calendar_aligned_frame,
    field_when,
    fmt_hours,
    fmt_num,
    garmin_label,
    latest_field,
    readiness_when,
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
    values = pd.to_numeric(wellness[column], errors="coerce").dropna().tolist()
    return values if len(values) >= 2 else None


# ---- ค่าล่าสุด ----
sleep = latest_field(wellness, "sleep_score")
hrv = latest_field(wellness, "hrv_last_night")
rhr = latest_field(wellness, "resting_hr")
battery = latest_field(wellness, "bb_most_recent")
stress = latest_field(wellness, "stress_avg")
readiness = latest_field(wellness, "training_readiness",
                         ("readiness_timestamp_local", "readiness_timestamp_utc"))

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
         field_when(battery, today), "bb_most_recent"),
        ("Stress เฉลี่ย", stress, fmt_num(stress["value"]) if stress else "–",
         field_when(stress, today), "stress_avg"),
    ]
    if readiness:
        tiles.append((
            "Training Readiness", readiness, fmt_num(readiness["value"]),
            " · ".join(filter(None, [garmin_label(readiness["row"].get("readiness_level")),
                                     readiness_when(readiness, today)])),
            "training_readiness"))
    for label, snapshot, value, note, column in tiles:
        st.metric(label, value, note, delta_color="off", delta_arrow="off",
                  border=True, chart_data=spark(column) if snapshot else None)


def chart_card(title, caption=None):
    card = st.container(border=True)
    card.markdown(f"**{title}**")
    if caption:
        card.caption(caption)
    return card


def line(card, columns, labels, y_label):
    frame = daily[["วันที่", *columns]].rename(columns=dict(zip(columns, labels)))
    card.line_chart(frame, x="วันที่", y=list(labels), x_label="",
                    y_label=y_label, height=CHART_HEIGHT)


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
        card.bar_chart(stages, x="วันที่", y=["Deep", "REM", "Light", "ตื่น"],
                       color=["#104281", "#3987e5", "#aed0f7", "#eb6834"],
                       x_label="", y_label="ชั่วโมง", height=CHART_HEIGHT)
    if has("resting_hr"):
        line(chart_card("Resting HR"), ["resting_hr"], ["RHR"], "bpm")
    if has("stress_avg", "max_stress"):
        line(chart_card("Stress", "ค่าเฉลี่ยและสูงสุดของวัน"),
             ["stress_avg", "max_stress"], ["เฉลี่ย", "สูงสุด"], "")
    if has("training_readiness"):
        line(chart_card("Training Readiness"), ["training_readiness"], ["Readiness"], "คะแนน")

with st.expander("ตารางค่ารายวันทั้งหมด", icon=":material/table_view:"):
    table = wellness.sort_values("calendar_date", ascending=False)
    shown = pd.DataFrame({
        "วันที่": table["calendar_date"].astype(str).str[:10],
        "Sleep": table.get("sleep_score"),
        "นอน": table.get("sleep_duration_sec").map(fmt_hours),
        "HRV (ms)": table.get("hrv_last_night"),
        "HRV status": table.get("hrv_status").map(garmin_label),
        "RHR": table.get("resting_hr"),
        "BB สูงสุด": table.get("body_battery_high"),
        "BB ต่ำสุด": table.get("body_battery_low"),
        "Stress": table.get("stress_avg"),
        "Readiness": table.get("training_readiness"),
        "Training Status": table.get("training_status").map(garmin_label),
        "ก้าว": table.get("steps"),
    })
    st.dataframe(shown.dropna(axis=1, how="all"), hide_index=True, width="stretch")
