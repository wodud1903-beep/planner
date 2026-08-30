"""주간 요약 — 한 주를 한 장으로.

금요일마다 손으로 세시던 것(이번 주 계약 몇 건, 출고 몇 건, 수수료 얼마,
다음 주에 뭐가 오는지)을 시트에서 그대로 뽑는다. 새로 입력하실 것은 없다.

브리핑과 같은 방식으로 **내용을 먼저 만들고**(`sections`) 평문과 HTML 두 가지로
그린다. 두 벌을 따로 쓰면 반드시 어긋난다 — 브리핑에서 이미 겪었다.

한 주는 **월요일 시작**이다. 주간 실적을 월~일로 세는 것이 업계 관행이고,
일요일 시작으로 두면 금요일에 보는 요약에 다음 주 이틀이 섞여 들어온다.
"""

from __future__ import annotations

from datetime import date, timedelta
from html import escape as _esc

from . import sheets, theme

WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]

# 진행현황이 이 말로 시작하면 '끝난 계약' 으로 본다
DONE_WORDS = ("출고", "완료")
CANCEL_WORD = "취소"


def week_range(today: date, offset: int = 0) -> tuple[date, date]:
    """그 주의 (월요일, 일요일). offset=+1 이면 다음 주."""
    mon = today - timedelta(days=today.weekday()) + timedelta(days=7 * offset)
    return mon, mon + timedelta(days=6)


def _label(d: date) -> str:
    return f"{d:%m-%d}({WEEKDAY_KO[d.weekday()]})"


def _money(n: int) -> str:
    return f"{n:,}원"


def _fee(cr) -> int:
    """그 건의 수수료 합계 (시트 H열). 못 읽으면 0."""
    try:
        return int(sheets.digits_only(cr.total) or 0)
    except Exception:
        return 0


def _live(cr) -> bool:
    """취소된 계약이 아닌가 — 실적·예정 어디에도 취소 건은 넣지 않는다."""
    return cr.get("status").strip() != CANCEL_WORD


def _in(d, lo: date, hi: date) -> bool:
    return d is not None and lo <= d <= hi


def sections(rows: list, today: date, expiry_months: int = 3) -> list[dict]:
    """주간 요약의 내용. 브리핑 섹션과 같은 모양이라 그리는 코드를 나눠 쓴다."""
    mon, sun = week_range(today)
    nmon, nsun = week_range(today, 1)
    rows = [r for r in (rows or []) if _live(r)]

    secs = []

    # ---- 이번 주 출고 (실적) ----
    out = []
    for cr in rows:
        d = sheets.parse_date(cr.get("deliver_date"))
        if _in(d, mon, sun):
            out.append((d, cr))
    out.sort(key=lambda x: x[0])
    fee_sum = sum(_fee(cr) for _d, cr in out)
    secs.append({
        "icon": "🚗", "title": "이번 주 출고", "color": "green",
        "items": [{"lead": _label(d), "text": cr.get("customer"),
                   "sub": " · ".join(x for x in (cr.get("finance"),
                                                 cr.get("model")) if x)}
                  for d, cr in out],
        "note": f"수수료 합계 {_money(fee_sum)}" if out else "",
        "empty": "이번 주 출고가 없습니다",
    })

    # ---- 이번 주 계약(발주) ----
    made = []
    for cr in rows:
        d = sheets.parse_date(cr.get("contract_date"))
        if _in(d, mon, sun):
            made.append((d, cr))
    made.sort(key=lambda x: x[0])
    secs.append({
        "icon": "📝", "title": "이번 주 계약", "color": "blue",
        "items": [{"lead": _label(d), "text": cr.get("customer"),
                   "sub": " · ".join(x for x in (cr.get("finance"),
                                                 cr.get("model")) if x)}
                  for d, cr in made],
        "empty": "이번 주 신규 계약이 없습니다",
    })

    # ---- 금융사별 (이번 주 출고 기준) ----
    by_fin: dict[str, list] = {}
    for _d, cr in out:
        by_fin.setdefault(cr.get("finance").strip() or "기타", []).append(cr)
    if by_fin:
        order = sorted(by_fin.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        secs.append({
            "icon": "🏦", "title": "금융사별", "color": "gray",
            "items": [{"lead": f"{len(v)}건", "text": k,
                       "sub": _money(sum(_fee(c) for c in v))}
                      for k, v in order],
            "count": len(order),
        })

    # ---- 다음 주 출고 예정 ----
    plan = []
    for cr in rows:
        d = sheets.parse_date(cr.get("deliver_date"))
        if _in(d, nmon, nsun):
            plan.append((d, cr))
    plan.sort(key=lambda x: x[0])
    secs.append({
        "icon": "📦", "title": "다음 주 출고 예정", "color": "orange",
        "items": [{"lead": _label(d), "text": cr.get("customer"),
                   "sub": " · ".join(x for x in (cr.get("finance"),
                                                 cr.get("model")) if x)}
                  for d, cr in plan],
        "empty": "다음 주 출고 예정이 없습니다",
    })

    # ---- 진행 중 (발주했는데 아직 출고 안 됨) ----
    open_rows = []
    for cr in rows:
        st = cr.get("status").strip()
        if any(st.startswith(w) for w in DONE_WORDS):
            continue
        cd = sheets.parse_date(cr.get("contract_date"))
        if cd is None or cd > today:
            continue
        if sheets.parse_date(cr.get("deliver_date")) is not None:
            continue                   # 출고일이 이미 잡혔으면 진행 중이 아니다
        open_rows.append(((today - cd).days, cd, cr))
    open_rows.sort(key=lambda x: -x[0])           # 오래 묵은 것이 위로
    if open_rows:
        secs.append({
            "icon": "⏳", "title": "진행 중 (출고 대기)", "color": "red",
            "items": [{"lead": f"{n}일째", "text": cr.get("customer"),
                       "sub": f"{cd:%m-%d} 계약 · {cr.get('status') or '진행현황 없음'}"}
                      for n, cd, cr in open_rows[:15]],
            "count": len(open_rows),
            "more": max(0, len(open_rows) - 15),
            "hint": "오래 묵은 건부터 캐피탈에 진행 상황을 확인해 보세요.",
        })

    # ---- 다음 주 만기 (재계약) ----
    if int(expiry_months or 0) > 0:
        exp = []
        for cr in rows:
            d = sheets.expiry_date(cr)
            if _in(d, nmon, nsun):
                exp.append((d, cr))
        exp.sort(key=lambda x: x[0])
        if exp:
            secs.append({
                "icon": "🔔", "title": "다음 주 만기", "color": "violet",
                "items": [{"lead": _label(d), "text": cr.get("customer"),
                           "sub": cr.get("model")} for d, cr in exp],
                "count": len(exp),
                "hint": "[고객관리] 탭에서 [이력] 로 상담 내역을 보고 재계약을 준비하세요.",
            })

    return secs


def title_line(today: date) -> str:
    mon, sun = week_range(today)
    return f"{mon:%Y년 %m월 %d일} ~ {sun:%m월 %d일} 주간 요약"


def to_text(rows: list, today: date, expiry_months: int = 3) -> str:
    """복사·파일 저장용 평문."""
    secs = sections(rows, today, expiry_months)
    lines = [title_line(today), ""]
    for s in secs:
        n = s.get("count", len(s["items"]))
        lines.append(f"[{s['title']}]  {n}건" if n else f"[{s['title']}]")
        if s.get("note"):
            lines.append(f"  {s['note']}")
        if not s["items"]:
            lines.append(f"  ({s.get('empty', '없음')})")
        for it in s["items"]:
            lead = (it.get("lead") or "").strip()
            sub = (it.get("sub") or "").strip()
            lines.append(f"  · {lead + '  ' if lead else ''}{it['text']}"
                         + (f"  ({sub})" if sub else ""))
        if s.get("more"):
            lines.append(f"  … 외 {s['more']}건")
        if s.get("hint"):
            lines.append(f"  → {s['hint']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def to_html(rows: list, today: date, expiry_months: int = 3) -> str:
    """화면용 — 브리핑과 같은 색·크기 규칙."""
    secs = sections(rows, today, expiry_months)
    txt, sub_c, line_c = theme.c("text"), theme.c("subtext"), theme.c("border")

    out = [f"<div style='font-family:Malgun Gothic;color:{txt};'>",
           f"<p style='margin:0 0 10px 0;font-size:19px;font-weight:bold;color:{txt};'>"
           f"{_esc(title_line(today))}</p>"]
    for s in secs:
        col, bg = theme.strong(s["color"]), theme.strong_bg(s["color"])
        n = s.get("count", len(s["items"]))
        badge = (f"<span style='background-color:{bg};color:{col};font-size:12px;"
                 f"font-weight:bold;'>&nbsp;{n}건&nbsp;</span>" if n else
                 f"<span style='color:{sub_c};font-size:12px;'>&nbsp;0건&nbsp;</span>")
        out.append(f"<hr style='border:1px solid {line_c};'>")
        out.append(f"<p style='margin:8px 0 4px 0;font-size:16px;font-weight:bold;"
                   f"color:{col};'>{s['icon']} {_esc(s['title'])} &nbsp;{badge}</p>")
        if s.get("note"):
            out.append(f"<p style='margin:0 0 4px 6px;font-size:13px;font-weight:bold;"
                       f"color:{col};'>{_esc(s['note'])}</p>")
        if not s["items"]:
            out.append(f"<p style='margin:2px 0 6px 12px;font-size:13px;color:{sub_c};'>"
                       f"{_esc(s.get('empty', '없음'))}</p>")
        for it in s["items"]:
            lead = (it.get("lead") or "").strip()
            sub = (it.get("sub") or "").strip()
            head = (f"<b style='color:{col};'>{_esc(lead)}</b> &nbsp;" if lead else "")
            tail = (f" <span style='color:{sub_c};font-size:12px;'>{_esc(sub)}</span>"
                    if sub else "")
            out.append(f"<p style='margin:1px 0 1px 12px;font-size:14px;'>"
                       f"{head}{_esc(it['text'])}{tail}</p>")
        if s.get("more"):
            out.append(f"<p style='margin:2px 0 4px 12px;font-size:12px;color:{sub_c};'>"
                       f"… 외 {s['more']}건</p>")
        if s.get("hint"):
            out.append(f"<p style='margin:4px 0 6px 12px;font-size:12px;color:{sub_c};'>"
                       f"→ {_esc(s['hint'])}</p>")
    out.append("</div>")
    return "".join(out)


def file_name(today: date) -> str:
    mon, _sun = week_range(today)
    return f"주간요약_{mon:%Y%m%d}.txt"


def week_key(today: date) -> str:
    """'이 주를 이미 보여 줬는가' 를 기억할 열쇠 (월요일 날짜)."""
    mon, _sun = week_range(today)
    return f"{mon:%Y-%m-%d}"
