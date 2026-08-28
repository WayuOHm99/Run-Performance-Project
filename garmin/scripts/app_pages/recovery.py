"""หน้า "การฟื้นตัว" ของ Coach Dashboard"""

import datetime
import math

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from dashboard_domain import (
    available_series,
    chart_title,
    field_freshness,
    fmt_num,
    fmt_pace,
    fmt_recovery_time,
    fmt_sec,
    fmt_text,
    get_recovery_minutes,
    has_any_value,
    latest_field,
    period_metric,
    readiness_when,
    recovery_minutes_series,
    wellness_quality_flags,
)

from dashboard_view import (
    C_CRIT,
    SERIES_COLORS,
    mark_partial_today,
)

from dashboard_data import (
    load_athlete_devices,
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


st.header(f"การฟื้นตัว — {selected_name}", anchor=f"recovery-{selected_anchor}")
st.caption(f"ค่าเฉลี่ยและแนวโน้มระหว่าง {start_date.strftime('%d/%m/%Y')}–{end_date.strftime('%d/%m/%Y')}")

if wellness_df.empty:
    st.info("ไม่มีข้อมูลสุขภาพในช่วงเวลานี้")
else:
    # Sleep/RHR เป็นค่าหลังคืนสิ้นสุดและใช้ของวันนี้ได้; BB-high/Stress เป็น
    # intraday aggregates ที่ยังเปลี่ยนถึงเที่ยงคืน จึงไม่นับวันนี้เฉพาะสองค่านั้น
    average_specs = [
        ("Sleep score เฉลี่ย", "sleep_score", "", False),
        ("Body Battery สูงสุดเฉลี่ย", "body_battery_high", "", True),
        ("Resting HR เฉลี่ย", "resting_hr", " bpm", False),
        ("Stress เฉลี่ย", "stress_avg", "", True),
    ]
    average_results = {
        column: period_metric(
            wellness_df, column, today, exclude_today, start_date, end_date
        )
        for _, column, _, exclude_today in average_specs
    }
    # เหตุผลว่าทำไม denominator ของแต่ละการ์ดไม่เท่ากันอยู่ใน help ของการ์ดนั้นเอง
    # ไม่ใช่ย่อหน้าใต้แถว — คนที่สงสัยการ์ดไหนจะจิ้มการ์ดนั้น
    with st.container(horizontal=True):
        for label, column, unit, exclude_today_metric in average_specs:
            result = average_results[column]
            sample_note = (
                f"{result['count']}/{result['total_days']} วันมีข้อมูล"
                if result["total_days"] else "ไม่มีวันเต็มในช่วง"
            )
            st.metric(
                label, fmt_num(result["mean"], unit), delta=sample_note,
                delta_color="off", border=True,
                help=(
                    "mean() ใช้เฉพาะวันที่มีค่าจริง; วันที่ว่างไม่ถูกแทนด้วยศูนย์ · "
                    + ("ไม่นับวันนี้ซึ่งค่ายังเปลี่ยนถึงเที่ยงคืน"
                       if exclude_today_metric
                       else "นับวันนี้ได้เพราะค่าสรุปหลังจบคืนแล้ว")
                    + " · กราฟและตารางยังแสดงวันนี้พร้อมเส้นประ"
                ),
            )

    quality_flags = wellness_quality_flags(wellness_df)
    if quality_flags:
        st.warning(
            f"พบ {len(quality_flags)} กลุ่มค่าที่ควรตรวจเทียบนาฬิกา — "
            "ยังคงค่าดิบไว้และรวมในค่าเฉลี่ย ไม่ตัด outlier อัตโนมัติ",
            icon=":material/data_alert:",
        )
        with st.expander("ดูค่าที่ควรตรวจทาน", icon=":material/troubleshoot:"):
            for note in quality_flags:
                st.markdown(f"- {note}")

    # --- Sleep / Body Battery: สร้างเฉพาะ trace ที่มีข้อมูลและใช้ชื่อที่คนอ่านเข้าใจ ---
    health_series = available_series(wellness_df, {
        "sleep_score": "คะแนนการนอน",
        "body_battery_high": "Body Battery สูงสุดของวัน",
    })
    if health_series:
        fig_health = go.Figure()
        for column, label in health_series:
            # จำนวนจุดที่มีจริงอยู่ใน legend ข้าง ๆ เส้นนั้นเอง แทน caption ใต้กราฟ
            # ที่ไล่ทุกเส้นรวดเดียว — ช่องว่างบนเส้นคือวันที่ Garmin ไม่มีค่า
            filled = int(wellness_plot_df[column].notna().sum())
            fig_health.add_trace(go.Scatter(
                x=wellness_plot_df["calendar_date"], y=wellness_plot_df[column],
                mode="lines+markers", connectgaps=False,
                name=f"{label} ({filled}/{len(wellness_plot_df)} วัน)",
                line=dict(color=SERIES_COLORS[column]),
                hovertemplate=f"%{{x|%d %b}}<br>{label}: %{{y:.0f}}<extra></extra>",
            ))
        fig_health.update_layout(
            title="แนวโน้มคะแนนการนอนและ Body Battery สูงสุดของวัน",
            xaxis_title="วันที่", yaxis_title="คะแนน", hovermode="x unified",
        )
        mark_partial_today(fig_health, today, start_date, end_date)
        st.plotly_chart(fig_health, width="stretch")

    # --- Stress กับ Readiness มีทิศทางความหมายตรงข้าม จึงแยกแกนและบอกชัด ---
    stress_ready_series = available_series(wellness_df, {
        "stress_avg": "Stress เฉลี่ย (สูง = แย่)",
        "training_readiness": "Training Readiness (สูง = ดี)",
    })
    if stress_ready_series:
        # ทั้งคู่เป็นคะแนน 0–100 จึงอยู่แกนเดียวกันได้ตรง ๆ (กฎกราฟ 01)
        # แกนขวาเดิมไม่ได้เพิ่มอะไรนอกจากทำให้จุดตัดของสองเส้นดูมีความหมาย
        fig_stress = go.Figure()
        for column, label in stress_ready_series:
            fig_stress.add_trace(go.Scatter(
                x=wellness_plot_df["calendar_date"], y=wellness_plot_df[column],
                mode="lines+markers", name=label, connectgaps=False,
                line=dict(color=SERIES_COLORS[column]),
                hovertemplate=f"%{{x|%d %b}}<br>{label}: %{{y:.0f}}<extra></extra>",
            ))
        fig_stress.update_layout(
            title=chart_title(stress_ready_series, {
                frozenset({"stress_avg", "training_readiness"}):
                    "Stress เทียบ Training Readiness",
                frozenset({"stress_avg"}): "แนวโน้ม Stress เฉลี่ย",
                frozenset({"training_readiness"}): "แนวโน้ม Training Readiness",
            }),
            xaxis_title="วันที่",
            hovermode="x unified",
        )
        # ทิศทางการอ่านอยู่บนแกน ไม่ต้องมี caption ใต้กราฟมาอธิบายซ้ำ
        fig_stress.update_yaxes(
            title_text=(
                "คะแนน 0–100 · Stress สูง = แย่ · Readiness สูง = ดี"
                if len(stress_ready_series) > 1
                else "คะแนน 0–100 · " + (
                    "สูง = แย่"
                    if stress_ready_series[0][0] == "stress_avg" else "สูง = ดี"
                )
            ),
            range=[0, 100],
        )
        mark_partial_today(fig_stress, today, start_date, end_date)
        st.plotly_chart(fig_stress, width="stretch")
    # เดิมมี caption อธิบายว่าทำไมไม่มีเส้น Readiness ตรงนี้ — ตัดออกแล้วเพราะ
    # หัวข้อกราฟไม่เอ่ยถึงค่าที่ไม่ได้วาดอีกต่อไป (`chart_title`) จึงไม่มีอะไรให้แก้ต่าง
    # และหัวข้อ "ความพร้อมซ้อม" ด้านล่างบอกเรื่องอุปกรณ์ไว้ที่เดียวแล้ว

    # --- RHR / HRV recovery trends ---
    # bpm กับ ms เป็นคนละหน่วยจริง จึงเป็นคนละกราฟ ไม่ใช่แกนขวา (กฎกราฟ 01)
    recovery_trend_specs = [
        (
            {"resting_hr": "Resting HR"},
            "แนวโน้ม Resting HR", "ครั้ง/นาที (bpm)",
        ),
        (
            {
                "hrv_last_night": "HRV คืนล่าสุด",
                "hrv_weekly_avg": "HRV เฉลี่ย 7 วัน",
            },
            "แนวโน้ม HRV", "มิลลิวินาที (ms)",
        ),
    ]
    for label_map, figure_title, axis_title in recovery_trend_specs:
        trend_series = available_series(wellness_df, label_map)
        if not trend_series:
            continue
        fig_trend = go.Figure()
        for column, label in trend_series:
            fig_trend.add_trace(go.Scatter(
                x=wellness_plot_df["calendar_date"], y=wellness_plot_df[column],
                mode="lines+markers", name=label, connectgaps=False,
                line=dict(color=SERIES_COLORS[column],
                          dash="dot" if column == "hrv_weekly_avg" else "solid"),
                hovertemplate=f"%{{x|%d %b}}<br>{label}: %{{y:.0f}}<extra></extra>",
            ))
        fig_trend.update_layout(
            title=figure_title, xaxis_title="วันที่", yaxis_title=axis_title,
            hovermode="x unified", showlegend=len(trend_series) > 1,
        )
        mark_partial_today(fig_trend, today, start_date, end_date)
        st.plotly_chart(fig_trend, width="stretch")

    # --- ค่าเฉลี่ยเสริม พร้อม sample count เหมือนการ์ดหลัก ---
    extra_specs = [
        ("หายใจตอนตื่น", "avg_waking_respiration", " brpm", True),
        ("หายใจตอนนอน", "avg_sleep_respiration", " brpm", False),
        ("Stress สูงสุดเฉลี่ย", "max_stress", "", True),
        ("Floors/วัน", "floors_ascended", "", True),
        ("Active kcal/วัน", "active_kilocalories", " kcal", True),
    ]
    extra_results = []
    for label, column, unit, exclude_today in extra_specs:
        result = period_metric(
            wellness_df, column, today, exclude_today, start_date, end_date
        )
        if pd.notna(result["mean"]):
            extra_results.append((label, unit, result))
    if extra_results:
        with st.container(horizontal=True):
            for label, unit, result in extra_results:
                st.metric(
                    label, fmt_num(result["mean"], unit),
                    delta=f"{result['count']}/{result['total_days']} วันมีข้อมูล",
                    delta_color="off", border=True,
                )

    # --- Respiration trend: เปิดเมื่อมีค่าตอนตื่นหรือตอนนอนอย่างใดอย่างหนึ่ง ---
    respiration_series = available_series(wellness_df, {
        "avg_sleep_respiration": "ขณะนอน",
        "avg_waking_respiration": "ขณะตื่น",
    })
    if respiration_series:
        fig_resp = go.Figure()
        for column, label in respiration_series:
            fig_resp.add_trace(go.Scatter(
                x=wellness_plot_df["calendar_date"], y=wellness_plot_df[column],
                mode="lines+markers", name=label, connectgaps=False,
                hovertemplate=f"%{{x|%d %b}}<br>{label}: %{{y:.1f}} brpm<extra></extra>",
            ))
        fig_resp.update_layout(
            title="อัตราการหายใจ — ขณะนอนเทียบขณะตื่น",
            xaxis_title="วันที่", yaxis_title="ครั้ง/นาที (brpm)", hovermode="x unified",
        )
        mark_partial_today(fig_resp, today, start_date, end_date)
        st.plotly_chart(fig_resp, width="stretch")

    # --- Garmin Readiness / Recovery: เปิดเมื่อ field ใด field หนึ่งมีค่า ไม่ผูกกับ ACWR factor ---
    readiness_section_fields = [
        "training_readiness", "recovery_time_min",
        "acute_load", "acwr_percent", "hrv_factor_pct", "stress_history_pct",
        "readiness_sleep_factor_pct", "recovery_time_factor_pct",
        "training_status",
    ]
    if has_any_value(wellness_df, readiness_section_fields):
        st.subheader("ความพร้อมซ้อมและเวลาฟื้นตัวจาก Garmin")
        ready_snap = latest_field(
            wellness_df, "training_readiness",
            ("readiness_timestamp_local", "readiness_timestamp_utc"),
        )
        recovery_snap = latest_field(wellness_df, "recovery_time_min")
        acute_snap = latest_field(wellness_df, "acute_load")
        acwr_factor_snap = latest_field(wellness_df, "acwr_percent")
        ready_level = fmt_text(ready_snap["row"].get("readiness_level")) if ready_snap else ""
        with st.container(horizontal=True):
            st.metric(
                "Readiness ล่าสุด",
                fmt_num(ready_snap["value"] if ready_snap else float("nan")),
                delta=ready_level.replace("_", " ") or None,
                delta_color="off", border=True,
                help=readiness_when(ready_snap, today),
            )
            st.metric(
                "Recovery Time",
                fmt_recovery_time(get_recovery_minutes(recovery_snap["row"])
                                  if recovery_snap else float("nan")),
                border=True,
                help=("Garmin ส่งหน่วยเป็นนาที; Dashboard แปลงเป็นชั่วโมง+นาที · "
                      + field_freshness(recovery_snap, today)),
            )
            st.metric(
                "Acute Load ล่าสุด",
                fmt_num(acute_snap["value"] if acute_snap else float("nan")),
                border=True, help=field_freshness(acute_snap, today),
            )
            st.metric(
                "ปัจจัย Acute Load ต่อ Readiness",
                (f"{fmt_num(acwr_factor_snap['value'])}%" if acwr_factor_snap else "–"),
                help=("คะแนนองค์ประกอบที่ Garmin ใช้คำนวณ Training Readiness; "
                      "เป็นคะแนนปัจจัยของ Garmin Readiness ไม่ใช่โหลดสะสมที่ Dashboard คำนวณในแท็บการซ้อม · "
                      + field_freshness(acwr_factor_snap, today)),
                border=True,
            )

        # ความสดของแต่ละค่าอยู่ใน help ของการ์ดนั้นแล้ว จึงไม่ต้องมี caption
        # ไล่ทั้งสี่ค่าซ้ำอีกรอบ · ส่วนคำบรรยายของ Garmin เป็นคำของ Garmin
        # ไม่ใช่ตัวเลขที่ต้องตัดสินใจ จึงลงไปอยู่ในกล่องพับด้านล่างที่เดียว
        garmin_notes = []
        if ready_snap:
            ready_row = ready_snap["row"]
            feedback = (fmt_text(ready_row.get("readiness_feedback_long"))
                        or fmt_text(ready_row.get("readiness_feedback")))
            if feedback:
                garmin_notes.append(("Garmin feedback ล่าสุด", feedback))
            input_context = fmt_text(ready_row.get("readiness_input_context"))
            if input_context:
                garmin_notes.append(("Readiness input context", input_context))
        if recovery_snap:
            change_phrase = fmt_text(recovery_snap["row"].get("recovery_time_change_phrase"))
            if change_phrase:
                garmin_notes.append(("สถานะ Recovery Time", change_phrase))

        if has_any_value(wellness_df, ["training_readiness"]):
            fig_ready = go.Figure(go.Scatter(
                x=wellness_plot_df["calendar_date"], y=wellness_plot_df["training_readiness"],
                mode="lines+markers", name="Training Readiness", connectgaps=False,
                line=dict(color=SERIES_COLORS["training_readiness"]),
                hovertemplate="%{x|%d %b}<br>Readiness: %{y:.0f}<extra></extra>",
            ))
            fig_ready.add_hrect(y0=0, y1=50, fillcolor=C_CRIT, opacity=0.08, line_width=0)
            fig_ready.update_layout(
                title="แนวโน้ม Training Readiness (0–100)",
                xaxis_title="วันที่", yaxis_title="Readiness (สูง = ดี)", showlegend=False,
            )
            mark_partial_today(fig_ready, today, start_date, end_date)
            st.plotly_chart(fig_ready, width="stretch")

        recovery_minutes = recovery_minutes_series(wellness_plot_df)
        if recovery_minutes.notna().any():
            recovery_labels = recovery_minutes.map(
                lambda value: fmt_recovery_time(value) if pd.notna(value) else "ไม่มีข้อมูล"
            )
            fig_recovery = go.Figure(go.Scatter(
                # Keep every calendar row: NaN in y now creates the intended
                # visible gap because connectgaps=False instead of being masked out.
                x=wellness_plot_df["calendar_date"],
                y=recovery_minutes / 60,
                customdata=recovery_labels,
                mode="lines+markers", name="Recovery Time", connectgaps=False,
                line=dict(color=SERIES_COLORS["recovery_time"]),
                hovertemplate="%{x|%d %b}<br>Recovery Time: %{customdata}<extra></extra>",
            ))
            fig_recovery.update_layout(
                title="แนวโน้ม Recovery Time", xaxis_title="วันที่",
                yaxis_title="ชั่วโมง (ค่าต้นทางเป็นนาที)", showlegend=False,
            )
            mark_partial_today(fig_recovery, today, start_date, end_date)
            st.plotly_chart(fig_recovery, width="stretch")

        factor_specs = [
            ("ปัจจัย Acute Load", "acwr_percent", "acwr_factor_feedback"),
            ("ปัจจัย HRV", "hrv_factor_pct", "hrv_factor_feedback"),
            ("ปัจจัยประวัติ Stress", "stress_history_pct", "stress_history_factor_feedback"),
            ("ปัจจัยการนอน", "readiness_sleep_factor_pct", "readiness_sleep_factor_feedback"),
            ("ปัจจัย Recovery Time", "recovery_time_factor_pct", "recovery_time_factor_feedback"),
        ]
        factor_rows = []
        for label, column, feedback_column in factor_specs:
            snapshot = latest_field(wellness_df, column)
            if snapshot:
                factor_rows.append({
                    "องค์ประกอบ Readiness": label,
                    "คะแนนองค์ประกอบ": f"{fmt_num(snapshot['value'])}%",
                    "Garmin feedback": fmt_text(snapshot["row"].get(feedback_column), "–").replace("_", " "),
                    "วันที่/ความสด": field_freshness(snapshot, today),
                })
        for note_label, note_value in garmin_notes:
            factor_rows.append({
                "องค์ประกอบ Readiness": note_label,
                "คะแนนองค์ประกอบ": "–",
                "Garmin feedback": note_value.replace("_", " "),
                "วันที่/ความสด": "–",
            })
        if factor_rows:
            with st.expander("ดูองค์ประกอบที่ Garmin ใช้คำนวณ Readiness", icon=":material/tune:"):
                st.dataframe(pd.DataFrame(factor_rows), hide_index=True)
                st.caption("เป็น factor ของ Readiness ไม่ใช่โหลดสะสมของระบบ")
    else:
        st.subheader("ความพร้อมซ้อมและเวลาฟื้นตัวจาก Garmin")
        readiness_summary = availability_by_key["readiness"]
        if readiness_summary["state"] == "outside_range":
            readiness_missing_message = (
                "บัญชีนี้เคยมีข้อมูลความพร้อม/การฟื้นตัว แต่ไม่มีค่าในช่วงวันที่ที่เลือก "
                "ลองเลือก ‘ทั้งหมด’ หรือช่วงที่ยาวขึ้น"
            )
        else:
            models = ", ".join(load_athlete_devices(athlete_id))
            readiness_missing_message = (
                "Garmin Connect ยังไม่เคยส่ง Training Readiness, Recovery Time, Acute Load "
                "หรือ Training Status ให้บัญชีนี้ — นาฬิกาบางรุ่นแสดง Recovery Time "
                "บนหน้าปัดแต่ไม่ส่งขึ้น Connect Dashboard จะไม่เดาหรือคำนวณค่าทดแทน"
                + (f" (อุปกรณ์ที่พบใน 90 วัน: {models})" if models else "")
            )
        st.info(readiness_missing_message, icon=":material/watch:")

    # --- รายละเอียดที่เก็บแล้ว: collapsed เพื่อให้ตรวจเทียบนาฬิกาได้โดยไม่ทำหน้าหลักแน่น ---
    detail_specs = [
        ("HRV", "HRV เฉลี่ย 7 วัน", "hrv_weekly_avg", " ms"),
        ("การนอน", "ระยะเวลานอน", "sleep_duration_sec", "duration"),
        ("การนอน", "Deep sleep", "deep_sleep_sec", "duration"),
        ("การนอน", "Light sleep", "light_sleep_sec", "duration"),
        ("การนอน", "REM sleep", "rem_sleep_sec", "duration"),
        ("การนอน", "Awake", "awake_sec", "duration"),
        ("Body Battery", "ต่ำสุดของวัน", "body_battery_low", ""),
        ("Body Battery", "ตอนตื่น", "bb_at_wake", ""),
        ("Body Battery", "ชาร์จ", "bb_charged", ""),
        ("Body Battery", "ใช้ไป", "bb_drained", ""),
        ("Body Battery", "ระหว่างนอน", "bb_during_sleep", ""),
        ("กิจวัตร", "Steps", "steps", " ก้าว"),
        ("กิจวัตร", "เป้า Steps", "steps_goal", " ก้าว"),
        ("กิจวัตร", "BMR", "bmr_kilocalories", " kcal"),
        ("กิจวัตร", "Active time", "active_seconds", "duration"),
        ("การหายใจ", "สูงสุด", "highest_respiration", " brpm"),
        ("การหายใจ", "ต่ำสุด", "lowest_respiration", " brpm"),
        ("การซ้อม", "Training Status", "training_status", "text"),
        ("สมรรถนะ", "Endurance Score", "endurance_score", ""),
        ("สมรรถนะ", "Hill Score", "hill_score_overall", ""),
        ("สมรรถนะ", "Hill Strength", "hill_score_strength", ""),
        ("สมรรถนะ", "Hill Endurance", "hill_score_endurance", ""),
    ]
    detail_rows = []
    for category, label, column, unit in detail_specs:
        snapshot = latest_field(wellness_df, column)
        if not snapshot:
            continue
        if unit == "duration":
            display_value = fmt_sec(snapshot["value"])
        elif unit == "text":
            display_value = fmt_text(snapshot["value"], "–").replace("_", " ")
        else:
            display_value = fmt_num(snapshot["value"], unit)
        detail_rows.append({
            "หมวด": category, "รายการ": label, "ค่าล่าสุด": display_value,
            "วันที่/ความสด": field_freshness(snapshot, today),
        })
    if detail_rows:
        with st.expander("ดูข้อมูลสุขภาพเพิ่มเติมล่าสุด", icon=":material/monitor_heart:"):
            st.dataframe(pd.DataFrame(detail_rows), hide_index=True)
            st.caption(
                "แต่ละแถวเลือกค่าล่าสุดของ field นั้นเอง — fetched_at เป็นเวลาระดับแถว"
            )

    history_labels = {
        "calendar_date": "วันที่",
        "resting_hr": "Resting HR",
        "hrv_weekly_avg": "HRV 7 วัน",
        "hrv_last_night": "HRV คืนล่าสุด",
        "hrv_status": "สถานะ HRV",
        "sleep_score": "Sleep score",
        "sleep_duration_sec": "เวลานอน", "deep_sleep_sec": "Deep",
        "light_sleep_sec": "Light", "rem_sleep_sec": "REM", "awake_sec": "Awake",
        "body_battery_high": "BB สูงสุด", "body_battery_low": "BB ต่ำสุด",
        "stress_avg": "Stress เฉลี่ย", "max_stress": "Stress สูงสุด",
        "bb_at_wake": "BB ตอนตื่น",
        "bb_charged": "BB ชาร์จ", "bb_drained": "BB ใช้ไป",
        "bb_during_sleep": "BB ระหว่างนอน", "bb_most_recent": "BB ล่าสุด",
        "steps": "Steps", "steps_goal": "เป้า Steps", "floors_ascended": "Floors",
        "active_kilocalories": "Active kcal", "bmr_kilocalories": "BMR kcal",
        "active_seconds": "Active time",
        "avg_waking_respiration": "หายใจเฉลี่ยตอนตื่น",
        "avg_sleep_respiration": "หายใจเฉลี่ยตอนนอน",
        "highest_respiration": "หายใจสูงสุด", "lowest_respiration": "หายใจต่ำสุด",
        "training_readiness": "Readiness", "readiness_level": "Readiness level",
        "readiness_feedback": "Readiness feedback",
        "readiness_feedback_long": "Readiness feedback ละเอียด",
        "readiness_timestamp_utc": "เวลา Readiness (UTC)",
        "readiness_timestamp_local": "เวลา Readiness (local)",
        "readiness_input_context": "Readiness context",
        "acute_load": "Acute Load", "acwr_percent": "Readiness: Acute Load factor %",
        "acwr_factor_feedback": "Acute Load feedback",
        "hrv_factor_pct": "Readiness: HRV factor %",
        "hrv_factor_feedback": "HRV factor feedback",
        "stress_history_pct": "Readiness: Stress factor %",
        "stress_history_factor_feedback": "Stress factor feedback",
        "readiness_sleep_factor_pct": "Readiness: Sleep factor %",
        "readiness_sleep_factor_feedback": "Sleep factor feedback",
        "recovery_time_min": "Recovery Time (นาที)",
        "recovery_time_factor_pct": "Readiness: Recovery factor %",
        "recovery_time_factor_feedback": "Recovery factor feedback",
        "recovery_time_change_phrase": "สถานะ Recovery Time",
        "training_status": "Training Status",
        "vo2max_trend": "VO2max",
        "fitness_age": "Fitness Age",
        "endurance_score": "Endurance Score", "hill_score_overall": "Hill Score",
        "hill_score_strength": "Hill Strength", "hill_score_endurance": "Hill Endurance",
        "lactate_threshold_hr": "LT Heart Rate",
        "lactate_threshold_pace_min_km": "LT Pace",
    }
    history_columns = [
        column for column in history_labels
        if column in wellness_df.columns
        and (column == "calendar_date" or wellness_df[column].notna().any())
    ]
    if len(history_columns) > 1:
        with st.expander("ดูประวัติสุขภาพรายวัน", icon=":material/table_chart:"):
            history = wellness_df[history_columns].copy().sort_values("calendar_date", ascending=False)
            history["calendar_date"] = pd.to_datetime(
                history["calendar_date"], errors="coerce"
            ).dt.date
            for column in (
                "sleep_duration_sec", "deep_sleep_sec", "light_sleep_sec",
                "rem_sleep_sec", "awake_sec", "active_seconds",
            ):
                if column in history:
                    history[column] = history[column].map(fmt_sec)
            if "lactate_threshold_pace_min_km" in history:
                history["lactate_threshold_pace_min_km"] = history[
                    "lactate_threshold_pace_min_km"
                ].map(lambda value: (
                    f"{fmt_pace(value)} /km" if pd.notna(value) else "–"
                ))
            text_history_columns = (
                "hrv_status", "training_status", "readiness_level",
                "readiness_feedback", "readiness_feedback_long",
                "readiness_input_context", "acwr_factor_feedback",
                "hrv_factor_feedback", "stress_history_factor_feedback",
                "readiness_sleep_factor_feedback", "recovery_time_factor_feedback",
                "recovery_time_change_phrase",
            )
            for column in text_history_columns:
                if column in history:
                    history[column] = history[column].map(
                        lambda value: (value.replace("_", " ")
                                       if isinstance(value, str) else value)
                    )
            history = history.rename(columns=history_labels)
            st.dataframe(history, hide_index=True)
