"""ข้อมูลต้องสดใหม่ไม่ว่าโค้ชจะค้างอยู่แท็บไหน

ที่มา (26 ส.ค. 69): ตอนใส่ `if tab_x.open:` เพื่อให้กดแท็บแล้วไม่ต้องสร้างกราฟใหม่
ทั้ง 14 ใบ (`c9f4b07`) บรรทัดสุดท้ายของไฟล์ถูกเยื้องตามเข้าไปด้วยโดยไม่ตั้งใจ
`auto_refresh_dashboard()` จึงไปนั่งอยู่ใต้ `if tab_splits.open:` ผลคือ
**ระบบรีเฟรชอัตโนมัติทำงานเฉพาะตอนเปิดแท็บ "รายละเอียดเซสชัน" เท่านั้น**
อีกห้าแท็บค้างข้อมูลเดิมไปเรื่อย ๆ ทั้งที่ sidebar เขียนว่ารีเฟรชอัตโนมัติทุกนาที

มันเป็น `@st.fragment(run_every=...)` ด้วย จึงไม่ได้แค่ "ไม่ทำงาน" แต่ **ไม่ถูก
ลงทะเบียนเลย** ถ้าไม่ผ่านการเรียกนั้น — ไม่มี error ไม่มีอะไรเตือน หน้าจอดูปกติทุกอย่าง

ทำไมไม่เทสด้วย `AppTest`: CI ตั้ง `GARMIN_DATA_DIR` เป็นโฟลเดอร์ว่าง สคริปต์จึง
`st.stop()` ตั้งแต่ยังไม่ถึงบล็อกแท็บ เทสชุดนี้จึงอ่านโครงสร้างจริงด้วย `ast` แทน
โดยถามว่า "การเรียกนี้ถูกเงื่อนไขอะไรครอบอยู่บ้าง" ซึ่งคือกลไกของบั๊กตรง ๆ
ไม่ใช่การนับช่องอินเดนต์แบบที่ `CLAUDE.md` ห้ามไว้ — จัดโครงใหม่ยังไงก็ไม่แดง
ตราบใดที่การเรียกยังอยู่นอกเงื่อนไข
"""

import ast
import unittest
from pathlib import Path

DASHBOARD_PATH = Path(__file__).resolve().parent.parent / "scripts" / "dashboard.py"
DASHBOARD_SRC = DASHBOARD_PATH.read_text(encoding="utf-8")
TREE = ast.parse(DASHBOARD_SRC)


def call_guards(function_name):
    """คืนรายการเงื่อนไขที่ครอบการเรียก ``function_name`` ในเส้นทางที่สคริปต์รันจริง

    หนึ่งสมาชิกต่อหนึ่งจุดที่ถูกเรียก แต่ละสมาชิกเป็นลิสต์ของเงื่อนไขจากนอกเข้าใน
    ลิสต์ว่าง = ถูกเรียกทุกครั้งที่สคริปต์รัน ซึ่งคือสิ่งที่ auto-refresh ต้องเป็น

    ไม่เดินเข้าไปใน ``def`` เพราะสนใจเฉพาะสิ่งที่เกิดขึ้นตอน Streamlit รันสคริปต์
    """
    hits = []

    def scan(body, guards):
        for node in body:
            if isinstance(node, ast.If):
                condition = ast.unparse(node.test)
                scan(node.body, guards + [condition])
                scan(node.orelse, guards + [f"not ({condition})"])
                continue
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue  # นิยาม ไม่ใช่การรัน
            if isinstance(node, (ast.With, ast.For, ast.While, ast.Try)):
                for field in ("body", "orelse", "finalbody"):
                    scan(getattr(node, field, None) or [], guards)
                for handler in getattr(node, "handlers", []):
                    scan(handler.body, guards)
                continue
            for inner in ast.walk(node):
                if (isinstance(inner, ast.Call)
                        and isinstance(inner.func, ast.Name)
                        and inner.func.id == function_name):
                    hits.append(list(guards))

    scan(TREE.body, [])
    return hits


def module_constants(*names):
    """ค่าคงที่ระดับโมดูล — ดึงด้วย ast เพราะ import ทั้งไฟล์คือการรันแอป"""
    wanted, found = set(names), {}
    for node in TREE.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in wanted:
                    found[target.id] = ast.literal_eval(node.value)
    missing = wanted - set(found)
    assert not missing, f"ไม่พบค่าคงที่ {missing} ในสคริปต์แล้ว — เทสนี้ต้องปรับตาม"
    return found


def calls_made_inside(function_name):
    """ชื่อทุกอย่างที่ฟังก์ชันนี้ *เรียก* จริง — อ่านจาก AST ไม่ใช่ค้นสตริง

    ค้นสตริงในซอร์สจะไปโดน docstring ที่อธิบายว่า "ไม่เรียกอะไร" แล้วแดงผิด ๆ
    (เจอมาแล้วตอนเขียนเทสนี้เอง)
    """
    for node in TREE.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return {
                ast.unparse(inner.func)
                for inner in ast.walk(node)
                if isinstance(inner, ast.Call)
            }
    raise AssertionError(f"ไม่พบฟังก์ชัน {function_name} ในสคริปต์แล้ว")


class AutoRefreshReachesEveryTabTests(unittest.TestCase):
    def test_auto_refresh_runs_whichever_tab_is_open(self):
        guards = call_guards("auto_refresh_dashboard")
        self.assertEqual(
            len(guards), 1,
            "คาดว่ามีจุดเรียก auto_refresh_dashboard() จุดเดียวในเส้นทางรันของสคริปต์",
        )
        self.assertEqual(
            guards[0], [],
            "auto_refresh_dashboard() ถูกเงื่อนไข "
            f"{guards[0]} ครอบอยู่ — แท็บที่ไม่เข้าเงื่อนไขจะไม่รีเฟรชเลย "
            "และเพราะมันเป็น @st.fragment มันจะไม่ถูกลงทะเบียนด้วยซ้ำ",
        )


class CacheStaysInStepWithTheRefreshTests(unittest.TestCase):
    def test_cached_data_expires_within_one_refresh_cycle(self):
        # ถ้า ttl ยาวกว่ารอบรีเฟรช การรีเฟรชจะหยิบค่าเดิมจาก cache มาแสดงซ้ำ
        # = หน้าจอ "รีเฟรช" แล้วแต่ตัวเลขไม่ขยับ ซึ่งแย่กว่าไม่รีเฟรชเพราะดูเหมือนสด
        values = module_constants("CACHE_TTL_SEC", "AUTO_REFRESH_SEC")
        self.assertLessEqual(
            values["CACHE_TTL_SEC"], values["AUTO_REFRESH_SEC"],
            f"cache อยู่ได้ {values['CACHE_TTL_SEC']} วิ แต่รีเฟรชทุก "
            f"{values['AUTO_REFRESH_SEC']} วิ — รอบรีเฟรชจะได้ค่าเดิมกลับมา",
        )

    def test_the_automatic_refresh_does_not_flush_the_whole_app_cache(self):
        # `st.cache_data.clear()` ล้าง cache ของ loader ทั้ง 21 ตัวและทุก session
        # พอ auto-refresh กลับมาทำงานทุกแท็บ มันจะกลายเป็น cold rerun ทุกนาที
        # ปุ่มรีเฟรชที่ผู้ใช้กดเองยังใช้ได้ — ตรงนั้นตั้งใจให้ทุบทั้งกระดาน
        self.assertNotIn(
            "st.cache_data.clear", calls_made_inside("auto_refresh_dashboard"),
            "รอบรีเฟรชอัตโนมัติทุบ cache ทั้งแอป ปล่อยให้ ttl หมดอายุเองแทน",
        )


if __name__ == "__main__":
    unittest.main()
