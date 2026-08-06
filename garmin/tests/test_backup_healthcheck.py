"""เทส Healthchecks.io pilot ของสาย backup (backup_db.py) — mock network ทั้งหมด
ไม่มีการยิง HTTP จริงแม้แต่ครั้งเดียวในไฟล์นี้ และไม่มีเคสไหนแตะ garmin/data หรือ
C:\\Backup ของจริงเลย (mock snapshot/rotate_daily/write_status ทุกเคสที่เรียก main())"""

import importlib.util
import io
import os
import socket
import sys
import unittest
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

GARMIN_ROOT = Path(__file__).resolve().parents[1]


def load_script(name, filename):
    spec = importlib.util.spec_from_file_location(name, GARMIN_ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backup_db = load_script("garmin_backup_db_healthcheck_under_test", "backup_db.py")


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
