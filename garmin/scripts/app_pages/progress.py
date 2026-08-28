"""หน้า "ความก้าวหน้า" ของ Coach Dashboard"""

import datetime
import math

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from dashboard_domain import (
    field_freshness,
    fmt_num,
    fmt_pace,
    fmt_sec,
    latest_field,
    personal_record_rows,
)

from dashboard_view import (
    SERIES_COLORS,
)

from dashboard_data import (
    load_body_composition,
    load_latest_lt,
    load_personal_records,
    load_race_predictions,
)

from dashboard_context import page_context

_ctx = page_context()
availability_by_key = _ctx.availability_by_key
athlete_id = _ctx.athlete_id
start_date = _ctx.start_date
end_date = _ctx.end_date
wellness_df = _ctx.wellness_df
wellness_plot_df = _ctx.wellness_plot_df
today = _ctx.today
selected_name = _ctx.selected_name
selected_anchor = _ctx.selected_anchor


st.header(f"ความก้าวหน้า — {selected_name}", anchor=f"progress-{selected_anchor}")
st.caption(
    f"แนวโน้มระหว่าง {start_date.strftime('%d/%m/%Y')}–{end_date.strftime('%d/%m/%Y')} · "
    "ใช้ค่าจาก Garmin ดูทิศทาง ส่วนค่าสัมบูรณ์ให้ยึดผลเทสจริง"
)

advanced_summary = availability_by_key["advanced"]
advanced_performance_missing_message = None
if advanced_summary["state"] == "never_received":
    advanced_performance_missing_message = (
        "Garmin Connect ยังไม่เคยส่ง VO2max, Fitness Age, Endurance/Hill Score "
        "หรือ Lactate Threshold ให้บัญชีนี้"
    )
elif advanced_summary["state"] == "outside_range":
    advanced_performance_missing_message = (
        "มีประวัติเมตริกสมรรถนะขั้นสูง แต่ไม่มีค่าในช่วงวันที่ที่เลือก"
    )
elif advanced_summary["state"] == "partial":
    advanced_performance_missing_message = (
        f"Garmin Connect เคยส่งเมตริกสมรรถนะขั้นสูง "
        f"{advanced_summary['history_available']}/{advanced_summary['total_fields']} ชนิด; "
        "ส่วนที่ไม่แสดงคือค่าที่บัญชีนี้ยังไม่เคยได้รับ"
    )
# หนึ่งหน้า หนึ่งกล่อง "ของที่ยังไม่มี" — จองที่ไว้บนสุดแล้วเติมตอนจบ
# เดิมทุกหัวข้อที่ว่างขึ้นกล่องของตัวเอง นาฬิกาที่ไม่ส่งเมตริกขั้นสูงจึงเจอ
# กล่องสีหกใบพูดเรื่องเดียวกัน ทั้งที่กล่องบนสุดสรุปไว้หมดแล้ว
data_gap_slot = st.empty()
missing_here = []

# ---------------- VO2max trend ----------------
vo2 = (wellness_df.dropna(subset=["vo2max_trend"])
       if "vo2max_trend" in wellness_df else wellness_df.iloc[0:0])
# Fitness Age อ่านจาก wellness_df เต็ม ไม่ใช่จาก vo2 ที่กรอง vo2max_trend มาแล้ว —
# คนละ endpoint กัน (extras เขียน fitness_age ให้วันล่าสุดวันเดียว ส่วน vo2max_trend
# ขึ้นเฉพาะวันที่มีวิ่ง outdoor) ถ้าอ่านจาก vo2 ค่าจะหายทุกครั้งที่วันล่าสุดไม่ได้วิ่ง
_fit_age = (wellness_df["fitness_age"].dropna()
            if "fitness_age" in wellness_df else pd.Series(dtype=float))
if not vo2.empty or not _fit_age.empty:
    with st.container(horizontal=True):
        if not vo2.empty:
            # Garmin คำนวณ VO2max ใหม่เฉพาะวันที่วิ่ง GPS นอกลู่ นักกีฬาที่วิ่งลู่
            # เป็นหลักจึงเห็นค่าเดิมค้างเป็นเดือน (P'kao ค้าง 26 วันเมื่อ 26 ส.ค. 69)
            # การ์ดต้องบอกวันที่ของค่านั้น และห้ามเทียบกับตัวเองแล้วขึ้น +0.0
            first_v, last_v = vo2["vo2max_trend"].iloc[0], vo2["vo2max_trend"].iloc[-1]
            vo2_snap = latest_field(wellness_df, "vo2max_trend")
            vo2_delta = (f"{last_v - first_v:+.1f} เทียบต้นช่วง"
                         if len(vo2) > 1 else "มีค่าเดียวในช่วงนี้")
            st.metric("VO2max ล่าสุด (Garmin)", f"{last_v:.1f}",
                      delta=vo2_delta,
                      delta_color="normal" if len(vo2) > 1 else "off",
                      border=True,
                      help=("Garmin อัปเดตเฉพาะวันที่มีวิ่ง GPS นอกลู่ · "
                            + field_freshness(vo2_snap, today)))
        if not _fit_age.empty:
            st.metric("Fitness Age", fmt_num(_fit_age.iloc[-1]), border=True)
if not vo2.empty:
    # ต่างจากกราฟสุขภาพรายวันตรงที่ connectgaps=True: Garmin คำนวณ VO2max ใหม่เฉพาะ
    # วันที่มีวิ่ง GPS เข้าเกณฑ์ (get_max_metrics ตอบว่างเปล่าในวันอื่น — ตรวจแล้ว
    # 18 ส.ค. 69) ค่าไม่ได้หายไปในวันที่ไม่ได้คำนวณ เส้นขาดเป็นท่อนจึงสื่อผิด
    # marker ยังอยู่เฉพาะวันที่ Garmin วัดจริง เส้นแค่เชื่อมจุดที่มีจริงเข้าด้วยกัน
    fig_vo2 = go.Figure(go.Scatter(
        x=wellness_plot_df["calendar_date"], y=wellness_plot_df["vo2max_trend"],
        mode="lines+markers", name="VO2max", connectgaps=True,
        hovertemplate="%{x|%d %b}<br>VO2max: %{y:.1f}<extra></extra>",
    ))
    fig_vo2.update_layout(
        title="แนวโน้ม VO2max (Garmin อัปเดตเฉพาะวันที่มีวิ่ง GPS)",
        xaxis_title="วันที่", yaxis_title="VO2max", showlegend=False,
    )
    st.plotly_chart(fig_vo2, width="stretch")
else:
    missing_here.append("VO2max (Garmin อัปเดตเฉพาะวันที่มีวิ่ง GPS)")

# ---------------- Body composition ----------------
# endpoint นี้มักมีข้อมูลห่าง ๆ และอาจอยู่นอกช่วง 30 วันที่เลือก จึงแสดงค่าล่าสุด
# จากประวัติทั้งหมด พร้อมวันที่จริงของแต่ละ field แทนการทำให้ค่าหายจาก dashboard.
body_composition = load_body_composition(athlete_id)
body_fields = [
    ("weight_kg", "น้ำหนัก", " kg", "{:.1f}"),
    ("bmi", "BMI", "", "{:.1f}"),
    ("body_fat_pct", "ไขมันในร่างกาย", "%", "{:.1f}"),
]
body_latest = []
if not body_composition.empty:
    for column, label, unit, number_format in body_fields:
        valid = body_composition.dropna(subset=[column])
        if not valid.empty:
            row = valid.iloc[-1]
            body_latest.append((
                label,
                number_format.format(row[column]) + unit,
                row["calendar_date"],
            ))
if not body_latest:
    missing_here.append("น้ำหนัก, BMI และเปอร์เซ็นต์ไขมัน")
else:
    st.subheader("องค์ประกอบร่างกายจาก Garmin")
    with st.container(horizontal=True):
        for label, value, measured_at in body_latest:
            st.metric(
                label,
                value,
                delta=(measured_at.strftime("%d/%m/%Y")
                       if pd.notna(measured_at) else None),
                delta_color="off",
                border=True,
            )
    body_history = body_composition.rename(columns={
        "calendar_date": "วันที่",
        "weight_kg": "น้ำหนัก (kg)",
        "bmi": "BMI",
        "body_fat_pct": "ไขมัน (%)",
    })
    with st.expander("ประวัติองค์ประกอบร่างกาย", icon=":material/monitor_weight:"):
        st.dataframe(
            body_history,
            hide_index=True,
            column_config={
                "วันที่": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "น้ำหนัก (kg)": st.column_config.NumberColumn(format="%.1f"),
                "BMI": st.column_config.NumberColumn(format="%.1f"),
                "ไขมัน (%)": st.column_config.NumberColumn(format="%.1f"),
            },
        )

# ---------------- Race predictions ----------------
preds = load_race_predictions(athlete_id, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
if preds.empty:
    missing_here.append("เวลาการแข่งขันที่ Garmin คาดการณ์")
else:
    st.subheader("เวลาการแข่งขันที่ Garmin คาดการณ์")
    race_cols = [("time_5k_sec", "5K"), ("time_10k_sec", "10K"),
                 ("time_half_sec", "Half"), ("time_full_sec", "Marathon")]
    with st.container(horizontal=True):
        for col, label in race_cols:
            # ใช้ค่าล่าสุด "ที่มีจริง" ต่อคอลัมน์ — แถววันปัจจุบันมักเป็น NULL
            # (Garmin ยังไม่คำนวณของวันใหม่ตอน sync เช้า)
            s = preds[col].dropna()
            cur = s.iloc[-1] if not s.empty else float("nan")
            base = s.iloc[0] if len(s) >= 2 else float("nan")
            delta_s = cur - base if pd.notna(cur) and pd.notna(base) else float("nan")
            st.metric(label, fmt_sec(cur),
                      delta=(f"{delta_s:+.0f} วิ เทียบต้นช่วง" if pd.notna(delta_s) else None),
                      delta_color="inverse", border=True)  # เวลาลด = ดีขึ้น (เขียว)
    fig_pred = go.Figure()
    for col, label, color in [("time_5k_sec", "5K", SERIES_COLORS["time_5k_sec"]),
                             ("time_10k_sec", "10K", SERIES_COLORS["time_10k_sec"])]:
        if preds[col].notna().any():
            fig_pred.add_trace(go.Scatter(
                x=preds["calendar_date"], y=preds[col], mode="lines", name=label,
                line=dict(color=color, width=2),
                customdata=[fmt_sec(v) for v in preds[col]],
                hovertemplate="%{x|%d %b}<br>" + label + ": %{customdata}<extra></extra>"))
    fig_pred.update_layout(
        title="แนวโน้มคาดการณ์ 5K / 10K (ยิ่งต่ำยิ่งเร็ว)",
        yaxis=dict(title="เวลา"), xaxis=dict(title="วันที่"), hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02))
    # แกน Y เป็น M:SS อ่านง่าย (แทนวินาทีดิบ) — step ปรับตามช่วงข้อมูล
    all_t = pd.concat([preds["time_5k_sec"], preds["time_10k_sec"]]).dropna()
    if not all_t.empty:
        lo, hi = float(all_t.min()), float(all_t.max())
        rng = max(hi - lo, 1.0)
        step = 30 if rng <= 300 else (60 if rng <= 900 else 300)
        start = int(lo // step) * step
        tickvals = list(range(start, int(hi) + step + 1, step))
        fig_pred.update_yaxes(tickvals=tickvals, ticktext=[fmt_sec(v) for v in tickvals])
    st.plotly_chart(fig_pred, width="stretch")
    st.caption("Garmin Race Predictor เป็นค่าประมาณจากโมเดลของผู้ผลิต — "
               "ใช้ดูแนวโน้มและเทียบข้อผิดพลาดกับ race/time trial จริงของคนเดิม ไม่ใช้แทนผลงานจริง")

# ---------------- Lactate Threshold (Garmin) ----------------
lt_row = load_latest_lt(athlete_id)
if lt_row:
    lt_date, lt_hr, lt_pace = lt_row
    st.subheader("Lactate threshold จาก Garmin")
    with st.container(horizontal=True):
        st.metric("LT Heart Rate", f"{lt_hr:.0f} bpm" if lt_hr is not None else "–", border=True)
        st.metric("LT Pace", f"{fmt_pace(lt_pace)} /km" if lt_pace is not None else "–", border=True)
        st.metric("วันที่วัด", lt_date, border=True)
    st.caption("ค่าประเมินจากอัลกอริทึม Garmin — เทียบกับผลเทสแลบ/field test "
               "และดูวันที่วัดก่อนใช้ปรับโซน")
else:
    missing_here.append(
        "Lactate Threshold (ต้องใช้อุปกรณ์/กิจกรรมที่เข้าเงื่อนไขของ Garmin)"
    )
# ---------------- Endurance / Hill score (device-dependent) ----------------
eh_cols = [c for c in ("endurance_score", "hill_score_overall") if c in wellness_df]
eh = wellness_df.dropna(subset=eh_cols, how="all") if eh_cols else wellness_df.iloc[0:0]
if not eh.empty and any(eh[c].notna().any() for c in eh_cols):
    st.subheader("Endurance และ Hill score")
    with st.container(horizontal=True):
        if eh["endurance_score"].notna().any():
            e_last = eh["endurance_score"].dropna()
            st.metric("Endurance Score ล่าสุด", f"{e_last.iloc[-1]:.0f}",
                      delta=f"{e_last.iloc[-1] - e_last.iloc[0]:+.0f} เทียบต้นช่วง", border=True)
        if "hill_score_overall" in eh and eh["hill_score_overall"].notna().any():
            h_last = eh["hill_score_overall"].dropna()
            st.metric("Hill Score ล่าสุด", f"{h_last.iloc[-1]:.0f}", border=True)
    if eh["endurance_score"].notna().any():
        fig_end = go.Figure(go.Scatter(
            x=wellness_plot_df["calendar_date"],
            y=wellness_plot_df["endurance_score"],
            mode="lines+markers", name="Endurance Score", connectgaps=False,
            hovertemplate="%{x|%d %b}<br>Endurance Score: %{y:.0f}<extra></extra>",
        ))
        fig_end.update_layout(
            title="แนวโน้ม Endurance Score (ความอึดสะสม)",
            xaxis_title="วันที่", yaxis_title="Endurance Score", showlegend=False,
        )
        st.plotly_chart(fig_end, width="stretch")
else:
    missing_here.append("Endurance Score และ Hill Score (ขึ้นกับรุ่นอุปกรณ์)")
# ---------------- Personal records ----------------
prs = load_personal_records(athlete_id)
if prs.empty:
    missing_here.append("สถิติส่วนตัว (PR)")
else:
    st.subheader("สถิติส่วนตัวจาก Garmin")
    st.dataframe(pd.DataFrame(personal_record_rows(prs)), hide_index=True)
    st.caption("PR นับตามที่นาฬิกาบันทึกอัตโนมัติ — ระยะที่ GPS วัดไม่ถึงเกณฑ์ (เช่น 4.98 กม.) จะไม่ถูกนับเป็น 5K")

# เติมกล่องเดียวที่จองไว้บนสุด — ตอนนี้รู้ครบแล้วว่าหัวข้อไหนไม่มีของ
if missing_here or advanced_performance_missing_message:
    lines = []
    if advanced_performance_missing_message:
        lines.append(advanced_performance_missing_message)
    if missing_here:
        lines.append(
            "ยังไม่มีข้อมูลให้แสดงในช่วงนี้: " + " · ".join(missing_here)
        )
    data_gap_slot.info("\n\n".join(lines), icon=":material/insights:")
