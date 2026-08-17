#!/usr/bin/env python3
"""Persist per-condition alert cooldown and one-shot recovery transitions."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path


_IDENTIFIER = re.compile(r"[a-zA-Z0-9_.:'-]{1,200}\Z")
_FUTURE_SKEW = timedelta(minutes=10)


class PolicyError(ValueError):
    pass


def _aware(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise PolicyError("time_invalid") from exc
    else:
        raise PolicyError("time_invalid")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PolicyError("time_timezone_missing")
    return parsed


def _condition(value):
    if not isinstance(value, dict):
        raise PolicyError("condition_invalid")
    key = value.get("key")
    title = value.get("title")
    body = value.get("body")
    if not isinstance(key, str) or not _IDENTIFIER.fullmatch(key):
        raise PolicyError("condition_key_invalid")
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise PolicyError("condition_title_invalid")
    if not isinstance(body, str) or not body.strip() or len(body) > 2000:
        raise PolicyError("condition_body_invalid")
    return {"key": key, "title": title.strip(), "body": body.strip()}


def _load_records(path):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("version") != 1 or not isinstance(payload.get("conditions"), list):
            raise PolicyError("state_invalid")
        records = {}
        for item in payload["conditions"]:
            if not isinstance(item, dict):
                raise PolicyError("state_invalid")
            identity = item.get("identity")
            if not isinstance(identity, str) or not identity:
                raise PolicyError("state_invalid")
            records[identity] = item
        return records
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError, PolicyError):
        # A broken cooldown file must fail open: alert active conditions again,
        # then replace the broken state with one valid atomic snapshot.
        return {}


def _write_records(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "conditions": [records[key] for key in sorted(records)],
    }
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    )
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _state_lock(path, timeout_seconds=10):
    """Serialize the complete read/update/replace transaction across tasks."""
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+b")
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()

    deadline = time.monotonic() + timeout_seconds
    acquired = False
    while not acquired:
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError as exc:
            if time.monotonic() >= deadline:
                handle.close()
                raise PolicyError("state_lock_timeout") from exc
            time.sleep(0.05)
    try:
        yield
    finally:
        handle.seek(0)
        if os.name == "nt":
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def update_state(
    path, *, scope, conditions, now, cooldown, observation_complete=True
):
    if not isinstance(scope, str) or not _IDENTIFIER.fullmatch(scope):
        raise PolicyError("scope_invalid")
    if not isinstance(cooldown, timedelta) or cooldown <= timedelta(0):
        raise PolicyError("cooldown_invalid")
    if not isinstance(observation_complete, bool):
        raise PolicyError("observation_invalid")
    now = _aware(now)
    current = {}
    for raw in conditions:
        item = _condition(raw)
        if item["key"] in current:
            raise PolicyError("condition_duplicate")
        current[item["key"]] = item

    path = Path(path)
    alerts = []
    recoveries = []
    now_text = now.astimezone(timezone.utc).isoformat(timespec="seconds")
    with _state_lock(path):
        records = _load_records(path)

        # Missing conditions mean recovered only when the caller completed a
        # trustworthy observation.  Sleep/parse failures are unknown, not healthy.
        if observation_complete:
            for identity, record in list(records.items()):
                if record.get("scope") != scope or not record.get("active"):
                    continue
                key = record.get("key")
                if isinstance(key, str) and key not in current:
                    recoveries.append({
                        "key": key,
                        "title": record.get("title", "Garmin"),
                        "body": record.get("body", key),
                    })
                    record["active"] = False
                    record["changed_at"] = now_text

        for key, item in current.items():
            identity = f"{scope}|{key}"
            record = records.get(identity)
            changed = bool(
                record
                and (
                    record.get("title") != item["title"]
                    or record.get("body") != item["body"]
                )
            )
            due = record is None or not record.get("active") or changed
            if not due and record.get("last_notified"):
                try:
                    last_notified = _aware(record["last_notified"])
                    due = (
                        last_notified > now + _FUTURE_SKEW
                        or now - last_notified >= cooldown
                    )
                except PolicyError:
                    due = True
            elif not due:
                due = True

            if due:
                alerts.append(item)
            records[identity] = {
                "identity": identity,
                "scope": scope,
                **item,
                "active": True,
                "last_notified": now_text if due else record.get("last_notified"),
                "changed_at": (
                    now_text
                    if record is None or changed
                    else record.get("changed_at")
                ),
            }

        _write_records(path, records)
    return {"alerts": alerts, "recoveries": recoveries}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--scope", required=True)
    parser.add_argument("--conditions", type=Path, required=True)
    parser.add_argument("--now", default=datetime.now(timezone.utc).isoformat())
    parser.add_argument("--cooldown-minutes", type=int, default=360)
    parser.add_argument(
        "--observation", choices=("complete", "unknown"), default="complete"
    )
    args = parser.parse_args(argv)
    try:
        conditions = json.loads(args.conditions.read_text(encoding="utf-8"))
        if not isinstance(conditions, list):
            raise PolicyError("conditions_invalid")
        result = update_state(
            args.state,
            scope=args.scope,
            conditions=conditions,
            now=args.now,
            cooldown=timedelta(minutes=args.cooldown_minutes),
            observation_complete=args.observation == "complete",
        )
    except (OSError, json.JSONDecodeError, PolicyError) as exc:
        print(json.dumps({"ok": False, "reason": str(exc)}))
        return 1
    print(json.dumps({"ok": True, **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
