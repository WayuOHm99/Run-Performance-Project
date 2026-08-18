# Claude Code instructions

## Context

- อ่าน `docs/PROJECT.md` ก่อนวิเคราะห์ระบบ แก้โค้ด หรือใช้ข้อมูลนักกีฬา
- อ่าน `docs/TRAINING.md` เมื่อสร้างตารางหรือข้อความสั่งซ้อม
- ใช้ `garmin/data/garmin.db` เป็น source of truth ของตัวเลข และใส่ `deleted_at IS NULL` เมื่อ query กิจกรรม
- รักษาขอบเขต Garmin → SQLite → Dashboard ตาม `docs/PROJECT.md`

## Workflow

1. ตรวจ requirement, `git status --short` และโค้ดที่เกี่ยวข้อง
2. แก้เฉพาะขอบเขตที่ขอ พร้อมรักษาการเปลี่ยนแปลงเดิมของผู้ใช้
3. รันเทสที่เกี่ยวข้อง เมื่อแก้ระบบ Garmin ให้รันจาก `garmin/`:
   `.venv\Scripts\python.exe -m unittest discover -s tests`
4. ตรวจ diff และผลทดสอบของตัวเองก่อนสรุป
5. งานที่ทำผ่าน branch แยกแล้ว merge เข้า main แล้ว — ถ้า CI เขียวและไม่มีปัญหาค้าง
   ให้ลบ branch นั้นทิ้งทันที (`git branch -d` local + `git push origin --delete` remote)
   ไม่ต้องรอถาม ให้ repo สะอาดเหมือนใหม่เสมอ ยกเว้นผู้ใช้บอกให้เก็บไว้ก่อน

งานเสร็จเมื่อ behavior ตรงคำขอ เทสที่เกี่ยวข้องผ่าน และสรุปไฟล์ที่แก้กับข้อจำกัดที่ยังเหลือแล้ว

### เลือกเส้นทางให้ตรงขนาดงาน

```
รู้แล้วว่าจะแก้อะไร แก้ไม่กี่จุด   →  /tdd  →  commit
ยังไม่ชัดว่าจะทำอะไร ต้องตัดสินใจ  →  /grill-with-docs  →  /tdd
ของพัง หาสาเหตุไม่เจอ            →  /diagnosing-bugs
ก่อน merge เข้า main             →  /code-review
```

**ห้ามเอางานเล็กเข้า `/grill-with-docs`** — 18 ส.ค. 69 งานแก้การแสดงผลสองจุด
(ชื่อรายการ PR กับป้ายฐาน ACWR) ถูกลากเข้าการซัก 4 รอบ จบด้วย ADR และอภิธานศัพท์
ที่ผู้ใช้ไม่ได้ขอและต้องลบทิ้งทั้งหมด ส่วนงานพี่น้องกันที่เข้า `/tdd` ตรง ๆ จบใน 4 รอบ
red-green เกณฑ์คือ **"ตัดสินใจอะไรไม่ได้ถ้าไม่ถาม"** ไม่ใช่ "งานสำคัญแค่ไหน"

`/triage`, `/to-spec`, `/to-tickets`, `/wayfinder` ไม่ใช้ในโปรเจกต์นี้ — คนเดียว
ไม่มี issue ไหลเข้าจากข้างนอก และงานที่นี่ไม่เคยใหญ่ข้ามเซสชัน

### หาข้อเท็จจริงก่อนตัดสินใจ ห้ามเดา

ถ้าคำถามตอบได้ด้วยการดูของจริง (query DB, ยิง Garmin API อ่านอย่างเดียว, อ่านโค้ด
ไลบรารีใน `.venv`) ให้ไปดู อย่าอนุมานจากชื่อฟิลด์หรือความรู้ทั่วไป — เช่นตอนแก้ชื่อ PR
การยิง `get_personal_record()` ดูครั้งเดียวพบว่า `prTypeLabelKey` เป็น null ทุกแถว
ซึ่งตัดแนวทางที่วางไว้ทิ้งทันที ถ้าเดาไปจะแก้ผิดที่

### DB มีชีวิตตลอดเวลา

Scheduled Task ยิง sync ระหว่างที่ทำงานอยู่ ตัวเลขที่อ่านตอนต้นเซสชันเก่าได้ก่อนจบเซสชัน
(เกิดจริง 18 ส.ค. 69: รายงานว่า "ไม่มีข้อมูลวันนี้" แล้วข้อมูลเข้ามาระหว่างทาง)
เวลารายงานตัวเลขให้ระบุเวลาที่อ่าน และเช็ค `fetched_at` / `MAX(start_time_local)`
ก่อนสรุปว่าข้อมูลขาด

## Agent skills

### Issue tracker

Issues are tracked in this repository's GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the five default canonical triage labels. See `docs/agents/triage-labels.md`.

### Domain docs

This repository uses a single-context domain documentation layout. See `docs/agents/domain.md`.
