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
rem Exit 75 means another sync owns the cross-task lock; skipping is expected. Drop the
rem start marker when we skip: the watchdog reads a marker with no matching status as
rem "started and never finished", and a skipped round is not a dead one.
if "%SYNC_EXIT%"=="75" goto skipped
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\notify_sync.ps1" -SyncExit %SYNC_EXIT% -Lane reconcile -StartMarker "sync_reconcile_run_start.txt" >> "%LOG%" 2>&1
exit /b 0

:skipped
del /q "data\sync_reconcile_run_start.txt" >nul 2>&1
exit /b 0
