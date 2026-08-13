"""Publish a privacy-preserving external heartbeat for the local health report."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


GARMIN_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = GARMIN_ROOT.parent
HEALTH_REPORT = GARMIN_ROOT / "scripts" / "health_report.py"
RELEASE_TAG = "system-health"
ASSET_NAME = "system-health.json"


class HeartbeatError(RuntimeError):
    pass


def summarize(report: dict) -> dict:
    raw_summary = report.get("summary")
    if not isinstance(raw_summary, dict):
        raise HeartbeatError("summary_missing")
    summary = {}
    for key in ("ok", "warning", "error", "total"):
        value = raw_summary.get(key)
        if not isinstance(value, int) or value < 0:
            raise HeartbeatError("summary_invalid")
        summary[key] = value
    if summary["ok"] + summary["warning"] + summary["error"] != summary["total"]:
        raise HeartbeatError("summary_inconsistent")
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "error" if summary["error"] else "ok",
        "summary": summary,
    }


def _run(command: list[str], *, cwd=None, timeout=180, allow_failure=False):
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0 and not allow_failure:
        raise HeartbeatError(f"command_failed:{Path(command[0]).name}")
    return completed


def _github_repository(gh: str) -> str:
    result = _run(
        [gh, "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        cwd=PROJECT_ROOT,
    )
    repository = result.stdout.strip()
    if "/" not in repository:
        raise HeartbeatError("github_repository_unknown")
    return repository


def _ensure_release(gh: str, repository: str) -> None:
    result = _run(
        [gh, "release", "view", RELEASE_TAG, "--repo", repository],
        allow_failure=True,
    )
    if result.returncode == 0:
        return
    _run(
        [
            gh, "release", "create", RELEASE_TAG, "--repo", repository,
            "--title", "System health heartbeat",
            "--notes", "Machine-readable status only; contains no athlete findings or health measurements.",
            "--latest=false", "--target", "main",
        ]
    )


def publish() -> dict:
    gh = shutil.which("gh")
    if not gh:
        raise HeartbeatError("gh_missing")
    report_result = _run(
        [sys.executable, str(HEALTH_REPORT), "--json"],
        cwd=GARMIN_ROOT,
        timeout=180,
        allow_failure=True,
    )
    try:
        report = json.loads(report_result.stdout)
    except json.JSONDecodeError as exc:
        raise HeartbeatError("health_report_invalid") from exc
    heartbeat = summarize(report)
    repository = _github_repository(gh)
    _ensure_release(gh, repository)
    with tempfile.TemporaryDirectory(prefix="run-performance-heartbeat-") as raw:
        asset = Path(raw) / ASSET_NAME
        asset.write_text(json.dumps(heartbeat, ensure_ascii=False), encoding="utf-8")
        _run(
            [
                gh, "release", "upload", RELEASE_TAG, str(asset),
                "--repo", repository, "--clobber",
            ]
        )
    return heartbeat


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    summarize_parser = subparsers.add_parser("summarize")
    summarize_parser.add_argument("report", type=Path)
    subparsers.add_parser("publish")
    args = parser.parse_args(argv)

    try:
        if args.command == "summarize":
            heartbeat = summarize(json.loads(args.report.read_text(encoding="utf-8")))
        else:
            heartbeat = publish()
    except (HeartbeatError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "reason": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(heartbeat, ensure_ascii=False))
    return 1 if heartbeat["status"] == "error" else 0


if __name__ == "__main__":
    sys.exit(main())
