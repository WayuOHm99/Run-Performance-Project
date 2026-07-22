@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ---- %date% %time% ---->> "C:\Backup\garmin-sync-log.txt"
rem NOTE: keep this .bat pure ASCII. Thai text in a .bat breaks cmd.exe parsing
rem (multibyte bytes get mis-split into bogus commands, even inside rem). Thai belongs
rem in the .py/.ps1 files, not here.
rem write ISO start-time marker so notify can tell if fetch_all wrote status THIS run
rem (prevents a false "sync died" toast on a manual run near a previous run)
powershell -NoProfile -Command "(Get-Date).ToString('o') | Set-Content -NoNewline -Encoding ASCII 'data\sync_run_start.txt'"
".venv\Scripts\python.exe" scripts\fetch_all.py --days 3 >> "C:\Backup\garmin-sync-log.txt" 2>&1
rem toast alert on failure / bad token / suspicious data (silent when OK); pass exit code
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\notify_sync.ps1" -SyncExit %ERRORLEVEL% >> "C:\Backup\garmin-sync-log.txt" 2>&1
