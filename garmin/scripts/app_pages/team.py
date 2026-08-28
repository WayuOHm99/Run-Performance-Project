"""หน้า "ทีม" ของ Coach Dashboard"""

import datetime
import math

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from dashboard_domain import (
    status_parts,
    team_urgency_rank,
)

from dashboard_view import (
    TEAM_CARD_CSS,
    css_key,
    render_team_card,
    status_shape_svg,
)

from dashboard_context import page_context

_ctx = page_context()
athletes_df = _ctx.athletes_df
today = _ctx.today

from dashboard_context import focus_athlete
from dashboard_team import team_snapshot

team_df, TEAM_INTERNAL_COLUMNS = team_snapshot(athletes_df, today)
team_rows = team_df.to_dict("records")


st.header("สัญญาณทีมวันนี้")
st.caption(
    f"ข้อมูล ณ {today.isoformat()} — สรุปสิ่งที่อุปกรณ์ตรวจพบ ไม่ใช่คำสั่งพร้อมซ้อม/ต้องพัก · "
    "pace–HR และโหลดเป็นแนวโน้มประกอบ ต้องคุยอาการเจ็บ ป่วย ความล้า และบริบทกับนักกีฬา"
)


# การ์ดต่อคนแทนตารางสรุป 10 คอลัมน์ที่กว้างเกินจอ — คอลัมน์ท้าย ๆ เคยถูกมองข้าม
# ทั้งที่มีข้อมูล แค่ต้องเลื่อนดู. เรียงตามความเร่งด่วน เพราะคำถามแรกของเช้าคือ
# "ใครต้องดูก่อน" ไม่ใช่ "เรียงตามชื่อแล้วใครอยู่บนสุด"
st.markdown(TEAM_CARD_CSS, unsafe_allow_html=True)
ordered_team = sorted(team_rows, key=lambda item: team_urgency_rank(item["สถานะ"]))
for order, row in enumerate(ordered_team):
    # การ์ดทั้งใบเป็นปุ่ม: ปุ่มจริงถูกวางทับทั้งใบแบบโปร่งใสด้วย CSS ที่เจาะจงผ่าน
    # คลาส st-key-* ซึ่ง Streamlit ติดให้ทุก container/widget ที่มี key
    # ถ้า CSS ไม่ทำงาน ปุ่มจะกลับไปอยู่ใต้การ์ดตามเดิม — เสียหน้าตา แต่ยังกดได้
    # ต่อลำดับท้ายคีย์เสมอ เพราะชื่อไทยสองชื่อที่ต่างกันแค่วรรณยุกต์จะถูกล้างเหลือ
    # สลักเดียวกัน แล้ว Streamlit จะโยน StreamlitDuplicateElementKey ทั้งหน้า
    slug = f"{css_key(row['นักกีฬา'])}-{order}"
    with st.container(key=f"teamcard-{slug}"):
        st.markdown(render_team_card(row), unsafe_allow_html=True)
        st.button(
            f"ดูรายละเอียดของ {row['นักกีฬา']}",
            key=f"open-athlete-{slug}",
            on_click=focus_athlete,
            args=(row["นักกีฬา"],),
            width="stretch",
        )

with st.expander("ดูตัวเลขทีมทั้งหมด", icon=":material/table_view:"):
    st.dataframe(
        # "สถานะ" กับ "สถานะ pace–HR" เก็บอีโมจิไว้เป็น *คีย์* ให้การ์ดแปลงเป็นรูปทรง
        # (การ์ดอ่านจาก `team_df` ก่อนบรรทัดนี้ จึงยังได้คีย์ครบ) — ตารางนี้เป็น
        # ข้อความล้วนที่คนอ่าน จึงต้องถอดคีย์ออกก่อน ไม่งั้นอีโมจิถึงตาโค้ชตรง ๆ
        team_df.drop(columns=TEAM_INTERNAL_COLUMNS).assign(
            **{
                column: (lambda frame, name=column: frame[name].map(
                    lambda value: status_parts(value)[1]))
                for column in ("สถานะ", "สถานะ pace–HR")
            }
        ),
        hide_index=True,
        column_config={
            "นักกีฬา": st.column_config.TextColumn("นักกีฬา", pinned=True),
            "pace–HR trend": st.column_config.TextColumn(
                "แนวโน้ม pace–HR รันเบา"),
            "Body Battery ตอนนี้/ล่าสุด": st.column_config.NumberColumn(
                "Body Battery ตอนนี้/ล่าสุด", format="%.0f"),
            "Sleep": st.column_config.NumberColumn("Sleep", format="%.0f"),
            "RHR": st.column_config.NumberColumn("RHR", format="%.0f"),
            "Readiness": st.column_config.NumberColumn("Readiness", format="%.0f"),
            "สถานะซ้อม (Garmin)": st.column_config.TextColumn(
                "สถานะซ้อม (Garmin)",
                help="สถานะที่ Garmin คำนวณเองและขึ้นกับรุ่นนาฬิกา"),
            "โหลด 7 วัน": st.column_config.TextColumn(
                "โหลด 7 วัน",
                help="ปริมาณดิบพร้อมหน่วยของตัวเอง — TL จาก Garmin ถ้านาฬิกาให้ "
                     "ไม่งั้นเป็นระยะวิ่ง (km) เทียบข้ามคนไม่ได้"),
            "ค่าเฉลี่ยโหลด 28 วัน": st.column_config.TextColumn(
                "ค่าเฉลี่ยโหลด 28 วัน",
                help="แสดงแยกจากโหลด 7 วัน ไม่หารเป็น ACWR และไม่ใช้เป็นเส้นเสี่ยง"),
            "เซสชัน 7 วัน": st.column_config.NumberColumn(
                "เซสชัน 7 วัน", format="%d",
                help="คนที่โหลดมาจาก TL นับทุกกิจกรรม "
                     "ส่วนคนที่ใช้ระยะวิ่งนับเฉพาะการวิ่ง"),
        },
    )

with st.expander("เกณฑ์ที่ใช้ประเมิน", icon=":material/info:"):
    # คำอธิบายต้องใช้สัญลักษณ์เดียวกับที่การ์ดวาดจริง — เดิมเป็นอีโมจิ
    # ทั้งที่การ์ดเป็นรูปทรงวาดมาตั้งแต่ PR #32 โค้ชจึงเห็นคนละภาษาในหน้าเดียว
    # และบนกระดาษขาวดำคำอธิบายเหลือช่องว่างส่วนการ์ดยังอ่านได้
    def _legend_mark(key):
        return status_shape_svg(key, 11)

    st.markdown(
        "**สรุปสัญญาณจากอุปกรณ์:** "
        + _legend_mark("watch") + " ควรทบทวนก่อนซ้อม = มี Garmin signal อย่างน้อย 1 ข้อ · "
        + _legend_mark("ready")
        + " ไม่พบสัญญาณเตือนจากอุปกรณ์ = ไม่มี signal ในข้อมูลที่มี (ไม่ใช่ training clearance) · "
        + _legend_mark("unknown")
        + " ข้อมูลไม่พอ = ยังไม่มีข้อมูลซ้อม หรือ wellness สดน้อยกว่า 3/4 ค่า · "
        + _legend_mark("unknown")
        + " ไม่มีข้อมูล = ยังไม่มีทั้ง workload และ wellness",
        unsafe_allow_html=True,
    )
    # หน่วยของโหลดขึ้นกับรุ่นนาฬิกา ทีมนี้จึงมีทั้ง TL และ km พร้อมกัน
    # (วัดจริง 27 ส.ค. 69: 32.7 km · 92.6 km · 323 TL) — ถ้าไม่บอกไว้ตรงนี้
    # ตัวเลขดิบที่วางเรียงกันจะถูกอ่านว่าเทียบกันได้
    st.markdown(
        "**โหลด 7 วัน:** หน่วยขึ้นกับ**รุ่นนาฬิกา** — ได้ Garmin Training Load (TL) "
        "ถ้านาฬิกาส่งมา ไม่งั้นคิดจากระยะวิ่ง (km) **ตัวเลขดิบจึงเทียบข้ามคนไม่ได้** "
        "ระบบแสดงโหลด 7 วันกับค่าเฉลี่ย 28 วันแยกกันและไม่หารเป็น ACWR · "
        "จำนวนเซสชันก็คนละนิยาม: โหลดจาก TL นับทุกกิจกรรม ส่วนโหลดจากระยะวิ่งนับเฉพาะการวิ่ง"
    )
    st.markdown(r"""

**นโยบาย Garmin-only:** ไม่มีแบบฟอร์มและไม่รวมค่าเป็นคะแนนความสดใหม่ของระบบ
ก่อนซ้อมต้องถามปากเปล่าเรื่องอาการเจ็บ ป่วย และความล้าผิดปกติ

**Garmin signals ที่แสดงให้ทบทวน:** Sleep อยู่หมวด Poor · HRV LOW/UNBALANCED ·
Training Readiness LOW/POOR · Training Status Strained/Overreaching/Unproductive
ค่ากลุ่มนี้สัมพันธ์และซ้อนองค์ประกอบกัน จึงไม่นับจำนวนเป็นคะแนนโหวต

**แนวโน้ม pace–HR รันเบา** = ความเร็ว (ม./นาที) ÷ HR เฉลี่ย นับเฉพาะข้อมูลวิ่ง easy
(HR ≤ 89% LTHR, ระยะรวม ≥ 3 กม.) โดยรวมหลาย activity ในวันเดียวเป็นหนึ่งค่ารายวัน
แล้วเทียบ median 3 วันล่าสุดกับฐาน 28 วันก่อนหน้าที่ไม่ซ้อนกัน
ค่านี้ไวต่อเพซ เส้นทาง ความชัน อากาศ การหยุด และ HR sensor จึงเป็นบริบทเท่านั้น
ไม่ใช่ running economy หรือความสด และไม่มีเกณฑ์สั่งพัก/เพิ่มโหลด

**ก่อนเปลี่ยนตาราง:** ต้องถามอาการเจ็บเฉพาะจุด/วิ่งเสียฟอร์ม อาการป่วย ไข้ เจ็บหน้าอก
เวียนหัว ความล้า/ปวดกล้ามเนื้อ คุณภาพการนอน ความเครียด และเป้าหมายของเซสชัน
หากมีอาการทางการแพทย์หรืออาการเจ็บที่เปลี่ยนการวิ่ง ให้หยุดประเมินโดยโค้ชอย่างเดียว
และส่งต่อผู้เชี่ยวชาญที่เหมาะสม

_โหลด 7 วันและค่าเฉลี่ย 28 วันเป็นบริบทแยกกัน ไม่ดันสถานะและไม่สร้าง ACWR ในชื่อใหม่_
""")
