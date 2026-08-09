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
from PySide6.QtGui import QAction, QColor, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QHBoxLayout, QHeaderView,
    QLabel, QMainWindow, QMenu, QMessageBox, QPushButton, QSystemTrayIcon, QTabWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import alarm_window, config, followup, google_client, hotkey, sync, theme, updater
from .calendar_window import CalendarWindow
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
    sig_account = Signal(str)          # 로그인 계정 이메일 확인됨
    sig_synced = Signal(bool)          # Drive 동기화 완료(변경 여부)
    sig_update = Signal(object, str, bool)  # (릴리스정보|None, 오류, 수동여부)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(config.APP_NAME)
        # 최대화 버튼 제거 + 크기 고정. 세로를 늘려 '내 할일'을 더 많이 보이게.
        # 단, 작은 화면에서도 잘리지 않도록 화면 크기에 맞춰 고정값을 정한다.
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, False)
        _avail = QGuiApplication.primaryScreen().availableGeometry()
        _w = min(1040, _avail.width() - 20)
        _h = min(920, _avail.height() - 60)
        self.setFixedSize(_w, _h)

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
        self._range = "all"           # 빠른 필터 기본값: 전체 (week/next/all)
        self._cal_win = None          # 캘린더 창 참조
        self.account_email = ""
        self._app_icon = make_icon()

        # 저장된 테마 반영
        theme.set_theme(self.settings.dark_mode)

        self.setWindowIcon(self._app_icon)
        self._build_ui()
        self._build_tray()

        self.sig_tasks_done.connect(self._on_tasks_done)
        self.sig_events_done.connect(self._on_events_done)
        self.sig_fetch_done.connect(self._on_fetch_done)
        self.sig_toast.connect(self._toast)
        self.sig_account.connect(self._on_account_ready)
        self.sig_synced.connect(self._on_synced)
        self.sig_update.connect(self._on_update_checked)

        # 동기화 푸시 디바운스 타이머
        self._sync_timer = QTimer(self)
        self._sync_timer.setSingleShot(True)
        self._sync_timer.timeout.connect(self._do_sync_push)

        self.refresh_todo()
        self.refresh_alarm()
        self.update_google_status()
        self.chk_autofetch.setChecked(self.settings.auto_fetch)
        self._last_seen_mtime = self._data_mtime()

        # 시작 시 자동 백업 + 연결 시 계정확인→동기화→불러오기
        self._startup_brief_pending = True
        self._backup(manual=False)
        if self.gauth.is_connected():
            self._start_account_sync()               # 끝에서 fetch_all_async 호출
            QTimer.singleShot(15000, self._do_startup_brief)  # 네트워크 지연 대비
        else:
            QTimer.singleShot(600, self._do_startup_brief)

        # 시작 시 조용히 업데이트 확인
        QTimer.singleShot(4000, lambda: self.check_update(manual=False))

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

    # ------------------------------------------------------------ 테마
    def _apply_topbar_theme(self):
        self._topbar.setStyleSheet(
            f"background:{theme.c('topbar')};border-bottom:1px solid {theme.c('border')};")
        self._title_lbl.setStyleSheet(
            f"color:{theme.c('topbar_text')};font-size:19px;font-weight:bold;background:transparent;")
        self.lbl_account.setStyleSheet(
            f"color:{theme.c('subtext')};background:transparent;")
        self.chk_startup.setStyleSheet(
            f"color:{theme.c('topbar_text')};background:transparent;")

    def apply_theme(self):
        theme.set_theme(self.settings.dark_mode)
        app = QApplication.instance()
        if app:
            app.setStyleSheet(theme.qss())
        self._apply_topbar_theme()
        self.refresh_calendar()
        self.refresh_todo()
        self.refresh_alarm()

    # ------------------------------------------------------------ 계정 / 동기화
    def _start_account_sync(self):
        def worker():
            email = ""
            try:
                email = google_client.get_user_email(self.gauth)
            except Exception:
                email = ""
            self.sig_account.emit(email)
        threading.Thread(target=worker, daemon=True).start()

    def _on_account_ready(self, email: str):
        if email:
            self.account_email = email
            config.set_account(email)
            self.lbl_account.setText(f"· {email}")
            sync.migrate_legacy()
            self.reload_data()   # 계정 폴더 기준으로 다시 로드
        # Drive 에서 최신본 받아오기(백그라운드)
        def worker():
            changed = False
            try:
                changed = sync.pull(self.gauth)
            except Exception:
                changed = False
            self.sig_synced.emit(changed)
        threading.Thread(target=worker, daemon=True).start()

    def _on_synced(self, changed: bool):
        if changed:
            self.reload_data()
            self.sig_toast.emit(config.APP_NAME, "다른 PC의 변경사항을 동기화했습니다.")
        # 원격 초기 시드/수렴을 위해 로컬 상태를 한 번 업로드 예약
        self._touch_sync()
        self.fetch_all_async()

    def reload_data(self):
        """현재 데이터 폴더에서 모델을 다시 읽고 UI/설정을 갱신."""
        self.todo_file = config.data_file("todos.json")
        self.alarm_file = config.data_file("pcalarms.json")
        self.taskalarm_file = config.data_file("taskalarms.json")
        self.cfg_file = config.data_file("plan_cfg.json")
        self.followup_file = config.data_file("followups.json")
        self.todos = load_list(self.todo_file, TodoItem)
        self.alarms = load_list(self.alarm_file, PcAlarm)
        self.task_alarms = TaskAlarmStore(self.taskalarm_file)
        self.settings = AppSettings.load(self.cfg_file)
        self.followup_tracker = followup.FollowupTracker(self.followup_file)
        # 설정 파생 UI 반영
        self.chk_autofetch.blockSignals(True)
        self.chk_autofetch.setChecked(self.settings.auto_fetch)
        self.chk_autofetch.blockSignals(False)
        self.apply_theme()
        try:
            self.hotkeys.apply(self.settings)
        except Exception:
            pass
        self._last_seen_mtime = self._data_mtime()

    def _touch_sync(self):
        """데이터 변경 후 호출 → 잠시 뒤 Drive 로 업로드(디바운스)."""
        if self.gauth.is_connected():
            self._sync_timer.start(2500)

    def _data_mtime(self) -> float:
        m = 0.0
        for f in (self.todo_file, self.alarm_file, self.taskalarm_file,
                  self.cfg_file, self.followup_file):
            try:
                if f.exists():
                    m = max(m, f.stat().st_mtime)
            except Exception:
                pass
        return m

    def _maybe_autosync(self):
        """로컬 데이터 파일이 바뀌었으면(어느 경로로든) 업로드 예약."""
        if not self.gauth.is_connected():
            return
        m = self._data_mtime()
        if m > self._last_seen_mtime + 0.001:
            self._last_seen_mtime = m
            self._touch_sync()

    def _do_sync_push(self):
        if not self.gauth.is_connected():
            return
        def worker():
            try:
                sync.push(self.gauth)
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    # 저장 + 동기화 예약 헬퍼
    def _save_todos(self):
        save_list(self.todo_file, self.todos)
        self._touch_sync()

    def _save_alarms(self):
        save_list(self.alarm_file, self.alarms)
        self._touch_sync()

    def _save_task_alarms(self):
        self.task_alarms.save()
        self._touch_sync()

    def _save_settings(self):
        self.settings.save(self.cfg_file)
        self._touch_sync()

    # ------------------------------------------------------------ 캘린더 창
    def open_calendar(self):
        if not self.gauth.is_connected():
            QMessageBox.information(self, config.APP_NAME,
                                    "먼저 [설정]에서 Google 로그인 하세요.")
            return
        if self._cal_win is None:
            self._cal_win = CalendarWindow(self.gauth, self)
        self._cal_win.show()
        self._cal_win.raise_()
        self._cal_win.activateWindow()

    # ------------------------------------------------------------ 빠른 필터
    def _on_range_changed(self, _idx):
        self._range = self.cmb_range.currentData() or "week"
        self.refresh_calendar()
        self.refresh_todo()

    def _range_bounds(self):
        """(start, end) 반개구간. all 이면 None."""
        today = date.today()
        if self._range == "week":
            return today, today + timedelta(days=7)
        if self._range == "next":
            return today + timedelta(days=7), today + timedelta(days=14)
        return None

    # ------------------------------------------------------------ 업데이트
    def check_update(self, manual: bool):
        def worker():
            try:
                res = updater.check()
                self.sig_update.emit(res, "", manual)
            except Exception as e:
                self.sig_update.emit(None, str(e), manual)
        threading.Thread(target=worker, daemon=True).start()

    def _on_update_checked(self, res, err, manual):
        if res == "__applied__":
            # 교체 배치가 실행됨 → 앱 종료하면 새 버전이 뜬다
            self._really_close = True
            self._shutdown()
            QApplication.quit()
            return
        if err:
            if manual:
                QMessageBox.warning(self, config.APP_NAME, "업데이트 확인 실패:\n" + err)
            return
        if not res:
            if manual:
                QMessageBox.information(self, config.APP_NAME,
                                       f"현재 최신 버전입니다. (v{config.APP_VERSION})")
            return
        msg = (f"새 버전 {res['version']} 이(가) 있습니다. (현재 v{config.APP_VERSION})\n\n"
               f"{(res.get('notes') or '').strip()[:300]}\n\n지금 업데이트할까요?")
        if QMessageBox.question(self, config.APP_NAME, msg) != QMessageBox.Yes:
            return
        if not updater.is_frozen():
            QMessageBox.information(
                self, config.APP_NAME,
                "개발 모드에서는 자동 교체가 되지 않습니다.\n"
                f"릴리스에서 {config.UPDATE_ASSET_NAME} 를 받아 사용하세요.")
            return
        self.sig_toast.emit(config.APP_NAME, "업데이트 다운로드 중...")

        def worker():
            try:
                path = updater.download(res["asset_url"])
                updater.apply_and_restart(path)
                self.sig_update.emit("__applied__", "", manual)
            except Exception as e:
                self.sig_update.emit(None, str(e), True)
        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 상단 바
        self._topbar = QWidget()
        self._topbar.setFixedHeight(52)
        tl = QHBoxLayout(self._topbar)
        tl.setContentsMargins(16, 0, 16, 0)
        self._title_lbl = QLabel(config.APP_NAME)
        tl.addWidget(self._title_lbl)
        self.lbl_account = QLabel("")
        tl.addWidget(self.lbl_account)
        tl.addStretch()
        self.chk_startup = QCheckBox("PC 시작 시 실행")
        self.chk_startup.toggled.connect(lambda on: _set_startup(on))
        tl.addWidget(self.chk_startup)
        outer.addWidget(self._topbar)
        self._apply_topbar_theme()

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
        self.btn_calendar = QPushButton("캘린더 열기")
        self.btn_calendar.clicked.connect(self.open_calendar)
        row.addWidget(self.btn_calendar)
        self.btn_fetch = QPushButton("새로고침")
        self.btn_fetch.clicked.connect(self.fetch_all_async)
        row.addWidget(self.btn_fetch)
        self.lbl_status = QLabel("")
        row.addWidget(self.lbl_status)
        row.addStretch()
        # 빠른 필터
        row.addWidget(QLabel("표시:"))
        self.cmb_range = QComboBox()
        self.cmb_range.addItem("이번주", "week")
        self.cmb_range.addItem("다음주", "next")
        self.cmb_range.addItem("전체", "all")
        # 시작 기본값: 전체 (초기화 중 새로고침이 두 번 돌지 않도록 시그널 차단 후 설정)
        self.cmb_range.blockSignals(True)
        self.cmb_range.setCurrentIndex(self.cmb_range.findData(self._range))
        self.cmb_range.blockSignals(False)
        self.cmb_range.currentIndexChanged.connect(self._on_range_changed)
        row.addWidget(self.cmb_range)
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
        # 전체 선택/해제
        self.btn_todo_all = QPushButton("전체선택")
        self.btn_todo_all.clicked.connect(self._toggle_all_todo_checks)
        trow.addWidget(self.btn_todo_all)
        trow.addStretch()
        v.addLayout(trow)

        # 맨 왼쪽에 체크박스 열(선택) 추가 → 여러 건 일괄 완료
        self.tbl_todo = self._make_table(
            ["선택", "날짜", "시각", "할일", "알람", "멘트"], [46, 120, 80, 360, 60, 220])
        self.tbl_todo.doubleClicked.connect(self._on_todo_dblclick)
        # 우클릭 컨텍스트 메뉴 (버튼과 동일한 동작)
        self.tbl_todo.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tbl_todo.customContextMenuRequested.connect(self._todo_context_menu)
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
            ("캘린더 열기", self.open_calendar),
            ("오늘 브리핑", lambda: self.show_briefing(manual=True)),
            ("지금 백업", lambda: self._backup(manual=True)),
            ("업데이트 확인", lambda: self.check_update(manual=True)),
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
        self._save_settings()

    def on_settings_click(self):
        was_connected = self.gauth.is_connected()
        prev_dark = self.settings.dark_mode
        dlg = SettingsDialog(self.gauth, self.settings, self)
        accepted = dlg.exec() == SettingsDialog.Accepted
        if accepted:
            self._save_settings()
            self.hotkeys.apply(self.settings)
            self.followup_tracker.last_scan = None  # 설정이 바뀌었으니 다시 스캔
            if self.settings.dark_mode != prev_dark:
                self.apply_theme()   # 다크모드 즉시 반영
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

        # 팔로업이 켜져 있으면 과거 출고 일정까지 스캔하도록 과거 구간도 받는다
        back_days = 0
        if self.settings.follow_on:
            back_days = self.settings.follow_months * 31 + 30

        def worker():
            from concurrent.futures import ThreadPoolExecutor
            # 토큰을 먼저 확보(갱신 1회) → 캘린더·할일을 동시에 조회
            try:
                self.gauth.valid_token()
            except Exception:
                pass
            with ThreadPoolExecutor(max_workers=2) as ex:
                f_ev = ex.submit(google_client.fetch_calendar_events, self.gauth, back_days, 14)
                f_tk = ex.submit(google_client.fetch_tasks, self.gauth)
                try:
                    self.sig_events_done.emit(f_ev.result(), "")
                except Exception as e:
                    self.sig_events_done.emit(None, str(e))
                try:
                    self.sig_tasks_done.emit(f_tk.result(), "")
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
        if added:
            self._save_todos()
            self.followup_tracker.save()
            self._touch_sync()
            self.refresh_todo()
            self.sig_toast.emit("팔로업 자동 등록", f"{len(added)}건을 [내 할일]에 추가했습니다.")
            # 설정 시 구글 캘린더에도 종일 일정으로 등록
            if self.settings.follow_to_calendar and self.gauth.is_connected():
                items = [(it.title, it.run_date) for it in added]

                def worker():
                    for title, d in items:
                        try:
                            google_client.insert_event(self.gauth, "primary", title, d, all_day=True)
                        except Exception:
                            pass
                threading.Thread(target=worker, daemon=True).start()
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
        bounds = self._range_bounds()
        start, end = bounds if bounds else (today, today + timedelta(days=14))
        for ev in self.cal_events:
            d = ev.start.date()
            if not (start <= d < end):
                continue
            r = self.tbl_week.rowCount()
            self.tbl_week.insertRow(r)
            vals = [ev.start.strftime("%m-%d(%a)"), ev.time_text(), "일정", ev.summary]
            for c, val in enumerate(vals):
                self.tbl_week.setItem(r, c, QTableWidgetItem(val))
            self.week_dates.append(d)
            self._colorize_row(self.tbl_week, r, d)
        label = {"week": "이번주", "next": "다음주", "all": "전체"}.get(self._range, "이번주")
        self.lbl_week.setText(f"{label} 일정  {self.tbl_week.rowCount()}건")

    def _colorize_row(self, table: QTableWidget, row: int, d: date | None):
        if d is None:
            return
        today = date.today()
        color = None
        bold = False
        if d == today:
            color = QColor(theme.c("today"))
            bold = True
        elif d == today + timedelta(days=1):
            color = QColor(theme.c("tomorrow"))
            bold = True
        if color is None:
            return
        fg = QColor(theme.c("row_text"))
        for c in range(table.columnCount()):
            it = table.item(row, c)
            if it is None:
                continue
            it.setBackground(color)
            it.setForeground(fg)
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
        bounds = self._range_bounds()

        def in_range(has_due, d):
            if bounds is None:
                return True
            return bool(has_due) and d is not None and bounds[0] <= d < bounds[1]

        rows = []
        for it in self.todos:
            if it.done:  # 완료된 항목은 목록에서 숨김(제거된 것처럼)
                continue
            if it.run_date and it.run_date < today - timedelta(days=7):
                continue
            if not in_range(True, it.run_date):
                continue
            grp, sd = self._group(True, it.run_date, today)
            rows.append((grp, sd, False, it))
        for tk in self.gtasks:
            if tk.has_due and tk.due and tk.due < today - timedelta(days=7):
                continue
            if not in_range(tk.has_due, tk.due):
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
            # 0열: 체크박스(선택) — 키를 여기에 저장
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            chk.setCheckState(Qt.Unchecked)
            chk.setTextAlignment(Qt.AlignCenter)
            chk.setData(Qt.UserRole, key)
            self.tbl_todo.setItem(r, 0, chk)
            # 1열부터 데이터
            for c, val in enumerate(vals):
                self.tbl_todo.setItem(r, c + 1, QTableWidgetItem(val))
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

    # ---- 체크박스 선택 헬퍼 ----
    def _checked_todo_keys(self) -> list:
        keys = []
        for r in range(self.tbl_todo.rowCount()):
            it = self.tbl_todo.item(r, 0)
            if it and it.checkState() == Qt.Checked:
                k = it.data(Qt.UserRole)
                if k:
                    keys.append(k)
        return keys

    def _toggle_all_todo_checks(self):
        rows = self.tbl_todo.rowCount()
        any_unchecked = any(
            self.tbl_todo.item(r, 0) and self.tbl_todo.item(r, 0).checkState() != Qt.Checked
            for r in range(rows))
        new = Qt.Checked if any_unchecked else Qt.Unchecked
        for r in range(rows):
            it = self.tbl_todo.item(r, 0)
            if it:
                it.setCheckState(new)
        self.btn_todo_all.setText("전체해제" if any_unchecked else "전체선택")

    def _on_todo_dblclick(self, index):
        # 체크박스 열 더블클릭은 편집 대신 무시(체크 토글은 단일 클릭)
        if index.column() == 0:
            return
        self.on_todo_edit()

    def _todo_context_menu(self, pos):
        # 우클릭한 행을 선택한 뒤, 버튼과 동일한 메뉴를 띄운다
        idx = self.tbl_todo.indexAt(pos)
        if idx.isValid():
            self.tbl_todo.selectRow(idx.row())
        menu = QMenu(self)
        for text, slot in [
            ("추가", self.on_todo_add),
            ("수정", self.on_todo_edit),
            ("삭제", self.on_todo_del),
            ("완료", self.on_todo_done),
            ("멘트 복사", self.on_todo_copy),
        ]:
            act = menu.addAction(text)
            act.triggered.connect(slot)
        menu.exec(self.tbl_todo.viewport().mapToGlobal(pos))

    def on_todo_done(self):
        """체크된(없으면 현재 선택된) 할일을 완료 처리하고 목록에서 제거."""
        keys = self._checked_todo_keys()
        if not keys:
            k = self._sel_todo_key()
            if k:
                keys = [k]
        if not keys:
            QMessageBox.information(self, config.APP_NAME, "완료할 할일을 체크하거나 선택하세요.")
            return
        if len(keys) > 1 and QMessageBox.question(
                self, config.APP_NAME,
                f"체크한 {len(keys)}건을 완료 처리할까요?") != QMessageBox.Yes:
            return

        local_ids = {k[1] for k in keys if k[0] == "local"}
        google_items = [k[1] for k in keys if k[0] == "google"]

        # 1) 로컬 할일: 완료 = 목록에서 제거
        if local_ids:
            self.todos = [t for t in self.todos if id(t) not in local_ids]
            save_list(self.todo_file, self.todos)

        # 2) 구글 Tasks: 완료 처리(완료되면 미완료 목록에서 사라짐)
        errors = []
        for tid in google_items:
            gt = next((t for t in self.gtasks if t.id == tid), None)
            if gt is None:
                continue
            try:
                google_client.complete_task(self.gauth, gt.list_id, gt.id)
            except Exception as e:
                errors.append(f"{gt.title}: {e}")

        if google_items:
            self.fetch_all_async()   # 구글 목록 새로고침(완료분 제외)
        else:
            self.refresh_todo()

        if errors:
            QMessageBox.warning(self, config.APP_NAME,
                                "일부 완료 처리 실패:\n" + "\n".join(errors))

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
        # 로컬 데이터 변경 감지 시 Drive 동기화 예약
        self._maybe_autosync()

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
        lines += ["", f"오늘: 일정 {cnt_cal}건 / 할일 {cnt_todo}건"]

        # ---- 이번주 요약 (오늘~+7일) ----
        week_end = today + timedelta(days=7)
        wk_cal = sorted([e for e in self.cal_events if today <= e.start.date() < week_end],
                        key=lambda e: e.start)
        wk_todo = []
        for it in self.todos:
            if not it.done and it.run_date and today <= it.run_date < week_end:
                wk_todo.append((it.run_date, it.run_time.strftime('%H:%M'), it.title))
        for tk in self.gtasks:
            if tk.has_due and tk.due and today <= tk.due < week_end:
                wk_todo.append((tk.due, "", tk.title))
        wk_todo.sort(key=lambda x: (x[0], x[1]))

        lines += ["", "━━━━━━━━━━━━━━━━━━━━", "[이번주 요약]  (오늘~7일)",
                  f"일정 {len(wk_cal)}건 / 할일 {len(wk_todo)}건"]
        if wk_cal:
            lines.append("· 일정")
            for e in wk_cal[:12]:
                lines.append(f"   {e.start.strftime('%m-%d(%a)')} {e.time_text()}  {e.summary}")
            if len(wk_cal) > 12:
                lines.append(f"   … 외 {len(wk_cal) - 12}건")
        if wk_todo:
            lines.append("· 할일")
            for d, tm, title in wk_todo[:12]:
                lines.append(f"   {d.strftime('%m-%d(%a)')} {tm}  {title}")
            if len(wk_todo) > 12:
                lines.append(f"   … 외 {len(wk_todo) - 12}건")
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
