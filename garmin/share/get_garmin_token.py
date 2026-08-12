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

import base64
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from getpass import getpass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
MIN_PY = (3, 12)
GARMINCONNECT_VERSION = "0.3.9"
GARMINCONNECT_REQUIREMENT = f"garminconnect=={GARMINCONNECT_VERSION}"

_WINDOWS_PRIVATE_ACL = r"""
$ErrorActionPreference = 'Stop'
$target = [System.IO.Path]::GetFullPath($env:RUNPERF_PRIVATE_PATH)
$isDirectory = $env:RUNPERF_PRIVATE_KIND -eq 'directory'
$item = Get-Item -LiteralPath $target -Force
if ([bool]$item.PSIsContainer -ne $isDirectory) {
    throw 'Private path kind does not match the filesystem object'
}
if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
    throw 'Refusing to secure a reparse point'
}

$currentSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$systemSid = [System.Security.Principal.SecurityIdentifier]::new('S-1-5-18')
$adminsSid = [System.Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')
$allowed = @($currentSid.Value, $systemSid.Value, $adminsSid.Value)
$sections = [System.Security.AccessControl.AccessControlSections]::Access
if ($isDirectory) {
    $acl = [System.IO.Directory]::GetAccessControl($target, $sections)
    $inheritance = [System.Security.AccessControl.InheritanceFlags]::ContainerInherit -bor
                   [System.Security.AccessControl.InheritanceFlags]::ObjectInherit
}
else {
    $acl = [System.IO.File]::GetAccessControl($target, $sections)
    $inheritance = [System.Security.AccessControl.InheritanceFlags]::None
}
$propagation = [System.Security.AccessControl.PropagationFlags]::None
$allow = [System.Security.AccessControl.AccessControlType]::Allow
$full = [System.Security.AccessControl.FileSystemRights]::FullControl
$acl.SetAccessRuleProtection($true, $false)
foreach ($ace in @($acl.GetAccessRules(
        $true, $true, [System.Security.Principal.SecurityIdentifier]))) {
    [void]$acl.RemoveAccessRuleSpecific($ace)
}
foreach ($sid in @($currentSid, $systemSid, $adminsSid)) {
    $rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
        $sid, $full, $inheritance, $propagation, $allow
    )
    [void]$acl.AddAccessRule($rule)
}
if ($isDirectory) {
    [System.IO.Directory]::SetAccessControl($target, $acl)
    $check = [System.IO.Directory]::GetAccessControl($target, $sections)
}
else {
    [System.IO.File]::SetAccessControl($target, $acl)
    $check = [System.IO.File]::GetAccessControl($target, $sections)
}

$rules = @($check.GetAccessRules(
    $true, $true, [System.Security.Principal.SecurityIdentifier]
))
if (-not $check.AreAccessRulesProtected -or $rules.Count -ne 3) {
    throw 'Private DACL verification failed'
}
foreach ($sid in $allowed) {
    $matches = @($rules | Where-Object {
        $_.IdentityReference.Value -eq $sid -and
        $_.AccessControlType -eq $allow -and
        -not $_.IsInherited -and
        (($_.FileSystemRights -band $full) -eq $full) -and
        $_.InheritanceFlags -eq $inheritance -and
        $_.PropagationFlags -eq $propagation
    })
    if ($matches.Count -ne 1) {
        throw 'Private DACL verification failed'
    }
}
"""


def configure_utf8_output() -> None:
    """Keep Thai/emoji status messages usable on legacy Windows consoles."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            # Some redirected or embedded streams cannot be reconfigured.
            pass


def harden_private_path(path: Path, *, directory: bool) -> None:
    """Apply and verify an owner-private ACL/mode before storing credentials."""
    path = Path(path).resolve()
    if os.name != "nt":
        path.chmod(0o700 if directory else 0o600)
        return

    encoded = base64.b64encode(_WINDOWS_PRIVATE_ACL.encode("utf-16le")).decode("ascii")
    env = {
        **os.environ,
        "RUNPERF_PRIVATE_PATH": str(path),
        "RUNPERF_PRIVATE_KIND": "directory" if directory else "file",
    }
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-EncodedCommand",
            encoded,
        ],
        env=env,
        capture_output=True,
        text=False,
        timeout=30,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode != 0:
        raise RuntimeError("Windows could not apply and verify a private token ACL")


def check_python() -> None:
    if sys.version_info < MIN_PY:
        cur = ".".join(map(str, sys.version_info[:3]))
        print(f"❌ ต้องใช้ Python {MIN_PY[0]}.{MIN_PY[1]} ขึ้นไป (ของคุณคือ {cur})")
        print("   ดาวน์โหลดเวอร์ชันใหม่ที่: https://www.python.org/downloads/")
        _pause_exit(1)


def ensure_garminconnect():
    try:
        installed_version = version("garminconnect")
    except PackageNotFoundError:
        installed_version = None

    if installed_version == GARMINCONNECT_VERSION:
        return

    action = "ติดตั้ง" if installed_version is None else f"อัปเดตจาก {installed_version}"
    print(
        f"📦 กำลัง{action} garminconnect {GARMINCONNECT_VERSION} "
        "(รอสักครู่)..."
    )
    try:
        subprocess.check_call(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                GARMINCONNECT_REQUIREMENT,
            ]
        )
    except Exception as e:  # noqa: BLE001
        print(f"❌ ติดตั้งอัตโนมัติไม่สำเร็จ: {e}")
        print("   ลองรันคำสั่งนี้เองในเทอร์มินัลก่อน แล้วรันสคริปต์ใหม่:")
        print(f"   {sys.executable} -m pip install {GARMINCONNECT_REQUIREMENT}")
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

    # สร้าง staging สุ่มชื่อบน volume เดียวกับ ZIP ปลายทาง แล้วล็อกสิทธิ์ก่อน
    # เขียน credential ใด ๆ; plaintext token จะถูกลบทิ้งใน finally เสมอ.
    try:
        token_dir = Path(tempfile.mkdtemp(prefix=".garmin-token-", dir=SCRIPT_DIR))
    except OSError as e:
        print(f"❌ สร้าง staging สำหรับ token ไม่สำเร็จ: {e}")
        _pause_exit(1)
    try:
        try:
            harden_private_path(token_dir, directory=True)
        except Exception as e:  # noqa: BLE001
            print(f"❌ สร้างพื้นที่เก็บ token แบบส่วนตัวไม่สำเร็จ: {e}")
            _pause_exit(1)

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

        # 4) ตรวจว่าไฟล์ token ถูกเซฟจริงและล็อกไฟล์ plaintext โดยตรง
        token_file = token_dir / "garmin_tokens.json"
        if not token_file.exists():
            print("❌ ไม่พบไฟล์ token ที่ควรจะถูกสร้าง — โปรดลองใหม่อีกครั้ง")
            _pause_exit(1)
        try:
            harden_private_path(token_file, directory=False)
        except Exception as e:  # noqa: BLE001
            print(f"❌ ล็อกสิทธิ์ไฟล์ token ไม่สำเร็จ: {e}")
            _pause_exit(1)

        # 5) สร้าง ZIP ใน staging ที่ล็อกแล้ว ก่อนย้ายแบบ rename ไปปลายทาง
        zip_path = SCRIPT_DIR / f"garmin_token_{name}.zip"
        staged_zip = token_dir / ".token-archive.zip"
        published = False
        try:
            with zipfile.ZipFile(staged_zip, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(token_file, arcname=f"{name}/garmin_tokens.json")
            harden_private_path(staged_zip, directory=False)
            os.replace(staged_zip, zip_path)
            published = True
            # Verify/apply again after rename; never trust the destination parent ACL.
            harden_private_path(zip_path, directory=False)
        except Exception as e:  # noqa: BLE001
            if published:
                zip_path.unlink(missing_ok=True)
            print(f"❌ สร้างไฟล์ ZIP แบบส่วนตัวไม่สำเร็จ: {e}")
            _pause_exit(1)

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
        print("       หลังส่งแล้วให้ลบ ZIP นี้จากเครื่องและถังขยะ")
        print("       อยากยกเลิกภายหลัง: เปลี่ยนรหัส Garmin หรือ sign out ทุกอุปกรณ์")
        print("─" * 52)
        _pause_exit(0)
    finally:
        # staging มี plaintext refresh token; ห้ามทิ้งไว้แม้ login/zip ล้มเหลว.
        try:
            shutil.rmtree(token_dir)
        except FileNotFoundError:
            pass
        except Exception as e:
            raise RuntimeError(
                "ลบ staging ที่มี plaintext token ไม่สำเร็จ; กรุณาปิดโปรแกรมแล้วลบทันที"
            ) from e


if __name__ == "__main__":
    configure_utf8_output()
    main()
