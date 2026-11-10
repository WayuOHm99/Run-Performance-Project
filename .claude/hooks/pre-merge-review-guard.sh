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
prnum=$("$PY" -c '
import re, shlex, sys
cmd = sys.stdin.read()
try:
    parts = shlex.split(cmd)
except ValueError:
    parts = cmd.split()
for i, tok in enumerate(parts[:-2]):
    if parts[i:i+3] == ["gh", "pr", "merge"]:
        skip_next = False
        for arg in parts[i+3:]:
            if skip_next:
                skip_next = False
                continue
            if arg in {"-R", "--repo", "-t", "--subject", "-b", "--body", "-F", "--body-file", "--author-email", "--match-head-commit"}:
                skip_next = True
                continue
            if arg in {"&&", "||", ";", "|"}:
                break
            if arg.startswith("-"):
                continue
            m = re.search(r"(?:^|/pull/)([0-9]+)$", arg)
            if m:
                print(m.group(1))
                break
        break
' <<< "$cmd")
[ -z "$prnum" ] && prnum=$(gh pr view --json number -q .number 2>/dev/null)

if [ -n "$prnum" ]; then
  files=$(gh pr diff "$prnum" --name-only 2>/dev/null)
  marker="$ROOT/.claude/reviewed/pr-$prnum"
else
  branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
  files=$(git diff --name-only main...HEAD 2>/dev/null)
  marker="$ROOT/.claude/reviewed/branch-${branch//\//-}"
fi

# ดูรายการไฟล์ไม่ได้ = บล็อกไว้ก่อน (fail-closed) เพื่อไม่ให้ข้ามการตรวจ path เสี่ยงโดยไม่ตั้งใจ
if [ -z "$files" ]; then
  PYTHONIOENCODING=utf-8 "$PY" -c '
import json
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason":
            "ยามรีวิวอ่านรายการไฟล์ของ PR ไม่ได้ จึงบล็อก gh pr merge ไว้ก่อน (fail-closed) — ตรวจสอบ `gh pr diff` หรือสถานะเครือข่ายแล้วลองใหม่",
    },
}, ensure_ascii=False))
'
  exit 0
fi

# รายการนี้มาจาก `git ls-files` จริง ไม่ใช่การเดา — คำว่า token เดี่ยว ๆ กว้างเกินไป
# เพราะอาจไปชนไฟล์ชื่อ design token ของหน้าจอที่ไม่เกี่ยวกับ token ของ auth
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
