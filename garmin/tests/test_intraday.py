"""Intraday wellness (HR / stress / body battery) — parse, store, prune และ hook ใน lane.

ทุกเทสใช้ fake Garmin เท่านั้น ไม่ยิง Garmin จริง; DB ทดสอบสร้างจาก 02_init_schema.py
(อ่าน schema จาก data/garmin.db = เขียวในเครื่อง แดงบน CI)
"""

import importlib.util
import shutil
import sqlite3
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

GARMIN_ROOT = Path(__file__).resolve().parents[1]


def load_script(name, filename):
    spec = importlib.util.spec_from_file_location(
        name, GARMIN_ROOT / "scripts" / filename
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


intraday = load_script("garmin_intraday_under_test", "intraday.py")
schema = load_script("garmin_schema_intraday_test", "02_init_schema.py")
backfill = load_script("garmin_backfill_intraday_test", "03_backfill.py")

# 2030-01-02 03:00:00 UTC เป็นต้นไป (epoch ms)
T0 = int(datetime(2030, 1, 2, 3, 0, tzinfo=timezone.utc).timestamp() * 1000)
MIN = 60_000
DAY = "2030-01-02"


def hr_payload(points, keys=("timestamp", "heartrate")):
    return {
        "calendarDate": DAY,
        "heartRateValueDescriptors": [
            {"index": i, "key": k} for i, k in enumerate(keys)
        ],
        "heartRateValues": points,
    }


def stress_payload(stress_points, bb_points=None, stress_keys=("timestamp", "stressLevel"),
                   bb_keys=("timestamp", "bodyBatteryStatus", "bodyBatteryLevel",
                            "bodyBatteryVersion")):
    return {
        "calendarDate": DAY,
        "stressValueDescriptorsDTOList": [
            {"index": i, "key": k} for i, k in enumerate(stress_keys)
        ],
        "stressValuesArray": stress_points,
        "bodyBatteryValueDescriptorsDTOList": [
            {"bodyBatteryValueDescriptorIndex": i, "bodyBatteryValueDescriptorKey": k}
            for i, k in enumerate(bb_keys)
        ],
        "bodyBatteryValuesArray": bb_points if bb_points is not None else [],
    }


def make_db(directory):
    path = Path(directory) / "garmin.db"
    schema.init_schema(path)
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO dim_athlete (athlete_id, slug, display_name) VALUES (1, 'a', 'A')")
    conn.commit()
    return conn


class IntradayBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="intraday-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.conn = make_db(self.tmp)
        self.addCleanup(self.conn.close)

    def rows(self, metric=None):
        sql = "SELECT metric, ts_utc, value, source_code FROM fact_wellness_intraday"
        args = ()
        if metric:
            sql += " WHERE metric = ?"
            args = (metric,)
        return self.conn.execute(sql + " ORDER BY metric, ts_utc", args).fetchall()


class ParseTests(unittest.TestCase):
    def test_heart_rate_located_by_descriptor_key_not_position(self):
        # สลับตำแหน่งคอลัมน์: ถ้า hard-code index 0/1 ค่าจะกลายเป็นเวลา
        payload = hr_payload([[61, T0], [None, T0 + 2 * MIN]], keys=("heartrate", "timestamp"))
        rows = intraday.parse_heart_rate(payload)
        self.assertEqual(
            [(r["ts_utc"], r["value"]) for r in rows],
            [("2030-01-02T03:00:00Z", 61.0), ("2030-01-02T03:02:00Z", None)],
        )
        self.assertEqual({r["calendar_date"] for r in rows}, {DAY})

    def test_none_or_nonpositive_bpm_is_null_never_zero(self):
        rows = intraday.parse_heart_rate(hr_payload([[T0, None], [T0 + MIN, 0], [T0 + 2 * MIN, 58]]))
        self.assertEqual([r["value"] for r in rows], [None, None, 58.0])

    def test_negative_stress_is_null_value_with_source_code(self):
        rows = intraday.parse_stress(stress_payload([[T0, -1], [T0 + 3 * MIN, -2], [T0 + 6 * MIN, 27]]))
        self.assertEqual(
            [(r["value"], r["source_code"]) for r in rows],
            [(None, -1), (None, -2), (27.0, None)],
        )

    def test_body_battery_uses_level_descriptor(self):
        payload = stress_payload([], [[T0, "MEASURED", 74, 1], [T0 + MIN, "MEASURED", None, 1]])
        rows = intraday.parse_body_battery(payload)
        self.assertEqual([r["value"] for r in rows], [74.0, None])

    def test_missing_descriptor_key_raises_drift(self):
        payload = hr_payload([[T0, 60]], keys=("timestamp", "bpm_renamed"))
        with self.assertRaises(intraday.IntradaySchemaDrift):
            intraday.parse_heart_rate(payload)

    def test_empty_or_missing_payload_is_no_data_not_drift(self):
        self.assertEqual(intraday.parse_heart_rate(None), [])
        self.assertEqual(intraday.parse_heart_rate({"calendarDate": DAY}), [])
        self.assertEqual(intraday.parse_stress(stress_payload([])), [])


class StoreTests(IntradayBase):
    def test_missing_descriptor_stores_nothing_and_records_failure(self):
        failures = []
        payloads = {"heart_rate": hr_payload([[T0, 60]], keys=("timestamp", "bpm_renamed"))}
        counts = intraday.store_intraday(self.conn, 1, payloads, failures=failures)
        self.assertEqual(self.rows("heart_rate"), [])
        self.assertEqual(counts["heart_rate"], 0)
        self.assertEqual(failures, [{"endpoint": "get_heart_rates", "reason": "payload"}])

    def test_drift_in_one_metric_does_not_block_the_others(self):
        failures = []
        payloads = {
            "heart_rate": hr_payload([[T0, 60]]),
            "stress": stress_payload([[T0, 30]], [[T0, "M", 50, 1]],
                                     bb_keys=("timestamp", "status", "renamed", "v")),
        }
        intraday.store_intraday(self.conn, 1, payloads, failures=failures)
        self.assertEqual(len(self.rows("heart_rate")), 1)
        self.assertEqual(len(self.rows("stress")), 1)
        self.assertEqual(self.rows("body_battery"), [])
        self.assertEqual(failures, [{"endpoint": "get_stress_data", "reason": "payload"}])

    def test_rerun_is_idempotent_and_changed_value_updates(self):
        payloads = {"heart_rate": hr_payload([[T0, 60], [T0 + 2 * MIN, 62]])}
        intraday.store_intraday(self.conn, 1, payloads)
        intraday.store_intraday(self.conn, 1, payloads)
        self.assertEqual(len(self.rows()), 2)

        payloads = {"heart_rate": hr_payload([[T0, 75], [T0 + 2 * MIN, 62]])}
        intraday.store_intraday(self.conn, 1, payloads)
        self.assertEqual(len(self.rows()), 2)
        self.assertEqual(self.rows("heart_rate")[0][2], 75.0)

    def test_a_refetch_that_comes_back_empty_does_not_erase_a_good_point(self):
        # code review 30 ก.ย. 69 — กฎ NULL-safe merge เดียวกับ wellness รายวัน
        intraday.store_intraday(self.conn, 1, {"heart_rate": hr_payload([[T0, 60]])})
        intraday.store_intraday(self.conn, 1, {"heart_rate": hr_payload([[T0, None]])})
        self.assertEqual(self.rows("heart_rate")[0][2], 60.0)

    def test_no_payload_for_a_metric_leaves_existing_rows_alone(self):
        intraday.store_intraday(self.conn, 1, {"heart_rate": hr_payload([[T0, 60]])})
        intraday.store_intraday(self.conn, 1, {"heart_rate": None, "stress": None})
        self.assertEqual(len(self.rows("heart_rate")), 1)


class PruneTests(IntradayBase):
    def test_prune_keeps_last_180_days_only(self):
        now = datetime(2030, 6, 1, 12, 0, tzinfo=timezone.utc)

        def ms(days_ago):
            return int((now - timedelta(days=days_ago)).timestamp() * 1000)

        old, edge = ms(181), ms(179)
        intraday.store_intraday(
            self.conn, 1, {"heart_rate": hr_payload([[old, 60], [edge, 61], [ms(1), 62]])}
        )
        # สรุปรายวันต้องไม่ถูกแตะ
        self.conn.execute(
            "INSERT INTO fact_daily_wellness (athlete_id, calendar_date, resting_hr) "
            "VALUES (1, '2029-01-01', 50)"
        )
        self.conn.commit()

        deleted = intraday.prune(self.conn, now=now)

        self.assertEqual(deleted, 1)
        self.assertEqual(len(self.rows("heart_rate")), 2)
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM fact_daily_wellness").fetchone()[0], 1
        )


class FakeGarmin:
    """Garmin ปลอม: get_* ที่ไม่รู้จักตอบ None (ไม่มีข้อมูล); stress ยกเว้นได้."""

    def __init__(self, stress_raises=False, hr=None, stress=None):
        self.stress_raises = stress_raises
        self.hr = hr
        self.stress = stress
        self.calls = []

    def login(self, _token_dir):
        return None

    def get_full_name(self):
        return "Fake"

    def get_heart_rates(self, day):
        self.calls.append(("hr", day))
        return self.hr

    def get_stress_data(self, day):
        self.calls.append(("stress", day))
        if self.stress_raises:
            raise RuntimeError("boom")
        return self.stress

    def __getattr__(self, name):
        if name.startswith("get_"):
            return lambda *a, **k: None
        raise AttributeError(name)


class LaneHookTests(IntradayBase):
    def _today(self):
        return backfill.datetime.now(backfill.BANGKOK_TZ).date()

    def _hook(self, garmin, day, failures):
        with mock.patch.object(backfill.time, "sleep"):
            return backfill._sync_intraday_day(garmin, self.conn, 1, day, failures)

    def test_stress_failure_still_stores_heart_rate_and_keeps_prior_rows(self):
        day = self._today()
        # แถว stress เดิมจากรอบก่อน ต้องไม่ถูกล้าง
        intraday.store_intraday(self.conn, 1, {"stress": stress_payload([[T0, 33]])})
        before = self.rows("stress")
        garmin = FakeGarmin(stress_raises=True, hr=hr_payload([[T0, 64]]))
        failures = []

        self._hook(garmin, day, failures)

        self.assertEqual(len(self.rows("heart_rate")), 1)
        self.assertEqual(self.rows("stress"), before)
        self.assertEqual([f["endpoint"] for f in failures], ["get_stress_data"])

    def test_hook_never_raises_even_if_storing_blows_up(self):
        garmin = FakeGarmin(hr=hr_payload([[T0, 64]]))
        failures = []
        broken = sqlite3.connect(":memory:")  # ไม่มีตาราง → store ล้ม
        self.addCleanup(broken.close)
        with mock.patch.object(backfill.time, "sleep"):
            result = backfill._sync_intraday_day(garmin, broken, 1, self._today(), failures)
        self.assertIsNone(result)
        self.assertEqual(failures[-1]["endpoint"], "intraday_store")


class MainLaneTests(unittest.TestCase):
    """--wellness-fast / full sync ผ่าน main() จริง ด้วย fake Garmin."""

    def setUp(self):
        self.data_dir = Path(tempfile.mkdtemp(prefix="intraday-main-"))
        self.addCleanup(shutil.rmtree, self.data_dir, True)
        previous = backfill.use_data_dir(self.data_dir)
        self.addCleanup(backfill.use_data_dir, previous)
        schema.init_schema(self.data_dir / "garmin.db")

    def _run_main(self, argv_extra, garmin):
        project_root = self.data_dir / "project"
        (project_root / "tokens" / "probe").mkdir(parents=True)
        fake = types.ModuleType("garminconnect")
        fake.Garmin = lambda: garmin
        argv = ["03_backfill.py", "--athlete", "probe", *argv_extra]
        with (
            mock.patch.object(backfill, "PROJECT_ROOT", project_root),
            mock.patch.object(backfill.time, "sleep"),
            mock.patch.dict(sys.modules, {"garminconnect": fake}),
            mock.patch.object(sys, "argv", argv),
        ):
            backfill.main()
        conn = sqlite3.connect(self.data_dir / "garmin.db")
        self.addCleanup(conn.close)
        return conn, backfill.json.loads(
            (backfill.STATUS_DIR / "probe.json").read_text(encoding="utf-8")
        )

    def test_wellness_fast_lane_stores_heart_rate_when_stress_endpoint_fails(self):
        today = backfill.datetime.now(backfill.BANGKOK_TZ).date()
        garmin = FakeGarmin(stress_raises=True, hr={
            **hr_payload([[T0, 66], [T0 + 2 * MIN, 67]]), "calendarDate": today.isoformat(),
        })

        conn, status = self._run_main(["--days", "0", "--wellness-fast"], garmin)

        self.assertEqual(
            conn.execute(
                "SELECT COUNT(*) FROM fact_wellness_intraday WHERE metric='heart_rate'"
            ).fetchone()[0], 2)
        # ยิงวันนี้เท่านั้น และ 1 ครั้ง/endpoint ต่อรอบ
        self.assertEqual(
            garmin.calls, [("hr", today.isoformat()), ("stress", today.isoformat())]
        )
        # ความล้มเหลวโผล่ทางเดียวกับ endpoint อื่น และรอบไม่ถูกตีว่าล้ม
        self.assertTrue(status["ok"])
        self.assertIn("get_stress_data", [f["endpoint"] for f in status["endpoint_failures"]])

    def test_full_sync_fetches_yesterday_and_prunes_once(self):
        today = backfill.datetime.now(backfill.BANGKOK_TZ).date()
        yesterday = today - timedelta(days=1)
        old_ms = int((datetime.now(timezone.utc) - timedelta(days=200)).timestamp() * 1000)
        conn0 = sqlite3.connect(self.data_dir / "garmin.db")
        conn0.execute("INSERT INTO dim_athlete (athlete_id, slug, display_name) VALUES (1,'probe','P')")
        conn0.commit()
        conn0.close()
        garmin = FakeGarmin(hr={
            **hr_payload([[T0, 66]]), "calendarDate": yesterday.isoformat(),
        })
        # แถวเก่า 200 วัน (ใส่ผ่าน store ก่อนรัน)
        pre = sqlite3.connect(self.data_dir / "garmin.db")
        intraday.store_intraday(pre, 1, {"heart_rate": hr_payload([[old_ms, 50]])})
        pre.commit()
        pre.close()

        conn, _ = self._run_main(["--days", "3", "--skip-activities"], garmin)

        self.assertIn(("hr", yesterday.isoformat()), garmin.calls)
        self.assertNotIn(("hr", today.isoformat()), garmin.calls)
        remaining = [r[0] for r in conn.execute(
            "SELECT value FROM fact_wellness_intraday WHERE metric='heart_rate'")]
        self.assertEqual(remaining, [66.0])


if __name__ == "__main__":
    unittest.main()


class PruneFailureVisibilityTests(IntradayBase):
    def test_a_failed_prune_is_recorded_not_swallowed(self):
        # เดิม except แล้ว rollback เงียบ ๆ — ถ้าล้มถาวร ตารางจะโตไม่หยุดโดยไม่มีใครรู้
        failures = []
        with mock.patch.object(intraday, "prune", side_effect=sqlite3.OperationalError("locked")), \
                mock.patch.object(backfill, "_intraday_module", return_value=intraday):
            backfill._prune_intraday(self.conn, failures)
        self.assertEqual([f.get("endpoint") for f in failures], ["intraday_prune"])
