"""การจัดรูปค่าของ Dashboard แบบ Garmin-only (30 ก.ย. 69)

ทุกฟังก์ชันใน ``dashboard_domain.py`` ต้องทำแค่ เปลี่ยนรูปแบบ / เลือกค่าล่าสุด /
บวกตรง ๆ เทสชุดนี้ล็อกบทเรียนที่ยังใช้ได้จากชุดเก่า (ค่าล่าสุดรายช่อง, วันไทย,
วันที่ขาดต้องเป็นช่องว่าง, ป้าย sync ของ 3 ก.ย. 69) และพฤติกรรมของตัวช่วยใหม่
"""

import datetime
import sys
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dashboard_modules import HELPERS  # noqa: E402


class LatestPerFieldTests(unittest.TestCase):
    def test_partial_latest_row_does_not_hide_yesterdays_sleep_and_hrv(self):
        frame = pd.DataFrame({
            "calendar_date": ["2026-08-08", "2026-08-09"],
            "fetched_at": ["2026-08-08T04:00:00Z", "2026-08-09T04:00:00Z"],
            "sleep_score": [57, None],
            "hrv_last_night": [82, None],
            "bb_most_recent": [48, 93],
        })

        sleep = HELPERS["latest_field"](frame, "sleep_score")
        hrv = HELPERS["latest_field"](frame, "hrv_last_night")
        battery = HELPERS["latest_field"](frame, "bb_most_recent")

        self.assertEqual((sleep["value"], sleep["date"]), (57, date(2026, 8, 8)))
        self.assertEqual((hrv["value"], hrv["date"]), (82, date(2026, 8, 8)))
        self.assertEqual((battery["value"], battery["date"]), (93, date(2026, 8, 9)))

    def test_readiness_uses_source_timestamp_within_the_same_calendar_date(self):
        frame = pd.DataFrame({
            "calendar_date": ["2026-08-09", "2026-08-09"],
            "training_readiness": [32, 78],
            "readiness_timestamp_local": ["2026-08-09T08:00:00+07:00",
                                          "2026-08-09T11:30:00+07:00"],
            "fetched_at": ["2026-08-09T01:05:00Z", "2026-08-09T04:35:00Z"],
        })

        latest = HELPERS["latest_field"](
            frame, "training_readiness",
            timestamp_columns=("readiness_timestamp_local", "readiness_timestamp_utc"))

        self.assertEqual(latest["value"], 78)
        self.assertIn("11:30", HELPERS["readiness_when"](latest, date(2026, 8, 9)))



class SelectedDayTests(unittest.TestCase):
    """หน้าแรกยึดวันที่เลือก — ค่าทุกช่องบนการ์ดต้องมาจากแถวของวันนั้นแถวเดียว"""

    frame = pd.DataFrame({
        "calendar_date": ["2026-09-28", "2026-09-29", "2026-09-30"],
        "sleep_score": [70, 75, None],
        "bb_most_recent": [30, 12, 65],
        "body_battery_high": [90, 88, 70],
    })

    def test_the_card_uses_only_the_selected_days_row(self):
        row = HELPERS["day_row"](self.frame, date(2026, 9, 30))
        self.assertIsNone(HELPERS["value_of"](row, "sleep_score"))   # ไม่ยืมของเมื่อวานมา
        self.assertEqual(HELPERS["value_of"](row, "bb_most_recent"), 65)

    def test_yesterdays_high_never_stands_in_for_todays_latest_body_battery(self):
        # ข้อบกพร่อง 4.5: เดิมถ้าวันนี้ไม่มีค่าล่าสุด โค้ดเอาสูงสุดของเมื่อวานมาแสดงแทน
        frame = self.frame.assign(bb_most_recent=[30, 12, None])
        row = HELPERS["day_row"](frame, date(2026, 9, 30))
        self.assertIsNone(HELPERS["value_of"](row, "bb_most_recent"))

    def test_a_missing_value_is_offered_separately_with_its_own_date(self):
        previous = HELPERS["last_before"](self.frame, "sleep_score", date(2026, 9, 30))
        self.assertEqual((previous["value"], previous["date"]), (75, date(2026, 9, 29)))

    def test_day_status_says_what_is_known(self):
        today = date(2026, 9, 30)
        row_today = HELPERS["day_row"](self.frame, today)
        row_past = HELPERS["day_row"](self.frame, date(2026, 9, 29))
        self.assertEqual(HELPERS["day_status"](row_today, today, today)[0], "partial_today")
        self.assertEqual(HELPERS["day_status"](row_past, date(2026, 9, 29), today)[0],
                         "complete_day")
        self.assertEqual(HELPERS["day_status"](None, today, today)[0], "no_data")


class DuplicateSuspectTests(unittest.TestCase):
    def test_same_athlete_start_and_type_with_different_ids_is_flagged_not_removed(self):
        frame = pd.DataFrame([
            {"activity_id": 1, "athlete_id": 3, "start_time_local": "2026-09-29 20:08:32",
             "activity_type": "treadmill_running"},
            {"activity_id": 2, "athlete_id": 3, "start_time_local": "2026-09-29 20:08:32",
             "activity_type": "treadmill_running"},
            {"activity_id": 3, "athlete_id": 3, "start_time_local": "2026-09-29 20:08:32",
             "activity_type": "strength_training"},
            {"activity_id": 4, "athlete_id": 1, "start_time_local": "2026-09-29 20:08:32",
             "activity_type": "treadmill_running"},
        ])
        self.assertEqual(HELPERS["duplicate_suspects"](frame), {1, 2})
        self.assertEqual(len(frame), 4)


class WeeklyTotalsTests(unittest.TestCase):
    @staticmethod
    def activity(when, kind, metres, seconds, zones=(0, 0, 0, 0, 0)):
        row = {"start_time_local": pd.Timestamp(when), "activity_type": kind,
               "distance_m": metres, "duration_sec": seconds}
        row.update(dict(zip(HELPERS["HR_ZONE_COLUMNS"], zones)))
        return row

    def test_sums_are_plain_totals_of_what_garmin_recorded(self):
        frame = pd.DataFrame([
            self.activity("2026-09-07 06:00", "running", 10000, 3600, (60, 1200, 1800, 540, 0)),
            self.activity("2026-09-08 06:00", "treadmill_running", 5000, 1800, (0, 1800, 0, 0, 0)),
            self.activity("2026-09-08 18:00", "strength_training", None, 1800),
        ])

        weeks = HELPERS["weekly_totals"](frame, date(2026, 9, 1), date(2026, 9, 14))
        week = weeks.set_index("week").loc[pd.Timestamp("2026-09-07")]

        self.assertAlmostEqual(week["run_km"], 15.0)      # เวทไม่นับเป็นระยะวิ่ง
        self.assertAlmostEqual(week["hours"], 2.0)        # แต่นับเป็นเวลาซ้อม
        self.assertAlmostEqual(week["Z2"], 50.0)          # (1200 + 1800) วินาที เป็นนาที

    def test_unknown_hr_zones_stay_unknown_instead_of_becoming_zero(self):
        # ข้อบกพร่อง 4.7: fillna(0) ทำให้สัปดาห์ที่ Garmin ไม่ส่งโซนดูเหมือน "0 นาที"
        frame = pd.DataFrame([self.activity("2026-09-14 06:00", "running", 8000, 2400,
                                            (None, None, None, None, None))])
        weeks = HELPERS["weekly_totals"](frame, date(2026, 9, 14), date(2026, 9, 20))
        self.assertTrue(pd.isna(weeks.loc[0, "Z2"]))
        self.assertEqual(weeks.loc[0, "run_km"], 8.0)

    def test_a_week_without_training_stays_on_the_axis_as_zero(self):
        frame = pd.DataFrame([self.activity("2026-09-14 06:00", "running", 8000, 2400)])

        weeks = HELPERS["weekly_totals"](frame, date(2026, 9, 1), date(2026, 9, 20))

        self.assertEqual(list(weeks["run_km"]), [0.0, 0.0, 8.0])


class FormattingTests(unittest.TestCase):
    def test_integer_metrics_do_not_show_dot_zero(self):
        self.assertEqual(HELPERS["fmt_num"](93.0), "93")
        self.assertEqual(HELPERS["fmt_num"](44.6, " bpm"), "44.6 bpm")
        self.assertEqual(HELPERS["fmt_num"](None), "–")

    def test_times_and_paces(self):
        self.assertEqual(HELPERS["fmt_sec"](1323), "22:03")
        self.assertEqual(HELPERS["fmt_sec"](14023), "3:53:43")
        self.assertEqual(HELPERS["fmt_pace"](5.75), "5:45")
        self.assertEqual(HELPERS["fmt_pace"](4.999), "5:00")

    def test_recovery_minutes_are_formatted_as_hours_and_minutes(self):
        self.assertEqual(HELPERS["fmt_recovery_time"](5_425), "90 ชม. 25 นาที")
        self.assertEqual(HELPERS["fmt_recovery_time"](4_320), "72 ชม.")
        self.assertEqual(HELPERS["fmt_recovery_time"](0), "0 นาที")

    def test_garmin_words_are_kept_but_internal_suffixes_are_dropped(self):
        self.assertEqual(HELPERS["garmin_label"]("PRODUCTIVE_1"), "Productive")
        self.assertEqual(HELPERS["garmin_label"]("BALANCED"), "Balanced")
        self.assertEqual(HELPERS["garmin_label"]("treadmill_running"), "Treadmill Running")
        self.assertEqual(HELPERS["garmin_label"](float("nan")), "")

    def test_dashboard_business_date_and_db_timestamp_are_bangkok_pinned(self):
        utc_evening = datetime.datetime(2026, 8, 8, 18, 30, tzinfo=datetime.timezone.utc)

        self.assertEqual(HELPERS["bangkok_date"](utc_evening), date(2026, 8, 9))
        local = HELPERS["to_bangkok_timestamp"]("2026-08-08T18:30:00Z")
        self.assertEqual((local.date(), local.hour), (date(2026, 8, 9), 1))

    def test_calendar_alignment_inserts_an_explicit_gap_for_a_missing_day(self):
        frame = pd.DataFrame({"calendar_date": ["2026-08-07", "2026-08-09"],
                              "resting_hr": [48, 49]})

        aligned = HELPERS["calendar_aligned_frame"](
            frame, "calendar_date", date(2026, 8, 7), date(2026, 8, 9))

        self.assertEqual(len(aligned), 3)
        self.assertTrue(pd.isna(aligned.loc[1, "resting_hr"]))

    def test_field_when_names_the_day_of_the_value(self):
        today = date(2026, 9, 30)
        self.assertEqual(HELPERS["field_when"]({"date": today}, today), "วันนี้")
        self.assertEqual(HELPERS["field_when"]({"date": date(2026, 9, 29)}, today), "เมื่อวาน")
        self.assertEqual(HELPERS["field_when"]({"date": date(2026, 9, 20)}, today), "20/09")
        self.assertEqual(HELPERS["field_when"](None, today), "ไม่มีข้อมูล")


class ActivityTableTests(unittest.TestCase):
    def test_short_and_zero_distance_activities_stay_in_the_table(self):
        # เคยกรอง >500 ม. แล้ว warm-up/cool-down ของ Tong หายทั้งเซสชัน
        frame = pd.DataFrame([
            {"start_time_local": pd.Timestamp("2026-09-29 06:00"), "activity_name": "Warm up",
             "activity_type": "running", "distance_m": 300.0, "duration_sec": 120,
             "avg_pace_min_per_km": 6.6, "avg_hr": 120, "max_hr": 130},
            {"start_time_local": pd.Timestamp("2026-09-29 06:10"), "activity_name": None,
             "activity_type": "strength_training", "distance_m": 0.0, "duration_sec": 900,
             "avg_pace_min_per_km": None, "avg_hr": 100, "max_hr": 140},
        ])

        rows = HELPERS["activity_rows"](frame)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows.loc[0, "กิจกรรม"], "Strength Training")  # ใหม่สุดอยู่บน
        self.assertTrue(pd.isna(rows.loc[0, "ระยะ (km)"]))  # ไม่มีระยะ ไม่ใช่ 0.00 km


class DataAvailabilitySummaryTests(unittest.TestCase):
    def test_distinguishes_available_partial_outside_range_and_never_received(self):
        summarize = HELPERS["summarize_metric_group"]
        fields = ("score", "recovery")

        def state(history, selected):
            return summarize(fields, dict(zip(fields, history)), dict(zip(fields, selected)),
                             {"score": "2026-08-17"})["state"]

        self.assertEqual(state((5, 5), (1, 1)), "available")
        self.assertEqual(state((5, 0), (1, 0)), "partial")
        self.assertEqual(state((5, 5), (0, 0)), "outside_range")
        self.assertEqual(state((0, 0), (0, 0)), "never_received")

    def test_latest_date_is_taken_only_from_fields_that_have_real_values(self):
        result = HELPERS["summarize_metric_group"](
            ("score", "recovery"),
            history_counts={"score": 2, "recovery": 0},
            selected_counts={"score": 1, "recovery": 0},
            latest_dates={"score": "2026-08-15", "recovery": "2099-01-01"},
        )
        self.assertEqual(result["latest_date"], date(2026, 8, 15))

    def test_device_inventory_filters_stale_and_discloses_last_seen(self):
        labels = HELPERS["device_inventory_labels"]([
            {"product_display_name": "Fresh Watch", "last_seen_at_utc": "2026-08-01T00:00:00Z"},
            {"product_display_name": "Old Watch", "last_seen_at_utc": "2026-01-01T00:00:00Z"},
            {"display_name": "Legacy Watch", "last_seen_at_utc": None},
        ], now_utc="2026-08-09T00:00:00Z", stale_days=90)

        self.assertTrue(any("Fresh Watch" in label for label in labels))
        self.assertFalse(any("Old Watch" in label for label in labels))
        self.assertTrue(any("Legacy Watch" in label and "เคยพบ" in label for label in labels))


class PersonalRecordTests(unittest.TestCase):
    def test_record_garmin_never_named_says_so_instead_of_inventing_a_name_or_unit(self):
        records = pd.DataFrame([{"record_type_id": 15, "record_label": None,
                                 "value": 6.0, "achieved_date": "2026-07-18"}])
        self.assertEqual(HELPERS["personal_record_rows"](records), [{
            "รายการ": "รายการที่ Garmin ไม่ได้ระบุชื่อ (รหัส 15)",
            "สถิติ": "6",
            "ทำได้เมื่อ": "2026-07-18",
        }])

    def test_known_record_types_keep_their_units(self):
        records = pd.DataFrame([
            {"record_type_id": 3, "record_label": "วิ่ง 5 กม. (วินาที)",
             "value": 1347.63, "achieved_date": "2026-08-15"},
            {"record_type_id": 7, "record_label": "วิ่งไกลสุด (เมตร)",
             "value": 21217.44, "achieved_date": "2026-07-11"},
            {"record_type_id": 12, "record_label": "ก้าวมากสุด/วัน",
             "value": 33888.0, "achieved_date": "2026-07-15"},
        ])
        self.assertEqual([row["สถิติ"] for row in HELPERS["personal_record_rows"](records)],
                         ["22:28", "21.22 km", "33,888 ก้าว"])


if __name__ == "__main__":
    unittest.main()


class IntradaySeriesTests(unittest.TestCase):
    def test_a_long_gap_breaks_the_line_instead_of_bridging_it(self):
        points = pd.DataFrame({
            "athlete_id": [1, 1, 1],
            "metric": ["heart_rate"] * 3,
            "ts": pd.to_datetime(["2026-09-30 06:00", "2026-09-30 06:02", "2026-09-30 09:00"]),
            "value": [60.0, 62.0, 70.0],
        })
        series = HELPERS["intraday_series"](points, "heart_rate")
        self.assertEqual(len(series), 4)                  # สามจุดจริง + หนึ่งช่องว่าง
        self.assertTrue(pd.isna(series["ค่า"].iloc[2]))
        self.assertEqual(series["ค่า"].dropna().tolist(), [60.0, 62.0, 70.0])  # ไม่มีจุดปลอม

    def test_unmeasured_points_stay_empty_not_zero(self):
        points = pd.DataFrame({"athlete_id": [1, 1], "metric": ["stress", "stress"],
                               "ts": pd.to_datetime(["2026-09-30 06:00", "2026-09-30 06:03"]),
                               "value": [30.0, None]})
        series = HELPERS["intraday_series"](points, "stress")
        self.assertTrue(pd.isna(series["ค่า"].iloc[1]))
