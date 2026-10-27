"""왼쪽 메뉴(v1.22) — 플로우처럼 모든 메뉴를 왼쪽에.

지점장 요청: "플로우처럼 메뉴를 모두 왼쪽에 넣어주고, 테마 톤을 밝고 연하게".
화면 자체는 예전 QTabWidget 그대로이고 탭 막대만 숨겼다. 메뉴가 탭과 늘 같은
순서·같은 선택을 가리키는지, 끌어 옮긴 순서가 남는지, 접기가 남는지 본다.
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
import os as _os
_os.chdir(_ROOT / "python")

import json
import os
import tempfile

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QFont, QIcon  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from planner import config, google_client, navicons, sheets, sync, theme  # noqa: E402
from planner import startup_dialog as _sd  # noqa: E402

_sd.StartupDialog.show_for = staticmethod(lambda *a, **k: None)

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name
          + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


app = QApplication.instance() or QApplication([])
_f = QFont("Malgun Gothic", 10)
_f.setWeight(QFont.DemiBold)
app.setFont(_f)
theme.apply_to_app(app)
config.set_account("tester@example.com")
google_client.GoogleAuth.is_connected = lambda self: False
sync.sync_now = lambda *a, **k: (False, "")
sheets.read_rows = lambda *a, **k: (1, [], [])

from planner.main_window import MainWindow  # noqa: E402


def pump(n=8):
    for _ in range(n):
        app.processEvents()


def tab_names(w):
    return [w.tabs.tabText(i) for i in range(w.tabs.count())]


def nav_texts(w):
    nav = w.sidebar.nav
    return [nav.item(i).text() for i in range(nav.count())]


w = MainWindow()
w.show()
pump()
side = w.sidebar
nav = side.nav

print("[1] 배치 — 왼쪽 메뉴 + 오른쪽 화면, 상단바·탭 막대는 없다")
ok("탭 막대는 숨겼다", not w.tabs.tabBar().isVisible())
ok("상단바가 없다", not hasattr(w, "_topbar"))
ok("메뉴 줄 = 탭 수", nav.count() == w.tabs.count() == 7, (nav.count(), w.tabs.count()))
ok("메뉴가 탭과 같은 순서·같은 이름", nav.names() == tab_names(w), nav.names())
ok("메뉴 글자도 탭 이름", nav_texts(w) == tab_names(w))
ok("메뉴마다 아이콘", all(not nav.item(i).icon().isNull() for i in range(nav.count())))
ok("탭마다 제 아이콘(기본 점이 아님)",
   all(navicons.for_tab(n) != "dot" for n in tab_names(w)),
   [n for n in tab_names(w) if navicons.for_tab(n) == "dot"])
for nm in ("lbl_account", "btn_ver", "chk_startup", "btn_settings", "btn_calendar"):
    ok(f"{nm} 은 왼쪽 메뉴에", side.isAncestorOf(getattr(w, nm)))
ok("버전 단추 글자", w.btn_ver.text() == f"v{config.APP_VERSION}", w.btn_ver.text())
ok("일정 화면의 단추 줄에서는 [설정]·[캘린더 열기] 가 빠졌다",
   not w.tab_main.isAncestorOf(w.btn_settings) and not w.tab_main.isAncestorOf(w.btn_calendar))
ok("[새로고침]·[주간 요약] 은 일정 화면에 그대로",
   w.tab_main.isAncestorOf(w.btn_fetch) and w.tab_main.isAncestorOf(w.btn_weekly))
ok("계정 줄에 앞 점(·)을 붙이지 않는다", "·" not in w.lbl_account.text())

print("\n[2] 메뉴를 누르면 그 화면으로, 제목줄도 바뀐다")
nav.setCurrentRow(3)
pump()
ok("고른 메뉴의 화면", w.tabs.currentIndex() == 3, w.tabs.currentIndex())
ok("제목줄 = 그 화면 이름", w.lbl_page.text() == w.tabs.tabText(3), w.lbl_page.text())
ok("오늘 날짜가 보인다", "월" in w.lbl_today.text() and "일" in w.lbl_today.text(),
   w.lbl_today.text())

print("\n[3] 코드가 화면을 바꿔도(캘린더 → '해당 고객으로 이동') 메뉴가 따라온다")
w.tabs.setCurrentWidget(w.tab_cust)
pump()
ok("메뉴 선택이 고객관리", nav.currentRow() == w.tabs.indexOf(w.tab_cust),
   (nav.currentRow(), w.tabs.indexOf(w.tab_cust)))
ok("제목줄도 고객관리", w.lbl_page.text() == "고객관리", w.lbl_page.text())
w.open_files_for("홍길동")
pump()
ok("고객정보로 건너가면 메뉴도", nav.item(nav.currentRow()).data(Qt.UserRole) == "고객정보")

print("\n[4] 메뉴를 끌어 옮기면 탭도 같은 순서로, 그리고 기억한다")
w.tabs.setCurrentWidget(w.tab_greet)
pump()
src = nav.names().index("자료검색")
nav.move_row(src, 0)
pump()
ok("탭 맨 앞이 자료검색", w.tabs.tabText(0) == "자료검색", tab_names(w))
ok("메뉴와 탭 순서가 같다", nav.names() == tab_names(w), (nav.names(), tab_names(w)))
ok("보던 화면은 그대로", w.tabs.currentWidget() is w.tab_greet)
ok("메뉴 선택도 보던 화면", nav.currentRow() == w.tabs.indexOf(w.tab_greet),
   (nav.currentRow(), w.tabs.indexOf(w.tab_greet)))
ok("설정에 순서가 남는다", w.settings.tab_order == tab_names(w), w.settings.tab_order)
order = tab_names(w)
w2 = MainWindow()
pump()
ok("다시 켜도 그 순서", tab_names(w2) == order, tab_names(w2))
ok("다시 켠 창의 메뉴도 그 순서", w2.sidebar.nav.names() == order, w2.sidebar.nav.names())
ok("고객정보는 여전히 고객관리 옆(위젯으로 찾는다)",
   abs(w2.tabs.indexOf(w2.tab_files) - w2.tabs.indexOf(w2.tab_cust)) == 1)
w2.hide()
w2.deleteLater()
pump()

print("\n[5] [＋ 할일 추가] — 어느 화면에서든 일정으로 가서 바로 적는다")
called = []
w.on_todo_add = lambda: called.append(w.tabs.currentWidget())
w.tabs.setCurrentWidget(w.tab_kb)
pump()
side.btn_primary.click()
pump()
ok("할일 추가를 불렀다", len(called) == 1)
ok("부를 때 이미 일정 화면", called and called[0] is w.tab_main)
ok("메뉴도 일정 / 할일", nav.item(nav.currentRow()).data(Qt.UserRole) == "일정 / 할일")

print("\n[6] 접기 — 아이콘만 남기고, 다시 켜도 기억한다")
wide = side.width()
side.btn_fold.click()
pump()
ok("좁아졌다", side.width() == side.W_SHUT < wide, (wide, side.width()))
ok("메뉴 글자를 숨기고 이름은 풍선 도움말로",
   all(t == "" for t in nav_texts(w))
   and all(nav.item(i).toolTip() == nav.item(i).data(Qt.UserRole) for i in range(nav.count())))
ok("계정·버전·시작 실행은 숨김",
   not w.lbl_account.isVisible() and not w.btn_ver.isVisible() and not w.chk_startup.isVisible())
ok("단추는 아이콘만", side.btn_primary.text() == "" and w.btn_settings.text() == "")
ok("접은 것을 설정에 남긴다", w.settings.side_collapsed is True)
cfg = [p for p in _pl.Path(os.environ["APPDATA"]).rglob("*.json")
       if "sideCollapsed" in p.read_text(encoding="utf-8", errors="replace")]
ok("설정 파일에 적혔다", any(json.loads(p.read_text(encoding="utf-8")).get("sideCollapsed")
                         for p in cfg), [str(p) for p in cfg])
w3 = MainWindow()
pump()
ok("다시 켜도 접힌 채", w3.sidebar.is_collapsed() and w3.sidebar.width() == side.W_SHUT)
ok("접힌 채 켜도 메뉴 글자 없음", all(t == "" for t in nav_texts(w3)))
w3.hide()
w3.deleteLater()
pump()
side.btn_fold.click()
pump()
ok("펼치면 원래 폭·글자", side.width() == side.W_OPEN and nav_texts(w) == tab_names(w))
ok("펼친 것도 남긴다", w.settings.side_collapsed is False)

print("\n[7] 테마를 바꿔도 메뉴가 그대로(아이콘만 새 색으로)")
w.tabs.setCurrentIndex(2)
pump()
for t in theme.THEME_ORDER:
    w.settings.theme = t
    w.apply_theme()
    pump()
    ok(f"{t}: 메뉴 그대로·선택 그대로",
       nav.names() == tab_names(w) and nav.currentRow() == 2, (t, nav.currentRow()))
w.settings.theme = "light"
w.apply_theme()

print("\n[8] 기능이 늘면 메뉴에 저절로 붙는다")
extra = QWidget()
w.tabs.addTab(extra, "새 기능")
w._sync_nav()
ok("새 탭이 메뉴 끝에", nav.count() == 8 and nav.names()[-1] == "새 기능")
ok("표에 없는 이름은 기본 아이콘", navicons.for_tab("새 기능") == "dot"
   and not nav.item(7).icon().isNull())
w.tabs.removeTab(w.tabs.indexOf(extra))
w._sync_nav()
ok("빼면 메뉴에서도 빠진다", nav.count() == 7)

print("\n[9] 아이콘 — 모두 그려진다")
for nm in navicons.NAMES:
    px = navicons.pixmap(nm, theme.c("text"), 20, 2.0)
    img = px.toImage()
    inked = any(img.pixelColor(x, y).alpha() > 0
                for x in range(0, img.width(), 2) for y in range(0, img.height(), 2))
    ok(f"{nm} 아이콘에 선이 있다", not px.isNull() and inked)
ic = navicons.icon("bell", theme.c("subtext"), theme.c("nav_sel_text"))
ok("고른 줄용 색이 따로 있다", ic.availableSizes(QIcon.Selected) != [])

print("\n[10] 왼쪽 메뉴의 글자가 세 테마에서 읽힌다")


def lum(h):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda v: v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4  # noqa: E731
    return .2126 * f(r) + .7152 * f(g) + .0722 * f(b)


def ratio(a, b):
    la, lb = lum(a), lum(b)
    return round((max(la, lb) + .05) / (min(la, lb) + .05), 2)


for t in theme.THEME_ORDER:
    P = theme.THEMES[t][1]
    for fg, bg, need, what in (
            ("topbar_text", "topbar", 7.0, "메뉴 글자"),
            ("subtext", "topbar", 4.5, "계정·작은 글씨"),
            ("subtext", "panel_bg", 4.5, "흐린 글자"),
            ("nav_sel_text", "select_bg", 4.5, "고른 메뉴 글자"),
            ("topbar_text", "btn_hover", 4.5, "마우스 올린 메뉴")):
        r = ratio(P[fg], P[bg])
        ok(f"{t}: {what} {need}:1", r >= need, r)
    for k in ("primary", "primary_hover"):
        r = ratio(theme.fill_text(), P[k])
        ok(f"{t}: [＋ 할일 추가]({k}) 흰 글자 4.5:1", r >= 4.5, r)
    ok(f"{t}: 고른 메뉴 배경이 메뉴 바탕과 다르다", P["select_bg"] != P["topbar"])
    theme.set_theme(t)
    q = theme.qss()
    ok(f"{t}: 스타일시트에 메뉴 규칙", "QFrame#sidebar" in q and "QListWidget#navlist" in q
       and "QTabWidget#pages::pane" in q and P["nav_sel_text"] in q)
theme.set_theme("light")

w.hide()
print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
