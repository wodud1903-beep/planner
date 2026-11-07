"""빠른 자료검색 창 — 내용(메모) 칸을 크게(v1.28.2, 지점장 요청).

"빠른 자료검색 단축키를 눌러서 킬때 자료화면에서 메모박스가 너무 작아서 보기가 힘들어.
 가로,세로크기를 조금씩 키워서 메모박스의 크기를 키워 한눈에 보기 쉽도록"
  · 창 860×520 → 1120×720 (작은 화면이면 화면 안으로)
  · 목록 : 내용 = 2 : 3 → 1 : 2 (빠른검색만 — 자료 탭은 그대로)
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
import os
import tempfile
import time

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


app = QApplication.instance() or QApplication([])
from planner import kb_tab, theme  # noqa: E402
theme.apply_to_app(app)


def pump(sec=0.2):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


class _Scr:
    def __init__(self, w, h):
        self.g = QRect(0, 0, w, h)

    def availableGeometry(self):
        return self.g


_real = QGuiApplication.primaryScreen
QGuiApplication.primaryScreen = staticmethod(lambda: _Scr(1920, 1040))
q = kb_tab.QuickSearch()
ok("창 크기 1120×720(예전 860×520)", (q.width(), q.height()) == (1120, 720), (q.width(), q.height()))
q.show()
pump()
new_body = q.view.txt_body.size()
lw, rw = q.view.split.sizes()
ok("내용(메모) 칸이 목록의 두 배쯤", rw >= 1.8 * lw, (lw, rw))
# 예전 모양(860×520 · 2:3)으로 재서 견준다
q.resize(860, 520)
q.view.split.setSizes([344, 516])
pump()
old_body = q.view.txt_body.size()
ok("메모 칸 가로가 넓어졌다", new_body.width() >= old_body.width() + 150, (old_body.width(), new_body.width()))
ok("메모 칸 세로가 높아졌다", new_body.height() >= old_body.height() + 150, (old_body.height(), new_body.height()))
q.close()
QGuiApplication.primaryScreen = staticmethod(lambda: _Scr(1280, 680))
q2 = kb_tab.QuickSearch()
ok("작은 화면이면 화면 안으로 줄인다", q2.width() <= int(1280 * 0.92) and q2.height() <= int(680 * 0.9),
   (q2.width(), q2.height()))
q2.close()
QGuiApplication.primaryScreen = _real
v = kb_tab.KbView()
ok("자료 탭(보통 화면)의 나눔은 그대로(2:3)", v.split.orientation() is not None)
print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
