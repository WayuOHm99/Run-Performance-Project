"""หน้า "การซ้อม" — ซ้อมไปเท่าไหร่ในช่วงที่เลือก

ตัวเลขบนหน้านี้เป็นผลรวมตรง ๆ ของค่าที่ Garmin ส่งมาต่อกิจกรรม (ระยะ เวลา
วินาทีในโซน HR) ไม่มีการจัดความหนักเอง ไม่มีค่าเฉลี่ยเทียบฐาน และไม่มีเป้าสัดส่วน
โซน HR คือโซนที่ตั้งไว้ในนาฬิกา/Garmin Connect ของนักกีฬาแต่ละคน
"""

import altair as alt
import pandas as pd
import streamlit as st

from dashboard_context import page_context
from dashboard_domain import (
    HR_ZONE_COLUMNS,
    HR_ZONE_LABELS,
    RUN_TYPES,
    activity_rows,
    fmt_hours,
    fmt_num,
    weekly_totals,
)

ctx = page_context()
activities = ctx.activity_df
CHART_HEIGHT = 240
ZONE_COLORS = ["#cde2fb", "#9ec5f4", "#3987e5", "#1c5cab", "#0b2e5c"]

st.title(f"การซ้อม · {ctx.selected_name}")
st.caption(f"{ctx.start_date.strftime('%d/%m/%Y')} – {ctx.end_date.strftime('%d/%m/%Y')} · "
           "ผลรวมของกิจกรรมที่ Garmin บันทึก")

if activities.empty:
    st.info("ยังไม่มีกิจกรรมในช่วงนี้", icon=":material/info:")
    st.stop()

runs = activities[activities["activity_type"].isin(RUN_TYPES)]
distance = pd.to_numeric(runs["distance_m"], errors="coerce").sum() / 1000
duration = pd.to_numeric(activities["duration_sec"], errors="coerce").sum()
days_trained = activities["start_time_local"].dt.date.nunique()

with st.container(horizontal=True):
    st.metric("ระยะวิ่งรวม", f"{distance:,.1f} km", border=True)
    st.metric("เวลาซ้อมรวม", fmt_hours(duration), border=True,
              help="ทุกกิจกรรม รวมเวท/HIIT/ปั่น")
    st.metric("จำนวนกิจกรรม", f"{len(activities)}", border=True,
              help="Garmin อาจบันทึก warm-up งานหลัก และ cool-down เป็นคนละกิจกรรม")
    st.metric("วันที่ซ้อม", f"{days_trained} วัน", border=True)

weeks = weekly_totals(activities, ctx.start_date, ctx.end_date)
weeks["สัปดาห์"] = weeks["week"].dt.strftime("%d/%m")
weeks = weeks.rename(columns={"run_km": "ระยะวิ่ง (km)"}).round(1)
# กราฟซ้อนต้องเป็นตารางยาว ไม่งั้น tooltip ขึ้นชื่อคอลัมน์ภายในอย่าง "value"/"color"
zones_long = weeks.melt(id_vars="สัปดาห์", value_vars=list(HR_ZONE_LABELS),
                        var_name="โซน", value_name="นาที").round(0)

left, right = st.columns(2)
with left, st.container(border=True):
    st.markdown("**ระยะวิ่งรายสัปดาห์**")
    st.caption("ผลรวม km ของกิจกรรมวิ่ง · สัปดาห์เริ่มวันจันทร์")
    st.bar_chart(weeks, x="สัปดาห์", y="ระยะวิ่ง (km)", x_label="", y_label="km",
                 height=CHART_HEIGHT, sort=False)
with right, st.container(border=True):
    st.markdown("**เวลาในโซน HR รายสัปดาห์**")
    st.caption("นาทีในแต่ละโซนที่ Garmin นับไว้ ทุกกิจกรรม")
    has_zones = any(column in activities and activities[column].notna().any()
                    for column in HR_ZONE_COLUMNS)
    if has_zones:
        # โซนเป็นลำดับ จึงไล่เฉดสีเดียวอ่อนไปเข้ม ไม่ใช้เขียว-แดงที่อ่านว่า "ดี/อันตราย"
        # st.bar_chart รับได้ทั้งคอลัมน์สีหรือรายการสี แต่ไม่ทั้งสองอย่าง จึงต้องลง altair
        st.altair_chart(
            alt.Chart(zones_long).mark_bar().encode(
                x=alt.X("สัปดาห์:N", sort=None, title=None),
                y=alt.Y("sum(นาที):Q", title="นาที"),
                color=alt.Color("โซน:N", scale=alt.Scale(domain=list(HR_ZONE_LABELS),
                                                        range=ZONE_COLORS),
                                legend=alt.Legend(orient="bottom", title=None)),
                order=alt.Order("โซน:N"),
                tooltip=["สัปดาห์", "โซน", "นาที"],
            ).properties(height=CHART_HEIGHT),
            width="stretch",
        )
    else:
        st.caption("Garmin ยังไม่ได้ส่งเวลาในโซน HR ของกิจกรรมในช่วงนี้")

load = activities.dropna(subset=["training_load"]) if "training_load" in activities else None
if load is not None and not load.empty:
    with st.container(border=True):
        st.markdown("**Training Load ต่อกิจกรรม**")
        st.caption("ค่าที่ Garmin คำนวณให้แต่ละกิจกรรม · นาฬิกาบางรุ่นไม่ส่งค่านี้")
        load = load.rename(columns={"start_time_local": "วันเวลา", "training_load": "Training Load"})
        st.bar_chart(load, x="วันเวลา", y="Training Load", x_label="",
                     y_label="Training Load", height=CHART_HEIGHT)

st.subheader("กิจกรรมทั้งหมด", anchor=False)
st.dataframe(
    activity_rows(activities), hide_index=True, width="stretch",
    column_config={
        "ระยะ (km)": st.column_config.NumberColumn(format="%.2f"),
        "HR เฉลี่ย": st.column_config.NumberColumn(format="%d"),
        "HR สูงสุด": st.column_config.NumberColumn(format="%d"),
        "Training Effect": st.column_config.NumberColumn(
            format="%.1f", help="Aerobic Training Effect ของ Garmin (0–5)"),
        "Training Load": st.column_config.NumberColumn(format="%d"),
    },
)
st.caption(f"รวม {fmt_num(len(activities))} กิจกรรม · เปิดดูรายละเอียดรายรอบได้ที่หน้า \"เซสชัน\"")
