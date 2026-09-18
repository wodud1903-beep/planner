"""구글 캘린더 창 — 월 달력을 보고 날짜를 클릭해 일정을 추가·수정·삭제.

- 달력(월 보기)에 일정이 있는 날을 굵게 표시
- 날짜 클릭 → 그 날의 일정 목록 표시
- 날짜 더블클릭 또는 [이 날짜에 일정 추가] → 구글 캘린더에 바로 등록(쓰기)
- 아래 목록에서 일정 더블클릭 또는 [수정]/[삭제] → 기존 일정 편집
- [브라우저에서 열기] → 실제 구글 캘린더 웹으로 이동
"""

from __future__ import annotations

import threading
import webbrowser
from datetime import date, datetime, time, timedelta

from PySide6.QtCore import QDate, QRect, QSize, Qt, QTime, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetrics, QGuiApplication, QPainter
from PySide6.QtWidgets import (
    QCalendarWidget, QCheckBox, QComboBox, QDateEdit, QDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
    QMessageBox, QPushButton, QSizePolicy, QSplitter, QTimeEdit, QVBoxLayout,
    QWidget,
)

from . import config, followup, google_client, holiday, searchcombo, theme


class EventCalendar(QCalendarWidget):
    """월 달력 각 칸에 날짜 + 그 날의 일정명을 함께 그리는 캘린더.

    구글 캘린더처럼 클릭하지 않아도 일정이 칸 안에 보인다.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._by_date: dict = {}   # date -> [(timetext, summary), ...]
        self.setGridVisible(True)
        self.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.setHorizontalHeaderFormat(QCalendarWidget.ShortDayNames)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_events(self, by_date: dict):
        self._by_date = by_date or {}
        self.updateCells()

    def chip_bg(self, i: int) -> str:
        """한 칸에 일정이 여러 개면 색을 번갈아 써 서로 구분되게 한다.

        오른쪽 일정 목록도 이 색을 쓴다(창 쪽에서 부른다) — 그래서 공개 이름이다.
        """
        pal = theme.chip_colors()
        return pal[i % len(pal)]

    def paintCell(self, painter, rect, qd):  # noqa: N802
        d = date(qd.year(), qd.month(), qd.day())
        today = date.today()
        in_month = (qd.month() == self.monthShown() and qd.year() == self.yearShown())
        selected = (qd == self.selectedDate())

        painter.save()
        # 배경
        if selected:
            bg = QColor(theme.c("select_bg"))
        elif d == today:
            bg = QColor(theme.c("today"))
        else:
            bg = QColor(theme.c("panel_bg") if in_month else theme.c("window_bg"))
        painter.fillRect(rect, bg)
        # 칸 테두리
        painter.setPen(QColor(theme.c("grid")))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))

        # 날짜 숫자 (일요일·공휴일(대체공휴일 포함)=빨강, 토=파랑)
        dow = qd.dayOfWeek()  # 1=월 .. 7=일
        # 색을 박아 두면 테마를 못 따라간다 — 다크에서 3.6:1 까지 떨어졌었다
        if dow == 7 or holiday.is_holiday(d):
            numcol = QColor(theme.strong("red"))
        elif dow == 6:
            numcol = QColor(theme.strong("blue"))
        else:
            numcol = QColor(theme.c("text"))
        if not in_month:
            numcol = QColor(theme.c("subtext"))
        f = painter.font()
        f.setPointSize(9)
        f.setBold(d == today)
        painter.setFont(f)
        painter.setPen(numcol)
        painter.drawText(rect.adjusted(5, 3, -4, 0), Qt.AlignLeft | Qt.AlignTop, str(qd.day()))

        # 일정명 — 색칠한 띠(칩) 위에 굵은 글씨로. 날짜 숫자와 확실히 구분된다.
        evs = self._by_date.get(d, [])
        if evs:
            fe = painter.font()
            fe.setPointSize(8)
            fe.setBold(True)
            painter.setFont(fe)
            fm = painter.fontMetrics()
            # 칩 여백은 최소로 — 칸에 들어가는 일정 수가 예전보다 줄면 안 된다
            chip_h = fm.height() + 2
            line_h = chip_h + 1
            top = rect.top() + 20
            avail = rect.height() - 22
            maxlines = max(0, avail // line_h)
            shown = evs if len(evs) <= maxlines else evs[:max(0, maxlines - 1)]

            painter.setRenderHint(QPainter.Antialiasing, True)
            for i, (tm, summ) in enumerate(shown):
                label = (tm + " " if tm else "") + summ
                y = top + i * line_h
                box = QRect(rect.left() + 3, y, rect.width() - 7, chip_h)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(self.chip_bg(i)))
                painter.drawRoundedRect(box, 4, 4)
                painter.setPen(QColor(theme.c("chip_text")))
                painter.drawText(box.adjusted(5, 0, -4, 0),
                                 Qt.AlignLeft | Qt.AlignVCenter,
                                 fm.elidedText(label, Qt.ElideRight, box.width() - 9))
            painter.setBrush(Qt.NoBrush)
            if len(evs) > maxlines and maxlines >= 1:
                more = f"+{len(evs) - len(shown)}건"
                painter.setPen(QColor(theme.c("accent")))
                painter.drawText(rect.left() + 5, top + len(shown) * line_h,
                                 rect.width() - 9, line_h,
                                 Qt.AlignLeft | Qt.AlignVCenter, more)
        painter.restore()


class AddEventDialog(QDialog):
    """일정 추가 / 수정 공용.

    event 를 주면 '수정' 모드가 된다. 다른 캘린더로 옮기는 것은 구글에서 별도
    move 요청이라 수정 모드에서는 캘린더 선택을 잠근다(제목·날짜·시각만 바꾼다).
    """

    def __init__(self, day: date, calendars: list[dict], parent=None, event=None):
        super().__init__(parent)
        self.edit_mode = event is not None
        self.setWindowTitle(("일정 수정 · " if self.edit_mode else "일정 추가 · ")
                            + day.strftime("%Y-%m-%d (%a)"))
        self.setMinimumWidth(380)
        self.day = day
        form = QFormLayout(self)

        self.ed_title = QLineEdit()
        form.addRow("제목", self.ed_title)

        self.cmb_cal = QComboBox()
        searchcombo.install(self.cmb_cal)
        for c in calendars:
            label = ("★ " if c["primary"] else "") + c["name"]
            self.cmb_cal.addItem(label, c["id"])
        form.addRow("캘린더", self.cmb_cal)

        # 수정할 때 날짜도 옮길 수 있어야 한다(하루 밀린 일정을 고치는 일이 잦다)
        self.de_day = QDateEdit()
        self.de_day.setCalendarPopup(True)
        self.de_day.setDisplayFormat("yyyy-MM-dd")
        self.de_day.setDate(QDate(day.year, day.month, day.day))
        form.addRow("날짜", self.de_day)

        self.chk_allday = QCheckBox("종일")
        self.chk_allday.setChecked(True)
        self.chk_allday.toggled.connect(lambda on: self.dt_time.setEnabled(not on))
        form.addRow(self.chk_allday)

        self.dt_time = QTimeEdit()
        self.dt_time.setDisplayFormat("HH:mm")
        self.dt_time.setTime(QTime(9, 0))
        self.dt_time.setEnabled(False)
        form.addRow("시각", self.dt_time)

        if self.edit_mode:
            self.ed_title.setText(event.summary)
            self.chk_allday.setChecked(not event.has_time)
            if event.has_time:
                self.dt_time.setTime(QTime(event.start.hour, event.start.minute))
            idx = self.cmb_cal.findData(event.cal_id)
            if idx >= 0:
                self.cmb_cal.setCurrentIndex(idx)
            self.cmb_cal.setEnabled(False)
            self.cmb_cal.setToolTip("수정할 때는 다른 캘린더로 옮길 수 없습니다.")

        row = QHBoxLayout()
        row.addStretch()
        ok = QPushButton("저장" if self.edit_mode else "추가")
        ok.setDefault(True)
        ok.clicked.connect(self._ok)
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.reject)
        row.addWidget(ok)
        row.addWidget(cancel)
        form.addRow(row)

    def _ok(self):
        if not self.ed_title.text().strip():
            QMessageBox.information(self, config.APP_NAME, "제목을 입력하세요.")
            return
        self.accept()

    def values(self):
        t = self.dt_time.time()
        qd = self.de_day.date()
        return {
            "title": self.ed_title.text().strip(),
            "calendar_id": self.cmb_cal.currentData(),
            "all_day": self.chk_allday.isChecked(),
            "time": time(t.hour(), t.minute()),
            "day": date(qd.year(), qd.month(), qd.day()),
        }


PENDING_GRACE_SEC = 60   # 서버 반영이 늦어도 이 시간까지는 방금 추가한 일정을 유지


class CalendarWindow(QWidget):
    sig_events = Signal(object, str, int)   # (list[CalEvent]|None, error, 조회시작 epoch)
    sig_cals = Signal(object)               # list[dict]
    sig_added = Signal(object, object, str)  # (임시기록, 실제 CalEvent|None, error)
    sig_changed = Signal(str, str)           # (error, 성공 메시지) — 수정/삭제 결과

    def __init__(self, auth: google_client.GoogleAuth, parent=None):
        super().__init__(parent)
        self.auth = auth
        self.calendars: list[dict] = []
        self.events: list[google_client.CalEvent] = []
        self._marked: list[QDate] = []
        # 아직 서버 반영이 확인되지 않은(방금 추가한) 일정
        self._pending: list[dict] = []
        self._epoch = 0
        self._adding = False       # 일정 하나가 아직 구글로 올라가는 중인가

        self.setWindowTitle("구글 캘린더")
        # ⚠️ **따로 뜨는 창**이다. parent 를 주면서 이 깃발을 안 켜면 그냥 자식
        #    위젯이 되어 메인 창 안쪽에 갇힌다 — 메인 창보다 넓게 만들어도
        #    넘치는 만큼(오른쪽 일정 열이 딱 그만큼이다) 소리 없이 잘려서,
        #    손으로 메인 창을 넓혀야 일정이 나타났다.
        #    parent 는 그대로 둔다: 설정(cal_side_w)·고객 이동에 쓰고,
        #    메인 창을 닫으면 이 창도 같이 닫힌다.
        self.setWindowFlag(Qt.Window, True)
        self.setWindowIcon(parent.windowIcon() if parent else self.windowIcon())
        self._open_own_size()
        # 뒤 창이 비치지 않도록 불투명 배경 + 스타일 배경 적용
        self.setObjectName("calwin")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"#calwin{{background:{theme.c('window_bg')};}}")

        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)
        top = QHBoxLayout()
        # ⚠️ [이 날짜에 일정 추가]·[선택 일정 수정]·[선택 일정 삭제] 단추는 없앴다.
        #    셋 다 '먼저 고르고 위에서 누른다' 는 두 동작이라, 마우스로 바로
        #    하는 편이 빠르다. 지금은 이렇게 한다:
        #      · 달력의 날짜를 더블클릭 → 그 날에 일정 추가
        #      · 오른쪽 목록에서 더블클릭 → 수정
        #      · 오른쪽 목록에서 오른쪽 버튼 → 추가·수정·삭제·해당 고객으로 이동
        #    그래서 아래 안내를 한 줄 둔다 — 단추가 없어지면 할 수 있는 일도
        #    같이 안 보이게 되기 때문이다.
        self.lbl_hint = QLabel("날짜를 더블클릭하면 일정 추가 · "
                               "오른쪽 목록에서 마우스 오른쪽 버튼으로 수정·삭제")
        self.lbl_hint.setStyleSheet(self._hint_css())
        self.btn_refresh = QPushButton("새로고침")
        # '불러오는 중…' 으로 글자가 길어져도 잘리지 않게 폭을 미리 잡아 둔다
        self.btn_refresh.setMinimumWidth(110)
        self.btn_refresh.clicked.connect(self.reload)
        self.btn_web = QPushButton("브라우저에서 열기")
        self.btn_web.clicked.connect(lambda: webbrowser.open("https://calendar.google.com/"))
        self.btn_close = QPushButton("닫기")
        self.btn_close.clicked.connect(self.close)
        top.addWidget(self.btn_refresh)
        top.addSpacing(10)
        top.addWidget(self.lbl_hint)
        top.addStretch()
        top.addWidget(self.btn_web)
        top.addWidget(self.btn_close)
        v.addLayout(top)

        self.cal = EventCalendar()
        self.cal.clicked.connect(self._on_day_selected)
        self.cal.activated.connect(lambda _d: self._add_for_selected())

        # 그 날의 일정은 **오른쪽 한 열**에 세운다.
        # 예전엔 달력 아래에 높이 120px 로 눕혀 뒀는데, 그러면 세 건만 넘어도
        # 스크롤해야 했고 고객 이름이 긴 건(주식회사 …)은 옆으로 잘렸다.
        side = QWidget()
        sv = QVBoxLayout(side)
        sv.setContentsMargins(8, 0, 0, 0)
        sv.setSpacing(4)
        self.lbl_day = QLabel("날짜를 선택하면 그 날의 일정이 여기에 보입니다")
        # 배경색과 글자색이 겹쳐 안 보이는 문제 방지 → 색을 명시적으로 지정
        self.lbl_day.setStyleSheet(self._day_label_css())
        self.lbl_day.setWordWrap(True)
        sv.addWidget(self.lbl_day)
        self.lst = QListWidget()
        # 아래 좁은 칸이 아니라 오른쪽 한 열이 됐으니 줄을 띄워 읽기 좋게 한다
        self.lst.setSpacing(2)
        self.lst.setWordWrap(True)
        self.lst.itemDoubleClicked.connect(lambda _i: self._edit_selected())
        self.lst.setContextMenuPolicy(Qt.CustomContextMenu)
        self.lst.customContextMenuRequested.connect(self._list_menu)
        sv.addWidget(self.lst, 1)

        self.split = QSplitter(Qt.Horizontal)
        self.split.addWidget(self.cal)
        self.split.addWidget(side)
        self.split.setStretchFactor(0, 1)    # 넓어지면 달력이 가져간다
        self.split.setStretchFactor(1, 0)
        self.split.setChildrenCollapsible(False)   # 끌어서 아예 없애지는 못하게
        v.addWidget(self.split, 1)
        # 사람이 끌어 정한 폭을 기억한다. 값이 없으면 오른쪽 340px.
        QTimer.singleShot(0, self._restore_split)

        self.sig_events.connect(self._on_events)
        self.sig_cals.connect(self._on_cals)
        self.sig_added.connect(self._on_added)
        self.sig_changed.connect(self._on_changed)
        self.apply_theme()

        # 체감 속도 향상: 메인 창이 이미 받아둔 일정으로 즉시 화면을 그린다.
        seed = getattr(parent, "cal_events", None) if parent is not None else None
        if seed:
            self.events = list(seed)
            self._redraw()

        # 창이 먼저 뜨고 나서(다음 이벤트 루프 틱) 백그라운드 로딩 → 여는 순간 멈춤 방지
        QTimer.singleShot(0, self.reload)

    # ---- 제 크기로 열기 ----
    DEFAULT_W, DEFAULT_H = 1440, 920   # 달력 1100 + 오른쪽 일정 열 340

    def _open_own_size(self):
        """메인 창 크기와 상관없이 제 크기로, 화면 가운데에 뜬다.

        달력이 눌리면 칸 안의 일정명이 먼저 잘리므로 달력 쪽에 1100px 은 남긴다.
        화면이 그보다 작으면 화면에 맞춘다.
        """
        avail = self._avail()
        w = min(self.DEFAULT_W, avail.width())
        h = min(self.DEFAULT_H, avail.height())
        self.resize(w, h)
        self.move(avail.left() + (avail.width() - w) // 2,
                  avail.top() + (avail.height() - h) // 2)

    def _avail(self):
        """이 창이 뜰 화면의 작업 영역. 여러 화면을 쓰면 부모가 있는 화면."""
        scr = None
        p = self.parent()
        if p is not None:
            scr = p.screen()
        if scr is None:
            scr = self.screen() or QGuiApplication.primaryScreen()
        return scr.availableGeometry()

    # ---- 좌우 폭 기억 ----
    def _restore_split(self):
        """정해 둔 좌우 폭을 되살린다. 없으면 오른쪽 340px."""
        want = 0
        try:
            want = int(getattr(self.parent(), "settings", None).cal_side_w or 0)
        except Exception:
            want = 0
        total = max(self.split.width(), 600)
        side = want if 240 <= want <= total - 400 else 340
        self.split.setSizes([total - side, side])
        self.split.splitterMoved.connect(lambda *_a: self._remember_split())

    def _remember_split(self):
        st = getattr(self.parent(), "settings", None)
        if st is None:
            return
        sizes = self.split.sizes()
        if len(sizes) == 2 and sizes[1] > 0:
            st.cal_side_w = int(sizes[1])
            try:
                st.save()
            except Exception:
                pass

    # ---- 오른쪽 목록 우클릭 ----
    def _list_menu(self, pos):
        """오른쪽 목록의 마우스 오른쪽 버튼 — 추가·수정·삭제·고객으로 이동."""
        item = self.lst.itemAt(pos)
        if item is not None:
            self.lst.setCurrentItem(item)
        ev = item.data(Qt.UserRole) if item else None
        menu, acts = self._menu_for(ev)
        picked = menu.exec(self.lst.viewport().mapToGlobal(pos))
        if picked is None:
            return
        if picked is acts["add"]:
            self._add_for_selected()
        elif picked is acts["edit"]:
            self._edit_selected()
        elif picked is acts["del"]:
            self._delete_selected()
        elif picked is acts["go"]:
            self._goto_customer(ev)

    def _menu_for(self, ev):
        """그 메뉴를 **만들기만** 한다. 띄우는 것은 _list_menu 가 한다.

        위 단추들을 없앴으므로 여기가 유일한 길이다. 그래서 일정이 없는 빈
        자리에서 눌러도 [~일에 일정 추가] 는 늘 켜 둔다.

        ⚠️ 만드는 일과 띄우는 일을 갈라 둔다. 한 덩어리로 두면 검사에서 메뉴가
           뜬 채 영영 멈춘다(QMenu.exec 은 모달이다) — 실제로 그렇게 걸렸다.
        """
        menu = QMenu(self)
        qd = self.cal.selectedDate()
        acts = {"add": menu.addAction(f"{qd.month()}월 {qd.day()}일에 일정 추가")}
        menu.addSeparator()
        acts["edit"] = menu.addAction("일정 수정")
        acts["del"] = menu.addAction("일정 삭제")
        menu.addSeparator()
        acts["go"] = menu.addAction("해당 일정으로 이동")
        acts["edit"].setEnabled(ev is not None)
        acts["del"].setEnabled(ev is not None)
        # 고객과 이어지는 일정일 때만 켠다 — 눌러 놓고 '아무 일도 안 난다' 가
        # 제일 나쁘다.
        acts["go"].setEnabled(bool(ev) and bool(self._customer_name_of(ev)))
        return menu, acts

    def _customer_name_of(self, ev) -> str:
        """일정 제목에서 고객명. 고객과 안 이어진 일정이면 ''.

        두 가지를 본다 — 둘 다 followup 이 만들거나 읽는 모양이다.
          "[출고 1개월] 홍길동"   팔로업 할일이 캘린더에 올라간 것
          "홍길동 출고"           출고일을 정할 때 자동으로 만든 것
        """
        title = getattr(ev, "summary", "") or ""
        name = followup.followup_name(title)
        if name:
            return name
        keyword = "출고"
        st = getattr(self.parent(), "settings", None)
        if st is not None:
            keyword = (getattr(st, "follow_keyword", "") or "출고").strip() or "출고"
        return followup.extract_customer_name(title, keyword)

    def _goto_customer(self, ev):
        """그 고객의 출고정보(고객 수정 창)를 연다."""
        name = self._customer_name_of(ev)
        parent = self.parent()
        if not name or parent is None or not hasattr(parent, "open_customer_by_name"):
            QMessageBox.information(
                self, config.APP_NAME,
                "이 일정은 고객과 이어져 있지 않습니다.\n"
                "'<고객명> 출고' 나 '[출고 1개월] <고객명>' 형태의 일정에서만 됩니다.")
            return
        parent.open_customer_by_name(name, self)

    def resizeEvent(self, e):          # noqa: N802
        super().resizeEvent(e)
        self._clamp_split()

    def _clamp_split(self):
        """창이 줄어도 오른쪽 열이 사라지지 않게 잡아 둔다."""
        if not hasattr(self, "split"):
            return
        total = self.split.width()
        if total < 400:
            return
        sizes = self.split.sizes()
        if len(sizes) != 2:
            return
        side = min(max(sizes[1], 240), max(240, total - 400))
        if abs(side - sizes[1]) > 1:
            self.split.setSizes([total - side, side])

    def goto_date(self, d: date):
        """그 날짜로 달력을 옮기고 아래에 그 날 일정을 펼친다."""
        if d is None:
            return
        qd = QDate(d.year, d.month, d.day)
        self.cal.setSelectedDate(qd)
        self.cal.setCurrentPage(d.year, d.month)
        self._on_day_selected(qd)
        if self.lst.count():
            self.lst.setCurrentRow(0)      # 바로 [수정]/[삭제] 를 누를 수 있게

    # ---- 오른쪽 목록 글씨 ----
    LIST_PT = 12        # 기본 글씨보다 한 단계 크게 — 멀리서도 읽힌다

    def _hint_css(self) -> str:
        return f"color:{theme.c('subtext')};background:transparent;"

    def _day_label_css(self) -> str:
        # 배경색과 글자색이 겹쳐 안 보이는 문제 방지 → 색을 명시적으로 지정
        return (f"font-weight:bold;font-size:{self.LIST_PT}pt;"
                f"background:transparent;color:{theme.c('text')};padding:2px 0 4px;")

    def _list_font(self, bold: bool = True):
        f = self.font()
        f.setPointSize(self.LIST_PT)
        f.setBold(bold)
        return f

    def _list_row_h(self) -> int:
        """글씨 크기에 맞춘 줄 높이. 띠(라벨색)가 글자에 붙지 않게 여백을 준다."""
        return QFontMetrics(self._list_font()).height() + 12

    def apply_theme(self):
        """다크/라이트 전환 시 창 배경·글자색을 현재 테마로 갱신."""
        self.setStyleSheet(f"#calwin{{background:{theme.c('window_bg')};}}")
        self.lbl_day.setStyleSheet(self._day_label_css())
        self.lbl_hint.setStyleSheet(self._hint_css())
        self.cal.updateCells()
        # 목록의 라벨색도 테마 색이다 — 같이 다시 칠한다
        self._on_day_selected(self.cal.selectedDate())

    def _redraw(self):
        """달력 칸 + 아래 목록을 현재 self.events 기준으로 다시 그린다."""
        self._mark_dates()
        self._on_day_selected(self.cal.selectedDate())

    # ---- 로드 ----
    def reload(self):
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("불러오는 중…")
        epoch = self._epoch   # 조회 '시작' 시점의 세대

        def worker():
            # 1) 화면에 바로 필요한 '일정'을 먼저 조회 → 체감 속도 향상
            try:
                evs = google_client.fetch_calendar_events(self.auth, back_days=31, forward_days=62)
                self.sig_events.emit(evs, "", epoch)
            except Exception as e:
                self.sig_events.emit(None, str(e), epoch)
            # 2) [추가] 대화상자용 캘린더 목록은 뒤이어 조회(표시엔 불필요)
            try:
                cals = google_client.fetch_calendar_list(self.auth)
                self.sig_cals.emit(cals)
            except Exception:
                self.sig_cals.emit([])

        threading.Thread(target=worker, daemon=True).start()

    def _on_cals(self, cals):
        self.calendars = cals or []

    def _on_events(self, evs, err, fetch_epoch: int = 0):
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("새로고침")
        if evs is None:
            # 이미 메인 창 데이터로 표시 중이면 조용히 무시(모달로 방해하지 않음)
            if not self.events:
                QMessageBox.warning(self, config.APP_NAME, "일정을 불러오지 못했습니다:\n" + err)
            return
        self.events = self._merge_pending(evs, fetch_epoch)
        self._redraw()

    def _merge_pending(self, server: list, fetch_epoch: int) -> list:
        """서버 목록 위에, 아직 반영 확인이 안 된 방금 추가한 일정을 얹는다.

        이 조회가 등록보다 먼저 출발했다면(fetch_epoch < epoch) 새 일정이 없는 게
        당연하므로 유지한다 → 추가한 일정이 깜빡 사라졌다 나타나지 않는다.
        """
        now = datetime.now()
        alive, out = [], list(server)
        for p in self._pending:
            ev = p["ev"]
            if any(s.start == ev.start and s.summary == ev.summary for s in server):
                continue                       # 서버에 실제로 생김 → 임시본 폐기
            if p["epoch"] == 0 or fetch_epoch < p["epoch"] or now < p["deadline"]:
                alive.append(p)
                out.append(ev)
        self._pending = alive
        return sorted(out, key=lambda e: e.start)

    def _mark_dates(self):
        # 날짜별 일정명을 달력 칸에 직접 표시하도록 맵 구성
        by_date: dict = {}
        for ev in sorted(self.events, key=lambda e: e.start):
            d = ev.start.date()
            tm = "" if not ev.has_time else ev.start.strftime("%H:%M")
            by_date.setdefault(d, []).append((tm, ev.summary))
        self.cal.set_events(by_date)

    def _on_day_selected(self, qd: QDate):
        d = date(qd.year(), qd.month(), qd.day())
        # 요일은 한국어로. strftime("%a") 는 로캘을 타서 'Sun' 이 나온다
        # (한국어 프로그램에 영어 요일이 섞여 보였다).
        # config.DAY_NAMES 는 1=일 … 7=토 이고, isoweekday() 는 월=1 … 일=7 이라
        # %7+1 로 자리를 맞춘다.
        dow = config.DAY_NAMES[d.isoweekday() % 7 + 1]
        day_evs = sorted([e for e in self.events if e.start.date() == d],
                         key=lambda e: e.start)
        self.lbl_day.setText(f"{d:%Y-%m-%d} ({dow}) 일정  {len(day_evs)}건")
        self.lst.clear()
        if not day_evs:
            li = QListWidgetItem("(일정 없음) — 달력에서 날짜를 더블클릭하면 추가됩니다")
            li.setFont(self._list_font(bold=False))
            self.lst.addItem(li)
            return
        for i, e in enumerate(day_evs):
            li = QListWidgetItem(f"{e.time_text()}  {e.summary}")
            li.setData(Qt.UserRole, e)      # 수정/삭제에 쓸 원본 일정
            # 읽기 좋게 크게, 그리고 달력 칸과 **같은 색**으로 칠한다.
            # ⚠️ 색은 EventCalendar.chip_bg 를 그대로 쓴다. 두 곳이 같은 순서
            #    (e.start 로 정렬)로 도니 달력 칸의 셋째 띠가 목록의 셋째 줄과
            #    같은 색이 된다 — 색을 따로 고르면 이 짝이 어긋난다.
            li.setFont(self._list_font())
            li.setBackground(QColor(self.cal.chip_bg(i)))
            li.setForeground(QColor(theme.c("chip_text")))
            li.setSizeHint(QSize(0, self._list_row_h()))
            self.lst.addItem(li)

    # ---- 수정 / 삭제 ----
    def _selected_event(self):
        li = self.lst.currentItem()
        ev = li.data(Qt.UserRole) if li else None
        if ev is None:
            QMessageBox.information(self, config.APP_NAME,
                                    "아래 목록에서 일정을 먼저 선택하세요.")
            return None
        if not getattr(ev, "event_id", ""):
            QMessageBox.information(
                self, config.APP_NAME,
                "이 일정은 아직 구글에 등록 중이거나 식별할 수 없어\n"
                "수정·삭제할 수 없습니다. [새로고침] 후 다시 시도하세요.")
            return None
        return ev

    def _edit_selected(self):
        ev = self._selected_event()
        if ev is None:
            return
        cals = self.calendars or [{"id": ev.cal_id or "primary",
                                   "name": "내 캘린더", "primary": True}]
        dlg = AddEventDialog(ev.start.date(), cals, self, event=ev)
        if dlg.exec() != QDialog.Accepted:
            return
        vals = dlg.values()

        def worker():
            try:
                google_client.update_event(
                    self.auth, ev.cal_id, ev.event_id, vals["title"], vals["day"],
                    start_time=None if vals["all_day"] else vals["time"],
                    all_day=vals["all_day"], description=ev.description)
                self.sig_changed.emit("", "일정을 수정했습니다.")
            except Exception as e:
                self.sig_changed.emit(str(e), "")
        threading.Thread(target=worker, daemon=True).start()

    def _delete_selected(self):
        ev = self._selected_event()
        if ev is None:
            return
        if QMessageBox.question(
                self, config.APP_NAME,
                f"'{ev.summary}' 일정을 구글 캘린더에서 삭제할까요?\n"
                "삭제하면 휴대폰 등 다른 기기에서도 사라집니다.") != QMessageBox.Yes:
            return

        # 화면에서 먼저 지운다 (되돌리기는 실패 응답에서 새로고침으로 처리)
        self.events = [e for e in self.events
                       if getattr(e, "event_id", "") != ev.event_id]
        self._redraw()

        def worker():
            try:
                google_client.delete_event(self.auth, ev.cal_id, ev.event_id)
                self.sig_changed.emit("", "일정을 삭제했습니다.")
            except Exception as e:
                self.sig_changed.emit(str(e), "")
        threading.Thread(target=worker, daemon=True).start()

    def _on_changed(self, err: str, msg: str):
        """수정/삭제 결과 처리 — 어느 쪽이든 서버 기준으로 다시 맞춘다."""
        if err:
            QMessageBox.warning(self, config.APP_NAME, "실패했습니다:\n" + err)
        self._epoch += 1
        self.reload()

    # ---- 추가 ----
    def _add_for_selected(self):
        if getattr(self, "_adding", False):
            return                 # 앞의 추가가 아직 올라가는 중이다
        qd = self.cal.selectedDate()
        d = date(qd.year(), qd.month(), qd.day())
        # 캘린더 목록을 아직 못 받았어도 기본 캘린더로 바로 추가할 수 있게 한다
        cals = self.calendars or [{"id": "primary", "name": "내 캘린더", "primary": True}]
        dlg = AddEventDialog(d, cals, self)
        if dlg.exec() != QDialog.Accepted:
            return
        vals = dlg.values()
        d = vals["day"]          # 대화상자에서 날짜를 바꿨을 수 있다

        # ── 네트워크보다 먼저 화면에 그린다 (POST 가 오래 걸려도 즉시 보인다) ──
        if vals["all_day"]:
            start, has_time = datetime(d.year, d.month, d.day), False
        else:
            t = vals["time"]
            start, has_time = datetime(d.year, d.month, d.day, t.hour, t.minute), True
        ev = google_client.CalEvent(start=start, has_time=has_time,
                                    summary=vals["title"], uid="")
        pend = {"ev": ev, "epoch": 0,
                "deadline": datetime.now() + timedelta(seconds=PENDING_GRACE_SEC)}
        self._pending.append(pend)
        self.events = sorted(list(self.events) + [ev], key=lambda e: e.start)
        self._redraw()
        self._adding = True        # 예전엔 [추가] 단추를 잠갔다. 단추가 없어졌으니 깃발로.

        rmin = self._reminder_minutes()

        def worker():
            try:
                real = google_client.insert_event(
                    self.auth, vals["calendar_id"], vals["title"], d,
                    start_time=None if vals["all_day"] else vals["time"],
                    all_day=vals["all_day"], reminder_minutes=rmin)
                self.sig_added.emit(pend, real, "")
            except Exception as e:
                self.sig_added.emit(pend, None, str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _reminder_minutes(self):
        """부모(메인 창) 설정의 구글 캘린더 알림 분. 꺼져 있으면 None."""
        p = self.parent()
        try:
            if p is not None and hasattr(p, "_reminder_minutes"):
                return p._reminder_minutes()
        except Exception:
            pass
        return None

    def _on_added(self, pend, real, err: str):
        """일정 추가 결과 (UI 스레드)."""
        self._adding = False
        if err:
            # 롤백 — 미리 그려 둔 일정을 걷어낸다
            if pend in self._pending:
                self._pending.remove(pend)
            try:
                self.events.remove(pend["ev"])
            except ValueError:
                pass
            self._redraw()
            QMessageBox.warning(self, config.APP_NAME, "일정 추가 실패:\n" + err)
            return

        self._epoch += 1
        pend["epoch"] = self._epoch
        pend["deadline"] = datetime.now() + timedelta(seconds=PENDING_GRACE_SEC)
        # 서버가 돌려준 실제 일정으로 교체(uid 확보 → 팔로업 중복등록 방지에 도움)
        if real is not None:
            try:
                idx = self.events.index(pend["ev"])
                self.events[idx] = real
            except ValueError:
                pass
            pend["ev"] = real

        # 메인 창의 '이번주 일정'에는 네트워크 없이 바로 꽂아 넣는다
        parent = self.parent()
        if parent is not None and hasattr(parent, "add_optimistic_event"):
            try:
                parent.add_optimistic_event(pend["ev"])
            except Exception:
                pass
        # 서버 기준 재조회는 이 창에서 한 번만 (전체 재조회 2회 → 1회)
        QTimer.singleShot(1500, self.reload)
