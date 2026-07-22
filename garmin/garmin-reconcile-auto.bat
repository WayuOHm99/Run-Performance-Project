@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem รายสัปดาห์: เช็คกิจกรรมที่ถูกลบฝั่ง Garmin ย้อนหลัง 90 วัน แล้ว mark deleted_at
rem (ดึงแค่รายชื่อ activityId ไม่ดึงรายละเอียด — เบา API) ตั้ง Task รันสัปดาห์ละครั้ง
echo ==== RECONCILE %date% %time% ====>> "C:\Backup\garmin-sync-log.txt"
".venv\Scripts\python.exe" scripts\fetch_all.py --days 90 --reconcile >> "C:\Backup\garmin-sync-log.txt" 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\notify_sync.ps1" -SyncExit %ERRORLEVEL% >> "C:\Backup\garmin-sync-log.txt" 2>&1
