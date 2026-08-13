"""Read-only SQLite validation used by backup and restore automation."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def validate(path: str | Path) -> dict:
    database = Path(path)
    if not database.is_file():
        return {"ok": False, "quick_check": "missing", "size_bytes": 0}

    uri = f"file:{database.resolve().as_posix()}?mode=ro&immutable=1"
    try:
        connection = sqlite3.connect(uri, uri=True)
        try:
            rows = connection.execute("PRAGMA quick_check").fetchall()
        finally:
            connection.close()
    except (OSError, sqlite3.Error) as exc:
        return {
            "ok": False,
            "quick_check": f"error: {exc}",
            "size_bytes": database.stat().st_size,
        }

    messages = [str(row[0]) for row in rows]
    quick_check = "; ".join(messages)
    return {
        "ok": messages == ["ok"],
        "quick_check": quick_check,
        "size_bytes": database.stat().st_size,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit one JSON object")
    parser.add_argument("database", type=Path)
    args = parser.parse_args(argv)

    result = validate(args.database)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    elif result["ok"]:
        print(f"OK: quick_check = ok ({result['size_bytes']} bytes)")
    else:
        print(f"ERROR: {result['quick_check']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
