"""구글 캘린더 창 — 월 달력을 보고 날짜를 클릭해 일정을 직접 추가.

- 달력(월 보기)에 일정이 있는 날을 굵게 표시
- 날짜 클릭 → 그 날의 일정 목록 표시
- 날짜 더블클릭 또는 [이 날짜에 일정 추가] → 구글 캘린더에 바로 등록(쓰기)
- [브라우저에서 열기] → 실제 구글 캘린더 웹으로 이동
"""

from __future__ import annotations

import threading
import webbrowser
from datetime import date, datetime, time

from PySide6.QtCore import QDate, Qt, QTime, Signal
from PySide6.QtGui import QColor, QTextCharFormat
from PySide6.QtWidgets import (
    QCalendarWidget, QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton, QSizePolicy,
    QTimeEdit, QVBoxLayout, QWidget,
)

from . import config, google_client, theme


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

        # 날짜 숫자 (토=파랑, 일=빨강)
        dow = qd.dayOfWeek()  # 1=월 .. 7=일
        if dow == 7:
            numcol = QColor("#D24B4B")
        elif dow == 6:
            numcol = QColor("#3D74C7")
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

        # 일정명
        evs = self._by_date.get(d, [])
        if evs:
            fe = painter.font()
            fe.setPointSize(8)
            fe.setBold(False)
            painter.setFont(fe)
            fm = painter.fontMetrics()
            line_h = fm.height() + 1
            top = rect.top() + 20
            avail = rect.height() - 22
            maxlines = max(0, avail // line_h)
            painter.setPen(QColor(theme.c("text")))
            shown = evs if len(evs) <= maxlines else evs[:max(0, maxlines - 1)]
            for i, (tm, summ) in enumerate(shown):
                label = (tm + " " if tm else "") + summ
                label = fm.elidedText(label, Qt.ElideRight, rect.width() - 8)
                painter.drawText(rect.left() + 4, top + i * line_h,
                                 rect.width() - 8, line_h,
                                 Qt.AlignLeft | Qt.AlignVCenter, label)
            if len(evs) > maxlines and maxlines >= 1:
                more = f"+{len(evs) - len(shown)}건"
                painter.setPen(QColor(theme.c("accent")))
                painter.drawText(rect.left() + 4, top + len(shown) * line_h,
                                 rect.width() - 8, line_h,
                                 Qt.AlignLeft | Qt.AlignVCenter, more)
        painter.restore()


class AddEventDialog(QDialog):
    def __init__(self, day: date, calendars: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"일정 추가 · {day.strftime('%Y-%m-%d (%a)')}")
        self.setMinimumWidth(380)
        self.day = day
        form = QFormLayout(self)

        self.ed_title = QLineEdit()
        form.addRow("제목", self.ed_title)

        self.cmb_cal = QComboBox()
        for c in calendars:
            label = ("★ " if c["primary"] else "") + c["name"]
            self.cmb_cal.addItem(label, c["id"])
        form.addRow("캘린더", self.cmb_cal)

        self.chk_allday = QCheckBox("종일")
        self.chk_allday.setChecked(True)
        self.chk_allday.toggled.connect(lambda on: self.dt_time.setEnabled(not on))
        form.addRow(self.chk_allday)

        self.dt_time = QTimeEdit()
        self.dt_time.setDisplayFormat("HH:mm")
        self.dt_time.setTime(QTime(9, 0))
        self.dt_time.setEnabled(False)
        form.addRow("시각", self.dt_time)

        row = QHBoxLayout()
        row.addStretch()
        ok = QPushButton("추가")
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
        return {
            "title": self.ed_title.text().strip(),
            "calendar_id": self.cmb_cal.currentData(),
            "all_day": self.chk_allday.isChecked(),
            "time": time(t.hour(), t.minute()),
        }


class CalendarWindow(QWidget):
    sig_events = Signal(object, str)   # (list[CalEvent] or None, error)
    sig_cals = Signal(object)          # list[dict]
    sig_added = Signal(object, str)    # (추가된 CalEvent or None, error)

    def __init__(self, auth: google_client.GoogleAuth, parent=None):
        super().__init__(parent)
        self.auth = auth
        self.calendars: list[dict] = []
        self.events: list[google_client.CalEvent] = []
        self._marked: list[QDate] = []

        self.setWindowTitle("구글 캘린더")
        # 메인 프로그램과 동일한 크기로 열어 칸을 크게(내용이 잘리지 않게)
        if parent is not None:
            self.resize(parent.width(), parent.height())
        else:
            self.resize(1040, 880)
        self.setWindowIcon(parent.windowIcon() if parent else self.windowIcon())
        # 뒤 창이 비치지 않도록 불투명 배경 + 스타일 배경 적용
        self.setObjectName("calwin")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"#calwin{{background:{theme.c('window_bg')};}}")

        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)
        top = QHBoxLayout()
        self.btn_add = QPushButton("이 날짜에 일정 추가")
        self.btn_add.clicked.connect(self._add_for_selected)
        self.btn_refresh = QPushButton("새로고침")
        self.btn_refresh.clicked.connect(self.reload)
        self.btn_web = QPushButton("브라우저에서 열기")
        self.btn_web.clicked.connect(lambda: webbrowser.open("https://calendar.google.com/"))
        self.btn_close = QPushButton("닫기")
        self.btn_close.clicked.connect(self.close)
        top.addWidget(self.btn_add)
        top.addWidget(self.btn_refresh)
        top.addStretch()
        top.addWidget(self.btn_web)
        top.addWidget(self.btn_close)
        v.addLayout(top)

        self.cal = EventCalendar()
        self.cal.clicked.connect(self._on_day_selected)
        self.cal.activated.connect(lambda _d: self._add_for_selected())
        v.addWidget(self.cal, 1)   # 남는 공간을 달력이 모두 차지 → 중간 빈칸 없음

        self.lbl_day = QLabel("날짜를 선택하면 아래에 그 날의 일정이 보입니다")
        self.lbl_day.setStyleSheet("font-weight:bold;")
        v.addWidget(self.lbl_day)
        self.lst = QListWidget()
        self.lst.setFixedHeight(120)   # 하단 상세 목록은 고정 높이(달력이 대부분 차지)
        v.addWidget(self.lst)

        self.sig_events.connect(self._on_events)
        self.sig_cals.connect(self._on_cals)
        self.sig_added.connect(self._on_added)
        self.reload()

    # ---- 로드 ----
    def reload(self):
        self.btn_refresh.setEnabled(False)

        def worker():
            try:
                cals = google_client.fetch_calendar_list(self.auth)
                self.sig_cals.emit(cals)
            except Exception:
                self.sig_cals.emit([])
            try:
                evs = google_client.fetch_calendar_events(self.auth, back_days=31, forward_days=62)
                self.sig_events.emit(evs, "")
            except Exception as e:
                self.sig_events.emit(None, str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_cals(self, cals):
        self.calendars = cals or []

    def _on_events(self, evs, err):
        self.btn_refresh.setEnabled(True)
        if evs is None:
            QMessageBox.warning(self, config.APP_NAME, "일정을 불러오지 못했습니다:\n" + err)
            return
        self.events = evs
        self._mark_dates()
        self._on_day_selected(self.cal.selectedDate())

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
        self.lbl_day.setText(d.strftime("%Y-%m-%d (%a) 일정"))
        self.lst.clear()
        day_evs = sorted([e for e in self.events if e.start.date() == d], key=lambda e: e.start)
        if not day_evs:
            self.lst.addItem("(일정 없음) — 더블클릭하거나 [이 날짜에 일정 추가]")
            return
        for e in day_evs:
            self.lst.addItem(f"{e.time_text()}  {e.summary}")

    # ---- 추가 ----
    def _add_for_selected(self):
        qd = self.cal.selectedDate()
        d = date(qd.year(), qd.month(), qd.day())
        if not self.calendars:
            QMessageBox.information(self, config.APP_NAME, "캘린더 목록을 아직 불러오는 중입니다.")
            return
        dlg = AddEventDialog(d, self.calendars, self)
        if dlg.exec() != QDialog.Accepted:
            return
        vals = dlg.values()
        self.btn_add.setEnabled(False)

        def worker():
            try:
                google_client.insert_event(
                    self.auth, vals["calendar_id"], vals["title"], d,
                    start_time=None if vals["all_day"] else vals["time"],
                    all_day=vals["all_day"])
            except Exception as e:
                self.sig_added.emit(None, str(e))
                return
            # 즉시 화면에 보이도록 낙관적 이벤트 구성
            if vals["all_day"]:
                start = datetime(d.year, d.month, d.day)
                has_time = False
            else:
                t = vals["time"]
                start = datetime(d.year, d.month, d.day, t.hour, t.minute)
                has_time = True
            ev = google_client.CalEvent(start=start, has_time=has_time,
                                        summary=vals["title"], uid="")
            self.sig_added.emit(ev, "")

        threading.Thread(target=worker, daemon=True).start()

    def _on_added(self, ev, err: str):
        """일정 추가 결과 (UI 스레드)."""
        self.btn_add.setEnabled(True)
        if err:
            QMessageBox.warning(self, config.APP_NAME, "일정 추가 실패:\n" + err)
            return
        # 1) 낙관적으로 즉시 반영
        if ev is not None:
            self.events.append(ev)
            self._mark_dates()
            self._on_day_selected(self.cal.selectedDate())
        # 2) 서버 기준으로 재조회(정확한 목록으로 갱신)
        self.reload()
        # 3) 메인 창의 이번주/할일 목록도 갱신
        parent = self.parent()
        if parent is not None and hasattr(parent, "fetch_all_async"):
            try:
                parent.fetch_all_async()
            except Exception:
                pass
