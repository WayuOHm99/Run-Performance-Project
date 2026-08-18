"""Publish a privacy-preserving external heartbeat for the local health report."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

try:  # รันปกติ (scripts/ อยู่ใน sys.path)
    import win_process
except ModuleNotFoundError:  # ถูกโหลดตรงด้วย importlib จาก cwd ไหนก็ได้
    _wp_spec = importlib.util.spec_from_file_location(
        "garmin_win_process", Path(__file__).with_name("win_process.py")
    )
    win_process = importlib.util.module_from_spec(_wp_spec)
    _wp_spec.loader.exec_module(win_process)


GARMIN_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = GARMIN_ROOT.parent
DATA_DIR = Path(os.environ.get("GARMIN_DATA_DIR", GARMIN_ROOT / "data"))
HEALTH_REPORT = GARMIN_ROOT / "scripts" / "health_report.py"
RELEASE_TAG = "system-health"
ASSET_NAME = "system-health.json"
PUBLISH_MARKER = "heartbeat_published_at.txt"


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
    completed = win_process.run(
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
        # ชื่อคำสั่ง + สาเหตุ (แยก "โดนสั่งจบ" ออกจาก "จบเองแบบล้มเหลว") โดยไม่พก
        # stdout/stderr ติดไปด้วย — heartbeat ห้ามพารายละเอียดออกนอกเครื่อง
        raise HeartbeatError(
            f"command_failed:{win_process.command_label(command)}:"
            f"{win_process.exit_reason(completed.returncode)}"
        )
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


def record_publish(*, data_dir=None, now=None) -> Path:
    """บันทึกเวลาที่ส่ง heartbeat สำเร็จไว้ในเครื่อง.

    GitHub เห็นได้แค่ "ไม่มีของใหม่มา" ซึ่งแปลว่าเครื่องหลับก็ได้ publisher พังก็ได้ —
    แยกไม่ออกจากข้างนอก. ในเครื่องแยกออก เพราะรู้ว่าตัวเองตื่นมานานแค่ไหน; marker นี้
    คือฝั่งหนึ่งของการเทียบนั้น (อีกฝั่งคือ notify_sync.ps1 -CheckStale).
    """
    target = Path(data_dir) if data_dir is not None else DATA_DIR
    target.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now().astimezone()).isoformat(timespec="seconds")
    marker = target / PUBLISH_MARKER
    marker.write_text(stamp, encoding="ascii")
    return marker


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
    # หลัง upload สำเร็จเท่านั้น — รอบที่อัปโหลดล้มต้องไม่ทิ้งหลักฐานว่าสำเร็จไว้
    # ไม่งั้น watchdog ในเครื่องจะเงียบทั้งที่ publisher พังอยู่
    record_publish()
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
