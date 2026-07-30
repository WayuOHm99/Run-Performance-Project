@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ---- FAST %date% %time% ---->> "C:\Backup\garmin-sync-log.txt"
rem NOTE: keep this .bat pure ASCII. The fast path fetches only today's activity
rem summaries; the twice-daily full sync fills wellness, detail, weather and splits.
powershell -NoProfile -Command "(Get-Date).ToString('o') | Set-Content -NoNewline -Encoding ASCII 'data\sync_fast_run_start.txt'"
".venv\Scripts\python.exe" scripts\fetch_all.py --days 0 --activities-only --max-workers 3 --lock-timeout 0 >> "C:\Backup\garmin-sync-log.txt" 2>&1
set "SYNC_EXIT=%ERRORLEVEL%"
rem Exit 75 means a full/fast sync owns the cross-task lock; skipping is expected.
if "%SYNC_EXIT%"=="75" exit /b 0
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\notify_sync.ps1" -SyncExit %SYNC_EXIT% -StartMarker "sync_fast_run_start.txt" >> "C:\Backup\garmin-sync-log.txt" 2>&1
