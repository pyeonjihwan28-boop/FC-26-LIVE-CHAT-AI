#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FC 26 라이브 채팅
- FC 26이 켜지면 자동으로 채팅 창(유튜브 라이브 채팅 스타일)과 선발 명단 오버레이를 띄웁니다.
- 게임 소리(해설)를 이 PC 안에서 받아쓰고(faster-whisper), 스코어보드를 읽고(RapidOCR),
  이 PC에서 돌아가는 AI(Ollama)로 채팅을 만듭니다. 외부 API는 쓰지 않습니다.
- AI나 받아쓰기가 없으면 내장 문장으로 대신 반응합니다.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import logging
import math
import os
import queue
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import tkinter as tk
from tkinter import colorchooser, messagebox, ttk
from tkinter import font as tkfont

APP_NAME = "FC26 실시간 채팅"
APP_DIR = Path(__file__).resolve().parent
CFG_PATH = APP_DIR / "fc26_chat_config.json"
LOG_PATH = APP_DIR / "fc26_chat.log"
PID_PATH = APP_DIR / "fc26_chat.pid"
LEARN_PATH = APP_DIR / "fc26_chat_learned.json"   # AI가 채팅 기록을 보고 스스로 보완한 문장·닉네임
IS_WIN = sys.platform.startswith("win")

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
    "use_ai": True,
    "ollama_model": "gemma3:4b",
    "ai_interval_sec": 20,
    "self_review": True,              # 채팅 기록을 AI에게 보내 어색한 문장·닉네임을 스스로 고치기
    "review_interval_sec": 120,
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
        return int(round((self.home.fans_or_default + self.away.fans_or_default) * 1e6 * 1.5 / 1000))

    def lineup(self, key) -> dict | None:
        lu = self.cfg.get("lineups", {}).get(self.side(key).label)
        return lu if lu and any(p.get("name") for p in lu.get("players", [])) else None

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
# 해설 속 장면 감지
# ---------------------------------------------------------------------------
NOT_SCORE = re.compile(r"(득점\s*(기회|찬스|없이|실패|을?\s*노|하지\s*못|에\s*실패|권)|넣었어야|넣지\s*못|실점\s*위기|골\s*찬스|골\s*기회|옆\s*그물)")
DETECT = [
    ("end", re.compile(r"(경기\s*(가|는)?\s*(종료|끝)|종료\s*휘슬|모든\s*경기가\s*끝|full[\s-]?time|final whistle)", re.I)),
    ("half", re.compile(r"(전반\s*(전)?\s*(이|은)?\s*(종료|끝)|하프\s*타임|half[\s-]?time)", re.I)),
    ("kickoff", re.compile(r"(킥\s*오프|경기\s*시작|후반\s*(전)?\s*(이|을)?\s*시작|kick[\s-]?off|we('re| are) underway)", re.I)),
    ("red", re.compile(r"(레드\s*카드|퇴장|경고\s*누적|red card|sent off|sending off)", re.I)),
    # 골이 취소되면 득점이 아니라 판정 장면
    ("var", re.compile(r"(노\s*골(?!적)|골\s*(이|은)?\s*취소|득점\s*(이|은)?\s*(취소|인정되지)|\bvar\b|비디오\s*판독|disallowed|ruled out)", re.I)),
    ("score", re.compile(r"(득점|골망|골\s*네트|그물을\s*(흔|가르|가릅|갈라)|골문을\s*(흔|가르|가릅|갈라)|골인|넣었습니다|넣습니다|넣어요|넣었어요|골입니다|골이에요|골이죠|골{2,}|(^|\s)골(\s|$|!|~)|\bgoal\b|scores|scored|back of the net)", re.I)),
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
COOLDOWN = {"score": 25, "end": 60, "half": 60, "kickoff": 60, "red": 20, "penalty": 20}
MINOR = {"corner", "freekick", "offside", "sub"}
BIG = {"hgoal", "agoal", "end", "red", "penalty"}
EV_DESC = {
    "save": "골키퍼의 선방", "miss": "결정적인 찬스를 놓침", "post": "슈팅이 골대를 맞음",
    "penalty": "페널티킥 상황", "yellow": "경고 카드", "red": "퇴장", "var": "VAR/판정 논란",
    "offside": "오프사이드", "corner": "코너킥", "freekick": "프리킥", "sub": "선수 교체",
    "kickoff": "킥오프", "half": "전반 종료, 하프타임", "end": "경기 종료", "score": "골이 나온 것 같음",
}


def detect_event(text: str):
    for ev, rx in DETECT:
        if rx.search(text):
            if ev == "score" and NOT_SCORE.search(text):
                continue
            return ev
    return None


def names_in_text(text: str, names: list[str]) -> list[str]:
    low = text.lower()
    hits = []
    for n in names:
        parts = [n] + [p for p in n.split() if len(p) >= 2]
        if any(len(p) >= 2 and p.lower() in low for p in parts):
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
# 채팅 만들기 (내장 문장)
# ---------------------------------------------------------------------------
P = {
    "celeb": ["골!!!!!!", "{t} 가즈아아아", "미쳤다 ㄷㄷㄷ", "와 이걸 넣네", "{p} 폼 미쳤다", "소리 질러!!!", "⚽⚽⚽", "이게 {t}지 ㅋㅋㅋ",
              "클립 따주세요", "키퍼 반응도 못함", "{o} 팬들 어디 갔냐 ㅋㅋ", "역시 믿고 있었다", "오늘 이긴다", "골 장면 한 번 더!!",
              "ㅋㅋㅋㅋㅋㅋㅋ", "나 방금 소리 질렀음", "{t} 사랑한다", "완벽한 마무리", "이 맛에 축구 본다", "{o} 수비 뭐냐 ㅋㅋ"],
    "groan": ["아 ㅠㅠ", "수비 뭐함", "키퍼 잠들었냐", "아직 시간 있다", "집중하자 집중", "라인 너무 올렸음", "ㅠㅠㅠㅠ", "이건 막았어야지",
              "괜찮아 다시 가자", "{t} 오늘 왜 이래", "오프사이드 아님?", "파울 아니냐 이거", "하.. 멘탈 나감", "동점골 가자",
              "아직 안 끝났다", "수비 교체 좀", "이걸 먹네", "노마킹이었음"],
    "ngoal": ["와 골 예술이다", "이 경기 재밌네", "{t} 골 ㄷㄷ", "중립인데 소름 돋음", "이제 경기 불붙는다", "빌드업부터 완벽했음",
              "수비가 너무 쉽게 열렸네", "이러면 {o} 급해지겠다", "스코어 {score}", "오늘 골 많이 나오겠는데", "킥 궤적 미쳤다", "{p} 클래스 봐라"],
    "hint": ["골?!", "들어갔나?", "어어어", "와", "ㄷㄷㄷ", "골이다!!", "뭐야 뭐야", "헐"],
    "save": ["선방 미쳤다", "키퍼 폼 ㄷㄷ", "와 이걸 막네", "슈퍼 세이브!!", "손 뻗는 거 봐", "키퍼가 다 했다", "반사신경 무엇", "이게 막히네 ㅋㅋ", "오늘 키퍼 MOM"],
    "miss": ["아 이걸 못 넣네", "하늘로 쏘냐 ㅋㅋ", "결정력 어디 감", "이건 넣어야지", "아까비", "ㅠㅠ 아쉽다", "관중석 맞췄네", "슈팅 각은 좋았는데", "침착하게 좀"],
    "post": ["골대!!!", "땡 소리 봐", "골대 맞았다 ㄷㄷ", "아 한 뼘", "운이 없네", "골대가 수비함 ㅋㅋ", "크로스바 맞고 나왔다"],
    "penalty": ["PK!!", "페널티다!!", "이거 PK 맞음?", "누가 차냐", "파넨카 가자 ㅋㅋ", "키커 긴장되겠다", "시뮬 아님?", "확실한 PK네"],
    "yellow": ["카드 받을 만했다", "심판 칼같네", "옐로 떴다", "경고 누적 조심", "너무 늦게 들어감", "이게 카드야?", "옐로 정도면 다행"],
    "red": ["퇴장?!", "레드 실화냐", "이건 너무했다", "10명이서 버텨야 함", "말도 안 돼", "경기 흐름 바뀐다", "레드는 오버다", "심판 오늘 왜 이럼"],
    "var": ["VAR 가냐", "이게 파울임?", "느린 화면 보면 애매함", "주심 표정 봐", "판정 제발"],
    "offside": ["오프사이드 ㅠ", "깃발 올라갔네", "반 발 차이", "라인 잘 맞췄네", "아깝다 라인"],
    "corner": ["코너킥 기회", "헤더 가자", "세트피스 한 방", "니어 포스트!", "키 큰 애들 올라간다"],
    "freekick": ["프리킥 각", "직접 차라", "벽 몇 명임", "감아 차 가자", "여기서 한 방"],
    "sub": ["교체 타이밍 좋다", "드디어 교체", "새 다리 들어간다", "이 교체 맞음?", "체력 떨어졌었음"],
    "half": ["전반 끝", "화장실 다녀옴", "후반 기대된다", "전반 평점 누가 1등?", "치킨 시켰다", "후반엔 달라져야 함", "전반 {score}"],
    "end": ["경기 끝!!", "GG", "수고했다", "오늘 경기 재밌었다", "MOM 누구임", "다음 경기도 봅시다", "최종 {score}"],
    "win": ["이겼다!!!", "{t} 최고", "3점 챙겼다", "오늘 잠 잘 오겠다", "역시 {t}"],
    "lose": ["하.. 졌네", "오늘은 인정", "다음 경기 이기자", "멘탈 나감", "{t} 반성하자"],
    "kickoff": ["시작한다!!", "킥오프!", "오늘 경기 기대된다", "예측: 2대1", "⚽ 가즈아", "{t} 화이팅!", "라인업 좋다"],
    "fan_idle": ["{t} 가즈아", "{t} 화이팅", "오늘 {t}가 이긴다", "{o} 별거 없네 ㅋㅋ", "{t} 빌드업 좋다", "{o} 수비 구멍 보인다",
                 "{t} 팬 모여라", "점유율 우리가 잡자", "역습 한 방이면 된다", "{t} 압박 좋다", "{o} 팬들 조용하네", "{p} 믿는다", "{p} 오늘 폼 좋다"],
    "kor_idle": ["{k} 화이팅!!", "{k} 오늘 폼 좋다", "{k} 공 좀 줘라", "한국 선수 나와서 봄 ㅋㅋ", "{k} 골 가자", "{k} 보러 왔습니다",
                 "{k} 나올 때마다 소리 지름", "대한민국 ♥", "{k} 터치 봐라"],
    "neu_idle": ["점유율 좋네", "빌드업 깔끔하다", "압박 좋다", "중원 싸움 치열하다", "ㅋㅋㅋㅋ", "롱볼 너무 많음", "역습 조심", "몇 분임?",
                 "세트피스 기대", "ㅎㅇㅎㅇ", "방금 들어옴", "스코어 몇 대 몇?", "슈팅 좀 때리자", "난이도 뭐로 하세요?", "해설 목소리 좋다",
                 "중립 기어 박고 봅니다", "오늘 전술 뭐임", "양 팀 다 잘하네", "템포 빠르다", "이 경기 끝까지 본다"],
    "echo_fan": ["{t} 공격 좋다", "{t} 좀 더 올라가자", "{t} 템포 좋네", "{t} 패스 미스 좀 줄이자", "{t} 흐름 탔다", "{o} 막아라!!"],
    "echo_kor": ["{k}!!!", "{k} 나왔다", "{k} 가자!!", "오 {k} 터치 좋다", "{k} 해설에 나왔다 ㅋㅋ"],
}
P.update({
    "fan_lead": ["이대로만 가자", "{t} 오늘 잡았다", "{o} 팬들 조용하네 ㅋㅋ", "한 골 더!!", "추가골 가자", "오늘 편하게 본다", "{score} 좋다 좋아",
                 "방심하지 말고", "클린시트 가자", "{o} 오늘 답 없네"],
    "fan_trail": ["아직 시간 있다", "한 골만 넣자", "{t} 제발", "동점 가자", "공격 좀 올려라", "왜 슈팅을 안 때리냐", "교체 좀 해라",
                  "이거 뒤집는다 무조건", "하 답답하다", "{p} 뭐하냐 오늘"],
    "late_fan": ["추가시간 몇 분 줌?", "이제 버텨야 됨", "시간 끌기 들어가냐", "마지막 한 방", "심장 떨린다", "제발 끝나라", "집중 집중"],
    "late_neu": ["추가시간 몇 분임?", "이제 진짜 얼마 안 남음", "막판 치열하다", "마지막까지 모른다", "누가 이길지 모르겠네"],
    "blowout": ["오늘 한 팀만 뛰네", "스코어 {score} 실화냐", "이건 끝났다", "{o} 멘탈 나갔다 ㅋㅋ", "골 잔치네"],
    "super_goal": ["{t} 골 기념!!", "{p} 사랑해요!!", "골 기념 후원 ㅋㅋ", "오늘 이기면 치킨 쏜다", "{t} 화이팅!!", "이 맛에 봅니다",
                   "골 들어가자마자 후원함 ㅋㅋ", "{t} 오늘 우승각"],
    "agree": ["ㄹㅇ", "ㅇㅈ", "ㄹㅇㅋㅋ", "인정", "ㅋㅋㅋㅋ 맞말", "이건 맞지", "ㄴㄴ 아님", "@{n} ㄹㅇ", "@{n} ㅋㅋㅋ", "@{n} ㄴㄴ"],
    "ans_min": ["{min}분", "{min}분임", "지금 {min}분", "{min}분쯤"],
    "ans_score": ["{score}", "{score}임", "지금 {score}", "{home} {hs} {away} {as}"],
})
QUESTIONS = {"몇 분임?": "ans_min", "스코어 몇 대 몇?": "ans_score", "지금 몇 대 몇임?": "ans_score"}
P["neu_idle"].append("지금 몇 대 몇임?")

# 닉네임 재료 — 실제 유튜브 채팅처럼 실명, 영문 이름, @핸들, 일상 닉네임, 채널 이름, 팀 팬 구호가 섞이게
SURNAMES = [("김", "kim"), ("김", "kim"), ("김", "kim"), ("이", "lee"), ("이", "lee"), ("박", "park"), ("박", "park"), ("최", "choi"),
            ("정", "jung"), ("강", "kang"), ("조", "cho"), ("윤", "yoon"), ("장", "jang"), ("임", "lim"), ("한", "han"), ("오", "oh"),
            ("서", "seo"), ("신", "shin"), ("권", "kwon"), ("황", "hwang"), ("안", "ahn"), ("송", "song"), ("홍", "hong")]
GIVENS = [("민준", "minjun"), ("서준", "seojun"), ("도윤", "doyoon"), ("예준", "yejun"), ("시우", "siwoo"), ("하준", "hajun"),
          ("지호", "jiho"), ("주원", "juwon"), ("지훈", "jihoon"), ("준서", "junseo"), ("현우", "hyunwoo"), ("건우", "gunwoo"),
          ("우진", "woojin"), ("민재", "minjae"), ("성민", "sungmin"), ("동현", "donghyun"), ("승우", "seungwoo"), ("재현", "jaehyun"),
          ("민수", "minsu"), ("영호", "youngho"), ("상훈", "sanghoon"), ("태훈", "taehoon"), ("정우", "jungwoo"), ("진영", "jinyoung"),
          ("서연", "seoyeon"), ("지우", "jiwoo"), ("하은", "haeun"), ("수아", "sua"), ("민서", "minseo"), ("지민", "jimin"),
          ("예린", "yerin"), ("유나", "yuna"), ("수빈", "subin"), ("은지", "eunji")]
CASUAL = ["감자", "고구마", "도토리", "밤톨", "초코", "뭉치", "하루", "콩이", "보리", "모찌", "호빵", "만두", "구름", "라떼", "두부",
          "배고픈곰", "졸린고양이", "퇴근하고싶다", "월요병", "귤까먹는중", "야식러", "잠못드는밤", "치킨은반반", "그냥사람",
          "지나가던행인", "눈팅만함", "새벽감성", "아무개", "무지개", "꿀벌", "햄찌", "펭귄", "다람쥐", "산책가자", "오늘도맑음",
          "축구보는곰", "주말엔축구", "공차는고양이", "왼발잡이", "조기축구에이스", "벤치워머", "만년후보", "침대축구반대"]
CASUAL_TAIL = ["", "", "", "", "", "맘", "아빠", "짱", "님", "이", "22", "99", "0", "123", "_"]
CHANNEL = ["{w}TV", "{w}의 일상", "{w}로그", "{w} 채널", "{w}브이로그", "{g}네 집", "{w}게임", "{g}의 축구일기"]
ENG_WORDS = ["sunny", "daily", "noname", "kkkk", "zzz", "happy", "blue", "moon", "lucky", "chill", "cozy", "gamer", "footy", "pitch",
             "night", "coffee", "mango", "tiger", "panda"]
FAN_TAGS = {"Manchester United": ["ggmu", "mufc", "redevil"], "Liverpool": ["ynwa", "lfc", "kopite"], "Arsenal": ["coyg", "gooner"],
            "Tottenham Hotspur": ["coys", "spurs", "thfc"], "Real Madrid": ["halamadrid", "madridista"],
            "FC Barcelona": ["viscabarca", "culer", "fcb"], "Chelsea": ["ktbffh", "cfc", "blues"], "Manchester City": ["mcfc", "citizen"],
            "FC Bayern München": ["miasanmia", "fcbayern"], "Paris Saint-Germain": ["psg", "icicestparis"], "Juventus": ["juve", "finoallafine"],
            "AC Milan": ["acmilan", "rossoneri"], "Inter": ["inter", "nerazzurri"], "Borussia Dortmund": ["bvb", "echteliebe"]}
FAN_KO = ["{s}팬", "{s} {n}년차", "{s}만 봄", "{s}사랑", "{s}는 못참지", "찐{s}팬", "{s} 우승하자", "{s}의 봄", "{s}팬{d}"]


def _digits() -> str:
    return random.choice(["", "", str(random.randint(1, 99)), str(random.randint(80, 99)), str(random.randint(1990, 2008)),
                          "%02d%02d" % (random.randint(1, 12), random.randint(1, 28))])


LAUGH_RX = re.compile(r"ㅋ{2,}")


# ---------------------------------------------------------------------------
# 자가 보완: AI가 채팅 기록을 보고 고른 어색한 문장·닉네임은 빼고, 새로 만든 것은 보탬
# ---------------------------------------------------------------------------
POOL_DESC = {
    "celeb": "응원하는 팀이 골을 넣었을 때 팬의 환호", "groan": "응원하는 팀이 실점했을 때 팬의 한숨·변명",
    "ngoal": "중립 시청자가 골 장면을 보고", "save": "골키퍼 선방", "miss": "결정적인 슈팅을 놓침", "post": "슈팅이 골대를 맞음",
    "penalty": "페널티킥 선언", "yellow": "경고 카드", "red": "퇴장", "var": "VAR·판정 논란", "offside": "오프사이드",
    "corner": "코너킥", "freekick": "프리킥", "sub": "선수 교체", "half": "전반 종료", "end": "경기 종료", "kickoff": "킥오프",
    "fan_idle": "평소 팬의 응원·신경전 잡담", "neu_idle": "평소 중립 시청자의 잡담", "fan_lead": "응원 팀이 이기고 있을 때",
    "fan_trail": "응원 팀이 지고 있을 때", "late_fan": "경기 막판 팬", "win": "응원 팀이 이겼을 때", "lose": "응원 팀이 졌을 때",
}
LEARNED: dict = {"lines": {}, "names": [], "banned": [], "banned_names": []}
_BASE_POOLS: dict = {}


def load_learned():
    try:
        if LEARN_PATH.exists():
            d = json.loads(LEARN_PATH.read_text(encoding="utf-8"))
            for k in LEARNED:
                if isinstance(d.get(k), type(LEARNED[k])):
                    LEARNED[k] = d[k]
    except Exception:
        log.exception("learned load failed")
    apply_learned()


def save_learned():
    if DEMO:
        return
    try:
        LEARN_PATH.write_text(json.dumps(LEARNED, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        log.exception("learned save failed")


def apply_learned():
    """내장 문장 + 배운 문장 − 뺀 문장 으로 문장 목록을 다시 만듦 (목록이 너무 줄지는 않게)"""
    if not _BASE_POOLS:
        _BASE_POOLS.update({k: list(v) for k, v in P.items()})
    banned = set(LEARNED["banned"])
    for k, base in _BASE_POOLS.items():
        merged = list(dict.fromkeys(base + LEARNED["lines"].get(k, [])))
        kept = [t for t in merged if t not in banned]
        P[k] = kept if len(kept) >= 4 else merged


def valid_line(text: str) -> str | None:
    t = clean_ai_text(text, "normal")
    if not t or len(t) > 30:
        return None
    if re.search(r"\{(?![topk]\})", t) or "}" in t.replace("{t}", "").replace("{o}", "").replace("{p}", "").replace("{k}", ""):
        return None                       # 모르는 {자리}는 안 됨
    low = norm(t)
    for team in TEAMS:                    # 특정 팀 이름을 박아 넣은 문장은 다른 경기에 못 쓰니 뺌
        if any(len(norm(a)) >= 2 and norm(a) in low for a in [team["ko"], *team["alias"]]):
            return None
    return t


def valid_name(name: str) -> str | None:
    n = re.sub(r"\s+", " ", str(name or "")).strip()
    if not (2 <= len(n) <= 20) or re.search(r"[<>{}\[\]\n]|http|www\.", n):
        return None
    if n.count(" ") > 2 or FORMAL_RX.search(n):
        return None
    if any(norm(n) == norm(a) for t in TEAMS for a in [t["ko"], t["en"], *t["alias"]]):
        return None                       # 팀 이름 그 자체는 닉네임으로 안 씀
    return n


JOSA_PAIRS = {"이": ("이", "가"), "가": ("이", "가"), "은": ("은", "는"), "는": ("은", "는"), "을": ("을", "를"), "를": ("을", "를"),
              "과": ("과", "와"), "와": ("과", "와")}


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


class Viewer:
    """채팅에 계속 나오는 한 사람. 닉네임·멤버 여부·말버릇이 경기 내내 같음."""

    def __init__(self, name: str, faction: str, kind: str):
        self.name, self.faction, self.kind = name, faction, kind
        self.weight = min(25.0, random.paretovariate(1.3))   # 몇몇 사람이 유독 많이 씀
        self.laugh = random.choice([2, 3, 3, 4, 4, 5, 6, 8])
        self.nospace = random.random() < 0.25
        self.tail = random.choice(["", "", "", "", "", "ㅋㅋ", "!!", "~", "ㅎㅎ", "..", "ㅠ"])

    def style(self, text: str, light: bool = False) -> str:
        t = LAUGH_RX.sub(lambda _m: "ㅋ" * max(2, self.laugh + random.randint(-1, 2)), text)
        if self.nospace and len(t) <= 16 and random.random() < 0.6:
            t = t.replace(" ", "")
        if light:
            return t
        if self.tail and random.random() < 0.35 and not t.endswith(("ㅋ", "!", "?", "~", "ㅠ", "ㅎ", ".")):
            t += ("" if self.nospace or self.tail in ("!!", "~", "..") else " ") + self.tail
        if t.endswith("?") and random.random() < 0.2:
            t += "?"
        elif t.endswith("!") and random.random() < 0.1:
            t += "!" * random.randint(1, 3)
        return t


class Audience:
    """시청자 무리. 세력 비율대로 사람을 만들고, 가끔 새 사람이 들어옴."""

    def __init__(self, match: "Match"):
        self.m = match
        self.people: list[Viewer] = []
        self.rebuild()

    def make_name(self, faction: str) -> str:
        learned = LEARNED["names"]
        if learned and random.random() < min(0.4, len(learned) / 60):
            n = random.choice(learned)
            return n + (str(random.randint(1, 99)) if random.random() < 0.2 else "")
        for _ in range(5):
            n = self._make_name(faction)
            if n not in LEARNED["banned_names"]:
                return n
        return n

    def _make_name(self, faction: str) -> str:
        side = self.m.side(faction) if faction in ("home", "away") else None
        sk, se = random.choice(SURNAMES)
        gk, ge = random.choice(GIVENS)
        r = random.random()
        if side is not None and side.name and r < 0.14:             # 응원 팀이 드러나는 이름
            t = lookup_team(side.name)
            tags = FAN_TAGS.get(t["en"]) if t else None
            if tags and random.random() < 0.45:
                tag = random.choice(tags)
                return random.choice([tag + _digits(), f"@{tag}_{ge}", f"{ge}_{tag}", tag.upper() + _digits()])
            return random.choice(FAN_KO).format(s=side.short.replace(" ", ""), n=random.randint(3, 25), d=random.randint(1, 99))
        r = random.random()
        if r < 0.20:                                                 # 실명
            return sk + gk
        if r < 0.32:                                                 # 영문 이름
            name = random.choice([f"{ge.capitalize()} {se.capitalize()}", f"{se.capitalize()} {ge.capitalize()}", f"{ge} {se}"])
            return name
        if r < 0.55:                                                 # @핸들
            return "@" + random.choice([
                f"{ge}{_digits()}", f"{se}{ge}{_digits()}", f"{ge[0]}{ge[-1]}{se}{random.randint(1, 99)}", f"{ge}_{se}",
                f"{ge}.{se}", f"{ge}__", f"{random.choice(ENG_WORDS)}_{ge}", f"{ge}{random.choice(ENG_WORDS)}",
                "user-" + "".join(random.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(10))])
        if r < 0.80:                                                 # 일상 닉네임
            return random.choice(CASUAL) + random.choice(CASUAL_TAIL)
        if r < 0.90:                                                 # 채널 이름
            return random.choice(CHANNEL).format(w=random.choice(CASUAL[:20] + [gk]), g=gk)
        return random.choice(ENG_WORDS) + random.choice(["", "", "_", "."]) + random.choice(ENG_WORDS + [ge]) + _digits()

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

    def rename(self, old: str, new: str | None = None):
        for v in self.people:
            if v.name == old:
                v.name = new or self.make_name(v.faction)

    def pick(self, faction: str | None, exclude: str | None = None) -> Viewer:
        if random.random() < 0.08 or not self.people:
            return self.new_person(faction or "neutral")
        pool = [v for v in self.people if (faction is None or v.faction == faction) and v.name != exclude]
        if not pool:
            return self.new_person(faction or "neutral")
        return random.choices(pool, weights=[v.weight for v in pool])[0]


class ChatEngine:
    def __init__(self, match: Match):
        self.m = match
        self.crowd = Audience(match)
        self.recent: list[str] = []

    def pick_faction(self) -> str:
        sp = self.m.split()
        r = random.random() * 100
        if r < sp["home"]:
            return "home"
        if r < sp["home"] + sp["away"]:
            return "away"
        return "neutral"

    def nickname(self, faction: str | None = None) -> str:
        return self.crowd.pick(faction).name

    def choose(self, pool: list[str]) -> str:
        """최근에 쓴 문장은 피해서 고름"""
        fresh = [t for t in pool if t not in self.recent] or pool
        t = random.choice(fresh)
        self.recent = (self.recent + [t])[-45:]
        return t

    def fill(self, t: str, key: str = "home") -> str:
        key = key if key in ("home", "away") else "home"
        players = self.m.lineup_names(key)[:11] or []
        kor = self.m.korean_names(key)
        # 채팅에서는 "맨체스터 유나이티드" 대신 "맨유"처럼 줄여 씀
        words = {"t": self.m.side(key).short, "o": self.m.side(self.m.other(key)).short,
                 "p": random.choice(players) if players else self.m.side(key).short,
                 "k": random.choice(kor) if kor else "한국 선수"}
        t = re.sub(r"\{([topk])\}(이|가|은|는|을|를|과|와)?(?![가-힣])",
                   lambda mm: words[mm.group(1)] + (josa(words[mm.group(1)], mm.group(2)) if mm.group(2) else ""), t)
        t = re.sub(r"\{([topk])\}", lambda mm: words[mm.group(1)], t)
        return (t.replace("{min}", str(self.m.minute or ""))
                 .replace("{home}", self.m.home.short).replace("{away}", self.m.away.short)
                 .replace("{hs}", str(self.m.hs)).replace("{as}", str(self.m.as_))
                 .replace("{score}", f"{self.m.hs}:{self.m.as_}"))

    def msg(self, text: str, faction: str, kind: str | None = None, amount: int = 0, light: bool = False,
            tpl: str | None = None) -> dict:
        v = self.crowd.pick(faction if faction in ("home", "away", "neutral") else None)
        if kind in ("super", "newmember"):
            return {"name": v.name, "text": text, "kind": kind, "amount": amount, "side": v.faction, "tpl": tpl}
        return {"name": v.name, "text": v.style(text, light), "kind": v.kind, "amount": 0, "side": v.faction, "tpl": tpl}

    def say(self, pool_key: str, faction: str, key: str | None = None) -> dict:
        t = self.choose(P[pool_key])
        return self.msg(self.fill(t, key or faction), faction, tpl=t)

    def idle(self) -> dict:
        m = self.m
        f = self.pick_faction()
        late = (m.minute or 0) >= 80
        r = random.random()
        if f == "neutral":
            if late and r < 0.3:
                return self.say("late_neu", f, "home")
            if abs(m.hs - m.as_) >= 3 and r < 0.35:
                return self.say("blowout", f, "home" if m.hs > m.as_ else "away")
            return self.say("neu_idle", f, "home")
        lead = (m.hs - m.as_) * (1 if f == "home" else -1)
        if lead > 0 and r < 0.35:
            return self.say("fan_lead", f)
        if lead < 0 and r < 0.4:
            return self.say("fan_trail", f)
        if late and r < 0.5:
            return self.say("late_fan", f)
        if m.has_korean(f) and random.random() < 0.45:
            return self.say("kor_idle", f)
        return self.say("fan_idle", f)

    def followups(self, msg: dict) -> list[tuple[float, dict]]:
        """다른 사람이 답하거나 맞장구침 → [(몇 초 뒤, 메시지)]"""
        if msg.get("kind") not in ("normal", "member", "mod"):
            return []
        text = msg.get("text", "")
        for q, pool in QUESTIONS.items():
            if text.startswith(q.rstrip("?")):
                if pool == "ans_min" and self.m.minute is None:
                    return []
                if random.random() < 0.75:
                    return [(random.uniform(2.0, 6.0), self.msg(self.fill(self.choose(P[pool])), self.pick_faction()))]
                return []
        if len(text) >= 5 and random.random() < 0.05:
            f = msg.get("side") if random.random() < 0.6 else self.pick_faction()
            v = self.crowd.pick(f, exclude=msg.get("name"))
            reply = self.choose(P["agree"]).replace("{n}", msg.get("name", "").lstrip("@"))
            return [(random.uniform(1.5, 5.0), {"name": v.name, "text": v.style(reply), "kind": v.kind, "amount": 0, "side": v.faction})]
        return []

    def goal(self, scorer: str, n: int = 16) -> list[dict]:
        out = []
        for _ in range(n):
            f = self.pick_faction()
            if f == scorer:
                out.append(self.say("celeb", f, scorer))
            elif f == "neutral":
                out.append(self.say("ngoal", f, scorer))
            else:
                out.append(self.say("groan", f))
        if random.random() < 0.75:
            out.append(self.msg(self.fill(self.choose(P["super_goal"]), scorer), scorer, "super",
                                random.choice([2000, 2000, 5000, 5000, 10000, 20000, 50000])))
        if random.random() < 0.5:
            v = self.crowd.pick(scorer)
            v.kind = "member"      # 이 사람은 이제부터 멤버로 보임
            out.append({"name": v.name, "text": "", "kind": "newmember", "amount": 0, "side": scorer})
        return out

    def burst(self, ev: str, n: int = 8) -> list[dict]:
        if ev == "hgoal":
            return self.goal("home", n)
        if ev == "agoal":
            return self.goal("away", n)
        if ev == "end":
            out = []
            winner = "home" if self.m.hs > self.m.as_ else ("away" if self.m.as_ > self.m.hs else None)
            for _ in range(n):
                f = self.pick_faction()
                if winner and f == winner:
                    out.append(self.say("win", f))
                elif winner and f in ("home", "away"):
                    out.append(self.say("lose", f))
                else:
                    out.append(self.say("end", f, "home"))
            out.append(self.msg("오늘 경기 수고하셨습니다!", "neutral", "super", random.choice([2000, 5000, 10000])))
            return out
        pool = P.get(ev, P["neu_idle"])
        out = []
        for _ in range(min(n, len(pool))):
            f = self.pick_faction()
            t = self.choose(pool)
            out.append(self.msg(self.fill(t, f if f != "neutral" else "home"), f, tpl=t))
        return out

    def echo(self, text: str) -> list[dict]:
        """이벤트가 아닌 해설 문장에 가볍게 반응"""
        out = []
        for key in ("home", "away"):
            kor = self.m.korean_names(key)
            if names_in_text(text, kor) and random.random() < 0.8:
                for _ in range(random.randint(1, 3)):
                    out.append(self.say("echo_kor", key))
            aliases = [self.m.side(key).name] + self.m.lineup_names(key)
            if names_in_text(text, [a for a in aliases if a]) and random.random() < 0.35:
                out.append(self.say("echo_fan", key))
        return out


# ---------------------------------------------------------------------------
# 이 PC에서 도는 AI (Ollama)
# ---------------------------------------------------------------------------
class LocalAI:
    BASE = "http://127.0.0.1:11434"

    def __init__(self, cfg):
        self.cfg = cfg
        self._ok = False
        self._checked = 0.0
        self._lock = threading.Lock()

    @property
    def model(self):
        return self.cfg.get("ollama_model") or "gemma3:4b"

    def _req(self, path, payload=None, timeout=10):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(self.BASE + path, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def ensure_server(self):
        try:
            self._req("/api/tags", timeout=2)
            return
        except Exception:
            pass
        exe = shutil.which("ollama")
        if not exe and IS_WIN:
            cand = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
            exe = str(cand) if cand.exists() else None
        if exe:
            try:
                flags = 0x08000000 if IS_WIN else 0  # CREATE_NO_WINDOW
                subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
                log.info("started ollama serve")
            except Exception:
                log.exception("ollama start failed")

    def available(self) -> bool:
        if not self.cfg.get("use_ai", True):
            return False
        now = time.time()
        if now - self._checked < 30:
            return self._ok
        self._checked = now
        try:
            tags = self._req("/api/tags", timeout=2)
            names = [m.get("name", "") for m in tags.get("models", [])]
            base = self.model.split(":")[0]
            self._ok = any(n == self.model or n.split(":")[0] == base for n in names)
        except Exception:
            self._ok = False
        return self._ok

    def _chat(self, prompt, schema, images=None, num_predict=900, timeout=90):
        msg = {"role": "user", "content": prompt}
        if images:
            msg["images"] = images
        payload = {"model": self.model, "messages": [msg], "stream": False, "keep_alive": "30m",
                   "format": schema, "options": {"temperature": 0.95, "top_p": 0.95, "repeat_penalty": 1.15, "num_predict": num_predict}}
        with self._lock:
            try:
                r = self._req("/api/chat", payload, timeout=timeout)
            except urllib.error.HTTPError:
                payload["format"] = "json"          # 오래된 Ollama 대비
                r = self._req("/api/chat", payload, timeout=timeout)
        text = r.get("message", {}).get("content", "")
        return json.loads(text[text.find("{"): text.rfind("}") + 1])

    def chats(self, prompt: str) -> dict:
        schema = {
            "type": "object",
            "properties": {
                "scored": {"type": "string", "enum": ["home", "away", "unknown", "none"]},
                "chats": {"type": "array", "items": {"type": "object", "properties": {
                    "name": {"type": "string"}, "text": {"type": "string"},
                    "side": {"type": "string", "enum": ["home", "away", "neutral"]},
                    "kind": {"type": "string", "enum": ["normal", "member", "mod", "super"]},
                    "amount": {"type": "integer"}},
                    "required": ["name", "text", "side", "kind", "amount"]}},
            },
            "required": ["scored", "chats"],
        }
        return self._chat(prompt, schema)

    def review(self, prompt: str) -> dict:
        schema = {"type": "object", "properties": {
            "bad_chat_ids": {"type": "array", "items": {"type": "integer"}},
            "bad_name_ids": {"type": "array", "items": {"type": "integer"}},
            "new_lines": {"type": "array", "items": {"type": "object", "properties": {
                "pool": {"type": "string", "enum": list(POOL_DESC)}, "text": {"type": "string"}}, "required": ["pool", "text"]}},
            "new_names": {"type": "array", "items": {"type": "string"}}},
            "required": ["bad_chat_ids", "bad_name_ids", "new_lines", "new_names"]}
        return self._chat(prompt, schema, num_predict=1400, timeout=150)

    def identify(self, jpeg_b64: str) -> dict:
        schema = {"type": "object", "properties": {
            "found": {"type": "boolean"}, "home": {"type": "string"}, "away": {"type": "string"},
            "home_color": {"type": "string"}, "away_color": {"type": "string"}},
            "required": ["found", "home", "away", "home_color", "away_color"]}
        prompt = ("이 이미지는 EA SPORTS FC 26 경기 화면의 스코어보드 부분이야. 엠블럼과 팀 약칭을 보고 두 팀을 알아내.\n"
                  "- home = 스코어보드 왼쪽 팀, away = 오른쪽 팀. 이름은 영어 공식 팀 이름으로.\n"
                  "- home_color/away_color = 그 팀 대표 색 (#RRGGBB).\n"
                  "- 스코어보드가 안 보이거나 확신이 없으면 found=false.")
        return self._chat(prompt, schema, images=[jpeg_b64], num_predict=200, timeout=60)


RULES = """채팅 규칙:
- 시청자는 한국인. 한국 유튜브 라이브 채팅 말투: 반말, 대부분 3~15자(길어도 25자), 띄어쓰기·맞춤법은 대충, 마침표는 거의 안 씀.
- 말투 예: "와 이걸 넣네", "키퍼 뭐함ㅋㅋ", "ㄹㅇ 폼 미쳤다", "아 제발", "심판 뭐하냐", "몇대몇임?", "ㄷㄷ", "이건 PK지".
- 쓰지 말 말투: "~습니다", "~입니다", "정말 멋진 골이에요!", 해설처럼 상황을 설명하는 문장, 이모지 남발, 해시태그, 따옴표.
- 모두 같은 얘기를 하지 말고 섞을 것: 짧은 감탄, 선수 평가, 심판 탓, 농담, 질문, 딴소리, 다른 채팅에 대한 맞장구.
- 작성자 세력(side)을 위 '시청자 세력' 비율대로 섞을 것. 팬은 자기 팀 편에서 반응(좋은 장면엔 환호, 상대 골엔 한숨·변명·신경전), 중립은 재미·분석 위주.
- 해설 내용과 선수 이름에 실제로 반응할 것. 같은 문장 반복 금지.
- 욕설, 비속어, 혐오 표현, 실존 인물 모욕 금지. 팬끼리 가벼운 신경전까지만.
- name은 짧은 닉네임 아무거나. 실존 인물 이름 금지.
- kind는 대부분 normal. amount는 super일 때만 1000~100000 원, 나머지는 0."""
FORMAL_RX = re.compile(r"(습니다|습니까|ㅂ니다|입니다|여러분|#)")


def clean_ai_text(text: str, kind: str) -> str | None:
    """AI가 만든 채팅 중 어색한 것은 버리고, 끝의 마침표 같은 건 다듬음"""
    t = re.sub(r"\s+", " ", str(text or "")).strip().strip('"“”\'「」')
    if not t:
        return None
    if kind == "super":
        return t[:120]
    if FORMAL_RX.search(t) or len(t) > 40:
        return None
    if t.endswith(".") and not t.endswith(".."):
        t = t[:-1]
    return t


class AIWorker(threading.Thread):
    """AI 요청을 한 번에 하나씩 처리. 장면(event) 요청이 흐름(flow) 요청보다 먼저."""

    def __init__(self, ai: LocalAI, bus: queue.Queue):
        super().__init__(daemon=True, name="ai")
        self.ai, self.bus = ai, bus
        self.jobs: queue.PriorityQueue = queue.PriorityQueue()
        self.seq = 0
        self.busy = False

    def submit(self, prio: int, job: dict):
        if prio > 0 and (self.busy or not self.jobs.empty()):
            return  # 흐름·잡담 요청은 밀려 있으면 버림
        self.seq += 1
        self.jobs.put((prio, self.seq, job))

    def run(self):
        while True:
            _, _, job = self.jobs.get()
            self.busy = True
            try:
                if job["type"] == "identify":
                    res = self.ai.identify(job["image"])
                    self.bus.put(("teams_ai", res))
                elif job["type"] == "review":
                    res = self.ai.review(job["prompt"])
                    self.bus.put(("ai_review", {"job": job, "res": res}))
                else:
                    res = self.ai.chats(job["prompt"])
                    self.bus.put(("ai_chats", {"job": job, "res": res}))
            except Exception as e:
                log.warning("ai job failed: %s", e)
                self.bus.put(("ai_failed", job))
            finally:
                self.busy = False


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

    MAX_SEG = 9.0        # 쉬지 않고 이어지는 말은 이 길이에서 끊음 (초)
    END_SIL = 0.45       # 이만큼 조용하면 한 문장이 끝난 것으로 봄 (초)

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
        threads = min(4, max(2, (os.cpu_count() or 4) // 3))
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
        beam = 5 if self._device == "cuda" else 3
        kw = dict(language=lang, beam_size=beam, vad_filter=not vad_done, condition_on_previous_text=False,
                  initial_prompt=prompt or None, temperature=0.0, no_speech_threshold=0.5, log_prob_threshold=-0.8,
                  compression_ratio_threshold=2.2, without_timestamps=True)
        if hot and not self.no_hotwords:
            kw["hotwords"] = hot
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
        if text:
            log.info("stt[%s]: %s", lang or getattr(info, "language", "?"), text)
            self.bus.put(("text", text))

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
                    continue
                piece, buf = buf[start:cut], buf[cut:]
                if len(piece) >= int(0.4 * SR):
                    self.transcribe(piece, vad_done=True)
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
    def __init__(self, cfg, bus: queue.Queue, need_ident_fn, ai_worker: AIWorker, ai: LocalAI):
        super().__init__(daemon=True, name="board")
        self.cfg, self.bus, self.need_ident_fn = cfg, bus, need_ident_fn
        self.aiw, self.ai = ai_worker, ai
        self.stop_flag = threading.Event()
        self.last_ident = 0.0

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
            while not self.stop_flag.is_set():
                t0 = time.time()
                try:
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
                    # 엠블럼 인식: 팀을 아직 모를 때 20초마다
                    if self.need_ident_fn() and time.time() - self.last_ident > 20 and self.ai.available():
                        self.last_ident = time.time()
                        crop = img.convert("RGB")
                        if crop.width < 900:
                            crop = crop.resize((crop.width * 2, crop.height * 2))
                        bio = io.BytesIO()
                        crop.save(bio, format="JPEG", quality=88)
                        self.aiw.submit(0, {"type": "identify", "image": base64.b64encode(bio.getvalue()).decode()})
                except Exception:
                    log.exception("board loop")
                self.stop_flag.wait(max(0.5, 3.0 - (time.time() - t0)))

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
MEMBER, MOD = "#2ba640", "#5e84f1"
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
        self.lbl_title = tk.Label(self.header, text="실시간 채팅  ▾", bg=BG, fg=FG, font=self.f["title"], cursor="hand2")
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

    # ----- 입력창 (보기용) -----
    def build_composer(self):
        cp = self.composer
        for w in cp.winfo_children():
            w.destroy()
        tk.Frame(cp, bg=LINE, height=1).pack(fill="x")
        inner = tk.Frame(cp, bg=BG)
        inner.pack(fill="x", padx=self.px(16), pady=(self.px(12), self.px(8)))
        top = tk.Frame(inner, bg=BG)
        top.pack(fill="x")
        tk.Label(top, image=self.avatar("시청자", self.px(24), self.px(16)), bg=BG).pack(side="left")
        tk.Label(top, text="시청자", bg=BG, fg=FG2, font=self.f["author"]).pack(side="left")
        field = tk.Frame(inner, bg=BG)
        field.pack(fill="x", padx=(self.px(40), 0), pady=(self.px(6), 0))
        tk.Label(field, text="채팅...", bg=BG, fg="#717171", font=self.f["input"], anchor="w").pack(fill="x")
        tk.Frame(field, bg="#717171", height=1).pack(fill="x", pady=(self.px(4), 0))
        foot = tk.Frame(inner, bg=BG)
        foot.pack(fill="x", padx=(self.px(34), 0), pady=(self.px(6), 0))
        tk.Label(foot, text="☺", bg=BG, fg=FG2, font=self.f["title"]).pack(side="left")
        tk.Label(foot, text="➤", bg=BG, fg="#717171", font=self.f["title"]).pack(side="right")
        tk.Label(foot, text="0/200", bg=BG, fg="#717171", font=self.f["small"]).pack(side="right", padx=self.px(8))

    # ----- 메시지 넣기 -----
    def add(self, m: dict):
        # 같은 문장이 연달아 나오면 건너뜀 (진짜 채팅처럼)
        if m["kind"] in ("normal", "member", "mod"):
            recent = getattr(self, "_recent", [])
            if m["text"] in recent:
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
            tag = m["kind"] if m["kind"] in ("member", "mod") else "author"
            t.insert("end", m["name"], (tag,))
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

        m.add_command(label="선발 명단 설정…", command=self.app.open_lineup_editor)
        m.add_command(label="선수 기록 넣기 (골·카드·교체)…", command=self.app.open_mark_dialog)
        m.add_command(label="팀 직접 정하기…", command=self.app.open_team_dialog)
        m.add_separator()
        m.add_checkbutton(label="해설 자막 보기", variable=self.v_trans, command=toggle_trans)
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
            players = [{"no": no.get().strip(), "name": nm.get().strip()} for no, nm in col["rows"]]
            bench = []
            for part in re.split(r"[,，]", col["bench"].get()):
                part = part.strip()
                if not part:
                    continue
                mm = re.match(r"^(\d{1,2})\s*(.*)$", part)
                bench.append({"no": mm.group(1), "name": mm.group(2).strip()} if mm else {"no": "", "name": part})
            cfg.setdefault("lineups", {})[col["label"]] = {"formation": col["formation"].get().strip() or "4-3-3",
                                                           "players": players, "bench": bench, "color": col["color"]}
        cfg["lineup_visible"] = True
        self.app.chat.v_lineup.set(True)
        save_cfg(cfg)
        self.app.refresh_overlay()
        self.top.destroy()


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
        load_learned()
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
        self.engine = ChatEngine(self.match)
        self.ai = LocalAI(self.cfg)
        self.aiw = AIWorker(self.ai, self.bus)
        self.aiw.start()
        self.chat = ChatWindow(self)
        self.overlay = LineupOverlay(self)
        self.session_on = False
        self.live = False                  # 킥오프 버튼을 눌렀는지 (눌러야 채팅이 나옴)
        self.kickoff_at = 0.0
        self.demo_fed = False
        self.stt: AudioSTT | None = None
        self.board: BoardWatcher | None = None
        self.queue: list[tuple[float, dict]] = []   # (보여 줄 시각, 메시지) — 시각 순
        self.hype = 0.0                    # 큰 장면 직후 채팅이 몰리는 정도 (시간이 지나면 줄어듦)
        self.hype_t = time.time()
        self.last_pool_req = 0.0
        self.chat_log: list[dict] = []       # 화면에 나온 채팅 (자가 보완용)
        self.last_review = time.time()
        self.viewers = 0
        self.last_seen: dict[str, float] = {}
        self.pending_goal_at = 0.0
        self.board_prev = None
        self.board_stable = None
        self.teams_known = False
        self.teams_locked = False
        self.last_ai_flow = 0.0
        self.last_ai_comment_n = 0
        self.alias_counts: dict[str, int] = {}
        self.idle_pool: list[dict] = []
        self.place_chat_window()
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.root.after(100, self.poll)
        self.root.after(4000, self.tick_viewers)
        self.root.after(1000, self.watch_obs)
        self.root.after(3000, self.tick_flow)
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
        if self.cfg.get("use_ai", True):
            threading.Thread(target=self.ai.ensure_server, daemon=True).start()
        if not self.args.demo:
            self.stt = AudioSTT(self.cfg, self.bus, self.whisper_prompt)
            self.stt.start()
            self.board = BoardWatcher(self.cfg, self.bus, lambda: not self.teams_known and not self.teams_locked, self.aiw, self.ai)
            self.board.start()
        self.viewers = int(self.match.viewer_floor() * (1 + random.random() * 0.12))
        self.chat.set_viewers(self.viewers)
        self.refresh_overlay()
        self.request_idle_pool()
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
        self.teams_known = False
        self.teams_locked = False
        self.board_prev = self.board_stable = None
        self.match.reset_for_new_match()
        self.overlay.render()
        self.root.withdraw()

    # ----- 자동 설정 (메뉴에서 뺀 항목들) -----
    def auto_settings(self):
        c = self.cfg
        c["use_ai"] = True            # AI가 없으면 LocalAI.available()이 알아서 내장 문장으로
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
        log.info("kickoff pressed")
        self.chat.show_kickoff(False)
        # 새 경기: 지난 채팅과 선수 기록은 자동으로 지움
        self.chat.clear()
        self.match.marks.clear()
        self.match.events.clear()
        self.refresh_overlay()
        self.last_seen["kickoff"] = time.time()      # 해설의 "킥오프"와 겹쳐서 두 번 반응하지 않게
        self.match.push_event("킥오프")
        self.add_hype(1.5)
        self.enqueue(self.engine.burst("kickoff", random.randint(5, 7)), 0.3, 5.0)
        self.ai_event("kickoff", "")
        self.update_state_line()
        if self.args.demo and not self.demo_fed:
            self.demo_fed = True
            self.root.after(2500, self.demo_feed)

    def pause_chat(self, reason: str = ""):
        """경기가 끝났거나 새 경기가 시작되면 자동으로 킥오프 전으로"""
        if not self.live:
            return
        log.info("chat paused: %s", reason)
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
        if color and re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            side.color = color

    def teams_changed(self):
        self.teams_known = True
        self.match.reset_for_new_match()
        self.on_split_changed()
        self.refresh_overlay()
        self.request_idle_pool()
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
        hot = " ".join([m.home.name, m.away.name, *names]).strip()
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
        base = 0.3 * (max(200, self.viewers) / 1000) ** 0.35
        mult = SPEED_MULT.get(self.cfg.get("speed", "normal"), 1.0)
        return max(0.1, min(12.0, base * mult * (1 + self.cur_hype())))

    def emit(self, m: dict):
        self.chat.add(m)
        if m["kind"] in ("normal", "member", "mod"):
            self.chat_log = (self.chat_log + [m])[-60:]
        now = time.time()
        for d, f in self.engine.followups(m):
            self.queue.append((now + d, f))
        self.queue.sort(key=lambda q: q[0])

    def next_idle(self) -> dict:
        if self.idle_pool and random.random() < 0.45:
            side, text = self.idle_pool.pop(random.randrange(len(self.idle_pool)))
            if len(self.idle_pool) < 6:
                self.request_idle_pool()
            return self.engine.msg(text, side, light=True)
        return self.engine.idle()

    def tick_chat(self):
        """채팅 한 줄씩 내보내기. 간격은 무작위(푸아송)라 몰렸다 뜸했다 함."""
        if self.session_on and self.live:
            now = time.time()
            # 너무 늦어진 반응은 버림 (장면이 지나갔는데 뒤늦게 나오면 어색함)
            self.queue = [q for q in self.queue if now - q[0] < 12 or q[1]["kind"] == "super"]
            if self.queue and self.queue[0][0] <= now:
                self.emit(self.queue.pop(0)[1])
            elif not self.queue or random.random() < 0.25:
                self.emit(self.next_idle())
        gap = random.expovariate(self.chat_rate())
        self.root.after(int(max(60, min(8000, gap * 1000))), self.tick_chat)

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
        elif kind == "teams_ai":
            if data.get("found") and data.get("home") and data.get("away") and not self.teams_locked:
                self.set_team("home", data["home"], color=data.get("home_color"))
                self.set_team("away", data["away"], color=data.get("away_color"))
                self.teams_changed()
        elif kind == "ai_chats":
            self.on_ai_chats(data)
        elif kind == "ai_review":
            self.on_ai_review(data)
        elif kind == "obs":
            if data != self.obs_on:
                self.obs_on = data
                self.cfg["chroma"] = data
                log.info("obs %s -> chroma %s", "on" if data else "off", data)
                self.chat.apply_theme()
        elif kind == "ai_failed":
            job = data
            if job.get("fallback_ev"):
                self.enqueue(self.engine.burst(job["fallback_ev"], 8))

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
        ev = detect_event(text)
        if ev:
            self.apply_marks(ev, text)
        if ev and self.cooldown_ok(ev):
            self.fire(ev, text)
        else:
            self.enqueue(self.engine.echo(text))

    def apply_marks(self, ev, text):
        """해설 속 선수 이름으로 선발 명단에 카드·교체 표시 (채팅 반응 쿨다운과 상관없이)"""
        m = self.match
        if ev not in ("yellow", "red", "sub"):
            return
        key_name = [(k, n) for k in ("home", "away") for n in names_in_text(text, m.lineup_names(k))]
        if ev in ("yellow", "red"):
            key_name = key_name[:1]  # 카드는 한 명
        for k, n in key_name:
            if ev == "sub":
                m.mark(k, n, "on" if m.is_bench(k, n) else "off")
            else:
                team = m.side(k).label
                last = m.marks.get(team, {}).get(n, {}).get("_card_at", 0)
                if time.time() - last < 20:      # 같은 카드를 해설이 반복해도 한 번만
                    continue
                m.mark(k, n, ev)
                m.marks[team][n]["_card_at"] = time.time()
        if key_name:
            self.refresh_overlay()

    def player_side(self, name):
        for key in ("home", "away"):
            if name in self.match.lineup_names(key) or name in self.match.korean_names(key):
                return key
        return None

    def fire(self, ev, text=""):
        m = self.match
        self.add_hype({"score": 1.5, "red": 2.5, "penalty": 2.0, "end": 2.0, "kickoff": 1.0, "half": 0.8,
                       "save": 1.2, "miss": 1.0, "post": 1.3, "var": 1.0, "yellow": 0.6}.get(ev, 0.4))
        if ev == "score":
            has_ocr = self.board_stable is not None
            if has_ocr:
                # 스코어보드가 확인해 줄 때까지 짧게 반응만
                self.pending_goal_at = time.time()
                self.enqueue([self.engine.say("hint", self.engine.pick_faction(), "home") for _ in range(3)], 0.2, 2.5)
                return
            # 스코어보드가 없으면 해설 속 이름으로 어느 팀인지 판단
            side = None
            for key in ("home", "away"):
                if names_in_text(text, [m.side(key).name, *m.lineup_names(key), *m.korean_names(key)]):
                    side = key if side is None else "both"
            if side in ("home", "away"):
                self.goal(side, text)
            else:
                self.enqueue(self.engine.burst("hint", 5), 0.2, 2.5)
                self.ai_event("score", text)
            return
        if ev in MINOR:
            self.enqueue(self.engine.burst(ev, random.randint(3, 4)))
            m.push_event(EV_DESC[ev])
            return
        m.push_event(EV_DESC.get(ev, ev))
        if ev in BIG:
            self.bump_viewers()
        if ev == "end":
            self.enqueue(self.engine.burst("end", 6))
            ko = self.kickoff_at
            # 2분 뒤 킥오프 전으로 (그 사이 새 경기 킥오프를 눌렀으면 건드리지 않음)
            self.root.after(120000, lambda: self.kickoff_at == ko and self.pause_chat("경기 종료"))
        else:
            self.enqueue(self.engine.burst(ev, 3))
        self.ai_event(ev, text)
        if ev in ("kickoff", "half"):
            self.request_idle_pool()

    def goal(self, side, text="", ai_msgs=None):
        m = self.match
        if side == "home":
            m.hs += 1
        else:
            m.as_ += 1
        ev = "hgoal" if side == "home" else "agoal"
        m.push_event(f"{m.side(side).label} 득점")
        # 득점자: 최근 25초 해설에서 그 팀 선수 이름
        scorer = None
        cands = m.lineup_names(side)
        for chunk in [text] + [t for ts, t in reversed(m.commentary) if time.time() - ts < 25]:
            hit = names_in_text(chunk, cands) if chunk else []
            if hit:
                scorer = hit[0]
                break
        if scorer:
            m.mark(side, scorer, "goal")
            if m.is_bench(side, scorer):
                m.mark(side, scorer, "on")
        self.refresh_overlay()
        self.bump_viewers()
        self.add_hype(3.0)
        self.update_state_line()
        if ai_msgs:
            self.enqueue(self.engine.goal(side, 4) + ai_msgs)
        elif self.ai_ready():
            self.enqueue(self.engine.goal(side, 5))
            self.ai_event(ev, text)
        else:
            self.enqueue(self.engine.goal(side, 16))

    def on_board(self, d):
        m = self.match
        if d.get("minute") is not None:
            if m.minute is not None and m.minute >= 60 and d["minute"] <= 3:
                self.pause_chat("경기 시간이 처음으로 돌아감 (새 경기)")
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

    # ----- AI -----
    def context(self) -> str:
        m = self.match
        sp = m.split()
        kor = "; ".join(f"{m.side(k).label}에 한국 선수({', '.join(m.korean_names(k))})가 있어 한국인 시청자 일부가 이 팀을 응원"
                        for k in ("home", "away") if m.has_korean(k))
        recent = "\n".join("- " + t for _, t in m.commentary[-8:]) or "- (아직 없음)"
        return (f"홈 팀: {m.home.label} (선수: {', '.join(m.lineup_names('home')[:11]) or '정보 없음'})\n"
                f"원정 팀: {m.away.label} (선수: {', '.join(m.lineup_names('away')[:11]) or '정보 없음'})\n"
                f"현재 스코어: {m.score_text()}\n"
                f"경기 시간: {str(m.minute) + '분' if m.minute is not None else '알 수 없음'}\n"
                f"시청자 세력: {m.home.label} 팬 {sp['home']:.1f}%, {m.away.label} 팬 {sp['away']:.1f}%, 중립 {sp['neutral']:.1f}%"
                + (f"\n참고: {kor}" if kor else "") +
                f"\n최근 사건: {' / '.join(m.events[-6:]) or '없음'}\n"
                f"최근 게임 해설(음성 받아쓰기라 오타가 있을 수 있음):\n{recent}")

    def ai_ready(self):
        return self.cfg.get("use_ai", True) and self.ai.available()

    def ai_event(self, ev, text):
        if not self.ai_ready():
            if ev in ("red", "penalty", "end"):
                self.enqueue(self.engine.burst(ev, 7))
            return
        n = {"hgoal": 14, "agoal": 14, "score": 12, "end": 12, "red": 10, "penalty": 10}.get(ev, 8)
        desc = {"hgoal": f"{self.match.home.label} 득점!", "agoal": f"{self.match.away.label} 득점!"}.get(ev, EV_DESC.get(ev, ev))
        sup = ("큰 장면이니 kind super(후원 채팅)를 1~2개 섞을 것. 후원은 주로 기뻐하는 쪽 팬이 보냄." if ev in BIG or ev == "score"
               else "kind super는 쓰지 말 것.")
        who = ("scored에는 해설 문맥으로 판단한 득점 팀(home/away), 모르면 unknown." if ev == "score" else "scored는 none.")
        prompt = (f"너는 한국 축구 게임(FC 26) 방송의 유튜브 라이브 채팅 생성기야. 방금 장면에 시청자들이 반응하는 채팅 {n}개를 만들어.\n\n"
                  f"{self.context()}\n\n방금 해설: {text or '(자료 없음)'}\n감지된 장면: {desc}\n\n{RULES}\n- {sup}\n- {who}")
        self.aiw.submit(0, {"type": "chat", "prompt": prompt, "ev": ev, "fallback_ev": ev if ev in ("hgoal", "agoal", "end") else None})

    def request_idle_pool(self):
        if not self.ai_ready() or time.time() - self.last_pool_req < 40:
            return
        self.last_pool_req = time.time()
        prompt = (f"너는 한국 축구 게임(FC 26) 방송의 유튜브 라이브 채팅 생성기야. 특별한 사건이 없을 때 흘러가는 평범한 잡담 30개를 만들어. "
                  f"팬들의 응원·신경전, 중립 팬의 전술 이야기, 선수 이야기, 인사, 먹을 것, 예측 같은 주제. 골이나 실점 이야기는 하지 말 것.\n\n"
                  f"{self.context()}\n\n{RULES}\n- kind super는 쓰지 말 것.\n- scored는 none.")
        self.aiw.submit(1, {"type": "chat", "prompt": prompt, "idle": True})

    def tick_flow(self):
        n = len(self.match.commentary)
        if (self.session_on and self.live and n > self.last_ai_comment_n and time.time() - self.last_ai_flow > self.cfg.get("ai_interval_sec", 20)
                and self.ai_ready()):
            self.last_ai_flow = time.time()
            self.last_ai_comment_n = n
            k = random.randint(5, 7)
            prompt = (f"너는 한국 축구 게임(FC 26) 방송의 유튜브 라이브 채팅 생성기야. 방금까지의 해설 흐름을 보고 시청자들이 쓸 법한 채팅 {k}개를 만들어. "
                      f"큰 사건이 없으면 경기 흐름, 선수, 해설이 한 말에 대한 가벼운 반응과 팬끼리의 신경전 위주로.\n\n"
                      f"{self.context()}\n\n{RULES}\n- kind super는 쓰지 말 것.\n- scored는 none.")
            self.aiw.submit(2, {"type": "chat", "prompt": prompt})
        elif (self.session_on and self.live and self.cfg.get("self_review", True) and len(self.chat_log) >= 30
              and time.time() - self.last_review > self.cfg.get("review_interval_sec", 120) and self.ai_ready()):
            self.request_review()
        self.root.after(3000, self.tick_flow)

    # ----- 자가 보완 -----
    def request_review(self):
        self.last_review = time.time()
        log_rows = self.chat_log[-40:]
        names = list(dict.fromkeys(m["name"] for m in log_rows))
        chats = "\n".join(f"{i}. [{m['name']}] {m['text']}" for i, m in enumerate(log_rows))
        name_list = "\n".join(f"{i}. {n}" for i, n in enumerate(names))
        pools = "\n".join(f"- {k}: {v}" for k, v in POOL_DESC.items())
        prompt = (
            "너는 한국 유튜브 라이브 채팅을 아주 많이 본 검수자야. 아래는 축구 게임(FC 26) 방송에서 자동으로 만든 가짜 채팅 기록이야. "
            "진짜 한국 시청자가 쓴 것처럼 보이게 다듬는 게 목표야.\n\n"
            f"[채팅 기록]\n{chats}\n\n[닉네임 목록]\n{name_list}\n\n"
            "할 일:\n"
            "1. bad_chat_ids: 실제 채팅에서는 안 쓸 어색한 채팅 번호 (번역투, 기계적인 문장, 상황에 안 맞는 말, 너무 반복되는 말). 괜찮으면 빈 배열.\n"
            "2. bad_name_ids: 실제 유튜브에서 안 보일 어색한 닉네임 번호 (억지 조합, 부자연스러운 단어 붙이기). 괜찮으면 빈 배열.\n"
            "3. new_lines: 아래 상황별로 진짜 한국 라이브 채팅 같은 짧은 문장 12~20개. 팀 이름·선수 이름은 직접 쓰지 말고 "
            "{t}(자기 팀), {o}(상대 팀), {p}(자기 팀 선수) 자리 표시로만. 기존 문장과 겹치지 않게.\n"
            f"{pools}\n"
            "4. new_names: 실제 한국 유튜브 시청자 같은 닉네임 10~15개 (실명 같은 이름, 영문 아이디, @핸들, 귀여운 별명, 채널 이름 등 골고루). "
            "실존 유명인 이름 금지.\n\n"
            "문장 말투: 반말, 3~15자, 마침표 없음, 존댓말·설명조·이모지 남발 금지. 욕설·비하 금지.")
        self.aiw.submit(3, {"type": "review", "prompt": prompt, "rows": log_rows, "names": names})

    def on_ai_review(self, data):
        job, res = data["job"], data["res"]
        rows, names = job["rows"], job["names"]
        banned, renamed, added, new_names = [], [], 0, []
        for i in res.get("bad_chat_ids", [])[:10]:
            if isinstance(i, int) and 0 <= i < len(rows) and rows[i].get("tpl"):
                banned.append(rows[i]["tpl"])
        for n in res.get("new_names", [])[:20]:
            v = valid_name(n)
            if v and v not in LEARNED["names"] and v not in LEARNED["banned_names"]:
                new_names.append(v)
        for i in res.get("bad_name_ids", [])[:10]:
            if isinstance(i, int) and 0 <= i < len(names):
                old = names[i]
                if old not in LEARNED["banned_names"]:
                    LEARNED["banned_names"].append(old)
                self.engine.crowd.rename(old, new_names.pop() if new_names else None)
                renamed.append(old)
        LEARNED["names"] = [n for n in LEARNED["names"] + new_names if n not in LEARNED["banned_names"]][-300:]
        LEARNED["banned_names"] = LEARNED["banned_names"][-500:]
        LEARNED["banned"] = list(dict.fromkeys(LEARNED["banned"] + banned))[-400:]
        for item in res.get("new_lines", [])[:25]:
            pool = item.get("pool") if isinstance(item, dict) else None
            t = valid_line(item.get("text", "")) if pool in POOL_DESC else None
            if t and t not in LEARNED["banned"] and t not in P.get(pool, []):
                LEARNED["lines"].setdefault(pool, []).append(t)
                LEARNED["lines"][pool] = LEARNED["lines"][pool][-60:]
                added += 1
        apply_learned()
        save_learned()
        log.info("self review: -%d lines, -%d names (%s), +%d lines, +%d names",
                 len(banned), len(renamed), ", ".join(renamed), added, len(new_names))

    def on_ai_chats(self, data):
        job, res = data["job"], data["res"]
        msgs, pool = [], []
        for c in res.get("chats", [])[:30]:
            kind = "super" if c.get("kind") == "super" else "normal"
            text = clean_ai_text(c.get("text", ""), kind)
            if not text:
                continue
            side = c.get("side") if c.get("side") in ("home", "away", "neutral") else self.engine.pick_faction()
            if kind == "super":
                try:
                    amt = int(c.get("amount") or 0)
                except (TypeError, ValueError):
                    amt = 0
                msgs.append(self.engine.msg(text, side, "super", min(500000, max(1000, amt or 5000))))
            else:
                # 이름·멤버 표시는 AI 말고 고정된 시청자 무리에서 (같은 사람이 계속 나오게)
                msgs.append(self.engine.msg(text, side, light=True))
                pool.append((side, text))
        if job.get("idle"):
            if len(pool) >= 8:
                self.idle_pool = pool
            return
        if job.get("ev") == "score" and self.board_stable is None:
            sc = res.get("scored")
            if sc in ("home", "away"):
                self.goal(sc, ai_msgs=msgs)
                return
        self.enqueue(msgs, 0.2, 6.0)

    # ----- 주기 작업 -----
    def tick_viewers(self):
        if self.session_on:
            floor = self.match.viewer_floor()
            self.viewers = max(floor, int(self.viewers + (random.random() - 0.52) * self.viewers * 0.01))
            self.chat.set_viewers(self.viewers)
        self.root.after(4000, self.tick_viewers)

    # ----- 창 -----
    def open_lineup_editor(self):
        LineupEditor(self)

    def open_team_dialog(self):
        TeamDialog(self)

    def open_mark_dialog(self):
        MarkDialog(self)

    def quit(self):
        try:
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
