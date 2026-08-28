"""ชั้นที่ 5 — พิสูจน์ในเบราว์เซอร์จริงว่า "หน้าย้ายจริงไหม" ไม่ใช่แค่ "สคริปต์รันจบ"

CLAUDE.md เคยเขียนไว้เองว่าข้อนี้ **ไม่มีชั้นไหนพิสูจน์ได้** — ชั้นนี้ปิดช่องนั้น
ขับ Chrome ผ่าน CDP ด้วย ``websockets`` ที่มีอยู่แล้วใน .venv ไม่ต้องลง playwright

**มันจับของจริงมาแล้ว (29 ส.ค. 69):** ปุ่มบนการ์ดทีมเรียก ``st.switch_page()`` ใน
คอลแบ็กของปุ่ม ซึ่งเขียน session_state สำเร็จแต่ **หน้าไม่ย้าย และไม่มี error เลย**
เทส 549 ตัวเขียว ชั้นที่ 4 สะอาด AppTest ก็ผ่าน — มีแต่ชั้นนี้ที่เห็น

วิธีใช้ (ต้องมี streamlit รันอยู่ก่อน):

    cd garmin && .venv/Scripts/python.exe -m streamlit run scripts/dashboard.py         --server.headless=true --server.port=8996 --server.fileWatcherType=none &
    PYTHONIOENCODING=utf-8 garmin/.venv/Scripts/python.exe         .claude/hooks/browser_nav_check.py 8996 9333

กับดักที่เสียเวลาไปแล้ว ห้ามเจอซ้ำ:
- ต้องตั้ง ``PYTHONIOENCODING=utf-8`` ไม่งั้น print ภาษาไทยพังกลางทาง
- ``h1`` ตัวแรกของหน้าคือ *ชื่อแอป* ซึ่งเหมือนกันทุกหน้า — ใช้ ``location.pathname``
  เป็นสัญญาณว่าย้ายหน้าจริง และอ่าน h2/h3 ใน ``[data-testid=stMain]`` เป็นหัวข้อหน้า
- ปุ่มตัวแรกในหน้าคือปุ่มรีเฟรชใน sidebar ต้องจำกัดขอบเขตด้วย ``[data-testid=stMain]``
- อย่าใช้ sleep ตายตัว ให้ poll จนค่าที่รอเปลี่ยน (``settle()``)
"""

import asyncio
import json
import subprocess
import sys
import tempfile
import time
import urllib.request

import websockets

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
APP_PORT = sys.argv[1]
CDP_PORT = sys.argv[2]


class Tab:
    def __init__(self, ws):
        self.ws = ws
        self.n = 0

    async def send(self, method, **params):
        self.n += 1
        await self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            message = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=30))
            if message.get("id") == self.n:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message.get("result", {})

    async def js(self, expression):
        result = await self.send("Runtime.evaluate", expression=expression,
                                 awaitPromise=True, returnByValue=True)
        return result.get("result", {}).get("value")


async def settle(tab, expression, want, timeout=40.0):
    """รอจน Streamlit วาดเสร็จ — ไม่ใช้ sleep ตายตัวเพราะเวลาโหลดไม่คงที่"""
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = await tab.js(expression)
        if want(last):
            return last
        await asyncio.sleep(0.25)
    raise AssertionError(f"รอไม่ทัน: {expression} ค่าล่าสุด {last!r}")


NAV_ITEMS = ("""(() => {
  const bar = document.querySelector('[data-testid="stNavSectionHeader"]')
    || document.querySelector('header');
  const links = [...document.querySelectorAll('a[data-testid="stBaseLinkButton-headerNoPadding"], '
    + 'nav a, [data-testid="stTopNavLink"], [data-testid="stNavLink"]')];
  return links.map(a => a.innerText.trim()).filter(Boolean);
})()""")

SUBHEADS = ("""[...document.querySelectorAll('[data-testid=stMain] h2, [data-testid=stMain] h3')]
  .map(h => h.innerText.trim()).filter(Boolean)""")

HEADING = ("(document.querySelector('[data-testid=stMain] h1, "
           "[data-testid=stMain] h2, [data-testid=stMain] h3') || {})"
           ".innerText || ''")


async def main():
    profile = tempfile.mkdtemp(prefix="cdp-nav-")
    chrome = subprocess.Popen(
        [CHROME, "--headless=new", f"--remote-debugging-port={CDP_PORT}",
         f"--user-data-dir={profile}", "--no-first-run", "--window-size=1440,900",
         "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(80):
            try:
                pages = json.loads(urllib.request.urlopen(
                    f"http://127.0.0.1:{CDP_PORT}/json/list", timeout=2).read())
                target = next(p for p in pages if p["type"] == "page")
                break
            except Exception:
                await asyncio.sleep(0.25)
        else:
            raise RuntimeError("Chrome ไม่ยอมเปิด CDP")

        async with websockets.connect(target["webSocketDebuggerUrl"],
                                      max_size=None) as ws:
            tab = Tab(ws)
            await tab.send("Runtime.enable")
            await tab.send("Page.enable")
            await tab.send("Log.enable")
            await tab.send("Page.navigate", url=f"http://127.0.0.1:{APP_PORT}")

            await settle(tab, HEADING, lambda v: bool(v and v.strip()))
            names = await settle(tab, NAV_ITEMS, lambda v: v and len(v) >= 6)
            print("แถบ navigation:", " | ".join(n.replace(chr(10), " ") for n in names))

            print("หน้าเริ่มต้น: path =", await tab.js("location.pathname"),
                  "| หัวข้อรอง =", (await tab.js(SUBHEADS) or [""])[0][:44])

            # กดทีละหน้าแล้วเก็บ (path, หัวข้อรอง) — หน้าเริ่มต้นมี path เป็น "/"
            # จึงเช็คว่า "ได้ครบ 6 หน้าที่ต่างกัน" แทนที่จะบังคับว่าทุกคลิกต้องเปลี่ยน
            visited = []
            for index in range(len(names)):
                clicked = await tab.js(f"""(() => {{
                  const links = [...document.querySelectorAll('a[data-testid="stTopNavLink"], '
                    + '[data-testid="stNavLink"], nav a')].filter(a => a.innerText.trim());
                  const target = links[{index}];
                  if (!target) return null;
                  target.click();
                  return target.innerText.trim();
                }})()""")
                if not clicked:
                    continue
                previous = visited[-1][1] if visited else None
                subhead = await settle(
                    tab, SUBHEADS,
                    lambda v: bool(v) and (previous is None or v[0] != previous),
                    timeout=45)
                path = await tab.js("location.pathname")
                visited.append((path, subhead[0]))
                label = clicked.replace(chr(10), " ")
                print(f"  คลิก {label:26s} -> {path:26s} {subhead[0][:38]}")

            paths = {path for path, _ in visited}
            print(f"หน้าที่ไปถึงได้: {len(paths)} จาก {len(names)} รายการบนแถบ")

            # ปุ่มบนการ์ดทีม: คลิกเดียวต้องเปลี่ยนทั้ง "คนที่เลือก" และ "หน้า"
            # เดิมเขียนป้ายแท็บลง session_state ตอนนี้เรียก st.switch_page — ชั้นนี้เท่านั้น
            # ที่พิสูจน์ได้ว่ามันย้ายหน้าจริง ไม่ใช่แค่เขียนค่าลงไปแล้วเงียบ
            await tab.js("""(() => {
              const links = [...document.querySelectorAll('a[data-testid="stTopNavLink"], '
                + '[data-testid="stNavLink"], nav a')].filter(a => a.innerText.trim());
              const team = links.find(a => a.getAttribute('href')?.includes('team'));
              if (team) team.click();
            })()""")
            await settle(tab, SUBHEADS, lambda v: bool(v) and "ทีม" in v[0], timeout=45)
            # รอให้การ์ดวาดปุ่มเสร็จก่อน ไม่งั้นบางรอบจะไปถึงตอนหน้ายังว่าง
            await settle(
                tab,
                "document.querySelectorAll('[data-testid=stMain] "
                "[data-testid=\"stButton\"] button').length",
                lambda v: bool(v) and v >= 1, timeout=45)

            picked = await tab.js("""(() => {
              const buttons = [...document.querySelectorAll(
                '[data-testid=stMain] [data-testid="stButton"] button')];
              const target = buttons.find(b => b.innerText.trim());
              if (!target) return null;
              const label = target.innerText.trim();
              target.click();
              return label;
            })()""")
            if picked:
                path = await settle(tab, "location.pathname", lambda v: v == "/", timeout=45)
                chosen = await tab.js(
                    "(document.querySelector('[data-testid=stSelectbox]') || {})"
                    ".innerText || ''") or ""
                # รอให้หน้าใหม่วาดหัวข้อของตัวเองก่อน ไม่งั้นอ่านได้ค่าว่างของจังหวะกลางทาง
                subhead = (await settle(tab, SUBHEADS,
                                        lambda v: bool(v) and "วันนี้ของ" in v[0],
                                        timeout=45))[0]
                print(f"ปุ่มบนการ์ด {picked!r} -> path {path} · หัวข้อ {subhead[:40]} · sidebar {chosen.strip().splitlines()[-1][:20] if chosen.strip() else "?"}")
            else:
                print("ปุ่มบนการ์ด: หาไม่เจอ")

            errors = await tab.js("""(() => {
              const boxes = [...document.querySelectorAll('[data-testid="stException"], '
                + '[data-testid="stAlertContainer"]')];
              return boxes.map(b => b.innerText.trim().slice(0, 120));
            })()""")
            exceptions = [e for e in (errors or []) if "Traceback" in e or "Error" in e]
            print("กล่อง exception บนหน้า:", exceptions if exceptions else "ไม่มี")

            overflow = await tab.js(
                "document.documentElement.scrollWidth - document.documentElement.clientWidth")
            print("ล้นแนวนอน:", f"{overflow}px" if overflow else "ไม่ล้น")
    finally:
        chrome.terminate()


asyncio.run(main())
