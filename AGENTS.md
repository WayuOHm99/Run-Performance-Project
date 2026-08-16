# Codex instructions

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

งานเสร็จเมื่อ behavior ตรงคำขอ เทสที่เกี่ยวข้องผ่าน และสรุปไฟล์ที่แก้กับข้อจำกัดที่ยังเหลือแล้ว
