@echo off
chcp 65001 >nul
echo Opening Dashboard on this computer only...
cd /d "%~dp0\garmin"
".venv\Scripts\python.exe" -m streamlit run scripts\dashboard.py --server.address 127.0.0.1
pause
