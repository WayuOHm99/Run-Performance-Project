#!/usr/bin/env python3
"""
สร้าง Garmin Connect token เพื่อส่งให้หัวหน้าทีม (Standalone — ใช้ไฟล์เดียว)

วิธีใช้ (ทำครั้งเดียว):
  1) ติดตั้ง Python 3.12 ขึ้นไป  ->  https://www.python.org/downloads/
     (ตอนติดตั้งบน Windows ให้ติ๊ก "Add Python to PATH")
  2) เปิด Terminal / PowerShell / CMD ในโฟลเดอร์ที่มีไฟล์นี้
  3) พิมพ์:   python get_garmin_token.py
  4) กรอก ชื่อ / อีเมล / รหัสผ่าน Garmin (+ โค้ด MFA ถ้าเปิดไว้)
  5) ส่งไฟล์ .zip ที่ได้กลับให้หัวหน้าทีม "ทางแชทส่วนตัวเท่านั้น"

หมายเหตุความปลอดภัย:
  * รหัสผ่านของคุณไม่ถูกบันทึกลงไฟล์ใด ๆ ทั้งสิ้น
  * ไฟล์ที่ส่งกลับเก็บเฉพาะ "token" ที่ใช้ดึงข้อมูลสุขภาพ/กิจกรรม
    (ยกเลิกได้ทุกเมื่อโดยเปลี่ยนรหัส Garmin หรือออกจากระบบทุกอุปกรณ์)
"""

import re
import subprocess
import sys
import zipfile
from getpass import getpass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
MIN_PY = (3, 12)


def check_python() -> None:
    if sys.version_info < MIN_PY:
        cur = ".".join(map(str, sys.version_info[:3]))
        print(f"❌ ต้องใช้ Python {MIN_PY[0]}.{MIN_PY[1]} ขึ้นไป (ของคุณคือ {cur})")
        print("   ดาวน์โหลดเวอร์ชันใหม่ที่: https://www.python.org/downloads/")
        _pause_exit(1)


def ensure_garminconnect():
    try:
        import garminconnect  # noqa: F401
        return
    except ImportError:
        pass

    print("📦 ยังไม่มีไลบรารี garminconnect — กำลังติดตั้งให้อัตโนมัติ (รอสักครู่)...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "garminconnect"]
        )
    except Exception as e:  # noqa: BLE001
        print(f"❌ ติดตั้งอัตโนมัติไม่สำเร็จ: {e}")
        print("   ลองรันคำสั่งนี้เองในเทอร์มินัลก่อน แล้วรันสคริปต์ใหม่:")
        print(f"   {sys.executable} -m pip install garminconnect")
        _pause_exit(1)

    import importlib
    importlib.invalidate_caches()


def slugify(name: str) -> str:
    """แปลงชื่อให้เป็น slug ปลอดภัย: a-z, 0-9, _ เท่านั้น."""
    s = name.strip().lower().replace(" ", "_")
    return re.sub(r"[^a-z0-9_]+", "", s)


def _pause_exit(code: int) -> None:
    """หยุดรอ Enter ก่อนปิด (กันหน้าต่างปิดเองตอนดับเบิลคลิก) แล้วออก."""
    try:
        input("\nกด Enter เพื่อปิด...")
    except EOFError:
        pass
    sys.exit(code)


def main() -> None:
    print("=" * 52)
    print("  Garmin Connect — สร้าง Token ให้ทีมวิ่ง")
    print("=" * 52)
    print()

    check_python()
    ensure_garminconnect()
    from garminconnect import Garmin

    # 1) ชื่อ (ใช้ตั้งชื่อไฟล์ + ให้หัวหน้าทีมรู้ว่าเป็นของใคร)
    raw_name = input("ชื่อของคุณเป็นภาษาอังกฤษ (เช่น testohm, tong): ").strip()
    name = slugify(raw_name)
    if not name:
        print("❌ ชื่อต้องมีตัวอักษรอังกฤษหรือตัวเลขอย่างน้อย 1 ตัว")
        _pause_exit(1)

    # 2) ข้อมูลเข้าสู่ระบบ (ไม่ถูกบันทึก)
    email = input("อีเมล Garmin Connect: ").strip()
    password = getpass("รหัสผ่าน Garmin (พิมพ์ไปได้เลย จอจะไม่แสดง): ")
    if not email or not password:
        print("❌ ต้องกรอกทั้งอีเมลและรหัสผ่าน")
        _pause_exit(1)

    token_dir = SCRIPT_DIR / f"garmin_token_{name}"
    token_dir.mkdir(parents=True, exist_ok=True)

    # 3) เข้าสู่ระบบ
    print()
    print(f"🔐 กำลังเข้าสู่ระบบด้วย {email} ...")
    print("   (ถ้าเปิด MFA/2FA ไว้ ให้เปิดแอป/ดู SMS/อีเมล เพื่อเอาโค้ดมากรอก)")
    print()

    try:
        garmin = Garmin(
            email,
            password,
            prompt_mfa=lambda: input("กรอกโค้ด MFA/2FA จากมือถือ: ").strip(),
        )
        garmin.login(str(token_dir))
        full_name = garmin.get_full_name()
    except Exception as e:  # noqa: BLE001
        print(f"❌ เข้าสู่ระบบไม่สำเร็จ: {e}")
        print()
        print("สาเหตุที่พบบ่อย:")
        print("  - อีเมลหรือรหัสผ่านไม่ถูกต้อง")
        print("  - กรอกโค้ด MFA ช้าเกินไป")
        print("  - พยายาม login บ่อยเกินไป (รอ ~15 นาทีแล้วลองใหม่)")
        _pause_exit(1)

    # 4) ตรวจว่าไฟล์ token ถูกเซฟจริง
    token_file = token_dir / "garmin_tokens.json"
    if not token_file.exists():
        print("❌ ไม่พบไฟล์ token ที่ควรจะถูกสร้าง — โปรดลองใหม่อีกครั้ง")
        _pause_exit(1)

    # 5) แพ็กเป็น .zip (โครงสร้างข้างในคือ <ชื่อ>/garmin_tokens.json)
    zip_path = SCRIPT_DIR / f"garmin_token_{name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(token_file, arcname=f"{name}/garmin_tokens.json")

    # 6) แจ้งผล + ขั้นตอนสุดท้าย
    print(f"✅ สำเร็จ! สวัสดี {full_name} 🎉")
    print()
    print("─" * 52)
    print("📨 ขั้นตอนสุดท้าย — ส่งไฟล์นี้กลับให้หัวหน้าทีม:")
    print()
    print(f"      {zip_path.name}")
    print(f"      (อยู่ที่: {zip_path})")
    print()
    print("   ⚠️  ส่งทางแชทส่วนตัวเท่านั้น ห้ามโพสต์ในกลุ่ม/ที่สาธารณะ")
    print("       ไฟล์นี้ไม่มีรหัสผ่าน แต่ใช้เข้าถึงข้อมูล Garmin ของคุณได้")
    print("       อยากยกเลิกภายหลัง: เปลี่ยนรหัส Garmin หรือ sign out ทุกอุปกรณ์")
    print("─" * 52)
    _pause_exit(0)


if __name__ == "__main__":
    main()
