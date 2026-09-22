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

from planner import google_client, sheets, sync, theme  # noqa: E402

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
# ⚠️ 화면이 좁으면(검사용 가상 화면은 800x600 이다) 화면에 맞춘다.
#    '무조건 1440' 으로 못 박으면 작은 노트북에서 창이 화면 밖으로 나간다.
_avail = cw._avail()
ok("제 크기로 열린다 (화면이 좁으면 화면에 맞춘다)",
   cw.width() == min(CalendarWindow.DEFAULT_W, _avail.width()),
   f"{cw.width()} / 화면 {_avail.width()}")

print("\n[A2] 캘린더는 **따로 뜨는 창**이다")
# ⚠️ 자식 위젯으로 두면 메인 창 안쪽에 갇혀, 메인 창보다 넓은 만큼
#    (오른쪽 일정 열이 딱 그만큼이다) 소리 없이 잘린다. 손으로 메인 창을
#    넓혀야 일정이 나타났다 — 실제로 그렇게 걸렸다.
ok("독립된 창이다 (자식 위젯이 아니다)", cw.isWindow())
before = (cw.width(), cw.height())
main_w = w.width()
w.resize(700, 600)
pump()
ok("메인 창을 줄여도 캘린더는 그대로다", (cw.width(), cw.height()) == before,
   f"{before} → {(cw.width(), cw.height())}")
cw4 = CalendarWindow(w.gauth, w)
cw4.show()
pump()
ok("좁은 메인 창에서 열어도 제 크기로 뜬다", cw4.width() > w.width(),
   f"캘린더 {cw4.width()} / 메인 {w.width()}")
ok("달력 쪽이 일정 열보다 넓다", cw4.split.sizes()[0] > cw4.split.sizes()[1],
   cw4.split.sizes())
ok("화면 밖으로 나가지 않는다",
   cw4.width() <= cw4._avail().width() and cw4.height() <= cw4._avail().height(),
   f"{cw4.width()}x{cw4.height()} 화면 {cw4._avail().width()}x{cw4._avail().height()}")
cw4.close()
w.resize(main_w, 920)
pump()

print("\n[B] 그 날의 일정이 목록에 들어온다")
ok("세 건이 보인다", cw.lst.count() == 3, cw.lst.count())
ok("일정 원본을 들고 있다",
   cw.lst.item(0).data(Qt.UserRole) is not None)

print("\n[B2] 읽기 좋게 — 큰 글씨 + 줄마다 라벨색")
base = cw.font().pointSize()
ok("기본 글씨보다 크다", cw.lst.item(0).font().pointSize() > base,
   f"목록 {cw.lst.item(0).font().pointSize()}pt / 기본 {base}pt")
ok("굵게 쓴다", cw.lst.item(0).font().bold())
ok("줄 높이도 글씨에 맞춰 늘어난다", cw.lst.item(0).sizeHint().height() >= 28,
   cw.lst.item(0).sizeHint().height())
# ⚠️ 달력 칸의 띠와 **같은 색**이어야 한다. 둘 다 e.start 로 정렬해 같은 차례로
#    도니, 달력의 셋째 띠와 목록의 셋째 줄이 같은 색이 된다. 색을 따로 고르면
#    이 짝이 어긋나 오히려 헷갈린다.
cols = [cw.lst.item(i).background().color().name() for i in range(cw.lst.count())]
want = [cw.cal.chip_bg(i).lower() for i in range(cw.lst.count())]
ok("달력 칸과 같은 라벨색", cols == want, f"{cols} vs {want}")
ok("줄마다 색이 다르다", len(set(cols)) == len(cols), cols)
ok("글자색도 색띠 위에서 읽히게 정한다",
   cw.lst.item(0).foreground().color().name() == theme.c("chip_text").lower(),
   cw.lst.item(0).foreground().color().name())

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

print("\n[E] 우클릭 메뉴 — 이제 여기가 유일한 길이다")
src = (_ROOT / "python" / "planner" / "calendar_window.py").read_text(encoding="utf-8")
ok("목록에 우클릭 메뉴가 붙어 있다", "customContextMenuRequested" in src)
ok("[일정 수정] 이 있다", '"일정 수정"' in src)
ok("[일정 삭제] 가 있다", '"일정 삭제"' in src)
ok("[해당 일정으로 이동] 이 있다", '"해당 일정으로 이동"' in src)
# 더블클릭은 예전과 똑같이 수정 창을 연다
ok("더블클릭은 그대로 수정", "itemDoubleClicked" in src and "_edit_selected" in src)
ok("달력 더블클릭은 그대로 추가", "cal.activated" in src and "_add_for_selected" in src)

# ⚠️ 위 단추 셋을 없앴다. 없앤 뒤 메뉴에 그 일이 없으면 **할 방법이 통째로
#    사라진다.** 그래서 단추가 없다는 것과 메뉴에 있다는 것을 같이 못 박는다.
for gone in ("이 날짜에 일정 추가", "선택 일정 수정", "선택 일정 삭제"):
    ok(f"[{gone}] 단추가 없다", f'QPushButton("{gone}")' not in src)
for attr in ("btn_add", "btn_edit", "btn_del"):
    ok(f"{attr} 를 아무도 안 쓴다", attr not in src, attr)
ok("남은 단추는 새로고침·브라우저·닫기",
   all(hasattr(cw, a) for a in ("btn_refresh", "btn_web", "btn_close")))
ok("무엇을 할 수 있는지 한 줄 안내가 있다",
   hasattr(cw, "lbl_hint") and "오른쪽 버튼" in cw.lbl_hint.text(), 
   getattr(getattr(cw, "lbl_hint", None), "text", lambda: "")())

# 실제로 메뉴를 만들어 본다.
# ⚠️ _list_menu 를 부르면 안 된다 — QMenu.exec 은 모달이라 검사가 거기서
#    영영 멈춘다(그렇게 한 번 걸렸다). 그래서 만드는 쪽만 따로 부른다.
cw.lst.setCurrentRow(0)
ev0 = cw.lst.item(0).data(Qt.UserRole)
_menu, acts = cw._menu_for(ev0)
names = [a.text() for a in _menu.actions() if not a.isSeparator()]
ok("메뉴에 추가·수정·삭제·이동이 다 있다",
   "일정 추가" in names[0] and "일정 수정" in names
   and "일정 삭제" in names and "해당 일정으로 이동" in names, names)
ok("추가 메뉴에 고른 날짜가 적힌다", "9월 20일" in names[0], names[0])
ok("일정 위에서는 수정·삭제가 켜진다",
   acts["edit"].isEnabled() and acts["del"].isEnabled())
ok("고객 일정이면 [해당 일정으로 이동] 도 켜진다", acts["go"].isEnabled())
_menu2, acts2 = cw._menu_for(None)
ok("빈 자리에서도 [일정 추가] 는 켜져 있다", acts2["add"].isEnabled())
ok("빈 자리에서 수정·삭제는 꺼진다",
   not acts2["edit"].isEnabled() and not acts2["del"].isEnabled())
_menu3, acts3 = cw._menu_for(EVENTS[2])          # 치과 예약 — 고객과 안 이어진다
ok("고객과 안 이어진 일정은 [이동] 이 꺼진다", not acts3["go"].isEnabled())

print("\n[E2] 연/월 글씨가 크다")
from planner import theme as _th  # noqa: E402
q = _th.qss()
ok("달력 위쪽 연/월이 기본보다 크다", "font-size: 12pt" in q,
   [l.strip() for l in q.split("\n") if "font-size: 12pt" in l][:2])
ok("연도를 고칠 때 뜨는 칸도 같은 크기",
   "QCalendarWidget QSpinBox" in q and q.split("QCalendarWidget QSpinBox")[1]
   .split("}")[0].find("12pt") > 0)

print("\n[E3] 날짜 숫자가 굵고 또렷한가")
from PySide6.QtCore import Qt as _Qt  # noqa: E402
from planner import theme as _th2  # noqa: E402
ok("날짜 글씨가 커졌다 (9pt → 11pt 이상)", cw.cal.DAY_PT >= 11, cw.cal.DAY_PT)
_src = (_ROOT / "python" / "planner" / "calendar_window.py").read_text(encoding="utf-8")
ok("이번 달 날짜는 굵게 그린다", "f.setBold(in_month)" in _src)
ok("토·일 색을 팔레트에서 가져온다",
   'theme.c("day_sun")' in _src and 'theme.c("day_sat")' in _src)
# 맨 윗줄 요일 이름도 같은 색이라야 따로 놀지 않는다
_sat = cw.cal.weekdayTextFormat(_Qt.Saturday)
_sun = cw.cal.weekdayTextFormat(_Qt.Sunday)
_mon = cw.cal.weekdayTextFormat(_Qt.Monday)
# QColor.name() 은 소문자로 준다 — 팔레트는 대문자라 맞춰서 견준다
ok("머리줄 '토' 가 토요일 색",
   _sat.foreground().color().name() == _th2.c("day_sat").lower(),
   _sat.foreground().color().name())
ok("머리줄 '일' 이 일요일 색",
   _sun.foreground().color().name() == _th2.c("day_sun").lower(),
   _sun.foreground().color().name())
ok("머리줄 평일은 본문색",
   _mon.foreground().color().name() == _th2.c("text").lower(),
   _mon.foreground().color().name())
ok("머리줄도 굵다", _sat.fontWeight() >= 75, _sat.fontWeight())
# 날짜 숫자를 키웠으니 일정 띠가 숫자를 파고들면 안 된다
ok("일정 띠 자리는 숫자 높이에서 잡는다", "rect.top() + num_h" in _src)

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
