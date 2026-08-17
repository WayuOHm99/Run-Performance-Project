"""เทส health_report.py — ทุกเคสใช้ temp directory + ข้อมูลสังเคราะห์ล้วน ห้ามแตะ
garmin/data ของจริง ยกเว้น LaneLimitConsistencyRealFilesTest ที่ตั้งใจอ่าน (read-only)
dashboard.py / notify_sync.ps1 จริงของโปรเจกต์ เพื่อพิสูจน์ว่าค่าที่ deploy จริงตรงกัน
(ตามข้อยกเว้นที่อนุญาตไว้)"""

import importlib.util
import io
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

GARMIN_ROOT = Path(__file__).resolve().parents[1]


def load_script(name, filename):
    spec = importlib.util.spec_from_file_location(name, GARMIN_ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hr = load_script("garmin_health_report_under_test", "health_report.py")

PRODUCTION_DATA_DIR = GARMIN_ROOT / "data"


class IsolatedHealthDirMixin:
    """ชี้ DATA_DIR/BACKUP_DIR ของ health_report ไป temp dir ตลอดอายุเคส — ไม่มีเคสไหน
    แตะ garmin/data หรือ C:\\Backup ของจริงเลย"""

    def setUp(self):
        super().setUp()
        self.data_dir = Path(tempfile.mkdtemp(prefix="health-data-"))
        self.backup_dir = Path(tempfile.mkdtemp(prefix="health-backup-"))
        self.addCleanup(shutil.rmtree, self.data_dir, True)
        self.addCleanup(shutil.rmtree, self.backup_dir, True)
        prev_data = hr.use_data_dir(self.data_dir)
        prev_backup = hr.use_backup_dir(self.backup_dir)
        self.addCleanup(hr.use_data_dir, prev_data)
        self.addCleanup(hr.use_backup_dir, prev_backup)

    # ── ตัวช่วยสร้างข้อมูลสังเคราะห์ ──

    def write_lane_status(self, lane, run_at, ok=True, reason="ok", warnings=None):
        d = self.data_dir / "sync_lane"
        d.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_at": run_at.isoformat(timespec="seconds"),
            "lane": lane,
            "results": [{"slug": "synthetic", "ok": ok, "reason": reason, "warnings": warnings or []}],
        }
        (d / f"{lane}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def write_marker(self, name, at):
        (self.data_dir / name).write_text(at.isoformat(), encoding="utf-8")

    def write_raw_marker(self, name, raw_text):
        (self.data_dir / name).write_text(raw_text, encoding="utf-8")

    def write_raw_lane(self, lane, raw_run_at, ok=True, reason="ok"):
        d = self.data_dir / "sync_lane"
        d.mkdir(parents=True, exist_ok=True)
        payload = {"run_at": raw_run_at, "lane": lane,
                   "results": [{"slug": "synthetic", "ok": ok, "reason": reason, "warnings": []}]}
        (d / f"{lane}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def find(findings, prefix):
    return [f for f in findings if f.check.startswith(prefix)]


class ScheduledTaskChecksTests(IsolatedHealthDirMixin, unittest.TestCase):
    def test_health_report_monitors_its_own_publisher_task(self):
        self.assertIn("Run-Performance-SystemHealth", hr.SCHEDULED_TASKS)
        findings = hr.check_scheduled_tasks(
            provider=lambda name: (
                "Last Run Time: 8/17/2026 10:25:00 AM\n"
                "Last Result: 0\nStatus: Ready\n"
            ),
            now=datetime(2026, 8, 17, 10, 30),
        )
        own = find(
            findings, "scheduled_task:Run-Performance-SystemHealth"
        )
        self.assertEqual(len(own), 1)
        self.assertEqual(own[0].level, hr.OK)

    def test_real_provider_decodes_thai_windows_cp874_without_reader_crash(self):
        raw = (
            "Last Run Time: 8/9/2026 11:55:00 AM\n"
            "Last Result: 0\n"
            "Task To Run: D:\\\\สำรอง\\garmin-sync.bat\n"
        ).encode("cp874")
        completed = type(
            "Completed", (), {"returncode": 0, "stdout": raw, "stderr": b""}
        )()

        with (
            mock.patch.object(hr.os, "name", "nt"),
            mock.patch.object(hr.subprocess, "run", return_value=completed) as run,
        ):
            output = hr.default_schtasks_provider("Synthetic-Task")

        self.assertIn("สำรอง", output)
        self.assertEqual(
            hr.parse_schtasks_output(output)["last_result"], "0"
        )
        self.assertFalse(run.call_args.kwargs["text"])

    def test_task_reports_error_when_lane_status_says_failed(self):
        now = datetime(2026, 8, 6, 12, 0, 0)
        self.write_lane_status("fast", now - timedelta(minutes=5), ok=False, reason="token")

        def provider(task_name):
            return "TaskName: \\Run-Performance-Garmin-Fast\nLast Run Time: 8/6/2026 11:55:00 AM\nLast Result: 1\n"

        findings = hr.check_scheduled_tasks(provider=provider, now=now)
        fast = [f for f in findings if f.check == "scheduled_task:Run-Performance-Garmin-Fast"]
        self.assertEqual(len(fast), 1)
        self.assertEqual(fast[0].level, hr.ERROR)
        self.assertIn("token", fast[0].message)

    def test_task_never_run_is_warning_not_error(self):
        def provider(task_name):
            return "TaskName: \\Run-Performance-Garmin-DeepSync\nLast Run Time: N/A\nLast Result: N/A\n"

        findings = hr.check_scheduled_tasks(provider=provider)
        deep = [f for f in findings if f.check == "scheduled_task:Run-Performance-Garmin-DeepSync"]
        self.assertEqual(len(deep), 1)
        self.assertEqual(deep[0].level, hr.WARNING)
        self.assertIn("ยังไม่เคยรัน", deep[0].message)

    def test_task_ok_when_last_result_zero_and_lane_ok(self):
        now = datetime(2026, 8, 6, 12, 0, 0)
        self.write_lane_status("wellness", now - timedelta(minutes=2), ok=True)

        def provider(task_name):
            return "Last Run Time: 8/6/2026 11:58:00 AM\nLast Result: 0\n"

        findings = hr.check_scheduled_tasks(provider=provider, now=now)
        wellness = [f for f in findings if f.check == "scheduled_task:Run-Performance-Garmin-Wellness"]
        self.assertEqual(wellness[0].level, hr.OK)

    def test_nonzero_last_result_is_error_even_when_old_lane_status_is_ok(self):
        now = datetime(2026, 8, 6, 12, 0, 0)
        self.write_lane_status("fast", now - timedelta(minutes=2), ok=True)

        findings = hr.check_scheduled_tasks(
            provider=lambda name: (
                "Last Run Time: 8/6/2026 11:58:00 AM\n"
                "Last Result: 5\nStatus: Ready\n"
            ),
            now=now,
        )
        fast = find(findings, "scheduled_task:Run-Performance-Garmin-Fast")[0]
        self.assertEqual(fast.level, hr.ERROR)
        self.assertIn("LastTaskResult=5", fast.message)

    def test_missing_or_empty_lane_status_is_not_reported_ok(self):
        findings = hr.check_scheduled_tasks(provider=lambda name: (
            "Last Run Time: 8/6/2026 11:58:00 AM\n"
            "Last Result: 0\nStatus: Ready\n"
        ))
        self.assertTrue(findings)
        lane_findings = [
            f for f in findings if f.check.removeprefix("scheduled_task:") in hr.TASK_LANE
        ]
        self.assertTrue(all(f.level == hr.WARNING for f in lane_findings))
        self.assertEqual(
            find(findings, "scheduled_task:Run-Performance-SystemHealth")[0].level,
            hr.OK,
        )

    def test_malformed_lane_results_are_warning_not_crash_or_ok(self):
        lane_dir = self.data_dir / "sync_lane"
        lane_dir.mkdir(parents=True)
        for lane in hr.EXPECTED_LANES:
            (lane_dir / f"{lane}.json").write_text(
                json.dumps({"run_at": "2026-08-06T11:58:00", "results": ["bad"]}),
                encoding="utf-8",
            )
        findings = hr.check_scheduled_tasks(provider=lambda name: (
            "Last Run Time: 8/6/2026 11:58:00 AM\n"
            "Last Result: 0\nStatus: Ready\n"
        ))
        lane_findings = [
            f for f in findings if f.check.removeprefix("scheduled_task:") in hr.TASK_LANE
        ]
        self.assertTrue(all(f.level == hr.WARNING for f in lane_findings))
        self.assertEqual(
            find(findings, "scheduled_task:Run-Performance-SystemHealth")[0].level,
            hr.OK,
        )

    def test_disabled_expected_task_is_error(self):
        now = datetime(2026, 8, 6, 12, 0, 0)
        for lane in hr.EXPECTED_LANES:
            self.write_lane_status(lane, now - timedelta(minutes=2), ok=True)
        findings = hr.check_scheduled_tasks(provider=lambda name: (
            "Last Run Time: 8/6/2026 11:58:00 AM\n"
            "Last Result: 0\nStatus: Disabled\n"
        ))
        self.assertTrue(all(f.level == hr.ERROR for f in findings))

    def test_non_windows_provider_is_skipped_not_broken(self):
        # จำลอง "เครื่องนี้ไม่ใช่ Windows" แบบตายตัว ไม่ผูกกับ OS จริงที่รันเทส —
        # ต้องได้ผลเดียวกันไม่ว่าเทสจะถูกรันบน Linux (sandbox/CI) หรือ Windows (production)
        with mock.patch.object(hr.os, "name", "posix"):
            with self.assertRaises(hr.SchtasksUnavailable):
                hr.default_schtasks_provider("Run-Performance-Garmin-Fast")

            findings = hr.check_scheduled_tasks(provider=hr.default_schtasks_provider)
        self.assertEqual(len(findings), len(hr.SCHEDULED_TASKS))
        for f in findings:
            self.assertEqual(f.level, hr.WARNING, msg=f.message)
            self.assertIn("skipped", f.message)
            self.assertNotEqual(f.level, hr.ERROR)

    def test_failed_windows_query_for_expected_task_is_error(self):
        def provider(task_name):
            raise hr.ScheduledTaskQueryFailed(f"missing:{task_name}")

        findings = hr.check_scheduled_tasks(provider=provider)

        self.assertEqual(len(findings), len(hr.SCHEDULED_TASKS))
        self.assertTrue(all(f.level == hr.ERROR for f in findings))

    def test_task_scheduler_not_yet_run_code_is_warning(self):
        findings = hr.check_scheduled_tasks(provider=lambda name: (
            "Last Run Time: 11/30/1999 12:00:00 AM\n"
            "Last Result: 267011\nStatus: Ready\n"
        ))

        restore = find(
            findings, "scheduled_task:Run-Performance-RestoreDrill"
        )[0]
        self.assertEqual(restore.level, hr.WARNING)
        self.assertIn("ยังไม่เคยรัน", restore.message)


class LaneFreshnessTests(IsolatedHealthDirMixin, unittest.TestCase):
    def test_stale_lane_is_error(self):
        now = datetime(2026, 8, 6, 12, 0, 0)
        # เกินเพดาน fast (75 นาที) ไปมาก
        self.write_lane_status("fast", now - timedelta(hours=5))
        findings = hr.check_lane_freshness(now=now)
        fast = find(findings, "lane_freshness:fast")
        self.assertEqual(fast[0].level, hr.ERROR)

    def test_fresh_lane_is_ok(self):
        now = datetime(2026, 8, 6, 12, 0, 0)
        self.write_lane_status("wellness", now - timedelta(minutes=5))
        findings = hr.check_lane_freshness(now=now)
        wellness = find(findings, "lane_freshness:wellness")
        self.assertEqual(wellness[0].level, hr.OK)

    def test_missing_lane_status_is_warning(self):
        findings = hr.check_lane_freshness()
        deep = find(findings, "lane_freshness:deep")
        self.assertEqual(deep[0].level, hr.WARNING)


class RecoveryFreshnessTests(IsolatedHealthDirMixin, unittest.TestCase):
    def write_operation(self, operation, run_at, *, ok=True, reason="ok"):
        lane_dir = self.data_dir / "sync_lane"
        lane_dir.mkdir(parents=True, exist_ok=True)
        (lane_dir / f"{operation}.json").write_text(
            json.dumps({"run_at": run_at.isoformat(), "ok": ok, "reason": reason}),
            encoding="utf-8",
        )

    def test_recent_successful_backup_and_restore_are_ok(self):
        now = datetime(2026, 8, 13, 12, 0, 0)
        self.write_operation("offsite_backup", now - timedelta(hours=2))
        self.write_operation("restore_drill", now - timedelta(days=2))

        findings = hr.check_recovery_freshness(now=now)

        self.assertTrue(all(item.level == hr.OK for item in findings))

    def test_failed_offsite_backup_is_error_even_when_fresh(self):
        now = datetime(2026, 8, 13, 12, 0, 0)
        self.write_operation(
            "offsite_backup", now - timedelta(minutes=5),
            ok=False, reason="upload_failed",
        )
        self.write_operation("restore_drill", now - timedelta(days=2))

        finding = find(
            hr.check_recovery_freshness(now=now), "recovery:offsite_backup"
        )[0]

        self.assertEqual(finding.level, hr.ERROR)
        self.assertIn("upload_failed", finding.message)

    def test_stale_restore_drill_is_error(self):
        now = datetime(2026, 8, 13, 12, 0, 0)
        self.write_operation("offsite_backup", now - timedelta(hours=2))
        self.write_operation("restore_drill", now - timedelta(days=36))

        finding = find(
            hr.check_recovery_freshness(now=now), "recovery:restore_drill"
        )[0]

        self.assertEqual(finding.level, hr.ERROR)

    def test_missing_proof_is_error_not_a_green_heartbeat(self):
        findings = hr.check_recovery_freshness(
            now=datetime(2026, 8, 13, 12, 0, 0)
        )

        self.assertTrue(all(item.level == hr.ERROR for item in findings))

class UnfinishedRunTests(IsolatedHealthDirMixin, unittest.TestCase):
    def test_started_and_never_finished_is_error(self):
        now = datetime(2026, 8, 6, 12, 0, 0)
        # marker เริ่มไว้นานเกิน grace ของ full (30 นาที) แต่ไม่มีสถานะของรอบนั้นตามมา
        self.write_marker("sync_run_start.txt", now - timedelta(minutes=90))
        findings = hr.check_unfinished_runs(now=now)
        full = find(findings, "unfinished_run:full")
        self.assertEqual(len(full), 1)
        self.assertEqual(full[0].level, hr.ERROR)

    def test_started_and_finished_reports_nothing_for_that_lane(self):
        now = datetime(2026, 8, 6, 12, 0, 0)
        started = now - timedelta(minutes=5)
        self.write_marker("sync_run_start.txt", started)
        self.write_lane_status("full", started + timedelta(minutes=2))
        findings = hr.check_unfinished_runs(now=now)
        full = find(findings, "unfinished_run:full")
        self.assertEqual(full, [])

    def test_still_within_grace_is_ok(self):
        now = datetime(2026, 8, 6, 12, 0, 0)
        self.write_marker("sync_fast_run_start.txt", now - timedelta(minutes=2))  # grace fast = 10
        findings = hr.check_unfinished_runs(now=now)
        fast = find(findings, "unfinished_run:fast")
        self.assertEqual(fast[0].level, hr.OK)

    def test_no_markers_at_all_reports_single_ok(self):
        findings = hr.check_unfinished_runs()
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, hr.OK)


class DbIntegrityTests(IsolatedHealthDirMixin, unittest.TestCase):
    def test_missing_db_is_error(self):
        findings = hr.check_db_integrity()
        self.assertEqual(findings[0].level, hr.ERROR)
        self.assertIn("ไม่พบไฟล์ DB", findings[0].message)

    def test_healthy_db_is_ok(self):
        conn = sqlite3.connect(str(hr.DB_PATH))
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        conn.execute("INSERT INTO t (v) VALUES ('x')")
        conn.commit()
        conn.close()

        findings = hr.check_db_integrity()
        self.assertEqual(findings[0].level, hr.OK)
        self.assertIn("quick_check", findings[0].message)

    def test_corrupted_db_is_error(self):
        hr.DB_PATH.write_bytes(b"this is not a sqlite database file at all")
        findings = hr.check_db_integrity()
        self.assertEqual(findings[0].level, hr.ERROR)

    def test_never_writes_to_the_db(self):
        conn = sqlite3.connect(str(hr.DB_PATH))
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()
        before = hr.DB_PATH.read_bytes()

        hr.check_db_integrity()

        after = hr.DB_PATH.read_bytes()
        self.assertEqual(before, after, "check_db_integrity ห้ามแก้ไฟล์ DB แม้แต่ไบต์เดียว")


class BackupChecksTests(IsolatedHealthDirMixin, unittest.TestCase):
    @staticmethod
    def _write_valid_sqlite(path, pad_bytes=20_000):
        conn = sqlite3.connect(str(path))
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        conn.execute("INSERT INTO t (v) VALUES (?)", ("x" * pad_bytes,))
        conn.commit()
        conn.close()

    def test_no_backup_files_is_error(self):
        findings = hr.check_backup()
        daily = find(findings, "backup:daily_files")
        self.assertEqual(daily[0].level, hr.ERROR)

    def test_missing_backup_dir_is_warning_not_error(self):
        shutil.rmtree(self.backup_dir)
        findings = hr.check_backup()
        daily = find(findings, "backup:daily_files")
        self.assertEqual(daily[0].level, hr.WARNING)

    def test_old_backup_file_is_flagged(self):
        f = self.backup_dir / "garmin-20260701.db"
        self._write_valid_sqlite(f)
        old_time = (datetime.now() - timedelta(hours=100)).timestamp()
        import os as _os
        _os.utime(f, (old_time, old_time))

        findings = hr.check_backup()
        daily = find(findings, "backup:daily_files")
        self.assertEqual(daily[0].level, hr.ERROR)
        self.assertIn("เก่ามาก", daily[0].message)

    def test_fresh_reasonable_backup_is_ok(self):
        f = self.backup_dir / "garmin-20260806.db"
        self._write_valid_sqlite(f)
        findings = hr.check_backup()
        daily = find(findings, "backup:daily_files")
        self.assertEqual(daily[0].level, hr.OK)
        self.assertIn("quick_check", daily[0].message)

    def test_tiny_backup_file_is_error(self):
        f = self.backup_dir / "garmin-20260806.db"
        f.write_bytes(b"x")  # เล็กกว่า BACKUP_MIN_BYTES มาก — เปิดเป็น sqlite ไม่ได้ด้วยซ้ำ
        findings = hr.check_backup()
        daily = find(findings, "backup:daily_files")
        self.assertEqual(daily[0].level, hr.ERROR)

    def test_corrupted_backup_file_is_error_even_when_size_looks_fine(self):
        # ข้อกำหนดสำคัญ: ห้ามใช้ขนาดไฟล์ตัดสินเพียงอย่างเดียว — ไฟล์ที่ขนาดดูปกติ
        # (เกิน BACKUP_MIN_BYTES) แต่เนื้อหาไม่ใช่ sqlite ที่ใช้งานได้ ต้องโดน ERROR จาก quick_check
        f = self.backup_dir / "garmin-20260806.db"
        f.write_bytes(b"garbage-not-sqlite-" * 1000)  # ~19KB มากกว่า BACKUP_MIN_BYTES แต่ใช้งานไม่ได้
        self.assertGreater(f.stat().st_size, hr.BACKUP_MIN_BYTES)
        findings = hr.check_backup()
        daily = find(findings, "backup:daily_files")
        self.assertEqual(daily[0].level, hr.ERROR)
        self.assertIn("เปิด/ตรวจสอบไม่ผ่าน", daily[0].message)

    def test_lane_reported_failure_is_error(self):
        self.write_lane_status("backup", datetime.now(), ok=False, reason="robocopy")
        findings = hr.check_backup()
        lane = find(findings, "backup:lane_status")
        self.assertEqual(lane[0].level, hr.ERROR)


class DiskSpaceTests(unittest.TestCase):
    def _fake_usage(self, total_gb, free_gb):
        total = int(total_gb * 1024 ** 3)
        free = int(free_gb * 1024 ** 3)
        return lambda path: type("Usage", (), {"total": total, "used": total - free, "free": free})()

    def test_low_disk_space_is_error(self):
        findings = hr.check_disk_space(disk_usage=self._fake_usage(500, 1))
        self.assertEqual(findings[0].level, hr.ERROR)

    def test_warning_band(self):
        # 7 GB / 100 GB = 7% ว่าง: พ้นเกณฑ์ ERROR (2 GB / 3%) แต่ยังต่ำกว่าเกณฑ์ WARNING (5 GB / 10%)
        findings = hr.check_disk_space(disk_usage=self._fake_usage(100, 7))
        self.assertEqual(findings[0].level, hr.WARNING)

    def test_plenty_of_space_is_ok(self):
        findings = hr.check_disk_space(disk_usage=self._fake_usage(500, 300))
        self.assertEqual(findings[0].level, hr.OK)

    def test_disk_usage_error_is_warning_not_crash(self):
        def boom(path):
            raise OSError("no such drive")
        findings = hr.check_disk_space(disk_usage=boom)
        self.assertEqual(findings[0].level, hr.WARNING)

    def test_backup_volume_is_checked_separately_from_live_data_volume(self):
        usages = iter((
            self._fake_usage(500, 300)("data"),
            self._fake_usage(100, 1)("backup"),
        ))
        findings = hr.check_disk_space(disk_usage=lambda path: next(usages))
        self.assertEqual(len(findings), 2)
        self.assertEqual(findings[0].level, hr.OK)
        self.assertEqual(findings[1].level, hr.ERROR)
        self.assertEqual(findings[1].check, "disk_space:backup")


class DatetimeNormalizationTests(IsolatedHealthDirMixin, unittest.TestCase):
    """เทส regression ของบั๊กจริงที่พังบน Windows: 'can't compare offset-naive and
    offset-aware datetimes' ใน check_unfinished_runs() — marker เขียนโดย PowerShell
    (Get-Date).ToString("o") ซึ่งมี timezone offset (aware) ส่วน run_at ใน sync_lane
    เขียนโดย Python datetime.now().isoformat() ซึ่งเป็น naive"""

    def test_started_aware_run_at_naive_does_not_crash(self):
        # started_at แบบมี offset (รูปแบบจริงจาก prep_log.ps1), run_at แบบ naive
        # (รูปแบบจริงจาก fetch_all.py) — คู่นี้คือคู่ที่ crash จริงบน Windows
        self.write_raw_marker("sync_run_start.txt", "2026-08-06T08:14:22.123456+07:00")
        self.write_raw_lane("full", "2026-08-06T09:30:00")
        try:
            findings = hr.check_unfinished_runs(now=datetime(2026, 8, 6, 10, 0, 0))
        except TypeError as e:
            self.fail(f"check_unfinished_runs ต้องไม่ crash เมื่อ marker/lane คนละแบบ aware/naive: {e}")
        self.assertIsInstance(findings, list)

    def test_started_naive_run_at_aware_does_not_crash(self):
        self.write_raw_marker("sync_fast_run_start.txt", "2026-08-06T08:00:00")
        self.write_raw_lane("fast", "2026-08-06T08:05:00+00:00")
        try:
            findings = hr.check_unfinished_runs(now=datetime(2026, 8, 6, 9, 0, 0))
        except TypeError as e:
            self.fail(f"check_unfinished_runs ต้องไม่ crash เมื่อ marker/lane คนละแบบ aware/naive: {e}")
        self.assertIsInstance(findings, list)

    def test_both_aware_different_timezones_compares_correctly(self):
        # started_at 09:00 ที่ +07:00 (ไทย) = 02:00 UTC | run_at 03:00 ที่ +00:00 (UTC)
        # = หลัง started_at 1 ชม. จริง ๆ (ไม่ใช่แค่ตัวเลขนาฬิกาบังเอิญมากกว่ากัน) -> ต้องถือว่า "จบแล้ว"
        self.write_raw_marker("sync_wellness_run_start.txt", "2026-08-06T09:00:00+07:00")
        self.write_raw_lane("wellness", "2026-08-06T03:00:00+00:00")
        findings = hr.check_unfinished_runs(now=datetime(2026, 8, 6, 10, 0, 0, tzinfo=timezone.utc))
        wellness = [f for f in findings if f.check.startswith("unfinished_run:wellness")]
        self.assertEqual(wellness, [], "เทียบข้ามโซนเวลาแล้วต้องรู้ว่ารอบจบแล้ว ไม่ใช่ยังไม่จบ")

    def test_both_aware_different_timezones_still_unfinished_when_truly_unfinished(self):
        # started_at 09:00+07:00 = 02:00 UTC | run_at ก่อนหน้านั้นจริง (01:00 UTC) = ยังไม่จบจริง
        self.write_raw_marker("sync_deep_run_start.txt", "2026-08-06T09:00:00+07:00")
        self.write_raw_lane("deep", "2026-08-06T01:00:00+00:00")
        findings = hr.check_unfinished_runs(
            now=datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc))  # เกิน grace (90 นาที) ของ deep
        deep = [f for f in findings if f.check.startswith("unfinished_run:deep")]
        self.assertEqual(len(deep), 1)
        self.assertEqual(deep[0].level, hr.ERROR)

    def test_both_naive_still_works_as_before(self):
        self.write_raw_marker("sync_reconcile_run_start.txt", "2026-08-06T08:00:00")
        self.write_raw_lane("reconcile", "2026-08-06T08:05:00")
        findings = hr.check_unfinished_runs(now=datetime(2026, 8, 6, 9, 0, 0))
        reconcile = [f for f in findings if f.check.startswith("unfinished_run:reconcile")]
        self.assertEqual(reconcile, [], "naive คู่กันเหมือนเดิม (ตีความโซนเดียวกัน) ต้องยังทำงานถูกเหมือนก่อนแก้")

    def test_unparseable_marker_reports_finding_not_crash(self):
        self.write_raw_marker("sync_backup_run_start.txt", "not-a-real-timestamp")
        try:
            findings = hr.check_unfinished_runs()
        except Exception as e:
            self.fail(f"marker พังต้องได้ finding ไม่ใช่ exception: {e}")
        backup = [f for f in findings if f.check.startswith("unfinished_run:backup")]
        self.assertEqual(len(backup), 1)
        self.assertEqual(backup[0].level, hr.WARNING)
        self.assertIn("อ่านรูปแบบเวลาไม่ได้", backup[0].message)

    def test_unparseable_lane_run_at_reports_finding_not_crash(self):
        self.write_raw_lane("fast", "definitely-not-a-timestamp")
        try:
            findings = hr.check_lane_freshness()
        except Exception as e:
            self.fail(f"run_at พังต้องได้ finding ไม่ใช่ exception: {e}")
        fast = [f for f in findings if f.check == "lane_freshness:fast"]
        self.assertEqual(fast[0].level, hr.WARNING)
        self.assertIn("รูปแบบเวลาอ่านไม่ได้", fast[0].message)


class LaneLimitConsistencyTests(unittest.TestCase):
    def _write(self, tmp, name, content):
        p = Path(tmp) / name
        p.write_text(content, encoding="utf-8")
        return p

    def test_mismatched_limits_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            dash = self._write(tmp, "dashboard.py", (
                'LANE_STALE_LIMIT_MIN = {\n'
                '    "full": 900, "fast": 75, "wellness": 90,\n'
                '    "reconcile": 12240, "deep": 44640, "backup": 1800,\n'
                '}\n'
            ))
            # backup ไม่ตรงกันโดยตั้งใจ (1800 vs 999)
            watch = self._write(tmp, "notify_sync.ps1", (
                '$STALE_LIMIT_MIN = [ordered]@{ full = 900; fast = 75; wellness = 90\n'
                '                               reconcile = 12240; deep = 44640; backup = 999 }\n'
            ))
            findings = hr.check_lane_limit_consistency(dashboard_path=dash, watchdog_path=watch)
            self.assertEqual(findings[0].level, hr.ERROR)
            self.assertIn("ไม่ตรงกัน", findings[0].message)

    def test_missing_lane_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            dash = self._write(tmp, "dashboard.py", (
                'LANE_STALE_LIMIT_MIN = {"full": 900, "fast": 75}\n'
            ))
            watch = self._write(tmp, "notify_sync.ps1", (
                '$STALE_LIMIT_MIN = [ordered]@{ full = 900; fast = 75 }\n'
            ))
            findings = hr.check_lane_limit_consistency(dashboard_path=dash, watchdog_path=watch)
            self.assertEqual(findings[0].level, hr.ERROR)
            self.assertIn("ไม่ครบ 6 สาย", findings[0].message)


class LaneLimitConsistencyRealFilesTest(unittest.TestCase):
    """ข้อยกเว้นเดียวที่อ่านไฟล์จริงของโปรเจกต์ — อ่าน source code อย่างเดียว (ast/regex)
    ไม่แตะ garmin/data และไม่เขียนอะไรทั้งสิ้น พิสูจน์ว่าของที่ deploy จริงยังตรงกัน"""

    def test_real_dashboard_and_watchdog_agree(self):
        findings = hr.check_lane_limit_consistency()
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, hr.OK, msg=findings[0].message)


class PrivateAclChecksTests(unittest.TestCase):
    def test_exact_private_acl_is_ok(self):
        findings = hr.check_private_acls(provider=lambda: {
            "ok": True,
            "available": True,
            "scanned": 17,
            "problems": [],
        })
        self.assertEqual(findings[0].level, hr.OK)
        self.assertIn("17", findings[0].message)

    def test_acl_drift_is_error_without_disclosing_private_paths(self):
        findings = hr.check_private_acls(provider=lambda: {
            "ok": False,
            "available": True,
            "scanned": 17,
            "problems": [
                {"path": r"D:\\private\\athlete-name", "code": "unexpected_ace"},
                {"path": r"D:\\private\\athlete-name", "code": "wrong_owner"},
            ],
        })
        self.assertEqual(findings[0].level, hr.ERROR)
        self.assertIn("unexpected_ace", findings[0].message)
        self.assertNotIn("athlete-name", findings[0].message)

    def test_acl_check_unavailable_off_windows_is_warning(self):
        def unavailable():
            raise hr.PrivateAclUnavailable("not Windows")

        findings = hr.check_private_acls(provider=unavailable)
        self.assertEqual(findings[0].level, hr.WARNING)

    def test_default_provider_is_read_only_recursive_and_checks_task_users(self):
        completed = type("Completed", (), {
            "returncode": 0,
            "stdout": b'{"ok":true,"available":true,"scanned":4,"problems":[]}',
            "stderr": b"",
        })()
        with (
            mock.patch.object(hr.os, "name", "nt"),
            mock.patch.object(hr.subprocess, "run", return_value=completed) as run,
        ):
            payload = hr.default_private_acl_provider()

        self.assertTrue(payload["ok"])
        command = run.call_args.args[0]
        self.assertIn("-CheckOnly", command)
        self.assertIn("-Recurse", command)
        self.assertIn("-CheckTaskPrincipals", command)
        self.assertNotIn("-Targets", command)


class HealthcheckSecretStorageChecksTests(unittest.TestCase):
    def test_dpapi_only_storage_is_ok(self):
        findings = hr.check_healthcheck_secret_storage(
            provider=lambda: {"dpapi_present": True, "machine_value_present": False}
        )
        self.assertEqual(findings[0].level, hr.OK)

    def test_machine_scope_copy_is_error_without_printing_value(self):
        findings = hr.check_healthcheck_secret_storage(
            provider=lambda: {"dpapi_present": True, "machine_value_present": True}
        )
        self.assertEqual(findings[0].level, hr.ERROR)
        self.assertIn("machine-scope", findings[0].message)
        self.assertNotIn("hc-ping.com", findings[0].message)

    def test_missing_optional_configuration_is_warning(self):
        findings = hr.check_healthcheck_secret_storage(
            provider=lambda: {"dpapi_present": False, "machine_value_present": False}
        )
        self.assertEqual(findings[0].level, hr.WARNING)

    @unittest.skipUnless(os.name == "nt", "Windows registry metadata test")
    def test_presence_probe_does_not_need_to_read_value_data(self):
        self.assertFalse(
            hr._machine_environment_value_present(
                "RUN_PERFORMANCE_SYNTHETIC_VALUE_THAT_DOES_NOT_EXIST"
            )
        )


class ReportOutputTests(IsolatedHealthDirMixin, unittest.TestCase):
    def test_exit_code_zero_when_no_error(self):
        fixed = [hr.Finding("x", hr.OK, "fine"), hr.Finding("y", hr.WARNING, "meh")]
        with mock.patch.object(hr, "run_all_checks", return_value=fixed):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = hr.main([])
        self.assertEqual(code, 0)

    def test_exit_code_one_when_any_error(self):
        fixed = [hr.Finding("x", hr.OK, "fine"), hr.Finding("y", hr.ERROR, "broken")]
        with mock.patch.object(hr, "run_all_checks", return_value=fixed):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = hr.main([])
        self.assertEqual(code, 1)

    def test_text_output_contains_all_findings(self):
        fixed = [hr.Finding("checkA", hr.OK, "hello"), hr.Finding("checkB", hr.ERROR, "boom")]
        with mock.patch.object(hr, "run_all_checks", return_value=fixed):
            buf = io.StringIO()
            with redirect_stdout(buf):
                hr.main([])
        out = buf.getvalue()
        self.assertIn("checkA", out)
        self.assertIn("checkB", out)
        self.assertIn("OK", out)
        self.assertIn("ERROR", out)

    def test_json_output_is_valid_and_matches_findings(self):
        fixed = [hr.Finding("checkA", hr.OK, "hello"), hr.Finding("checkB", hr.WARNING, "meh")]
        with mock.patch.object(hr, "run_all_checks", return_value=fixed):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = hr.main(["--json"])
        self.assertEqual(code, 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(len(payload["findings"]), 2)
        self.assertEqual(payload["summary"]["ok"], 1)
        self.assertEqual(payload["summary"]["warning"], 1)
        self.assertEqual(payload["summary"]["error"], 0)
        self.assertEqual(payload["findings"][1]["check"], "checkB")


class ProductionDataIsolationTests(unittest.TestCase):
    """สัญญาว่าเทสในไฟล์นี้ไม่มีตัวไหนแตะ garmin/data ของจริงเลย"""

    def test_full_suite_never_touches_the_real_data_dir(self):
        if PRODUCTION_DATA_DIR.exists():
            before = sorted(p.relative_to(PRODUCTION_DATA_DIR) for p in PRODUCTION_DATA_DIR.rglob("*"))
        else:
            before = None

        # รันเช็คทั้งหมดหนึ่งรอบด้วย DATA_DIR/BACKUP_DIR ที่ชี้ temp dir (ตาม mixin ปกติ)
        data_dir = Path(tempfile.mkdtemp(prefix="health-data-"))
        backup_dir = Path(tempfile.mkdtemp(prefix="health-backup-"))
        try:
            prev_data = hr.use_data_dir(data_dir)
            prev_backup = hr.use_backup_dir(backup_dir)
            try:
                hr.run_all_checks(
                    schtasks_provider=lambda name: (_ for _ in ()).throw(
                        hr.SchtasksUnavailable("test")
                    ),
                    acl_provider=lambda: {
                        "ok": True, "available": True, "scanned": 0, "problems": []
                    },
                    healthcheck_storage_provider=lambda: {
                        "dpapi_present": False, "machine_value_present": False
                    },
                )
            finally:
                hr.use_data_dir(prev_data)
                hr.use_backup_dir(prev_backup)
        finally:
            shutil.rmtree(data_dir, ignore_errors=True)
            shutil.rmtree(backup_dir, ignore_errors=True)

        if before is None:
            self.assertFalse(PRODUCTION_DATA_DIR.exists(),
                              "health_report ต้องไม่สร้างโฟลเดอร์ garmin/data ขึ้นมาใหม่")
        else:
            after = sorted(p.relative_to(PRODUCTION_DATA_DIR) for p in PRODUCTION_DATA_DIR.rglob("*"))
            self.assertEqual(before, after, "garmin/data ของจริงถูกแตะระหว่างรันเทส!")


if __name__ == "__main__":
    unittest.main()
