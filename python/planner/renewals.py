"""만기 재계약 캠페인 — 만기가 다가오는 고객을 한 줄씩 챙긴다(v1.26).

[고객관리] → [재계약] 에서 만기가 N개월 안에 오는(또는 막 지난) 고객을 급한 순으로 보고,
고객마다 상태를 둔다:  미연락 → 연락함 → 상담중 → 재계약 / 안 함
[멘트 복사] 는 그 고객 이름·차종·금융사·만기일을 채운 안내 글을 복사하고, 아직 '미연락' 이면
'연락함' 으로 바꾼다(안내멘트 [복사] 가 '보냄' 을 남기는 것과 같은 생각).

상태는 renewals.json 에 {고객열쇠|만기일: {s, at, memo}} 로 두고 동기화한다(keyed — 같은 열쇠면
나중에 고친 쪽). 같은 고객이 재계약하면 새 만기일이라 새 줄이다.
알림 서버(아침 브리핑의 '이번 달 만기')와 자동 규칙(만기 D-90·D-30 할일)도 이 기록을 보고
'재계약·안 함' 으로 정리한 고객은 뺀다.
"""

from __future__ import annotations

import json
from datetime import date

from . import auto_rules, config, sheets

FILE = "renewals.json"
STATUSES = ["미연락", "연락함", "상담중", "재계약", "안 함"]
CLOSED = {"재계약", "안 함"}
PAST_DAYS = 30                    # 만기가 지난 건도 한 달은 남겨 둔다(놓친 건이 조용히 사라지지 않게)


def key(cr, d: date) -> str:
    return f"{auto_rules.cust_key(cr)}|{d.isoformat()}"


def load() -> dict:
    try:
        o = json.loads(config.data_file(FILE).read_text(encoding="utf-8"))
        return o if isinstance(o, dict) else {}
    except Exception:
        return {}


def save(store: dict) -> None:
    config.atomic_write(config.data_file(FILE), json.dumps(store, ensure_ascii=False, indent=1))


def status(store: dict, cr, d: date) -> str:
    r = (store or {}).get(key(cr, d))
    s = r.get("s") if isinstance(r, dict) else ""
    return s if s in STATUSES else "미연락"


def closed(store: dict, cr, d: date) -> bool:
    return status(store, cr, d) in CLOSED


def set_status(store: dict, cr, d: date, s: str, memo: str | None = None) -> None:
    k = key(cr, d)
    cur = dict(store.get(k) or {})
    cur["s"] = s if s in STATUSES else "미연락"
    if memo is not None:
        cur["memo"] = memo
    cur["at"] = auto_rules.now_stamp()
    cur["name"] = auto_rules.short_name(cr)        # 사람이 파일을 볼 때 알아보게
    store[k] = cur


def targets(rows, today: date, months: int, store: dict, hide_closed: bool = False) -> list:
    """[(고객 줄, 만기일, D-day, 상태)] — 급한 순(지난 것 먼저, 그다음 가까운 것)."""
    months = max(1, int(months or 0) or 3)
    ahead = months * 31
    out = []
    for cr in rows or []:
        if not (cr.get("customer") or "").strip():
            continue
        if (cr.get("status") or "").strip() == "취소":
            continue
        d = sheets.expiry_date(cr)
        if d is None:
            continue
        left = (d - today).days
        if not (-PAST_DAYS <= left <= ahead):
            continue
        s = status(store, cr, d)
        if hide_closed and s in CLOSED:
            continue
        out.append((cr, d, left, s))
    out.sort(key=lambda x: (x[2], auto_rules.short_name(x[0])))
    return out


def counts(items) -> dict:
    c = {s: 0 for s in STATUSES}
    for _cr, _d, _left, s in items:
        c[s] = c.get(s, 0) + 1
    c["전체"] = len(items)
    done = c["재계약"] + c["안 함"]
    c["성공률"] = round(c["재계약"] * 100 / done) if done else None
    return c


def ment(cr, d: date, template: str = "") -> str:
    return auto_rules.fill(template or auto_rules.RENEW_MENT, cr, None, d)
