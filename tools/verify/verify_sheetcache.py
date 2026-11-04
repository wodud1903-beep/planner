"""고객 목록 저장본(v1.26) — 켜자마자 지난번 목록, 뒤에서 새로 읽는다.

예전엔 켤 때마다 시트를 다 읽을 때까지 고객 목록·보드·대시보드가 비었다(인터넷이
없으면 영영). 이제 마지막으로 읽은 그대로를 계정 폴더 sheet_cache.json 에 두었다가
켜자마자 그린다. 읽기에 실패해도 창을 띄우지 않고 조금 뒤 다시 읽는다.
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
import os as _os
_os.chdir(_ROOT / "python")

import json
import os
import tempfile
import time

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import requests  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from planner import config, google_client, kb_files, net, sheet_cache, sheets, sync, theme  # noqa: E402
from planner import startup_dialog as _sd  # noqa: E402
from planner.models import AppSettings  # noqa: E402

_sd.StartupDialog.show_for = staticmethod(lambda *a, **k: None)
WARN = []
QMessageBox.warning = staticmethod(lambda *a, **k: WARN.append(a[2] if len(a) > 2 else ""))
QMessageBox.information = staticmethod(lambda *a, **k: None)
FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name
          + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


app = QApplication.instance() or QApplication([])
theme.apply_to_app(app)
ME = "me@example.com"
HDR = ["순번", "고객명", "금융사", "차종", "차량가격", "금융수수료", "대리점 수당", "합계",
       "특판 / 대리점", "계약일(발주)", "출고일", "진행현황", "계약조건", "내용", "출고유형",
       "고객센터 번호", "사고접수연락처"]
LEFT = [HDR,
        ["1", "김상현", "KB캐피탈", "쏘나타", "30,000,000", "", "", "", "", "2026. 10. 1", "", "발주"],
        ["2", "박영희", "우리금융캐피탈", "아반떼", "22,000,000", "", "", "", "", "2026. 9. 20",
         "2026. 11. 20", "출고대기"]]
RIGHT = [[], ["", ""], ["", ""]]


class _Resp:
    status_code = 200
    text = ""

    def __init__(self, j):
        self._j = j

    def json(self):
        return self._j


NET = {"up": True}


class _Sess:
    def get(self, url, **k):
        if not NET["up"]:
            raise requests.ConnectionError("검사 — 인터넷 없음")
        return _Resp({"valueRanges": [{"values": LEFT}, {"values": RIGHT}]})

    def __getattr__(self, name):
        def call(*a, **k):
            raise requests.ConnectionError("검사 — 쓰지 않는다")
        return call


class _NoNet:
    def __getattr__(self, name):
        def call(*a, **k):
            raise requests.ConnectionError("검사 — 인터넷 없음")
        return call


for mod in (net, google_client, kb_files):
    for attr in ("http", "_http"):
        if hasattr(mod, attr):
            setattr(mod, attr, lambda: _NoNet())
sheets._http = lambda: _Sess()
google_client.GoogleAuth.valid_token = lambda self: "AT"
google_client.GoogleAuth.has_scope = lambda self, s: True
google_client.get_user_email = lambda a, detail=False: ((ME, "") if NET["up"] else ("", "net")) \
    if detail else (ME if NET["up"] else "")
google_client.fetch_tasks = lambda a: []
google_client.fetch_calendar_events = lambda *a, **k: []
sheets.read_ments = lambda *a: ({2: "김상현 고객님 안내멘트"} if NET["up"] else {})
sheets.read_docs = lambda *a: {}
sheets.read_uids = lambda *a: ({2: "uid-kim", 3: "uid-park"} if NET["up"] else {})
sync.pull = lambda a: False
sync.sync_now = lambda a: False
sync.push = lambda a: None

config.set_account(ME)
s = AppSettings.load(config.data_file("plan_cfg.json"))
s.sheet_on, s.sheet_id, s.sheet_name = True, "SHEET", "고객관리"
s.save(config.data_file("plan_cfg.json"))
config.set_account("")
config.remember_account(ME)
(config.base_dir() / "google_token.json").write_text(
    json.dumps({"refresh_token": "RT", "scopes": []}), encoding="utf-8")

from planner.main_window import MainWindow  # noqa: E402


def pump(sec=0.6):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


print("[1] 처음 — 시트를 읽으면 저장본을 남긴다")
w = MainWindow()
ok("저장본이 없으면 비어서 시작", not w.sheet_rows)
pump(3.0)
ok("시트를 읽었다", w._sheet_loaded and [c.get("customer") for c in w.sheet_rows] == ["김상현", "박영희"],
   [c.get("customer") for c in w.sheet_rows])
config.set_account(ME)
c = sheet_cache.load("SHEET", "고객관리")
ok("계정 폴더에 저장본(받은 그대로)", c is not None and c["left"] == LEFT, (c or {}).get("left"))
ok("멘트·고객ID 도 같이", c and c["ments"].get(2) == "김상현 고객님 안내멘트" and c["uids"].get(3) == "uid-park")
ok("다른 시트·탭이면 쓰지 않는다", sheet_cache.load("SHEET", "다른탭") is None
   and sheet_cache.load("OTHER", "고객관리") is None)
ok("동기화 대상이 아니다(PC 마다 그때 읽은 것)", sheet_cache.FILE not in sync._FILES)
w.hide()
w.deleteLater()
pump(0.2)

print("[2] 인터넷이 없을 때 켠다 — 저장본이 바로 보인다")
config.set_account("")
NET["up"] = False
WARN.clear()
w2 = MainWindow()
ok("켜자마자(기다리지 않고) 지난번 목록", [c.get("customer") for c in w2.sheet_rows] == ["김상현", "박영희"],
   [c.get("customer") for c in w2.sheet_rows])
ok("아직 '새로 읽음' 은 아니다(자동 일정·규칙은 새로 읽은 것으로만)", not w2._sheet_loaded)
ok("멘트·고객ID 도 채워져 있다", w2.sheet_rows[0].ment == "김상현 고객님 안내멘트"
   and w2.sheet_rows[1].uid == "uid-park")
ok("목록 아래 줄에 '저장해 둔 목록(시각)'", "저장해 둔 목록(" in w2.lbl_cust.text(), w2.lbl_cust.text())
ok("대시보드·보드용 줄도 저장본으로", len(w2.sheet_rows) == 2)
pump(3.0)
ok("읽기에 실패해도 오류 창을 띄우지 않는다(저장본을 보는 중)", not WARN, WARN)
ok("'잠시 뒤 다시 읽습니다'", "잠시 뒤 다시" in w2.lbl_cust.text(), w2.lbl_cust.text())
# v1.27 — 못 읽는 까닭을 보여 주고, 계속 안 되면 알림 한 번 뒤 그만 조른다([불러오기] 로 다시)
_t2 = []
w2.sig_toast.connect(lambda t, m: _t2.append(m))
_n0 = getattr(w2, "_sheet_cache_fails", 0)
for _i in range(10 - _n0):
    w2._on_sheet_rows(None, 0, "HTTP 403 권한이 없습니다\n자세한 내용")
ok("못 읽는 까닭도 보인다", "권한이 없습니다" in w2.lbl_cust.text(), w2.lbl_cust.text())
ok("10번째에는 알림 한 번 · '[불러오기] 를 눌러'", len(_t2) == 1 and "[불러오기]" in w2.lbl_cust.text(),
   (_t2, w2.lbl_cust.text()))
ok("그래도 오류 창은 없다", not WARN, WARN)
w2._sheet_cache_fails = 0

print("[3] 인터넷이 붙으면 새로 읽은 것으로 바꾼다")
NET["up"] = True
LEFT.append(["3", "새고객", "현대캐피탈", "그랜저", "45,000,000"])
RIGHT.append(["", ""])
w2.load_sheet_async(manual=False)
pump(2.0)
ok("새로 읽은 목록", w2._sheet_loaded and [c.get("customer") for c in w2.sheet_rows][-1] == "새고객",
   [c.get("customer") for c in w2.sheet_rows])
ok("'저장해 둔 목록' 표시가 사라진다", "저장해 둔" not in w2.lbl_cust.text(), w2.lbl_cust.text())
config.set_account(ME)
ok("저장본도 새것으로", len(sheet_cache.load("SHEET", "고객관리")["left"]) == 4)

print("[4] 저장본이 없는데 읽기에 실패하면 — 예전처럼 알린다")
sheet_cache.clear()
config.set_account("")
NET["up"] = False
WARN.clear()
w3 = MainWindow()
pump(3.0)
ok("저장본 없음 → 비어 있음", not w3.sheet_rows)
w3.load_sheet_async(manual=True)
pump(1.0)
ok("직접 [불러오기] 가 실패하면 알린다", bool(WARN), WARN)
w3.hide()

print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
