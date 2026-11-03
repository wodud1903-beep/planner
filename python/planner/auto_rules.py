"""진행현황 자동 규칙 — 고객의 상태·날짜가 바뀌면 [내 할일] 이 저절로 생긴다(v1.26).

플로우의 '자동화' 처럼. 규칙은 세 모양이다(설정 → [자동 규칙] 에서 고친다).

  status  : 진행현황에 이 말(쉼표로 여럿)이 **새로 들어가면** → 그날(+며칠) 할일
  deliver : 출고일이 정해지면 → 출고일 ± 며칠에 할일
            출고일이 바뀌면 할일도 옮기고, 미정으로 되돌리거나 취소되면 지운다(안 한 것만)
  expiry  : 계약 만기일 ± 며칠에 할일 — 2주 앞부터 올린다
            만기 재계약 목록에서 '재계약·안 함' 으로 정리했으면 만들지 않는다(있으면 지운다)

할일은 팔로업과 같은 [내 할일](멘트 복사·알람)이다. 멘트 칸에 고객에게 보낼 글을 채워 둔다.

두 번 만들지 않는다 — 만든 것은 auto_done.json 에 {규칙|고객: {title, date, base, at}} 로 적고
동기화한다(사무실·집 PC 가 같은 기록을 본다, sync 의 keyed 합치기). 사용자가 지운 할일은
되살리지 않는다(기록이 남아 있으니까).

**처음 켠 날은 지금 상태를 '본 것' 으로만 적는다** — 그동안 쌓인 '가결' 이 한꺼번에 할일로
몰려오지 않게. 진행현황이 바뀐 것을 알려면 지난번 본 값이 있어야 하므로 auto_seen.json
(이 PC 만, 동기화 안 함)에 둔다. 날짜 규칙은 처음에도 앞으로 올 날짜만 올린다.

무엇을 할지 정하는 것(plan)은 통신·파일 없는 순수 계산이다 — 시트도 구글도 없이 시험한다.
"""

from __future__ import annotations

import datetime as _dt
import json
from datetime import date, timedelta

from . import config, sheets

DONE_FILE = "auto_done.json"     # 동기화(keyed)
SEEN_FILE = "auto_seen.json"     # 이 PC 만

KINDS = {"status": "진행현황이 바뀌면", "deliver": "출고일 기준", "expiry": "만기일 기준"}

# 날짜 규칙을 몇 날 앞까지 미리 올릴지(너무 먼 것은 다음에) — 팔로업과 같은 2주.
# 처음 켠 날 앞으로 두 달치 출고가 한꺼번에 할일로 몰려오지 않게.
AHEAD = {"deliver": 14, "expiry": 14}
# 이만큼 지난 것은 만들지 않고 '처리함' 으로만 적는다
LATE = {"deliver": 0, "expiry": 7}

RENEW_MENT = ("{고객} 고객님, 안녕하세요.\n"
              "이용 중이신 {차종}({금융사}) 계약이 {만기일} 만료 예정입니다.\n"
              "재계약 · 반납 · 인수 가운데 유리한 조건을 미리 비교해 안내해 드리겠습니다.\n"
              "편하실 때 연락 주세요. 감사합니다.")

DEFAULT_RULES = [
    {"id": "approved", "on": True, "kind": "status", "word": "가결, 승인", "days": 0,
     "title": "[승인 안내] {고객}",
     "ment": ("{고객} 고객님, 안녕하세요.\n"
              "신청하신 {차종} {금융사} 심사가 승인되었습니다.\n"
              "출고 일정과 준비하실 서류를 곧 안내해 드리겠습니다. 감사합니다.")},
    {"id": "deliver_prep", "on": True, "kind": "deliver", "word": "", "days": -1,
     "title": "[내일 출고] {고객}",
     "ment": ("내일({출고일}) 출고 준비 확인\n"
              "· 탁송 시간·장소  · 보험 가입  · 등록·번호판 서류  · 고객 안내 연락\n"
              "{고객} / {차종} / {금융사}")},
    {"id": "deliver_thanks", "on": True, "kind": "deliver", "word": "", "days": 1,
     "title": "[출고 감사] {고객}",
     "ment": ("{고객} 고객님, {차종} 출고를 축하드립니다!\n"
              "운행하시다 궁금하거나 불편한 점이 있으면 언제든 편하게 연락 주세요.\n"
              "바쁘시겠지만 짧은 후기 한 줄 남겨 주시면 큰 힘이 됩니다. 감사합니다.")},
    {"id": "renew_90", "on": True, "kind": "expiry", "word": "", "days": -90,
     "title": "[만기 D-90] {고객}", "ment": RENEW_MENT},
    {"id": "renew_30", "on": True, "kind": "expiry", "word": "", "days": -30,
     "title": "[만기 D-30] {고객}",
     "ment": ("{고객} 고객님, 계약 만기({만기일})가 한 달 남았습니다.\n"
              "재계약 여부를 정해 주시면 차량 준비와 서류를 바로 진행하겠습니다. 감사합니다.")},
]


# ---------------------------------------------------------------------------
# 규칙
# ---------------------------------------------------------------------------
def clean_rule(o) -> dict | None:
    if not isinstance(o, dict):
        return None
    kind = str(o.get("kind") or "")
    if kind not in KINDS:
        return None
    rid = str(o.get("id") or "").strip()
    if not rid:
        return None
    try:
        days = max(-365, min(365, int(o.get("days") or 0)))
    except (TypeError, ValueError):
        days = 0
    return {"id": rid, "on": bool(o.get("on", True)), "kind": kind,
            "word": str(o.get("word") or "").strip(), "days": days,
            "title": str(o.get("title") or "").strip() or "[자동] {고객}",
            "ment": str(o.get("ment") or "")}


def rules_of(settings) -> list[dict]:
    """설정에 적힌 규칙(없으면 기본 규칙)."""
    raw = getattr(settings, "auto_rules", None)
    got = [r for r in (clean_rule(x) for x in (raw or [])) if r]
    return got if raw else [dict(r) for r in DEFAULT_RULES]


def words(rule) -> list[str]:
    return [w.strip() for w in str(rule.get("word") or "").replace("/", ",").split(",") if w.strip()]


def describe(rule) -> str:
    """규칙 한 줄 설명(목록에 보인다)."""
    d = int(rule.get("days") or 0)
    if rule["kind"] == "status":
        when = f"진행현황에 '{rule.get('word') or '?'}' 이(가) 들어가면"
        at = "그날" if d == 0 else (f"{d}일 뒤" if d > 0 else f"{-d}일 전")
    else:
        base = "출고일" if rule["kind"] == "deliver" else "만기일"
        when = base
        at = "당일" if d == 0 else (f"{d}일 뒤" if d > 0 else f"{-d}일 전")
    return f"{when} {at} → {rule.get('title')}"


# ---------------------------------------------------------------------------
# 고객 · 글 채우기
# ---------------------------------------------------------------------------
def cust_key(cr) -> str:
    """고객 열쇠 — 안내멘트 '보냄' 기록과 같다(main_window._ment_key): 고객ID, 없으면 순번|이름."""
    uid = (getattr(cr, "uid", "") or "").strip()
    if uid:
        return "uid:" + uid
    return f"{getattr(cr, 'seq', '')}|{cr.get('customer')}".strip()


def short_name(cr) -> str:
    """'박성일 / 박가네 백년약초' → '박성일' (제목·멘트에는 사람 이름만)."""
    return (cr.get("customer") or "").split("/")[0].strip()


def _md(d) -> str:
    return f"{d.month}/{d.day}" if d else ""


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


def _canceled(cr) -> bool:
    from . import board
    return board.stage((cr.get("status") or "").strip()) == board.CANCEL


# ---------------------------------------------------------------------------
# 무엇을 할지 — 순수 계산
# ---------------------------------------------------------------------------
def plan(rows, rules, done: dict, seen: dict | None, today: date, closed=None):
    """→ (할 일 목록, 새 seen).

    할 일: {"op": add|move|remove|mark, "key", "title", "date", "ment", "base", "old"}
      add    — 새 할일
      move   — 날짜가 바뀌었다: old(title·date)의 할일을 date 로 옮긴다(없으면 새로)
      remove — 더는 필요 없다(출고 미정·취소·재계약 정리): old 의 할일을 지운다(안 한 것만)
      mark   — 만들지 않고 '처리함' 으로만(이미 지난 날짜)
    closed(cr, 만기일) → 재계약 목록에서 정리했나(재계약·안 함).
    """
    first = seen is None
    seen = dict(seen or {})
    new_seen = dict(seen)
    acts = []
    for cr in rows or []:
        name = (cr.get("customer") or "").strip()
        if not name:
            continue
        ck = cust_key(cr)
        st = (cr.get("status") or "").strip()
        prev = seen.get(ck)
        new_seen[ck] = st
        cancel = _canceled(cr)
        deliver = sheets.parse_date(cr.get("deliver_date"))
        expiry = sheets.expiry_date(cr)
        for r in rules or []:
            if not r.get("on", True):
                continue
            kind, days = r["kind"], int(r.get("days") or 0)
            if kind == "status":
                k = f"{r['id']}|{ck}"
                ws = words(r)
                if not ws or k in done or first or cancel:
                    continue
                now_hit = any(w in st for w in ws)
                was_hit = prev is not None and any(w in prev for w in ws)
                if now_hit and not was_hit:
                    due = today + timedelta(days=max(0, days))
                    acts.append({"op": "add", "key": k, "date": due, "base": st,
                                 "title": fill(r["title"], cr, deliver, expiry),
                                 "ment": fill(r["ment"], cr, deliver, expiry)})
                continue
            if kind == "deliver":
                k = f"{r['id']}|{ck}"
                rec = done.get(k)
                if cancel or deliver is None:
                    if rec and rec.get("title") and not rec.get("skip") and not rec.get("gone"):
                        acts.append({"op": "remove", "key": k, "old": rec})
                    continue
                due = deliver + timedelta(days=days)
                base = deliver.isoformat()
                title = fill(r["title"], cr, deliver, expiry)
                ment = fill(r["ment"], cr, deliver, expiry)
                if rec and rec.get("base") == base:
                    continue                          # 그대로 — 이미 했다
                if due < today - timedelta(days=LATE["deliver"]):
                    acts.append({"op": "mark", "key": k, "date": due, "base": base})
                    continue
                if due > today + timedelta(days=AHEAD["deliver"]):
                    continue                          # 아직 이르다 — 다음에
                live_rec = rec and rec.get("title") and not rec.get("skip") and not rec.get("gone")
                acts.append({"op": "move" if live_rec else "add",
                             "key": k, "date": due, "base": base, "title": title, "ment": ment,
                             "old": rec})
                continue
            if kind == "expiry":
                if expiry is None or cancel:
                    continue
                k = f"{r['id']}|{ck}|{expiry.isoformat()}"
                rec = done.get(k)
                if closed is not None and closed(cr, expiry):
                    if rec and rec.get("title") and not rec.get("skip") and not rec.get("gone"):
                        acts.append({"op": "remove", "key": k, "old": rec, "keep": True})
                    continue
                if rec:
                    continue
                due = expiry + timedelta(days=days)
                if due < today - timedelta(days=LATE["expiry"]):
                    acts.append({"op": "mark", "key": k, "date": due, "base": expiry.isoformat()})
                    continue
                if due > today + timedelta(days=AHEAD["expiry"]):
                    continue
                acts.append({"op": "add", "key": k, "date": max(due, today), "base": expiry.isoformat(),
                             "title": fill(r["title"], cr, deliver, expiry),
                             "ment": fill(r["ment"], cr, deliver, expiry)})
    if not rows:
        new_seen = seen               # 못 읽었을 때 지난 기록을 지우지 않는다
    return acts, new_seen


# ---------------------------------------------------------------------------
# 기록 파일
# ---------------------------------------------------------------------------
def now_stamp() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(name) -> dict | None:
    try:
        o = json.loads(config.data_file(name).read_text(encoding="utf-8"))
        return o if isinstance(o, dict) else None
    except Exception:
        return None


def load_done() -> dict:
    return _load(DONE_FILE) or {}


def save_done(d: dict) -> None:
    config.atomic_write(config.data_file(DONE_FILE), json.dumps(d, ensure_ascii=False, indent=1))


def load_seen() -> dict | None:
    """지난번 본 진행현황. 처음이면 None(→ 이번엔 적기만 한다)."""
    return _load(SEEN_FILE)


def save_seen(d: dict) -> None:
    config.atomic_write(config.data_file(SEEN_FILE), json.dumps(d, ensure_ascii=False))
