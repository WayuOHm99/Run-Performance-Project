"""หน้า "การซ้อม" ของ Coach Dashboard"""

import datetime
import math

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from dashboard_domain import (
    EASY_MAX_PCT,
    EF_BASELINE_DAYS,
    EF_BASELINE_MIN_DAYS,
    EF_MIN_DISTANCE_M,
    EF_RECENT_DAYS,
    EF_STALE_DAYS,
    INTENSITY_ORDER,
    aggregate_pace_min_per_km,
    classify_intensity,
    compute_load_windows,
    easy_run_efficiency,
    easy_share_pct,
    efficiency_change_pct,
    efficiency_display,
    efficiency_recent_value,
    efficiency_status,
    efficiency_windows,
    fmt_pace,
    get_lthr,
    hr_zone_coverage,
    intensity_minutes,
    usable_hr_zone_rows,
)

from dashboard_view import (
    C_BLUE,
    C_CONTEXT,
    INTENSITY_COLORS,
    SERIES_COLORS,
)

from dashboard_data import (
    RUN_TYPES,
    load_daily_workload,
    load_easy_runs,
    load_first_load_date,
    load_first_run_date,
)

from dashboard_context import page_context

_ctx = page_context()
athlete_id = _ctx.athlete_id
start_date = _ctx.start_date
end_date = _ctx.end_date
activity_df = _ctx.activity_df
selected_name = _ctx.selected_name
selected_slug = _ctx.selected_slug
selected_anchor = _ctx.selected_anchor


st.header(f"การซ้อม — {selected_name}", anchor=f"training-{selected_anchor}")
st.caption(f"สรุประหว่าง {start_date.strftime('%d/%m/%Y')}–{end_date.strftime('%d/%m/%Y')}")

if activity_df.empty:
    st.info("ไม่มีข้อมูลการวิ่งในช่วงเวลานี้")
else:
    runs_df = activity_df[activity_df["activity_type"].isin(RUN_TYPES)]

    total_distance = runs_df["distance_km"].sum()
    avg_pace_raw = aggregate_pace_min_per_km(runs_df)
    total_hours = runs_df["duration_sec"].sum() / 3600

    with st.container(horizontal=True):
        st.metric("ระยะวิ่งรวม", f"{total_distance:.2f} km", border=True)
        # Tong/Dan บันทึก warm-up / งานหลัก / cool-down เป็นคนละรายการ
        # (2.3 และ 2.1 รายการต่อวันที่ซ้อม) "44 ครั้ง" จึงอ่านเป็น 44 เซสชันไม่ได้
        run_days = (runs_df["start_time_local"].astype(str).str[:10].nunique()
                    if not runs_df.empty else 0)
        st.metric("รายการวิ่ง", f"{len(runs_df)}",
                  delta=f"{run_days} วันที่ซ้อม", delta_color="off", border=True,
                  help="นาฬิกาบันทึก warm-up / งานหลัก / cool-down เป็นคนละรายการ "
                       "จำนวนรายการจึงมากกว่าจำนวนเซสชันจริง")
        st.metric("เพซเฉลี่ย", f"{fmt_pace(avg_pace_raw)} /km" if pd.notna(avg_pace_raw) else "–", border=True)
        st.metric("เวลาวิ่งรวม", f"{total_hours:.1f} ชม.", border=True)

    # ---------------- pace-HR trend ของรันเบา — บริบทประกอบ ----------------
    st.subheader("แนวโน้ม pace–HR ของรันเบา")
    ef_lookback = start_date - datetime.timedelta(days=EF_BASELINE_DAYS)
    lthr_for_tab, _ = get_lthr(selected_slug, athlete_id)
    ef_all = easy_run_efficiency(
        load_easy_runs(athlete_id, ef_lookback.isoformat(), end_date.isoformat()),
        lthr_for_tab,
    )
    ef_windows_tab = efficiency_windows(ef_all, end_date)
    ef_pct_tab = efficiency_change_pct(ef_all, end_date)
    ef_view = ef_all[ef_all["date"] >= pd.Timestamp(start_date)]

    if ef_view.empty:
        st.info(
            "ยังมีรัน easy ไม่พอในช่วงนี้ที่จะคำนวณ pace–HR trend "
            f"(ต้องมี HR, ระยะ ≥ {EF_MIN_DISTANCE_M / 1000:.0f} กม. และ HR ≤ "
            f"{EASY_MAX_PCT * 100:.0f}% ของ LTHR"
            + (f" = {lthr_for_tab * EASY_MAX_PCT:.0f} bpm)" if lthr_for_tab else ")")
            + " — เป็นเรื่องปกติของคนที่ซ้อม cross-training เป็นหลัก ไม่ใช่ระบบขัดข้อง",
            icon=":material/info:",
        )
    else:
        _, txt = efficiency_status(ef_pct_tab)
        ef_baseline_median = (
            ef_windows_tab["baseline_median"]
            if ef_windows_tab is not None else float("nan")
        )
        with st.container(horizontal=True):
            _ef_now = efficiency_recent_value(ef_all, end_date)
            st.metric("pace–HR ล่าสุด (median 3 วัน)",
                      f"{_ef_now:.3f}" if pd.notna(_ef_now) else "–",
                      delta=txt, delta_color="off", border=True,
                      help="รวมรายการวิ่ง easy ที่ Garmin แยกบันทึกในวันเดียวกันก่อน "
                           "แล้วคำนวณความเร็ว (ม./นาที) ÷ HR เฉลี่ยถ่วงเวลา; "
                           "ไม่ใช่ running economy หรือ readiness test")
            st.metric("เทียบฐานก่อนหน้า", efficiency_display(ef_pct_tab), border=True,
                      help="ฐาน 28 วันก่อนสามวันล่าสุดและไม่ซ้อนกับค่าปัจจุบัน; "
                           "ไม่มีเกณฑ์พร้อมซ้อม/ต้องพัก")
            st.metric("จำนวนวันที่มีข้อมูลวิ่ง easy", f"{len(ef_view)} วัน", border=True,
                      help=f"จะสรุปได้ต้องมีข้อมูลวิ่ง easy {EF_RECENT_DAYS} วัน"
                           f"ภายใน {EF_STALE_DAYS} วัน และมีฐานอย่างน้อย "
                           f"{EF_BASELINE_MIN_DAYS} วันใน {EF_BASELINE_DAYS} "
                           "วันก่อนหน้า — ไม่ครบแล้วขึ้น 'ข้อมูลไม่พอ' คือวันวิ่ง easy "
                           "ไม่พอ ไม่ใช่ระบบขัดข้อง")

        fig_ef = go.Figure()
        fig_ef.add_trace(go.Scatter(
            x=ef_view["date"], y=ef_view["ef"], mode="lines+markers",
            line=dict(color=C_BLUE, width=2), marker=dict(size=6), name="pace–HR ต่อวัน",
            connectgaps=False,
            hovertemplate="%{x|%d %b}<br>pace–HR %{y:.3f}<extra></extra>",
        ))
        if pd.notna(ef_baseline_median):
            fig_ef.add_trace(go.Scatter(
                x=ef_view["date"],
                y=[ef_baseline_median] * len(ef_view),
                mode="lines", line=dict(color=C_CONTEXT, width=2, dash="dash"),
                name="ฐานของตัวเอง",
                hovertemplate="ฐาน %{y:.3f}<extra></extra>",
            ))
        fig_ef.update_layout(
            title="ความเร็ว ÷ HR ในรัน easy — ดูทิศทาง ไม่ใช้แทน running economy/ความสด",
            yaxis=dict(title="เมตร/นาที ต่อ 1 bpm"),
            xaxis=dict(title="วันที่"),
            showlegend=True, hovermode="x unified",
        )
        st.plotly_chart(fig_ef, width="stretch")

    # ---------------- โหลดสะสม (บริบท ไม่ใช่คำตัดสิน) ----------------
    st.subheader("โหลดสะสม (บริบท)")
    load_start = start_date - datetime.timedelta(days=56)
    daily_wl, wl_metric, wl_unit = load_daily_workload(athlete_id, load_start.isoformat(), end_date.isoformat())
    first_workload_date = (
        load_first_load_date(athlete_id)
        if wl_metric == "training_load"
        else load_first_run_date(athlete_id)
    )
    history_start = max(load_start, first_workload_date) if first_workload_date else load_start
    load_df = compute_load_windows(daily_wl, end_date, history_start=history_start)
    load_view = load_df[load_df["date"] >= pd.Timestamp(start_date)]
    load_valid = load_view.dropna(subset=["acute"])
    _src = "Garmin training_load (รวม cross-training)" if wl_metric == "training_load" else "ระยะทางวิ่ง"
    _afmt = ".0f" if wl_metric == "training_load" else ".1f"

    if load_valid.empty:
        st.info("ยังไม่มีข้อมูลครบ 7 วันพอสรุปโหลดสะสม")
    else:
        latest_load = load_valid.iloc[-1]
        with st.container(horizontal=True):
            st.metric("โหลด 7 วัน", f"{latest_load['acute']:{_afmt}} {wl_unit}", border=True)
            st.metric("ค่าเฉลี่ย 28 วัน",
                      f"{latest_load['chronic']:{_afmt}} {wl_unit}/สัปดาห์"
                      if pd.notna(latest_load["chronic"]) else "–", border=True)

        fig_load = go.Figure()
        fig_load.add_trace(go.Scatter(
            x=load_view["date"], y=load_view["acute"], mode="lines",
            line=dict(color=C_BLUE, width=2), name=f"โหลด 7 วัน ({wl_unit})",
            connectgaps=False,
            hovertemplate="%{x|%d %b}<br>7 วัน %{y:,.1f}<extra></extra>",
        ))
        fig_load.add_trace(go.Scatter(
            x=load_view["date"], y=load_view["chronic"], mode="lines",
            line=dict(color=C_CONTEXT, width=2, dash="dash"),
            name=f"ฐาน 28 วัน ({wl_unit}/สัปดาห์)", connectgaps=False,
            hovertemplate="%{x|%d %b}<br>ฐาน %{y:,.1f}<extra></extra>",
        ))
        fig_load.update_layout(
            title=f"ปริมาณที่ทำไปเทียบฐานของตัวเอง (จาก {_src})",
            yaxis=dict(title=wl_unit), xaxis=dict(title="วันที่"),
            showlegend=True, hovermode="x unified",
        )
        # แสดง 7 วันและค่าเฉลี่ย 28 วันแยกกันเพื่อให้เห็นบริบท โดยไม่หารเป็น
        # acute:chronic ratio หรือวางเส้นปลอดภัย/เสี่ยงที่หลักฐานรองรับไม่พอ
        st.plotly_chart(fig_load, width="stretch")

    # ---------------- training-intensity distribution ----------------
    st.subheader("สัดส่วนความหนักการซ้อม (3 โซน)")
    zone_cols = ["hr_zone1_sec", "hr_zone2_sec", "hr_zone3_sec", "hr_zone4_sec", "hr_zone5_sec"]
    have_zone_cols = set(zone_cols).issubset(activity_df.columns)
    zdf = usable_hr_zone_rows(activity_df, zone_cols) if have_zone_cols else activity_df.iloc[0:0]

    if not zdf.empty:
        # สัดส่วนของโปรแกรมวิ่งควรดูการวิ่งแยกจาก HIIT/มวย/indoor cardio
        # เพราะงานคนละชนิดเจือจางตัวเลขจนอ่านผิด (วัดจริง 26 ส.ค. 69:
        # P'kao เห็นเบา 33% ทั้งที่เฉพาะการวิ่งเบาแค่ 22% และหนักถึง 53%)
        # จึงวาดสองวง และให้การ์ดอ่านจากวงการวิ่ง
        run_zdf = zdf[zdf["activity_type"].isin(RUN_TYPES)]
        run_buckets = intensity_minutes(run_zdf, zone_cols)
        all_buckets = intensity_minutes(zdf, zone_cols)
        run_coverage = hr_zone_coverage(runs_df, zone_cols)
        all_coverage = hr_zone_coverage(activity_df, zone_cols)
        headline = run_buckets or all_buckets
        headline_is_run = run_buckets is not None
        headline_coverage = run_coverage if headline_is_run else all_coverage
        easy_pct = easy_share_pct(headline)

        # วงที่สองมีความหมายต่อเมื่อ cross-training กินเวลาจริง — ไม่งั้นสองวง
        # จะเหมือนกันเป๊ะ (เคสของ Tong/Dan ที่วิ่งเกือบ 100%) แล้วกลายเป็นสิ่งรบกวน
        cross_share = 0.0
        if run_buckets and all_buckets:
            cross_share = 1 - sum(run_buckets.values()) / sum(all_buckets.values())
        rings = [("การวิ่ง", run_buckets)] if headline_is_run else []
        if cross_share >= 0.10 and all_buckets:
            rings.append(("ทั้งหมด (รวม cross-training)", all_buckets))
        if not rings:
            rings = [("ทั้งหมด", all_buckets)]

        col_pie, col_info = st.columns([3, 2])
        with col_pie:
            fig_pie = go.Figure()
            for index, (ring_name, ring_buckets) in enumerate(rings):
                span = 1 / len(rings)
                fig_pie.add_trace(go.Pie(
                    labels=INTENSITY_ORDER,
                    values=[ring_buckets[name] for name in INTENSITY_ORDER],
                    name=ring_name, hole=0.55, sort=False,
                    marker=dict(colors=[INTENSITY_COLORS[n] for n in INTENSITY_ORDER]),
                    domain=dict(x=[index * span, (index + 1) * span]),
                    title=dict(text=ring_name),
                    textinfo="percent",
                    hovertemplate=(f"{ring_name}<br>%{{label}}<br>"
                                   "%{value:.0f} นาที (%{percent})<extra></extra>"),
                ))
            fig_pie.update_layout(
                title="สัดส่วนเฉพาะเวลาที่ Garmin จัด HR zone ได้",
                legend=dict(orientation="h", yanchor="bottom", y=-0.12),
            )
            st.plotly_chart(fig_pie, width="stretch")
        with col_info:
            label = ("สัดส่วนเบาของการวิ่ง (Z1-2 ตามเวลาจริง)" if headline_is_run
                     else "สัดส่วนเบา (Z1-2 ตามเวลาจริง)")
            all_pct = easy_share_pct(all_buckets)
            unclassified_min = headline_coverage["unclassified_sec"] / 60
            coverage_pct = headline_coverage["coverage_pct"]
            coverage_note = (
                f"ครอบคลุม {coverage_pct:.1f}% ของ duration · "
                f"ไม่ได้จัดโซน {unclassified_min:.1f} นาที"
            )
            st.metric(label, f"{easy_pct:.0f}%", delta=coverage_note,
                      delta_color="off", border=True,
                      help=("นับจากเวลาในโซน HR จริงที่นาฬิกาเก็บวินาทีต่อโซน "
                            f"({len(run_zdf) if headline_is_run else len(zdf)} กิจกรรม) · "
                            "เปอร์เซ็นต์ในวงใช้เฉพาะเวลาที่จัดโซนได้; coverage "
                            "เทียบกับ duration ของทุกกิจกรรม Garmin ในขอบเขต · "
                            "เป็นคำอธิบายสัดส่วน ไม่ได้มีเป้า 80% สากล · "
                            + (f"รวม cross-training ทั้งหมดได้ {all_pct:.0f}%"
                               if headline_is_run and pd.notna(all_pct)
                               else "ยังไม่มีการวิ่งที่มีเวลาในโซนในช่วงนี้")))
            for name in INTENSITY_ORDER:
                st.markdown(f"- **{name}** — {headline[name]:.0f} นาที")
    else:
        # fallback วิธีเดิม (avg HR ต่อเซสชัน) เมื่อไม่มี time-in-zone
        lthr, lthr_source = get_lthr(selected_slug, athlete_id)
        hr_runs = runs_df.dropna(subset=["avg_hr", "duration_sec"]).copy()
        if not lthr or hr_runs.empty:
            st.info("ไม่มีข้อมูล HR zones หรือ LTHR สำหรับจำแนกความหนัก")
        else:
            hr_runs["intensity"] = hr_runs["avg_hr"].map(lambda h: classify_intensity(h, lthr))
            dist = (hr_runs.groupby("intensity")
                    .agg(minutes=("duration_sec", lambda s: s.sum() / 60), sessions=("duration_sec", "size"))
                    .reindex(INTENSITY_ORDER).dropna(how="all").reset_index())
            easy_pct = 0.0
            if dist["minutes"].sum() > 0:
                easy_pct = (dist[dist["intensity"] == INTENSITY_ORDER[0]]["minutes"].sum()
                            / dist["minutes"].sum()) * 100
            col_pie, col_info = st.columns([3, 2])
            with col_pie:
                fig_pie = px.pie(dist, values="minutes", names="intensity", hole=0.55,
                                 color="intensity", color_discrete_map=INTENSITY_COLORS,
                                 category_orders={"intensity": INTENSITY_ORDER},
                                 title="สัดส่วนเวลาซ้อมตามโซนความหนัก (จาก avg HR)")
                fig_pie.update_traces(textinfo="percent+label", sort=False,
                                      hovertemplate="%{label}<br>%{value:.0f} นาที (%{percent})<extra></extra>")
                st.plotly_chart(fig_pie, width="stretch")
            with col_info:
                st.metric("สัดส่วนวิ่งเบา (ตามเวลา)", f"{easy_pct:.0f}%", border=True,
                          help="ไม่มีเวลาในโซน HR จริง จึงจำแนกจาก avg HR "
                               f"ต่อเซสชันเทียบ LTHR {lthr} bpm ({lthr_source}) "
                               "ซึ่งหยาบกว่าและใช้กับ interval ได้ไม่ดี; "
                               "เป็นคำอธิบาย ไม่ใช่เป้า 80% สากล")
                for _, r in dist.iterrows():
                    st.markdown(f"- **{r['intensity']}** — {r['minutes']:.0f} นาที · {int(r['sessions'])} เซสชัน")

    # ---------------- Running Dynamics (สรุปช่วงที่เลือก) ----------------
    dyn_cols = {
        "avg_cadence": ("Cadence เฉลี่ย", "spm", "%.0f"),
        "avg_stride_length_cm": ("Stride Length", "cm", "%.0f"),
        "avg_ground_contact_time_ms": ("Ground Contact", "ms", "%.0f"),
        "avg_vertical_oscillation_cm": ("Vertical Oscillation", "cm", "%.1f"),
        "avg_vertical_ratio": ("Vertical Ratio", "%", "%.1f"),
    }
    run_dyn = runs_df[runs_df.get("avg_ground_contact_time_ms").notna()] if "avg_ground_contact_time_ms" in runs_df else runs_df.iloc[0:0]
    if not run_dyn.empty:
        # รายละเอียดฟอร์มเป็นของที่ดูตอนสงสัย ไม่ใช่ค่าที่ต้องเห็นทุกครั้งที่เปิดหน้า
        # ห้าตัวนี้เคยดันแท็บนี้ให้เป็นแท็บที่มีตัวเลขพร้อมกันมากที่สุดในไฟล์ (16 ตัว)
        dyn_drawer = st.expander(
            "ดู Running dynamics เฉลี่ย", icon=":material/podiatry:"
        )
        with dyn_drawer, st.container(horizontal=True):
            for col, (label, unit, fmt) in dyn_cols.items():
                val = pd.to_numeric(run_dyn[col], errors="coerce").mean() if col in run_dyn else float("nan")
                st.metric(label, (fmt % val + f" {unit}") if pd.notna(val) else "–",
                          border=True,
                          help="จากเซสชันวิ่งที่นาฬิกาเก็บ running dynamics — "
                               "ใช้ดูคนเดิมที่เพซ/พื้นผิว/ความชัน/อุปกรณ์ใกล้กัน; "
                               "GCT หรือ vertical ratio ต่ำไม่ได้แปลว่าประหยัดแรงหรือเสี่ยงเจ็บน้อยโดยลำพัง")

    # ---------------- กราฟเดิม ----------------
    fig_dist = px.bar(activity_df, x="start_time_local", y="distance_km",
                      title="ระยะทางของแต่ละกิจกรรม",
                      labels={"distance_km": "ระยะทาง (km)", "start_time_local": "วันที่และเวลา"})
    fig_dist.update_traces(marker_color=SERIES_COLORS["distance_km"])
    st.plotly_chart(fig_dist, width="stretch")

    # ขนาดวงกลม = ความหนัก: ใช้ training_load ถ้านาฬิกาให้ ไม่งั้น Training Effect aerobic (ทุกคนมีครบ)
    if activity_df["training_load"].notna().any():
        size_col, size_label = "training_load", "Training Load"
    else:
        size_col, size_label = "training_effect_aerobic", "Training Effect (แอโรบิก)"
    clean_activity = activity_df.dropna(subset=["avg_pace_min_per_km", size_col]).copy()
    if clean_activity.empty:
        st.info("ยังไม่มีข้อมูล Pace + ความหนักครบพอสำหรับกราฟนี้ในช่วงเวลาที่เลือก")
    else:
        clean_activity["_size"] = clean_activity[size_col].clip(lower=0.1)  # กัน 0 ทำวงกลมหาย
        fig_perf = px.scatter(clean_activity, x="start_time_local", y="avg_pace_min_per_km",
                              size="_size", color="avg_hr",
                              title=f"เพซเทียบความหนัก ({size_label} = ขนาดวงกลม)",
                              labels={"avg_pace_min_per_km": "Pace (นาที/กม.)",
                                      "start_time_local": "วันที่",
                                      "avg_hr": "หัวใจเฉลี่ย (bpm)"})
        fig_perf.update_yaxes(autorange="reversed")
        st.plotly_chart(fig_perf, width="stretch")
