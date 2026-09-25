SimulChat 한국어로 쓰기

SimulChat(https://github.com/mem0cypher/SimulChat, MIT 라이선스)은 영어 전용이라,
이 폴더의 파일로 채팅을 한국어로 바꿉니다. SimulChat 코드는 여기 들어 있지 않고, 원본을 받아서 바꿉니다.

[처음 한 번]
1. Node.js, FFmpeg 설치 (명령 창에서)
     winget install OpenJS.NodeJS.LTS
     winget install Gyan.FFmpeg
   설치 후 명령 창을 새로 여세요.
2. 한국어 채팅 모델 받기:  ollama pull exaone3.5:7.8b
   화면 분석 모델 받기:    ollama pull qwen2.5vl:3b
3. https://github.com/mem0cypher/SimulChat 에서 Code → Download ZIP → 압축 풀기
4. 이 폴더의 simulchat_korean.py 와 start_simulchat_ko.bat 을
   압축 푼 SimulChat 폴더(backend, frontend가 있는 곳)에 복사

[실행]
start_simulchat_ko.bat 더블클릭 → 창 두 개가 뜨면, "SimulChat 화면" 창에 나온 주소를 브라우저에서 엽니다.

[바뀌는 것]
- 모든 AI 시청자가 한국어 라이브 채팅 말투로 채팅 (성격은 그대로)
- 영어 이모트(KEKW, POG…)만 나오면 한국식(ㅋㅋㅋㅋ, ㄷㄷ…)으로
- 채팅 모델: exaone3.5:7.8b (start_simulchat_ko.bat 안의 SIMULCHAT_CHAT_MODEL로 바꿀 수 있음)
- 목소리 인식: 한국어
- 원본은 backend\app.py.orig 로 남습니다. 되돌리려면 이 파일 이름을 app.py 로 바꾸세요.

화면 글자(메뉴·AI 시청자 이름)는 영어 그대로입니다.
