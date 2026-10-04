"""หน้า "สถานะระบบ" — สำหรับคนดูแลระบบ แยกจากหน้าสุขภาพของนักกีฬา

แสดงผลของ ``health_report.run_all_checks()`` ตัวเดียวกับที่ heartbeat ใช้ (อ่านอย่างเดียว
ไม่ซ่อม ไม่ restart อะไร) และสถานะ sync ล่าสุดรายคนจาก ``data/sync_status/<slug>.json``
ไม่แสดง token, stack trace หรือค่าข้อมูลสุขภาพ
"""

import pandas as pd
import streamlit as st

import health_report
from dashboard_context import page_context
from dashboard_freshness import load_freshness, read_sync_summary

ctx = page_context()

st.title("สถานะระบบ")
st.subheader("ความสดและวันที่ไม่มีข้อมูล", anchor=False)
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
    sync_rows.append({"นักกีฬา": name, "ผล": sync["result"],
                      "จบรอบล่าสุด (เวลาเครื่องซิงก์/เวลาไทยเมื่อมีโซน)": sync["finished"],
                      "ควรทำต่อ": sync["action"]})
st.caption(f"ตรวจช่วง {ctx.start_date:%d/%m/%Y}–{ctx.end_date:%d/%m/%Y} ของทุกคน · "
           "ไม่นับวันนี้ที่ยังไม่จบและวันก่อนมีข้อมูลครั้งแรก · มีค่าอย่างน้อยหนึ่งช่องในหน้าร่างกายถือว่ามีข้อมูล")
st.dataframe(pd.DataFrame(coverage), hide_index=True, width="stretch")
st.caption("วันว่างไม่ได้ยืนยันว่าซิงก์ล้ม และวันที่มีก็ไม่ได้หมายถึงครบทุกช่อง · "
           "วันที่ไม่วิ่งไม่ถือเป็นกิจกรรมขาด · ตรวจวันเดียวกันใน Garmin Connect และการใส่/ซิงก์นาฬิกาก่อน")
with st.expander("ควรเริ่มตรวจอย่างไร"):
    st.markdown("1. ตรวจวันเดียวกันใน Garmin Connect และให้นาฬิกาซิงก์กับแอป\n"
                "2. ดูผลซิงก์รายคนด้านล่าง: token ต้องขอใหม่บนเครื่องใช้งาน; "
                "เน็ต/ช่องข้อมูลที่ล้มให้รอรอบถัดไป\n"
                "3. ถ้า Garmin Connect มีข้อมูลแต่หน้ายังว่าง ให้กดรีเฟรชข้อมูล "
                "แล้วตรวจ log บนเครื่องใช้งานตามคู่มือ ไม่ส่งรหัสผ่านหรือ token")

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


findings, failure = ([], None) if ctx.demo_mode else load_findings()
if ctx.demo_mode:
    st.info("Demo ไม่ตรวจ Scheduled Task, token, backup หรือ heartbeat ของเครื่องจริง · "
            "ใช้สำหรับทดลองหน้าจอเท่านั้น")
elif failure:
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
st.dataframe(pd.DataFrame(sync_rows), hide_index=True, width="stretch")
st.caption("สำเร็จบางส่วน = มีช่องข้อมูลที่ Garmin ตอบไม่สำเร็จในรอบนั้น รอบถัดไปจะลองใหม่เอง · "
           "แจ้งเตือนจริงส่งผ่าน Windows toast และ GitHub heartbeat ตามเดิม")
