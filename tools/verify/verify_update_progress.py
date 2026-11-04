"""업데이트 진행 창(v1.27) — 지점장 요청:
"업데이트 할 때에는 프로그레스바를 만들어서 업데이트 하고 있다는 내용을 시각적으로 보이게 해줘".

  · 받는 동안 막대(%)와 'MB' — 켤 때 · [업데이트 확인] · 켜 둔 동안 모두
  · 다 받으면 '바꾸는 중 — 잠시 뒤 새 버전이 저절로 켜집니다' 를 보여 준 뒤 끝낸다
  · 실패하면 까닭을 진행 창에 잠깐(묻는 창 없음) · 직접 누른 것이면 예전처럼 알림 창
  · 새 판이 켜지면 '업데이트 완료' 를 잠깐(누르면 변경 이력)
  · 단추가 없고 포커스를 빼앗지 않는다(받는 동안 그대로 일한다)
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
import os as _os
_os.chdir(_ROOT / "python")

import inspect
import json
import os
import tempfile
import time

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton  # noqa: E402

from planner import config, crashlog, google_client, sheets, sync, theme, updater  # noqa: E402
from planner import startup_dialog as _sd  # noqa: E402
from planner.update_progress import UpdateProgress  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


app = QApplication.instance() or QApplication([])
theme.apply_to_app(app)


def pump(sec=0.3):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


MB = 1 << 20
print("[1] 진행 창 — 막대 · % · MB · 단계")
p = UpdateProgress("1.27.0")
p.pop()
pump(0.1)
ok("뜬다 · 단추가 없다", p.isVisible() and not p.findChildren(QPushButton))
ok("포커스를 빼앗지 않는다(받는 동안 그대로 일한다)", p.testAttribute(Qt.WA_ShowWithoutActivating)
   and bool(p.windowFlags() & Qt.WindowStaysOnTopHint))
g = QGuiApplication.primaryScreen().availableGeometry()
ok("화면 오른쪽 아래(작업 표시줄 위)", g.contains(p.frameGeometry()) and p.x() > g.center().x()
   and p.y() > g.center().y(), (p.geometry(), g))
ok("제목에 새 판 번호", "v1.27.0" in p.lbl_title.text(), p.lbl_title.text())
p.progress(10 * MB, 50 * MB)
ok("받는 정도 — 20% · '10.0 / 50.0 MB'", p.bar.value() == 20 and "20%" in p.lbl_msg.text()
   and "10.0 / 50.0 MB" in p.lbl_msg.text(),
   (p.bar.value(), p.lbl_msg.text()))
p.progress(50 * MB, 50 * MB)
ok("다 받으면 100%", p.bar.value() == 100)
p.progress(3 * MB, 0)
ok("크기를 모르면 오가는 막대 + 받은 MB", p.bar.maximum() == 0 and "3.0 MB" in p.lbl_msg.text())
p.applying()
ok("바꾸는 중 — '잠시 뒤 새 버전이 저절로 켜집니다'", p.state == "apply" and p.bar.value() == 100
   and "저절로 켜집니다" in p.lbl_sub.text() and "바꾸는 중" in p.lbl_msg.text(), p.lbl_sub.text())
p.progress(1, 2)
ok("바꾸는 중에는 막대가 뒤로 가지 않는다", p.bar.value() == 100)
p.failed("HTTP 503 잠시 응답 없음\n자세히")
ok("실패 — 까닭을 빨간 글로 · 지금 판으로 계속", p.state == "fail" and "HTTP 503" in p.lbl_msg.text()
   and p.lbl_msg.property("bad") == "true" and "지금 판으로" in p.lbl_sub.text())
ok("실패는 잠깐 보여 주고 저절로 닫힌다", p._close_timer.isActive())
p.done("1.27.0")
ok("완료 — '새 버전 v1.27.0 으로 바뀌었습니다' · 저절로 닫힘", p.state == "done"
   and "v1.27.0" in p.lbl_msg.text() and p._close_timer.isActive() and p.bar.value() == 100)
p.close()
for name in ("light", "dark", "warm"):
    theme.set_theme(name)
    q = UpdateProgress("1.27.0")
    ok(f"테마 '{name}' 색을 쓴다", theme.c("panel_bg") in q.card.styleSheet()
       and theme.c("accent") in q.card.styleSheet())
    ok(f"테마 '{name}' — 막대 안에 글자를 쓰지 않는다(가득 차면 안 읽혔다)", not q.bar.isTextVisible())
    q.close()
theme.set_theme("light")

print("[2] 받기 — 받는 동안 진행을 알린다(updater.download)")


class _Resp:
    status_code = 200

    def __init__(self, n_chunks, size=1 << 16, length=True):
        self.n, self.size = n_chunks, size
        self.headers = {"Content-Length": str(n_chunks * size)} if length else {}

    def iter_content(self, chunk_size=0):
        for _ in range(self.n):
            yield b"x" * self.size


_get = updater.requests.get
CALLS = []
updater.requests.get = lambda *a, **k: _Resp(20)            # 1.25MB
path = updater.download("https://x/asset", progress=lambda g_, t_: CALLS.append((g_, t_)))
ok("처음(0)부터 끝(전체)까지 알린다", CALLS[0] == (0, 20 * 65536) and CALLS[-1] == (20 * 65536, 20 * 65536)
   and len(CALLS) == 21, (CALLS[:2], CALLS[-1:], len(CALLS)))
os.remove(path)
CALLS.clear()
updater.requests.get = lambda *a, **k: _Resp(20, length=False)
path = updater.download("https://x/asset", progress=lambda g_, t_: CALLS.append((g_, t_)))
ok("크기를 모르면 전체를 0 으로", CALLS[-1] == (20 * 65536, 0))
os.remove(path)
boom = lambda g_, t_: 1 / 0                              # noqa: E731
path = updater.download("https://x/asset", progress=boom)
ok("화면 쪽이 탈나도 받기는 끝까지", os.path.getsize(path) == 20 * 65536)
os.remove(path)
updater.requests.get = _get

print("[3] 일정관리기 — 받는 동안 진행 창, 다 받으면 '바꾸는 중' 뒤 끝낸다")
_sd.StartupDialog.show_for = staticmethod(lambda *a, **k: None)
BOXES = []
QMessageBox.information = staticmethod(lambda *a, **k: BOXES.append(("info", a[2] if len(a) > 2 else "")))
QMessageBox.warning = staticmethod(lambda *a, **k: BOXES.append(("warning", a[2] if len(a) > 2 else "")))
QMessageBox.question = staticmethod(lambda *a, **k: BOXES.append(("question", "")))
google_client.GoogleAuth.is_connected = lambda self: False
sync.sync_now = lambda *a, **k: False
sheets.read_rows = lambda *a, **k: (1, [], [])
updater.check = lambda *a, **k: None
updater.is_frozen = lambda: True
from planner.main_window import MainWindow  # noqa: E402

w = MainWindow()
w.show()
pump(0.3)
STEPS = []


def fake_download(url, progress=None):
    for i in range(0, 11):
        progress(i * 5 * MB, 50 * MB)
        STEPS.append(i)
        time.sleep(0.03)
    fd, pth = tempfile.mkstemp()
    os.close(fd)
    return pth


APPLIED = []
updater.download = fake_download
updater.apply_and_restart = lambda pth: APPLIED.append(pth)
EXITS = []
_real_exit = os._exit
os._exit = lambda code: EXITS.append(code)
w._shutdown = lambda: None
crashlog.clean_exit = lambda *a, **k: None
crashlog.shutdown = lambda *a, **k: None
REL = {"version": "9.9.9", "asset_url": "https://x/asset", "notes": ""}
seen_pct = []
w.sig_upd_progress.connect(lambda g_, t_: seen_pct.append(w._upd_prog.bar.value()))
w._auto_updating = True
w._begin_update(REL, manual=False)
ok("받기 시작하면 바로 진행 창", w._upd_prog is not None and w._upd_prog.isVisible()
   and w._upd_prog.state in ("download", "apply"))
for _ in range(80):
    pump(0.05)
    if EXITS:
        break
ok("받는 동안 막대가 올라간다", len(seen_pct) >= 2 and seen_pct == sorted(seen_pct) and max(seen_pct) == 100,
   seen_pct)
ok("다 받으면 바꾸는 중을 보여 준 뒤 끝낸다", APPLIED and EXITS == [0] and w._upd_prog.state == "apply",
   (APPLIED, EXITS, w._upd_prog.state))
mark = json.loads((config.base_dir() / "update_resume.json").read_text(encoding="utf-8"))
ok("새 판에 '업데이트 완료' 를 넘길 표시(바꾸려는 판)", mark.get("to") == "9.9.9"
   and mark.get("from") == config.APP_VERSION, mark)
ok("묻는 창은 하나도 없다", not BOXES, BOXES)

print("[4] 받다 실패하면 — 진행 창에 까닭(자동) · 알림 창(직접 누름)")
EXITS.clear()
APPLIED.clear()


def bad_download(url, progress=None):
    progress(1 * MB, 50 * MB)
    raise RuntimeError("다운로드 중 연결이 끊겼습니다: 시험")


updater.download = bad_download
TOASTS = []
w.sig_toast.connect(lambda t, m: TOASTS.append(m))
w._auto_updating = True
w._begin_update(REL, manual=False)
pump(0.6)
ok("자동 — 진행 창에 까닭을 보여 주고(저절로 닫힘) 묻지 않는다",
   w._upd_prog.state == "fail" and "연결이 끊겼습니다" in w._upd_prog.lbl_msg.text()
   and w._upd_prog.isVisible() and not BOXES and not EXITS, (w._upd_prog.state, BOXES))
ok("실패하면 다음 확인을 막지 않는다", w._auto_updating is False)
w._auto_updating = True
w._begin_update(REL, manual=True)
pump(0.6)
ok("직접 누른 것 — 진행 창을 닫고 예전처럼 알림 창", not w._upd_prog.isVisible()
   and BOXES and BOXES[-1][0] == "warning" and "연결이 끊겼습니다" in BOXES[-1][1], BOXES)
BOXES.clear()

print("[5] 이미 받는 중에 [업데이트 확인] — 진행 창을 다시 앞으로")
w._upd_prog.downloading()
w._upd_prog.hide()
w._auto_updating = True
w.check_update(manual=True)
ok("진행 창이 다시 보인다", w._upd_prog.isVisible())
w._auto_updating = False
w._upd_prog.close()

print("[6] 새 판이 켜지면 — '업데이트 완료' (누르면 변경 이력)")
_ver = config.APP_VERSION
config.APP_VERSION = "1.26.2"
updater.mark_resume(tray=False, to="v1.27.0")
config.APP_VERSION = "1.27.0"
r = updater.take_resume()
ok("표시를 읽는다(한 번 읽으면 지운다)", r.get("to") == "1.27.0" and updater.take_resume() == {}, r)
ok("바꾸려던 판으로 켜졌으면 완료", updater.finished_update(r) == "1.27.0")
config.APP_VERSION = "1.26.2"
ok("바꾸지 못하고 옛 판으로 켜졌으면(되돌림) 완료라 하지 않는다", updater.finished_update(r, "1.27.0") == "")
# 지난번에 켠 판을 기억한다 — 표시(to)를 모르던 옛 판(v1.26.2)이 바꿔 준 첫 업데이트도 '완료'
(config.base_dir() / "last_version.json").unlink(missing_ok=True)
ok("처음 켠 판은 지난 판이 없다", updater.note_run_version() == "")
ok("다시 켜면 지난번 판", updater.note_run_version() == "1.26.2")
config.APP_VERSION = "1.27.0"
prev = updater.note_run_version()
ok("판이 올라가면 지난 판(1.26.2) → 완료", prev == "1.26.2" and updater.finished_update({}, prev) == "1.27.0")
ok("같은 판으로 다시 켜면 완료가 아니다", updater.finished_update({}, updater.note_run_version()) == "")
config.APP_VERSION = "1.26.2"
ok("판이 내려가면(되돌림) 완료가 아니다", updater.finished_update({}, "1.27.0") == "")
_ji = updater.just_installed
updater.just_installed = lambda window_sec=600: True
config.APP_VERSION = "1.27.0"
ok("기록이 없는 첫 판인데 방금 배치가 깔았으면 완료", updater.finished_update({}, "") == "1.27.0")
updater.just_installed = lambda window_sec=600: False
ok("기록도 없고 배치가 깐 것도 아니면(처음 설치) 조용히", updater.finished_update({}, "") == "")
updater.just_installed = _ji
config.APP_VERSION = _ver
ok("15분이 지난 표시는 버린다", (lambda: (
    (config.base_dir() / "update_resume.json").write_text(json.dumps({"tray": True, "at": time.time() - 2000,
                                                                       "to": "1.27.0"}), encoding="utf-8"),
    updater.take_resume() == {})[1])())
OPENED = []
w.open_changelog = lambda: OPENED.append(1)
w.show_update_done("1.27.0")
pump(0.2)
d = w._upd_done
ok("완료 창 — '새 버전 v1.27.0 으로 바뀌었습니다'", d.isVisible() and d.state == "done" and "v1.27.0" in d.lbl_msg.text())
from PySide6.QtTest import QTest  # noqa: E402
QTest.mouseClick(d, Qt.LeftButton)
pump(0.2)
ok("누르면 변경 이력을 열고 닫힌다", OPENED == [1] and not d.isVisible(), OPENED)
src = inspect.getsource(__import__("planner.app", fromlist=["main"]).main)
ok("켤 때 — 업데이트로 켜졌으면 완료 창(app.main)", "updater.take_resume()" in src
   and "updater.finished_update(resume, updater.note_run_version())" in src and "show_update_done" in src)
ok("업데이트로 켜질 때 트레이였으면 트레이로(그대로)", 'resume.get("tray")' in src)

os._exit = _real_exit
w.hide()
print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
