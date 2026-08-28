"""ภาพรวมทีมรายคน — ใช้ร่วมกันระหว่างหน้า "ทีม" กับหน้า "วันนี้"

เดิมเป็นบล็อกกลางสคริปต์ที่ครอบด้วย ``if tab_today.open or tab_team.open`` เพราะ
สองแท็บใช้ค่าชุดเดียวกัน แต่แท็บอื่นไม่ควรจ่ายค่าคำนวณย้อนหลัง 42 วันของทุกคน
ตอนแยกหน้าแล้ว หน้าไหนต้องใช้ก็เรียกเอง หน้าที่ไม่ใช้ไม่แตะเลย
"""

import datetime
import math

import pandas as pd
import streamlit as st

from dashboard_domain import (
    HRV_ALERT,
    HRV_TREND_BASELINE_DAYS,
    HRV_TREND_CURRENT_DAYS,
    HRV_TREND_LOOKBACK_DAYS,
    READINESS_ALERT,
    SLEEP_LOW,
    body_battery_snapshots,
    easy_run_efficiency,
    efficiency_change_pct,
    efficiency_display,
    efficiency_status,
    field_age_days,
    fmt_text,
    get_lthr,
    hrv_trend_status,
    hrv_trend_summary,
    latest_field,
    load_session_scope,
    load_volume_display,
    team_status,
)

from dashboard_data import (
    load_daily_workload,
    load_easy_runs,
    load_first_load_date,
    load_first_run_date,
    load_wellness_data,
)


def team_snapshot(athletes_df, today):
    """คืน ``(team_df, TEAM_INTERNAL_COLUMNS)`` — คอลัมน์ภายในไม่ได้ไว้โชว์บนตาราง"""
    team_rows = []
    for _, ath in athletes_df.iterrows():
        aid, name = ath["athlete_id"], ath["display_name"]

        # โหลดย้อน 42 วัน (training_load ถ้านาฬิกาให้ = จับ cross-training ครบ ไม่งั้นระยะวิ่ง)
        daily, metric, unit = load_daily_workload(
            aid, (today - datetime.timedelta(days=42)).isoformat(), today.isoformat())
        acute = chronic_wk = float("nan")
        sessions_7d = 0
        if not daily.empty:
            win7 = daily[daily["date"] >= pd.Timestamp(today - datetime.timedelta(days=6))]
            win28 = daily[daily["date"] >= pd.Timestamp(today - datetime.timedelta(days=27))]
            acute = win7["value"].sum()
            sessions_7d = int(win7["sessions"].sum())
            first = load_first_load_date(aid) if metric == "training_load" else load_first_run_date(aid)
            days_of_history = (today - first).days + 1 if first else 0
            if days_of_history >= 28 and win28["value"].sum() > 0:
                chronic_wk = win28["value"].sum() / 4

        # pace-HR trend ของรันเบา — บริบทประกอบเท่านั้น ไม่ใช้ตัดสินพร้อมซ้อม
        ath_lthr, _ = get_lthr(ath["slug"], aid)
        easy_ef = easy_run_efficiency(
            load_easy_runs(aid, (today - datetime.timedelta(days=70)).isoformat(),
                           today.isoformat()),
            ath_lthr,
        )
        ef_pct = efficiency_change_pct(easy_ef, today)

        # Wellness แต่ละ endpoint อาจมาคนละรอบ จึงเลือก "ล่าสุดแยกทีละ field"
        # แทนการใช้แถวเดียวแล้วทำให้ Sleep/HRV ที่ยังใช้ได้ถูกซ่อนโดย snapshot บางส่วนของวันนี้
        w = load_wellness_data(
            aid,
            (today - datetime.timedelta(days=HRV_TREND_LOOKBACK_DAYS - 1)).isoformat(),
            today.isoformat(),
        )
        sleep_snap = latest_field(w, "sleep_score")
        rhr_snap = latest_field(w, "resting_hr")
        hrv_snap = latest_field(w, "hrv_last_night")
        bb_display_snap, bb_completed_snap = body_battery_snapshots(w, today)
        ready_snap = latest_field(
            w,
            "training_readiness",
            ("readiness_timestamp_local", "readiness_timestamp_utc"),
        )
        train_snap = latest_field(w, "training_status")

        # วันนี้แสดงระดับล่าสุดระหว่างวัน; ธงใช้ high ล่าสุดของวันที่จบแล้วแยกกัน
        bb = bb_completed_snap["value"] if bb_completed_snap else float("nan")
        bb_now = bb_display_snap["value"] if bb_display_snap else float("nan")
        sleep = sleep_snap["value"] if sleep_snap else float("nan")
        rhr = rhr_snap["value"] if rhr_snap else float("nan")
        hrv_ms = hrv_snap["value"] if hrv_snap else float("nan")
        ready = ready_snap["value"] if ready_snap else float("nan")
        hrv_stat = fmt_text(hrv_snap["row"].get("hrv_status")) if hrv_snap else ""
        ready_level = fmt_text(ready_snap["row"].get("readiness_level")) if ready_snap else ""
        train_stat = fmt_text(train_snap["value"]) if train_snap else ""

        rhr_delta = float("nan")
        if rhr_snap and "resting_hr" in w:
            rhr_dates = pd.to_datetime(w["calendar_date"], errors="coerce").dt.date
            baseline = pd.to_numeric(
                w.loc[rhr_dates < rhr_snap["date"], "resting_hr"], errors="coerce"
            ).dropna()
            if pd.notna(rhr) and len(baseline) >= 7:
                rhr_delta = rhr - baseline.mean()

        core_snaps = [bb_display_snap, sleep_snap, rhr_snap, hrv_snap]
        fresh_core_count = sum(
            1 for snapshot in core_snaps
            if field_age_days(snapshot, today) is not None
            and 0 <= field_age_days(snapshot, today) <= 1
        )

        # สัญญาณให้ทบทวน — เก็บคู่กับค่าเพื่อให้แท็บวันนี้ตีกรอบไทล์ตรงกัน
        # ถ้าแท็บนั้นคำนวณเกณฑ์เองซ้ำ สองหน้าจะขัดกันเงียบ ๆ ทันทีที่เกณฑ์ฝั่งใดฝั่งหนึ่งขยับ
        flags = []
        flag_fields = []
        if pd.notna(sleep) and sleep < SLEEP_LOW and field_age_days(sleep_snap, today) <= 1:
            flags.append(f"Garmin Sleep อยู่หมวด Poor ({sleep:.0f})")
            flag_fields.append("sleep")
        if (hrv_stat in HRV_ALERT
                and field_age_days(hrv_snap, today) <= 1):
            flags.append(f"Garmin HRV {hrv_stat}")
            flag_fields.append("hrv")
        # Training Status ขึ้นกับอุปกรณ์/บัญชีและ endpoint; ใช้ค่าที่เคยได้รับจริงโดยไม่
        # เหมารวมกับ respiration หรือสรุปจาก NULL ว่าอุปกรณ์ไม่รองรับ
        # ค่าดิบมี suffix ตัวเลข เช่น STRAINED_1 / UNPRODUCTIVE_5 → ตัดเหลือคำหลักก่อนเทียบ
        _ts_base = (train_stat or "").split("_")[0]
        _ts_flag = {"STRAINED": "ล้าสะสม (Strained)",
                    "OVERREACHING": "โหลดเกินตัว (Overreaching)",
                    "UNPRODUCTIVE": "ซ้อมไม่ขึ้น (Unproductive)"}
        if (_ts_base in _ts_flag and train_snap
                and field_age_days(train_snap, today) <= 1):
            flags.append(f"Garmin: {_ts_flag[_ts_base]}")
        # Training Readiness: ประวัติปัจจุบันมีเฉพาะ P'kao ส่วน Tong/Dan ยังไม่เคยได้รับค่า;
        # นี่คือสถานะข้อมูล ไม่ใช่ข้อสรุปความสามารถของรุ่นนาฬิกา และค่าอัปเดตได้ระหว่างวัน
        if (ready_level in READINESS_ALERT and ready_snap
                and field_age_days(ready_snap, today) <= 1):
            flags.append(f"Readiness ต่ำ ({ready:.0f} {ready_level.title()})"
                         if pd.notna(ready) else f"Readiness {ready_level.title()}")
            flag_fields.append("readiness")

        # สรุปการมี/ไม่มีสัญญาณจากอุปกรณ์เท่านั้น ไม่ใช่ training clearance
        status = team_status(
            flags, not daily.empty, fresh_core_count,
            any(snapshot is not None for snapshot in core_snaps),
        )

        coverage_notes = []
        if fresh_core_count < 3:
            coverage_notes.append(f"wellness สด {fresh_core_count}/4 ค่า")
        freshness_note = " · ".join(
            f"{label} {snapshot['date'].strftime('%d/%m')}"
            for label, snapshot in (
                ("BB", bb_display_snap), ("Sleep", sleep_snap),
                ("RHR", rhr_snap), ("HRV", hrv_snap), ("Readiness", ready_snap),
            )
            if snapshot and snapshot.get("date")
        ) or "ไม่มี wellness"

        emoji, ef_txt = efficiency_status(ef_pct)
        # HRV trend เป็นตัวเลขประกอบแยกจาก Garmin HRV Status ไม่สร้างธงซ้ำ
        hrv_summary = hrv_trend_summary(w, today)
        hrv_pct = hrv_summary["pct"]
        hrv_trend_key, hrv_trend_txt = hrv_trend_status(hrv_pct)
        team_rows.append({
            "นักกีฬา": name,
            "สถานะ": status,
            # อยู่ต้นตาราง (ไม่ใช่ท้ายสุด) เพราะตารางนี้มี 13 คอลัมน์ กว้างเกินจอปกติ —
            # วางไว้ท้ายก่อนหน้านี้ทำให้มองข้ามว่า "ไม่ขึ้น" ทั้งที่จริงมีข้อมูล แค่ต้องเลื่อนดู
            "สถานะซ้อม (Garmin)": _ts_base.title() if _ts_base else "–",
            "pace–HR trend": efficiency_display(ef_pct),
            "สถานะ pace–HR": f"{emoji} {ef_txt}",
            "เทรนด์ HRV 7 คืน (%)": (f"{hrv_pct:+.1f}%" if pd.notna(hrv_pct) else "–"),
            "จำนวนคืน HRV ที่ใช้": (
                f'{hrv_summary["current_n"]}/{HRV_TREND_CURRENT_DAYS} คืน · '
                f'ฐาน {hrv_summary["baseline_n"]}/{HRV_TREND_BASELINE_DAYS} คืน'
            ),
            "สถานะเทรนด์ HRV": hrv_trend_txt if pd.notna(hrv_pct) else "",
            "โหลด 7 วัน": load_volume_display(acute, metric, unit),
            "ค่าเฉลี่ยโหลด 28 วัน": load_volume_display(
                chronic_wk, metric, f"{unit}/สัปดาห์"
            ),
            "เซสชัน 7 วัน": sessions_7d,
            "ขอบเขตโหลด": load_session_scope(metric),
            "Body Battery ตอนนี้/ล่าสุด": bb_now if pd.notna(bb_now) else None,
            "Sleep": sleep if pd.notna(sleep) else None,
            "RHR": rhr if pd.notna(rhr) else None,
            "ΔRHR": f"{rhr_delta:+.0f}" if pd.notna(rhr_delta) else "–",
            "HRV คืนล่าสุด": ((f"{hrv_ms:.0f} ms" + (f" · {hrv_stat}" if hrv_stat else ""))
                              if pd.notna(hrv_ms) else "–"),
            "Readiness": ready if pd.notna(ready) else None,
            "ความสดรายค่า": freshness_note,
            "ธงเฝ้าระวัง": (" | ".join(flags) if flags else "—")
                           + ((" · ข้อมูลไม่พอ: " + ", ".join(coverage_notes))
                              if status.startswith("⚪") and coverage_notes else ""),
            # สองคีย์ล่างนี้ไม่ได้ไว้อ่านบนตาราง — แท็บวันนี้ใช้ต่อ จึงถูกซ่อนจาก
            # "ดูตัวเลขทีมทั้งหมด" แต่ต้องอยู่ใน team_rows เพื่อให้สองแท็บใช้ค่าเดียวกัน
            "ธงเฝ้าระวังรายค่า": flag_fields,
            "pace–HR จากฐาน (%)": ef_pct,
        })

    team_df = pd.DataFrame(team_rows)
    TEAM_INTERNAL_COLUMNS = ["ธงเฝ้าระวังรายค่า", "pace–HR จากฐาน (%)", "สถานะเทรนด์ HRV",
                             "ขอบเขตโหลด"]

    return team_df, TEAM_INTERNAL_COLUMNS
