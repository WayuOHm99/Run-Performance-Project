#!/usr/bin/env bash
# Stop hook — รันชุดเทส garmin เมื่อมี .py ใต้ garmin/ เปลี่ยนบนสาขานี้หรือยังไม่ commit
# ไม่มี .py เปลี่ยน = ออกทันที ไม่เสียเวลา
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY="$ROOT/garmin/.venv/Scripts/python.exe"

payload=$(cat)
# กันวนไม่รู้จบ: เทิร์นนี้ต่อมาจาก Stop hook เดิมอยู่แล้ว
case "$payload" in *'"stop_hook_active": true'*|*'"stop_hook_active":true'*) exit 0 ;; esac

cd "$ROOT" || exit 0
[ -x "$PY" ] || exit 0

changed=$( { git status --porcelain -- garmin 2>/dev/null | sed 's/^...//'
             git diff --name-only main...HEAD -- garmin 2>/dev/null
           } | grep -E '\.py$' )
[ -z "$changed" ] && exit 0

out=$(cd "$ROOT/garmin" && "$PY" -m unittest discover -s tests 2>&1)
status=$?
[ $status -eq 0 ] && exit 0

summary=$(printf '%s\n' "$out" | grep -E '^(FAILED|OK|Ran |FAIL:|ERROR:)' | head -25)
PYTHONIOENCODING=utf-8 "$PY" -c '
import json, sys
print(json.dumps({
    "decision": "block",
    "reason": "เทส garmin ไม่ผ่าน ยังสรุปงานไม่ได้ (Stop hook)\n" + sys.stdin.read()
              + "\nรันเต็ม ๆ ด้วย: cd garmin && .venv/Scripts/python.exe -m unittest discover -s tests",
}, ensure_ascii=False))
' <<< "$summary"
exit 0
