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
from pathlib import Path

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


def wait(cond, sec=5.0):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return cond()


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
   and d.tbl.item(0, 2).text() == "11/27 10:00" and d.tbl.item(1, 2).text() == "" and "자료 1.10.0" in d.tbl.item(0, 4).text())
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
ok("계정이 확인되면 알리고 · 지점장이면 단추를 보인다(v1.40)",
   'members.report_async(self.gauth, email, "planner", config.APP_VERSION)' in src
   and "self.sidebar.btn_members.setVisible(config.is_owner(email))" in src)
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

# ===========================================================================
print("[5] v1.40 — 내 상태 묻기 · 지점장 일(제한 · 관리자) · 이 PC 기억 · 관리자 권한")
got = members.status(Auth(), get=lambda url, params=None, headers=None, timeout=0:
                     R(200, {"email": "Kim@Example.com", "owner": False, "admin": True, "blocked": False}))
ok("내 상태 — ?me=1 · 이메일 소문자", got == {"email": "kim@example.com", "owner": False, "admin": True, "blocked": False})
ok("못 물으면 None(아무것도 바꾸지 않게)", members.status(Auth(), get=lambda *a, **k: R(500, {})) is None
   and members.status(Auth(), get=lambda *a, **k: (_ for _ in ()).throw(OSError())) is None)
sent2 = []
st = members.manage(Auth(), "block", " Kim@Example.com", post=lambda url, json=None, headers=None, timeout=0:
                    sent2.append(json) or R(200, {"ok": True, "status": {"email": "kim@example.com", "blocked": True}}))
ok("사용 제한 — 보낸 것 · 받은 상태", sent2 == [{"action": "block", "email": "kim@example.com"}] and st["blocked"] is True)
for code, body, want in ((403, {}, "지점장 계정만"), (400, {"error": "owner"}, "지점장 계정은"), (400, {"error": "bad"}, "이메일을"),
                         (503, {}, "준비되지 않았습니다")):
    try:
        members.manage(Auth(), "admin", "x@example.com", post=lambda *a, _c=code, _b=body, **k: R(_c, _b))
        ok(f"manage {code}", False)
    except members.MembersError as e:
        ok(f"manage {code} → '{want}'", want in str(e), str(e))
cache = members.StatusCache(Path(tempfile.mkdtemp()) / "st.json")
cache.put("Kim@Example.com", {"blocked": True, "admin": False})
ok("이 PC 기억 — 소문자 · 제한된 계정 찾기", cache.get("kim@example.com") == {"blocked": True, "admin": False}
   and cache.blocked_email() == "kim@example.com" and cache.get("none@example.com") is None)
cache.put("kim@example.com", {"blocked": False, "admin": True})
ok("…답이 바뀌면 덮어쓴다", cache.get("kim@example.com") == {"blocked": False, "admin": True} and cache.blocked_email() == "")
ok("기본 자리는 두 프로그램이 같이 보는 곳(APPDATA/JYMembers)", members.StatusCache().path.parent.name == "JYMembers")
ok("지점장 = config.OWNER_EMAIL = members.OWNER", config.OWNER_EMAIL == members.OWNER and config.is_owner("WODUD1903@gmail.com"))
ok("지정 전엔 관리자 아님", not config.is_rates_admin("lee@example.com") and not config.is_kb_admin("lee@example.com"))
config.grant_admin("Lee@Example.com", True)
ok("관리자로 지정되면 지점장과 같은 자료 수정 권한(수당율 · 회사 공통 업무자료 · 인증문자 정리)",
   config.is_rates_admin("lee@example.com") and config.is_kb_admin("lee@example.com") and not config.is_owner("lee@example.com"))
config.grant_admin("lee@example.com", False)
ok("해제하면 다시 아님", not config.is_rates_admin("lee@example.com"))

print("[6] 회원 목록 — 상태 칸 · 줄을 골라 사용 제한 · 관리자 지정(지점장 줄은 못 바꿈)")
import planner.members_dialog as mdlg  # noqa: E402
rows2 = [{"email": "wodud1903@gmail.com", "owner": True, "admin": True, "blocked": False,
          "apps": {"planner": {"first": "2026-11-01T00:00:00.000Z", "last": "2026-11-28T01:00:00.000Z", "ver": "1.40.0"}}},
         {"email": "kim@example.com", "owner": False, "admin": False, "blocked": False, "apps": rows[0]["apps"]},
         {"email": "lee@example.com", "owner": False, "admin": True, "blocked": False, "apps": rows[1]["apps"]},
         {"email": "bad@example.com", "owner": False, "admin": False, "blocked": True, "apps": {}}]
members.fetch = lambda auth, get=None: [dict(x) for x in rows2]
did = []
members.manage = lambda auth, action, email, post=None: did.append((action, email)) or {"email": email}
hints = []
real_hint = mdlg.MembersDialog.share_hint
mdlg.MembersDialog.share_hint = lambda self, action, email: hints.append((action, email))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
d2 = MembersDialog(Auth())
d2.show()
pump(0.5)
ok("상태 칸 — 지점장 · 관리자 · 사용 제한", [d2.tbl.item(i, 1).text() for i in range(4)] == ["지점장", "", "관리자", "사용 제한"])
ok("위 줄에 몇 명씩", "관리자 1명 · 사용 제한 1명" in d2.lbl.text(), d2.lbl.text())
ok("줄을 고르기 전엔 단추가 꺼져 있다", not any(b.isEnabled() for b in (d2.btn_block, d2.btn_unblock, d2.btn_admin, d2.btn_unadmin)))
d2.tbl.selectRow(0)
ok("지점장 줄은 아무것도 못 바꾼다", not any(b.isEnabled() for b in (d2.btn_block, d2.btn_unblock, d2.btn_admin,
                                                            d2.btn_unadmin)) and "지점장" in d2.lbl_pick.text())
d2.tbl.selectRow(1)
ok("일반 직원 — [사용 제한] [관리자로 지정] 만", d2.btn_block.isEnabled() and d2.btn_admin.isEnabled()
   and not d2.btn_unblock.isEnabled() and not d2.btn_unadmin.isEnabled())
d2.btn_block.click()
ok("사용 제한 → 묻고 서버로 · 다시 받는다", wait(lambda: did[-1:] == [("block", "kim@example.com")] and not d2._busy
                                            and d2.btn_reload.isEnabled(), 3))
d2.tbl.selectRow(1)
d2.btn_admin.click()
ok("관리자로 지정 → 서버로 · 시트 공유 안내", wait(lambda: hints[-1:] == [("admin", "kim@example.com")], 3), hints)
pump(0.3)
d2.tbl.selectRow(2)
ok("관리자 줄 — [관리자 해제] 가 켜진다", d2.btn_unadmin.isEnabled() and not d2.btn_admin.isEnabled())
d2.btn_unadmin.click()
ok("관리자 해제 → 시트 공유도 빼라고 안내", wait(lambda: hints[-1:] == [("unadmin", "lee@example.com")], 3))
pump(0.3)
d2.tbl.selectRow(3)
ok("제한된 줄 — [제한 풀기]", d2.btn_unblock.isEnabled() and not d2.btn_block.isEnabled())
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
n_did = len(did)
d2.btn_unblock.click()
pump(0.3)
ok("[아니오] 면 아무것도 안 한다", len(did) == n_did)
d2.close()


class FakeBox:
    """시트 공유 안내 창 — 단추를 차례로 누른다."""
    Information, ActionRole, RejectRole = 1, 2, 3
    clicks = []

    def __init__(self, parent=None):
        self.buttons, self.text = [], ""

    def setWindowTitle(self, t):
        pass

    def setIcon(self, i):
        pass

    def setText(self, t):
        self.text = t
        FakeBox.last = t

    def addButton(self, label, role):
        b = type("B", (), {"label": label})()
        self.buttons.append(b)
        return b

    def exec(self):
        self._c = FakeBox.clicks.pop(0)

    def clickedButton(self):
        return next((b for b in self.buttons if b.label == self._c), None)


opened = []
real_box = mdlg.QMessageBox
mdlg.QMessageBox = FakeBox
mdlg.QDesktopServices.openUrl = staticmethod(lambda url: opened.append(url.toString()))
FakeBox.clicks = ["수당연동용 시트 열기", "인증문자 시트 열기", "닫기"]
mdlg.MembersDialog.share_hint = real_hint
real_hint(d2, "admin", "kim@example.com")
mdlg.QMessageBox = real_box
ok("시트 공유 안내 — 이메일 복사 · 수당연동용 · 인증문자 시트를 연다 · 편집자로",
   QGuiApplication.clipboard().text() == "kim@example.com" and opened == [
       mdlg.SHEET_URL.format(config.RATES_SHEET_ID), mdlg.SHEET_URL.format(config.OTP_DEF_SHEET_ID)]
   and "편집자" in FakeBox.last, (opened, FakeBox.last[:60]))

print("[7] 잠금 창 · 켤 때 · 서버 답 — 제한된 계정은 쓸 수 없다")
from planner.member_lock import LockDialog  # noqa: E402
from PySide6.QtWidgets import QDialog  # noqa: E402
answers = [None, {"blocked": True}, {"blocked": False, "admin": False}]
dl = LockDialog("bad@example.com", lambda: answers.pop(0), "일정관리기")
dl.show()
ok("잠금 창 — 이메일 · [다시 확인] [끝내기]", dl.lbl_mail.text() == "bad@example.com"
   and dl.btn_recheck.text() == "다시 확인" and dl.btn_quit.text() == "끝내기")
dl.btn_recheck.click()
ok("못 물으면 — 인터넷 안내 · 그대로 잠금", wait(lambda: "확인하지 못했습니다" in dl.lbl_state.text(), 3) and dl.isVisible())
dl.btn_recheck.click()
ok("아직 제한 — 그대로 잠금", wait(lambda: "아직 제한" in dl.lbl_state.text(), 3) and dl.isVisible())
dl.btn_recheck.click()
ok("풀렸으면 창이 닫히고 계속 쓴다", wait(lambda: dl.result() == QDialog.Accepted, 3))
dl2 = LockDialog("bad@example.com", lambda: None)
dl2.show()
dl2.btn_quit.click()
ok("[끝내기] → reject", dl2.result() == QDialog.Rejected)

locks, quits, kbset = [], [], []


class FakeLock:
    answer = (QDialog.Rejected, None)

    def __init__(self, email, recheck, name="", parent=None):
        locks.append(email)
        self.status = FakeLock.answer[1]

    def exec(self):
        return FakeLock.answer[0]


mw.LockDialog = FakeLock
w._force_quit = lambda: quits.append(1)
w.tab_kb.set_account = lambda e: kbset.append(e)
w._member_cache = members.StatusCache(Path(tempfile.mkdtemp()) / "st.json")
w._member_cache.put("bad@example.com", {"blocked": True, "admin": False})
w._provisional_account = "bad@example.com"
w._startup_gate()
ok("켤 때 — 이 PC 가 '제한됨' 으로 기억한 계정이면 바로 잠금 · [끝내기] 면 끝낸다", locks == ["bad@example.com"] and quits == [1])
w._provisional_account = ""
config.forget_account()
locks.clear(); quits.clear()
w._startup_gate()
ok("로그아웃해 둬도 이 PC 에서 제한됐던 계정이 있으면 잠금(로그아웃으로 비켜 가지 못하게)",
   locks == ["bad@example.com"] and quits == [1])
FakeLock.answer = (QDialog.Accepted, {"blocked": False, "admin": True})
locks.clear(); quits.clear()
w._startup_gate()
ok("잠금 창에서 풀리면(다시 확인) 그대로 쓴다 · 관리자면 관리자", quits == [] and config.is_rates_admin("bad@example.com"))
config.grant_admin("bad@example.com", False)
w._member_cache = members.StatusCache(Path(tempfile.mkdtemp()) / "st.json")
w._member_cache.put("boss2@example.com", {"blocked": False, "admin": True})
w._provisional_account = "boss2@example.com"
locks.clear()
w._startup_gate()
ok("켤 때 — 관리자로 기억한 계정은 서버 답을 기다리지 않고 관리자", config.is_rates_admin("boss2@example.com") and locks == [])
w._on_member("boss2@example.com", None)
ok("서버 답을 못 받으면 아무것도 바꾸지 않는다", config.is_rates_admin("boss2@example.com"))
w._on_member("boss2@example.com", {"blocked": False, "admin": False})
ok("서버가 관리자 해제라 하면 바로 해제 · 회사 공통 자료 화면도 새 권한으로", not config.is_rates_admin("boss2@example.com")
   and kbset[-1:] == ["boss2@example.com"] and w._member_cache.get("boss2@example.com") == {"blocked": False, "admin": False})
FakeLock.answer = (QDialog.Rejected, None)
locks.clear(); quits.clear()
w._on_member("boss2@example.com", {"blocked": True, "admin": False})
ok("쓰는 중에 제한되면(30분마다 묻는다) 잠금 → 끝내기", locks == ["boss2@example.com"] and quits == [1]
   and w._member_cache.blocked_email() == "boss2@example.com")
members.ENABLED = True
google_client.GoogleAuth.is_connected = lambda self: True
members.status = lambda auth, get=None: {"email": "x", "owner": False, "admin": True, "blocked": False}
w._check_member("Boss3@Example.com")
ok("계정이 확인되면 서버에 묻고(뒤에서) 답을 적용", wait(lambda: config.is_rates_admin("boss3@example.com"), 3))
ok("30분마다 다시 묻는다", w._member_timer.isActive() and w._member_timer.interval() == 30 * 60 * 1000)
google_client.GoogleAuth.is_connected = lambda self: False
members.ENABLED = False

print()
print(f"{len(FAIL)}건 실패" if FAIL else "전부 통과", flush=True)
os._exit(1 if FAIL else 0)
