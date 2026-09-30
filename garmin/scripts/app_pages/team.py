"""หน้า "ทีม" — ค่าล่าสุดที่นาฬิกาของแต่ละคนส่งมา + กิจกรรมล่าสุดของทั้งทีม

คำถามของหน้านี้: เช้านี้นาฬิกาของใครส่งอะไรมาแล้วบ้าง และใครซ้อมอะไรไป
ไม่มีสถานะหรือธงที่ระบบตัดสินเอง — คำของ Garmin (เช่น HRV "Balanced") แสดงตามจริง
"""

import datetime

import pandas as pd
import streamlit as st

from dashboard_context import focus_athlete, page_context
from dashboard_data import (
    athlete_has_training_readiness,
    load_athlete_devices,
    load_latest_activity,
    load_team_activities,
    load_wellness_data,
)
from dashboard_domain import (
    activity_rows,
    activity_title,
    body_battery_now,
    field_when,
    fmt_num,
    fmt_pace,
    fmt_recovery_time,
    fmt_sec,
    garmin_label,
    latest_field,
    readiness_when,
    sync_status,
)

ctx = page_context()
today = ctx.today
LOOKBACK_DAYS = 14

st.title("ทีม")
st.caption("ค่าล่าสุดที่นาฬิกาของแต่ละคนส่งมา · ป้ายสีบอกว่านาฬิกา sync วันนี้แล้วหรือยัง · "
           "ดูกราฟย้อนหลังได้ที่หน้า \"ร่างกาย\"")


def metric(label, value, note):
    # กว้างคงที่ให้วางได้สองใบต่อแถวในการ์ดสามคอลัมน์ — การ์ดสั้นพอกวาดตาทีเดียวจบ
    st.metric(label, value, note, delta_color="off", delta_arrow="off", width=125)


def athlete_card(athlete, order):
    aid, name = athlete["athlete_id"], athlete["display_name"]
    wellness = load_wellness_data(
        aid, (today - datetime.timedelta(days=LOOKBACK_DAYS - 1)).isoformat(), today.isoformat())

    sleep = latest_field(wellness, "sleep_score")
    hrv = latest_field(wellness, "hrv_last_night")
    rhr = latest_field(wellness, "resting_hr")
    battery = body_battery_now(wellness, today)
    readiness = latest_field(wellness, "training_readiness",
                             ("readiness_timestamp_local", "readiness_timestamp_utc"))
    status = latest_field(wellness, "training_status")
    recovery = latest_field(wellness, "recovery_time_min")
    sync_key, sync_text = sync_status([sleep, hrv, rhr, battery], today)

    with st.container(border=True, key=f"team-card-{order}"):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.subheader(name, anchor=False)
            st.badge(sync_text,
                     icon=":material/check:" if sync_key == "today" else ":material/schedule:",
                     color="green" if sync_key == "today" else "orange")
        devices = load_athlete_devices(aid)
        if devices:
            st.caption(devices[0].split(" (")[0])

        # วันที่ของการ์ดบอกไว้ที่ป้าย sync แล้ว ใต้ตัวเลขจึงบอกวันเฉพาะค่าที่เก่ากว่านั้น
        # (เช่น HRV ของคืนก่อน) — ไม่งั้นทุกช่องซ้ำคำว่า "เมื่อวาน" จนอ่านคำของ Garmin ไม่เห็น
        dated = [snap["date"] for snap in (sleep, hrv, rhr, battery) if snap and snap.get("date")]
        card_date = max(dated) if dated else None

        def note(snapshot, *words):
            if not snapshot:
                return "ไม่มีข้อมูล"
            parts = [word for word in words if word]
            if snapshot.get("date") != card_date:
                parts.append(field_when(snapshot, today))
            return " · ".join(parts) or None

        with st.container(horizontal=True, gap="small"):
            metric("Sleep score", fmt_num(sleep["value"]) if sleep else "–", note(sleep))
            metric("HRV คืนล่าสุด", fmt_num(hrv["value"], " ms") if hrv else "–",
                   note(hrv, garmin_label(hrv["row"].get("hrv_status")) if hrv else ""))
            metric("Body Battery", fmt_num(battery["value"]) if battery else "–",
                   note(battery, ("ตอนนี้" if battery["kind"] == "now" else "สูงสุดของวัน")
                        if battery else ""))
            metric("RHR", fmt_num(rhr["value"], " bpm") if rhr else "–", note(rhr))
            if athlete_has_training_readiness(aid):
                metric("Training Readiness",
                       fmt_num(readiness["value"]) if readiness else "–",
                       " · ".join(filter(None, [
                           garmin_label(readiness["row"].get("readiness_level"))
                           if readiness else "",
                           readiness_when(readiness, today)])) if readiness else "ไม่มีข้อมูล")

        garmin_words = []
        if status:
            garmin_words.append(f"Training Status **{garmin_label(status['value'])}**")
        if recovery:
            garmin_words.append(f"Recovery Time **{fmt_recovery_time(recovery['value'])}**")
        if garmin_words:
            st.markdown(" · ".join(garmin_words))

        latest = load_latest_activity(aid)
        if latest:
            when = pd.to_datetime(latest["start_time_local"])
            distance = latest.get("distance_m")
            parts = [
                when.strftime("%d/%m %H:%M"),
                activity_title(latest),
                f"{distance / 1000:.2f} km" if pd.notna(distance) and distance > 0 else None,
                fmt_sec(latest.get("duration_sec")),
                (fmt_pace(latest.get("avg_pace_min_per_km")) + " /km")
                if pd.notna(distance) and distance > 0 else None,
                f"HR {latest['avg_hr']:.0f}" if pd.notna(latest.get("avg_hr")) else None,
            ]
            st.markdown(":material/directions_run: **กิจกรรมล่าสุด** · "
                        + " · ".join(part for part in parts if part and part != "–"))
        else:
            st.caption("ยังไม่มีกิจกรรม")

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

st.subheader("กิจกรรม 7 วันล่าสุดของทีม", anchor=False)
feed = load_team_activities((today - datetime.timedelta(days=6)).isoformat(), today.isoformat())
if feed.empty:
    st.caption("ยังไม่มีกิจกรรมใน 7 วันล่าสุด")
else:
    table = activity_rows(feed)
    table.insert(1, "นักกีฬา", feed.sort_values("start_time_local", ascending=False)
                 ["display_name"].reset_index(drop=True))
    st.dataframe(
        table, hide_index=True, width="stretch",
        column_config={
            "ระยะ (km)": st.column_config.NumberColumn(format="%.2f"),
            "HR เฉลี่ย": st.column_config.NumberColumn(format="%d"),
            "HR สูงสุด": st.column_config.NumberColumn(format="%d"),
            "Training Effect": st.column_config.NumberColumn(format="%.1f"),
            "Training Load": st.column_config.NumberColumn(format="%d"),
        },
    )

st.caption("ข้อมูลทั้งหมดมาจาก Garmin · ก่อนซ้อมต้องถามอาการเจ็บ ป่วย และความล้าจากนักกีฬาเอง")
