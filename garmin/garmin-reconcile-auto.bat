@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Weekly: detect activities deleted on Garmin's side over the last 90 days and mark
rem deleted_at (fetches activity-id list only, no detail -> light API). Schedule weekly.
rem Keep this .bat pure ASCII: Thai text breaks cmd.exe parsing.
rem Own log file per lane - a shared log made concurrent lanes drop whole rounds.
set "LOG=C:\Backup\garmin-sync-reconcile.log"
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\prep_log.ps1" -LogPath "%LOG%" -Marker "data\sync_reconcile_run_start.txt"
echo ==== RECONCILE %date% %time% ====>> "%LOG%"
".venv\Scripts\python.exe" scripts\fetch_all.py --days 90 --reconcile >> "%LOG%" 2>&1
set "SYNC_EXIT=%ERRORLEVEL%"
if "%SYNC_EXIT%"=="75" exit /b 0
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\notify_sync.ps1" -SyncExit %SYNC_EXIT% -Lane reconcile -StartMarker "sync_reconcile_run_start.txt" >> "%LOG%" 2>&1
