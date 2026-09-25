@echo off
chcp 65001 >nul
cd /d "%~dp0"
python fc26_live_chat.py --stop
python fc26_live_chat.py --uninstall-autostart
echo 채팅을 끄고 자동 실행을 해제했습니다. 다시 쓰려면 install.bat을 실행하세요.
pause
