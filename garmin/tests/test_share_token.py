import csv
import importlib.util
import json
import os
import subprocess
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "share" / "get_garmin_token.py"
SPEC = importlib.util.spec_from_file_location("get_garmin_token", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
TOKEN_SCRIPT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOKEN_SCRIPT)


# เพดานนี้มีไว้จับ "สคริปต์ค้าง" ไม่ใช่วัดความเร็วเครื่อง — Windows runner ของ GitHub
# ช้าเป็นพัก ๆ จนสปอว์นโปรเซสเกิน 30 วิได้ (CI ล้มจริง 18 ส.ค. 69 ทั้ง prep_log.ps1 และ
# setup_scheduled_tasks.ps1) งบเวลาจริงคุมด้วย timeout-minutes ของ job ไม่ใช่ตรงนี้
SUBPROCESS_TIMEOUT_SEC = 120


class GarminConnectDependencyTests(unittest.TestCase):
    def test_matching_version_does_not_invoke_pip(self):
        with (
            patch.object(
                TOKEN_SCRIPT,
                "version",
                return_value=TOKEN_SCRIPT.GARMINCONNECT_VERSION,
            ),
            patch.object(TOKEN_SCRIPT.subprocess, "check_call") as check_call,
        ):
            TOKEN_SCRIPT.ensure_garminconnect()

        check_call.assert_not_called()

    def test_mismatched_version_is_replaced_with_tested_pin(self):
        with (
            patch.object(TOKEN_SCRIPT, "version", return_value="0.3.6"),
            patch.object(TOKEN_SCRIPT.subprocess, "check_call") as check_call,
            patch("builtins.print"),
        ):
            TOKEN_SCRIPT.ensure_garminconnect()

        check_call.assert_called_once_with(
            [
                TOKEN_SCRIPT.sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                TOKEN_SCRIPT.GARMINCONNECT_REQUIREMENT,
            ]
        )

    def test_missing_package_installs_tested_pin(self):
        with (
            patch.object(
                TOKEN_SCRIPT,
                "version",
                side_effect=TOKEN_SCRIPT.PackageNotFoundError,
            ),
            patch.object(TOKEN_SCRIPT.subprocess, "check_call") as check_call,
            patch("builtins.print"),
        ):
            TOKEN_SCRIPT.ensure_garminconnect()

        self.assertEqual(
            check_call.call_args.args[0][-1], TOKEN_SCRIPT.GARMINCONNECT_REQUIREMENT
        )


class PrivatePackagingFlowTests(unittest.TestCase):
    def test_success_publishes_private_zip_and_removes_plaintext_staging(self):
        class FakeGarmin:
            def __init__(self, *_args, **_kwargs):
                pass

            def login(self, token_dir):
                Path(token_dir, "garmin_tokens.json").write_text(
                    '{"synthetic": true}', encoding="utf-8"
                )

            def get_full_name(self):
                return "Synthetic Runner"

        fake_module = types.ModuleType("garminconnect")
        fake_module.Garmin = FakeGarmin
        with tempfile.TemporaryDirectory(prefix="share-token-flow-") as temp:
            output_dir = Path(temp)
            with (
                patch.object(TOKEN_SCRIPT, "SCRIPT_DIR", output_dir),
                patch.object(TOKEN_SCRIPT, "check_python"),
                patch.object(TOKEN_SCRIPT, "ensure_garminconnect"),
                patch.object(TOKEN_SCRIPT, "getpass", return_value="synthetic-password"),
                patch.dict(TOKEN_SCRIPT.sys.modules, {"garminconnect": fake_module}),
                patch("builtins.input", side_effect=["runner", "runner@example.test", ""]),
                patch("builtins.print"),
                self.assertRaises(SystemExit) as exited,
            ):
                TOKEN_SCRIPT.main()

            self.assertEqual(exited.exception.code, 0)
            archive = output_dir / "garmin_token_runner.zip"
            self.assertTrue(archive.is_file())
            self.assertEqual(list(output_dir.glob(".garmin-token-*")), [])
            with zipfile.ZipFile(archive) as zf:
                self.assertEqual(zf.namelist(), ["runner/garmin_tokens.json"])


@unittest.skipUnless(os.name == "nt", "Windows DACL integration test")
class PrivateTokenAclTests(unittest.TestCase):
    @staticmethod
    def inspect_acl(path):
        script = r"""
$target = [System.IO.Path]::GetFullPath($env:RUNPERF_ACL_TEST_PATH)
$sections = [System.Security.AccessControl.AccessControlSections]::Access
$acl = if ([System.IO.Directory]::Exists($target)) {
    [System.IO.Directory]::GetAccessControl($target, $sections)
} else {
    [System.IO.File]::GetAccessControl($target, $sections)
}
$rules = @($acl.GetAccessRules($true, $true,
    [System.Security.Principal.SecurityIdentifier]))
[ordered]@{
    protected = $acl.AreAccessRulesProtected
    rules = @($rules | ForEach-Object {
        [ordered]@{
            sid = $_.IdentityReference.Value
            inherited = $_.IsInherited
            type = [string]$_.AccessControlType
            rights = [int64]$_.FileSystemRights
        }
    })
} | ConvertTo-Json -Depth 5 -Compress
"""
        completed = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-NonInteractive",
                "-Command", script,
            ],
            env={**os.environ, "RUNPERF_ACL_TEST_PATH": str(path)},
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SEC,
            check=False,
        )
        if completed.returncode != 0:
            raise AssertionError(completed.stderr)
        return json.loads(completed.stdout)

    def test_windows_helper_removes_broad_aces_and_verifies_exact_dacl(self):
        with tempfile.TemporaryDirectory(prefix="share-token-acl-") as temp:
            private_dir = Path(temp) / "private"
            private_dir.mkdir()
            subprocess.run(
                [
                    "icacls.exe", str(private_dir), "/grant",
                    "*S-1-5-32-545:(OI)(CI)RX",
                ],
                capture_output=True,
                timeout=SUBPROCESS_TIMEOUT_SEC,
                check=True,
            )

            TOKEN_SCRIPT.harden_private_path(private_dir, directory=True)
            archive = private_dir / "archive.zip"
            archive.write_bytes(b"synthetic-not-a-token")
            TOKEN_SCRIPT.harden_private_path(archive, directory=False)

            whoami = subprocess.run(
                ["whoami.exe", "/user", "/fo", "csv", "/nh"],
                capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_SEC, check=True,
            )
            expected = {
                next(csv.reader([whoami.stdout.strip()]))[1],
                "S-1-5-18",
                "S-1-5-32-544",
            }
            for path in (private_dir, archive):
                with self.subTest(path=path.name):
                    acl = self.inspect_acl(path)
                    self.assertTrue(acl["protected"])
                    self.assertEqual({rule["sid"] for rule in acl["rules"]}, expected)
                    self.assertEqual(len(acl["rules"]), 3)
                    self.assertTrue(all(not rule["inherited"] for rule in acl["rules"]))
                    self.assertTrue(all(rule["type"] == "Allow" for rule in acl["rules"]))


if __name__ == "__main__":
    unittest.main()
