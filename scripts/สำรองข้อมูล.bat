@echo off
rem === Run-Performance backup (mirror D:\Run-Performance to C:\Backup) ===
rem Excludes: .env (secret key), __pycache__ (junk)
rem Usage: double-click to run manually, or Task Scheduler runs it daily 22:00
set SRC=D:\Run-Performance
set DEST=C:\Backup\Run-Performance
set LOG=C:\Backup\backup-log.txt
if not exist "C:\Backup" mkdir "C:\Backup"
robocopy "%SRC%" "%DEST%" /MIR /XF .env /XD __pycache__ /R:2 /W:5 /NP /LOG:"%LOG%"
if %errorlevel% geq 8 goto :bad
echo.
echo [OK] Backup done - %DEST%
goto :done
:bad
echo.
echo [FAIL] Backup problem - open %LOG% and show it to Claude
:done
if /I not "%~1"=="auto" pause