import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "garmin" / "scripts" / "system_heartbeat.py"


class SystemHeartbeatCliTests(unittest.TestCase):
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
        self.assertIn("TotalHours", source)
        self.assertIn("TotalMinutes -lt -10", source)
        self.assertIn("summary.error", source)
        self.assertNotRegex(source, r"(?m)^    env:\s*$")

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
