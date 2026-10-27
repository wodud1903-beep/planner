"""회귀 — 이번에 건드린 자리 주변이 그대로인가."""
# ⚠️ 경로를 박아 두지 않는다. 예전에는 이 검사들이 작업용 임시 폴더에만 있고
# "/home/user/planner" 를 글자 그대로 들고 있어서, 컨테이너가 다시 뜨면 통째로
# 사라졌다(실제로 두 번 겪었다). 이제 저장소 안에 살고, 자기 위치에서 뿌리를 찾는다.
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]      # tools/verify/x.py → 저장소 뿌리
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
import os as _os
_os.chdir(_ROOT / "python")                          # 'planner/...' 상대경로를 쓰는 검사용
import os, shutil, sys, tempfile
from datetime import date, datetime, time, timedelta

FAIL = []
def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond: FAIL.append(name)

tmp = tempfile.mkdtemp(); os.environ["APPDATA"] = tmp
# 쓰시는 PC 의 모니터(FHD) 크기 — v1.22 부터 왼쪽 메뉴 몫만큼 창이 넓다
os.environ["QT_QPA_PLATFORM"] = os.environ.get("PLAT", "vnc:size=1920x1080")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from planner import (config, contacts, followup, google_client, hangul, kb,
                     kb_seed, sheets, sync, theme, weekly)
from planner.sheets import CustomerRow
# 시작 브리핑은 모달이라, 검사에서 뜨면 processEvents 가 거기서 멈춘다.
# (실제 사용에서는 떠야 맞다 — 여기서만 막는다)
from planner import startup_dialog as _sd
_sd.StartupDialog.show_for = staticmethod(lambda *a, **k: None)

from planner.models import AppSettings

app = QApplication([])
# 실제 앱과 같은 글꼴을 심는다(app.py). 이걸 안 하면 Qt 기본 글꼴로 재게 되어
# 열 폭·단추 폭이 실제보다 넓게 나온다 — 예전엔 여기서 헛다리를 짚었다.
from PySide6.QtGui import QFont
_f = QFont("Malgun Gothic", 10); _f.setWeight(QFont.DemiBold); app.setFont(_f)
theme.apply_to_app(app)
config.set_account("tester@example.com")

def row(**kw):
    cr = CustomerRow(row=kw.pop("row", 2), total=kw.pop("total", ""),
                     center=kw.pop("center", ""), accident=kw.pop("accident", ""))
    cr.values.update(kw)
    return cr

print("\n[A] 시트 값 다루기")
ok("금액 소수점 반올림", sheets.digits_only("₩1,234.56") == "1235")
ok("통화기호 뒤 음수", sheets.digits_only("₩-1,000") == "-1000")
ok("회계 괄호는 음수", sheets.digits_only("(₩1,000)") == "-1000")
ok("날짜 여러 형식", all(sheets.parse_date(s) == date(2026, 8, 14) for s in
   ("2026. 8. 14", "2026-08-14", "2026년 8월 14일")))
ok("못 읽으면 None", sheets.parse_date("8/14 예정") is None)
ok("수식 열은 안 쓴다", sheets.FORMULA_COLS == [0, 7, 15, 16, 17, 19])
ok("P·Q 열 번호", (sheets.COL_CENTER, sheets.COL_ACCIDENT) == (15, 16))
ok("만기 계산", sheets.expiry_date(
    row(deliver_date="2021. 9. 3", terms="60개월")) == date(2026, 9, 3))

print("\n[B] 초성 검색")
ok("초성", hangul.chosung("쏘나타") == "ㅆㄴㅌ")
ok("겹자음 느슨하게", hangul.matches("쏘나타", "ㅅㄴㅌ"))
ok("낱말 AND", hangul.matches("그랜저 하이브리드", "그랜 하이"))
ok("없는 건 안 걸린다", not hangul.matches("쏘나타", "카니발"))

print("\n[C] 자료검색 · 연락처")
kb.save_shared(kb_seed.DEFAULTS)
items = kb.load_all()
ok("기본자료 25건 이상", len(items) >= 25, len(items))
ok("심사서류 3종", len(kb.doc_templates(items)) == 3,
   [i["title"] for i in kb.doc_templates(items)])
ok("제목 검색이 위로", kb.search(items, "BNK")[0]["title"].startswith("BNK"))
ok("본문 빈 줄 정규화", kb.norm_body("가 \n\n 나  ") == "가\n\n 나")

ok("신한카드 하나로 정해진다",
   [c["finance"] for c in contacts.candidates(items, "신한카드")] == ["신한카드"])
amb = [c["finance"] for c in contacts.candidates(items, "우리캐피탈")]
ok("우리캐피탈은 후보 여럿", len(amb) >= 2, amb)
ok("시트 번호가 먼저",
   contacts.for_customer(items, row(finance="신한카드", center="1544-7000"))[0]
   == [("고객센터", "1544-7000")])
ok("승계 수수료를 번호로 안 줍는다",
   not any("165" in v for _l, v in contacts.phones_of(
       [i for i in items if i.get("finance") == "롯데렌터카"][0])))

print("\n[D] 동기화 — 목록은 항목 단위로 합친다")
import json
a = json.dumps([{"name": "A", "after": "1", "miss": "2"}], ensure_ascii=False)
b = json.dumps([{"name": "B", "after": "3", "miss": "4"}], ensure_ascii=False)
merged = json.loads(sync.merge_text("greetings.json", a, b))
ok("양쪽 채널이 다 남는다", {x["name"] for x in merged} == {"A", "B"}, merged)
ok("할일은 합치지 않는다", "todos.json" not in sync._MERGE)
ok("깨진 JSON 이 멀쩡한 쪽을 안 지운다",
   sync.merge_text("greetings.json", "{{{", b) in (b, "{{{") )
ok("window.json 은 동기화 대상이 아님", "window.json" not in sync._FILES)

import inspect
print("\n[E] 창 크기 — 보통과 최대화 둘뿐")
google_client.GoogleAuth.is_connected = lambda self: False
sync.sync_now = lambda *a, **k: (False, "")
sheets.read_rows = lambda *a, **k: (1, [], [])
from planner.main_window import MainWindow
from PySide6.QtGui import QGuiApplication as _QGA
_avail = _QGA.primaryScreen().availableGeometry()
_avail_w, _avail_h = _avail.width(), _avail.height()
w = MainWindow(); w.show(); app.processEvents()
h_norm = w._normal_h
import time as _t


def pumpw(n=6):
    for _ in range(n):
        app.processEvents()
        _t.sleep(0.01)


# v1.22.2: 세로도 끌어서 바꾼다(예전엔 '보통' 세로를 못 박고 되돌렸다).
# 지키는 것은 하나 — 제목표시줄이 화면 밖으로 나가지 않게.
ok("세로 하한은 있다(왼쪽 메뉴가 겹치지 않게)",
   w.minimumHeight() == min(MainWindow.MIN_HEIGHT, _avail_h - 60), w.minimumHeight())
ok("가로는 조절 가능", w.minimumWidth() < w.maximumWidth())
ok("최대화 단추가 있다", bool(w.windowFlags() & Qt.WindowMaximizeButtonHint))
ok("세로 상한을 걸지 않는다(걸면 최대화가 죽는다)", w.maximumHeight() >= _avail_h,
   (w.maximumHeight(), _avail_h))
h0 = w.height()
w.resize(w.width(), h0 - 150); pumpw()
ok("세로를 줄일 수 있다", w.height() == h0 - 150, w.height())
w.resize(w.width(), min(h0 + 60, _avail_h - 40)); pumpw()
ok("세로를 늘릴 수 있다", w.height() == min(h0 + 60, _avail_h - 40), w.height())
w.resize(w.width(), _avail_h + 400); pumpw()
ok("화면보다 크게는 안 된다(제목표시줄이 밖으로 안 나가게)",
   w.frameGeometry().height() <= _avail_h, (w.frameGeometry().height(), _avail_h))
w.resize(w.width(), h0); pumpw()
w.move(w.x(), _avail.top() - 500); pumpw()
ok("제목표시줄이 화면 위로 나가면 되돌린다", w.frameGeometry().top() >= _avail.top(),
   w.frameGeometry().top())
w.move(w.x(), _avail.bottom() + 80); pumpw()
ok("화면 아래로 사라지면 끌어올린다",
   w.frameGeometry().top() <= _avail.bottom() - MainWindow.TITLE_KEEP, w.frameGeometry().top())
w.move(_avail.right() + 300, _avail.top() + 50); pumpw()
ok("오른쪽 밖으로 나가도 제목줄 일부는 화면에", w.frameGeometry().left() <= _avail.right() - 200,
   w.frameGeometry().left())
w.move(_avail.left() + 10, _avail.top() + 10); pumpw()
ok("화면 안에서는 옮긴 자리 그대로", (w.frameGeometry().left(), w.frameGeometry().top())
   == (_avail.left() + 10, _avail.top() + 10), (w.frameGeometry().left(), w.frameGeometry().top()))
# 크기를 기억한다(가로·세로)
w.resize(w.width(), h0 - 100); pumpw()
w._remember_width()
_wj = json.loads((config.base_dir() / MainWindow.WIN_FILE).read_text(encoding="utf-8"))
ok("세로도 적어 둔다", _wj.get("height") == h0 - 100, _wj)
w6 = MainWindow()
ok("다시 켜면 그 세로로", w6._normal_h == h0 - 100 and w6.height() == h0 - 100,
   (w6._normal_h, w6.height()))
w6.deleteLater()
(config.base_dir() / MainWindow.WIN_FILE).write_text(
    json.dumps({"width": 1600, "height": _avail_h + 900, "maximized": False, "layout": 2}),
    encoding="utf-8")
w7 = MainWindow()
ok("큰 모니터에서 맞춘 세로라도 이 화면 안으로", w7._normal_h <= _avail_h - 40, w7._normal_h)
w7.deleteLater()
(config.base_dir() / MainWindow.WIN_FILE).write_text(
    json.dumps({"width": 1600, "maximized": False, "layout": 2}), encoding="utf-8")
w8 = MainWindow()
ok("세로를 못 바꾸던 시절 파일이면 기본 세로", w8._normal_h == min(920, _avail_h - 60), w8._normal_h)
w8.deleteLater()
w.resize(w.width(), h0); pumpw()
h_norm = w.height()

# 최대화 중에는 크기를 건드리지 않는다(되돌리면 최대화가 풀려 버린다).
# setWindowState 로 진짜 최대화를 시키면 이 환경(창관리자 없음)이 멈추므로,
# '최대화 상태' 만 흉내 내어 우리 쪽 판단이 맞게 도는지 본다.
_real_is_max = MainWindow._is_max
MainWindow._is_max = lambda self: True
w.resizeEvent(__import__("PySide6.QtGui", fromlist=["QResizeEvent"])
              .QResizeEvent(w.size(), w.size()))
ok("가로 상한이 걸려 있지 않다", w.maximumWidth() > _avail_w, w.maximumWidth())
_tall = h_norm + 200
w.resize(w.width(), _tall); pumpw()
ok("최대화 중에는 세로를 안 건드린다", w.height() == _tall, w.height())
ok("최대화 중 크기는 '보통' 으로 치지 않는다", w._normal_h == h_norm, w._normal_h)
w._remember_width()
_wj = json.loads((config.base_dir() / MainWindow.WIN_FILE).read_text(encoding="utf-8"))
ok("최대화 중에는 '보통' 크기를 적어 둔다", _wj.get("height") == h_norm and _wj.get("maximized"),
   _wj)
MainWindow._is_max = _real_is_max
w.resize(w.width(), h_norm)            # 최대화를 풀면 창관리자가 원래 크기로 되돌린다
pumpw()
ok("풀면 다시 보통으로 친다", not w._is_max() and w.height() == h_norm, w.height())
ok("되돌려도 가로 상한은 안 건다", w.maximumWidth() > _avail_w, w.maximumWidth())
ok("가로 하한은 남아 있다", w.minimumWidth() >= min(MainWindow.MIN_WIDTH, _avail_w - 20),
   w.minimumWidth())
# 화면을 거의 채운 크기면 상태 비트가 없어도 최대화로 본다(윈도는 '커졌다' 가 먼저 온다)
_mw, _mh = _avail_w, _avail_h - 19
w.resize(_mw, _mh); pumpw()
ok("화면을 채웠으면 상태 비트가 없어도 최대화로 본다", w._is_max(),
   (w.width(), w.height(), _avail_w, _avail_h))
w.resize(_mw, h_norm - 100); pumpw()
ok("가로만 넓힌 건 최대화가 아니다", not w._is_max() and w.height() == h_norm - 100, w.height())
w.resize(min(MainWindow.DEFAULT_W, _avail_w - 20), h_norm); pumpw()

ok("창 상태 알림이 없어도 스스로 맞춘다(resizeEvent 에서도 부른다)",
   "self._apply_size_mode()" in inspect.getsource(MainWindow.resizeEvent))

ok("최대화 여부를 적어 둔다", '"maximized"' in inspect.getsource(MainWindow))
ok("최대화 중 폭은 '보통' 폭으로 적는다",
   "self._normal_w if mx else self.width()" in inspect.getsource(MainWindow))
ok("켤 때 지난 상태를 되살린다",
   "_saved_maximized" in inspect.getsource(MainWindow)
   and "showMaximized" in inspect.getsource(MainWindow))
import inspect as _i
# 창 자신에게 setFixedHeight 를 쓰면 최대화가 다시 막힌다.
# (상단바 같은 자식 위젯에 쓰는 건 상관없다)
ok("창 세로를 못 박지 않는다",
   "self.setFixedHeight(" not in _i.getsource(MainWindow),
   [l.strip() for l in _i.getsource(MainWindow).splitlines()
    if "self.setFixedHeight(" in l])

ok("탭 7개", w.tabs.count() == 7, [w.tabs.tabText(i) for i in range(w.tabs.count())])
ok("탭 차례 그대로",
   [w.tabs.tabText(i) for i in range(7)] ==
   ["대시보드", "고객관리", "고객정보", "멘트복사", "자료검색",
    "수당계산기", "PC 알람"],
   [w.tabs.tabText(i) for i in range(w.tabs.count())])
ok("고객정보는 고객관리 바로 옆",
   w.tabs.indexOf(w.tab_files) == w.tabs.indexOf(w.tbl_cust.parent().parent()) + 1
   or w.tabs.tabText(w.tabs.indexOf(w.tab_files) - 1) == "고객관리")
# 폴더가 크면 훑는 데 몇 초 걸린다 → 켤 때가 아니라 탭을 처음 열 때 읽는다
ok("켤 때는 안 읽는다", w._files_loaded is False)
w.tabs.setCurrentIndex(w.tabs.indexOf(w.tab_files)); app.processEvents()
ok("탭을 열면 읽는다", w._files_loaded is True)
w.tabs.setCurrentIndex(0); app.processEvents()

print("\n[F] 고객관리 화면")
import inspect
src = inspect.getsource(MainWindow)
ok("더블클릭은 수정",
   "on_customer_edit" in inspect.getsource(MainWindow._on_cust_dblclick))
# 버튼 줄은 [고객 추가][삭제] 둘뿐이다. 서류·이력은 지우지 않고 우클릭
# 메뉴로 옮겼다 — 이미 적어 둔 상담 메모를 못 열게 되면 안 되므로.
btnrow = inspect.getsource(MainWindow._build_customer_tab)
ok("버튼 줄은 [고객 추가][삭제] 뿐",
   '("고객 추가", self.on_customer_add)' in btnrow
   and '("삭제", self.on_customer_del)' in btnrow
   and '("서류"' not in btnrow and '("이력"' not in btnrow)
menu = inspect.getsource(MainWindow._cust_context_menu)
ok("서류·이력은 우클릭으로 남아 있다",
   '("이력", self.on_customer_history)' in menu
   and '("서류", self.on_customer_docs)' in menu)
ok("우클릭 연락처 메뉴", "contacts.for_customer" in src)
ok("주간 요약 버튼", "btn_weekly" in src)
ok("통합 보드를 연다", "btn_weekly.clicked.connect(self.show_startup_screen)" in src)
# 이 창은 모달이라 겹치면 아래 것의 [확인] 이 안 눌린다.
# 시작 브리핑 타이머가 도는 중에 [주간 요약] 을 누르면 실제로 겹쳤다.
_ss = inspect.getsource(MainWindow.show_startup_screen)
ok("브리핑 창은 겹쳐 뜨지 않는다", "_startup_open" in _ss and "return" in _ss)
ok("빠른검색 단축키는 인자 없음",
   list(inspect.signature(MainWindow.open_kb_search).parameters) == ["self"])
ok("탭 열기는 말을 받는다",
   list(inspect.signature(MainWindow.open_kb_for).parameters) == ["self", "query"])

print("\n[F-2] 고객 목록 — '내용' 말고는 잘리면 안 된다")
# 글씨를 10pt→11pt 로 키우고 차량가격·내용 열을 넣은 뒤, 예전 폭 그대로 두어
# 금융사·차종·차량가격·계약일·출고일·수수료 여섯 열이 잘렸었다.
# 앞으로 폰트나 열을 건드릴 때 같은 일이 나면 여기서 잡힌다.
LONG = dict(customer="주식회사 대한모빌리티", finance="우리금융캐피탈",
            model="카니발 9인승 하이리무진", price="145,800,000",
            contract_date="2026. 12. 31", deliver_date="2026. 12. 31",
            status="진행보류", note="아주 긴 상담 내용 " * 6)
_long = row(row=2, total="12,240,000", **LONG); _long.seq = "1"
sheets.read_rows = lambda *a, **k: (1, [_long], [])
w2 = MainWindow(); w2.sheet_rows = [_long]; w2.show(); app.processEvents()
# 앞 [E] 에서 폭을 바꿔 본 값이 저장돼 넘어온다. 열 폭 검사는 '평소 폭' 기준이므로
# 여기서 그 폭으로 맞춰 놓고 잰다(딴 검사가 남긴 값에 휘둘리지 않게).
w2.resize(min(MainWindow.DEFAULT_W, _avail_w - 20), w2.height()); app.processEvents()
w2.tabs.setCurrentIndex(1); w2.refresh_customers()
for _ in range(3):
    app.processEvents()
t2 = w2.tbl_cust
heads = [t2.horizontalHeaderItem(i).text() for i in range(t2.columnCount())]
cut = [(h, t2.columnWidth(i), t2.sizeHintForColumn(i))
       for i, h in enumerate(heads)
       if h != "내용" and t2.sizeHintForColumn(i) > t2.columnWidth(i)]
ok("가장 긴 값에서도 '내용' 외에는 안 잘린다", not cut, cut)
ok("차량가격·내용 열이 있다", "차량가격" in heads and "내용" in heads, heads)
ok("차량가격은 차종 바로 뒤", heads.index("차량가격") == heads.index("차종") + 1)
ok("내용은 수수료 바로 뒤", heads.index("내용") == heads.index("수수료") + 1)
ok("서류 버튼 열은 없다", "서류" not in heads, heads)
ok("'내용' 은 남는 폭을 받아 넉넉하다", t2.columnWidth(heads.index("내용")) >= 150,
   t2.columnWidth(heads.index("내용")))
ok("표가 창 안에 들어간다(가로 스크롤 없음)",
   sum(t2.columnWidth(i) for i in range(t2.columnCount())) <= t2.viewport().width() + 2,
   (sum(t2.columnWidth(i) for i in range(t2.columnCount())), t2.viewport().width()))
ok("줄 높이가 넉넉하다", t2.verticalHeader().defaultSectionSize() >= 30,
   t2.verticalHeader().defaultSectionSize())
ok("목록 글씨 10pt", "font-size: 10pt" in t2.styleSheet(), t2.styleSheet())
# 쓰시는 분이 직접 정해 주신 폭 — 마음대로 바꾸지 않는다.
ok("고객명 236", t2.columnWidth(heads.index("고객명 / 사업자")) == 236,
   t2.columnWidth(heads.index("고객명 / 사업자")))
ok("안내멘트 80", t2.columnWidth(heads.index("안내멘트")) == 80,
   t2.columnWidth(heads.index("안내멘트")))
ok("내용 255 이상(남는 폭을 받는다)", t2.columnWidth(heads.index("내용")) >= 255,
   t2.columnWidth(heads.index("내용")))
# 복사하면 '복사' → '✓ 복사' 로 길어진다. 그때 체크표시가 잘렸었다.
_b = t2.cellWidget(0, MainWindow.COL_MENT_BTN)
_b.setText("✓ 복사"); _b.adjustSize()
ok("'✓ 복사' 가 안내멘트 칸에 들어간다",
   _b.sizeHint().width() <= t2.columnWidth(heads.index("안내멘트")),
   (_b.sizeHint().width(), t2.columnWidth(heads.index("안내멘트"))))

print("\n[F-2c] v1.22 왼쪽 메뉴 — 표 자리는 그대로, 예전 폭은 메뉴 몫만큼 넓혀 연다")
ok("기본 폭 = 정해 주신 1570 + 메뉴 몫", MainWindow.DEFAULT_W == 1570 + MainWindow.LAYOUT_EXTRA
   and MainWindow.BASE_W == 1570)
_wp = config.base_dir() / MainWindow.WIN_FILE
_wp.write_text(json.dumps({"width": 1500, "maximized": False}), encoding="utf-8")
w4 = MainWindow()
ok("상단바 시절 폭(1500)은 메뉴 몫을 더해 연다",
   w4._normal_w == min(1500 + MainWindow.LAYOUT_EXTRA, _avail_w - 20), w4._normal_w)
w4._remember_width()
ok("새로 적을 때는 배치 판을 같이 적는다",
   json.loads(_wp.read_text(encoding="utf-8")).get("layout") == MainWindow.LAYOUT_VER)
_wp.write_text(json.dumps({"width": 1500, "maximized": False, "layout": 2}), encoding="utf-8")
w5 = MainWindow()
ok("새 배치에서 맞춘 폭은 그대로(두 번 더하지 않는다)", w5._normal_w == 1500, w5._normal_w)
for _x in (w4, w5):
    _x.hide(); _x.deleteLater()
app.processEvents()

print("\n[F-2b] 고객관리 → 고객정보 건너뛰기")
# 고객관리에서 우클릭 → '이 고객 서류 보기' 로 넘어오면, 고객정보 탭으로
# 옮겨 가면서 그 고객 이름으로 찾아 둬야 한다.
_files_root = os.path.join(tmp, "고객정보")
for _rel in ("2026-08 김상현(신한카드)/계약서.pdf",
             "2026-08 김상현(신한카드)/신분증.jpg",
             "2026-09 이수민(KB캐피탈)/견적서.pdf"):
    _full = os.path.join(_files_root, _rel)
    os.makedirs(os.path.dirname(_full), exist_ok=True)
    open(_full, "wb").write(b"%PDF")
w.settings.files_dir = _files_root
w.open_files_for("김상현"); app.processEvents()
ok("고객정보 탭으로 옮겨간다",
   w.tabs.tabText(w.tabs.currentIndex()) == "고객정보",
   w.tabs.tabText(w.tabs.currentIndex()))
ok("검색칸에 고객 이름이 들어간다", w.tab_files.ed_search.text() == "김상현",
   w.tab_files.ed_search.text())
# 검색은 전체 목록(index)을 뒤에서 만든 다음 걸러 낸다. 여기서는 그 목록을
# 직접 넣어 걸러지는지만 본다(만드는 과정은 verify_browse.py 가 본다).
from planner import customer_files as _cf
w.tab_files.source = _cf.LocalSource(_files_root)
w.tab_files.index = _cf.sort_nodes(w.tab_files.source.scan())
w.tab_files._show_search("김상현"); app.processEvents()
_rows = [w.tab_files.tbl.item(r, 0).text()
         for r in range(w.tab_files.tbl.rowCount())]
ok("그 고객 서류만 나온다",
   _rows and all("이수민" not in x for x in _rows)
   and any("계약서.pdf" in x for x in _rows), _rows)
# 우클릭 메뉴에 그 항목이 실제로 있는가
_menu_src = inspect.getsource(MainWindow._cust_context_menu)
ok("우클릭 메뉴에 '서류 보기'", "open_files_for" in _menu_src)
w.tabs.setCurrentIndex(0); app.processEvents()

# 로그인하면 창이 설정 객체를 통째로 새로 읽는다(reload_data). 예전엔 고객정보
# 탭이 만들 때 받은 옛 객체를 붙들고 있어서, 설정에서 폴더를 지정해도 탭은 빈
# 값을 보고 늘 0건이었다. 실제로 겪으신 증상이 이것이다.
# reload_data() 가 하는 일의 핵심은 이 한 줄 — 설정 객체를 통째로 갈아끼우는 것.
# (reload_data() 를 통째로 부르면 이 검사 환경에서 멈춰서, 같은 상황만 만든다)
_fresh = AppSettings.load(w.cfg_file)
ok("갈아끼우기 전에는 같은 객체", w.tab_files.settings is w.settings)
w.settings = _fresh
ok("설정을 새로 읽어도 탭이 창을 따라본다",
   w.tab_files.settings is w.settings)
w.settings.files_dir = _files_root
ok("창에서 폴더를 바꾸면 탭도 그 값을 본다",
   w.tab_files.settings.files_dir == _files_root,
   w.tab_files.settings.files_dir)
from planner import customer_files as _cf2
_src, _why = _cf2.pick_source(w.tab_files.settings, w.gauth)
ok("그래서 읽을 곳이 정해진다", _src is not None and _src.kind == "local", _why)
ok("설정을 바꾸면 다시 읽도록 표시한다",
   "self.tab_files.reload()" in inspect.getsource(MainWindow.on_settings_click))

print("\n[F-3] 메인 화면 [Google 계정으로 로그인]")
# 로그아웃 상태면 설정 창을 열지 않고도 바로 로그인할 수 있어야 한다
ok("로그아웃이면 단추가 보인다", w.btn_google.isVisible())
ok("구글 로고가 붙어 있다", not w.btn_google.icon().isNull())
ok("글자가 구글 안내대로", w.btn_google.text() == "Google 계정으로 로그인",
   w.btn_google.text())
ok("설정으로 가라는 안내는 뺐다", "설정" not in w.lbl_status.text(),
   w.lbl_status.text())
_was = google_client.GoogleAuth.is_connected
google_client.GoogleAuth.is_connected = lambda self: True
w.update_google_status(); app.processEvents()
ok("로그인하면 단추가 사라진다", not w.btn_google.isVisible())
google_client.GoogleAuth.is_connected = _was
w.update_google_status(); app.processEvents()
ok("로그아웃하면 다시 나온다", w.btn_google.isVisible())
# 로고 색은 브랜드 값이라 테마를 따라가면 안 된다
from planner import google_button
_light = google_button.button_css()
theme.set_theme("dark")
ok("밝은/어두운 배색이 다르다", google_button.button_css() != _light)
ok("로고는 늘 네 가지 색", all(
    c in google_button._G_SVG for c in ("#4285F4", "#34A853", "#FBBC05", "#EA4335")))
theme.set_theme("light")

print("\n[G] 브리핑은 평문·HTML 두 벌")
secs = w._briefing_sections()
ok("브리핑 섹션이 만들어진다", isinstance(secs, list) and secs)
t, h = w.build_briefing(), w.build_briefing_html()
ok("평문에 날짜", f"{date.today():%Y년}" in t)
ok("HTML 태그가 평문에 안 샌다", "<" not in t)
ok("HTML 은 태그가 있다", "<p" in h)

print("\n[H] 테마 3종")
ok("세 가지", theme.THEME_ORDER == ("light", "warm", "dark"), theme.THEME_ORDER)
base = set(theme.LIGHT)
for k in theme.THEME_ORDER:
    pal = theme.THEMES[k][1]
    ok(f"{k}: 색 열쇠가 빠짐없다", set(pal) == base, sorted(base ^ set(pal)))
    theme.set_theme(k)
    ok(f"{k}: 스타일시트가 만들어진다", theme.c("window_bg") in theme.qss())
theme.set_theme("light")

shutil.rmtree(tmp, ignore_errors=True)
print("\n" + ("실패 %d건: %s" % (len(FAIL), FAIL) if FAIL else "전부 통과"))
sys.exit(1 if FAIL else 0)
