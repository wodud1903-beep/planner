"""고객 진행 보드 — 플로우의 '업무 상태' 처럼 진행현황별 칸에 고객 카드를 놓는다.

칸은 **시트에 실제로 있는 진행현황 값**으로 만든다(발주 · 진행보류 · 출고 …).
없는 값을 새로 만들면 시트의 드롭다운에 없는 글자가 들어가 버린다.
카드를 다른 칸으로 옮기면 그 칸의 진행현황 글자 그대로 시트 L열에 쓴다.

칸 순서는 영업 흐름(상담 → 심사 → 계약·발주 → 출고 대기 → 출고 → 보류 → 취소)을
말로 짐작해 정하고, 같은 단계면 많이 쓰는 값이 앞이다.
취소·부결은 기본으로 숨기고, 출고(완료)는 최근 것만 보여 준다(수백 건이라).

⚠️ web/js/board.js 가 이 계산을 그대로 옮겼다. 파이썬이 낸 정답표(vectors.json)로 대조한다.
"""

from __future__ import annotations

from datetime import date

from . import sheets

# (단계, 이 말이 들어 있으면) — 위에서부터 먼저 맞는 것
_RULES = [
    (8, ("진행보류", "보류", "홀딩")),
    (9, ("취소", "부결", "철회")),
    (0, ("상담", "문의", "견적")),
    (1, ("서류", "접수", "신청")),
    (2, ("심사",)),
    (3, ("가결", "승인")),
    (5, ("배정", "생산", "선적", "입고", "탁송")),
    (6, ("출고대기", "출고예정", "출고 대기", "출고 예정")),
    (4, ("계약", "발주", "약정")),
    (7, ("출고", "완료", "인도")),
    (6, ("대기", "예정")),
]
NO_STATUS = "(진행현황 없음)"
DONE = 7
HOLD = 8
CANCEL = 9
STALE_WARN = 14          # 발주 뒤 이만큼 지나면 주황
STALE_BAD = 30           # 이만큼이면 빨강
DONE_DAYS = 30           # 출고 칸은 최근 이만큼만


def stage(status: str) -> int:
    s = (status or "").strip()
    if not s:
        return -1
    for rank, words in _RULES:
        if any(w in s for w in words):
            return rank
    return 4                       # 모르는 말은 가운데(계약 즈음)


def _md(d: date) -> str:
    return f"{d.month}/{d.day}"


def card(cr, today: date) -> dict:
    """카드 한 장 — 이름 · 금융사·차종 · 한 줄 알림(며칠째 / 출고일)."""
    st = (cr.get("status") or "").strip()
    rk = stage(st)
    cd = sheets.parse_date(cr.get("contract_date"))
    dd = sheets.parse_date(cr.get("deliver_date"))
    chip, tone, key = "", "", ""
    if rk == DONE:
        if dd:
            chip, key = f"출고 {_md(dd)}", dd.isoformat()
    elif rk in (CANCEL,):
        chip = st
    elif dd and rk >= 3:
        left = (dd - today).days
        chip = (f"출고 {_md(dd)}" + (f" · D-{left}" if left > 0 else
                                    " · 오늘" if left == 0 else f" · {-left}일 지남"))
        tone = "green" if left >= 0 else "red"
        key = dd.isoformat()
    elif cd:
        n = (today - cd).days
        if n >= 0:
            chip = f"계약 {n}일째"
            tone = "red" if n >= STALE_BAD else "orange" if n >= STALE_WARN else ""
            if rk == HOLD:
                tone = ""
        else:
            chip = f"계약 {_md(cd)}"
        key = cd.isoformat()
    if rk != DONE:
        # 진행 중 칸의 순서는 늘 계약일 — 오래 묵은 건이 위로(출고일이 잡혀도 같다)
        key = cd.isoformat() if cd else (dd.isoformat() if dd else "")
    return {
        "row": cr.row, "name": (cr.get("customer") or "").strip(),
        "sub": " · ".join(x for x in (cr.get("finance"), cr.get("model")) if x),
        "chip": chip, "tone": tone, "key": key,
    }


def columns(rows: list, today: date, show_cancel: bool = False,
            done_days: int = DONE_DAYS) -> list[dict]:
    """[{status, rank, count, cards, more}] — 보드에 그릴 칸들."""
    groups: dict[str, list] = {}
    for cr in rows or []:
        if not (cr.get("customer") or "").strip():
            continue
        st = (cr.get("status") or "").strip() or NO_STATUS
        groups.setdefault(st, []).append(cr)
    cols = []
    for st, crs in groups.items():
        rk = stage("" if st == NO_STATUS else st)
        if rk == CANCEL and not show_cancel:
            continue
        cards = [card(cr, today) for cr in crs]
        more = 0
        if rk == DONE:
            # 출고 — 최근 것만(오래된 순으로 쌓이면 수백 장이다)
            # 출고일이 아직 없는 건(방금 이 칸으로 옮긴 것)은 늘 보이게 맨 위에
            lo = date.fromordinal(today.toordinal() - done_days)
            recent = [c for c in cards if not c["key"] or c["key"] >= lo.isoformat()]
            more = len(cards) - len(recent)
            cards = sorted(recent, key=lambda c: (c["key"] == "", c["key"]), reverse=True)
        else:
            # 오래 묵은 것(계약일이 이른 것)이 위로, 날짜 없는 것은 아래로
            cards.sort(key=lambda c: (c["key"] == "", c["key"], c["name"]))
        cols.append({"status": st, "rank": rk, "count": len(crs),
                     "cards": cards, "more": more})
    cols.sort(key=lambda c: (c["rank"], -c["count"], c["status"]))
    return cols
