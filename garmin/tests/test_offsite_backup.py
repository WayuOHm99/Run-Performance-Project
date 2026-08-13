import importlib.util
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "garmin" / "scripts" / "validate_sqlite_backup.py"
OFFSITE_SCRIPT = PROJECT_ROOT / "garmin" / "scripts" / "offsite_backup.py"
SETUP_SCRIPT = PROJECT_ROOT / "scripts" / "setup_offsite_backup.ps1"


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_sqlite_backup", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_offsite_backup():
    scripts_dir = str(OFFSITE_SCRIPT.parent)
    sys.path.insert(0, scripts_dir)
    try:
        spec = importlib.util.spec_from_file_location(
            "offsite_backup_under_test", OFFSITE_SCRIPT
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(scripts_dir)


class SqliteBackupValidationTests(unittest.TestCase):
    def test_valid_backup_passes_read_only_quick_check(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory(prefix="offsite-db-valid-") as raw:
            database = Path(raw) / "garmin-20260812.db"
            conn = sqlite3.connect(database)
            conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")
            conn.execute("INSERT INTO sample VALUES (1)")
            conn.commit()
            conn.close()
            expected_size = database.stat().st_size

            result = validator.validate(database)

        self.assertTrue(result["ok"])
        self.assertEqual(result["quick_check"], "ok")
        self.assertEqual(result["size_bytes"], expected_size)

    def test_invalid_backup_fails_without_mutating_or_creating_sidecars(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory(prefix="offsite-db-invalid-") as raw:
            database = Path(raw) / "garmin-20260812.db"
            database.write_bytes(b"not a sqlite database")
            before = hashlib.sha256(database.read_bytes()).hexdigest()

            result = validator.validate(database)

            after = hashlib.sha256(database.read_bytes()).hexdigest()
            self.assertFalse(result["ok"])
            self.assertEqual(before, after)
            self.assertFalse(database.with_name(database.name + "-wal").exists())
            self.assertFalse(database.with_name(database.name + "-shm").exists())

    def test_cli_emits_machine_readable_result_and_truthful_exit_code(self):
        with tempfile.TemporaryDirectory(prefix="offsite-db-cli-") as raw:
            database = Path(raw) / "garmin.db"
            conn = sqlite3.connect(database)
            conn.execute("CREATE TABLE sample (id INTEGER)")
            conn.close()

            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--json", str(database)],
                cwd=PROJECT_ROOT / "garmin",
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["ok"])


class OffsiteBackupCliTests(unittest.TestCase):
    def test_plan_uses_verified_backup_generations_and_declares_retention(self):
        completed = subprocess.run(
            [sys.executable, str(OFFSITE_SCRIPT), "plan", "--json"],
            cwd=PROJECT_ROOT / "garmin",
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(
            payload["sources"],
            [r"C:\Backup\garmin-db-daily", r"C:\Backup\Run-Performance"],
        )
        self.assertNotIn(r"D:\Run-Performance-Project\garmin\data\garmin.db", payload["sources"])
        self.assertEqual(
            payload["retention"],
            {"daily": 7, "weekly": 8, "monthly": 12, "release_assets": 3},
        )
        self.assertEqual(
            payload["excludes"],
            ["**/.git/**", "**/.venv*/**", "**/__pycache__/**"],
        )

    def test_backup_fails_closed_before_network_when_dpapi_secret_is_missing(self):
        with tempfile.TemporaryDirectory(prefix="offsite-no-secret-") as raw:
            env = dict(os.environ)
            env["GARMIN_DATA_DIR"] = raw
            completed = subprocess.run(
                [sys.executable, str(OFFSITE_SCRIPT), "backup", "--json"],
                cwd=PROJECT_ROOT / "garmin",
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

        self.assertNotEqual(completed.returncode, 0)
        payload = json.loads(completed.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["reason"], "secret_missing")

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI setup contract")
    def test_setup_plan_keeps_recovery_secret_out_of_plaintext_files(self):
        completed = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(SETUP_SCRIPT), "-Plan", "-Json",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["local_secret_storage"], "DPAPI CurrentUser")
        self.assertEqual(payload["recovery_secret_storage"], "GitHub Actions secret")
        self.assertFalse(payload["plaintext_secret_file"])
        self.assertEqual(
            set(payload["scheduled_tasks"]),
            {
                "Run-Performance-OffsiteBackup",
                "Run-Performance-RestoreDrill",
                "Run-Performance-SystemHealth",
            },
        )

        source = SETUP_SCRIPT.read_text(encoding="utf-8-sig")
        self.assertNotIn("$password | & $gh", source)
        self.assertIn("StandardInput.Write($Value)", source)
        self.assertIn("--repo $Repository", source)

    @unittest.skipUnless(os.name == "nt", "Windows Scheduled Task contract")
    def test_scheduler_exposes_offsite_backup_and_restore_drill_tasks(self):
        scheduler = PROJECT_ROOT / "scripts" / "setup_scheduled_tasks.ps1"
        expected = {
            "Run-Performance-OffsiteBackup": "backup",
            "Run-Performance-RestoreDrill": "restore-drill",
        }
        for task_name, command in expected.items():
            with self.subTest(task_name=task_name):
                completed = subprocess.run(
                    [
                        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-File", str(scheduler), "-DryRun", "-TaskName", task_name,
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, msg=completed.stderr)
                self.assertIn("offsite_backup.py", completed.stdout)
                self.assertIn(command, completed.stdout)

    def test_disaster_recovery_workflow_uses_guarded_secret_and_uploaded_artifact(self):
        workflow = PROJECT_ROOT / ".github" / "workflows" / "restore-offsite-backup.yml"
        source = workflow.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", source)
        self.assertIn("secrets.RESTIC_REPOSITORY_PASSWORD", source)
        self.assertIn("gh release download offsite-backup", source)
        self.assertIn("Get-FileHash", source)
        self.assertIn("restic restore latest", source)
        self.assertIn("actions/upload-artifact@v4", source)
        self.assertNotRegex(source, r"(?m)^    env:\s*$")

    def test_repository_archive_hash_is_streamed(self):
        offsite = load_offsite_backup()
        with tempfile.TemporaryDirectory(prefix="offsite-repository-") as raw:
            root = Path(raw)
            repository = root / "repository"
            destination = root / "output"
            repository.mkdir()
            destination.mkdir()
            (repository / "pack").write_bytes(b"encrypted-pack" * 1000)

            with (
                mock.patch.object(offsite, "LOCAL_REPOSITORY", repository),
                mock.patch.object(
                    Path, "read_bytes",
                    side_effect=AssertionError("archive must not be read into memory"),
                ),
            ):
                archive, digest = offsite._archive_repository(destination)

            with archive.open("rb") as stream:
                expected = hashlib.file_digest(stream, "sha256").hexdigest()
            self.assertEqual(digest, expected)


if __name__ == "__main__":
    unittest.main()
