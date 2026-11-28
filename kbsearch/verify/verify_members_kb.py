"""사용 제한 · 관리자 지정(kb-v1.13) — 업무자료검색 쪽.

지점장: "현재 로그인했던 사용자 중에 내가 계정 리스트를 보고 해당 이메일에 사용 제한할 수 있는 기능" — 앱 전체.
"내가 관리자로 지정할 이메일도 — 관리자는 지금 내가 자료 수정할 수 있는 권한들을 모두."
목록 · 제한 · 지정은 일정관리기 [회원 목록](지점장)에서 한다. 여기서는 켤 때 · 30분마다 묻고 잠그는 것 · 관리자 권한 ·
일정관리기와 같은 파일인지(members · member_lock).
"""
import pathlib as _pl
import sys as _sys

_HERE = _pl.Path(__file__).resolve().parent
_sys.path.insert(0, str(_HERE.parent))
_sys.path.insert(0, str(_HERE))

import os  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

os.environ["APPDATA"] = tempfile.mkdtemp()
tempfile.tempdir = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication([])

from fake_google import FakeGoogle  # noqa: E402
from kbsearch import config, members  # noqa: E402
import kbsearch.main_window as mw  # noqa: E402
from kbsearch.main_window import MainWindow  # noqa: E402
from kbsearch.settings import Settings  # noqa: E402

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


QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)

print("[1] 지점장 · 관리자 권한")
ok("지점장 = config.OWNER_EMAIL = members.OWNER", config.OWNER_EMAIL == members.OWNER == "wodud1903@gmail.com")
ok("지정 전엔 관리자 아님", not config.is_admin("lee@example.com"))
config.grant_admin("Lee@Example.com", True)
ok("관리자로 지정되면 회사 공통 자료를 고치고 시트로 올린다(is_admin)", config.is_admin("lee@example.com"))
config.grant_admin("lee@example.com", False)
ok("해제하면 다시 아님 · 원래 관리자는 그대로", not config.is_admin("lee@example.com")
   and config.is_admin("qkrwlsgh7303@gmail.com"))

print("[2] 일정관리기와 같은 파일")
planner = _HERE.parents[1] / "python" / "planner"
for f in ("members.py", "member_lock.py"):
    mine = (_HERE.parent / "kbsearch" / f).read_text(encoding="utf-8")
    theirs = planner / f
    if theirs.is_file():
        ok(f"{f} — 일정관리기와 글자 하나 다르지 않다", mine == theirs.read_text(encoding="utf-8"))
    else:
        print(f"  (일정관리기 {f} 가 이 작업 폴더에 없어 견주지 않음)")
cfg = (planner / "config.py")
if cfg.is_file():
    import re  # noqa: E402
    m = re.search(r'OWNER_EMAIL = "([^"]+)"', cfg.read_text(encoding="utf-8"))
    ok("일정관리기 config.OWNER_EMAIL 과 같다", m and m.group(1) == config.OWNER_EMAIL)

print("[3] 켤 때 · 서버 답 — 제한된 계정은 잠그고 끝낸다")
g = FakeGoogle().install()
g.tab = False
w = MainWindow(Settings.load())
locks, quits, refreshed = [], [], []


class FakeLock:
    answer = (QDialog.Rejected, None)

    def __init__(self, email, recheck, name="", parent=None):
        locks.append(email)
        self.status = FakeLock.answer[1]

    def exec(self):
        return FakeLock.answer[0]


mw.LockDialog = FakeLock
w.quit_app = lambda: quits.append(1)
real_refresh = w.refresh_account
w.refresh_account = lambda: refreshed.append(1) or real_refresh()
w._member_cache = members.StatusCache(Path(tempfile.mkdtemp()) / "st.json")
w._member_cache.put("bad@example.com", {"blocked": True, "admin": False})
w._account = lambda: "bad@example.com"
w._startup_gate()
ok("이 PC 가 '제한됨' 으로 기억한 계정 — 켜자마자 잠금 · [끝내기] 면 끝낸다", locks == ["bad@example.com"] and quits == [1])
w._account = lambda: ""
locks.clear(); quits.clear()
w._startup_gate()
ok("로그아웃해 둬도 이 PC 에서 제한됐던 계정이 있으면 잠금", locks == ["bad@example.com"] and quits == [1])
FakeLock.answer = (QDialog.Accepted, {"blocked": False, "admin": False})
locks.clear(); quits.clear()
w._startup_gate()
ok("잠금 창에서 풀리면(다시 확인) 그대로 쓴다", quits == [])
w._member_cache = members.StatusCache(Path(tempfile.mkdtemp()) / "st.json")
w._member_cache.put("boss@example.com", {"blocked": False, "admin": True})
w._account = lambda: "boss@example.com"
refreshed.clear()
w._startup_gate()
ok("관리자로 기억한 계정 — 켜자마자 관리자 · 아래 줄 새로", config.is_admin("boss@example.com") and refreshed)
w._on_member("boss@example.com", None)
ok("서버 답을 못 받으면 아무것도 바꾸지 않는다", config.is_admin("boss@example.com"))
w._on_member("boss@example.com", {"blocked": False, "admin": False})
ok("관리자 해제 — 바로", not config.is_admin("boss@example.com")
   and w._member_cache.get("boss@example.com") == {"blocked": False, "admin": False})
FakeLock.answer = (QDialog.Rejected, None)
locks.clear(); quits.clear()
w._on_member("boss@example.com", {"blocked": True, "admin": False})
ok("쓰는 중에 제한되면(30분마다 묻는다) 잠금 → 끝내기", locks == ["boss@example.com"] and quits == [1])
members.ENABLED = True
members.status = lambda auth, get=None: {"email": "x", "owner": False, "admin": True, "blocked": False}
w._account = lambda: "boss2@example.com"
w._check_member()
ok("로그인돼 있으면 서버에 묻고(뒤에서) 답을 적용", wait(lambda: config.is_admin("boss2@example.com"), 3))
members.ENABLED = False
ok("30분마다 다시 묻는다", w._member_timer.isActive() and w._member_timer.interval() == 30 * 60 * 1000)
import inspect  # noqa: E402
ok("로그인하면 바로 묻는다", "self._check_member()" in inspect.getsource(MainWindow._on_login))

print()
print(f"{len(FAIL)}건 실패" if FAIL else "전부 통과", flush=True)
os._exit(1 if FAIL else 0)
