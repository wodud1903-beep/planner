"""메인 화면 (델파이 uDash 이식).

탭1: 이번주 일정(구글 캘린더) + 내 할일(로컬 + 구글 Tasks)
탭2: PC 알람 (요일/시간 반복)
트레이 상주, 1초 타이머로 알람 감시, 시작 시 오늘 브리핑.
카카오톡 스케줄러는 제거했다.  구글 연동은 [Google 로그인] 한 번으로 끝난다.
"""

from __future__ import annotations

import sys
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QHBoxLayout, QHeaderView, QLabel,
    QMainWindow, QMenu, QMessageBox, QPushButton, QSystemTrayIcon, QTabWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import alarm_window, config, followup, google_client, hotkey
from .edit_dialog import EditDialog
from .icon import make_icon
from .models import (
    AppSettings, PcAlarm, TaskAlarm, TaskAlarmStore, TodoItem, load_list, save_list,
)
from .settings_dialog import SettingsDialog


def _startup_set() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run")
        try:
            winreg.QueryValueEx(key, config.APP_ID)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


def _set_startup(enable: bool):
    if sys.platform != "win32":
        return
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_SET_VALUE)
        try:
            if enable:
                winreg.SetValueEx(key, config.APP_ID, 0, winreg.REG_SZ,
                                  f'"{sys.executable}"')
            else:
                try:
                    winreg.DeleteValue(key, config.APP_ID)
                except FileNotFoundError:
                    pass
        finally:
            winreg.CloseKey(key)
    except Exception:
        pass


class MainWindow(QMainWindow):
    # 백그라운드 스레드 → UI 마샬링
    sig_tasks_done = Signal(object, str)
    sig_events_done = Signal(object, str)
    sig_fetch_done = Signal()
    sig_toast = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(config.APP_NAME)
        # 최대화 버튼 제거 + 크기 고정 (가로폭만 조금 넓힘)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, False)
        self.setFixedSize(1040, 720)

        # 데이터
        self.todo_file = config.data_file("todos.json")
        self.alarm_file = config.data_file("pcalarms.json")
        self.taskalarm_file = config.data_file("taskalarms.json")
        self.cfg_file = config.data_file("plan_cfg.json")
        self.followup_file = config.data_file("followups.json")
        self.todos: list[TodoItem] = load_list(self.todo_file, TodoItem)
        self.alarms: list[PcAlarm] = load_list(self.alarm_file, PcAlarm)
        self.task_alarms = TaskAlarmStore(self.taskalarm_file)
        self.settings = AppSettings.load(self.cfg_file)
        self.followup_tracker = followup.FollowupTracker(self.followup_file)
        self.gauth = google_client.GoogleAuth(config.data_file("google_token.json"))
        self.cal_events: list[google_client.CalEvent] = []
        self.gtasks: list[google_client.GoogleTask] = []
        self.week_dates: list[date | None] = []
        self.todo_dates: list[date | None] = []
        self.alarm_stack = 0
        self.last_backup: date | None = None
        self.last_fetch = datetime.min
        self._really_close = False
        self._app_icon = make_icon()

        self.setWindowIcon(self._app_icon)
        self._build_ui()
        self._build_tray()

        self.sig_tasks_done.connect(self._on_tasks_done)
        self.sig_events_done.connect(self._on_events_done)
        self.sig_fetch_done.connect(self._on_fetch_done)
        self.sig_toast.connect(self._toast)

        self.refresh_todo()
        self.refresh_alarm()
        self.update_google_status()
        self.chk_autofetch.setChecked(self.settings.auto_fetch)

        # 시작 시 자동 백업 + 연결돼 있으면 불러오기
        self._startup_brief_pending = True
        self._backup(manual=False)
        if self.gauth.is_connected():
            # 로딩(수 초)이 끝난 뒤 브리핑을 띄운다 (0건으로 뜨는 것 방지).
            # 네트워크 지연 대비: 최대 12초 뒤에는 강제로 표시.
            self.fetch_all_async()
            QTimer.singleShot(12000, self._do_startup_brief)
        else:
            # 구글 미연결이면 로딩할 게 없으니 바로 표시
            QTimer.singleShot(600, self._do_startup_brief)

        self.chk_startup.setChecked(_startup_set())

        # 전역 단축키 (Windows)
        self.hotkeys = hotkey.HotkeyManager(
            QApplication.instance(), int(self.winId()), self._on_hotkey)
        QTimer.singleShot(0, lambda: self.hotkeys.apply(self.settings))

        # 1초 타이머
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)
        self.timer.start(1000)

    def _do_startup_brief(self):
        """시작 브리핑을 한 번만 표시 (데이터 로딩 후 또는 타임아웃 시)."""
        if not self._startup_brief_pending:
            return
        self._startup_brief_pending = False
        self.show_briefing(manual=False)

    def _on_hotkey(self):
        self.show_window()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 상단 바
        top = QWidget()
        top.setFixedHeight(52)
        top.setStyleSheet(f"background:{config.COLOR_TOPBAR};")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(16, 0, 16, 0)
        title = QLabel(config.APP_NAME)
        title.setStyleSheet("color:white;font-size:19px;font-weight:bold;")
        tl.addWidget(title)
        tl.addStretch()
        self.chk_startup = QCheckBox("PC 시작 시 실행")
        self.chk_startup.setStyleSheet("color:white;")
        self.chk_startup.toggled.connect(lambda on: _set_startup(on))
        tl.addWidget(self.chk_startup)
        outer.addWidget(top)

        # 탭
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs)
        self.tabs.addTab(self._build_main_tab(), "일정 / 할일")
        self.tabs.addTab(self._build_alarm_tab(), "PC 알람")

    def _build_main_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        # 상단 조작줄
        row = QHBoxLayout()
        self.btn_settings = QPushButton("설정")
        self.btn_settings.clicked.connect(self.on_settings_click)
        row.addWidget(self.btn_settings)
        self.btn_fetch = QPushButton("새로고침")
        self.btn_fetch.clicked.connect(self.fetch_all_async)
        row.addWidget(self.btn_fetch)
        self.lbl_status = QLabel("")
        row.addWidget(self.lbl_status)
        row.addStretch()
        self.chk_autofetch = QCheckBox("30분 자동갱신")
        self.chk_autofetch.toggled.connect(self._on_autofetch_toggled)
        row.addWidget(self.chk_autofetch)
        v.addLayout(row)

        # 이번주 일정
        self.lbl_week = QLabel("이번주 일정")
        v.addWidget(self.lbl_week)
        self.tbl_week = self._make_table(["날짜", "시각", "구분", "내용"], [130, 80, 80, 620])
        self.tbl_week.setMaximumHeight(250)
        v.addWidget(self.tbl_week)

        # 내 할일 조작줄
        trow = QHBoxLayout()
        trow.addWidget(QLabel("내 할일"))
        for text, slot in [
            ("추가", self.on_todo_add), ("수정", self.on_todo_edit),
            ("삭제", self.on_todo_del), ("완료", self.on_todo_done),
            ("멘트 복사", self.on_todo_copy),
        ]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            trow.addWidget(b)
        trow.addStretch()
        v.addLayout(trow)

        self.tbl_todo = self._make_table(
            ["날짜", "시각", "할일", "알람", "멘트"], [120, 80, 400, 60, 220])
        self.tbl_todo.doubleClicked.connect(lambda _i: self.on_todo_edit())
        v.addWidget(self.tbl_todo)
        return w

    def _build_alarm_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        row = QHBoxLayout()
        for text, slot in [
            ("추가", self.on_alarm_add), ("수정", self.on_alarm_edit),
            ("삭제", self.on_alarm_del), ("미리보기", self.on_alarm_test),
        ]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch()
        v.addLayout(row)
        self.tbl_alarm = self._make_table(
            ["사용", "이름", "요일", "시각", "멘트"], [50, 200, 120, 80, 480])
        self.tbl_alarm.doubleClicked.connect(lambda _i: self.on_alarm_edit())
        v.addWidget(self.tbl_alarm)
        return w

    def _make_table(self, headers, widths) -> QTableWidget:
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.SingleSelection)
        t.setShowGrid(True)
        for i, wdt in enumerate(widths):
            t.setColumnWidth(i, wdt)
        t.horizontalHeader().setStretchLastSection(True)
        return t

    def _build_tray(self):
        self.tray = QSystemTrayIcon(self._app_icon, self)
        self.tray.setToolTip(config.APP_NAME)
        menu = QMenu()
        acts = [
            ("창 열기", self.show_window),
            ("오늘 브리핑", lambda: self.show_briefing(manual=True)),
            ("지금 백업", lambda: self._backup(manual=True)),
            (None, None),
            ("종료", self.quit_app),
        ]
        for text, slot in acts:
            if text is None:
                menu.addSeparator()
                continue
            a = QAction(text, self)
            a.triggered.connect(slot)
            menu.addAction(a)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self.show_window() if r == QSystemTrayIcon.DoubleClick else None)
        self.tray.show()

    # ------------------------------------------------------------ 구글 연동
    def update_google_status(self):
        if self.gauth.is_connected():
            self.lbl_status.setText("구글: 연결됨  (설정에서 로그인/로그아웃)")
            self.lbl_status.setStyleSheet("color:green;")
        else:
            self.lbl_status.setText("구글: 로그인 필요  ([설정] → Google 로그인)")
            self.lbl_status.setStyleSheet("color:#c00;")

    def _on_autofetch_toggled(self, on: bool):
        self.settings.auto_fetch = on
        self.settings.save(self.cfg_file)

    def on_settings_click(self):
        was_connected = self.gauth.is_connected()
        dlg = SettingsDialog(self.gauth, self.settings, self)
        accepted = dlg.exec() == SettingsDialog.Accepted
        if accepted:
            self.settings.save(self.cfg_file)
            self.hotkeys.apply(self.settings)
            self.followup_tracker.last_scan = None  # 설정이 바뀌었으니 다시 스캔
        self.update_google_status()
        # 로그인/로그아웃이 있었으면 데이터 갱신
        if dlg.tasks_changed or (was_connected != self.gauth.is_connected()):
            if self.gauth.is_connected():
                self.fetch_all_async()
            else:
                self.cal_events = []
                self.gtasks = []
                self.refresh_calendar()
                self.refresh_todo()
        elif accepted:
            # 설정만 바뀐 경우에도 팔로업 재스캔
            self._run_followups()

    def fetch_all_async(self):
        if not self.gauth.is_connected():
            QMessageBox.information(
                self, config.APP_NAME,
                "먼저 [Google 로그인] 을 눌러 구글 계정에 연결하세요.")
            return
        self.btn_fetch.setEnabled(False)
        self.last_fetch = datetime.now()

        def worker():
            try:
                events = google_client.fetch_calendar_events(self.gauth)
                self.sig_events_done.emit(events, "")
            except Exception as e:
                self.sig_events_done.emit(None, str(e))
            try:
                tasks = google_client.fetch_tasks(self.gauth)
                self.sig_tasks_done.emit(tasks, "")
            except Exception as e:
                self.sig_tasks_done.emit(None, str(e))
            # 캘린더·할일 두 갱신 신호가 처리된 뒤 마지막으로 완료 신호
            self.sig_fetch_done.emit()

        threading.Thread(target=worker, daemon=True).start()

    def _on_fetch_done(self):
        # 시작 브리핑이 대기 중이면 데이터가 채워진 지금 표시
        self._do_startup_brief()

    def _on_events_done(self, events, err: str):
        self.btn_fetch.setEnabled(True)
        if events is not None:
            self.cal_events = events
            self.refresh_calendar()
            self._run_followups()

    def _run_followups(self):
        """캘린더에서 팔로업 대상을 찾아 내 할일로 자동 등록."""
        added = followup.check_followups(
            self.settings, self.cal_events, self.todos, self.followup_tracker)
        if added > 0:
            save_list(self.todo_file, self.todos)
            self.followup_tracker.save()
            self.refresh_todo()
            self.sig_toast.emit("팔로업 자동 등록", f"{added}건을 [내 할일]에 추가했습니다.")

    def _on_tasks_done(self, tasks, err: str):
        if tasks is not None:
            self.gtasks = tasks
            self.refresh_todo()

    # ------------------------------------------------------------ 캘린더 뷰
    def refresh_calendar(self):
        self.tbl_week.setRowCount(0)
        self.week_dates = []
        today = date.today()
        week_end = today + timedelta(days=7)
        for ev in self.cal_events:
            d = ev.start.date()
            if not (today <= d < week_end):
                continue
            r = self.tbl_week.rowCount()
            self.tbl_week.insertRow(r)
            vals = [ev.start.strftime("%m-%d(%a)"), ev.time_text(), "일정", ev.summary]
            for c, val in enumerate(vals):
                self.tbl_week.setItem(r, c, QTableWidgetItem(val))
            self.week_dates.append(d)
            self._colorize_row(self.tbl_week, r, d)
        self.lbl_week.setText(f"이번주 일정  {self.tbl_week.rowCount()}건")

    def _colorize_row(self, table: QTableWidget, row: int, d: date | None):
        if d is None:
            return
        today = date.today()
        color = None
        bold = False
        if d == today:
            color = QColor(config.COLOR_TODAY)
            bold = True
        elif d == today + timedelta(days=1):
            color = QColor(config.COLOR_TOMORROW)
            bold = True
        if color is None:
            return
        for c in range(table.columnCount()):
            it = table.item(row, c)
            if it is None:
                continue
            it.setBackground(color)
            it.setForeground(QColor("#000000"))
            if bold:
                f = it.font()
                f.setBold(True)
                it.setFont(f)

    # ------------------------------------------------------------ 할일 뷰
    def refresh_todo(self):
        self.tbl_todo.setRowCount(0)
        self.todo_dates = []
        today = date.today()

        # (grp, sortdate, is_google, obj)
        rows = []
        for it in self.todos:
            if it.run_date and it.run_date < today - timedelta(days=7):
                continue
            grp, sd = self._group(True, it.run_date, today)
            rows.append((grp, sd, False, it))
        for tk in self.gtasks:
            if tk.has_due and tk.due and tk.due < today - timedelta(days=7):
                continue
            grp, sd = self._group(tk.has_due, tk.due, today)
            rows.append((grp, sd, True, tk))

        def sort_key(row):
            grp, sd, is_g, obj = row
            base = sd or date.min
            if grp == 1:  # 지난 일정: 최근 과거 우선(내림차순)
                ordv = date.max.toordinal() - base.toordinal()
            else:
                ordv = base.toordinal()
            return (grp, ordv)

        rows.sort(key=sort_key)

        for grp, sd, is_google, obj in rows:
            r = self.tbl_todo.rowCount()
            self.tbl_todo.insertRow(r)
            if not is_google:
                it: TodoItem = obj
                title = ("[완료] " if it.done else "") + it.title
                ment = it.ment.replace("\n", " ")[:60]
                vals = [it.days_text(),
                        it.run_time.strftime("%H:%M") if it.has_time else "-",
                        title, "ON" if it.alarm else "", ment]
                self.todo_dates.append(it.run_date)
                key = ("local", id(it))
            else:
                tk: google_client.GoogleTask = obj
                a = self.task_alarms.find(tk.id)
                day = tk.due.strftime("%m-%d(%a)") if (tk.has_due and tk.due) else "기한없음"
                tm = a.run_time.strftime("%H:%M") if (a and a.alarm) else "-"
                on = "ON" if (a and a.alarm) else ""
                if a and a.ment.strip():
                    ment = a.ment.replace("\n", " ")[:60]
                else:
                    ment = (tk.notes or "").replace("\n", " ")[:60]
                vals = [day, tm, "[구글] " + tk.title, on, ment]
                self.todo_dates.append(tk.due if tk.has_due else None)
                key = ("google", tk.id)
            for c, val in enumerate(vals):
                item = QTableWidgetItem(val)
                if c == 0:
                    item.setData(Qt.UserRole, key)
                self.tbl_todo.setItem(r, c, item)
            self._colorize_row(self.tbl_todo, r, self.todo_dates[-1])

    def _group(self, has_due: bool, due: date | None, today: date):
        if not has_due or due is None:
            return 2, None
        if due >= today:
            return 0, due
        return 1, due

    def _sel_todo_key(self):
        r = self.tbl_todo.currentRow()
        if r < 0:
            return None
        it = self.tbl_todo.item(r, 0)
        return it.data(Qt.UserRole) if it else None

    def _sel_local_todo(self) -> TodoItem | None:
        key = self._sel_todo_key()
        if not key or key[0] != "local":
            return None
        for it in self.todos:
            if id(it) == key[1]:
                return it
        return None

    def _sel_gtask(self) -> "google_client.GoogleTask | None":
        key = self._sel_todo_key()
        if not key or key[0] != "google":
            return None
        for tk in self.gtasks:
            if tk.id == key[1]:
                return tk
        return None

    # ------------------------------------------------------------ 할일 조작
    def on_todo_add(self):
        # 구글 연결 시 구글 Tasks 에 등록, 아니면 로컬
        if self.gauth.is_connected():
            tmp = TaskAlarm()
            ok, title, notes, due, has_due = EditDialog.edit_google_task(
                "할일 추가 (구글 Tasks)", "", "", date.today(), True, tmp, self)
            if not ok or not title.strip():
                return
            try:
                google_client.insert_task(self.gauth, "", title, notes, due if has_due else None)
            except Exception as e:
                QMessageBox.warning(self, config.APP_NAME, "구글 할일 추가 실패:\n" + str(e))
                return
            self._pending_alarm = (title, tmp)
            self.fetch_all_async()
            return
        it = TodoItem()
        if EditDialog.edit_todo(it, self):
            self.todos.append(it)
            save_list(self.todo_file, self.todos)
            self.refresh_todo()

    def on_todo_edit(self):
        gt = self._sel_gtask()
        if gt is not None:
            a = self.task_alarms.ensure(gt.id)
            ok, title, notes, due, has_due = EditDialog.edit_google_task(
                "할일 수정 (구글 Tasks)", gt.title, gt.notes, gt.due, gt.has_due, a, self)
            if not ok or not title.strip():
                return
            try:
                google_client.update_task(self.gauth, gt.list_id, gt.id, title, notes, due, has_due)
            except Exception as e:
                QMessageBox.warning(self, config.APP_NAME, "수정 실패:\n" + str(e))
                return
            self.task_alarms.save()
            self.fetch_all_async()
            return
        it = self._sel_local_todo()
        if it is None:
            return
        if EditDialog.edit_todo(it, self):
            save_list(self.todo_file, self.todos)
            self.refresh_todo()

    def on_todo_del(self):
        gt = self._sel_gtask()
        if gt is not None:
            if QMessageBox.question(self, config.APP_NAME, "이 구글 할일을 삭제할까요?") != QMessageBox.Yes:
                return
            try:
                google_client.delete_task(self.gauth, gt.list_id, gt.id)
            except Exception as e:
                QMessageBox.warning(self, config.APP_NAME, "삭제 실패:\n" + str(e))
                return
            self.fetch_all_async()
            return
        it = self._sel_local_todo()
        if it is None:
            return
        if QMessageBox.question(self, config.APP_NAME, "이 할일을 삭제할까요?") != QMessageBox.Yes:
            return
        self.todos.remove(it)
        save_list(self.todo_file, self.todos)
        self.refresh_todo()

    def on_todo_done(self):
        gt = self._sel_gtask()
        if gt is not None:
            try:
                google_client.complete_task(self.gauth, gt.list_id, gt.id)
            except Exception as e:
                QMessageBox.warning(self, config.APP_NAME, "완료 처리 실패:\n" + str(e))
                return
            self.fetch_all_async()
            return
        it = self._sel_local_todo()
        if it is None:
            return
        it.done = not it.done
        save_list(self.todo_file, self.todos)
        self.refresh_todo()

    def on_todo_copy(self):
        it = self._sel_local_todo()
        ment = ""
        if it is not None:
            ment = it.ment
        else:
            gt = self._sel_gtask()
            if gt is not None:
                a = self.task_alarms.find(gt.id)
                ment = (a.ment if (a and a.ment.strip()) else gt.notes) or ""
        if ment.strip():
            QApplication.clipboard().setText(ment)
            self.sig_toast.emit(config.APP_NAME, "멘트를 클립보드에 복사했습니다.")

    def _apply_pending_alarm(self):
        """구글 추가 직후, 방금 만든 항목에 알람 설정을 붙인다."""
        pend = getattr(self, "_pending_alarm", None)
        if not pend:
            return
        title, src = pend
        self._pending_alarm = None
        found = None
        for tk in self.gtasks:
            if tk.title == title:
                found = tk
        if found is None:
            return
        a = self.task_alarms.ensure(found.id)
        a.alarm = src.alarm
        a.run_time = src.run_time
        a.ment = src.ment
        self.task_alarms.save()
        self.refresh_todo()

    # ------------------------------------------------------------ PC 알람
    def refresh_alarm(self):
        self.tbl_alarm.setRowCount(0)
        for al in self.alarms:
            r = self.tbl_alarm.rowCount()
            self.tbl_alarm.insertRow(r)
            vals = ["ON" if al.enabled else "OFF", al.title, al.days_text(),
                    al.run_time.strftime("%H:%M"), al.ment.replace("\n", " ")[:80]]
            for c, val in enumerate(vals):
                item = QTableWidgetItem(val)
                if c == 0:
                    item.setData(Qt.UserRole, id(al))
                self.tbl_alarm.setItem(r, c, item)

    def _sel_alarm(self) -> PcAlarm | None:
        r = self.tbl_alarm.currentRow()
        if r < 0:
            return None
        it = self.tbl_alarm.item(r, 0)
        if not it:
            return None
        key = it.data(Qt.UserRole)
        for al in self.alarms:
            if id(al) == key:
                return al
        return None

    def on_alarm_add(self):
        al = PcAlarm()
        if EditDialog.edit_alarm(al, self):
            self.alarms.append(al)
            save_list(self.alarm_file, self.alarms)
            self.refresh_alarm()

    def on_alarm_edit(self):
        al = self._sel_alarm()
        if al is None:
            return
        if EditDialog.edit_alarm(al, self):
            save_list(self.alarm_file, self.alarms)
            self.refresh_alarm()

    def on_alarm_del(self):
        al = self._sel_alarm()
        if al is None:
            return
        if QMessageBox.question(self, config.APP_NAME, "이 알람을 삭제할까요?") != QMessageBox.Yes:
            return
        self.alarms.remove(al)
        save_list(self.alarm_file, self.alarms)
        self.refresh_alarm()

    def on_alarm_test(self):
        al = self._sel_alarm()
        if al is None:
            QMessageBox.information(self, config.APP_NAME, "미리볼 알람을 선택하세요.")
            return
        self.fire_alarm(al.title, al.ment)

    # ------------------------------------------------------------ 알람 발생
    def fire_alarm(self, title: str, ment: str):
        alarm_window.popup(title, ment, self.alarm_stack)
        self.alarm_stack += 1
        if self.alarm_stack > 4:
            self.alarm_stack = 0

    def check_alarms(self):
        now = datetime.now()
        # 1) 로컬 할일
        changed = False
        for todo in self.todos:
            if todo.due_alarm(now):
                todo.last_alarm = now
                self.fire_alarm("[할일] " + todo.title, todo.ment)
                changed = True
        if changed:
            save_list(self.todo_file, self.todos)
            self.refresh_todo()
        # 2) PC 알람
        changed = False
        for al in self.alarms:
            if al.due_now(now):
                al.last_fire = now
                self.fire_alarm("[알람] " + al.title, al.ment)
                changed = True
        if changed:
            save_list(self.alarm_file, self.alarms)
            self.refresh_alarm()
        # 3) 구글 Tasks 알람
        changed = False
        for tk in self.gtasks:
            a = self.task_alarms.find(tk.id)
            if a and a.due_alarm(now, tk.due, tk.has_due):
                a.last_alarm = now
                self.fire_alarm("[할일] " + tk.title, a.ment)
                changed = True
        if changed:
            self.task_alarms.save()
        # 4) 구글 캘린더 시간 일정 (정시)
        for ev in self.cal_events:
            if (ev.has_time and ev.start.date() == now.date()
                    and ev.start.hour == now.hour and ev.start.minute == now.minute
                    and now.second < 2):
                self.fire_alarm("[구글] " + ev.summary, "")

    def _on_tick(self):
        self.check_alarms()
        today = date.today()
        if self.last_backup != today:
            self._backup(manual=False)
        if self.chk_autofetch.isChecked() and self.gauth.is_connected():
            if (datetime.now() - self.last_fetch).total_seconds() >= 1800:
                self.fetch_all_async()
        # 구글 추가 직후 알람 매핑 반영
        if getattr(self, "_pending_alarm", None) and self.gtasks:
            self._apply_pending_alarm()

    # ------------------------------------------------------------ 브리핑
    def build_briefing(self) -> str:
        today = date.today()
        lines = [datetime.now().strftime("%Y년 %m월 %d일 (%a)"), ""]
        lines.append("[오늘 일정]")
        cnt_cal = 0
        for ev in self.cal_events:
            if ev.start.date() == today:
                lines.append(f"  · {ev.time_text()}  {ev.summary}")
                cnt_cal += 1
        if cnt_cal == 0:
            lines.append("  (없음)")
        lines += ["", "[오늘 할일]"]
        cnt_todo = 0
        for it in self.todos:
            if not it.done and it.run_date == today:
                lines.append(f"  · {it.run_time.strftime('%H:%M')}  {it.title}")
                cnt_todo += 1
        for tk in self.gtasks:
            if tk.has_due and tk.due == today:
                lines.append(f"  · {tk.title}")
                cnt_todo += 1
        if cnt_todo == 0:
            lines.append("  (없음)")
        lines += ["", f"일정 {cnt_cal}건 / 할일 {cnt_todo}건"]
        return "\n".join(lines)

    def show_briefing(self, manual: bool):
        alarm_window.popup("오늘 브리핑", self.build_briefing(), 0, siren=False)

    # ------------------------------------------------------------ 백업
    def _backup(self, manual: bool):
        bk_dir = config.data_dir() / "backup"
        bk_dir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        for f in (self.todo_file, self.alarm_file, self.taskalarm_file):
            if f.exists():
                try:
                    (bk_dir / f"{stamp}_{f.name}").write_bytes(f.read_bytes())
                except Exception:
                    pass
        # 30일 지난 백업 정리
        cutoff = datetime.now() - timedelta(days=30)
        for old in bk_dir.glob("*.json"):
            try:
                if datetime.fromtimestamp(old.stat().st_mtime) < cutoff:
                    old.unlink()
            except Exception:
                pass
        self.last_backup = date.today()
        if manual:
            self.sig_toast.emit(config.APP_NAME, f"백업 완료: {bk_dir}")

    # ------------------------------------------------------------ 트레이/종료
    def _toast(self, title: str, text: str):
        self.tray.showMessage(title, text, self._app_icon, 4000)

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        if self._really_close:
            event.accept()
            return
        box = QMessageBox(self)
        box.setWindowTitle(config.APP_NAME)
        box.setText("창을 닫습니다.")
        box.setInformativeText("[트레이로] 최소화하면 알람이 계속 동작합니다.")
        b_tray = box.addButton("트레이로", QMessageBox.AcceptRole)
        b_quit = box.addButton("완전 종료", QMessageBox.DestructiveRole)
        box.addButton("취소", QMessageBox.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked == b_tray:
            event.ignore()
            self.hide()
            self.tray.showMessage(config.APP_NAME, "트레이에서 계속 실행 중입니다.",
                                  self._app_icon, 3000)
        elif clicked == b_quit:
            self._shutdown()
            event.accept()
            QApplication.quit()
        else:
            event.ignore()

    def quit_app(self):
        if QMessageBox.question(
                self, config.APP_NAME,
                "프로그램을 종료하면 알람이 모두 중지됩니다. 종료할까요?") != QMessageBox.Yes:
            return
        self._really_close = True
        self._shutdown()
        self.close()
        QApplication.quit()

    def _shutdown(self):
        self.timer.stop()
        try:
            self.hotkeys.release()
        except Exception:
            pass
        alarm_window.close_all()
        self.tray.hide()
