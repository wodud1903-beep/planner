"""회원 목록 · 매크로 로그인 필수(v1.37).

지점장: "매크로를 작동하려면 로그인이 필수로 되어 있어야 가능하게 해 주고, 일정관리기 및 자료검색 앱에서 로그인한
목록은 내 관리자 계정으로 회원 리스트를 이메일로 알고 싶어."
서버(api/members)는 web/verify/verify_api.mjs [회원] 이 본다. 여기서는 PC 쪽 — 알리기 · 받아 보기 · 관리자 단추 ·
매크로 시작 막기.
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
import os as _os
_os.chdir(_ROOT / "python")

import os
import tempfile
import time
from datetime import date

os.environ["APPDATA"] = tempfile.mkdtemp()
tempfile.tempdir = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFont, QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication([])
app.setFont(QFont("Malgun Gothic", 10))

from planner import config, google_client, members, sheets, sync, theme  # noqa: E402
from planner import startup_dialog as _sd  # noqa: E402
from planner.members_dialog import MembersDialog  # noqa: E402

theme.apply_to_app(app)
FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


def pump(sec=0.2):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


class Auth:
    def __init__(self, on=True):
        self.on = on

    def is_connected(self):
        return self.on

    def _headers(self):
        return {"Authorization": "Bearer AT-123"}


class R:
    def __init__(self, code, body=None):
        self.status_code, self._b = code, body

    def json(self):
        return self._b


print("[1] 알리기 — 앱 이름 · 판만(이메일은 서버가 구글에 직접 묻는다) · 하루 한 번")
sent = []
ok_ = members.report(Auth(), "planner", "1.37.0",
                     post=lambda url, json=None, headers=None, timeout=0: sent.append((url, json, headers)) or R(200))
ok("서버 주소 · 토큰 · 보낸 것", ok_ and sent[0][0] == "https://jyplanner.vercel.app/api/members"
   and sent[0][1] == {"app": "planner", "ver": "1.37.0"} and sent[0][2]["Authorization"] == "Bearer AT-123")
ok("이메일은 보내지 않는다", "email" not in sent[0][1])
ok("실패해도 오류 없이 False", members.report(Auth(), "kb", "1", post=lambda *a, **k: (_ for _ in ()).throw(OSError())) is False)
calls = []
members.ENABLED = True
real_report = members.report
members.report = lambda auth, app_, ver: calls.append((app_, ver)) or True
ok("처음엔 보낸다", members.report_async(Auth(), "Me@Example.com", "planner", "1.37.0"))
ok("같은 날 같은 앱은 다시 안 보낸다", not members.report_async(Auth(), "me@example.com", "planner", "1.37.0"))
ok("업무자료검색은 따로 센다", members.report_async(Auth(), "me@example.com", "kb", "1.10.0"))
ok("로그인 전이면 안 보낸다", not members.report_async(Auth(False), "x@example.com", "planner", "1"))
pump(0.3)
ok("뒤에서 보냈다", sorted(calls) == [("kb", "1.10.0"), ("planner", "1.37.0")], calls)
members.report = lambda *a: False
ok("못 보내면 다음에 다시", members.report_async(Auth(), "y@example.com", "planner", "1") and (pump(0.3) or True)
   and members.report_async(Auth(), "y@example.com", "planner", "1"))
members.report = real_report
members.ENABLED = False
ok("검사(윈도가 아님)에서는 진짜 서버로 보내지 않는다", not members.report_async(Auth(), "z@example.com", "planner", "1"))

print("[2] 받아 보기 — 관리자만(서버가 확인) · 까닭은 알아들을 말로")
rows = [{"email": "kim@example.com", "apps": {"planner": {"first": "2026-11-20T01:00:00.000Z", "last": "2026-11-27T01:00:00.000Z",
                                                          "ver": "1.37.0", "n": 5},
                                              "kb": {"first": "2026-11-25T00:00:00.000Z", "last": "2026-11-26T00:00:00.000Z",
                                                     "ver": "1.10.0", "n": 1}}},
        {"email": "lee@example.com", "apps": {"kb": {"first": "2026-11-26T03:00:00.000Z", "last": "2026-11-26T03:00:00.000Z",
                                                     "ver": "1.10.0", "n": 1}}}]
ok("받는다", members.fetch(Auth(), get=lambda *a, **k: R(200, {"members": rows})) == rows)
for code, want in ((403, "관리자 계정만"), (401, "다시 로그인"), (503, "준비되지 않았습니다"), (500, "HTTP 500")):
    try:
        members.fetch(Auth(), get=lambda *a, _c=code, **k: R(_c, {}))
        ok(f"HTTP {code}", False)
    except members.MembersError as e:
        ok(f"HTTP {code} → '{want}'", want in str(e), str(e))
ok("시각은 한국 시각으로 짧게", members.short("2026-11-27T01:00:00.000Z") == "11/27 10:00" and members.short("") == "")

print("[3] 회원 목록 창 — 이메일 · 앱마다 마지막 로그인 · 판 · [이메일 목록 복사]")
members.fetch = lambda auth, get=None: rows
d = MembersDialog(Auth())
d.show()
ok("다 받으면 표로", (pump(0.5) or True) and d.tbl.rowCount() == 2 and d.tbl.item(0, 0).text() == "kim@example.com"
   and d.tbl.item(0, 1).text() == "11/27 10:00" and d.tbl.item(1, 1).text() == "" and "자료 1.10.0" in d.tbl.item(0, 3).text())
ok("모두 · 앱마다 몇 명", d.lbl.text().startswith("모두 2명 — 일정관리기 1명 · 업무자료검색 2명"), d.lbl.text())
d.btn_copy.click()
ok("이메일 목록 복사(한 줄에 하나)", QGuiApplication.clipboard().text() == "kim@example.com\nlee@example.com")
members.fetch = lambda auth, get=None: (_ for _ in ()).throw(members.MembersError("관리자 계정만 볼 수 있습니다."))
d.btn_reload.click()
ok("못 받으면 까닭", (pump(0.5) or True) and "관리자 계정만" in d.lbl.text(), d.lbl.text())
d.close()

print("[4] 일정관리기 — [회원 목록] 은 관리자만 · 매크로는 로그인해야 시작")
_sd.StartupDialog.show_for = staticmethod(lambda *a, **k: None)
QMessageBox.information = staticmethod(lambda *a, **k: None)
config.set_account("tester@example.com")
google_client.GoogleAuth.is_connected = lambda self: False
sync.sync_now = lambda *a, **k: (False, "")
sheets.read_rows = lambda *a, **k: (1, [], [])
from planner.main_window import MainWindow  # noqa: E402
w = MainWindow()
w.show()
pump(0.3)
ok("계정 확인 전엔 [회원 목록] 숨김", w.sidebar.btn_members.isHidden())
src = __import__("inspect").getsource(MainWindow)
ok("계정이 확인되면 알리고 · 관리자면 단추를 보인다",
   'members.report_async(self.gauth, email, "planner", config.APP_VERSION)' in src
   and "self.sidebar.btn_members.setVisible(config.is_rates_admin(email))" in src)
opened = []
import planner.main_window as mw  # noqa: E402
mw.MembersDialog = lambda auth, parent=None: type("D", (), {"exec": lambda self: opened.append(1)})()
w.account_email = "staff@example.com"
w.open_members()
ok("관리자가 아니면 창을 열지 않는다", opened == [])
w.account_email = "wodud1903@gmail.com"
w.open_members()
ok("관리자는 연다", opened == [1])
msgs = []
QMessageBox.information = staticmethod(lambda *a, **k: msgs.append(a[2] if len(a) > 2 else ""))
v = w.tab_macro
v.rb_modes[0].click()
v.memo.setPlainText("안녕하세요")
v.btn_start.click()
ok("로그인 전 [매크로 시작] → 막고 알린다", not v.busy() and msgs and "구글 로그인" in msgs[-1], msgs[-1:])
ok("화면 위에도 '로그인해야 시작' 표시", "구글 로그인" in v.lbl_where.text(), v.lbl_where.text())
google_client.GoogleAuth.is_connected = lambda self: True
ok("로그인하면 막지 않는다", w._macro_login_msg() == "" and v.start_block() == "")
google_client.GoogleAuth.is_connected = lambda self: False

print()
print(f"{len(FAIL)}건 실패" if FAIL else "전부 통과", flush=True)
os._exit(1 if FAIL else 0)
