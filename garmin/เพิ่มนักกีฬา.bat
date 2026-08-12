@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==========================================
echo   ADD ATHLETE - CREATE GARMIN TOKEN
echo ==========================================
echo.
echo You will be asked for an ASCII athlete slug, email, and Garmin password.
echo The password stays hidden and is never saved.
echo.
".venv\Scripts\python.exe" scripts\01_generate_token.py
echo.
pause
