import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "garmin" / "scripts" / "system_heartbeat.py"
VALIDATOR = PROJECT_ROOT / "garmin" / "scripts" / "validate_system_heartbeat.py"


# เพดานนี้มีไว้จับ "สคริปต์ค้าง" ไม่ใช่วัดความเร็วเครื่อง — Windows runner ของ GitHub
# ช้าเป็นพัก ๆ จนสปอว์นโปรเซสเกิน 30 วิได้ (CI ล้มจริง 18 ส.ค. 69 ทั้ง prep_log.ps1 และ
# setup_scheduled_tasks.ps1) งบเวลาจริงคุมด้วย timeout-minutes ของ job ไม่ใช่ตรงนี้
SUBPROCESS_TIMEOUT_SEC = 120

BANGKOK = timezone(timedelta(hours=7))


def load_script(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


heartbeat_script = load_script("garmin_system_heartbeat_under_test", SCRIPT)


class SystemHeartbeatCliTests(unittest.TestCase):
    def run_validator(self, payload, now, *, incident_after=None):
        with tempfile.TemporaryDirectory(prefix="heartbeat-validator-") as raw:
            source = Path(raw) / "system-health.json"
            source.write_text(json.dumps(payload), encoding="utf-8")
            command = [
                sys.executable,
                str(VALIDATOR),
                str(source),
                "--now", now,
                "--timezone", "Asia/Bangkok",
                "--offline-start", "01:00",
                "--offline-end", "08:00",
            ]
            if incident_after is not None:
                command += ["--incident-after-hours", str(incident_after)]
            completed = subprocess.run(
                command,
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT_SEC,
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
                timeout=SUBPROCESS_TIMEOUT_SEC,
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
        self.assertIn("issues: write", source)
        self.assertIn("heartbeat_issue_alert.py", source)
        self.assertIn("force_failure", source)
        self.assertIn("--incident-after-hours 12", source)
        # เงียบเพราะเครื่องหลับต้องไม่แตะ incident เลย — ไม่เปิดใหม่ และไม่ปิดของเดิม
        # ที่ยังค้างอยู่ (ปิดให้ = โกหกว่า "recovered" ทั้งที่ยังไม่มี heartbeat ใหม่)
        self.assertIn("steps.validate.outputs.code", source)
        self.assertIn("steps.verdict.outputs.status != 'quiet'", source)
        self.assertIn("steps.verdict.outputs.status == 'failure'", source)
        self.assertIn("if: always()", source)
        self.assertIn("continue-on-error: true", source)
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
            self.heartbeat("2026-08-16T14:00:00+00:00"),  # เงียบ 13 ชม.
            "2026-08-17T03:00:00+00:00",                  # 10:00 Bangkok
        )
        self.assertEqual(completed.returncode, 1)
        self.assertEqual((result["ok"], result["reason"]), (False, "stale"))

    def test_validator_holds_the_incident_while_the_laptop_may_be_asleep(self):
        """เคสจริง 18 ส.ค. 69 รอบ #108: โน้ตบุ๊กหลับ 16:19–20:17 ข้ามช่องส่ง 16:25/18:25

        payload สะอาด (error 0) แค่ไม่มีใครส่งใหม่ — จากนอกเครื่องแยก "หลับ" กับ
        "publisher พัง" ไม่ออก จึงต้องรอให้เงียบนานเกินกว่าที่การงีบอธิบายได้ก่อน
        """
        completed, result = self.run_validator(
            self.heartbeat("2026-08-18T07:25:00+00:00"),  # 14:25 Bangkok
            "2026-08-18T10:49:54+00:00",                  # 17:49 Bangkok, อายุ 3:24
        )
        self.assertEqual(completed.returncode, 2, msg=completed.stdout)
        self.assertEqual((result["ok"], result["reason"]), (False, "offline_grace"))

    def test_validator_opens_the_incident_once_silence_outlasts_any_nap(self):
        completed, result = self.run_validator(
            self.heartbeat("2026-08-17T22:00:00+00:00"),  # 05:00 Bangkok
            "2026-08-18T11:00:00+00:00",                  # 18:00 Bangkok, อายุ 13 ชม.
        )
        self.assertEqual(completed.returncode, 1, msg=completed.stdout)
        self.assertEqual((result["ok"], result["reason"]), (False, "stale"))

    def test_validator_grace_window_is_tunable_and_must_exceed_freshness(self):
        payload = self.heartbeat("2026-08-18T07:25:00+00:00")
        tightened, tight_result = self.run_validator(
            payload, "2026-08-18T10:49:54+00:00", incident_after=3
        )
        self.assertEqual(tightened.returncode, 1)
        self.assertEqual(tight_result["reason"], "stale")

        broken, broken_result = self.run_validator(
            payload, "2026-08-18T10:49:54+00:00", incident_after=1
        )
        self.assertEqual(broken.returncode, 1)
        self.assertEqual(broken_result["reason"], "invalid")

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
        # 08:01 หมดข้ออ้าง "ปิดเครื่องตามแผน" แล้ว แต่ 7.5 ชม. ยังอยู่ในช่วงผ่อนผัน
        self.assertEqual(awake.returncode, 2)
        self.assertEqual(awake_result["reason"], "offline_grace")

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

    def test_validator_rejects_unexpected_privacy_sensitive_fields(self):
        payload = self.heartbeat("2026-08-17T03:00:00+00:00")
        cases = []
        with_findings = dict(payload)
        with_findings["findings"] = [
            {"athlete": "private-name", "measurement": 42}
        ]
        cases.append(with_findings)
        with_summary_detail = dict(payload)
        with_summary_detail["summary"] = {
            **payload["summary"], "athlete": "private-name"
        }
        cases.append(with_summary_detail)

        for candidate in cases:
            with self.subTest(keys=sorted(candidate)):
                completed, result = self.run_validator(
                    candidate, "2026-08-17T03:05:00+00:00"
                )
                self.assertEqual(completed.returncode, 1)
                self.assertEqual(result["reason"], "invalid")

    def test_publish_records_a_local_marker_for_the_in_machine_watchdog(self):
        """GitHub เห็นแค่ความเงียบ แต่ในเครื่องรู้ว่าตัวเองตื่นอยู่ไหม — marker นี้คือสิ่งที่
        notify_sync.ps1 ใช้จับ "publisher พังตอนเครื่องเปิดอยู่" ซึ่งข้างนอกจับแทนไม่ได้"""
        with tempfile.TemporaryDirectory(prefix="heartbeat-marker-") as raw:
            data_dir = Path(raw) / "data"
            written = heartbeat_script.record_publish(
                data_dir=data_dir,
                now=datetime(2026, 8, 18, 20, 25, tzinfo=BANGKOK),
            )
            self.assertEqual(written.parent, data_dir)
            self.assertEqual(
                written.read_text(encoding="ascii"), "2026-08-18T20:25:00+07:00"
            )

        source = SCRIPT.read_text(encoding="utf-8")
        body = source.split("def publish(")[1].split("def main(")[0]
        self.assertIn("record_publish(", body)
        # marker ต้องเขียน "หลัง" upload สำเร็จเท่านั้น ไม่งั้นรอบที่อัปโหลดล้มจะทิ้ง
        # หลักฐานว่าสำเร็จไว้ แล้ว watchdog ในเครื่องจะเงียบทั้งที่ publisher พังอยู่
        self.assertLess(body.index("--clobber"), body.index("record_publish("))

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
            timeout=SUBPROCESS_TIMEOUT_SEC,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertIn("system_heartbeat.py", completed.stdout)
        self.assertIn("publish", completed.stdout)
        self.assertIn("retry: 2 ครั้ง ระยะห่าง PT15M", completed.stdout)


if __name__ == "__main__":
    unittest.main()
