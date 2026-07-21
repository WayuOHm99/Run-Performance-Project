@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ---- %date% %time% ---->> "C:\Backup\garmin-sync-log.txt"
".venv\Scripts\python.exe" scripts\fetch_all.py --days 3 >> "C:\Backup\garmin-sync-log.txt" 2>&1
