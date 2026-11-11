"""หน้า "สถานะระบบ" — สำหรับคนดูแลระบบ แยกจากหน้าสุขภาพของนักกีฬา

แสดงผลของ ``health_report.run_all_checks()`` ตัวเดียวกับที่ heartbeat ใช้ (อ่านอย่างเดียว
ไม่ซ่อม ไม่ restart อะไร) และสถานะ sync ล่าสุดรายคนจาก ``data/sync_status/<slug>.json``
ไม่แสดง token, stack trace หรือค่าข้อมูลสุขภาพ
"""

import health_report
import pandas as pd
import streamlit as st
from dashboard_context import chart_header, page_context, page_lead, section_heading
from dashboard_data import data_dir
from dashboard_freshness import load_freshness, read_sync_summary

ctx = page_context()

LANE_THAI = {
    "full": "หลัก (08:00 / 21:00)",
    "fast": "ด่วนรายชั่วโมง",
    "wellness": "สุขภาพรายชั่วโมง",
    "reconcile": "ทวนยอดย้อนหลัง",
    "deep": "ดึงย้อนหลังเชิงลึก",
    "backup": "สำรองข้อมูล",
}

EXACT_CHECK_THAI = {
    "unfinished_run": "งานซิงก์ที่เริ่มแล้วยังไม่จบ",
    "backup:lane_status": "สำรองข้อมูล · สถานะงานล่าสุด",
    "backup:daily_files": "สำรองข้อมูล · ไฟล์รายวันในเครื่อง",
    "recovery:offsite_backup": "สำรองข้อมูล · สำเนานอกโฟลเดอร์หลัก",
    "recovery:restore_drill": "ทดสอบกู้คืนฐานข้อมูล (Restore Drill)",
    "db_integrity": "ความสมบูรณ์ไฟล์ฐานข้อมูล SQLite",
    "disk_space:data": "พื้นที่ว่างดิสก์ · โฟลเดอร์ข้อมูล",
    "disk_space:backup": "พื้นที่ว่างดิสก์ · โฟลเดอร์สำรองข้อมูล",
    "lane_limit_consistency": "เพดานเวลาแจ้งเตือนตรงกันทุกสคริปต์",
    "private_acl": "สิทธิ์จำกัดการเข้าถึงโฟลเดอร์ข้อมูล (Windows ACL)",
    "healthcheck_secret_storage": "การจัดเก็บรหัสแจ้งเตือนอย่างปลอดภัย",
}


def _human_check_name(raw_key: str) -> str:
    if raw_key in EXACT_CHECK_THAI:
        return EXACT_CHECK_THAI[raw_key]
    if raw_key.startswith("scheduled_task:"):
        task = raw_key.split(":", 1)[1].removeprefix("Run-Performance-")
        return f"งานตั้งเวลา Windows · {task}"
    if raw_key.startswith("lane_freshness:"):
        lane = raw_key.split(":", 1)[1]
        return f"ความสดสายซิงก์ · {LANE_THAI.get(lane, lane)}"
    if raw_key.startswith("unfinished_run:"):
        lane = raw_key.split(":", 1)[1]
        return f"งานซิงก์ค้าง · {LANE_THAI.get(lane, lane)}"
    if raw_key.startswith("data_quality_coverage:"):
        slug = raw_key.split(":", 1)[1]
        return f"ความต่อเนื่องข้อมูล · {slug}"
    if raw_key.startswith("disk_space:"):
        target = raw_key.split(":", 1)[1]
        return f"พื้นที่ว่างดิสก์ · {target}"
    return raw_key


st.title("สถานะระบบ")
page_lead(
    "ตรวจสอบความสดของข้อมูล งานซิงก์อัตโนมัติ และไฟล์สำรองฐานข้อมูลแบบอ่านอย่างเดียว "
    "(ไม่แสดงรหัสผ่านหรือ token)"
)

coverage = []
sync_rows = []
for athlete in ctx.athletes_df.to_dict("records"):
    summary = load_freshness(athlete["athlete_id"], ctx.start_date, ctx.end_date, ctx.today)
    sync = read_sync_summary(athlete["slug"]) if not ctx.demo_mode else {
        "result": "ไม่ได้ซิงก์จริง (Demo)", "finished": "–",
        "action": "ลองนักกีฬา A, B และนักกีฬาใหม่ เพื่อดูข้อมูลต่อเนื่อง วันว่าง และยังไม่มีประวัติ",
    }
    name = ctx.athlete_labels[athlete["athlete_id"]]
    coverage.append({
        "นักกีฬา": name, "สุขภาพล่าสุด": summary["latest_text"],
        "ดึงค่าหลักล่าสุด (เวลาไทย)": summary["received_at"],
        "วันไม่มีข้อมูลสุขภาพ": summary["gaps_text"],
    })
    sync_rows.append({
        "นักกีฬา": name,
        "ผลซิงก์ล่าสุด": sync["result"],
        "เวลาจบรอบล่าสุด": sync["finished"],
        "คำแนะนำ": sync["action"],
    })

section_heading("ความต่อเนื่องของข้อมูลรายคน", f"ช่วงวันที่ตรวจสอบ {ctx.start_date:%d/%m/%Y} – {ctx.end_date:%d/%m/%Y}")
with st.container(border=True, key="surface-sys-coverage"):
    chart_header(
        st,
        "ความสดของข้อมูลและวันที่ว่าง",
        "ตรวจเฉพาะวันก่อนหน้าวันนี้ (ไม่นับวันที่ยังไม่จบวัน) · วันว่างมักเกิดจากไม่ได้ใส่นาฬิกานอนหรือยังไม่ได้เปิดแอป Garmin Connect",
        f"{len(coverage)} คน",
    )
    st.dataframe(pd.DataFrame(coverage), hide_index=True, width="stretch")
    with st.expander("ขั้นตอนตรวจสอบเมื่อพบวันไม่มีข้อมูล", icon=":material/help:"):
        st.markdown("1. เปิดแอป Garmin Connect ของนักกีฬาเพื่อตรวจว่านาฬิกาซิงก์ข้อมูลวันนั้นขึ้นคลาวด์แล้วหรือยัง\n"
                    "2. ดูตาราง **sync ล่าสุดรายคน** ด้านล่าง — หากแจ้งเรื่อง token ให้ต่ออายุบนเครื่องซิงก์; "
                    "หากเป็นปัญหาเครือข่ายชั่วคราว ระบบจะดึงซ้ำให้อัตโนมัติในรอบถัดไป\n"
                    "3. เมื่อซิงก์เสร็จแล้ว กดปุ่ม **รีเฟรชข้อมูลทันที** ที่แถบซ้ายเพื่อโหลดข้อมูลใหม่ขึ้นหน้าจอ")

LEVEL_TEXT = {"ERROR": "ต้องแก้ไข", "WARNING": "ควรตรวจสอบ", "OK": "ปกติ"}
LEVEL_ORDER = {"ERROR": 0, "WARNING": 1, "OK": 2}


@st.cache_data(ttl=120, show_spinner="กำลังตรวจสถานะระบบ…")
def load_findings(current_data_dir: str):
    # ตรวจ ACL 2,100+ paths + Scheduled Tasks แบบขนานใน ~1.2 วินาที และแคชไว้ 2 นาที
    previous = health_report.use_data_dir(current_data_dir)
    try:
        return [finding.to_dict() for finding in health_report.run_all_checks()], None
    except Exception as exc:  # noqa: BLE001 — หน้าดูแลระบบต้องไม่ล้มทั้งแอปเพราะตัวตรวจพัง
        return [], type(exc).__name__
    finally:
        health_report.use_data_dir(previous)


section_heading("งานอัตโนมัติและประวัติการซิงก์", "Scheduled Tasks · Backup · สถานะซิงก์รายคน")
with st.container(border=True, key="surface-sys-health"):
    chart_header(
        st,
        "ผลตรวจสุขภาพระบบอัตโนมัติ",
        "ตรวจการทำงานของ Scheduled Task ไฟล์สำรอง ความสมบูรณ์ฐานข้อมูล และพื้นที่ว่างดิสก์ (เมื่อเปิดเครื่องกลับมา ระบบจะตามเก็บรอบซิงก์ที่ค้างเอง)",
    )
    findings, failure = ([], None) if ctx.demo_mode else load_findings(str(data_dir()))
    if ctx.demo_mode:
        st.info("โหมด Demo ไม่ตรวจ Scheduled Task, token หรือ backup ของเครื่องจริง", icon=":material/info:")
    elif failure:
        st.error(f"ตัวตรวจสถานะทำงานไม่สำเร็จ ({failure}) — ลองรัน "
                 "`garmin\\.venv\\Scripts\\python.exe scripts\\health_report.py` เพื่อดูรายละเอียด",
                 icon=":material/error:")
    else:
        counts = {level: sum(f["level"] == level for f in findings) for level in LEVEL_TEXT}
        c_err, c_warn, c_ok = st.columns(3)
        err_key = "sys-kpi-err-active" if counts["ERROR"] > 0 else "sys-kpi-err"
        warn_key = "sys-kpi-warn-active" if counts["WARNING"] > 0 else "sys-kpi-warn"
        with c_err, st.container(key=err_key):
            st.metric("ต้องแก้ไข", counts["ERROR"], border=True, width="stretch")
        with c_warn, st.container(key=warn_key):
            st.metric("ควรตรวจสอบ", counts["WARNING"], border=True, width="stretch")
        with c_ok, st.container(key="sys-kpi-ok"):
            st.metric("ปกติ", counts["OK"], border=True, width="stretch")
        if findings:
            ordered = sorted(findings, key=lambda f: (LEVEL_ORDER.get(f["level"], 3), f["check"]))
            table = pd.DataFrame({
                "สถานะ": [LEVEL_TEXT.get(f["level"], f["level"]) for f in ordered],
                "หัวข้อที่ตรวจ": [_human_check_name(f["check"]) for f in ordered],
                "รายละเอียด": [f["message"] for f in ordered],
            })
            st.dataframe(table, hide_index=True, width="stretch")
        else:
            st.caption("ไม่มีรายการตรวจสถานะ")

with st.container(border=True, key="surface-sys-sync"):
    chart_header(
        st,
        "sync ล่าสุดรายคน",
        "ผลจากการรันซิงก์รอบล่าสุดของแต่ละบัญชี · หากสำเร็จบางส่วน ระบบจะดึงส่วนที่ค้างใหม่อัตโนมัติในรอบถัดไป",
    )
    st.dataframe(pd.DataFrame(sync_rows), hide_index=True, width="stretch")
