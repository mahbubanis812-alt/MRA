@echo off
cd /d "%~dp0"
py -m pip install -r requirements.txt
py setup_profile.py
pause
