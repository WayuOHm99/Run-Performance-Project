"""กราฟของ Dashboard — สร้าง spec ของ Altair ครั้งเดียวต่อโครงกราฟแล้วแคช JSON ไว้

สร้างแค่ spec และตารางข้อมูล (ไม่เรียก ``st.``) เพื่อให้หน้าเว็บส่งเข้า ``st.vega_lite_chart``
โดยไม่ต้องรัน ``altair.to_dict()`` และตรวจ ``jsonschema`` ซ้ำทุกครั้งที่สคริปต์ rerun
"""

import json
from functools import lru_cache

import altair as alt
import pandas as pd

PRIMARY_BLUE = "#155eef"
ACCENT_ORANGE = "#d95d24"
ACCENT_TEAL = "#0d9488"
DEEP_NAVY = "#0b2545"
SERIES_PALETTE = (PRIMARY_BLUE, ACCENT_ORANGE, ACCENT_TEAL, DEEP_NAVY)
Y_NUMBER_FORMAT = ",.2~f"
CHART_FONT = "IBM Plex Sans Thai, -apple-system, BlinkMacSystemFont, sans-serif"
CHART_PADDING = {"left": 10, "right": 12, "top": 8, "bottom": 6}


def _polish(chart):
    """จัดฟอนต์ เส้นตาราง และแกนแบบ Editorial สะอาดตา ไม่ตีกรอบทึบ และไม่ตัดสระภาษาไทย"""
    return (
        chart.properties(padding=CHART_PADDING)
        .configure(font=CHART_FONT)
        .configure_view(stroke="transparent")
        .configure_axis(
            labelColor="#475467",
            titleColor="#344054",
            labelFontSize=11.5,
            titleFontSize=11.5,
            titleFontWeight=600,
            gridColor="#edf0f5",
            labelPadding=6,
            titlePadding=10,
        )
        .configure_axisX(
            domainColor="#e4e7ec",
            tickColor="#d0d5dd",
            tickSize=4,
            grid=False,
        )
        .configure_axisY(
            domain=False,
            ticks=False,
            grid=True,
        )
        .configure_legend(
            labelColor="#344054",
            labelFontSize=11.5,
            symbolType="circle",
            symbolSize=76,
            columnPadding=16,
            padding=2,
            offset=8,
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
    show_legend = names is None or len(names) > 1
    x = alt.X(
        "เวลา:T",
        scale=alt.Scale(domain=[start.isoformat(), end.isoformat()]),
        axis=alt.Axis(format="%H:%M", title=None, tickCount=8, labelAngle=0, grid=False),
    )
    y = alt.Y(
        "ค่า:Q",
        scale=alt.Scale(zero=False, nice=True, padding=14),
        axis=alt.Axis(title=y_title, grid=True, format=Y_NUMBER_FORMAT),
    )
    color = alt.Color(
        "นักกีฬา:N",
        scale=alt.Scale(range=list(SERIES_PALETTE)),
        legend=alt.Legend(orient="top", title=None) if show_legend else None,
    )
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
def _cached_intraday_spec_json(day_iso: str, y_title: str, height: int, show_legend: bool) -> str:
    start = pd.Timestamp(day_iso)
    end = start + pd.Timedelta(days=1)
    placeholder = pd.DataFrame({
        "athlete_id": pd.Series(dtype="int64"),
        "เวลา": pd.Series(dtype="datetime64[ns]"),
        "ค่า": pd.Series(dtype="float64"),
        "นักกีฬา": pd.Series(dtype="object"),
    })
    x = alt.X(
        "เวลา:T",
        scale=alt.Scale(domain=[start.isoformat(), end.isoformat()]),
        axis=alt.Axis(format="%H:%M", title=None, tickCount=8, labelAngle=0, grid=False),
    )
    y = alt.Y(
        "ค่า:Q",
        scale=alt.Scale(zero=False, nice=True, padding=14),
        axis=alt.Axis(title=y_title, grid=True, format=Y_NUMBER_FORMAT),
    )
    color = alt.Color(
        "นักกีฬา:N",
        scale=alt.Scale(range=list(SERIES_PALETTE)),
        legend=alt.Legend(orient="top", title=None) if show_legend else None,
    )
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
            tooltip=[
                alt.Tooltip("นักกีฬา:N"),
                alt.Tooltip("เวลา:T", format="%H:%M", title="เวลา"),
                alt.Tooltip("ค่า:Q", format=".0f", title=y_title or "ค่า"),
            ],
        )
    )
    return _spec_without_data((line + points).properties(height=height))


def intraday_frame_and_spec(series, day, *, y_title, names=None, height=180):
    """คืน ``(frame, spec)`` สำหรับ ``st.vega_lite_chart`` โดยสร้าง spec แค่ครั้งแรก"""
    frame = series.copy()
    frame["นักกีฬา"] = frame["athlete_id"].map(names or {}).fillna(frame["athlete_id"].astype(str))
    show_legend = names is None or len(names) > 1
    spec = json.loads(
        _cached_intraday_spec_json(pd.Timestamp(day).date().isoformat(), y_title, int(height), show_legend)
    )
    return frame, spec


@lru_cache(maxsize=64)
def _cached_single_line_spec_json(
    label: str,
    y_label: str,
    height: int,
    point_size: int,
    formatted_col: str | None,
    clamp_zero_min: bool,
    y_mmss: bool,
) -> str:
    cols = {
        "วันที่": pd.Series(dtype="datetime64[ns]"),
        label: pd.Series(dtype="float64"),
    }
    if formatted_col:
        cols[formatted_col] = pd.Series(dtype="object")
    placeholder = pd.DataFrame(cols)
    x = alt.X(
        "วันที่:T",
        axis=alt.Axis(title="", format="%d/%m", tickCount=6, labelOverlap="parity", grid=False, labelAngle=0),
    )
    scale_kwargs = {"zero": False, "nice": not y_mmss, "padding": 14}
    if clamp_zero_min:
        scale_kwargs["domainMin"] = 0
    if y_mmss:
        mmss_expr = (
            "floor(round(datum.value) / 60) + ':' + "
            "((round(datum.value) % 60) < 10 ? '0' : '') + (round(datum.value) % 60)"
        )
        y_axis = alt.Axis(title=y_label, grid=True, tickCount=5, labelExpr=mmss_expr)
    else:
        y_axis = alt.Axis(title=y_label, grid=True, format=Y_NUMBER_FORMAT)
    y = alt.Y(f"{label}:Q", scale=alt.Scale(**scale_kwargs), axis=y_axis)
    if formatted_col:
        tooltip = [
            alt.Tooltip("วันที่:T", format="%d/%m/%Y", title="วันที่"),
            alt.Tooltip(f"{formatted_col}:N", title=label),
        ]
    else:
        tooltip = [
            alt.Tooltip("วันที่:T", format="%d/%m/%Y", title="วันที่"),
            alt.Tooltip(f"{label}:Q", format=",.1~f", title=f"{label}" + (f" ({y_label})" if y_label else "")),
        ]
    base = alt.Chart(placeholder)
    # ไม่ซ้อน mark_area เพราะ Vega-Lite บังคับฐานแกน Y กลับไปที่ 0 ทำให้กราฟ RHR/5K/Sleep แบนติดเพดาน
    line = base.mark_line(
        color=PRIMARY_BLUE, strokeWidth=2.3, strokeCap="round", strokeJoin="round",
    ).encode(x=x, y=y, tooltip=tooltip)
    # วาดจุดจริงเพื่อให้วันที่ที่มีข้อมูลวันเดียวคั่นกลางระหว่างวันว่างยังมองเห็นบนจอ
    points = (
        base.transform_filter(f"isValid(datum[{json.dumps(label)}])")
        .mark_circle(color=PRIMARY_BLUE, size=point_size, opacity=0.95, stroke="#ffffff", strokeWidth=1.3)
        .encode(x=x, y=y, tooltip=tooltip)
    )
    return _spec_without_data((line + points).properties(height=height))


@lru_cache(maxsize=64)
def _cached_multi_line_spec_json(
    labels: tuple[str, ...], y_label: str, height: int, point_size: int, clamp_zero_min: bool
) -> str:
    placeholder = pd.DataFrame({
        "วันที่": pd.Series(dtype="datetime64[ns]"),
        "รายการ": pd.Series(dtype="object"),
        "ค่า": pd.Series(dtype="float64"),
    })
    palette = list(SERIES_PALETTE[: max(1, len(labels))])
    x = alt.X(
        "วันที่:T",
        axis=alt.Axis(title="", format="%d/%m", tickCount=6, labelOverlap="parity", grid=False, labelAngle=0),
    )
    scale_kwargs = {"zero": False, "nice": True, "padding": 14}
    if clamp_zero_min:
        scale_kwargs["domainMin"] = 0
    y = alt.Y(
        "ค่า:Q",
        scale=alt.Scale(**scale_kwargs),
        axis=alt.Axis(title=y_label, grid=True, format=Y_NUMBER_FORMAT),
    )
    color = alt.Color(
        "รายการ:N",
        scale=alt.Scale(domain=list(labels), range=palette),
        legend=alt.Legend(orient="top", title=None),
    )
    tooltip = [
        alt.Tooltip("วันที่:T", format="%d/%m/%Y", title="วันที่"),
        alt.Tooltip("รายการ:N", title="รายการ"),
        alt.Tooltip("ค่า:Q", format=",.1~f", title=f"ค่า ({y_label})" if y_label else "ค่า"),
    ]
    base = alt.Chart(placeholder)
    line = base.mark_line(strokeWidth=2.2, strokeCap="round", strokeJoin="round").encode(
        x=x, y=y, color=color, tooltip=tooltip,
    )
    points = (
        base.transform_filter("isValid(datum['ค่า'])")
        .mark_circle(size=point_size, opacity=0.95, stroke="#ffffff", strokeWidth=1.2)
        .encode(x=x, y=y, color=color, tooltip=tooltip)
    )
    return _spec_without_data((line + points).properties(height=height))


def daily_line_frame_and_spec(
    daily, columns, labels, *, y_label="", height=220, formatted_col=None, y_mmss=False
):
    """คืน ``(frame, spec)`` ของกราฟเส้นรายวัน (คงแถว NaN ไว้ให้เส้นขาดตรงวันที่ไม่มีข้อมูล)"""
    labels_tuple = tuple(labels)
    n_days = len(daily)
    point_size = 36 if n_days <= 14 else (22 if n_days <= 45 else 10)
    numeric_mins = [
        float(s.min())
        for col in columns
        if col in daily.columns and not (s := pd.to_numeric(daily[col], errors="coerce").dropna()).empty
    ]
    clamp_zero_min = bool(numeric_mins) and min(numeric_mins) >= 0 and min(numeric_mins) <= 6
    keep_cols = ["วันที่", *columns]
    if formatted_col and formatted_col in daily.columns:
        keep_cols.append(formatted_col)
    else:
        formatted_col = None
    renamed = daily[keep_cols].rename(columns=dict(zip(columns, labels_tuple, strict=True)))
    if len(labels_tuple) == 1:
        spec = json.loads(
            _cached_single_line_spec_json(
                labels_tuple[0], y_label, int(height), point_size, formatted_col, clamp_zero_min, bool(y_mmss)
            )
        )
        return renamed, spec
    melted = renamed.melt(id_vars="วันที่", value_vars=list(labels_tuple),
                          var_name="รายการ", value_name="ค่า")
    spec = json.loads(
        _cached_multi_line_spec_json(labels_tuple, y_label, int(height), point_size, clamp_zero_min)
    )
    return melted, spec


@lru_cache(maxsize=16)
def _cached_sleep_stage_bar_spec_json(
    labels: tuple[str, ...], colors: tuple[str, ...], y_label: str, height: int, ordinal_axis: bool
) -> str:
    if ordinal_axis:
        placeholder = pd.DataFrame({
            "วัน": pd.Series(dtype="object"),
            "วันที่เต็ม": pd.Series(dtype="object"),
            "ระยะ": pd.Series(dtype="object"),
            "ชั่วโมง": pd.Series(dtype="float64"),
            "ลำดับ": pd.Series(dtype="int64"),
        })
        x_enc = alt.X(
            "วัน:N",
            sort=None,
            scale=alt.Scale(paddingInner=0.22, paddingOuter=0.08),
            axis=alt.Axis(title="", labelAngle=0, labelOverlap="greedy", grid=False),
        )
        date_tip = alt.Tooltip("วันที่เต็ม:N", title="วันที่")
    else:
        placeholder = pd.DataFrame({
            "วันที่": pd.Series(dtype="datetime64[ns]"),
            "ระยะ": pd.Series(dtype="object"),
            "ชั่วโมง": pd.Series(dtype="float64"),
            "ลำดับ": pd.Series(dtype="int64"),
        })
        x_enc = alt.X(
            "วันที่:T",
            axis=alt.Axis(title="", format="%d/%m/%y", tickCount=7, labelOverlap="parity", grid=False, labelAngle=0),
        )
        date_tip = alt.Tooltip("วันที่:T", format="%d/%m/%Y", title="วันที่")

    chart = (
        alt.Chart(placeholder)
        .mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2)
        .encode(
            x=x_enc,
            y=alt.Y("ชั่วโมง:Q", axis=alt.Axis(title=y_label, grid=True, format=Y_NUMBER_FORMAT)),
            color=alt.Color(
                "ระยะ:N",
                scale=alt.Scale(domain=list(labels), range=list(colors)),
                legend=alt.Legend(orient="top", title=None),
            ),
            order=alt.Order("ลำดับ:Q"),
            tooltip=[
                date_tip,
                alt.Tooltip("ระยะ:N", title="ระยะการนอน"),
                alt.Tooltip("ชั่วโมง:Q", format=".1f", title="ระยะเวลา (ชม.)"),
            ],
        )
        .properties(height=height)
    )
    return _spec_without_data(chart)


def sleep_stage_bar_frame_and_spec(stages, *, labels, colors, y_label="ชั่วโมง", height=220):
    """คืน ``(frame, spec)`` ของกราฟแท่งซ้อนระยะการนอน โดยปรับความกว้างแท่งให้อ่านออกชัดเจน"""
    labels_tuple = tuple(labels)
    colors_tuple = tuple(colors)
    order_map = {label: idx for idx, label in enumerate(labels_tuple)}
    ordinal_axis = len(stages) <= 100
    work = stages.copy()
    dt = pd.to_datetime(work["วันที่"])
    if ordinal_axis:
        fmt = "%d/%m/%y" if dt.dt.year.nunique() > 1 else "%d/%m"
        work["วัน"] = dt.dt.strftime(fmt)
        work["วันที่เต็ม"] = dt.dt.strftime("%d/%m/%Y")
        melted = work.melt(
            id_vars=["วัน", "วันที่เต็ม"], value_vars=list(labels_tuple),
            var_name="ระยะ", value_name="ชั่วโมง",
        )
    else:
        melted = work.melt(
            id_vars="วันที่", value_vars=list(labels_tuple),
            var_name="ระยะ", value_name="ชั่วโมง",
        )
    melted["ลำดับ"] = melted["ระยะ"].map(order_map)
    spec = json.loads(
        _cached_sleep_stage_bar_spec_json(labels_tuple, colors_tuple, y_label, int(height), ordinal_axis)
    )
    return melted, spec


@lru_cache(maxsize=16)
def _cached_weekly_bar_spec_json(x_col: str, y_col: str, y_title: str, height: int) -> str:
    placeholder = pd.DataFrame({
        x_col: pd.Series(dtype="object"),
        y_col: pd.Series(dtype="float64"),
    })
    chart = (
        alt.Chart(placeholder)
        .mark_bar(color=PRIMARY_BLUE, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X(
                f"{x_col}:N",
                sort=None,
                scale=alt.Scale(paddingInner=0.28, paddingOuter=0.14),
                axis=alt.Axis(title=None, labelAngle=0, labelOverlap="greedy", grid=False),
            ),
            y=alt.Y(f"{y_col}:Q", axis=alt.Axis(title=y_title, grid=True, format=Y_NUMBER_FORMAT)),
            tooltip=[
                alt.Tooltip(f"{x_col}:N", title="สัปดาห์เริ่ม จ."),
                alt.Tooltip(f"{y_col}:Q", format=".1f", title=y_col),
            ],
        )
        .properties(height=height)
    )
    return _spec_without_data(chart)


def weekly_bar_spec(*, y_col: str, y_title: str, x_col: str = "สัปดาห์", height: int = 240) -> dict:
    """คืน spec ของกราฟแท่งรายสัปดาห์แบบมุมมน ป้ายแกน X แนวนอนไม่ชนกันแม้เลือกหลายเดือน"""
    return json.loads(_cached_weekly_bar_spec_json(x_col, y_col, y_title, int(height)))


@lru_cache(maxsize=8)
def _cached_activity_load_bar_spec_json(height: int) -> str:
    placeholder = pd.DataFrame({
        "รหัสเวลา": pd.Series(dtype="object"),
        "วันเวลาแสดง": pd.Series(dtype="object"),
        "กิจกรรม": pd.Series(dtype="object"),
        "Training Load": pd.Series(dtype="float64"),
    })
    chart = (
        alt.Chart(placeholder)
        .mark_bar(color=PRIMARY_BLUE, cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X(
                "รหัสเวลา:N",
                sort=None,
                scale=alt.Scale(paddingInner=0.24, paddingOuter=0.1),
                axis=alt.Axis(
                    title=None,
                    labelAngle=0,
                    labelOverlap="greedy",
                    labelExpr="slice(datum.label, 0, 5)",
                    grid=False,
                ),
            ),
            y=alt.Y("Training Load:Q", axis=alt.Axis(title="Training Load", grid=True, format=Y_NUMBER_FORMAT)),
            tooltip=[
                alt.Tooltip("วันเวลาแสดง:N", title="วันเวลา"),
                alt.Tooltip("กิจกรรม:N", title="กิจกรรม"),
                alt.Tooltip("Training Load:Q", format=".0f", title="Training Load"),
            ],
        )
        .properties(height=height)
    )
    return _spec_without_data(chart)


def activity_load_bar_spec(*, height: int = 220) -> dict:
    """คืน spec ของกราฟ Training Load ต่อกิจกรรม เรียงตามลำดับเวลาโดยไม่ทับกันเมื่อซ้อมวันละหลายรอบ"""
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
            x=alt.X(
                "สัปดาห์:N",
                sort=None,
                scale=alt.Scale(paddingInner=0.28, paddingOuter=0.14),
                axis=alt.Axis(title=None, labelAngle=0, labelOverlap="greedy", grid=False),
            ),
            y=alt.Y("sum(นาที):Q", axis=alt.Axis(title="นาที", grid=True, format=Y_NUMBER_FORMAT)),
            color=alt.Color(
                "โซน:N",
                scale=alt.Scale(domain=list(zone_labels), range=list(zone_colors)),
                legend=alt.Legend(orient="top", title=None),
            ),
            order=alt.Order("โซน:N"),
            tooltip=[
                alt.Tooltip("สัปดาห์:N", title="สัปดาห์เริ่ม จ."),
                alt.Tooltip("โซน:N", title="โซนชีพจร"),
                alt.Tooltip("นาที:Q", format=".0f", title="เวลา (นาที)"),
            ],
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
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X(
                "โซน:N",
                sort=None,
                scale=alt.Scale(paddingInner=0.3, paddingOuter=0.16),
                axis=alt.Axis(title=None, labelAngle=0, grid=False),
            ),
            y=alt.Y("นาที:Q", axis=alt.Axis(title="นาที", grid=True, format=Y_NUMBER_FORMAT)),
            color=alt.Color(
                "โซน:N",
                scale=alt.Scale(domain=list(zone_labels), range=list(zone_colors)),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("โซน:N", title="โซนชีพจร"),
                alt.Tooltip("นาที:Q", format=".1f", title="เวลา (นาที)"),
            ],
        )
        .properties(height=height)
    )
    return _spec_without_data(chart)


def session_zone_bar_spec(zone_labels, zone_colors, *, height=220) -> dict:
    """คืน spec ของกราฟเวลาในโซน HR ของเซสชันเดียว (แกน X แนวนอน + ไล่เฉดโซน Z1-Z5)"""
    return json.loads(_cached_session_zone_bar_spec_json(tuple(zone_labels), tuple(zone_colors), int(height)))


@lru_cache(maxsize=8)
def _cached_session_lap_hr_spec_json(height: int, extra_tips: tuple[str, ...]) -> str:
    cols = {
        "Lap": pd.Series(dtype="object"),
        "รายการ": pd.Series(dtype="object"),
        "bpm": pd.Series(dtype="float64"),
    }
    for extra in extra_tips:
        cols[extra] = pd.Series(dtype="object")
    placeholder = pd.DataFrame(cols)
    labels = ["HR เฉลี่ย", "HR สูงสุด"]
    colors = [PRIMARY_BLUE, ACCENT_ORANGE]
    x = alt.X(
        "Lap:N",
        sort=None,
        axis=alt.Axis(title="รอบที่ (Lap)", labelAngle=0, labelOverlap="greedy", grid=False),
    )
    y = alt.Y(
        "bpm:Q",
        scale=alt.Scale(zero=False, nice=True, padding=14),
        axis=alt.Axis(title="bpm", grid=True, format=Y_NUMBER_FORMAT),
    )
    color = alt.Color(
        "รายการ:N",
        scale=alt.Scale(domain=labels, range=colors),
        legend=alt.Legend(orient="top", title=None),
    )
    tooltip = [
        alt.Tooltip("Lap:N", title="Lap"),
        alt.Tooltip("รายการ:N", title="ค่า"),
        alt.Tooltip("bpm:Q", format=".0f", title="ชีพจร (bpm)"),
        *[alt.Tooltip(f"{extra}:N", title=extra) for extra in extra_tips],
    ]
    base = alt.Chart(placeholder)
    line = base.mark_line(strokeWidth=2.2, strokeCap="round", strokeJoin="round").encode(
        x=x, y=y, color=color, tooltip=tooltip,
    )
    points = (
        base.transform_filter("isValid(datum['bpm'])")
        .mark_circle(size=34, opacity=0.95, stroke="#ffffff", strokeWidth=1.2)
        .encode(x=x, y=y, color=color, tooltip=tooltip)
    )
    return _spec_without_data((line + points).properties(height=height))


def session_lap_hr_spec(*, height=220, extra_tips: tuple[str, ...] = ()) -> dict:
    """คืน spec ของกราฟ HR เฉลี่ย/สูงสุดต่อ lap โดยคงลำดับเลข lap จริงและไม่ให้เลขซ้อนทับกัน"""
    return json.loads(_cached_session_lap_hr_spec_json(int(height), tuple(extra_tips)))
