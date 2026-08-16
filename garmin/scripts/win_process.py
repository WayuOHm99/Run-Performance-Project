"""เรียกโปรเซสลูกแบบ "ไม่มีหน้าต่างให้ใครปิด" (ใช้ร่วมกันทุกสคริปต์อัตโนมัติ)

ทำไมต้องมีไฟล์นี้ (เจอจริง 16 ส.ค. 69 — สาย offsite backup ล้ม)
    งาน Python ล้วน (`Run-Performance-OffsiteBackup`, `-RestoreDrill`,
    `-SystemHealth`) รันด้วย ``pythonw.exe`` ซึ่งตั้งใจให้ "ไม่มีหน้าต่าง" —
    แต่ pythonw ไม่มี console ของตัวเอง พอไปเรียกโปรแกรม console (gh.exe /
    restic.exe / powershell.exe / schtasks.exe) **Windows จะสร้าง console
    ใหม่ให้ลูกเสมอ** = จอดำโผล่ขึ้นมาจริง ๆ และปิดได้ด้วยมือ
    พอมีคนปิด (หรือ session จบ) ลูกได้ CTRL_CLOSE_EVENT แล้วตายด้วย
    ``0xC000013A`` เงียบ ๆ กลางทาง — ตรงกับบทเรียนเดิมของโปรเจกต์:
    **หน้าต่างที่ปิดได้ คือหน้าต่างที่จะโดนปิด**

    หลักฐาน (วัดบนเครื่องนี้): pythonw → subprocess ธรรมดา ลูกได้
    ``GetConsoleWindow() = 132394`` (มี console จริง) แต่พอใส่
    ``CREATE_NO_WINDOW`` ได้ ``0`` (ไม่มี console ให้ปิด)

กติกา
    ทุก subprocess ในสคริปต์อัตโนมัติต้องเรียกผ่าน ``win_process.run``
    ห้ามเรียก ``subprocess.run`` ตรง ๆ — มี regression test คุมไว้ที่
    ``tests/test_ops_security.py::WindowlessSubprocessTests``
"""

from __future__ import annotations

import os
import re
import subprocess


# ไม่ให้ Windows สร้าง console ใหม่ให้โปรเซสลูกเลย (stdout/stderr ยังส่งผ่าน
# pipe/redirect ได้ตามปกติ — ตัดเฉพาะ "หน้าต่าง" ไม่ได้ตัดการอ่านผลลัพธ์)
CREATE_NO_WINDOW = 0x08000000

# STATUS_CONTROL_C_EXIT — Windows คืนค่านี้เมื่อโปรเซสถูกสั่งจบจากข้างนอก
# (ปิดหน้าต่าง console / Ctrl+C / ExecutionTimeLimit หมด / โดนสั่ง kill)
TERMINATED_BY_CONSOLE = 0xC000013A

_SUBCOMMAND = re.compile(r"[a-z][a-z0-9-]*")
# แยกชื่อไฟล์เองด้วย regex ไม่ใช้ pathlib.Path เพราะ path ที่ตัดคือ path ของ Windows
# เสมอ แต่เทส/CI รันบน Linux ด้วย — ที่นั่น Path() ไม่ถือว่า '\' เป็นตัวคั่น เลยคืน
# ทั้งก้อน 'c:\program files\github cli\gh' มาเป็นชื่อคำสั่ง (CI จับได้จริง 16 ส.ค. 69)
_EXECUTABLE_NAME = re.compile(r"[^\\/]+\Z")


def run(command, **kwargs):
    """subprocess.run ที่ไม่มีทางเปิดหน้าต่างค้างให้คนปิดบน Windows."""
    if os.name == "nt":
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | CREATE_NO_WINDOW
    return subprocess.run(command, **kwargs)


def command_label(command, *, max_words: int = 3) -> str:
    """ชื่อคำสั่งแบบสั้นไว้ใส่ในข้อความ error เช่น ``gh release upload``

    เก็บเฉพาะชื่อไฟล์ + subcommand ที่เป็นคำล้วน ตัด path/tag/URL/ธงทิ้ง
    เพื่อให้รายงานบอกได้ว่า "พังตอนทำอะไร" โดยไม่หลุดชื่อ repo หรือ path จริง
    """
    executable = _EXECUTABLE_NAME.search(str(command[0]))
    name = executable.group(0) if executable else str(command[0])
    if name.lower().endswith(".exe"):
        name = name[:-len(".exe")]
    parts = [name.lower()]
    for raw in command[1:]:
        if len(parts) >= max_words:
            break
        text = str(raw)
        if not _SUBCOMMAND.fullmatch(text):
            break
        parts.append(text)
    return " ".join(parts)


def was_terminated(returncode) -> bool:
    """True เมื่อโปรเซสถูกสั่งจบจากข้างนอก ไม่ใช่จบเองด้วย exit code ปกติ."""
    try:
        code = int(returncode)
    except (TypeError, ValueError):
        return False
    return (code & 0xFFFFFFFF) == TERMINATED_BY_CONSOLE


def exit_reason(returncode) -> str:
    """ข้อความสาเหตุที่อ่านแล้วไม่หลงทาง — แยก "โดนฆ่า" ออกจาก "จบเองแบบล้มเหลว"

    ``exit_3221225786`` อ่านไม่ออกว่าคืออะไร และเคยทำให้ไล่ผิดจุดมาแล้ว
    (บทเรียน 5 ส.ค. 69: 0xC000013A มีผู้ต้องสงสัย 3 ราย — คนปิดหน้าต่าง /
    ExecutionTimeLimit หมด / StopIfGoingOnBatteries)
    """
    if was_terminated(returncode):
        return "killed_0xC000013A(window_closed_or_timeout_or_battery)"
    return f"exit_{returncode}"
