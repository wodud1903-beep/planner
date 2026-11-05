"""만기 재계약 캠페인 — 만기가 다가오는 고객을 한 줄씩 챙긴다(v1.26).

[고객관리] → [재계약] 에서 만기가 N개월 안에 오는(또는 막 지난) 고객을 급한 순으로 보고,
고객마다 상태를 둔다:  미연락 → 연락함 → 상담중 → 재계약 / 안 함
[멘트 복사] 는 그 고객 이름·차종·금융사·만기일을 채운 안내 글을 복사하고, 아직 '미연락' 이면
'연락함' 으로 바꾼다(안내멘트 [복사] 가 '보냄' 을 남기는 것과 같은 생각).

상태는 renewals.json 에 {고객열쇠|만기일: {s, at, memo}} 로 두고 동기화한다(keyed — 같은 열쇠면
나중에 고친 쪽). 같은 고객이 재계약하면 새 만기일이라 새 줄이다.
알림 서버(아침 브리핑의 '이번 달 만기')도 이 기록을 보고 '재계약·안 함' 으로 정리한 고객은 뺀다.
(v1.28: 진행현황 자동 규칙은 없앴다 — 고객 열쇠·이름·멘트 채우기 도우미는 여기로 옮겼다)
"""

from __future__ import annotations

import datetime as _dt
import json
from datetime import date

from . import config, sheets

FILE = "renewals.json"
STATUSES = ["미연락", "연락함", "상담중", "재계약", "안 함"]
CLOSED = {"재계약", "안 함"}
PAST_DAYS = 30                    # 만기가 지난 건도 한 달은 남겨 둔다(놓친 건이 조용히 사라지지 않게)


RENEW_MENT = ("{고객} 고객님, 안녕하세요.\n"
              "이용 중이신 {차종}({금융사}) 계약이 {만기일} 만료 예정입니다.\n"
              "재계약 · 반납 · 인수 가운데 유리한 조건을 미리 비교해 안내해 드리겠습니다.\n"
              "편하실 때 연락 주세요. 감사합니다.")


def cust_key(cr) -> str:
    """고객 열쇠 — 안내멘트 '보냄' 기록과 같다(main_window._ment_key): 고객ID, 없으면 순번|이름.
    알림 서버(web/js/brief.js renewKey)도 같은 모양을 쓴다."""
    uid = (getattr(cr, "uid", "") or "").strip()
    if uid:
        return "uid:" + uid
    return f"{getattr(cr, 'seq', '')}|{cr.get('customer')}".strip()


def short_name(cr) -> str:
    """'박성일 / 박가네 백년약초' → '박성일' (멘트·알림에는 사람 이름만)."""
    return (cr.get("customer") or "").split("/")[0].strip()


def fill(text: str, cr, deliver=None, expiry=None) -> str:
    """{고객} {차종} {금융사} {출고일} {만기일} {계약일} 을 채운다(없으면 빈칸)."""
    contract = sheets.parse_date(cr.get("contract_date"))
    rep = {
        "{고객}": short_name(cr), "{차종}": (cr.get("model") or "").strip(),
        "{금융사}": (cr.get("finance") or "").strip(),
        "{출고일}": f"{deliver:%Y-%m-%d}" if deliver else "",
        "{만기일}": f"{expiry:%Y-%m-%d}" if expiry else "",
        "{계약일}": f"{contract:%Y-%m-%d}" if contract else "",
    }
    out = str(text or "")
    for k, v in rep.items():
        out = out.replace(k, v)
    return out


def now_stamp() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def key(cr, d: date) -> str:
    return f"{cust_key(cr)}|{d.isoformat()}"


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
    cur["at"] = now_stamp()
    cur["name"] = short_name(cr)        # 사람이 파일을 볼 때 알아보게
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
    out.sort(key=lambda x: (x[2], short_name(x[0])))
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
    return fill(template or RENEW_MENT, cr, None, d)
