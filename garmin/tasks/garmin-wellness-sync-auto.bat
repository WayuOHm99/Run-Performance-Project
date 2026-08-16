@echo off
chcp 65001 >nul
cd /d "%~dp0.."
rem NOTE: keep this .bat pure ASCII. Fast wellness pulls today's intraday values
rem (body battery / resting HR / stress / steps / HRV / sleep / training readiness)
rem and updates them column-by-column, so nothing the full sync stored gets wiped.
rem If yesterday is incomplete or invalid, the Python path also repairs it with a
rem six-hour cooldown and includes sleep respiration. This closes late Garmin updates
rem without doubling API traffic on every 30-minute round. The twice-daily full sync
rem still owns training status, VO2max trend, endurance / hill scores and the extras.
rem Own log file per lane - a shared log made concurrent lanes drop whole rounds.
set "LOG=C:\Backup\run-performance-logs\garmin-sync-wellness.log"
powershell -NoProfile -ExecutionPolicy Bypass -File "..\scripts\harden_private_acl.ps1" -Scope Logs -Recurse >nul 2>&1
set "ACL_EXIT=%ERRORLEVEL%"
if not "%ACL_EXIT%"=="0" exit /b %ACL_EXIT%
powershell -NoProfile -ExecutionPolicy Bypass -File "..\scripts\harden_private_acl.ps1" -Scope Garmin -Recurse >nul 2>&1
set "ACL_EXIT=%ERRORLEVEL%"
if not "%ACL_EXIT%"=="0" exit /b %ACL_EXIT%
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\prep_log.ps1" -LogPath "%LOG%" -Marker "data\sync_wellness_run_start.txt"
set "PREP_EXIT=%ERRORLEVEL%"
if not "%PREP_EXIT%"=="0" exit /b %PREP_EXIT%
echo ---- WELLNESS %date% %time% ---->> "%LOG%"
rem lock-timeout 240 (was 0): waiting beats throwing the round away. Triggers are spread
rem across the hour, but when the PC wakes from sleep Windows fires every missed trigger
rem at once - on 2026-08-04 the full sync and this lane both fired at 08:14, this one lost
rem the lock, and the team's body battery / HRV sat 9 hours stale until the next round.
rem 4 min is safe here: rounds are 30 min apart, the task limit is 20 min, and a round
rem that still cannot get the lock exits 75 and skips exactly as before.
".venv\Scripts\python.exe" scripts\fetch_all.py --days 0 --wellness-fast --max-workers 3 --lock-timeout 240 >> "%LOG%" 2>&1
set "SYNC_EXIT=%ERRORLEVEL%"
rem Exit 75 means another sync owns the cross-task lock; skipping is expected. Drop the
rem start marker when we skip: the watchdog reads a marker with no matching status as
rem "started and never finished", and a skipped round is not a dead one.
if "%SYNC_EXIT%"=="75" goto skipped
rem -CheckStale: this lane runs every 30 min, so it doubles as the watchdog that warns
rem when any other lane (full / fast / wellness / reconcile / deep) has silently stopped
rem producing rounds, or started a round that never finished.
:notify
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\notify_sync.ps1" -SyncExit %SYNC_EXIT% -Lane wellness -StartMarker "sync_wellness_run_start.txt" -CheckStale >> "%LOG%" 2>&1
exit /b %SYNC_EXIT%

:skipped
del /q "data\sync_wellness_run_start.txt" >nul 2>&1
rem Still run the watchdog on a skipped round. This lane is the system heartbeat, and a
rem long-running lane hogging sync.lock is exactly when something is wrong - the watchdog
rem must not go quiet at the same time. -StaleOnly because there is no round result here.
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\notify_sync.ps1" -StaleOnly -CheckStale >> "%LOG%" 2>&1
exit /b 0
