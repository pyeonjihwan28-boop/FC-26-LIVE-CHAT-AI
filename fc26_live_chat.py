#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FC 26 라이브 채팅
- FC 26이 켜지면 자동으로 채팅 창(유튜브 라이브 채팅 스타일)과 선발 명단 오버레이를 띄웁니다.
- 게임 소리(해설)를 이 PC 안에서 받아쓰고(faster-whisper), 스코어보드를 읽고(RapidOCR),
  채팅은 AI 없이 chat_lines.py의 문장과 경기 상황으로 만듭니다 (Ollama 같은 AI는 쓰지 않음).
- 받아쓴 해설은 게임 위 자막 창으로도 띄웁니다 (말하는 중에도 먼저 뜨는 미리보기 자막, 파일 저장).
- 채팅 분위기(모드)·세기, 방장 채팅 입력, 시청자끼리 @부르기, 채팅 캡처 저장.
- 받아쓰기가 없으면 스코어보드와 평소 잡담만으로 채팅합니다.
"""
from __future__ import annotations

import argparse
import functools
import unicodedata
import json
import logging
import math
import os
import queue
import random
import re
import sys
import threading
import time
from pathlib import Path

import tkinter as tk
from tkinter import colorchooser, messagebox, ttk
from tkinter import font as tkfont

APP_NAME = "FC26 실시간 채팅"
APP_DIR = Path(__file__).resolve().parent
CFG_PATH = APP_DIR / "fc26_chat_config.json"
LOG_PATH = APP_DIR / "fc26_chat.log"
PID_PATH = APP_DIR / "fc26_chat.pid"
LEARN_PATH = APP_DIR / "fc26_chat_learned.json"   # 예전 버전이 AI로 모은 문장·닉네임 (이제 안 쓰고, 켤 때 지움)
IS_WIN = sys.platform.startswith("win")

sys.path.insert(0, str(APP_DIR))
import chat_lines as CL  # noqa: E402  (채팅 문장·닉네임 재료)

logging.basicConfig(
    filename=str(LOG_PATH), level=logging.INFO, encoding="utf-8",
    format="%(asctime)s %(levelname)s %(threadName)s: %(message)s",
)
log = logging.getLogger("fc26")

# ---------------------------------------------------------------------------
# 팀 정보
# 팬 수(백만 명) = 공식 SNS 팔로워 합계. 상위 10팀은 GOAL(2026년 1월), 나머지는
# Sportingpedia/Planet Football(2026년 1월) 집계를 따름. 대략적인 추정치입니다.
# codes = 게임 스코어보드에 뜰 수 있는 약칭 후보.
# ---------------------------------------------------------------------------
TEAMS = [
    dict(ko="레알 마드리드", en="Real Madrid", codes=["RMA", "RMD"], alias=["레알", "마드리드", "real madrid"], fans=449.5),
    dict(ko="바르셀로나", en="FC Barcelona", codes=["BAR", "FCB", "BCN"], alias=["바르샤", "바르셀로나", "barcelona", "barca"], fans=403.3),
    dict(ko="맨체스터 유나이티드", en="Manchester United", codes=["MUN", "MNU", "MUFC"], alias=["맨유", "맨체스터 유나이티드", "manchester united", "man utd"], fans=229.6),
    dict(ko="파리 생제르맹", en="Paris Saint-Germain", codes=["PSG", "PAR"], alias=["파리", "생제르맹", "psg"], fans=195.0),
    dict(ko="맨체스터 시티", en="Manchester City", codes=["MCI", "MCFC", "MNC"], alias=["맨시티", "맨체스터 시티", "manchester city", "man city"], fans=173.1),
    dict(ko="리버풀", en="Liverpool", codes=["LIV"], alias=["리버풀", "liverpool"], fans=171.2),
    dict(ko="유벤투스", en="Juventus", codes=["JUV"], alias=["유벤투스", "유베", "juventus"], fans=164.5),
    dict(ko="첼시", en="Chelsea", codes=["CHE"], alias=["첼시", "chelsea"], fans=155.6),
    dict(ko="바이에른 뮌헨", en="FC Bayern München", codes=["FCB", "BAY", "FCBM"], alias=["바이에른", "뮌헨", "bayern"], fans=146.3),
    dict(ko="아스널", en="Arsenal", codes=["ARS"], alias=["아스널", "arsenal"], fans=116.5),
    dict(ko="토트넘", en="Tottenham Hotspur", codes=["TOT"], alias=["토트넘", "스퍼스", "tottenham", "spurs"], fans=106.3),
    dict(ko="AC 밀란", en="AC Milan", codes=["MIL", "ACM"], alias=["ac 밀란", "밀란", "ac milan", "milan"], fans=80.0),
    dict(ko="아틀레티코 마드리드", en="Atlético de Madrid", codes=["ATM", "ATL"], alias=["아틀레티코", "atletico"], fans=72.3),
    dict(ko="인테르", en="Inter", codes=["INT", "INTER"], alias=["인테르", "인터 밀란", "inter"], fans=69.7),
    dict(ko="알 나스르", en="Al Nassr", codes=["NAS", "ANS"], alias=["알 나스르", "al nassr"], fans=62.0),
    dict(ko="도르트문트", en="Borussia Dortmund", codes=["BVB", "DOR"], alias=["도르트문트", "dortmund"], fans=59.0),
    dict(ko="갈라타사라이", en="Galatasaray", codes=["GAL", "GS"], alias=["갈라타사라이", "galatasaray"], fans=48.4),
    dict(ko="인터 마이애미", en="Inter Miami", codes=["MIA"], alias=["인터 마이애미", "inter miami"], fans=42.0),
    dict(ko="아약스", en="Ajax", codes=["AJA", "AJX"], alias=["아약스", "ajax"], fans=25.5),
    dict(ko="모나코", en="AS Monaco", codes=["MON", "ASM"], alias=["모나코", "monaco"], fans=24.0),
    dict(ko="마르세유", en="Olympique de Marseille", codes=["OM", "MAR", "OMA"], alias=["마르세유", "marseille"], fans=21.8),
    dict(ko="나폴리", en="Napoli", codes=["NAP"], alias=["나폴리", "napoli"], fans=19.2),
    dict(ko="뉴캐슬", en="Newcastle United", codes=["NEW"], alias=["뉴캐슬", "newcastle"], fans=18.9),
    dict(ko="레버쿠젠", en="Bayer 04 Leverkusen", codes=["B04", "LEV"], alias=["레버쿠젠", "leverkusen"], fans=17.0),
    dict(ko="아틀레틱 빌바오", en="Athletic Club", codes=["ATH", "BIL"], alias=["빌바오", "아틀레틱", "athletic"], fans=16.7),
    dict(ko="벤피카", en="SL Benfica", codes=["BEN", "SLB"], alias=["벤피카", "benfica"], fans=12.1),
    dict(ko="스포르팅", en="Sporting CP", codes=["SCP", "SPO"], alias=["스포르팅", "sporting"], fans=10.9),
    dict(ko="비야레알", en="Villarreal", codes=["VIL"], alias=["비야레알", "villarreal"], fans=8.4),
    dict(ko="PSV", en="PSV", codes=["PSV"], alias=["psv", "아인트호벤"], fans=5.4),
    dict(ko="프랑크푸르트", en="Eintracht Frankfurt", codes=["SGE", "FRA"], alias=["프랑크푸르트", "frankfurt"], fans=5.3),
    dict(ko="아탈란타", en="Atalanta", codes=["ATA"], alias=["아탈란타", "atalanta"], fans=3.6),
    dict(ko="올림피아코스", en="Olympiacos", codes=["OLY"], alias=["올림피아코스", "olympiacos"], fans=3.4),
    dict(ko="클럽 브뤼헤", en="Club Brugge", codes=["BRU", "CLU"], alias=["브뤼헤", "brugge"], fans=3.0),
    # 팬 수 자료가 없는 팀(기본값으로 계산) - 이름 인식용
    dict(ko="아스톤 빌라", en="Aston Villa", codes=["AVL"], alias=["아스톤 빌라", "빌라", "aston villa"], fans=None),
    dict(ko="울버햄튼", en="Wolverhampton Wanderers", codes=["WOL"], alias=["울버햄튼", "울브스", "wolves"], fans=None),
    dict(ko="브라이턴", en="Brighton & Hove Albion", codes=["BHA", "BRI"], alias=["브라이턴", "brighton"], fans=None),
    dict(ko="웨스트햄", en="West Ham United", codes=["WHU"], alias=["웨스트햄", "west ham"], fans=None),
    dict(ko="마인츠", en="Mainz 05", codes=["M05", "MAI"], alias=["마인츠", "mainz"], fans=None),
    dict(ko="페예노르트", en="Feyenoord", codes=["FEY"], alias=["페예노르트", "feyenoord"], fans=None),
    dict(ko="LAFC", en="Los Angeles FC", codes=["LAFC", "LAF"], alias=["lafc", "로스앤젤레스"], fans=None),
    dict(ko="AS 로마", en="AS Roma", codes=["ROM", "ROMA"], alias=["로마", "roma"], fans=None),
    dict(ko="헐 시티", en="Hull City", codes=["HUL"], alias=["헐 시티", "헐시티", "hull"], fans=None),
]
DEFAULT_FANS = 10.0  # 백만 명, 팬 수를 모를 때
# 화면에 보이는 시청자 수 배율 (0.1 = 예전의 10분의 1). 채팅 속도·후원 빈도는 예전 시청자 수 기준 그대로.
VIEWER_SCALE = 0.1

# 선발 명단 머리에 쓰는 짧은 이름
SHORT = {
    "레알 마드리드": "레알", "바르셀로나": "바르샤", "맨체스터 유나이티드": "맨유", "파리 생제르맹": "PSG",
    "맨체스터 시티": "맨시티", "바이에른 뮌헨": "뮌헨", "아틀레티코 마드리드": "아틀레티코", "인터 마이애미": "마이애미",
    "아틀레틱 빌바오": "빌바오", "프랑크푸르트": "프랑크푸르트", "아스톤 빌라": "빌라", "울버햄튼": "울브스",
    "갈라타사라이": "갈라타사라이", "올림피아코스": "올림피아코스", "클럽 브뤼헤": "브뤼헤", "헐 시티": "헐시티", "AS 로마": "로마",
}

# 한국 선수(2025-26 시즌 기준 추정, 설정 파일에서 고칠 수 있음)
KOREAN_DEFAULT = {
    "파리 생제르맹": ["이강인"],
    "바이에른 뮌헨": ["김민재"],
    "울버햄튼": ["황희찬"],
    "LAFC": ["손흥민"],
    "마인츠": ["이재성"],
    "페예노르트": ["황인범"],
}

DEFAULT_CFG = {
    "whisper_model": "auto",          # auto / tiny / base / small / medium / large-v3-turbo
    "whisper_device": "auto",         # auto = 그래픽카드가 되면 그래픽카드, cpu = 항상 CPU
    "language": "ko",                 # (예전 설정, 지금은 commentary_language를 씀)
    "commentary_language": "ko",      # 해설 언어 (FC 26 한국어 해설). auto = 알아서 찾기
    "neutral_pct": 33,
    "speed": "normal",                # (자동) 시청자 수로 정해지므로 메뉴에서 뺐음
    "font_scale": 1.0,
    "always_on_top": True,
    "chroma": False,
    "show_transcript": False,
    "show_viewers": True,
    "show_composer": True,
    "lineup_visible": True,
    "lineup_scale": 1.0,
    "lineup_layout": "row",           # row = 가로로 나란히, column = 세로로 쌓기
    "scoreboard_region": [0.0, 0.0, 0.5, 0.2],   # 화면 비율 (왼쪽, 위, 폭, 높이)
    "korean_players": KOREAN_DEFAULT,
    "lineups": {},
    # 채팅 분위기 (CHAT_MODES) · 세기 0~10
    "chat_mode": "default",
    "chat_intensity": 5,
    "streamer_name": "방장",          # 입력창에 내가 쓴 채팅이 뜨는 이름
    # 해설 자막
    "show_captions": True,            # 게임 위 화면 아래쪽에 자막 창
    "caption_preview": "auto",        # 말하는 중에 먼저 뜨는 미리보기 자막 (auto = 그래픽카드로 받아쓸 때만)
    "save_transcript": False,         # 받아쓴 해설을 transcripts 폴더에 .txt로 저장
}


def load_cfg() -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CFG))
    try:
        if CFG_PATH.exists():
            user = json.loads(CFG_PATH.read_text(encoding="utf-8"))
            cfg.update({k: v for k, v in user.items() if k in DEFAULT_CFG})
    except Exception:
        log.exception("config load failed")
    return cfg


DEMO = False


def save_cfg(cfg: dict) -> None:
    if DEMO:
        return
    try:
        CFG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        log.exception("config save failed")


def norm(s: str) -> str:
    return re.sub(r"[\s.\-_'’&]", "", str(s or "").lower())


_ALIAS = sorted(
    [(norm(a), t) for t in TEAMS for a in [t["ko"], t["en"], *t["alias"]]],
    key=lambda x: -len(x[0]),
)
CODE_INDEX: dict[str, list] = {}
for _t in TEAMS:
    for _c in _t["codes"]:
        CODE_INDEX.setdefault(_c, []).append(_t)


def lookup_team(name: str):
    n = norm(name)
    if not n:
        return None
    for a, t in _ALIAS:
        if len(a) >= 3 and (n == a or a in n or (len(n) >= 3 and n in a)):
            return t
        if len(a) < 3 and n == a:
            return t
    return None


# ---------------------------------------------------------------------------
# 경기 상태 / 세력
# ---------------------------------------------------------------------------
class Side:
    def __init__(self, key: str):
        self.key = key
        self.name = ""
        self.fans: float | None = None
        self.fans_manual = False           # 팀 직접 정하기에서 팬 수를 넣었으면 AI가 바꾸지 않음
        self.color = "#FF4B44" if key == "home" else "#2F6BFF"

    @property
    def label(self) -> str:
        return self.name or ("홈 팀" if self.key == "home" else "원정 팀")

    @property
    def short(self) -> str:
        return SHORT.get(self.name, self.label)

    @property
    def fans_or_default(self) -> float:
        return self.fans if (self.fans or 0) > 0 else DEFAULT_FANS


class Match:
    def __init__(self, cfg):
        self.cfg = cfg
        self.home = Side("home")
        self.away = Side("away")
        self.hs = 0
        self.as_ = 0
        self.minute: int | None = None
        self.events: list[str] = []
        self.commentary: list[tuple[float, str]] = []
        self.marks: dict[str, dict[str, dict]] = {}   # 팀 이름 -> 선수 이름 -> 표시

    def side(self, key):
        return self.home if key == "home" else self.away

    def other(self, key):
        return "away" if key == "home" else "home"

    def korean_names(self, key) -> list[str]:
        return list(self.cfg.get("korean_players", {}).get(self.side(key).name, []))

    def has_korean(self, key) -> bool:
        return bool(self.korean_names(key))

    def split(self) -> dict:
        n0 = max(0.0, min(90.0, float(self.cfg.get("neutral_pct", 33))))
        fh, fa = self.home.fans_or_default, self.away.fans_or_default
        pool = 100.0 - n0
        h0 = pool * fh / (fh + fa)
        a0 = pool - h0
        # 한국 선수가 있는 팀: 중립 비율 × 그 팀 비율만큼 중립에서 그 팀으로 이동
        sh = n0 * h0 / 100.0 if self.has_korean("home") else 0.0
        sa = n0 * a0 / 100.0 if self.has_korean("away") else 0.0
        return {"home": h0 + sh, "away": a0 + sa, "neutral": n0 - sh - sa}

    def viewer_floor(self) -> int:
        return int(round((self.home.fans_or_default + self.away.fans_or_default) * 1e6 * 1.5 / 1000 * VIEWER_SCALE))

    def lineup(self, key) -> dict | None:
        lu = self.cfg.get("lineups", {}).get(self.side(key).label)
        return lu if lu and any(p.get("name") for p in lu.get("players", [])) else None

    def lineup_people(self, key) -> list[dict]:
        lu = self.lineup(key) or {}
        return [q for q in lu.get("players", []) + lu.get("bench", []) if q.get("name")]

    def lineup_en(self, key) -> list[str]:
        return [q["en"] for q in self.lineup_people(key) if q.get("en")]

    def lineup_desc(self, key, n=11) -> str:
        """AI에게 줄 명단: 야말(Lamine Yamal)"""
        return ", ".join(q["name"] + (f"({q['en']})" if q.get("en") and q["en"] != q["name"] else "")
                         for q in self.lineup_people(key)[:n])

    def lineup_names(self, key) -> list[str]:
        lu = self.lineup(key)
        if not lu:
            return []
        out = [p["name"] for p in lu.get("players", []) if p.get("name")]
        out += [p["name"] for p in lu.get("bench", []) if p.get("name")]
        return out

    def score_text(self) -> str:
        return f"{self.home.label} {self.hs} : {self.as_} {self.away.label}"

    def push_event(self, desc: str):
        pre = f"{self.minute}분 " if self.minute is not None else ""
        self.events.append(pre + desc)
        self.events = self.events[-12:]

    def mark(self, key, player, what):
        team = self.side(key).label
        m = self.marks.setdefault(team, {}).setdefault(player, {"goals": 0, "yellow": 0, "red": False, "off": False, "on": False})
        if what == "goal":
            m["goals"] += 1
        elif what == "yellow":
            m["yellow"] = min(2, m["yellow"] + 1)
            if m["yellow"] >= 2:
                m["red"] = True
        elif what == "red":
            m["red"] = True
        elif what in ("on", "off"):
            m[what] = True

    def is_bench(self, key, name) -> bool:
        lu = self.lineup(key) or {}
        return name in [b.get("name") for b in lu.get("bench", [])]

    def reset_for_new_match(self):
        self.hs = self.as_ = 0
        self.minute = None
        self.events.clear()
        self.marks.clear()


# ---------------------------------------------------------------------------
# 해설 속 장면 감지 (AI 없이 단어로)
# ---------------------------------------------------------------------------
# '골'이라는 말이 있어도 득점이 아닌 경우
NOT_SCORE = re.compile(r"(득점\s*(기회|찬스|없이|실패|을?\s*노|하지\s*못|에\s*실패|권|왕|력|원)|넣었어야|넣지\s*못|못\s*넣|실점\s*위기|"
                       r"골\s*찬스|골\s*기회|옆\s*그물|골\s*결정력|골\s*가뭄|골\s*욕심|골\s*냄새|골\s*[이가]\s*(안|나오지|필요)|골\s*을?\s*노)")
# (장면, 정규식) — 위에서부터 먼저. 큰 장면
DETECT = [
    ("end", re.compile(r"(경기\s*(가|는)?\s*(종료|끝)|종료\s*휘슬|모든\s*경기가\s*끝|full[\s-]?time|final whistle)", re.I)),
    ("half", re.compile(r"(전반\s*(전)?\s*(이|은)?\s*(종료|끝)|하프\s*타임|half[\s-]?time)", re.I)),
    ("kickoff", re.compile(r"(킥\s*오프|경기\s*시작|후반\s*(전)?\s*(이|을)?\s*시작|kick[\s-]?off|we('re| are) underway)", re.I)),
    ("red", re.compile(r"(레드\s*카드|퇴장|경고\s*누적|red card|sent off|sending off)", re.I)),
    # 골이 취소되면 득점이 아니라 판정 장면
    ("var", re.compile(r"(노\s*골(?!적)|골\s*(이|은)?\s*취소|득점\s*(이|은)?\s*(취소|인정되지)|\bvar\b|비디오\s*판독|disallowed|ruled out)", re.I)),
    ("goal", re.compile(r"(득점|골망|골\s*네트|그물을\s*(흔|가르|가릅|갈라)|골문을\s*(흔|가르|가릅|갈라)|골인|넣었습니다|넣습니다|넣어요|"
                        r"넣었어요|골입니다|골이에요|골이죠|골{2,}|(^|\s)골(\s|$|!|~)|\bgoal\b|scores|scored|back of the net)", re.I)),
    ("penalty", re.compile(r"(페널티\s*킥|페널티\s*스팟|페널티를?\s*(선언|얻|줍|내줍|내주|찍)|\bpk\b|penalty\s*(kick|awarded|given|spot))", re.I)),
    ("post", re.compile(r"(골대|골\s*포스트|크로스바|골\s*바|woodwork|crossbar|the post|off the bar)", re.I)),
    ("save", re.compile(r"(선방|막아냅니다|막아냈|막아요|막습니다|막아\s*냅|잡아냅니다|잡아냈|쳐\s*냅니다|쳐냈|펀칭|세이브|\bsaves?\b|great stop|denied)", re.I)),
    ("yellow", re.compile(r"(옐로\s*카드|경고|카드를\s*(꺼|받)|\byellow\b|booked)", re.I)),
    ("offside", re.compile(r"(오프\s*사이드|offside)", re.I)),
    ("miss", re.compile(r"(빗나갑니다|빗나가|벗어납니다|벗어나|놓칩니다|놓쳤|하늘로|옆\s*그물|넘어갑니다|아쉽습니다|넣었어야|\bwide\b|over the bar|misses|missed)", re.I)),
    ("sub", re.compile(r"(교체|substitut|comes on|coming off)", re.I)),
    ("corner", re.compile(r"(코너\s*킥|코너\s*플래그|corner)", re.I)),
    ("freekick", re.compile(r"(프리\s*킥|free[\s-]?kick)", re.I)),
]
# 큰 장면이 아닌 평범한 해설에도 짧게 반응하는 장면들 (위에서부터 먼저)
MOMENTS = [
    ("chance", re.compile(r"(찬스|결정적|위험한|위험합니다|일\s*대\s*일|1\s*대\s*1|노마크|(좋은|완벽한|절호의)\s*(득점\s*)?기회)")),
    ("shot", re.compile(r"(슈팅|슛|때립니다|때렸|때려|중거리|발리|감아\s*찹|강하게\s*찹)")),
    ("cross", re.compile(r"(크로스|헤딩|헤더|머리로)")),
    ("dribble", re.compile(r"(드리블|제칩니다|제쳤|제쳐|돌파|개인기|탈압박)")),
    ("foul", re.compile(r"(파울|반칙|태클|넘어집니다|넘어졌|밀었|잡아당)")),
    ("attack", re.compile(r"(역습|속공|카운터|빠르게\s*올라|전진합니다|쇄도)")),
    ("injury", re.compile(r"(부상|쓰러|고통|치료|들것)")),
    ("pass", re.compile(r"(스루\s*패스|킬\s*패스|침투\s*패스|롱\s*패스|원\s*터치|패스)")),
    ("keeper", re.compile(r"(골키퍼|키퍼)")),
]
EV_DESC = {"goal": "골", "save": "선방", "miss": "슈팅이 빗나감", "post": "골대 맞음", "penalty": "PK 선언", "yellow": "옐로카드",
           "red": "퇴장", "var": "VAR 판정", "offside": "오프사이드", "corner": "코너킥", "freekick": "프리킥", "sub": "교체",
           "kickoff": "킥오프", "half": "전반 종료", "end": "경기 종료", "chance": "찬스", "shot": "슈팅", "cross": "크로스",
           "dribble": "드리블 돌파", "foul": "파울", "attack": "역습", "injury": "부상", "pass": "좋은 패스", "keeper": "키퍼 캐치"}
COOLDOWN = {"goal": 25, "end": 60, "half": 60, "kickoff": 60, "red": 20, "penalty": 20, "var": 12, "post": 8, "save": 6, "miss": 6,
            "yellow": 10, "offside": 8, "corner": 8, "freekick": 8, "sub": 8, "chance": 5, "shot": 5, "cross": 6, "dribble": 6,
            "foul": 6, "attack": 6, "injury": 15, "pass": 8, "keeper": 8}
BIG = {"goal", "end", "red", "penalty"}
HYPE = {"goal": 2.0, "red": 2.5, "penalty": 2.0, "end": 2.0, "kickoff": 1.0, "half": 0.8, "save": 1.2, "miss": 1.0,
        "post": 1.3, "var": 1.0, "yellow": 0.6, "chance": 0.8, "shot": 0.5, "attack": 0.4, "dribble": 0.3, "foul": 0.4}
# 장면마다 반응하는 채팅 수 (최소, 최대)
REACT_N = {"goal": (10, 16), "red": (8, 12), "penalty": (7, 11), "end": (8, 12), "half": (5, 8), "kickoff": (4, 7), "var": (4, 7),
           "post": (4, 7), "save": (3, 6), "miss": (3, 6), "yellow": (2, 4), "sub": (1, 3), "offside": (2, 3), "corner": (1, 3),
           "freekick": (1, 3), "chance": (2, 4), "shot": (1, 3), "injury": (1, 3)}


def detect_event(text: str) -> str | None:
    for ev, rx in DETECT:
        if rx.search(text):
            if ev == "goal" and NOT_SCORE.search(text):
                continue
            return ev
    for ev, rx in MOMENTS:
        if rx.search(text):
            return ev
    return None


R_CHO = ["g", "kk", "n", "d", "tt", "l", "m", "b", "pp", "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h"]
R_JUNG = ["a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe", "yo", "u", "wo", "we", "wi", "yu", "eu", "ui", "i"]
R_JONG = ["", "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "l", "l", "l", "p", "l", "m", "p", "p", "t", "t", "ng", "t", "t",
          "k", "t", "p", "t"]


def romanize(s: str) -> str:
    out = []
    for ch in s:
        c = ord(ch) - 0xAC00
        if 0 <= c < 11172:
            out.append(R_CHO[c // 588] + R_JUNG[(c % 588) // 28] + R_JONG[c % 28])
        else:
            out.append(ch)
    return "".join(out)


@functools.lru_cache(maxsize=8192)
def phon(s: str) -> str:
    """이름 발음 뼈대: 한글은 로마자로 바꾸고, 한국어 외래어 표기에서 헷갈리는 소리를 한데 모음.
    야말 → iamal = Yamal → iamal, 레반도프스키 → lepantopski = Lewandowski → lepantopski"""
    hangul = is_hangul(s)
    t = romanize(s).lower()
    if not hangul:                                   # 영어 이름을 한국어 표기처럼 읽기
        t = re.sub(r"a([^aeiou\s])e\b", r"ei\1", t)    # Kane → kein (케인)
        t = re.sub(r"z\b", "s", t)                      # Perez → peres (페레스)
        t = re.sub(r"er\b", "o", t)                     # Palmer → palmo (팔머)
        t = re.sub(r"(?<=[aeiou])h\b", "", t)          # Salah → sala (살라)
        t = re.sub(r"r(?=[^aeiouy\s])", "", t)          # Rashford → rashfod (자음 앞 r은 소리 안 냄)
        t = t.replace("aa", "a")
    t = re.sub(r"[^a-z]", "", t)
    for a, b in (("ph", "f"), ("ck", "k"), ("sch", "s"), ("sh", "s"), ("th", "t"), ("eu", ""), ("ae", "e"), ("eo", "o"),
                 ("oo", "u"), ("ou", "u"), ("ee", "i"), ("c", "k"), ("q", "k"), ("x", "ks"), ("z", "j"), ("r", "l"),
                 ("v", "b"), ("w", "b"), ("f", "p"), ("y", "i"), ("g", "k"), ("d", "t"), ("b", "p")):
        t = t.replace(a, b)
    return re.sub(r"(.)\1+", r"\1", t)


def is_hangul(s: str) -> bool:
    return bool(re.search(r"[가-힣]", s))


def same_name(a: str, b: str) -> bool:
    """글자(한글/영어)가 달라도 같은 이름인지"""
    pa, pb = phon(a), phon(b)
    if len(pa) < 3 or len(pb) < 3:
        return False
    if pa == pb:
        return True
    if min(len(pa), len(pb)) <= 4:          # 짧은 이름은 흔한 말과 겹치기 쉬워서 완전히 같을 때만 (팔로 ≠ Palmer)
        return False
    from difflib import SequenceMatcher
    return pa[0] == pb[0] and SequenceMatcher(None, pa, pb).ratio() >= 0.82


def _name_tokens(text: str) -> list[str]:
    out = []
    for tok in re.findall(r"[가-힣]+|[A-Za-z][A-Za-z'\-]+", text):
        out.append(split_josa(tok)[0] if is_hangul(tok) else tok)
    return out


def names_in_text(text: str, names: list[str]) -> list[str]:
    low = text.lower()
    hits = []
    toks = None
    for n in names:
        parts = [n] + [p for p in n.split() if len(p) >= 2]
        if any(len(p) >= 2 and p.lower() in low for p in parts):
            hits.append(n)
            continue
        # 한글 ↔ 영어 (해설에 Yamal, 명단엔 야말 / 그 반대)
        if toks is None:
            toks = _name_tokens(text)
        if any(is_hangul(t) != is_hangul(q) and same_name(t, q) for t in toks for q in parts):
            hits.append(n)
    return hits


# ---------------------------------------------------------------------------
# 받아쓰기가 틀린 선수·팀 이름 바로잡기 (자모 단위로 비슷한 이름을 찾음)
# ---------------------------------------------------------------------------
CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNG = ["ㅏ", "ㅐ", "ㅑ", "ㅒ", "ㅓ", "ㅔ", "ㅕ", "ㅖ", "ㅗ", "ㅘ", "ㅙ", "ㅚ", "ㅛ", "ㅜ", "ㅝ", "ㅞ", "ㅟ", "ㅠ", "ㅡ", "ㅢ", "ㅣ"]
JONG = ["", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ", "ㅆ",
        "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]
HANGUL_WORD = re.compile(r"^[가-힣]+$")
# 이름 뒤에 붙는 말 (긴 것부터)
JOSA = sorted(["선수가", "선수는", "선수의", "선수를", "선수", "에게서", "으로부터", "에게", "에서", "으로", "까지", "부터", "처럼", "보다",
               "한테", "께서", "이랑", "은", "는", "이", "가", "을", "를", "의", "에", "와", "과", "도", "로", "만", "랑"], key=len, reverse=True)
# 이름과 비슷해도 고치면 안 되는 흔한 중계 단어
COMMON_WORDS = {"선수", "경기", "골키퍼", "수비", "공격", "슈팅", "패스", "크로스", "코너", "프리킥", "전반", "후반", "주심", "심판", "관중",
                "홈팀", "원정", "득점", "실점", "동점", "역전", "찬스", "기회", "상황", "지금", "오늘", "이번", "다시", "정말", "아주",
                "그리고", "하지만", "그러나", "이건", "이게", "저게", "여기", "거기", "우리", "상대", "왼쪽", "오른쪽", "중앙", "측면"}


def jamo(s: str) -> str:
    out = []
    for ch in s:
        c = ord(ch) - 0xAC00
        if 0 <= c < 11172:
            out.append(CHO[c // 588] + JUNG[(c % 588) // 28] + JONG[c % 28])
        else:
            out.append(ch.lower())
    return "".join(out)


def split_josa(word: str) -> tuple[str, str]:
    for j in JOSA:
        if len(word) > len(j) + 1 and word.endswith(j):
            return word[: -len(j)], word[-len(j):]
    return word, ""


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def fix_names(text: str, vocab: list[str]) -> str:
    """받아쓰기 결과에서 명단에 있는 이름과 거의 같은 단어를 그 이름으로 바꿈 (예: 세스코 → 세슈코).
    자모(ㄱ,ㅏ…)가 짧은 이름은 1개, 긴 이름은 2개까지만 달라야 하고, 첫 소리는 같아야 함."""
    cands = {}
    for v in vocab:
        for part in [v, *v.split()]:
            part = part.strip()
            if 2 <= len(part) <= 8 and HANGUL_WORD.match(part):
                cands[part] = jamo(part)
    if not cands:
        return text
    out = []
    for tok in text.split(" "):
        m = re.match(r"^([가-힣]+)(.*)$", tok)
        if not m:
            out.append(tok)
            continue
        word, rest = m.group(1), m.group(2)
        core, suf = split_josa(word)
        # 두 글자 단어는 흔한 말과 헷갈리기 쉬워서(그런→그린) 세 글자 이상만 고침
        if core in cands or word in cands or core in COMMON_WORDS or len(core) < 3:
            out.append(tok)
            continue
        cj = jamo(core)
        best, bd = None, 99
        for name, nj in cands.items():
            if len(name) != len(core) or nj[:1] != cj[:1]:
                continue
            d = edit_distance(cj, nj)
            if d < bd:
                best, bd = name, d
        allow = 1 if len(core) <= 3 else 2
        out.append(best + suf + rest if best and bd <= allow else tok)
    return " ".join(out)


# ---------------------------------------------------------------------------
# 시청자와 채팅 — AI 없이 chat_lines.py의 문장 + 지금 경기 상황 + 사람마다 다른 말버릇으로 만듦
# ---------------------------------------------------------------------------
LAUGH_RX = re.compile(r"ㅋ{2,}")
JOSA_PAIRS = {"이": ("이", "가"), "가": ("이", "가"), "은": ("은", "는"), "는": ("은", "는"), "을": ("을", "를"), "를": ("을", "를"),
              "과": ("과", "와"), "와": ("과", "와")}
SLOT_JOSA_RX = re.compile(r"\{(\w+)\}(이|가|은|는|을|를|과|와)(?![가-힣])")
SLOT_RX = re.compile(r"\{(\w+)\}")
INTERJ_RX = re.compile(r"^(아|와|오|하|헐|엥|어|캬|에휴|아니|ㄹㅇ|진짜|@)")
END_MARK = ("ㅋ", "!", "?", "~", "ㅠ", "ㄷ", "ㅎ", ".", "ㅡ", "ㅜ")
SHOUT_RX = re.compile(r"[^\d\s]{1,6}[!ㅋㄷ~]*")       # 골!!!!, 와아아아, 가즈아 — 여럿이 따라 쳐도 자연스러운 외침


def josa(word: str, j: str) -> str:
    """앞말 받침에 맞춰 조사 고르기 (리버풀가 → 리버풀이)"""
    last = word.strip()[-1:] if word.strip() else ""
    code = ord(last) - 0xAC00 if last else -1
    if 0 <= code < 11172:
        has_final = code % 28 != 0
    else:
        has_final = last.lower() in "lmnr0136789"   # 영문·숫자는 대충 발음으로
    a, b = JOSA_PAIRS[j]
    return a if has_final else b


def render(tpl: str, d: dict) -> str | None:
    """자리 표시를 채움. 채울 값이 없는 자리가 하나라도 있으면 None (그 문장은 지금 못 씀)."""
    missing = []

    def val(key):
        v = d.get(key)
        if v is None or v == "":
            missing.append(key)
            return ""
        return str(v)

    out = SLOT_JOSA_RX.sub(lambda mm: (lambda w: w + (josa(w, mm.group(2)) if w else ""))(val(mm.group(1))), tpl)
    out = SLOT_RX.sub(lambda mm: val(mm.group(1)), out)
    return None if missing else out


# 사람 성격: 어떤 말을 많이 하고 어떻게 치는지 (비율)
PERSONAS = {"shout": 30, "fan": 20, "calm": 14, "analyst": 12, "joker": 10, "asker": 7, "grumpy": 7}
# 장면별 감정 (관점에 따라): pos = 좋음, neg = 나쁨, surp = 놀람, neu = 보통
SENT = {
    "goal": {"own": "pos", "opp": "neg", "neu": "surp", "unk": "surp"},
    "save": {"own": "pos", "opp": "neg", "neu": "surp", "unk": "surp"},
    "miss": {"own": "neg", "opp": "pos", "neu": "neu", "unk": "neg"},
    "post": {"own": "neg", "opp": "pos", "neu": "surp", "unk": "surp"},
    "chance": {"own": "pos", "opp": "neg", "neu": "surp", "unk": "surp"},
    "penalty": {"own": "pos", "opp": "neg", "neu": "surp", "unk": "surp"},
    "yellow": {"own": "neg", "opp": "pos", "neu": "neu", "unk": "neu"},
    "red": {"own": "neg", "opp": "pos", "neu": "surp", "unk": "surp"},
    "offside": {"own": "neg", "opp": "pos", "neu": "neu", "unk": "neu"},
    "foul": {"own": "neg", "opp": "neg", "neu": "neu", "unk": "neu"},
    "var": {"unk": "surp"}, "injury": {"unk": "neg"}, "sub": {"unk": "neu"}, "keeper": {"unk": "pos"},
}
SENT_DEFAULT = {"own": "pos", "opp": "neg", "neu": "neu", "unk": "neu"}


class Viewer:
    """채팅에 계속 나오는 한 사람. 닉네임·멤버 여부·성격·말버릇이 경기 내내 같음."""

    def __init__(self, name: str, faction: str, kind: str):
        self.name, self.faction, self.kind = name, faction, kind
        self.weight = min(25.0, random.paretovariate(1.3))   # 몇몇 사람이 유독 많이 씀
        self.persona = random.choices(list(PERSONAS), weights=list(PERSONAS.values()))[0]
        self.laugh = random.choice([2, 3, 3, 4, 4, 5, 6, 8])
        self.nospace = random.random() < 0.22              # 띄어쓰기 안 하는 사람
        self.kbatchim = random.random() < 0.3              # "미쳤닼ㅋㅋ"처럼 ㅋ을 받침으로 붙이는 사람
        self.tail_p = random.choice([0.05, 0.15, 0.3, 0.45]) + (0.2 if self.persona in ("shout", "joker") else 0)
        self.prefix_p = 0.0 if self.persona in ("analyst", "calm") else random.choice([0.05, 0.12, 0.2])
        self.fav: str | None = None                        # 좋아하는 선수 (명단을 알면 정함)
        self.last_t = 0.0                                  # 마지막으로 말한 때 (사람은 1~2초에 여러 줄을 못 침)


class Audience:
    """시청자 무리. 세력 비율대로 사람을 만들고, 가끔 새 사람이 들어옴."""

    def __init__(self, match: "Match"):
        self.m = match
        self.people: list[Viewer] = []
        self.rebuild()

    def make_name(self, faction: str) -> str:
        used = {v.name for v in self.people}
        for _ in range(8):
            n = self._make_name(faction)
            if n not in used:
                return n
        return n + str(random.randint(1, 999))

    def _make_name(self, faction: str) -> str:
        side = self.m.side(faction) if faction in ("home", "away") else None
        sk, se = random.choice(CL.SURNAMES)
        gk, ge = random.choice(CL.GIVENS)

        def digits():
            return random.choice(["", "", str(random.randint(1, 99)), str(random.randint(80, 99)), str(random.randint(1990, 2008)),
                                  "%02d%02d" % (random.randint(1, 12), random.randint(1, 28))])
        if side is not None and side.name and random.random() < 0.14:      # 응원 팀이 드러나는 이름
            t = lookup_team(side.name)
            tags = CL.FAN_TAGS.get(t["en"]) if t else None
            if tags and random.random() < 0.45:
                tag = random.choice(tags)
                return random.choice([tag + digits(), f"@{tag}_{ge}", f"{ge}_{tag}", tag.upper() + digits()])
            # "{s}는 못참지"의 조사는 팀 이름 받침에 맞게 (토트넘은, 맨유는)
            return render(random.choice(CL.FAN_KO), {"s": side.short.replace(" ", ""), "n": str(random.randint(3, 25)),
                                                     "d": str(random.randint(1, 99))})
        r = random.random()
        if r < 0.20:                                                 # 실명
            return sk + gk
        if r < 0.30:                                                 # 영문 이름
            return random.choice([f"{ge.capitalize()} {se.capitalize()}", f"{se.capitalize()} {ge.capitalize()}", f"{ge} {se}"])
        if r < 0.55:                                                 # @핸들
            return "@" + random.choice([
                f"{ge}{digits()}", f"{se}{ge}{digits()}", f"{ge[0]}{ge[-1]}{se}{random.randint(1, 99)}", f"{ge}_{se}",
                f"{ge}.{se}", f"{ge}__", f"{random.choice(CL.ENG_WORDS)}_{ge}", f"{ge}{random.choice(CL.ENG_WORDS)}",
                "user-" + "".join(random.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(10))])
        if r < 0.80:                                                 # 일상 닉네임
            return random.choice(CL.CASUAL) + random.choice(CL.CASUAL_TAIL)
        if r < 0.90:                                                 # 채널 이름
            return random.choice(CL.CHANNEL).format(w=random.choice(CL.CASUAL[:20] + [gk]), g=gk)
        return random.choice(CL.ENG_WORDS) + random.choice(["", "", "_", "."]) + random.choice(CL.ENG_WORDS + [ge]) + digits()

    def new_person(self, faction: str, kind: str | None = None) -> Viewer:
        if kind is None:
            kind = "member" if random.random() < 0.1 else "normal"
        v = Viewer(self.make_name(faction), faction, kind)
        self.people.append(v)
        if len(self.people) > 400:
            self.people.pop(0)
        return v

    def rebuild(self):
        self.people = []
        sp = self.m.split()
        for i in range(140):
            r = random.random() * 100
            f = "home" if r < sp["home"] else ("away" if r < sp["home"] + sp["away"] else "neutral")
            self.new_person(f, "mod" if i < 2 else None)

    def pick(self, faction: str | None, exclude: str | None = None) -> Viewer:
        ex = (exclude or "").lstrip("@")
        if random.random() < 0.08 or not self.people:
            return self.new_person(faction or "neutral")
        pool = [v for v in self.people if (faction is None or v.faction == faction) and (not ex or v.name.lstrip("@") != ex)]
        if not pool:
            return self.new_person(faction or "neutral")
        return random.choices(pool, weights=[v.weight for v in pool])[0]

    def find(self, name: str) -> Viewer | None:
        return next((v for v in self.people if v.name == name), None)


class ChatEngine:
    """채팅 만들기. 장면·경기 상황에 맞는 문장을 고르고, 사람마다 말버릇을 입히고, 서로 대답하게 함."""

    def __init__(self, match: Match, cfg: dict):
        self.m, self.cfg = match, cfg
        self.crowd = Audience(match)
        self.recent_tpl: list[str] = []     # 최근에 쓴 문장 틀 (같은 말 반복 피하기)
        self.recent_txt: list[str] = []
        self.scene: dict | None = None      # 마지막 장면 {"ev", "side", "player", "t", "desc"}
        self.scorer: str | None = None      # 마지막 득점자

    # ----- 누가 말하나 -----
    def pick_faction(self) -> str:
        sp = self.m.split()
        r = random.random() * 100
        if r < sp["home"]:
            return "home"
        if r < sp["home"] + sp["away"]:
            return "away"
        return "neutral"

    def speaker(self, faction: str | None = None, exclude: str | None = None, used: set | None = None) -> Viewer:
        """말할 사람. used = 이번 반응에서 이미 말한 사람 (한 사람이 같은 순간에 여러 번 치지 않게)"""
        now = time.time()
        for _ in range(5):
            v = self.crowd.pick(faction or self.pick_faction(), exclude)
            if (used is None or v.name not in used) and now - v.last_t > 3.0:
                break
        v.last_t = now
        if used is not None:
            used.add(v.name)
        return v

    # ----- 문장 고르기 -----
    def slots(self, v: Viewer | None, key: str | None, player: str | None = None, **extra) -> dict:
        """문장 자리에 넣을 값. key = 문장 속 '우리 팀'"""
        m = self.m
        if key not in ("home", "away"):
            key = random.choice(["home", "away"])
        other = m.other(key)
        side, oside = m.side(key), m.side(other)
        players = m.lineup_names(key)[:11]
        kor = m.korean_names(key)
        if v is not None and v.faction == key and players and v.fav not in players + kor:
            v.fav = random.choice(kor * 3 + players) if kor else random.choice(players)
        lead = trail = ""
        if m.hs != m.as_ and m.home.name and m.away.name:
            lead, trail = (m.home.short, m.away.short) if m.hs > m.as_ else (m.away.short, m.home.short)
        lu = m.lineup(key) or {}
        d = {"t": side.short if side.name else "", "o": oside.short if oside.name else "",
             "p": player if player is not None else (random.choice(players) if players else ""),
             "k": random.choice(kor) if kor else "", "gk": players[0] if players else "",
             "fav": v.fav if v is not None and v.faction == key and v.fav else "",
             "score": f"{m.hs}:{m.as_}", "hs": str(m.hs), "as": str(m.as_),
             "home": m.home.short if m.home.name else "", "away": m.away.short if m.away.name else "",
             "min": str(m.minute) if m.minute is not None else "", "lead": lead, "trail": trail,
             "host": self.cfg.get("streamer_name") or "방장", "form": lu.get("formation", "") if lu.get("players") else "",
             "ev": self.scene["desc"] if self.scene and time.time() - self.scene["t"] < 90 else "",
             "n": ""}
        d.update(extra)
        return d

    def choose(self, tpls: list[str], d: dict, v: Viewer | None = None, strict: bool = False) -> str | None:
        """채울 수 있는 문장 중에서, 최근에 안 쓴 것 위주로, 그 사람 성격에 맞는 길이로 하나.
        strict = 최근에 안 쓴 문장이 없으면 None (같은 말 되풀이보다 안 하는 게 나은 곳)"""
        cands = []
        for tp in tpls:
            txt = render(tp, d)
            if txt:
                cands.append((tp, txt))
        if not cands:
            return None
        fresh = [c for c in cands if c[0] not in self.recent_tpl and c[1] not in self.recent_txt]
        if not fresh and strict:
            return None
        if not fresh:
            last = {tp: i for i, tp in enumerate(self.recent_tpl)}
            fresh = sorted(cands, key=lambda c: last.get(c[0], -1))[:max(1, len(cands) // 3)]
        weights = []
        for _tp, txt in fresh:
            w = 1.0
            if v is not None:
                if v.persona == "shout":
                    w = 3.0 if len(txt) <= 8 else 0.7
                elif v.persona == "analyst":
                    w = 3.0 if len(txt) >= 9 else 0.6
                elif v.persona == "fan" and v.fav and v.fav in txt:
                    w = 4.0
            weights.append(w)
        tp, txt = random.choices(fresh, weights=weights)[0]
        self.recent_tpl = (self.recent_tpl + [tp])[-150:]
        return txt

    def mode_line(self, v: Viewer, what: str, d: dict, scale: float) -> str | None:
        """채팅 분위기(메뉴)를 골랐으면 세기에 따라 그 분위기 문장으로"""
        mode = self.cfg.get("chat_mode", "default")
        lines = CL.MODE.get(mode, {}).get(what)
        if not lines:
            return None
        try:
            n = max(0, min(10, int(self.cfg.get("chat_intensity", 5))))
        except (TypeError, ValueError):
            n = 5
        if random.random() >= n / 10 * scale:
            return None
        return self.choose(lines, d, v)

    # ----- 말버릇 입히기 -----
    def style(self, v: Viewer, text: str, sent: str = "neu") -> str:
        t = text
        is_reply = t.startswith("@")
        # 앞말(와, 아 …)이나 끝말(ㅋㅋ, ㅠㅠ …) 중 하나만 — 둘 다 붙이면 꾸민 티가 남
        if sent in CL.PREFIX and random.random() < v.prefix_p and not INTERJ_RX.match(t) and not t.startswith("ㅋ") and len(t) >= 3:
            t = random.choice(CL.PREFIX[sent]) + t
        elif sent in CL.TAIL and random.random() < v.tail_p and not t.endswith(END_MARK):
            t += random.choice(CL.TAIL[sent])
        t = LAUGH_RX.sub(lambda _m: "ㅋ" * max(2, v.laugh + random.randint(-1, 2)), t)
        # "미쳤다 ㅋㅋㅋ" → "미쳤닼ㅋㅋ" (받침 없는 마지막 글자에 ㅋ을 붙여 치는 버릇)
        mm = re.search(r"([가-힣]) ?(ㅋ{2,})$", t)
        if mm and v.kbatchim and random.random() < 0.7:
            code = ord(mm.group(1)) - 0xAC00
            if code % 28 == 0:
                t = t[:mm.start()] + chr(0xAC00 + code + 24) + mm.group(2)[1:]
        if v.nospace and len(t) <= 12 and random.random() < 0.6:
            if is_reply and " " in t:
                head, rest = t.split(" ", 1)
                t = head + " " + rest.replace(" ", "")
            else:
                t = t.replace(" ", "")
        if t.endswith("?") and not t.endswith("??") and random.random() < 0.2:
            t += "?"
        elif t.endswith("!") and random.random() < (0.35 if self.cfg.get("chat_mode") == "hype" else 0.1):
            t += "!" * random.randint(1, 3)
        return t

    def say(self, v: Viewer, text: str, sent: str = "neu", **tags) -> dict:
        t = self.style(v, text, sent)
        self.recent_txt = (self.recent_txt + [text])[-80:]
        return {"name": v.name, "text": t, "kind": v.kind, "amount": 0, "side": v.faction, **tags}

    # ----- 장면 반응 -----
    def react(self, ev: str, actor: str | None, player: str | None = None, n: int = 6, variant: str | None = None) -> list[dict]:
        """장면에 여러 사람이 반응. actor = 장면의 주인공 팀 (골 넣은 팀, 선방한 팀, 파울한 팀 …), 모르면 None.
        variant = 같은 장면의 다른 문장 묶음 (교체: sub_in 들어오는 선수 / sub_out 나가는 선수)"""
        pools = CL.REACT.get(variant or ev)
        if not pools:
            return []
        out, used = [], set()
        for _ in range(n):
            v = self.speaker(used=used)
            f = v.faction
            if ev == "kickoff":                     # 킥오프는 누구에게나 '우리 팀' 시작
                persp = "own" if f in ("home", "away") else "neu"
                key = f if f in ("home", "away") else None
            elif actor in ("home", "away") and ("own" in pools or "neu" in pools):
                persp = "neu" if f == "neutral" else ("own" if f == actor else "opp")
                key = f if f in ("home", "away") else actor
            else:
                persp = "unk"
                key = f if f in ("home", "away") else None
            sent = SENT.get(ev, SENT_DEFAULT).get(persp, SENT_DEFAULT.get(persp, "neu"))
            # 장면 선수를 모르면 선수 이름이 들어가는 문장은 안 씀 (엉뚱한 선수가 골 넣은 것처럼 되지 않게)
            d = self.slots(v, key, player or "")
            text = None
            if sent in ("pos", "neg"):
                text = self.mode_line(v, sent, d, 0.7)
            if not text:
                tpls = list(pools.get(persp) or pools.get("unk") or pools.get("neu") or [])
                if persp != "unk" and pools.get("unk") and random.random() < 0.25:
                    tpls = list(pools["unk"])      # 누구나 할 법한 짧은 반응도 섞음
                text = self.choose(tpls, d, v)
            if text:
                out.append(self.say(v, text, sent, chant=ev == "goal" and bool(SHOUT_RX.fullmatch(text))))
        return out

    def chant(self, side: str, player: str | None, n: int) -> list[dict]:
        """골 직후 도배: 한 사람이 치면 여럿이 비슷하게 따라 침"""
        out, used = [], set()
        base = None
        for _ in range(n):
            v = self.speaker(side if random.random() < 0.8 else None, used=used)
            if base is None or random.random() < 0.35:
                base = self.choose(CL.CHANT, self.slots(v, side, player or ""))
            if base:
                out.append(self.say(v, base, "pos", chant=True))
        return out

    def scorer_lines(self, side: str, name: str, n: int) -> list[dict]:
        out, used = [], set()
        for _ in range(n):
            v = self.speaker(used=used)
            persp = "neu" if v.faction == "neutral" else ("own" if v.faction == side else "opp")
            key = v.faction if v.faction in ("home", "away") else side
            text = self.choose(CL.SCORER[persp], self.slots(v, key, name, n=name), v)
            if text:
                out.append(self.say(v, text, {"own": "pos", "opp": "neg"}.get(persp, "surp")))
        return out

    def phase_lines(self, which: str, n: int) -> list[dict]:
        """전반 종료(half) / 경기 종료(end): 이 사람이 응원하는 팀이 이기고 있는지로"""
        m = self.m
        pools = CL.HALF if which == "half" else CL.END
        out, used = [], set()
        for _ in range(n):
            v = self.speaker(used=used)
            f = v.faction
            if f in ("home", "away"):
                diff = (m.hs - m.as_) * (1 if f == "home" else -1)
                cat = ("lead" if diff > 0 else "trail" if diff < 0 else "draw") if which == "half" else \
                      ("win" if diff > 0 else "lose" if diff < 0 else "draw")
                key = f
            else:
                cat, key = "neu", None
            text = self.choose(pools[cat], self.slots(v, key), v)
            if text:
                out.append(self.say(v, text, {"lead": "pos", "win": "pos", "trail": "neg", "lose": "neg"}.get(cat, "neu")))
        return out

    def echo(self, text: str) -> list[dict]:
        """큰 장면이 아닌 해설에 선수 이름이 나오면 그 선수 이야기"""
        m = self.m
        out = []
        for key in ("home", "away"):
            kor = m.korean_names(key)
            if names_in_text(text, kor) and random.random() < 0.85:
                for _ in range(random.randint(1, 3)):
                    v = self.speaker(key if random.random() < 0.7 else None)
                    t = self.choose(CL.ECHO["kor"], self.slots(v, key), v)
                    if t:
                        out.append(self.say(v, t, "pos"))
            for p in [p for p in names_in_text(text, m.lineup_names(key)) if p not in kor][:2]:
                if random.random() < 0.6:
                    v = self.speaker()
                    persp = "neu" if v.faction == "neutral" else ("own" if v.faction == key else "opp")
                    t = self.choose(CL.ECHO[persp], self.slots(v, v.faction if v.faction in ("home", "away") else key, p), v)
                    if t:
                        out.append(self.say(v, t, "pos" if persp == "own" else "neu"))
        return out

    # ----- 평소 잡담 -----
    def idle(self, phase: str) -> dict:
        m = self.m
        v = self.speaker()
        f = v.faction
        key = f if f in ("home", "away") else None
        d = self.slots(v, key)
        r = random.random()
        # 질문 (다른 사람이 경기 상황으로 대답함)
        if r < (0.16 if v.persona == "asker" else 0.035):
            q, kind = random.choice(CL.QUESTIONS)
            t = render(q, d)
            if t and t not in self.recent_txt[-40:]:
                return self.say(v, t, "neu", q=kind, qk=key)
        # 방금 장면 이야기가 한동안 이어짐
        sc = self.scene
        if sc and time.time() - sc["t"] < 40 and sc["ev"] in CL.LINGER and random.random() < 0.15:
            t = self.choose(CL.LINGER[sc["ev"]], self.slots(v, key, sc.get("player") or None), v, strict=True)
            if t:
                return self.say(v, t, "neu", op=True)
        if phase in ("half", "ended"):
            pools = CL.HALF if phase == "half" else CL.END
            cat = "neu"
            if f in ("home", "away") and random.random() < 0.6:
                diff = (m.hs - m.as_) * (1 if f == "home" else -1)
                cat = ("lead" if diff > 0 else "trail" if diff < 0 else "draw") if phase == "half" else \
                      ("win" if diff > 0 else "lose" if diff < 0 else "draw")
            t = self.choose(pools[cat] + CL.IDLE["chat"], d, v)
            if t:
                return self.say(v, t, "neu")
        # 분위기 (메뉴)
        t = self.mode_line(v, "idle", d, 0.6)
        if t:
            return self.say(v, t, "neu", op=True)
        # 경기 상황에 맞는 잡담
        late = (m.minute or 0) >= 80
        gap = abs(m.hs - m.as_)
        cats: list[tuple[str, float]] = [("chat", 0.9)]
        if f in ("home", "away"):
            lead = (m.hs - m.as_) * (1 if f == "home" else -1)
            cats += [("fan", 3.0), ("kor", 2.0 if m.has_korean(f) else 0)]
            if gap >= 3:
                cats.append(("blowout_win" if lead > 0 else "blowout_lose", 2.0))
            elif lead > 0:
                cats.append(("lead", 1.6))
            elif lead < 0:
                cats.append(("trail", 1.8))
            else:
                cats.append(("draw", 0.8))
            if late:
                cats.append(("late_fan", 2.2))
        else:
            cats += [("neu", 3.0)]
            if gap >= 3:
                cats.append(("blowout_neu", 1.5))
            if late:
                cats.append(("late_neu", 1.8))
        if m.hs == m.as_ == 0 and (m.minute or 0) >= 25:
            cats.append(("zero", 0.8))
        if v.persona == "grumpy" and self.cfg.get("chat_mode", "default") == "default" and random.random() < 0.3:
            t = self.choose(CL.MODE["toxic"]["idle"], d, v)       # 투덜이는 가끔 까칠한 말
            if t:
                return self.say(v, t, "neg", op=True)
        cats = [(c, w) for c, w in cats if w > 0]
        for _ in range(3):
            cat = random.choices([c for c, _ in cats], weights=[w for _, w in cats])[0]
            t = self.choose(CL.IDLE[cat], d, v)
            if t:
                return self.say(v, t, "neu", op=cat not in ("chat",))
        return self.say(v, random.choice(["ㅋㅋㅋㅋ", "ㅎㅇ", "ㄷㄷ", "오"]), "neu")

    # ----- 서로 대답하기 -----
    def followups(self, msg: dict, hype: float = 0.0) -> list[tuple[float, dict]]:
        """다른 사람이 대답하거나 맞장구침 → [(몇 초 뒤, 메시지)]"""
        if msg.get("kind") not in ("normal", "member", "mod"):
            return []
        out = []
        name = msg.get("name", "").lstrip("@")
        # 질문 → 경기 상황으로 대답
        if msg.get("q") and random.random() < 0.8:
            a = self.answer(msg["q"], msg.get("name"), msg.get("qk"))
            if a:
                out.append((random.uniform(2.0, 6.0), a))
            if a and random.random() < 0.3:
                b = self.answer(msg["q"], msg.get("name"), msg.get("qk"))
                if b:
                    out.append((random.uniform(3.0, 8.0), b))
            return out
        text = msg.get("text", "")
        # 골 뒤 외침은 분위기가 달아올랐을 때 여럿이 따라 침 (따라 친 채팅을 또 따라 치지는 않음)
        if msg.get("chant") and not msg.get("copy") and hype > 1.5 and random.random() < 0.3:
            for _ in range(random.randint(1, 2)):
                v = self.speaker(msg.get("side"), exclude=msg.get("name"))
                out.append((random.uniform(0.3, 2.5), self.say(v, text, "pos", copy=True)))
            return out
        # 의견에 맞장구·반박 (가끔 팬끼리 신경전)
        if msg.get("op") and len(text) >= 5 and random.random() < 0.12:
            side = msg.get("side")
            v = self.speaker(exclude=msg.get("name"))
            if side in ("home", "away") and v.faction in ("home", "away") and v.faction != side:
                pool = CL.RIVAL if random.random() < 0.6 else CL.DISAGREE
                key, sent = v.faction, "neg"
            else:
                pool = CL.AGREE if random.random() < 0.75 else CL.DISAGREE
                key, sent = (v.faction if v.faction in ("home", "away") else side), "neu"
            t = self.choose(pool, self.slots(v, key, n=name), v)
            if t:
                out.append((random.uniform(1.5, 5.0), self.say(v, t, sent)))
        return out

    def answer(self, kind: str, asker: str | None, qkey: str | None = None) -> dict | None:
        m = self.m
        v = self.speaker(exclude=asker)
        key = qkey if kind == "form" and qkey else (v.faction if v.faction in ("home", "away") else None)
        if kind == "lead" and m.hs == m.as_:
            kind = "lead_draw"
        if kind == "kor" and not (m.has_korean("home") or m.has_korean("away")):
            kind = "kor_none"
        if kind == "kor":
            key = "home" if m.has_korean("home") else "away"
        if kind == "scorer" and not self.scorer:
            return None
        d = self.slots(v, key, n=self.scorer or "")
        t = self.choose(CL.ANSWERS.get(kind, []), d, v)
        return self.say(v, t, "neu") if t else None

    # ----- 방장(입력창) 채팅에 반응 -----
    HOST_INTENTS = [
        ("predict", re.compile(r"(누가\s*이길|예측|예상|몇\s*대\s*몇\s*(으로|날|될)|이길\s*(까|것)|스코어\s*예상)")),
        ("score", re.compile(r"(몇\s*대\s*몇|스코어\s*(몇|뭐))")),
        ("min", re.compile(r"몇\s*분")),
        ("kor", re.compile(r"한국\s*선수")),
        ("greet", re.compile(r"(안녕|ㅎㅇ|하이|반가|어서\s*와|hello|\bhi\b)", re.I)),
        ("thanks", re.compile(r"(고마|감사|ㄳ|ㄱㅅ|땡큐)")),
        ("cheer", re.compile(r"(가자|가즈아|화이팅|파이팅|이기자|ㄱㄱ|힘내)")),
        ("sad", re.compile(r"(ㅠ|ㅜ|아쉽|졌|망했|슬프)")),
        ("laugh", re.compile(r"^[ㅋㅎ\s!?]+$|ㅋㅋㅋ")),
        ("chat", re.compile(r"(채팅|다들|여러분|시청자)")),
        ("question", re.compile(r"(\?|뭐|왜|어때|어떻|누구|언제|맞지|맞아|할까|일까)")),
    ]

    def host_replies(self, text: str, mention: str | None) -> list[dict]:
        intent = next((k for k, rx in self.HOST_INTENTS if rx.search(text)), "other")
        out = []
        if mention:                                          # 방장이 부른 사람이 먼저 대답
            v = self.crowd.find(mention)
            if v:
                t = self.choose(CL.HOST["called"], self.slots(v, v.faction if v.faction in ("home", "away") else None), v)
                if t:
                    out.append(self.say(v, t, "neu"))
        n = random.randint(3, 6)
        used = {mention} if mention else set()
        for _ in range(n):
            v = self.speaker(used=used)
            key = v.faction if v.faction in ("home", "away") else None
            if intent in ("score", "min", "kor"):
                a = self.answer(intent, None)
                if a:
                    out.append(a)
                continue
            pool = CL.HOST.get(intent, CL.HOST["other"])
            if intent == "question" and random.random() < 0.3:
                pool = CL.HOST["other"]
            t = self.choose(pool, self.slots(v, key), v)
            if t:
                out.append(self.say(v, t, {"laugh": "pos", "cheer": "pos", "sad": "neg"}.get(intent, "neu")))
        return out

    # ----- 후원·새 멤버 -----
    def super_chat(self, kind: str, side: str | None = None) -> dict | None:
        f = side or self.pick_faction()
        v = self.speaker(f if f in ("home", "away", "neutral") else None)
        key = v.faction if v.faction in ("home", "away") else (side if side in ("home", "away") else None)
        text = self.choose(CL.SUPER[kind], self.slots(v, key), v)
        if not text:
            return None
        amounts = {"goal": [2000, 2000, 5000, 5000, 10000, 20000, 50000], "end": [2000, 5000, 10000]}.get(
            kind, [1000, 1000, 2000, 2000, 3000, 5000, 5000, 10000, 20000])
        return {"name": v.name, "text": text, "kind": "super", "amount": random.choice(amounts), "side": v.faction}

    def new_member(self, faction: str | None = None) -> dict:
        v = self.speaker(faction)
        for _ in range(4):
            if v.kind == "normal":
                break
            v = self.speaker(faction)
        if v.kind == "mod":
            v = self.crowd.new_person(faction or "neutral", "normal")
        v.kind = "member"          # 이 사람은 이제부터 멤버로 보임
        return {"name": v.name, "text": "", "kind": "newmember", "amount": 0, "side": v.faction}


# 채팅 분위기 (메뉴 이름). 문장은 chat_lines.MODE
CHAT_MODES = {"default": "기본", "hype": "응원 폭발", "toxic": "까칠", "wholesome": "훈훈", "backseat": "훈수", "clueless": "엉뚱"}


# ---------------------------------------------------------------------------
# 게임 소리 받아쓰기 (WASAPI 루프백 + faster-whisper)
# ---------------------------------------------------------------------------
HALLUCINATION = ["시청해 주셔서", "감사합니다 감사합니다", "구독", "좋아요", "알림 설정", "다음 시간에", "오늘 영상", "영상이었습니다",
                 "제작 지원", "후원", "MBC", "KBS", "SBS", "JTBC", "기자입니다", "뉴스입니다", "이 영상은", "시청해주셔서", "구독과 좋아요", "구독 좋아요", "좋아요와 구독", "자막 제공", "자막by", "자막 by",
                 "mbc 뉴스", "kbs 뉴스", "sbs 뉴스", "다음 영상에서", "영상 끝까지", "한글자막", "배달의민족", "ytn"]
ONLY_FILLER = re.compile(r"^(감사합니다|고맙습니다|네|아|음|어|예|네네|안녕하세요)[.!?~ ]*$")
SR = 16000


def clean_transcript(text: str, prompt: str = "") -> str:
    t = re.sub(r"\s+", " ", text).strip()
    # "골 골 골 골 골" 처럼 같은 말이 끝없이 반복되면 두 번까지만
    t = re.sub(r"(\S+(?:\s\S+){0,3}?)(?:\s\1){2,}", r"\1 \1", t)
    low = t.lower().replace(" ", "")
    if len(t) < 2 or ONLY_FILLER.match(t) or any(h.replace(" ", "") in low for h in HALLUCINATION):
        return ""
    # 힌트로 준 문장을 그대로 따라 쓴 것은 버림
    if len(low) >= 6 and low in prompt.lower().replace(" ", ""):
        return ""
    return t


def to_16k(a, rate: int):
    import numpy as np
    if rate == SR:
        return a
    if rate % SR == 0:                 # 48000 → 16000: 평균 내서 줄이면 잡음이 덜 섞임
        f = rate // SR
        n = len(a) // f * f
        return a[:n].reshape(-1, f).mean(axis=1).astype(np.float32)
    n = int(len(a) * SR / rate)
    return np.interp(np.linspace(0, len(a), n, endpoint=False), np.arange(len(a)), a).astype(np.float32)


LANG_NAMES = {"ko": "한국어", "en": "영어", "es": "스페인어", "fr": "프랑스어", "de": "독일어", "it": "이탈리아어",
              "pt": "포르투갈어", "ja": "일본어", "zh": "중국어", "nl": "네덜란드어", "ar": "아랍어", "pl": "폴란드어", "tr": "튀르키예어"}
CUDA_ERR = re.compile(r"(cublas|cudnn|cuda|cudart|nvrtc|curand)", re.I)


def add_cuda_dll_dirs():
    """pip로 설치한 NVIDIA 라이브러리(nvidia-cublas-cu12 등)를 윈도우가 찾을 수 있게 경로에 넣음"""
    if not IS_WIN:
        return
    import site
    roots = list(site.getsitepackages()) + [site.getusersitepackages()]
    for root in roots:
        base = Path(root) / "nvidia"
        if not base.is_dir():
            continue
        for b in base.glob("*/bin"):
            try:
                os.add_dll_directory(str(b))
            except Exception:
                pass
            os.environ["PATH"] = str(b) + os.pathsep + os.environ.get("PATH", "")


class AudioSTT(threading.Thread):
    """게임 소리에서 해설자 말소리만 골라(VAD) 문장 단위로 끊어서 받아씀.
    예전처럼 5초씩 자르면 단어가 중간에 잘려 인식이 망가지므로, 말이 멈춘 곳에서 자름."""
    _model = None
    _size = ""
    _device = "cpu"

    MAX_SEG = 5.0        # 쉬지 않고 이어지는 말은 이 길이에서 끊음 (초) — 짧을수록 빨리 뜸
    END_SIL = 0.3        # 이만큼 조용하면 한 문장이 끝난 것으로 봄 (초)
    MAX_LAG = 4.0        # 받아쓰기가 이만큼 밀리면 밀린 소리는 버리고 지금 소리부터 (실시간 유지)
    PREVIEW_EVERY = 0.7  # 말하는 중 미리보기 자막을 새로 만드는 간격 (초)

    def __init__(self, cfg, bus: queue.Queue, prompt_fn):
        super().__init__(daemon=True, name="stt")
        self.cfg, self.bus, self.prompt_fn = cfg, bus, prompt_fn
        self.stop_flag = threading.Event()
        self.chunks: list[bytes] = []
        self.lock = threading.Lock()
        self.no_hotwords = False
        lang = str(self.cfg.get("commentary_language", "ko") or "ko")
        self.lang = None if lang == "auto" else lang     # 정해진 해설 언어 (auto면 몇 번 듣고 정함)
        self.lang_votes: list[str] = []

    @classmethod
    def load_model(cls, cfg, force_cpu: bool = False):
        if cls._model is not None and not force_cpu:
            return cls._model
        add_cuda_dll_dirs()
        import numpy as np
        from faster_whisper import WhisperModel
        size = cfg.get("whisper_model", "auto")
        use_cuda = False
        if not force_cpu and cfg.get("whisper_device", "auto") != "cpu":
            try:
                import ctranslate2
                use_cuda = ctranslate2.get_cuda_device_count() > 0
            except Exception:
                pass
        threads = min(6, max(2, (os.cpu_count() or 4) // 2))
        err = None
        for device in (["cuda", "cpu"] if use_cuda else ["cpu"]):
            compute = "int8_float16" if device == "cuda" else "int8"   # 게임과 그래픽 메모리를 나눠 쓰니 가볍게
            if size == "auto":
                # 한국어는 작은 모델에서 틀리는 게 많아서 가능한 한 큰 모델부터 시도
                cands = ["large-v3-turbo", "small"] if device == "cuda" else ["small", "base"]
            else:
                cands = [size]
            for s in cands:
                try:
                    log.info("loading whisper %s on %s", s, device)
                    model = WhisperModel(s, device=device, compute_type=compute, cpu_threads=threads)
                    if device == "cuda":
                        # 그래픽카드 라이브러리(cuBLAS·cuDNN)는 실제로 돌릴 때 불러오므로 한 번 시험해 봄
                        segs, _ = model.transcribe(np.zeros(SR, dtype=np.float32), language="ko", beam_size=1)
                        list(segs)
                    cls._model, cls._size, cls._device = model, s, device
                    return model
                except Exception as e:
                    log.warning("whisper %s on %s failed: %s", s, device, e)
                    err = e
                    if device == "cuda" and CUDA_ERR.search(str(e)):
                        break          # 그래픽카드 라이브러리가 없으면 다른 크기도 안 되니 바로 CPU로
        raise err or RuntimeError("no whisper model")

    def _cb(self, in_data, frame_count, time_info, status):
        with self.lock:
            self.chunks.append(in_data)
        return (None, self._continue)

    def _vad(self):
        """말소리 구간 찾기 (faster-whisper 안의 Silero VAD). 없으면 None."""
        try:
            from faster_whisper.vad import VadOptions, get_speech_timestamps
            opts = VadOptions(threshold=0.6, min_speech_duration_ms=300, min_silence_duration_ms=300, speech_pad_ms=150)
            import numpy as np
            get_speech_timestamps(np.zeros(SR, dtype=np.float32), opts)   # 한 번 돌려 봄
            return lambda a: get_speech_timestamps(a, opts)
        except Exception as e:
            log.warning("vad unavailable, fixed chunks: %s", e)
            return None

    def transcribe(self, piece, vad_done: bool):
        import numpy as np
        model = self.model
        peak = float(np.max(np.abs(piece))) if len(piece) else 0.0
        rms = float(np.sqrt(np.mean(piece * piece))) if len(piece) else 0.0
        if peak < 0.01 or rms < 0.004:
            return
        piece = (piece * min(3.0, 0.9 / peak)).astype(np.float32)    # 작은 소리만 조금 키움 (너무 키우면 관중 소리를 말로 착각)
        lang = self.lang
        # 힌트(앞 문맥·핫워드)는 한국어 해설일 때만. 다른 언어에 한국어 힌트를 주면 엉뚱하게 번역하듯 받아씀
        prompt, hot = self.prompt_fn() if lang == "ko" else ("", "")
        beam = 5 if self._device == "cuda" else 1      # CPU는 빠르게(한 번에 하나만 추측)
        kw = dict(language=lang, beam_size=beam, vad_filter=not vad_done, condition_on_previous_text=False,
                  initial_prompt=prompt or None, temperature=0.0, no_speech_threshold=0.5, log_prob_threshold=-0.8,
                  compression_ratio_threshold=2.2, without_timestamps=True)
        if hot and not self.no_hotwords:
            kw["hotwords"] = hot
        t0 = time.time()
        try:
            try:
                segs, info = model.transcribe(piece, **kw)
                segs = list(segs)
            except TypeError:                   # 오래된 faster-whisper에는 hotwords가 없음
                self.no_hotwords = True
                kw.pop("hotwords", None)
                segs, info = model.transcribe(piece, **kw)
                segs = list(segs)
        except Exception as e:
            if self._device == "cuda" and CUDA_ERR.search(str(e)):
                # 그래픽카드로 못 돌리면 CPU로 바꿔서 계속
                log.warning("cuda transcribe failed, switching to cpu: %s", e)
                self.bus.put(("stt_status", ("loading", "그래픽카드를 쓸 수 없어 CPU로 바꾸는 중…")))
                self.model = self.load_model(self.cfg, force_cpu=True)
                self.bus.put(("stt_status", ("on", "해설 듣는 중 (CPU)")))
                return
            raise
        if lang is None:
            self.vote_language(info)
        parts = []
        for s in segs:
            if s.avg_logprob < -0.8:            # 자신 없는 받아쓰기는 버림
                continue
            if s.no_speech_prob > 0.45:         # 말소리가 아닐 가능성이 크면 버림
                continue
            if getattr(s, "compression_ratio", 1.0) > 2.4:
                continue
            parts.append(s.text.strip())
        text = clean_transcript(" ".join(parts), prompt)
        took = time.time() - t0
        if took > len(piece) / SR:
            log.warning("stt slower than real time: %.1fs audio took %.1fs", len(piece) / SR, took)
        if text:
            log.info("stt[%s] %.1fs/%.1fs: %s", lang or getattr(info, "language", "?"), took, len(piece) / SR, text)
            self.bus.put(("text", text))

    def preview_on(self) -> bool:
        """미리보기 자막: 자막을 보여 줄 때만. auto면 그래픽카드로 받아쓸 때만 (CPU는 최종 자막이 늦어지므로)."""
        c = self.cfg
        if not (c.get("show_captions", True) or c.get("show_transcript", False)):
            return False
        mode = c.get("caption_preview", "auto")
        return bool(mode) and (mode is True or mode == "on" or (mode == "auto" and self._device == "cuda"))

    def preview(self, piece):
        """아직 말하는 중인 소리를 빠르게(beam 1) 받아써서 미리보기 자막으로. 채팅 반응에는 쓰지 않음."""
        import numpy as np
        peak = float(np.max(np.abs(piece))) if len(piece) else 0.0
        if peak < 0.01:
            return
        piece = (piece * min(3.0, 0.9 / peak)).astype(np.float32)
        try:
            segs, _ = self.model.transcribe(piece, language=self.lang, beam_size=1, vad_filter=False,
                                            condition_on_previous_text=False, temperature=0.0,
                                            without_timestamps=True, no_speech_threshold=0.5)
            text = clean_transcript(" ".join(s.text.strip() for s in segs if s.no_speech_prob <= 0.45))
        except Exception as e:
            log.info("preview failed: %s", e)
            return
        if text:
            self.bus.put(("partial", text))

    def vote_language(self, info):
        """해설 언어 자동 찾기: 확신 있는 결과가 3번 연속 같으면 그 언어로 고정"""
        code = getattr(info, "language", None)
        prob = float(getattr(info, "language_probability", 0.0) or 0.0)
        if not code or prob < 0.7:
            return
        self.lang_votes = (self.lang_votes + [code])[-3:]
        if len(self.lang_votes) == 3 and len(set(self.lang_votes)) == 1:
            self.lang = code
            log.info("commentary language: %s", code)
            self.bus.put(("stt_status", ("on", f"해설 듣는 중 ({LANG_NAMES.get(code, code)})")))

    def run(self):
        try:
            import numpy as np
            import pyaudiowpatch as pyaudio
            self._continue = pyaudio.paContinue
        except Exception as e:
            self.bus.put(("stt_status", ("error", f"받아쓰기 준비 실패: {e}")))
            return
        try:
            self.bus.put(("stt_status", ("loading", "받아쓰기 모델 불러오는 중…")))
            self.model = self.load_model(self.cfg)
        except Exception as e:
            log.exception("whisper load failed")
            self.bus.put(("stt_status", ("error", f"받아쓰기 모델을 불러오지 못했습니다: {e}")))
            return
        vad = self._vad()
        p = pyaudio.PyAudio()
        stream = None
        try:
            wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
            dev = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
            if not dev.get("isLoopbackDevice"):
                for lb in p.get_loopback_device_info_generator():
                    if dev["name"] in lb["name"]:
                        dev = lb
                        break
            rate = int(dev["defaultSampleRate"])
            ch = max(1, int(dev["maxInputChannels"]))
            stream = p.open(format=pyaudio.paInt16, channels=ch, rate=rate, input=True,
                            input_device_index=dev["index"], frames_per_buffer=2048, stream_callback=self._cb)
            stream.start_stream()
            self.bus.put(("stt_status", ("on", "해설 듣는 중")))
            log.info("stt on: model=%s device=%s vad=%s", self._size, self._device, vad is not None)
            buf = np.zeros(0, dtype=np.float32)
            last_check = 0.0
            last_preview = 0.0
            while not self.stop_flag.is_set():
                time.sleep(0.15)
                with self.lock:
                    raw, self.chunks = b"".join(self.chunks), []
                if raw:
                    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                    a = a[: len(a) // ch * ch].reshape(-1, ch).mean(axis=1)
                    a = to_16k(a, rate)
                    buf = np.concatenate([buf, a])
                    self.bus.put(("level", float(np.sqrt(np.mean(a * a))) if len(a) else 0.0))
                if len(buf) > 30 * SR:                      # 받아쓰기가 밀리면 오래된 소리는 버림
                    buf = buf[-12 * SR:]
                if vad is None:                             # VAD가 없으면 예전처럼 5초씩
                    if len(buf) >= 5 * SR:
                        piece, buf = buf[:5 * SR], buf[5 * SR:]
                        self.transcribe(piece, vad_done=False)
                    continue
                if len(buf) < int(0.8 * SR) or time.time() - last_check < 0.35:
                    continue
                last_check = time.time()
                spans = vad(buf)
                if not spans:
                    buf = buf[-int(0.5 * SR):]              # 말소리가 없으면 끝부분만 남김
                    continue
                start = max(0, spans[0]["start"] - int(0.15 * SR))
                end = spans[-1]["end"]
                silent_tail = len(buf) - end
                cut = None
                if silent_tail >= int(self.END_SIL * SR):   # 말이 멈춤 → 여기까지 한 덩어리
                    cut = min(len(buf), end + int(0.15 * SR))
                elif len(buf) - start >= int(self.MAX_SEG * SR):
                    # 말이 길게 이어짐 → 3초 이후의 가장 마지막 쉼에서 끊음
                    for s1, s2 in zip(reversed(spans[:-1]), reversed(spans[1:])):
                        if s1["end"] - start >= 3 * SR:
                            cut = (s1["end"] + s2["start"]) // 2
                            break
                    if cut is None:
                        cut = start + int(self.MAX_SEG * SR)
                if cut is None:
                    if start > 0:                           # 말 시작 전의 소리는 버림
                        buf = buf[start:]
                    # 아직 말하는 중 → 미리보기 자막 (realtime-captions처럼 문장이 끝나기 전에 먼저 보여 줌)
                    if (len(buf) >= int(0.8 * SR) and time.time() - last_preview >= self.PREVIEW_EVERY
                            and self.preview_on()):
                        last_preview = time.time()
                        self.preview(buf.copy())
                    continue
                piece, buf = buf[start:cut], buf[cut:]
                if len(piece) >= int(0.4 * SR):
                    self.transcribe(piece, vad_done=True)
                if len(buf) > int(self.MAX_LAG * SR):       # 받아쓰는 동안 쌓인 소리가 너무 많으면 최근 것만
                    log.info("stt lag %.1fs, skipping old audio", len(buf) / SR)
                    buf = buf[-int(1.5 * SR):]
        except Exception as e:
            log.exception("audio loop failed")
            self.bus.put(("stt_status", ("error", f"게임 소리를 가져오지 못했습니다: {e}")))
        finally:
            try:
                if stream:
                    stream.stop_stream()
                    stream.close()
                p.terminate()
            except Exception:
                pass

    def stop(self):
        self.stop_flag.set()


# ---------------------------------------------------------------------------
# 스코어보드 읽기 (화면 캡처 + RapidOCR) / 엠블럼 인식 요청
# ---------------------------------------------------------------------------
SCORE_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,3})\s+(\d{1,2})\s*[-–—:|]?\s*(\d{1,2})\s+([A-Z][A-Z0-9]{1,3})\b")
CLOCK_RE = re.compile(r"(\d{1,3})\s*[:：]\s*(\d{2})")
# 라리가처럼 팀이 위아래로 쌓인 스코어보드: "VIL 0 / BAR 0"
STACK_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,3})\s+(\d{1,2})\s+([A-Z][A-Z0-9]{1,3})\s+(\d{1,2})\b")


def parse_board(items: list[tuple[float, float, str]]):
    """items = (y, x, text). 스코어보드 문자열에서 팀 약칭, 점수, 경기 시간을 뽑음."""
    if not items:
        return None
    items = sorted(items, key=lambda t: (round(t[0] / 25), t[1]))
    joined = " ".join(t[2] for t in items).upper()
    clock = CLOCK_RE.search(joined)
    minute = int(clock.group(1)) if clock else None
    rest = CLOCK_RE.sub(" ", joined)
    rest = re.sub(r"\b[OQD]\b", "0", rest)              # 숫자 0을 글자 O로 읽는 경우
    m = SCORE_RE.search(rest)
    if not m:
        spaced = re.sub(r"(?<=[A-Z])(?=\d)|(?<=\d)(?=[A-Z])", " ", rest)
        spaced = re.sub(r"(\d)\s*[-–—:|]\s*(\d)", r"\1 - \2", spaced)
        m = SCORE_RE.search(spaced)
        if not m:
            st = STACK_RE.search(spaced)
            if st:
                h, hs, a, as_ = st.group(1), int(st.group(2)), st.group(3), int(st.group(4))
                if hs > 20 or as_ > 20 or h == a:
                    return {"minute": minute} if minute is not None else None
                return {"codes": (h, a), "score": (hs, as_), "minute": minute}
    if not m:
        return {"minute": minute} if minute is not None else None
    h, hs, as_, a = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
    if hs > 20 or as_ > 20 or h == a:
        return {"minute": minute} if minute is not None else None
    return {"codes": (h, a), "score": (hs, as_), "minute": minute}


# 일시정지 화면의 선발 라인업 목록: 왼쪽 = 홈 팀 ("10 Parejo"), 오른쪽 = 원정 팀 ("Lamine Yamal 10")
LINEUP_LEFT = (0.03, 0.30, 0.24, 0.50)      # 화면 비율 (왼쪽, 위, 폭, 높이)
LINEUP_RIGHT = (0.73, 0.30, 0.24, 0.50)
NAME_CH = r"A-Za-zÀ-ÖØ-öø-ÿĀ-ž"


def parse_lineup_column(items: list[tuple[float, float, str]], row_tol: float, right: bool) -> list[tuple[str, str]]:
    """OCR 조각 (y, x, 글자) → [(등번호, 이름)], 위에서 아래 순서.
    주장(C)·골 아이콘처럼 한 글자짜리 조각은 버림."""
    rows: list[list] = []
    for y, x, t in sorted(items):
        t = t.strip()
        if not t:
            continue
        if rows and abs(rows[-1][0] - y) < row_tol:
            rows[-1][1].append((x, t))
        else:
            rows.append([y, [(x, t)]])
    out = []
    for _, parts in rows:
        toks = " ".join(t for _, t in sorted(parts)).split()
        toks = [t for t in toks if not (len(t) == 1 and not t.isdigit()) and t not in ("(C)", "[C]", "©")]
        line = " ".join(toks)
        m = (re.match(rf"^.*?(?<!\d)(\d{{1,2}})\s+([{NAME_CH}].*?)$", line) if right is False
             else re.match(rf"^([{NAME_CH}].*?[{NAME_CH}.])\s*(\d{{1,2}})(?!\d).*$", line))
        if not m:
            continue
        no, name = (m.group(1), m.group(2)) if not right else (m.group(2), m.group(1))
        name = re.sub(rf"[^{NAME_CH}.\-' ]", "", name).strip(" -").lstrip(".")
        if len(re.sub(rf"[^{NAME_CH}]", "", name)) >= 2:
            out.append((no, name))
    return out


PLAYER_HUD = (0.0, 0.80, 1.0, 0.20)          # 화면 아래: 조작 중인 선수 표시 ("DIAS 33"), 골 뒤 득점자 이름


SQUAD_PITCH = (0.04, 0.14, 0.54, 0.50)        # 팀 관리 화면의 경기장 그림 (선수 이름이 포메이션 모양으로 놓임)


def parse_squad_pitch(items: list[tuple[float, float, str]], height: float) -> dict | None:
    """경기장 그림 속 선수 이름 (y, x, 글자) → {"formation": "4-2-3-1", "rows": [[골키퍼], [수비 왼→오], …]}.
    이름의 세로 위치로 줄을 나눔 (원근 때문에 양쪽 풀백이 조금 위에 있어도 한 줄로)."""
    names = []
    for y, x, t in items:
        t = re.sub(rf"[^{NAME_CH}.\-' ]", "", t).strip(" .-")
        if len(re.sub(rf"[^{NAME_CH}]", "", t)) >= 3:
            names.append((y, x, t))
    if len(names) != 11:
        return None
    names.sort()
    rows: list[list] = [[names[0]]]
    for n in names[1:]:
        if n[0] - rows[-1][-1][0] > height * 0.03:
            rows.append([n])
        else:
            rows[-1].append(n)
    rows.reverse()                                    # 아래(골키퍼)부터
    if len(rows[0]) != 1 or not (3 <= len(rows) - 1 <= 5) or any(len(r) > 5 for r in rows[1:]):
        return None
    ordered = [[t for _, _, t in sorted(r, key=lambda n: n[1])] for r in rows]
    return {"formation": "-".join(str(len(r)) for r in rows[1:]), "rows": ordered}


# 경기 전 '예상 라인업' 화면 (상대 팀): 왼쪽 경기장에 포메이션 모양으로 선수 이름, 아래 '교체' 줄,
# 오른쪽에 리그·엠블럼·ATT/MID/DEF 능력치. 한글은 글자 읽기(OCR)가 못 읽어서 ATT/MID/DEF로 이 화면인지 알아봄.
PREVIEW_PANEL = (0.66, 0.60, 0.32, 0.10)     # ATT MID DEF 글자
PREVIEW_PITCH = (0.04, 0.13, 0.56, 0.50)     # 포메이션 제목(4-4-2 플랫) + 선발 11명
PREVIEW_BENCH = (0.04, 0.70, 0.56, 0.10)     # 교체 선수 이름 줄
FORM_RX = re.compile(r"(?<!\d)(\d)\s*-\s*(\d)\s*-\s*(\d)(?:\s*-\s*(\d))?(?:\s*-\s*(\d))?(?!\d)")


def clean_shown_name(t: str) -> str:
    """화면 이름 다듬기: 주장 C·눈(스카우트) 아이콘처럼 한 글자로 읽힌 조각은 버림 ('C A. Pedraza' → 'A. Pedraza')"""
    toks = [x for x in str(t or "").split() if not (len(x) == 1 and x.isalpha())]
    t = re.sub(rf"[^{NAME_CH}.\-' ]", "", " ".join(toks)).strip(" -")
    # 글자 읽기가 띄어쓰기를 빼먹은 것 되살리기: PauNavarro → Pau Navarro, A.Pedraza → A. Pedraza (McTominay, C.V.는 그대로)
    t = re.sub(r"([a-zß-ÿ])(?=[A-ZÀ-Þ])", lambda mm: mm.group(1) if re.search(r"\bMa?c$", t[:mm.end()]) else mm.group(1) + " ", t)
    t = re.sub(r"\.(?=[A-ZÀ-Þ][a-zß-ÿ])", ". ", t)
    return t if len(re.sub(rf"[^{NAME_CH}]", "", t)) >= 3 else ""


def parse_preview(pitch: list[tuple[float, float, str]], bench: list[tuple[float, float, str]]) -> dict | None:
    """예상 라인업 화면의 글자 (y, x, 글자) → {"formation": "4-4-2", "rows": [[골키퍼], [수비 왼→오], …], "bench": [...]}.
    포메이션 제목이 읽히면 그 숫자대로 아래(골키퍼)부터 줄을 나눔 — 원근 때문에 측면 선수가 조금 위에 있어도 맞게."""
    form = None
    names = []
    for y, x, t in pitch:
        fm = FORM_RX.search(t)
        if fm:
            form = [int(g) for g in fm.groups() if g]
            continue
        n = clean_shown_name(t)
        if n:
            names.append((y, x, n))
    if len(names) != 11:
        return None
    names.sort(key=lambda n: -n[0])                  # 아래(골키퍼)부터
    if form and sum(form) == 10 and 3 <= len(form) <= 5:
        rows, i = [[names[0]]], 1
        for k in form:
            rows.append(names[i:i + k])
            i += k
        # 줄끼리 세로로 겹치면 잘못 나눈 것 (다른 화면이거나 이름을 덜 읽음)
        if any(min(n[0] for n in lower) <= max(n[0] for n in upper) for lower, upper in zip(rows, rows[1:])):
            return None
    else:
        span = max(n[0] for n in names) - min(n[0] for n in names)
        rows = [[names[0]]]
        for n in names[1:]:
            if rows[-1][-1][0] - n[0] > span * 0.08:
                rows.append([n])
            else:
                rows[-1].append(n)
        if len(rows[0]) != 1 or not (3 <= len(rows) - 1 <= 5) or any(len(r) > 5 for r in rows[1:]):
            return None
        form = [len(r) for r in rows[1:]]
    ordered = [[t for _, _, t in sorted(r, key=lambda n: n[1])] for r in rows]
    subs = [clean_shown_name(t) for _, _, t in sorted(bench, key=lambda b: b[1])]
    return {"formation": "-".join(map(str, form)), "rows": ordered, "bench": [s for s in subs if s][:12]}


def ocr_lines(items: list[tuple[float, float, str]], row_tol: float) -> list[str]:
    """OCR 조각 (y, x, 글자) → 줄 단위 글"""
    rows: list[list] = []
    for y, x, t in sorted(items):
        if rows and abs(rows[-1][0] - y) < row_tol:
            rows[-1][1].append((x, t))
        else:
            rows.append([y, [(x, t)]])
    return [" ".join(t for _, t in sorted(parts)).strip() for _, parts in rows]


def plain(s: str) -> str:
    """악센트·대소문자 무시 (Rúben = RUBEN)"""
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()


def fc_to_overlay_order(players: list[dict], formation: str) -> list[dict]:
    """게임 목록 순서(골키퍼, 수비 오른쪽→왼쪽, 미드 오른쪽→왼쪽 …)를 명단 그림 순서(각 줄 왼쪽→오른쪽)로"""
    rows = formation_rows(formation)
    if len(players) != sum(rows) + 1:
        return players
    out, i = [players[0]], 1
    for k in rows:
        out += list(reversed(players[i:i + k]))
        i += k
    return out


def primary_monitor():
    try:
        import mss
        with getattr(mss, "MSS", mss.mss)() as s:
            mons = s.monitors[1:]
            for mo in mons:
                if mo["left"] == 0 and mo["top"] == 0:
                    return mo, mons
            return mons[0], mons
    except Exception:
        return None, []


class BoardWatcher(threading.Thread):
    def __init__(self, cfg, bus: queue.Queue, hud_fn=lambda: False):
        super().__init__(daemon=True, name="board")
        self.cfg, self.bus, self.hud_fn = cfg, bus, hud_fn
        self.stop_flag = threading.Event()
        self.board_miss = 0              # 스코어보드를 연달아 못 읽은 횟수 (일시정지·메뉴 화면)
        self.last_lineup_check = 0.0
        self.last_lineup_sig = None
        self.last_squad_sig = None
        self.last_preview_sig = None

    @staticmethod
    def ocr_region(sct, mon, ocr, np, region) -> list[tuple[float, float, str]]:
        """화면 한 부분의 글자 → [(y, x, 글자)]. 작은 화면(1280×720 등)은 2배로 키워서 읽음."""
        l, t, w, h = region
        reg = {"left": int(mon["left"] + l * mon["width"]), "top": int(mon["top"] + t * mon["height"]),
               "width": max(40, int(w * mon["width"])), "height": max(20, int(h * mon["height"]))}
        shot = np.array(sct.grab(reg))[:, :, :3]            # BGR
        if mon["width"] < 1700:
            shot = shot.repeat(2, axis=0).repeat(2, axis=1)
        result, _ = ocr(shot.copy())
        return [(sum(p[1] for p in box) / 4, sum(p[0] for p in box) / 4, txt) for box, txt, _s in (result or [])]

    def read_preview_screen(self, sct, mon, ocr, np) -> bool:
        """경기 전 '예상 라인업'(상대 팀) 화면이면 포메이션·선발·교체 명단을 보냄. 이 화면이면 True."""
        labels = {t.strip().upper() for _, _, t in self.ocr_region(sct, mon, ocr, np, PREVIEW_PANEL)}
        if len(labels & {"ATT", "MID", "DEF"}) < 2:
            return False
        parsed = parse_preview(self.ocr_region(sct, mon, ocr, np, PREVIEW_PITCH),
                               self.ocr_region(sct, mon, ocr, np, PREVIEW_BENCH))
        if not parsed:
            log.info("preview screen seen but lineup not readable")
            return True
        sig = (parsed["formation"], tuple(n for r in parsed["rows"] for n in r), tuple(parsed["bench"]))
        if sig != self.last_preview_sig:
            self.last_preview_sig = sig
            log.info("preview screen (opponent): %s %s bench=%s", parsed["formation"], parsed["rows"], parsed["bench"])
            self.bus.put(("preview_screen", {**parsed, "t": time.time()}))
        return True

    def read_hud(self, sct, mon, ocr, np):
        """화면 아래 글자를 읽어 보냄 → App이 명단과 맞춰 '지금 조작 중인 선수'와 '골 넣은 선수'를 찾음"""
        l, t, w, h = PLAYER_HUD
        reg = {"left": int(mon["left"] + l * mon["width"]), "top": int(mon["top"] + t * mon["height"]),
               "width": int(w * mon["width"]), "height": int(h * mon["height"])}
        shot = np.array(sct.grab(reg))[:, :, :3].copy()   # BGR
        result, _ = ocr(shot)
        items = [(sum(p[1] for p in box) / 4, sum(p[0] for p in box) / 4, txt) for box, txt, _s in (result or [])]
        lines = [x for x in ocr_lines(items, row_tol=mon["height"] * 0.012) if re.search(rf"[{NAME_CH}]{{2}}", x)]
        if lines:
            self.bus.put(("hud", {"t": time.time(), "lines": lines}))

    def read_squad_screen(self, sct, mon, ocr, np, Image):
        """팀 관리(스쿼드) 화면이면 내 팀 포메이션과 자리를 보냄"""
        l, t, w, h = SQUAD_PITCH
        reg = {"left": int(mon["left"] + l * mon["width"]), "top": int(mon["top"] + t * mon["height"]),
               "width": int(w * mon["width"]), "height": int(h * mon["height"])}
        shot = np.array(sct.grab(reg))[:, :, :3].copy()   # BGR
        result, _ = ocr(shot)
        items = [(sum(p[1] for p in box) / 4, sum(p[0] for p in box) / 4, txt) for box, txt, _s in (result or [])]
        parsed = parse_squad_pitch(items, mon["height"])
        if not parsed:
            return
        sig = (parsed["formation"], tuple(n for r in parsed["rows"] for n in r))
        if sig == self.last_squad_sig:
            return
        self.last_squad_sig = sig
        log.info("squad screen: %s %s", parsed["formation"], parsed["rows"])
        self.bus.put(("squad_screen", parsed))

    def read_lineup_screen(self, sct, mon, ocr, np, Image):
        """스코어보드가 안 보일 때만 호출: 선발 라인업 화면이면 두 팀 명단을 보냄"""
        cols = []
        for (l, t, w, h), right in ((LINEUP_LEFT, False), (LINEUP_RIGHT, True)):
            reg = {"left": int(mon["left"] + l * mon["width"]), "top": int(mon["top"] + t * mon["height"]),
                   "width": int(w * mon["width"]), "height": int(h * mon["height"])}
            img = Image.fromarray(np.array(sct.grab(reg))[:, :, :3][:, :, ::-1])
            big = img.resize((img.width * 2, img.height * 2))
            result, _ = ocr(np.array(big)[:, :, ::-1].copy())
            items = [(sum(p[1] for p in box) / 4, sum(p[0] for p in box) / 4, txt) for box, txt, _s in (result or [])]
            cols.append(parse_lineup_column(items, row_tol=mon["height"] * 0.012 * 2, right=right))
            if len(cols[-1]) < 9:          # 선발 라인업 목록이 아님 → 팀 관리 화면인지
                self.read_squad_screen(sct, mon, ocr, np, Image)
                return
        home, away = cols
        sig = (tuple(n for n, _ in home), tuple(n for n, _ in away))
        if sig == self.last_lineup_sig:
            return
        self.last_lineup_sig = sig
        log.info("lineup screen: home=%s | away=%s", home, away)
        self.bus.put(("lineup_screen", {"home": home[:11], "away": away[:11]}))

    def run(self):
        try:
            import mss
            import numpy as np
            from PIL import Image
        except Exception as e:
            self.bus.put(("board_status", f"화면 읽기 준비 실패: {e}"))
            return
        ocr = None
        try:
            from rapidocr_onnxruntime import RapidOCR
            ocr = RapidOCR()
        except Exception as e:
            log.warning("rapidocr unavailable: %s", e)
            self.bus.put(("board_status", "스코어보드 글자 읽기 기능이 없어 점수는 해설로만 판단합니다."))
        mon, _ = primary_monitor()
        with getattr(mss, "MSS", mss.mss)() as sct:
            if mon is None:
                mon = sct.monitors[1]
            tick = 0
            while not self.stop_flag.is_set():
                t0 = time.time()
                tick += 1
                try:
                    # 선수 표시는 1.5초마다 (골 넣은 선수를 놓치지 않게), 스코어보드는 3초마다
                    if ocr is not None and self.hud_fn():
                        self.read_hud(sct, mon, ocr, np)
                    if tick % 2:
                        raise StopIteration
                    l, t, w, h = self.cfg.get("scoreboard_region", [0, 0, 0.5, 0.16])
                    reg = {"left": int(mon["left"] + l * mon["width"]), "top": int(mon["top"] + t * mon["height"]),
                           "width": max(40, int(w * mon["width"])), "height": max(20, int(h * mon["height"]))}
                    shot = np.array(sct.grab(reg))[:, :, :3]  # BGR
                    img = Image.fromarray(shot[:, :, ::-1])
                    if ocr is not None:
                        big = img.resize((img.width * 2, img.height * 2))
                        arr = np.array(big)[:, :, ::-1].copy()
                        result, _ = ocr(arr)
                        items = []
                        for box, txt, _score in (result or []):
                            ys = [p[1] for p in box]
                            xs = [p[0] for p in box]
                            items.append((sum(ys) / 4, sum(xs) / 4, txt))
                        parsed = parse_board(items)
                        if parsed:
                            self.bus.put(("board", parsed))
                        self.board_miss = 0 if (parsed and "codes" in parsed) else self.board_miss + 1
                        # 스코어보드가 안 보이면(일시정지·메뉴) 4초마다: 예상 라인업(상대 팀) → 선발 라인업 → 팀 관리 화면인지 확인
                        if self.board_miss >= 2 and time.time() - self.last_lineup_check > 4:
                            self.last_lineup_check = time.time()
                            if not self.read_preview_screen(sct, mon, ocr, np):
                                self.read_lineup_screen(sct, mon, ocr, np, Image)
                except StopIteration:
                    pass
                except Exception:
                    log.exception("board loop")
                self.stop_flag.wait(max(0.3, 1.5 - (time.time() - t0)))

    def stop(self):
        self.stop_flag.set()


# ---------------------------------------------------------------------------
# 게임 실행 감지
# ---------------------------------------------------------------------------
GAME_RX = re.compile(r"^fc\s?2\d.*\.exe$", re.I)


def game_running() -> bool:
    try:
        import psutil
        for p in psutil.process_iter(["name"]):
            n = p.info.get("name") or ""
            if GAME_RX.match(n):
                return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# 화면: 유튜브 라이브 채팅 스타일 창
# ---------------------------------------------------------------------------
BG, BG2, LINE = "#0f0f0f", "#181818", "#303030"
FG, FG2 = "#f1f1f1", "#aaaaaa"
MEMBER, MOD, OWNER = "#2ba640", "#5e84f1", "#ffd600"
CHROMA = "#00b140"
TIERS = [  # (최소 금액, 머리 색, 몸 색, 글자 색)
    (100000, "#d00000", "#e62117", "#ffffff"),
    (50000, "#c2185b", "#e91e63", "#ffffff"),
    (20000, "#e65100", "#f57c00", "#ffffff"),
    (10000, "#ffb300", "#ffca28", "#111111"),
    (5000, "#00bfa5", "#1de9b6", "#111111"),
    (2000, "#00b8d4", "#00e5ff", "#111111"),
    (0, "#1565c0", "#1e88e5", "#ffffff"),
]
AV_COLORS = ["#e91e63", "#9c27b0", "#673ab7", "#3f51b5", "#1e88e5", "#039be5", "#00897b", "#5d4037",
             "#8e24aa", "#f4511e", "#6d4c41", "#546e7a", "#c2185b", "#5e35b1", "#00838f", "#ef6c00"]
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\malgunbd.ttf", r"C:\Windows\Fonts\malgun.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/System/Library/Fonts/AppleSDGothicNeo.ttc",
]
# 채팅 속도: 시청자 수로 기본 속도를 정하고, 메뉴의 느림/보통/빠름은 거기에 곱함
SPEED_MULT = {"slow": 0.55, "normal": 1.0, "fast": 1.7}
KICK_RED, KICK_RED_HOVER = "#e62117", "#ff3b30"


def pick_font(root, *names):
    fams = set(tkfont.families(root))
    for n in names:
        if n in fams:
            return n
    return "TkDefaultFont"


class ChatWindow:
    """유튜브 라이브 채팅(다크) 모양. 크기는 모두 '유튜브 CSS 픽셀 × 화면 배율'로 계산해서
    윈도우 배율(125%, 150% …)에서도 글자와 칸이 같이 커지도록 함."""

    def __init__(self, app):
        self.app = app
        self.root = app.root
        self.k = app.k
        cfg = app.cfg
        self.ui = pick_font(self.root, "Malgun Gothic", "맑은 고딕", "Noto Sans CJK KR", "Apple SD Gothic Neo")
        self.f = {}
        self._img_cache = {}
        self._ttf = next((f for f in FONT_CANDIDATES if Path(f).exists()), None)
        self._ttf_reg = next((f for f in [r"C:\Windows\Fonts\malgun.ttf", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"] if Path(f).exists()), self._ttf)
        self.cards: list = []
        self.ticks: list = []
        self.build_fonts()

        r = self.root
        r.title(APP_NAME)
        r.configure(bg=BG)
        # 머리: "실시간 채팅 ▾"  ...  시청자 수  ⋮
        self.header = tk.Frame(r, bg=BG, height=self.px(48))
        self.header.pack_propagate(False)
        self.lbl_title = tk.Label(self.header, text="실시간 채팅 · 미리보기  ▾" if app.args.demo else "실시간 채팅  ▾", bg=BG, fg=FG, font=self.f["title"], cursor="hand2")
        self.lbl_title.pack(side="left", padx=(self.px(16), 0))
        self.lbl_title.bind("<Button-1>", self.popup)
        self.btn_menu = tk.Label(self.header, text="⋮", bg=BG, fg=FG, font=self.f["title"], cursor="hand2", padx=self.px(12))
        self.btn_menu.pack(side="right")
        self.btn_menu.bind("<Button-1>", self.popup)
        self.lbl_viewers = tk.Label(self.header, text="", bg=BG, fg=FG2, font=self.f["small"])
        self.lbl_viewers.pack(side="right")
        self.sep = tk.Frame(r, bg=LINE, height=1)
        # 후원 알림 줄
        self.ticker = tk.Frame(r, bg=BG, height=self.px(48))
        self.ticker.pack_propagate(False)
        self.sep2 = tk.Frame(r, bg=LINE, height=1)
        # 채팅 목록
        self.body = tk.Frame(r, bg=BG)
        self.text = tk.Text(self.body, bg=BG, fg=FG, bd=0, highlightthickness=0, wrap="word", padx=0, pady=self.px(8),
                            cursor="arrow", font=self.f["msg"], takefocus=0, yscrollcommand=self._on_scroll)
        self.text.pack(fill="both", expand=True)
        self.jump = tk.Canvas(self.body, width=self.px(40), height=self.px(40), bg=BG, highlightthickness=0, cursor="hand2")
        self.jump.bind("<Button-1>", lambda e: self.scroll_end())
        self._jump_on = False
        # 킥오프 버튼 (누르기 전에는 채팅이 나오지 않음)
        self.kick = tk.Canvas(self.body, bg=BG, highlightthickness=0, cursor="hand2")
        self.kick.bind("<Button-1>", lambda e: self.app.kickoff())
        self.kick.bind("<Enter>", lambda e: self._draw_kickoff(True))
        self.kick.bind("<Leave>", lambda e: self._draw_kickoff(False))
        self._kick_on = False
        # 입력창 (보기용)
        self.composer = tk.Frame(r, bg=BG)
        self.build_composer()
        # 해설 자막 줄 (기본은 숨김)
        self.status = tk.Frame(r, bg=BG2)
        self.lbl_state = tk.Label(self.status, text="", bg=BG2, fg=FG2, font=self.f["small"], anchor="w")
        self.lbl_state.pack(fill="x", padx=self.px(12), pady=(self.px(6), 0))
        self.lbl_trans = tk.Label(self.status, text="", bg=BG2, fg=FG2, font=self.f["small"], anchor="w", justify="left")
        self.lbl_trans.pack(fill="x", padx=self.px(12), pady=(0, self.px(4)))
        self.level = tk.Canvas(self.status, height=self.px(3), bg=BG2, highlightthickness=0)
        self.level.pack(fill="x", padx=self.px(12), pady=(0, self.px(6)))
        self._level_bar = self.level.create_rectangle(0, 0, 0, self.px(3), fill=MEMBER, width=0)

        self._last_w = 0
        self.text.bind("<Configure>", self._on_resize)
        r.bind("<Button-3>", self.popup)
        self.text.configure(state="disabled")
        self.layout()
        self.apply_theme()
        self.build_menu()
        self.root.after(1000, self._tick_ticker)

    # ----- 크기 -----
    def px(self, n: float) -> int:
        return max(1, int(round(n * self.k)))

    def fs(self) -> float:
        return getattr(self, "_fs", 1.0)

    def auto_font_scale(self, width: int) -> float:
        """채팅 창 폭(기본 400px)에 비례해 글자 크기를 정함"""
        return round(max(0.9, min(1.6, width / (400 * self.k))) * 20) / 20

    def build_fonts(self):
        s = self.fs()

        def mk(key, px, weight="normal"):
            size = -max(6, int(round(px * self.k * (s if key not in ("title", "small") else 1.0))))
            if key in self.f:
                self.f[key].configure(size=size, weight=weight)
            else:
                self.f[key] = tkfont.Font(family=self.ui, size=size, weight=weight)
        mk("title", 16)
        mk("small", 12)
        mk("author", 13)
        mk("msg", 13)
        mk("pname", 14)
        mk("pamt", 14, "bold")
        mk("pbody", 15)
        mk("tick", 13, "bold")
        mk("input", 14)
        mk("kick", 20, "bold")

    def layout(self):
        """보이는 부분을 순서대로 다시 배치"""
        for w in (self.header, self.sep, self.ticker, self.sep2, self.body, self.composer, self.status):
            w.pack_forget()
        chroma = bool(self.app.cfg.get("chroma"))
        if not chroma:
            self.header.pack(fill="x")
            self.sep.pack(fill="x")
            if self.ticks:
                self.ticker.pack(fill="x")
                self.sep2.pack(fill="x")
        if self.app.cfg.get("show_transcript", False) and not chroma:
            self.status.pack(fill="x", side="bottom")
        if self.app.cfg.get("show_composer", True) and not chroma:
            self.composer.pack(fill="x", side="bottom")
        self.body.pack(fill="both", expand=True)

    def apply_theme(self):
        chroma = bool(self.app.cfg.get("chroma"))
        bg = CHROMA if chroma else BG
        self.build_fonts()
        for w in (self.root, self.body, self.text, self.jump):
            w.configure(bg=bg)
        t = self.text
        s = self.fs()
        av = self.px(24 * s)
        t.tag_configure("line", lmargin1=self.px(16), lmargin2=self.px(16) + av + self.px(16), rmargin=self.px(24),
                        spacing1=self.px(4), spacing3=self.px(4))
        t.tag_configure("author", foreground="#e8e8e8" if chroma else FG2, font=self.f["author"])
        t.tag_configure("member", foreground="#ffe57f" if chroma else MEMBER, font=self.f["author"])
        t.tag_configure("mod", foreground="#b5c8ff" if chroma else MOD, font=self.f["author"])
        # 유튜브에서 채널 주인(방장) 이름은 노란 바탕
        t.tag_configure("owner", foreground="#0f0f0f", background=OWNER, font=self.f["author"])
        t.tag_configure("msg", foreground="#ffffff" if chroma else FG, font=self.f["msg"])
        t.tag_configure("card", spacing1=self.px(4), spacing3=self.px(4))
        self.lbl_viewers.configure(text=self.lbl_viewers.cget("text") if self.app.cfg.get("show_viewers", True) else "")
        self.lbl_trans.configure(wraplength=max(self.px(200), self.root.winfo_width() - self.px(30)))
        self.layout()
        self._redraw_cards(force=True)
        self._draw_jump()
        self._draw_kickoff()
        try:
            self.root.attributes("-topmost", bool(self.app.cfg.get("always_on_top", True)))
        except tk.TclError:
            pass

    # ----- 그림 -----
    def _font_path(self, bold=True):
        return self._ttf if bold else self._ttf_reg

    def avatar(self, name: str, size: int, gap: int = 0):
        """동그란 프로필(이니셜). gap = 오른쪽 투명 여백(글자와 간격)."""
        color = AV_COLORS[sum(ord(c) * (i + 7) for i, c in enumerate(name)) % len(AV_COLORS)]
        ch = name.lstrip("@")[:1] or "?"
        key = (color, ch, size, gap)
        if key in self._img_cache:
            return self._img_cache[key]
        try:
            from PIL import Image, ImageDraw, ImageFont, ImageTk
            ss = 4
            im = Image.new("RGBA", ((size + gap) * ss, size * ss), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            d.ellipse((0, 0, size * ss - 1, size * ss - 1), fill=color)
            if self._ttf:
                f = ImageFont.truetype(self._ttf, int(size * ss * 0.48))
                d.text((size * ss / 2, size * ss / 2), ch.upper(), font=f, fill="white", anchor="mm")
            im = im.resize((size + gap, size), Image.LANCZOS)
            img = ImageTk.PhotoImage(im)
        except Exception:
            img = tk.PhotoImage(width=size + gap, height=size)
            img.put(color, to=(0, 0, size, size))
        self._img_cache[key] = img
        return img

    def badge(self, kind: str):
        size = self.px(14 * self.fs())
        key = ("badge", kind, size)
        if key in self._img_cache:
            return self._img_cache[key]
        try:
            from PIL import Image, ImageDraw, ImageTk
            ss = 6
            S = size * ss
            gap = self.px(4) * ss
            im = Image.new("RGBA", (S + gap * 2, S), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            ox = gap
            if kind == "member":   # 초록 방패 + 별
                d.rounded_rectangle((ox, 0, ox + S - 1, S - 1), radius=S // 4, fill=MEMBER)
                import math as _m
                pts = []
                for i in range(10):
                    r_ = S * (0.36 if i % 2 == 0 else 0.15)
                    a = _m.radians(-90 + i * 36)
                    pts.append((ox + S / 2 + _m.cos(a) * r_, S / 2 + _m.sin(a) * r_))
                d.polygon(pts, fill="white")
            else:                  # 파란 렌치
                c = MOD
                d.line((ox + S * 0.25, S * 0.8, ox + S * 0.62, S * 0.42), fill=c, width=int(S * 0.18))
                d.ellipse((ox + S * 0.5, S * 0.08, ox + S * 0.95, S * 0.53), outline=c, width=int(S * 0.16))
                d.rectangle((ox + S * 0.72, S * 0.02, ox + S * 0.98, S * 0.28), fill=(0, 0, 0, 0))
            im = im.resize((size + 2 * self.px(4), size), Image.LANCZOS)
            img = ImageTk.PhotoImage(im)
        except Exception:
            img = None
        self._img_cache[key] = img
        return img

    def spacer(self, w: int):
        key = ("sp", w)
        if key not in self._img_cache:
            self._img_cache[key] = tk.PhotoImage(width=max(1, w), height=1)
        return self._img_cache[key]

    @staticmethod
    def rrect(c, x1, y1, x2, y2, r, **kw):
        r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return c.create_polygon(pts, smooth=True, **kw)

    @staticmethod
    def mix(fg: str, bg: str, a: float) -> str:
        f = [int(fg[i:i + 2], 16) for i in (1, 3, 5)]
        b = [int(bg[i:i + 2], 16) for i in (1, 3, 5)]
        return "#%02x%02x%02x" % tuple(int(f[i] * a + b[i] * (1 - a)) for i in range(3))

    # ----- 후원 / 멤버 카드 (둥근 모서리 캔버스를 채팅 속에 끼움) -----
    def _card_width(self):
        w = self.text.winfo_width()
        if w < self.px(120):
            w = self.px(400)
        return w - 2 * self.px(16)

    def _draw_card(self, c, m):
        c.delete("all")
        W = self._card_width()
        s = self.fs()
        bg = CHROMA if self.app.cfg.get("chroma") else BG
        c.configure(width=W, bg=bg)
        pad = self.px(16)
        avs = self.px(40 * s)
        r = self.px(4)
        if m["kind"] == "super":
            tier = next(t for t in TIERS if m["amount"] >= t[0])
            hd, bd, ink = tier[1], tier[2], tier[3]
            top_lines = [(m["name"], self.f["pname"], self.mix(ink, hd, 0.7)), (f"₩{m['amount']:,}", self.f["pamt"], ink)]
            body = m.get("text", "")
        else:  # 새 멤버
            hd, bd, ink = "#0f9d58", None, "#ffffff"
            top_lines = [(m["name"], self.f["pamt"], ink), ("새 멤버가 되신 것을 환영합니다!", self.f["pname"], self.mix(ink, hd, 0.85))]
            body = ""
        # 머리 높이 = 프로필 + 위아래 여백
        lh = sum(fn.metrics("linespace") for _, fn, _ in top_lines)
        head_h = max(avs, lh) + self.px(16)
        items = []
        x_txt = pad + avs + self.px(16)
        y = head_h / 2 - lh / 2
        for txt, fn, col in top_lines:
            items.append(c.create_text(x_txt, y, text=txt, font=fn, fill=col, anchor="nw"))
            y += fn.metrics("linespace")
        items.append(c.create_image(pad, head_h / 2, image=self.avatar(m["name"], avs), anchor="w"))
        body_h = 0
        if body:
            bid = c.create_text(pad, head_h + self.px(8), text=body, font=self.f["pbody"], fill=ink, anchor="nw", width=W - 2 * pad)
            bb = c.bbox(bid)
            body_h = (bb[3] - bb[1]) + self.px(16)
            items.append(bid)
        H = head_h + body_h
        # 바탕 (나중에 그려서 맨 뒤로)
        bgs = []
        if body:
            bgs.append(self.rrect(c, 0, 0, W, H, r, fill=bd, outline=""))
            bgs.append(self.rrect(c, 0, 0, W, head_h + r, r, fill=hd, outline=""))
            bgs.append(c.create_rectangle(0, head_h - 1, W, head_h + r + 1, fill=bd, outline=""))
            bgs.append(c.create_rectangle(0, head_h - r, W, head_h, fill=hd, outline=""))
        else:
            bgs.append(self.rrect(c, 0, 0, W, H, r, fill=hd, outline=""))
        for b in reversed(bgs):
            c.tag_lower(b)
        c.configure(height=H)

    def _redraw_cards(self, force=False):
        alive = set(self.text.window_names())
        keep = []
        for c, m in self.cards:
            if str(c) in alive:
                self._draw_card(c, m)
                keep.append((c, m))
            else:
                c.destroy()
        self.cards = keep

    def _on_resize(self, e):
        if abs(e.width - self._last_w) > 2:
            self._last_w = e.width
            fs = self.auto_font_scale(self.root.winfo_width())
            if abs(fs - self.fs()) >= 0.05:
                self._fs = fs
                self.root.after_idle(self.apply_theme)
            self._redraw_cards()
            self.lbl_trans.configure(wraplength=max(self.px(200), e.width - self.px(30)))

    # ----- 후원 알림 줄 -----
    def add_tick(self, m):
        if self.app.cfg.get("chroma"):
            return
        tier = next(t for t in TIERS if m["amount"] >= t[0])
        life = min(180.0, 30 + m["amount"] / 1000 * 1.5)
        amt = f"₩{m['amount']:,}"
        w = self.px(4) + self.px(24) + self.px(6) + self.f["tick"].measure(amt) + self.px(12)
        h = self.px(32)
        c = tk.Canvas(self.ticker, width=w, height=h, bg=BG, highlightthickness=0)
        c.pack(side="left", padx=(self.px(8), 0), pady=self.px(8))
        self.ticks.append({"c": c, "t0": time.time(), "life": life, "tier": tier, "amt": amt, "name": m["name"], "w": w, "h": h})
        self._draw_tick(self.ticks[-1])
        if len(self.ticks) == 1:
            self.layout()

    def _draw_tick(self, tk_):
        c, w, h = tk_["c"], tk_["w"], tk_["h"]
        _, hd, bd, ink = tk_["tier"]
        frac = max(0.0, 1 - (time.time() - tk_["t0"]) / tk_["life"])
        c.delete("all")
        self.rrect(c, 0, 0, w, h, h / 2, fill=bd, outline="")
        if frac > 0:
            self.rrect(c, 0, 0, max(h, w * frac), h, h / 2, fill=hd, outline="")
        c.create_image(self.px(4), h / 2, image=self.avatar(tk_["name"], self.px(24)), anchor="w")
        c.create_text(self.px(4) + self.px(24) + self.px(6), h / 2, text=tk_["amt"], font=self.f["tick"], fill=ink, anchor="w")

    def _tick_ticker(self):
        now = time.time()
        for t in list(self.ticks):
            if now - t["t0"] >= t["life"]:
                t["c"].destroy()
                self.ticks.remove(t)
                if not self.ticks:
                    self.layout()
            else:
                self._draw_tick(t)
        self.root.after(1000, self._tick_ticker)

    # ----- 킥오프 버튼 -----
    def show_kickoff(self, on: bool):
        self._kick_on = on
        if on:
            self._draw_kickoff()
            self.kick.place(relx=0.5, rely=0.45, anchor="center")
            self.kick.tk.call("raise", self.kick._w)   # Canvas.lift는 도형용이라 창 자체를 올림
        else:
            self.kick.place_forget()

    def _draw_kickoff(self, hover: bool = False):
        c = self.kick
        c.delete("all")
        bg = CHROMA if self.app.cfg.get("chroma") else BG
        W, H, bh = self.px(240), self.px(118), self.px(64)
        c.configure(width=W, height=H, bg=bg)
        self.rrect(c, 2, 2, W - 2, bh, bh / 2, fill=KICK_RED_HOVER if hover else KICK_RED, outline="")
        c.create_text(W / 2, bh / 2 + 1, text="⚽  킥오프", font=self.f["kick"], fill="#ffffff")
        c.create_text(W / 2, bh + self.px(26), text="경기가 시작되면 눌러 주세요\n누르면 채팅이 시작돼요",
                      font=self.f["small"], fill="#ffffff" if bg == CHROMA else FG2, justify="center")

    # ----- 아래로 이동 버튼 -----
    def _draw_jump(self):
        c = self.jump
        c.delete("all")
        n = self.px(40)
        bg = CHROMA if self.app.cfg.get("chroma") else BG
        c.configure(bg=bg)
        c.create_oval(1, 1, n - 1, n - 1, fill="#272727", outline="#3f3f3f")
        a = self.px(7)
        c.create_line(n / 2 - a, n / 2 - a / 2, n / 2, n / 2 + a / 2, n / 2 + a, n / 2 - a / 2, fill=FG, width=self.px(2), capstyle="round", joinstyle="round")

    def _on_scroll(self, first, last):
        show = float(last) < 0.995 and not self.app.cfg.get("chroma")
        if show and not self._jump_on:
            self.jump.place(relx=0.5, rely=1.0, y=-self.px(12), anchor="s")
        elif not show and self._jump_on:
            self.jump.place_forget()
        self._jump_on = show

    def scroll_end(self):
        self.text.yview_moveto(1.0)

    # ----- 입력창: 방장이 직접 채팅을 치면 시청자들이 반응함 (fake-twitch-chat의 "채팅에 말 걸기") -----
    def build_composer(self):
        cp = self.composer
        for w in cp.winfo_children():
            w.destroy()
        name = self.app.cfg.get("streamer_name") or "방장"
        tk.Frame(cp, bg=LINE, height=1).pack(fill="x")
        inner = tk.Frame(cp, bg=BG)
        inner.pack(fill="x", padx=self.px(16), pady=(self.px(12), self.px(8)))
        top = tk.Frame(inner, bg=BG)
        top.pack(fill="x")
        tk.Label(top, image=self.avatar(name, self.px(24), self.px(16)), bg=BG).pack(side="left")
        tk.Label(top, text=name, bg=BG, fg=FG2, font=self.f["author"]).pack(side="left")
        field = tk.Frame(inner, bg=BG)
        field.pack(fill="x", padx=(self.px(40), 0), pady=(self.px(6), 0))
        self.entry_var = tk.StringVar()
        self.entry = tk.Entry(field, textvariable=self.entry_var, bg=BG, fg=FG, insertbackground=FG, relief="flat",
                              bd=0, highlightthickness=0, font=self.f["input"])
        self.entry.pack(fill="x")
        hint = tk.Label(field, text="채팅...", bg=BG, fg="#717171", font=self.f["input"], anchor="w", cursor="xterm")
        underline = tk.Frame(field, bg="#717171", height=1)
        underline.pack(fill="x", pady=(self.px(4), 0))
        foot = tk.Frame(inner, bg=BG)
        foot.pack(fill="x", padx=(self.px(34), 0), pady=(self.px(6), 0))
        tk.Label(foot, text="☺", bg=BG, fg=FG2, font=self.f["title"]).pack(side="left")
        send = tk.Label(foot, text="➤", bg=BG, fg="#717171", font=self.f["title"], cursor="hand2")
        send.pack(side="right")
        count = tk.Label(foot, text="0/200", bg=BG, fg="#717171", font=self.f["small"])
        count.pack(side="right", padx=self.px(8))

        def show_hint():
            try:
                focused = self.root.focus_get() is self.entry
            except (KeyError, tk.TclError):     # 메뉴가 열려 있으면 focus_get이 실패할 수 있음
                focused = False
            if not self.entry_var.get() and not focused:
                hint.place(in_=self.entry, x=0, rely=0.5, anchor="w")
            else:
                hint.place_forget()

        def changed(*_):
            v = self.entry_var.get()
            if len(v) > 200:
                self.entry_var.set(v[:200])
                return
            count.configure(text=f"{len(v)}/200")
            send.configure(fg="#3ea6ff" if v.strip() else "#717171")
            show_hint()

        def submit(_e=None):
            v = self.entry_var.get().strip()
            if v:
                self.entry_var.set("")
                self.app.send_user_chat(v)
            return "break"

        self.entry_var.trace_add("write", changed)
        self.entry.bind("<Return>", submit)
        self.entry.bind("<FocusIn>", lambda e: (hint.place_forget(), underline.configure(bg="#3ea6ff")))
        self.entry.bind("<FocusOut>", lambda e: (show_hint(), underline.configure(bg="#717171")))
        hint.bind("<Button-1>", lambda e: self.entry.focus_set())
        send.bind("<Button-1>", submit)
        self.root.after(50, show_hint)

    # ----- 메시지 넣기 -----
    def add(self, m: dict):
        # 같은 문장이 연달아 나오면 건너뜀 (진짜 채팅처럼)
        if m["kind"] in ("normal", "member", "mod"):
            recent = getattr(self, "_recent", [])
            # 골 직후 짧은 외침("골!!!!")은 여러 사람이 똑같이 도배하는 게 자연스러움
            if m["text"] in recent and not (len(m["text"]) <= 8 and self.app.cur_hype() > 1.5):
                return
            self._recent = (recent + [m["text"]])[-25:]
        t = self.text
        at_bottom = t.yview()[1] >= 0.98
        t.configure(state="normal")
        s = self.fs()
        if m["kind"] in ("super", "newmember"):
            c = tk.Canvas(t, bg=BG, highlightthickness=0, bd=0)
            self._draw_card(c, m)
            a = t.index("end-1c")
            t.window_create("end", window=c, padx=self.px(16))
            t.insert("end", "\n")
            t.tag_add("card", a, "end-1c")
            self.cards.append((c, m))
            if m["kind"] == "super":
                self.add_tick(m)
        else:
            a = t.index("end-1c")
            t.image_create("end", image=self.avatar(m["name"], self.px(24 * s), self.px(16)), align="center")
            tag = m["kind"] if m["kind"] in ("member", "mod", "owner") else "author"
            t.insert("end", f" {m['name']} " if m["kind"] == "owner" else m["name"], (tag,))
            b = self.badge(m["kind"]) if m["kind"] in ("member", "mod") else None
            if b is not None:
                t.image_create("end", image=b, align="center")
            t.image_create("end", image=self.spacer(self.px(8)), align="center")
            t.insert("end", m["text"], ("msg",))
            t.insert("end", "\n")
            t.tag_add("line", a, "end-1c")
        lines = int(t.index("end-1c").split(".")[0])
        if lines > 600:
            t.delete("1.0", "201.0")
            self._redraw_cards()
        t.configure(state="disabled")
        if at_bottom:
            t.update_idletasks()
            t.yview_moveto(1.0)

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        self._redraw_cards()

    def set_viewers(self, n: int):
        self.lbl_viewers.configure(text=f"{n:,}명 시청 중" if self.app.cfg.get("show_viewers", True) else "")

    def set_state(self, text: str):
        self.lbl_state.configure(text=text)

    def set_transcript(self, text: str):
        self.lbl_trans.configure(text=("해설: " + text) if text else "")

    def set_level(self, v: float):
        w = self.level.winfo_width()
        self.level.coords(self._level_bar, 0, 0, int(min(1.0, v * 6) * w), self.px(3))

    # ----- 메뉴 -----
    def build_menu(self):
        """사람이 직접 해야 하는 것만 남김. 나머지(속도, 글자 크기, 명단 크기·배치, 중립 비율, OBS 초록 배경,
        채팅·기록 지우기 등)는 App.auto_settings()와 경기 흐름에 따라 자동으로 정해짐."""
        cfg = self.app.cfg
        m = tk.Menu(self.root, tearoff=0, font=self.f["small"])
        self.v_trans = tk.BooleanVar(value=cfg.get("show_transcript", False))

        def toggle_trans():
            cfg["show_transcript"] = self.v_trans.get()
            save_cfg(cfg)
            self.apply_theme()

        def toggle(key, var, after=None):
            cfg[key] = var.get()
            save_cfg(cfg)
            if after:
                after()

        m.add_command(label="선발 명단 설정…", command=self.app.open_lineup_editor)
        m.add_command(label="선수 기록 넣기 (골·카드·교체)…", command=self.app.open_mark_dialog)
        m.add_command(label="팀 직접 정하기…", command=self.app.open_team_dialog)
        m.add_separator()
        # 채팅 분위기·세기 (fake-twitch-chat의 모드·강도)
        self.v_mode = tk.StringVar(value=cfg.get("chat_mode", "default"))
        self.v_int = tk.IntVar(value=int(cfg.get("chat_intensity", 5)))
        mm = tk.Menu(m, tearoff=0, font=self.f["small"])
        for key, label in CHAT_MODES.items():
            mm.add_radiobutton(label=label, value=key, variable=self.v_mode, command=lambda: toggle("chat_mode", self.v_mode))
        mm.add_separator()
        mi = tk.Menu(mm, tearoff=0, font=self.f["small"])
        for n in range(11):
            mi.add_radiobutton(label=f"{n}" + ("  (거의 티 안 남)" if n == 0 else "  (한계까지)" if n == 10 else ""),
                               value=n, variable=self.v_int, command=lambda: toggle("chat_intensity", self.v_int))
        mm.add_cascade(label="분위기 세기", menu=mi)
        m.add_cascade(label="채팅 분위기", menu=mm)
        m.add_command(label="내 채팅 이름…", command=self.app.open_name_dialog)
        m.add_command(label="채팅 캡처 저장 (최근 12줄)", command=self.app.save_clip)
        m.add_separator()
        # 해설 자막 (realtime-captions-system-audio)
        self.v_caps = tk.BooleanVar(value=cfg.get("show_captions", True))
        self.v_save = tk.BooleanVar(value=cfg.get("save_transcript", False))
        m.add_checkbutton(label="게임 위에 해설 자막 띄우기", variable=self.v_caps,
                          command=lambda: toggle("show_captions", self.v_caps, self.app.captions.refresh))
        m.add_checkbutton(label="채팅 창 아래에 해설 자막 보기", variable=self.v_trans, command=toggle_trans)
        m.add_checkbutton(label="받아쓴 해설을 파일로 저장 (transcripts 폴더)", variable=self.v_save,
                          command=lambda: toggle("save_transcript", self.v_save))
        m.add_separator()
        m.add_command(label="종료", command=self.app.quit)
        self.menu = m

    def popup(self, e):
        try:
            self.menu.tk_popup(e.x_root, e.y_root)
        finally:
            self.menu.grab_release()


# ---------------------------------------------------------------------------
# 선발 명단 오버레이 (화면 왼쪽 아래) - 라리가 중계 그래픽 느낌
# ---------------------------------------------------------------------------
KEY_COLOR = "#010203"
LL_CORAL = "#FF4B44"
LL_CARD = "#0d1016"
LL_PITCH = "#161a22"
LL_PITCH2 = "#1a1f28"
LL_LINE = "#3a414f"
SUB_GREEN = "#39e75f"
LIGHT_KITS = ("#ffffff", "#fff", "#f5f5f5", "#fafafa", "#ffca28", "#ffd400", "#ffeb3b", "#f5a200", "#ffb300")


def formation_rows(formation: str) -> list[int]:
    nums = [int(x) for x in re.findall(r"\d", formation or "")]
    if sum(nums) != 10 or not nums:
        nums = [4, 3, 3]
    return nums


def formation_positions(formation: str) -> list[tuple[float, float]]:
    """(x, y) 0~1, y=0 우리 골문, y=1 상대 골문. 순서: GK, 뒤쪽 줄부터 왼쪽→오른쪽."""
    rows = formation_rows(formation)
    pos = [(0.5, 0.02)]
    n = len(rows)
    for i, k in enumerate(rows):
        y = 0.22 + (0.95 - 0.22) * (i / max(1, n - 1))
        if k == 2:
            xs = [0.27, 0.73]
        elif k == 3:
            xs = [0.1, 0.5, 0.9] if i == n - 1 else [0.2, 0.5, 0.8]
        elif k == 1:
            xs = [0.5]
        else:
            xs = [0.04 + 0.92 * j / (k - 1) for j in range(k)]
        for j in range(k):
            x = xs[j]
            yy = y
            if i == n - 1 and k == 3:           # 공격 3명: 양쪽 윙은 조금 아래
                yy = y if j == 1 else y - 0.07
            if 0 < i < n - 1 and k >= 4 and j in (0, k - 1):   # 미드 4명 이상: 양쪽은 조금 위
                yy = y + 0.02
            pos.append((x, min(0.95, yy)))
    return pos


def row_labels(formation: str) -> list[str]:
    rows = formation_rows(formation)
    if len(rows) == 3:
        names = ["수비", "미드", "공격"]
    elif len(rows) == 4:
        names = ["수비", "수비형 미드", "공격형 미드", "공격"]
    else:
        names = ["수비"] + ["미드"] * (len(rows) - 2) + ["공격"]
    out = ["골키퍼"]
    for i, k in enumerate(rows):
        for j in range(k):
            out.append(f"{names[min(i, len(names) - 1)]} {j + 1}")
    return out


class LineupOverlay:
    """화면 왼쪽 아래 선발 명단. 초록 이름 = 교체된 선수(나간/들어온), 공 = 득점, 네모 = 카드.
    교체로 들어온 선수는 경기장 아래에 따로 보여 줌."""

    def __init__(self, app):
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.configure(bg=KEY_COLOR)
        try:
            self.win.attributes("-topmost", True)
            if IS_WIN:
                self.win.attributes("-transparentcolor", KEY_COLOR)
        except tk.TclError:
            pass
        self.cv = tk.Canvas(self.win, bg=KEY_COLOR, highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True)
        self.fam_ui = app.chat.ui
        self.fam_num = pick_font(app.root, "Bahnschrift SemiBold Condensed", "Bahnschrift", "Arial Narrow", "DejaVu Sans Condensed", self.fam_ui)
        self._click_through_done = False

    def _click_through(self):
        if not IS_WIN or self._click_through_done:
            return
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.win.winfo_id())
            GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW = -20, 0x80000, 0x20, 0x80
            st = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, st | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW)
            self._click_through_done = True
        except Exception:
            log.exception("click-through failed")

    # ----- 그리기 도구 -----
    def font(self, px, bold=True, fam=None):
        return (fam or self.fam_ui, -max(6, int(round(px * self.s))), "bold" if bold else "normal")

    def measure(self, text, fnt):
        key = (fnt, text)
        if not hasattr(self, "_mcache"):
            self._mcache = {}
        if key not in self._mcache:
            self._mcache[key] = tkfont.Font(family=fnt[0], size=fnt[1], weight=fnt[2]).measure(text)
        return self._mcache[key]

    def fit_name(self, name, max_w, base_px=12):
        """옆 선수와 겹치지 않게: 원래 이름 → 조금 작게 → 성(마지막 단어) → 더 작게 → 말줄임"""
        if max_w is None:
            return name, self.font(base_px)
        for px in (base_px, base_px * 0.9, base_px * 0.8):
            f = self.font(px)
            if self.measure(name, f) <= max_w:
                return name, f
        parts = [x for x in name.split() if len(x) >= 2]
        if len(parts) >= 2:
            last = parts[-1]
            for px in (base_px, base_px * 0.9, base_px * 0.8):
                f = self.font(px)
                if self.measure(last, f) <= max_w:
                    return last, f
            name = last
        f = self.font(base_px * 0.8)
        cut = name
        while len(cut) > 1 and self.measure(cut + "…", f) > max_w:
            cut = cut[:-1]
        return (cut + "…" if cut != name else cut), f

    @staticmethod
    def rrect(cv, x1, y1, x2, y2, r, **kw):
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return cv.create_polygon(pts, smooth=True, **kw)

    def otext(self, x, y, text, font, fill="#ffffff", outline="#000000", w=1, **kw):
        """테두리 있는 글자 (방송 그래픽처럼)"""
        for dx in (-w, 0, w):
            for dy in (-w, 0, w):
                if dx or dy:
                    self.cv.create_text(x + dx, y + dy, text=text, font=font, fill=outline, **kw)
        self.cv.create_text(x, y, text=text, font=font, fill=fill, **kw)

    def shirt(self, x, y, w, color, trim):
        h = w * 0.92
        l, t = x - w / 2, y - h / 2
        pts = [
            l + w * 0.30, t, l + w * 0.40, t + h * 0.09, l + w * 0.60, t + h * 0.09, l + w * 0.70, t,
            l + w, t + h * 0.18, l + w * 0.88, t + h * 0.44, l + w * 0.78, t + h * 0.38,
            l + w * 0.78, t + h, l + w * 0.22, t + h, l + w * 0.22, t + h * 0.38,
            l + w * 0.12, t + h * 0.44, l, t + h * 0.18,
        ]
        self.cv.create_polygon(pts, fill=color, outline=trim, width=max(1, int(w / 20)), joinstyle="round")

    def ball(self, x, y, r):
        cv = self.cv
        cv.create_oval(x - r, y - r, x + r, y + r, fill="#ffffff", outline="#111111", width=max(1, int(r / 6)))
        k = r * 0.38
        cv.create_polygon(x, y - k, x + k * 0.95, y - k * 0.3, x + k * 0.6, y + k * 0.8, x - k * 0.6, y + k * 0.8, x - k * 0.95, y - k * 0.3, fill="#111111")
        for ang in (-90, -18, 54, 126, 198):
            a = math.radians(ang)
            ex, ey = x + math.cos(a) * r * 0.95, y + math.sin(a) * r * 0.95
            cv.create_line(x + math.cos(a) * k, y + math.sin(a) * k, ex, ey, fill="#111111", width=max(1, int(r / 7)))

    def card(self, x, y, s, red=False):
        self.cv.create_rectangle(x, y, x + 9 * s, y + 12 * s, fill="#e53935" if red else "#ffd400", outline="#111111", width=1)

    def player(self, cx, cy, sw, color, p, mk, s, max_w=None):
        s = self.s
        light = color.lower() in LIGHT_KITS
        trim = "#111111" if light else "#ffffff"
        self.shirt(cx, cy, sw, color, trim)
        num = str(p.get("no", "")).strip()
        if num:
            self.otext(cx, cy + 3 * s, num, self.font(21, fam=self.fam_num),
                       fill="#111111" if light else "#ffffff", outline="#ffffff" if light else "#111111", w=max(1, int(1.2 * s)))
        name = p.get("name", "")
        if name:
            subbed = mk.get("off") or mk.get("on")
            name, fnt = self.fit_name(name, max_w)
            self.otext(cx, cy + sw * 0.5 + 9 * s, name, fnt,
                       fill=SUB_GREEN if subbed else "#ffffff", outline="#000000", w=max(1, int(1.2 * s)))
        # 득점: 유니폼 오른쪽 위에 축구공 (여러 골이면 겹쳐서)
        g = int(mk.get("goals", 0))
        for i in range(min(3, g)):
            self.ball(cx + sw * 0.42 - i * 9 * s, cy - sw * 0.62, 7.5 * s)
        # 카드: 유니폼 오른쪽 어깨
        if mk.get("red") or mk.get("yellow"):
            self.card(cx + sw * 0.5 - (4 * s if g else 0), cy - sw * 0.42 + (6 * s if g else 0), s, red=bool(mk.get("red")))

    # ----- 팀 카드 -----
    def team_size(self, key, W, s):
        lu = self.app.match.lineup(key)
        pad = int(12 * s)
        head_h = int(42 * s)
        pw = W - pad * 2
        ph = int(pw * 1.5)
        subs_on = self.subs_on(key)
        extra = int(78 * s) if subs_on else 0
        return head_h + ph + pad + extra + pad, head_h, pad, pw, ph

    def subs_on(self, key):
        m = self.app.match
        lu = m.lineup(key) or {}
        marks = m.marks.get(m.side(key).label, {})
        return [b for b in lu.get("bench", []) if b.get("name") and marks.get(b["name"], {}).get("on")]

    def draw_team(self, x0, y0, W, key, s):
        cv = self.cv
        m = self.app.match
        side = m.side(key)
        lu = m.lineup(key)
        color = lu.get("color") or side.color
        formation = lu.get("formation", "4-3-3")
        marks = m.marks.get(side.label, {})
        H, head_h, pad, pw, ph = self.team_size(key, W, s)
        # 카드 바탕
        self.rrect(cv, x0, y0, x0 + W, y0 + H, int(14 * s), fill=LL_CARD, outline="")
        # 머리: 코랄 탭 + 팀 약칭 + 포메이션 알약
        tab_w = int(6 * s)
        self.rrect(cv, x0 + pad, y0 + int(11 * s), x0 + pad + tab_w, y0 + head_h - int(9 * s), int(3 * s), fill=LL_CORAL, outline="")
        pill_f = self.font(13, fam=self.fam_num)
        ftw = self.measure(formation, pill_f) + 16 * s
        title_max = W - pad * 2 - tab_w - int(8 * s) - ftw - int(8 * s)
        title, tf = self.fit_name(f"{side.short} 포메이션", title_max, base_px=16)
        cv.create_text(x0 + pad + tab_w + int(8 * s), y0 + head_h / 2 + 1, text=title, anchor="w", fill="#ffffff", font=tf)
        self.rrect(cv, x0 + W - pad - ftw, y0 + head_h / 2 - 9 * s, x0 + W - pad, y0 + head_h / 2 + 9 * s, int(9 * s), fill="#ffffff", outline="")
        cv.create_text(x0 + W - pad - ftw / 2, y0 + head_h / 2, text=formation, fill="#111111", font=pill_f)
        cv.create_rectangle(x0 + pad, y0 + head_h - 3 * s, x0 + W - pad, y0 + head_h - 1 * s, fill=color, outline="")
        # 경기장
        px, py = x0 + pad, y0 + head_h + int(4 * s)
        self.rrect(cv, px, py, px + pw, py + ph, int(8 * s), fill=LL_PITCH, outline="")
        for i in range(1, 8, 2):
            cv.create_rectangle(px + 2, py + ph * i / 8, px + pw - 2, py + ph * (i + 1) / 8, fill=LL_PITCH2, outline="")
        lw = max(1, int(1.5 * s))
        ins = 7 * s
        cv.create_rectangle(px + ins, py + ins, px + pw - ins, py + ph - ins, outline=LL_LINE, width=lw)
        cv.create_line(px + ins, py + ph / 2, px + pw - ins, py + ph / 2, fill=LL_LINE, width=lw)
        rr = pw * 0.15
        cv.create_oval(px + pw / 2 - rr, py + ph / 2 - rr, px + pw / 2 + rr, py + ph / 2 + rr, outline=LL_LINE, width=lw)
        cv.create_oval(px + pw / 2 - 2 * s, py + ph / 2 - 2 * s, px + pw / 2 + 2 * s, py + ph / 2 + 2 * s, fill=LL_LINE, outline="")
        for top in (True, False):
            bw, bh = pw * 0.58, ph * 0.14
            gw, gh = pw * 0.28, ph * 0.05
            yb = py + ins if top else py + ph - ins
            sg = 1 if top else -1
            cv.create_rectangle(px + pw / 2 - bw / 2, yb, px + pw / 2 + bw / 2, yb + sg * bh, outline=LL_LINE, width=lw)
            cv.create_rectangle(px + pw / 2 - gw / 2, yb, px + pw / 2 + gw / 2, yb + sg * gh, outline=LL_LINE, width=lw)
        # 선발 11명
        sw = 36 * s
        players = (lu.get("players") or [])[:11]
        span = pw - 2 * ins - sw * 1.1
        spots = []
        for i, (fx, fy) in enumerate(formation_positions(formation)):
            if i >= len(players):
                break
            cx = px + ins + sw * 0.55 + fx * span
            cy = py + ph - ins - sw * 0.5 - fy * (ph - 2 * ins - sw * 1.45)
            spots.append((cx, cy, players[i]))
        name_y = lambda y: y + sw * 0.5 + 9 * s
        for i, (cx, cy, p) in enumerate(spots):
            if not p.get("name") and not p.get("no"):
                continue
            # 이름 줄 높이가 겹치는 이웃 중 가장 가까운 선수까지의 거리로 이름 폭 제한
            near = [abs(cx - ox) for j, (ox, oy, _) in enumerate(spots) if j != i and abs(name_y(cy) - name_y(oy)) < 16 * s]
            max_w = (min(near) - 6 * s) if near else (pw - 8 * s)
            max_w = min(max_w, pw - 8 * s)
            if cx - max_w / 2 < px + 2 * s:                 # 경기장 밖으로 안 나가게
                max_w = 2 * (cx - px - 2 * s)
            if cx + max_w / 2 > px + pw - 2 * s:
                max_w = 2 * (px + pw - 2 * s - cx)
            self.player(cx, cy, sw, color, p, marks.get(p.get("name", ""), {}), s, max_w)
        # 교체로 들어온 선수: 경기장 아래 오른쪽부터
        on = self.subs_on(key)
        if on:
            by = py + ph + int(12 * s) + sw * 0.5
            cv.create_text(px, by - sw * 0.1, text="교체 투입", anchor="w", fill="#9aa3b2", font=self.font(12))
            step = sw * 1.9
            shown = on[:4]
            for i, b in enumerate(shown):
                cx = px + pw - sw * 0.7 - (len(shown) - 1 - i) * step
                self.player(cx, by, sw, color, b, marks.get(b["name"], {}), s, step - 6 * s)
        return H

    def render(self):
        cv = self.cv
        cv.delete("all")
        keys = [k for k in ("home", "away") if self.app.match.lineup(k)]
        if not keys or not self.app.session_on:
            self.win.withdraw()
            return
        mon, _ = primary_monitor()
        mw0 = mon["width"] if mon else self.app.root.winfo_screenwidth()
        mh0 = mon["height"] if mon else self.app.root.winfo_screenheight()
        # 크기: 1080p 화면 기준으로 해상도에 맞춰 (화면 배율도 반영)
        k = self.app.k
        s = max(0.8 * k, min(1.4 * k, mh0 / 1080))
        self.s = s
        W = int(280 * s)
        gap = int(12 * s)
        # 배치: 가로로 나란히 두면 화면 폭의 45%를 넘을 때만 세로로 쌓기
        column = len(keys) > 1 and (len(keys) * W + gap) > mw0 * 0.45
        x = y = 0
        tw = th = 0
        for k in keys:
            h = self.draw_team(x, y, W, k, s)
            if column:
                y += h + gap
                tw, th = W, y - gap
            else:
                x += W + gap
                tw, th = x - gap, max(th, h)
        mon, _ = primary_monitor()
        if mon:
            left, top, mw, mh = mon["left"], mon["top"], mon["width"], mon["height"]
        else:
            left, top, mw, mh = 0, 0, self.app.root.winfo_screenwidth(), self.app.root.winfo_screenheight()
        margin = int(24 * s)
        self.win.geometry(f"{tw}x{th}+{left + margin}+{max(top, top + mh - th - margin)}")
        cv.configure(width=tw, height=th)
        self.win.deiconify()
        self.win.lift()
        self.win.after(50, self._click_through)


class CaptionOverlay:
    """게임 위 화면 아래쪽에 뜨는 해설 자막 (realtime-captions-system-audio의 자막 창).
    항상 위, 클릭은 뒤 게임으로 통과, 작업 표시줄에 안 보임, 조용하면 사라짐.
    말하는 중에는 노란 미리보기 자막, 문장이 끝나면 흰 최종 자막으로 바뀜."""
    HIDE_AFTER = 5.0      # 마지막 자막 뒤 이만큼 조용하면 숨김 (초)

    def __init__(self, app):
        self.app = app
        k = app.k
        self.win = tk.Toplevel(app.root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.configure(bg="#0b0b0b")
        try:
            self.win.attributes("-topmost", True)
            self.win.attributes("-alpha", 0.85)
        except tk.TclError:
            pass
        fam = app.chat.ui
        self.lbl = tk.Label(self.win, text="", bg="#0b0b0b", fg="#ffffff", font=(fam, -int(24 * k), "bold"),
                            justify="center", padx=int(24 * k), pady=int(10 * k))
        self.lbl.pack(fill="both", expand=True)
        self.last = 0.0
        self.shown = False
        self._click_through_done = False
        self.app.root.after(500, self._tick)

    def _click_through(self):
        if not IS_WIN or self._click_through_done:
            return
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.win.winfo_id())
            GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW = -20, 0x80000, 0x20, 0x80
            st = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, st | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW)
            self._click_through_done = True
        except Exception:
            log.exception("caption click-through failed")

    def enabled(self) -> bool:
        return bool(self.app.cfg.get("show_captions", True)) and self.app.session_on

    def show(self, text: str, partial: bool = False):
        if not self.enabled() or not text:
            return
        self.lbl.configure(text=text, fg="#ffe57f" if partial else "#ffffff")
        self.last = time.time()
        self._place()
        if not self.shown:
            self.win.deiconify()
            self.shown = True
        self.win.lift()
        self.win.after(50, self._click_through)

    def _place(self):
        k = self.app.k
        mon, _ = primary_monitor()
        if mon:
            left, top, mw, mh = mon["left"], mon["top"], mon["width"], mon["height"]
        else:
            left, top, mw, mh = 0, 0, self.app.root.winfo_screenwidth(), self.app.root.winfo_screenheight()
        # 왼쪽 아래 선발 명단, 같은 모니터 오른쪽의 채팅 창과 겹치지 않는 가운데 빈 곳에
        lo, hi, gap = left, left + mw, int(16 * k)
        for w_, is_left in ((self.app.overlay.win, True), (self.app.root, False)):
            try:
                if not w_.winfo_ismapped():
                    continue
                x0, x1 = w_.winfo_rootx(), w_.winfo_rootx() + w_.winfo_width()
            except tk.TclError:
                continue
            if left <= x0 < left + mw:
                if is_left and x1 < left + mw * 0.5:
                    lo = max(lo, x1 + gap)
                elif not is_left and x0 > left + mw * 0.5:
                    hi = min(hi, x0 - gap)
        w = max(int(320 * k), min(int(mw * 0.72), int(1100 * k), hi - lo - 2 * gap))
        self.lbl.configure(wraplength=w - int(48 * k))
        self.win.update_idletasks()
        h = min(self.lbl.winfo_reqheight(), int(mh * 0.25))
        x = max(left, min(left + mw - w, lo + (hi - lo - w) // 2))
        self.win.geometry(f"{w}x{h}+{x}+{top + mh - h - int(110 * k)}")

    def hide(self):
        if self.shown:
            self.win.withdraw()
            self.shown = False

    def refresh(self):
        if not self.enabled():
            self.hide()

    def _tick(self):
        if self.shown and (time.time() - self.last > self.HIDE_AFTER or not self.enabled()):
            self.hide()
        self.app.root.after(500, self._tick)


class MarkDialog:
    """받아쓰기가 놓친 골·카드·교체를 직접 표시"""

    def __init__(self, app):
        self.app = app
        t = tk.Toplevel(app.root)
        t.title("선수 기록 넣기")
        t.attributes("-topmost", True)
        t.configure(padx=14, pady=12)
        self.t = t
        self.side = tk.StringVar(value="home")
        row = tk.Frame(t)
        row.pack(fill="x")
        for key in ("home", "away"):
            ttk.Radiobutton(row, text=app.match.side(key).label, value=key, variable=self.side, command=self.refresh).pack(side="left", padx=4)
        self.player = ttk.Combobox(t, width=24, state="readonly")
        self.player.pack(fill="x", pady=8)
        btns = tk.Frame(t)
        btns.pack(fill="x")
        for label, what in (("⚽ 골", "goal"), ("골 취소", "ungoal"), ("경고", "yellow"), ("퇴장", "red"),
                            ("교체로 나감", "off"), ("교체로 들어옴", "on"), ("표시 지우기", "clear")):
            ttk.Button(btns, text=label, command=lambda w=what: self.apply(w)).pack(side="left", padx=2, pady=2)
        self.refresh()

    def refresh(self):
        names = self.app.match.lineup_names(self.side.get())
        self.player.configure(values=names)
        if names:
            self.player.current(0)

    def apply(self, what):
        name = self.player.get()
        if not name:
            return
        key = self.side.get()
        m = self.app.match
        mk = m.marks.setdefault(m.side(key).label, {}).setdefault(name, {"goals": 0, "yellow": 0, "red": False, "off": False, "on": False})
        if what == "goal":
            mk["goals"] += 1
            if name in [b.get("name") for b in (m.lineup(key) or {}).get("bench", [])]:
                mk["on"] = True
        elif what == "ungoal":
            mk["goals"] = max(0, mk["goals"] - 1)
        elif what == "yellow":
            m.mark(key, name, "yellow")
        elif what == "red":
            m.mark(key, name, "red")
        elif what in ("off", "on"):
            mk[what] = True
        elif what == "clear":
            m.marks[m.side(key).label].pop(name, None)
        self.app.refresh_overlay()


# ---------------------------------------------------------------------------
# 선발 명단 설정 창
# ---------------------------------------------------------------------------
PRESETS = ["4-3-3", "4-2-3-1", "4-4-2", "4-2-1-3", "4-1-4-1", "4-3-1-2", "3-5-2", "3-4-3", "3-4-2-1", "5-3-2", "5-4-1"]


class LineupEditor:
    def __init__(self, app):
        self.app = app
        m = app.match
        self.top = tk.Toplevel(app.root)
        self.top.title("선발 명단 설정")
        self.top.attributes("-topmost", True)
        self.top.configure(padx=14, pady=12)
        tk.Label(self.top, text="팀별로 포메이션과 등번호·이름을 적으면 화면 왼쪽 아래에 선발 명단이 뜹니다. 팀 이름별로 저장되어 다음 경기에도 그대로 쓰입니다.",
                 wraplength=760, justify="left").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        self.cols = {}
        for c, key in enumerate(("home", "away")):
            self.cols[key] = self.build_col(key, c)
        bar = tk.Frame(self.top)
        bar.grid(row=2, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(bar, text="닫기", command=self.top.destroy).pack(side="right", padx=4)
        ttk.Button(bar, text="저장하고 띄우기", command=self.save).pack(side="right", padx=4)

    def build_col(self, key, c):
        m = self.app.match
        side = m.side(key)
        lu = self.app.cfg.get("lineups", {}).get(side.label, {})
        fr = ttk.LabelFrame(self.top, text=f"{'홈' if key == 'home' else '원정'} · {side.label}", padding=10)
        fr.grid(row=1, column=c, sticky="n", padx=6)
        col = {"color": lu.get("color") or side.color}
        row = tk.Frame(fr)
        row.pack(fill="x", pady=(0, 6))
        tk.Label(row, text="포메이션").pack(side="left")
        fv = tk.StringVar(value=lu.get("formation", "4-3-3"))
        cb = ttk.Combobox(row, textvariable=fv, values=PRESETS, width=10)
        cb.pack(side="left", padx=6)
        swatch = tk.Label(row, text="  유니폼 색  ", bg=col["color"], fg="#ffffff", cursor="hand2")
        swatch.pack(side="right")

        def pick():
            c2 = colorchooser.askcolor(color=col["color"], parent=self.top)[1]
            if c2:
                col["color"] = c2
                swatch.configure(bg=c2)
        swatch.bind("<Button-1>", lambda e: pick())
        grid = tk.Frame(fr)
        grid.pack(fill="x")
        rows = []
        labels = []
        players = lu.get("players", [])
        for i in range(11):
            lb = tk.Label(grid, text="", width=11, anchor="w", fg="#666666")
            lb.grid(row=i, column=0, sticky="w")
            no = ttk.Entry(grid, width=4)
            no.grid(row=i, column=1, padx=4, pady=1)
            nm = ttk.Entry(grid, width=16)
            nm.grid(row=i, column=2, pady=1)
            if i < len(players):
                no.insert(0, str(players[i].get("no", "")))
                nm.insert(0, players[i].get("name", ""))
            rows.append((no, nm))
            labels.append(lb)

        def relabel(*_):
            for lb, t in zip(labels, row_labels(fv.get())):
                lb.configure(text=t)
        fv.trace_add("write", relabel)
        relabel()
        tk.Label(fr, text="교체 선수 (예: 6 아자이, 32 멘디)", anchor="w").pack(fill="x", pady=(8, 2))
        bench = ttk.Entry(fr, width=34)
        bench.pack(fill="x")
        bench.insert(0, ", ".join(f"{b.get('no', '')} {b.get('name', '')}".strip() for b in lu.get("bench", [])))
        col.update(formation=fv, rows=rows, bench=bench, label=side.label)
        return col

    def save(self):
        cfg = self.app.cfg
        for key, col in self.cols.items():
            old = cfg.get("lineups", {}).get(col["label"], {})
            old_en = {q.get("name"): q.get("en", "") for q in old.get("players", []) + old.get("bench", []) if q.get("en")}
            players = [{"no": no.get().strip(), "name": nm.get().strip()} for no, nm in col["rows"]]
            for q in players:                      # AI가 채운 영어 이름은 이름을 안 바꿨으면 그대로
                if q["name"] in old_en:
                    q["en"] = old_en[q["name"]]
            bench = []
            for part in re.split(r"[,，]", col["bench"].get()):
                part = part.strip()
                if not part:
                    continue
                mm = re.match(r"^(\d{1,2})\s*(.*)$", part)
                bench.append({"no": mm.group(1), "name": mm.group(2).strip()} if mm else {"no": "", "name": part})
            cfg.setdefault("lineups", {})[col["label"]] = {"formation": col["formation"].get().strip() or "4-3-3",
                                                           "players": players, "bench": bench, "color": col["color"]}
        save_cfg(cfg)
        self.app.refresh_overlay()
        self.top.destroy()


class NameDialog:
    """입력창에 쓴 내 채팅이 뜨는 이름"""

    def __init__(self, app):
        self.app = app
        t = tk.Toplevel(app.root)
        t.title("내 채팅 이름")
        t.attributes("-topmost", True)
        t.configure(padx=14, pady=12)
        self.t = t
        tk.Label(t, text="입력칸에 쓴 내 채팅이 이 이름(노란색)으로 뜹니다.").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        self.name = ttk.Entry(t, width=20)
        self.name.grid(row=1, column=0, sticky="w")
        self.name.insert(0, app.cfg.get("streamer_name") or "방장")
        self.name.bind("<Return>", lambda e: self.apply())
        ttk.Button(t, text="저장", command=self.apply).grid(row=1, column=1, sticky="e", padx=(8, 0))

    def apply(self):
        self.app.cfg["streamer_name"] = re.sub(r"\s+", " ", self.name.get()).strip()[:20] or "방장"
        save_cfg(self.app.cfg)
        self.app.chat.build_composer()
        self.t.destroy()


class TeamDialog:
    def __init__(self, app):
        self.app = app
        m = app.match
        t = tk.Toplevel(app.root)
        t.title("팀 직접 정하기")
        t.attributes("-topmost", True)
        t.configure(padx=14, pady=12)
        self.t = t
        tk.Label(t, text="자동 감지가 틀렸을 때 고치세요. 팬 수를 비워 두면 내장 자료(없으면 1000만 명)로 계산합니다.", wraplength=420, justify="left").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self.e = {}
        for r, key in enumerate(("home", "away"), start=1):
            tk.Label(t, text="홈 팀" if key == "home" else "원정 팀").grid(row=r, column=0, sticky="w")
            name = ttk.Entry(t, width=20)
            name.grid(row=r, column=1, padx=6, pady=3)
            name.insert(0, m.side(key).name)
            fans = ttk.Entry(t, width=10)
            fans.grid(row=r, column=2, pady=3)
            if m.side(key).fans:
                fans.insert(0, str(m.side(key).fans))
            self.e[key] = (name, fans)
        tk.Label(t, text="팀 이름                                   팬 수(백만)", fg="#666666").grid(row=3, column=1, columnspan=2, sticky="w")
        ttk.Button(t, text="적용", command=self.apply).grid(row=4, column=2, sticky="e", pady=(10, 0))

    def apply(self):
        for key, (name, fans) in self.e.items():
            n = name.get().strip()
            try:
                f = float(fans.get().strip()) if fans.get().strip() else None
            except ValueError:
                f = None
            self.app.set_team(key, n, fans=f, manual=True)
        self.app.teams_locked = True
        self.app.on_split_changed()
        self.t.destroy()


# ---------------------------------------------------------------------------
# 앱
# ---------------------------------------------------------------------------
class App:
    def __init__(self, args):
        self.args = args
        self.cfg = load_cfg()
        self.obs_on = False
        self.auto_settings()
        if LEARN_PATH.exists() and not args.demo:     # 예전 버전이 AI로 모은 문장·닉네임은 지움
            try:
                LEARN_PATH.unlink()
                log.info("removed old learned words: %s", LEARN_PATH)
            except OSError:
                log.exception("could not remove %s", LEARN_PATH)
        if IS_WIN:
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                pass
        self.root = tk.Tk()
        try:
            self.k = max(1.0, self.root.winfo_fpixels("1i") / 96.0)   # 윈도우 화면 배율 (100%=1.0, 150%=1.5)
        except Exception:
            self.k = 1.0
        self.bus: queue.Queue = queue.Queue()
        self.match = Match(self.cfg)
        self.engine = ChatEngine(self.match, self.cfg)
        self.chat = ChatWindow(self)
        self.overlay = LineupOverlay(self)
        self.captions = CaptionOverlay(self)
        self.transcript_file = None        # 받아쓴 해설 저장 파일 (킥오프마다 새 파일)
        self.session_on = False
        self.live = False                  # 킥오프 버튼을 눌렀는지 (눌러야 채팅이 나옴)
        self.kickoff_at = 0.0
        self.phase = "pre"                 # pre(킥오프 전) / play / half(하프타임) / ended
        self.last_react_at = 0.0
        self.demo_fed = False
        self.stt: AudioSTT | None = None
        self.board: BoardWatcher | None = None
        self.queue: list[tuple[float, dict]] = []   # (보여 줄 시각, 메시지) — 시각 순
        self.hype = 0.0                    # 큰 장면 직후 채팅이 몰리는 정도 (시간이 지나면 줄어듦)
        self.hype_t = time.time()
        self.chat_log: list[dict] = []       # 화면에 나온 채팅 (방장이 부른 닉네임 찾기, 채팅 캡처)
        self.viewers = 0
        self.last_seen: dict[str, float] = {}
        self.last_board_goal: dict | None = None   # {"side", "t", "scorer"} — 스코어보드가 본 마지막 골
        self.last_comm_goal_at = 0.0       # 해설에서 골이라고 반응한 때 (채팅만, 점수는 스코어보드로)
        self.hud_hist: list[tuple[float, str, str]] = []   # (시각, 팀, 선수) — 화면 아래 선수 표시 기록
        self.user_side_votes = {"home": 0, "away": 0}      # 선수 표시에 자주 나오는 팀 = 내가 조작하는 팀
        self.board_prev = None
        self.board_stable = None
        self.teams_known = False
        self.teams_locked = False
        self.alias_counts: dict[str, int] = {}
        self.pending_screen: dict | None = None      # 팀을 알기 전에 읽은 선발 라인업 화면
        self.pending_squad: dict | None = None       # 명단을 알기 전에 읽은 팀 관리 화면 (포메이션)
        self.pending_preview: dict | None = None     # 어느 팀인지 알기 전에 읽은 예상 라인업 화면 (상대 팀)
        self.place_chat_window()
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.root.after(100, self.poll)
        self.root.after(4000, self.tick_viewers)
        self.root.after(1000, self.watch_obs)
        if args.always or args.demo:
            self.root.after(300, self.start_session)
        else:
            self.root.withdraw()
            self.root.after(500, self.watch_game)
        if args.demo:
            self.root.after(1500, self.run_demo)

    # ----- 창 위치 -----
    def place_chat_window(self):
        prim, mons = primary_monitor()
        w = int(400 * self.k)
        if mons and len(mons) > 1 and prim:
            other = next(mo for mo in mons if mo is not prim)
            x, y, h = other["left"] + other["width"] - w, other["top"], other["height"] - 60
        elif prim:
            x, y, h = prim["left"] + prim["width"] - w - 8, prim["top"] + 40, prim["height"] - 120
        else:
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            x, y, h = sw - w - 8, 40, sh - 120
        self.root.geometry(f"{w}x{max(400, h)}+{x}+{y}")

    # ----- 게임 감지 -----
    def watch_game(self):
        def check():
            running = game_running()
            self.bus.put(("game", running))
        threading.Thread(target=check, daemon=True).start()
        self.root.after(3000, self.watch_game)

    def start_session(self):
        if self.session_on:
            return
        self.session_on = True
        log.info("session start")
        self.root.deiconify()
        self.chat.set_state("● 준비 중…")
        if not self.args.demo:
            self.stt = AudioSTT(self.cfg, self.bus, self.whisper_prompt)
            self.stt.start()
            self.board = BoardWatcher(self.cfg, self.bus,
                                      hud_fn=lambda: self.live and bool(self.match.lineup("home") or self.match.lineup("away")))
            self.board.start()
        self.viewers = int(self.match.viewer_floor() * (1 + random.random() * 0.12))
        self.chat.set_viewers(self.viewers)
        self.refresh_overlay()
        self.live = False
        self.chat.show_kickoff(True)

    def stop_session(self):
        if not self.session_on:
            return
        self.session_on = False
        self.live = False
        self.queue.clear()
        log.info("session stop")
        for th in (self.stt, self.board):
            if th:
                th.stop()
        self.stt = self.board = None
        self.captions.hide()
        self.close_transcript()
        self.teams_known = False
        self.teams_locked = False
        self.board_prev = self.board_stable = None
        self.match.reset_for_new_match()
        self.overlay.render()
        self.root.withdraw()

    # ----- 자동 설정 (메뉴에서 뺀 항목들) -----
    def auto_settings(self):
        c = self.cfg
        c["speed"] = "normal"         # 속도는 시청자 수와 장면으로
        c["always_on_top"] = True
        c["show_viewers"] = True
        c["show_composer"] = True
        c["chroma"] = self.obs_on     # OBS가 켜져 있으면 초록 배경
        c["neutral_pct"] = self.auto_neutral() if hasattr(self, "match") else 33

    def auto_neutral(self) -> int:
        """인기 팀끼리 붙으면 팬이 많아 중립이 적고, 작은 팀끼리면 중립이 많음"""
        total = self.match.home.fans_or_default + self.match.away.fans_or_default   # 백만 명
        return int(max(20, min(50, 45 - 8 * math.log10(max(1.0, total / 20)))))

    def watch_obs(self):
        def check():
            on = False
            try:
                import psutil
                for pr in psutil.process_iter(["name"]):
                    n = (pr.info.get("name") or "").lower()
                    if n.startswith("obs") or "streamlabs" in n:
                        on = True
                        break
            except Exception:
                pass
            self.bus.put(("obs", on))
        threading.Thread(target=check, daemon=True).start()
        self.root.after(5000, self.watch_obs)

    # ----- 킥오프 -----
    def kickoff(self):
        if not self.session_on or self.live:
            return
        self.live = True
        self.kickoff_at = time.time()
        self.phase = "play"
        log.info("kickoff pressed")
        self.chat.show_kickoff(False)
        # 새 경기: 지난 채팅과 선수 기록은 자동으로 지움
        self.chat.clear()
        self.close_transcript()            # 새 경기는 새 해설 파일
        self.match.marks.clear()
        self.match.events.clear()
        self.refresh_overlay()
        self.last_seen["kickoff"] = time.time()      # 해설의 "킥오프"와 겹쳐서 두 번 반응하지 않게
        self.match.push_event("킥오프")
        self.add_hype(1.5)
        self.enqueue(self.engine.react("kickoff", None, None, random.randint(5, 8)), 0.3, 5.0)
        # 킥오프 전에 느린 속도로 잡아 둔 다음 채팅 차례를 지금 속도로 다시 (누르자마자 채팅이 나오게)
        if getattr(self, "_tick_id", None):
            self.root.after_cancel(self._tick_id)
        self._tick_id = self.root.after(200, self.tick_chat)
        self.update_state_line()
        if self.args.demo and not self.demo_fed:
            self.demo_fed = True
            self.root.after(2500, self.demo_feed)

    def pause_chat(self, reason: str = ""):
        """경기가 끝났거나 새 경기가 시작되면 자동으로 킥오프 전으로"""
        if not self.live:
            return
        log.info("chat paused: %s", reason)
        self.phase = "pre"
        self.live = False
        self.queue.clear()
        self.chat.show_kickoff(True)
        log.info("chat paused")

    # ----- 팀 -----
    def set_team(self, key, name, fans=None, color=None, manual=False):
        side = self.match.side(key)
        t = lookup_team(name) if name else None
        side.name = t["ko"] if t else (name or "")
        side.fans = fans if (fans and fans > 0) else (t["fans"] if t else None)
        side.fans_manual = bool(manual and fans and fans > 0)
        if color and re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            side.color = color

    def teams_changed(self):
        self.teams_known = True
        self.match.reset_for_new_match()
        self.on_split_changed()
        self.refresh_overlay()
        if self.pending_screen:
            data, self.pending_screen = self.pending_screen, None
            self.on_lineup_screen(data)
        self.retry_preview()
        log.info("teams: %s vs %s", self.match.home.label, self.match.away.label)

    def on_split_changed(self):
        self.cfg["neutral_pct"] = self.auto_neutral()
        self.engine.crowd.rebuild()
        floor = self.match.viewer_floor()
        if self.viewers < floor or self.viewers > floor * 1.6:
            self.viewers = int(floor * (1 + random.random() * 0.12))
        self.chat.set_viewers(self.viewers)
        self.update_state_line()

    def resolve_code(self, code: str):
        cands = CODE_INDEX.get(code, [])
        if len(cands) <= 1:
            return cands[0] if cands else None
        return max(cands, key=lambda t: self.alias_counts.get(t["ko"], 0))

    # ----- 화면 갱신 -----
    def refresh_overlay(self):
        self.overlay.render()

    def update_state_line(self):
        if not self.session_on:
            return
        sp = self.match.split()
        self.chat.set_state(f"● {self.match.score_text()}   ·   팬 {self.match.home.label} {sp['home']:.0f}% / 중립 {sp['neutral']:.0f}% / {self.match.away.label} {sp['away']:.0f}%")

    def name_vocab(self) -> list[str]:
        m = self.match
        out = m.lineup_names("home") + m.lineup_names("away") + m.korean_names("home") + m.korean_names("away")
        for key in ("home", "away"):
            t = lookup_team(m.side(key).name) if m.side(key).name else None
            out += [m.side(key).name] + ([a for a in t["alias"] if HANGUL_WORD.match(a.replace(" ", ""))] if t else [])
        return [n for n in dict.fromkeys(out) if n]

    def whisper_prompt(self) -> tuple[str, str]:
        """(앞 문맥 힌트, 핫워드). 받아쓰기 스레드에서 부름."""
        m = self.match
        names = m.lineup_names("home")[:11] + m.lineup_names("away")[:11] + m.korean_names("home") + m.korean_names("away")
        names = list(dict.fromkeys(names))
        teams = f"{m.home.label} 대 {m.away.label}" if m.home.name or m.away.name else "축구"
        prompt = f"{teams} 경기 중계입니다."
        # 핫워드엔 영어 이름도 (해설자가 원어 발음으로 부르는 이름)
        hot = " ".join([m.home.name, m.away.name, *names, *m.lineup_en("home")[:11], *m.lineup_en("away")[:11]]).strip()
        return prompt, hot

    # ----- 메시지 처리 -----
    def enqueue(self, msgs, lo: float = 0.4, hi: float = 7.0):
        """반응마다 사람마다 다른 시간차를 줌: 짧은 외침은 바로, 긴 문장·후원은 조금 뒤에."""
        if not self.live:
            return
        now = time.time()
        for m in msgs:
            if m["kind"] == "super":
                d = random.uniform(2.5, 9.0)
            elif m["kind"] == "newmember":
                d = random.uniform(1.5, 8.0)
            else:
                d = lo + min(hi - lo, random.gammavariate(1.6, (hi - lo) / 5) + len(m.get("text", "")) * 0.06)
            self.queue.append((now + d, m))
        self.queue.sort(key=lambda q: q[0])

    def add_hype(self, v: float):
        self.hype = min(4.0, self.cur_hype() + v)
        self.hype_t = time.time()

    def cur_hype(self) -> float:
        return self.hype * math.exp(-(time.time() - self.hype_t) / 12.0)

    def chat_rate(self) -> float:
        """1초에 나오는 채팅 수. 시청자 1천 명 ≈ 0.3개, 3만 명 ≈ 1개, 30만 명 ≈ 2.2개, 100만 명 ≈ 3.3개."""
        base = 0.3 * (max(200, self.viewers / VIEWER_SCALE) / 1000) ** 0.35
        mult = SPEED_MULT.get(self.cfg.get("speed", "normal"), 1.0)
        # 경기 흐름: 하프타임·경기 뒤엔 뜸하고, 후반 막판엔 빨라짐
        if self.phase == "half":
            mult *= 0.55
        elif self.phase == "ended":
            mult *= 0.6
        elif (self.match.minute or 0) >= 80:
            mult *= 1.25
        return max(0.1, min(12.0, base * mult * (1 + self.cur_hype())))

    def emit(self, m: dict):
        self.chat.add(m)
        if m["kind"] in ("normal", "member", "mod", "owner"):
            self.chat_log = (self.chat_log + [{**m, "t": time.time()}])[-60:]
        now = time.time()
        for d, f in self.engine.followups(m, self.cur_hype()):
            self.queue.append((now + d, f))
        self.queue.sort(key=lambda q: q[0])

    def next_idle(self) -> dict | None:
        # 가끔 후원·새 멤버 (시청자가 많을수록 조금 더 자주)
        p = min(0.02, 0.003 * (max(1000, self.viewers / VIEWER_SCALE) / 100000) ** 0.5)
        r = random.random()
        if r < p:
            return self.engine.super_chat("idle")
        if r < p * 1.8:
            return self.engine.new_member()
        return self.engine.idle(self.phase)

    def tick_chat(self):
        """채팅 한 줄씩 내보내기. 간격은 무작위(푸아송)라 몰렸다 뜸했다 함."""
        if self.session_on and self.live:
            now = time.time()
            # 너무 늦어진 반응은 버림 (장면이 지나갔는데 뒤늦게 나오면 어색함)
            self.queue = [q for q in self.queue if now - q[0] < 12 or q[1]["kind"] == "super"]
            if self.queue and self.queue[0][0] <= now:
                self.emit(self.queue.pop(0)[1])
            elif not self.queue or random.random() < 0.25:
                m = self.next_idle()
                if m:
                    self.emit(m)
        gap = random.expovariate(self.chat_rate())
        self._tick_id = self.root.after(int(max(60, min(8000, gap * 1000))), self.tick_chat)

    def poll(self):
        try:
            while True:
                kind, data = self.bus.get_nowait()
                self.handle(kind, data)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def handle(self, kind, data):
        if kind == "game":
            if data and not self.session_on:
                self.start_session()
            elif not data and self.session_on:
                self.stop_session()
        elif kind == "text":
            self.on_commentary(data)
        elif kind == "partial":
            self.captions.show(data, partial=True)
            self.chat.set_transcript(data + " …")
        elif kind == "level":
            self.chat.set_level(data)
        elif kind == "stt_status":
            st, msg = data
            if st == "error":
                self.chat.set_state("● " + msg)
            elif st == "on":
                self.update_state_line()
            else:
                self.chat.set_state("● " + msg)
        elif kind == "board_status":
            log.info(data)
        elif kind == "board":
            self.on_board(data)
        elif kind == "hud":
            self.on_hud(data)
        elif kind == "squad_screen":
            self.on_squad_screen(data)
        elif kind == "lineup_screen":
            self.on_lineup_screen(data)
        elif kind == "preview_screen":
            self.on_preview_screen(data)
        elif kind == "obs":
            if data != self.obs_on:
                self.obs_on = data
                self.cfg["chroma"] = data
                log.info("obs %s -> chroma %s", "on" if data else "off", data)
                self.chat.apply_theme()

    def cooldown_ok(self, ev):
        now = time.time()
        if now - self.last_seen.get(ev, 0) < COOLDOWN.get(ev, 9):
            return False
        self.last_seen[ev] = now
        return True

    def on_commentary(self, text):
        m = self.match
        if len(re.findall(r"[가-힣]", text)) >= len(text.replace(" ", "")) * 0.5:
            text = fix_names(text, self.name_vocab())
        m.commentary.append((time.time(), text))
        m.commentary = m.commentary[-60:]
        self.chat.set_transcript(text)
        self.captions.show(text)
        self.write_transcript(text)
        for t in TEAMS:
            if names_in_text(text, [t["ko"], *t["alias"]]):
                self.alias_counts[t["ko"]] = self.alias_counts.get(t["ko"], 0) + 1
        # 스코어보드로 팀을 못 찾으면 해설에서 가장 많이 나온 두 팀
        if not self.teams_known and not self.teams_locked and len(m.commentary) >= 12:
            top = sorted(self.alias_counts.items(), key=lambda x: -x[1])[:2]
            if len(top) == 2 and top[1][1] >= 2:
                self.set_team("home", top[0][0])
                self.set_team("away", top[1][0])
                self.teams_changed()
        if not self.live:          # 킥오프 전에는 팀 찾기만 하고 채팅 반응은 안 함
            return
        self.react_to_commentary(text)

    def scene_actor(self, ev: str, text: str) -> tuple[str | None, str | None]:
        """해설 속 장면의 주인공 팀과 선수 (선수 이름 → 팀 이름 → 화면 아래 선수 표시 순서로)"""
        m = self.match
        side = player = None
        for key in ("home", "away"):
            hit = names_in_text(text, m.lineup_names(key) + m.korean_names(key))
            if hit:
                side, player = key, hit[0]
                break
        if side is None:
            for key in ("home", "away"):
                s = m.side(key)
                t = lookup_team(s.name) if s.name else None
                if s.name and names_in_text(text, [s.name, *(t["alias"] if t else [])]):
                    side = key
                    break
        if side is None and ev in ("chance", "shot", "dribble", "pass", "attack", "cross", "miss", "post"):
            bh = self.ball_holder()
            if bh:
                side, player = bh
        if ev == "save" and side and player:
            gk = (m.lineup_names(side) or [None])[0]
            if player != gk:               # 슈팅한 선수 이름이면 막은 쪽은 상대 팀
                side = m.other(side)
                player = None
        return side, player

    def react_to_commentary(self, text: str):
        """해설 한 문장 → 어떤 장면인지 단어로 찾고, 장면에 맞게 여러 사람이 반응"""
        m = self.match
        ev = detect_event(text)
        if ev is None:
            if random.random() < 0.5:          # 장면이 아니어도 선수 이름이 나오면 가끔 그 선수 이야기
                self.enqueue(self.engine.echo(text), 0.5, 4.0)
            return
        side, player = self.scene_actor(ev, text)
        variant = None
        if ev == "sub":
            for key in ("home", "away"):
                names = names_in_text(text, m.lineup_names(key))
                on = [nm for nm in names if m.is_bench(key, nm)]
                if names:
                    side, player = key, (on or names)[0]
                    variant = "sub_in" if on else "sub_out"
                    break
        self.last_react_at = time.time()
        log.info("scene: %s team=%s player=%s | %s", ev, side, player, text)
        if ev in ("yellow", "red") and side and player:
            self.mark_card(side, player, ev)
            self.refresh_overlay()
        if ev == "sub":
            for key in ("home", "away"):
                for nm in names_in_text(text, m.lineup_names(key)):
                    m.mark(key, nm, "on" if m.is_bench(key, nm) else "off")
            self.refresh_overlay()
        if not self.cooldown_ok(ev):
            if ev in BIG:                      # 같은 장면을 해설이 또 말함 → 몇 명만 더
                self.enqueue(self.engine.react(ev, side, player, random.randint(1, 3)), 0.3, 2.5)
            return
        desc = EV_DESC[ev] + (f" ({player})" if player else "")
        chat_desc = f"{player} {EV_DESC[ev]}" if player else EV_DESC[ev]
        self.engine.scene = {"ev": ev, "side": side, "player": player, "t": time.time(), "desc": chat_desc}
        if ev == "goal":
            self.last_comm_goal_at = time.time()    # 점수는 스코어보드가 셈. 여기서는 채팅만.
        else:
            m.push_event(desc)
        self.add_hype(HYPE.get(ev, 0.3))
        if ev in BIG:
            self.bump_viewers()
        if ev == "half":
            self.phase = "half"
        elif ev == "kickoff":
            self.phase = "play"
        elif ev == "end":
            self.phase = "ended"
            ko = self.kickoff_at
            # 2분 뒤 킥오프 전으로 (그 사이 새 경기 킥오프를 눌렀으면 건드리지 않음)
            self.root.after(120000, lambda: self.kickoff_at == ko and self.pause_chat("경기 종료"))
        lo, hi = REACT_N.get(ev, (1, 3))
        n = random.randint(lo, hi)
        if ev in ("half", "end"):
            msgs = self.engine.phase_lines(ev, n)
            if ev == "end" and random.random() < 0.7:
                sc = self.engine.super_chat("end")
                if sc:
                    msgs.append(sc)
        else:
            msgs = self.engine.react(ev, side, player, n, variant)
        if ev == "goal" and side:
            msgs += self.engine.chant(side, player, random.randint(3, 6))
        self.enqueue(msgs, 0.1, 2.5 if ev in BIG else 4.0)
        if ev not in BIG and random.random() < 0.3:
            self.enqueue(self.engine.echo(text), 1.0, 5.0)

    def resolve_player(self, name: str, side: str | None = None) -> tuple[str | None, str | None]:
        """AI가 말한 선수 이름(한글이든 영어든)을 선발 명단의 (팀, 이름)으로"""
        name = str(name or "").strip()
        if not name:
            return None, None
        for key in [k for k in (side, "home", "away") if k in ("home", "away")]:
            for q in self.match.lineup_people(key):
                cands = [q["name"]] + ([q["en"]] if q.get("en") else [])
                if names_in_text(name, cands) or any(c in name or name in c for c in cands):
                    return key, q["name"]
        return None, None

    # ----- 선발 명단: 게임의 선발 라인업 화면에서 읽기 -----
    def on_lineup_screen(self, data):
        if not self.teams_known:                 # 팀을 찾으면 그때 붙임
            self.pending_screen = data
            return
        for key in ("home", "away"):
            rows = data.get(key) or []
            if len(rows) >= 9:
                self.apply_screen_lineup(key, rows)
        if self.pending_squad:
            self.on_squad_screen(self.pending_squad)
        self.retry_preview()
        self.refresh_overlay()

    def apply_screen_lineup(self, key, rows: list[tuple[str, str]]):
        m = self.match
        side = m.side(key)
        lineups = self.cfg.setdefault("lineups", {})
        old = lineups.get(side.label) or {}
        order = [no for no, _ in rows]
        prev = old.get("screen_order") or []
        known = {q.get("no"): q for q in old.get("players", []) + old.get("bench", []) if q.get("no")}
        if prev == order:
            return
        # 같은 경기에서 몇 자리만 바뀌었으면 교체 (게임은 교체 선수를 나간 선수 자리에 둠)
        if len(prev) == len(order) and sum(a != b for a, b in zip(prev, order)) <= 5 and old.get("players"):
            players, bench = list(old["players"]), list(old.get("bench", []))
            for i, (no, en) in enumerate(rows):
                if prev[i] == no:
                    continue
                out_q = next((q for q in players if q.get("no") == prev[i]), None)
                in_q = known.get(no) or {"no": no, "name": en, "en": en}
                if out_q:
                    players[players.index(out_q)] = in_q
                    bench = [b for b in bench if b.get("no") != no] + [out_q]
                    m.mark(key, out_q["name"], "off")
                m.mark(key, in_q["name"], "on")
                log.info("sub from lineup screen: %s out, %s in", out_q and out_q["name"], in_q["name"])
            lineups[side.label] = {**old, "players": players, "bench": bench, "screen_order": order}
        else:
            # 새 명단: 등번호가 같은 선수는 전에 쓰던 한국어 이름을 그대로
            people = []
            for no, en in rows:
                q = known.get(no)
                people.append({"no": no, "name": q["name"], "en": en} if q and same_name(q.get("en") or q["name"], en) or
                              (q and q["name"] == en) else {"no": no, "name": en, "en": en})
            form = old.get("formation") or "4-3-3"
            # 예상 라인업 화면에서 읽은 자리(등번호 없음)가 있으면 자리는 그대로 두고 등번호·영어 이름만 채움
            if old.get("formation_from_screen") and old.get("players") and not any(q.get("no") for q in old["players"]):
                def same(a, b):
                    return any(w in plain(b) for w in re.split(r"[\s.\-']+", plain(a)) if len(w) >= 3)
                filled = []
                for q in old["players"]:
                    hit = next(((no, en) for no, en in rows if same(q.get("en") or q["name"], en)), None)
                    filled.append({**q, "no": hit[0], "en": hit[1]} if hit else q)
                if sum(1 for q in filled if q.get("no")) >= 9:
                    lineups[side.label] = {**old, "players": filled, "screen_order": order}
                    save_cfg(self.cfg)
                    return
            if old.get("formation_from_screen") and sorted(order) == sorted(q.get("no") for q in old.get("players", [])):
                # 같은 선수들 — 팀 관리 화면에서 읽은 포메이션·자리 그대로
                lineups[side.label] = {**old, "screen_order": order}
            else:
                lineups[side.label] = {"formation": form, "players": fc_to_overlay_order(people, form),
                                       "bench": old.get("bench", []), "color": old.get("color", side.color), "screen_order": order}
        save_cfg(self.cfg)

    def person_for(self, key: str, shown: str) -> dict | None:
        """화면 이름('amine Yamal', 'Donnarumm' 처럼 잘려도)과 명단 선수 맞추기"""
        words = [w for w in re.split(r"[\s.\-']+", plain(shown)) if len(w) >= 3]
        for q in self.match.lineup_people(key):
            full = plain((q.get("en") or "") + " " + q["name"])
            if any(w in full for w in words) or any(len(w) >= 5 and w[:5] in full for w in words) or names_in_text(shown, [q["name"]]):
                return q
        return None

    def on_squad_screen(self, data):
        """팀 관리 화면 = 내 팀. 선발 명단 이름이 더 많이 맞는 쪽을 내 팀으로 보고 포메이션·자리를 그대로 씀."""
        shown = [n for r in data["rows"] for n in r]
        score = {k: sum(1 for n in shown if self.person_for(k, n)) for k in ("home", "away")}
        key = max(score, key=score.get)
        if score[key] < 8:
            self.pending_squad = data                 # 선발 라인업 화면을 읽은 뒤에 적용
            return
        self.pending_squad = None
        lu = self.cfg.get("lineups", {}).get(self.match.side(key).label)
        ordered, used = [], set()
        for n in shown:
            q = self.person_for(key, n)
            if q and q.get("no") not in used:
                ordered.append(q)
                used.add(q.get("no"))
            else:
                ordered.append(None)
        rest = [q for q in lu.get("players", []) if q.get("no") not in used]
        ordered = [q if q else rest.pop(0) for q in ordered if q or rest]
        if len(ordered) != 11:
            return
        lu.update({"formation": data["formation"], "players": ordered, "formation_from_screen": True})
        self.user_side_votes[key] += 5
        save_cfg(self.cfg)
        log.info("formation from squad screen: %s %s", self.match.side(key).label, data["formation"])
        self.refresh_overlay()
        self.retry_preview()

    # ----- 상대 팀 명단: 경기 전 '예상 라인업' 화면에서 읽기 -----
    def on_preview_screen(self, data):
        """예상 라인업 화면 = 상대 팀. 포메이션·자리·교체 명단을 화면에 나온 그대로 씀.
        어느 팀인지 아직 모르면(경기 전엔 스코어보드가 없어 팀을 모름) 기억해 뒀다가 알게 되면 붙임."""
        self.pending_preview = data
        self.retry_preview()

    def retry_preview(self):
        data = self.pending_preview
        if not data or not self.teams_known:
            return
        if time.time() - data.get("t", 0) > 20 * 60:        # 한참 전 화면은 다른 경기일 수 있음
            self.pending_preview = None
            return
        key = self.preview_side(data)
        if key is None:
            return
        self.pending_preview = None
        self.apply_preview(key, data)

    def preview_side(self, data) -> str | None:
        """예상 라인업이 어느 팀인지: 이미 아는 명단과 이름이 맞는 팀 → 내 팀(조작하는 팀)의 반대 → 명단을 아는 팀의 반대"""
        m = self.match
        shown = [n for r in data["rows"] for n in r]
        score = {k: sum(1 for n in shown if self.person_for(k, n)) for k in ("home", "away")}
        best = max(score, key=score.get)
        if score[best] >= 6:
            return best
        v = self.user_side_votes
        mine = max(v, key=v.get)
        if v[mine] >= 3 and v[mine] > v[m.other(mine)]:
            return m.other(mine)
        # 한 팀 명단만 알고(보통 지난 경기에 저장된 내 팀) 그 명단과 거의 안 맞으면 → 다른 팀
        known = [k for k in ("home", "away") if len(m.lineup_names(k)) >= 9]
        if len(known) == 1 and score[known[0]] <= 2:
            return m.other(known[0])
        return None

    def apply_preview(self, key, data):
        m = self.match
        side = m.side(key)
        lineups = self.cfg.setdefault("lineups", {})
        old = lineups.get(side.label) or {}
        used: set[str] = set()

        def person(shown: str) -> dict:
            q = self.person_for(key, shown) if old else None
            if q and q["name"] not in used:
                used.add(q["name"])
                return dict(q)                      # 전에 쓰던 이름·등번호 그대로
            return {"no": "", "name": shown, "en": shown}

        players = [person(n) for r in data["rows"] for n in r]
        bench = [person(n) for n in data.get("bench", [])]
        lineups[side.label] = {**old, "formation": data["formation"], "players": players, "bench": bench,
                               "color": old.get("color", side.color), "formation_from_screen": True}
        self.user_side_votes[m.other(key)] += 3       # 상대 팀 명단이니 다른 쪽이 내 팀
        save_cfg(self.cfg)
        log.info("opponent lineup from preview screen: %s %s %s | bench %s", side.label, data["formation"],
                 ", ".join(p["name"] for p in players), ", ".join(b["name"] for b in bench))
        self.refresh_overlay()

    def mark_card(self, key, name, what):
        m = self.match
        team = m.side(key).label
        last = m.marks.get(team, {}).get(name, {}).get("_card_at", 0)
        if time.time() - last < 20:      # 같은 카드를 해설이 반복해도 한 번만
            return
        m.mark(key, name, what)
        m.marks[team][name]["_card_at"] = time.time()

    # ----- 방장 채팅 (입력창) -----
    def recent_chat(self) -> list[dict]:
        """2분 안의 마지막 12줄"""
        now = time.time()
        return [c for c in self.chat_log if now - c.get("t", 0) <= 120][-12:]

    def send_user_chat(self, text: str):
        """방장이 입력창에 쓴 채팅: 노란 이름으로 바로 띄우고, 시청자 여럿이 그 말에 반응"""
        text = re.sub(r"[\r\n\t<>]+", " ", text).strip()[:200]
        if not text or not self.session_on:
            return
        name = self.cfg.get("streamer_name") or "방장"
        self.emit({"name": name, "text": text, "kind": "owner", "amount": 0, "side": "neutral"})
        self.chat.scroll_end()
        if not self.live:                 # 킥오프 전에는 시청자 채팅이 안 나옴
            return
        # 방장이 최근 채팅의 누군가를 부르면 (@닉네임이든 그냥 닉네임이든) 그 사람이 대답
        mention = next((c["name"] for c in reversed(self.recent_chat())
                        if c.get("kind") != "owner" and len(c["name"].lstrip("@")) >= 2 and c["name"].lstrip("@") in text), None)
        msgs = self.engine.host_replies(text, mention)
        if mention and msgs and msgs[0]["name"] == mention:     # 부른 사람이 먼저 대답
            self.enqueue(msgs[:1], 0.6, 1.8)
            msgs = msgs[1:]
        self.enqueue(msgs, 1.0, 5.0)

    # ----- 해설 받아쓰기 저장 -----
    def write_transcript(self, text: str):
        if not self.cfg.get("save_transcript", False) or DEMO:
            return
        try:
            if self.transcript_file is None:
                folder = APP_DIR / "transcripts"
                folder.mkdir(exist_ok=True)
                path = folder / f"해설_{time.strftime('%Y%m%d_%H%M%S')}.txt"
                self.transcript_file = open(path, "a", encoding="utf-8")   # noqa: SIM115 (경기 동안 열어 둠)
                self.transcript_file.write(f"# {time.strftime('%Y-%m-%d %H:%M')}  {self.match.home.label} 대 {self.match.away.label}\n\n")
                log.info("transcript file: %s", path)
            mnt = f" {self.match.minute}분" if self.match.minute is not None else ""
            self.transcript_file.write(f"[{time.strftime('%H:%M:%S')}{mnt}] {text}\n")
            self.transcript_file.flush()
        except Exception:
            log.exception("transcript write failed")

    def close_transcript(self):
        if self.transcript_file is not None:
            try:
                self.transcript_file.close()
            except Exception:
                pass
            self.transcript_file = None

    # ----- 채팅 캡처 (fake-twitch-chat의 Clip) -----
    def save_clip(self):
        rows = self.chat_log[-12:]
        if not rows:
            self.chat.set_state("● 저장할 채팅이 아직 없습니다")
            return
        try:
            from PIL import Image, ImageDraw, ImageFont
            ttf, ttf_reg = self.chat._font_path(True), self.chat._font_path(False)
            S = 2                                             # 2배 해상도
            W, pad, av, gap = 420 * S, 16 * S, 24 * S, 8 * S
            f_name = ImageFont.truetype(ttf, 13 * S) if ttf else ImageFont.load_default()
            f_msg = ImageFont.truetype(ttf_reg, 13 * S) if ttf_reg else ImageFont.load_default()
            f_av = ImageFont.truetype(ttf, int(av * 0.48)) if ttf else f_msg
            probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
            text_x, line_h = pad + av + 16 * S, 20 * S
            lines = []                                        # (메시지, [(줄 글자, 이름 자리 포함 여부)])
            for m in rows:
                name_w = probe.textlength(m["name"] + "  ", font=f_name) + (8 * S if m["kind"] == "owner" else 0)
                words, cur, first, out = m["text"].split(" "), "", True, []
                for w in words:
                    room = W - pad - text_x - (name_w if first else 0)
                    t = (cur + " " + w).strip()
                    if cur and probe.textlength(t, font=f_msg) > room:
                        out.append(cur)
                        cur, first = w, False
                    else:
                        cur = t
                out.append(cur)
                lines.append((m, name_w, out))
            H = pad * 2 + sum(max(av, len(o) * line_h) + gap for _, _, o in lines)
            im = Image.new("RGB", (W, H), BG)
            d = ImageDraw.Draw(im)
            y = pad
            for m, name_w, out in lines:
                color = AV_COLORS[sum(ord(c) * (i + 7) for i, c in enumerate(m["name"])) % len(AV_COLORS)]
                d.ellipse((pad, y, pad + av, y + av), fill=color)
                d.text((pad + av / 2, y + av / 2), (m["name"].lstrip("@")[:1] or "?").upper(), font=f_av, fill="white", anchor="mm")
                nc = {"member": MEMBER, "mod": MOD}.get(m["kind"], FG2)
                if m["kind"] == "owner":
                    d.rounded_rectangle((text_x, y + 2 * S, text_x + name_w - 6 * S, y + line_h - 2 * S), radius=2 * S, fill=OWNER)
                    d.text((text_x + 4 * S, y + line_h / 2), m["name"], font=f_name, fill="#0f0f0f", anchor="lm")
                else:
                    d.text((text_x, y + line_h / 2), m["name"], font=f_name, fill=nc, anchor="lm")
                for i, ln in enumerate(out):
                    d.text((text_x + (name_w if i == 0 else 0), y + line_h / 2 + i * line_h), ln, font=f_msg, fill=FG, anchor="lm")
                y += max(av, len(out) * line_h) + gap
            folder = APP_DIR / "clips"
            folder.mkdir(exist_ok=True)
            path = folder / f"채팅_{time.strftime('%Y%m%d_%H%M%S')}.png"
            im.save(path)
            log.info("clip saved: %s", path)
            self.chat.set_state(f"● 채팅 캡처 저장: clips\\{path.name}")
        except Exception as e:
            log.exception("clip failed")
            self.chat.set_state(f"● 채팅 캡처 실패: {e}")

    # ----- 화면 아래 선수 표시 → 조작 중인 선수, 득점자 -----
    def match_hud(self, line: str) -> tuple[str, str] | None:
        """'DIAS 33' → (팀, 명단 이름). 등번호가 먼저, 이름은 보조 (화면엔 성, 명단엔 이름만 있을 수 있음)"""
        m = (re.search(rf"([{NAME_CH}][{NAME_CH}'.\- ]{{1,24}}?)\s*(\d{{1,2}})(?!\d)", line)
             or re.search(rf"(?<!\d)(\d{{1,2}})\s+([{NAME_CH}][{NAME_CH}'.\- ]{{1,24}})", line))
        if not m:
            return None
        txt, no = (m.group(1), m.group(2)) if not m.group(1).isdigit() else (m.group(2), m.group(1))
        cands = [(k, q) for k in ("home", "away") for q in self.match.lineup_people(k) if q.get("no") == no]
        if not cands:
            return None
        words = [w for w in re.split(r"[\s.\-']+", plain(txt)) if len(w) >= 3]

        def name_ok(q):
            full = plain((q.get("en") or "") + " " + q["name"])
            return any(w in full for w in words) or bool(names_in_text(txt, [q["name"]]))

        good = [c for c in cands if name_ok(c[1])]
        if len(good) == 1 or len(cands) == 1:
            key, q = (good or cands)[0]
            self.user_side_votes[key] += 1
            return key, q["name"]
        mine = max(self.user_side_votes, key=self.user_side_votes.get)
        pick = [c for c in (good or cands) if c[0] == mine]
        if self.user_side_votes[mine] >= 3 and len(pick) == 1:
            return pick[0][0], pick[0][1]["name"]
        return None

    def on_hud(self, data):
        now = data["t"]
        for line in data["lines"]:
            hit = self.match_hud(line)
            if hit:
                self.hud_hist = [h for h in self.hud_hist if now - h[0] < 60] + [(now, hit[0], hit[1])]
                if self.pending_preview:              # 내 팀을 알게 되면 기다리던 상대 명단을 붙임
                    self.retry_preview()
                break
        # 골 뒤 화면 아래에 득점자 이름이 뜨면 (상대 팀 골도) 그걸로
        bg = self.last_board_goal
        if bg and not bg["scorer"] and now - bg["t"] < 45:
            for line in data["lines"]:
                low = plain(line)
                for q in self.match.lineup_people(bg["side"]):
                    parts = [w for w in re.split(r"[\s.\-']+", plain(q.get("en") or q["name"])) if len(w) >= 4]
                    if any(re.search(rf"\b{re.escape(w)}\b", low) for w in parts) or names_in_text(line, [q["name"]]):
                        self.set_scorer(bg, q["name"], "득점자 표시")
                        return

    def ball_holder(self) -> tuple[str, str] | None:
        if self.hud_hist and time.time() - self.hud_hist[-1][0] < 5:
            return self.hud_hist[-1][1], self.hud_hist[-1][2]
        return None

    def set_scorer(self, bg: dict, name: str, how: str):
        m = self.match
        side = bg["side"]
        bg["scorer"] = name
        m.mark(side, name, "goal")
        if m.is_bench(side, name):
            m.mark(side, name, "on")
        if m.events and m.events[-1].endswith("득점"):
            m.events[-1] += f" ({name})"
        log.info("scorer (%s): %s %s", how, m.side(side).label, name)
        self.refresh_overlay()
        self.engine.scorer = name
        if self.engine.scene and self.engine.scene["ev"] == "goal":
            self.engine.scene.update(player=name, desc=f"{name} 골")
        self.enqueue(self.engine.scorer_lines(side, name, random.randint(2, 4)), 0.3, 3.0)

    def goal(self, side, text=""):
        """점수 올리기 — 스코어보드가 점수 변화를 봤을 때만 (해설로는 세지 않음).
        득점자 = 골 직전 화면 아래에 표시된 그 팀 선수 (없으면 골 뒤 득점자 표시를 기다림)."""
        m = self.match
        if side == "home":
            m.hs += 1
        else:
            m.as_ += 1
        m.push_event(f"{m.side(side).label} 득점")
        bg = {"side": side, "t": time.time(), "scorer": None}
        self.last_board_goal = bg
        # 골 장면·리플레이 동안엔 표시가 사라지니, 45초 안의 마지막 그 팀 선수
        last = [h for h in self.hud_hist if h[1] == side and time.time() - h[0] < 45]
        self.refresh_overlay()
        self.bump_viewers()
        self.add_hype(3.0)
        self.update_state_line()
        recent = time.time() - self.last_comm_goal_at < 40       # 해설 반응으로 골 채팅이 이미 나감
        self.engine.scene = {"ev": "goal", "side": side, "player": None, "t": time.time(), "desc": f"{m.side(side).short} 골"}
        msgs = self.engine.react("goal", side, None, random.randint(3, 5) if recent else random.randint(10, 15))
        if not recent:
            msgs += self.engine.chant(side, None, random.randint(3, 6))
        if random.random() < 0.75:
            sc = self.engine.super_chat("goal", side)
            if sc:
                msgs.append(sc)
        if random.random() < 0.5:
            msgs.append(self.engine.new_member(side))
        self.enqueue(msgs, 0.2, 5.0)
        if last:
            self.set_scorer(bg, last[-1][2], "골 직전 선수 표시")

    def on_board(self, d):
        m = self.match
        if d.get("minute") is not None:
            if m.minute is not None and m.minute >= 60 and d["minute"] <= 3:
                self.pause_chat("경기 시간이 처음으로 돌아감 (새 경기)")
            if self.phase == "half" and d["minute"] >= 46:      # 후반 시계가 돌기 시작
                self.phase = "play"
            m.minute = d["minute"]
        if "codes" not in d:
            return
        key = (d["codes"], d["score"])
        if key != self.board_prev:          # 두 번 연속 같아야 믿음
            self.board_prev = key
            return
        codes, score = d["codes"], d["score"]
        prev = self.board_stable
        self.board_stable = key
        if prev is not None and prev[0] != codes:
            self.pause_chat("스코어보드의 팀이 바뀜 (새 경기)")
        if not self.teams_locked and (prev is None or prev[0] != codes):
            th, ta = self.resolve_code(codes[0]), self.resolve_code(codes[1])
            if not self.teams_known or prev is not None:
                self.set_team("home", th["ko"] if th else codes[0])
                self.set_team("away", ta["ko"] if ta else codes[1])
                if th and ta:
                    self.teams_changed()
                else:
                    self.on_split_changed()
            m.hs, m.as_ = score
            self.update_state_line()
            return
        if (m.hs, m.as_) == score:
            return
        dh, da = score[0] - m.hs, score[1] - m.as_
        if (dh, da) == (1, 0):
            self.goal("home")
        elif (dh, da) == (0, 1):
            self.goal("away")
        else:
            m.hs, m.as_ = score
        self.update_state_line()

    def bump_viewers(self):
        self.viewers = int(self.viewers * (1.04 + random.random() * 0.08))
        self.chat.set_viewers(self.viewers)

    # ----- 주기 작업 -----
    def tick_viewers(self):
        if self.session_on:
            # 시청자 흐름: 경기가 진행될수록 조금씩 늘고, 하프타임엔 빠졌다 돌아오고, 끝나면 서서히 나감.
            # 골 같은 장면에서 확 늘었다가(bump_viewers) 1분쯤에 걸쳐 제자리로.
            floor = self.match.viewer_floor()
            mnt = self.match.minute or 0
            if not self.live:
                target = floor * 0.85
            elif self.phase == "half":
                target = floor * 0.88
            elif self.phase == "ended":
                target = max(floor * 0.3, self.viewers * 0.95)
            else:
                target = floor * (1.0 + 0.18 * min(1.0, mnt / 90))
            self.viewers = max(100, int(self.viewers + (target - self.viewers) * 0.06
                                        + (random.random() - 0.5) * self.viewers * 0.006))
            self.chat.set_viewers(self.viewers)
        self.root.after(4000, self.tick_viewers)

    # ----- 창 -----
    def open_lineup_editor(self):
        LineupEditor(self)

    def open_team_dialog(self):
        TeamDialog(self)

    def open_mark_dialog(self):
        MarkDialog(self)

    def open_name_dialog(self):
        NameDialog(self)

    def quit(self):
        try:
            self.close_transcript()
            for th in (self.stt, self.board):
                if th:
                    th.stop()
            PID_PATH.unlink(missing_ok=True)
        finally:
            self.root.destroy()

    def run(self):
        self.tick_chat()
        self.root.mainloop()

    # ----- 시험용 -----
    def run_demo(self):
        self.set_team("home", "맨체스터 유나이티드")
        self.set_team("away", "헐 시티", color="#F5A200")
        self.teams_changed()
        self.cfg.setdefault("lineups", {})
        self.cfg["lineups"].setdefault("맨체스터 유나이티드", {"formation": "4-2-1-3", "color": "#ffffff", "players": [
            {"no": "1", "name": "라먼스"}, {"no": "23", "name": "루크 쇼"}, {"no": "26", "name": "헤븐"}, {"no": "5", "name": "매과이어"},
            {"no": "3", "name": "마즈라위"}, {"no": "37", "name": "마이누"}, {"no": "8", "name": "브루노 페르난데스"}, {"no": "10", "name": "쿠냐"},
            {"no": "9", "name": "래시포드"}, {"no": "30", "name": "세슈코"}, {"no": "19", "name": "음뵈모"}], "bench": []})
        self.cfg["lineups"].setdefault("헐 시티", {"formation": "3-4-2-1", "color": "#F5A200", "players": [
            {"no": "19", "name": "졸라키스"}, {"no": "17", "name": "맥네어"}, {"no": "15", "name": "이건"}, {"no": "22", "name": "헤링턴"},
            {"no": "3", "name": "자일스"}, {"no": "27", "name": "슬레이터"}, {"no": "25", "name": "크룩스"}, {"no": "18", "name": "드라메"},
            {"no": "7", "name": "밀러"}, {"no": "10", "name": "벨루미"}, {"no": "9", "name": "맥버니"}],
            "bench": [{"no": "6", "name": "아자이"}, {"no": "32", "name": "멘디"}, {"no": "11", "name": "그린"}]})
        self.refresh_overlay()

    def demo_feed(self):
        lines = [ "크룩스 경고를 받습니다", "세슈코 빠지고 교체", "래시포드 교체되어 나갑니다",
                 "마이누 교체", "드라메 나오고 아자이 교체 투입", "맥네어 대신 멘디 교체", "헤링턴 교체",
                 "아자이 골입니다!", "골키퍼가 막아냅니다", "코너킥 얻어냅니다", "양 팀 치열합니다", "프리킥 기회",
                 "헐 시티 역습", "멘디 골입니다!"]

        def feed(i=0):
            if i < len(lines) and self.live:
                self.on_commentary(lines[i])
                self.root.after(4500, feed, i + 1)
        feed()


# ---------------------------------------------------------------------------
# 설치 도우미
# ---------------------------------------------------------------------------
def startup_dir() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def install_autostart():
    if not IS_WIN:
        print("윈도우에서만 자동 실행을 등록할 수 있습니다.")
        return
    pyw = Path(sys.executable).with_name("pythonw.exe")
    exe = str(pyw if pyw.exists() else sys.executable)
    vbs = startup_dir() / "FC26_live_chat.vbs"
    vbs.write_text(f'CreateObject("WScript.Shell").Run """{exe}"" ""{Path(__file__).resolve()}""", 0\n', encoding="utf-16")
    print(f"자동 실행 등록 완료: {vbs}")


def uninstall_autostart():
    p = startup_dir() / "FC26_live_chat.vbs"
    if p.exists():
        p.unlink()
        print("자동 실행 해제 완료")


def stop_running():
    try:
        pid = int(PID_PATH.read_text())
        import psutil
        psutil.Process(pid).terminate()
        print("실행 중인 채팅을 껐습니다.")
    except Exception:
        print("실행 중인 채팅이 없습니다.")
    PID_PATH.unlink(missing_ok=True)


def prepare():
    cfg = load_cfg()
    save_cfg(cfg)
    print("받아쓰기 모델 내려받는 중 (처음 한 번)…")
    try:
        AudioSTT.load_model(cfg)
        print("  완료")
    except Exception as e:
        print("  실패:", e)
    print("스코어보드 읽기 준비 중…")
    try:
        from rapidocr_onnxruntime import RapidOCR
        RapidOCR()
        print("  완료")
    except Exception as e:
        print("  실패:", e)


def already_running() -> bool:
    try:
        pid = int(PID_PATH.read_text())
        import psutil
        p = psutil.Process(pid)
        return any("fc26_live_chat" in a for a in p.cmdline())
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser(description=APP_NAME)
    ap.add_argument("--always", action="store_true", help="게임을 기다리지 않고 바로 켜기")
    ap.add_argument("--demo", action="store_true", help="게임 없이 시험 화면 보기")
    ap.add_argument("--prepare", action="store_true", help="모델 미리 내려받기")
    ap.add_argument("--install-autostart", action="store_true")
    ap.add_argument("--uninstall-autostart", action="store_true")
    ap.add_argument("--stop", action="store_true")
    args = ap.parse_args()
    if args.prepare:
        return prepare()
    if args.install_autostart:
        return install_autostart()
    if args.uninstall_autostart:
        return uninstall_autostart()
    if args.stop:
        return stop_running()
    global DEMO
    DEMO = args.demo
    if already_running():
        return
    PID_PATH.write_text(str(os.getpid()))
    try:
        App(args).run()
    except Exception:
        log.exception("fatal")
        try:
            messagebox.showerror(APP_NAME, f"오류가 나서 종료합니다. 자세한 내용은 {LOG_PATH.name} 파일을 확인해 주세요.")
        except Exception:
            pass
    finally:
        PID_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
