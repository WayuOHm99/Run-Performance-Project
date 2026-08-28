#!/usr/bin/env bash
# Stop hook — ชั้นที่ 4 ของ CLAUDE.md: บูต streamlit จริงเมื่อ dashboard.py หรือ
# .streamlit/config.toml เปลี่ยน แล้ว **บังคับให้มันรันสคริปต์หนึ่งรอบ** ก่อนอ่าน log
#
# สูตรเดิมในไฟล์ CLAUDE.md (`streamlit run` + `grep error` + รอ 40 วิ) แดงไม่เป็น —
# 27 ส.ค. 69 ใส่ `import` ที่ไม่มีอยู่จริงลง dashboard.py แล้วมันยังเขียว
# เพราะเซิร์ฟเวอร์ไม่แตะสคริปต์เลยจนกว่าจะมี client ต่อเข้ามา
# ตัวนี้จึงใช้ drive_session.py ต่อ websocket เข้าไปสั่งรัน แล้วดูทั้ง exception
# ที่ส่งกลับมาและ error ใน log ของเซิร์ฟเวอร์
#
# ยังพิสูจน์ไม่ได้ด้วยชั้นนี้: ฟอนต์ถูกวาดไหม CSS ทับกันไหม กราฟอ่านง่ายขึ้นไหม
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY="$ROOT/garmin/.venv/Scripts/python.exe"
DRIVER="$ROOT/.claude/hooks/drive_session.py"
PORT=8988

payload=$(cat)
case "$payload" in *'"stop_hook_active": true'*|*'"stop_hook_active":true'*) exit 0 ;; esac

cd "$ROOT" || exit 0
[ -x "$PY" ] || exit 0

touched=$( { git status --porcelain -- garmin 2>/dev/null | sed 's/^...//'
             git diff --name-only main...HEAD -- garmin 2>/dev/null
           } | grep -E 'garmin/scripts/dashboard\.py$|garmin/\.streamlit/config\.toml$' )
[ -z "$touched" ] && exit 0

LOG=$(mktemp)
cd "$ROOT/garmin" || exit 0
"$PY" -m streamlit run scripts/dashboard.py \
    --server.headless=true --server.port="$PORT" --server.fileWatcherType=none \
    > "$LOG" 2>&1 &
pid=$!

up=0
for _ in $(seq 1 60); do
  if curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$PORT/_stcore/health"; then up=1; break; fi
  kill -0 "$pid" 2>/dev/null || break
  sleep 0.5
done

if [ "$up" -eq 1 ]; then
  driven=$(PYTHONIOENCODING=utf-8 "$PY" "$DRIVER" "$PORT" 2>&1)
else
  driven="EXCEPTION boot: เซิร์ฟเวอร์ไม่ตอบ /_stcore/health ภายใน 30 วินาที"
fi
kill "$pid" 2>/dev/null
wait "$pid" 2>/dev/null

logged=$(grep -iE 'error|traceback|should have|exception' "$LOG" | head -10)
rm -f "$LOG"
bad=$(printf '%s\n%s' "$driven" "$logged" | grep -v '^$')
[ -z "$bad" ] && exit 0

PYTHONIOENCODING=utf-8 "$PY" -c '
import json, sys
print(json.dumps({
    "decision": "block",
    "reason": "เปิด dashboard จริงแล้วมี error ยังสรุปงานไม่ได้ (Stop hook)\n" + sys.stdin.read(),
}, ensure_ascii=False))
' <<< "$bad"
exit 0
