"""대시보드(v1.23) — 플로우 첫 화면처럼, 오늘 브리핑·이번 주·다음 주 요약을 늘 펼쳐 둔다.

지점장 요청: "일정/할일 부분을 대시보드로. 주간요약을 누르면 나오는 브리핑을 넣고,
추가로 다음주 요약까지. 할일 추가 버튼은 따로."
그리고 같은 판에 고친 것 — 지난 기록에 나온 오류 셋(캘린더 단추·고객정보 끌어내기·
메모리 재기)도 여기서 본다.
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
from datetime import date, datetime, time as dtime, timedelta

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QFont, QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from planner import config, dashboard, google_client, sheets, sync, theme, weekly  # noqa: E402
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

from planner.google_client import CalEvent, GoogleTask  # noqa: E402
from planner.main_window import MainWindow  # noqa: E402
from planner.models import TodoItem  # noqa: E402
from planner.sheets import CustomerRow  # noqa: E402


def pump(n=10, sl=0.0):
    for _ in range(n):
        app.processEvents()
        if sl:
            time.sleep(sl)


def settle():
    time.sleep(0.15)
    pump(10)


def plain(tb):
    return tb.toPlainText()


T = date.today()
NMON, NSUN = weekly.week_range(T + timedelta(days=7))
MON, SUN = weekly.week_range(T)


def ev(d, hh, s):
    return CalEvent(start=datetime.combine(d, dtime(hh, 0)), has_time=True, summary=s)


def row(n, **kw):
    cr = CustomerRow(row=n, total="1,000,000", center="", accident="")
    cr.values.update(kw)
    return cr


def fmt(d):
    return f"{d.year}. {d.month}. {d.day}"


w = MainWindow()
w.resize(1846, 920)
w.show()
pump(10)

print("[1] 첫 화면이 대시보드")
ok("메뉴 첫 줄 이름이 '대시보드'", w.tabs.tabText(0) == "대시보드", w.tabs.tabText(0))
ok("그 화면이 대시보드(예전 일정 / 할일 자리)", w.tabs.widget(0) is w.tab_main)
ok("메뉴 아이콘도 따로(바둑판)", __import__("planner.navicons", fromlist=["x"]).for_tab("대시보드") == "grid")
w.tabs.setCurrentWidget(w.tab_main)
pump()
ok("제목줄은 인사말", w.lbl_page.text().startswith("안녕하세요!"), w.lbl_page.text())
w.tabs.setCurrentWidget(w.tab_cust)
pump()
ok("다른 화면은 메뉴 이름", w.lbl_page.text() == "고객관리", w.lbl_page.text())
w.tabs.setCurrentWidget(w.tab_main)
pump()
cards = [w.card_todo, w.card_brief, w.card_sched, w.card_this, w.card_next]
ok("카드 5장", all(c.isVisible() for c in cards))
ok("카드 제목", [c.lbl_title.text().split()[0] for c in cards]
   == ["내", "오늘", w.lbl_week.text().split()[0], "이번", "다음"],
   [c.lbl_title.text() for c in cards])
ok("일정·할일 표는 그대로 카드 안에", w.card_todo.isAncestorOf(w.tbl_todo)
   and w.card_sched.isAncestorOf(w.tbl_week))
ok("[주간 요약]·[새로고침] 도 그대로", w.tab_main.isAncestorOf(w.btn_weekly)
   and w.tab_main.isAncestorOf(w.btn_fetch))

print("\n[2] [＋ 할일 추가] 는 따로 — 할일 카드 머리에")
ok("채운 주 단추", w.btn_todo_add.objectName() == "dashprimary" and "할일 추가" in w.btn_todo_add.text())
ok("할일 카드 안에", w.card_todo.isAncestorOf(w.btn_todo_add))
called = []
w.on_todo_add = lambda: called.append(1)
w.btn_todo_add.click()
ok("누르면 할일 추가", called == [1])

print("\n[3] 카드 내용 — 오늘 브리핑 · 이번 주 요약 · 다음 주 요약")
w.cal_events = [ev(T, 10, "오늘 상담"), ev(NMON, 9, "다음주 월간 보고"),
                ev(NMON + timedelta(days=2), 15, "다음주 계약 미팅")]
w.todos = [TodoItem(title="오늘 할 일", run_date=T),
           TodoItem(title="다음주 마감 서류", run_date=NMON + timedelta(days=1)),
           TodoItem(title="다 한 일", run_date=NMON, done=True)]
w.gtasks = [GoogleTask(id="g1", list_id="L", title="구글 다음주 할일", due=NMON + timedelta(days=3),
                       has_due=True)]
w.sheet_rows = [row(2, customer="이번주출고", finance="현대캐피탈", model="그랜저",
                    deliver_date=fmt(T), contract_date=fmt(T - timedelta(days=30)), status="출고"),
                row(3, customer="다음주출고", finance="KB캐피탈", model="카니발",
                    deliver_date=fmt(NMON + timedelta(days=2)),
                    contract_date=fmt(T - timedelta(days=10)), status="발주")]
w.refresh_calendar()
w.refresh_todo()
settle()
b, wk, nx = plain(w.txt_dash_brief), plain(w.txt_dash_week), plain(w.txt_dash_next)
ok("브리핑에 오늘 일정", "오늘 상담" in b, b[:120])
ok("브리핑 카드 머리에 건수", "오늘 일정" in w.card_brief.lbl_count.text(), w.card_brief.lbl_count.text())
ok("이번 주 요약 = 주간 요약 내용", "이번 주 출고" in wk and "이번주출고" in wk, wk[:160])
ok("이번 주 카드 머리에 기간", w.card_this.lbl_count.text() == f"{MON:%m/%d} ~ {SUN:%m/%d}",
   w.card_this.lbl_count.text())
ok("다음 주 요약 — 다음 주 일정", "다음 주 일정" in nx and "다음주 월간 보고" in nx
   and "다음주 계약 미팅" in nx and "오늘 상담" not in nx, nx[:200])
ok("다음 주 요약 — 할일(로컬 + 구글)", "다음주 마감 서류" in nx and "구글 다음주 할일" in nx
   and "오늘 할 일" not in nx and "다 한 일" not in nx)
ok("다음 주 요약 — 출고 예정", "다음 주 출고 예정" in nx and "다음주출고" in nx and "이번주출고" not in nx)
ok("다음 주 요약은 진행 중·만기를 되풀이하지 않는다", "진행 중" not in nx and "만기" not in nx)
ok("다음 주 카드 머리에 기간", w.card_next.lbl_count.text() == f"{NMON:%m/%d} ~ {NSUN:%m/%d}")
ok("할일 카드에 건수", w.card_todo.lbl_count.text() == f"{w.tbl_todo.rowCount()}건")

print("\n[4] 바뀌면 다시 그린다 · 시트를 못 읽었으면 안내")
w.todos.append(TodoItem(title="방금 넣은 다음주 일", run_date=NMON + timedelta(days=4)))
w.refresh_todo()
settle()
ok("할일을 고치면 다음 주 카드도", "방금 넣은 다음주 일" in plain(w.txt_dash_next))
n0 = []
_orig = w._paint_dashboard
w._paint_dashboard = lambda: (n0.append(1), _orig())
w._dash_timer.timeout.disconnect()
w._dash_timer.timeout.connect(w._paint_dashboard)
for _ in range(5):
    w.refresh_calendar()
    w.refresh_todo()
settle()
ok("한꺼번에 여러 번 바뀌어도 한 번만 그린다", n0 == [1], n0)
w.sheet_rows = []
w.refresh_dashboard()
settle()
ok("시트를 못 읽었으면 이번 주 카드에 안내", "시트를 읽은 뒤" in plain(w.txt_dash_week))
ok("다음 주 카드는 일정·할일은 보여 주고 시트 부분만 안내",
   "다음 주 일정" in plain(w.txt_dash_next) and "시트를 읽은 뒤" in plain(w.txt_dash_next))

print("\n[5] 복사 단추 — 카톡에 붙여 넣을 글")
w.sheet_rows = [row(3, customer="다음주출고", finance="KB캐피탈", model="카니발",
                    deliver_date=fmt(NMON + timedelta(days=2)),
                    contract_date=fmt(T - timedelta(days=10)), status="발주")]
w._copy_dash("next")
clip = QGuiApplication.clipboard().text()
ok("다음 주 요약 복사", "다음 주 요약" in clip and "다음주출고" in clip and "[다음 주 일정]" in clip,
   clip[:160])
w._copy_dash("brief")
ok("브리핑 복사", "오늘" in QGuiApplication.clipboard().text())
w._copy_dash("week")
ok("이번 주 요약 복사", "주간 요약" in QGuiApplication.clipboard().text())

print("\n[6] 좁은 창 — 카드를 한 줄에 하나씩")
ok("넓으면 2줄 배치", w.dash_grid.wide)
w.dash_grid.relayout(800)
ok("좁으면 1열", not w.dash_grid.wide)
w.dash_grid.relayout(1600)
ok("다시 넓히면 2줄", w.dash_grid.wide)
pos = [w.dash_grid._grid.getItemPosition(w.dash_grid._grid.indexOf(c)) for c in cards]
ok("위: 할일(2칸)·브리핑 / 아래: 일정·이번 주·다음 주",
   pos == [(0, 0, 1, 2), (0, 2, 1, 1), (1, 0, 1, 1), (1, 1, 1, 1), (1, 2, 1, 1)], pos)

print("\n[7] 바로가기 — 누르면 그 화면")
names = [t.text() for t in w.dash_tiles]
ok("바로가기 6개", names == ["캘린더", "고객관리", "고객정보", "자료검색", "멘트복사", "수당계산기"], names)
w.dash_tiles[3].click()
pump()
ok("자료검색으로", w.tabs.currentWidget() is w.tab_kb)
w.dash_tiles[1].click()
pump()
ok("고객관리로", w.tabs.currentWidget() is w.tab_cust)
w.tabs.setCurrentWidget(w.tab_main)

print("\n[8] 옛 메뉴 순서('일정 / 할일')도 대시보드로 이어진다")
w.settings.tab_order = ["자료검색", "일정 / 할일", "고객관리", "고객정보", "멘트복사", "수당계산기", "PC 알람"]
w._save_settings()
w2 = MainWindow()
pump()
ok("저장된 순서 그대로(대시보드가 두 번째)",
   [w2.tabs.tabText(i) for i in range(3)] == ["자료검색", "대시보드", "고객관리"],
   [w2.tabs.tabText(i) for i in range(w2.tabs.count())])
w2.deleteLater()

print("\n[9] 인사말")
ok("아침", dashboard.greeting(datetime(2026, 1, 1, 8)) == "안녕하세요! 좋은 아침이에요.")
ok("오후", "오후" in dashboard.greeting(datetime(2026, 1, 1, 15)))
ok("저녁", "수고" in dashboard.greeting(datetime(2026, 1, 1, 21)))

print("\n[10] 세 테마에서 그려진다")
for t in theme.THEME_ORDER:
    w.settings.theme = t
    w.apply_theme()
    settle()
    q = theme.qss()
    ok(f"{t}: 카드·주 단추 규칙", "QFrame#card" in q and "QPushButton#dashprimary" in q)
    ok(f"{t}: 브리핑이 그려진다", bool(plain(w.txt_dash_brief).strip()))
w.settings.theme = "light"
w.apply_theme()

print("\n[11] 지난 기록의 오류 — 캘린더 단추 · 고객정보 끌어내기 · 메모리 재기")
opened = []
w.gauth.is_connected = lambda: True


class _Cal:
    def __init__(self, *a, **k):
        pass

    def show(self):
        opened.append("show")

    def raise_(self):
        pass

    def activateWindow(self):
        pass

    def goto_date(self, d):
        opened.append(d)


import planner.main_window as _mw  # noqa: E402
_real_cal = _mw.CalendarWindow
_mw.CalendarWindow = _Cal
w._cal_win = None
w.btn_calendar.click()          # 예전: 'bool' object has no attribute 'year'
ok("[캘린더] 단추가 날짜 대신 False 를 넘기지 않는다", opened == ["show"], opened)
w.open_calendar(False)
ok("open_calendar 가 날짜가 아닌 것은 무시한다", opened == ["show", "show"], opened)
w.open_calendar(T)
ok("날짜를 주면 그 날로", opened[-1] == T)
_mw.CalendarWindow = _real_cal
w.gauth.is_connected = lambda: False

from planner.customer_files_tab import _FileTable  # noqa: E402
ft = _FileTable(2, lambda: [])
pm = ft._drag_pixmap()
ok("고객정보 끌어내기 그림을 만든다(예전엔 SP_FileIcon 오류)", not pm.isNull())
import planner.customer_files_tab as _cft  # noqa: E402
_execs = []
_real_drag = _cft.QDrag


class _Drag(_real_drag):
    def exec(self, *a, **k):        # noqa: A003
        _execs.append(self.mimeData().urls())
        return Qt.CopyAction


_cft.QDrag = _Drag
_tmpf = os.path.join(tempfile.mkdtemp(), "서류.pdf")
with open(_tmpf, "wb") as f:
    f.write(b"%PDF-1.4\n")
ft._external_drag([_tmpf])
_cft.QDrag = _real_drag
ok("창 밖으로 끌어내기가 끝까지 간다(카카오톡에 놓을 수 있게)",
   len(_execs) == 1 and _execs[0] and _execs[0][0].toLocalFile() == _tmpf, _execs)
ok("startDrag 도 같은 그림 함수", "_drag_pixmap()" in inspect.getsource(_FileTable.startDrag))

from planner import crashlog  # noqa: E402
ok("감시 스레드는 ctypes 를 부르지 않는다(값만 읽는다)",
   "_mem_now()" in inspect.getsource(crashlog._watch_loop)
   and "_mem_bytes()" not in inspect.getsource(crashlog._watch_loop))
ok("윈도에서는 화면 스레드가 잰 값을 쓴다",
   "_mem_last if sys.platform == \"win32\"" in inspect.getsource(crashlog._mem_now))
ok("구조체·함수는 한 번만 만든다(_win_mem)", "if _win_mem is None:" in inspect.getsource(crashlog._mem_bytes))
ok("남의 kernel32 설정을 바꾸지 않는다(제 것 WinDLL)",
   'ctypes.WinDLL("kernel32")' in inspect.getsource(crashlog._mem_bytes)
   and "ctypes.windll.kernel32" not in inspect.getsource(crashlog._mem_bytes))
ok("화면 스레드 박동에서 30초마다 잰다", "sample_memory()" in inspect.getsource(crashlog.start_watchdog))
from planner import kb_tab  # noqa: E402
src = inspect.getsource(kb_tab.KbView.open_attachment)
ok("크게 보기는 exec 안에서 지워지지 않는다(닫은 뒤 deleteLater)",
   "setAttribute(Qt.WA_DeleteOnClose, False)" in src and "dlg.deleteLater()" in src)
ok("[이름 바꾸기] 단추도 False 를 넘기지 않는다",
   "lambda: self.rename_attachment()" in inspect.getsource(kb_tab.KbEditDialog))

print("\n[12] 시작 화면에서 다음 주로 넘기면 제목도 '다음 주'(예전엔 늘 '이번 주 출고')")
from planner.startup_dialog import StartupDialog  # noqa: E402
sd = StartupDialog("", "", w.sheet_rows, T)
sd._move(+1)
ok("다음 주로 넘기면 '다음 주 출고 예정'", "다음 주 출고" in sd.txt_weekly.toPlainText()
   and "이번 주 출고" not in sd.txt_weekly.toPlainText(), sd.txt_weekly.toPlainText()[:80])
sd._move(-1)
ok("돌아오면 '이번 주 출고'", "이번 주 출고" in sd.txt_weekly.toPlainText())
sd._move(-1)
ok("지난 주는 '지난 주 출고'", "지난 주 출고" in sd.txt_weekly.toPlainText())
sd.reject()
ok("주 이름", (weekly.week_word(T, T), weekly.week_word(T + timedelta(days=7), T),
              weekly.week_word(T - timedelta(days=7), T), weekly.week_word(T + timedelta(days=21), T))
   == ("이번 주", "다음 주", "지난 주", "그 주"))

print("\n[13] 켤 때 자동 업데이트 — 묻지 않고, 같은 판 두 번 실패하면 그만")
from PySide6.QtWidgets import QMessageBox  # noqa: E402
from planner import updater  # noqa: E402
asked, told, started = [], [], []
_q, _i = QMessageBox.question, QMessageBox.information
QMessageBox.question = staticmethod(lambda *a, **k: asked.append(a) or QMessageBox.No)
QMessageBox.information = staticmethod(lambda *a, **k: told.append(a))
_frozen, _att, _note = updater.is_frozen, updater.attempts, updater.note_attempt
updater.is_frozen = lambda: True
tries = {"n": 0}
updater.attempts = lambda v: tries["n"]
updater.note_attempt = lambda v: tries.__setitem__("n", tries["n"] + 1)
w._start_update = lambda res, manual: started.append((res["version"], manual))
w._update_failed = ""
res = {"version": "v9.9.9", "asset_url": "x", "notes": ""}
w._on_update_checked(res, "", False)
ok("켤 때는 묻지 않고 바로 받는다", started == [("v9.9.9", False)] and asked == [], (started, asked))
ok("시도를 센다", tries["n"] == 1)
w._on_update_checked(res, "", False)
ok("두 번째도 한다", len(started) == 2 and tries["n"] == 2)
w._on_update_checked(res, "", False)
ok("같은 판 두 번 실패 뒤엔 그만(켤 때마다 꺼지지 않게)", len(started) == 2, started)
ok("그만둘 때 한 번 알린다", len(told) == 1)
w._on_update_checked(res, "", False)
ok("알림은 한 번만", len(told) == 1)
tries["n"] = 0
w._update_failed = "missing"
w._on_update_checked(res, "", False)
ok("지난 업데이트가 실패했다고 알린 판에서는 자동으로 다시 안 한다", len(started) == 2)
w._update_failed = ""
w._on_update_checked(res, "", True)
ok("[업데이트 확인](직접 누름)은 물어본다", len(asked) == 1 and len(started) == 2)
w._on_update_checked(None, "연결 안 됨", False)
ok("켤 때 확인이 실패해도 창을 띄우지 않는다", len(told) == 1)
QMessageBox.question, QMessageBox.information = _q, _i
updater.is_frozen, updater.attempts, updater.note_attempt = _frozen, _att, _note
src_up = inspect.getsource(MainWindow._on_update_checked)
ok("업데이트를 걸면 곧바로 끝낸다(마무리 정리에서 멈추지 않게)",
   "os._exit(0)" in src_up and "crashlog.shutdown()" in src_up)

print("\n[14] 남아 있는 옛 판 — 방금 깔린 새 판이 넘겨받는다")
from planner import app as _app  # noqa: E402
_ji, _ko, _fz = updater.just_installed, updater.kill_other_instances, updater.is_frozen
kills = []
updater.is_frozen = lambda: True
updater.kill_other_instances = lambda: kills.append(1) or 1
updater.just_installed = lambda: True
ok("대답 없는(옛) 판이 남아 있으면 끝내고 뜬다", _app._take_over_after_update("") and kills == [1])
ok("더 낮은 판이 남아 있어도", _app._take_over_after_update("1.0.0") and len(kills) == 2)
ok("같은 판이면(그냥 두 번 실행) 넘겨받지 않는다",
   not _app._take_over_after_update(config.APP_VERSION) and len(kills) == 2)
updater.just_installed = lambda: False
ok("방금 깔린 게 아니면 예전처럼 있는 창만 띄운다", not _app._take_over_after_update("")
   and len(kills) == 2)
updater.just_installed, updater.kill_other_instances, updater.is_frozen = _ji, _ko, _fz
msrc = inspect.getsource(_app.main)
ok("대답에 판 번호를 싣는다", 'f"ok {config.APP_VERSION}' in msrc)
ok("끝낼 때 Qt 문구 처리기를 먼저 뗀다", "aboutToQuit.connect(crashlog.remove_qt_handler)" in msrc)
ok("마무리 정리 없이 끝낸다(os._exit)", "os._exit(rc)" in msrc and "crashlog.shutdown()" in msrc)

w.hide()
print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
