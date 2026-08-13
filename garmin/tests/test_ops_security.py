"""Regression tests for Windows automation and local-secret hardening.

The Windows ACL integration test only touches a temporary directory.  It never
queries or changes the production token, data, backup, or Scheduled Task paths.
"""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GARMIN_ROOT = PROJECT_ROOT / "garmin"
ACL_SCRIPT = PROJECT_ROOT / "scripts" / "harden_private_acl.ps1"


def load_script(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


token_generator = load_script(
    "garmin_token_generator_under_test",
    GARMIN_ROOT / "scripts" / "01_generate_token.py",
)


class WrapperExitPropagationTests(unittest.TestCase):
    BAT_EXIT_VARS = {
        "garmin-fast-sync-auto.bat": "SYNC_EXIT",
        "garmin-wellness-sync-auto.bat": "SYNC_EXIT",
        "garmin-sync-auto.bat": "SYNC_EXIT",
        "garmin-reconcile-auto.bat": "SYNC_EXIT",
        "garmin-deepsync-auto.bat": "SYNC_EXIT",
    }

    def test_sync_batches_propagate_real_result_after_notification(self):
        for filename, variable in self.BAT_EXIT_VARS.items():
            with self.subTest(filename=filename):
                source = (GARMIN_ROOT / filename).read_text(encoding="utf-8-sig")
                self.assertRegex(
                    source,
                    rf"(?im)^exit /b %{re.escape(variable)}%\s*$",
                    f"{filename} must expose the real worker result to Task Scheduler",
                )

    def test_deep_sync_propagates_drift_failure_with_explicit_context(self):
        source = (GARMIN_ROOT / "garmin-deepsync-auto.bat").read_text(
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
                source = (GARMIN_ROOT / filename).read_text(encoding="utf-8-sig")
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
            *sorted(GARMIN_ROOT.glob("garmin-*-hidden.vbs")),
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

    @unittest.skipUnless(os.name == "nt", "Windows Scheduled Task contract")
    def test_scheduler_retries_only_slow_critical_lanes(self):
        policies = {
            "Run-Performance-Backup": (3, "PT15M"),
            "Run-Performance-Garmin-Reconcile": (2, "PT30M"),
            "Run-Performance-Garmin-DeepSync": (2, "PT1H"),
            "Run-Performance-OffsiteBackup": (3, "PT30M"),
            "Run-Performance-RestoreDrill": (1, "PT2H"),
            "Run-Performance-SystemHealth": (2, "PT15M"),
        }
        for task_name, (count, interval) in policies.items():
            with self.subTest(task_name=task_name):
                completed = subprocess.run(
                    [
                        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-File", str(PROJECT_ROOT / "scripts" / "setup_scheduled_tasks.ps1"),
                        "-DryRun", "-TaskName", task_name,
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, msg=completed.stderr)
                self.assertIn(
                    f"retry: {count} ครั้ง ระยะห่าง {interval}",
                    completed.stdout,
                )


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
            timeout=30,
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
            timeout=30,
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
                timeout=30,
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
