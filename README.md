<div align="center">

# 🏃 Run Performance Project

**ระบบดึงข้อมูลนาฬิกา Garmin ของนักกีฬาในทีม มาเก็บในฐานข้อมูลกลาง แล้วแสดงเป็น Coach Dashboard ภาษาไทย**

[![CI](https://github.com/WayuOHm99/Run-Performance-Project/actions/workflows/ci.yml/badge.svg)](https://github.com/WayuOHm99/Run-Performance-Project/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.14-3776AB?style=flat-square&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-Dashboard-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-WAL-003B57?style=flat-square&logo=sqlite&logoColor=white)
![Tests](https://img.shields.io/badge/tests-500%2B-16a34a?style=flat-square)

</div>

---

## 📌 โปรเจกต์นี้ทำอะไร

โค้ชที่ดูแลนักกีฬาหลายคนต้องเปิดแอป Garmin ของแต่ละคนทีละบัญชีเพื่อดูผลซ้อม การนอน และการฟื้นตัว ซึ่งเสียเวลาและเทียบกันได้ยาก

โปรเจกต์นี้รวบข้อมูลของทุกคนมาไว้ในที่เดียวแบบอัตโนมัติ

```text
Garmin Connect API  ──►  SQLite (garmin.db)  ──►  Streamlit Coach Dashboard
    ดึงข้อมูลตามเวลา          แหล่งข้อมูลจริงหนึ่งเดียว        เปิดดูในเครื่องโค้ช
```

ระบบ **แสดงข้อมูลเพื่อช่วยโค้ชตัดสินใจ ไม่ได้สั่งซ้อมหรือสั่งพักแทนคน** ค่าจาก Garmin เช่น Training Readiness หรือ VO2max จะแสดงพร้อมระบุที่มาเสมอ

## ✨ ความสามารถหลัก

### Coach Dashboard 6 หน้า

| หน้า | ใช้ดูอะไร |
| --- | --- |
| 📅 **วันนี้** | สรุปสถานะของทุกคนในวันนี้ และสัญญาณที่ควรระวัง |
| 👥 **ทีม** | สัญญาณของทั้งทีมในมุมเดียว พร้อมเตือนเมื่อข้อมูลของใครไม่อัปเดต |
| 🌙 **การฟื้นตัว** | HRV, การนอน, ความพร้อมซ้อมและเวลาฟื้นตัวจาก Garmin เทียบกับค่าปกติของแต่ละคน |
| 🏃 **การซ้อม** | แนวโน้ม pace–HR ของรันเบา, โหลดสะสม และสัดส่วนความหนัก 3 โซน |
| 📈 **ความก้าวหน้า** | Lactate threshold, เวลาแข่งที่คาดการณ์, Endurance/Hill score และสถิติส่วนตัว |
| 🔎 **รายละเอียดเซสชัน** | ภาพรวมของการซ้อมแต่ละครั้ง พร้อมตาราง Splits รายรอบ |

### ระบบเบื้องหลังที่ทำงานเองได้

- **ซิงก์อัตโนมัติ** ด้วย Windows Task Scheduler มีทั้งรอบเร็วทุก 15 นาที รอบ wellness ทุก 30 นาที และรอบเต็มวันละ 2 ครั้ง โดยเหลื่อมเวลากันไม่ให้ชนกัน
- **ตรวจความถูกต้องของข้อมูล** มีรอบตรวจกิจกรรมที่ถูกลบรายสัปดาห์ และรอบ deep resync ทุก 4 สัปดาห์
- **สำรองข้อมูลสองชั้น** มี local snapshot ที่ตรวจแล้ว และ Restic backup ที่ **เข้ารหัสก่อนออกจากเครื่อง**
- **ซ้อมกู้คืนข้อมูลจริง** ทุก 4 สัปดาห์ระบบจะดาวน์โหลด backup มากู้คืนแล้วตรวจ schema และความสดของข้อมูล
- **เฝ้าสุขภาพระบบ** ส่ง heartbeat ที่มีแค่สถานะ (ไม่มีข้อมูลนักกีฬา) และ GitHub Actions เปิด Issue แจ้งเตือนเมื่อระบบเงียบหาย

## 🔒 ความเป็นส่วนตัว

ข้อมูลสุขภาพของนักกีฬาเป็นข้อมูลอ่อนไหว ระบบจึงออกแบบให้

- `garmin.db` และ token ของบัญชี Garmin **อยู่นอก git ทั้งหมด** และจำกัดสิทธิ์ไฟล์ด้วย ACL
- รหัสผ่าน Garmin **ไม่ถูกเก็บที่ใดเลย** ใช้แค่ครั้งเดียวตอนขอ token
- Dashboard เปิดเฉพาะ `127.0.0.1` คือดูได้จากเครื่องโค้ชเท่านั้น
- Backup ที่ออกนอกเครื่องถูกเข้ารหัสก่อนเสมอ

## 🧰 เทคโนโลยี

| ส่วน | เลือกใช้ |
| --- | --- |
| ภาษา | Python 3.14, จัดการ dependency ด้วย [uv](https://docs.astral.sh/uv/) |
| ดึงข้อมูล | [`garminconnect`](https://github.com/cyberjunky/python-garminconnect) |
| ฐานข้อมูล | SQLite (โหมด WAL) |
| Dashboard | Streamlit (multipage), Plotly, pandas |
| งานอัตโนมัติ | Windows Task Scheduler, PowerShell |
| Backup | Restic, GitHub Releases (private) |
| CI | GitHub Actions: unittest, py_compile และตรวจว่าเทสไม่แตะข้อมูลจริง |

## 🚀 เริ่มใช้งาน

> ต้องใช้ Windows, Python 3.14 และ [uv](https://docs.astral.sh/uv/)

```powershell
# 1) ติดตั้ง dependency
cd garmin
uv sync

# 2) สร้างฐานข้อมูล
uv run python scripts/02_init_schema.py

# 3) ขอ token ของนักกีฬา (ถามชื่อ อีเมล และรหัสผ่านแบบซ่อน รหัสผ่านไม่ถูกบันทึก)
uv run python scripts/01_generate_token.py

# 4) ดึงข้อมูลย้อนหลังของทุกคน
uv run python scripts/fetch_all.py --days 30

# 5) เปิด Dashboard
cd ..
.\run_dashboard.bat
```

ตั้งงานอัตโนมัติทั้งหมดด้วย `scripts/setup_scheduled_tasks.ps1`

## 🧪 การทดสอบ

```powershell
cd garmin
uv run python -m unittest discover -s tests
```

มีเทสมากกว่า 500 กรณี ครอบคลุมทุกหน้าของ Dashboard, นโยบายแจ้งเตือน, การ backup และการกู้คืน, heartbeat และความปลอดภัยของไฟล์ ทุกบั๊กที่เคยเจอจริงจะมีเทสล็อกไว้ไม่ให้เกิดซ้ำ

## 🗂️ โครงสร้างโปรเจกต์

```text
Run-Performance-Project/
├─ garmin/
│  ├─ scripts/          โค้ดหลัก: ดึงข้อมูล, Dashboard, backup, ตรวจสุขภาพระบบ
│  │  └─ app_pages/     หน้าต่าง ๆ ของ Dashboard
│  ├─ tests/            ชุดเทสอัตโนมัติ
│  ├─ tasks/            ตัวเรียกงานของ Task Scheduler (.bat / .vbs)
│  └─ share/            ชุดขอ token ที่ส่งให้นักกีฬารันเอง
├─ scripts/             ตั้ง Scheduled Task, backup offsite, ตั้งสิทธิ์ไฟล์
├─ docs/                คู่มือโปรเจกต์และบันทึกบทเรียน
├─ .github/workflows/   CI, ตรวจ heartbeat, กู้คืน backup
└─ run_dashboard.bat    ปุ่มเปิด Dashboard
```

## 📄 สถานะโปรเจกต์

ใช้งานจริงภายในทีมวิ่งขนาดเล็ก พัฒนาต่อเนื่อง ข้อมูลจาก Garmin เป็นค่าประมาณของผู้ผลิต ไม่ใช่ผลตรวจทางการแพทย์
