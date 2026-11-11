"""หน้า "การซ้อม" — ซ้อมไปเท่าไหร่ในช่วงที่เลือก

ตัวเลขบนหน้านี้เป็นผลรวมตรง ๆ ของค่าที่ Garmin ส่งมาต่อกิจกรรม (ระยะ เวลา
วินาทีในโซน HR) ไม่มีการจัดความหนักเอง ไม่มีค่าเฉลี่ยเทียบฐาน และไม่มีเป้าสัดส่วน
โซน HR คือโซนที่ตั้งไว้ในนาฬิกา/Garmin Connect ของนักกีฬาแต่ละคน
"""

import pandas as pd
import streamlit as st
from dashboard_charts import activity_load_bar_spec, weekly_bar_spec, zone_bar_spec
from dashboard_context import (
    chart_header,
    page_context,
    page_lead,
    render_metric_grid,
    request_page,
    section_heading,
)
from dashboard_domain import (
    HR_ZONE_COLUMNS,
    HR_ZONE_LABELS,
    RUN_TYPES,
    activity_rows,
    activity_title,
    fmt_hours,
    fmt_num,
    series_range_stat,
    weekly_totals,
)

ctx = page_context()
activities = ctx.activity_df
CHART_HEIGHT = 240
ZONE_COLORS = ["#c7d7fe", "#84adff", "#3b82f6", "#155eef", "#0b2545"]
OPTIONAL_ACTIVITY_COLS = ("HR เฉลี่ย", "HR สูงสุด", "Training Effect", "Training Load")

st.title(f"การซ้อม · {ctx.selected_name}")
span_days = max(1, (ctx.end_date - ctx.start_date).days + 1)
page_lead(
    f"ผลรวมระยะวิ่ง เวลาซ้อม และเวลาในโซนชีพจรจากทุกกิจกรรมที่บันทึก · ช่วงวันที่ "
    f"{ctx.start_date:%d/%m/%Y} – {ctx.end_date:%d/%m/%Y} ({span_days} วัน)"
)

if activities.empty:
    st.info("ยังไม่มีกิจกรรมในช่วงนี้", icon=":material/info:")
    st.stop()

runs = activities[activities["activity_type"].isin(RUN_TYPES)]
distance = pd.to_numeric(runs["distance_m"], errors="coerce").sum() / 1000
duration = pd.to_numeric(activities["duration_sec"], errors="coerce").sum()
days_trained = activities["start_time_local"].dt.date.nunique()

section_heading("สรุปปริมาณซ้อมรวมในช่วงที่เลือก", "บวกตรงจากทุกกิจกรรมที่ซิงก์เข้าฐานข้อมูลแล้ว")
render_metric_grid(
    [
        ("ระยะวิ่งรวม", f"{distance:,.1f} km", f"{len(runs)} กิจกรรมวิ่ง"),
        ("เวลาซ้อมรวม", fmt_hours(duration), "รวมทุกชนิดกีฬา", "รวมวิ่ง เวท ปั่น และคาร์ดิโอทั้งหมด"),
        ("จำนวนกิจกรรม", f"{len(activities)}", "รายการที่บันทึก",
         "Garmin อาจบันทึก warm-up งานหลัก และ cool-down แยกเป็นคนละรายการ"),
        ("วันที่ซ้อม", f"{days_trained} วัน", f"จากทั้งหมด {span_days} วัน"),
    ],
    cols_per_row=4,
    border=True,
)

section_heading("ปริมาณรายสัปดาห์และโหลดต่อเซสชัน", "นับสัปดาห์เริ่มวันจันทร์ · โซนชีพจรอ้างอิงตามที่ตั้งไว้ในนาฬิกา")

weeks = weekly_totals(activities, ctx.start_date, ctx.end_date)
week_fmt = "%d/%m/%y" if weeks["week"].dt.year.nunique() > 1 else "%d/%m"
weeks["สัปดาห์"] = weeks["week"].dt.strftime(week_fmt)
weeks = weeks.rename(columns={"run_km": "ระยะวิ่ง (km)"})
numeric_cols = ["ระยะวิ่ง (km)", "hours"]
weeks[numeric_cols] = weeks[numeric_cols].round(1)
zones_long = weeks.melt(id_vars="สัปดาห์", value_vars=list(HR_ZONE_LABELS),
                        var_name="โซน", value_name="นาที")
zones_long["นาที"] = zones_long["นาที"].round(0)

max_week_km = float(weeks["ระยะวิ่ง (km)"].max()) if not weeks.empty else 0.0
km_stat = f"รวม {distance:,.1f} km · สูงสุด {max_week_km:,.1f} km/สัปดาห์"

left, right = st.columns(2)
with left, st.container(border=True, key="surface-train-weekly-km"):
    chart_header(
        st,
        "ระยะวิ่งรายสัปดาห์",
        "กิโลเมตรรวมเฉพาะกิจกรรมวิ่งในแต่ละสัปดาห์ (จันทร์–อาทิตย์) · ป้ายแกนล่างคือวันจันทร์ต้นสัปดาห์",
        km_stat,
    )
    st.vega_lite_chart(
        weeks[["สัปดาห์", "ระยะวิ่ง (km)"]],
        weekly_bar_spec(y_col="ระยะวิ่ง (km)", y_title="km", height=CHART_HEIGHT),
        width="stretch",
    )

with right, st.container(border=True, key="surface-train-zones"):
    has_zones = any(column in activities and activities[column].notna().any()
                    for column in HR_ZONE_COLUMNS)
    total_zone_min = float(zones_long["นาที"].dropna().sum()) if has_zones else 0.0
    zone_stat = f"รวม {total_zone_min:,.0f} นาที" if has_zones and total_zone_min > 0 else None
    chart_header(
        st,
        "เวลาในโซนชีพจรรายสัปดาห์ (HR Zones)",
        "นาทีรวมทุกกิจกรรม · สีอ่อนไปเข้มคือ Z1 (โซนต่ำสุด) ไล่ถึง Z5 (โซนสูงสุด) ตามที่ตั้งในนาฬิกา",
        zone_stat,
    )
    if has_zones:
        st.vega_lite_chart(
            zones_long,
            zone_bar_spec(HR_ZONE_LABELS, ZONE_COLORS, height=CHART_HEIGHT),
            width="stretch",
        )
    else:
        st.caption("Garmin ยังไม่ได้ส่งเวลาในโซน HR ของกิจกรรมในช่วงนี้")

load = activities.dropna(subset=["training_load"]) if "training_load" in activities else None
if load is not None and not load.empty:
    ordered_load = load.sort_values("start_time_local", ascending=True, na_position="last", kind="stable")
    load_vals = pd.to_numeric(ordered_load["training_load"], errors="coerce")
    load_when = ordered_load["start_time_local"]
    load_frame = pd.DataFrame({
        "รหัสเวลา": [
            f"{ts.strftime('%d/%m') if pd.notna(ts) else '--/--'} #{idx}"
            for idx, ts in enumerate(load_when, start=1)
        ],
        "วันเวลาแสดง": [
            ts.strftime("%d/%m/%Y %H:%M") if pd.notna(ts) else "–"
            for ts in load_when
        ],
        "กิจกรรม": [activity_title(row) for _, row in ordered_load.iterrows()],
        "Training Load": load_vals.to_numpy(),
    })
    with st.container(border=True, key="surface-train-load"):
        chart_header(
            st,
            "โหลดการซ้อมรายกิจกรรม (Training Load)",
            "ค่า EPOC Training Load ที่ Garmin คำนวณให้แต่ละเซสชัน เรียงจากซ้ายไปขวาตามลำดับเวลาซ้อม",
            series_range_stat(load_frame["Training Load"]),
        )
        st.vega_lite_chart(
            load_frame,
            activity_load_bar_spec(height=CHART_HEIGHT),
            width="stretch",
        )

with st.container(border=True, key="surface-train-table"):
    with st.container(horizontal=True, vertical_alignment="center"):
        st.subheader("รายการกิจกรรมทั้งหมด", anchor=False)
        st.button(
            "เปิดดูรายรอบในหน้าเซสชัน",
            icon=":material/timer:",
            key="train-open-session",
            on_click=request_page,
            args=("app_pages/session.py",),
        )
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
                format="%.1f", help="Aerobic Training Effect ของ Garmin (0.0–5.0)"),
            "Training Load": st.column_config.NumberColumn(format="%d"),
        },
    )
    st.caption(f"รวม {fmt_num(len(activities))} กิจกรรม · เลือกดูเพซและชีพจรรายรอบ (Lap) ได้ที่หน้า \"เซสชัน\"")
