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
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

import websockets


def _resolve_chrome() -> str:
    candidates = [
        os.environ.get("CHROME_PATH"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        shutil.which("chrome"),
        shutil.which("google-chrome"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    raise FileNotFoundError("ไม่พบ Google Chrome (ตั้งค่า CHROME_PATH ได้หากติดตั้งไว้ที่อื่น)")


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

SUBHEADS = ("""[...document.querySelectorAll('[data-testid=stMain] h1, [data-testid=stMain] h2, [data-testid=stMain] h3')]
  .map(h => h.innerText.trim()).filter(Boolean)""")

HEADING = ("(document.querySelector('[data-testid=stMain] h1, "
           "[data-testid=stMain] h2, [data-testid=stMain] h3') || {})"
           ".innerText || ''")


async def main(app_port: str, cdp_port: str) -> int:
    chrome_bin = _resolve_chrome()
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with tempfile.TemporaryDirectory(prefix="cdp-nav-", ignore_cleanup_errors=True) as profile:
        chrome = subprocess.Popen(
            [chrome_bin, "--headless=new", f"--remote-debugging-port={cdp_port}",
             f"--user-data-dir={profile}", "--no-first-run", "--window-size=1440,900",
             "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=creationflags)
        try:
            for _ in range(80):
                try:
                    pages = json.loads(urllib.request.urlopen(
                        f"http://127.0.0.1:{cdp_port}/json/list", timeout=2).read())
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
                await tab.send("Page.navigate", url=f"http://127.0.0.1:{app_port}")

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
                        lambda v, prev=previous: bool(v) and (prev is None or v[0] != prev),
                        timeout=45)
                    path = await tab.js("location.pathname")
                    visited.append((path, subhead[0]))
                    label = clicked.replace(chr(10), " ")
                    print(f"  คลิก {label:26s} -> {path:26s} {subhead[0][:38]}")

                paths = {path for path, _ in visited}
                print(f"หน้าที่ไปถึงได้: {len(paths)} จาก {len(names)} รายการบนแถบ")

                # ปุ่มบนการ์ดทีม: คลิกเดียวต้องเปลี่ยนทั้ง "คนที่เลือก" และ "หน้า"
                # เลือกปุ่มคนที่ 2 เมื่อมีอย่างน้อย 2 คน เพื่อพิสูจน์ว่า sidebar เปลี่ยนจากค่าเริ่มต้นจริง
                await tab.js("""(() => {
                  const links = [...document.querySelectorAll('a[data-testid="stTopNavLink"], '
                    + '[data-testid="stNavLink"], nav a')].filter(a => a.innerText.trim());
                  const team = links.find(a => a.innerText.trim().endsWith('ทีม'));
                  if (team) team.click();
                })()""")
                await settle(tab, SUBHEADS, lambda v: bool(v) and "ทีม" in v[0], timeout=45)
                await settle(
                    tab,
                    "document.querySelectorAll('[data-testid=stMain] "
                    "[class*=\"st-key-open-athlete-\"] button').length",
                    lambda v: bool(v) and v >= 1, timeout=45)

                picked = await tab.js("""(() => {
                  const buttons = [...document.querySelectorAll(
                    '[data-testid=stMain] [class*="st-key-open-athlete-"] button')]
                    .filter(b => b.innerText.trim());
                  const target = buttons.length >= 2 ? buttons[1] : buttons[0];
                  if (!target) return null;
                  const label = target.innerText.trim();
                  target.click();
                  return label;
                })()""")
                expected_name = ""
                sidebar_line = "?"
                if picked:
                    if "ดูข้อมูลของ" in picked:
                        expected_name = picked.split("ดูข้อมูลของ", 1)[-1].strip()
                    path = await settle(tab, "location.pathname", lambda v: v == "/body", timeout=45)
                    subhead = (await settle(
                        tab,
                        SUBHEADS,
                        lambda v: bool(v) and "ร่างกาย" in v[0] and (not expected_name or expected_name in v[0]),
                        timeout=45,
                    ))[0]
                    sidebar_line = await tab.js("""(() => {
                      const inp = document.querySelector('.st-key-selected_athlete input')
                        || document.querySelector('[data-testid="stSelectbox"] input');
                      if (inp && typeof inp.value === 'string' && inp.value.trim()) {
                        return inp.value.trim();
                      }
                      const sel = document.querySelector('.st-key-selected_athlete [data-baseweb="select"]')
                        || document.querySelector('[data-testid="stSelectbox"] [data-baseweb="select"]')
                        || document.querySelector('[data-testid="stSelectbox"]');
                      if (!sel) return '?';
                      const raw = (sel.innerText || sel.textContent || '').trim();
                      return raw.replace(/keyboard_arrow_down$/i, '').trim() || '?';
                    })()""") or "?"
                    sidebar_clean = sidebar_line.replace(chr(10), " ")
                    print(
                        f"ปุ่มบนการ์ด {picked!r} -> path {path} · หัวข้อ {subhead[:40]} · "
                        f"sidebar {sidebar_clean[:32]}"
                    )
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

                failures: list[str] = []
                if len(paths) < 6:
                    failures.append(f"ไปไม่ครบ 6 หน้า (ได้ {len(paths)} จาก {len(names)})")
                if not picked:
                    failures.append("หาปุ่มดูข้อมูลบนการ์ดทีมไม่เจอ")
                elif expected_name and expected_name not in sidebar_line:
                    failures.append(
                        f"sidebar ไม่เปลี่ยนเป็น {expected_name!r} (ได้ {sidebar_line!r})"
                    )
                if exceptions:
                    failures.append(f"พบ exception บนหน้า: {exceptions}")
                if (overflow or 0) > 0:
                    failures.append(f"หน้าล้นแนวนอน {overflow}px")
                if failures:
                    for item in failures:
                        print(f"FAIL: {item}", file=sys.stderr)
                    return 1
                return 0
        finally:
            chrome.terminate()
            try:
                chrome.wait(timeout=5)
            except subprocess.TimeoutExpired:
                chrome.kill()
                chrome.wait(timeout=5)


def _cli() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 3:
        print("วิธีใช้: python .claude/hooks/browser_nav_check.py <app_port> <cdp_port>", file=sys.stderr)
        return 2
    return asyncio.run(main(sys.argv[1], sys.argv[2]))


if __name__ == "__main__":
    raise SystemExit(_cli())
