"""PR ต้องตรงกับ snapshot ล่าสุดของ Garmin — และห้ามแตะอะไรเมื่อดึงไม่สำเร็จ."""

import importlib.util
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

GARMIN_ROOT = Path(__file__).resolve().parents[1]


def load_script(name, filename):
    spec = importlib.util.spec_from_file_location(
        name, GARMIN_ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backfill = load_script("garmin_pr_snapshot_backfill", "03_backfill.py")
schema = load_script("garmin_pr_snapshot_schema", "02_init_schema.py")


def pr(type_id, value, activity_id=111, day="2026-09-01"):
    return {"typeId": type_id, "value": value, "activityId": activity_id,
            "prStartTimeGmtFormatted": day}


class FakeGarmin:
    def __init__(self, prs):
        self.prs = prs

    def get_personal_record(self):
        if isinstance(self.prs, Exception):
            raise self.prs
        return self.prs

    def __getattr__(self, name):  # endpoint อื่นของ extras: ไม่มีข้อมูล
        return lambda *a, **k: None


class PersonalRecordSnapshotTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = Path(tmp.name) / "t.db"
        schema.init_schema(db)
        self.conn = sqlite3.connect(db)
        self.addCleanup(self.conn.close)

    def sync(self, prs, athlete=1):
        failures = []
        with mock.patch.object(backfill.time, "sleep"):
            backfill.fetch_and_insert_extras(
                FakeGarmin(prs), self.conn, athlete,
                date(2026, 9, 1), date(2026, 9, 1), endpoint_failures=failures)
        return failures

    def rows(self, athlete=1):
        return self.conn.execute(
            "SELECT record_type_id, value FROM fact_personal_record "
            "WHERE athlete_id = ? ORDER BY record_type_id", (athlete,)).fetchall()

    def test_record_deleted_in_garmin_is_removed(self):
        self.sync([pr(1, 83.0), pr(2, 300.0)])
        self.assertEqual(self.rows(), [(1, 83.0), (2, 300.0)])
        self.sync([pr(2, 300.0)])
        self.assertEqual(self.rows(), [(2, 300.0)])

    def test_a_row_garmin_sent_but_we_could_not_read_is_never_deleted(self):
        """code review 30 ก.ย. 69: แถวที่ parse ไม่ได้ต้องไม่ถูกตีความว่า "Garmin ลบแล้ว"

        Garmin ส่งมาครบ 2 รายการ แต่รายการที่ 1 ค่าเพี้ยน → ต้องไม่ลบ PR เดิมของรายการนั้น
        """
        self.sync([pr(1, 83.0), pr(2, 300.0)])
        self.sync([pr(1, None), pr(2, 290.0)])
        self.assertEqual(self.rows(), [(1, 83.0), (2, 290.0)])

    def test_other_athletes_rows_are_untouched(self):
        self.sync([pr(1, 83.0)], athlete=2)
        self.sync([pr(2, 300.0)], athlete=1)
        self.assertEqual(self.rows(athlete=2), [(1, 83.0)])

    def test_corrected_value_replaces_old_value(self):
        self.sync([pr(1, 83.0, activity_id=5)])
        self.sync([pr(1, 240.0, activity_id=None)])
        row = self.conn.execute(
            "SELECT value, activity_id FROM fact_personal_record").fetchone()
        self.assertEqual(row, (240.0, None))

    def test_failed_call_changes_nothing_and_records_failure(self):
        self.sync([pr(1, 83.0), pr(2, 300.0)])
        failures = self.sync(RuntimeError("HTTP 500 boom"))
        self.assertEqual(self.rows(), [(1, 83.0), (2, 300.0)])
        self.assertEqual([f["endpoint"] for f in failures], ["get_personal_record"])

    def test_none_and_unexpected_payload_change_nothing(self):
        self.sync([pr(1, 83.0)])
        self.sync(None)
        failures = self.sync("garbage")
        self.assertEqual(self.rows(), [(1, 83.0)])
        self.assertEqual([f["reason"] for f in failures], ["payload"])

    def test_empty_list_never_wipes_existing_rows(self):
        self.sync([pr(1, 83.0)])
        self.sync([])
        self.sync({"personalRecords": []})
        self.sync([{"typeId": "x", "value": None}])  # อ่านไม่ได้สักแถว
        self.assertEqual(self.rows(), [(1, 83.0)])

    def test_dict_wrapper_is_a_snapshot_too(self):
        self.sync([pr(1, 83.0), pr(2, 300.0)])
        self.sync({"personalRecords": [pr(2, 300.0)]})
        self.assertEqual(self.rows(), [(2, 300.0)])


if __name__ == "__main__":
    unittest.main()
