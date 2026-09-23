@echo off
cd /d "%~dp0"
py -m playwright install chromium >nul 2>&1
py photoroom_bg_remove.py
pause
