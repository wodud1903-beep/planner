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
import urllib.parse
from datetime import date

from . import config, sheets
from .net import http as _http

TOP_ROWS = 12            # 머리글 + 맨 위 11줄 — 4초 사이 이보다 많이 오는 일은 없다
POLL_MS = 4000           # 이만큼마다 본다(같은 계정 PC 두 대여도 구글 읽기 한도 안쪽)
BACKOFF_TICKS = 7        # 읽기가 탈나면 이만큼 건너뛴다(약 30초)

_KEY = r"(?:인증|승인|확인|보안|OTP|otp|Otp|코드|code|Code|CODE|비밀번호)"
_RE_KEY = re.compile(_KEY + r"[^0-9\n]{0,20}?(?<!\d)(\d{4,8})(?!\d)")
_RE_BRACKET = re.compile(r"[\[\(【<]\s*(\d{4,8})\s*[\]\)】>]")
_RE_SIX = re.compile(r"(?<![\d\-])(\d{6})(?![\d\-])")
_RE_TAG = re.compile(r"\[([^\[\]\n]{1,24})\]")
_NOT_SENDER = {"web발신", "국외발신", "국제발신", "광고"}
_RE_DATE = re.compile(r"(\d{4})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})")


def range_a1(tab: str) -> str:
    a1 = f"A1:F{TOP_ROWS}"
    tab = (tab or "").strip()
    return f"'{tab}'!{a1}" if tab else a1          # 탭을 비우면 첫 번째 탭


def read_top(auth, sheet_id: str, tab: str = "") -> list:
    """시트 맨 위 몇 줄(글자 그대로)."""
    url = config.SHEETS_VALUES_URL.format(sheet_id=sheet_id,
                                          rng=urllib.parse.quote(range_a1(tab), safe=""))
    r = _http().get(url, headers=sheets._headers(auth), timeout=10,
                    params={"valueRenderOption": "FORMATTED_VALUE"})
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
        body = max(cells, key=lambda c: len(c.strip())).strip()
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

    def reset(self) -> None:
        self.prev = None

    def poll(self, auth, sheet_id: str, tab: str = "", today: date | None = None) -> list:
        where = (sheet_id, tab or "")
        if where != self.where:                      # 시트를 바꿨다 — 그 시트의 지금 것은 '본 것'
            self.where, self.prev = where, None
        rows = rows_of(read_top(auth, sheet_id, tab))
        news = new_rows(self.prev, rows)
        self.prev = [r["key"] for r in rows]
        return items_of(news, today or date.today())
