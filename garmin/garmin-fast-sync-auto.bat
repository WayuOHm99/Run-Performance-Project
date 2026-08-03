@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem NOTE: keep this .bat pure ASCII. The fast path fetches only today's activity
rem summaries; the twice-daily full sync fills wellness, detail, weather and splits.
rem Own log file per lane - a shared log made concurrent lanes drop whole rounds.
set "LOG=C:\Backup\garmin-sync-fast.log"
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\prep_log.ps1" -LogPath "%LOG%" -Marker "data\sync_fast_run_start.txt"
echo ---- FAST %date% %time% ---->> "%LOG%"
".venv\Scripts\python.exe" scripts\fetch_all.py --days 0 --activities-only --max-workers 3 --lock-timeout 0 >> "%LOG%" 2>&1
set "SYNC_EXIT=%ERRORLEVEL%"
rem Exit 75 means another sync owns the cross-task lock; skipping is expected.
if "%SYNC_EXIT%"=="75" exit /b 0
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\notify_sync.ps1" -SyncExit %SYNC_EXIT% -Lane fast -StartMarker "sync_fast_run_start.txt" >> "%LOG%" 2>&1
