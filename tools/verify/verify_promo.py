"""v1.34 — 수입차 프로모션: 시트 읽기 · 브랜드 블록 해석(4행 제목) · 실시간 검색 · 화면 · 메뉴 · 설정.

시트 값은 진짜 '수입차 프로모션' 탭과 **모양만** 같게 만든 가짜다(공개 저장소 — 회사 금액·담당자 이름을 넣지 않는다).
  · B:G 벤츠 · I:N BMW · P:U 아우디 · 2~3행 제목(별표·긴 공백) · 3행 묶음 제목(병합) · 4행 열 제목
  · 구역 이름(전기차 라인업 …) · 여러 줄 안내(재구매 · 특별 이슈) · 줄마다 길이가 다르다(구글은 뒤 빈칸을 뺀다)
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
import os as _os
_os.chdir(_ROOT / "python")

import json
import os
import tempfile
import threading
import time
import traceback

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
tempfile.tempdir = tempfile.mkdtemp()

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import fake_google as fg  # noqa: E402

FAIL, ERRS = [], []
_ORIG_HOOK = _sys.excepthook


def _hook(t, v, tb):
    ERRS.append("".join(traceback.format_exception(t, v, tb)))
    _ORIG_HOOK(t, v, tb)


_sys.excepthook = _hook
threading.excepthook = lambda a: ERRS.append("".join(
    traceback.format_exception(a.exc_type, a.exc_value, a.exc_traceback)))


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


from planner import config, google_client, models, navicons, net, promo, sheets, theme  # noqa: E402
from planner import startup_dialog as _sd  # noqa: E402

W = fg.World("staff@example.com")
_sd.StartupDialog.show_for = staticmethod(lambda *a, **k: None)
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
for mod in (net, google_client, sheets):
    for attr in ("http", "_http"):
        if hasattr(mod, attr):
            setattr(mod, attr, lambda: fg.Session(W))
google_client.GoogleAuth.valid_token = lambda self: "AT"

app = QApplication.instance() or QApplication([])
theme.apply_to_app(app)


def pump(sec=0.3):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def wait(cond, sec=8.0):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.03)
    return bool(cond())


class Auth:
    def __init__(self, on=True):
        self.on = on

    def valid_token(self):
        return "AT"

    def is_connected(self):
        return self.on


AUTH = Auth()


# ------------------------------------------------------------------ 가짜 시트
def row(b=(), m=(), a=()):
    """한 줄 — 벤츠(B:G) · BMW(I:N) · 아우디(P:U). 구글처럼 뒤 빈칸은 뺀다."""
    r = [""] * 21
    for c0, cells in ((1, b), (8, m), (15, a)):
        for k, v in enumerate(cells):
            r[c0 + k] = v
    while r and r[-1] == "":
        r.pop()
    return r


NOTE1 = "<재구매>\r\nAMG, Maybach, S - 2%\r\n그 외 차종 - 1%\r\n\r\n트레이드인 - 전 차종 1%"
NOTE2 = ("*법인 진행시 1%~3% 추가 할인\n 할인 차종 [ S , AMG , GLS]\n\n* 컨퀘스트 할인\n"
         "다른 브랜드 소유자 대상 GLC & GLE 구매시 1% 추가할인 (중복 불가)\n\n*보증연장 프로모션\n전기차 보증 2년 연장")
VALUES = [
    ["."],
    row(["BENZ"], ["BMW 11월 프로모션        ***** 11/05 기준 *****  > 10월 조건에서 일부수정"], ["AUDI"]),
    row(["벤츠 11월 프로모션      ***** 11/03 (화) 기준 *****"],
        ["기본값 변동 X", "", "11월 프로모션"], ["기본값 변동 X", "", "", "11월 프로모션"]),
    row(["차 종", "차량가격", "MBF", "프로모션", "비고", "담당자/추가 할인 조건"],
        ["모델명(연식)", "차량가", "현금", "제휴사", "비고", "담당자"],
        ["모델명[연식]", "차량가", "비고", "현금 할인", "제휴사 할인", "딜러사/이름"]),
    row(["A220 Hatch [26MY]", "40,000,000", "", "1,000,000"],
        ["120i_P2 [26MY]", "41,000,000", "재고없음"],
        ["A3 40 TFSI [26MY]", "42,000,000", "", "2,000,000", "", "가나딜러 홍길동"]),
    row(["E300 4M+ AMG Line [26MY]", "90,000,000", "9,000,000", "8,000,000"],
        ["X5 30d M Spt [26MY]", "120,000,000", "이번달끝 단종 신형예정", "10,000,000", "12,000,000"],
        ["Q5 스포트백 40TFSI Qu, S-line [26MY]", "80,000,000", "", "7,000,000", "", "가나딜러 홍길동"]),
    row(["E300 4M+ EX [27MY]", "91,000,000", "8,000,000", "7,000,000"],
        ["520i LCI [26MY]", "70,000,000", "", "9,000,000", "11,000,000"],
        ["A6 40 TDI Qu. S-line [26MY]", "83,000,000", "하나캐피탈 이자지원 390", "6,000,000"]),
    row(["GLC300 4M+ AV [26MY]", "80,000,000", "9,100,000", "5,800,000"],
        ["X3 xDrive 20d xLine LCI [26MY]", "74,000,000", "", "6,500,000", "7,000,000"],
        ["The New Q7 3.0 55 TFSI Qu. [25MY]", "116,000,000", "재고없음"]),
    row(["S 450 4M+ [27MY]", "160,000,000", "신형"], ["X1 sDrive 18d xLine _P2 [26MY]", "60,000,000"],
        ["전기차 라인업"]),
    row(["전기차 라인업"], ["i4 eDrive 40 M Spt LCI [26MY]", "79,000,000", "", "11,000,000", "12,000,000"],
        ["Q4 45 e-tron [26MY]", "66,000,000", "연식변경", "", "", "다라딜러/김철수"]),
    row(["EQA 250 AMG Line [26MY]", "76,000,000", "종료"], [], ["Q6 e-tron S-line [26MY]", "95,000,000", "단종"]),
    row([" EQS 580 4M+ SUV [26MY]", "192,000,000", "신형", "19,200,000"]),
    row(["고성능 라인업"]),
    row(["AMG GT 43 4M+ [26MY]", "164,000,000", "", "14,800,000", "4%추가"]),
    row(["AMG G 450d [25MY]", "194,900,000", "0%", "0"]),
    row(["재구매 및 트레이드 인"]),
    row([NOTE1]),
    [], [], [],
    row(["이번달 특별 이슈"]),
    row([NOTE2]),
]
# 3행 묶음 제목 병합(0부터 · 끝은 빼고) — I3:J3 · K3:L3 · P3:R3 · S3:T3 · (벤츠 안내 B17:G20)
MERGES = [
    {"startRowIndex": 2, "endRowIndex": 3, "startColumnIndex": 8, "endColumnIndex": 10},
    {"startRowIndex": 2, "endRowIndex": 3, "startColumnIndex": 10, "endColumnIndex": 12},
    {"startRowIndex": 2, "endRowIndex": 3, "startColumnIndex": 15, "endColumnIndex": 18},
    {"startRowIndex": 2, "endRowIndex": 3, "startColumnIndex": 18, "endColumnIndex": 20},
    {"startRowIndex": 16, "endRowIndex": 20, "startColumnIndex": 1, "endColumnIndex": 7},
]
MLIST = [[m["startRowIndex"], m["endRowIndex"], m["startColumnIndex"], m["endColumnIndex"]] for m in MERGES]

# ------------------------------------------------------------------ [1]
print("[1] 해석 — 4행 열 제목 · 빈 열로 나뉜 세 블록 · 2~3행 제목")
B = promo.parse(VALUES, MLIST)
ok("블록 셋(벤츠 · BMW · 아우디)", [b["key"] for b in B] == ["benz", "bmw", "audi"], [b["key"] for b in B])
ok("보이는 이름", [b["brand"] for b in B] == ["벤츠", "BMW", "아우디"])
ok("열 위치 B · I · P", [b["col"] for b in B] == [1, 8, 15])
ok("열 제목 = 4행 그대로(블록마다 다르다)",
   B[0]["headers"] == ["차 종", "차량가격", "MBF", "프로모션", "비고", "담당자/추가 할인 조건"]
   and B[1]["headers"][2:4] == ["현금", "제휴사"] and B[2]["headers"][2:5] == ["비고", "현금 할인", "제휴사 할인"],
   [b["headers"] for b in B])
ok("제목 — 별표·긴 공백을 걷는다", B[0]["title"] == "BENZ · 벤츠 11월 프로모션 11/03 (화) 기준", B[0]["title"])
ok("BMW 제목", B[1]["title"] == "BMW 11월 프로모션 11/05 기준 > 10월 조건에서 일부수정", B[1]["title"])
ok("묶음 제목은 병합 너비대로(I3:J3 · K3:L3)",
   B[1]["groups"] == [(0, 2, "기본값 변동 X"), (2, 2, "11월 프로모션")], B[1]["groups"])
ok("아우디 묶음(P3:R3 · S3:T3)", B[2]["groups"] == [(0, 3, "기본값 변동 X"), (3, 2, "11월 프로모션")], B[2]["groups"])
B2 = promo.parse(VALUES, [])
ok("병합을 몰라도 — 다음 묶음 앞까지", B2[1]["groups"] == [(0, 2, "기본값 변동 X"), (2, 4, "11월 프로모션")],
   B2[1]["groups"])
ok("한 칸짜리 제목 줄('.') 은 버린다", all("." != b["title"] for b in B))

kinds = [(r["kind"], r["cells"][0][:12]) for r in B[0]["rows"]]
ok("구역 이름 · 안내 글을 가린다",
   ("section", "전기차 라인업") in kinds and ("section", "고성능 라인업") in kinds
   and ("section", "재구매 및 트레이드") in [(k, t[:10]) for k, t in kinds]
   and [k for k, _t in kinds].count("note") == 2, kinds)
note = next(r for r in B[0]["rows"] if r["kind"] == "note")
ok("안내 글은 줄바꿈 그대로(\\r\\n → \\n)", note["cells"][0] == NOTE1.replace("\r\n", "\n"), repr(note["cells"][0][:30]))
ok("안내 글의 구역", note["section"] == "재구매 및 트레이드 인")
eqs = next(r for r in B[0]["rows"] if "EQS" in r["cells"][0])
ok("모델 이름 앞뒤 공백을 걷는다", eqs["cells"][0] == "EQS 580 4M+ SUV [26MY]" and eqs["section"] == "전기차 라인업")
ok("짧은 줄은 빈칸으로 채운다(너비 6)", all(len(r["cells"]) == 6 for b in B for r in b["rows"]))
ok("시트 행 번호", next(r for r in B[0]["rows"] if r["cells"][0].startswith("A220"))["row"] == 5)
ok("아우디 구역(P 열 첫 칸만)", [r["cells"][0] for r in B[2]["rows"] if r["kind"] == "section"] == ["전기차 라인업"])
ok("BMW 빈 줄은 건너뛴다", all(any(c for c in r["cells"]) for r in B[1]["rows"]))
ok("모델 수(벤츠 9 · BMW 6 · 아우디 6)", promo.model_count(B) == 9 + 6 + 6, promo.model_count(B))
ok("열 제목 줄을 스스로 찾는다(4행)", promo.header_row(VALUES) == 3)
shifted = [["메모"]] + VALUES
ok("한 줄 밀려도 찾는다", promo.header_row(shifted) == 4 and promo.model_count(promo.parse(shifted)) == 21)
ok("빈 시트", promo.parse([]) == [] and promo.parse([["."]]) == [])

# ------------------------------------------------------------------ [2]
print("[2] 찾기 — 자료검색처럼(부분 · 초성 · 낱말 모두 · 끝 글자 조합 중)")


def names(found):
    return [(b["key"], r["cells"][0]) for b, rows in found for r in rows]


f = promo.search(B, "e300")
ok("'e300' → 벤츠 E300 두 줄만", names(f) == [("benz", "E300 4M+ AMG Line [26MY]"), ("benz", "E300 4M+ EX [27MY]")],
   names(f))
ok("대소문자·띄어쓰기 무관('E 300')", names(promo.search(B, "E 300"))[:2] == names(f)[:2])
ok("'x5' → BMW", names(promo.search(B, "x5")) == [("bmw", "X5 30d M Spt [26MY]")])
ok("'q5 스포트백' → 아우디", names(promo.search(B, "q5 스포트백")) == [("audi", "Q5 스포트백 40TFSI Qu, S-line [26MY]")])
ok("초성 'ㅅㅍㅌㅂ'", names(promo.search(B, "ㅅㅍㅌㅂ")) == [("audi", "Q5 스포트백 40TFSI Qu, S-line [26MY]")])
ok("끝 글자 조합 중 '스포트배'", names(promo.search(B, "스포트배")) == [("audi", "Q5 스포트백 40TFSI Qu, S-line [26MY]")])
f = promo.search(B, "eqs")
ok("구역 안 모델은 구역 이름과 함께", names(f) == [("benz", "전기차 라인업"), ("benz", "EQS 580 4M+ SUV [26MY]")], names(f))
f = promo.search(B, "전기차")
ok("구역 이름을 치면 그 구역이 통째로(두 브랜드)",
   names(f)[:3] == [("benz", "전기차 라인업"), ("benz", "EQA 250 AMG Line [26MY]"), ("benz", "EQS 580 4M+ SUV [26MY]")]
   and [n for k, n in names(f) if k == "audi"] == ["전기차 라인업", "Q4 45 e-tron [26MY]", "Q6 e-tron S-line [26MY]"],
   names(f))
f = promo.search(B, "트레이드")
ok("안내 글도 찾는다", [r["kind"] for _b, rows in f for r in rows] == ["section", "note"], names(f))
ok("'컨퀘스트' → 특별 이슈 안내", [r["kind"] for _b, rows in promo.search(B, "컨퀘스트") for r in rows] == ["section", "note"])
f = promo.search(B, "벤츠 glc")
ok("브랜드 말 + 모델 '벤츠 glc'", names(f)[0] == ("benz", "GLC300 4M+ AV [26MY]") and {k for k, _n in names(f)} == {"benz"},
   names(f))
ok("그 모델이 적힌 안내도 함께(이번달 특별 이슈 — GLC 1% 추가할인)",
   [r["kind"] for _b, rows in f for r in rows] == ["model", "section", "note"] and "GLC" in names(f)[2][1])
ok("브랜드만 '아우디' → 아우디 전부", {b["key"] for b, _r in promo.search(B, "아우디")} == {"audi"}
   and len(promo.search(B, "아우디")[0][1]) == len(B[2]["rows"]))
ok("치는 도중 '벤' 도 벤츠로(0건 깜빡임 없이)", {b["key"] for b, _r in promo.search(B, "벤")} == {"benz"})
ok("'bmw x' → BMW 의 x 모델만", all(k == "bmw" for k, _n in names(promo.search(B, "bmw x"))) and
   len(names(promo.search(B, "bmw x"))) >= 3)
ok("브랜드 단추로 거르기", {b["key"] for b, _r in promo.search(B, "", "bmw")} == {"bmw"})
ok("단추보다 친 브랜드가 먼저", {b["key"] for b, _r in promo.search(B, "아우디 q7", "bmw")} == {"audi"})
ok("검색이 비면 그 브랜드 모든 줄 그대로", promo.search(B, "", "benz")[0][1] == B[0]["rows"])
ok("없으면 빈 목록", promo.search(B, "zzzz") == [])
ok("구역 이름끼리 이어 붙어 걸리지 않는다('라인업amg')", promo.search(B, "라인업amg") == [])
ok("건수", promo.hit_count(promo.search(B, "e")) .get("benz", 0) >= 3)
ok("브랜드 말 가르기", promo.split_query("벤츠  e300 ") == ({"benz"}, "e300"))

# ------------------------------------------------------------------ [3]
print("[3] 복사 글 · 숫자 · 색")
e300 = next(r for r in B[0]["rows"] if r["cells"][0].startswith("E300 4M+ AMG"))
ok("한 줄 복사 = 모델 · 제목 값", promo.row_text(B[0], e300)
   == "E300 4M+ AMG Line [26MY] · 차량가격 90,000,000 · MBF 9,000,000 · 프로모션 8,000,000",
   promo.row_text(B[0], e300))
x5 = next(r for r in B[1]["rows"] if r["cells"][0].startswith("X5"))
ok("BMW 는 BMW 제목으로", promo.row_text(B[1], x5)
   == "X5 30d M Spt [26MY] · 차량가 120,000,000 · 현금 이번달끝 단종 신형예정 · 제휴사 10,000,000 · 비고 12,000,000",
   promo.row_text(B[1], x5))
ok("숫자 칸", promo.is_number("4,900,000") and promo.is_number("0") and promo.is_number("0%")
   and not promo.is_number("4%추가") and not promo.is_number("신형") and not promo.is_number(""))
ok("재고 없음·종료·단종은 빨강, 신형은 파랑",
   [promo.tone_of(x) for x in ("재고없음", "재고 없음", "종료", "단종", "신형", "연식변경", "9,000,000", "비고")]
   == ["red", "red", "red", "red", "blue", "blue", "", ""])
ok("제목 다듬기", promo.clean_title("벤츠 11월   ***** 11/03 *****") == "벤츠 11월 11/03")
ok("브랜드 알아보기", promo.brand_of("BMW 11월") == ("bmw", "BMW") and promo.brand_of("AUDI") == ("audi", "아우디")
   and promo.brand_of("모르는 곳") is None)
ok("모르는 브랜드도 블록으로(제목 첫 낱말)",
   [b["brand"] for b in promo.parse([["", "VOLVO"], [], [], ["", "모델", "차량가"], ["", "XC60", "70,000,000"]])]
   == ["볼보"])
ok("이름 없는 블록", promo.parse([[], [], [], ["", "모델", "차량가"], ["", "A", "1"]])[0]["brand"] == "브랜드 1")

# ------------------------------------------------------------------ [4]
print("[4] 시트 읽기 — 권한 · 없는 시트 · 탭 이름 · 저장본")
SID, TAB = config.PROMO_DEF_SHEET_ID, config.PROMO_DEF_TAB
W.sheets[SID] = {"다른 탭": [["x"]], TAB: VALUES}
W.merges[SID] = {TAB: MERGES}
raw = promo.read(AUTH, SID, TAB)
ok("값 · 병합 · 탭 번호", raw["values"][3][1] == "차 종" and raw["merges"] == MLIST and raw["gid"] == 1, raw.get("gid"))
ok("읽기만 한다(쓰기 없음)", not [w for w in W.writes if SID in str(w[1])])
gets = [u for m, u, _p in fg.LOG if SID in u and "/values/" in u]
ok("열은 넉넉히(A1:AZ)", gets and gets[-1].endswith(f"'{TAB}'!A1:AZ"), gets[-1:])


def err_of(fn):
    try:
        fn()
    except Exception as e:      # noqa: BLE001
        return e
    return None


W.deny_sheets.add(SID)
e = err_of(lambda: promo.read(AUTH, SID, TAB))
ok("403 → '뷰어로 공유' 안내(편집 권한은 필요 없다)", isinstance(e, promo.PromoError) and "뷰어" in str(e)
   and "편집자" not in str(e), e)
W.deny_sheets.discard(SID)
e = err_of(lambda: promo.read(AUTH, "NOPE", TAB))
ok("없는 시트 → 설정 안내", isinstance(e, promo.PromoError) and "찾지 못했" in str(e), e)
e = err_of(lambda: promo.read(AUTH, SID, "없는탭"))
ok("없는 탭 → 탭 이름 안내", isinstance(e, promo.PromoError) and "'없는탭' 탭이 없" in str(e), e)
e = err_of(lambda: promo.read(Auth(False), SID, TAB))
ok("로그인 전", isinstance(e, promo.PromoError) and "로그인" in str(e), e)
e = err_of(lambda: promo.read(AUTH, "", TAB))
ok("주소가 비면", isinstance(e, promo.PromoError) and "비어" in str(e), e)
ok("탭이 비면 첫 탭", promo.read(AUTH, SID, "")["values"] == [["x"]])

promo.save_cache(SID, TAB, raw)
ok("저장본 — 같은 시트·탭이면 그대로", promo.load_cache(SID, TAB)["values"] == VALUES
   and promo.load_cache(SID, TAB)["gid"] == 1)
ok("다른 시트·탭이면 없음", promo.load_cache("OTHER", TAB) is None and promo.load_cache(SID, "x") is None)
ok("계정 폴더 안에", str(config.data_file(promo.CACHE_FILE)).startswith(os.environ["APPDATA"]))
ok("시트 주소(탭으로 바로)", promo.sheet_url("S1", 5) == "https://docs.google.com/spreadsheets/d/S1/edit#gid=5"
   and promo.sheet_url("S1") == "https://docs.google.com/spreadsheets/d/S1/edit")

# ------------------------------------------------------------------ [5]
print("[5] 설정 — 시트·탭(비우면 회사 프로모션 시트)")
ok("기본값", models.AppSettings().promo_sheet == SID and models.AppSettings().promo_tab == TAB)
ok("비우면 기본", models.promo_where("", "") == (SID, TAB) and models.promo_where(" ", None) == (SID, TAB))
ok("다른 시트는 탭을 비워 둘 수 있다", models.promo_where("MINE", "") == ("MINE", ""))
cfgp = _pl.Path(tempfile.mkdtemp()) / "plan_cfg.json"
s = models.AppSettings.load(cfgp)
s.promo_sheet, s.promo_tab = "MINE", "조건표"
s.save(cfgp)
s2 = models.AppSettings.load(cfgp)
ok("설정 파일에 남는다(promoSheet · promoTab)", (s2.promo_sheet, s2.promo_tab) == ("MINE", "조건표")
   and json.loads(cfgp.read_text(encoding="utf-8")).get("promoSheet") == "MINE")
cfgp.write_text(json.dumps({"promoSheet": "", "promoTab": ""}), encoding="utf-8")
ok("옛 파일·빈 값은 기본으로", (models.AppSettings.load(cfgp).promo_sheet, models.AppSettings.load(cfgp).promo_tab)
   == (SID, TAB))
from planner import settings_dialog  # noqa: E402


class _A:
    def is_connected(self):
        return False

    def email(self):
        return "staff@example.com"


s3 = models.AppSettings()
dlg = settings_dialog.SettingsDialog(_A(), s3, account="staff@example.com")
ok("설정 창에 지금 시트가 보인다", dlg.ed_promo_sheet.text() == SID and dlg.ed_promo_tab.text() == TAB)
dlg.ed_promo_sheet.setText("https://docs.google.com/spreadsheets/d/1Zz_promo-X/edit#gid=7")
dlg.ed_promo_tab.setText(" 조건표 ")
dlg._on_ok()
ok("주소를 붙여도 ID 만 · 탭 이름 다듬기", (s3.promo_sheet, s3.promo_tab) == ("1Zz_promo-X", "조건표"),
   (s3.promo_sheet, s3.promo_tab))
dlg = settings_dialog.SettingsDialog(_A(), s3, account="staff@example.com")
dlg.ed_promo_sheet.setText("")
dlg.ed_promo_tab.setText("")
dlg._on_ok()
ok("비우면 회사 프로모션 시트로", (s3.promo_sheet, s3.promo_tab) == (SID, TAB))

# ------------------------------------------------------------------ [6]
print("[6] 화면 — 저장본부터 · 새로 읽기 · 표 · 검색 · 복사 · 오류")
from planner.promo_tab import PromoTab  # noqa: E402

t = PromoTab()
t.set_auth(AUTH)
t.resize(1300, 800)
t.show()
pump(0.1)
ok("처음엔 '불러오는 중'", t.stack.currentWidget() is t.lbl_empty and "불러오는 중" in t.lbl_empty.text())
W.sheets[SID][TAB] = VALUES + [row(["CLA 220 [27MY]", "59,000,000", "신형"])]      # 시트에 한 줄 늘었다
n_get = len([1 for m, u, _p in fg.LOG if SID in u and "/values/" in u])
t.on_shown()
ok("저장본을 바로 보여 준다(읽기를 기다리지 않는다)", promo.model_count(t.blocks) == 21 and t.stack.currentWidget() is t.tbl,
   promo.model_count(t.blocks))
ok("뒤에서 새로 읽는다", wait(lambda: promo.model_count(t.blocks) == 22), promo.model_count(t.blocks))
ok("새로 읽은 것을 저장본으로", len(promo.load_cache(SID, TAB)["values"]) == len(VALUES) + 1)
t.on_shown()
pump(0.3)
ok("10분 안에 다시 열면 또 읽지 않는다",
   len([1 for m, u, _p in fg.LOG if SID in u and "/values/" in u]) == n_get + 1)
ok("검색칸에 커서", t.ed_find.hasFocus() or not t.isActiveWindow())

kinds = [k for k, _b, _r in t._rows]
ok("브랜드마다 제목 · 묶음 · 열 제목 줄", kinds[:3] == ["title", "head", "model"]
   and kinds.count("title") == 3 and kinds.count("head") == 3 and kinds.count("groups") == 2, kinds[:8])
i_head_bmw = [i for i, (k, b, _r) in enumerate(t._rows) if k == "head" and b["key"] == "bmw"][0]
ok("BMW 열 제목 = 4행 I:N", [t.tbl.item(i_head_bmw, k).text() for k in range(6)]
   == ["모델명(연식)", "차량가", "현금", "제휴사", "비고", "담당자"])
i_grp = [i for i, (k, b, _r) in enumerate(t._rows) if k == "groups" and b["key"] == "bmw"][0]
ok("묶음 제목은 병합 칸으로", t.tbl.columnSpan(i_grp, 0) == 2 and t.tbl.columnSpan(i_grp, 2) == 2
   and t.tbl.item(i_grp, 2).text() == "11월 프로모션")
i_title = 0
ok("제목 줄은 표 폭 전체", t.tbl.columnSpan(i_title, 0) == 6 and "11/03" in t.tbl.item(0, 0).text())
i_note = [i for i, (k, _b, _r) in enumerate(t._rows) if k == "note"][1]
ok("긴 안내는 줄 수만큼 높게", t.tbl.rowHeight(i_note) > 6 * t.tbl.fontMetrics().height(), t.tbl.rowHeight(i_note))
i_e300 = [i for i, (k, _b, r) in enumerate(t._rows) if k == "model" and r["cells"][0].startswith("E300 4M+ AMG")][0]
ok("숫자는 오른쪽", t.tbl.item(i_e300, 1).textAlignment() & Qt.AlignRight)
i_s = [i for i, (k, _b, r) in enumerate(t._rows) if k == "model" and r["cells"][0].startswith("S 450")][0]
ok("'신형' 은 파랑", t.tbl.item(i_s, 2).foreground().color().name().lower() == theme.strong("blue").lower())
ok("모델 칸 폭은 넉넉히", t.tbl.columnWidth(0) >= 180)

t.ed_find.setText("e300")
t._paint()
kinds = [(k, b["key"]) for k, b, _r in t._rows]
ok("'e300' → 벤츠 제목·열 제목 + 두 줄", kinds == [("title", "benz"), ("head", "benz"), ("model", "benz"), ("model", "benz")],
   kinds)
ok("단추에 브랜드별 건수", t._brand_btns["benz"].text() == "벤츠 2" and t._brand_btns["bmw"].text() == "BMW 0"
   and t._brand_btns[""].text() == "전체 2", [b.text() for b in t._brand_btns.values()])
ok("상태 줄", "찾은 모델 2개" in t.lbl_status.text(), t.lbl_status.text())
t.tbl.selectRow(2)
t.copy_selected()
ok("Ctrl+C — 카톡에 붙일 한 줄", QApplication.clipboard().text() == promo.row_text(B[0], e300),
   QApplication.clipboard().text())
t.tbl.clearSelection()
t.tbl.selectRow(0)
ok("제목 줄 복사", t.selected_text().startswith("[벤츠] BENZ"))
ok("제목에 브랜드가 있으면 앞에 또 붙이지 않는다", t.tbl.item(0, 0).text().startswith("BENZ · 벤츠 11월"),
   t.tbl.item(0, 0).text())

t._brand_btns["bmw"].click()
pump(0.05)
ok("BMW 단추 + 'e300' → 다른 브랜드에 있다고 알려 준다",
   t.stack.currentWidget() is t.lbl_empty and "벤츠 2" in t.lbl_empty.text(), t.lbl_empty.text())
t.ed_find.setText("x")
t._paint()
ok("BMW 만", {b["key"] for _k, b, _r in t._rows} == {"bmw"})
t._brand_btns[""].click()
t.ed_find.setText("zzzz")
t._paint()
ok("없으면 안내", t.stack.currentWidget() is t.lbl_empty and "맞는 모델이 없" in t.lbl_empty.text())
t.ed_find.setText("")
t._paint()
ok("지우면 전체", promo.model_count(t.blocks) == sum(1 for k, _b, _r in t._rows if k == "model"))
ok("단추 글자 되돌림", t._brand_btns["benz"].text() == "벤츠")

# 오류 — 저장본은 두고 상태 줄에만
W.deny_sheets.add(SID)
t.reload(manual=True)
ok("못 읽어도 보던 표는 그대로", wait(lambda: not t._loading) and t.stack.currentWidget() is t.tbl and t._err)
ok("상태 줄에 이유", "뷰어" in t.lbl_status.text(), t.lbl_status.text())
W.deny_sheets.discard(SID)

# 계정·시트가 바뀌면
t.set_where("OTHER", "x")
ok("다른 시트로 바꾸면 처음부터(보고 있으면 바로 읽는다)", wait(lambda: not t._loading) and not t.blocks
   and t.stack.currentWidget() is t.lbl_empty and "찾지 못했" in t.lbl_empty.text(), t.lbl_empty.text())
t.set_where("", "")
ok("비우면 회사 시트로", wait(lambda: promo.model_count(t.blocks) == 22), promo.model_count(t.blocks))
t2 = PromoTab()
t2.set_auth(Auth(False))
t2.on_shown()
ok("로그인 전 · 저장본이 있으면 — 표는 보여 주고 이유는 상태 줄에",
   t2.stack.currentWidget() is t2.tbl and "로그인" in t2.lbl_status.text(), t2.lbl_status.text())
t2.deleteLater()
config.data_file(promo.CACHE_FILE).unlink()
t2 = PromoTab()
t2.set_auth(Auth(False))
t2.on_shown()
ok("로그인 전 · 저장본도 없으면 — 이유를 크게", t2.stack.currentWidget() is t2.lbl_empty
   and "로그인" in t2.lbl_empty.text(), t2.lbl_empty.text())
for th in theme.THEME_ORDER:
    theme.set_theme(th)
    t.apply_theme()
ok("테마마다 그려진다", t.tbl.rowCount() > 0)
theme.set_theme("light")
t.close()
t2.deleteLater()

# ------------------------------------------------------------------ [7]
print("[7] 메인 창 — 왼쪽 메뉴 '수입차 프로모션'(자료검색 다음) · 처음 열 때 읽기 · 옛 순서에도 끼워 넣기")
ok("메뉴 아이콘(차)", navicons.for_tab("수입차 프로모션") == "car" and "car" in navicons.NAMES)
img = navicons.pixmap("car", "#000000", 20, 2.0).toImage()
ok("아이콘이 그려진다", any(img.pixelColor(x, y).alpha() > 0 for x in range(0, img.width(), 2)
                         for y in range(0, img.height(), 2)))
(config.base_dir() / "google_token.json").write_text(
    json.dumps({"refresh_token": "RT", "scopes": list(config.SCOPE_LABELS)}), encoding="utf-8")
from planner.main_window import MainWindow  # noqa: E402

w = MainWindow()
w.show()
ok("계정 확인", wait(lambda: w._account_verified, 10), w.account_email)
names_ = [w.tabs.tabText(i) for i in range(w.tabs.count())]
ok("자료검색 다음", names_.index("수입차 프로모션") == names_.index("자료검색") + 1, names_)
ok("메뉴에도", "수입차 프로모션" in w.sidebar.nav.names())
n0 = len([1 for m, u, _p in fg.LOG if SID in u and "/values/" in u])
pump(0.5)
ok("켤 때는 안 읽는다", len([1 for m, u, _p in fg.LOG if SID in u and "/values/" in u]) == n0)
w.tabs.setCurrentWidget(w.tab_promo)
ok("메뉴로 열면 읽는다", wait(lambda: promo.model_count(w.tab_promo.blocks) == 22))
ok("제목줄 = 메뉴 이름", w.lbl_page.text() == "수입차 프로모션")
w.settings.promo_sheet, w.settings.promo_tab = "OTHER", ""
w._settings_follow_up(w._settings_snapshot())
ok("설정이 바뀌면 탭도 그 시트로", w.tab_promo.sheet_id == "OTHER")
w.settings.promo_sheet, w.settings.promo_tab = SID, TAB
w._settings_follow_up(w._settings_snapshot())
ok("되돌리기", w.tab_promo.sheet_id == SID and w.tab_promo.tab == TAB)

d = w.open_status()
ok("연결 상태 점검 — 볼 수 있으면 ✔ 모델 수", wait(lambda: not d._running and "promo" in d.results)
   and d.results["promo"][0] == "ok" and "22" in d.results["promo"][1], d.results.get("promo"))
d.close()

# 옛 판에서 메뉴 순서를 바꿔 둔 사람 — 새 메뉴가 맨 끝이 아니라 만든 자리(자료검색 다음)에
w.settings.tab_order = ["자료검색", "대시보드", "고객관리", "고객정보", "멘트복사", "수당계산기", "PC 알람"]
w._save_settings()
w.tabs.setCurrentWidget(w.tab_main)
w._quitting = True
w.close()
pump(0.2)
w2 = MainWindow()
pump(0.5)
n2 = [w2.tabs.tabText(i) for i in range(w2.tabs.count())]
ok("옛 순서 그대로 + 새 메뉴는 자료검색 다음",
   n2 == ["자료검색", "수입차 프로모션", "대시보드", "고객관리", "고객정보", "멘트복사", "수당계산기", "PC 알람"], n2)
ok("메뉴도 같은 순서", w2.sidebar.nav.names() == n2)
w2._quitting = True
w2.close()

pump(0.3)
ok("끝까지 예외가 없다", not ERRS, ERRS[:2])
ok("모르는 주소로 나가지 않는다", not fg.UNKNOWN, fg.UNKNOWN[:5])
print()
print("실패:", FAIL if FAIL else "없음")
_sys.exit(1 if FAIL else 0)
