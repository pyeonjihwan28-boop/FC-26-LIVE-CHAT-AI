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
echo [1/4] 필요한 프로그램 설치 중...
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
echo [2/4] 이 PC용 AI(Ollama) 확인 중...
set "OLLAMA=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
where ollama >nul 2>nul && set "OLLAMA=ollama"
if "%OLLAMA%"=="ollama" goto ollama_ok
if exist "%OLLAMA%" goto ollama_ok
echo Ollama가 없어 설치합니다...
where winget >nul 2>nul
if not errorlevel 1 (
  winget install -e --id Ollama.Ollama --accept-source-agreements --accept-package-agreements
)
if exist "%OLLAMA%" goto ollama_ok
echo winget으로 설치하지 못해 설치 파일을 직접 내려받습니다...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://ollama.com/download/OllamaSetup.exe' -OutFile \"$env:TEMP\OllamaSetup.exe\""
if exist "%TEMP%\OllamaSetup.exe" (
  echo Ollama 설치 창이 뜨면 설치를 눌러 주세요. 끝나면 이 창으로 돌아옵니다.
  start /wait "" "%TEMP%\OllamaSetup.exe"
)
if not exist "%OLLAMA%" (
  echo Ollama를 설치하지 못했습니다. AI 없이 기본 반응으로 동작합니다.
  echo 나중에 ollama.com 에서 설치한 뒤 이 파일을 다시 실행하면 AI가 켜집니다.
  goto after_ollama
)
:ollama_ok
start "" /b "%OLLAMA%" serve >nul 2>nul
timeout /t 5 >nul
echo AI 모델 내려받는 중 (약 8GB, 처음 한 번)...
echo  - 채팅용 한국어 모델 (EXAONE 3.5)
"%OLLAMA%" pull exaone3.5:7.8b
echo  - 화면 보고 팀 찾는 모델 (gemma3)
"%OLLAMA%" pull gemma3:4b
:after_ollama
echo.
echo [3/4] 받아쓰기·화면 읽기 모델 내려받는 중 (처음 한 번)...
python fc26_live_chat.py --prepare
echo.
echo [4/4] 윈도우 켜질 때 자동으로 대기하도록 등록 중...
python fc26_live_chat.py --install-autostart
start "" pythonw fc26_live_chat.py
echo.
echo 설치 완료! 이제 FC 26만 실행하면 채팅 창과 선발 명단이 자동으로 뜹니다.
echo (FC 26 화면 설정에서 '테두리 없는 창' 모드를 쓰면 게임 위에 잘 보입니다.)
pause
