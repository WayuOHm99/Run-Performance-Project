// ============================================================
// LINE webhook → Supabase (โปรเจกต์ Run-Performance)
//
// หน้าที่: รับรูป/ข้อความจากกลุ่มไลน์ทีม เก็บลง Storage + ตาราง line_*
//          เพื่อให้สคริปต์บนเครื่องโค้ชมาดึงต่อ
//
// ความปลอดภัย: ตรวจลายเซ็น HMAC-SHA256 จาก LINE ทุก request
//               (จึงตั้ง verify_jwt = false ได้ เพราะมี auth ของตัวเอง)
// ============================================================

import { createClient } from "jsr:@supabase/supabase-js@2";

const CHANNEL_SECRET = Deno.env.get("LINE_CHANNEL_SECRET") ?? "";
const ACCESS_TOKEN = Deno.env.get("LINE_CHANNEL_ACCESS_TOKEN") ?? "";
const BUCKET = "line-media";

const db = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  { auth: { persistSession: false } },
);

// ---------- ตรวจลายเซ็น ----------

function toBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let s = "";
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
  return btoa(s);
}

/** เทียบแบบ constant-time กันการเดาลายเซ็นทีละตัวอักษร */
function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function hmacBase64(secret: string, body: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return toBase64(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body)));
}

/** เผื่อกรณีก๊อปค่ามาแล้วมีช่องว่าง/ขึ้นบรรทัดติดมา ให้ลองแบบตัดช่องว่างด้วย */
async function validSignature(rawBody: string, received: string): Promise<boolean> {
  if (!received || !CHANNEL_SECRET) return false;
  if (safeEqual(await hmacBase64(CHANNEL_SECRET, rawBody), received)) return true;
  const trimmed = CHANNEL_SECRET.trim();
  if (trimmed === CHANNEL_SECRET) return false;
  return safeEqual(await hmacBase64(trimmed, rawBody), received);
}

// ---------- คุยกับ LINE ----------

async function fetchDisplayName(
  sourceType: string,
  sourceId: string | null,
  userId: string,
): Promise<string | null> {
  let url: string;
  if (sourceType === "group" && sourceId) {
    url = `https://api.line.me/v2/bot/group/${sourceId}/member/${userId}`;
  } else if (sourceType === "room" && sourceId) {
    url = `https://api.line.me/v2/bot/room/${sourceId}/member/${userId}`;
  } else {
    url = `https://api.line.me/v2/bot/profile/${userId}`;
  }
  try {
    const r = await fetch(url, { headers: { Authorization: `Bearer ${ACCESS_TOKEN}` } });
    if (!r.ok) return null;
    const j = await r.json();
    return j.displayName ?? null;
  } catch {
    return null;
  }
}

/** เนื้อไฟล์บน LINE มีอายุจำกัด ต้องรีบดึงตอนได้ event */
async function downloadAndStore(messageId: string, sentAt: Date) {
  const r = await fetch(`https://api-data.line.me/v2/bot/message/${messageId}/content`, {
    headers: { Authorization: `Bearer ${ACCESS_TOKEN}` },
  });
  if (!r.ok) throw new Error(`ดึงไฟล์จาก LINE ไม่สำเร็จ: HTTP ${r.status}`);

  const contentType = r.headers.get("content-type") ?? "image/jpeg";
  const bytes = new Uint8Array(await r.arrayBuffer());
  const ext = contentType.includes("png") ? "png" : "jpg";
  const path = `${sentAt.toISOString().slice(0, 10)}/${messageId}.${ext}`;

  const { error } = await db.storage
    .from(BUCKET)
    .upload(path, bytes, { contentType, upsert: true });
  if (error) throw error;

  return { path, contentType, size: bytes.byteLength };
}

// ---------- จัดการ event ----------

async function ensureAthlete(userId: string | null, sourceType: string, sourceId: string | null) {
  if (!userId) return;
  const { data } = await db
    .from("line_athletes")
    .select("line_user_id, display_name")
    .eq("line_user_id", userId)
    .maybeSingle();
  if (data?.display_name) return; // รู้จักแล้ว ไม่ต้องยิงถาม LINE ซ้ำ

  const displayName = await fetchDisplayName(sourceType, sourceId, userId);
  await db
    .from("line_athletes")
    .upsert({ line_user_id: userId, display_name: displayName }, { onConflict: "line_user_id" });
}

// deno-lint-ignore no-explicit-any
async function handleEvent(ev: any) {
  await db.from("line_raw_events").insert({ event_type: ev?.type ?? "unknown", payload: ev });

  if (ev?.type !== "message") return;

  const src = ev.source ?? {};
  const sourceType: string = src.type ?? "user";
  const userId: string | null = src.userId ?? null;
  const sourceId: string | null = src.groupId ?? src.roomId ?? src.userId ?? null;
  const sentAt = new Date(typeof ev.timestamp === "number" ? ev.timestamp : Date.now());

  await ensureAthlete(userId, sourceType, sourceId);

  const msg = ev.message ?? {};
  const base = {
    line_message_id: msg.id,
    line_user_id: userId,
    source_id: sourceId,
    sent_at: sentAt.toISOString(),
  };
  const opts = { onConflict: "line_message_id" };

  if (msg.type === "image") {
    try {
      const { path, contentType, size } = await downloadAndStore(msg.id, sentAt);
      await db.from("line_messages").upsert(
        { ...base, kind: "image", storage_path: path, content_type: contentType, byte_size: size },
        opts,
      );
    } catch (e) {
      // บันทึกไว้ว่าพลาด จะได้ตามเก็บทีหลังได้ ไม่เงียบหาย
      await db.from("line_messages").upsert({ ...base, kind: "image", error: String(e) }, opts);
    }
  } else if (msg.type === "text") {
    await db.from("line_messages").upsert({ ...base, kind: "text", text_body: msg.text ?? "" }, opts);
  } else {
    await db.from("line_messages").upsert({ ...base, kind: "other" }, opts);
  }
}

// ---------- entrypoint ----------

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return new Response("ok", { status: 200 });

  const rawBody = await req.text();
  if (!(await validSignature(rawBody, req.headers.get("x-line-signature") ?? ""))) {
    return new Response("invalid signature", { status: 401 });
  }

  // deno-lint-ignore no-explicit-any
  let body: any;
  try {
    body = JSON.parse(rawBody);
  } catch {
    return new Response("bad json", { status: 400 });
  }

  const events = Array.isArray(body?.events) ? body.events : [];

  // LINE ต้องการ 200 เร็วๆ — ตอบก่อน แล้วค่อยดึงรูปเบื้องหลัง
  const work = (async () => {
    for (const ev of events) {
      try {
        await handleEvent(ev);
      } catch (e) {
        console.error("จัดการ event ไม่สำเร็จ:", e);
      }
    }
  })();

  // @ts-ignore EdgeRuntime มีเฉพาะบน Supabase
  if (typeof EdgeRuntime !== "undefined") EdgeRuntime.waitUntil(work);
  else await work;

  return new Response("ok", { status: 200 });
});
