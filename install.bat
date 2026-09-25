@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   FC 26 라이브 채팅 설치 (처음 한 번만)
echo ============================================
where python >nul 2>nul
if errorlevel 1 (
  echo 파이썬이 없습니다. python.org 에서 Python 3.11 또는 3.12를 설치하고
  echo 설치 화면에서 "Add python.exe to PATH"를 꼭 체크한 뒤 다시 실행해 주세요.
  pause
  exit /b 1
)
echo.
echo [1/3] 필요한 프로그램 설치 중...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo 설치에 실패했습니다. 인터넷 연결을 확인하고 다시 실행해 주세요.
  pause
  exit /b 1
)
echo.
where nvidia-smi >nul 2>nul
if not errorlevel 1 (
  echo NVIDIA 그래픽카드를 찾았습니다. 받아쓰기를 그래픽카드로 돌리는 데 필요한 파일을 설치합니다...
  python -m pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"
)
echo.
echo [2/3] 받아쓰기·화면 읽기 모델 내려받는 중 (처음 한 번)...
python fc26_live_chat.py --prepare
echo.
echo [3/3] 윈도우 켜질 때 자동으로 대기하도록 등록 중...
python fc26_live_chat.py --install-autostart
start "" pythonw fc26_live_chat.py
echo.
echo 설치 완료! 이제 FC 26만 실행하면 채팅 창과 선발 명단이 자동으로 뜹니다.
echo (FC 26 화면 설정에서 '테두리 없는 창' 모드를 쓰면 게임 위에 잘 보입니다.)
pause
