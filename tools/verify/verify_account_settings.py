"""시트·서류 폴더를 내 계정에 바로 · 고친 자료를 그 자리에서 내 계정으로(v1.30).

지점장: "PC 앱에서 설정을 변경하고 저장하면 바로 실시간 웹과 동기화. 설정에서 구글시트 주소·서류폴더 주소를
지정하면 개개인의 동기화된 계정에 실시간으로 — 웹에도 바로. 회사공통 - 내 계정에서만 고침도 PC 가 아니라
해당 계정에 저장되게."
  · 내 구글 드라이브 앱 공간 account_settings.json — 웹(jyplanner)과 같은 파일 · 같은 규칙(항목마다 나중에 바꾼 쪽).
  · PC 의 서류 폴더(G:\\내 드라이브\\영업\\고객정보)는 웹이 찾을 수 있게 '영업/고객정보' 로.
  · 고친 자료는 저장하는 그 자리에서 kb_edits.json 으로(2.5초 뒤 묶음 동기화를 기다리지 않는다).
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))

import inspect
import json
import os
import tempfile
import threading
import time

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from planner import account_settings as acs, config, drive_path, google_client, sync  # noqa: E402
from planner.models import AppSettings  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


print("[1] PC 의 서류 폴더 → 웹이 찾을 수 있는 '내 드라이브' 기준 경로")
cases = {
    "": "고객정보",
    r"G:\내 드라이브\고객정보": "고객정보",
    r"G:\내 드라이브\영업\고객정보": "영업/고객정보",
    r"H:\My Drive\고객서류": "고객서류",
    r"C:\Users\a\Google Drive\고객정보": "고객정보",
    r"D:\서류": "",
    r"G:\공유 드라이브\팀\고객정보": "",
    r"G:\내 드라이브": "",
}
got = {k: drive_path.web_ref(k) for k in cases}
ok("경로 바꾸기(비우면 고객정보 · 내 드라이브 밖이면 올리지 않음)", got == cases, got)

print("[2] 올릴 항목 · 바꾼 때 적기")
s = AppSettings()
ok("아무것도 안 정했으면 시트는 빠지고 폴더는 기본(고객정보)",
   acs.local_items(s) == {"folder": {"ref": "고객정보", "at": "", "by": "pc"}}, acs.local_items(s))
before = acs.local_items(s)
s.sheet_id, s.sheet_name, s.files_dir = "SHEET1", "미출고차량", r"G:\내 드라이브\영업\고객정보"
ok("바꾸면 바꾼 때를 적는다", acs.stamp_changes(s, before, acs.local_items(s), "2026-11-09T03:00:00Z")
   and s.sheet_at == "2026-11-09T03:00:00Z" and s.folder_at == "2026-11-09T03:00:00Z")
before = acs.local_items(s)
s.theme = "dark"
ok("시트·폴더 말고 다른 설정만 바꾸면 그대로", not acs.stamp_changes(s, before, acs.local_items(s), "2026-11-09T04:00:00Z")
   and s.sheet_at == "2026-11-09T03:00:00Z")
p = config.data_dir() / "plan_cfg_test.json"
s.save(p)
s2 = AppSettings.load(p)
ok("바꾼 때도 설정 파일에 남는다(다른 PC 로도 따라간다)", s2.sheet_at == s.sheet_at and s2.folder_at == s.folder_at)

print("[3] 합치는 규칙 — 항목마다 나중에 바꾼 쪽")
L = {"sheet": {"id": "P", "tab": "T", "at": "2026-11-09T03:00:00Z", "by": "pc"},
     "folder": {"ref": "영업/고객정보", "at": "2026-11-09T03:00:00Z", "by": "pc"}}
out, push = acs.merge({}, L, "NOW")
ok("계정에 없으면 올린다", push and out["sheet"]["id"] == "P" and out["folder"]["ref"] == "영업/고객정보" and out["v"] == 1)
out, push = acs.merge({"sheet": dict(L["sheet"], at="2000-01-01T00:00:00Z"), "folder": dict(L["folder"])}, L, "NOW")
ok("값이 같으면 시각이 달라도 쓰지 않는다", not push)
R = {"sheet": {"id": "W", "tab": "WT", "at": "2026-11-09T05:00:00Z", "by": "web"}}
out, push = acs.merge(R, {"sheet": L["sheet"]}, "NOW")
ok("웹에서 나중에 바꾼 것은 덮지 않는다", not push and out["sheet"]["id"] == "W")
out, push = acs.merge(R, {"sheet": dict(L["sheet"], at="2026-11-09T06:00:00Z")}, "NOW")
ok("PC 에서 그 뒤에 바꾸면 PC 것", push and out["sheet"]["id"] == "P" and out["sheet"]["by"] == "pc")
out, push = acs.merge(R, {"sheet": dict(L["sheet"], at="")}, "NOW")
ok("옛 설정(바꾼 때 없음)은 계정에 있는 것을 덮지 않는다", not push)
out, push = acs.merge({}, {"sheet": dict(L["sheet"], at="")}, "2026-11-09T07:00:00Z")
ok("옛 설정이라도 계정에 없으면 지금 시각으로 올린다", push and out["sheet"]["at"] == "2026-11-09T07:00:00Z")
out, push = acs.merge({"folder": {"ref": "폰 폴더", "at": "2026-11-09T05:00:00Z"}}, L, "NOW")
ok("칸마다 따로(시트는 올리고 폴더는 웹 것)", push and out["sheet"]["id"] == "P" and out["folder"]["ref"] == "폰 폴더")

print("[4] 내 계정(드라이브 앱 공간)에 쓴다")
DRIVE, WRITES = {}, []


def find(auth, name):
    if DRIVE.get("__fail"):
        raise google_client.GoogleError("HTTP 500")
    return name if name in DRIVE else None


def read(auth, fid):
    return DRIVE[fid]


def write(auth, name, content):
    WRITES.append(name)
    DRIVE[name] = content
    return name


google_client.drive_find, google_client.drive_read, google_client.drive_write = find, read, write
ok("처음이면 만든다", acs.push(None, s) is True and json.loads(DRIVE[acs.FILE])["sheet"]["id"] == "SHEET1"
   and json.loads(DRIVE[acs.FILE])["folder"]["ref"] == "영업/고객정보")
n = len(WRITES)
ok("그대로면 또 쓰지 않는다", acs.push(None, s) is False and len(WRITES) == n)
DRIVE["__fail"] = True
try:
    acs.push(None, s)
    ok("못 읽으면 AccountSettingsError", False)
except acs.AccountSettingsError:
    ok("못 읽으면 AccountSettingsError · 쓰지 않는다", len(WRITES) == n)
DRIVE.pop("__fail")
DRIVE[acs.FILE] = "{깨짐"
ok("깨진 파일은 새로 쓴다(두 칸뿐이라 잃을 것이 없다)", acs.push(None, s) is True
   and json.loads(DRIVE[acs.FILE])["sheet"]["id"] == "SHEET1")

print("[5] 동기화 때도 맞춘다(다른 PC 에서 바꾼 것 · 그때 인터넷이 끊겼던 것)")
config.set_account("me@example.com")
cfg = AppSettings()
cfg.sheet_id, cfg.sheet_name, cfg.sheet_at = "SHEET_SYNC", "탭", "2099-01-01T00:00:00Z"
cfg.save(config.data_dir() / "plan_cfg.json")
DRIVE.clear()
sync.push(None)
ok("올리기(push) 끝에 계정 설정도 맞춘다", acs.FILE in DRIVE and json.loads(DRIVE[acs.FILE])["sheet"]["id"] == "SHEET_SYNC")
ok("받기·지금 동기화 쪽도 · 실패해도 동기화는 그대로",
   "_account_settings(auth)" in inspect.getsource(sync.sync_now)
   and "except Exception" in inspect.getsource(sync._account_settings))

print("[6] 설정 창에서 저장 · 자료를 고쳐 저장 — 그 자리에서 내 계정으로(PC 화면 코드)")
from planner.main_window import MainWindow  # noqa: E402

src = inspect.getsource(MainWindow.on_settings_click)
ok("설정 창 저장 → 바꾼 때 적고 바로 올린다", "stamp_changes" in src and "_push_account_settings(announce=True)" in src
   and src.index("stamp_changes") < src.index("self._save_settings()"))


class Sig:
    def __init__(self):
        self.got = []
        self.ev = threading.Event()

    def emit(self, *a):
        self.got.append(a)
        self.ev.set()


class Auth:
    def is_connected(self):
        return True


class Fake:
    gauth = Auth()
    _account_verified = True
    _push_kb_edits = MainWindow._push_kb_edits

    def __init__(self):
        self.sig_acct_pushed = Sig()
        self.sig_kb_pushed = Sig()
        self.settings = s
        self.touched = 0

    def _touch_sync(self):
        self.touched += 1


f = Fake()
DRIVE.clear()
s.sheet_id, s.sheet_at = "SHEET_NOW", "2099-02-01T00:00:00Z"
MainWindow._push_account_settings(f, announce=True)
f.sig_acct_pushed.ev.wait(5)
ok("설정 저장 → 기다리지 않고 바로 올린다 · 성공을 알린다", f.sig_acct_pushed.got == [("",)]
   and json.loads(DRIVE[acs.FILE])["sheet"]["id"] == "SHEET_NOW", f.sig_acct_pushed.got)
f2 = Fake()
f2._account_verified = False
MainWindow._push_account_settings(f2, announce=True)
ok("구글 연결 전이면 올리지 않고 '연결되면 맞춘다' 고 알린다", f2.sig_acct_pushed.got == [("offline",)])

from planner import kb_edits  # noqa: E402
called = []
_orig_sync = kb_edits.sync
kb_edits.sync = lambda auth: called.append(time.time()) or ["메리츠캐피탈"]
f3 = Fake()
t0 = time.time()
MainWindow._on_kb_local_saved(f3)
f3.sig_kb_pushed.ev.wait(5)
ok("자료 저장 → 그 자리에서 내 계정(kb_edits.json)으로 · 받은 것도 알린다",
   called and called[0] - t0 < 2 and f3.sig_kb_pushed.got == [("", ["메리츠캐피탈"], True)] and f3.touched == 1,
   f3.sig_kb_pushed.got)
kb_edits.sync = _orig_sync
shared = [{"category": "심사서류", "finance": "", "title": "개인 심사서류", "tags": "",
           "body": "1. 신분증\n팩스 0504-214-5287", "checklist": ["신분증"]}]
web_rec = {"item": {"title": "개인 심사서류", "body": "1. 신분증\n팩스 0504-000-1111"},     # 웹은 바꾼 칸만 싣는다
           "base": {"title": "개인 심사서류", "body": shared[0]["body"]}, "at": "2099-01-01T00:00:00Z"}
m = kb_edits.merge([], {}, {"개인 심사서류": web_rec}, "2026-11-09T00:00:00Z", shared)
ok("웹(jyplanner)에서 고친 것을 PC 가 받으면 본문만 바뀌고 체크리스트는 회사 것 그대로",
   m["recs"] and m["recs"][0]["item"]["body"].endswith("0504-000-1111")
   and m["recs"][0]["item"].get("checklist") == ["신분증"] and m["changed"] == ["개인 심사서류"], m["recs"])
whole = (_ROOT / "python" / "planner" / "main_window.py").read_text(encoding="utf-8")
ok("웹에서 고친 것도 2분마다 받아 온다", "self._kb_poll.start(2 * 60 * 1000)" in whole)

app = QApplication.instance() or QApplication([])
from planner.kb_tab import KbTab  # noqa: E402
tab = KbTab()
tab.show_note("내 계정에 저장했습니다", "ok", ms=50)
ok("자료검색 위 안내 줄에 알린다", tab.lbl_hint.text() == "내 계정에 저장했습니다")
t_end = time.time() + 2
while time.time() < t_end and tab.lbl_hint.text() != KbTab.HINT:
    app.processEvents()
    time.sleep(0.02)
ok("조금 뒤 원래 안내로", tab.lbl_hint.text() == KbTab.HINT)

print()
print("실패:", FAIL if FAIL else "없음")
_sys.exit(1 if FAIL else 0)
