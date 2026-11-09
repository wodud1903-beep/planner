"""새로 만든 고객관리 시트(고객 0명) — 금융사 드롭다운 · 첫 고객 등록(v1.28.4).

지점장:
  ① "신규로 만든 시트는 금융사가 드롭다운으로 안 나와 — 스프레드시트에 있는 드롭다운을 전체 다 불러와줘"
     → 후보를 이미 적힌 고객 값에서만 뽑던 것에, 시트 칸에 걸린 드롭다운 목록을 더한다.
  ② "고객이 1건도 없으면 계속 불러오기 하라고만 나오고 고객추가가 안 돼"
     → 시트를 읽었으면 0명이어도 등록. 첫 고객은 머리글 바로 아래 줄, 순번 1, 머리글 서식은 안 베낀다.

구글 시트 API 를 가짜로 끼워 실제 요청 모양 그대로 시험한다(네트워크 없음).
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))

import json
import os
import re
import tempfile
import urllib.parse

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from planner import sheets  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


TAB = "고객관리"
FIN = ["현대캐피탈", "KB캐피탈", "하나캐피탈", "롯데캐피탈", "메리츠캐피탈", "BNK캐피탈"]
STATUS_LIST = ["출고", "발주", "취소", "진행보류", "심사중"]
CENTER = ["롯데렌터카", "SK렌터카", "롯데캐피탈", "MG캐피탈", "BNK캐피탈", "현대캐피탈", "KB캐피탈"]


class Resp:
    def __init__(self, code=200, body=None):
        self.status_code = code
        self._body = body if body is not None else {}
        self.text = json.dumps(self._body, ensure_ascii=False)

    def json(self):
        return self._body


def rule_list(vals):
    return {"dataValidation": {"condition": {"type": "ONE_OF_LIST",
                                             "values": [{"userEnteredValue": v} for v in vals]}}}


def rule_range(ref):
    return {"dataValidation": {"condition": {"type": "ONE_OF_RANGE", "values": [{"userEnteredValue": ref}]}}}


class Sheet:
    def __init__(self):
        self.cells = {}           # (행, 열) → 값(수식이면 '=…')
        self.calls = []
        self.has_center = True
        self.no_fin_rule = False

    def col(self, ci):
        mx = max([r for (r, c) in self.cells if c == ci] or [0])
        return [[str(self.cells.get((r, ci), ""))] for r in range(1, mx + 1)]


SH = Sheet()


class Session:
    def get(self, url, headers=None, timeout=None, params=None):
        SH.calls.append(("GET", url, params))
        if "/values/" in url:
            rng = urllib.parse.unquote(url.split("/values/", 1)[1]).split("!", 1)[1]
            m = re.fullmatch(r"([A-Z])(\d+)(?::([A-Z])(\d*))?", rng)
            ci = ord(m.group(1)) - 65
            if m.group(3) and not m.group(4):           # 한 열 전체(B1:B)
                return Resp(200, {"values": SH.col(ci)})
            v = SH.cells.get((int(m.group(2)), ci), "")
            return Resp(200, {"values": [[v]] if v != "" else []})
        if url.endswith("values:batchGet"):
            rs = [v for k, v in params if k == "ranges"]
            out = []
            for r in rs:
                if "고객센터" in r and not SH.has_center:
                    return Resp(400, {"error": {"message": "Unable to parse range"}})
                vals = (["렌트", "리스", "할부"] if "목록" in r
                        else CENTER if "고객센터" in r else [])
                out.append({"range": r, "values": [[x] for x in vals]})
            return Resp(200, {"valueRanges": out})
        p = dict(params) if isinstance(params, list) else (params or {})
        if "dataValidation" in str(p.get("fields", "")):
            rs = [v for k, v in params if k == "ranges"]
            grids = []
            for r in rs:
                col = r.split("!", 1)[1][0]
                if col == "C" and SH.no_fin_rule:
                    grids.append({})
                elif col == "C":     # 금융사 — 칸마다 같은 목록(앞 몇 줄만 걸려 있다)
                    grids.append({"rowData": [{"values": [rule_list(FIN)]}] * 5 + [{"values": [{}]}]})
                elif col == "L":   # 진행현황 — 목록
                    grids.append({"rowData": [{"values": [rule_list(STATUS_LIST)]}]})
                elif col == "O":   # 출고유형 — 다른 탭 범위를 가리킨다
                    grids.append({"rowData": [{"values": [rule_range("='목록'!$A$2:$A")]}]})
                else:
                    grids.append({})
            return Resp(200, {"sheets": [{"data": grids}]})
        if "sheets(properties" in str(p.get("fields", "")):
            return Resp(200, {"sheets": [{"properties": {"sheetId": 7, "title": TAB}}]})
        return Resp(404, {"error": {"message": "?"}})

    def post(self, url, headers=None, timeout=None, json=None):
        SH.calls.append(("POST", url, json))
        if url.endswith("values:batchUpdate"):
            for d in json["data"]:
                a1 = d["range"].split("!", 1)[1]
                m = re.fullmatch(r"([A-Z])(\d+)", a1)
                SH.cells[(int(m.group(2)), ord(m.group(1)) - 65)] = d["values"][0][0]
        return Resp(200, {})

    def put(self, url, headers=None, timeout=None, params=None, json=None):
        SH.calls.append(("PUT", url, json))
        return Resp(200, {})


class Auth:
    def valid_token(self):
        return "t"


sheets._http = lambda: Session()
A = Auth()

print("[1] 드롭다운 규칙 읽기(순수 계산)")
g = {"rowData": [{"values": [rule_list(["가", "나"])]}, {"values": [rule_list(["가", "나"])]},
                 {"values": [rule_range("=목록!A2:A")]}, {"values": [{}]}, {}]}
ok("목록 · 다른 범위 · 같은 규칙은 한 번", sheets.dropdown_rules(g) == [("list", ["가", "나"]), ("range", "=목록!A2:A")],
   sheets.dropdown_rules(g))
ok("범위 글자 — 시트 이름이 없으면 그 탭", sheets._range_a1("=$Z$2:$Z$40", TAB) == f"'{TAB}'!Z2:Z40"
   and sheets._range_a1("='목록'!$A$2:$A", TAB) == "'목록'!A2:A")

print("[2] 새 시트(고객 0명) — 드롭다운 목록을 다 불러온다")
SH.cells.clear()
for ci, v in enumerate(["순번", "고객명 / 사업자 / (실차주)", "금융사"]):
    SH.cells[(3, ci)] = v
hdr, rows, _sum = sheets.parse_rows([["요약"], [], ["순번", "고객명 / 사업자 / (실차주)", "금융사"]], [], TAB)
ok("머리글만 있는 시트도 읽힌다(고객 0명)", hdr == 3 and rows == [], (hdr, rows))
drops = sheets.read_dropdowns(A, "SID", TAB, hdr)
ok("금융사 드롭다운 목록 전체", drops.get("finance") == FIN, drops.get("finance"))
ok("진행현황 목록 · 출고유형은 다른 탭 범위의 값", drops.get("status") == STATUS_LIST
   and drops.get("kind") == ["렌트", "리스", "할부"], drops)
ok("드롭다운 없는 칸은 비워 둔다", "channel" not in drops)
q = [c for c in SH.calls if c[0] == "GET" and "dataValidation" in str(c[2])][-1][2]
rngs = [v for k, v in q if k == "ranges"]
ok("머리글 아래 줄들만 본다(드롭다운 칸 4개를 한 번에)", len(rngs) == 4 and all(f"{hdr + 1}:" in r for r in rngs), rngs)
ch = sheets.merge_choices(sheets.choices(rows), drops)
ok("고객이 없어도 고객 등록 창 후보에 금융사가 다 나온다", ch["finance"] == FIN)

print("[2-2] 새 시트에 드롭다운이 걸린 칸이 없으면 — '고객센터' 탭의 금융사 목록")
SH.no_fin_rule = True
d2 = sheets.read_dropdowns(A, "SID", TAB, hdr)
ok("기존 시트처럼 '고객센터' 탭 A3 부터의 금융사를 쓴다", d2.get("finance") == CENTER, d2.get("finance"))
ok("기존 시트의 드롭다운 모양(='고객센터'!$A$3:$A$30)도 읽는다",
   sheets._range_a1("='고객센터'!$A$3:$A$30", TAB) == "'고객센터'!A3:A30")
SH.has_center = False
d3 = sheets.read_dropdowns(A, "SID", TAB, hdr)
ok("'고객센터' 탭도 없으면 금융사만 빠지고 나머지는 그대로", "finance" not in d3
   and d3.get("kind") == ["렌트", "리스", "할부"] and d3.get("status") == STATUS_LIST, d3)
SH.has_center, SH.no_fin_rule = True, False

print("[3] 고객이 있는 시트 — 자주 쓴 금융사가 먼저, 드롭다운에만 있는 것은 뒤에")
used = {"finance": ["메리츠캐피탈", "신한카드"], "status": ["출고"]}
m = sheets.merge_choices(used, drops)
ok("자주 쓴 순서 그대로 + 나머지 드롭다운 값", m["finance"] == ["메리츠캐피탈", "신한카드"] + [x for x in FIN if x != "메리츠캐피탈"],
   m["finance"])
ok("겹치는 값은 한 번만", len(m["status"]) == len(set(m["status"])) and m["status"][0] == "출고")

print("[4] 첫 고객 등록 — 머리글 바로 아래 · 순번 1 · 머리글 서식은 안 베낀다")
ok("새 시트 순번 = 1", sheets.next_seq(A, "SID", TAB, hdr, [], header_row=hdr) == "1")
SH.cells[(hdr + 1, 0)] = "=ROW()-3"
ok("새 줄 A 에 수식이 미리 걸려 있으면 수식에 맡긴다", sheets.next_seq(A, "SID", TAB, hdr, [], header_row=hdr) == "")
del SH.cells[(hdr + 1, 0)]
SH.calls.clear()
new = sheets.append_row(A, "SID", TAB, {"customer": "첫고객", "finance": "KB캐피탈"}, hdr, seq="1", header_row=hdr)
ok("머리글 바로 아래 줄에 쓴다", new == hdr + 1 and SH.cells.get((hdr + 1, 1)) == "첫고객"
   and SH.cells.get((hdr + 1, 0)) == "1", new)
ok("머리글 서식(굵은 글씨·색)을 첫 고객 줄에 덮어쓰지 않는다",
   not any(c[0] == "POST" and c[1].endswith(":batchUpdate") and "/values:" not in c[1] for c in SH.calls))
ok("두 번째 고객 — 방금 넣은 줄의 순번 다음(목록이 아직 안 바뀌었어도)",
   sheets.next_seq(A, "SID", TAB, hdr + 1, [], header_row=hdr) == "2")
SH.calls.clear()
new2 = sheets.append_row(A, "SID", TAB, {"customer": "둘째"}, hdr + 1, seq="2", header_row=hdr)
ok("두 번째부터는 위 고객 줄의 서식·드롭다운을 베낀다", new2 == hdr + 2
   and any(c[0] == "POST" and c[1].endswith(":batchUpdate") and "/values:" not in c[1] for c in SH.calls))

print("[5] 화면 — 0명이어도 [고객 추가] · 금융사 드롭다운")
src = (_ROOT / "python" / "planner" / "main_window.py").read_text(encoding="utf-8")
add = src[src.index("def on_customer_add"):src.index("def _confirm_image_share")]
ok("시트를 읽었으면 고객이 0명이어도 등록 창을 연다",
   "if not self._sheet_loaded and not self.sheet_rows and not self._sheet_pending:" in add)
ok("순번·서식 판단에 머리글 줄을 넘긴다", "header_row=hdr_row" in add and add.count("header_row=hdr_row") == 2)
ok("불러올 때 드롭다운도 읽어 후보에 더한다", "sheets.read_dropdowns(" in src
   and src.count("sheets.merge_choices(sheets.choices(") >= 3)
from PySide6.QtWidgets import QApplication  # noqa: E402
app = QApplication.instance() or QApplication([])
from planner.customer_dialog import CustomerDialog  # noqa: E402
d = CustomerDialog("고객 등록", {}, ch)
w = d.widgets["finance"][0]
items = [w.itemText(i) for i in range(w.count())]
ok("고객 등록 창 금융사 드롭다운에 시트 목록이 다 있다", all(x in items for x in FIN), items)
d.reject()

print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
