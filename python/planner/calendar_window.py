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

from PySide6.QtCore import QDate, Qt, QTime, QTimer, Signal
from PySide6.QtGui import QColor, QTextCharFormat
from PySide6.QtWidgets import (
    QCalendarWidget, QCheckBox, QComboBox, QDateEdit, QDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QSizePolicy, QTimeEdit, QVBoxLayout, QWidget,
)

from . import config, google_client, holiday, theme


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

        # 날짜 숫자 (일요일·공휴일(대체공휴일 포함)=빨강, 토=파랑)
        dow = qd.dayOfWeek()  # 1=월 .. 7=일
        if dow == 7 or holiday.is_holiday(d):
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
        self.btn_edit = QPushButton("선택 일정 수정")
        self.btn_edit.clicked.connect(self._edit_selected)
        self.btn_del = QPushButton("선택 일정 삭제")
        self.btn_del.clicked.connect(self._delete_selected)
        self.btn_refresh = QPushButton("새로고침")
        # '불러오는 중…' 으로 글자가 길어져도 잘리지 않게 폭을 미리 잡아 둔다
        self.btn_refresh.setMinimumWidth(110)
        self.btn_refresh.clicked.connect(self.reload)
        self.btn_web = QPushButton("브라우저에서 열기")
        self.btn_web.clicked.connect(lambda: webbrowser.open("https://calendar.google.com/"))
        self.btn_close = QPushButton("닫기")
        self.btn_close.clicked.connect(self.close)
        top.addWidget(self.btn_add)
        top.addWidget(self.btn_edit)
        top.addWidget(self.btn_del)
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
        # 배경색과 글자색이 겹쳐 안 보이는 문제 방지 → 색을 명시적으로 지정
        self.lbl_day.setStyleSheet(
            f"font-weight:bold;background:transparent;color:{theme.c('text')};")
        v.addWidget(self.lbl_day)
        self.lst = QListWidget()
        self.lst.setFixedHeight(120)   # 하단 상세 목록은 고정 높이(달력이 대부분 차지)
        self.lst.itemDoubleClicked.connect(lambda _i: self._edit_selected())
        v.addWidget(self.lst)

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

    def apply_theme(self):
        """다크/라이트 전환 시 창 배경·글자색을 현재 테마로 갱신."""
        self.setStyleSheet(f"#calwin{{background:{theme.c('window_bg')};}}")
        self.lbl_day.setStyleSheet(
            f"font-weight:bold;background:transparent;color:{theme.c('text')};")
        self.cal.updateCells()

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
        self.lbl_day.setText(d.strftime("%Y-%m-%d (%a) 일정"))
        self.lst.clear()
        day_evs = sorted([e for e in self.events if e.start.date() == d], key=lambda e: e.start)
        if not day_evs:
            self.lst.addItem("(일정 없음) — 더블클릭하거나 [이 날짜에 일정 추가]")
            return
        for e in day_evs:
            li = QListWidgetItem(f"{e.time_text()}  {e.summary}")
            li.setData(Qt.UserRole, e)      # 수정/삭제에 쓸 원본 일정
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
        self.btn_add.setEnabled(False)

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
        self.btn_add.setEnabled(True)
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
