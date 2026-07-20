@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ---- %date% %time% ---->> "C:\Backup\sync-log.txt"
python sync_line.py >> "C:\Backup\sync-log.txt" 2>&1
