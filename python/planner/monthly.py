"""월 마감 리포트 — 한 달 출고·수수료를 금융사별·차종별로, 지난달과 견줘서(v1.26).

손으로 세던 월말 정리를 시트에서 그대로 뽑는다(주간 요약 weekly.py 와 같은 기준):
  · 출고 = 출고일이 그달인 건(취소 제외) · 수수료 = H열 합계 · 신규 계약 = 계약일이 그달인 건
  · 금융사별(출고·수수료·비중) · 차종별(출고) · 출고 목록 · 최근 12개월 추이

쓰는 곳 셋
  · 대시보드 [월 마감] 창 — 달을 골라 보고 [복사](카톡 보고) · [시트에 적기]
  · 매달 1일 이후 처음 시트를 새로 읽을 때 지난달 것을 고객 시트의 '월마감' 탭에 저절로 적는다
    (설정 monthly_on, 한 번 적은 달은 monthly_last 에 남겨 다른 PC 가 또 적지 않는다)
  · 시트 탭에는 숫자를 숫자로 적는다(시트에서 더하고 그래프를 그릴 수 있게)

통신 없는 순수 계산(시트에 쓰는 일은 sheets.write_tab 이 한다).
"""

from __future__ import annotations

from datetime import date

from . import sheets

TAB = "월마감"
CANCEL_WORD = "취소"


def prev_month(y: int, m: int) -> tuple[int, int]:
    return (y - 1, 12) if m == 1 else (y, m - 1)


def _fee(cr) -> int:
    try:
        return int(sheets.digits_only(cr.total) or 0)
    except Exception:
        return 0


def _live(cr) -> bool:
    return (cr.get("customer") or "").strip() != "" and (cr.get("status") or "").strip() != CANCEL_WORD


def _in_month(d, y, m) -> bool:
    return d is not None and d.year == y and d.month == m


def stats(rows, y: int, m: int) -> dict:
    """그달 숫자."""
    out_rows, made = [], 0
    for cr in rows or []:
        if not _live(cr):
            continue
        dd = sheets.parse_date(cr.get("deliver_date"))
        if _in_month(dd, y, m):
            out_rows.append((dd, cr))
        if _in_month(sheets.parse_date(cr.get("contract_date")), y, m):
            made += 1
    out_rows.sort(key=lambda x: (x[0], (x[1].get("customer") or "")))
    fin: dict = {}
    model: dict = {}
    total = 0
    for _d, cr in out_rows:
        f = (cr.get("finance") or "").strip() or "(금융사 없음)"
        k = (cr.get("model") or "").strip() or "(차종 없음)"
        fee = _fee(cr)
        total += fee
        c, s = fin.get(f, (0, 0))
        fin[f] = (c + 1, s + fee)
        model[k] = model.get(k, 0) + 1
    by_fin = sorted(((n, c, s) for n, (c, s) in fin.items()), key=lambda x: (-x[1], -x[2], x[0]))
    by_model = sorted(model.items(), key=lambda x: (-x[1], x[0]))
    return {"y": y, "m": m, "count": len(out_rows), "fee": total, "contracts": made,
            "by_fin": by_fin, "by_model": by_model,
            "list": [(d, (cr.get("customer") or "").strip(), (cr.get("finance") or "").strip(),
                      (cr.get("model") or "").strip(), _fee(cr)) for d, cr in out_rows]}


def report(rows, y: int, m: int) -> dict:
    py, pm = prev_month(y, m)
    hist = []
    yy, mm = y, m
    for _ in range(12):
        s = stats(rows, yy, mm)
        hist.append((f"{yy}-{mm:02d}", s["count"], s["fee"], s["contracts"]))
        yy, mm = prev_month(yy, mm)
    return {"cur": stats(rows, y, m), "prev": stats(rows, py, pm), "hist": hist}


def _money(n: int) -> str:
    return f"{n:,}원"


def _diff(a: int, b: int, money: bool = False) -> str:
    d = a - b
    sign = "+" if d > 0 else ("−" if d < 0 else "±")
    body = f"{abs(d):,}" + ("원" if money else "")
    pct = f", {d * 100 / b:+.0f}%" if b else ""
    return f"{sign}{body}{pct}"


def render_text(rep: dict) -> str:
    """카톡 보고용 글."""
    c, p = rep["cur"], rep["prev"]
    lines = [f"{c['y']}년 {c['m']}월 마감", ""]
    lines.append(f"· 출고 {c['count']}대 (지난달 {p['count']}대 · {_diff(c['count'], p['count'])})")
    lines.append(f"· 수수료 {_money(c['fee'])} (지난달 {_money(p['fee'])} · {_diff(c['fee'], p['fee'], True)})")
    lines.append(f"· 신규 계약 {c['contracts']}건 (지난달 {p['contracts']}건)")
    if c["by_fin"]:
        lines += ["", "[금융사별]"]
        for n, cnt, fee in c["by_fin"]:
            share = f" · {cnt * 100 / c['count']:.0f}%" if c["count"] else ""
            lines.append(f"· {n} {cnt}대 {_money(fee)}{share}")
    if c["by_model"]:
        lines += ["", "[차종별]"]
        lines.append(" · ".join(f"{n} {cnt}" for n, cnt in c["by_model"][:12])
                     + (f" 외 {len(c['by_model']) - 12}종" if len(c["by_model"]) > 12 else ""))
    return "\n".join(lines)


def sheet_values(rep: dict, made_on: date | None = None, source: str = "") -> list:
    """'월마감' 탭에 적을 칸(2차원). 숫자는 숫자로."""
    c, p = rep["cur"], rep["prev"]
    when = f"{made_on:%Y-%m-%d}" if made_on else ""
    v = [[f"{c['y']}년 {c['m']}월 마감 리포트"],
         [f"일정관리기가 적음 {when}" + (f" · 시트 '{source}' 기준" if source else "")
          + " · 출고 = 출고일이 그달인 건(취소 제외), 수수료 = 합계(H열)"],
         [],
         ["항목", "이번 달", "지난달", "차이"],
         ["출고(대)", c["count"], p["count"], c["count"] - p["count"]],
         ["수수료(원)", c["fee"], p["fee"], c["fee"] - p["fee"]],
         ["신규 계약(건)", c["contracts"], p["contracts"], c["contracts"] - p["contracts"]],
         [],
         ["금융사", "출고(대)", "수수료(원)", "비중(%)"]]
    for n, cnt, fee in c["by_fin"]:
        v.append([n, cnt, fee, round(cnt * 100 / c["count"]) if c["count"] else 0])
    v += [[], ["차종", "출고(대)"]]
    for n, cnt in c["by_model"]:
        v.append([n, cnt])
    v += [[], ["출고일", "고객", "금융사", "차종", "수수료(원)"]]
    for d, name, fin, model, fee in c["list"]:
        v.append([f"{d:%Y-%m-%d}", name, fin, model, fee])
    v += [[], ["최근 12개월", "출고(대)", "수수료(원)", "신규 계약(건)"]]
    for ym, cnt, fee, made in rep["hist"]:
        v.append([ym, cnt, fee, made])
    return v
