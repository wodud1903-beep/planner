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
        sys.modules[name] = mod

from planner import commission, hangul, sheets  # noqa: E402

HANGUL_CASES = [
    ("김상현", ["ㄱㅅㅎ", "김상", "김", "ㄱㅅㅎㅇ", "상현", "", "ㅅㅎ"]),
    ("쏘나타 디 엣지", ["ㅅㄴㅌ", "ㅆㄴㅌ", "쏘나타", "디엣지", "디 엣지", "ㄷㅇㅈ", "쏘 엣"]),
    ("Kia K5", ["k5", "K5", "kia", "ㅋ", "k 5"]),
    ("현대 아이오닉5", ["ㅎㄷ", "아이오닉", "ㅇㅇㄴ5", "닉5"]),
    ("2026-03 김철수", ["2026", "03 김", "ㄱㅊㅅ", "2026-03"]),
    ("우리금융캐피탈", ["ㅇㄹ", "우리", "캐피탈", "ㅋㅍㅌ", "금융"]),
    ("BNK캐피탈 승계", ["bnk", "ㅅㄱ", "BNK 승", "bnkㅅㄱ"]),
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

    for rows in RATE_ROWS:
        got = sheets.read_rates.__wrapped__ if False else None   # (통신 함수라 직접 안 쓴다)
        out["parse_rates"].append([rows, _parse_rates(rows)])

    dest = ROOT / "web" / "verify" / "vectors.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")
    n = sum(len(v) for k, v in out.items() if isinstance(v, list))
    print(f"{dest.relative_to(ROOT)} — 정답 {n}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
