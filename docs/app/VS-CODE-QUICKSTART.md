# คู่มือ VS Code ฉบับเริ่มต้น

## เปิดโปรเจกต์

เปิดโฟลเดอร์นี้เป็น workspace:

```text
D:\Run-Performance-Project
```

พื้นที่แอปใหม่อยู่ใต้ `platform/` ส่วน `athletes/`, `team_data/`, `garmin/`,
`scripts/`, root `supabase/` และ `CLAUDE.md` เป็นระบบเดิม ห้ามแก้หรือลบระหว่าง
งานแอป

## Extension

กด `Ctrl+Shift+X` เพื่อเปิด Extensions แล้วค้นหา `@recommended` เพื่อตรวจรายการ
แนะนำของ workspace

ตัวที่จำเป็น:

- ESLint — แสดงปัญหามาตรฐานโค้ด
- Prettier — จัดรูปแบบไฟล์
- Expo Tools — ช่วยอ่านและ debug Expo configuration
- ChatGPT/Codex — วางแผนและควบคุมงานหลัก
- Claude Code — เขียนฟีเจอร์ที่มี task packet ชัดเจน
- Gemini Code Assist — ใช้สำหรับ AGY/second opinion
- Markdownlint — ตรวจเอกสาร Markdown

Live Server ไม่ใช้กับ Expo ให้ใช้ Metro ผ่านคำสั่ง `pnpm start` แทน

## เปิดแอป

Terminal ใหม่จะเริ่มที่ `platform/` โดยอัตโนมัติ:

```powershell
corepack pnpm --filter @run-performance/mobile start
```

- กด `w` เพื่อเปิดเว็บ
- กด `a` เพื่อเปิด Android emulator
- กด `Ctrl+C` เพื่อหยุด

## ตรวจงาน

```powershell
corepack pnpm format:check
corepack pnpm lint
corepack pnpm typecheck
corepack pnpm test
```

## อ่าน Git status

กด Source Control ที่แถบซ้าย:

- `M` หมายถึงไฟล์ถูกแก้
- `U` หมายถึงไฟล์ใหม่ที่ยังไม่ track
- สีเขียวใน diff หมายถึงเพิ่ม
- สีแดงใน diff หมายถึงลบ

อย่ากด Commit, Sync, Publish Branch, Push, Discard Changes หรือ Resolve Conflict
จนกว่า task handoff จะระบุให้ทำ

## ไฟล์ลับ

`platform/apps/mobile/.env.local` เป็นไฟล์ในเครื่องเท่านั้น:

- ห้ามเปิดแชร์หน้าจอโดยมีไฟล์นี้แสดงอยู่
- ห้ามลากเข้า AI chat
- ห้าม commit
- ห้ามใส่ secret หรือ service-role key

## Claude

Claude Code ของ workspace เริ่มต้นใน Plan mode แต่ app implementation ต้องเปิด
ผ่าน isolated-worktree command ที่ Codex จัดให้ ห้ามเปิด Auto mode หรือใช้ session
ธรรมดาจาก repository root

ถ้า Claude ขออ่าน `CLAUDE.md`, `athletes/`, `team_data/`, `garmin/`, environment
files หรือ token ให้กดปฏิเสธและแจ้ง Codex

## เมื่อเห็นปัญหา

อย่ากด Quick Fix หรือ Accept All โดยไม่อ่าน diff ให้ส่ง:

1. ภาพหน้าจอ
2. ข้อความ error
3. คำสั่งที่เพิ่งรัน

มาให้ Codex วินิจฉัยก่อน
