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


async def drive(port: str, timeout: float = 15.0) -> list[str]:
    url = f"ws://127.0.0.1:{port}/_stcore/stream"
    async with websockets.connect(url, subprotocols=["streamlit"], max_size=None) as ws:
        msg = BackMsg()
        msg.rerun_script.query_string = ""
        await ws.send(msg.SerializeToString())

        errors: list[str] = []
        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                forward = ForwardMsg()
                forward.ParseFromString(raw)
                kind = forward.WhichOneof("type")
                if kind == "delta" and forward.delta.WhichOneof("type") == "new_element":
                    element = forward.delta.new_element
                    if element.WhichOneof("type") == "exception":
                        errors.append(
                            f"EXCEPTION {element.exception.type}: {element.exception.message}"
                        )
                elif kind == "script_finished":
                    break
        except asyncio.TimeoutError:
            errors.append("EXCEPTION timeout: สคริปต์ไม่จบภายใน %.0f วินาที" % timeout)
        return errors


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
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
