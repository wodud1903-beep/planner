"""메뉴 단축키 Ctrl+1 ~ Ctrl+9(v1.37).

지점장: "메인메뉴 대시보드/고객관리/고객정보 등 앱이 최상단에 켜져 있을 때 순서에 맞게 단축키를 누르면 화면이
옮겨지게 — 순서대로 컨트롤+1, 컨트롤+2 등으로 화면 전환, 메뉴의 우측에는 작은 글씨로 단축키 명을 기재."
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
tempfile.tempdir = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QWidget  # noqa: E402

app = QApplication.instance() or QApplication([])
_f = QFont("Malgun Gothic", 10)
_f.setWeight(QFont.DemiBold)
app.setFont(_f)

from planner import config, google_client, sheets, sidebar, sync, theme  # noqa: E402
from planner import startup_dialog as _sd  # noqa: E402

theme.apply_to_app(app)
_sd.StartupDialog.show_for = staticmethod(lambda *a, **k: None)
config.set_account("tester@example.com")
google_client.GoogleAuth.is_connected = lambda self: False
sync.sync_now = lambda *a, **k: (False, "")
sheets.read_rows = lambda *a, **k: (1, [], [])

from planner.main_window import MainWindow  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


def pump(sec=0.05):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


def press(widget, n):
    QTest.keyClick(widget, getattr(Qt, f"Key_{n}"), Qt.ControlModifier)
    pump()


def names(w):
    return [w.tabs.tabText(i) for i in range(w.tabs.count())]


w = MainWindow()
w.show()
w.activateWindow()
QTest.qWaitForWindowActive(w, 2000)
pump(0.2)
nav = w.sidebar.nav

print("[1] Ctrl+1 ~ Ctrl+9 — 메뉴 순서대로 화면")
seen = []
for n in range(1, 10):
    press(w, n)
    seen.append(w.tabs.currentIndex())
ok("Ctrl+N → N 번째 화면", seen == list(range(9)), seen)
ok("메뉴 선택 · 제목줄도 따라간다", nav.currentRow() == 8 and w.lbl_page.text() == names(w)[8], w.lbl_page.text())
press(w, 2)
ok("Ctrl+2 = 고객관리(지금 순서)", w.tabs.currentWidget() is w.tab_cust)
edit = w.findChild(QLineEdit)
if edit is not None and edit.isVisible():
    edit.setFocus()
    pump()
    press(edit, 1)
    ok("글자 칸에 있어도 먹는다", w.tabs.currentIndex() == 0)

print("[2] 메뉴를 끌어 순서를 바꾸면 단축키도 따라간다")
src = nav.names().index("카톡 매크로")
nav.move_row(src, 0)
pump()
press(w, 1)
ok("맨 앞으로 옮긴 '카톡 매크로' 가 Ctrl+1", w.tabs.currentWidget() is w.tab_macro, names(w))
press(w, 9)
ok("Ctrl+9 = 이제 맨 끝 메뉴", w.tabs.currentIndex() == 8 and names(w)[8] == "PC 알람", names(w))
nav.move_row(0, nav.count() - 1)
pump()

print("[3] 메뉴 오른쪽에 작은 회색 글씨")
ok("줄마다 글씨 'Ctrl+1' … 'Ctrl+9' · 10번째부터 없음",
   [sidebar.shortcut_text(i) for i in range(10)] == [f"Ctrl+{i}" for i in range(1, 10)] + [""])


def ink(row):
    """그 줄 오른쪽 끝(단축키 자리)에 바탕과 다른 점이 있나."""
    img = nav.viewport().grab().toImage()
    r = nav.visualItemRect(nav.item(row))
    bg = img.pixelColor(r.right() - 4, r.top() + 2)
    n = 0
    for x in range(r.right() - 48, r.right() - 10):
        for y in range(r.top() + 8, r.bottom() - 8):
            c = img.pixelColor(x, y)
            if abs(c.red() - bg.red()) + abs(c.green() - bg.green()) + abs(c.blue() - bg.blue()) > 60:
                n += 1
    return n


w.tabs.setCurrentIndex(0)
pump()
inks = [ink(i) for i in range(nav.count())]
ok("아홉 줄 모두 오른쪽에 글씨", all(v > 5 for v in inks), inks)
extra = QWidget()
w.tabs.addTab(extra, "새 기능")
w._sync_nav()
pump()
ok("10번째 메뉴에는 글씨가 없다", ink(9) == 0 and nav.item(9).toolTip() == "새 기능", ink(9))
press(w, 0)
ok("Ctrl+0 은 아무 일도 없다", w.tabs.currentIndex() == 0)
w.tabs.removeTab(w.tabs.indexOf(extra))
w._sync_nav()
pump()
w.sidebar.set_collapsed(True)
pump()
with_keys = nav.viewport().grab().toImage()
_dg = nav.itemDelegate()
from PySide6.QtWidgets import QStyledItemDelegate  # noqa: E402
_plain = QStyledItemDelegate(nav)
nav.setItemDelegate(_plain)
pump()
plain = nav.viewport().grab().toImage()
nav.setItemDelegate(_dg)
pump()
ok("접으면 글씨는 숨고(아이콘만 — 보통 메뉴와 똑같이 그려진다) 풍선 도움말에 '고객관리 (Ctrl+2)'",
   with_keys == plain and nav.item(1).toolTip() == "고객관리 (Ctrl+2)", nav.item(1).toolTip())
w.sidebar.set_collapsed(False)
pump()
for th in theme.THEME_ORDER:
    w.settings.theme = th
    w.apply_theme()
    pump()
    ok(f"{th}: 글씨가 보인다", all(v > 5 for v in (ink(i) for i in range(nav.count()))))
w.settings.theme = "light"
w.apply_theme()
pump()
nav.viewport().grab().save(str(_pl.Path(tempfile.gettempdir()) / "nav_keys.png"))

print("[4] 창 단축키 — 다른 창이 앞이면 안 먹는다")
w.tabs.setCurrentIndex(0)
dlg = QDialog(w)
dlg.setModal(True)
dlg.show()
dlg.activateWindow()
QTest.qWaitForWindowActive(dlg, 2000)
pump(0.1)
press(dlg, 3)
ok("고객 수정 같은 창이 떠 있으면 Ctrl+3 이 화면을 안 바꾼다", w.tabs.currentIndex() == 0, w.tabs.currentIndex())
dlg.close()
w.activateWindow()
QTest.qWaitForWindowActive(w, 2000)
pump(0.1)
press(w, 3)
ok("닫으면 다시 먹는다", w.tabs.currentIndex() == 2)
ok("단축키 아홉 개(창 단축키)", len(w._page_keys) == 9 and all(s.context() == Qt.WindowShortcut for s in w._page_keys))

print()
print(f"{len(FAIL)}건 실패" if FAIL else "전부 통과", flush=True)
os._exit(1 if FAIL else 0)
