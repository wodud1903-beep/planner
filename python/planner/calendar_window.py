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
    QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton, QTimeEdit,
    QVBoxLayout, QWidget,
)

from . import config, google_client, theme


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
        self.resize(560, 640)
        self.setWindowIcon(parent.windowIcon() if parent else self.windowIcon())

        v = QVBoxLayout(self)
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

        self.cal = QCalendarWidget()
        self.cal.setGridVisible(True)
        self.cal.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.cal.clicked.connect(self._on_day_selected)
        self.cal.activated.connect(lambda _d: self._add_for_selected())
        v.addWidget(self.cal)

        self.lbl_day = QLabel("날짜를 선택하세요")
        self.lbl_day.setStyleSheet("font-weight:bold;")
        v.addWidget(self.lbl_day)
        self.lst = QListWidget()
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
        # 이전 표시 초기화
        blank = QTextCharFormat()
        for qd in self._marked:
            self.cal.setDateTextFormat(qd, blank)
        self._marked = []
        fmt = QTextCharFormat()
        fmt.setFontWeight(75)
        fmt.setForeground(QColor(theme.c("accent")))
        seen = set()
        for ev in self.events:
            d = ev.start.date()
            qd = QDate(d.year, d.month, d.day)
            if qd not in seen:
                self.cal.setDateTextFormat(qd, fmt)
                self._marked.append(qd)
                seen.add(qd)

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
