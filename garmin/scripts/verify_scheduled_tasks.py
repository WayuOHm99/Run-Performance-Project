"""Read-only comparison of installed Windows tasks with the declared plan."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

try:
    import win_process
except ModuleNotFoundError:
    _spec = importlib.util.spec_from_file_location(
        "scheduler_win_process", Path(__file__).with_name("win_process.py")
    )
    win_process = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(win_process)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SETUP_SCRIPT = PROJECT_ROOT / "scripts" / "setup_scheduled_tasks.ps1"
NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}


def _text(root, path, default=None):
    node = root.find(path, NS)
    if node is None or node.text is None:
        return default
    return node.text.strip()


def _bool_text(value):
    return str(value or "").casefold() == "true"


def _parse_boundary(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.utcoffset() is not None else None


def _duration(value):
    match = re.fullmatch(
        r"P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?"
        r"(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?",
        value or "",
    )
    if not match:
        return None
    parts = {name: int(number or 0) for name, number in match.groupdict().items()}
    return timedelta(**parts)


def _trigger_clock(boundary):
    if boundary is None:
        return {"startTime": None, "utcOffset": None}
    offset = boundary.strftime("%z")
    return {
        "startTime": boundary.strftime("%H:%M:%S"),
        "utcOffset": f"{offset[:3]}:{offset[3:]}",
    }


def normalize_task_xml(source: str, *, now=None) -> dict:
    now = now or datetime.now().astimezone()
    root = ET.fromstring(source)
    disallow_battery = _bool_text(
        _text(root, "t:Settings/t:DisallowStartIfOnBatteries", "false")
    )
    stop_on_battery = _bool_text(
        _text(root, "t:Settings/t:StopIfGoingOnBatteries", "false")
    )
    triggers = []
    trigger_root = root.find("t:Triggers", NS)
    for trigger in list(trigger_root) if trigger_root is not None else []:
        kind = trigger.tag.rsplit("}", 1)[-1]
        boundary = _parse_boundary(_text(trigger, "t:StartBoundary"))
        clock = _trigger_clock(boundary)
        end_boundary_text = _text(trigger, "t:EndBoundary")
        end_boundary = _parse_boundary(end_boundary_text)
        end_boundary_value = (
            end_boundary.isoformat(timespec="seconds")
            if end_boundary
            else end_boundary_text
        )
        enabled = _bool_text(_text(trigger, "t:Enabled", "true"))
        if kind == "TimeTrigger":
            duration_text = _text(trigger, "t:Repetition/t:Duration")
            repeat_duration = _duration(duration_text)
            window_active = bool(
                boundary is not None
                and repeat_duration is not None
                and boundary <= now.astimezone(boundary.tzinfo)
                < boundary + repeat_duration
            )
            triggers.append({
                "type": "time",
                **clock,
                "endBoundary": end_boundary_value,
                "enabled": enabled,
                "interval": _text(trigger, "t:Repetition/t:Interval"),
                "duration": duration_text,
                "windowActive": window_active,
            })
        elif trigger.find("t:ScheduleByDay", NS) is not None:
            triggers.append({
                "type": "daily",
                **clock,
                "endBoundary": end_boundary_value,
                "enabled": enabled,
                "daysInterval": int(
                    _text(trigger, "t:ScheduleByDay/t:DaysInterval", "0")
                ),
            })
        elif trigger.find("t:ScheduleByWeek", NS) is not None:
            days = trigger.find("t:ScheduleByWeek/t:DaysOfWeek", NS)
            start_boundary = _text(trigger, "t:StartBoundary")
            triggers.append({
                "type": "weekly",
                "startBoundary": (
                    boundary.isoformat(timespec="seconds") if boundary else start_boundary
                ),
                **clock,
                "endBoundary": end_boundary_value,
                "enabled": enabled,
                "weeksInterval": int(
                    _text(trigger, "t:ScheduleByWeek/t:WeeksInterval", "0")
                ),
                "daysOfWeek": [
                    child.tag.rsplit("}", 1)[-1]
                    for child in (list(days) if days is not None else [])
                ],
            })
        else:
            triggers.append({
                "type": kind,
                **clock,
                "endBoundary": end_boundary_value,
                "enabled": enabled,
            })

    actions_root = root.find("t:Actions", NS)
    actions = list(actions_root) if actions_root is not None else []
    return {
        "actionCount": len(actions),
        "actionTypes": [action.tag.rsplit("}", 1)[-1] for action in actions],
        "exe": _text(root, "t:Actions/t:Exec/t:Command", ""),
        "argument": _text(root, "t:Actions/t:Exec/t:Arguments", ""),
        "workingDirectory": _text(
            root, "t:Actions/t:Exec/t:WorkingDirectory", ""
        ),
        "logonType": _text(root, "t:Principals/t:Principal/t:LogonType", ""),
        "executionTimeLimit": _text(root, "t:Settings/t:ExecutionTimeLimit", ""),
        "retryCount": int(
            _text(root, "t:Settings/t:RestartOnFailure/t:Count", "0")
        ),
        "retryInterval": _text(
            root, "t:Settings/t:RestartOnFailure/t:Interval"
        ),
        "onBattery": not disallow_battery and not stop_on_battery,
        "multipleInstances": _text(
            root, "t:Settings/t:MultipleInstancesPolicy", ""
        ),
        "startWhenAvailable": _bool_text(
            _text(root, "t:Settings/t:StartWhenAvailable", "false")
        ),
        "triggers": triggers,
    }


def compare_task(expected: dict, actual: dict) -> list[str]:
    checks = {
        "action_count": "actionCount",
        "action_types": "actionTypes",
        "action_executable": "exe",
        "action_arguments": "argument",
        "working_directory": "workingDirectory",
        "logon_type": "logonType",
        "execution_time_limit": "executionTimeLimit",
        "retry_count": "retryCount",
        "retry_interval": "retryInterval",
        "battery_policy": "onBattery",
        "overlap_policy": "multipleInstances",
        "start_when_available": "startWhenAvailable",
        "trigger_schedule": "triggers",
    }
    problems = []
    for code, key in checks.items():
        wanted = expected.get(key)
        found = actual.get(key)
        if key in {"exe", "workingDirectory"}:
            wanted = os.path.normcase(str(wanted or ""))
            found = os.path.normcase(str(found or ""))
        if wanted != found:
            problems.append(code)
    return problems


def _declared_plan() -> dict:
    completed = win_process.run(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(SETUP_SCRIPT), "-DryRun", "-Json", "-IncludeOptional",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("declared_plan_failed")
    return json.loads(completed.stdout)


def _installed_xml(task_name: str) -> str:
    environment = os.environ.copy()
    environment["RUN_PERF_TASK_NAME"] = task_name
    command = (
        "[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding $false; "
        "Export-ScheduledTask -TaskName $env:RUN_PERF_TASK_NAME"
    )
    completed = win_process.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        env=environment,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("task_missing_or_unreadable")
    return completed.stdout


def verify(plan: dict, xml_provider=_installed_xml) -> dict:
    results = []
    for expected in plan.get("tasks", []):
        name = expected.get("name", "unknown")
        try:
            actual = normalize_task_xml(xml_provider(name))
            problems = compare_task(expected, actual)
        except (ET.ParseError, OSError, RuntimeError, ValueError):
            problems = ["task_missing_or_unreadable"]
        results.append({"name": name, "ok": not problems, "problems": problems})
    return {"ok": all(item["ok"] for item in results), "tasks": results}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if os.name != "nt":
        payload = {"ok": False, "available": False, "reason": "not_windows"}
        print(json.dumps(payload) if args.json else "Windows only")
        return 2
    try:
        payload = {"available": True, **verify(_declared_plan())}
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        payload = {"ok": False, "available": True, "reason": str(exc)}
    print(json.dumps(payload, ensure_ascii=False) if args.json else json.dumps(payload, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
