#!/usr/bin/env bash
# PreToolUse (Bash) — ดัก `gh pr merge` เมื่อ PR แตะ path เสี่ยงตาม CLAUDE.md
# path เสี่ยง = เขียน DB (03_backfill.py, schema, migration) · token/auth/ACL · backup/restore
# ปลดล็อกโดยรัน /code-review แล้ววางไฟล์ .claude/reviewed/pr-<N> (หรือ branch-<ชื่อ>)
set -uo pipefail

payload=$(cat)
# ทางลัดแบบ bash ล้วน: ไม่เกี่ยวกับ gh pr merge ก็ออกทันที ไม่ต้องเรียก python
case "$payload" in *"gh pr merge"*) ;; *) exit 0 ;; esac

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY="$ROOT/garmin/.venv/Scripts/python.exe"
[ -x "$PY" ] || exit 0

cmd=$("$PY" -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' <<< "$payload")
case "$cmd" in *"gh pr merge"*) ;; *) exit 0 ;; esac

cd "$ROOT" || exit 0
prnum=$(printf '%s' "$cmd" | grep -oE 'gh pr merge[[:space:]]+[0-9]+' | grep -oE '[0-9]+$' | head -1)
[ -z "$prnum" ] && prnum=$(gh pr view --json number -q .number 2>/dev/null)

if [ -n "$prnum" ]; then
  files=$(gh pr diff "$prnum" --name-only 2>/dev/null)
  marker="$ROOT/.claude/reviewed/pr-$prnum"
else
  branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
  files=$(git diff --name-only main...HEAD 2>/dev/null)
  marker="$ROOT/.claude/reviewed/branch-${branch//\//-}"
fi

# ดูรายการไฟล์ไม่ได้ = ไม่บล็อก แต่บอกให้รู้ว่ายามตัวนี้มองไม่เห็นอะไร
[ -z "$files" ] && { printf '%s\n' '{"systemMessage":"ยามรีวิว: ดูรายการไฟล์ของ PR ไม่ได้ ปล่อยผ่านโดยไม่ตรวจ"}'; exit 0; }

# รายการนี้มาจาก `git ls-files` จริง ไม่ใช่การเดา — คำว่า token กว้างเกินไป
# เพราะ test_dashboard_chart_tokens.py คือ design token ไม่ใช่ token ของ auth
RISKY='(_backfill\.py|_init_schema\.py|schema|migrat|get_garmin_token\.py|_generate_token\.py|test_share_token\.py|test_ops_security\.py|backup|restore|offsite|harden_private_acl)'
hits=$(printf '%s\n' "$files" | grep -iE "$RISKY")
[ -z "$hits" ] && exit 0
[ -f "$marker" ] && exit 0

MARKER="$marker" PYTHONIOENCODING=utf-8 "$PY" -c '
import json, os, sys
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason":
            "PR นี้แตะ path เสี่ยงตาม CLAUDE.md ต้องผ่าน /code-review ก่อน merge:\n"
            + sys.stdin.read().strip()
            + "\n\nรีวิวเสร็จแล้วปลดล็อกด้วย: touch " + os.environ["MARKER"],
    },
}, ensure_ascii=False))
' <<< "$hits"
exit 0
