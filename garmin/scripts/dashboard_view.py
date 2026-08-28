"""ชิ้นส่วนหน้าตาที่คืนค่าเป็นสตริง — HTML/SVG/CSS และการแต่งรูป Plotly

ยังไม่แตะ ``st.`` สักบรรทัด จึงเรียกและทดสอบได้โดยไม่ต้องรัน Streamlit
ส่วนที่เรียก ``st.`` จริงยังอยู่ใน ``dashboard.py``
"""

import datetime
import html

import pandas as pd

from dashboard_domain import (
    INTENSITY_ORDER,
    _num_text,
    fmt_pace,
    fmt_sec,
    load_context_line,
    status_parts,
)


# สีสถานะ (ผ่าน CVD validation) — ใช้คู่กับข้อความกำกับเสมอ ไม่สื่อด้วยสีอย่างเดียว
C_GOOD = "#0ca30c"

C_WARN = "#fab219"

C_CRIT = "#d03b3b"

C_BLUE = "#2a78d6"   # เส้นข้อมูลหลัก

C_CONTEXT = "#8a8d94"  # เส้นฐาน เส้นตาราง วันพัก — บริบทต้องถอยไปข้างหลัง (กฎกราฟ 04)

TREND_KEY_BY_LABEL = {
    "แนวโน้มประกอบ": "gain",
    "ข้อมูลไม่พอ": "unknown",
}

def mark_partial_today(fig, today_date, period_start, period_end):
    """Mark today's still-changing point on a Plotly date chart."""
    start = pd.Timestamp(period_start).date()
    end = pd.Timestamp(period_end).date()
    if start <= today_date <= end:
        x_value = datetime.datetime.combine(today_date, datetime.time.min)
        fig.add_shape(
            type="line", x0=x_value, x1=x_value, y0=0, y1=1,
            xref="x", yref="paper", line=dict(color=C_CONTEXT, dash="dot", width=1),
        )
        fig.add_annotation(
            x=x_value, y=1, xref="x", yref="paper", text="วันนี้ · ยังไม่ครบวัน",
            showarrow=False, xanchor="left", yanchor="bottom", font=dict(size=10, color="#61656d"),
        )
    return fig

STATUS_COLORS = {"rest": C_CRIT, "watch": C_WARN, "ready": C_GOOD,
                 "gain": C_BLUE, "unknown": "#8a8d94"}

# ข้อความสีสำหรับตัวหนังสือ — สีจุดสถานะบางตัวจางเกินจะอ่านเป็นตัวอักษรบนพื้นขาว
STATUS_TEXT_COLORS = {"rest": C_CRIT, "watch": "#8a5b00", "ready": "#006300",
                      "gain": "#184f95", "unknown": "#55585f"}

def status_shape_svg(key, size=12):
    """รูปทรงประจำสถานะแทนอีโมจิ — วงกลม/สี่เหลี่ยม/สามเหลี่ยม/วงว่าง

    อีโมจิเรนเดอร์ไม่เหมือนกันข้ามเครื่องและหายตอนพิมพ์ขาวดำ ซึ่งเป็นเหตุผลเดียวกับที่
    dashboard ล็อกธีมสว่างไว้ (ดู .streamlit/config.toml) — รูปทรงวาดอ่านได้ทั้งบนจอ
    บนกระดาษขาวดำ และแยกออกโดยไม่ต้องพึ่งสีสำหรับคนตาบอดสี
    """
    color = STATUS_COLORS.get(key, STATUS_COLORS["unknown"])
    if key == "rest":
        box, body = "0 0 12 11", f'<path d="M6 0 L12 11 L0 11 Z" fill="{color}"/>'
    elif key == "watch":
        box, body = "0 0 11 11", f'<rect width="11" height="11" fill="{color}"/>'
    elif key == "unknown":
        box = "0 0 11 11"
        body = (f'<circle cx="5.5" cy="5.5" r="4.7" fill="none" '
                f'stroke="{color}" stroke-width="1.6"/>')
    else:
        box, body = "0 0 11 11", f'<circle cx="5.5" cy="5.5" r="5.5" fill="{color}"/>'
    return (f'<svg width="{size}" height="{size}" viewBox="{box}" aria-hidden="true"'
            f' style="flex-shrink:0">{body}</svg>')

def css_key(name):
    """ชื่อนักกีฬา -> คีย์ที่ปลอดภัยสำหรับใช้เป็นคลาส CSS

    Streamlit ติดคลาส ``st-key-<key>`` ให้ทุก container/widget ที่มี key แต่ชื่อจริง
    มีอักขระที่ใช้ในคลาสไม่ได้ — "P'kao" จะกลายเป็นเซเลกเตอร์พังและ CSS ทั้งบล็อกถูกทิ้ง
    """
    cleaned = "".join(
        character if character.isalnum() or character in "-_" else "-"
        for character in str(name).lower()
    ).strip("-")
    return cleaned or "athlete"

def render_team_card(row):
    """การ์ดหนึ่งใบต่อนักกีฬาหนึ่งคน แทนหนึ่งแถวของตารางสรุปเดิม

    อ่านจาก dict เดียวกับที่ team_df ใช้ — ห้ามเปลี่ยนชื่อคีย์ เพราะแท็บ "วันนี้"
    อ่าน team_df ต่อจากที่นี่ (team_row["สถานะ"], ["สถานะ pace–HR"], ["โหลด 7 วัน"] ฯลฯ)
    """
    esc = html.escape
    key, label = status_parts(row["สถานะ"])
    color = STATUS_COLORS.get(key, STATUS_COLORS["unknown"])
    text_color = STATUS_TEXT_COLORS.get(key, STATUS_TEXT_COLORS["unknown"])

    raw_flags = str(row.get("ธงเฝ้าระวัง") or "").strip()
    flags = [part.strip() for part in raw_flags.split("|")
             if part.strip() and part.strip() != "—"]
    if flags:
        flag_label = f"ธงเฝ้าระวัง {len(flags)} ข้อ"
        chips = "".join(
            f'<span class="team-card__chip" style="border:1px solid {color};'
            f'color:{text_color}">{status_shape_svg(key, 9)}{esc(flag)}</span>'
            for flag in flags
        )
    else:
        flag_label = "ธงเฝ้าระวัง"
        chips = '<div style="font-size:14px;color:#55585f">ไม่มี</div>'

    ef_key, ef_label = status_parts(row.get("สถานะ pace–HR") or "")
    ef_color = STATUS_TEXT_COLORS.get(ef_key, STATUS_TEXT_COLORS["unknown"])

    hrv_raw = str(row.get("HRV คืนล่าสุด") or "–")
    hrv_val, _, hrv_note = hrv_raw.partition(" · ")
    hrv_color = {"LOW": C_CRIT, "UNBALANCED": "#8a5b00"}.get(hrv_note, "#006300")

    # ค่าว่างของ EF ต้องบอกเหตุผลตรงจุดที่มันว่าง ไม่งั้นโค้ชอ่านว่า sync พังแล้วไปไล่
    # แก้ระบบที่ไม่ได้เสีย — ข้อความนี้โผล่เฉพาะตอนสรุปไม่ได้ ไม่ใช่คำอธิบายที่เห็นตลอด
    ef_value = str(row.get("pace–HR trend") or "–")
    ef_missing = ef_value.strip() in ("–", "-", "")
    hrv_trend_value = str(row.get("เทรนด์ HRV 7 คืน (%)") or "–")
    hrv_trend_label = str(row.get("สถานะเทรนด์ HRV") or "")
    hrv_trend_sample = str(row.get("จำนวนคืน HRV ที่ใช้") or "")

    # pace-HR เงียบเพราะรัน easy ไม่พอ ไม่ใช่เพราะระบบพัง — ถ้ามีเทรนด์ HRV ให้ใช้
    # เป็นข้อมูลประกอบแทน โดยไม่เรียกค่าใดค่าหนึ่งว่า "ความสด"
    if ef_missing and hrv_trend_label:
        trend_key = TREND_KEY_BY_LABEL.get(hrv_trend_label, "unknown")
        first_cell = (
            "เทรนด์ HRV 7 คืน", esc(hrv_trend_value),
            f'{status_shape_svg(trend_key, 10)}'
            f'<span style="color:{STATUS_TEXT_COLORS.get(trend_key, "#55585f")}">'
            f'{esc(hrv_trend_label)}</span>'
            + (f'<br><span style="color:#55585f">{esc(hrv_trend_sample)}</span>'
               if hrv_trend_sample else ''))
    else:
        ef_note = (' <span style="color:#8a8d94">— ต้องมีข้อมูลวิ่ง easy 3 วันภายใน 14 วัน '
                   'ไม่ใช่ระบบขัดข้อง</span>') if ef_missing else ""
        first_cell = (
            "แนวโน้ม pace–HR รันเบา", esc(ef_value),
            f'{status_shape_svg(ef_key, 10)}'
            f'<span style="color:{ef_color}">{esc(ef_label)}</span>{ef_note}')

    cells = [
        first_cell,
        # BB อยู่ในชุดเดียวกับอีก 3 ค่าที่ใช้บอกความครบของข้อมูลอุปกรณ์ จึงแสดงค่าจริง
        # แยกจากสถานะ Garmin โดยไม่ตั้งเส้นตัดพร้อมซ้อม/ต้องพักขึ้นเอง
        ("BODY BAT.", _num_text(row.get("Body Battery ตอนนี้/ล่าสุด")), ""),
        ("SLEEP", _num_text(row.get("Sleep")), ""),
        ("RHR", _num_text(row.get("RHR")),
         f'<span style="color:#55585f">{esc(str(row.get("ΔRHR") or "–"))}</span>'),
        ("HRV", esc(hrv_val),
         f'<span style="color:{hrv_color}">{esc(hrv_note)}</span>' if hrv_note else ""),
    ]
    load_line = load_context_line(
        str(row.get("โหลด 7 วัน") or "–"),
        str(row.get("ค่าเฉลี่ยโหลด 28 วัน") or "–"),
        row.get("เซสชัน 7 วัน") or 0,
        str(row.get("ขอบเขตโหลด") or "วิ่ง"),
    )

    numbers = "".join(
        f'<div><div class="team-card__lbl" style="margin-bottom:2px">{esc(title)}</div>'
        f'<div class="team-card__val">{value}</div>'
        + (f'<div class="team-card__sub">{sub}</div>' if sub else "")
        + "</div>"
        for title, value, sub in cells
    )

    return (
        f'<div class="team-card" style="border-left-color:{color}">'
        f'<div class="team-card__who">'
        f'<div class="team-card__head">{status_shape_svg(key, 13)}'
        f'<span class="team-card__name">{esc(str(row["นักกีฬา"]))}</span></div>'
        f'<div class="team-card__status" style="color:{text_color}">{esc(label)}</div>'
        f'<div class="team-card__fresh">{esc(str(row.get("ความสดรายค่า") or ""))}</div>'
        f'</div>'
        f'<div class="team-card__flags">'
        f'<div class="team-card__lbl">{esc(flag_label)}</div>'
        f'<div class="team-card__chips">{chips}</div>'
        f'<div class="team-card__load">โหลด {esc(load_line)} '
        f'<span style="color:#8a8d94">— แสดงแยก ไม่คำนวณอัตราส่วนเสี่ยง</span></div>'
        f'</div>'
        f'<div class="team-card__nums">{numbers}</div>'
        f'</div>'
    )

# ความหนักเป็นค่ามีลำดับ (เบา→กลาง→หนัก) จึงไล่น้ำเงินเฉดเดียว — เขียว/เหลือง/แดง
# จองไว้ให้ "สถานะ" เท่านั้น ถ้ายืมมาใช้ที่นี่ด้วย สีเดียวกันจะแปลสองความหมายในหน้าเดียว
INTENSITY_CHIP_COLORS = {
    INTENSITY_ORDER[0]: ("#cde2fb", "#104281"),
    INTENSITY_ORDER[1]: (C_BLUE, "#ffffff"),
    INTENSITY_ORDER[2]: ("#104281", "#ffffff"),
}

def sparkline_svg(values, width=104, height=22, color=C_BLUE):
    """เส้นแนวโน้มเล็กใต้ตัวเลข — คืน "" เมื่อจุดใช้ได้น้อยกว่า 3 จุด

    วันที่นาฬิกาไม่ส่งค่าถูกข้าม ไม่ใช่ลากลงศูนย์ ซึ่งจะวาดหลุมที่ไม่มีอยู่จริง
    """
    series = pd.to_numeric(pd.Series(list(values), dtype="object"), errors="coerce")
    points = [float(value) for value in series.dropna()]
    if len(points) < 3:
        return ""
    low, high = min(points), max(points)
    span = high - low
    step = width / (len(points) - 1)
    pad = 2.0
    inner = height - pad * 2
    coords = " ".join(
        f"{index * step:.1f},{pad + inner * (1 - (0.5 if span == 0 else (value - low) / span)):.1f}"
        for index, value in enumerate(points)
    )
    return (f'<svg class="today-spark" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" aria-hidden="true">'
            f'<polyline fill="none" stroke="{color}" stroke-width="1.5" '
            f'stroke-linejoin="round" points="{coords}"/></svg>')

def render_today_tile(label, value, unit="", note="", spark="", alert=None):
    """ไทล์ค่าเดียว: ชื่อ ค่า หน่วย/ที่มา ส่วนต่างจากฐาน และเส้นแนวโน้ม

    ไทล์ที่ติดธงถูกตีกรอบสีสถานะ *และ* มีรูปทรงกับข้อความกำกับ — สีอย่างเดียวอ่านไม่ได้
    บนกระดาษขาวดำ ซึ่งเป็นเหตุผลเดียวกับที่โปรเจกต์ล็อกธีมสว่างไว้
    """
    esc = html.escape
    border = STATUS_COLORS.get(alert, "#e4e1da") if alert else "#e4e1da"
    note_color = STATUS_TEXT_COLORS.get(alert, "#55585f") if alert else "#55585f"
    mark = status_shape_svg(alert, 9) if alert else ""
    note_html = (
        f'<div class="today-tile__note" style="color:{note_color}">{mark}{esc(note)}</div>'
        if note else ""
    )
    unit_html = f'<span class="today-tile__unit">{esc(unit)}</span>' if unit else ""
    return (f'<div class="today-tile" style="border-color:{border}">'
            f'<div class="today-lbl">{esc(label)}</div>'
            f'<div class="today-tile__val">{esc(str(value))}{unit_html}</div>'
            f'{note_html}{spark}</div>')

def render_today_verdict(row):
    """แผงสรุปสัญญาณของนักกีฬาที่เลือก — ไม่ทำหน้าที่ medical/training clearance

    เดิมเป็นกล่อง st.warning/success ที่เลือกชนิดด้วย ``status_text.startswith("🔴")``
    ซึ่งผูกกับอีโมจิในสตริงโดยตรง ถ้าแท็บทีมถอดอีโมจิออกเมื่อไหร่กล่องจะเงียบไปทั้งอัน
    ที่นี่จึงอ่านสถานะผ่าน ``status_parts()`` ที่เดียวเหมือนการ์ดของแท็บทีม
    """
    esc = html.escape
    key, label = status_parts(row["สถานะ"])
    color = STATUS_COLORS.get(key, STATUS_COLORS["unknown"])
    text_color = STATUS_TEXT_COLORS.get(key, STATUS_TEXT_COLORS["unknown"])

    raw_flags = str(row.get("ธงเฝ้าระวัง") or "").strip()
    flags = [part.strip() for part in raw_flags.split("|")
             if part.strip() and part.strip() != "—"]
    if flags:
        chips = "".join(
            f'<span class="today-chip" style="border:1px solid {color};color:{text_color}">'
            f'{status_shape_svg(key, 9)}{esc(flag)}</span>'
            for flag in flags
        )
        flag_block = f'<div class="today-chips">{chips}</div>'
    else:
        flag_block = '<div class="today-none">ไม่มีธงเฝ้าระวัง</div>'

    note = ('<div class="today-verdict__note">ข้อมูลจากอุปกรณ์ไม่ใช่คำอนุญาตให้ซ้อม '
            'ก่อนปรับตารางต้องถามปากเปล่าเรื่องอาการเจ็บ ป่วย ความล้า '
            'และความรู้สึกของนักกีฬา</div>')

    figures = "".join(
        f'<div><div class="today-lbl">{esc(title)}</div>'
        f'<div class="today-verdict__fig">{esc(str(value))}</div></div>'
        for title, value in (
            ("แนวโน้ม pace–HR รันเบา", row.get("pace–HR trend") or "–"),
            ("โหลด 7 วัน", row.get("โหลด 7 วัน") or "–"),
            ("ค่าเฉลี่ยโหลด 28 วัน", row.get("ค่าเฉลี่ยโหลด 28 วัน") or "–"),
            ("เซสชัน 7 วัน", f'{row.get("เซสชัน 7 วัน") or 0} '
                             f'({row.get("ขอบเขตโหลด") or "วิ่ง"})'),
        )
    )
    return (
        f'<div class="today-verdict" style="border-top-color:{color}">'
        f'<div class="today-verdict__main">'
        f'<div class="today-verdict__head">{status_shape_svg(key, 17)}'
        f'<span class="today-verdict__title">{esc(str(row["นักกีฬา"]))} '
        f'<span style="color:{text_color}">{esc(label)}</span></span></div>'
        f'{flag_block}{note}</div>'
        f'<div class="today-verdict__figs">{figures}</div>'
        f'</div>'
    )

def session_intensity_chip(label):
    """ชิปความหนักของเซสชัน — ค่าว่างไม่วาดอะไรเลย

    ไม่มี HR = ไม่รู้ความหนัก การเดาว่า "เบา" ทำให้สัดส่วนความหนักที่โค้ชอ่านผิดไปด้วย
    """
    if not label or label not in INTENSITY_CHIP_COLORS:
        return ""
    background, text = INTENSITY_CHIP_COLORS[label]
    return (f'<span class="today-chip today-chip--zone" '
            f'style="background:{background};color:{text}">{html.escape(str(label))}</span>')

def render_session_row(when, title, distance_km, duration_sec, pace, avg_hr, intensity):
    """หนึ่งเซสชันหนึ่งแถว แทนการ์ดซ้อนการ์ดที่มี st.metric ห้าช่องต่อกิจกรรม"""
    esc = html.escape
    distance = ("–" if distance_km is None or pd.isna(distance_km)
                else f"{float(distance_km):.2f} กม.")
    heart = "–" if avg_hr is None or pd.isna(avg_hr) else f"{float(avg_hr):.0f}"
    cells = "".join(
        f'<div class="today-sess__num">{esc(text)}</div>'
        for text in (distance, fmt_sec(duration_sec), fmt_pace(pace), heart)
    )
    return (f'<div class="today-sess__row">'
            f'<div class="today-sess__when">{esc(str(when))}</div>'
            f'<div class="today-sess__name">{esc(str(title))}</div>'
            f'{cells}'
            f'<div class="today-sess__zone">{session_intensity_chip(intensity)}</div>'
            f'</div>')

def render_load_strip(days, digits=1):
    """แถบโหลดรายวัน 7 ช่อง — วันพักเป็นขีด ไม่ใช่แท่งสูงศูนย์ที่อ่านเหมือนมีข้อมูล"""
    esc = html.escape
    values = [value for _, value in days
              if value is not None and not pd.isna(value) and float(value) > 0]
    peak = max(values) if values else 0.0
    columns = []
    for label, value in days:
        has_value = value is not None and not pd.isna(value) and float(value) > 0
        height = (float(value) / peak * 100) if has_value and peak > 0 else 0
        bar = (f'<div class="today-strip__bar" style="height:{height:.0f}%"></div>'
               if has_value else '<div class="today-strip__rest"></div>')
        text = f"{float(value):.{digits}f}" if has_value else "–"
        columns.append(
            f'<div class="today-strip__col">'
            f'<div class="today-strip__plot">{bar}</div>'
            f'<div class="today-strip__val">{esc(text)}</div>'
            f'<div class="today-strip__day">{esc(str(label))}</div></div>'
        )
    return f'<div class="today-strip">{"".join(columns)}</div>'
