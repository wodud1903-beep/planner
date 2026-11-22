"""v1.35 — 메뉴별 정리(지점장이 고른 것): 버그 B · 대시보드 D · 고객관리 C · 고객정보 I ·
멘트복사 M2 · 자료검색 K · 프로모션 P1 · 수당계산기 S · PC 알람 A.

화면마다 '예전엔 어땠고 이제 어떤가' 를 실제 위젯을 눌러 가며 본다. 가짜 자료만 쓴다.
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
from datetime import date, datetime, time as dtime, timedelta

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from planner import config, google_client, sheets, sync, theme, weekly  # noqa: E402
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


T = date.today()


def ev(d, hh, s):
    return CalEvent(start=datetime.combine(d, dtime(hh, 0)), has_time=True, summary=s)


def row(n, **kw):
    cr = CustomerRow(row=n, total="1,000,000", center="", accident="")
    cr.values.update(kw)
    return cr


def fmt(d):
    return f"{d.year}. {d.month}. {d.day}"


def href_for(w, target_kind, pred):
    """대시보드 카드 글 속 링크 중 대상이 맞는 것의 주소."""
    for k, (kind, what) in w._dash_hrefs.items():
        if kind == "open" and what and what[0] == target_kind and pred(what[1]):
            return QUrl("dash:" + k)
    return None


w = MainWindow()
w.resize(1536, 864)
w.show()
pump(10)
w.tabs.setCurrentWidget(w.tab_main)
pump()

# ---------------------------------------------------------------- B4
print("[B4] 요일은 한국어로 — 윈도에서 strftime('%a') 는 'Sat' 처럼 영어였다")
ok("kdow", [config.kdow(date(2026, 11, 22 + i)) for i in range(7)]
   == ["일", "월", "화", "수", "목", "금", "토"])
one = TodoItem(title="한 번 알람", run_date=date(2026, 11, 21), repeats=False)
ok("한 번만 울리는 알람 날짜", one.days_text() == "11-21(토)", one.days_text())
w.cal_events = [ev(T, 10, "요일 확인 일정")]
w.gtasks = [GoogleTask(id="gk", list_id="L", title="요일 확인 할일", due=T, has_due=True)]
w.refresh_calendar()
w.refresh_todo()
settle()
wk = w.tbl_week.item(0, 0).text()
ok("대시보드 일정 표", wk == f"{T:%m-%d}({config.kdow(T)})", wk)
cells = [w.tbl_todo.item(r, 1).text() for r in range(w.tbl_todo.rowCount())]
ok("대시보드 할일 표(구글 할일)", f"{T:%m-%d}({config.kdow(T)})" in cells, cells)
ok("영어 요일이 남지 않았다", not any(x in " ".join(cells + [wk])
                                    for x in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")))
from planner.calendar_window import AddEventDialog, EventCalendar  # noqa: E402
dlg = AddEventDialog(date(2026, 11, 21), [{"id": "c", "name": "내 캘린더", "primary": True}], w)
ok("일정 추가 창 제목", dlg.windowTitle().endswith("2026-11-21 (토)"), dlg.windowTitle())
dlg.deleteLater()

# ---------------------------------------------------------------- B5
print("\n[B5] 고객관리 요약 — '이번달 출고' 가 두 번 나오던 것")
w.sheet_rows = [row(2, customer="이번달고객", deliver_date=fmt(T), contract_date=fmt(T), status="출고")]
w._show_summary([("발주", "3"), ("이번달출고", "5")])
txt = w.lbl_cust_summary.text()
ok("시트 값이 있으면 한 번만(시트 값)", txt.count("이번달출고") == 1 and "이번달 출고" not in txt, txt[:200])
ok("수수료·지난달 대비는 그대로", "수수료" in txt)
w._show_summary([])
txt = w.lbl_cust_summary.text()
ok("시트 요약이 없으면 앱이 센 값", "이번달 출고" in txt and "1건" in txt, txt[:200])

# ---------------------------------------------------------------- D2
print("\n[D2] 구글 연결 — 잘 붙어 있으면 작은 점 하나")
w.gauth.is_connected = lambda: True
w.gauth.missing_scopes = lambda core_only=False: []
w.update_google_status()
ok("연결됨: 점만 보이고 글자는 없다", not w.lbl_gdot.isHidden() and w.lbl_status.text() == "",
   w.lbl_status.text())
ok("점에 마우스를 올리면 설명", "연결됨" in w.lbl_gdot.toolTip())
w.gauth.missing_scopes = lambda core_only=False: [config.SCOPE_LABELS and next(iter(config.SCOPE_LABELS))]
w.update_google_status()
ok("권한이 빠졌으면 점 대신 글자로 알린다", w.lbl_gdot.isHidden() and "권한 빠짐" in w.lbl_status.text())
w.gauth.is_connected = lambda: False
w.update_google_status()
ok("로그인 전: 점 없이 '로그인 필요'", w.lbl_gdot.isHidden() and "로그인 필요" in w.lbl_status.text())

# ---------------------------------------------------------------- D4
print("\n[D4] 내 할일 — 체크하면 완료 · 수정·삭제는 마우스를 올렸을 때만")
heads = [b.text() for b in w.card_todo.findChildren(QPushButton)]
ok("카드 머리에는 [＋ 할일 추가] 만", heads == [w.btn_todo_add.text()], heads)
ok("첫 칸 이름이 '완료'", w.tbl_todo.horizontalHeaderItem(0).text() == "완료")
w.gtasks = []
w.todos = [TodoItem(title="체크로 끝낼 일", run_date=T), TodoItem(title="남길 일", run_date=T),
           TodoItem(title="반복 일", run_date=T, repeats=True, weekdays="1234567")]
w.refresh_todo()
settle()
titles = lambda: [w.tbl_todo.item(r, 3).text() for r in range(w.tbl_todo.rowCount())]  # noqa: E731
r0 = titles().index("체크로 끝낼 일")
w.tbl_todo.item(r0, 0).setCheckState(Qt.Checked)
pump()
ok("체크하면 바로 지우지 않고 줄을 긋는다", "체크로 끝낼 일" in titles()
   and w.tbl_todo.item(r0, 3).font().strikeOut())
w.tbl_todo.item(r0, 0).setCheckState(Qt.Unchecked)
pump()
time.sleep(w.TODO_DONE_MS / 1000 + 0.3)
pump(20)
ok("그 사이 다시 누르면 취소", "체크로 끝낼 일" in titles() and not w.tbl_todo.item(r0, 3).font().strikeOut())
w.tbl_todo.item(titles().index("체크로 끝낼 일"), 0).setCheckState(Qt.Checked)
w.refresh_todo()          # 기다리는 동안 다시 그려도 체크는 남는다
pump()
r1 = titles().index("체크로 끝낼 일")
ok("기다리는 동안 다시 그려도 체크가 남는다", w.tbl_todo.item(r1, 0).checkState() == Qt.Checked)
w.tbl_todo.item(titles().index("반복 일"), 0).setCheckState(Qt.Checked)
time.sleep(w.TODO_DONE_MS / 1000 + 0.3)
pump(20)
ok("잠깐 뒤 완료 — 목록에서 빠진다", "체크로 끝낼 일" not in titles() and "남길 일" in titles(), titles())
rep = next(t for t in w.todos if t.title == "반복 일")
ok("반복 할일은 지우지 않고 다음 차례로", rep.run_date > T, rep.run_date)
w.todos = [TodoItem(title="마우스 올릴 일", run_date=T, ment="메모 글")]
w.refresh_todo()
settle()
rect = w.tbl_todo.visualRect(w.tbl_todo.model().index(0, 2))
w.todo_acts.hover_at(rect.center())
ok("줄에 마우스를 올리면 단추가 뜬다", not w.todo_acts.isHidden()
   and [b.text() for b in w.todo_acts.buttons] == ["메모 복사", "수정", "삭제"])
w.todo_acts.hover_at(QPoint(-5, -5))
ok("벗어나면 숨는다", w.todo_acts.isHidden())
got = []
w.on_todo_edit = lambda: got.append(w._sel_todo_key())
w.todo_acts.hover_at(rect.center())
w.todo_acts.buttons[1].click()
ok("[수정] 은 그 줄을 고른 뒤 연다", got and got[0][0] == "local", got)
del w.on_todo_edit
ok("알람 칸은 'ON' 대신 종 모양", all(w.tbl_todo.item(r, 4).text() in ("", "🔔")
                                    for r in range(w.tbl_todo.rowCount())))

# ---------------------------------------------------------------- D3 · D5
print("\n[D3·D5] 브리핑 — 이름을 누르면 그리로 · 길면 'N건 더 보기' · 카드 안 스크롤 없음")
cust = row(7, customer="안내대상", finance="KB캐피탈", model="카니발",
           deliver_date=fmt(T), contract_date=fmt(T - timedelta(days=20)), status="출고")
w.sheet_rows = [cust]
w.cal_events = [ev(T, 9, "오늘 상담")]
w.todos = [TodoItem(title=f"오늘 일 {i}", run_date=T) for i in range(8)]
w.refresh_calendar()
w.refresh_todo()
w.refresh_customers()
settle()
w._paint_dashboard()
brief = w.txt_dash_brief.toPlainText()
ok("오늘 할일은 5줄까지만 먼저", "오늘 일 4" in brief and "오늘 일 5" not in brief
   and "3건 더 보기" in brief, brief[:300])
fold = next(QUrl("dash:" + k) for k, (kind, what) in w._dash_hrefs.items()
            if kind == "fold" and what == "b:오늘 할일")
w._on_dash_link(fold)
brief = w.txt_dash_brief.toPlainText()
ok("누르면 펼친다(접기 단추로 바뀜)", "오늘 일 7" in brief and "접기" in brief)
fold = next(QUrl("dash:" + k) for k, (kind, what) in w._dash_hrefs.items()
            if kind == "fold" and what == "b:오늘 할일")
w._on_dash_link(fold)
ok("다시 누르면 접는다", "오늘 일 7" not in w.txt_dash_brief.toPlainText())
ok("카드 글 칸은 스크롤이 없다(글만큼 키가 자란다)",
   w.txt_dash_brief.verticalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
   and w.txt_dash_brief.height() >= int(w.txt_dash_brief.document().size().height()) - 2,
   (w.txt_dash_brief.height(), w.txt_dash_brief.document().size().height()))

pump(10)
ok("카드가 글을 다 담는다(최소 높이에 눌려 아래가 잘리지 않는다)",
   w.card_brief.height() >= w.card_brief.minimumSizeHint().height() - 2
   and w.card_brief.minimumHeight() == 0, (w.card_brief.height(), w.card_brief.minimumSizeHint().height()))
opened = []
w.on_customer_edit = lambda: opened.append(w._sel_customer())
u = href_for(w, "cust", lambda cr: cr is cust)
ok("안내멘트 미발송 고객 이름이 링크", u is not None)
if u is not None:
    w._on_dash_link(u)
ok("누르면 그 고객 창", opened and opened[0] is cust, opened)
w.ed_cust_find.setText("다른 사람")
w.refresh_customers()
opened.clear()
w._paint_dashboard()
w._on_dash_link(href_for(w, "cust", lambda cr: cr is cust))
ok("고객 표가 검색으로 걸러져 있어도 찾아서 연다", opened and opened[0] is cust
   and w.ed_cust_find.text() == "")
del w.on_customer_edit
cal = []
w.open_calendar = lambda goto=None: cal.append(goto)
w._on_dash_link(href_for(w, "cal", lambda d: d == T))
ok("오늘 일정을 누르면 캘린더가 그 날짜로", cal == [T], cal)
del w.open_calendar
ed = []
w.on_todo_edit = lambda: ed.append(w._sel_todo_key())
target_todo = next(t for t in w.todos if t.title == "오늘 일 2")
w._on_dash_link(href_for(w, "todo", lambda k: k == ("local", id(target_todo))))
ok("할일을 누르면 그 할일 고치기", ed == [("local", id(target_todo))], ed)
del w.on_todo_edit
wk = w.txt_dash_week.toHtml()
ok("이번 주 요약의 고객 이름도 링크", "dash:a" in wk)

# ---------------------------------------------------------------- D6
print("\n[D6] 달력 — 마우스를 올리면 그날 일정 전부")
cal_w = EventCalendar()
cal_w.resize(700, 520)
cal_w.set_events({T: [("09:00", "아주 긴 일정 이름이라 칸에서 잘리는 것"), ("", "종일 일정"),
                      ("14:00", "세 번째"), ("16:00", "네 번째"), ("18:00", "다섯 번째")]})
cal_w.setSelectedDate(cal_w.selectedDate())
cal_w.show()
pump(20)
r = cal_w._cells.get(T)
ok("칸 자리를 기억한다", r is not None)
if r is not None:
    ok("그 자리 → 그 날짜", cal_w.date_at(r.center()) == T)
tip = cal_w.tip_for(T)
ok("풍선 글에 일정 다섯 개 다", all(x in tip for x in ("아주 긴 일정 이름이라 칸에서 잘리는 것", "종일  종일 일정",
                                                  "다섯 번째")) and "5건" in tip, tip)
ok("일정 없는 날은 풍선 없음", cal_w.tip_for(T + timedelta(days=40)) == "")
cal_w.deleteLater()

# ---------------------------------------------------------------- C1 · C2 · C3 · C6
print("\n[C1] 고객 표 — 1536 폭에서도 한눈에(금융사·차종 한 칸 두 줄 · 날짜 짧게)")
from planner import customer_files as cust_folders  # noqa: E402
from planner.tablecells import TwoLineDelegate, short_date  # noqa: E402
w.ed_cust_find.setText("")
w._cust_status = ""
w.sheet_rows = [
    row(2, customer="이서연", finance="현대캐피탈", model="그랜저 HEV", price="52,300,000",
        contract_date="2026. 11. 9", deliver_date="2026. 11. 25", status="발주", note="출고 전 썬팅 예약"),
    row(3, customer="박지훈 (주)한빛물류", finance="우리금융캐피탈", model="카니발 9인승 하이리무진",
        contract_date="2026. 11. 13", status="심사중"),
    row(4, customer="김민준", finance="KB캐피탈", model="쏘렌토 HEV", contract_date="2026. 11. 1",
        deliver_date="2026. 11. 18", status="출고완료"),
    row(5, customer="서지호", finance="신한카드", model="EV3", contract_date="2026. 11. 14",
        deliver_date="2026. 12. 11", status="발주"),
]
w.tabs.setCurrentWidget(w.tab_cust)
w._set_cust_view("list", save=False)
w.resize(1536, 864)
pump(20)
w.refresh_customers()
pump(20)
t = w.tbl_cust
heads = [t.horizontalHeaderItem(i).text() for i in range(t.columnCount())]
ok("칸: 금융사 · 차종 한 칸", heads == ["순번", "고객명 / 사업자", "금융사 · 차종", "차량가격", "계약일",
                                    "출고일", "진행현황", "수수료", "내용", "안내멘트"], heads)
tot = sum(t.columnWidth(i) for i in range(t.columnCount()))
ok("1536 폭에서 가로 스크롤 없이 다 들어간다", tot <= t.viewport().width() + 2, (tot, t.viewport().width()))
ok("안내멘트 칸 80 그대로", t.columnWidth(heads.index("안내멘트")) == 80)
ok("내용 칸이 눌리지 않는다(200 안팎)", t.columnWidth(heads.index("내용")) >= 190,
   t.columnWidth(heads.index("내용")))
names = [t.item(r, 1).text() for r in range(t.rowCount())]
r = names.index("이서연")
fm = t.item(r, w.COL_FINMODEL)
ok("두 줄 칸: 위 금융사 · 아래 차종", fm.data(TwoLineDelegate.TOP) == "현대캐피탈"
   and fm.text().endswith("그랜저 HEV"), (fm.data(TwoLineDelegate.TOP), fm.text()))
ok("가장 긴 차종도 두 줄 칸에 들어간다",
   t.itemDelegateForColumn(w.COL_FINMODEL).sizeHint(t.viewOptions() if hasattr(t, "viewOptions") else __import__("PySide6.QtWidgets", fromlist=["x"]).QStyleOptionViewItem(),
                                                     t.model().index(names.index("박지훈 (주)한빛물류"), w.COL_FINMODEL)).width()
   <= t.columnWidth(w.COL_FINMODEL) + 30)
dc = t.item(r, 4)
ok("날짜는 짧게(26.11.09) · 원래 글은 풍선", dc.text() == "26.11.09" and dc.toolTip() == "2026. 11. 9",
   (dc.text(), dc.toolTip()))
ok("short_date 가 못 읽는 글은 그대로", short_date("8/14 예정") == "8/14 예정" and short_date("") == "")
from planner.tablecells import _last_line  # noqa: E402
ok("두 줄 칸 — Qt 가 넘기는 줄 구분자(U+2028)도 줄로 본다(글자가 겹치던 것)",
   _last_line("우리금융캐피탈\u2028쏘나타 디 엣지") == "쏘나타 디 엣지" and _last_line("KB\n쏘렌토") == "쏘렌토"
   and _last_line("EV3") == "EV3")
w.resize(MainWindow.DEFAULT_W, 900)
pump(20)
w._fit_cust_columns()
ok("평소 폭에서는 고객명 236 · 내용 313 이상(정해 주신 값)",
   t.columnWidth(1) == 236 and t.columnWidth(w.COL_NOTE) >= 313, (t.columnWidth(1), t.columnWidth(w.COL_NOTE)))
w.resize(1536, 864)
pump(20)

print("\n[C1] 보드 — 1536 폭에서 마지막 칸까지 보인다")
w._set_cust_view("board", save=False)
pump(20)
cols = [c for c in w.board.inner.findChildren(__import__("PySide6.QtWidgets", fromlist=["x"]).QFrame)
        if c.objectName() == "boardcol"]
right = max(c.geometry().right() for c in cols) if cols else 0
ok("칸이 다 화면 안에", cols and right <= w.board.scroll.viewport().width() + 2,
   (len(cols), right, w.board.scroll.viewport().width()))
w._set_cust_view("list", save=False)

print("\n[C2] 진행현황 칩 — 눌러서 바로 거른다")
w.refresh_customers()
txts = w.cust_chips.texts()
ok("칩: 전체 + 진행현황별 건수(보드와 같은 차례)", txts[0] == "전체 4" and "발주 2" in txts
   and txts.index("심사중 1") < txts.index("발주 2") < txts.index("출고완료 1"), txts)
w.cust_chips.buttons()["발주"].click()
pump()
shown = [t.item(r, 1).text() for r in range(t.rowCount())]
ok("[발주] 를 누르면 발주만", sorted(shown) == ["서지호", "이서연"], shown)
ok("위 줄에 '보이는 것' 건수", "보이는 것 2건" in w.lbl_cust.text(), w.lbl_cust.text())
w.cust_chips.buttons()["발주"].click()
pump()
ok("같은 칩을 다시 누르면 전체", t.rowCount() == 4 and w.cust_chips.current == "")
w.ed_cust_find.setText("이서")
w.refresh_customers()
ok("검색하면 칩 건수도 검색 결과로", w.cust_chips.texts()[0] == "전체 1", w.cust_chips.texts())
w.ed_cust_find.setText("")
w.refresh_customers()

print("\n[C3] [삭제] 는 [고객 추가] 옆이 아니라 오른쪽 끝")
ok("검색칸보다 오른쪽", w.btn_cust_del.x() > w.ed_cust_find.x() > w.btn_cust_add.x(),
   (w.btn_cust_add.x(), w.ed_cust_find.x(), w.btn_cust_del.x()))

print("\n[C6] 재계약 — 비었으면 까닭을 한 줄로")
w.renew.set_data([], {}, T)
ok("시트 전", not w.renew.lbl_empty.isHidden() and "불러오면" in w.renew.lbl_empty.text()
   and w.renew.stack.currentWidget() is w.renew.lbl_empty)
w.renew.set_data(w.sheet_rows, {}, T)
ok("만기 고객이 없으면", "만기가 오는 고객이 없습니다" in w.renew.lbl_empty.text()
   and w.renew.stack.currentWidget() is w.renew.lbl_empty, w.renew.lbl_empty.text())

# ---------------------------------------------------------------- C4
print("\n[C4] 고객 창 — 두 칸(왼쪽 짧은 칸 · 오른쪽 계약조건·내용·서류)")
from planner.customer_dialog import CustomerDialog  # noqa: E402
d = CustomerDialog("고객 수정", w.sheet_rows[0].values, {}, "이서연 고객님 안녕하세요", w,
                   files=[], auth=None, open_folder=lambda n, par: None)
d.show()
pump(10)
xs = {k: d.widgets[k][0].mapTo(d, QPoint(0, 0)).x() for k in ("customer", "price", "status", "note", "terms")}
xs["doc"] = d.files_box.mapTo(d, QPoint(0, 0)).x()
ok("계약조건·내용·서류는 오른쪽 칸", min(xs["note"], xs["terms"], xs["doc"]) > max(xs["customer"], xs["price"], xs["status"]) + 200, xs)
ok("창 크기는 1536×864 화면 안에(1180×790 까지 · 작은 화면이면 줄인다)", d.SIZE == (1180, 790) and d.width() <= 1180,
   (d.width(), d.height()))
d.resize(1180, 766)          # 1536×864 화면(작업 표시줄 빼고)에서 받는 크기
pump(20)
from PySide6.QtWidgets import QScrollArea as _QSA  # noqa: E402
_sa = d.findChild(_QSA)
ok("그 크기에서 스크롤 없이 한 화면(두 칸)", _sa.widget().minimumSizeHint().height() <= _sa.viewport().height()
   and not _sa.verticalScrollBar().isVisible() and not _sa.horizontalScrollBar().isVisible(),
   (_sa.widget().minimumSizeHint().height(), _sa.viewport().height()))
ok("[📁 고객정보 폴더] 단추", not d.btn_folder.isHidden())
d.close()
d.deleteLater()

# ---------------------------------------------------------------- I1
print("\n[I1] 고객정보 폴더 ↔ 고객관리 서류")
N = cust_folders.Node
nodes = [N(name="이서연", is_dir=True, key="/r/이서연"), N(name="김민준_쏘렌토", is_dir=True, key="/r/김민준_쏘렌토"),
         N(name="이서연", is_dir=True, folder="지난고객", key="/r/지난고객/이서연"),
         N(name="견적서.pdf", is_dir=False, folder="이서연", key="/r/이서연/견적서.pdf")]
ok("이름이 같은 폴더(얕은 것 먼저)", cust_folders.find_customer_folder(nodes, "이서연").key == "/r/이서연")
ok("이름을 품은 폴더", cust_folders.find_customer_folder(nodes, "김민준").key == "/r/김민준_쏘렌토")
ok("'이름 / 회사' 칸도", cust_folders.find_customer_folder(nodes, "없는회사 / 이서연").key == "/r/이서연")
ok("없으면 None", cust_folders.find_customer_folder(nodes, "홍길동") is None)
w.sheet_rows[0].uid = "u2"
w.sheet_rows[0].files_cell = sheets.files_cell("u2", [{"id": "F1", "name": "견적서.pdf", "mime": "application/pdf"},
                                                      {"id": "F2", "name": "등록증.jpg", "mime": "image/jpeg"}])
got = w._docs_for_folder("이서연")
ok("폴더 이름 → 그 고객의 서류", got and got[0] == "이서연" and [a["name"] for a in got[1]] == ["견적서.pdf", "등록증.jpg"], got)
ok("서류 없는 고객은 None", w._docs_for_folder("김민준") is None)
w.tab_files.show_customer_docs("이서연")
btns = [b.text() for b in w.tab_files.docs_bar.findChildren(QPushButton)]
ok("고객정보 탭 위 띠에 서류 단추", not w.tab_files.docs_bar.isHidden() and btns == ["견적서.pdf", "등록증.jpg"], btns)
opened_docs = []
w._open_customer_docs = lambda a, al: opened_docs.append(a["id"])
w.tab_files.open_customer_docs = w._open_customer_docs
w.tab_files.docs_bar.findChildren(QPushButton)[1].click()
ok("누르면 그 서류를 크게", opened_docs == ["F2"], opened_docs)
w.tab_files.show_customer_docs("김민준")
ok("서류 없는 폴더면 띠를 숨긴다", w.tab_files.docs_bar.isHidden())
import planner.main_window as _mw  # noqa: E402
tmp_root = _pl.Path(tempfile.mkdtemp()) / "고객정보"
(tmp_root / "이서연").mkdir(parents=True)
_orig_pick = cust_folders.pick_source
cust_folders.pick_source = lambda st, au: (cust_folders.LocalSource(str(tmp_root)), "")
_urls = []
_orig_open = _mw.QDesktopServices.openUrl
_mw.QDesktopServices.openUrl = staticmethod(lambda u: _urls.append(u.toLocalFile()))
w.open_customer_folder("이서연", w)
ok("[📁 고객정보 폴더] → 탐색기로 그 폴더", _urls == [str(tmp_root / "이서연")], _urls)
cust_folders.pick_source = _orig_pick
_mw.QDesktopServices.openUrl = _orig_open

# ---------------------------------------------------------------- M2
print("\n[M2] 멘트복사 — 고객 안내 문구를 한곳에서 보고·고치고·복사")
from planner import ment_templates, renewals  # noqa: E402
from planner.models import AppSettings  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
secs = w.tab_greet.templates
ok("카드 셋: 출고 안내 · 출고 1개월 · 재계약", [c.spec["key"] for c in secs.cards] == ["cust", "follow", "renew"])
fc = secs.card("follow")
ok("출고 1개월 — 미리보기(이름 자리는 ○○○)", "○○○" in fc.lbl_preview.text(), fc.lbl_preview.text())
ok("단추: 고객 골라 복사 · 이름 없이 복사 · 고치기",
   [b.text() for b in fc.buttons] == ["고객 골라 복사", "이름 없이 복사", "고치기"])
cr0 = next(c for c in w.sheet_rows if c.get("customer") == "이서연")
_orig_pick = ment_templates.CustomerPicker.run
ment_templates.CustomerPicker.run = classmethod(lambda cls, title, rows, label, parent=None: cr0)
fc.buttons[0].click()
clip = QGuiApplication.clipboard().text()
ok("고객 골라 복사 — 이름을 채운다", clip.startswith("이서연 고객님") and "%s" not in clip, clip[:40])
cr0.values["deliver_date"] = "2026. 11. 25"
cr0.values["terms"] = "48개월 / 3만km"
rc = secs.card("renew")
rc.buttons[0].click()
clip = QGuiApplication.clipboard().text()
ok("재계약 — 이름·차종·금융사·만기일을 채운다", clip.startswith("이서연 고객님") and "그랜저 HEV" in clip
   and "{" not in clip, clip[:80])
cust_copied = []
_orig_ccm = w._copy_customer_ment
w._copy_customer_ment = lambda cr: cust_copied.append(cr)
secs.card("cust").buttons[0].click()
ok("고객 안내멘트 — 고객관리 [복사] 와 같은 길(보냄 표시)", cust_copied == [cr0])
w._copy_customer_ment = _orig_ccm
ment_templates.CustomerPicker.run = _orig_pick
_orig_edit = ment_templates.TemplateEditDialog.run
ment_templates.TemplateEditDialog.run = classmethod(
    lambda cls, title, text, default, help_text, parent=None: "{고객} 고객님, 만기({만기일}) 안내드립니다.")
rc.buttons[1].click()
ok("재계약 글을 고치면 설정에 남는다", w.settings.renew_ment == "{고객} 고객님, 만기({만기일}) 안내드립니다.")
ok("재계약 [멘트 복사](고객관리)도 고친 글", w._renew_template() == w.settings.renew_ment)
ok("카드 미리보기도 바로 바뀐다", "만기(" in rc.lbl_preview.text(), rc.lbl_preview.text())
ment_templates.TemplateEditDialog.run = classmethod(
    lambda cls, title, text, default, help_text, parent=None: renewals.RENEW_MENT)
rc.buttons[1].click()
ok("기본 글로 되돌리면 설정은 비운다(기본 글을 따른다)", w.settings.renew_ment == ""
   and w._renew_template() == renewals.RENEW_MENT)
ment_templates.TemplateEditDialog.run = _orig_edit
st = AppSettings()
st.renew_ment = "고친 글"
_cfgp = _pl.Path(tempfile.mkdtemp()) / "plan_cfg.json"
st.save(_cfgp)
ok("재계약 글은 설정 파일에 저장·복원(다른 PC 로도 넘어간다)",
   AppSettings.load(_cfgp).renew_ment == "고친 글" and st.to_json().get("renewMent") == "고친 글")
pk = ment_templates.CustomerPicker("고르기", w.sheet_rows, lambda c: c.get("customer"), w)
pk.ed.setText("ㅇㅅㅇ")
pk._fill()
ok("고객 고르기 — 초성으로 찾는다", pk.lst.count() == 1 and pk.picked() is cr0, pk.lst.count())
pk.deleteLater()

# ---------------------------------------------------------------- K1 · K2 · K3 · K4
print("\n[K1·K2·K3] 자료검색 — 줄에 금융사·분류·📎 · 분류 칩 · 즐겨찾기·최근 본 자료")
import json as _json  # noqa: E402
from planner import kb, kb_marks, kb_tab, promo  # noqa: E402
KB_ITEMS = [
    {"title": "KB캐피탈 신차 할부 서류", "finance": "KB캐피탈", "category": "필요서류", "body": "신분증 사본",
     "files": [{"id": "x1", "name": "체크리스트.pdf", "mime": "application/pdf"}]},
    {"title": "현대캐피탈", "finance": "현대캐피탈", "category": "연락처", "body": "심사팀 02-000-0000"},
    {"title": "하나캐피탈 중도상환 수수료", "finance": "하나캐피탈", "category": "금리·수수료", "body": "최대 2%"},
    {"title": "메리츠캐피탈 법인 서류", "finance": "메리츠캐피탈", "category": "필요서류", "body": "법인등기부등본"},
]
kb.save_shared(KB_ITEMS)
w.tab_kb.reload()
view = w.tab_kb.view
view.ed_find.setText("")
view.flush_search()
view._refilter()
ok("K1 줄 모양은 두 줄(제목 · 금융사·분류)", isinstance(view.lst.itemDelegate(), kb_tab._ItemDelegate)
   and view.lst.sizeHintForRow(0) >= 40, view.lst.sizeHintForRow(0))
ok("K1 금융사가 제목과 같으면 한 번만(분류만)", kb_tab.sub_line(KB_ITEMS[1]) == "연락처"
   and kb_tab.sub_line(KB_ITEMS[0]) == "KB캐피탈 · 필요서류")
tips = [view.lst.item(i).toolTip() for i in range(view.lst.count())]
ok("K1 첨부 있는 자료는 표시(풍선에도)", any("첨부 있음" in t for t in tips), tips)
ok("K2 분류는 칩(건수)", view.cat_chips.texts()[:1] == ["전체 4"] and "필요서류 2" in view.cat_chips.texts(),
   view.cat_chips.texts())
view.cat_chips.buttons()["필요서류"].click()
pump()
names = [view.lst.item(i).text() for i in range(view.lst.count())]
ok("K2 칩을 누르면 그 분류만", sorted(names) == ["KB캐피탈 신차 할부 서류", "메리츠캐피탈 법인 서류"], names)
view.cat_chips.buttons()["필요서류"].click()
view.ed_find.setText("하나")
view.flush_search()
view._refilter()
ok("K2 검색하면 칩 건수도 검색 결과로", view.cat_chips.texts()[0] == "전체 1", view.cat_chips.texts())
view.ed_find.setText("")
view.flush_search()
view._refilter()
base_order = [view.lst.item(i).data(Qt.UserRole)["title"] for i in range(view.lst.count())]
row_of = lambda title: [view.lst.item(i).data(Qt.UserRole)["title"] for i in range(view.lst.count())].index(title)  # noqa: E731
view.lst.setCurrentRow(row_of("메리츠캐피탈 법인 서류"))
view.btn_fav.click()
ok("K3 즐겨찾기 — 설정에 남는다(다른 PC 로도)", w.settings.kb_favs == ["메리츠캐피탈 법인 서류"], w.settings.kb_favs)
ok("K3 단추가 ★ 로", view.btn_fav.text().startswith("★"))
view._refilter()
first = view.lst.item(0).data(Qt.UserRole)["title"]
ok("K3 검색어 없이 보면 즐겨찾기가 맨 위", first == "메리츠캐피탈 법인 서류", first)
it_h = view.lst.item(row_of("하나캐피탈 중도상환 수수료"))
view.lst.setCurrentItem(it_h)
view.lst.itemClicked.emit(it_h)
view._copy_body()
view._refilter()
order = [view.lst.item(i).data(Qt.UserRole)["title"] for i in range(view.lst.count())]
ok("K3 본 자료를 맨 위로 올리지 않는다(최근 본 자료 없앰 — v1.35.3)",
   order[0] == "메리츠캐피탈 법인 서류" and order[1:] == [t for t in base_order if t != "메리츠캐피탈 법인 서류"], order)
ok("K3 줄 앞 표시는 즐겨찾기(★)만", kb_marks.mark_of(KB_ITEMS[3]) == "★" and kb_marks.mark_of(KB_ITEMS[2]) == "")
ok("K3 최근 본 자료 파일을 쓰지 않는다", not (config.data_dir() / "kb_recent.json").exists())
view.lst.setCurrentRow(0)
view.btn_fav.click()
ok("K3 다시 누르면 뺀다", w.settings.kb_favs == [] and view.btn_fav.text().startswith("☆"))

print("\n[K4] 빠른검색 창 — 고객 · 프로모션에서도 찾는다")
fx = _json.loads((_ROOT / "web/verify/fixtures/promo.json").read_text(encoding="utf-8"))
w.tab_promo.blocks = promo.parse(fx["values"], fx.get("merges") or [])
got = w._quick_extra("이서연")
ok("고객 이름으로", any(x["kind"] == "cust" and "이서연" in x["label"] for x in got), [x["label"] for x in got])
got = w._quick_extra("E300")
ok("프로모션 모델로(그 줄 글 그대로 복사)", any(x["kind"] == "promo" and "E300" in x["label"] for x in got),
   [x["label"] for x in got])
w.open_kb_search()
qs = w._kb_quick
qs.view.ed_find.setText("이서연")
qs.view.flush_search()
qs.refresh_extra()
ok("창 아래에 고객 · 프로모션 칸이 뜬다", not qs.lst_extra.isHidden() and qs.lst_extra.count() >= 1)
opened2 = []
w.open_customer = lambda cr: opened2.append(cr.get("customer"))
qs._run_extra(qs.lst_extra.item(0))
pump(5)
ok("Enter(누르기) — 창을 닫고 그 고객 창", opened2 == ["이서연"] and not qs.isVisible(), opened2)
del w.open_customer
w.open_kb_search()
qs.view.ed_find.setText("E300")
qs.view.flush_search()
qs.refresh_extra()
pr = next(i for i in range(qs.lst_extra.count()) if qs.lst_extra.item(i).data(Qt.UserRole)["kind"] == "promo")
qs._run_extra(qs.lst_extra.item(pr))
pump(5)
ok("프로모션 줄은 복사", QGuiApplication.clipboard().text().startswith("E300"), QGuiApplication.clipboard().text()[:60])
qs.view.ed_find.setText("")
qs.refresh_extra()
ok("검색어가 없으면 숨긴다", qs.lst_extra.isHidden())
qs.close()

# ---------------------------------------------------------------- S1 · S2
print("\n[S1·S2] 수당계산기 — 가운데 한 줄 · 처음엔 회색 안내")
pg = next(iter(w.tab_comm.pages.values()))
pg.reset()
ok("S1 차종 칸은 쳐서 찾는다(초성) — 원래 있던 기능, 안내 글로 알려 준다",
   getattr(pg.cmb_car, "_combo_search", None) is not None and "초성" in pg.cmb_car.itemText(0))
ok("S2 처음: 무엇을 넣을지 회색 안내 · 복사 단추는 꺼짐",
   pg.lbl_need.text() == "차종을 고르고 차량가를 넣어 주세요" and not pg.btn_copy.isEnabled()
   and theme.c("subtext").lower() in pg.lbl_result.styleSheet().lower(), pg.lbl_result.styleSheet())
pg.cmb_car.setCurrentIndex(1)
pg.ed_price.setText("30,000,000")
pg.recalc()
ok("S2 다 넣으면 금액(강조색) · 복사 단추 켜짐", pg.lbl_need.text() == "" and pg.btn_copy.isEnabled()
   and pg.lbl_result.text() != "₩ 0" and "subtext" not in pg.lbl_result.styleSheet())
w.tabs.setCurrentWidget(w.tab_comm)
pump(10)
col = pg.findChild(__import__("PySide6.QtWidgets", fromlist=["x"]).QWidget, "calccol")
ok("S2 입력칸이 화면 폭만큼 늘어나지 않는다(680 이하)", col is not None and col.width() <= 680, col.width() if col else None)
pg.reset()

# ---------------------------------------------------------------- A1 · A2 · A3
print("\n[A1·A2·A3] PC 알람 — 스위치 · 다음 울림(가까운 순) · 다시 알림 고르기")
from planner.models import PcAlarm  # noqa: E402
from planner.switch import Switch  # noqa: E402
from planner import alarm_window  # noqa: E402
NOW = datetime.now()
far = (NOW + timedelta(hours=3)).time().replace(second=0, microsecond=0)
near = (NOW + timedelta(minutes=30)).time().replace(second=0, microsecond=0)
w.alarms = [PcAlarm(title="먼 알람", weekdays="1234567", run_time=far),
            PcAlarm(title="꺼진 알람", weekdays="1234567", run_time=near, enabled=False),
            PcAlarm(title="가까운 알람", weekdays="1234567", run_time=near)]
w.refresh_alarm()
ta = w.tbl_alarm
heads = [ta.horizontalHeaderItem(i).text() for i in range(ta.columnCount())]
ok("A2 '다음 울림' 칸", heads[:3] == ["사용", "다음 울림", "이름"], heads)
order = [ta.item(r, 2).text() for r in range(ta.rowCount())]
ok("A2 가까운 순 · 꺼진 것은 아래", order == ["가까운 알람", "먼 알람", "꺼진 알람"]
   or (order[-1] == "꺼진 알람" and order[0] in ("가까운 알람", "먼 알람")), order)
t0 = ta.item(order.index("가까운 알람"), 1).text()
ok("A2 '오늘 HH:MM' · '내일 …' 모양", t0.startswith(("오늘 ", "내일 ")) and t0.endswith(f"{near:%H:%M}"), t0)
ok("A2 꺼진 알람은 '꺼짐'", ta.item(order.index("꺼진 알람"), 1).text() == "꺼짐")
sws = [ta.cellWidget(r, 0).findChild(Switch) for r in range(ta.rowCount())]
ok("A1 ON/OFF 글자 대신 스위치", all(sws) and [s_.isChecked() for s_ in sws] == [True, True, False]
   and all(ta.item(r, 0).text() == "" for r in range(ta.rowCount())))
sws[2].click()
pump(5)
ok("A1 스위치를 켜면 알람이 켜지고 저장 · 다음 울림이 생긴다",
   next(a for a in w.alarms if a.title == "꺼진 알람").enabled
   and "꺼짐" not in [ta.item(r, 1).text() for r in range(ta.rowCount())])
mon = PcAlarm(title="월", weekdays="2", run_time=dtime(9, 0))
base = datetime(2026, 11, 21, 10, 0)          # 토요일
ok("A2 다음 울림 계산(토 10시 → 월 9시)", mon.next_fire(base) == datetime(2026, 11, 23, 9, 0), mon.next_fire(base))
ok("A2 요일이 없으면 없음", PcAlarm(weekdays="").next_fire(base) is None)
win = alarm_window.AlarmWindow("[알람] 시험", "메모", 0, siren=True)
if win is not None:
    acts = [a.text() for a in win.snooze_menu.actions()]
    ok("A3 다시 알림 고르기: 5분·10분·30분·내일 아침", acts == ["5분 뒤", "10분 뒤", "30분 뒤", "내일 아침 9시"], acts)
    win.snooze_menu.actions()[2].trigger()
    ok("A3 30분 뒤 → 숨었다가 30분 뒤", win._snooze_left == 1800 and win.isHidden())
    win.stop()
    win.deleteLater()
ok("A3 내일 아침 9시까지 초", alarm_window.snooze_seconds("morning", datetime(2026, 11, 21, 21, 30)) == int(11.5 * 3600))

# ---------------------------------------------------------------- P1
print("\n[P1] 수입차 프로모션 — 같은 달 안에서 바뀐 곳만 노랗게")
VT = _json.loads((_ROOT / "web/verify/vectors.json").read_text(encoding="utf-8"))["promo_track"]
pt = w.tab_promo
pt.set_where("PROMO_TEST_SHEET", "수입차 프로모션")
for f in ("promo_marks.json",):
    try:
        (config.data_dir() / f).unlink()
    except OSError:
        pass
pt._take({"values": VT["steps"][0]["values"], "merges": VT["merges"], "at": "2026-11-03 10:00"}, fresh=True)
ok("처음 읽으면 표시 없음", not any(pt.marks.values()), pt.marks)
pt._take({"values": VT["steps"][1]["values"], "merges": VT["merges"], "at": "2026-11-20 09:00"}, fresh=True)
ok("11/20 판 — 벤츠만", [k for k, m in pt.marks.items() if m] == ["benz"], pt.marks.keys())
pt.ed_find.setText("")
pt._pick_brand("")
tb = pt.tbl
texts = {(r, c): (tb.item(r, c).text() if tb.item(r, c) else "") for r in range(tb.rowCount()) for c in range(tb.columnCount())}
title_rows = [v for (r, c), v in texts.items() if c == 0 and "✎" in v]
ok("블록 제목 줄에 '11/03 → 11/20 바뀐 모델 3개 · 빠진 모델: …'",
   len(title_rows) == 1 and "11/03 → 11/20 바뀐 모델 3개" in title_rows[0] and "GLC300" in title_rows[0], title_rows)
row_e300 = next(r for (r, c), v in texts.items() if c == 0 and v == "E300 4M+ AMG Line [26MY]")
yellow = theme.c("tomorrow").lower()
ok("바뀐 칸(E300 AMG 차량가격)만 노랗게",
   tb.item(row_e300, 1).background().color().name() == yellow
   and tb.item(row_e300, 2).background().style() == Qt.NoBrush)
row_new = next(r for (r, c), v in texts.items() if c == 0 and v.startswith("🆕 "))
ok("새 모델은 '🆕' 표시", texts[(row_new, 0)] == "🆕 C200 New [27MY]")
tb.clearSelection()
tb.selectRow(row_new)
ok("복사하는 글에는 🆕 가 안 들어간다", pt.selected_text().startswith("C200 New [27MY]"), pt.selected_text())
pt.marks = {}
pt._take({"values": VT["steps"][1]["values"], "merges": VT["merges"], "at": "2026-11-20 09:00"}, fresh=False)
ok("다시 켜서 저장본으로 보여도 표시가 남는다(PC 에 남긴 기록)", bool(pt.marks.get("benz")))
pt._take({"values": VT["steps"][3]["values"], "merges": VT["merges"], "at": "2026-12-01 09:00"}, fresh=True)
# (아우디는 제목에 달이 없어 읽은 때의 달로 본다 — 이 검사는 한자리에서 잇달아 읽으므로 같은 달이 된다)
ok("12월 판 — 달이 바뀌면 표시 없음(제목에 달이 있는 벤츠·BMW)",
   not pt.marks.get("benz") and not pt.marks.get("bmw"), {k: bool(m) for k, m in pt.marks.items()})
pt._take({"values": VT["steps"][4]["values"], "merges": VT["merges"], "at": "2026-12-15 09:00"}, fresh=True)
ok("12/15 판 — 12월 안에서 바뀐 벤츠는 다시 표시", bool(pt.marks.get("benz")))
ok("기록은 이 PC 계정 폴더(promo_marks.json)", (config.data_dir() / "promo_marks.json").exists())

print()
if FAIL:
    print(f"실패 {len(FAIL)}건:")
    for f in FAIL:
        print("  -", f)
    raise SystemExit(1)
print("전부 통과")
