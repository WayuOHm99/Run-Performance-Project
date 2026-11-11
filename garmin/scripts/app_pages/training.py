"""หน้า "การซ้อม" — ซ้อมไปเท่าไหร่ในช่วงที่เลือก

ตัวเลขบนหน้านี้เป็นผลรวมตรง ๆ ของค่าที่ Garmin ส่งมาต่อกิจกรรม (ระยะ เวลา
วินาทีในโซน HR) ไม่มีการจัดความหนักเอง ไม่มีค่าเฉลี่ยเทียบฐาน และไม่มีเป้าสัดส่วน
โซน HR คือโซนที่ตั้งไว้ในนาฬิกา/Garmin Connect ของนักกีฬาแต่ละคน
"""

import pandas as pd
import streamlit as st

from dashboard_charts import activity_load_bar_spec, weekly_bar_spec, zone_bar_spec
from dashboard_context import page_context
from dashboard_domain import (
    HR_ZONE_COLUMNS,
    HR_ZONE_LABELS,
    RUN_TYPES,
    activity_rows,
    activity_title,
    fmt_hours,
    fmt_num,
    weekly_totals,
)

ctx = page_context()
activities = ctx.activity_df
CHART_HEIGHT = 240
ZONE_COLORS = ["#dbeafe", "#93c5fd", "#3b82f6", "#1d4ed8", "#0f3a7d"]
OPTIONAL_ACTIVITY_COLS = ("HR เฉลี่ย", "HR สูงสุด", "Training Effect", "Training Load")

st.title(f"การซ้อม · {ctx.selected_name}")
st.caption(f"ช่วงข้อมูล {ctx.start_date.strftime('%d/%m/%Y')} – {ctx.end_date.strftime('%d/%m/%Y')} · "
           "ผลรวมของกิจกรรมที่ Garmin บันทึก")

if activities.empty:
    st.info("ยังไม่มีกิจกรรมในช่วงนี้", icon=":material/info:")
    st.stop()

runs = activities[activities["activity_type"].isin(RUN_TYPES)]
distance = pd.to_numeric(runs["distance_m"], errors="coerce").sum() / 1000
duration = pd.to_numeric(activities["duration_sec"], errors="coerce").sum()
days_trained = activities["start_time_local"].dt.date.nunique()

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.metric("ระยะวิ่งรวม", f"{distance:,.1f} km", border=True, width="stretch")
with k2:
    st.metric("เวลาซ้อมรวม", fmt_hours(duration), border=True, width="stretch",
              help="ทุกกิจกรรม รวมเวท/HIIT/ปั่น")
with k3:
    st.metric("จำนวนกิจกรรม", f"{len(activities)}", border=True, width="stretch",
              help="Garmin อาจบันทึก warm-up งานหลัก และ cool-down เป็นคนละกิจกรรม")
with k4:
    st.metric("วันที่ซ้อม", f"{days_trained} วัน", border=True, width="stretch")

weeks = weekly_totals(activities, ctx.start_date, ctx.end_date)
week_fmt = "%d/%m/%y" if weeks["week"].dt.year.nunique() > 1 else "%d/%m"
weeks["สัปดาห์"] = weeks["week"].dt.strftime(week_fmt)
weeks = weeks.rename(columns={"run_km": "ระยะวิ่ง (km)"})
numeric_cols = ["ระยะวิ่ง (km)", "hours"]
weeks[numeric_cols] = weeks[numeric_cols].round(1)
# กราฟซ้อนต้องเป็นตารางยาว ไม่งั้น tooltip ขึ้นชื่อคอลัมน์ภายในอย่าง "value"/"color"
zones_long = weeks.melt(id_vars="สัปดาห์", value_vars=list(HR_ZONE_LABELS),
                        var_name="โซน", value_name="นาที")
zones_long["นาที"] = zones_long["นาที"].round(0)

left, right = st.columns(2)
with left, st.container(border=True, key="surface-train-weekly-km"):
    st.markdown("**ระยะวิ่งรายสัปดาห์**")
    st.caption("ผลรวม km ของกิจกรรมวิ่ง · สัปดาห์เริ่มวันจันทร์")
    st.vega_lite_chart(
        weeks[["สัปดาห์", "ระยะวิ่ง (km)"]],
        weekly_bar_spec(y_col="ระยะวิ่ง (km)", y_title="km", height=CHART_HEIGHT),
        width="stretch",
    )
with right, st.container(border=True, key="surface-train-zones"):
    st.markdown("**เวลาในโซน HR รายสัปดาห์**")
    st.caption("นาทีในแต่ละโซนที่ Garmin นับไว้ ทุกกิจกรรม")
    has_zones = any(column in activities and activities[column].notna().any()
                    for column in HR_ZONE_COLUMNS)
    if has_zones:
        # โซนเป็นลำดับ จึงไล่เฉดสีเดียวอ่อนไปเข้ม ไม่ใช้เขียว-แดงที่อ่านว่า "ดี/อันตราย"
        st.vega_lite_chart(
            zones_long,
            zone_bar_spec(HR_ZONE_LABELS, ZONE_COLORS, height=CHART_HEIGHT),
            width="stretch",
        )
    else:
        st.caption("Garmin ยังไม่ได้ส่งเวลาในโซน HR ของกิจกรรมในช่วงนี้")

load = activities.dropna(subset=["training_load"]) if "training_load" in activities else None
if load is not None and not load.empty:
    with st.container(border=True, key="surface-train-load"):
        st.markdown("**Training Load ต่อกิจกรรม**")
        st.caption("ค่าที่ Garmin คำนวณให้แต่ละกิจกรรม · นาฬิกาบางรุ่นไม่ส่งค่านี้")
        load_frame = pd.DataFrame({
            "วันเวลา": load["start_time_local"],
            "กิจกรรม": [activity_title(row) for _, row in load.iterrows()],
            "Training Load": pd.to_numeric(load["training_load"], errors="coerce"),
        })
        st.vega_lite_chart(
            load_frame,
            activity_load_bar_spec(height=CHART_HEIGHT),
            width="stretch",
        )

with st.container(border=True, key="surface-train-table"):
    st.subheader("กิจกรรมทั้งหมด", anchor=False)
    shown_table = activity_rows(activities)
    empty_optional = [c for c in OPTIONAL_ACTIVITY_COLS
                      if c in shown_table and shown_table[c].isna().all()]
    if empty_optional:
        shown_table = shown_table.drop(columns=empty_optional)
    st.dataframe(
        shown_table, hide_index=True, width="stretch",
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
