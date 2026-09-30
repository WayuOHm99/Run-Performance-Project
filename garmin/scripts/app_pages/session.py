"""หน้า "เซสชัน" — กิจกรรมเดียวแบบละเอียด ตามที่นาฬิกาบันทึก

แสดงเฉพาะช่องที่ Garmin ส่งมากับกิจกรรมนั้น ช่องที่ไม่มีค่าจะไม่ถูกวาด
lap ทุกรอบแสดงตามจริง รวม lap ระยะ 0 m (ตัดสิน 7 ส.ค. 69 — ห้ามกรองด้วยระยะขั้นต่ำ
เพราะเคยลบ interval สั้นทิ้งทั้งเซสชัน)
"""

import pandas as pd
import streamlit as st

from dashboard_context import page_context
from dashboard_data import load_splits
from dashboard_domain import (
    HR_ZONE_COLUMNS,
    HR_ZONE_LABELS,
    activity_title,
    fmt_num,
    fmt_pace,
    fmt_sec,
    garmin_label,
)

ctx = page_context()
activities = ctx.activity_df
CHART_HEIGHT = 220

st.title(f"เซสชัน · {ctx.selected_name}")

if activities.empty:
    st.info("ยังไม่มีกิจกรรมในช่วงนี้", icon=":material/info:")
    st.stop()

candidates = activities.sort_values("start_time_local", ascending=False)
labels = {}
for _, row in candidates.iterrows():
    distance = row.get("distance_m")
    labels[int(row["activity_id"])] = " · ".join(filter(None, [
        row["start_time_local"].strftime("%d/%m/%Y %H:%M"),
        activity_title(row),
        f"{distance / 1000:.2f} km" if pd.notna(distance) and distance > 0 else None,
    ]))
chosen = st.selectbox("กิจกรรม", options=list(labels), format_func=labels.get,
                      key="session_activity")
activity = candidates[candidates["activity_id"] == chosen].iloc[0]


def value(column, unit="", decimals=0):
    raw = activity.get(column)
    return fmt_num(raw, unit, decimals) if pd.notna(raw) else None


def speed(column):
    """Garmin ส่งความเร็วเป็น m/s — แปลงหน่วยเป็น km/h เท่านั้น"""
    raw = pd.to_numeric(activity.get(column), errors="coerce")
    return f"{raw * 3.6:.1f} km/h" if pd.notna(raw) and raw > 0 else None


distance_m = activity.get("distance_m")
has_distance = pd.notna(distance_m) and distance_m > 0
groups = [
    ("ภาพรวม", [
        ("ระยะ", f"{distance_m / 1000:.2f} km" if has_distance else None),
        ("เวลา", fmt_sec(activity.get("duration_sec"))
         if pd.notna(activity.get("duration_sec")) else None),
        ("เวลาเคลื่อนที่", fmt_sec(activity.get("moving_duration_sec"))
         if pd.notna(activity.get("moving_duration_sec")) else None),
        ("เพซเฉลี่ย", fmt_pace(activity.get("avg_pace_min_per_km")) + " /km"
         if has_distance and pd.notna(activity.get("avg_pace_min_per_km")) else None),
        ("HR เฉลี่ย", value("avg_hr", " bpm")),
        ("HR ต่ำสุด", value("min_hr", " bpm")),
        ("HR สูงสุด", value("max_hr", " bpm")),
        ("ความเร็วเฉลี่ย", speed("avg_speed_mps")),
        ("ความเร็วสูงสุด", speed("max_speed_mps")),
        ("ความเร็วปรับความชัน", speed("avg_grade_adjusted_speed_mps")),
        ("แคลอรี่", value("calories", " kcal")),
        ("นาทีหนักปานกลาง", value("moderate_intensity_min", " นาที")),
        ("นาทีหนักมาก", value("vigorous_intensity_min", " นาที")),
    ]),
    ("Garmin ประเมินให้เซสชันนี้", [
        ("Aerobic TE", value("training_effect_aerobic", "", 1)),
        ("Anaerobic TE", value("training_effect_anaerobic", "", 1)),
        ("ผลการซ้อม", garmin_label(activity.get("training_effect_label")) or None),
        ("Training Load", value("training_load")),
        ("VO2max", value("vo2max_value")),
        ("Impact Load", value("impact_load", "", 1)),
        ("Stamina เริ่ม → จบ",
         f"{activity['begin_stamina']:.0f}% → {activity['end_stamina']:.0f}%"
         if pd.notna(activity.get("begin_stamina")) and pd.notna(activity.get("end_stamina"))
         else None),
        ("Body Battery ที่ใช้", value("diff_body_battery")),
        ("เหงื่อ (ประมาณ)", value("sweat_loss_ml", " ml")),
    ]),
    ("ฟอร์มการวิ่ง", [
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
    ("เส้นทางและอากาศ", [
        ("ไต่ขึ้น", value("elevation_gain_m", " m")),
        ("ลดระดับ", value("elevation_loss_m", " m")),
        ("จุดต่ำสุด", value("min_elevation_m", " m")),
        ("จุดสูงสุด", value("max_elevation_m", " m")),
        ("อุณหภูมิ", value("weather_temp_c", " °C")),
        ("ความชื้น", value("weather_humidity", "%")),
        ("ลม", value("weather_wind_kph", " km/h")),
        ("สถานที่", activity.get("location_name")
         if isinstance(activity.get("location_name"), str) else None),
        ("จุดเริ่ม", f"{activity['start_latitude']:.4f}, {activity['start_longitude']:.4f}"
         if pd.notna(activity.get("start_latitude")) and pd.notna(activity.get("start_longitude"))
         else None),
    ]),
]
for title, items in groups:
    items = [(label, shown) for label, shown in items if shown]
    if not items:
        continue
    st.markdown(f"**{title}**")
    with st.container(horizontal=True):
        for label, shown in items:
            st.metric(label, shown, border=True, width=170)

zone_minutes = pd.DataFrame({
    "โซน": list(HR_ZONE_LABELS),
    "นาที": [pd.to_numeric(activity.get(column), errors="coerce") / 60
             for column in HR_ZONE_COLUMNS],
})
splits = load_splits(int(chosen))

left, right = st.columns([1, 2])
with left, st.container(border=True):
    st.markdown("**เวลาในโซน HR**")
    if zone_minutes["นาที"].notna().any():
        st.bar_chart(zone_minutes, x="โซน", y="นาที", x_label="", y_label="นาที",
                     height=CHART_HEIGHT, sort=False)
    else:
        st.caption("Garmin ไม่ได้ส่งเวลาในโซนของกิจกรรมนี้")
with right, st.container(border=True):
    st.markdown("**HR ต่อ lap**")
    if not splits.empty and splits["avg_hr"].notna().any():
        hr = splits.assign(Lap=splits["split_num"].astype(int).astype(str))
        st.line_chart(hr.rename(columns={"avg_hr": "HR เฉลี่ย", "max_hr": "HR สูงสุด"}),
                      x="Lap", y=["HR เฉลี่ย", "HR สูงสุด"], x_label="lap",
                      y_label="bpm", height=CHART_HEIGHT)
    else:
        st.caption("ไม่มีข้อมูล lap ของกิจกรรมนี้")

st.subheader("Lap ทั้งหมด", anchor=False)
if splits.empty:
    st.caption("Garmin ไม่ได้ส่งข้อมูล lap ของกิจกรรมนี้ (หรือยังไม่ถึงรอบ full sync 08:00/21:00)")
else:
    table = pd.DataFrame({
        "Lap": splits["split_num"].astype(int),
        "ระยะ (m)": splits["distance_m"].round(0),
        "เวลา": splits["duration_sec"].map(fmt_sec),
        "เพซ /km": splits["avg_pace_min_km"].map(fmt_pace),
        "HR เฉลี่ย": splits["avg_hr"],
        "HR สูงสุด": splits["max_hr"],
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
        "ชนิด": splits.get("intensity_type").map(garmin_label)
                if "intensity_type" in splits else None,
    })
    st.dataframe(table.dropna(axis=1, how="all"), hide_index=True, width="stretch",
                 column_config={"ระยะ (m)": st.column_config.NumberColumn(format="%d"),
                                "HR เฉลี่ย": st.column_config.NumberColumn(format="%d"),
                                "HR สูงสุด": st.column_config.NumberColumn(format="%d"),
                                "Cadence": st.column_config.NumberColumn(format="%d"),
                                "Cadence สูงสุด": st.column_config.NumberColumn(format="%d")})
