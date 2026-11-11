"""กราฟของ Dashboard — สร้าง spec ของ Altair ครั้งเดียวต่อโครงกราฟแล้วแคช JSON ไว้

สร้างแค่ spec และตารางข้อมูล (ไม่เรียก ``st.``) เพื่อให้หน้าเว็บส่งเข้า ``st.vega_lite_chart``
โดยไม่ต้องรัน ``altair.to_dict()`` และตรวจ ``jsonschema`` ซ้ำทุกครั้งที่สคริปต์ rerun
"""

from functools import lru_cache
import json

import altair as alt
import pandas as pd

PRIMARY_BLUE = "#1d63dc"
ACCENT_ORANGE = "#eb6834"
Y_NUMBER_FORMAT = ",.2~f"
CHART_PADDING = {"left": 10, "right": 8, "top": 6, "bottom": 4}


def _polish(chart):
    """ปรับเส้นตาราง แกน และกรอบของกราฟทุกใบให้อ่านสะอาดตาและไม่ตัดสระบนของชื่อแกนภาษาไทย"""
    return (
        chart.properties(padding=CHART_PADDING)
        .configure_view(stroke="transparent")
        .configure_axis(
            labelColor="#64748b",
            titleColor="#475569",
            labelFontSize=11,
            titleFontSize=11,
            titleFontWeight=600,
            domainColor="#e2e8f0",
            tickColor="#e2e8f0",
            gridColor="#eef2f6",
            gridDash=[3, 3],
            labelPadding=6,
            titlePadding=10,
        )
        .configure_legend(
            labelColor="#334155",
            labelFontSize=11,
            symbolSize=70,
            columnPadding=14,
            padding=4,
        )
    )


def _spec_without_data(chart) -> str:
    """Validate Vega-Lite spec once via Altair, strip inline datasets, and return JSON."""
    spec = _polish(chart).to_dict()
    spec.pop("data", None)
    spec.pop("datasets", None)
    return json.dumps(spec, ensure_ascii=False)


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
              axis=alt.Axis(format="%H:%M", title=None, tickCount=8, grid=False))
    y = alt.Y("ค่า:Q", scale=alt.Scale(zero=False, padding=14),
              axis=alt.Axis(title=y_title, grid=True, format=Y_NUMBER_FORMAT))
    color = alt.Color("นักกีฬา:N", legend=alt.Legend(orient="top", title=None))
    detail = alt.Detail("athlete_id:N")
    line = alt.Chart(frame).mark_line(strokeWidth=2.0, strokeCap="round", strokeJoin="round").encode(
        x=x, y=y, color=color, detail=detail,
    )
    points = alt.Chart(frame.dropna(subset=["ค่า"])).mark_circle(size=44, opacity=0).encode(
        x=x, y=y, color=color, detail=detail,
        tooltip=["นักกีฬา", alt.Tooltip("เวลา:T", format="%H:%M"), alt.Tooltip("ค่า:Q", format=".0f")],
    )
    return _polish((line + points).properties(height=height))


@lru_cache(maxsize=64)
def _cached_intraday_spec_json(day_iso: str, y_title: str, height: int) -> str:
    start = pd.Timestamp(day_iso)
    end = start + pd.Timedelta(days=1)
    placeholder = pd.DataFrame({
        "athlete_id": pd.Series(dtype="int64"),
        "เวลา": pd.Series(dtype="datetime64[ns]"),
        "ค่า": pd.Series(dtype="float64"),
        "นักกีฬา": pd.Series(dtype="object"),
    })
    x = alt.X("เวลา:T", scale=alt.Scale(domain=[start.isoformat(), end.isoformat()]),
              axis=alt.Axis(format="%H:%M", title=None, tickCount=8, grid=False))
    y = alt.Y("ค่า:Q", scale=alt.Scale(zero=False, padding=14),
              axis=alt.Axis(title=y_title, grid=True, format=Y_NUMBER_FORMAT))
    color = alt.Color("นักกีฬา:N", legend=alt.Legend(orient="top", title=None))
    detail = alt.Detail("athlete_id:N")
    base = alt.Chart(placeholder)
    line = base.mark_line(strokeWidth=2.0, strokeCap="round", strokeJoin="round").encode(
        x=x, y=y, color=color, detail=detail,
    )
    points = (
        base.transform_filter("isValid(datum['ค่า'])")
        .mark_circle(size=44, opacity=0)
        .encode(
            x=x, y=y, color=color, detail=detail,
            tooltip=["นักกีฬา:N", alt.Tooltip("เวลา:T", format="%H:%M"), alt.Tooltip("ค่า:Q", format=".0f")],
        )
    )
    return _spec_without_data((line + points).properties(height=height))


def intraday_frame_and_spec(series, day, *, y_title, names=None, height=180):
    """คืน ``(frame, spec)`` สำหรับ ``st.vega_lite_chart`` โดยสร้าง spec แค่ครั้งแรก"""
    frame = series.copy()
    frame["นักกีฬา"] = frame["athlete_id"].map(names or {}).fillna(frame["athlete_id"].astype(str))
    spec = json.loads(_cached_intraday_spec_json(pd.Timestamp(day).date().isoformat(), y_title, int(height)))
    return frame, spec


@lru_cache(maxsize=64)
def _cached_single_line_spec_json(label: str, y_label: str, height: int) -> str:
    placeholder = pd.DataFrame({
        "วันที่": pd.Series(dtype="datetime64[ns]"),
        label: pd.Series(dtype="float64"),
    })
    x = alt.X("วันที่:T", axis=alt.Axis(title="", format="%d/%m", grid=False, labelAngle=0))
    y = alt.Y(f"{label}:Q", scale=alt.Scale(zero=False, padding=14),
              axis=alt.Axis(title=y_label, grid=True, format=Y_NUMBER_FORMAT))
    tooltip = [alt.Tooltip("วันที่:T", format="%d/%m/%Y"), alt.Tooltip(f"{label}:Q")]
    base = alt.Chart(placeholder)
    line = base.mark_line(
        color=PRIMARY_BLUE, strokeWidth=2.2, strokeCap="round", strokeJoin="round",
    ).encode(x=x, y=y, tooltip=tooltip)
    # วาดจุดจริงเพื่อให้วันที่ที่มีข้อมูลวันเดียวคั่นกลางระหว่างวันว่างยังมองเห็นบนจอ
    points = (
        base.transform_filter(f"isValid(datum[{json.dumps(label)}])")
        .mark_circle(color=PRIMARY_BLUE, size=34, opacity=0.9)
        .encode(x=x, y=y, tooltip=tooltip)
    )
    return _spec_without_data((line + points).properties(height=height))


@lru_cache(maxsize=64)
def _cached_multi_line_spec_json(labels: tuple[str, ...], y_label: str, height: int) -> str:
    placeholder = pd.DataFrame({
        "วันที่": pd.Series(dtype="datetime64[ns]"),
        "รายการ": pd.Series(dtype="object"),
        "ค่า": pd.Series(dtype="float64"),
    })
    x = alt.X("วันที่:T", axis=alt.Axis(title="", format="%d/%m", grid=False, labelAngle=0))
    y = alt.Y("ค่า:Q", scale=alt.Scale(zero=False, padding=14),
              axis=alt.Axis(title=y_label, grid=True, format=Y_NUMBER_FORMAT))
    color = alt.Color(
        "รายการ:N",
        scale=alt.Scale(domain=list(labels)),
        legend=alt.Legend(orient="bottom", title=None),
    )
    tooltip = [
        alt.Tooltip("วันที่:T", format="%d/%m/%Y"),
        alt.Tooltip("รายการ:N"),
        alt.Tooltip("ค่า:Q"),
    ]
    base = alt.Chart(placeholder)
    line = base.mark_line(strokeWidth=2.2, strokeCap="round", strokeJoin="round").encode(
        x=x, y=y, color=color, tooltip=tooltip,
    )
    points = (
        base.transform_filter("isValid(datum['ค่า'])")
        .mark_circle(size=34, opacity=0.9)
        .encode(x=x, y=y, color=color, tooltip=tooltip)
    )
    return _spec_without_data((line + points).properties(height=height))


def daily_line_frame_and_spec(daily, columns, labels, *, y_label="", height=220):
    """คืน ``(frame, spec)`` ของกราฟเส้นรายวัน (คงแถว NaN ไว้ให้เส้นขาดตรงวันที่ไม่มีข้อมูล)"""
    labels_tuple = tuple(labels)
    renamed = daily[["วันที่", *columns]].rename(columns=dict(zip(columns, labels_tuple, strict=True)))
    if len(labels_tuple) == 1:
        spec = json.loads(_cached_single_line_spec_json(labels_tuple[0], y_label, int(height)))
        return renamed, spec
    melted = renamed.melt(id_vars="วันที่", value_vars=list(labels_tuple),
                          var_name="รายการ", value_name="ค่า")
    spec = json.loads(_cached_multi_line_spec_json(labels_tuple, y_label, int(height)))
    return melted, spec


@lru_cache(maxsize=16)
def _cached_sleep_stage_bar_spec_json(
    labels: tuple[str, ...], colors: tuple[str, ...], y_label: str, height: int
) -> str:
    placeholder = pd.DataFrame({
        "วันที่": pd.Series(dtype="datetime64[ns]"),
        "ระยะ": pd.Series(dtype="object"),
        "ชั่วโมง": pd.Series(dtype="float64"),
        "ลำดับ": pd.Series(dtype="int64"),
    })
    chart = (
        alt.Chart(placeholder)
        .mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2)
        .encode(
            x=alt.X("วันที่:T", axis=alt.Axis(title="", format="%d/%m", grid=False, labelAngle=0)),
            y=alt.Y("ชั่วโมง:Q", axis=alt.Axis(title=y_label, grid=True, format=Y_NUMBER_FORMAT)),
            color=alt.Color(
                "ระยะ:N",
                scale=alt.Scale(domain=list(labels), range=list(colors)),
                legend=alt.Legend(orient="bottom", title=None),
            ),
            order=alt.Order("ลำดับ:Q"),
            tooltip=[
                alt.Tooltip("วันที่:T", format="%d/%m/%Y"),
                alt.Tooltip("ระยะ:N"),
                alt.Tooltip("ชั่วโมง:Q", format=".1f"),
            ],
        )
        .properties(height=height)
    )
    return _spec_without_data(chart)


def sleep_stage_bar_frame_and_spec(stages, *, labels, colors, y_label="ชั่วโมง", height=220):
    """คืน ``(frame, spec)`` ของกราฟแท่งซ้อนระยะการนอน"""
    labels_tuple = tuple(labels)
    colors_tuple = tuple(colors)
    order_map = {label: idx for idx, label in enumerate(labels_tuple)}
    melted = stages.melt(id_vars="วันที่", value_vars=list(labels_tuple),
                         var_name="ระยะ", value_name="ชั่วโมง")
    melted["ลำดับ"] = melted["ระยะ"].map(order_map)
    spec = json.loads(_cached_sleep_stage_bar_spec_json(labels_tuple, colors_tuple, y_label, int(height)))
    return melted, spec


@lru_cache(maxsize=16)
def _cached_weekly_bar_spec_json(x_col: str, y_col: str, y_title: str, height: int) -> str:
    placeholder = pd.DataFrame({
        x_col: pd.Series(dtype="object"),
        y_col: pd.Series(dtype="float64"),
    })
    chart = (
        alt.Chart(placeholder)
        .mark_bar(color=PRIMARY_BLUE, cornerRadiusTopLeft=5, cornerRadiusTopRight=5)
        .encode(
            x=alt.X(f"{x_col}:N", sort=None, axis=alt.Axis(title=None, labelAngle=0, grid=False)),
            y=alt.Y(f"{y_col}:Q", axis=alt.Axis(title=y_title, grid=True, format=Y_NUMBER_FORMAT)),
            tooltip=[alt.Tooltip(f"{x_col}:N"), alt.Tooltip(f"{y_col}:Q", format=".1f")],
        )
        .properties(height=height)
    )
    return _spec_without_data(chart)


def weekly_bar_spec(*, y_col: str, y_title: str, x_col: str = "สัปดาห์", height: int = 240) -> dict:
    """คืน spec ของกราฟแท่งรายสัปดาห์แบบมุมมน ป้ายแกน X แนวนอนอ่านตรงได้ทันที"""
    return json.loads(_cached_weekly_bar_spec_json(x_col, y_col, y_title, int(height)))


@lru_cache(maxsize=8)
def _cached_activity_load_bar_spec_json(height: int) -> str:
    placeholder = pd.DataFrame({
        "วันเวลา": pd.Series(dtype="datetime64[ns]"),
        "กิจกรรม": pd.Series(dtype="object"),
        "Training Load": pd.Series(dtype="float64"),
    })
    chart = (
        alt.Chart(placeholder)
        .mark_bar(color=PRIMARY_BLUE, cornerRadiusTopLeft=4, cornerRadiusTopRight=4, size=14)
        .encode(
            x=alt.X("วันเวลา:T", axis=alt.Axis(title=None, format="%d/%m", labelAngle=0, grid=False)),
            y=alt.Y("Training Load:Q", axis=alt.Axis(title="Training Load", grid=True, format=Y_NUMBER_FORMAT)),
            tooltip=[
                alt.Tooltip("วันเวลา:T", format="%d/%m/%Y %H:%M"),
                alt.Tooltip("กิจกรรม:N"),
                alt.Tooltip("Training Load:Q", format=".0f"),
            ],
        )
        .properties(height=height)
    )
    return _spec_without_data(chart)


def activity_load_bar_spec(*, height: int = 220) -> dict:
    """คืน spec ของกราฟ Training Load ต่อกิจกรรม"""
    return json.loads(_cached_activity_load_bar_spec_json(int(height)))


@lru_cache(maxsize=16)
def _cached_zone_bar_spec_json(
    zone_labels: tuple[str, ...], zone_colors: tuple[str, ...], height: int
) -> str:
    placeholder = pd.DataFrame({
        "สัปดาห์": pd.Series(dtype="object"),
        "โซน": pd.Series(dtype="object"),
        "นาที": pd.Series(dtype="float64"),
    })
    chart = (
        alt.Chart(placeholder)
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X("สัปดาห์:N", sort=None, axis=alt.Axis(title=None, labelAngle=0, grid=False)),
            y=alt.Y("sum(นาที):Q", axis=alt.Axis(title="นาที", grid=True, format=Y_NUMBER_FORMAT)),
            color=alt.Color(
                "โซน:N",
                scale=alt.Scale(domain=list(zone_labels), range=list(zone_colors)),
                legend=alt.Legend(orient="bottom", title=None),
            ),
            order=alt.Order("โซน:N"),
            tooltip=["สัปดาห์:N", "โซน:N", alt.Tooltip("นาที:Q", format=".0f")],
        )
        .properties(height=height)
    )
    return _spec_without_data(chart)


def zone_bar_spec(zone_labels, zone_colors, *, height=240) -> dict:
    """คืน spec ของกราฟแท่งซ้อนเวลาในโซน HR รายสัปดาห์"""
    return json.loads(_cached_zone_bar_spec_json(tuple(zone_labels), tuple(zone_colors), int(height)))


@lru_cache(maxsize=8)
def _cached_session_zone_bar_spec_json(
    zone_labels: tuple[str, ...], zone_colors: tuple[str, ...], height: int
) -> str:
    placeholder = pd.DataFrame({
        "โซน": pd.Series(dtype="object"),
        "นาที": pd.Series(dtype="float64"),
    })
    chart = (
        alt.Chart(placeholder)
        .mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5)
        .encode(
            x=alt.X("โซน:N", sort=None, axis=alt.Axis(title=None, labelAngle=0, grid=False)),
            y=alt.Y("นาที:Q", axis=alt.Axis(title="นาที", grid=True, format=Y_NUMBER_FORMAT)),
            color=alt.Color(
                "โซน:N",
                scale=alt.Scale(domain=list(zone_labels), range=list(zone_colors)),
                legend=None,
            ),
            tooltip=["โซน:N", alt.Tooltip("นาที:Q", format=".1f")],
        )
        .properties(height=height)
    )
    return _spec_without_data(chart)


def session_zone_bar_spec(zone_labels, zone_colors, *, height=220) -> dict:
    """คืน spec ของกราฟเวลาในโซน HR ของเซสชันเดียว (แกน X แนวนอน + ไล่เฉดโซน Z1-Z5)"""
    return json.loads(_cached_session_zone_bar_spec_json(tuple(zone_labels), tuple(zone_colors), int(height)))


@lru_cache(maxsize=8)
def _cached_session_lap_hr_spec_json(height: int) -> str:
    placeholder = pd.DataFrame({
        "Lap": pd.Series(dtype="object"),
        "รายการ": pd.Series(dtype="object"),
        "bpm": pd.Series(dtype="float64"),
    })
    labels = ["HR เฉลี่ย", "HR สูงสุด"]
    colors = [PRIMARY_BLUE, ACCENT_ORANGE]
    x = alt.X("Lap:N", sort=None, axis=alt.Axis(title="Lap", labelAngle=0, grid=False))
    y = alt.Y("bpm:Q", scale=alt.Scale(zero=False, padding=14),
              axis=alt.Axis(title="bpm", grid=True, format=Y_NUMBER_FORMAT))
    color = alt.Color(
        "รายการ:N",
        scale=alt.Scale(domain=labels, range=colors),
        legend=alt.Legend(orient="bottom", title=None),
    )
    tooltip = ["Lap:N", "รายการ:N", alt.Tooltip("bpm:Q", format=".0f")]
    base = alt.Chart(placeholder)
    line = base.mark_line(strokeWidth=2.2, strokeCap="round", strokeJoin="round").encode(
        x=x, y=y, color=color, tooltip=tooltip,
    )
    points = (
        base.transform_filter("isValid(datum['bpm'])")
        .mark_circle(size=42, opacity=0.95)
        .encode(x=x, y=y, color=color, tooltip=tooltip)
    )
    return _spec_without_data((line + points).properties(height=height))


def session_lap_hr_spec(*, height=220) -> dict:
    """คืน spec ของกราฟ HR เฉลี่ย/สูงสุดต่อ lap โดยคงลำดับเลข lap จริงและป้ายแนวนอน"""
    return json.loads(_cached_session_lap_hr_spec_json(int(height)))
