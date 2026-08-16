@echo off
chcp 65001 >nul
cd /d "%~dp0.."
rem NOTE: keep this .bat pure ASCII. The fast path fetches only today's activity
rem summaries; the twice-daily full sync fills wellness, detail, weather and splits.
rem Own log file per lane - a shared log made concurrent lanes drop whole rounds.
set "LOG=C:\Backup\run-performance-logs\garmin-sync-fast.log"
powershell -NoProfile -ExecutionPolicy Bypass -File "..\scripts\harden_private_acl.ps1" -Scope Logs -Recurse >nul 2>&1
set "ACL_EXIT=%ERRORLEVEL%"
if not "%ACL_EXIT%"=="0" exit /b %ACL_EXIT%
powershell -NoProfile -ExecutionPolicy Bypass -File "..\scripts\harden_private_acl.ps1" -Scope Garmin -Recurse >nul 2>&1
set "ACL_EXIT=%ERRORLEVEL%"
if not "%ACL_EXIT%"=="0" exit /b %ACL_EXIT%
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\prep_log.ps1" -LogPath "%LOG%" -Marker "data\sync_fast_run_start.txt"
set "PREP_EXIT=%ERRORLEVEL%"
if not "%PREP_EXIT%"=="0" exit /b %PREP_EXIT%
echo ---- FAST %date% %time% ---->> "%LOG%"
rem lock-timeout 120 (was 0): a round that waits still delivers; a round that skips is
rem gone for 15 minutes. Collisions happen mostly on wake-from-sleep, when Windows fires
rem every missed trigger at once. Kept shorter than the wellness lane's wait because this
rem one repeats 2x more often and its task limit is 10 min.
".venv\Scripts\python.exe" scripts\fetch_all.py --days 0 --activities-only --max-workers 3 --lock-timeout 120 >> "%LOG%" 2>&1
set "SYNC_EXIT=%ERRORLEVEL%"
rem Exit 75 means another sync owns the cross-task lock; skipping is expected. Drop the
rem start marker when we skip: the watchdog reads a marker with no matching status as
rem "started and never finished", and a skipped round is not a dead one.
if "%SYNC_EXIT%"=="75" goto skipped
:notify
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\notify_sync.ps1" -SyncExit %SYNC_EXIT% -Lane fast -StartMarker "sync_fast_run_start.txt" >> "%LOG%" 2>&1
exit /b %SYNC_EXIT%

:skipped
del /q "data\sync_fast_run_start.txt" >nul 2>&1
exit /b 0
