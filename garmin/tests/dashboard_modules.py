"""import โมดูลของ dashboard ให้เทสใช้ตรง ๆ และรวบซอร์สทั้งแอปไว้ให้ยามที่ค้นข้อความ

``import dashboard`` ตรง ๆ ไม่ได้เพราะมันคือการรันแอป Streamlit ทั้งหน้า ของที่เทสต้องใช้
จึงอยู่ใน ``dashboard_domain.py`` (จัดรูปค่า ไม่มี Streamlit) และ ``dashboard_data.py``
(loader ที่อ่าน SQLite)
"""

import sys
from pathlib import Path

GARMIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = GARMIN_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import dashboard_data  # noqa: E402
import dashboard_domain  # noqa: E402

HELPERS = {
    name: value
    for module in (dashboard_domain, dashboard_data)
    for name, value in vars(module).items()
    if not name.startswith("__")
}


def _dashboard_sources():
    """ทุกไฟล์ที่ประกอบกันเป็น Dashboard — หน้าเปลือก โมดูล และหน้าแต่ละหน้า

    อ่านจาก glob ไม่ใช่รายชื่อตายตัว — ยามที่ถามว่า "กฎนี้ยังอยู่ไหม" ต้องไม่แดงเพียงเพราะ
    โค้ดย้ายไฟล์ และต้องไม่พังเพราะไฟล์ที่ลบไปแล้ว (CLAUDE.md: เทสผูกกับพฤติกรรม)
    """
    return sorted(SCRIPTS_DIR.glob("dashboard*.py")) + sorted(
        (SCRIPTS_DIR / "app_pages").glob("*.py"))


ALL_SRC = chr(10).join(path.read_text(encoding="utf-8") for path in _dashboard_sources())
