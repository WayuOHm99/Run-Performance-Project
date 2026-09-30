"""กราฟระหว่างวัน — แกนเวลา 00:00–24:00 ของวันนั้นเสมอ เพื่อให้เทียบกันได้ตรงช่วงเวลา

สร้างแค่ spec ของ altair (ไม่เรียก ``st.``) หน้าไหนจะวาดก็ส่งเข้า ``st.altair_chart``
"""

import altair as alt
import pandas as pd


def intraday_chart(series, day, *, y_title, names=None, height=180):
    """เส้นระหว่างวันของหนึ่ง metric — หลายคนได้ในกราฟเดียว (สีตามคน)

    ``series`` มาจาก ``intraday_series`` (มีแถว NaN ตรงช่วงข้อมูลขาด เส้นจึงขาดตรงนั้น)
    จุดโปร่งใสบนเส้นมีไว้ให้แตะ/ชี้ดูค่าได้ทั้งบนมือถือและคอม ไม่พึ่ง hover อย่างเดียว
    """
    start = pd.Timestamp(day)
    end = start + pd.Timedelta(days=1)
    frame = series.copy()
    frame["นักกีฬา"] = frame["athlete_id"].map(names or {}).fillna(frame["athlete_id"].astype(str))
    x = alt.X("เวลา:T", scale=alt.Scale(domain=[start.isoformat(), end.isoformat()]),
              axis=alt.Axis(format="%H:%M", title=None, tickCount=8))
    y = alt.Y("ค่า:Q", title=y_title)
    color = alt.Color("นักกีฬา:N", legend=alt.Legend(orient="top", title=None))
    line = alt.Chart(frame).mark_line(strokeWidth=1.6).encode(x=x, y=y, color=color)
    points = alt.Chart(frame.dropna(subset=["ค่า"])).mark_circle(size=40, opacity=0).encode(
        x=x, y=y, color=color,
        tooltip=["นักกีฬา", alt.Tooltip("เวลา:T", format="%H:%M"), alt.Tooltip("ค่า:Q", format=".0f")],
    )
    return (line + points).properties(height=height)

