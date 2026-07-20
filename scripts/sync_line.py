#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_line.py — ดึงรูป/ข้อความจากกลุ่มไลน์ลงเครื่อง

ทำอะไร
  1. ถาม Supabase ว่ามีรูป/ข้อความใหม่ที่ยังไม่ได้ดึงลงเครื่องไหม
  2. จับกลุ่มเป็น "เซสชัน" ด้วยเวลา (ห่างกันเกิน 30 นาที = คนละเซสชัน)
  3. แยกว่าเป็นการบ้านหรือคุยเล่น (ดู classify)
  4. บันทึกลง  D:\\Run-Performance\\<ชื่อนักกีฬา>\\<YYYY-MM-DD>\\
       การบ้าน  -> sN_MM.jpg
       คุยเล่น   -> _แชท\\HHMM_MM.jpg
  5. เขียน context.json เก็บข้อความ/RPE ของวันนั้นไว้ให้โค้ชกับ Claude อ่าน
  6. ทำเครื่องหมายว่าดึงแล้ว + ลบไฟล์บนคลาวด์ (กัน storage เต็ม)

หลักการกันพัง
  - ความผิดพลาดของรูปใบเดียว/คนเดียว ต้องไม่ทำให้ทั้งรอบล้ม
  - ลบของบนคลาวด์เฉพาะเมื่อไฟล์บนเครื่องเขียนสำเร็จและขนาดตรงกัน
  - ไม่เขียนทับไฟล์เดิม
  - รันซ้ำกี่ครั้งผลต้องเหมือนเดิม (idempotent) ไม่งอกซ้ำใน context.json
  - การตัดสินว่าเป็นการบ้าน/คุยเล่น ต้องดูจากข้อความ "ทั้งเซสชัน" เสมอ
    ไม่ใช่ดูเฉพาะส่วนที่ยังไม่ได้ดึง (ไม่งั้นผลจะเปลี่ยนไปมาระหว่างรอบ)
  - ใครที่ยังไม่ได้จับคู่ชื่อโฟลเดอร์ จะถูกข้ามและรายงาน ไม่เดาเอง

วิธีใช้
  python sync_line.py --dry-run    # ลองดูเฉยๆ ไม่เขียนไม่ลบอะไร  <- รันอันนี้ก่อนเสมอ
  python sync_line.py              # ทำจริง
"""

from __future__ import annotations

import argparse
import concurrent.futures
import http.client
import json
import re
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------- ตั้งค่า ----------------

TH = timezone(timedelta(hours=7))          # ไทยไม่มี DST ใช้ offset คงที่ได้เลย
ROOT = Path(r"D:\Run-Performance")
BUCKET = "line-media"
SESSION_GAP_MINUTES = 30                    # ห่างเกินนี้ = คนละเซสชัน
CONTEXT_LOOKBACK_HOURS = 24                 # ดึงข้อความเก่ามาช่วยตัดสินย้อนหลังแค่ไหน
MAX_ROWS = 5000
DEFAULT_SUPABASE_URL = "https://tnmxpwcyfaekwwwrefjd.supabase.co"
SCRIPT_DIR = Path(__file__).resolve().parent
ENV_FILE = SCRIPT_DIR / ".env"

# ---- แยกการบ้านออกจากการคุยเล่น ----
#
# สัญญาณหลัก: ส่งการบ้าน = แคปหลายแท็บรัวๆ ทีเดียว (ของจริงในโฟลเดอร์: 3-31 รูป)
#             คุยเล่น    = ส่งทีละใบ
# ไม่ต้องให้นักกีฬาจำคำสั่งอะไร แต่ถ้าอยากบังคับก็พิมพ์ #ซ้อม / #ไม่ใช่ซ้อม ได้
TRAINING_MIN_IMAGES = 3
FORCE_TRAINING_TAGS = ("#ซ้อม", "#การบ้าน", "#training")
FORCE_CHAT_TAGS = ("#ไม่ใช่ซ้อม", "#คุยเล่น", "#chat")
# คำที่มักโผล่มาพร้อมการบ้าน แม้รูปจะน้อย
TRAINING_HINTS = ("rpe", "เพซ", "pace", "กม.", "โซน", "zone",
                  "interval", "tempo", "long run", "ซ้อม")
CHAT_DIR_NAME = "_แชท"

# ---- จับ "คำสั่งโค้ช" จากข้อความในไลน์ ----
#
# ทำไมต้องมี: การประเมินผลซ้อมโดยไม่รู้ว่าโค้ชสั่งอะไรไว้ ทำให้สรุปผิดมาแล้ว 2 ครั้ง
#             (พี่เก้า 17 ก.ค. บันทึกว่า "ตามแผน" ทั้งที่ฝ่าคำสั่งพัก / แดน 18 ก.ค.)
# คำสั่งจริงของโค้ชจะยาว มีหลายบรรทัด มีศัพท์ซ้อม และมักมี @ ระบุตัวคน
ORDER_MIN_CHARS = 80
ORDER_MIN_HINTS = 2
ORDER_HINTS = (
    "rpe", "เพซ", "pace", "กม.", "ซ้อม", "วิ่ง", "ฟื้นฟู", "พัก", "ดริล",
    "สไตร์ด", "stride", "str ", "laps", "interval", "tempo", "โซน", "zone",
    "ตาราง", "วอร์ม", "คูลดาวน์", "ยืดเหยียด", "นาที", "ชั่วโมง",
)
ORDER_FILE = "คำสั่งโค้ช.md"
TEAM_DIR_NAME = "_ทีม"          # ใช้เมื่อคำสั่งไม่ได้ระบุตัวใครเป็นพิเศษ

# หน้าจอ Windows ปกติไม่ใช่ UTF-8 ถ้าไม่บังคับตรงนี้ ภาษาไทยจะกลายเป็นตัวประหลาด
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def die(msg: str) -> None:
    print(f"\n[หยุด] {msg}\n", file=sys.stderr)
    sys.exit(1)


def load_config() -> tuple[str, str]:
    """อ่าน SUPABASE_URL / SUPABASE_SERVICE_KEY จากไฟล์ .env ข้างสคริปต์"""
    if not ENV_FILE.exists():
        die(
            f"ไม่พบไฟล์ {ENV_FILE}\n"
            "       รัน  ตั้งกุญแจ.bat  เพื่อสร้างให้อัตโนมัติ"
        )
    cfg: dict[str, str] = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        cfg[k.strip()] = v.strip().strip('"').strip("'")

    key = cfg.get("SUPABASE_SERVICE_KEY", "")
    if not key:
        die("ไฟล์ .env ไม่มีบรรทัด SUPABASE_SERVICE_KEY — รัน ตั้งกุญแจ.bat")
    if len(key) < 30:
        die(
            f"SUPABASE_SERVICE_KEY สั้นผิดปกติ ({len(key)} ตัวอักษร)\n"
            "       ระวังก๊อปชื่อหัวข้อมาแทนค่าจริง — รัน ตั้งกุญแจ.bat"
        )
    return cfg.get("SUPABASE_URL", DEFAULT_SUPABASE_URL).rstrip("/"), key


# ---------------- คุยกับ Supabase ----------------

class NotFound(Exception):
    """ไฟล์หายไปจากคลาวด์แล้ว (เช่น ถูกลบไปตอนรอบก่อน)"""


class Api:
    SELECT = (
        "id,line_message_id,line_user_id,kind,text_body,storage_path,"
        "content_type,byte_size,sent_at,synced_at,error,"
        "line_athletes(display_name,folder_name,is_coach)"
    )

    def __init__(self, base_url: str, key: str) -> None:
        self.base = base_url
        self.key = key
        parts = urllib.parse.urlparse(base_url)
        self._host = parts.netloc
        self._use_https = parts.scheme != "http"
        self._conn: http.client.HTTPConnection | None = None   # เปิดค้างไว้ ใช้ซ้ำ (keep-alive)

    def _connect(self) -> http.client.HTTPConnection:
        if self._use_https:
            return http.client.HTTPSConnection(self._host, timeout=60)
        return http.client.HTTPConnection(self._host, timeout=60)

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def _req(self, method: str, path: str, body: bytes | None = None,
             extra_headers: dict[str, str] | None = None) -> bytes:
        headers = {"apikey": self.key, "Authorization": f"Bearer {self.key}"}
        if extra_headers:
            headers.update(extra_headers)
        # ยิงผ่าน connection เดิมที่เปิดค้างไว้ ถ้ามันขาด/พังค่อยต่อใหม่แล้วลองอีกครั้ง
        # (เปิด TCP+TLS ใหม่ทุก request ช้ากว่าใช้ซ้ำ ~30% จากที่วัดจริงกับ Supabase)
        last_err: Exception | None = None
        for attempt in (1, 2):
            if self._conn is None:
                self._conn = self._connect()
            try:
                self._conn.request(method, path, body=body, headers=headers)
                resp = self._conn.getresponse()
                data = resp.read()          # ต้องอ่านจนจบก่อน ถึงจะใช้ connection ซ้ำได้
            except (http.client.HTTPException, OSError) as e:
                last_err = e
                self.close()                # connection เสีย ทิ้งแล้วต่อใหม่รอบหน้า
                continue
            if 200 <= resp.status < 300:
                return data
            detail = data.decode("utf-8", "replace")[:400]
            if resp.status in (401, 403):
                die(f"Supabase ปฏิเสธ ({resp.status}) — key ผิดหรือหมดอายุ ลองรัน ตั้งกุญแจ.bat\n       {detail}")
            if resp.status in (400, 404) and "not_found" in detail:
                raise NotFound(detail) from None
            raise RuntimeError(f"HTTP {resp.status} {method} {path}: {detail}") from None
        die(f"ต่อเน็ตไม่ได้: {last_err}")
        raise RuntimeError("unreachable")   # die() ออกโปรแกรมไปแล้ว บรรทัดนี้แค่กัน type checker

    def pending(self) -> list[dict]:
        q = urllib.parse.urlencode({
            "synced_at": "is.null", "select": self.SELECT,
            "order": "sent_at.asc", "limit": str(MAX_ROWS),
        })
        return json.loads(self._req("GET", f"/rest/v1/line_messages?{q}"))

    def since(self, iso_ts: str) -> list[dict]:
        """ดึงข้อความทั้งหมดตั้งแต่เวลาหนึ่ง (รวมที่ดึงไปแล้ว) เพื่อให้จัดกลุ่ม/ตัดสินได้ครบ"""
        q = urllib.parse.urlencode({
            "sent_at": f"gte.{iso_ts}", "select": self.SELECT,
            "order": "sent_at.asc", "limit": str(MAX_ROWS),
        })
        return json.loads(self._req("GET", f"/rest/v1/line_messages?{q}"))

    def download(self, storage_path: str) -> bytes:
        return self._req("GET", f"/storage/v1/object/{BUCKET}/{urllib.parse.quote(storage_path)}")

    def download_isolated(self, storage_path: str) -> bytes:
        """ดาวน์โหลด 1 รูปผ่าน connection ใหม่ของตัวเอง — thread-safe ใช้ตอนดึงขนาน
        (http.client ใช้ connection ข้าม thread ไม่ได้ จึงห้ามแตะ self._conn ที่ใช้ร่วมกัน)"""
        path = f"/storage/v1/object/{BUCKET}/{urllib.parse.quote(storage_path)}"
        headers = {"apikey": self.key, "Authorization": f"Bearer {self.key}"}
        conn = self._connect()
        try:
            conn.request("GET", path, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
        finally:
            conn.close()
        if 200 <= resp.status < 300:
            return data
        detail = data.decode("utf-8", "replace")[:400]
        if resp.status in (400, 404) and "not_found" in detail:
            raise NotFound(detail)
        raise RuntimeError(f"HTTP {resp.status} download {storage_path}: {detail}")

    def delete_object(self, storage_path: str) -> None:
        self._req("DELETE", f"/storage/v1/object/{BUCKET}/{urllib.parse.quote(storage_path)}")

    def mark_synced(self, row_id: int, when: str, note: str | None = None) -> None:
        payload: dict[str, str] = {"synced_at": when}
        if note:
            payload["error"] = note
        self._req(
            "PATCH", f"/rest/v1/line_messages?id=eq.{row_id}",
            json.dumps(payload).encode("utf-8"),
            {"Content-Type": "application/json", "Prefer": "return=minimal"},
        )

    def mark_synced_many(self, row_ids: list[int], when: str) -> None:
        """ทำเครื่องหมาย 'ดึงแล้ว' หลายแถวในครั้งเดียว (PostgREST id=in.(...))
        เดิมยิงทีละแถว = ทีละ request วันหนึ่งเป็นหลายสิบ request; รวบเหลือ ~1"""
        payload = json.dumps({"synced_at": when}).encode("utf-8")
        hdr = {"Content-Type": "application/json", "Prefer": "return=minimal"}
        for i in range(0, len(row_ids), 500):          # กัน URL ยาวเกิน แบ่งก้อนละ 500
            ids = ",".join(str(x) for x in row_ids[i:i + 500])
            self._req("PATCH", f"/rest/v1/line_messages?id=in.({ids})", payload, hdr)

    def delete_objects(self, storage_paths: list[str]) -> None:
        """ลบไฟล์บนคลาวด์หลายไฟล์ในครั้งเดียว (Supabase storage bulk delete)"""
        hdr = {"Content-Type": "application/json"}
        for i in range(0, len(storage_paths), 500):
            body = json.dumps({"prefixes": storage_paths[i:i + 500]}).encode("utf-8")
            self._req("DELETE", f"/storage/v1/object/{BUCKET}", body, hdr)


def fetch_parallel(api: Api, rows: list[dict], workers: int = 5) -> dict[int, bytes | Exception]:
    """ดาวน์โหลดหลายรูปพร้อมกัน คืน {row_id: bytes ถ้าสำเร็จ / Exception ถ้าพัง}
    ไม่โยน error ออกมา — เก็บ error (รวม NotFound) ไว้ใน dict ให้ loop จัดการทีละใบเหมือนเดิม
    ตอนส่งการบ้านชุดใหญ่ 20-30 รูป ดึงขนานเร็วกว่าทีละใบหลายวินาที"""
    out: dict[int, bytes | Exception] = {}
    if not rows:
        return out

    def one(r: dict) -> tuple[int, bytes | Exception]:
        try:
            return r["id"], api.download_isolated(r["storage_path"])
        except Exception as e:                       # NotFound รวมอยู่ในนี้ (เก็บ object ไว้)
            return r["id"], e

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(workers, len(rows))) as ex:
        for rid, res in ex.map(one, rows):
            out[rid] = res
    return out


# ---------------- จับกลุ่มเซสชัน ----------------

def parse_ts(raw: str) -> datetime:
    """แปลงเวลาจาก Postgres (UTC) เป็นเวลาไทย"""
    s = raw.replace("Z", "+00:00")
    if "." in s:                                    # ทำเศษวินาทีให้เหลือ 6 หลักพอดี
        head, _, tail = s.partition(".")
        digits = re.match(r"\d+", tail)
        offset = tail[digits.end():] if digits else tail
        frac = (digits.group()[:6] if digits else "0").ljust(6, "0")
        s = f"{head}.{frac}{offset}"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TH)


def split_sessions(rows: list[dict]) -> list[list[dict]]:
    """แบ่งรายการ (เรียงเวลาแล้ว) เป็นเซสชันตามช่องว่างของเวลา"""
    sessions: list[list[dict]] = []
    current: list[dict] = []
    prev: datetime | None = None
    for r in rows:
        t = r["_t"]
        if prev is not None and (t - prev) > timedelta(minutes=SESSION_GAP_MINUTES):
            sessions.append(current)
            current = []
        current.append(r)
        prev = t
    if current:
        sessions.append(current)
    return sessions


def classify(images: list[dict], texts: list[dict]) -> tuple[bool, str]:
    """ตัดสินว่าชุดนี้เป็นการบ้านหรือคุยเล่น — คืน (เป็นการบ้านไหม, เหตุผล)"""
    blob = " ".join((t.get("text_body") or "") for t in texts).lower()

    for tag in FORCE_CHAT_TAGS:
        if tag in blob:
            return False, f"เจ้าตัวสั่งเองว่า {tag}"
    for tag in FORCE_TRAINING_TAGS:
        if tag in blob:
            return True, f"เจ้าตัวสั่งเองว่า {tag}"

    n = len(images)
    if n >= TRAINING_MIN_IMAGES:
        return True, f"ส่งรูปรัว {n} ใบในชุดเดียว"

    hit = next((w for w in TRAINING_HINTS if w in blob), None)
    if hit and n >= 1:
        return True, f"รูปแค่ {n} ใบ แต่ข้อความมีคำว่า '{hit}'"

    if n == 0:
        return False, "ไม่มีรูปเลย มีแต่ข้อความ"
    return False, f"รูปแค่ {n} ใบ และไม่มีคำที่บ่งบอกว่าเป็นการซ้อม"


# ---------------- คำสั่งโค้ช ----------------

def looks_like_order(text: str) -> tuple[bool, str]:
    """ข้อความนี้เป็นคำสั่งซ้อมหรือแค่คุยเล่น — คืน (ใช่ไหม, เหตุผล)"""
    t = (text or "").strip()
    if len(t) < ORDER_MIN_CHARS:
        return False, f"สั้นเกินไป ({len(t)} ตัวอักษร)"
    low = t.lower()
    hits = [w for w in ORDER_HINTS if w in low]
    if len(hits) < ORDER_MIN_HINTS:
        return False, f"มีศัพท์ซ้อมแค่ {len(hits)} คำ"
    return True, f"ยาว {len(t)} ตัวอักษร มีศัพท์ซ้อม {len(hits)} คำ ({', '.join(hits[:4])}...)"


def resolve_mentions(text: str, roster: dict[str, str]) -> list[str]:
    """หาว่าคำสั่งนี้ระบุถึงใครบ้าง — roster = {display_name: folder_name}"""
    found: list[str] = []
    for display, folder in roster.items():
        if not display:
            continue
        if f"@{display}" in text and folder not in found:
            found.append(folder)
    return found


def write_order(day_dir: Path, when: datetime, msg_id: str, text: str,
                targets: list[str]) -> bool:
    """ต่อท้ายคำสั่งลงไฟล์ — คืน True ถ้าเขียนใหม่จริง (False = มีอยู่แล้ว)"""
    path = day_dir / ORDER_FILE
    marker = f"<!-- id:{msg_id} -->"
    if path.exists() and marker in path.read_text(encoding="utf-8"):
        return False                                   # เคยเขียนแล้ว ไม่ซ้ำ

    to = " / ".join(targets) if targets else "ทั้งทีม"
    block = (
        f"\n{marker}\n"
        f"## {when:%H:%M} — ถึง {to}\n\n"
        f"{text.strip()}\n\n---\n"
    )
    day_dir.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(
            f"# คำสั่งโค้ชจากไลน์ — ส่งวันที่ {when:%Y-%m-%d}\n\n"
            f"> เก็บอัตโนมัติจากกลุ่มไลน์ ใช้เป็นบริบทตอนตรวจผลซ้อม\n"
            f">\n"
            f"> **หมายเหตุสำคัญ:** วันที่ในไฟล์นี้คือ *วันที่ส่งคำสั่ง* ไม่ใช่วันที่ให้ทำ\n"
            f"> คำสั่งที่ส่งตอนกลางคืนมักหมายถึงวันถัดไป — ตอนตรวจผลซ้อมของวันไหน\n"
            f"> ให้เปิดดูไฟล์ของวันนั้นและวันก่อนหน้าด้วยเสมอ\n",
            encoding="utf-8",
        )
    with path.open("a", encoding="utf-8") as f:
        f.write(block)
    return True


# ---------------- เขียนลงเครื่อง ----------------

def write_context(day_dir: Path, athlete: str, day: str, blocks: list[dict]) -> None:
    """เขียน context.json โดยแทนที่บล็อกเดิมที่คีย์ซ้ำ ไม่ต่อท้ายซ้ำเวลารันหลายรอบ"""
    path = day_dir / "context.json"
    doc: dict = {}
    if path.exists():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            backup = path.with_name("context.json.bak")
            path.replace(backup)
            print(f"      ! context.json เดิมอ่านไม่ออก ย้ายไปเป็น {backup.name} แล้วสร้างใหม่")
            doc = {}

    doc.setdefault("athlete", athlete)
    doc.setdefault("date", day)
    existing: list[dict] = doc.get("sessions", [])

    merged: dict[tuple[str, str], dict] = {
        (b.get("session", ""), b.get("started_at", "")): b for b in existing
    }
    for b in blocks:                              # คีย์ซ้ำ = ทับของเดิม ไม่งอกใหม่
        merged[(b["session"], b["started_at"])] = b

    doc["sessions"] = sorted(merged.values(), key=lambda b: b.get("started_at", ""))
    doc["last_synced_at"] = datetime.now(TH).isoformat(timespec="seconds")
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------- เช็คสุขภาพระบบ ----------------

def health_check(api: Api) -> None:
    """ตอบคำถาม 'ระบบยังรับข้อมูลปกติไหม' ในคำสั่งเดียว — อ่านอย่างเดียว ไม่เขียนไม่ลบ"""
    now = datetime.now(TH)
    print("\n=== เช็คสุขภาพระบบรับข้อมูล ===\n")

    q = urllib.parse.urlencode({"select": "sent_at", "order": "sent_at.desc", "limit": "1"})
    rows = json.loads(api._req("GET", f"/rest/v1/line_messages?{q}"))
    if rows:
        last = parse_ts(rows[0]["sent_at"])
        age_h = (now - last).total_seconds() / 3600
        print(f"ของล่าสุดที่เข้าระบบ : {last:%Y-%m-%d %H:%M} ({age_h:.1f} ชม.ที่แล้ว)")
        if age_h > 48:
            print("  ! เกิน 48 ชม. ไม่มีอะไรเข้าเลย — ถ้าทีมยังส่งรูปกันอยู่ webhook อาจพัง")
            print("    เช็คตามลำดับ: bot ยังอยู่ในกลุ่ม? / สวิตช์ Use webhook เปิดอยู่? / token หมดอายุ?")
    else:
        print("ยังไม่มีข้อความเข้าระบบเลยสักรายการ")

    print(f"ค้างรอดึงลงเครื่อง   : {len(api.pending())} รายการ  (ดึงด้วย python sync_line.py)")

    q = urllib.parse.urlencode({"select": "sent_at,error", "error": "not.is.null",
                                "order": "sent_at.desc", "limit": "5"})
    errs = json.loads(api._req("GET", f"/rest/v1/line_messages?{q}"))
    if errs:
        print("รายการที่เคยมีปัญหา  : (แสดงล่าสุดไม่เกิน 5)")
        for e in errs:
            print(f"    {parse_ts(e['sent_at']):%m-%d %H:%M}  {(e.get('error') or '')[:70]}")
    else:
        print("รายการที่เคยมีปัญหา  : ไม่มี")

    q = urllib.parse.urlencode({"select": "display_name,folder_name"})
    ath = json.loads(api._req("GET", f"/rest/v1/line_athletes?{q}"))
    mapped = [a for a in ath if (a.get("folder_name") or "").strip()]
    print(f"คนในระบบ             : {len(ath)} (จับคู่โฟลเดอร์แล้ว {len(mapped)})")
    for a in ath:
        if not (a.get("folder_name") or "").strip():
            print(f"    ยังไม่จับคู่: {a.get('display_name') or '(ไม่รู้ชื่อ)'} — บอก Claude ให้จับคู่ได้")
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description="ดึงรูป/ข้อความจากกลุ่มไลน์ลงเครื่อง")
    ap.add_argument("--dry-run", action="store_true",
                    help="แสดงว่าจะทำอะไร แต่ไม่เขียนไฟล์ ไม่ลบของบนคลาวด์")
    ap.add_argument("--keep-cloud", action="store_true",
                    help="ดึงลงเครื่องแล้วแต่ไม่ลบไฟล์บนคลาวด์")
    ap.add_argument("--health", action="store_true",
                    help="เช็คสุขภาพระบบ (webhook ยังรับของไหม มีอะไรค้าง/พังไหม) อ่านอย่างเดียว")
    args = ap.parse_args()

    base_url, key = load_config()
    api = Api(base_url, key)

    if args.health:
        health_check(api)
        api.close()
        return

    if args.dry_run:
        print("\n*** โหมดทดลอง — ไม่มีการเขียนหรือลบอะไรทั้งสิ้น ***")

    pending = api.pending()
    if not pending:
        print("\nไม่มีของใหม่ — ทุกอย่างถูกดึงลงเครื่องหมดแล้ว\n")
        api.close()
        return

    # ดึงข้อความรอบๆ มาด้วย เพื่อให้จัดกลุ่มและตัดสินได้จากภาพรวมทั้งเซสชัน
    earliest = min(parse_ts(r["sent_at"]) for r in pending)
    window_start = (earliest - timedelta(hours=CONTEXT_LOOKBACK_HOURS)).astimezone(timezone.utc)
    rows = api.since(window_start.isoformat())
    pending_ids = {r["id"] for r in pending}

    # ---- แยกตามคน ----
    by_athlete: dict[str, list[dict]] = {}
    unmapped: dict[str, str] = {}

    for r in rows:
        a = r.get("line_athletes") or {}
        folder = (a.get("folder_name") or "").strip()
        if not folder:
            if r["id"] in pending_ids:
                uid = r.get("line_user_id") or "(ไม่ทราบ)"
                unmapped[uid] = a.get("display_name") or "(ยังไม่รู้ชื่อ)"
            continue
        r["_t"] = parse_ts(r["sent_at"])
        by_athlete.setdefault(folder, []).append(r)

    total_images = total_texts = 0
    failures: list[str] = []

    # ---- เก็บคำสั่งโค้ชแยกไว้ก่อน ----
    # ทำก่อนวนตามคน เพราะคำสั่งของโค้ชต้องไปลงโฟลเดอร์ของ "นักกีฬาที่ถูกสั่ง"
    roster: dict[str, str] = {}
    for r in rows:
        a = r.get("line_athletes") or {}
        if a.get("display_name") and a.get("folder_name") and not a.get("is_coach"):
            roster[a["display_name"]] = a["folder_name"]

    orders_written = 0
    for r in rows:
        a = r.get("line_athletes") or {}
        if not a.get("is_coach") or r["kind"] != "text" or r["id"] not in pending_ids:
            continue
        text = r.get("text_body") or ""
        ok, why = looks_like_order(text)
        if not ok:
            continue
        when = parse_ts(r["sent_at"])
        targets = resolve_mentions(text, roster)
        dests = targets or [TEAM_DIR_NAME]
        head = text.strip().splitlines()[0][:50]
        print(f"\n📋 คำสั่งโค้ช {when:%H:%M} → {' / '.join(dests)}  ({why})")
        print(f"   \"{head}...\"")
        if args.dry_run:
            for d in dests:
                print(f"   จะเขียนลง {ROOT / d / when.strftime('%Y-%m-%d') / ORDER_FILE}")
            continue
        for d in dests:
            try:
                if write_order(ROOT / d / when.strftime("%Y-%m-%d"),
                               when, r["line_message_id"], text, targets):
                    orders_written += 1
                    print(f"   เขียนลง {d}/{when:%Y-%m-%d}/{ORDER_FILE}")
                else:
                    print(f"   {d}: มีอยู่แล้ว ข้าม")
            except Exception as e:
                failures.append(f"เขียนคำสั่งลง {d} ไม่สำเร็จ — {e}")

    for athlete, items in sorted(by_athlete.items()):
        if not any(r["id"] in pending_ids for r in items):
            continue                                    # คนนี้ไม่มีของใหม่
        items.sort(key=lambda x: x["_t"])
        print(f"\n=== {athlete} ===")

        by_day: dict[str, list[dict]] = {}
        for r in items:
            by_day.setdefault(r["_t"].strftime("%Y-%m-%d"), []).append(r)

        for day, day_rows in sorted(by_day.items()):
            if not any(r["id"] in pending_ids for r in day_rows):
                continue
            day_dir = ROOT / athlete / day
            sessions = split_sessions(day_rows)
            blocks: list[dict] = []
            done: list[tuple[int, str | None, str | None]] = []   # (id, storage_path, note)
            sidx = 0

            for sess in sessions:
                imgs = [r for r in sess if r["kind"] == "image" and r.get("storage_path")]
                txts = [r for r in sess if r["kind"] == "text"]
                if not imgs and not txts:
                    # เช่น สติกเกอร์ — ทำเครื่องหมายว่าจัดการแล้วไม่ให้ค้าง แต่ไม่ต้องมีบล็อก
                    for r in sess:
                        if r["id"] in pending_ids and not args.dry_run:
                            done.append((r["id"], None, None))
                    continue

                is_training, why = classify(imgs, txts)
                if is_training:
                    sidx += 1
                    label, target_dir, prefix, mark = (
                        f"s{sidx}", day_dir, f"s{sidx}_", "📌 การบ้าน")
                else:
                    t0 = sess[0]["_t"]
                    label, target_dir, prefix, mark = (
                        f"chat-{t0:%H%M}", day_dir / CHAT_DIR_NAME, f"{t0:%H%M}_", "💬 คุยเล่น")

                t0, t1 = sess[0]["_t"], sess[-1]["_t"]
                fresh = sum(1 for r in sess if r["id"] in pending_ids)
                print(f"  {day} {t0:%H:%M}-{t1:%H:%M}  รูป {len(imgs)} / ข้อความ {len(txts)}"
                      f"  (ใหม่ {fresh})  {mark}  ({why})")

                # ดึงรูปที่ต้องโหลดแบบขนานไว้ล่วงหน้า แล้ว loop ข้างล่างค่อยหยิบจาก cache
                # (ตรรกะตัดสิน/เขียน/นับ ไม่เปลี่ยน — แตะแค่ "แหล่งของ bytes")
                # เผื่อไฟล์มีอยู่แล้วบางใบก็ดึงเกินนิดหน่อย ยอมได้ กันดึงซ้ำหลุด logic ง่ายกว่า
                fetched: dict[int, bytes | Exception] = {}
                if not args.dry_run:
                    need = [r for r in imgs if r["id"] in pending_ids]
                    fetched = fetch_parallel(api, need)

                saved: list[str] = []       # เฉพาะไฟล์ที่มีจริงบนดิสก์ — context.json ห้ามอ้างรูปที่ไม่มี
                for n, r in enumerate(imgs, start=1):       # นับจากรูปทั้งเซสชัน ชื่อจึงคงที่ทุกรอบ
                    ext = ".png" if (r.get("content_type") or "").endswith("png") else ".jpg"
                    fname = f"{prefix}{n:02d}{ext}"
                    dest = target_dir / fname

                    if r["id"] not in pending_ids:
                        if dest.exists():                   # ดึงไปแล้วรอบก่อน
                            saved.append(fname)
                        continue
                    if args.dry_run:
                        print(f"      จะบันทึก {dest}")
                        saved.append(fname)
                        continue
                    if dest.exists():
                        # ไฟล์อยู่ครบแล้ว (รอบก่อนอาจถูกขัดจังหวะ) — ปิดงานไม่ให้ค้างวนซ้ำ
                        print(f"      มี {fname} อยู่แล้ว — ถือว่าเรียบร้อย")
                        saved.append(fname)
                        done.append((r["id"], r.get("storage_path"), None))
                        continue

                    res = fetched.get(r["id"])
                    if res is None:                          # กันเหนียว: ไม่ควรเกิด — ดึงสำรองทีละใบ
                        try:
                            res = api.download_isolated(r["storage_path"])
                        except Exception as e:
                            res = e
                    if isinstance(res, NotFound):
                        msg = f"{athlete} {day} {fname}: ไฟล์หายจากคลาวด์แล้ว"
                        print(f"      ! {msg}")
                        failures.append(msg)
                        done.append((r["id"], None, "ไฟล์หายจากคลาวด์ ดึงไม่ได้"))
                        continue
                    if isinstance(res, Exception):           # ใบเดียวพัง ต้องไม่ล้มทั้งรอบ
                        msg = f"{athlete} {day} {fname}: {res}"
                        print(f"      ! โหลดไม่สำเร็จ — {res}")
                        failures.append(msg)
                        continue
                    data = res

                    expected = r.get("byte_size")
                    if expected and len(data) != expected:
                        msg = f"{athlete} {day} {fname}: ขนาดไม่ตรง ({len(data)} != {expected})"
                        print(f"      ! {msg} — ข้ามไว้ก่อน ไม่ลบของบนคลาวด์")
                        failures.append(msg)
                        continue

                    try:
                        target_dir.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(data)
                        if dest.stat().st_size != len(data):
                            raise IOError("เขียนไม่ครบ")
                    except Exception as e:
                        msg = f"{athlete} {day} {fname}: เขียนลงเครื่องไม่สำเร็จ — {e}"
                        print(f"      ! {msg}")
                        failures.append(msg)
                        continue

                    done.append((r["id"], r["storage_path"], None))
                    saved.append(fname)
                    total_images += 1

                for r in txts:
                    if r["id"] in pending_ids:
                        total_texts += 1
                        print(f"      ข้อความ {r['_t']:%H:%M}  {r.get('text_body')!r}")
                        if not args.dry_run:
                            done.append((r["id"], None, None))

                # ปิดงานให้ทุกแถวที่เหลือในเซสชัน (เช่น สติกเกอร์ kind='other')
                # ไม่งั้นจะค้างเป็น "ของใหม่" ตลอดไปทุกรอบ
                # ยกเว้นรูปที่ยังดึงไม่สำเร็จ — ต้องค้างไว้ให้ลองใหม่รอบหน้า และห้ามส่ง
                # storage_path เข้าคิวลบ เพราะไฟล์บนคลาวด์คือสำเนาเดียวที่เหลืออยู่
                if not args.dry_run:
                    handled = {d[0] for d in done}
                    for r in sess:
                        if r["id"] in pending_ids and r["id"] not in handled:
                            if r["kind"] == "image" and r.get("storage_path"):
                                continue
                            done.append((r["id"], None, None))

                blocks.append({
                    "session": label,
                    "kind": "training" if is_training else "chat",
                    "reason": why,
                    "started_at": t0.strftime("%H:%M"),
                    "ended_at": t1.strftime("%H:%M"),
                    "images": saved,
                    "messages": [
                        {"time": r["_t"].strftime("%H:%M"), "text": r.get("text_body") or ""}
                        for r in txts
                    ],
                })

            if args.dry_run:
                continue

            if blocks:
                try:
                    day_dir.mkdir(parents=True, exist_ok=True)
                    write_context(day_dir, athlete, day, blocks)
                except Exception as e:
                    failures.append(f"{athlete} {day}: เขียน context.json ไม่สำเร็จ — {e}")

            now = datetime.now(timezone.utc).isoformat()
            # ทำเครื่องหมาย 'ดึงแล้ว' แบบรวบ: แถวไม่มี note ยิงทีเดียวหมด (id=in.(...))
            # แถวมี note (เช่น ไฟล์หายจากคลาวด์) ยิงแยกเพราะข้อความต่างกัน
            # ลบไฟล์บนคลาวด์เฉพาะแถวที่ mark สำเร็จ (กันข้อมูลหายถ้า mark พลาด)
            plain = [(rid, sp) for rid, sp, note in done if not note]
            noted = [(rid, sp, note) for rid, sp, note in done if note]
            to_delete: list[str] = []

            if plain:
                try:
                    api.mark_synced_many([rid for rid, _ in plain], now)
                    to_delete += [sp for _, sp in plain if sp]
                except Exception:
                    # ยิงรวบพลาด — ถอยไปทีละแถว ไม่ให้แถวเดียวทำพังทั้งก้อน
                    for rid, sp in plain:
                        try:
                            api.mark_synced(rid, now)
                            if sp:
                                to_delete.append(sp)
                        except Exception as e:
                            failures.append(f"id={rid}: ทำเครื่องหมายไม่สำเร็จ — {e}")

            for rid, sp, note in noted:
                try:
                    api.mark_synced(rid, now, note)
                    if sp:
                        to_delete.append(sp)
                except Exception as e:
                    failures.append(f"id={rid}: ทำเครื่องหมายไม่สำเร็จ — {e}")

            if to_delete and not args.keep_cloud:
                try:
                    api.delete_objects(to_delete)
                except Exception as e:
                    failures.append(f"ลบไฟล์บนคลาวด์ไม่สำเร็จ ({len(to_delete)} ไฟล์) — {e}")

    # ---- สรุป ----
    print("\n" + "-" * 46)
    if args.dry_run:
        print("โหมดทดลอง: ไม่ได้เขียนหรือลบอะไรจริง")
    print(f"รูปที่ดึงลงเครื่อง : {total_images}")
    print(f"ข้อความที่เก็บ    : {total_texts}")
    print(f"คำสั่งโค้ชที่เก็บ  : {orders_written}")

    if failures:
        print(f"\n! มีปัญหา {len(failures)} รายการ:")
        for f in failures[:20]:
            print(f"    {f}")
        if len(failures) > 20:
            print(f"    ... และอีก {len(failures) - 20} รายการ")

    if unmapped:
        print("\n! ยังไม่รู้ว่าคนพวกนี้คือใคร จึงข้ามไว้ (ไม่เดา):")
        for uid, name in unmapped.items():
            print(f"    {name}   [{uid}]")
        print("\n  บอก Claude ว่าใครเป็นใคร แล้วให้ตั้งค่าให้")
    print()
    api.close()


if __name__ == "__main__":
    main()
