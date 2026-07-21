@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==========================================
echo   เพิ่มนักกีฬาใหม่ - สร้าง Garmin Token
echo ==========================================
echo.
echo จะถาม: ชื่อ (พิมพ์เป็น slug อังกฤษ เช่น dan) / อีเมล / รหัส Garmin
echo รหัสจะไม่แสดงบนจอ (ปกติ) และไม่ถูกบันทึกลงไฟล์
echo.
".venv\Scripts\python.exe" scripts\01_generate_token.py
echo.
pause
