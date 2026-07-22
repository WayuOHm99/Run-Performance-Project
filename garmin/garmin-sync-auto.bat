@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ---- %date% %time% ---->> "C:\Backup\garmin-sync-log.txt"
".venv\Scripts\python.exe" scripts\fetch_all.py --days 3 >> "C:\Backup\garmin-sync-log.txt" 2>&1
rem แจ้งเตือน (Windows toast) เมื่อ sync ล้มเหลว/token เสีย/ข้อมูลเพี้ยน — ปกติเงียบ
rem ส่ง exit code ของ fetch_all ไปด้วย เผื่อกรณีตายก่อนเขียนไฟล์สถานะ
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\notify_sync.ps1" -SyncExit %ERRORLEVEL% >> "C:\Backup\garmin-sync-log.txt" 2>&1
