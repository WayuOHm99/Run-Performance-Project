# วิจัยโฮสต์ไทยสำหรับ Run Performance Project

ตรวจข้อมูลจากหน้าเว็บทางการ ณ **17 สิงหาคม 2026** โดยพิจารณาระบบเต็มสาย `Garmin sync → SQLite/WAL → Streamlit Dashboard` รวม scheduler, health monitoring และ backup ตลอด 24 ชั่วโมง ไม่พิจารณา free tier

## ข้อสรุป

งบ **150–250 บาท/เดือนทำได้จริง** สำหรับนักกีฬา 3 คน หากใช้ Linux VPS เครื่องเดียวและคง SQLite ไว้บนดิสก์ local ของเครื่องนั้น ตัวเลือกที่สมดุลที่สุดคือ **ReadyIDC Ready Cloud Standard Fixed-Size XS: 1 vCPU, RAM 2 GB, SSD 30 GB, IPv4 1 IP, daily backup ย้อนหลัง 3 วัน ราคา 150 บาทก่อน VAT หรือ 160.50 บาท/เดือน** ([ราคาและสเปกทางการ](https://www.readyidc.com/products/cloud-server/)). ผู้ให้บริการระบุว่า cloud อยู่ในประเทศไทย มี SSH/SSH key สำหรับ Linux, monitoring ระดับ infrastructure และ NOC 24/7

ถ้ายังไม่มีโดเมน ReadyIDC แสดงราคา `.com` 540 บาท/ปี ไม่รวม VAT หรือเฉลี่ย **48.15 บาท/เดือนรวม VAT** ทำให้ VPS + domain เฉลี่ยราว **208.65 บาท/เดือน** ยังอยู่ในงบ ([ราคาโดเมน](https://www.readyidc.com/products/domain-register/)). ต้องยืนยันราคา renewal และยอดจริงที่ checkout ก่อนซื้อ

คำแนะนำนี้ยังเป็น **ตัวเลือกสำหรับทดลอง shadow 7–14 วัน** ไม่ใช่หลักประกันว่า Garmin จะไม่ล่ม เพราะตัวดึงข้อมูลใช้ไลบรารีชุมชน `python-garminconnect` ซึ่งใช้ mobile SSO flow และเรียก Garmin Connect; การย้าย cloud แก้ปัญหาไฟ/เน็ต/Task Scheduler ของเครื่องส่วนตัว แต่ไม่กำจัดความเสี่ยงจาก upstream Garmin หรือการเปลี่ยน endpoint ([โครงการต้นทาง](https://github.com/cyberjunky/python-garminconnect)).

## ขนาดขั้นต่ำที่เหมาะกับระบบนี้

- **ขั้นต่ำแนะนำ:** 1 vCPU, RAM 2 GB, SSD 20–30 GB และ public IPv4 หนึ่งหมายเลข
- **ไม่แนะนำ 512 MB–1 GB:** อาจรัน native Python ได้แบบตึงมาก แต่มีพื้นที่เผื่อไม่พอสำหรับ Streamlit + pandas/Plotly + sync + monitoring/backup พร้อมกัน ตัวอย่าง deployment ทางการของ Streamlit ตั้ง request 745 MiB และ limit 2 GiB จึงใช้ 2 GB เป็น engineering floor ไม่ใช่ข้อกำหนดตายตัวของ Streamlit ([Streamlit deployment example](https://docs.streamlit.io/deploy/tutorials/kubernetes)).
- ฐานข้อมูลปัจจุบันมีขนาดไม่ถึง 1 MB ดังนั้น SSD 20–30 GB เหลือพอมากสำหรับข้อมูล, image/dependencies และ logs; ต้องตั้ง log rotation และ disk alert ไว้ด้วย
- ไม่ต้องใช้ Kubernetes หรือ managed database สำหรับผู้ใช้คนเดียว/นักกีฬา 3 คน เพราะเพิ่มค่าใช้จ่ายและงานดูแลโดยไม่เพิ่มคุณค่าที่จำเป็น

## ตัวเลือกที่ตรวจสอบ

| ตัวเลือก | ราคา/เดือน | สิ่งที่เอกสารยืนยัน | ประเมินสำหรับโปรเจกต์ |
|---|---:|---|---|
| **ReadyIDC Ready Cloud XS (แนะนำ)** | 150 + VAT = **160.50 บาท** | 1 vCPU, RAM 2 GB, SSD 30 GB, IPv4, 1 Gbps shared, daily backup 3 วัน, Linux ผ่าน SSH/SSH key | เอกสารครบที่สุดและ backup รวมในราคา เหมาะกับ reliability-first |
| ReadyIDC VPS-LG1XS+ | 150 + VAT = **160.50 บาท** (หน้าเว็บระบุ VAT คำนวณเพิ่ม) | 2 vCPU, RAM 3 GB, SSD 30 GB, IPv4, 1 Gbps shared, unmetered, Ubuntu/Debian/AlmaLinux | สเปกดีกว่าในราคาเดียวกัน แต่หน้าแพ็กเกจระบุชัดว่า **ไม่มี backup** และเป็นแพ็กเกจ Game; ใช้ได้ต่อเมื่อฝ่ายขายยืนยัน web app/Docker/outbound Garmin ([แพ็กเกจ](https://www.readyidc.com/en/products/vps-game-plus/)) |
| CloudVPS.in.th Cloud VPS 1 | **199 บาท**; VAT ไม่ชัด | 2 cores, RAM 2 GB, disk 40 GB, 1 Gbps, 10 TB/Unlimited, เครื่องอยู่ไทย, เลือก OS, firewall และ manual backup | สเปกพอ แต่หน้าแพ็กเกจไม่ยืนยัน public IPv4, distro/root/Docker และความหมาย backup จึงเป็นตัวสำรองแบบมีเงื่อนไข ([แพ็กเกจ](https://my.cloudvps.in.th/store/cloud-vps)) |
| Sundae Cloud Vanilla Scoop | **199 บาท**; VAT ไม่ชัด | 2 cores, RAM 4 GB, SSD 40 GB, Linux/Ubuntu, ระบุว่า Ubuntu เหมาะกับ Docker, uptime 99.9%; international traffic อยู่ใต้ Fair Use | สเปกสูง แต่ไม่พบการยืนยัน public IPv4 หรือ backup/snapshot บนหน้าแพ็กเกจ จึงยังไม่เหมาะเป็นตัวเลือกคุณภาพสูงสุดก่อนฝ่ายขายตอบ ([แพ็กเกจ](https://sundaecloud.in.th/th/)) |
| Nakhonitech Starter-A | **199 บาท** + setup 100 บาท; VAT ไม่ชัด | 1 vCPU, RAM 1 GB, SSD/NVMe 20 GB, IPv4, Ubuntu/Debian/AlmaLinux, root SSH, daily backup 3 วัน | ฟังก์ชันครบแต่ RAM ต่ำกว่า floor; ไม่แนะนำสำหรับ dashboard และ sync พร้อมกัน ([แพ็กเกจ](https://www.nakhonitech.com/vps-server-cat-ntplc.html)) |
| Bangmod Cloud รุ่น 512 MB | **159 บาท** ตามตัวอย่าง billing ทางการ | RAM 512 MB, disk 20 GB, international transfer 2 TB และส่วนเกิน 0.6 บาท/GB | RAM ไม่พอ จึงตัดออก; เอกสารยังเตือนว่า quota ถูกเฉลี่ยรายชั่วโมง ไม่ใช่ก้อนรายเดือน ([วิธีคิด data transfer](https://kb.bangmod.cloud/article/how-bangmod-cloud-calculate-data-transfer-for-cloud-services)) |

ราคาและข้อเสนออาจเปลี่ยนได้ หน้า ReadyIDC ระบุสงวนสิทธิ์เปลี่ยนราคาโดยไม่แจ้งล่วงหน้า จึงต้องเก็บ screenshot/ใบเสนอราคาก่อนชำระจริง

## Linux, Docker และ SQLite

Ready Cloud ให้ Linux พร้อม root-level SSH จึงรองรับการติดตั้ง Python และโดยหลักรองรับ Docker Engine; อย่างไรก็ตามหน้าแพ็กเกจไม่ได้รับรอง Docker เป็นรายชื่อ workload จึงควรถามฝ่ายขายก่อนซื้อ Streamlit มีคู่มือ Docker ทางการสำหรับ Debian/Ubuntu และระบุ health endpoint/port 8501 ไว้ชัดเจน ([Streamlit Docker guide](https://docs.streamlit.io/deploy/tutorials/docker)).

เพื่อให้ดูแลง่ายและใช้ RAM น้อย แนะนำเริ่มด้วย **Ubuntu + Python venv + systemd services/timers + Caddy** มากกว่าแยกหลาย containers; Docker Compose เป็นตัวเลือกหากต้องการ reproducible deployment ภายหลัง ถ้าใช้ Docker ต้อง mount `garmin/data` เป็น persistent volume/bind mount เพราะข้อมูลใน writable container layer หายเมื่อ container ถูกลบ ([Docker storage](https://docs.docker.com/engine/storage/volumes/)).

SQLite/WAL เหมาะกับเครื่องเดียว แต่ฐานข้อมูลต้องอยู่บน **local filesystem ของ VPS** และทุก process ที่อ่าน/เขียนต้องอยู่ host เดียวกัน; เอกสาร SQLite ระบุว่า WAL ใช้บน network filesystem ไม่ได้และมี writer ได้ครั้งละหนึ่งราย ([SQLite WAL](https://www.sqlite.org/wal.html)). ดังนั้นอย่า mount `garmin.db` จาก object storage, SMB/NFS หรือ GitHub โดยตรง

## Public HTTPS และการเข้าถึงคนเดียว

รูปแบบที่เรียบง่ายและปลอดภัย:

1. ชี้ DNS `dashboard.<domain>` ไปยัง IPv4 ของ VPS
2. เปิด inbound เฉพาะ 22 (จำกัด source IP ถ้าทำได้), 80 และ 443; ไม่เปิด Streamlit 8501 สู่สาธารณะ
3. ให้ Caddy reverse proxy จาก HTTPS ไป `127.0.0.1:8501` Caddy ออกและต่ออายุใบรับรอง TLS พร้อม redirect HTTP→HTTPS อัตโนมัติ เมื่อ DNS ถูกต้องและพอร์ต 80/443 เข้าถึงได้ ([Caddy Automatic HTTPS](https://caddyserver.com/docs/automatic-https))
4. เพิ่ม login และ allowlist อีเมลเจ้าของเพียงคนเดียว Streamlit รองรับ OIDC ผ่าน `st.login`, `st.user`, `st.logout` แต่เอกสารเตือนว่า OIDC ให้ authentication ไม่ใช่ authorization จึงต้องตรวจอีเมลที่อนุญาตในแอปด้วย ([Streamlit authentication](https://docs.streamlit.io/develop/concepts/connections/authentication))

อย่าเผย Dashboard ด้วย IP/port 8501 โดยไม่มี TLS และ login เพราะมีข้อมูลสุขภาพนักกีฬา

## Backup และ monitoring

- Daily backup 3 วันของ Ready Cloud ช่วยกู้ทั้ง VM ระยะสั้น แต่ **ไม่ควรเป็นสำเนาเดียว** เพราะอยู่กับผู้ให้บริการเดียวกัน
- คง encrypted Restic off-site backup ของโปรเจกต์ไว้ และสร้าง SQLite snapshot อย่างถูกวิธีก่อนให้ Restic อ่าน ไม่ copy ไฟล์ `.db` แบบสด ๆ; SQLite มี Online Backup API สำหรับ snapshot ของฐานข้อมูลที่กำลังใช้งาน ([SQLite Online Backup API](https://www.sqlite.org/backup.html)).
- หลังย้าย cloud ต้อง port Scheduled Tasks/PowerShell/Windows toast เป็น `systemd timer`, service health checks และ notification ที่ใช้บน Linux; provider monitoring ตรวจ CPU/RAM/disk ไม่ได้รู้ว่า Garmin data สดหรือ Dashboard ถูกต้อง
- รักษาหลักการเดิม: retry/catch-up อัตโนมัติ, แจ้งเมื่อแก้เองไม่ได้, ตรวจสัปดาห์ละครั้ง และห้าม restore/แก้ DB อัตโนมัติโดยไม่มีอนุมัติ

## สิ่งที่ต้องถามก่อนซื้อ

ส่งคำถามสั้น ๆ ให้ ReadyIDC และเก็บคำตอบเป็นหลักฐาน:

1. Fixed-Size XS ราคา 150 บาทยังเปิดขายและยอดรวม VAT เท่ากับ 160.50 บาทต่อเดือนหรือไม่ มี setup/renewal fee หรือไม่
2. อนุญาต Python, Streamlit, Docker/Compose และ cron/systemd timers บน Ubuntu หรือไม่
3. IPv4 เป็น public static IP หรือไม่ และเปิด inbound 80/443 ได้หรือไม่
4. อนุญาต outbound HTTPS ต่อเนื่องไปต่างประเทศ รวม `connect.garmin.com`, GitHub และ ACME certificate authorities หรือไม่ มี quota/Fair Use/port block ใดบ้าง
5. Daily backup 3 วันครอบคลุมทั้ง system disk หรือไม่, restore เองได้หรือผ่าน ticket, มีค่า restore หรือไม่ และ RPO/RTO เท่าไร
6. แพ็กเกจมี snapshot ก่อน deploy/rollback หรือไม่ และคิดเพิ่มเท่าไร

หากข้อ 2–5 ตอบไม่ชัด ให้ทดลอง **ReadyIDC VPS-LG1XS+ หรือ CloudVPS.in.th** เป็น shadow แทน แต่ต้องมี off-site backup ตั้งแต่วันแรก

## เกณฑ์ผ่านช่วง shadow 7–14 วัน

- cloud เป็น writer เพียงชุดเดียวในฐานทดสอบ; ห้าม Windows และ cloud เขียน `garmin.db` ก้อนเดียวกัน
- เทียบจำนวนกิจกรรมที่ `deleted_at IS NULL`, wellness rows และ latest sync ต่อ athlete/ต่อ lane กับระบบเดิมทุกวัน
- sync, dashboard, health check และ backup/restore drill ผ่านต่อเนื่อง; ทดสอบ reboot VPS อย่างน้อยหนึ่งครั้ง
- วัด peak RAM, disk growth, CPU และอัตรา Garmin 401/429/5xx ก่อนตัดสินว่า 2 GB พอ
- cutover เมื่อข้อมูลครบ/สดเท่าระบบเดิมอย่างน้อย 7 วันติด และ rollback กลับ Windows ได้จาก runbook

## ความไม่แน่นอนที่ยังเหลือ

- ไม่มีผู้ให้บริการในงบนี้เผยรายละเอียดครบเรื่อง outbound ACL/Fair Use, Docker support, snapshot restore fee และ RPO/RTO บนหน้า public; ต้องยืนยันกับฝ่ายขาย
- คำว่า “backup” ของแต่ละเจ้าหมายถึงไม่เหมือนกัน เช่น provider VM backup, manual snapshot หรือพื้นที่ให้ผู้ใช้สำรองเอง จึงห้ามเทียบจากคำเดียว
- ราคา domain เป็นค่าใช้จ่ายเพิ่มหากยังไม่มีโดเมน; TLS จาก ACME/Caddy ไม่มีค่า certificate แต่ต้องมี DNS และ public reachability
- สเปก 2 GB เป็นจุดเริ่มต้นที่สมเหตุผล ไม่ใช่คำรับรอง performance; ผล shadow test ของ workload จริงเป็นเกณฑ์ตัดสินสุดท้าย
