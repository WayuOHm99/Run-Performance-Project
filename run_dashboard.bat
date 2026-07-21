@echo off
chcp 65001 >nul
echo กำลังเปิด Dashboard...
cd /d "%~dp0\garmin"
".venv\Scripts\python.exe" -m streamlit run scripts\dashboard.py
pause
