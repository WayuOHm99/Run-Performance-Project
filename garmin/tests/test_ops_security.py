"""Regression tests for Windows automation and local-secret hardening.

The Windows ACL integration test only touches a temporary directory.  It never
queries or changes the production token, data, backup, or Scheduled Task paths.
"""

import ast
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import unittest.mock
from datetime import datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GARMIN_ROOT = PROJECT_ROOT / "garmin"
TASKS_DIR = GARMIN_ROOT / "tasks"
ACL_SCRIPT = PROJECT_ROOT / "scripts" / "harden_private_acl.ps1"
SCHEDULER_VERIFY_SCRIPT = GARMIN_ROOT / "scripts" / "verify_scheduled_tasks.py"


# เพดานนี้มีไว้จับ "สคริปต์ค้าง" ไม่ใช่วัดความเร็วเครื่อง — Windows runner ของ GitHub
# ช้าเป็นพัก ๆ จนสปอว์นโปรเซสเกิน 30 วิได้ (CI ล้มจริง 18 ส.ค. 69 ทั้ง prep_log.ps1 และ
# setup_scheduled_tasks.ps1) งบเวลาจริงคุมด้วย timeout-minutes ของ job ไม่ใช่ตรงนี้
SUBPROCESS_TIMEOUT_SEC = 120


def load_script(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


token_generator = load_script(
    "garmin_token_generator_under_test",
    GARMIN_ROOT / "scripts" / "01_generate_token.py",
)
scheduler_verify = load_script(
    "scheduler_verify_under_test", SCHEDULER_VERIFY_SCRIPT
)


def scheduled_task_xml(
    *,
    argument='"C:\\Project\\worker.vbs"',
    interval="PT15M",
    start_boundary="2026-08-02T00:05:00+07:00",
    end_boundary=None,
    enabled=None,
    extra_action="",
):
    enabled_xml = "" if enabled is None else f"<Enabled>{str(enabled).lower()}</Enabled>"
    end_boundary_xml = (
        "" if end_boundary is None else f"<EndBoundary>{end_boundary}</EndBoundary>"
    )
    return f'''<?xml version="1.0"?>
<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Principals><Principal><LogonType>InteractiveToken</LogonType></Principal></Principals>
  <Settings>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT10M</ExecutionTimeLimit>
    <RestartOnFailure><Interval>PT30M</Interval><Count>2</Count></RestartOnFailure>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <StartWhenAvailable>true</StartWhenAvailable>
  </Settings>
  <Triggers><TimeTrigger><StartBoundary>{start_boundary}</StartBoundary>{end_boundary_xml}{enabled_xml}
    <Repetition><Interval>{interval}</Interval><Duration>P3650D</Duration></Repetition>
  </TimeTrigger></Triggers>
  <Actions><Exec><Command>wscript.exe</Command><Arguments>{argument}</Arguments>
    <WorkingDirectory>C:\\Project</WorkingDirectory></Exec>{extra_action}</Actions>
</Task>'''


class SchedulerInstalledComparisonTests(unittest.TestCase):
    NOW = datetime(2026, 8, 17, 12, tzinfo=timezone(timedelta(hours=7)))

    def expected(self):
        return {
            "exe": "wscript.exe",
            "actionCount": 1,
            "actionTypes": ["Exec"],
            "argument": '"C:\\Project\\worker.vbs"',
            "workingDirectory": "C:\\Project",
            "logonType": "InteractiveToken",
            "executionTimeLimit": "PT10M",
            "retryCount": 2,
            "retryInterval": "PT30M",
            "onBattery": True,
            "multipleInstances": "IgnoreNew",
            "startWhenAvailable": True,
            "triggers": [{
                "type": "time", "startTime": "00:05:00",
                "utcOffset": "+07:00", "endBoundary": None, "enabled": True,
                "interval": "PT15M", "duration": "P3650D",
                "windowActive": True,
            }],
        }

    def test_matching_installed_xml_has_no_drift(self):
        actual = scheduler_verify.normalize_task_xml(
            scheduled_task_xml(), now=self.NOW
        )
        self.assertEqual(scheduler_verify.compare_task(self.expected(), actual), [])

    def test_action_and_trigger_drift_are_reported_read_only(self):
        actual = scheduler_verify.normalize_task_xml(
            scheduled_task_xml(argument='"C:\\Wrong\\worker.vbs"', interval="PT1H"),
            now=self.NOW,
        )
        self.assertEqual(
            set(scheduler_verify.compare_task(self.expected(), actual)),
            {"action_arguments", "trigger_schedule"},
        )

    def test_disabled_expired_and_wrong_timezone_triggers_are_rejected(self):
        cases = (
            {"enabled": False},
            {"start_boundary": "2010-01-01T00:05:00+07:00"},
            {"start_boundary": "2026-08-02T00:05:00+00:00"},
            {"end_boundary": "2026-08-10T00:00:00+07:00"},
        )
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                actual = scheduler_verify.normalize_task_xml(
                    scheduled_task_xml(**kwargs), now=self.NOW
                )
                self.assertIn(
                    "trigger_schedule",
                    scheduler_verify.compare_task(self.expected(), actual),
                )

    def test_unexpected_non_exec_action_is_counted_and_rejected(self):
        actual = scheduler_verify.normalize_task_xml(
            scheduled_task_xml(
                extra_action=(
                    "<ComHandler><ClassId>00000000-0000-0000-0000-000000000000"
                    "</ClassId></ComHandler>"
                )
            ),
            now=self.NOW,
        )
        self.assertEqual(
            set(scheduler_verify.compare_task(self.expected(), actual)),
            {"action_count", "action_types"},
        )


class WrapperExitPropagationTests(unittest.TestCase):
    BAT_EXIT_VARS = {
        "garmin-fast-sync-auto.bat": "SYNC_EXIT",
        "garmin-wellness-sync-auto.bat": "SYNC_EXIT",
        "garmin-sync-auto.bat": "SYNC_EXIT",
        "garmin-reconcile-auto.bat": "SYNC_EXIT",
        "garmin-deepsync-auto.bat": "SYNC_EXIT",
    }

    def test_sync_batches_run_from_the_garmin_root_not_their_own_folder(self):
        """launcher อยู่ใน garmin\\tasks\\ แต่ทุก path ข้างในเขียนแบบอิงราก garmin

        ถ้าใครย้ายไฟล์แล้วลืมแก้บรรทัด cd งานจะพังเงียบ ๆ แบบเดียวกับตอนเปลี่ยนชื่อ
        โฟลเดอร์ 26 ก.ค. 69 — เทสนี้ตรึงข้อตกลงนั้นไว้
        """
        for filename in self.BAT_EXIT_VARS:
            with self.subTest(filename=filename):
                source = (TASKS_DIR / filename).read_text(encoding="utf-8-sig")
                self.assertRegex(source, r'(?im)^cd /d "%~dp0\.\."\s*$')

    def test_sync_batches_propagate_real_result_after_notification(self):
        for filename, variable in self.BAT_EXIT_VARS.items():
            with self.subTest(filename=filename):
                source = (TASKS_DIR / filename).read_text(encoding="utf-8-sig")
                self.assertRegex(
                    source,
                    rf"(?im)^exit /b %{re.escape(variable)}%\s*$",
                    f"{filename} must expose the real worker result to Task Scheduler",
                )

    def test_fast_lane_looks_back_far_enough_to_see_a_late_synced_evening_run(self):
        """สาย fast ต้องมองย้อนถึงเมื่อวาน ไม่ใช่แค่วันนี้

        นาฬิกาซิงค์เข้า Garmin ช้ากว่าเวลาวิ่งเป็นชั่วโมง และข้ามเที่ยงคืนได้
        (วัดจริง 18 ส.ค. 69: dan วิ่ง 17 ส.ค. 19:18 แต่ข้อมูลเข้า Garmin หลังเที่ยงคืน)
        ถ้าสายนี้ขอแค่ "วันนี้" กิจกรรมเย็นวานจะมองไม่เห็นไม่ว่ายิงถี่แค่ไหน
        ต้องรอสาย full รอบ 08:00/21:00 มาเก็บ — ช้าได้ถึง 13 ชม.

        การขยายหน้าต่างไม่เสีย API เพิ่ม: get_activities_by_date รับช่วงวันที่
        จึงยิงครั้งเดียวเท่ากันไม่ว่าขอ 1 วันหรือ 2 วัน
        """
        source = (TASKS_DIR / "garmin-fast-sync-auto.bat").read_text(
            encoding="utf-8-sig"
        )
        match = re.search(r"fetch_all\.py\s+--days\s+(\d+)", source)
        self.assertIsNotNone(
            match, "fast lane must pass an explicit --days window to fetch_all"
        )
        self.assertGreaterEqual(
            int(match.group(1)), 1,
            "fast lane must cover yesterday so an activity synced after midnight "
            "is picked up within one round instead of waiting for the full sync",
        )

    def test_deep_sync_propagates_drift_failure_with_explicit_context(self):
        source = (TASKS_DIR / "garmin-deepsync-auto.bat").read_text(
            encoding="ascii"
        )
        self.assertRegex(source, r'(?im)^set "DRIFT_EXIT=%ERRORLEVEL%"\s*$')
        self.assertRegex(source, r'(?im)^set "SYNC_EXIT=%DRIFT_EXIT%"\s*$')
        self.assertRegex(source, r'(?im)^set "FAILURE_CONTEXT=drift"\s*$')
        self.assertIn('-FailureContext "%FAILURE_CONTEXT%"', source)
        self.assertIn("check_drift.py --record-deep-status", source)

    def test_sync_batches_fail_closed_on_recursive_garmin_acl_hardening(self):
        for filename in self.BAT_EXIT_VARS:
            with self.subTest(filename=filename):
                source = (TASKS_DIR / filename).read_text(encoding="utf-8-sig")
                self.assertRegex(
                    source,
                    r'(?i)harden_private_acl\.ps1" -Scope Garmin -Recurse',
                )
                self.assertRegex(source, r'(?im)^set "ACL_EXIT=%ERRORLEVEL%"\s*$')
                self.assertRegex(
                    source,
                    r'(?im)^if not "%ACL_EXIT%"=="0" exit /b %ACL_EXIT%\s*$',
                )
                self.assertRegex(source, r'(?im)^set "PREP_EXIT=%ERRORLEVEL%"\s*$')
                self.assertRegex(
                    source,
                    r'(?im)^if not "%PREP_EXIT%"=="0" exit /b %PREP_EXIT%\s*$',
                )
                self.assertIn(r"C:\Backup\run-performance-logs", source)
                log_acl = source.lower().index("-scope logs -recurse")
                prep = source.lower().index('-file "scripts\\prep_log.ps1"')
                self.assertLess(log_acl, prep, "private log root must exist before marker/log writes")

    def test_backup_batch_propagates_backup_result(self):
        source = (PROJECT_ROOT / "scripts" / "สำรองข้อมูล.bat").read_text(
            encoding="ascii"
        )
        self.assertRegex(source, r"(?im)^exit /b %BACKUP_EXIT%\s*$")
        self.assertRegex(
            source,
            r'(?i)harden_private_acl\.ps1" -Scope Backup -Recurse',
        )
        self.assertRegex(
            source,
            r'(?im)^if not "%ACL_EXIT%"=="0" exit /b %ACL_EXIT%\s*$',
        )
        self.assertRegex(source, r'(?im)^set "PREP_EXIT=%ERRORLEVEL%"\s*$')
        self.assertIn(r"C:\Backup\run-performance-logs\backup-log.txt", source)
        self.assertLess(
            source.lower().index("-scope logs -recurse"),
            source.lower().index("prep_log.ps1"),
        )

    def test_hidden_launchers_return_child_exit_code(self):
        launchers = [
            PROJECT_ROOT / "scripts" / "backup-hidden.vbs",
            *sorted(TASKS_DIR.glob("garmin-*-hidden.vbs")),
        ]
        self.assertGreaterEqual(len(launchers), 6)
        for path in launchers:
            with self.subTest(path=path.name):
                source = path.read_text(encoding="utf-8-sig")
                self.assertRegex(source, r"(?i)ExitCode\s*=\s*.*\.Run\s*\(")
                self.assertRegex(source, r"(?im)^WScript\.Quit\s+ExitCode\s*$")
                self.assertTrue(source.isascii())
                self.assertNotIn("???", source)

    def test_every_tracked_batch_file_is_ascii(self):
        completed = subprocess.run(
            ["git", "ls-files", "-z", "--", "*.bat"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            check=True,
        )
        paths = [
            PROJECT_ROOT / raw.decode("utf-8")
            for raw in completed.stdout.split(b"\0")
            if raw
        ]
        self.assertTrue(paths)
        for path in paths:
            with self.subTest(path=path.relative_to(PROJECT_ROOT)):
                content = path.read_bytes()
                self.assertTrue(
                    content.isascii(),
                    "cmd.exe can split UTF-8 multibyte text into unintended commands",
                )


class WindowlessSubprocessTests(unittest.TestCase):
    """งานอัตโนมัติต้องไม่เปิดหน้าต่างที่คนปิดได้ (บทเรียนซ้ำรอบที่ 3 ของโปรเจกต์นี้)

    task ที่รันด้วย pythonw.exe ไม่มี console ของตัวเอง → Windows สร้าง console
    ใหม่ให้โปรเซสลูกที่เป็นโปรแกรม console (gh/restic/powershell/schtasks) เสมอ
    หน้าต่างนั้นปิดได้ และเคยโดนปิดจริง: offsite backup 16 ส.ค. 69 ล้มด้วย
    ``command_failed:gh.EXE:exit_3221225786`` (= 0xC000013A ถูกสั่งจบ)
    """

    SCRIPTS_DIR = GARMIN_ROOT / "scripts"
    HELPER = "win_process.py"

    def automated_scripts(self):
        return [
            path for path in sorted(self.SCRIPTS_DIR.glob("*.py"))
            if path.name != self.HELPER
        ]

    def test_no_script_launches_a_child_process_directly(self):
        for path in self.automated_scripts():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr in {"run", "Popen", "call", "check_output", "check_call"}
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "subprocess"
                ):
                    self.fail(
                        f"{path.name}:{node.lineno} เรียก subprocess.{func.attr} ตรง ๆ — "
                        f"ต้องผ่าน win_process.run ไม่งั้นจะได้หน้าต่าง console ที่ปิดได้"
                    )

    def test_helper_always_suppresses_the_console_window_on_windows(self):
        source = (self.SCRIPTS_DIR / self.HELPER).read_text(encoding="utf-8")
        self.assertIn("CREATE_NO_WINDOW = 0x08000000", source)
        self.assertIn("TERMINATED_BY_CONSOLE = 0xC000013A", source)

        win_process = load_script(
            "garmin_win_process_under_test", self.SCRIPTS_DIR / self.HELPER
        )
        recorded = {}

        def fake_run(command, **kwargs):
            recorded.update(kwargs)
            recorded["command"] = command
            return "sentinel"

        with unittest.mock.patch.object(win_process.subprocess, "run", fake_run):
            self.assertEqual(win_process.run(["gh", "release", "view"]), "sentinel")
        if os.name == "nt":
            self.assertTrue(
                recorded["creationflags"] & win_process.CREATE_NO_WINDOW
            )
        else:
            self.assertNotIn("creationflags", recorded)

    def test_helper_keeps_caller_creation_flags(self):
        win_process = load_script(
            "garmin_win_process_flags_under_test", self.SCRIPTS_DIR / self.HELPER
        )
        recorded = {}

        def fake_run(command, **kwargs):
            recorded.update(kwargs)
            return None

        with unittest.mock.patch.object(win_process.subprocess, "run", fake_run):
            win_process.run(["gh"], creationflags=0x00000200)
        if os.name == "nt":
            self.assertEqual(
                recorded["creationflags"],
                0x00000200 | win_process.CREATE_NO_WINDOW,
            )
        else:
            self.assertEqual(recorded["creationflags"], 0x00000200)

    def test_kill_and_command_labels_read_truthfully(self):
        win_process = load_script(
            "garmin_win_process_labels_under_test", self.SCRIPTS_DIR / self.HELPER
        )

        self.assertTrue(win_process.was_terminated(0xC000013A))
        self.assertFalse(win_process.was_terminated(1))
        self.assertIn("0xC000013A", win_process.exit_reason(0xC000013A))
        self.assertEqual(win_process.exit_reason(3), "exit_3")
        self.assertEqual(
            win_process.command_label(
                [r"C:\Program Files\GitHub CLI\gh.EXE", "release", "upload",
                 "offsite-backup", r"C:\tmp\restic-repository.zip", "--repo", "owner/name"]
            ),
            "gh release upload",
        )
        # path/tag/ธง ต้องไม่ติดไปกับ label (สถานะและ heartbeat ห้ามพกรายละเอียดออกไป)
        self.assertEqual(
            win_process.command_label([r"C:\restic.exe", "backup", r"C:\Backup\garmin-db-daily"]),
            "restic backup",
        )
        # เทส/CI รันบน Linux ด้วย — การตัดชื่อไฟล์ต้องไม่พึ่งตัวคั่น path ของ OS ที่รัน
        self.assertEqual(
            win_process.command_label(["/usr/bin/gh", "release", "view"]),
            "gh release view",
        )
        self.assertEqual(
            win_process.command_label(["powershell.exe", "-NoProfile", "-File", "x.ps1"]),
            "powershell",
        )


class TokenSlugSafetyTests(unittest.TestCase):
    def test_known_apostrophe_slug_is_preserved(self):
        self.assertEqual(token_generator.validate_athlete_slug("P'Kao"), "p'kao")

    def test_path_traversal_and_shell_path_characters_are_rejected(self):
        for value in (
            "../share",
            r"..\share",
            r"C:\temp\stolen",
            "/tmp/stolen",
            ".",
            "name/child",
            "name\\child",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    token_generator.validate_athlete_slug(value)

    def test_simple_legacy_slugs_still_work(self):
        for value in ("tong", "dan", "runner_01", "runner-01"):
            with self.subTest(value=value):
                self.assertEqual(token_generator.validate_athlete_slug(value), value)


class DashboardBindingTests(unittest.TestCase):
    def test_streamlit_config_binds_to_loopback(self):
        source = (GARMIN_ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
        self.assertRegex(source, r'(?ms)^\[server\].*?^address\s*=\s*"127\.0\.0\.1"\s*$')

    def test_manual_launcher_reasserts_loopback_binding(self):
        source = (PROJECT_ROOT / "run_dashboard.bat").read_text(encoding="utf-8-sig")
        self.assertIn("--server.address 127.0.0.1", source)


class CiCoverageTests(unittest.TestCase):
    def test_windows_ci_runs_temp_only_acl_and_wrapper_regressions(self):
        source = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        windows_job = source.split("  windows-ops:", 1)[1]
        self.assertIn("runs-on: windows-latest", source)
        self.assertIn("garmin.tests.test_ops_security", source)
        self.assertIn("garmin.tests.test_health_report.PrivateAclChecksTests", source)
        self.assertIn(
            "garmin.tests.test_backup_healthcheck.HealthcheckSecretStorageTests",
            source,
        )
        self.assertIn(
            "garmin.tests.test_health_report.HealthcheckSecretStorageChecksTests",
            source,
        )
        self.assertIn("garmin.tests.test_offsite_backup", source)
        self.assertIn("garmin.tests.test_system_heartbeat", source)
        self.assertIn("astral-sh/setup-uv@v9.0.0", windows_job)
        self.assertIn("uv sync --project garmin --frozen", windows_job)
        self.assertIn('tzutil /s "SE Asia Standard Time"', windows_job)
        self.assertIn(
            "uv run --project garmin --frozen python -m unittest", windows_job
        )


class PowerShellEncodingTests(unittest.TestCase):
    def test_acl_script_has_utf8_bom_for_windows_powershell(self):
        self.assertEqual(ACL_SCRIPT.read_bytes()[:3], b"\xef\xbb\xbf")
        migration = PROJECT_ROOT / "scripts" / "migrate_healthcheck_secret.ps1"
        self.assertEqual(migration.read_bytes()[:3], b"\xef\xbb\xbf")

    def test_every_tracked_powershell_file_has_utf8_bom(self):
        completed = subprocess.run(
            ["git", "ls-files", "-z", "--", "*.ps1"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            check=True,
        )
        for raw in completed.stdout.split(b"\0"):
            if not raw:
                continue
            path = PROJECT_ROOT / raw.decode("utf-8")
            with self.subTest(path=path.relative_to(PROJECT_ROOT)):
                self.assertEqual(path.read_bytes()[:3], b"\xef\xbb\xbf")

    def test_acl_all_scope_includes_private_log_child_not_backup_parent(self):
        source = ACL_SCRIPT.read_text(encoding="utf-8-sig")
        self.assertIn("$defaultLogs = @('C:\\Backup\\run-performance-logs')", source)
        self.assertRegex(
            source,
            r"default\s+\{\s*\$defaultGarmin \+ \$defaultBackup \+ \$defaultLogs\s*\}",
        )

    def test_acl_principal_check_covers_every_protected_operations_task(self):
        source = ACL_SCRIPT.read_text(encoding="utf-8-sig")
        for task_name in (
            "Run-Performance-OffsiteBackup",
            "Run-Performance-RestoreDrill",
            "Run-Performance-SystemHealth",
        ):
            with self.subTest(task_name=task_name):
                self.assertIn(f"'{task_name}'", source)

    def test_notification_does_not_hide_missing_or_malformed_round_state(self):
        source = (GARMIN_ROOT / "scripts" / "notify_sync.ps1").read_text(
            encoding="utf-8-sig"
        )
        self.assertIn("ไม่มี start marker", source)
        self.assertIn("ไฟล์สถานะเสีย/อ่านไม่ได้", source)
        self.assertRegex(
            source,
            r"\$SyncExit -ne 0 -and \$failed\.Count -eq 0",
        )
        self.assertIn("$okProperty.Value -isnot [bool]", source)
        self.assertIn("Garmin data quality/schema drift", source)
        self.assertNotIn("schema/API", source)

    def test_scheduler_setup_validates_selection_and_returns_failures(self):
        source = (PROJECT_ROOT / "scripts" / "setup_scheduled_tasks.ps1").read_text(
            encoding="utf-8-sig"
        )
        self.assertIn("$TaskName -notin $knownTaskNames", source)
        self.assertIn(
            "$t.Optional -and -not $IncludeOptional -and -not $TaskName",
            source,
        )
        self.assertRegex(source, r"if \(\$failed -gt 0\) \{ exit 1 \}\s*exit 0\s*\Z")
        self.assertNotIn("New-TimeSpan -Days 36500)", source)
        self.assertIn("New-TimeSpan -Days 3650)", source)

    def test_scheduler_exposes_a_machine_readable_plan(self):
        """-Json ต้องมีอยู่และไม่พิมพ์ข้อความคนปนออกมา

        เทสนี้อ่านซอร์ส (รันได้ทุก OS) ส่วนเทสด้านล่างรันของจริงบน Windows —
        เหตุผลที่ต้องมีโหมดเครื่องอ่าน: ข้อความไทยที่ redirect ออกไปจะถูกแปลงตาม
        code page ของ console ที่เรียก ทำให้กลายเป็น '?' เมื่อผู้เรียกไม่ได้ chcp 65001
        """
        source = (PROJECT_ROOT / "scripts" / "setup_scheduled_tasks.ps1").read_text(
            encoding="utf-8-sig"
        )
        self.assertIn("[switch]$Json", source)
        self.assertIn("$speak = -not $Json", source)
        self.assertRegex(source, r"ConvertTo-Json -Depth \d+")
        outside_say = re.sub(r"(?s)function Say \{.*?\n\}\n", "", source)
        self.assertNotIn(
            "Write-Host", outside_say,
            "ทุกข้อความคนต้องผ่าน Say ไม่งั้น -Json จะคืน JSON ปนข้อความ",
        )


class SchedulerPlanTests(unittest.TestCase):
    """สัญญาของตารางงานอัตโนมัติ อ่านจากแผน JSON ของ setup_scheduled_tasks.ps1."""

    RETRY_POLICY = {
        # สายช้า/สำคัญ: พลาดรอบแล้วต้องได้ลองใหม่เอง
        "Run-Performance-Backup": (3, "PT15M"),
        "Run-Performance-Garmin-Reconcile": (2, "PT30M"),
        "Run-Performance-Garmin-DeepSync": (2, "PT1H"),
        "Run-Performance-OffsiteBackup": (3, "PT30M"),
        "Run-Performance-RestoreDrill": (1, "PT2H"),
        "Run-Performance-SystemHealth": (2, "PT15M"),
        # สายถี่: รอบถัดไปมาเองใน 15–60 นาที การ retry มีแต่จะไปแย่ง sync.lock
        "Run-Performance-Garmin-Fast": (0, None),
        "Run-Performance-Garmin-Wellness": (0, None),
        "Run-Performance-Garmin": (0, None),
    }
    TRIGGER_POLICY = {
        "Run-Performance-Garmin-Fast": [
            {"type": "time", "startTime": "00:05:00", "utcOffset": "+07:00", "endBoundary": None, "enabled": True, "interval": "PT15M", "duration": "P3650D", "windowActive": True},
        ],
        "Run-Performance-Garmin-Wellness": [
            {"type": "time", "startTime": "00:12:00", "utcOffset": "+07:00", "endBoundary": None, "enabled": True, "interval": "PT30M", "duration": "P3650D", "windowActive": True},
        ],
        "Run-Performance-Garmin": [
            {"type": "time", "startTime": "00:00:00", "utcOffset": "+07:00", "endBoundary": None, "enabled": True, "interval": "PT1H", "duration": "P3650D", "windowActive": True},
        ],
        "Run-Performance-Backup": [
            {"type": "daily", "startTime": "22:00:00", "utcOffset": "+07:00", "endBoundary": None, "enabled": True, "daysInterval": 1},
        ],
        "Run-Performance-Garmin-Reconcile": [
            {"type": "weekly", "startBoundary": "2026-08-09T09:30:00+07:00", "startTime": "09:30:00", "utcOffset": "+07:00", "endBoundary": None, "enabled": True, "weeksInterval": 1, "daysOfWeek": ["Sunday"]},
        ],
        "Run-Performance-Garmin-DeepSync": [
            {"type": "weekly", "startBoundary": "2026-08-02T10:30:00+07:00", "startTime": "10:30:00", "utcOffset": "+07:00", "endBoundary": None, "enabled": True, "weeksInterval": 4, "daysOfWeek": ["Sunday"]},
        ],
        "Run-Performance-OffsiteBackup": [
            {"type": "daily", "startTime": "22:30:00", "utcOffset": "+07:00", "endBoundary": None, "enabled": True, "daysInterval": 1},
        ],
        "Run-Performance-RestoreDrill": [
            {"type": "weekly", "startBoundary": "2026-08-02T12:00:00+07:00", "startTime": "12:00:00", "utcOffset": "+07:00", "endBoundary": None, "enabled": True, "weeksInterval": 4, "daysOfWeek": ["Sunday"]},
        ],
        "Run-Performance-SystemHealth": [
            {"type": "time", "startTime": "00:25:00", "utcOffset": "+07:00", "endBoundary": None, "enabled": True, "interval": "PT2H", "duration": "P3650D", "windowActive": True},
        ],
    }

    @classmethod
    def setUpClass(cls):
        if os.name != "nt":
            raise unittest.SkipTest("Windows Scheduled Task contract")
        completed = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(PROJECT_ROOT / "scripts" / "setup_scheduled_tasks.ps1"),
                "-DryRun", "-Json", "-IncludeOptional",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=SUBPROCESS_TIMEOUT_SEC,
            check=False,
        )
        if completed.returncode != 0:
            raise AssertionError(completed.stderr or completed.stdout)
        cls.plan = json.loads(completed.stdout)
        cls.tasks = {task["name"]: task for task in cls.plan["tasks"]}

    def test_dry_run_plans_every_task_without_touching_windows(self):
        self.assertTrue(self.plan["dryRun"])
        self.assertEqual(set(self.tasks), set(self.RETRY_POLICY))
        self.assertEqual(self.plan["summary"]["failed"], 0)
        for name, task in self.tasks.items():
            with self.subTest(task_name=name):
                self.assertEqual(task["status"], "dryrun")
                self.assertEqual(task["problems"], [])

    def test_scheduler_retries_only_slow_critical_lanes(self):
        for name, (count, interval) in self.RETRY_POLICY.items():
            with self.subTest(task_name=name):
                self.assertEqual(self.tasks[name]["retryCount"], count)
                self.assertEqual(self.tasks[name]["retryInterval"], interval)

    def test_every_task_may_run_on_battery(self):
        """เครื่องนี้เป็นโน้ตบุ๊ก — ตั้ง $false เมื่อไหร่ Windows ได้สิทธิ์ทั้งไม่เริ่ม
        และฆ่ากลางคันแบบเงียบสนิท (backup หายทั้งคืน 4 ส.ค. 69)."""
        for name, task in self.tasks.items():
            with self.subTest(task_name=name):
                self.assertTrue(task["onBattery"])

    def test_plan_locks_action_settings_and_full_trigger_timetable(self):
        for name, task in self.tasks.items():
            with self.subTest(task_name=name):
                self.assertEqual(task["triggers"], self.TRIGGER_POLICY[name])
                self.assertEqual(task["actionCount"], 1)
                self.assertEqual(task["actionTypes"], ["Exec"])
                self.assertEqual(
                    Path(task["workingDirectory"]), Path(task["argument"].split('"')[1]).parent
                )
                self.assertEqual(task["logonType"], "InteractiveToken")
                self.assertEqual(task["multipleInstances"], "IgnoreNew")
                self.assertTrue(task["startWhenAvailable"])
                self.assertEqual(task["executionTimeLimit"], task["timeLimit"])

    def test_supported_principal_requires_login_without_storing_windows_password(self):
        source = (PROJECT_ROOT / "scripts" / "setup_scheduled_tasks.ps1").read_text(
            encoding="utf-8-sig"
        )
        self.assertTrue(
            all(task["logonType"] == "InteractiveToken" for task in self.tasks.values())
        )
        self.assertIn("-LogonType Interactive", source)
        self.assertNotRegex(source, r"(?i)-Password\b|AutoAdminLogon|DefaultPassword")

    def test_weekly_anchors_stay_on_their_own_weekday(self):
        """anchor ที่หลุดวัน = cadence เพี้ยนเงียบ ๆ และเลื่อนใหม่ทุกครั้งที่รันสคริปต์
        (DeepSync เคยกลายเป็นทุก 1 สัปดาห์ — เห็นได้เฉพาะตอน export XML)."""
        anchored = {
            name: task["anchors"] for name, task in self.tasks.items()
            if task["anchors"]
        }
        self.assertEqual(
            set(anchored),
            {
                "Run-Performance-Garmin-Reconcile",
                "Run-Performance-Garmin-DeepSync",
                "Run-Performance-RestoreDrill",
            },
        )
        for name, anchors in anchored.items():
            for anchor in anchors:
                with self.subTest(task_name=name, anchor=anchor["startBoundary"]):
                    self.assertEqual(anchor["dayOfWeek"], "Sunday")


@unittest.skipUnless(os.name == "nt", "Windows PowerShell integration test")
class PrepLogPowerShellIntegrationTests(unittest.TestCase):
    def run_prep(self, log_path, marker_path):
        return subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(GARMIN_ROOT / "scripts" / "prep_log.ps1"),
                "-LogPath", str(log_path), "-Marker", str(marker_path),
            ],
            capture_output=True,
            text=False,
            timeout=SUBPROCESS_TIMEOUT_SEC,
            check=False,
        )

    def test_marker_success_and_failure_have_truthful_exit_codes(self):
        with tempfile.TemporaryDirectory(prefix="run-performance-prep-test-") as raw:
            root = Path(raw)
            good = self.run_prep(root / "sync.log", root / "marker.txt")
            self.assertEqual(good.returncode, 0)
            self.assertTrue((root / "marker.txt").is_file())

            blocker = root / "not-a-directory"
            blocker.write_text("synthetic", encoding="ascii")
            bad = self.run_prep(blocker / "sync.log", blocker / "marker.txt")
            self.assertNotEqual(bad.returncode, 0)


@unittest.skipUnless(os.name == "nt", "Windows DACL integration test")
class PrivateAclPowerShellIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="run-performance-acl-test-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.root = self.temp_dir / "private-root"
        self.child = self.root / "nested" / "credential.json"
        self.child.parent.mkdir(parents=True)
        self.child.write_text("synthetic-not-a-real-secret", encoding="utf-8")

    def run_acl(self, *args):
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ACL_SCRIPT),
                "-Targets",
                str(self.root),
                "-Json",
                *args,
            ],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SEC,
            check=False,
        )
        self.assertTrue(
            completed.stdout.strip(),
            msg=f"ACL script produced no JSON; stderr={completed.stderr}",
        )
        payload = json.loads(completed.stdout.strip())
        return completed, payload

    def add_broad_aces(self):
        commands = (
            # Model production: the current user is owner but has no dedicated
            # FullControl ACE.  Owner can rewrite the DACL (WRITE_DAC) without
            # being able to redundantly set Owner (WRITE_OWNER).
            ["icacls.exe", str(self.root), "/inheritance:r"],
            ["icacls.exe", str(self.root), "/grant", "*S-1-5-32-545:(OI)(CI)RX"],
            ["icacls.exe", str(self.child), "/grant", "*S-1-5-11:M"],
        )
        for command in commands:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT_SEC,
            )
            self.assertEqual(completed.returncode, 0, msg=completed.stderr)

    def test_check_goes_red_then_recursive_hardening_goes_green(self):
        self.add_broad_aces()

        before, before_payload = self.run_acl("-CheckOnly", "-Recurse")
        self.assertNotEqual(before.returncode, 0)
        self.assertFalse(before_payload["ok"])
        self.assertTrue(before_payload["problems"])

        fixed, fixed_payload = self.run_acl("-Recurse")
        self.assertEqual(fixed.returncode, 0, msg=fixed.stderr)
        self.assertTrue(fixed_payload["ok"])

        after, after_payload = self.run_acl("-CheckOnly", "-Recurse")
        self.assertEqual(after.returncode, 0, msg=after.stderr)
        self.assertTrue(after_payload["ok"])
        self.assertEqual(after_payload["problems"], [])

        again, again_payload = self.run_acl("-Recurse")
        self.assertEqual(again.returncode, 0, msg=again.stderr)
        self.assertTrue(again_payload["ok"], "hardening must be idempotent")
        self.assertEqual(again_payload["changed"], [], "an exact DACL must be a no-op")


if __name__ == "__main__":
    unittest.main()
