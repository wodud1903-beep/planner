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

from planner import hangul, sheets  # noqa: E402

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

    dest = ROOT / "web" / "verify" / "vectors.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")
    n = sum(len(v) for k, v in out.items() if isinstance(v, list))
    print(f"{dest.relative_to(ROOT)} — 정답 {n}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
