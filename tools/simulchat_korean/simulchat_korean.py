# -*- coding: utf-8 -*-
"""SimulChat(https://github.com/mem0cypher/SimulChat)을 한국어 채팅으로 바꾸는 스크립트.
SimulChat 폴더(backend, frontend가 있는 곳)에 이 파일을 넣고 `python simulchat_korean.py` 실행.
원본 파일은 backend/app.py.orig 로 남겨 둠. 여러 번 실행해도 한 번만 바뀜."""
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / "backend" / "app.py"
MARK = "# [SimulChat 한국어]"

KOREAN_RULES = '''
KOREAN_RULES = """
[가장 중요 — 언어]
위 설명은 영어지만 채팅은 무조건 한국어로 써. 한국 트위치·유튜브 라이브 채팅 말투로.
- 반말, 대부분 1~15자로 짧게. 마침표 안 찍음. 번역투·존댓말 쓰지 말 것.
- 영어 이모트(KEKW, POG, LULW, catJAM, monkaS 등) 대신 한국식으로: ㅋㅋㅋㅋ, ㄷㄷ, ㅠㅠ, ㄹㅇ, ㅇㅈ, 헐, 와, 미쳤다
- 예시: ㅋㅋㅋㅋㅋ / 와 미쳤다 / ㄹㅇ / 이거 뭐임 / 개웃기네 / 헐 / ㅇㅈ / 방금 봤음? / 노래 좋다 / 오 잘하네 / ㄴㄴ 아님 / 몇 시에 끝남? / 배고프다
- 영어 단어·영어 문장은 쓰지 말 것 (게임·사람 이름 같은 고유명사만 빼고).
- 네 성격(위 설명)은 그대로 살리되 한국 사람이 치는 채팅처럼."""
KO_FALLBACK = ["ㅋㅋㅋㅋ", "ㄷㄷ", "ㄹㅇ", "와", "헐", "ㅇㅈ", "ㅋㅋㅋ 뭐임", "오", "미쳤다", "ㅠㅠ"]
EN_EMOTE_KO = {"kekw": "ㅋㅋㅋㅋ", "lulw": "ㅋㅋㅋㅋㅋ", "lul": "ㅋㅋ", "lol": "ㅋㅋ", "pog": "ㄷㄷ", "poggers": "ㄷㄷㄷ",
               "pogchamp": "와 ㄷㄷ", "monkas": "ㄷㄷ;;", "catjam": "노래 좋다", "based": "ㄹㅇ", "cringe": "좀 그렇네",
               "yikes": "헐", "nice": "오 굿", "true": "ㄹㅇ", "facts": "ㅇㅈ", "bruh": "아니 ㅋㅋ", "gg": "ㅈㅈ"}
_HANGUL = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]")


def to_korean_chat(msg):
    """한글이 하나도 없는 답(영어 이모트 등)은 한국식으로 바꿈"""
    if msg and _HANGUL.search(msg):
        return msg
    key = re.sub(r"[^a-z]", "", (msg or "").lower())
    return EN_EMOTE_KO.get(key) or KO_FALLBACK[hash(msg or "") % len(KO_FALLBACK)]
'''


def main():
    if not APP.exists():
        sys.exit("backend/app.py를 찾지 못했습니다. 이 파일을 SimulChat 폴더(backend, frontend가 있는 곳)에 넣고 실행하세요.")
    src = APP.read_text(encoding="utf-8")
    if MARK in src:
        print("이미 한국어로 바뀌어 있습니다.")
        return
    shutil.copy(APP, APP.with_suffix(".py.orig"))
    changes = [
        # 1) 한국어 규칙·영어 이모트 바꾸기 함수 추가
        ("def filter_authentic_twitch_response(response):",
         MARK + KOREAN_RULES + "\n\ndef filter_authentic_twitch_response(response):"),
        # 2) 모든 채팅 지시문 맨 끝에 한국어 규칙 (마지막 지시가 가장 잘 먹힘)
        ('        final_prompt = "\\n\\n".join(prompt_parts)',
         '        prompt_parts.append(KOREAN_RULES)\n        final_prompt = "\\n\\n".join(prompt_parts)'),
        # 3) 영어 이모트만 나오면 한국식으로
        ("        ai_message = filter_authentic_twitch_response(ai_message)",
         "        ai_message = to_korean_chat(filter_authentic_twitch_response(ai_message))"),
        # 4) 채팅 모델: 환경 변수 SIMULCHAT_CHAT_MODEL (예: exaone3.5:7.8b) — 채팅 시청자는 그림을 안 받아서 한국어 모델 가능
        ("        model_name = data.get('model_name', DEFAULT_OLLAMA_MODEL)",
         "        model_name = os.environ.get('SIMULCHAT_CHAT_MODEL') or data.get('model_name', DEFAULT_OLLAMA_MODEL)"),
        # 5) 목소리 인식: 한국어
        ("recognizer.recognize_google(audio_data)",
         "recognizer.recognize_google(audio_data, language=os.environ.get('SIMULCHAT_SPEECH_LANG', 'ko-KR'))"),
    ]
    missing = [old.strip()[:60] for old, _ in changes if src.count(old) != 1]
    if missing:
        sys.exit("SimulChat 버전이 달라서 바꿀 곳을 못 찾았습니다:\n- " + "\n- ".join(missing))
    for old, new in changes:
        src = src.replace(old, new)
    if not re.search(r"^import re\b", src, re.M):
        src = "import re\n" + src
    APP.write_text(src, encoding="utf-8")
    print("완료! SimulChat 채팅이 한국어로 나옵니다. (원본: backend/app.py.orig)")


if __name__ == "__main__":
    main()
