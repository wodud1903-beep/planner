"""카톡 매크로(A1Auto 옮김) — 업무자료검색의 [카톡 매크로] 창.

지점장: "kmacro 의 카카오톡 매크로 기능을 … 일정관리기 및 자료검색 프로그램 앱에만 추가해줘. 단, 기능은 절대
수정하지 말고 기존 기능을 전부." / "3,4번(자주 쓰는 문구 · 발송 간격)은 구글 계정에 저장하고 자동 불러오도록."
엔진은 verify_macro_engine 이 본다. 여기서는 단추 · 창 · 트레이 · 단축키를 볼 때 · 계정 파일 · 인증번호 · 업데이트 ·
끄기, 그리고 일정관리기 사본과 같은 파일인지.
"""
import pathlib as _pl
import sys as _sys

_HERE = _pl.Path(__file__).resolve().parent
_sys.path.insert(0, str(_HERE.parent))
_sys.path.insert(0, str(_HERE))

import os  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402

os.environ["APPDATA"] = tempfile.mkdtemp()
tempfile.tempdir = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication([])

from fake_google import FakeGoogle  # noqa: E402
from kbsearch import google_auth, kakao_macro as km, otp, otp_popup  # noqa: E402
from kbsearch.main_window import MainWindow, _AppDataIO  # noqa: E402
from kbsearch.settings import Settings  # noqa: E402

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


QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
g = FakeGoogle().install()
g.tab = False
w = MainWindow(Settings.load())
w.show_window()
pump(1.0)

print("[1] 위 단추줄 · 트레이에 [카톡 매크로]")
ok("[카톡 매크로] 단추", w.btn_macro.text() == "카톡 매크로" and w.btn_macro.isVisible())
ok("트레이 메뉴에도", "카톡 매크로" in [a.text() for a in w.tray.contextMenu().actions()])
ok("누르기 전엔 창을 만들지 않는다", w._macro is None)

print("[2] 누르면 A1Auto 창처럼 따로 뜬다")
w.btn_macro.click()
pump(0.4)
m = w._macro
ok("창 'A1Auto'", m is not None and m.isVisible() and m.windowTitle() == "A1Auto")
v = m.view
ok("A1Auto 화면 그대로(전송방식 · 시작/중지 · 카드 · 로그 · 도구 메뉴)",
   [r.text() for r in v.rb_modes] == ["텍스트", "이미지", "이미지+텍스트"]
   and v.btn_start.text() == "매크로 시작 (INSERT)" and v.btn_stop.text() == "매크로 중지 (DELETE)"
   and [a.text() for a in v.btn_tools.menu().actions()] == ["자주 쓰는 문구", "환경설정", "수정로그"])
ok("앱 트레이를 함께 쓴다(끝나면 풍선 알림)", v.tray is w.tray)
ok("창이 열려 있으면 Insert · Delete 를 본다", v.armed())
m.showMinimized()
pump(0.2)
ok("작게 내려도 본다(A1Auto 를 트레이에 내린 것과 같다)", v.armed())
m.showNormal()
pump(0.2)
v.memo.setPlainText("남겨 둘 메시지")
v.add_log("✅ 2026-11-27 09:00:00 → 홍길동 발송완료", "ok")
m.close()
pump(0.3)
ok("닫으면 안 본다(A1Auto 를 끈 것과 같다) · 로그 파일로", not v.armed() and not m.isVisible()
   and any(km.logs_dir().glob("log_*.txt")) and v.log.toPlainText() == "")
w.open_macro()
pump(0.3)
ok("다시 열면 같은 창(메시지는 그대로)", w._macro is m and m.isVisible() and v.memo.toPlainText() == "남겨 둘 메시지")

print("[3] 발송 간격 · 자주 쓰는 문구 — 로그인했으면 내 구글 계정(일정관리기와 같은 kakao_macro.json)")
w.gauth.is_connected = lambda: False
ok("로그인 전 — 이 PC 사본만", w._macro_io() == (None, ""))
msgs = []
QMessageBox.information = staticmethod(lambda *a, **k: msgs.append(a[2] if len(a) > 2 else ""))
v.rb_modes[0].click()
v.memo.setPlainText("hi")
v.btn_start.click()
ok("로그인 전 [매크로 시작] → 막고 '[동기화] 로 로그인' 안내", not v.busy() and msgs and "구글 로그인" in msgs[-1]
   and "[동기화]" in msgs[-1], msgs[-1:])
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
w.gauth.is_connected = lambda: True
w.gauth.email = "Me@Example.com"
io, acct = w._macro_io()
ok("로그인 뒤 — 앱 전용 공간 · 계정 · 매크로 시작 허용", isinstance(io, _AppDataIO) and acct == "me@example.com"
   and w._macro_login_msg() == "")
calls = []
google_auth.appdata_find = lambda auth, name: calls.append(("find", name)) or "FID9"
google_auth.appdata_write = lambda auth, name, text, fid=None: calls.append(("write", name, fid)) or "FID9"
io.write(km.REMOTE_NAME, "{}")
ok("쓸 때 먼저 찾아서 그 파일을 고친다(같은 이름이 둘 생기지 않게)", calls == [("find", km.REMOTE_NAME),
                                                                  ("write", km.REMOTE_NAME, "FID9")], calls)
w.gauth.is_connected = lambda: False

print("[4] 도는 동안 — 인증번호는 띄우기만 · 자동 업데이트 · 끄기 신호는 미룬다")
otp.claim = lambda it, now=None: True
shown = []
otp_popup.show = lambda it, copied=False: shown.append(copied)
QGuiApplication.clipboard().setText("붙여넣을 메시지")
v.busy = lambda: True
w._on_otp([{"code": "123456", "sender": "x", "body": "인증번호 123456"}], "")
ok("인증번호 → 클립보드 그대로 · 띄우기만", QGuiApplication.clipboard().text() == "붙여넣을 메시지" and shown == [False], shown)
ok("자동 업데이트를 미룬다", w._busy_now())
v.busy = lambda: False
w._on_otp([{"code": "654321", "sender": "x", "body": "인증번호 654321"}], "")
ok("쉬는 중이면 예전처럼 클립보드에", QGuiApplication.clipboard().text() == "654321" and shown[-1] is True)
import inspect  # noqa: E402
ok("끄기 신호(switch)도 미룬다", "self._macro_busy()" in inspect.getsource(MainWindow._on_switch))

print("[5] 끌 때 — A1Auto 를 끈 것처럼")
done = []
v.shutdown = lambda: done.append(1) or ""
w._shutdown()
ok("클립보드 · 발송 기록 · 로그(view.shutdown)", done == [1])

print("[6] 일정관리기 사본과 같은 파일")
planner = _HERE.parents[1] / "python" / "planner"
for f in ("kakao_win.py", "kakao_macro.py", "kakao_macro_view.py", "members.py"):
    mine = (_HERE.parent / "kbsearch" / f).read_text(encoding="utf-8")
    theirs = planner / f
    if theirs.is_file():
        ok(f"{f} — 일정관리기와 글자 하나 다르지 않다", mine == theirs.read_text(encoding="utf-8"))
    else:
        print(f"  (일정관리기 {f} 가 이 작업 폴더에 없어 견주지 않음)")

print()
print(f"{len(FAIL)}건 실패" if FAIL else "전부 통과", flush=True)
os._exit(1 if FAIL else 0)
