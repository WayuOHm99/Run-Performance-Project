@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Monthly: deep resync wellness/extras over the last 45 days (skip activities -> no
rem duplicate API). Catches values Garmin recomputes late (sleep/VO2max/training_status
rem beyond the daily 3-day window). Then run schema-drift check. Schedule monthly.
rem Keep this .bat pure ASCII: Thai text breaks cmd.exe parsing.
echo ==== DEEPSYNC %date% %time% ====>> "C:\Backup\garmin-sync-log.txt"
powershell -NoProfile -Command "(Get-Date).ToString('o') | Set-Content -NoNewline -Encoding ASCII 'data\sync_run_start.txt'"
".venv\Scripts\python.exe" scripts\fetch_all.py --days 45 --skip-activities >> "C:\Backup\garmin-sync-log.txt" 2>&1
".venv\Scripts\python.exe" scripts\check_drift.py >> "C:\Backup\garmin-sync-log.txt" 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\notify_sync.ps1" -SyncExit %ERRORLEVEL% >> "C:\Backup\garmin-sync-log.txt" 2>&1
