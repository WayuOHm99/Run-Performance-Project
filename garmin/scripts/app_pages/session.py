"""หน้า "รายละเอียดเซสชัน" ของ Coach Dashboard"""

import datetime
import math

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from dashboard_domain import (
    analyze_distance_halves,
    fmt_pace,
    fmt_sec,
    fmt_signed_delta,
    fmt_text,
    pace_axis_ticks,
    prepare_session_candidates,
)

from dashboard_view import (
    BLUE_RAMP_5,
    C_BLUE,
    SERIES_COLORS,
)

from dashboard_data import (
    load_splits,
)

from dashboard_context import page_context

_ctx = page_context()
start_date = _ctx.start_date
end_date = _ctx.end_date
activity_df = _ctx.activity_df
selected_name = _ctx.selected_name
selected_anchor = _ctx.selected_anchor


st.header(f"รายละเอียดเซสชัน — {selected_name}", anchor=f"sessions-{selected_anchor}")
st.caption(
    f"เลือกกิจกรรมระหว่าง {start_date.strftime('%d/%m/%Y')}–{end_date.strftime('%d/%m/%Y')} · "
    "เครื่องหมาย – หมายถึง Garmin ไม่ได้ส่งเมตริกนั้นมากับกิจกรรมที่เลือก ไม่ใช่ค่า 0"
)

if activity_df.empty:
    st.info("ไม่มีกิจกรรมในช่วงเวลานี้")
else:
    # แสดงทุกกิจกรรม — ตัวกรอง >500 ม. เดิมซ่อน warm-up/cool-down ของ Tong ทั้งเซสชัน
    # ทั้งที่ fact_activity_split มีข้อมูลครบ และทำให้ดูเหมือนระบบ sync มาไม่ครบ
    candidates = prepare_session_candidates(activity_df)
    if candidates.empty:
        st.info("ไม่มีกิจกรรมในช่วงเวลานี้")
    else:
        label_map = {}
        for _, r in candidates.iterrows():
            distance_label = (f"{r['distance_km']:.2f} km"
                              if pd.notna(r.get("distance_km")) else "ไม่มีระยะทาง")
            label_map[int(r["activity_id"])] = (
                f"{r['start_time_local']:%d %b %Y %H:%M} · "
                f"{fmt_text(r['activity_name'], fmt_text(r['activity_type'], 'กิจกรรม'))} · "
                f"{distance_label}"
            )
        chosen_id = st.selectbox(
            "กิจกรรมที่ต้องการวิเคราะห์",
            options=list(label_map.keys()),
            format_func=lambda i: label_map[i],
        )

        # --- การ์ดรายละเอียดเซสชัน (ข้อมูลเต็มจากนาฬิกา) ---
        arow = activity_df[activity_df["activity_id"] == chosen_id].iloc[0]

        def _fmt(v, unit="", fmt="{:.0f}"):
            return (fmt.format(v) + unit) if pd.notna(v) else "–"

        st.subheader("ภาพรวมเซสชัน")

        def _dur(sec):
            if pd.isna(sec):
                return "–"
            s = int(sec)
            return (f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}" if s >= 3600
                    else f"{s // 60}:{s % 60:02d}")

        # แถวภาพรวมหลัก (แบบหน้าสรุปในแอป Garmin)
        o1 = st.columns(4)
        o1[0].metric("ระยะทาง", _fmt(arow.get("distance_km"), " km", "{:.2f}"), border=True)
        o1[1].metric("เวลา", _dur(arow.get("duration_sec")), border=True)
        o1[2].metric("เพซเฉลี่ย",
                     (fmt_pace(arow.get("avg_pace_min_per_km")) + " /km")
                     if pd.notna(arow.get("avg_pace_min_per_km")) else "–", border=True)
        o1[3].metric("HR เฉลี่ย", _fmt(arow.get("avg_hr"), " bpm"), border=True)

        with st.expander("ตัวเลขเพิ่มเติมจากนาฬิกา", icon=":material/monitor_heart:"):
            o2 = st.columns(4)
            o2[0].metric("Cadence เฉลี่ย", _fmt(arow.get("avg_cadence"), " spm"), border=True)
            o2[1].metric("แคลอรี่", _fmt(arow.get("calories"), " kcal"), border=True)
            o2[2].metric("ไต่ระดับรวม", _fmt(arow.get("elevation_gain_m"), " m"), border=True)
            o2[3].metric("Power เฉลี่ย", _fmt(arow.get("avg_power"), " W"), border=True)

            r1 = st.columns(4)
            r1[0].metric("TE แอโรบิก", _fmt(arow.get("training_effect_aerobic"), "", "{:.1f}"), border=True)
            r1[1].metric("TE แอนแอโรบิก", _fmt(arow.get("training_effect_anaerobic"), "", "{:.1f}"), border=True)
            r1[2].metric("Training Load", _fmt(arow.get("training_load")), border=True)
            r1[3].metric("Impact Load", _fmt(arow.get("impact_load")), border=True)

            r2 = st.columns(4)
            r2[0].metric("HR ต่ำสุด", _fmt(arow.get("min_hr"), " bpm"), border=True)
            r2[1].metric("HR สูงสุด", _fmt(arow.get("max_hr"), " bpm"), border=True)
            r2[2].metric("เหงื่อ (ประมาณ)", _fmt(arow.get("sweat_loss_ml"), " ml"), border=True)
            r2[3].metric("Δ Body Battery", _fmt(arow.get("diff_body_battery")), border=True)

            if pd.notna(arow.get("begin_stamina")) or pd.notna(arow.get("end_stamina")):
                b, e = arow.get("begin_stamina"), arow.get("end_stamina")
                sc = st.columns(4)
                sc[0].metric("Stamina เริ่ม", _fmt(b, "%"), border=True)
                sc[1].metric("Stamina จบ", _fmt(e, "%"), border=True)
                sc[2].metric(
                    "Stamina ใช้ไป",
                    _fmt((b - e) if (pd.notna(b) and pd.notna(e)) else float("nan"), "%"),
                    border=True,
                )

            if pd.notna(arow.get("avg_ground_contact_time_ms")):
                dc = st.columns(4)
                dc[0].metric("Ground Contact", _fmt(arow.get("avg_ground_contact_time_ms"), " ms"), border=True)
                dc[1].metric(
                    "Vertical Osc",
                    _fmt(arow.get("avg_vertical_oscillation_cm"), " cm", "{:.1f}"),
                    border=True,
                )
                dc[2].metric(
                    "Vertical Ratio",
                    _fmt(arow.get("avg_vertical_ratio"), " %", "{:.1f}"),
                    border=True,
                )
                dc[3].metric("Stride Length", _fmt(arow.get("avg_stride_length_cm"), " cm"), border=True)

            if pd.notna(arow.get("weather_temp_c")):
                wc = st.columns(4)
                wc[0].metric("อุณหภูมิ", _fmt(arow.get("weather_temp_c"), " °C", "{:.1f}"), border=True)
                wc[1].metric(
                    "รู้สึกเหมือน",
                    _fmt(arow.get("weather_apparent_temp_c"), " °C", "{:.1f}"),
                    border=True,
                )
                wc[2].metric("ความชื้น", _fmt(arow.get("weather_humidity"), " %"), border=True)
                wc[3].metric("ลม", _fmt(arow.get("weather_wind_kph"), " km/h"), border=True)

            # ฟิลด์ต่อไปนี้ถูกเก็บใน fact_activity มาตลอด แต่หน้าเดิมไม่เคยแสดง
            # ทำให้ดูเหมือน sync มาไม่ครบ ทั้งที่ข้อมูลจริงอยู่ใน SQLite แล้ว.
            def _has_any(*fields):
                return any(pd.notna(arow.get(field)) for field in fields)

            if _has_any(
                "moving_duration_sec", "steps", "moderate_intensity_min",
                "vigorous_intensity_min",
            ):
                st.markdown("**เวลาและกิจกรรม**")
                tc = st.columns(4)
                tc[0].metric("เวลาที่เคลื่อนไหว", _dur(arow.get("moving_duration_sec")), border=True)
                tc[1].metric("จำนวนก้าวในกิจกรรม", _fmt(arow.get("steps"), " ก้าว"), border=True)
                tc[2].metric(
                    "Intensity ปานกลาง",
                    _fmt(arow.get("moderate_intensity_min"), " นาที"),
                    border=True,
                )
                tc[3].metric(
                    "Intensity หนัก",
                    _fmt(arow.get("vigorous_intensity_min"), " นาที"),
                    border=True,
                )

            if _has_any(
                "avg_speed_mps", "max_speed_mps", "avg_grade_adjusted_speed_mps",
            ):
                st.markdown("**ความเร็วจาก Garmin**")

                def _speed_kph(value):
                    return (_fmt(value * 3.6, " km/h", "{:.1f}")
                            if pd.notna(value) else "–")

                vc = st.columns(3)
                vc[0].metric("ความเร็วเฉลี่ย", _speed_kph(arow.get("avg_speed_mps")), border=True)
                vc[1].metric("ความเร็วสูงสุด", _speed_kph(arow.get("max_speed_mps")), border=True)
                vc[2].metric(
                    "Grade-adjusted speed",
                    _speed_kph(arow.get("avg_grade_adjusted_speed_mps")),
                    border=True,
                )

            if _has_any("vo2max_value", "normalized_power", "max_power", "max_cadence"):
                st.markdown("**สมรรถนะในกิจกรรม**")
                pc = st.columns(4)
                pc[0].metric(
                    "VO2max จากกิจกรรม",
                    _fmt(arow.get("vo2max_value"), "", "{:.1f}"),
                    border=True,
                )
                pc[1].metric("Normalized Power", _fmt(arow.get("normalized_power"), " W"), border=True)
                pc[2].metric("Power สูงสุด", _fmt(arow.get("max_power"), " W"), border=True)
                pc[3].metric("Cadence สูงสุด", _fmt(arow.get("max_cadence"), " spm"), border=True)

            if _has_any(
                "elevation_loss_m", "min_elevation_m", "max_elevation_m", "bmr_calories",
            ):
                st.markdown("**ระดับความสูงและพลังงานเพิ่มเติม**")
                ec = st.columns(4)
                ec[0].metric("ลงระดับรวม", _fmt(arow.get("elevation_loss_m"), " m"), border=True)
                ec[1].metric("ระดับต่ำสุด", _fmt(arow.get("min_elevation_m"), " m"), border=True)
                ec[2].metric("ระดับสูงสุด", _fmt(arow.get("max_elevation_m"), " m"), border=True)
                ec[3].metric("BMR calories", _fmt(arow.get("bmr_calories"), " kcal"), border=True)

            activity_meta = []
            if pd.notna(arow.get("activity_type")):
                activity_meta.append(f"ประเภท: {arow.get('activity_type')}")
            if pd.notna(arow.get("training_effect_label")):
                activity_meta.append(f"Training effect: {arow.get('training_effect_label')}")
            if pd.notna(arow.get("location_name")):
                activity_meta.append(f"สถานที่: {arow.get('location_name')}")
            if activity_meta:
                st.caption(" · ".join(activity_meta))
            if _has_any("start_latitude", "start_longitude"):
                latitude = arow.get("start_latitude")
                longitude = arow.get("start_longitude")
                coordinate = (
                    f"{latitude:.6f}, {longitude:.6f}"
                    if pd.notna(latitude) and pd.notna(longitude) else "พิกัดไม่ครบ"
                )
                st.caption(f"พิกัดเริ่มกิจกรรม: {coordinate}")

        zc = ["hr_zone1_sec", "hr_zone2_sec", "hr_zone3_sec", "hr_zone4_sec", "hr_zone5_sec"]
        if set(zc).issubset(activity_df.columns) and arow[zc].notna().any():
            zvals = [float(arow.get(c)) / 60 if pd.notna(arow.get(c)) else 0.0 for c in zc]
            if sum(zvals) > 0:
                zbar = pd.DataFrame({"โซน": ["Z1", "Z2", "Z3", "Z4", "Z5"], "นาที": zvals})
                fig_z = px.bar(zbar, x="โซน", y="นาที", color="โซน",
                               title="เวลาในโซน HR ของเซสชันนี้ (นาที)",
                               color_discrete_sequence=BLUE_RAMP_5)
                fig_z.update_layout(showlegend=False)
                st.plotly_chart(fig_z, width="stretch")

        # ⚠️ ห้ามกรอง splits ตามความยาวรอบ (แก้ 7 ส.ค. 69) — แถวใน fact_activity_split
        # คือ "lap ที่นาฬิกาบันทึก" ไม่ใช่ "ทุก 1 กม." เซสชัน interval สั้น ๆ จึงมีรอบ
        # หลักสิบเมตรเป็นเรื่องปกติ. ตัวกรอง `distance_m >= 100` เดิมลบทั้งเซสชันทิ้ง
        # แล้วหน้าเว็บขึ้น "ยังไม่ได้ดึง splits" ทั้งที่ดึงมาครบ (ต้อง activity 23885677442:
        # 0.85 กม. 12 รอบ 12–92 ม. — รวม 6 เซสชันใน DB ที่โดนแบบเดียวกัน)
        # → ข้อความ "ยังไม่ได้ดึง" ต้องผูกกับ "load_splits ไม่คืนแถวเลย" เท่านั้น
        splits = load_splits(chosen_id)

        if splits.empty:
            if pd.isna(arow.get("distance_m")) or arow.get("distance_m") <= 0:
                st.info("กิจกรรมนี้ไม่มีระยะทางจาก Garmin จึงไม่มี splits โดยปกติ "
                        "แต่ตัวเลขเวลา, HR และ Training Load ด้านบนยังแสดงครบตามที่นาฬิกาส่ง")
            else:
                st.info("ยังไม่ได้ดึง splits — fast sync จะลองเติมให้อัตโนมัติในรอบถัดไป "
                        "และ full sync 21:00 จะตรวจซ้ำ")
        else:
            # --- ครึ่งแรก vs ครึ่งหลัง: แสดงเลขดิบ ไม่ตัดสินโดยไม่รู้เป้าหมายเซสชัน ---
            if len(splits) >= 2:
                p1, p2, hr1, hr2 = analyze_distance_halves(splits)

                split_pct = (p2 - p1) / p1 * 100 if pd.notna(p1) and pd.notna(p2) and p1 > 0 else float("nan")

                with st.container(horizontal=True):
                    st.metric("ครึ่งแรก", f"{fmt_pace(p1)} /km", border=True)
                    st.metric("ครึ่งหลัง", f"{fmt_pace(p2)} /km", border=True)
                    st.metric(
                        "เพซครึ่งหลังเทียบครึ่งแรก",
                        f"{split_pct:+.1f}%" if pd.notna(split_pct) else "–",
                        delta_color="off", border=True,
                        help="ค่าบวก = ครึ่งหลังช้ากว่า; ต้องอ่านตามเป้าหมายเซสชัน "
                             "เส้นทาง และความชัน ไม่ใช้เส้นตัด ±2% สากล",
                    )
                    if pd.notna(hr1) and pd.notna(hr2):
                        st.metric("HR ครึ่งแรก → หลัง", f"{hr1:.0f} → {hr2:.0f} bpm",
                                  delta=fmt_signed_delta(hr2 - hr1, " bpm"),
                                  delta_color="off", border=True)

            # --- กราฟ pace + HR (แกน x ร่วม สองแถว — ไม่ใช้ dual-axis) ---
            x_labels = [f"{int(n)}" for n in splits["split_num"]]
            pace_txt = [fmt_pace(p) for p in splits["avg_pace_min_km"]]
            dist_km = (splits["distance_m"] / 1000).round(2)

            fig_sp = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                   vertical_spacing=0.07, row_heights=[0.55, 0.45])
            fig_sp.add_trace(go.Scatter(
                x=x_labels, y=splits["avg_pace_min_km"], mode="lines+markers",
                line=dict(color=C_BLUE, width=2), marker=dict(size=8), name="เพซ",
                customdata=list(zip(pace_txt, dist_km)),
                hovertemplate="รอบที่ %{x} (%{customdata[1]} กม.)<br>เพซ %{customdata[0]} /กม.<extra></extra>",
            ), row=1, col=1)
            if splits["avg_hr"].notna().any():
                fig_sp.add_trace(go.Scatter(
                    x=x_labels, y=splits["avg_hr"], mode="lines+markers",
                    line=dict(color=SERIES_COLORS["avg_hr"], width=2),
                    marker=dict(size=8), name="HR เฉลี่ย",
                    hovertemplate="รอบที่ %{x}<br>HR %{y:.0f} bpm<extra></extra>",
                ), row=2, col=1)

            pace_clean = splits["avg_pace_min_km"].dropna()
            pace_axis_kwargs = {}
            if not pace_clean.empty:
                tickvals, ticktext = pace_axis_ticks(pace_clean)
                pace_axis_kwargs = {"tickvals": tickvals, "ticktext": ticktext}
            fig_sp.update_yaxes(title_text="เพซ (นาที/กม.)", autorange="reversed",
                                row=1, col=1, **pace_axis_kwargs)
            fig_sp.update_yaxes(title_text="HR (bpm)", row=2, col=1)
            fig_sp.update_xaxes(title_text="รอบที่ (Split)", row=2, col=1)
            fig_sp.update_layout(title="เพซและ HR ราย Split (เพซ: ยิ่งสูง = ยิ่งเร็ว)",
                                 showlegend=True, hovermode="x unified",
                                 legend=dict(orientation="h", yanchor="bottom", y=1.02))
            st.plotly_chart(fig_sp, width="stretch")

            # --- กราฟ Cadence + Power + Elevation ราย Split ---
            extra_rows = []
            if splits["avg_cadence"].notna().any():
                extra_rows.append(("avg_cadence", "Cadence (spm)", SERIES_COLORS["avg_cadence"]))
            if "avg_power" in splits and splits["avg_power"].notna().any():
                extra_rows.append(("avg_power", "Power (W)", SERIES_COLORS["avg_power"]))
            if splits["elevation_gain_m"].notna().any():
                extra_rows.append(("elevation_gain_m", "Elevation Gain (m)", SERIES_COLORS["elevation_gain_m"]))

            if extra_rows:
                fig_extra = make_subplots(
                    rows=len(extra_rows), cols=1, shared_xaxes=True,
                    vertical_spacing=0.12,
                    subplot_titles=[t for _, t, _ in extra_rows])
                for i, (col, title, color) in enumerate(extra_rows, 1):
                    fig_extra.add_trace(go.Bar(
                        x=x_labels, y=splits[col], name=title,
                        marker_color=color,
                        hovertemplate=f"รอบที่ %{{x}}<br>{title}: %{{y:.0f}}<extra></extra>",
                    ), row=i, col=1)
                fig_extra.update_xaxes(title_text="รอบที่ (Split)", row=len(extra_rows), col=1)
                fig_extra.update_layout(showlegend=False, title="Cadence และ Elevation ราย Split")
                st.plotly_chart(fig_extra, width="stretch")

            # --- ตาราง splits รายรอบ เต็ม (แสดงตรง ไม่ซ่อนใน expander) ---
            st.subheader("ตาราง Splits (ผลต่อรอบ)")
            num0 = st.column_config.NumberColumn(format="%.0f")
            table_data = {
                "รอบที่": splits["split_num"].astype(int),
                "ระยะ (km)": dist_km,
                # เวลาต่อรอบคือค่าที่นาฬิกาวัดตรง ๆ ส่วนเพซเป็นค่าที่หารมาอีกที —
                # เซสชัน interval (เที่ยว ~19 วิ สลับพัก ~50 วิ) อ่านจากเพซไม่ได้เลย
                # เพราะเพซของเที่ยวพักกลายเป็น 14:40 ทั้งที่ duration_sec มีครบทุกแถว
                "เวลา": [fmt_sec(value) for value in splits["duration_sec"]],
                "เพซ": pace_txt,
                "HR เฉลี่ย": splits["avg_hr"],
                "HR สูงสุด": splits["max_hr"],
                "Cadence": splits["avg_cadence"],
            }
            cfg = {"HR เฉลี่ย": num0, "HR สูงสุด": num0, "Cadence": num0}

            def _add(colname, label, fmt=num0):
                if colname in splits and splits[colname].notna().any():
                    table_data[label] = splits[colname]
                    if fmt is not None:
                        cfg[label] = fmt

            _add("avg_power", "Power (W)")
            _add("max_power", "Power สูงสุด (W)")
            _add("normalized_power", "Normalized Power (W)")
            _add("avg_stride_length_cm", "Stride (cm)")
            _add("ground_contact_time_ms", "GCT (ms)")
            _add("vertical_oscillation_cm", "Vert Osc (cm)",
                 st.column_config.NumberColumn(format="%.1f"))
            _add("vertical_ratio", "Vertical Ratio (%)",
                 st.column_config.NumberColumn(format="%.1f"))
            _add("max_cadence", "Cadence สูงสุด")
            if "avg_speed_mps" in splits and splits["avg_speed_mps"].notna().any():
                table_data["ความเร็วเฉลี่ย (km/h)"] = splits["avg_speed_mps"] * 3.6
                cfg["ความเร็วเฉลี่ย (km/h)"] = st.column_config.NumberColumn(format="%.1f")
            table_data["ไต่ (m)"] = splits["elevation_gain_m"]
            cfg["ไต่ (m)"] = num0
            _add("elevation_loss_m", "ลง (m)")
            _add("intensity_type", "ประเภท", None)  # text

            st.dataframe(pd.DataFrame(table_data), hide_index=True, column_config=cfg)
