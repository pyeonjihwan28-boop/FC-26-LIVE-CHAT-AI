@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist backend\app.py (
  echo 이 파일을 SimulChat 폴더^(backend, frontend가 있는 곳^)에 넣고 실행하세요.
  pause
  exit /b 1
)
echo [1/3] 한국어로 바꾸기...
python simulchat_korean.py
rem 채팅 시청자용 한국어 모델 (없으면 ollama pull exaone3.5:7.8b)
set SIMULCHAT_CHAT_MODEL=exaone3.5:7.8b
set SIMULCHAT_SPEECH_LANG=ko-KR
echo [2/3] 백엔드 켜는 중 (처음엔 설치 때문에 오래 걸림)...
if not exist backend\venv python -m venv backend\venv
start "SimulChat 백엔드" cmd /k "cd /d %~dp0backend && venv\Scripts\activate && pip install -q -r requirements.txt && python app.py"
echo [3/3] 화면 켜는 중...
start "SimulChat 화면" cmd /k "cd /d %~dp0frontend && npm install && npm run dev"
echo.
echo 두 창이 뜹니다. "SimulChat 화면" 창에 나온 주소(보통 http://localhost:5173)를 브라우저에서 여세요.
echo 끌 때는 두 창을 닫으면 됩니다.
pause
