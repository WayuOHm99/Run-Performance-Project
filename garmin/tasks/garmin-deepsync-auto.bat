@echo off
chcp 65001 >nul
cd /d "%~dp0.."
rem Monthly: deep resync wellness/extras over the last 45 days (skip activities -> no
rem duplicate API). Catches values Garmin recomputes late (sleep/VO2max/training_status
rem beyond the daily 3-day window). Then run schema-drift check. Schedule monthly.
rem Keep this .bat pure ASCII: Thai text breaks cmd.exe parsing.
rem Own log file per lane - a shared log made concurrent lanes drop whole rounds.
set "LOG=C:\Backup\run-performance-logs\garmin-sync-deepsync.log"
powershell -NoProfile -ExecutionPolicy Bypass -File "..\scripts\harden_private_acl.ps1" -Scope Logs -Recurse >nul 2>&1
set "ACL_EXIT=%ERRORLEVEL%"
if not "%ACL_EXIT%"=="0" exit /b %ACL_EXIT%
powershell -NoProfile -ExecutionPolicy Bypass -File "..\scripts\harden_private_acl.ps1" -Scope Garmin -Recurse >nul 2>&1
set "ACL_EXIT=%ERRORLEVEL%"
if not "%ACL_EXIT%"=="0" exit /b %ACL_EXIT%
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\prep_log.ps1" -LogPath "%LOG%" -Marker "data\sync_deep_run_start.txt"
set "PREP_EXIT=%ERRORLEVEL%"
if not "%PREP_EXIT%"=="0" exit /b %PREP_EXIT%
echo ==== DEEPSYNC %date% %time% ====>> "%LOG%"
".venv\Scripts\python.exe" scripts\fetch_all.py --days 45 --skip-activities >> "%LOG%" 2>&1
set "SYNC_EXIT=%ERRORLEVEL%"
set "FAILURE_CONTEXT="
rem Exit 75 means another sync owns the cross-task lock; skipping is expected. Drop the
rem start marker when we skip: the watchdog reads a marker with no matching status as
rem "started and never finished", and a skipped round is not a dead one.
if "%SYNC_EXIT%"=="75" goto skipped
if not "%SYNC_EXIT%"=="0" goto notify
".venv\Scripts\python.exe" scripts\check_drift.py --record-deep-status >> "%LOG%" 2>&1
set "DRIFT_EXIT=%ERRORLEVEL%"
if "%DRIFT_EXIT%"=="0" goto notify
set "SYNC_EXIT=%DRIFT_EXIT%"
set "FAILURE_CONTEXT=drift"
:notify
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\notify_sync.ps1" -SyncExit %SYNC_EXIT% -Lane deep -StartMarker "sync_deep_run_start.txt" -FailureContext "%FAILURE_CONTEXT%" >> "%LOG%" 2>&1
exit /b %SYNC_EXIT%

:skipped
del /q "data\sync_deep_run_start.txt" >nul 2>&1
exit /b 0
