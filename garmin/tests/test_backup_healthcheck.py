"""เทส Healthchecks.io pilot ของสาย backup (backup_db.py) — mock network ทั้งหมด
ไม่มีการยิง HTTP จริงแม้แต่ครั้งเดียวในไฟล์นี้ และไม่มีเคสไหนแตะ garmin/data หรือ
C:\\Backup ของจริงเลย (mock snapshot/rotate_daily/write_status ทุกเคสที่เรียก main())"""

import importlib.util
import io
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest import mock

GARMIN_ROOT = Path(__file__).resolve().parents[1]


def load_script(name, filename):
    spec = importlib.util.spec_from_file_location(name, GARMIN_ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backup_db = load_script("garmin_backup_db_healthcheck_under_test", "backup_db.py")


class DataDirIsolationTests(unittest.TestCase):
    """ต้นทาง DB และสถานะ backup ต้องย้ายตาม GARMIN_DATA_DIR ทั้งตอน import/เทส."""

    def test_import_honors_garmin_data_dir_for_every_source_path(self):
        with tempfile.TemporaryDirectory(prefix="garmin-backup-data-") as temp:
            isolated_dir = Path(temp)
            with mock.patch.dict(
                os.environ, {"GARMIN_DATA_DIR": str(isolated_dir)}
            ):
                isolated = load_script(
                    "garmin_backup_db_data_dir_probe", "backup_db.py"
                )

            self.assertEqual(isolated.DATA_DIR, isolated_dir)
            self.assertEqual(isolated.DB_PATH, isolated_dir / "garmin.db")
            self.assertEqual(
                isolated.LANE_STATUS,
                isolated_dir / "sync_lane" / "backup.json",
            )

    def test_use_data_dir_repoints_database_and_lane_status_together(self):
        with tempfile.TemporaryDirectory(prefix="garmin-backup-data-") as temp:
            isolated_dir = Path(temp)
            previous = backup_db.use_data_dir(isolated_dir)
            try:
                self.assertEqual(backup_db.DATA_DIR, isolated_dir)
                self.assertEqual(backup_db.DB_PATH, isolated_dir / "garmin.db")
                self.assertEqual(
                    backup_db.LANE_STATUS,
                    isolated_dir / "sync_lane" / "backup.json",
                )
            finally:
                backup_db.use_data_dir(previous)

    def test_missing_source_database_is_never_created_by_snapshot(self):
        with tempfile.TemporaryDirectory(prefix="garmin-backup-data-") as temp:
            root = Path(temp)
            missing_source = root / "isolated" / "garmin.db"
            destination = root / "backup" / "garmin.db"
            missing_source.parent.mkdir()

            with self.assertRaises(FileNotFoundError):
                backup_db.snapshot(missing_source, destination)

            self.assertFalse(missing_source.exists())
            self.assertFalse(destination.exists())

    def test_snapshot_still_reads_an_existing_wal_database(self):
        with tempfile.TemporaryDirectory(prefix="garmin-backup-data-") as temp:
            root = Path(temp)
            source = root / "isolated" / "garmin.db"
            destination = root / "backup" / "garmin.db"
            source.parent.mkdir()
            writer = sqlite3.connect(source)
            try:
                writer.execute("PRAGMA journal_mode=WAL")
                writer.execute("CREATE TABLE fact_activity (activity_id INTEGER)")
                writer.executemany(
                    "INSERT INTO fact_activity VALUES (?)", [(1,), (2,)]
                )
                writer.commit()

                rows = backup_db.snapshot(source, destination)
            finally:
                writer.close()

            copied = sqlite3.connect(destination)
            try:
                copied_rows = copied.execute(
                    "SELECT COUNT(*) FROM fact_activity"
                ).fetchone()[0]
            finally:
                copied.close()
            self.assertEqual((rows, copied_rows), (2, 2))

    def test_snapshot_rejects_live_database_as_its_own_destination(self):
        with tempfile.TemporaryDirectory(prefix="garmin-backup-data-") as temp:
            database = Path(temp) / "garmin.db"
            conn = sqlite3.connect(database)
            conn.execute("CREATE TABLE fact_activity (activity_id INTEGER)")
            conn.commit()
            conn.close()
            before = database.read_bytes()

            with self.assertRaises(ValueError):
                backup_db.snapshot(database, database)

            self.assertEqual(database.read_bytes(), before)

    def test_daily_copy_is_valid_sqlite_and_leaves_no_partial_file(self):
        with tempfile.TemporaryDirectory(prefix="garmin-backup-daily-") as temp:
            root = Path(temp)
            snapshot = root / "snapshot.db"
            daily = root / "daily"
            conn = sqlite3.connect(snapshot)
            conn.execute("CREATE TABLE fact_activity (activity_id INTEGER)")
            conn.execute("INSERT INTO fact_activity VALUES (7)")
            conn.commit()
            conn.close()

            backup_db.rotate_daily(daily, snapshot)

            copies = list(daily.glob("garmin-*.db"))
            self.assertEqual(len(copies), 1)
            check = sqlite3.connect(copies[0])
            try:
                self.assertEqual(
                    check.execute("PRAGMA integrity_check").fetchone()[0], "ok"
                )
            finally:
                check.close()
            self.assertEqual(list(daily.glob("*.tmp")), [])

    def test_lane_status_write_failure_is_reported_to_caller(self):
        with tempfile.TemporaryDirectory(prefix="garmin-backup-status-") as temp:
            previous = backup_db.use_data_dir(temp)
            try:
                blocker = Path(temp) / "sync_lane"
                blocker.write_text("not a directory", encoding="ascii")
                written = backup_db.write_status(
                    datetime.now(), True, "ok", []
                )
            finally:
                backup_db.use_data_dir(previous)
            self.assertFalse(written)


class _FakeResponse:
    """จำลอง context manager ที่ urllib.request.urlopen() คืนตอนสำเร็จ"""

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class EnvVarIsolatedMixin:
    """กันไม่ให้ HEALTHCHECK_BACKUP_URL หลุดข้ามเคส/หลุดเข้า environment จริงของเครื่อง"""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        os.environ.pop(backup_db.HEALTHCHECK_ENV_VAR, None)
        self.addCleanup(patcher.stop)
        self.health_data = tempfile.TemporaryDirectory(
            prefix="garmin-healthcheck-secret-"
        )
        self.addCleanup(self.health_data.cleanup)
        previous = backup_db.use_data_dir(self.health_data.name)
        self.addCleanup(backup_db.use_data_dir, previous)


class HealthcheckSecretStorageTests(EnvVarIsolatedMixin, unittest.TestCase):
    def test_dpapi_file_is_used_when_environment_is_absent(self):
        encrypted = Path(self.health_data.name) / backup_db.HEALTHCHECK_DPAPI_FILE
        encrypted.write_bytes(b"synthetic-ciphertext")
        with mock.patch.object(backup_db.os, "name", "nt"), mock.patch.object(
            backup_db, "_dpapi_unprotect",
            return_value="https://hc-ping.com/synthetic-check",
        ) as decrypt:
            resolved = backup_db.get_healthcheck_url()
        self.assertEqual(resolved, "https://hc-ping.com/synthetic-check")
        decrypt.assert_called_once_with(b"synthetic-ciphertext")

    def test_environment_is_fallback_when_dpapi_file_is_absent(self):
        os.environ[backup_db.HEALTHCHECK_ENV_VAR] = "https://hc-ping.com/env-check"
        with mock.patch.object(backup_db, "_dpapi_unprotect") as decrypt:
            self.assertEqual(
                backup_db.get_healthcheck_url(),
                "https://hc-ping.com/env-check",
            )
        decrypt.assert_not_called()

    def test_dpapi_file_wins_over_stale_machine_environment(self):
        encrypted = Path(self.health_data.name) / backup_db.HEALTHCHECK_DPAPI_FILE
        encrypted.write_bytes(b"protected")
        os.environ[backup_db.HEALTHCHECK_ENV_VAR] = "https://hc-ping.com/stale-env"
        with mock.patch.object(backup_db.os, "name", "nt"), mock.patch.object(
            backup_db, "_dpapi_unprotect",
            return_value="https://hc-ping.com/protected-file",
        ):
            resolved = backup_db.get_healthcheck_url()
        self.assertEqual(resolved, "https://hc-ping.com/protected-file")

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI integration test")
    def test_windows_dpapi_current_user_round_trip(self):
        secret = "https://hc-ping.com/synthetic-dpapi-roundtrip"
        path = Path(self.health_data.name) / "roundtrip.dpapi"
        env = os.environ.copy()
        env["RUN_PERF_DPAPI_TEST_VALUE"] = secret
        env["RUN_PERF_DPAPI_TEST_PATH"] = str(path)
        script = (
            "Add-Type -AssemblyName System.Security;"
            "$raw=[Text.Encoding]::UTF8.GetBytes($env:RUN_PERF_DPAPI_TEST_VALUE);"
            "$blob=[Security.Cryptography.ProtectedData]::Protect("
            "$raw,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser);"
            "[IO.File]::WriteAllBytes($env:RUN_PERF_DPAPI_TEST_PATH,$blob)"
        )
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", script],
            env=env,
            capture_output=True,
            text=False,
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertEqual(backup_db._dpapi_unprotect(path.read_bytes()), secret)


class HealthcheckPingUnitTests(EnvVarIsolatedMixin, unittest.TestCase):
    """เทส notify_healthcheck()/_healthcheck_ping() แยกจาก main() ล้วน ๆ"""

    def test_no_env_var_never_touches_network(self):
        with mock.patch("urllib.request.urlopen") as m:
            backup_db.notify_healthcheck("start")
        m.assert_not_called()

    def test_start_hits_slash_start_suffix(self):
        os.environ[backup_db.HEALTHCHECK_ENV_VAR] = "https://hc-ping.com/abc123"
        with mock.patch("urllib.request.urlopen", return_value=_FakeResponse()) as m:
            backup_db.notify_healthcheck("start")
        self.assertEqual(m.call_args.args[0], "https://hc-ping.com/abc123/start")

    def test_http_or_url_with_query_never_touches_network(self):
        for unsafe in (
            "http://hc-ping.com/abc123",
            "https://hc-ping.com/abc123?athlete=secret",
            "https://user:pass@hc-ping.com/abc123",
        ):
            with self.subTest(unsafe=unsafe):
                os.environ[backup_db.HEALTHCHECK_ENV_VAR] = unsafe
                with mock.patch("urllib.request.urlopen") as request:
                    backup_db.notify_healthcheck("start")
                request.assert_not_called()

    def test_success_hits_bare_url_no_suffix(self):
        os.environ[backup_db.HEALTHCHECK_ENV_VAR] = "https://hc-ping.com/abc123"
        with mock.patch("urllib.request.urlopen", return_value=_FakeResponse()) as m:
            backup_db.notify_healthcheck("success")
        self.assertEqual(m.call_args.args[0], "https://hc-ping.com/abc123")

    def test_fail_hits_slash_fail_suffix(self):
        os.environ[backup_db.HEALTHCHECK_ENV_VAR] = "https://hc-ping.com/abc123"
        with mock.patch("urllib.request.urlopen", return_value=_FakeResponse()) as m:
            backup_db.notify_healthcheck("fail")
        self.assertEqual(m.call_args.args[0], "https://hc-ping.com/abc123/fail")

    def test_url_without_trailing_slash(self):
        os.environ[backup_db.HEALTHCHECK_ENV_VAR] = "https://hc-ping.com/abc123"
        with mock.patch("urllib.request.urlopen", return_value=_FakeResponse()) as m:
            backup_db.notify_healthcheck("start")
        self.assertEqual(m.call_args.args[0], "https://hc-ping.com/abc123/start")

    def test_url_with_trailing_slash_does_not_double_up(self):
        os.environ[backup_db.HEALTHCHECK_ENV_VAR] = "https://hc-ping.com/abc123/"
        with mock.patch("urllib.request.urlopen", return_value=_FakeResponse()) as m:
            backup_db.notify_healthcheck("start")
        self.assertEqual(m.call_args.args[0], "https://hc-ping.com/abc123/start")

    def test_timeout_is_swallowed(self):
        os.environ[backup_db.HEALTHCHECK_ENV_VAR] = "https://hc-ping.com/abc123"
        with mock.patch("urllib.request.urlopen", side_effect=socket.timeout("timed out")):
            try:
                backup_db.notify_healthcheck("start")
            except Exception as e:
                self.fail(f"notify_healthcheck ต้องไม่ปล่อย exception ออกมาเลย: {e}")

    def test_dns_error_is_swallowed(self):
        os.environ[backup_db.HEALTHCHECK_ENV_VAR] = "https://no-such-host.invalid/abc"
        err = urllib.error.URLError(socket.gaierror("Name or service not known"))
        with mock.patch("urllib.request.urlopen", side_effect=err):
            try:
                backup_db.notify_healthcheck("start")
            except Exception as e:
                self.fail(f"notify_healthcheck ต้องไม่ปล่อย exception ออกมาเลย: {e}")

    def test_generic_connection_error_is_swallowed(self):
        os.environ[backup_db.HEALTHCHECK_ENV_VAR] = "https://hc-ping.com/abc123"
        with mock.patch("urllib.request.urlopen", side_effect=ConnectionRefusedError("refused")):
            try:
                backup_db.notify_healthcheck("fail")
            except Exception as e:
                self.fail(f"notify_healthcheck ต้องไม่ปล่อย exception ออกมาเลย: {e}")

    def test_timeout_param_is_five_seconds(self):
        os.environ[backup_db.HEALTHCHECK_ENV_VAR] = "https://hc-ping.com/abc123"
        with mock.patch("urllib.request.urlopen", return_value=_FakeResponse()) as m:
            backup_db.notify_healthcheck("start")
        self.assertEqual(m.call_args.kwargs.get("timeout"), backup_db.HEALTHCHECK_TIMEOUT_SEC)
        self.assertEqual(backup_db.HEALTHCHECK_TIMEOUT_SEC, 5)

    def test_never_prints_or_logs_the_url(self):
        secret_url = "https://hc-ping.com/super-secret-check-id-123"
        os.environ[backup_db.HEALTHCHECK_ENV_VAR] = secret_url
        buf = io.StringIO()
        with mock.patch("urllib.request.urlopen", return_value=_FakeResponse()):
            with redirect_stdout(buf):
                backup_db.notify_healthcheck("start")
                backup_db.notify_healthcheck("success")
                backup_db.notify_healthcheck("fail")
        output = buf.getvalue()
        self.assertNotIn(secret_url, output)
        self.assertNotIn("hc-ping.com", output)


class MainPingSequenceTests(EnvVarIsolatedMixin, unittest.TestCase):
    """เทสว่า main() เรียก notify_healthcheck ถูกจังหวะ/ถูกจำนวนครั้ง — mock
    notify_healthcheck ไปเลยที่นี่ (แยกจาก HealthcheckPingUnitTests ที่เทส network จริง)
    และ mock snapshot/rotate_daily/write_status ทุกเคส ไม่แตะไฟล์จริงเลย"""

    def _run_main(self, snapshot_ok=True, snapshot_rows=5, robocopy_exit=0):
        argv = ["backup_db.py", "--dest", "/tmp/fake-dest", "--robocopy-exit", str(robocopy_exit)]
        snapshot_kwargs = ({"return_value": snapshot_rows} if snapshot_ok
                            else {"side_effect": RuntimeError("boom")})
        with mock.patch.object(backup_db, "notify_healthcheck") as ping_mock, \
             mock.patch.object(backup_db, "write_status") as status_mock, \
             mock.patch.object(backup_db, "snapshot", **snapshot_kwargs), \
             mock.patch.object(backup_db, "rotate_daily"), \
             mock.patch.object(sys, "argv", argv):
            code = backup_db.main()
        return code, ping_mock, status_mock

    def test_success_pings_start_then_success_exactly_once_each(self):
        code, ping_mock, _ = self._run_main(snapshot_ok=True, robocopy_exit=0)
        self.assertEqual(code, 0)
        kinds = [c.args[0] for c in ping_mock.call_args_list]
        self.assertEqual(kinds, ["start", "success"])

    def test_snapshot_failure_pings_start_then_fail_exactly_once_each(self):
        code, ping_mock, _ = self._run_main(snapshot_ok=False)
        self.assertEqual(code, 1)
        kinds = [c.args[0] for c in ping_mock.call_args_list]
        self.assertEqual(kinds, ["start", "fail"])

    def test_robocopy_failure_pings_start_then_fail_exactly_once_each(self):
        code, ping_mock, _ = self._run_main(snapshot_ok=True, robocopy_exit=8)
        self.assertEqual(code, 1)
        kinds = [c.args[0] for c in ping_mock.call_args_list]
        self.assertEqual(kinds, ["start", "fail"])

    def test_never_pings_the_same_kind_twice_in_one_round(self):
        for snapshot_ok, robocopy_exit in ((True, 0), (True, 8), (False, 0)):
            with self.subTest(snapshot_ok=snapshot_ok, robocopy_exit=robocopy_exit):
                _, ping_mock, _ = self._run_main(snapshot_ok=snapshot_ok, robocopy_exit=robocopy_exit)
                kinds = [c.args[0] for c in ping_mock.call_args_list]
                self.assertEqual(len(kinds), len(set(kinds)), f"kind ซ้ำในรอบเดียว: {kinds}")
                self.assertEqual(kinds[0], "start")
                self.assertEqual(len(kinds), 2, "ต้องมีแค่ start + ผลสุดท้ายอย่างละ 1 ครั้งต่อรอบ")

    def test_daily_rotation_failure_is_a_real_backup_failure(self):
        argv = [
            "backup_db.py", "--dest", "/tmp/fake-dest",
            "--daily", "/tmp/fake-daily", "--robocopy-exit", "0",
        ]
        with mock.patch.object(backup_db, "notify_healthcheck") as ping_mock, \
             mock.patch.object(backup_db, "write_status") as status_mock, \
             mock.patch.object(backup_db, "snapshot", return_value=5), \
             mock.patch.object(
                 backup_db, "rotate_daily", side_effect=OSError("disk full")
             ), \
             mock.patch.object(sys, "argv", argv):
            code = backup_db.main()

        self.assertEqual(code, 1)
        self.assertEqual([c.args[0] for c in ping_mock.call_args_list], ["start", "fail"])
        self.assertFalse(status_mock.call_args.args[1])
        self.assertEqual(status_mock.call_args.args[2], "daily")

    def test_lane_status_write_failure_turns_success_into_failure(self):
        argv = ["backup_db.py", "--dest", "/tmp/fake-dest", "--robocopy-exit", "0"]
        with mock.patch.object(backup_db, "notify_healthcheck") as ping_mock, \
             mock.patch.object(backup_db, "write_status", return_value=False), \
             mock.patch.object(backup_db, "snapshot", return_value=5), \
             mock.patch.object(sys, "argv", argv):
            code = backup_db.main()

        self.assertEqual(code, 1)
        self.assertEqual([c.args[0] for c in ping_mock.call_args_list], ["start", "fail"])


class MainExitCodeUnaffectedByHealthcheckOutageTests(EnvVarIsolatedMixin, unittest.TestCase):
    """ข้อกำหนดสำคัญที่สุด: Healthchecks.io ล่ม/เน็ตขาด ต้องไม่ทำให้ backup ล้มตาม หรือ
    เปลี่ยน exit code เลยแม้นิดเดียว — ใช้ notify_healthcheck ของจริง (ไม่ mock) แต่ mock
    แค่ urlopen ให้พังทุกครั้ง เพื่อพิสูจน์ end-to-end ว่า main() คืนผลเดิมเป๊ะ"""

    def setUp(self):
        super().setUp()
        os.environ[backup_db.HEALTHCHECK_ENV_VAR] = "https://hc-ping.com/down-check"

    def _run_main_with_broken_network(self, snapshot_ok, robocopy_exit):
        argv = ["backup_db.py", "--dest", "/tmp/fake-dest", "--robocopy-exit", str(robocopy_exit)]
        snapshot_kwargs = ({"return_value": 3} if snapshot_ok
                            else {"side_effect": RuntimeError("boom")})
        with mock.patch.object(sys, "argv", argv), \
             mock.patch.object(backup_db, "write_status"), \
             mock.patch.object(backup_db, "snapshot", **snapshot_kwargs), \
             mock.patch.object(backup_db, "rotate_daily"), \
             mock.patch("urllib.request.urlopen", side_effect=socket.timeout("simulated outage")):
            return backup_db.main()

    def test_success_path_same_exit_code_when_healthchecks_is_down(self):
        code = self._run_main_with_broken_network(snapshot_ok=True, robocopy_exit=0)
        self.assertEqual(code, 0)

    def test_snapshot_failure_same_exit_code_when_healthchecks_is_down(self):
        code = self._run_main_with_broken_network(snapshot_ok=False, robocopy_exit=0)
        self.assertEqual(code, 1)

    def test_robocopy_failure_same_exit_code_when_healthchecks_is_down(self):
        code = self._run_main_with_broken_network(snapshot_ok=True, robocopy_exit=8)
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
