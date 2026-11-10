"""ต่อ websocket เข้า Streamlit ที่รันอยู่ แล้วบังคับให้มันรันสคริปต์หนึ่งรอบจริง ๆ

`streamlit run` เฉย ๆ ไม่รันสคริปต์เลยจนกว่าจะมี client ต่อเข้ามา — พิสูจน์แล้ว
27 ส.ค. 69 ด้วยการใส่ `import` ที่ไม่มีอยู่จริงลง dashboard.py แล้ว log ยังสะอาด
ไฟล์นี้จึงส่ง BackMsg(rerun_script) เข้าไปเพื่อให้ ScriptRunner ทำงานจริง
แล้วอ่าน ForwardMsg กลับมาดูว่ามี element ชนิด exception โผล่ไหม

พิมพ์บรรทัด `EXCEPTION <type>: <message>` ต่อหนึ่งข้อผิดพลาด และคืน exit 1 เมื่อพบ
"""

import asyncio
import sys

import websockets
from streamlit.proto.BackMsg_pb2 import BackMsg
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg


async def _drain_run(
    ws,
    timeout: float,
    label: str,
    errors: list[str],
    pages: list[tuple[str, str]],
    seen_hashes: set[str],
) -> str | None:
    active_hash: str | None = None
    try:
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            forward = ForwardMsg()
            forward.ParseFromString(raw)
            kind = forward.WhichOneof("type")
            if kind == "new_session":
                if forward.new_session.page_script_hash:
                    active_hash = forward.new_session.page_script_hash
                for page in forward.new_session.app_pages:
                    if page.page_script_hash and page.page_script_hash not in seen_hashes:
                        seen_hashes.add(page.page_script_hash)
                        pages.append((page.page_script_hash, page.page_name or page.url_pathname))
            elif kind == "navigation":
                if forward.navigation.page_script_hash:
                    active_hash = forward.navigation.page_script_hash
                for page in forward.navigation.app_pages:
                    if page.page_script_hash and page.page_script_hash not in seen_hashes:
                        seen_hashes.add(page.page_script_hash)
                        pages.append((page.page_script_hash, page.page_name or page.url_pathname))
            elif kind == "delta" and forward.delta.WhichOneof("type") == "new_element":
                element = forward.delta.new_element
                if element.WhichOneof("type") == "exception":
                    errors.append(
                        f"EXCEPTION [{label}] {element.exception.type}: {element.exception.message}"
                    )
            elif kind == "script_finished":
                if forward.script_finished == ForwardMsg.FINISHED_EARLY_FOR_RERUN:
                    continue
                if forward.script_finished == ForwardMsg.FINISHED_WITH_COMPILE_ERROR:
                    errors.append(f"EXCEPTION [{label}] CompileError: สคริปต์คอมไพล์ไม่ผ่าน")
                break
    except TimeoutError:
        errors.append(f"EXCEPTION timeout [{label}]: สคริปต์ไม่จบภายใน {timeout:.0f} วินาที")
    return active_hash


async def drive(port: str, timeout: float = 20.0) -> list[str]:
    url = f"ws://127.0.0.1:{port}/_stcore/stream"
    async with websockets.connect(url, subprotocols=["streamlit"], max_size=None) as ws:
        errors: list[str] = []
        pages: list[tuple[str, str]] = []
        seen_hashes: set[str] = set()

        msg = BackMsg()
        msg.rerun_script.query_string = ""
        await ws.send(msg.SerializeToString())
        initial_hash = await _drain_run(ws, timeout, "default", errors, pages, seen_hashes)

        for page_hash, page_label in list(pages):
            if page_hash == initial_hash:
                continue
            step = BackMsg()
            step.rerun_script.query_string = ""
            step.rerun_script.page_script_hash = page_hash
            await ws.send(step.SerializeToString())
            await _drain_run(ws, timeout, page_label or page_hash[:8], errors, pages, seen_hashes)

        return errors


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        errors = asyncio.run(drive(sys.argv[1]))
    except Exception as exc:  # ต่อไม่ติด = ถือว่าเป็นความผิดพลาดเช่นกัน
        print(f"EXCEPTION {type(exc).__name__}: {exc}")
        return 1
    for line in errors:
        print(line)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
