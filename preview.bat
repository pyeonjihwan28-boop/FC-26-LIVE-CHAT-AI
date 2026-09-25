@echo off
chcp 65001 >nul
cd /d "%~dp0"
python fc26_live_chat.py --stop >nul 2>nul
start "" /wait pythonw fc26_live_chat.py --demo
start "" pythonw fc26_live_chat.py
