"""일반(관리자가 아닌) 계정으로 로그인했을 때의 오류들(v1.31.3 점검에서 찾아 고친 것).

지점장: "사소한 오류와 내 관리자 계정 외에 다른 일반 아이디로 로그인했을 때의 오류까지 전부 찾아서 수정해줘."
가짜 구글로 일정관리기를 일반 계정으로 실제로 띄워 찾은 것들이다.
  · 구글 동의 화면에서 항목을 빼고 로그인하면 아무 말 없이 그 기능만 안 됐다 → 로그인 직후·상태 줄에 알린다.
  · 'Drive 조회 실패 (HTTP 403)' — 무엇을 해야 하는지 없었다 → 다시 로그인(모두 선택)하라고 적는다.
  · 권한 없는 시트(남의 시트 · 보기만) — 무엇을 하면 되는지 적는다.
  · 켠 직후 설정에서 시트를 켜면 불러오기가 겹쳐 같은 오류 창이 두 번 떴다.
  · '내 계정에서만 고침' 묶음에 붙인 내 첨부의 이름 바꾸기가 빠져 있었다.
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))

import inspect
import json
import os
import tempfile

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton  # noqa: E402

app = QApplication.instance() or QApplication([])

from planner import config, google_client, kb, kb_tab, sheets, theme  # noqa: E402
from planner.main_window import MainWindow  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


CAL, TASKS = "https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/tasks"
APPDATA, SHEETS = "https://www.googleapis.com/auth/drive.appdata", config.SCOPE_SHEETS
FILE, DOCS = "https://www.googleapis.com/auth/drive.file", config.SCOPE_DOCS_READ
ALL = ["openid", "https://www.googleapis.com/auth/userinfo.email", CAL, TASKS, APPDATA, SHEETS, FILE, DOCS]

print("[1] 로그인할 때 빠진 권한을 안다")
tok = config.base_dir() / "google_token.json"


def auth_with(scopes, rt="RT"):
    tok.write_text(json.dumps({"refresh_token": rt, "scopes": scopes}), encoding="utf-8")
    return google_client.GoogleAuth(tok)


ok("다 받았으면 없음", auth_with(ALL).missing_scopes() == [])
a = auth_with(["openid", "https://www.googleapis.com/auth/userinfo.email", CAL, TASKS])
ok("시트·동기화·첨부·뉴스를 뺐다", a.missing_scopes() == [APPDATA, SHEETS, FILE, DOCS], a.missing_scopes())
ok("늘 살피는 것(상태 줄)에는 뉴스 문서 읽기를 넣지 않는다(뉴스 창이 따로 알린다)",
   auth_with([CAL, TASKS, APPDATA, SHEETS, FILE]).missing_scopes(core_only=True) == []
   and auth_with([CAL, TASKS, APPDATA, SHEETS, FILE]).missing_scopes() == [DOCS])
ok("드라이브 읽기가 있으면 문서 읽기는 없어도 된다",
   auth_with([CAL, TASKS, APPDATA, SHEETS, FILE, config.SCOPE_DRIVE_READ]).missing_scopes() == [])
ok("권한 목록을 모르는 옛 토큰은 섣불리 알리지 않는다", auth_with([]).missing_scopes() == [])
ok("로그인 안 했으면 없음", auth_with(ALL[:3], rt="").missing_scopes() == [])
ok("이름표가 요청하는 권한을 다 덮는다",
   all(sc in config.SCOPE_LABELS for sc in config.GOOGLE_SCOPES if sc not in ("openid", "email")))

print("[2] 로그인 직후 · 상태 줄에 알린다")
BOX = []
QMessageBox.warning = staticmethod(lambda *a, **k: BOX.append(a[2]))


class Btn:
    def hide(self): pass
    def show(self): pass
    def set_busy(self, on): pass
    def apply_theme(self): pass


class Fake:
    def __init__(self, auth):
        self.gauth = auth
        self.lbl_status = QLabel("")
        self.btn_google = Btn()


f = Fake(auth_with([CAL, TASKS, APPDATA]))
ok("빠진 것이 있으면 로그인 직후 창으로 알린다", MainWindow._warn_missing_scopes(f) is True and len(BOX) == 1
   and "구글 시트" in BOX[0] and "첨부 올리기" in BOX[0] and "모두 선택" in BOX[0], BOX[-1:])
MainWindow.update_google_status(f)
ok("상태 줄에도 늘 보인다(무엇이 빠졌는지 · 다시 로그인)", "권한 빠짐" in f.lbl_status.text()
   and "구글 시트" in f.lbl_status.text() and "다시 로그인" in f.lbl_status.text()
   and "모두 선택" in f.lbl_status.toolTip(), f.lbl_status.text())
BOX.clear()
f = Fake(auth_with(ALL))
ok("다 받았으면 아무 말 없다", MainWindow._warn_missing_scopes(f) is False and BOX == [])
MainWindow.update_google_status(f)
ok("상태 줄은 평소대로", f.lbl_status.text().startswith("구글: 연결됨  (") and f.lbl_status.toolTip() == "")
src = inspect.getsource(MainWindow._on_google_login_done)
ok("로그인이 끝나면 확인한다", "self._warn_missing_scopes()" in src)

print("[3] 드라이브·시트 권한 오류 — 무엇을 하면 되는지 적는다")


class R:
    def __init__(self, code, body=None):
        self.status_code = code
        self._b = body or {}
        self.text = json.dumps(self._b)

    def json(self):
        return self._b


class H:
    def __init__(self, r):
        self.r = r

    def get(self, *a, **k):
        return self.r

    post = patch = get


google_client.GoogleAuth._headers = lambda self: {}
google_client._http = lambda: H(R(403))
try:
    google_client.drive_find(auth_with(ALL), "planner_sync.json")
    ok("드라이브 403", False)
except google_client.GoogleError as e:
    ok("드라이브 403 — 다시 로그인(모두 선택)하라고 한다", "모두 선택" in str(e) and "HTTP 403" in str(e)
       and "드라이브" in str(e), str(e))
google_client._http = lambda: H(R(500))
try:
    google_client.drive_find(auth_with(ALL), "x")
    ok("드라이브 500", False)
except google_client.GoogleError as e:
    ok("다른 오류는 그대로(HTTP 500)", "HTTP 500" in str(e) and "모두 선택" not in str(e))
try:
    sheets._check(R(403, {"error": {"message": "The caller does not have permission", "status": "PERMISSION_DENIED"}}))
    ok("시트 403", False)
except google_client.GoogleError as e:
    ok("권한 없는 시트 — 공유를 요청하거나 시트 주소를 확인하라고 한다", "편집자" in str(e) and "(403)" in str(e)
       and "The caller does not have permission" in str(e), str(e))

print("[4] 시트 불러오기가 겹치지 않는다")
src = inspect.getsource(MainWindow.load_sheet_async)
ok("읽는 중이면 또 읽지 않는다", "self._sheet_loading == self._sheet_epoch" in src.replace('getattr(self, "_sheet_loading", None)', "self._sheet_loading"))
ok("불러오기를 시작하면 '저절로 불러오기' 는 더 조르지 않는다(실패한 것을 곧바로 또 읽어 창이 두 번 뜨지 않게)",
   "self._auto_load_started = True" in src)
ok("목록이 오면(또는 실패하면) 다시 불러올 수 있다",
   "self._sheet_loading = None" in inspect.getsource(MainWindow._on_sheet_rows))

print("[5] '내 계정에서만 고침' 에 붙인 내 첨부도 이름을 바꾼다")
kb.save_shared([{"category": "캐피탈", "finance": "", "title": "메리츠캐피탈", "tags": "", "body": "본문", "checklist": []}])
d = kb_tab.KbEditDialog("staff@example.com")
d.local[0]["files"] = [{"id": "F1", "name": "새이름.png", "_was": "옛이름.png", "mime": "image/png", "size": 3}]
ok("이름 바꾼 것에 들어 있다", d.renamed() == [("F1", "새이름.png")], d.renamed())
ok("일반 계정은 회사 공통 묶음이 없다 · 내 메모가 먼저", d.cmb_src.findData(kb.SRC_SHARED) < 0
   and d.cmb_src.itemData(0) == kb.SRC_MINE and d.cmb_src.findData(kb.SRC_LOCAL) == 1)

print()
print("실패:", FAIL if FAIL else "없음")
_sys.exit(1 if FAIL else 0)
