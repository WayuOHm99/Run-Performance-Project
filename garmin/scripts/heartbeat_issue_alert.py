#!/usr/bin/env python3
"""Keep one privacy-safe GitHub Issue in sync with heartbeat health."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

try:
    import win_process
except ModuleNotFoundError:
    _spec = importlib.util.spec_from_file_location(
        "heartbeat_alert_win_process", Path(__file__).with_name("win_process.py")
    )
    win_process = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(win_process)


INCIDENT_TITLE = "Run Performance system alert"
RECOVERY_MARKER = "<!-- run-performance-heartbeat-recovered -->"
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class AlertError(RuntimeError):
    pass


def _run_gh(arguments):
    completed = win_process.run(
        ["gh", *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        raise AlertError("github_issue_command_failed")
    return completed.stdout.strip()


def _open_incident(repository, gh):
    raw = gh([
        "issue", "list", "--repo", repository, "--state", "open",
        "--limit", "100", "--json", "number,title",
    ])
    try:
        issues = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise AlertError("github_issue_response_invalid") from exc
    if not isinstance(issues, list):
        raise AlertError("github_issue_response_invalid")
    for issue in issues:
        if not isinstance(issue, dict) or issue.get("title") != INCIDENT_TITLE:
            continue
        number = issue.get("number")
        if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
            raise AlertError("github_issue_response_invalid")
        return number
    return None


def _validate_scope(repository, run_url):
    if not REPOSITORY_PATTERN.fullmatch(repository or ""):
        raise AlertError("repository_invalid")
    expected_prefix = f"https://github.com/{repository}/actions/runs/"
    if not isinstance(run_url, str) or not run_url.startswith(expected_prefix):
        raise AlertError("run_url_invalid")


def _recovery_was_commented(repository, issue, gh):
    raw = gh([
        "issue", "view", str(issue), "--repo", repository,
        "--json", "comments",
    ])
    try:
        payload = json.loads(raw)
        comments = payload["comments"]
    except (TypeError, KeyError, json.JSONDecodeError) as exc:
        raise AlertError("github_issue_response_invalid") from exc
    if not isinstance(comments, list):
        raise AlertError("github_issue_response_invalid")
    return any(
        isinstance(comment, dict)
        and isinstance(comment.get("body"), str)
        and RECOVERY_MARKER in comment["body"]
        for comment in comments
    )


def sync_incident(*, status, repository, run_url, gh=_run_gh):
    """Open once on failure; comment and close once after recovery."""
    if status not in {"healthy", "failure"}:
        raise AlertError("status_invalid")
    _validate_scope(repository, run_url)
    issue = _open_incident(repository, gh)

    if status == "failure":
        if issue is not None:
            return {"ok": True, "action": "existing", "issue": issue}
        body = (
            "The local system heartbeat did not pass external validation.\n\n"
            f"Workflow evidence: {run_url}\n\n"
            "Next step: after the Windows user logs in, run "
            "`garmin\\.venv\\Scripts\\python.exe "
            "garmin\\scripts\\health_report.py --json` and inspect ERROR items."
        )
        created = gh([
            "issue", "create", "--repo", repository,
            "--title", INCIDENT_TITLE, "--body", body,
        ])
        match = re.search(r"/issues/(\d+)\s*$", created)
        if not match:
            raise AlertError("github_issue_create_response_invalid")
        return {"ok": True, "action": "opened", "issue": int(match.group(1))}

    if issue is None:
        return {"ok": True, "action": "none"}
    recovery = (
        f"{RECOVERY_MARKER}\n"
        "Recovery confirmed by a fresh healthy heartbeat.\n\n"
        f"Workflow evidence: {run_url}"
    )
    if not _recovery_was_commented(repository, issue, gh):
        gh([
            "issue", "comment", str(issue), "--repo", repository,
            "--body", recovery,
        ])
    gh([
        "issue", "close", str(issue), "--repo", repository,
        "--reason", "completed",
    ])
    return {"ok": True, "action": "recovered", "issue": issue}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", required=True, choices=("healthy", "failure"))
    parser.add_argument(
        "--repository", default=os.environ.get("GITHUB_REPOSITORY")
    )
    parser.add_argument("--run-url", required=True)
    args = parser.parse_args(argv)
    try:
        result = sync_incident(
            status=args.status,
            repository=args.repository,
            run_url=args.run_url,
        )
    except (AlertError, OSError, ValueError):
        result = {"ok": False, "reason": "github_issue_alert_failed"}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
