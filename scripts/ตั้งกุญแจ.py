#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ตั้งกุญแจ.py — ใส่/เปลี่ยน Supabase secret key แบบปลอดภัย

ทำไมต้องมีตัวนี้
  กุญแจ secret เปิดฐานข้อมูลได้ทั้งหมด ถ้าพิมพ์ลงในแชทหรือที่ไหนก็ตาม
  ถือว่าหลุดทันที ตัวนี้รับค่าแบบซ่อน (พิมพ์แล้วไม่ขึ้นบนจอ) เขียนลงไฟล์ .env
  ในเครื่องโดยตรง แล้วทดสอบให้ว่าใช้ได้จริง — ไม่ผ่านมือใครทั้งนั้น

วิธีใช้
  python ตั้งกุญแจ.py
  (หรือดับเบิลคลิก  ตั้งกุญแจ.bat)
"""

from __future__ import annotations

import getpass
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
ENV_FILE = SCRIPT_DIR / ".env"
DEFAULT_URL = "https://tnmxpwcyfaekwwwrefjd.supabase.co"

PAGE = "https://supabase.com/dashboard/project/tnmxpwcyfaekwwwrefjd/settings/api-keys"


def looks_like_key(v: str) -> tuple[bool, str]:
    if not v:
        return False, "ไม่ได้ใส่อะไรมาเลย"
    if " " in v or "\t" in v:
        return False, "มีช่องว่างปนอยู่ — น่าจะก๊อปมาเกิน"
    if v.lower() in ("service_role", "secret", "secret key", "service role"):
        return False, "นี่คือ 'ชื่อหัวข้อ' ไม่ใช่ค่าจริง — ค่าจริงอยู่ใต้หัวข้อนั้น"
    if v.startswith("sb_publishable_") or v.startswith("sb_p"):
        return False, "นี่คือ publishable key (ตัวสาธารณะ) ต้องใช้ตัว secret"
    if not (v.startswith("sb_secret_") or v.startswith("eyJ")):
        return False, "ค่าที่ถูกต้องต้องขึ้นต้นด้วย 'sb_secret_' หรือ 'eyJ'"
    if len(v) < 30:
        return False, f"สั้นผิดปกติ ({len(v)} ตัวอักษร)"
    return True, ""


def test_key(url: str, key: str) -> tuple[bool, str]:
    q = urllib.parse.urlencode({"select": "line_user_id", "limit": "1"})
    req = urllib.request.Request(
        f"{url}/rest/v1/line_athletes?{q}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            json.loads(r.read())
        return True, ""
    except urllib.error.HTTPError as e:
        return False, f"Supabase ตอบ HTTP {e.code} — {e.read().decode('utf-8','replace')[:200]}"
    except urllib.error.URLError as e:
        return False, f"ต่อเน็ตไม่ได้: {e.reason}"


def main() -> None:
    print()
    print("=" * 56)
    print("  ตั้ง / เปลี่ยนกุญแจ Supabase")
    print("=" * 56)
    print()
    print("หากุญแจได้ที่หน้านี้ (ก๊อปลิงก์ไปเปิดในเบราว์เซอร์):")
    print(f"   {PAGE}")
    print()
    print("   เลือกแถวที่เป็น  secret / service_role  (ไม่ใช่ publishable)")
    print("   ค่าที่ถูกต้องจะยาวมากและขึ้นต้นด้วย  sb_secret_  หรือ  eyJ")
    print()
    print("*** ตอนพิมพ์/วาง ค่าจะไม่ปรากฏบนจอ เป็นเรื่องปกติ ไม่ใช่ค้าง ***")
    print("    วางด้วยการคลิกขวา หรือ Ctrl+V แล้วกด Enter")
    print()

    key = getpass.getpass("วางกุญแจแล้วกด Enter: ").strip()

    ok, why = looks_like_key(key)
    if not ok:
        print(f"\n[ไม่ผ่าน] {why}")
        print("         ลองใหม่อีกครั้ง — ไม่มีอะไรถูกบันทึก\n")
        sys.exit(1)

    print(f"\n   รูปแบบถูกต้อง (ยาว {len(key)} ตัวอักษร) — กำลังทดสอบกับ Supabase...")

    url = DEFAULT_URL
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("SUPABASE_URL="):
                url = line.split("=", 1)[1].strip() or DEFAULT_URL

    good, err = test_key(url, key)
    if not good:
        print(f"\n[ใช้ไม่ได้] {err}")
        print("           ไฟล์เดิมไม่ถูกแตะต้อง ลองก๊อปใหม่อีกครั้ง\n")
        sys.exit(1)

    if ENV_FILE.exists():
        backup = ENV_FILE.with_suffix(".env.bak")
        backup.write_text(ENV_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"   สำรองไฟล์เดิมไว้ที่ {backup.name}")

    ENV_FILE.write_text(
        f"SUPABASE_SERVICE_KEY={key}\nSUPABASE_URL={url}\n", encoding="utf-8"
    )

    print("\n[สำเร็จ] ทดสอบผ่านและบันทึกลง .env แล้ว")
    print("         รันดึงข้อมูลได้เลย:  python sync_line.py --dry-run\n")


if __name__ == "__main__":
    main()
