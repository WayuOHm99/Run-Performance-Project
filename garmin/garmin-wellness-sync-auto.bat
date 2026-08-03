@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem NOTE: keep this .bat pure ASCII. Fast wellness pulls only today's intraday values
rem (body battery / resting HR / stress / steps / HRV / sleep / training readiness)
rem and updates them column-by-column, so nothing the full sync stored gets wiped.
rem The twice-daily full sync still owns respiration, training status, VO2max trend,
rem endurance / hill scores and the extras (LT, race predictions, PR, body comp).
rem Own log file per lane - a shared log made concurrent lanes drop whole rounds.
set "LOG=C:\Backup\garmin-sync-wellness.log"
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\prep_log.ps1" -LogPath "%LOG%" -Marker "data\sync_wellness_run_start.txt"
echo ---- WELLNESS %date% %time% ---->> "%LOG%"
".venv\Scripts\python.exe" scripts\fetch_all.py --days 0 --wellness-fast --max-workers 3 --lock-timeout 0 >> "%LOG%" 2>&1
set "SYNC_EXIT=%ERRORLEVEL%"
rem Exit 75 means another sync owns the cross-task lock; skipping is expected.
if "%SYNC_EXIT%"=="75" exit /b 0
rem -CheckStale: this lane runs every 30 min, so it doubles as the watchdog that warns
rem when any other lane (full / fast) has silently stopped producing rounds.
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\notify_sync.ps1" -SyncExit %SYNC_EXIT% -Lane wellness -StartMarker "sync_wellness_run_start.txt" -CheckStale >> "%LOG%" 2>&1
