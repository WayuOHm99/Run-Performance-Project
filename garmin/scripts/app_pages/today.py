"""หน้า "วันนี้" ของ Coach Dashboard"""

import html
import datetime
import math

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from dashboard_domain import (
    HRV_ALERT,
    HRV_TREND_LOOKBACK_DAYS,
    baseline_median,
    body_battery_snapshots,
    classify_intensity,
    field_freshness,
    fmt_num,
    fmt_text,
    get_lthr,
    has_any_value,
    latest_field,
    readiness_when,
    status_parts,
    tile_note,
)

from dashboard_view import (
    STATUS_TEXT_COLORS,
    TODAY_PANEL_CSS,
    render_load_strip,
    render_session_row,
    render_today_tile,
    render_today_verdict,
    sparkline_svg,
    status_shape_svg,
)

from dashboard_data import (
    athlete_has_load,
    athlete_has_training_readiness,
    load_activity_data,
    load_athlete_devices,
    load_daily_workload,
    load_wellness_data,
)

from dashboard_context import page_context

_ctx = page_context()
athletes_df = _ctx.athletes_df
athlete_id = _ctx.athlete_id
today = _ctx.today
selected_name = _ctx.selected_name
selected_slug = _ctx.selected_slug
selected_anchor = _ctx.selected_anchor

from dashboard_team import team_snapshot

team_df, TEAM_INTERNAL_COLUMNS = team_snapshot(athletes_df, today)


st.header(f"วันนี้ของ {selected_name}", anchor=f"today-{selected_anchor}")
st.caption(
    f"{today.strftime('%d/%m/%Y')} · สรุปสัญญาณจากอุปกรณ์ ไม่ใช่คำอนุญาตให้ซ้อม · "
    "ค่าที่ยังไม่มาของวันนี้แสดงค่าล่าสุดพร้อมวันที่กำกับ"
)

selected_team = team_df[team_df["นักกีฬา"] == selected_name]
team_row = selected_team.iloc[0] if not selected_team.empty else None
# ค่าไหนเป็นคนจุดธง มาจากแท็บทีมโดยตรง ไม่ได้คำนวณเกณฑ์ซ้ำที่นี่
flagged_fields = set(team_row["ธงเฝ้าระวังรายค่า"]) if team_row is not None else set()

recent_wellness = load_wellness_data(
    athlete_id,
    (today - datetime.timedelta(days=HRV_TREND_LOOKBACK_DAYS - 1)).isoformat(),
    today.isoformat(),
)
today_wellness = load_wellness_data(athlete_id, today.isoformat(), today.isoformat())
# ดึงย้อน 14 วันเพราะวันพักต้องยังมีของให้ดู — วันที่ไม่มีกิจกรรมไม่ใช่วันที่ไม่มีบริบท
recent_activities = load_activity_data(
    athlete_id, (today - datetime.timedelta(days=13)).isoformat(), today.isoformat()
)
if not recent_activities.empty:
    recent_activities = recent_activities.copy()
    recent_activities["start_time_local"] = pd.to_datetime(
        recent_activities["start_time_local"]
    )
    recent_activities["distance_km"] = recent_activities["distance_m"] / 1000
    recent_activities = recent_activities.sort_values(
        "start_time_local", ascending=False
    )
    today_activities = recent_activities[
        recent_activities["start_time_local"].dt.date == today
    ]
else:
    today_activities = recent_activities

readiness_supported = athlete_has_training_readiness(athlete_id)
training_load_supported = athlete_has_load(athlete_id)
device_names = load_athlete_devices(athlete_id)

st.markdown(TODAY_PANEL_CSS, unsafe_allow_html=True)

# ---- สรุปสัญญาณ: อ่านก่อนตัวเลขรายละเอียด ----
# สถานะโหลดต้องเตือนแม้ wellness วันนี้ยังไม่มา จึงวาดก่อนอ่านค่า wellness ทั้งหมด
# และไม่ผูกอยู่กับเงื่อนไขใด ๆ ของ wellness
if team_row is not None:
    st.markdown(render_today_verdict(team_row), unsafe_allow_html=True)

# ---- ค่าจากอุปกรณ์ที่ใช้เป็นบริบท ----
bb_snap, bb_completed_snap = body_battery_snapshots(recent_wellness, today)
sleep_snap = latest_field(recent_wellness, "sleep_score")
rhr_snap = latest_field(recent_wellness, "resting_hr")
hrv_snap = latest_field(recent_wellness, "hrv_last_night")
ready_snap = latest_field(
    recent_wellness,
    "training_readiness",
    ("readiness_timestamp_local", "readiness_timestamp_utc"),
)
hrv_status = fmt_text(hrv_snap["row"].get("hrv_status")) if hrv_snap else ""
readiness_level = fmt_text(ready_snap["row"].get("readiness_level")) if ready_snap else ""

wellness_history = (
    recent_wellness.sort_values("calendar_date")
    if not recent_wellness.empty else recent_wellness
)

def recent_series(column):
    """ค่า 14 วันล่าสุดของฟิลด์เดียว สำหรับเส้นแนวโน้มเล็กใต้ไทล์"""
    if wellness_history.empty or column not in wellness_history.columns:
        return []
    return list(wellness_history[column].tail(14))

def fresh_short(snapshot):
    """"วันนี้" / "เมื่อวาน" / "3 วันก่อน" — วันที่เต็มอยู่ใน expander ด้านล่าง"""
    return field_freshness(snapshot, today).split(" · ")[-1]

def snapshot_value(snapshot):
    return snapshot["value"] if snapshot else float("nan")

def snapshot_anchor(snapshot):
    return snapshot["date"] if snapshot and snapshot.get("date") else today

# Body Battery: ตัวเลขใหญ่คือระดับล่าสุดระหว่างวัน แต่ฐานเทียบได้เฉพาะ high ของวันที่
# จบแล้ว — สองอย่างนี้คนละหน่วยความหมาย จึงเขียนแยกให้เห็น ไม่เอามาลบกันเงียบ ๆ
bb_completed_value = snapshot_value(bb_completed_snap)
bb_note = tile_note(
    bb_completed_value,
    baseline_median(recent_wellness, "body_battery_high",
                    snapshot_anchor(bb_completed_snap)),
)
if pd.notna(bb_completed_value) and bb_note:
    bb_note = f"high วันล่าสุด {fmt_num(bb_completed_value)} · {bb_note}"

hrv_note = tile_note(
    snapshot_value(hrv_snap),
    baseline_median(recent_wellness, "hrv_last_night", snapshot_anchor(hrv_snap)),
)
if hrv_status:
    hrv_note = f"Garmin: {hrv_status.replace('_', ' ')}" + (f" · {hrv_note}" if hrv_note else "")

ready_note = tile_note(
    snapshot_value(ready_snap),
    baseline_median(recent_wellness, "training_readiness", snapshot_anchor(ready_snap)),
)
if readiness_level:
    ready_note = f"Garmin: {readiness_level.replace('_', ' ')}" + (
        f" · {ready_note}" if ready_note else ""
    )

tile_specs = [
    # ตัวเลขใหญ่คือระดับ ณ ตอนนี้ (ตกลงตลอดวันตามปกติ) ป้ายจึงต้องบอกเองว่านี่ไม่ใช่
    # ค่าสูงสุดของวัน ไม่งั้น "5" ตอนสี่ทุ่มอ่านเหมือนสัญญาณอันตราย
    ("BODY BATTERY ตอนนี้/ล่าสุด", bb_snap, "body_battery_high", "", bb_note,
     "bb", "watch"),
    ("SLEEP SCORE", sleep_snap, "sleep_score", "",
     tile_note(snapshot_value(sleep_snap),
               baseline_median(recent_wellness, "sleep_score",
                               snapshot_anchor(sleep_snap))),
     "sleep", "watch"),
    ("RESTING HR", rhr_snap, "resting_hr", " bpm",
     tile_note(snapshot_value(rhr_snap),
               baseline_median(recent_wellness, "resting_hr",
                               snapshot_anchor(rhr_snap))),
     "rhr", "watch"),
    ("HRV คืนล่าสุด", hrv_snap, "hrv_last_night", " ms", hrv_note, "hrv",
     HRV_ALERT.get(hrv_status, "watch")),
]
# ไทล์ความพร้อมซ้อมขึ้นเฉพาะนักกีฬาที่บัญชีเคยส่งค่านี้จริง — ช่องว่างถาวรของคนที่
# นาฬิกาไม่ส่ง อ่านได้ว่าระบบพัง ทั้งที่คำอธิบายอยู่ใน expander ด้านล่างแล้ว
if readiness_supported or ready_snap:
    tile_specs.append(
        ("ความพร้อมซ้อม (Garmin)", ready_snap, "training_readiness", "", ready_note,
         "readiness", "watch")
    )

st.markdown(
    '<div class="today-tiles">'
    + "".join(
        render_today_tile(
            label,
            fmt_num(snapshot_value(snapshot), suffix),
            fresh_short(snapshot),
            note,
            sparkline_svg(recent_series(column)),
            alert_key if field in flagged_fields else None,
        )
        for label, snapshot, column, suffix, note, field, alert_key in tile_specs
    )
    + "</div>",
    unsafe_allow_html=True,
)

# ---- pace-HR trend กับบริบทโหลดข้างกัน ----
if team_row is not None:
    ef_zone_key, ef_zone_label = status_parts(team_row["สถานะ pace–HR"])
    ef_pct_value = team_row["pace–HR จากฐาน (%)"]
    ef_color = STATUS_TEXT_COLORS.get(ef_zone_key, STATUS_TEXT_COLORS["unknown"])

    left, right = st.columns([1.05, 1.35], gap="large")
    with left:
        # ค่าว่างต้องบอกเหตุผลตรงจุดที่มันว่าง ไม่งั้นโค้ชอ่านว่า sync พัง
        ef_body = (
            f'<div style="display:flex;align-items:baseline;gap:10px">'
            f'<div class="today-ef__val" style="color:{ef_color}">'
            f'{ef_pct_value:+.1f}%</div>'
            f'<div style="font-size:13px;color:#55585f">จากฐานก่อนหน้าที่ไม่ซ้อนกัน</div></div>'
            f'<div style="font-size:12px;color:#55585f;margin-top:5px">'
            f'{status_shape_svg(ef_zone_key, 9)} {html.escape(ef_zone_label)}</div>'
            '<div style="font-size:12px;color:#55585f;margin-top:7px;line-height:1.6">'
            'ไม่ใช่ running economy หรือความสด; เส้นทาง เพซ ความชัน อากาศ การหยุด '
            'และ HR sensor ทำให้ค่าเปลี่ยนได้</div>'
            if pd.notna(ef_pct_value) else
            '<div class="today-ef__val" style="color:#8a8d94">–</div>'
            '<div style="font-size:12px;color:#55585f;margin-top:5px;line-height:1.6">'
            'ต้องมีข้อมูลวิ่ง easy 3 วันภายใน 14 วัน และฐานอย่างน้อย 5 วันใน 28 วันก่อนหน้า '
            '— ยังไม่ครบตามนี้ ไม่ใช่ระบบขัดข้อง</div>'
        )
        st.markdown(
            '<div class="today-panel"><div class="today-panel__head">'
            '<div class="today-panel__title">แนวโน้ม pace–HR ของรันเบา</div>'
            '<div class="today-panel__hint">บริบทประกอบ</div></div>'
            + ef_body + "</div>",
            unsafe_allow_html=True,
        )
    with right:
        strip_daily, strip_metric, strip_unit = load_daily_workload(
            athlete_id, (today - datetime.timedelta(days=6)).isoformat(),
            today.isoformat(),
        )
        by_date = {}
        if not strip_daily.empty:
            by_date = {
                row["date"].date(): row["value"]
                for _, row in strip_daily.iterrows()
            }
        strip_days = [
            (
                (today - datetime.timedelta(days=offset)).strftime("%d/%m"),
                by_date.get(today - datetime.timedelta(days=offset)),
            )
            for offset in range(6, -1, -1)
        ]
        st.markdown(
            '<div class="today-panel"><div class="today-panel__head">'
            f'<div class="today-panel__title">โหลดรายวัน 7 วัน ({html.escape(strip_unit)})</div>'
            '<div class="today-panel__hint">บริบท ไม่ได้ตัดสินสถานะ</div></div>'
            + render_load_strip(
                strip_days, digits=0 if strip_metric == "training_load" else 1
            )
            + '<div style="font-size:13px;color:#55585f;margin-top:12px">รวม 7 วัน '
            f'{html.escape(str(team_row["โหลด 7 วัน"] or "–"))} · '
            f'เฉลี่ย 28 วัน {html.escape(str(team_row["ค่าเฉลี่ยโหลด 28 วัน"] or "–"))} · '
            f'{html.escape(str(team_row["เซสชัน 7 วัน"] or 0))} เซสชัน'
            f' ({html.escape(str(team_row["ขอบเขตโหลด"] or "วิ่ง"))})</div></div>',
            unsafe_allow_html=True,
        )

# ---- เซสชันจริง ----
lthr_today, _ = get_lthr(selected_slug, athlete_id)
if not today_activities.empty:
    session_rows, session_hint = today_activities, "กิจกรรมของวันนี้"
else:
    # วันพักไม่ได้แปลว่าไม่มีอะไรให้ดู — ของสามครั้งก่อนหน้าคือบริบทของวันนี้
    session_rows = recent_activities.head(3)
    session_hint = "วันนี้ยังไม่มีกิจกรรม · แสดง 3 ครั้งก่อนหน้า"

if session_rows.empty:
    st.markdown(
        '<div class="today-panel"><div class="today-panel__title">เซสชัน</div>'
        '<div style="font-size:13px;color:#55585f;margin-top:8px">'
        'ยังไม่มีกิจกรรมที่บันทึกใน 14 วันล่าสุด</div></div>',
        unsafe_allow_html=True,
    )
else:
    header = "".join(
        f'<div class="today-lbl" style="{align}">{title}</div>'
        for title, align in (
            ("วันที่", ""), ("รายการ", ""), ("ระยะ", "text-align:right"),
            ("เวลา", "text-align:right"), ("เพซ", "text-align:right"),
            ("HR", "text-align:right"), ("ความหนัก", "text-align:right"),
        )
    )
    body = "".join(
        render_session_row(
            activity["start_time_local"].strftime("%d/%m %H:%M")
            if pd.notna(activity["start_time_local"]) else "ไม่ทราบเวลา",
            fmt_text(activity.get("activity_name"),
                     fmt_text(activity.get("activity_type"), "กิจกรรม")),
            activity.get("distance_km"),
            activity.get("duration_sec"),
            activity.get("avg_pace_min_per_km"),
            activity.get("avg_hr"),
            classify_intensity(activity.get("avg_hr"), lthr_today),
        )
        for _, activity in session_rows.iterrows()
    )
    st.markdown(
        '<div class="today-panel"><div class="today-panel__head">'
        '<div class="today-panel__title">เซสชัน</div>'
        f'<div class="today-panel__hint">{html.escape(session_hint)}</div></div>'
        f'<div class="today-sess__head">{header}</div>{body}</div>',
        unsafe_allow_html=True,
    )

# ---- คำอธิบายที่อ่านครั้งเดียวแล้วไม่ต้องอ่านอีก ----
with st.expander("วันที่ของแต่ละค่า และค่าที่นาฬิกายังไม่ส่ง", icon=":material/info:"):
    st.markdown(
        "**วันที่ของแต่ละค่า** — "
        + " · ".join(
            f"{label}: "
            + (readiness_when(snapshot, today) if label == "Readiness"
               else field_freshness(snapshot, today))
            for label, snapshot in (
                ("BB", bb_snap), ("Sleep", sleep_snap), ("RHR", rhr_snap),
                ("HRV", hrv_snap), ("Readiness", ready_snap),
            )
        )
    )

    pending_today = []
    for label, column in (("Sleep", "sleep_score"), ("HRV", "hrv_last_night")):
        if latest_field(today_wellness, column) is None:
            pending_today.append(label)
    if readiness_supported and latest_field(today_wellness, "training_readiness") is None:
        pending_today.append("Training Readiness")
    if not has_any_value(
        today_wellness,
        ["resting_hr", "sleep_score", "body_battery_high", "bb_most_recent",
         "hrv_last_night"],
    ):
        st.markdown(
            "ยังไม่มีข้อมูลสุขภาพของวันนี้จากนาฬิกา "
            "จึงแสดงค่าล่าสุดที่ยังใช้ได้พร้อมวันที่กำกับ"
        )
    if pending_today:
        st.markdown(
            "Garmin ยังไม่มีค่า " + ", ".join(pending_today)
            + " ของวันนี้ ระบบจะลองเติมในรอบ sync ถัดไป; ค่าที่แสดงจากวันก่อนมีวันที่กำกับ "
              "และไม่ได้ถูกคาดเดา"
        )
    if not readiness_supported:
        models = ", ".join(device_names) if device_names else "ยังไม่มีทะเบียนอุปกรณ์ที่สดพอ"
        st.markdown(
            "ยังไม่เคยได้รับ Training Readiness จากบัญชีนี้ในประวัติที่เก็บไว้ "
            f"(อุปกรณ์ที่เคยพบ: {models}; กรองรายการที่ยืนยันว่า last_seen เกิน 90 วัน) "
            "อาจเกิดจากความสามารถของอุปกรณ์ การตั้งค่าบัญชี "
            "หรือ endpoint ไม่ส่งข้อมูล จึงยังไม่สรุปจากค่าว่างเพียงอย่างเดียวว่า ‘รุ่นไม่รองรับ’"
        )
    if not training_load_supported:
        st.markdown(
            "ยังไม่เคยได้รับ Garmin Training Load จากกิจกรรมที่เก็บไว้; "
            "โหลดสะสมของระบบจึงคำนวณจากระยะวิ่งและระบุแหล่งที่มาชัดเจน"
        )
