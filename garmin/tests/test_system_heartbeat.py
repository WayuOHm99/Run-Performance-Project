import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "garmin" / "scripts" / "system_heartbeat.py"
VALIDATOR = PROJECT_ROOT / "garmin" / "scripts" / "validate_system_heartbeat.py"


class SystemHeartbeatCliTests(unittest.TestCase):
    def run_validator(self, payload, now):
        with tempfile.TemporaryDirectory(prefix="heartbeat-validator-") as raw:
            source = Path(raw) / "system-health.json"
            source.write_text(json.dumps(payload), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    str(source),
                    "--now", now,
                    "--timezone", "Asia/Bangkok",
                    "--offline-start", "01:00",
                    "--offline-end", "08:00",
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        return completed, json.loads(completed.stdout)

    @staticmethod
    def heartbeat(generated_at, *, status="ok", errors=0):
        return {
            "generated_at": generated_at,
            "status": status,
            "summary": {
                "ok": 24 - errors,
                "warning": 1,
                "error": errors,
                "total": 25,
            },
        }

    def test_summarize_strips_findings_and_athlete_details(self):
        report = {
            "generated_at": "2026-08-12T23:55:54",
            "findings": [
                {
                    "check": "data_quality_coverage:private-athlete",
                    "level": "WARNING",
                    "message": "private health detail must never leave the machine",
                }
            ],
            "summary": {"ok": 24, "warning": 1, "error": 0, "total": 25},
        }
        with tempfile.TemporaryDirectory(prefix="heartbeat-safe-") as raw:
            source = Path(raw) / "health.json"
            source.write_text(json.dumps(report), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "summarize", str(source)],
                cwd=PROJECT_ROOT / "garmin",
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        heartbeat = json.loads(completed.stdout)
        self.assertEqual(heartbeat["status"], "ok")
        self.assertEqual(heartbeat["summary"], report["summary"])
        self.assertNotIn("findings", heartbeat)
        self.assertNotIn("private-athlete", completed.stdout)
        self.assertNotIn("private health detail", completed.stdout)

    def test_external_watchdog_checks_freshness_and_error_count_hourly(self):
        workflow = PROJECT_ROOT / ".github" / "workflows" / "watch-system-health.yml"
        source = workflow.read_text(encoding="utf-8")
        self.assertIn("cron: '17 * * * *'", source)
        self.assertIn("gh release download system-health", source)
        self.assertIn('--repo "$GITHUB_REPOSITORY"', source)
        self.assertIn("validate_system_heartbeat.py", source)
        self.assertIn("--offline-start 01:00", source)
        self.assertIn("--offline-end 08:00", source)
        self.assertNotRegex(source, r"(?m)^    env:\s*$")

    def test_validator_accepts_fresh_healthy_heartbeat(self):
        completed, result = self.run_validator(
            self.heartbeat("2026-08-17T02:00:00+00:00"),
            "2026-08-17T03:00:00+00:00",
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertEqual((result["ok"], result["reason"]), (True, "fresh"))

    def test_validator_rejects_stale_heartbeat_during_operational_hours(self):
        completed, result = self.run_validator(
            self.heartbeat("2026-08-16T23:00:00+00:00"),
            "2026-08-17T03:00:00+00:00",
        )
        self.assertEqual(completed.returncode, 1)
        self.assertEqual((result["ok"], result["reason"]), (False, "stale"))

    def test_validator_allows_staleness_only_inside_planned_offline_window(self):
        payload = self.heartbeat("2026-08-16T17:30:00+00:00")  # 00:30 Bangkok
        offline, offline_result = self.run_validator(
            payload, "2026-08-16T21:00:00+00:00"  # 04:00 Bangkok
        )
        awake, awake_result = self.run_validator(
            payload, "2026-08-17T01:01:00+00:00"  # 08:01 Bangkok
        )
        self.assertEqual(offline.returncode, 0)
        self.assertEqual(offline_result["reason"], "planned_offline")
        self.assertEqual(awake.returncode, 1)
        self.assertEqual(awake_result["reason"], "stale")

    def test_validator_does_not_hide_multi_day_outage_during_offline_window(self):
        completed, result = self.run_validator(
            self.heartbeat("2026-08-14T17:25:00+00:00"),
            "2026-08-17T00:00:00+00:00",  # 07:00 Bangkok
        )

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(result["reason"], "stale")

    def test_validator_rejects_future_malformed_and_unhealthy_payloads(self):
        cases = [
            (
                self.heartbeat("2026-08-17T03:20:01+00:00"),
                "future",
            ),
            ({"generated_at": "not-a-date"}, "invalid"),
            (
                self.heartbeat(
                    "2026-08-17T03:00:00+00:00", status="error", errors=1
                ),
                "unhealthy",
            ),
        ]
        for payload, reason in cases:
            with self.subTest(reason=reason):
                completed, result = self.run_validator(
                    payload, "2026-08-17T03:00:00+00:00"
                )
                self.assertEqual(completed.returncode, 1)
                self.assertEqual(result["reason"], reason)

    @unittest.skipUnless(os.name == "nt", "Windows Scheduled Task contract")
    def test_scheduler_publishes_heartbeat_every_two_hours_with_retry(self):
        scheduler = PROJECT_ROOT / "scripts" / "setup_scheduled_tasks.ps1"
        completed = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(scheduler), "-DryRun", "-TaskName",
                "Run-Performance-SystemHealth",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertIn("system_heartbeat.py", completed.stdout)
        self.assertIn("publish", completed.stdout)
        self.assertIn("retry: 2 ครั้ง ระยะห่าง PT15M", completed.stdout)


if __name__ == "__main__":
    unittest.main()
