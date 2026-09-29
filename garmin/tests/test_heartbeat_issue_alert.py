import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "heartbeat_issue_alert.py"


def load_script():
    spec = importlib.util.spec_from_file_location(
        "heartbeat_issue_alert_under_test", SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeGh:
    def __init__(self, open_issues=(), comments=(), fail_close_once=False):
        self.open_issues = list(open_issues)
        self.comments = list(comments)
        self.fail_close_once = fail_close_once
        self.calls = []

    def __call__(self, arguments):
        self.calls.append(list(arguments))
        if arguments[:2] == ["issue", "list"]:
            return json.dumps(self.open_issues)
        if arguments[:2] == ["issue", "create"]:
            return "https://github.com/owner/repo/issues/123\n"
        if arguments[:2] == ["issue", "view"]:
            return json.dumps({"comments": [{"body": body} for body in self.comments]})
        if arguments[:2] == ["issue", "comment"]:
            self.comments.append(arguments[arguments.index("--body") + 1])
        if arguments[:2] == ["issue", "close"] and self.fail_close_once:
            self.fail_close_once = False
            raise RuntimeError("transient close failure")
        return ""


class HeartbeatIssueAlertTests(unittest.TestCase):
    def setUp(self):
        self.alert = load_script()
        self.run_url = "https://github.com/owner/repo/actions/runs/456"

    def test_failure_opens_one_privacy_safe_incident(self):
        gh = FakeGh()

        result = self.alert.sync_incident(
            status="failure",
            repository="owner/repo",
            run_url=self.run_url,
            gh=gh,
        )

        self.assertEqual(result, {"ok": True, "action": "opened", "issue": 123})
        create = next(call for call in gh.calls if call[:2] == ["issue", "create"])
        rendered = " ".join(create)
        self.assertIn(self.run_url, rendered)
        self.assertNotRegex(rendered, r"(?i)athlete|measurement|findings")

    def test_repeated_failure_reuses_the_open_incident_without_noise(self):
        gh = FakeGh([{"number": 77, "title": "Run Performance system alert"}])

        result = self.alert.sync_incident(
            status="failure", repository="owner/repo", run_url=self.run_url, gh=gh
        )

        self.assertEqual(result, {"ok": True, "action": "existing", "issue": 77})
        self.assertEqual(len(gh.calls), 1)

    def test_recovery_comments_once_and_closes_the_incident(self):
        gh = FakeGh([{"number": 77, "title": "Run Performance system alert"}])

        result = self.alert.sync_incident(
            status="healthy", repository="owner/repo", run_url=self.run_url, gh=gh
        )

        self.assertEqual(result, {"ok": True, "action": "recovered", "issue": 77})
        self.assertEqual(
            [call[:2] for call in gh.calls],
            [
                ["issue", "list"], ["issue", "view"],
                ["issue", "comment"], ["issue", "close"],
            ],
        )

    def test_recovery_retry_does_not_duplicate_comment_after_close_failure(self):
        gh = FakeGh(
            [{"number": 77, "title": "Run Performance system alert"}],
            fail_close_once=True,
        )

        with self.assertRaises(RuntimeError):
            self.alert.sync_incident(
                status="healthy",
                repository="owner/repo",
                run_url=self.run_url,
                gh=gh,
            )
        result = self.alert.sync_incident(
            status="healthy",
            repository="owner/repo",
            run_url=self.run_url,
            gh=gh,
        )

        self.assertEqual(result, {"ok": True, "action": "recovered", "issue": 77})
        comment_calls = [call for call in gh.calls if call[:2] == ["issue", "comment"]]
        close_calls = [call for call in gh.calls if call[:2] == ["issue", "close"]]
        self.assertEqual(len(comment_calls), 1)
        self.assertEqual(len(close_calls), 2)

    def test_healthy_without_an_incident_is_a_noop(self):
        gh = FakeGh()

        result = self.alert.sync_incident(
            status="healthy", repository="owner/repo", run_url=self.run_url, gh=gh
        )

        self.assertEqual(result, {"ok": True, "action": "none"})
        self.assertEqual(len(gh.calls), 1)


class WorkflowRunVerdictTests(unittest.TestCase):
    """Only a new incident (or a broken alert) should turn the hourly run red.

    Sep 2026: the open incident #82 already tracked the outage, yet every hourly run
    failed as well and sent another GitHub notification each time.
    """

    def setUp(self):
        self.alert = load_script()
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.output = Path(temp.name) / "github_output"
        self.output.write_text("", encoding="utf-8")

    def run_main(self, result):
        argv = ["--status", "failure", "--repository", "owner/repo",
                "--run-url", "https://github.com/owner/repo/actions/runs/1"]
        with mock.patch.dict(os.environ, {"GITHUB_OUTPUT": str(self.output)}), \
                mock.patch.object(self.alert, "sync_incident", return_value=result), \
                redirect_stdout(io.StringIO()):
            self.alert.main(argv)
        return dict(
            line.split("=", 1)
            for line in self.output.read_text(encoding="utf-8").splitlines()
        )

    def test_known_incident_does_not_fail_the_run_again(self):
        outputs = self.run_main({"ok": True, "action": "existing", "issue": 82})
        self.assertEqual(outputs["fail_run"], "false")

    def test_newly_opened_incident_fails_the_run(self):
        outputs = self.run_main({"ok": True, "action": "opened", "issue": 83})
        self.assertEqual(outputs["fail_run"], "true")

    def test_broken_alert_delivery_fails_the_run(self):
        outputs = self.run_main({"ok": False, "reason": "github_issue_alert_failed"})
        self.assertEqual(outputs["fail_run"], "true")

    def test_recovery_does_not_fail_the_run(self):
        outputs = self.run_main({"ok": True, "action": "recovered", "issue": 82})
        self.assertEqual(outputs["fail_run"], "false")


if __name__ == "__main__":
    unittest.main()
