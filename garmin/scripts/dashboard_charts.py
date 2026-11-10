"""กราฟของ Dashboard — สร้าง spec ของ Altair ครั้งเดียวต่อโครงกราฟแล้วแคช JSON ไว้

สร้างแค่ spec และตารางข้อมูล (ไม่เรียก ``st.``) เพื่อให้หน้าเว็บส่งเข้า ``st.vega_lite_chart``
โดยไม่ต้องรัน ``altair.to_dict()`` และตรวจ ``jsonschema`` ซ้ำทุกครั้งที่สคริปต์ rerun
"""

from functools import lru_cache
import json

import altair as alt
import pandas as pd


def _spec_without_data(chart) -> str:
    """Validate Vega-Lite spec once via Altair, strip inline datasets, and return JSON."""
    spec = chart.to_dict()
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
              axis=alt.Axis(format="%H:%M", title=None, tickCount=8))
    y = alt.Y("ค่า:Q", title=y_title)
    color = alt.Color("นักกีฬา:N", legend=alt.Legend(orient="top", title=None))
    detail = alt.Detail("athlete_id:N")
    line = alt.Chart(frame).mark_line(strokeWidth=1.6).encode(
        x=x, y=y, color=color, detail=detail,
    )
    points = alt.Chart(frame.dropna(subset=["ค่า"])).mark_circle(size=40, opacity=0).encode(
        x=x, y=y, color=color, detail=detail,
        tooltip=["นักกีฬา", alt.Tooltip("เวลา:T", format="%H:%M"), alt.Tooltip("ค่า:Q", format=".0f")],
    )
    return (line + points).properties(height=height)


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
              axis=alt.Axis(format="%H:%M", title=None, tickCount=8))
    y = alt.Y("ค่า:Q", title=y_title)
    color = alt.Color("นักกีฬา:N", legend=alt.Legend(orient="top", title=None))
    detail = alt.Detail("athlete_id:N")
    base = alt.Chart(placeholder)
    line = base.mark_line(strokeWidth=1.6).encode(x=x, y=y, color=color, detail=detail)
    points = (
        base.transform_filter("isValid(datum['ค่า'])")
        .mark_circle(size=40, opacity=0)
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
    x = alt.X("วันที่:T", axis=alt.Axis(title="", grid=False))
    y = alt.Y(f"{label}:Q", axis=alt.Axis(title=y_label, grid=True))
    tooltip = [alt.Tooltip("วันที่:T", format="%d/%m/%Y"), alt.Tooltip(f"{label}:Q")]
    base = alt.Chart(placeholder)
    line = base.mark_line().encode(x=x, y=y, tooltip=tooltip)
    points = (
        base.transform_filter(f"isValid(datum[{json.dumps(label)}])")
        .mark_circle(size=45, opacity=0)
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
    x = alt.X("วันที่:T", axis=alt.Axis(title="", grid=False))
    y = alt.Y("ค่า:Q", axis=alt.Axis(title=y_label, grid=True))
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
    line = base.mark_line().encode(x=x, y=y, color=color, tooltip=tooltip)
    points = (
        base.transform_filter("isValid(datum['ค่า'])")
        .mark_circle(size=45, opacity=0)
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
        .mark_bar()
        .encode(
            x=alt.X("วันที่:T", axis=alt.Axis(title="", grid=False)),
            y=alt.Y("ชั่วโมง:Q", axis=alt.Axis(title=y_label, grid=True)),
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
        .mark_bar()
        .encode(
            x=alt.X("สัปดาห์:N", sort=None, title=None),
            y=alt.Y("sum(นาที):Q", title="นาที"),
            color=alt.Color(
                "โซน:N",
                scale=alt.Scale(domain=list(zone_labels), range=list(zone_colors)),
                legend=alt.Legend(orient="bottom", title=None),
            ),
            order=alt.Order("โซน:N"),
            tooltip=["สัปดาห์:N", "โซน:N", "นาที:Q"],
        )
        .properties(height=height)
    )
    return _spec_without_data(chart)


def zone_bar_spec(zone_labels, zone_colors, *, height=240) -> dict:
    """คืน spec ของกราฟแท่งซ้อนเวลาในโซน HR รายสัปดาห์"""
    return json.loads(_cached_zone_bar_spec_json(tuple(zone_labels), tuple(zone_colors), int(height)))


