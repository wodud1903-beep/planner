"""알람 창 — 언제나 화면 안에 뜨는지, [✕]·끌기로 꼭 닫을 수 있는지.

예전 버그: 쌓는 칸 번호를 알람마다 올리기만 하고 닫아도 안 줄여서, 혼자 뜬
알람도 화면 아래 밖에 떠 [확인] 을 못 눌렀다(강제종료밖에 없었다).

창을 실제로 띄워 본다. 작은 화면에서 돌려 보면 더 확실하다:
    Xvfb :98 -screen 0 1366x768x24 &  DISPLAY=:98 python tools/verify/verify_alarm.py
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

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from planner import alarm_window  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name
          + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


app = QApplication.instance() or QApplication([])
QApplication.beep = staticmethod(lambda: None)      # 검사 중엔 소리 없이


def pump(n=20):
    for _ in range(n):
        app.processEvents()
        time.sleep(0.01)


def geo():
    return QGuiApplication.primaryScreen().availableGeometry()


def inside(r: QRect) -> bool:
    return geo().contains(r)


def gr(widget) -> QRect:
    """위젯의 화면 좌표 사각형."""
    return QRect(widget.mapToGlobal(QPoint(0, 0)), widget.size())


def all_visible_ok(ws):
    bad = []
    for i, w in enumerate(ws):
        if not (inside(w.frameGeometry()) and inside(gr(w.btn_ok)) and inside(gr(w.btn_x))):
            bad.append((i, w.frameGeometry().getRect()))
    return bad


MEMO = "\n".join(f"메모 {i}줄 — 고객 연락 확인" for i in range(8))
g = geo()
print(f"화면 작업 영역 {g.width()}×{g.height()}")

print("\n[1] 알람 하나 — 위 가운데, 확인·✕ 가 화면 안")
w1 = alarm_window.popup("고객 전화", MEMO)
pump()
ok("창이 화면 안", inside(w1.frameGeometry()), w1.frameGeometry().getRect())
ok("확인 단추가 화면 안", inside(gr(w1.btn_ok)))
ok("✕ 단추가 화면 안", inside(gr(w1.btn_x)))
ok("맨 위 칸에 뜬다", w1.y() <= g.top() + alarm_window._TOP + 1, w1.y())

print("\n[2] 옛 버그 — 옛 호출처럼 칸 번호 4 를 줘도 맨 위에 뜬다")
w1.close()
pump()
w2 = alarm_window.popup("두 번째", MEMO, 4)
pump()
ok("칸 번호와 상관없이 맨 위", w2.y() <= g.top() + alarm_window._TOP + 1, w2.y())
w2.close()
pump()

print("\n[3] 알람 일곱 개가 한꺼번에 — 전부 화면 안")
ws = [alarm_window.popup(f"알람 {i}", MEMO) for i in range(7)]
pump()
bad = all_visible_ok(ws)
ok("일곱 개 모두 창·확인·✕ 가 화면 안", not bad, bad)
ok("첫 창은 맨 위", ws[0].y() <= g.top() + alarm_window._TOP + 1)

print("\n[4] 하나 닫으면 남은 창이 위로 당겨진다")
y_before = ws[1].y()
ws[0].close()
pump()
ok("두 번째 창이 맨 위로", ws[1].y() < y_before and ws[1].y() <= g.top() + alarm_window._TOP + 1,
   f"{y_before} → {ws[1].y()}")
ok("남은 창 모두 화면 안", not all_visible_ok(ws[1:]))

print("\n[5] ✕ 를 누르면 닫힌다")
n = len(alarm_window._open_alarms)
ws[1].btn_x.click()
pump()
ok("✕ 로 닫힘", not ws[1].isVisible() and len(alarm_window._open_alarms) == n - 1)
alarm_window.close_all()
pump()
ok("모두 닫기", not alarm_window._open_alarms)

print("\n[6] 메모가 아주 길어도 창 키가 화면보다 작고 확인이 보인다")
long_memo = "\n".join(f"{i} 줄" for i in range(400))
for siren in (True, False):
    w = alarm_window.popup("긴 메모", long_memo, siren=siren)
    pump()
    ok(f"{'알람' if siren else '안내'}: 창이 화면 안", inside(w.frameGeometry()),
       f"키 {w.height()} / 화면 {g.height()}")
    ok(f"{'알람' if siren else '안내'}: 확인 단추가 화면 안", inside(gr(w.btn_ok)))
    w.close()
    pump()

print("\n[7] 위 막대를 끌면 옮겨지고, 화면 밖으로는 못 나간다")
w = alarm_window.popup("끌기", MEMO)
pump()


def mouse(target, kind, gpos: QPoint, btn=Qt.LeftButton):
    local = QPointF(target.mapFromGlobal(gpos))
    ev = QMouseEvent(kind, local, QPointF(gpos), btn,
                     btn if kind != QEvent.MouseButtonRelease else Qt.NoButton, Qt.NoModifier)
    QApplication.sendEvent(target, ev)


start = w.bar.mapToGlobal(QPoint(60, 15))
x0, y0 = w.x(), w.y()
mouse(w.bar, QEvent.MouseButtonPress, start)
mouse(w.bar, QEvent.MouseMove, start + QPoint(-40, 60))
mouse(w.bar, QEvent.MouseButtonRelease, start + QPoint(-40, 60))
pump()
ok("끈 만큼 옮겨진다", (w.x(), w.y()) == (x0 - 40, y0 + 60), (x0, y0, w.x(), w.y()))
mouse(w.bar, QEvent.MouseButtonPress, w.bar.mapToGlobal(QPoint(60, 15)))
far = QPoint(g.right() + 3000, g.bottom() + 3000)
mouse(w.bar, QEvent.MouseMove, far)
mouse(w.bar, QEvent.MouseButtonRelease, far)
pump()
ok("화면 밖으로 끌어도 안에 남는다", inside(w.frameGeometry()) and inside(gr(w.btn_ok)),
   w.frameGeometry().getRect())
w2 = alarm_window.popup("새 알람", MEMO)
pump()
ok("손으로 옮긴 창은 자동 정렬이 건드리지 않는다", w._moved and inside(w.frameGeometry()))
ok("새 알람은 맨 위", w2.y() <= g.top() + alarm_window._TOP + 1)
alarm_window.close_all()
pump()

print("\n[8] 5분 뒤 다시 — 다시 뜰 때도 화면 안")
ws = [alarm_window.popup(f"다시 {i}", MEMO) for i in range(4)]
pump()
last = ws[-1]
last._snooze()
pump()
ok("미루면 숨는다", not last.isVisible())
for w in ws[:-1]:
    w.close()
pump()
last._snooze_left = 1
last._snooze_tick()
pump()
ok("다시 뜬다", last.isVisible())
ok("다시 뜬 창이 화면 안 · 맨 위", inside(last.frameGeometry())
   and last.y() <= g.top() + alarm_window._TOP + 1, last.frameGeometry().getRect())
alarm_window.close_all()
pump()

print("\n[9] [보기] 단추가 있어도 확인이 화면 안")
w = alarm_window.popup("보기", MEMO, action=("열어 보기", lambda: None))
pump()
ok("단추 네 개가 모두 화면 안",
   all(inside(gr(b)) for b in (w.btn_copy, w.btn_act, w.btn_snooze, w.btn_ok)))
alarm_window.close_all()
pump()

print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
