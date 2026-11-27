#!/usr/bin/env python3
"""파이썬이 낸 정답표를 뽑아 web/verify/vectors.json 에 넣는다.

웹앱은 hangul.py / sheets.py 의 함수들을 JS 로 다시 옮겨 썼다. 옮긴 것이 원본과
조용히 어긋나면 검색이 안 걸리거나 돈이 100배로 나오는데, 그건 눈에 잘 안 띈다.
그래서 **파이썬이 정답을 만들고 JS 가 그걸 맞히는** 방식으로 못 박는다.

  python tools/gen_vectors.py        (결과를 web/verify/vectors.json 에 쓴다)

⚠️ sheets.py 는 google_client → requests 를 끌어와서 그냥 import 가 안 된다.
   여기서는 계산 함수만 필요하므로 그 모듈들을 가짜로 끼워 넣고 부른다.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

# --- sheets.py 를 부르기 위한 최소한의 가짜 모듈 ---------------------------------
for name in ("planner.google_client", "planner.net"):
    if name not in sys.modules:
        mod = types.ModuleType(name)
        mod.GoogleAuth = object
        mod.GoogleError = Exception
        mod.http = lambda: None
        mod.protect = lambda *a: None          # promo.py 가 켤 때 부른다(읽기 전용 표시)
        mod.check_write = lambda *a: None
        mod.ReadOnlySheet = Exception
        sys.modules[name] = mod

from planner import board, commission, hangul, promo, sheets, weekly  # noqa: E402

# 수입차 프로모션(v1.34.2) — 웹(web/js/promo.js)이 PC 와 같게 해석·검색하는지
PROMO_QUERIES = [("", ""), ("", "bmw"), ("e300", ""), ("E 300", ""), ("x5", ""), ("q5 스포트백", ""),
                 ("ㅅㅍㅌㅂ", ""), ("스포트배", ""), ("eqs", ""), ("전기차", ""), ("트레이드", ""),
                 ("컨퀘스트", ""), ("벤츠 glc", ""), ("아우디", ""), ("벤", ""), ("bmw x", ""),
                 ("아우디 q7", "bmw"), ("zzzz", ""), ("라인업amg", ""), ("e", "audi")]


def _promo_vectors():
    fx = json.loads((ROOT / "web" / "verify" / "fixtures" / "promo.json").read_text(encoding="utf-8"))
    blocks = promo.parse(fx["values"], fx["merges"])
    strip = lambda b: {k: (list(map(list, v)) if k == "groups" else v) for k, v in b.items() if k != "rows"}
    out = {
        "blocks": [dict(strip(b), rows=[{k: v for k, v in r.items() if k != "prep"} for r in b["rows"]])
                   for b in blocks],
        "blocks_nomerge": [[list(g) for g in b["groups"]] for b in promo.parse(fx["values"], [])],
        "header_row": promo.header_row(fx["values"]),
        "model_count": promo.model_count(blocks),
        "search": [],
        "row_text": [],
        "is_number": [[s, promo.is_number(s)] for s in
                      ["4,900,000", "0", "0%", "4%추가", "신형", "", " 1,000 ", "-", "12.5%", "3만원"]],
        "tone": [[s, promo.tone_of(s)] for s in
                 ["재고없음", "재고 없음", "종료", "단종", "신형", "연식변경", "9,000,000", "비고", "11/5기준 재고 0", ""]],
        "brand_token": [[s, promo.brand_token(s)] for s in
                        ["벤츠", "벤", "메", "BMW", "비", "아우", "audi", "glc", "", "스포트백", "볼보"]],
        "clean_title": [[s, promo.clean_title(s)] for s in
                        ["벤츠 11월 프로모션      ***** 11/03 (화) 기준 *****", "  a  b ", "*x*", ""]],
    }
    for q, brand in PROMO_QUERIES:
        found = promo.search(blocks, q, brand)
        out["search"].append([q, brand, [[b["key"], [[r["kind"], r["cells"][0]] for r in rows]] for b, rows in found],
                              promo.hit_count(promo.search(blocks, q, ""))])
    for b in blocks:
        for r in b["rows"]:
            out["row_text"].append([b["key"], r["row"], promo.row_text(b, r)])
    return out

def _no_targets(secs):
    """PC 대시보드만 쓰는 'target'(누르면 갈 고객 줄 — v1.35)은 빼고 견준다. 폰 웹(weekly.js)엔 없다."""
    return [dict(sec, items=[{k: v for k, v in it.items() if k != "target"} for it in sec.get("items") or []])
            for sec in secs]


def _promo_track_vectors():
    """바뀐 곳(v1.35 P1) — 같은 시트를 다섯 번 읽는다: 11/03 판 → 11/20 판(벤츠 값 2·신규 1·빠짐 1)
    → 그대로 한 번 더(표시가 남는다) → 12월 판(달이 바뀜 — 표시 없음) → 12/15 판(12월 안에서 바뀜).
    아우디는 제목에 달이 없어 받은 때(한국 시각)의 달로 본다."""
    import copy
    from datetime import datetime as _dt, timedelta as _td
    fx = json.loads((ROOT / "web" / "verify" / "fixtures" / "promo.json").read_text(encoding="utf-8"))
    merges = fx["merges"]

    def at(y, m, d, h=9):
        return int(((_dt(y, m, d, h) - _td(hours=9)) - _dt(1970, 1, 1)).total_seconds() * 1000)

    def put(v, r, c, val):
        while len(v) <= r:
            v.append([])
        while len(v[r]) <= c:
            v[r].append("")
        v[r][c] = val

    def repl(v, rows, old, new):
        for r in rows:
            v[r] = [str(x).replace(old, new) for x in v[r]]

    v0 = copy.deepcopy(fx["values"])
    v1 = copy.deepcopy(v0)
    put(v1, 5, 2, "91,000,000")          # 벤츠 E300 AMG — 차량가격
    put(v1, 6, 4, "7,500,000")           # 벤츠 E300 EX — 프로모션
    for c in range(1, 7):
        put(v1, 7, c, "")                # 벤츠 GLC300 — 빠짐
    v1.append(["", "C200 New [27MY]", "60,000,000", "", "2,000,000", "", ""])     # 벤츠 — 새 모델
    repl(v1, [2], "11/03", "11/20")
    v3 = copy.deepcopy(v1)
    repl(v3, [1, 2], "11월", "12월")
    repl(v3, [2], "11/20", "12/01")
    repl(v3, [1], "11/05", "12/01")
    put(v3, 5, 2, "92,000,000")
    put(v3, 4, 16, "43,000,000")         # 아우디 A3 — 차량가
    v4 = copy.deepcopy(v3)
    repl(v4, [2], "12/01", "12/15")
    put(v4, 4, 4, "1,500,000")           # 벤츠 A220 — 프로모션
    put(v4, 5, 18, "7,500,000")          # 아우디 Q5 — 현금 할인
    steps = [(v0, at(2026, 11, 3, 10)), (v1, at(2026, 11, 20)), (v1, at(2026, 11, 21)),
             (v3, at(2026, 12, 1)), (v4, at(2026, 12, 15))]
    out, hist = [], {}
    for v, now in steps:
        hist, marks = promo.track(hist, promo.parse(v, merges), now)
        out.append({"values": v, "now": now, "hist": hist, "marks": marks,
                    "text": {k: promo.change_text(m) for k, m in marks.items()}})
    return {
        "merges": merges, "steps": out,
        "title_month": [[t, promo.title_month(t), promo.title_date(t)] for t in
                        ["벤츠 11월 프로모션 · 11/03 (화) 기준", "BMW 11월 프로모션 11/05 기준 > 10월 조건에서",
                         "AUDI", "12/1 기준", "13월 32/40", "", "1월 프로모션", "２월"]],
        "row_keys": promo.row_keys({"rows": [
            {"kind": "section", "cells": ["전기차"], "section": ""},
            {"kind": "model", "cells": ["EQA", "1"], "section": "전기차"},
            {"kind": "model", "cells": ["EQA", "2"], "section": "전기차"},
            {"kind": "note", "cells": ["안내"], "section": "전기차"},
            {"kind": "model", "cells": ["", "x"], "section": ""},
            {"kind": "model", "cells": ["EQA", "3"], "section": ""}]}),
    }


HANGUL_CASES = [
    ("김상현", ["ㄱㅅㅎ", "김상", "김", "ㄱㅅㅎㅇ", "상현", "", "ㅅㅎ"]),
    ("쏘나타 디 엣지", ["ㅅㄴㅌ", "ㅆㄴㅌ", "쏘나타", "디엣지", "디 엣지", "ㄷㅇㅈ", "쏘 엣"]),
    ("Kia K5", ["k5", "K5", "kia", "ㅋ", "k 5"]),
    ("현대 아이오닉5", ["ㅎㄷ", "아이오닉", "ㅇㅇㄴ5", "닉5"]),
    ("2026-03 김철수", ["2026", "03 김", "ㄱㅊㅅ", "2026-03"]),
    ("우리금융캐피탈", ["ㅇㄹ", "우리", "캐피탈", "ㅋㅍㅌ", "금융"]),
    ("BNK캐피탈 승계", ["bnk", "ㅅㄱ", "BNK 승", "bnkㅅㄱ"]),
    # 끝 글자를 아직 치는 중(한글 입력기 조합 중) — 그 글자로 시작하는 글자까지 맞는다
    ("신한 전자약정", ["시", "신하", "전자약저", "전자야", "전자약ㅈ", "신한ㅈ", "ㅈㅈㅇㅈ",
                    "신 전자약저", "약정", "정자", "저", "샤"]),
    ("쏘나타 디 엣지", ["ㅅ", "쏘나", "소", "쏘나ㅌ", "엣ㅈ", "에"]),
    ("현대 아이오닉5", ["아이오니", "닉", "니", "5ㄱ"]),
]

MONEY_CASES = ["₩57,035,000", "₩1,234.56", "₩-1,000", "(₩1,000)", "1,000원",
               "0", "", "   ", "abc", "12.4", "12.5", "13.5", "-0", "(0)",
               "1.234.567", "３천"]

DATE_CASES = ["2026. 8. 14", "2026-08-14", "2026.8.14", "26. 8. 14", "2026/8/14",
              "2026년 8월 14일", "2026년8월14일", "20260814", "2026-08-14 0:00:00",
              "2026-02-30", "", "없음", "2026-8-14.", "8/14"]

TERMS_CASES = ["60개월 / 2만km / 무보증", "36 개 월", "선수금 30% 48개월",
               "999개월", "0개월", "개월", "", "12개월 24개월"]


# 시트를 푸는 규칙 — 헤더 탐지, 빈 줄 판정, R열 자리 맞추기.
# 실제로 사고가 났던 모양들을 일부러 넣었다.
HDR = ["순번", "고객명/사업자", "금융사", "차종", "차량가격", "금융수수료",
       "대리점 수당", "합계", "특판/대리점", "계약일(발주)", "출고일", "진행현황",
       "계약조건", "내용", "출고유형", "고객센터 번호", "사고접수연락처"]

PARSE_CASES = [
    # (이름, A~Q, S~T)
    ("머리글이 첫 줄", [HDR, ["1", "김상현", "우리금융캐피탈", "쏘나타", "3,500,000"]], []),
    ("위에 요약행이 세 줄", [
        ["", "", "", "", "", "", "", "", "", "", "", "", "", "이번달 대수", "12"],
        ["", "", "", "", "", "", "", "", "", "", "", "", "", "이번달 수당", "4,300,000"],
        [""],
        HDR,
        ["1", "박영희", "KB캐피탈", "아이오닉5", "5,200,000", "300,000", "200,000",
         "500,000", "대리점", "2026. 8. 1", "2026. 8. 20", "출고완료", "60/2만",
         "메모", "신차", "1588-1111", "1588-2222"],
    ], [["S값", "T값"]]),
    # 지운 줄 — 순번(A)이 수식이라 값이 남지만 고객명이 없으면 건너뛴다
    ("지운 줄은 건너뛴다", [HDR, ["3", "", "", ""], ["4", "최민수"]], []),
    ("아주 빈 줄은 건너뛴다", [HDR, [], ["", "", ""], ["5", "정해나"]], []),
    # S~T 가 A~Q 보다 길 때 — 열 번호가 밀리면 안 된다
    ("S~T 가 더 길다", [HDR, ["1", "한지민"]], [[], ["견적서", "완료"], ["x", "y"]]),
    ("A~Q 가 짧게 온다", [HDR, ["1", "이수현", "BNK캐피탈"]], []),
    ("머리글이 없다", [["아무거나"], ["1", "김"]], []),
    ("머리글이 31번째 줄이라 못 찾는다", [[""]] * 30 + [HDR, ["1", "늦은고객"]], []),
    ("빈 시트", [], []),
    ("공백이 붙은 머리글", [["  순번 ", " 고객명/사업자 "], ["1", " 띄어쓰기 "]], []),
    ("멘트 자리(R)는 늘 비어 있다", [HDR, ["1", "멘트고객"] + [""] * 15], [["", ""]]),
]


# 수당 계산 — 돈이 나오므로 1원도 어긋나면 안 된다.
# 반올림 경계, 면세, 화물차, 지급율 변형, 잘못된 입력을 두루 넣었다.
CALC_CASES = [
    (57035000, 4.1, False, 70.0, False),
    (57035000, 4.1, False, 70.0, True),      # 면세
    (30000000, 7.0, True, 70.0, False),      # 화물차
    (30000000, 7.0, True, 70.0, True),
    (52000000, 3.3, False, 100.0, False),    # 지급율 100
    (52000000, 3.3, False, 0.0, False),      # 지급율 0
    (1, 7.5, False, 70.0, False),            # 1원 — 버림이 드러난다
    (999, 7.5, False, 70.0, False),
    (1000, 5.0, False, 70.0, False),
    (0, 5.0, False, 70.0, False),            # 0원
    (-1000, 5.0, False, 70.0, False),        # 음수
    (12345678, 0.0, False, 70.0, False),     # 수당율 0
    (12345678, 7.5, False, 70.0, False),
    (12345678, 7.5, True, 70.0, True),
    (100000000, 2.3, False, 70.0, False),
    (45000000, 5.5, True, 85.5, False),      # 지급율에 소수점
    (33333333, 3.7, True, 70.0, True),
]

RATE_ROWS = [
    [["브랜드", "차종", "수당율(%)", "화물차"],
     ["현대", "쏘나타 / HEV", "6.0", "FALSE"],
     ["현대", "포터", "7", "TRUE"],
     ["기아", "카니발", "6.0", ""],
     ["기아", "봉고1톤", "7.0", "예"],
     ["기아", "타스만", "5.5", "Y"],
     ["현대", "스타리아", "6.0", "O"],
     ["현대", "넥쏘 수소", "2.3", "1"]],
    # 퍼센트 기호·공백·빈 이름·모자란 칸·모르는 브랜드
    [["현대", " GV80 ", " 4.1% ", " true "],
     ["현대", "", "5.0", "FALSE"],
     ["기아", "K5"],
     ["르노", "XM3", "5.0", "FALSE"],
     ["hyundai", "아반떼 / HEV", "7.0", "FALSE"],
     ["기아", "EV6", "abc", "FALSE"]],
    [],                                      # 빈 탭 → None
    [["브랜드", "차종", "수당율(%)", "화물차"]],   # 머리글만 → None
]


# S열(견적서/계약서)은 =IMAGE() 수식이다. 거기서 주소를 되찾는 규칙.
DOC_CASES = [
    '=IMAGE("https://drive.google.com/uc?export=view&id=1AbCdEf_-Xyz", 1)',
    '=image("https://drive.google.com/uc?export=view&id=1AbCdEf", 4)',
    '= IMAGE ( "https://example.com/a.png" , 1 )',
    'https://drive.google.com/uc?export=view&id=1AbCdEf',
    'https://example.com/a.png  설명',
    '=IMAGE("")',
    '',
    '   ',
    '견적서 있음',
    '=HYPERLINK("https://example.com","보기")',
]


# 주간 요약 — 주 경계(월요일 시작)·만기 계산·취소/보류 제외가 어긋나기 쉽다.
# 고객 줄을 손으로 만들어 여러 '오늘' 로 돌려 본다.
WEEKLY_ROWS = [
    # (고객, 금융사, 차종, 계약일, 출고일, 진행현황, 계약조건, 합계)
    ("김상현", "우리금융캐피탈", "쏘나타", "2026. 9. 15", "2026. 9. 17", "출고완료", "60개월", "500,000"),
    ("박영희", "KB캐피탈", "아이오닉5", "2026. 9. 16", "", "심사중", "48개월", "300,000"),
    ("최민수", "BNK캐피탈", "쏘렌토", "2026. 8. 1", "", "발주", "36개월", "200,000"),
    ("정해나", "하나캐피탈", "GV80", "2026. 7. 1", "", "진행보류", "60개월", "400,000"),
    ("한지민", "IM캐피탈", "G70", "2026. 6. 1", "", "취소", "60개월", "900,000"),
    ("이수현", "농협캐피탈", "카니발", "2026. 9. 14", "2026. 9. 20", "출고", "36개월", "150,000"),
    ("오지호", "MG캐피탈", "X6", "2021. 10. 5", "2021. 10. 20", "출고완료", "60개월", "700,000"),
    ("서junk", "기타금융사", "X3", "2026. 9. 18", "", "", "", ""),
    ("남기한", "오릭스캐피탈", "셀토스", "2026. 9. 19", "", "상담중", "개월표기없음", "0"),
]

WEEKLY_DAYS = ["2026-09-16", "2026-09-14", "2026-09-20", "2026-09-21", "2026-01-01"]


def _weekly_rows():
    out = []
    for (cust, fin, model, cd, dd, st, terms, total) in WEEKLY_ROWS:
        cr = sheets.CustomerRow(row=len(out) + 2, total=total)
        cr.values = {"customer": cust, "finance": fin, "model": model,
                     "contract_date": cd, "deliver_date": dd, "status": st,
                     "terms": terms}
        out.append(cr)
    return out


def _parse_rates(rows):
    """sheets.read_rates 의 '푸는 부분' 만 그대로 옮긴 것.
    그쪽은 통신에 묶여 있어 직접 못 부른다 — 규칙이 갈라지지 않게 여기서 한 번만 적는다."""
    out = {"hyundai": [], "kia": []}
    for row in rows:
        if not row or len(row) < 3:
            continue
        brand = str(row[0]).strip()
        if brand in ("브랜드", ""):
            continue
        key = sheets._KO_BRAND.get(brand, brand.strip().lower())
        if key not in out:
            continue
        name = str(row[1]).strip()
        if not name:
            continue
        try:
            rate = float(str(row[2]).replace("%", "").strip())
        except Exception:
            continue
        truck = str(row[3]).strip().upper() in ("TRUE", "Y", "예", "1", "O") \
            if len(row) > 3 else False
        out[key].append([name, rate, truck])
    if not (out["hyundai"] or out["kia"]):
        return None
    return out


def main() -> int:
    out = {
        "_설명": "파이썬이 만든 정답표. JS 포팅이 이걸 맞혀야 한다. "
                 "tools/gen_vectors.py 로 다시 만든다.",
        "hangul_matches": [],
        "hangul_rank": [],
        "hangul_chosung": [],
        "digits_only": [],
        "fmt_money": [],
        "parse_date": [],
        "contract_months": [],
        "parse_rows": [],
        "commission_calc": [],
        "parse_rates": [],
        "doc_url": [],
        "default_rates": {},
        "weekly_rows": [],
        "weekly_sections": [],
        "weekly_next": [],
        "board_stage": [],
        "board_columns": [],
        "weekly_text": [],
        "fmt_sheet_date": [],
        "choices": [],
    }
    for item, queries in HANGUL_CASES:
        out["hangul_chosung"].append([item, hangul.chosung(item)])
        for q in queries:
            out["hangul_matches"].append([item, q, hangul.matches(item, q)])
            out["hangul_rank"].append([item, q, hangul.rank(item, q)])
    for s in MONEY_CASES:
        out["digits_only"].append([s, sheets.digits_only(s)])
        out["fmt_money"].append([s, sheets.fmt_money(s)])
    for s in DATE_CASES:
        d = sheets.parse_date(s)
        out["parse_date"].append([s, d.isoformat() if d else None])
    for s in TERMS_CASES:
        out["contract_months"].append([s, sheets.contract_months(s)])

    for name, left, right in PARSE_CASES:
        try:
            hdr, rows, summary = sheets.parse_rows(left, right, "미출고차량")
            ans = {
                "headerRow": hdr,
                "rows": [{"row": c.row, "seq": c.seq, "total": c.total,
                          "ment": c.ment, "center": c.center, "accident": c.accident,
                          "values": c.values} for c in rows],
                "summary": [list(x) for x in summary],
            }
        except Exception as e:
            ans = {"error": type(e).__name__}
        out["parse_rows"].append([name, left, right, ans])

    for price, rate, truck, pay, free in CALC_CASES:
        out["commission_calc"].append(
            [price, rate, truck, pay, free,
             commission.calc(price, rate, truck, pay, free)])

    out["default_rates"] = {b: [[n, r, t] for n, r, t in commission.DEFAULT_RATES[b]]
                            for b in commission.BRANDS}

    import datetime as _dt
    out["weekly_rows"] = [
        {"row": cr.row, "total": cr.total, "values": cr.values} for cr in _weekly_rows()]
    for day in WEEKLY_DAYS:
        today = _dt.date.fromisoformat(day)
        secs = _no_targets(weekly.sections(_weekly_rows(), today))
        out["weekly_sections"].append([day, weekly.title_line(today), secs])
        # 대시보드 '다음 주 요약' — 다음 주 월요일 기준, 출고 예정·계약만
        nmon = weekly.week_range(today + _dt.timedelta(days=7))[0]
        out["weekly_next"].append(
            [day, _no_targets(weekly.sections(_weekly_rows(), nmon, word="다음 주", week_only=True))])
        out["weekly_text"].append([day, weekly.to_text(_weekly_rows(), today)])
        # 고객 진행 보드 — 칸·카드(취소 숨김 / 보임)
        for show in (False, True):
            out["board_columns"].append([day, show, board.columns(_weekly_rows(), today, show)])

    for st in ["", "발주", "출고", "출고완료", "출고대기", "출고 예정", "진행보류", "보류", "취소",
               "부결", "심사중", "심사대기", "서류대기", "가결", "상담", "배정완료", "계약", "모르는말"]:
        out["board_stage"].append([st, board.stage(st)])

    # 시트에 적을 날짜 서식 — **0 을 안 채운다**("2026. 8. 14")
    import datetime as _d2
    for iso in ["2026-08-14", "2026-01-01", "2026-12-31", "2026-10-09", "2026-09-05"]:
        d = _d2.date.fromisoformat(iso)
        out["fmt_sheet_date"].append([iso, sheets.fmt_date(d)])
    out["fmt_sheet_date"].append([None, sheets.fmt_date(None)])

    # 고르는 칸 후보 — 자주 쓰는 값이 위로
    _crows = _weekly_rows()
    out["choices"] = sheets.choices(_crows)

    for cell in DOC_CASES:
        out["doc_url"].append([cell, sheets.doc_url(cell)])

    for rows in RATE_ROWS:
        got = sheets.read_rates.__wrapped__ if False else None   # (통신 함수라 직접 안 쓴다)
        out["parse_rates"].append([rows, _parse_rates(rows)])

    out["promo"] = _promo_vectors()
    out["promo_track"] = _promo_track_vectors()

    # 멘트 · 명함 보내기(v1.37, 폰 웹) — PC [멘트복사] 와 같은 기본 문구 · 같은 명함 열쇠(web/js/ment.js)
    from planner import bizcard, greetings  # noqa: E402 — bizcard 는 Qt 를 부른다(여기서만)
    out["greetings_defaults"] = greetings.defaults()
    out["bizcard_keys"] = [[n, bizcard.key_of(n)] for n in (
        "에이원오토", "우리금융", "BNK캐피탈", "KB캐피탈", "  하나캐피탈 ", "롯데렌터카 본점", "A1 Auto", "😊 이모지", "")]

    dest = ROOT / "web" / "verify" / "vectors.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")
    n = sum(len(v) for k, v in out.items() if isinstance(v, list))
    print(f"{dest.relative_to(ROOT)} — 정답 {n}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
