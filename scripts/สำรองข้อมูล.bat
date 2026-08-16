@echo off
rem === Run-Performance backup (mirror the project folder to C:\Backup) ===
rem Usage: double-click to run manually, or Task Scheduler runs it daily 22:00
rem   (scheduled runs go through scripts\backup-hidden.vbs - no closable window)
rem SRC is derived from this file's own location (parent of scripts\), never
rem hardcoded - renaming or moving the project folder must not break backups.
rem
rem Keep this .bat pure ASCII: cmd.exe breaks on multibyte Thai even in rem lines.
rem
rem WHY THE DB IS HANDLED SEPARATELY (found 2026-08-04, backup was 2 days stale):
rem   garmin.db is permanent WAL mode - writes land in the -wal sidecar and the
rem   main file only moves on checkpoint. robocopy saw "same size, same time" and
rem   SKIPPED it, so the only copy of the whole team's health data silently froze
rem   at 2026-08-02 21:50 while the job looked fine every night. The db files are
rem   excluded from the mirror here and copied by backup_db.py through the sqlite
rem   backup API instead, which merges the WAL and verifies the result.
rem
rem WHY .venv IS EXCLUDED: 418 MB of reproducible packages. The 2026-08-03 run was
rem still grinding through the tree when it got killed (0xC000013A). Rebuild with
rem   garmin\.venv\Scripts\python.exe -m pip install -r garmin\requirements.txt
rem The pattern is .venv* on purpose: an abandoned throwaway env named
rem .venv-lock-test (306 MB) was mirrored every night for weeks because the old
rem exclusion matched the exact name .venv only, and git could not see it either
rem (a venv ships its own .gitignore). .tmp is scratch space for tooling and is
rem excluded for the same reason. Excluded directories are never deleted from the
rem destination by /MIR, so clean leftovers there by hand once.
for %%I in ("%~dp0..") do set "SRC=%%~fI"
set "GARMIN=%SRC%\garmin"
set "DEST=C:\Backup\Run-Performance"
set "DAILY=C:\Backup\garmin-db-daily"
set "LOG=C:\Backup\run-performance-logs\backup-log.txt"
if not exist "C:\Backup" mkdir "C:\Backup"

rem Rotate the log and drop a start marker, so the watchdog in notify_sync.ps1 can
rem tell "started and never finished" from "never started". A killed run cannot
rem report itself - the marker is the only trace it leaves behind.
powershell -NoProfile -ExecutionPolicy Bypass -File "%SRC%\scripts\harden_private_acl.ps1" -Scope Logs -Recurse >nul 2>&1
set "ACL_EXIT=%ERRORLEVEL%"
if not "%ACL_EXIT%"=="0" exit /b %ACL_EXIT%
powershell -NoProfile -ExecutionPolicy Bypass -File "%SRC%\scripts\harden_private_acl.ps1" -Scope Backup -Recurse >nul 2>&1
set "ACL_EXIT=%ERRORLEVEL%"
if not "%ACL_EXIT%"=="0" exit /b %ACL_EXIT%
powershell -NoProfile -ExecutionPolicy Bypass -File "%GARMIN%\scripts\prep_log.ps1" -LogPath "%LOG%" -Marker "%GARMIN%\data\sync_backup_run_start.txt"
set "PREP_EXIT=%ERRORLEVEL%"
if not "%PREP_EXIT%"=="0" exit /b %PREP_EXIT%
echo ==== BACKUP %date% %time% ====>> "%LOG%"

robocopy "%SRC%" "%DEST%" /MIR /XF .env garmin.db garmin.db-wal garmin.db-shm /XD __pycache__ .venv* node_modules .tmp /R:2 /W:5 /NP /NDL /LOG+:"%LOG%"
set "ROBO_EXIT=%ERRORLEVEL%"

"%GARMIN%\.venv\Scripts\python.exe" "%GARMIN%\scripts\backup_db.py" --dest "%DEST%\garmin\data" --daily "%DAILY%" --robocopy-exit %ROBO_EXIT% >> "%LOG%" 2>&1
set "BACKUP_EXIT=%ERRORLEVEL%"

:notify
powershell -NoProfile -ExecutionPolicy Bypass -File "%GARMIN%\scripts\notify_sync.ps1" -SyncExit %BACKUP_EXIT% -Lane backup -StartMarker "sync_backup_run_start.txt" >> "%LOG%" 2>&1

if "%BACKUP_EXIT%"=="0" goto ok
echo.
echo [FAIL] Backup problem - open %LOG% and show it to Claude
goto done
:ok
echo.
echo [OK] Backup done - %DEST% + db snapshot + %DAILY%
:done
if /I not "%~1"=="auto" pause
exit /b %BACKUP_EXIT%
