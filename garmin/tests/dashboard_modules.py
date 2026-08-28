"""import โมดูลของ dashboard ให้เทสใช้ตรง ๆ — แทนการแกะฟังก์ชันออกมาด้วย AST

เดิมเทสแต่ละไฟล์ต้อง ``ast.parse`` แล้ว ``exec`` เฉพาะ node ที่ต้องใช้ เพราะ
``import dashboard`` จะไปรันสคริปต์ Streamlit ทั้งหน้า ตอนนี้การคำนวณกับชิ้นส่วน
หน้าตาย้ายไป ``dashboard_domain.py`` / ``dashboard_view.py`` ซึ่ง import ได้ตรง ๆ

``HELPERS`` คงหน้าตาเดิมไว้ (dict ชื่อ -> ของ) เพื่อไม่ต้องแก้ call site ทุกบรรทัด
"""

import sys
from pathlib import Path

GARMIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = GARMIN_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import dashboard_data  # noqa: E402
import dashboard_domain  # noqa: E402
import dashboard_view  # noqa: E402

class _Helpers(dict):
    """ชื่อที่หาไม่เจอในโมดูล ให้ไปแกะจาก ``dashboard.py`` ให้อัตโนมัติ

    ของที่ยังต้องแกะคือ loader ที่ติด ``@st.cache_data`` กับ CSS ที่สคริปต์หน้าเว็บใช้เอง
    จะหมดไปตอนแยกหน้าในขั้นถัดไป
    """

    def __missing__(self, name):
        value = helpers(name)[name]
        self[name] = value
        return value


HELPERS = _Helpers(
    (name, value)
    for module in (dashboard_domain, dashboard_view, dashboard_data)
    for name, value in vars(module).items()
    if not name.startswith("__")
)

# ซอร์สของ "ทั้ง dashboard" — ยามที่ค้นข้อความต้องมองครบทั้งสามไฟล์ ไม่ใช่ไฟล์เดียว
# ตั้งแต่การคำนวณกับชิ้นส่วนหน้าตาแยกออกไป
ALL_SRC = chr(10).join(
    (SCRIPTS_DIR / name).read_text(encoding="utf-8")
    for name in ("dashboard.py", "dashboard_domain.py", "dashboard_view.py",
                 "dashboard_data.py")
)


def helpers(*names, extras=None):
    """คืน dict ของชื่อที่ขอ — หยิบจากโมดูลก่อน ที่เหลือค่อยแกะจาก ``dashboard.py``

    ที่ยังต้องแกะคือ loader ที่ติด ``@st.cache_data`` ซึ่งยังอยู่ในสคริปต์หน้าเว็บ
    (จะย้ายตอนแยกหน้าในขั้นถัดไป) ส่วนการคำนวณและชิ้นส่วนหน้าตามาจาก import ตรง ๆ แล้ว
    """
    import ast

    picked = {name: HELPERS[name] for name in names if name in HELPERS}
    rest = {name for name in names if name not in picked}
    if not rest:
        return picked

    source = (SCRIPTS_DIR / "dashboard.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    nodes, found = [], set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in rest:
            nodes.append(node)
            found.add(node.name)
        elif isinstance(node, ast.Assign):
            targets = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if targets & rest:
                nodes.append(node)
                found |= targets & rest
    missing = rest - found
    if missing:
        raise AssertionError(
            "หาไม่เจอทั้งใน dashboard_domain/dashboard_view และ dashboard.py: "
            f"{sorted(missing)}"
        )
    # ตั้งต้นด้วย HELPERS เพราะ node ที่แกะออกมาอาจอ้างค่าที่ย้ายไปโมดูลแล้ว
    # (dashboard.py ตัวจริงก็ import มันเข้ามาแบบเดียวกัน)
    namespace = {**HELPERS, **(extras or {})}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "dashboard.py", "exec"), namespace)
    picked.update({name: namespace[name] for name in found})
    return picked
