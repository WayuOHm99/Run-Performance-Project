@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Monthly: deep resync wellness/extras over the last 45 days (skip activities -> no
rem duplicate API). Catches values Garmin recomputes late (sleep/VO2max/training_status
rem beyond the daily 3-day window). Then run schema-drift check. Schedule monthly.
rem Keep this .bat pure ASCII: Thai text breaks cmd.exe parsing.
rem Own log file per lane - a shared log made concurrent lanes drop whole rounds.
set "LOG=C:\Backup\garmin-sync-deepsync.log"
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\prep_log.ps1" -LogPath "%LOG%" -Marker "data\sync_deep_run_start.txt"
echo ==== DEEPSYNC %date% %time% ====>> "%LOG%"
".venv\Scripts\python.exe" scripts\fetch_all.py --days 45 --skip-activities >> "%LOG%" 2>&1
rem capture the sync result before check_drift overwrites ERRORLEVEL (drift exits 1 on
rem its own findings - that must not be reported as "sync failed")
set "SYNC_EXIT=%ERRORLEVEL%"
".venv\Scripts\python.exe" scripts\check_drift.py >> "%LOG%" 2>&1
if "%SYNC_EXIT%"=="75" exit /b 0
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\notify_sync.ps1" -SyncExit %SYNC_EXIT% -Lane deep -StartMarker "sync_deep_run_start.txt" >> "%LOG%" 2>&1
