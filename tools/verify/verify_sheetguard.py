"""고객 시트 쓰기 — 줄이 옮겨져도 **그 고객에게만** 쓰는지.

예전 버그: 앱은 불러올 때의 줄 번호를 들고 있다가 그대로 썼다. 그 사이 시트를
정렬하거나 폰·다른 PC 에서 고객을 넣고 빼면, 그 줄의 **다른 고객**이 고쳐지거나
지워졌다. 추가도 들고 있던 마지막 줄 다음에 써서 폰에서 방금 넣은 고객을 덮었다.

구글 시트 API 를 가짜로 끼워 실제 요청 모양 그대로 시험한다(네트워크 없음).
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))

import json
import re
import urllib.parse

from planner import sheets  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name
          + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


TAB = "고객관리"
NCOL = 21                     # A..U


class FakeResp:
    def __init__(self, code=200, body=None):
        self.status_code = code
        self._body = body if body is not None else {}
        self.text = json.dumps(self._body, ensure_ascii=False)

    def json(self):
        return self._body


class FakeSheet:
    """줄 번호(1부터) → 21칸. A1 표기를 알아듣는 아주 작은 시트."""

    def __init__(self):
        self.rows = {}
        self.writes = []      # (행, 열, 값)

    def put(self, row, **cols):
        r = self.rows.setdefault(row, [""] * NCOL)
        for k, v in cols.items():
            r[ord(k) - 65] = v

    def cell(self, row, col):
        return self.rows.get(row, [""] * NCOL)[col]

    def name(self, row):
        return self.cell(row, 1)

    def max_row(self):
        return max(self.rows) if self.rows else 0

    # ---- A1 ----
    @staticmethod
    def _a1(a1):
        a1 = a1.split("!", 1)[1]
        m = re.fullmatch(r"([A-Z]+)(\d*)(?::([A-Z]+)(\d*))?", a1)
        c0 = ord(m.group(1)) - 65
        r0 = int(m.group(2) or 1)
        c1 = ord(m.group(3)) - 65 if m.group(3) else c0
        r1 = int(m.group(4)) if m.group(4) else (None if m.group(3) else r0)
        return c0, r0, c1, r1

    def read(self, a1):
        c0, r0, c1, r1 = self._a1(a1)
        r1 = r1 or self.max_row()
        out = []
        for r in range(r0, r1 + 1):
            out.append([self.cell(r, c) for c in range(c0, c1 + 1)])
        while out and not any(out[-1]):
            out.pop()
        return out

    def write(self, a1, val):
        c0, r0, _c1, _r1 = self._a1(a1)
        self.put(r0, **{chr(65 + c0): val})
        self.writes.append((r0, c0, val))


SH = FakeSheet()


class FakeSession:
    def get(self, url, headers=None, timeout=None, params=None):
        if "/values/" in url:
            rng = urllib.parse.unquote(url.split("/values/", 1)[1])
            return FakeResp(200, {"values": SH.read(rng)})
        if "fields" in (params or {}):
            return FakeResp(200, {"sheets": [{"properties": {"sheetId": 7, "title": TAB}}]})
        return FakeResp(404, {"error": {"message": "모름"}})

    def put(self, url, headers=None, timeout=None, params=None, json=None):
        rng = urllib.parse.unquote(url.split("/values/", 1)[1])
        SH.write(rng, json["values"][0][0])
        return FakeResp(200, {})

    def post(self, url, headers=None, timeout=None, json=None):
        if url.endswith("values:batchUpdate"):
            for d in json["data"]:
                SH.write(d["range"], d["values"][0][0])
        return FakeResp(200, {})


class FakeAuth:
    def valid_token(self):
        return "t"


sheets._http = lambda: FakeSession()
A = FakeAuth()


def fresh():
    """머리글 3행, 고객 4명(4~7행). 고객ID 는 U열."""
    SH.rows.clear()
    SH.writes.clear()
    SH.put(3, A="순번", B="고객명")
    for i, (n, u) in enumerate([("김가람", "u-kim"), ("이나래", "u-lee"),
                                ("박다솜", "u-park"), ("최라온", "u-choi")]):
        SH.put(4 + i, A=str(i + 1), B=n, L="발주", U=u)


print("[1] 그대로면 그 줄에 쓴다")
fresh()
row = sheets.update_row(A, "S", TAB, 5, {"status": "출고"}, name="이나래", uid="u-lee")
ok("5행 그대로", row == 5 and SH.cell(5, 11) == "출고")
ok("다른 고객은 안 건드림", all(SH.cell(r, 11) == "발주" for r in (4, 6, 7)))

print("\n[2] 정렬돼서 줄이 바뀌었으면 옮겨 간 줄에 쓴다 (고객ID 로 찾음)")
fresh()
# 이름순 → 역순으로 정렬된 것처럼 바꾼다
SH.put(4, B="최라온", U="u-choi"); SH.put(7, B="김가람", U="u-kim")
row = sheets.update_row(A, "S", TAB, 4, {"status": "취소"}, name="김가람", uid="u-kim")
ok("김가람은 이제 7행 — 7행에 썼다", row == 7 and SH.cell(7, 11) == "취소", row)
ok("4행(최라온)은 그대로", SH.cell(4, 11) == "발주")

print("\n[3] 고객ID 가 없는 옛 시트 — 이름으로 찾는다")
fresh()
for r in range(4, 8):
    SH.put(r, U="")
SH.put(5, B="박다솜"); SH.put(6, B="이나래")
row = sheets.update_row(A, "S", TAB, 5, {"status": "출고"}, name="이나래", uid="")
ok("이나래는 6행 — 6행에 썼다", row == 6 and SH.cell(6, 11) == "출고", row)
ok("5행(박다솜)은 그대로", SH.cell(5, 11) == "발주")

print("\n[4] 못 찾으면 쓰지 않는다")
fresh()
SH.put(5, B="", U="")             # 폰에서 지워진 고객
n_before = len(SH.writes)
try:
    sheets.update_row(A, "S", TAB, 5, {"status": "출고"}, name="이나래", uid="u-lee")
    ok("RowMoved 로 멈춘다", False)
except sheets.RowMoved:
    ok("RowMoved 로 멈춘다", True)
ok("시트에 아무것도 안 썼다", len(SH.writes) == n_before)

print("\n[5] 같은 이름이 둘이면(ID 없음) 쓰지 않는다")
fresh()
for r in range(4, 8):
    SH.put(r, U="")
SH.put(5, B="다른사람")            # 원래 자리엔 다른 고객
SH.put(6, B="이나래")
SH.put(7, B="이나래")              # 같은 이름이 두 줄
try:
    sheets.update_row(A, "S", TAB, 5, {"status": "출고"}, name="이나래")
    ok("동명이인이면 멈춘다", False)
except sheets.RowMoved:
    ok("동명이인이면 멈춘다", True)

print("\n[6] 이름이 같아도 다른 고객ID 가 적힌 줄은 건너뛴다")
fresh()
SH.put(5, B="이나래", U="u-other")          # 동명이인이 그 자리에
SH.put(7, B="이나래", U="")                  # 진짜(아직 ID 를 못 적은 줄)
row = sheets.update_row(A, "S", TAB, 5, {"status": "출고"}, name="이나래", uid="u-lee")
ok("ID 가 다른 5행을 피하고 7행에 썼다", row == 7 and SH.cell(5, 11) == "발주", row)

print("\n[7] 지우기도 같은 확인을 거친다")
fresh()
SH.put(5, B="박다솜", U="u-park"); SH.put(6, B="이나래", U="u-lee")
row = sheets.clear_row(A, "S", TAB, 5, name="이나래", uid="u-lee")
ok("이나래(6행)만 지웠다", row == 6 and SH.name(6) == "" and SH.name(5) == "박다솜", row)
ok("지운 줄의 고객ID 도 비웠다", SH.cell(6, 20) == "")
fresh()
SH.put(5, B="", U="")
try:
    sheets.clear_row(A, "S", TAB, 5, name="이나래", uid="u-lee")
    ok("못 찾으면 지우지 않는다", False)
except sheets.RowMoved:
    ok("못 찾으면 지우지 않는다", all(SH.name(r) for r in (4, 6, 7)))

print("\n[8] 추가 — 폰에서 방금 넣은 고객을 덮지 않는다")
fresh()
SH.put(8, A="5", B="정마루", U="u-jung")      # 앱이 불러온 뒤 폰에서 추가
new = sheets.append_row(A, "S", TAB, {"customer": "한새봄", "status": "발주"},
                        last_row=7, seq="", uid="u-han")
ok("8행(정마루)은 그대로", SH.name(8) == "정마루")
ok("새 고객은 9행", new == 9 and SH.name(9) == "한새봄", new)
fresh()
new = sheets.append_row(A, "S", TAB, {"customer": "한새봄"}, last_row=7, seq="", uid="u-han")
ok("아무 일 없으면 들고 있던 마지막 줄 다음", new == 8 and SH.name(8) == "한새봄")

print("\n[9] 예전처럼 이름·ID 없이 부르면 확인 없이 그 줄에 쓴다(호환)")
fresh()
row = sheets.update_row(A, "S", TAB, 6, {"status": "출고"})
ok("6행에 썼다", row == 6 and SH.cell(6, 11) == "출고")

print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
