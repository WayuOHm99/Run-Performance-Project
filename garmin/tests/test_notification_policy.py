import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


GARMIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = GARMIN_ROOT / "scripts" / "notification_policy.py"


def load_policy():
    spec = importlib.util.spec_from_file_location("notification_policy_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


policy = load_policy()


class NotificationPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="notification-policy-")
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / "notify_state.json"
        self.start = datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc)

    @staticmethod
    def condition(key, body=None):
        return {
            "key": key,
            "title": "Garmin sync problem",
            "body": body or key,
        }

    def update(
        self, conditions, minutes=0, scope="round-wellness",
        observation_complete=True,
    ):
        return policy.update_state(
            self.state,
            scope=scope,
            conditions=conditions,
            now=self.start + timedelta(minutes=minutes),
            cooldown=timedelta(hours=6),
            observation_complete=observation_complete,
        )

    def test_per_condition_cooldown_new_condition_and_single_recovery(self):
        first = self.condition("probe:network")
        second = self.condition("other:token")

        initial = self.update([first])
        duplicate = self.update([first], minutes=30)
        new_condition = self.update([first, second], minutes=60)
        recovery = self.update([], minutes=90)
        still_healthy = self.update([], minutes=120)

        self.assertEqual([item["key"] for item in initial["alerts"]], [first["key"]])
        self.assertEqual(duplicate, {"alerts": [], "recoveries": []})
        self.assertEqual(
            [item["key"] for item in new_condition["alerts"]], [second["key"]]
        )
        self.assertEqual(
            {item["key"] for item in recovery["recoveries"]},
            {first["key"], second["key"]},
        )
        self.assertEqual(still_healthy, {"alerts": [], "recoveries": []})

    def test_same_condition_repeats_only_after_its_own_cooldown(self):
        condition = self.condition("probe:network")
        self.update([condition])

        before = self.update([condition], minutes=359)
        after = self.update([condition], minutes=360)

        self.assertEqual(before["alerts"], [])
        self.assertEqual([item["key"] for item in after["alerts"]], [condition["key"]])

    def test_changed_condition_body_is_actionable_immediately(self):
        original = self.condition("probe:warning", "one warning")
        changed = self.condition("probe:warning", "two warnings")
        self.update([original])

        result = self.update([changed], minutes=5)

        self.assertEqual(result["alerts"][0]["body"], "two warnings")

    def test_corrupt_state_fails_open_and_is_replaced_atomically(self):
        self.state.write_text("not-json", encoding="utf-8")

        result = self.update([self.condition("probe:network")])

        self.assertEqual(len(result["alerts"]), 1)
        stored = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(stored["version"], 1)
        self.assertFalse(self.state.with_suffix(".json.tmp").exists())

    def test_unknown_observation_does_not_emit_false_recovery(self):
        condition = self.condition("probe:network")
        self.update([condition])

        unknown = self.update([], minutes=30, observation_complete=False)
        recovered = self.update([], minutes=60, observation_complete=True)
        healthy = self.update([], minutes=90, observation_complete=True)

        self.assertEqual(unknown, {"alerts": [], "recoveries": []})
        self.assertEqual(
            [item["key"] for item in recovered["recoveries"]], [condition["key"]]
        )
        self.assertEqual(healthy, {"alerts": [], "recoveries": []})

    def test_future_last_notified_fails_open(self):
        condition = self.condition("probe:network")
        self.update([condition])
        stored = json.loads(self.state.read_text(encoding="utf-8"))
        stored["conditions"][0]["last_notified"] = "2099-01-01T00:00:00+00:00"
        self.state.write_text(json.dumps(stored), encoding="utf-8")

        result = self.update([condition], minutes=5)

        self.assertEqual(
            [item["key"] for item in result["alerts"]], [condition["key"]]
        )

    def test_concurrent_scopes_do_not_lose_each_others_state(self):
        processes = []
        for index in range(8):
            condition_path = Path(self.temp.name) / f"conditions-{index}.json"
            condition_path.write_text(
                json.dumps([self.condition(f"condition-{index}")]), encoding="utf-8"
            )
            processes.append(subprocess.Popen(
                [
                    sys.executable, str(SCRIPT),
                    "--state", str(self.state),
                    "--scope", f"scope-{index}",
                    "--conditions", str(condition_path),
                    "--now", self.start.isoformat(),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            ))
        completed = [process.communicate(timeout=20) for process in processes]
        self.assertTrue(
            all(process.returncode == 0 for process in processes), msg=str(completed)
        )
        stored = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(len(stored["conditions"]), 8)


if __name__ == "__main__":
    unittest.main()
