"""หน้า "สถานะระบบ" — สำหรับคนดูแลระบบ แยกจากหน้าสุขภาพของนักกีฬา

แสดงผลของ ``health_report.run_all_checks()`` ตัวเดียวกับที่ heartbeat ใช้ (อ่านอย่างเดียว
ไม่ซ่อม ไม่ restart อะไร) และสถานะ sync ล่าสุดรายคนจาก ``data/sync_status/<slug>.json``
ไม่แสดง token, stack trace หรือค่าข้อมูลสุขภาพ
"""

import json

import pandas as pd
import streamlit as st

import health_report
from dashboard_context import page_context
from dashboard_data import data_dir

ctx = page_context()

st.title("สถานะระบบ")
st.caption("ตรวจงาน sync, Scheduled Task, backup, ฐานข้อมูล และพื้นที่ดิสก์แบบอ่านอย่างเดียว · "
           "เครื่องที่หลับหรือปิดอยู่ทำงานเหล่านี้ไม่ได้ เมื่อเปิดกลับมาจะตามเก็บรอบที่พลาดเอง")

LEVEL_TEXT = {"ERROR": "ต้องแก้", "WARNING": "ควรดู", "OK": "ปกติ"}
LEVEL_ORDER = {"ERROR": 0, "WARNING": 1, "OK": 2}


@st.cache_data(ttl=120, show_spinner="กำลังตรวจสถานะระบบ…")
def load_findings():
    # เรียก schtasks ทีละ task จึงใช้เวลาราว 4 วินาที — แคช 2 นาทีพอสำหรับหน้าดูแลระบบ
    try:
        return [finding.to_dict() for finding in health_report.run_all_checks()], None
    except Exception as exc:  # หน้าดูแลระบบต้องไม่ล้มทั้งแอปเพราะตัวตรวจพัง
        return [], type(exc).__name__


findings, failure = load_findings()
if failure:
    st.error(f"ตัวตรวจสถานะทำงานไม่สำเร็จ ({failure}) — ลองรัน "
             "`garmin\\.venv\\Scripts\\python.exe scripts\\health_report.py` เพื่อดูรายละเอียด",
             icon=":material/error:")
else:
    counts = {level: sum(f["level"] == level for f in findings) for level in LEVEL_TEXT}
    with st.container(horizontal=True):
        st.metric("ต้องแก้", counts["ERROR"], border=True)
        st.metric("ควรดู", counts["WARNING"], border=True)
        st.metric("ปกติ", counts["OK"], border=True)
    table = pd.DataFrame(sorted(findings, key=lambda f: (LEVEL_ORDER.get(f["level"], 3), f["check"])))
    table = table.assign(ระดับ=table["level"].map(LEVEL_TEXT).fillna(table["level"]))
    st.dataframe(
        table[["ระดับ", "check", "message"]].rename(columns={"check": "รายการ", "message": "รายละเอียด"}),
        hide_index=True, width="stretch",
    )

st.subheader("sync ล่าสุดรายคน", anchor=False)
rows = []
for athlete in ctx.athletes_df.to_dict("records"):
    path = data_dir() / "sync_status" / f"{athlete['slug']}.json"
    try:
        status = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        status = {}
    failures = status.get("endpoint_failures") or []
    rows.append({
        "นักกีฬา": athlete["display_name"],
        "ผล": "สำเร็จ" if status.get("ok") else ("ไม่มีบันทึก" if not status else "ล้มเหลว"),
        "สาเหตุ": {"ok": "", "token": "ต้องขอ token ใหม่ (เพิ่มนักกีฬา.bat)",
                   "network": "เน็ต/เซิร์ฟเวอร์ Garmin"}.get(status.get("reason"),
                                                             status.get("reason") or ""),
        "endpoint ที่ล้ม": len(failures),
        "เสร็จเมื่อ": (status.get("finished_at") or "")[:16].replace("T", " "),
    })
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
st.caption("endpoint ที่ล้ม = ช่องข้อมูลที่ Garmin ตอบไม่สำเร็จในรอบนั้น รอบถัดไปจะลองใหม่เอง · "
           "แจ้งเตือนจริงส่งผ่าน Windows toast และ GitHub heartbeat ตามเดิม")
