"""หน้า "เซสชัน" — กิจกรรมเดียวแบบละเอียด ตามที่นาฬิกาบันทึก

แสดงเฉพาะช่องที่ Garmin ส่งมากับกิจกรรมนั้น ช่องที่ไม่มีค่าจะไม่ถูกวาด
lap ทุกรอบแสดงตามจริง รวม lap ระยะ 0 m (ตัดสิน 7 ส.ค. 69 — ห้ามกรองด้วยระยะขั้นต่ำ
เพราะเคยลบ interval สั้นทิ้งทั้งเซสชัน)
"""

import pandas as pd
import streamlit as st
from dashboard_charts import session_lap_hr_spec, session_zone_bar_spec
from dashboard_context import (
    chart_header,
    page_context,
    page_lead,
    render_metric_grid,
    section_heading,
)
from dashboard_data import load_splits
from dashboard_domain import (
    HR_ZONE_COLUMNS,
    HR_ZONE_LABELS,
    activity_title,
    fmt_num,
    fmt_pace,
    fmt_sec,
    garmin_label,
    value_of,
)

ctx = page_context()
activities = ctx.activity_df
CHART_HEIGHT = 225
ZONE_COLORS = ["#c7d7fe", "#84adff", "#3b82f6", "#155eef", "#0b2545"]

st.title(f"เซสชัน · {ctx.selected_name}")
page_lead(
    f"ข้อมูลเชิงลึกรายกิจกรรม โซนชีพจร และตารางรายรอบ (Lap) · พบ {len(activities)} กิจกรรมในช่วง "
    f"{ctx.start_date:%d/%m/%Y} – {ctx.end_date:%d/%m/%Y}"
)

if activities.empty:
    st.info("ยังไม่มีกิจกรรมในช่วงนี้", icon=":material/info:")
    st.stop()

candidates = activities.sort_values("start_time_local", ascending=False, na_position="last")
labels = {}
for _, row in candidates.iterrows():
    distance = row.get("distance_m")
    start_ts = row.get("start_time_local")
    labels[int(row["activity_id"])] = " · ".join(filter(None, [
        start_ts.strftime("%d/%m/%Y %H:%M") if pd.notna(start_ts) else None,
        activity_title(row),
        f"{distance / 1000:.2f} km" if pd.notna(distance) and distance > 0 else None,
    ]))

option_ids = list(labels)
if st.session_state.get("session_activity") not in labels:
    st.session_state["session_activity"] = option_ids[0]


def _step_session(delta: int):
    current = st.session_state.get("session_activity", option_ids[0])
    idx = option_ids.index(current) if current in option_ids else 0
    next_idx = max(0, min(len(option_ids) - 1, idx + delta))
    st.session_state["session_activity"] = option_ids[next_idx]


with st.container(key="sess-nav"):
    chosen = st.selectbox("เลือกกิจกรรม", options=option_ids, format_func=labels.get,
                          key="session_activity")
    cur_idx = option_ids.index(chosen)
    with st.container(horizontal=True, vertical_alignment="center"):
        st.button("เซสชันใหม่กว่า", icon=":material/chevron_left:", on_click=_step_session,
                  args=(-1,), key="sess-newer", disabled=cur_idx == 0)
        st.button("เซสชันเก่ากว่า", icon=":material/chevron_right:", on_click=_step_session,
                  args=(1,), key="sess-older", disabled=cur_idx >= len(option_ids) - 1)
        st.badge(f"รายการที่ {cur_idx + 1} จาก {len(option_ids)}", icon=":material/list:", color="gray")

activity = candidates[candidates["activity_id"] == chosen].iloc[0]


def value(column, unit="", decimals=0):
    raw = value_of(activity, column)
    return fmt_num(raw, unit, decimals) if raw is not None else None


def speed(column):
    """Garmin ส่งความเร็วเป็น m/s — แปลงหน่วยเป็น km/h เท่านั้น"""
    raw = value_of(activity, column)
    return f"{float(raw) * 3.6:.1f} km/h" if raw is not None and float(raw) > 0 else None


distance_m = value_of(activity, "distance_m")
has_distance = distance_m is not None and float(distance_m) > 0
duration_sec = value_of(activity, "duration_sec")
moving_duration_sec = value_of(activity, "moving_duration_sec")
avg_pace = value_of(activity, "avg_pace_min_per_km")
steps_val = value_of(activity, "steps")
begin_stamina = value_of(activity, "begin_stamina")
end_stamina = value_of(activity, "end_stamina")
start_lat = value_of(activity, "start_latitude")
start_lon = value_of(activity, "start_longitude")

start_stamp = activity.get("start_time_local")
when_sub = (
    f"{activity_title(activity)} · เริ่ม {start_stamp:%d/%m/%Y %H:%M} น."
    if pd.notna(start_stamp) else activity_title(activity)
)

hero_items = [
    item for item in [
        ("ระยะทาง", f"{float(distance_m) / 1000:.2f} km" if has_distance else None),
        ("เวลารวม", fmt_sec(duration_sec) if duration_sec is not None else None),
        ("เพซเฉลี่ย", fmt_pace(avg_pace) + " /km"
         if has_distance and avg_pace is not None and float(avg_pace) > 0 else None),
        ("HR เฉลี่ย", value("avg_hr", " bpm")),
    ]
    if item[1]
]
if hero_items:
    section_heading("สรุปตัวเลขหลักของเซสชัน", when_sub)
    render_metric_grid(hero_items, cols_per_row=4, border=True)

groups = [
    ("overview", "ความเร็ว ชีพจร และพลังงาน", "ค่าพื้นฐานที่นาฬิกาวัดตลอดเซสชัน", [
        ("เวลาเคลื่อนที่", fmt_sec(moving_duration_sec)
         if moving_duration_sec is not None else None),
        ("HR ต่ำสุด", value("min_hr", " bpm")),
        ("HR สูงสุด", value("max_hr", " bpm")),
        ("ความเร็วเฉลี่ย", speed("avg_speed_mps")),
        ("ความเร็วสูงสุด", speed("max_speed_mps")),
        ("ความเร็วปรับความชัน", speed("avg_grade_adjusted_speed_mps")),
        ("ก้าว", f"{round(float(steps_val)):,}"
         if steps_val is not None and float(steps_val) > 0 else None),
        ("แคลอรี่", value("calories", " kcal")),
        ("นาทีหนักปานกลาง", value("moderate_intensity_min", " นาที")),
        ("นาทีหนักมาก", value("vigorous_intensity_min", " นาที")),
    ]),
    ("garmin-eval", "ผลประเมินเซสชันจาก Garmin", "คะแนนผลกระทบการซ้อมและพลังงานที่นาฬิกาประเมินหลังจบกิจกรรม", [
        ("Aerobic TE", value("training_effect_aerobic", "", 1)),
        ("Anaerobic TE", value("training_effect_anaerobic", "", 1)),
        ("ผลการซ้อม", garmin_label(activity.get("training_effect_label")) or None),
        ("Training Load", value("training_load")),
        ("VO2max", value("vo2max_value")),
        ("Impact Load", value("impact_load", "", 1)),
        ("Stamina เริ่ม → จบ",
         f"{float(begin_stamina):.0f}% → {float(end_stamina):.0f}%"
         if begin_stamina is not None and end_stamina is not None
         else None),
        ("Body Battery ที่ใช้", value("diff_body_battery")),
        ("เหงื่อ (ประมาณ)", value("sweat_loss_ml", " ml")),
    ]),
    ("dynamics", "ฟอร์มการวิ่งและกำลังวัตต์ (Running Dynamics & Power)", "ข้อมูลท่าทางการวิ่งจากเซนเซอร์นาฬิกาหรือสายคาดอก", [
        ("Cadence เฉลี่ย", value("avg_cadence", " spm")),
        ("Cadence สูงสุด", value("max_cadence", " spm")),
        ("Stride Length", value("avg_stride_length_cm", " cm")),
        ("Ground Contact", value("avg_ground_contact_time_ms", " ms")),
        ("Vertical Oscillation", value("avg_vertical_oscillation_cm", " cm", 1)),
        ("Vertical Ratio", value("avg_vertical_ratio", "%", 1)),
        ("Power เฉลี่ย", value("avg_power", " W")),
        ("Power สูงสุด", value("max_power", " W")),
        ("Normalized Power", value("normalized_power", " W")),
    ]),
    ("route-weather", "ความชันเส้นทางและสภาพอากาศ", "ระดับความสูงจาก GPS/บารอมิเตอร์ และสภาพอากาศขณะเริ่มซ้อม", [
        ("ไต่ขึ้น", value("elevation_gain_m", " m")),
        ("ลดระดับ", value("elevation_loss_m", " m")),
        ("จุดต่ำสุด", value("min_elevation_m", " m")),
        ("จุดสูงสุด", value("max_elevation_m", " m")),
        ("อุณหภูมิ", value("weather_temp_c", " °C")),
        ("อุณหภูมิที่รู้สึก", value("weather_apparent_temp_c", " °C")),
        ("ความชื้น", value("weather_humidity", "%")),
        ("ลม", value("weather_wind_kph", " km/h")),
        ("สถานที่", activity.get("location_name")
         if isinstance(activity.get("location_name"), str) else None,
         f"พิกัดเริ่ม {float(start_lat):.4f}, {float(start_lon):.4f}"
         if start_lat is not None and start_lon is not None else None),
        ("จุดเริ่ม",
         f"{float(start_lat):.3f}, {float(start_lon):.3f}"
         if (not isinstance(activity.get("location_name"), str) or not activity.get("location_name"))
         and start_lat is not None and start_lon is not None
         else None),
    ]),
]

section_heading("รายละเอียดเชิงลึกจากนาฬิกา", "แสดงเฉพาะหมวดและช่องที่อุปกรณ์ส่งมากับกิจกรรมนี้")

for key_slug, title, guide, items in groups:
    items = [item for item in items if item[1]]
    if not items:
        continue
    with st.container(border=True, key=f"surface-sess-{key_slug}"):
        chart_header(st, title, guide)
        render_metric_grid(items, cols_per_row=4, border=True)

zone_minutes = pd.DataFrame({
    "โซน": list(HR_ZONE_LABELS),
    "นาที": [(pd.to_numeric(activity.get(column), errors="coerce") / 60)
             for column in HR_ZONE_COLUMNS],
})
zone_minutes["นาที"] = zone_minutes["นาที"].round(1)
splits = load_splits(int(chosen))

section_heading("โซนชีพจรและกราฟรายรอบ (Laps)", "แสดงทุกรอบตามที่นาฬิกาบันทึก รวมถึงรอบกดพักหรือระยะ 0 m")
left, right = st.columns([1, 2])
with left, st.container(border=True, key="surface-sess-zones"):
    has_sess_zones = zone_minutes["นาที"].notna().any()
    total_z = float(zone_minutes["นาที"].dropna().sum()) if has_sess_zones else 0.0
    chart_header(
        st,
        "เวลาในโซนชีพจร (Z1–Z5)",
        "นาทีในแต่ละโซนชีพจรของเซสชันนี้ · สีอ่อนไปเข้มคือ Z1 (โซนต่ำ) → Z5 (โซนสูง)",
        f"รวม {total_z:,.1f} นาที" if has_sess_zones and total_z > 0 else None,
    )
    if has_sess_zones:
        st.vega_lite_chart(
            zone_minutes,
            session_zone_bar_spec(HR_ZONE_LABELS, ZONE_COLORS, height=CHART_HEIGHT),
            width="stretch",
        )
    else:
        st.caption("Garmin ไม่ได้ส่งเวลาในโซนของกิจกรรมนี้")

with right, st.container(border=True, key="surface-sess-lap-hr"):
    has_lap_hr = not splits.empty and splits["avg_hr"].notna().any()
    max_lap_hr = pd.to_numeric(splits.get("max_hr"), errors="coerce").max() if has_lap_hr else None
    lap_stat = (
        f"{len(splits)} รอบ"
        + (f" · สูงสุด {max_lap_hr:.0f} bpm" if pd.notna(max_lap_hr) else "")
        if has_lap_hr else None
    )
    chart_header(
        st,
        "ชีพจรเฉลี่ยและสูงสุดรายรอบ (Lap HR)",
        "เส้นน้ำเงิน = HR เฉลี่ยของรอบ · เส้นส้ม = HR สูงสุดของรอบ (ชี้ที่จุดเพื่อดูระยะและเพซของรอบนั้น)",
        lap_stat,
    )
    if has_lap_hr:
        ordered_splits = splits.assign(
            _lap_int=pd.to_numeric(splits["split_num"], errors="coerce")
        ).sort_values("_lap_int", kind="stable")
        lap_labels = ordered_splits["_lap_int"].astype("Int64").astype(str)
        dist_labels = pd.to_numeric(ordered_splits.get("distance_m"), errors="coerce").map(
            lambda d: f"{d:,.0f} m" if pd.notna(d) else "–"
        )
        pace_labels = ordered_splits.get(
            "avg_pace_min_km", pd.Series(index=ordered_splits.index, dtype="float64")
        ).map(lambda p: f"{fmt_pace(p)} /km" if fmt_pace(p) != "–" else "–")
        hr_base = pd.DataFrame({
            "Lap": lap_labels,
            "ระยะรอบ": dist_labels,
            "เพซรอบ": pace_labels,
            "HR เฉลี่ย": pd.to_numeric(ordered_splits.get("avg_hr"), errors="coerce"),
            "HR สูงสุด": pd.to_numeric(ordered_splits.get("max_hr"), errors="coerce"),
        })
        hr_long = hr_base.melt(
            id_vars=["Lap", "ระยะรอบ", "เพซรอบ"],
            value_vars=["HR เฉลี่ย", "HR สูงสุด"],
            var_name="รายการ",
            value_name="bpm",
        )
        st.vega_lite_chart(
            hr_long,
            session_lap_hr_spec(height=CHART_HEIGHT, extra_tips=("ระยะรอบ", "เพซรอบ")),
            width="stretch",
        )
    else:
        st.caption("ไม่มีข้อมูลชีพจรรายรอบของกิจกรรมนี้")

with st.container(border=True, key="surface-sess-laps"):
    chart_header(
        st,
        "ตาราง Lap ทั้งหมด",
        "ข้อมูลดิบทุกรอบตามลำดับที่นาฬิกาบันทึก",
        f"{len(splits)} รอบ" if not splits.empty else None,
    )
    if splits.empty:
        st.caption("Garmin ไม่ได้ส่งข้อมูล lap ของกิจกรรมนี้ (หรือยังไม่ถึงรอบ full sync 08:00/21:00)")
    else:
        def _fmt_lap(series, fn):
            if series is None:
                return None
            return series.map(
                lambda v: None if v is None or pd.isna(v) else (
                    None if (out := fn(v)) in ("", "–") else out
                )
            )

        table = pd.DataFrame({
            "Lap": pd.to_numeric(splits["split_num"], errors="coerce").astype("Int64"),
            "ระยะ (m)": splits["distance_m"].round(0),
            "เวลา": _fmt_lap(splits.get("duration_sec"), fmt_sec),
            "เพซ /km": _fmt_lap(splits.get("avg_pace_min_km"), fmt_pace),
            "HR เฉลี่ย": splits.get("avg_hr"),
            "HR สูงสุด": splits.get("max_hr"),
            "km/h": (pd.to_numeric(splits.get("avg_speed_mps"), errors="coerce") * 3.6).round(1),
            "Cadence": splits.get("avg_cadence"),
            "Cadence สูงสุด": splits.get("max_cadence"),
            "Power": splits.get("avg_power"),
            "Power สูงสุด": splits.get("max_power"),
            "NP": splits.get("normalized_power"),
            "Stride (cm)": splits.get("avg_stride_length_cm"),
            "GCT (ms)": splits.get("ground_contact_time_ms"),
            "VO (cm)": splits.get("vertical_oscillation_cm"),
            "V.Ratio (%)": splits.get("vertical_ratio"),
            "ไต่ (m)": splits.get("elevation_gain_m"),
            "ลด (m)": splits.get("elevation_loss_m"),
            "ชนิด": _fmt_lap(splits.get("intensity_type"), garmin_label)
                    if "intensity_type" in splits else None,
        })
        st.dataframe(table.dropna(axis=1, how="all"), hide_index=True, width="stretch",
                     column_config={"ระยะ (m)": st.column_config.NumberColumn(format="%d"),
                                    "HR เฉลี่ย": st.column_config.NumberColumn(format="%d"),
                                    "HR สูงสุด": st.column_config.NumberColumn(format="%d"),
                                    "Cadence": st.column_config.NumberColumn(format="%d"),
                                    "Cadence สูงสุด": st.column_config.NumberColumn(format="%d")})
