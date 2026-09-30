"""หน้าแรก "ภาพรวมสุขภาพทีม — วันที่เลือก"

ทุกตัวเลขบนหน้านี้ผูกกับ **วันที่เลือกวันเดียว** (ค่าเริ่มต้นคือวันนี้ตามเวลาไทย)
ไม่หยิบค่าล่าสุดของแต่ละช่องจากคนละวันมาประกอบการ์ดเดียว และไม่ใช้ยอดรวม 7 วัน
ถ้าวันที่เลือกไม่มีค่าช่องไหน จะบอกว่า "ไม่มี" แล้วแสดงค่าครั้งก่อนแยกพร้อมวันที่ของมัน

ไม่มีสถานะหรือธงที่ระบบตัดสินเอง — คำของ Garmin (เช่น HRV "Balanced") แสดงตามจริง
"""

import datetime

import pandas as pd
import streamlit as st

from dashboard_charts import intraday_chart
from dashboard_context import focus_athlete, page_context
from dashboard_data import (
    athlete_has_training_readiness,
    load_intraday,
    load_team_activities,
    load_wellness_data,
)
from dashboard_domain import (
    INTRADAY_METRICS,
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

if DAY_KEY not in st.session_state or st.session_state[DAY_KEY] > today:
    st.session_state[DAY_KEY] = today


def shift_day(days):
    st.session_state[DAY_KEY] = min(today, st.session_state[DAY_KEY]
                                    + datetime.timedelta(days=days))


def go_today():
    st.session_state[DAY_KEY] = today


st.title("ภาพรวมสุขภาพทีม")
with st.container(horizontal=True, vertical_alignment="bottom"):
    st.button("วันก่อนหน้า", icon=":material/chevron_left:", on_click=shift_day, args=(-1,),
              key="team-prev-day")
    st.date_input("วันที่", key=DAY_KEY, max_value=today, format="DD/MM/YYYY", width=170)
    st.button("วันถัดไป", icon=":material/chevron_right:", on_click=shift_day, args=(1,),
              key="team-next-day", disabled=st.session_state[DAY_KEY] >= today)
    st.button("วันนี้", icon=":material/today:", on_click=go_today, key="team-today",
              disabled=st.session_state[DAY_KEY] == today)
day = st.session_state[DAY_KEY]
st.caption(
    f"ข้อมูลของวันที่ {day.strftime('%d/%m/%Y')} ตามปฏิทินของ Garmin (เวลาไทย) · "
    "Sleep/HRV คือคืนที่ตื่นเช้าวันนี้ · ค่าที่ไม่มีของวันนี้จะบอกค่าครั้งก่อนแยกพร้อมวันที่")

day_activities = load_team_activities(day.isoformat(), day.isoformat())
suspects = duplicate_suspects(day_activities)


def metric(label, value, note=None):
    # กว้างคงที่ให้วางได้สองใบต่อแถวในการ์ดสามคอลัมน์ บนมือถือเรียงลงเป็นแถวเดียว
    st.metric(label, value, note, delta_color="off", delta_arrow="off", width=125)


def missing_note(wellness, column, unit=""):
    """ค่าของวันนี้ไม่มี → บอกค่าครั้งก่อนพร้อมวันที่ ให้เห็นว่าเป็นคนละวันชัด ๆ"""
    previous = last_before(wellness, column, day)
    if not previous:
        return "ไม่มีของวันนี้"
    return f"ไม่มีของวันนี้ · ครั้งก่อน {fmt_num(previous['value'], unit)} ({previous['date']:%d/%m})"


def athlete_card(athlete, order):
    aid, name = athlete["athlete_id"], athlete["display_name"]
    wellness = load_wellness_data(
        aid, (day - datetime.timedelta(days=FALLBACK_DAYS)).isoformat(), day.isoformat())
    row = day_row(wellness, day)
    status_key, status_text = day_status(row, day, today)

    def show(label, column, unit="", note=None, digits=None):
        value = value_of(row, column)
        if value is None:
            metric(label, "–", missing_note(wellness, column, unit))
        else:
            metric(label, fmt_num(value, unit, digits), note)

    with st.container(border=True, key=f"team-card-{order}"):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.subheader(name, anchor=False)
            st.badge(status_text,
                     icon={"complete_day": ":material/check:",
                           "partial_today": ":material/schedule:"}.get(
                               status_key, ":material/cloud_off:"),
                     color={"complete_day": "green", "partial_today": "blue"}.get(
                         status_key, "orange"))
        # ไม่โชว์ชื่ออุปกรณ์บนการ์ด — ทะเบียนอุปกรณ์ของ Garmin ไม่บอกว่าตัวไหนเป็นนาฬิกาหลัก
        # (is_primary_* เป็น NULL ทุกแถว) การ์ดของ P'kao จึงขึ้น "HRM 600" สายคาดอกแทน fenix 8
        # รายชื่ออุปกรณ์ทั้งหมดยังดูได้ใน "ข้อมูลที่ Garmin ส่งมา" บน sidebar
        fetched = to_bangkok_timestamp(value_of(row, "fetched_at"))
        if pd.notna(fetched):
            st.caption(f"แถวนี้ดึงจาก Garmin ล่าสุด {fetched:%d/%m %H:%M} น.")

        with st.container(horizontal=True, gap="small"):
            show("Sleep score", "sleep_score",
                 note=fmt_hours(value_of(row, "sleep_duration_sec"))
                 if value_of(row, "sleep_duration_sec") is not None else None)
            # สถานะของ Garmin อย่างเดียว — ค่าเฉลี่ย 7 วันอยู่ในกราฟหน้า "ร่างกาย"
            # ใส่ทั้งสองอย่างแล้วถูกตัดท้ายบนจอมือถือ 375 px จนอ่านสถานะไม่ครบ
            show("HRV เมื่อคืน", "hrv_last_night", " ms",
                 note=garmin_label(value_of(row, "hrv_status")) or None)
            show("RHR", "resting_hr", " bpm")
            high, low = value_of(row, "body_battery_high"), value_of(row, "body_battery_low")
            show("Body Battery ล่าสุด", "bb_most_recent",
                 note=f"สูง {fmt_num(high)} · ต่ำ {fmt_num(low)}"
                 if high is not None or low is not None else None)
            show("Stress เฉลี่ย", "stress_avg",
                 note=f"สูงสุด {fmt_num(value_of(row, 'max_stress'))}"
                 if value_of(row, "max_stress") is not None else None)
            if athlete_has_training_readiness(aid):
                show("Training Readiness", "training_readiness",
                     note=garmin_label(value_of(row, "readiness_level")) or None)

        garmin_words = []
        if value_of(row, "training_status") is not None:
            garmin_words.append(f"Training Status **{garmin_label(row['training_status'])}**")
        if value_of(row, "recovery_time_min") is not None:
            garmin_words.append(f"Recovery Time **{fmt_recovery_time(row['recovery_time_min'])}**")
        if value_of(row, "steps") is not None:
            garmin_words.append(f"ก้าว **{row['steps']:,.0f}**")
        if garmin_words:
            st.markdown(" · ".join(garmin_words))

        mine = day_activities[day_activities["athlete_id"] == aid] if not day_activities.empty \
            else day_activities
        if mine.empty:
            st.caption(":material/directions_run: ไม่มีกิจกรรมในวันนี้")
        for _, activity in mine.sort_values("start_time_local").iterrows():
            distance = activity.get("distance_m")
            parts = [
                pd.to_datetime(activity["start_time_local"]).strftime("%H:%M"),
                activity_title(activity),
                f"{distance / 1000:.2f} km" if pd.notna(distance) and distance > 0 else None,
                fmt_sec(activity.get("duration_sec")),
                (fmt_pace(activity.get("avg_pace_min_per_km")) + " /km")
                if pd.notna(distance) and distance > 0 else None,
                f"HR {activity['avg_hr']:.0f}" if pd.notna(activity.get("avg_hr")) else None,
                "⚠ อาจซ้ำ" if int(activity["activity_id"]) in suspects else None,
            ]
            st.markdown(":material/directions_run: "
                        + " · ".join(part for part in parts if part and part != "–"))

        st.button(f"ดูข้อมูลของ {name}", key=f"open-athlete-{order}",
                  on_click=focus_athlete, args=(name,), icon=":material/arrow_forward:",
                  type="tertiary")


athletes = ctx.athletes_df.to_dict("records")
for row_start in range(0, len(athletes), 3):
    columns = st.columns(3)
    for column, (order, athlete) in zip(
            columns, enumerate(athletes[row_start:row_start + 3], start=row_start)):
        with column:
            athlete_card(athlete, order)

st.subheader("เทียบระหว่างวันทั้งทีม", anchor=False)
intraday = load_intraday(day)
if intraday.empty:
    st.caption("ยังไม่มีข้อมูลระหว่างวันของวันนี้")
else:
    labels = {key: label for key, (label, _) in INTRADAY_METRICS.items()}
    chosen = st.segmented_control("ค่า", options=list(labels), format_func=labels.get,
                                  default="heart_rate", required=True, key="team_intraday_metric",
                                  label_visibility="collapsed")
    names = dict(zip(ctx.athletes_df["athlete_id"], ctx.athletes_df["display_name"]))
    series = intraday_series(intraday, chosen)
    if series["ค่า"].notna().any():
        st.altair_chart(intraday_chart(series, day, y_title=INTRADAY_METRICS[chosen][1],
                                       names=names, height=240), width="stretch")
        st.caption("แกนเวลาเดียวกัน 00:00–24:00 · เส้นขาด = ช่วงที่ไม่มีข้อมูลจากนาฬิกา")
    else:
        st.caption(f"ไม่มีข้อมูล {labels[chosen]} ระหว่างวันของวันนี้")

st.subheader("กิจกรรมของทีมในวันนี้", anchor=False)
if day_activities.empty:
    st.caption("ไม่มีกิจกรรมที่ Garmin บันทึกในวันนี้")
else:
    ordered = day_activities.sort_values("start_time_local", ascending=False)
    table = activity_rows(ordered)
    table.insert(1, "นักกีฬา", ordered["display_name"].reset_index(drop=True))
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
