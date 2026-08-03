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
rem Exit 75 means another sync owns the cross-task lock; skipping is expected. Drop the
rem start marker when we skip: the watchdog reads a marker with no matching status as
rem "started and never finished", and a skipped round is not a dead one.
if "%SYNC_EXIT%"=="75" goto skipped
rem -CheckStale: this lane runs every 30 min, so it doubles as the watchdog that warns
rem when any other lane (full / fast / wellness / reconcile / deep) has silently stopped
rem producing rounds, or started a round that never finished.
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\notify_sync.ps1" -SyncExit %SYNC_EXIT% -Lane wellness -StartMarker "sync_wellness_run_start.txt" -CheckStale >> "%LOG%" 2>&1
exit /b 0

:skipped
del /q "data\sync_wellness_run_start.txt" >nul 2>&1
rem Still run the watchdog on a skipped round. This lane is the system heartbeat, and a
rem long-running lane hogging sync.lock is exactly when something is wrong - the watchdog
rem must not go quiet at the same time. -StaleOnly because there is no round result here.
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\notify_sync.ps1" -StaleOnly -CheckStale >> "%LOG%" 2>&1
exit /b 0
