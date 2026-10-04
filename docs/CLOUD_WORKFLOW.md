# จากคลาวด์สู่การใช้งานจริง

คลาวด์นี้ใช้พัฒนาและทดสอบโปรเจกต์ด้วยข้อมูลจำลอง ระบบงานอัตโนมัติของโปรเจกต์ยังใช้ Windows Task Scheduler คุณไม่ต้องมี Windows เพื่อให้ GitHub Actions รันเทส Windows ให้ แต่การผ่าน CI ยังไม่ยืนยันว่าเข้าสู่ระบบ Garmin หรือซิงก์ข้อมูลจริงได้

## ส่งงานและตรวจ CI

1. ส่ง branch และเปิด Pull Request เทียบกับ `main` เพื่อให้ CI เริ่มทำงาน
2. รอให้ job ทั้งสามผ่าน: unittest บน Linux, unittest บน Windows และ browser/dependency checks
3. เทส Windows รันทั้งชุด รวม token ACL, DPAPI, Scheduled Task และการแจ้งเตือน เทสใช้ข้อมูลชั่วคราวและตรวจว่าไม่เขียนข้อมูลเข้าพาธ production
4. browser checks สร้าง DB จำลอง ตรวจทั้ง 6 หน้า การ์ดทีมและ dropdown ที่มีนักกีฬาชื่อซ้ำ รวมถึงการกดบนจอมือถือ ผลและภาพจำลองเก็บใน artifact `dashboard-smoke` 7 วัน
5. ถ้า CI ล้ม ให้อ่านผลของ job ที่ล้มก่อนรวมโค้ดเข้า `main`

ใน Codex cloud การอ่าน repository ด้วย Git และการใช้ GitHub API เป็นคนละการเชื่อมต่อ หาก Git ใช้งานได้แต่ `gh` ตอบ `Forbidden` ให้ตรวจว่า Environment settings อนุญาต `api.github.com` ด้วย การบันทึกร่างตั้งค่าจากแชทยังไม่ทำให้ runtime เปลี่ยน ต้องบันทึกการตั้งค่าและ Publish environment ตาม UI ก่อนลองส่ง PR อีกครั้ง อย่าวาง token หรือรหัสผ่านในแชท

## ลองซิงก์จริงเมื่อมีเครื่องใช้งานและ token

ขั้นตอนต่อไปนี้สำหรับเครื่อง Windows ที่จะใช้งานระบบจริง ยังไม่ได้ทดสอบบัญชี Garmin จริงจากคลาวด์นี้

1. หลังรวม PR แล้ว ให้ดึง `main` ล่าสุดบนเครื่องใช้งาน ตั้ง Python 3.14 และ uv ตาม README
2. เปิด PowerShell ที่โฟลเดอร์โปรเจกต์ แล้วรัน:

   ```powershell
   cd garmin
   uv sync --frozen
   uv run --frozen python -m unittest discover -s tests -v
   ```

3. หากมีฐานข้อมูลเดิม ให้สำรองด้วยขั้นตอน backup ที่ใช้อยู่ก่อนอัปเดต schema แล้วรัน:

   ```powershell
   uv run --frozen python scripts/02_init_schema.py
   ```

4. หากยังไม่มี token ให้รัน `uv run --frozen python scripts/01_generate_token.py` บนเครื่องนั้น แล้วกรอกบัญชี Garmin ของผู้ที่อนุญาตให้ใช้ข้อมูลผ่าน terminal ส่วนตัว รหัสผ่านไม่ถูกแสดงบนจอและไม่ควรส่งมาที่แชท
5. เลือก slug ของนักกีฬาที่ได้ token มา เปลี่ยน `runner` ในคำสั่งนี้เป็น slug นั้น แล้วลองเพียงคนเดียว:

   ```powershell
   uv run --frozen python scripts/fetch_all.py --athlete runner --days 3
   ```

6. คำสั่งต้องจบด้วย exit code 0 และสรุปว่า 1 คนสำเร็จ จากนั้นเปิด `run_dashboard.bat` ที่โฟลเดอร์หลัก ตรวจนักกีฬา วันที่ และข้อมูลที่ Garmin ส่งมาบนหน้าทีม/ร่างกาย/สถานะระบบ
7. เมื่อการซิงก์ด้วยมือสำเร็จแล้ว จึงตั้งงานอัตโนมัติตาม [วิธีใช้ระบบ](วิธีใช้ระบบ.md) การผ่านเทส Scheduled Task ใน CI เป็นการตรวจแผนและพฤติกรรมของโค้ด ไม่ใช่หลักฐานว่ามี task ติดตั้งบนเครื่องของคุณแล้ว

dependency ที่อัปเดตจาก lockfile มีผลกับ environment ของโปรเจกต์ หากมีสคริปต์ขอ token ที่คัดลอกไปเครื่องอื่นและใช้ environment เก่า ต้องอัปเดต dependency บนเครื่องนั้นด้วย
