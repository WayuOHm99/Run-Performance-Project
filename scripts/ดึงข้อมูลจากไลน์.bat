@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo ==========================================
echo   ดึงรูป/ข้อความจากกลุ่มไลน์ลงเครื่อง
echo ==========================================
python sync_line.py %*
echo.
pause
