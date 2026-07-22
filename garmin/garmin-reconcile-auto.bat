@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Weekly: detect activities deleted on Garmin's side over the last 90 days and mark
rem deleted_at (fetches activity-id list only, no detail -> light API). Schedule weekly.
rem Keep this .bat pure ASCII: Thai text breaks cmd.exe parsing.
echo ==== RECONCILE %date% %time% ====>> "C:\Backup\garmin-sync-log.txt"
powershell -NoProfile -Command "(Get-Date).ToString('o') | Set-Content -NoNewline -Encoding ASCII 'data\sync_run_start.txt'"
".venv\Scripts\python.exe" scripts\fetch_all.py --days 90 --reconcile >> "C:\Backup\garmin-sync-log.txt" 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\notify_sync.ps1" -SyncExit %ERRORLEVEL% >> "C:\Backup\garmin-sync-log.txt" 2>&1
