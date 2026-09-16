"""캘린더 창 — 오른쪽 일정 열, 우클릭 메뉴, 해당 고객으로 이동.

창을 실제로 띄워서 본다(화면 필요). 구글은 가짜로 끼운다.
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
from datetime import date, datetime

tmp = tempfile.mkdtemp()
os.environ["APPDATA"] = tmp
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QListWidget  # noqa: E402

from planner import google_client, sheets, sync  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name
          + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


app = QApplication.instance() or QApplication([])


def pump(n=30):
    for _ in range(n):
        app.processEvents()
        time.sleep(0.01)


# 로그인해 있는 것처럼 꾸민다. '해당 일정으로 이동' 은 시트가 연결돼 있어야
# 도는 기능이라(_sheet_ready), 연결 안 된 척하면 안내 창이 뜨고 거기서 멈춘다.
google_client.GoogleAuth.is_connected = lambda self: True
google_client.GoogleAuth.has_scope = lambda self, scope: True
google_client.fetch_calendar_events = lambda *a, **k: []
google_client.fetch_calendar_list = lambda *a, **k: []
google_client.fetch_tasks = lambda *a, **k: []
sync.sync_now = lambda *a, **k: (False, "")
sheets.read_rows = lambda *a, **k: (1, [], [])

from planner.calendar_window import CalendarWindow  # noqa: E402
from planner.main_window import MainWindow  # noqa: E402

# ⚠️ 시작 브리핑은 **모달 창**이라 화면 없는 검사에서 영영 멈춘다.
#    다른 검사들은 processEvents 를 한 번만 불러서 여기까지 안 왔을 뿐이다.
#    이 검사는 창을 실제로 굴려 봐야 해서 그 자리에서 걸렸다.
MainWindow.show_startup_screen = lambda self, *a, **k: None


def ev(summary, d: date):
    return google_client.CalEvent(
        start=datetime(d.year, d.month, d.day), has_time=False, summary=summary,
        uid="U" + summary, cal_id="primary", event_id="E" + summary)


DAY = date(2026, 9, 20)
EVENTS = [
    ev("홍길동 출고", DAY),
    ev("[출고 1개월] 김상현", DAY),
    ev("치과 예약", DAY),
]


def customer(name, row, model="", deliver=""):
    cr = sheets.CustomerRow(row=row, uid=f"u{row}")
    cr.values = {"customer": name, "model": model, "deliver_date": deliver}
    return cr


w = MainWindow()
w.settings.sheet_on = True
w.settings.sheet_id = "SHEET"
w.settings.sheet_name = "미출고차량"
w.sheet_rows = [
    customer("홍길동", 5, "쏘나타", "2026. 9. 20"),
    customer("박성일 / 박가네 백년약초", 6, "GV80"),
    customer("김상현", 7, "아이오닉5", "2026. 8. 20"),
]
w.refresh_customers()
pump()

cw = CalendarWindow(w.gauth, w)
cw.resize(1380, 880)
cw.show()
# ⚠️ 창은 뜬 뒤에 뒤에서 한 번 다시 불러온다(QTimer.singleShot → reload).
#    그래서 일정을 **먼저** 넣어 두면 그 조회 결과로 덮여 사라진다.
#    처음엔 그렇게 해 두고 '한 건밖에 안 보인다' 로 걸렸다. 가라앉힌 뒤에 넣는다.
pump()
cw.events = list(EVENTS)
cw._redraw()
cw.cal.setSelectedDate(QDate(2026, 9, 20))
cw._on_day_selected(QDate(2026, 9, 20))
pump(5)

print("\n[A] 일정 목록이 오른쪽에 한 열로 선다")
ok("좌우로 나뉘는 칸이 있다", hasattr(cw, "split") and cw.split.count() == 2)
cal_x = cw.cal.mapToGlobal(cw.cal.rect().topLeft()).x()
lst_x = cw.lst.mapToGlobal(cw.lst.rect().topLeft()).x()
ok("목록이 달력 **오른쪽**에 있다", lst_x > cal_x, f"달력 x={cal_x} 목록 x={lst_x}")
# 예전엔 높이 120px 로 달력 아래에 눕혀 두어 세 건만 넘어도 스크롤해야 했다
ok("높이가 120px 로 묶여 있지 않다", cw.lst.height() > 300, cw.lst.height())
ok("아예 접히지는 않는다", not cw.split.childrenCollapsible())
ok("창이 넓게 열린다", cw.width() >= 1380, cw.width())

print("\n[B] 그 날의 일정이 목록에 들어온다")
ok("세 건이 보인다", cw.lst.count() == 3, cw.lst.count())
ok("일정 원본을 들고 있다",
   cw.lst.item(0).data(Qt.UserRole) is not None)

print("\n[C] 제목에서 고객명 뽑기")
ok("'홍길동 출고' → 홍길동", cw._customer_name_of(EVENTS[0]) == "홍길동",
   cw._customer_name_of(EVENTS[0]))
ok("'[출고 1개월] 김상현' → 김상현", cw._customer_name_of(EVENTS[1]) == "김상현",
   cw._customer_name_of(EVENTS[1]))
ok("'치과 예약' 은 고객이 아니다", cw._customer_name_of(EVENTS[2]) == "",
   cw._customer_name_of(EVENTS[2]))

print("\n[D] 고객 찾기 — 슬래시가 섞인 고객 칸")
# ⚠️ 시트의 고객 칸은 "박성일 / 박가네 백년약초" 다. 캘린더에서 뽑히는 것은
#    한 조각(박성일)뿐이라 통째로 비교하면 못 찾는다.
ok("조각으로 갈라 찾는다", len(w._rows_named("박성일")) == 1)
ok("통째로 적어도 찾는다", len(w._rows_named("박성일 / 박가네 백년약초")) == 1)
ok("없는 이름은 안 나온다", w._rows_named("없는사람") == [])
ok("빈 이름은 안 나온다", w._rows_named("") == [])
w.sheet_rows.append(customer("홍길동", 9, "카니발"))
w.refresh_customers()
ok("동명이인은 둘 다 나온다 (말없이 고르지 않는다)",
   len(w._rows_named("홍길동")) == 2, len(w._rows_named("홍길동")))
w.sheet_rows.pop()
w.refresh_customers()
pump()

print("\n[E] 우클릭 메뉴")
src = (_ROOT / "python" / "planner" / "calendar_window.py").read_text(encoding="utf-8")
ok("목록에 우클릭 메뉴가 붙어 있다", "customContextMenuRequested" in src)
ok("[일정 수정] 이 있다", '"일정 수정"' in src)
ok("[해당 일정으로 이동] 이 있다", '"해당 일정으로 이동"' in src)
# 더블클릭은 예전과 똑같이 수정 창을 연다
ok("더블클릭은 그대로 수정", "itemDoubleClicked" in src and "_edit_selected" in src)

print("\n[F] 고객으로 이동")
opened = []
w.on_customer_edit = lambda: opened.append(w._sel_customer())
cw._goto_customer(EVENTS[0])
pump()
ok("고객 수정 창을 연다", len(opened) == 1, opened)
ok("맞는 고객을 골랐다", opened and opened[0] is not None
   and opened[0].get("customer") == "홍길동",
   opened and opened[0] and opened[0].get("customer"))
ok("고객관리 탭으로 옮겨 간다",
   w.tabs.currentWidget() is w.tab_cust, w.tabs.tabText(w.tabs.currentIndex()))

opened.clear()
cw._goto_customer(EVENTS[1])
pump()
ok("팔로업 일정도 그 고객을 연다",
   opened and opened[0] and opened[0].get("customer") == "김상현",
   opened and opened[0] and opened[0].get("customer"))

print("\n[G] 좌우 폭을 기억한다")
cw.split.setSizes([900, 420])
cw._remember_split()
ok("끌어 놓은 폭이 설정에 남는다", w.settings.cal_side_w == 420, w.settings.cal_side_w)
cw2 = CalendarWindow(w.gauth, w)
cw2.resize(1380, 880)
cw2.show()
pump()
ok("다시 열면 그 폭으로 선다", abs(cw2.split.sizes()[1] - 420) <= 2,
   cw2.split.sizes())
cw2.close()

print("\n[H] 말도 안 되는 폭은 안 쓴다")
w.settings.cal_side_w = 5          # 너무 좁다
cw3 = CalendarWindow(w.gauth, w)
cw3.resize(1380, 880)
cw3.show()
pump()
ok("너무 좁으면 기본값으로", cw3.split.sizes()[1] >= 240, cw3.split.sizes())
cw3.close()

cw.close()
print("\n" + (f"{len(FAIL)}건 실패" if FAIL else "전부 통과"))
raise SystemExit(1 if FAIL else 0)
