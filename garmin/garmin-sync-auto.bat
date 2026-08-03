@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem NOTE: keep this .bat pure ASCII. Thai text in a .bat breaks cmd.exe parsing
rem (multibyte bytes get mis-split into bogus commands, even inside rem). Thai belongs
rem in the .py/.ps1 files, not here.
rem IMPORTANT: every sync lane logs to its OWN file. When two lanes shared one log,
rem cmd.exe could not open the redirect target and the whole command line was skipped
rem (python never ran, the round vanished silently). See scripts\prep_log.ps1.
set "LOG=C:\Backup\garmin-sync-full.log"
rem rotate the log when oversized + write this round's ISO start marker for notify
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\prep_log.ps1" -LogPath "%LOG%" -Marker "data\sync_run_start.txt"
echo ---- FULL %date% %time% ---->> "%LOG%"
rem --catch-up-slots: the task fires hourly, this decides which round is real, so a PC
rem asleep at 08:00 still gets the 08:00 full sync when it wakes (exit 75 = skipped).
".venv\Scripts\python.exe" scripts\fetch_all.py --days 3 --catch-up-slots 08:00,21:00 >> "%LOG%" 2>&1
set "SYNC_EXIT=%ERRORLEVEL%"
rem Exit 75 = round skipped on purpose (this hourly round is not a catch-up slot).
rem Drop the start marker when we skip: the watchdog reads a marker with no matching
rem status as "started and never finished", and a skipped round is not a dead one.
if "%SYNC_EXIT%"=="75" goto skipped
rem toast alert on failure / bad token / suspicious data (silent when OK); pass exit code
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\notify_sync.ps1" -SyncExit %SYNC_EXIT% -Lane full >> "%LOG%" 2>&1
exit /b 0

:skipped
del /q "data\sync_run_start.txt" >nul 2>&1
exit /b 0
