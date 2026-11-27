"""회원 목록(v1.37) — 이 PC 앱에 구글 로그인한 계정을 서버(api/members)에 알리고, 관리자는 목록을 받아 본다.

지점장: "일정관리기 및 자료검색 앱에서 로그인한 목록은 내 관리자 계정으로 회원 리스트를 이메일로 알고 싶어."
  · 알리기: 로그인(계정 확인)이 끝나면 하루 한 번 — 앱 이름 · 판만 보낸다. 이메일은 서버가 그 토큰으로 구글에 직접
    물어 정한다(여기서 보낸 이메일을 믿지 않게 — 보내지도 않는다). 실패해도 조용히 넘어간다(다음에 다시).
  · 보기: 관리자 계정만 — 서버가 관리자인지 확인한다(PC 에서 막는 것이 아니다).
일정관리기(planner/members.py)와 업무자료검색(kbsearch/members.py)이 같은 파일을 쓴다. Qt 를 모른다.
"""

from __future__ import annotations

import sys
import threading
from datetime import date

import requests

URL = "https://jyplanner.vercel.app/api/members"
ENABLED = sys.platform == "win32"     # 직원 PC(윈도)에서만 알린다 — 검사(리눅스)가 진짜 서버로 보내지 않게
APP_NAMES = {"planner": "일정관리기", "kb": "업무자료검색"}

_sent: dict = {}                      # (계정, 앱) → 알린 날
_lock = threading.Lock()


class MembersError(Exception):
    """목록을 못 받은 까닭 — 그대로 화면에 보인다."""


def _due(account: str, app: str, today=None) -> bool:
    key = ((account or "").strip().lower(), app)
    d = (today or date.today()).isoformat()
    with _lock:
        if _sent.get(key) == d:
            return False
        _sent[key] = d
        return True


def report(auth, app: str, ver: str, post=None) -> bool:
    """서버에 '이 계정이 이 앱을 쓴다' 를 알린다 — 성공하면 True(실패는 조용히)."""
    try:
        hdr = dict(auth._headers())
        hdr["Content-Type"] = "application/json"
        r = (post or requests.post)(URL, json={"app": app, "ver": ver}, headers=hdr, timeout=15)
        return getattr(r, "status_code", 0) == 200
    except Exception:
        return False


def report_async(auth, account: str, app: str, ver: str) -> bool:
    """하루 한 번만(같은 계정 · 같은 앱) 뒤에서 알린다. 이번에 보냈으면 True."""
    if not ENABLED or auth is None or not auth.is_connected() or not account:
        return False
    if not _due(account, app):
        return False

    def run():
        if not report(auth, app, ver):
            with _lock:                 # 못 보냈다 — 다음 기회에 다시
                _sent.pop(((account or "").strip().lower(), app), None)
    threading.Thread(target=run, daemon=True).start()
    return True


def fetch(auth, get=None) -> list:
    """관리자 — 회원 목록 [{email, apps: {planner|kb: {first, last, ver, n}}}]. 못 받으면 MembersError."""
    try:
        r = (get or requests.get)(URL, headers=dict(auth._headers()), timeout=20)
    except Exception as e:
        raise MembersError(f"서버에 닿지 못했습니다 — 인터넷 연결을 확인해 주세요. ({type(e).__name__})")
    code = getattr(r, "status_code", 0)
    if code == 200:
        try:
            return list((r.json() or {}).get("members") or [])
        except Exception:
            raise MembersError("서버 답을 읽지 못했습니다.")
    if code == 403:
        raise MembersError("관리자 계정만 볼 수 있습니다.")
    if code == 401:
        raise MembersError("구글 로그인이 풀렸습니다 — 다시 로그인해 주세요.")
    if code == 503:
        raise MembersError("서버 저장소가 아직 준비되지 않았습니다.")
    raise MembersError(f"목록을 받지 못했습니다 (HTTP {code}).")


def short(iso: str) -> str:
    """'2026-11-27T01:00:00.000Z' → 한국 시각 '11/27 10:00'. 없으면 ''."""
    from datetime import datetime, timedelta
    try:
        t = datetime.strptime(str(iso)[:19], "%Y-%m-%dT%H:%M:%S") + timedelta(hours=9)
    except ValueError:
        return ""
    return f"{t.month}/{t.day} {t.hour:02d}:{t.minute:02d}"
