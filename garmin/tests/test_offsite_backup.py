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
from datetime import datetime, timezone


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "garmin" / "scripts" / "validate_sqlite_backup.py"
OFFSITE_SCRIPT = PROJECT_ROOT / "garmin" / "scripts" / "offsite_backup.py"
SETUP_SCRIPT = PROJECT_ROOT / "scripts" / "setup_offsite_backup.ps1"
SCHEMA_SCRIPT = PROJECT_ROOT / "garmin" / "scripts" / "02_init_schema.py"


ESSENTIAL_TABLES = (
    "dim_athlete", "dim_athlete_device", "fact_activity",
    "fact_activity_split", "fact_daily_wellness", "fact_race_prediction",
    "fact_personal_record", "fact_gear", "fact_body_composition",
)


def create_minimal_garmin_database(path, data_date="2026-08-17"):
    connection = sqlite3.connect(path)
    for table in ESSENTIAL_TABLES:
        if table == "dim_athlete":
            connection.execute(
                "CREATE TABLE dim_athlete (athlete_id INTEGER PRIMARY KEY, slug TEXT)"
            )
        elif table == "fact_activity":
            connection.execute(
                "CREATE TABLE fact_activity (activity_id INTEGER PRIMARY KEY, "
                "athlete_id INTEGER, start_time_local TEXT, deleted_at TEXT)"
            )
        elif table == "fact_daily_wellness":
            connection.execute(
                "CREATE TABLE fact_daily_wellness (athlete_id INTEGER, calendar_date TEXT)"
            )
        else:
            connection.execute(f"CREATE TABLE {table} (synthetic INTEGER)")
    connection.execute("INSERT INTO dim_athlete VALUES (1, 'synthetic')")
    connection.execute(
        "INSERT INTO fact_activity VALUES (101, 1, ?, NULL)",
        (f"{data_date} 06:00:00",),
    )
    connection.execute(
        "INSERT INTO fact_daily_wellness VALUES (1, ?)", (data_date,)
    )
    connection.commit()
    connection.close()


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
    def test_non_garmin_sqlite_is_rejected_even_when_quick_check_passes(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory(prefix="offsite-db-valid-") as raw:
            database = Path(raw) / "garmin-20260812.db"
            conn = sqlite3.connect(database)
            conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")
            conn.execute("INSERT INTO sample VALUES (1)")
            conn.commit()
            conn.close()
            expected_size = database.stat().st_size

            result = validator.validate(
                database, now=datetime(2026, 8, 17, tzinfo=timezone.utc)
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["quick_check"], "ok")
        self.assertEqual(result["size_bytes"], expected_size)
        self.assertEqual(result["reason"], "schema_missing")

    def test_garmin_schema_content_and_freshness_are_required(self):
        validator = load_validator()
        now = datetime(2026, 8, 17, 12, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory(prefix="offsite-db-garmin-") as raw:
            root = Path(raw)
            fresh = root / "fresh.db"
            stale = root / "stale.db"
            mixed = root / "mixed.db"
            orphaned = root / "orphaned.db"
            create_minimal_garmin_database(fresh, "2026-08-17")
            create_minimal_garmin_database(stale, "2026-07-01")
            create_minimal_garmin_database(mixed, "2026-07-01")
            create_minimal_garmin_database(orphaned, "2026-08-17")
            connection = sqlite3.connect(mixed)
            connection.execute(
                "UPDATE fact_daily_wellness SET calendar_date='2026-08-17'"
            )
            connection.commit()
            connection.close()
            connection = sqlite3.connect(orphaned)
            connection.execute("UPDATE fact_activity SET athlete_id=999")
            connection.execute("UPDATE fact_daily_wellness SET athlete_id=999")
            connection.commit()
            connection.close()

            fresh_result = validator.validate(fresh, now=now)
            stale_result = validator.validate(stale, now=now)
            mixed_result = validator.validate(mixed, now=now)
            orphaned_result = validator.validate(orphaned, now=now)

        self.assertTrue(fresh_result["ok"])
        self.assertEqual(fresh_result["reason"], "ok")
        self.assertEqual(fresh_result["athlete_count"], 1)
        self.assertEqual(fresh_result["active_activity_count"], 1)
        self.assertEqual(fresh_result["wellness_count"], 1)
        self.assertNotIn("synthetic", json.dumps(fresh_result))
        self.assertFalse(stale_result["ok"])
        self.assertEqual(stale_result["reason"], "data_stale")
        self.assertFalse(mixed_result["ok"])
        self.assertEqual(mixed_result["reason"], "data_stale")
        self.assertFalse(orphaned_result["ok"])
        self.assertEqual(orphaned_result["reason"], "content_empty")

    def test_dashboard_probe_uses_isolated_copy_and_preserves_source(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory(prefix="offsite-dashboard-probe-") as raw:
            root = Path(raw)
            data_dir = root / "schema-data"
            env = {**os.environ, "GARMIN_DATA_DIR": str(data_dir)}
            initialized = subprocess.run(
                [sys.executable, str(SCHEMA_SCRIPT)],
                cwd=PROJECT_ROOT / "garmin",
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
            self.assertEqual(initialized.returncode, 0, msg=initialized.stderr)
            database = data_dir / "garmin.db"
            connection = sqlite3.connect(database)
            connection.execute(
                "INSERT INTO dim_athlete (slug, display_name) VALUES ('synthetic', 'Synthetic')"
            )
            athlete_id = connection.execute(
                "SELECT athlete_id FROM dim_athlete WHERE slug='synthetic'"
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO fact_activity (activity_id, athlete_id, start_time_local, deleted_at) "
                "VALUES (101, ?, '2026-08-17 06:00:00', NULL)",
                (athlete_id,),
            )
            connection.execute(
                "INSERT INTO fact_daily_wellness (athlete_id, calendar_date) "
                "VALUES (?, '2026-08-17')",
                (athlete_id,),
            )
            connection.commit()
            connection.close()
            before = hashlib.sha256(database.read_bytes()).hexdigest()

            result = validator.validate(
                database,
                now=datetime(2026, 8, 17, 12, tzinfo=timezone.utc),
                dashboard_probe=True,
            )

            after = hashlib.sha256(database.read_bytes()).hexdigest()
            self.assertTrue(result["ok"], msg=result)
            self.assertEqual(result["dashboard_probe"], "ok")
            self.assertEqual(before, after)
            self.assertFalse(database.with_name(database.name + "-wal").exists())
            self.assertFalse(database.with_name(database.name + "-shm").exists())

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
            create_minimal_garmin_database(database)

            completed = subprocess.run(
                [
                    sys.executable, str(SCRIPT), "--json",
                    "--now", "2026-08-17T12:00:00+00:00", str(database),
                ],
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
        self.assertIn("uv sync --project garmin --frozen", source)
        self.assertIn("--dashboard-probe", source)
        self.assertIn("actions/upload-artifact@v4", source)
        self.assertIn("upload_recovered_files:", source)
        self.assertIn("if: ${{ inputs.upload_recovered_files }}", source)
        self.assertRegex(
            source,
            r"(?ms)upload_recovered_files:.*?default:\s*false",
        )
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

    def test_restore_drill_requires_application_validation_and_dashboard_probe(self):
        offsite = load_offsite_backup()
        with tempfile.TemporaryDirectory(prefix="restore-orchestration-") as raw:
            root = Path(raw) / "run-performance-restore-drill-synthetic"
            root.mkdir()

            def fake_run(command, **_kwargs):
                if "download" in command:
                    (root / "restic-repository-synthetic.zip").write_bytes(b"zip")
                if "restore" in command:
                    target = Path(command[command.index("--target") + 1])
                    target.mkdir(parents=True)
                    (target / "garmin-20260817.db").write_bytes(b"restored")
                stdout = '[{"id":"snapshot"}]' if "snapshots" in command else ""
                return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

            validation = {
                "ok": True,
                "size_bytes": 8,
                "latest_activity_date": "2026-08-17",
                "latest_wellness_date": "2026-08-17",
                "data_age_days": 0,
                "athlete_count": 3,
                "active_activity_count": 10,
                "wellness_count": 20,
                "dashboard_probe": "ok",
            }
            with (
                mock.patch.object(offsite.tempfile, "mkdtemp", return_value=str(root)),
                mock.patch.object(offsite, "_get_password", return_value="x" * 32),
                mock.patch.object(offsite, "_find_executable", side_effect=lambda name: name),
                mock.patch.object(offsite, "_repository_name", return_value="owner/repo"),
                mock.patch.object(
                    offsite, "_latest_asset",
                    return_value="restic-repository-synthetic.zip",
                ),
                mock.patch.object(offsite, "_run", side_effect=fake_run),
                mock.patch.object(offsite, "_safe_extract"),
                mock.patch.object(offsite, "_cleanup_restore_tree") as cleanup,
                mock.patch.object(offsite, "_write_status"),
                mock.patch.object(
                    offsite, "validate_sqlite", return_value=validation
                ) as validate,
            ):
                result = offsite.run_restore_drill()

            self.assertTrue(result["ok"], msg=result)
            self.assertEqual(result["dashboard_probe"], "ok")
            validate.assert_called_once()
            self.assertTrue(validate.call_args.kwargs["dashboard_probe"])
            cleanup.assert_called_once_with(root)


if __name__ == "__main__":
    unittest.main()
