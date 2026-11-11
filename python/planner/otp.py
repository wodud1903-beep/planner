"""휴대폰 인증번호를 PC 에서 바로 — MacroDroid 가 쌓는 '인증문자' 시트를 몇 초마다 본다(v1.31).

지점장: "PC 앱에서 실시간으로 인증번호를 받고 싶어." 폰의 MacroDroid 가 받은 문자를 구글 시트에
쌓고 있다(맨 위가 최신 · A 날짜 · C 본문). PC 는 그 시트의 **맨 위 몇 줄만** 읽어(요청 하나 · 작다)
새로 생긴 줄에서 인증번호를 뽑아 화면에 띄우고 클립보드에 넣는다(otp_popup · main_window).

  · 켤 때 이미 있던 문자는 띄우지 않는다 — 처음 읽은 것은 '본 것' 으로만 둔다.
  · 새 줄 = 지난번 맨 위 줄들보다 **위에** 생긴 줄. 같은 문자가 두 번 와도 자리로 가린다.
    지난번 줄이 안 보이면(누가 줄을 지웠다) 못 보던 줄만 새 것으로 본다.
  · 칸이 시트마다 달라도 되게 — 줄에서 **가장 긴 글**을 본문, 첫 칸을 날짜로 본다.
  · 인증번호 = '인증·승인·확인·보안·OTP·코드' 뒤의 4~8자리 숫자 → 없으면 괄호 안 숫자 → 6자리 숫자.
  · 날짜가 오늘이 아닌 줄은 띄우지 않는다(옛 문자).
  · 시트 주소는 공개 저장소에 적지 않는다 — 설정 창에서 넣는다(plan_cfg.json, PC 끼리 따라간다).
  · 인증번호는 기록(crashlog 등)에 남기지 않는다.
"""

from __future__ import annotations

import re
import sys
import time
import urllib.parse
from datetime import date

from . import config, net, sheets


def _http():
    # ⚠️ net.http 를 **부를 때** 찾는다. 'from .net import http' 로 묶어 두면 검사들이 net.http 를
    #    가짜로 바꿔도 여기는 진짜 인터넷으로 나갔다(v1.31.0~1.31.2 의 검사가 4초마다 구글에 갔다).
    return net.http()

TOP_ROWS = 12            # 머리글 + 맨 위 11줄 — 4초 사이 이보다 많이 오는 일은 없다
POLL_MS = 4000           # 이만큼마다 본다(같은 계정 PC 두 대여도 구글 읽기 한도 안쪽)
BACKOFF_TICKS = 7        # 읽기가 탈나면 이만큼 건너뛴다(약 30초)
# 권한이 없어 못 읽는 것은 기다려도 안 풀린다 — 10분에 한 번만 다시 본다(v1.31.3).
# 기본으로 켜져 있어서, 그 시트를 볼 수 없는 직원 PC 가 30초마다 헛읽기를 하며 읽기 한도를 썼다.
DENIED_TICKS = 150
# 이만큼 넘게 못 봤으면(PC 가 잠들었다 깼다 · 인터넷이 끊겼다 붙었다) 그사이 온 문자는 띄우지 않는다 —
# 아침에 PC 를 깨우면 새벽에 온 옛 인증번호 세 개가 뜨고 클립보드까지 바뀌었다(v1.31.3).
GAP_SEC = 120
# 자리 비움(키보드·마우스를 IDLE_SEC 넘게 안 씀 · 화면 잠금)이면 IDLE_EVERY 번에 한 번만(약 20초) 본다(v1.31.1).
# 구글 시트 읽기 한도가 프로젝트 전체 분당 300회라, 모든 직원 PC 가 4초마다 읽으면 20대에서 닿는다 —
# 닿으면 고객 목록 불러오기 등 다른 시트 기능까지 막힌다. 인증번호는 PC 에서 로그인하는 중에 오므로 빠르기는 그대로.
IDLE_SEC = 120
IDLE_EVERY = 5

_KEY = r"(?:인증|승인|확인|보안|OTP|otp|Otp|코드|code|Code|CODE|비밀번호)"
_RE_KEY = re.compile(_KEY + r"[^0-9\n]{0,20}?(?<!\d)(\d{4,8})(?!\d)")
_RE_BRACKET = re.compile(r"[\[\(【<]\s*(\d{4,8})\s*[\]\)】>]")
_RE_SIX = re.compile(r"(?<![\d\-])(\d{6})(?![\d\-])")
_RE_TAG = re.compile(r"\[([^\[\]\n]{1,24})\]")
_NOT_SENDER = {"web발신", "국외발신", "국제발신", "광고"}
_RE_DATE = re.compile(r"(\d{4})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})")


def idle_seconds() -> float:
    """마지막 키보드·마우스 입력 뒤 지난 초(윈도). 모르면 0(= 쓰는 중으로 본다)."""
    if sys.platform != "win32":
        return 0.0
    try:
        import ctypes

        class _LII(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        li = _LII()
        li.cbSize = ctypes.sizeof(li)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(li)):
            return 0.0
        k32 = ctypes.windll.kernel32
        k32.GetTickCount.restype = ctypes.c_uint
        return ((k32.GetTickCount() - li.dwTime) & 0xFFFFFFFF) / 1000.0
    except Exception:
        return 0.0


def range_a1(tab: str) -> str:
    a1 = f"A1:F{TOP_ROWS}"
    tab = (tab or "").strip()
    return f"'{tab}'!{a1}" if tab else a1          # 탭을 비우면 첫 번째 탭


class NoAccess(Exception):
    """이 계정으로는 인증문자 시트를 볼 수 없다(403 · 404) — 기다려도 안 풀린다."""


def read_top(auth, sheet_id: str, tab: str = "") -> list:
    """시트 맨 위 몇 줄(글자 그대로). 권한이 없으면 NoAccess."""
    url = config.SHEETS_VALUES_URL.format(sheet_id=sheet_id,
                                          rng=urllib.parse.quote(range_a1(tab), safe=""))
    r = _http().get(url, headers=sheets._headers(auth), timeout=10,
                    params={"valueRenderOption": "FORMATTED_VALUE"})
    if r.status_code in (403, 404):
        raise NoAccess(f"HTTP {r.status_code}")
    sheets._check(r)
    return (r.json() or {}).get("values", []) or []


def _is_header(row: list) -> bool:
    cells = [str(c or "").strip() for c in row]
    if not any(cells):
        return False
    if any(re.search(r"\d{4,}", c) for c in cells):
        return False                                 # 숫자가 든 줄은 문자다
    return any(k in c for c in cells for k in ("일시", "날짜", "인증", "내용", "문자", "보낸"))


def rows_of(values: list) -> list:
    """시트 값 → [{date, body, key}] (위에서부터). 머리글·빈 줄은 뺀다."""
    out = []
    for i, row in enumerate(values or []):
        cells = [str(c or "") for c in (row or [])]
        if not any(c.strip() for c in cells):
            continue
        if i == 0 and _is_header(cells):
            continue
        # 본문 = 날짜 칸(A) 뒤에서 가장 긴 칸. ⚠️ 날짜 칸까지 넣고 고르면 "인증 1234" 처럼 짧은 문자는
        #    날짜("2026. 11. 9")가 더 길어 본문으로 뽑혀 번호를 놓쳤다(v1.32 에서 고침).
        rest = [c.strip() for c in cells[1:] if c.strip()]
        body = max(reversed(rest), key=len) if rest else cells[0].strip()   # 길이가 같으면 뒤 칸
        d = cells[0].strip() if cells else ""
        out.append({"date": d, "body": body, "key": d + "\x1f" + body})
    return out


def new_rows(prev_keys, cur_rows: list) -> list:
    """맨 위가 최신. prev_keys = 지난번 줄 열쇠(위에서부터, 처음이면 None). 새로 위에 생긴 줄들."""
    if prev_keys is None:
        return []                                    # 처음 — 이미 있던 것은 띄우지 않는다
    cur = [r["key"] for r in cur_rows]
    if not prev_keys:
        return list(cur_rows)                        # 비어 있던 시트에 처음 들어왔다
    for k in range(len(cur)):
        tail = cur[k:]
        n = min(len(tail), len(prev_keys))
        if tail[:n] == prev_keys[:n]:
            return list(cur_rows[:k])                # 지난번 줄들이 k 칸 밀려 내려갔다
    seen = set(prev_keys)                            # 줄을 지웠거나 순서가 바뀌었다
    return [r for r in cur_rows if r["key"] not in seen]


def extract_code(body: str) -> str:
    s = str(body or "")
    for rx in (_RE_KEY, _RE_BRACKET, _RE_SIX):
        m = rx.search(s)
        if m:
            return m.group(1)
    return ""


def sender_of(body: str) -> str:
    for t in _RE_TAG.findall(str(body or "")):
        t = t.strip()
        if t and t.replace(" ", "").lower() not in _NOT_SENDER:
            return t
    return ""


def parse_day(s: str):
    m = _RE_DATE.search(str(s or ""))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def items_of(rows: list, today: date) -> list:
    """새 줄 → 띄울 인증번호 [{code, sender, body, date}] (위에서부터 · 많아야 3개)."""
    out = []
    for r in rows:
        code = extract_code(r["body"])
        if not code:
            continue
        d = parse_day(r["date"])
        if d is not None and d != today:
            continue                                 # 옛 문자
        out.append({"code": code, "sender": sender_of(r["body"]), "body": r["body"], "date": r["date"]})
    return out[:3]


class Watcher:
    """시트를 볼 때마다 새 인증번호만 돌려준다(통신은 부르는 쪽 스레드에서)."""

    def __init__(self):
        self.prev = None
        self.where = ("", "")
        self.seen_at = 0.0                           # 마지막으로 읽은 때(time.time)

    def reset(self) -> None:
        self.prev = None

    def poll(self, auth, sheet_id: str, tab: str = "", today: date | None = None,
             now: float | None = None) -> list:
        now = time.time() if now is None else now
        where = (sheet_id, tab or "")
        if where != self.where:                      # 시트를 바꿨다 — 그 시트의 지금 것은 '본 것'
            self.where, self.prev = where, None
        if self.prev is not None and now - self.seen_at > GAP_SEC:
            self.prev = None                         # 오래 못 봤다 — 그사이 온 것은 옛 문자다
        rows = rows_of(read_top(auth, sheet_id, tab))
        news = new_rows(self.prev, rows)
        self.prev = [r["key"] for r in rows]
        self.seen_at = now
        return items_of(news, today or date.today())


# ---------------------------------------------------------------- 같은 PC 에서 한 번만(v1.32)
# 일정관리기와 업무자료검색을 한 PC 에서 둘 다 켜 두면 같은 인증번호가 두 번 떴다.
# 먼저 본 쪽이 임시 폴더에 표식을 남기고, 다른 쪽은 그 표식이 있으면 띄우지 않는다.
CLAIM_SEC = 120


def _claim_dir():
    import tempfile
    from pathlib import Path
    d = Path(tempfile.gettempdir()) / "jy_otp_claims"
    d.mkdir(parents=True, exist_ok=True)
    return d


def claim(item: dict, now: float | None = None) -> bool:
    """이 인증번호를 이 PC 에서 처음 띄우는가. 다른 프로그램이 방금(2분 안) 띄웠으면 False."""
    import hashlib
    import os
    now = time.time() if now is None else now
    try:
        d = _claim_dir()
        key = hashlib.sha1("\x1f".join(str(item.get(k) or "") for k in ("code", "date", "body"))
                           .encode("utf-8")).hexdigest()[:20]
        for f in d.iterdir():                        # 오래된 표식은 치운다
            try:
                if now - f.stat().st_mtime > 600:
                    f.unlink()
            except OSError:
                pass
        p = d / key
        try:
            if p.exists() and now - p.stat().st_mtime <= CLAIM_SEC:
                return False
        except OSError:
            pass
        try:
            fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
        except FileExistsError:
            try:
                os.utime(str(p), None)               # 오래된 표식 — 내가 새로 맡는다
            except OSError:
                pass
        return True
    except Exception:
        return True                                  # 표식을 못 남겨도 번호는 띄운다


# ---------------------------------------------------------------- 지난 문자 지우기(v1.32)
# 지점장: "2일만 지나도 자동 삭제". 인증문자 시트에 줄이 끝없이 쌓였다(1,400줄 넘게).
# 관리자 PC 가 가끔(켤 때 · 6시간마다) 맨 아래의 옛 줄을 지운다 — 맨 위가 최신이라 아래부터 본다.
KEEP_DAYS = 2            # 오늘·어제 것만 남긴다(날짜가 이만큼 지난 줄부터 지운다)
CLEAN_EVERY_SEC = 6 * 3600


def old_tail(colA: list, today: date, keep_days: int = KEEP_DAYS) -> tuple:
    """A열 값(1행부터) → 지울 줄 (start, end) 0부터 · end 는 포함 안 함. 지울 것이 없으면 None.

    맨 아래에서 위로 올라가며 '지난 줄(또는 빈 줄)' 이 이어지는 데까지만 — 날짜를 못 읽는 줄을 만나면 멈춘다.
    1행(머리글)은 건드리지 않는다.
    """
    from datetime import timedelta
    cutoff = today - timedelta(days=keep_days)
    n = len(colA)
    start, any_old = n, False
    for i in range(n - 1, 0, -1):
        v = str((colA[i][0] if colA[i] else "") or "").strip()
        if not v:
            start = i
            continue
        d = parse_day(v)
        if d is None or d > cutoff:
            break
        start, any_old = i, True
    return (start, n) if any_old and start < n else None


def clean_old(auth, sheet_id: str, tab: str = "", today: date | None = None) -> int:
    """2일 지난 문자 줄을 시트에서 지운다. 지운 줄 수. (시트를 고칠 수 있는 계정만 된다)"""
    today = today or date.today()
    h = sheets._headers(auth)
    meta = _http().get(config.SHEETS_BASE_URL.format(sheet_id=sheet_id), headers=h, timeout=15,
                       params={"fields": "sheets(properties(sheetId,title))"})
    sheets._check(meta)
    props = [x.get("properties", {}) for x in (meta.json() or {}).get("sheets", [])]
    tab = (tab or "").strip()
    pick = next((x for x in props if x.get("title") == tab), None) if tab else (props[0] if props else None)
    if pick is None:
        return 0
    title = pick.get("title", "")
    r = _http().get(config.SHEETS_VALUES_URL.format(
        sheet_id=sheet_id, rng=urllib.parse.quote(f"'{title}'!A1:A", safe="")), headers=h, timeout=15,
        params={"valueRenderOption": "FORMATTED_VALUE"})
    sheets._check(r)
    span = old_tail((r.json() or {}).get("values", []) or [], today)
    if not span:
        return 0
    body = {"requests": [{"deleteDimension": {"range": {
        "sheetId": int(pick.get("sheetId", 0)), "dimension": "ROWS",
        "startIndex": span[0], "endIndex": span[1]}}}]}
    w = _http().post(config.SHEETS_BATCH_UPDATE_URL.format(sheet_id=sheet_id), headers=h, json=body, timeout=20)
    sheets._check(w)
    return span[1] - span[0]
