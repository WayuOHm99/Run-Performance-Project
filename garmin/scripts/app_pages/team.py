"""หน้าแรก "ภาพรวมสุขภาพทีม — วันที่เลือก"

ทุกตัวเลขบนหน้านี้ผูกกับ **วันที่เลือกวันเดียว** (ค่าเริ่มต้นคือวันนี้ตามเวลาไทย)
ไม่หยิบค่าล่าสุดของแต่ละช่องจากคนละวันมาประกอบการ์ดเดียว และไม่ใช้ยอดรวม 7 วัน
ถ้าวันที่เลือกไม่มีค่าช่องไหน จะบอกว่า "ไม่มี" แล้วแสดงค่าครั้งก่อนแยกพร้อมวันที่ของมัน

ไม่มีสถานะหรือธงที่ระบบตัดสินเอง — คำของ Garmin (เช่น HRV "Balanced") แสดงตามจริง
"""

import datetime
import html

import pandas as pd
import streamlit as st
from dashboard_charts import intraday_frame_and_spec
from dashboard_context import (
    chart_header,
    focus_athlete,
    page_context,
    page_lead,
    section_heading,
)
from dashboard_data import (
    athlete_has_training_readiness,
    load_intraday,
    load_team_activities,
    load_wellness_data,
)
from dashboard_domain import (
    INTRADAY_METRICS,
    _to_datetime,
    activity_rows,
    activity_title,
    day_row,
    day_status,
    duplicate_suspects,
    fmt_hours,
    fmt_num,
    fmt_pace,
    fmt_recovery_time,
    fmt_sec,
    garmin_label,
    intraday_series,
    last_before,
    to_bangkok_timestamp,
    value_of,
)

ctx = page_context()
today = ctx.today
DAY_KEY = "team_day"
FALLBACK_DAYS = 30  # ค่าครั้งก่อนที่ยอมย้อนไปหา เมื่อวันที่เลือกไม่มีค่านั้น
OPTIONAL_ACTIVITY_COLS = ("HR เฉลี่ย", "HR สูงสุด", "Training Effect", "Training Load")

INTRADAY_GUIDES = {
    "heart_rate": (
        "ชีพจรระหว่างวันเทียบทั้งทีม (Heart Rate)",
        "หน่วย bpm บนแกนเวลา 00:00–24:00 น. · ช่วงยอดกราฟสูงมักตรงกับเวลาซ้อม · เส้นขาดคือช่วงไม่ได้ใส่นาฬิกา",
    ),
    "stress": (
        "ความเครียดทางสรีรวิทยาระหว่างวัน (Stress)",
        "คะแนน 0–100 · Garmin งดวัด Stress ขณะวิ่งหรือออกกำลังกาย เส้นกราฟจึงเว้นว่างช่วงซ้อมตามปกติ",
    ),
    "body_battery": (
        "ระดับพลังงานระหว่างวัน (Body Battery)",
        "คะแนน 5–100 · กราฟไต่ขึ้นช่วงนอนหลับพักฟื้น และค่อย ๆ ลดลงตามการใช้พลังงานระหว่างวัน",
    ),
}

if DAY_KEY not in st.session_state or st.session_state[DAY_KEY] > today:
    st.session_state[DAY_KEY] = today


def shift_day(days):
    st.session_state[DAY_KEY] = min(today, st.session_state[DAY_KEY]
                                    + datetime.timedelta(days=days))


def go_today():
    st.session_state[DAY_KEY] = today


st.title("ภาพรวมสุขภาพทีม")
page_lead("สรุปสุขภาพเช้าและกิจกรรมซ้อมของทุกคนเฉพาะวันที่เลือก ไม่นำค่าคนละวันมาปนกันบนการ์ด")

day_preview = st.session_state[DAY_KEY]
day_activities = load_team_activities(day_preview.isoformat(), day_preview.isoformat())
suspects = duplicate_suspects(day_activities)

with (
    st.container(key="team-toolbar"),
    st.container(horizontal=True, vertical_alignment="center"),
):
    st.button("วันก่อนหน้า", icon=":material/chevron_left:", on_click=shift_day, args=(-1,),
              key="team-prev-day")
    st.date_input("วันที่", key=DAY_KEY, max_value=today, format="DD/MM/YYYY",
                  width=155, label_visibility="collapsed")
    st.button("วันถัดไป", icon=":material/chevron_right:", on_click=shift_day, args=(1,),
              key="team-next-day", disabled=st.session_state[DAY_KEY] >= today)
    st.button("วันนี้", icon=":material/today:", on_click=go_today, key="team-today",
              disabled=st.session_state[DAY_KEY] == today)
    day_offset = (today - st.session_state[DAY_KEY]).days
    st.badge(
        "วันนี้ (เวลาไทย)" if day_offset == 0 else f"ย้อนหลัง {day_offset} วัน",
        icon=":material/calendar_today:",
        color="blue" if day_offset == 0 else "gray",
    )
    st.badge(
        f"นักกีฬา {len(ctx.athletes_df)} คน · กิจกรรม {len(day_activities)} รายการ",
        icon=":material/groups:",
        color="gray",
    )

day = st.session_state[DAY_KEY]
day_word = "วันนี้" if day == today else "วันนั้น"
section_heading(
    f"สรุปรายคนประจำวันที่ {day.strftime('%d/%m/%Y')}",
    f"Sleep และ HRV คือผลคืนที่ตื่นเช้า{day_word} · ช่องที่ยังไม่มีข้อมูลจะระบุค่าครั้งก่อนพร้อมวันกำกับ",
)


def _esc(value):
    return html.escape(str(value), quote=False)


def missing_note(wellness, column, unit=""):
    """ค่าของวันที่เลือกไม่มี → บอกค่าครั้งก่อนพร้อมวันที่ ให้เห็นว่าเป็นคนละวันชัด ๆ"""
    previous = last_before(wellness, column, day)
    if not previous:
        return f"ไม่มีของ{day_word}"
    return f"ไม่มีของ{day_word} · ครั้งก่อน {fmt_num(previous['value'], unit)} ({previous['date']:%d/%m})"


def athlete_card(athlete, order):
    aid = athlete["athlete_id"]
    name = ctx.athlete_labels[aid]
    wellness = load_wellness_data(
        aid, (day - datetime.timedelta(days=FALLBACK_DAYS)).isoformat(), day.isoformat())
    row = day_row(wellness, day)
    status_key, status_text = day_status(row, day, today)

    def build_tile(label, column, unit="", note=None, digits=None):
        value = value_of(row, column)
        if value is None:
            return (label, "–", missing_note(wellness, column, unit))
        return (label, fmt_num(value, unit, digits), note)

    with st.container(border=True, key=f"team-card-{order}-{status_key}"):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.subheader(name, anchor=False)
            st.badge(status_text,
                     icon={"complete_day": ":material/check_circle:",
                           "partial_today": ":material/schedule:"}.get(
                               status_key, ":material/cloud_off:"),
                     color={"complete_day": "green", "partial_today": "blue"}.get(
                         status_key, "orange"))
        fetched = to_bangkok_timestamp(value_of(row, "fetched_at"))
        if pd.notna(fetched):
            st.caption(f"ซิงก์ล่าสุด {fetched:%d/%m · %H:%M} น.")

        high, low = value_of(row, "body_battery_high"), value_of(row, "body_battery_low")
        card_tiles = [
            build_tile("Sleep score", "sleep_score",
                       note=fmt_hours(value_of(row, "sleep_duration_sec"))
                       if value_of(row, "sleep_duration_sec") is not None else None),
            build_tile("HRV เมื่อคืน", "hrv_last_night", " ms",
                       note=garmin_label(value_of(row, "hrv_status")) or None),
            build_tile("RHR", "resting_hr", " bpm"),
            build_tile("Body Battery ล่าสุด", "bb_most_recent",
                       note=f"สูง {fmt_num(high)} · ต่ำ {fmt_num(low)}"
                       if high is not None or low is not None else None),
            build_tile("Stress เฉลี่ย", "stress_avg",
                       note=f"สูงสุด {fmt_num(value_of(row, 'max_stress'))}"
                       if value_of(row, "max_stress") is not None else None),
        ]
        if athlete_has_training_readiness(aid):
            card_tiles.append(
                build_tile("Training Readiness", "training_readiness",
                           note=garmin_label(value_of(row, "readiness_level")) or None)
            )

        for idx in range(0, len(card_tiles), 2):
            pair = card_tiles[idx:idx + 2]
            cols = st.columns(2, gap="small")
            for col, (label, val_text, note_text) in zip(cols, pair, strict=False):
                with col:
                    st.metric(label, val_text, note_text,
                              delta_color="off", delta_arrow="off", width="stretch")

        chips = []
        if value_of(row, "training_status") is not None:
            chips.append(
                f'<span class="rp-chip rp-chip-blue">Training Status '
                f'<strong>{_esc(garmin_label(row["training_status"]))}</strong></span>'
            )
        if value_of(row, "recovery_time_min") is not None:
            chips.append(
                f'<span class="rp-chip">Recovery '
                f'<strong>{_esc(fmt_recovery_time(row["recovery_time_min"]))}</strong></span>'
            )
        if value_of(row, "steps") is not None:
            chips.append(
                f'<span class="rp-chip">ก้าว '
                f'<strong class="rp-num">{row["steps"]:,.0f}</strong></span>'
            )
        if chips:
            st.markdown(f'<div class="rp-chip-row">{"".join(chips)}</div>', unsafe_allow_html=True)

        mine = day_activities[day_activities["athlete_id"] == aid] if not day_activities.empty \
            else day_activities
        if mine.empty:
            st.markdown(
                f'<div class="rp-act-box"><div class="rp-act-empty">'
                f'ไม่มีกิจกรรมซ้อมใน{day_word}</div></div>',
                unsafe_allow_html=True,
            )
        else:
            mine = mine.assign(_when=_to_datetime(mine["start_time_local"])).sort_values(
                "_when", na_position="last"
            )
            act_rows = []
            for _, activity in mine.iterrows():
                distance = activity.get("distance_m")
                when = activity.get("_when")
                has_dist = pd.notna(distance) and distance > 0
                meta_parts = [
                    f'<span class="rp-num">{distance / 1000:.2f} km</span>' if has_dist else None,
                    f'<span class="rp-num">{_esc(fmt_sec(activity.get("duration_sec")))}</span>',
                    f'<span class="rp-num">{_esc(fmt_pace(activity.get("avg_pace_min_per_km")))} /km</span>'
                    if has_dist else None,
                    f'<span class="rp-num">HR {activity["avg_hr"]:.0f}</span>'
                    if pd.notna(activity.get("avg_hr")) else None,
                ]
                meta_clean = " · ".join(p for p in meta_parts if p and ">–<" not in p)
                time_badge = (
                    f'<span class="rp-num" style="color:#667085">{when.strftime("%H:%M")}</span>'
                    if pd.notna(when) else ""
                )
                dup_badge = (
                    '<span class="rp-warn-tag">⚠ อาจซ้ำ</span>'
                    if int(activity["activity_id"]) in suspects else ""
                )
                act_rows.append(
                    f'<div class="rp-act-item">{time_badge}'
                    f'<strong>{_esc(activity_title(activity))}</strong>'
                    f'<span style="color:#475467">{meta_clean}</span>{dup_badge}</div>'
                )
            st.markdown(f'<div class="rp-act-box">{"".join(act_rows)}</div>', unsafe_allow_html=True)

        st.button(f"ดูข้อมูลของ {name}", key=f"open-athlete-{order}",
                  on_click=focus_athlete, args=(aid,), icon=":material/arrow_forward:",
                  type="tertiary")


athletes = ctx.athletes_df.to_dict("records")
for row_start in range(0, len(athletes), 3):
    columns = st.columns(3)
    for column, (order, athlete) in zip(
            columns, enumerate(athletes[row_start:row_start + 3], start=row_start), strict=False):
        with column:
            athlete_card(athlete, order)

section_heading("แนวโน้มระหว่างวันและตารางกิจกรรมรวม", f"ข้อมูลประจำวันที่ {day.strftime('%d/%m/%Y')}")

with st.container(border=True, key="surface-team-intraday"):
    intraday = load_intraday(day)
    if intraday.empty:
        chart_header(st, "เทียบระหว่างวันทั้งทีม", f"ยังไม่มีข้อมูลระหว่างวันของ{day_word}")
    else:
        labels = {key: label for key, (label, _) in INTRADAY_METRICS.items()}
        chosen = st.segmented_control("ค่า", options=list(labels), format_func=labels.get,
                                      default="heart_rate", required=True, key="team_intraday_metric",
                                      label_visibility="collapsed")
        names = ctx.athlete_labels
        series = intraday_series(intraday, chosen)
        title_text, guide_text = INTRADAY_GUIDES[chosen]
        unit_text = INTRADAY_METRICS[chosen][1]
        unit_suffix = f" {unit_text}" if unit_text else ""
        if series["ค่า"].notna().any():
            valid_vals = series["ค่า"].dropna()
            stat_text = f"ต่ำสุด–สูงสุดทั้งทีม {fmt_num(valid_vals.min())}{'–' + fmt_num(valid_vals.max(), unit_suffix)}"
            chart_header(st, title_text, guide_text, stat_text)
            in_frame, in_spec = intraday_frame_and_spec(
                series, day, y_title=unit_text, names=names, height=240,
            )
            st.vega_lite_chart(in_frame, in_spec, width="stretch")
        else:
            chart_header(st, title_text, f"ไม่มีข้อมูล {labels[chosen]} ระหว่างวันของ{day_word}")

with st.container(border=True, key="surface-team-activities"):
    chart_header(
        st,
        f"กิจกรรมของทีมใน{day_word}",
        "แสดงทุกกิจกรรมที่ซิงก์แล้วของวันที่เลือก เรียงจากเวลาเริ่มล่าสุด",
        f"{len(day_activities)} รายการ" if not day_activities.empty else None,
    )
    if day_activities.empty:
        st.caption(f"ไม่มีกิจกรรมที่ Garmin บันทึกใน{day_word}")
    else:
        ordered = day_activities.assign(_when=_to_datetime(day_activities["start_time_local"])).sort_values(
            ["_when", "activity_id"], ascending=[False, False], na_position="last", kind="stable"
        )
        table = activity_rows(ordered)
        table.insert(1, "นักกีฬา", ordered["athlete_id"].map(ctx.athlete_labels).fillna(
            ordered["display_name"]
        ).reset_index(drop=True))
        empty_optional = [c for c in OPTIONAL_ACTIVITY_COLS if c in table and table[c].isna().all()]
        if empty_optional:
            table = table.drop(columns=empty_optional)
        table["ตรวจสอบ"] = ["อาจซ้ำ" if int(aid) in suspects else ""
                            for aid in ordered["activity_id"]]
        st.dataframe(
            table, hide_index=True, width="stretch",
            column_config={
                "ระยะ (km)": st.column_config.NumberColumn(format="%.2f"),
                "HR เฉลี่ย": st.column_config.NumberColumn(format="%d"),
                "HR สูงสุด": st.column_config.NumberColumn(format="%d"),
                "Training Effect": st.column_config.NumberColumn(format="%.1f"),
                "Training Load": st.column_config.NumberColumn(format="%d"),
                "ตรวจสอบ": st.column_config.TextColumn(
                    help="คนเดียวกัน เริ่มเวลาเดียวกัน ชนิดเดียวกัน แต่ Garmin เก็บเป็นคนละรายการ "
                         "(เช่นบันทึกจากสองอุปกรณ์) ระบบไม่ลบหรือรวมเอง — ตรวจใน Garmin Connect"),
            },
        )
        if suspects:
            st.caption(f"มี {len(suspects)} รายการที่อาจซ้ำ — ยังนับรวมอยู่ในยอดทุกหน้า "
                       "จนกว่าจะลบรายการที่ซ้ำใน Garmin Connect")

st.caption("ข้อมูลทั้งหมดมาจาก Garmin · ก่อนซ้อมต้องถามอาการเจ็บ ป่วย และความล้าจากนักกีฬาเอง")
