@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem รายเดือน: deep resync wellness/extras ย้อนหลัง 45 วัน (ข้ามกิจกรรม — ไม่ยิง API ซ้ำ)
rem ดักค่าที่ Garmin คำนวณย้อนหลังทีหลัง (sleep/VO2max/training_status/readiness ที่มาช้า
rem เกินหน้าต่าง daily 3 วัน). ต่อด้วยตรวจ schema drift. ตั้ง Task รันเดือนละครั้ง
echo ==== DEEPSYNC %date% %time% ====>> "C:\Backup\garmin-sync-log.txt"
".venv\Scripts\python.exe" scripts\fetch_all.py --days 45 --skip-activities >> "C:\Backup\garmin-sync-log.txt" 2>&1
".venv\Scripts\python.exe" scripts\check_drift.py >> "C:\Backup\garmin-sync-log.txt" 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\notify_sync.ps1" -SyncExit %ERRORLEVEL% >> "C:\Backup\garmin-sync-log.txt" 2>&1
