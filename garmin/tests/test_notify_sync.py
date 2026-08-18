import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


GARMIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = GARMIN_ROOT / "scripts" / "notify_sync.ps1"
POWERSHELL = shutil.which("powershell.exe") or shutil.which("pwsh")


# เพดานนี้มีไว้จับ "สคริปต์ค้าง" ไม่ใช่วัดความเร็วเครื่อง — Windows runner ของ GitHub
# ช้าเป็นพัก ๆ จนสปอว์นโปรเซสเกิน 30 วิได้ (CI ล้มจริง 18 ส.ค. 69 ทั้ง prep_log.ps1 และ
# setup_scheduled_tasks.ps1) งบเวลาจริงคุมด้วย timeout-minutes ของ job ไม่ใช่ตรงนี้
SUBPROCESS_TIMEOUT_SEC = 120


@unittest.skipUnless(POWERSHELL, "PowerShell is required for notification behavior")
class NotifySyncBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="notify-sync-")
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        (self.data / "sync_lane").mkdir(parents=True)
        self.sink = Path(self.temp.name) / "notifications.jsonl"
        self.outputs = []
        self.marker = self.data / "sync_wellness_run_start.txt"
        self.marker.write_text("2026-08-17T10:00:00+07:00", encoding="ascii")

    def write_status(self, results, run_at="2026-08-17T10:00:05+07:00"):
        (self.data / "sync_lane" / "wellness.json").write_text(
            json.dumps({"run_at": run_at, "results": results}),
            encoding="utf-8",
        )

    def invoke(self, now, sync_exit):
        command = [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", str(SCRIPT),
            "-SyncExit", str(sync_exit),
            "-Lane", "wellness",
            "-StartMarker", self.marker.name,
            "-DataDir", str(self.data),
            "-NotificationLog", str(self.sink),
            "-NowIso", now,
            "-CooldownMinutes", "360",
        ]
        completed = subprocess.run(
            command,
            cwd=GARMIN_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=SUBPROCESS_TIMEOUT_SEC,
            check=False,
        )
        self.outputs.append(completed.stdout + completed.stderr)
        self.assertEqual(completed.returncode, 0, msg=completed.stdout + completed.stderr)

    def notifications(self):
        if not self.sink.exists():
            return []
        return [
            json.loads(line)
            for line in self.sink.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_deduplicates_per_condition_notifies_new_and_recovers_once(self):
        probe = {"slug": "probe", "ok": False, "reason": "network", "warnings": []}
        other = {"slug": "other", "ok": False, "reason": "token", "warnings": []}
        healthy = {"slug": "probe", "ok": True, "reason": "ok", "warnings": []}

        self.write_status([probe])
        self.invoke("2026-08-17T10:01:00+07:00", 1)
        self.invoke("2026-08-17T10:31:00+07:00", 1)
        self.assertEqual(len(self.notifications()), 1, msg="\n".join(self.outputs))

        self.write_status([probe, other])
        self.invoke("2026-08-17T11:01:00+07:00", 1)
        notifications = self.notifications()
        self.assertEqual(len(notifications), 2)
        self.assertIn("other", notifications[-1]["body"])
        self.assertNotIn("probe", notifications[-1]["body"])

        self.write_status([healthy])
        self.invoke("2026-08-17T11:31:00+07:00", 0)
        self.invoke("2026-08-17T12:01:00+07:00", 0)
        notifications = self.notifications()
        self.assertEqual(len(notifications), 3)
        self.assertIn("ปัญหาคลี่คลาย", notifications[-1]["title"])
        self.assertIn("probe", notifications[-1]["body"])
        self.assertIn("other", notifications[-1]["body"])

    def test_distinct_warning_causes_are_not_hidden_by_existing_cooldown(self):
        first = {
            "slug": "probe", "ok": True, "reason": "ok",
            "warnings": ["wellness endpoint degraded: get_sleep_data:network"],
        }
        second = {
            "slug": "probe", "ok": True, "reason": "ok",
            "warnings": ["วิ่ง 2026-08-17 ไม่มี HR (id 999)"],
        }

        self.write_status([first])
        self.invoke("2026-08-17T10:01:00+07:00", 0)
        self.write_status([second], run_at="2026-08-17T10:30:05+07:00")
        self.invoke("2026-08-17T10:31:00+07:00", 0)

        notifications = self.notifications()
        self.assertEqual(len(notifications), 3, msg="\n".join(self.outputs))
        self.assertIn("ไม่มี HR", notifications[1]["body"])
        # The identity distinguishes the cause, but sensitive warning details stay in logs.
        serialized = "\n".join(json.dumps(item, ensure_ascii=False) for item in notifications)
        self.assertNotIn("id 999", serialized)

    def test_unreadable_status_is_unknown_and_does_not_claim_recovery(self):
        failed = {"slug": "probe", "ok": False, "reason": "network", "warnings": []}
        healthy = {"slug": "probe", "ok": True, "reason": "ok", "warnings": []}
        self.write_status([failed])
        self.invoke("2026-08-17T10:01:00+07:00", 1)

        (self.data / "sync_lane" / "wellness.json").write_text(
            "not-json", encoding="utf-8"
        )
        self.invoke("2026-08-17T10:31:00+07:00", 1)
        notifications = self.notifications()
        self.assertEqual(len(notifications), 2, msg="\n".join(self.outputs))
        self.assertTrue(all("คลี่คลาย" not in item["title"] for item in notifications))

        self.write_status([healthy], run_at="2026-08-17T11:00:05+07:00")
        self.invoke("2026-08-17T11:01:00+07:00", 0)
        notifications = self.notifications()
        self.assertEqual(len(notifications), 3)
        self.assertIn("คลี่คลาย", notifications[-1]["title"])


@unittest.skipUnless(POWERSHELL, "PowerShell is required for notification behavior")
class HeartbeatPublisherWatchdogTests(unittest.TestCase):
    """18 ส.ค. 69: โน้ตบุ๊กหลับ 16:19–20:17 → GitHub เห็นแค่ "เงียบ" แล้วเปิด incident หลอก
    3 รอบติด. จากนอกเครื่อง "หลับ" กับ "publisher พัง" หน้าตาเหมือนกันเป๊ะ แต่ในเครื่อง
    แยกออก เพราะรู้ว่าตัวเองตื่นมานานแค่ไหน → ย้ายการเฝ้ามาไว้ตรงนี้ และนับเฉพาะเวลาตื่น
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="heartbeat-watchdog-")
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        (self.data / "sync_lane").mkdir(parents=True)
        self.sink = Path(self.temp.name) / "notifications.jsonl"
        self.outputs = []

    def write_time(self, name, value):
        (self.data / name).write_text(value, encoding="ascii")

    def invoke(self, now):
        completed = subprocess.run(
            [
                POWERSHELL,
                "-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-File", str(SCRIPT),
                "-CheckStale",
                "-StaleOnly",
                "-DataDir", str(self.data),
                "-NotificationLog", str(self.sink),
                "-NowIso", now,
                "-CooldownMinutes", "360",
            ],
            cwd=GARMIN_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=SUBPROCESS_TIMEOUT_SEC,
            check=False,
        )
        self.outputs.append(completed.stdout + completed.stderr)
        self.assertEqual(
            completed.returncode, 0, msg=completed.stdout + completed.stderr
        )

    def notifications(self):
        if not self.sink.exists():
            return []
        return [
            json.loads(line)
            for line in self.sink.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_alerts_when_the_publisher_is_silent_while_the_machine_stays_awake(self):
        self.write_time("notify_heartbeat.txt", "2026-08-18T13:31:00+07:00")
        self.write_time("notify_awake_since.txt", "2026-08-18T08:00:00+07:00")
        self.write_time("heartbeat_published_at.txt", "2026-08-18T08:25:00+07:00")

        self.invoke("2026-08-18T14:01:00+07:00")

        bodies = " ".join(item["body"] for item in self.notifications())
        self.assertIn("heartbeat", bodies, msg="\n".join(self.outputs))

    def test_stays_quiet_when_the_gap_was_the_machine_sleeping(self):
        # tick ล่าสุดค้างที่ก่อนหลับ (16:18) → รอบแรกหลังตื่นรู้ตัวว่าเพิ่งกลับมา
        self.write_time("notify_heartbeat.txt", "2026-08-18T16:18:00+07:00")
        self.write_time("notify_awake_since.txt", "2026-08-18T12:00:00+07:00")
        self.write_time("heartbeat_published_at.txt", "2026-08-18T14:25:00+07:00")

        self.invoke("2026-08-18T20:31:00+07:00")  # รอบแรกหลังตื่น
        # รอบถัดไปคือจุดที่เตือนหลอกได้จริง: ถ้านาฬิกา "ตื่นตั้งแต่" ไม่ถูกรีเซ็ตตอนตื่น
        # มันจะเห็นว่าเครื่องตื่นมา 9 ชม. และ heartbeat เก่า 6.6 ชม. แล้วเตือนทันที
        self.invoke("2026-08-18T21:01:00+07:00")

        self.assertEqual(self.notifications(), [], msg="\n".join(self.outputs))

    def test_stays_quiet_until_the_machine_has_been_awake_long_enough_to_judge(self):
        # ตื่นมา 40 นาที ยังไม่ถึงช่องส่งถัดไปด้วยซ้ำ — ความเงียบยังอธิบายได้ด้วยการหลับ
        self.write_time("notify_heartbeat.txt", "2026-08-18T20:31:00+07:00")
        self.write_time("notify_awake_since.txt", "2026-08-18T20:21:00+07:00")
        self.write_time("heartbeat_published_at.txt", "2026-08-18T14:25:00+07:00")

        self.invoke("2026-08-18T21:01:00+07:00")

        self.assertEqual(self.notifications(), [], msg="\n".join(self.outputs))

    def test_never_alerts_when_the_publisher_has_no_history_yet(self):
        self.write_time("notify_heartbeat.txt", "2026-08-18T13:31:00+07:00")
        self.write_time("notify_awake_since.txt", "2026-08-18T08:00:00+07:00")

        self.invoke("2026-08-18T14:01:00+07:00")

        self.assertEqual(self.notifications(), [], msg="\n".join(self.outputs))


if __name__ == "__main__":
    unittest.main()
