"""메인 화면 (델파이 uDash 이식).

탭1: 이번주 일정(구글 캘린더) + 내 할일(로컬 + 구글 Tasks)
탭2: PC 알람 (요일/시간 반복)
트레이 상주, 1초 타이머로 알람 감시, 시작 시 오늘 브리핑.
카카오톡 스케줄러는 제거했다.  구글 연동은 [Google 로그인] 한 번으로 끝난다.
"""

from __future__ import annotations

import sys
import threading
import uuid
import webbrowser
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton, QSystemTrayIcon,
    QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import (
    alarm_window, config, followup, google_client, hotkey, sheets, sync, theme, updater,
)
from .calendar_window import CalendarWindow
from .customer_dialog import CustomerDialog
from .edit_dialog import EditDialog
from .icon import make_icon
from .models import (
    AppSettings, PcAlarm, TaskAlarm, TaskAlarmStore, TodoItem, load_list, save_list,
)
from .settings_dialog import SettingsDialog

# ---------------------------------------------------------------------------
# 낙관적 UI (즉시 반영)
#
# 구글에 보내기 '전에' 화면부터 바꾸고, 전송은 뒤에서 처리한다.
# self.gtasks 는 서버 사본 그대로 두고, 확정 안 된 변경만 _pending_ops 에 쌓아
# 그릴 때 덧씌운다 → 롤백은 목록에서 빼기 한 줄로 끝난다.
# ---------------------------------------------------------------------------
PENDING_ID_PREFIX = "__pending__"
PENDING_GRACE_SEC = 60          # 서버 반영이 늦어도 이 시간까지는 화면에 유지
TASK_REFETCH_DELAY_MS = 1500    # 쓰기 성공 후 '할일만' 재조회 (디바운스)


@dataclass
class _PendingOp:
    """아직 서버 반영이 확인되지 않은 낙관적 변경 1건."""
    kind: str                       # "add" | "update" | "remove"
    key: str                        # add=임시 id, update/remove=실제 구글 task id
    task: object = None             # 화면에 보여줄 GoogleTask (remove 는 None)
    alarm: object = None            # add 시 대화상자에서 지정한 TaskAlarm
    err_prefix: str = ""            # 실패 시 안내 문구 앞머리
    epoch: int = 0                  # 쓰기가 성공한 시점의 세대 번호 (0=전송 중)
    deadline: datetime = field(default_factory=datetime.now)


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
    sig_tasks_done = Signal(object, str, int)   # (할일목록|None, 오류, 조회시작 epoch)
    sig_events_done = Signal(object, str)
    sig_fetch_done = Signal()
    sig_toast = Signal(str, str)
    sig_account = Signal(str)          # 로그인 계정 이메일 확인됨
    sig_synced = Signal(bool)          # Drive 동기화 완료(변경 여부)
    sig_update = Signal(object, str, bool)  # (릴리스정보|None, 오류, 수동여부)
    sig_write_done = Signal(object, object, str)   # (_PendingOp, 실제결과|None, 오류)
    sig_sheet_rows = Signal(object, object, str)   # (행목록|None, 마지막행, 오류)
    sig_sheet_written = Signal(object, object, str)  # (임시행, 실제행번호|None, 오류)
    sig_sheet_diag = Signal(str)                     # 시트 연결 진단 결과

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
        # --- 낙관적 UI 상태 (UI 스레드에서만 조작) ---
        self._pending_ops: list[_PendingOp] = []
        self._data_epoch = 0          # 쓰기가 성공할 때마다 +1
        self._write_errors: list[str] = []
        # --- 고객관리(구글 시트) 상태 ---
        self.sheet_rows: list = []
        self.sheet_choices: dict = {}
        self._sheet_last_row = 0
        self._sheet_pending: list = []   # 아직 시트에 안 올라간 행

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
        self.sig_write_done.connect(self._on_write_done)
        self.sig_sheet_rows.connect(self._on_sheet_rows)
        self.sig_sheet_written.connect(self._on_sheet_written)
        self.sig_sheet_diag.connect(self._on_sheet_diag)

        # 동기화 푸시 디바운스 타이머
        self._sync_timer = QTimer(self)
        self._sync_timer.setSingleShot(True)
        self._sync_timer.timeout.connect(self._do_sync_push)

        # 쓰기 직후 '할일만' 재조회 (디바운스) — 여러 건이 몰려도 한 번만
        self._task_refetch_timer = QTimer(self)
        self._task_refetch_timer.setSingleShot(True)
        self._task_refetch_timer.timeout.connect(self.fetch_tasks_async)

        # 실패 메시지를 모아 한 창으로
        self._err_timer = QTimer(self)
        self._err_timer.setSingleShot(True)
        self._err_timer.timeout.connect(self._flush_write_errors)

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
            theme.apply_to_app(app)   # 스타일시트 + 팔레트 함께
        self._apply_topbar_theme()
        self.refresh_calendar()
        self.refresh_todo()
        self.refresh_alarm()
        # 캘린더 창이 열려 있으면 그 창의 배경·글자색도 함께 갱신
        if self._cal_win is not None:
            try:
                self._cal_win.apply_theme()
            except Exception:
                pass

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

    def add_optimistic_event(self, ev) -> None:
        """캘린더 창에서 방금 추가한 일정을 재조회 없이 이번주 목록에 바로 반영."""
        self.cal_events = sorted(list(self.cal_events) + [ev], key=lambda e: e.start)
        self.refresh_calendar()

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
        self.tabs.addTab(self._build_customer_tab(), "고객관리")
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
            ("메모 복사", self.on_todo_copy),
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
            ["선택", "날짜", "시각", "할일", "알람", "메모"], [46, 120, 80, 360, 60, 220])
        self.tbl_todo.doubleClicked.connect(self._on_todo_dblclick)
        # 우클릭 컨텍스트 메뉴 (버튼과 동일한 동작)
        self.tbl_todo.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tbl_todo.customContextMenuRequested.connect(self._todo_context_menu)
        v.addWidget(self.tbl_todo)
        return w

    # ------------------------------------------------------ 고객관리(구글 시트)
    def _build_customer_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        row = QHBoxLayout()
        self.btn_cust_load = QPushButton("불러오기")
        self.btn_cust_load.clicked.connect(lambda: self.load_sheet_async(manual=True))
        row.addWidget(self.btn_cust_load)
        for text, slot in [("고객 추가", self.on_customer_add),
                           ("수정", self.on_customer_edit)]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        self.btn_cust_open = QPushButton("시트 열기")
        self.btn_cust_open.clicked.connect(self._open_sheet)
        row.addWidget(self.btn_cust_open)
        self.btn_cust_diag = QPushButton("연결 진단")
        self.btn_cust_diag.clicked.connect(self.diagnose_sheet)
        row.addWidget(self.btn_cust_diag)
        row.addStretch()
        row.addWidget(QLabel("검색:"))
        self.ed_cust_find = QLineEdit()
        self.ed_cust_find.setPlaceholderText("고객명 · 차종 · 금융사")
        self.ed_cust_find.setFixedWidth(220)
        self.ed_cust_find.textChanged.connect(lambda _t: self.refresh_customers())
        row.addWidget(self.ed_cust_find)
        v.addLayout(row)

        self.lbl_cust = QLabel("고객관리 시트를 불러오려면 [불러오기]를 누르세요.")
        v.addWidget(self.lbl_cust)

        self.tbl_cust = self._make_table(
            ["순번", "고객명 / 사업자", "금융사", "차종", "계약일", "출고일", "진행현황"],
            [52, 230, 110, 180, 100, 100, 80])
        self.tbl_cust.doubleClicked.connect(lambda _i: self.on_customer_edit())
        v.addWidget(self.tbl_cust)
        return w

    def _sheet_ready(self, quiet: bool = False) -> bool:
        if not self.settings.sheet_on:
            if not quiet:
                QMessageBox.information(
                    self, config.APP_NAME,
                    "[설정] → '구글 시트 고객관리' 에서 사용을 켜고 시트 주소를 지정하세요.")
            return False
        if not self.gauth.is_connected():
            if not quiet:
                QMessageBox.information(self, config.APP_NAME,
                                        "먼저 [설정]에서 Google 로그인 하세요.")
            return False
        if not (self.settings.sheet_id or "").strip():
            if not quiet:
                QMessageBox.information(self, config.APP_NAME, "설정에서 시트 주소를 입력하세요.")
            return False
        # 저장된 권한 목록에 스프레드시트가 없으면 요청 전에 미리 안내
        if not self.gauth.has_scope(config.SCOPE_SHEETS):
            if not quiet:
                QMessageBox.information(
                    self, config.APP_NAME,
                    "로그인 토큰에 스프레드시트 권한이 없습니다.\n"
                    "[설정] → [Google 로그아웃] 후 다시 [Google 로그인] 을 해주세요.")
            return False
        return True

    def _open_sheet(self):
        sid = (self.settings.sheet_id or "").strip()
        if not sid:
            QMessageBox.information(self, config.APP_NAME, "설정에서 시트 주소를 입력하세요.")
            return
        webbrowser.open(sheets.sheet_url(sid))

    def diagnose_sheet(self):
        """시트 연결 진단 — '권한 없음'의 진짜 원인을 짚어준다."""
        if not self.gauth.is_connected():
            QMessageBox.information(self, config.APP_NAME,
                                    "먼저 [설정]에서 Google 로그인 하세요.")
            return
        self.btn_cust_diag.setEnabled(False)
        self.btn_cust_diag.setText("진단 중…")
        sid = (self.settings.sheet_id or "").strip()
        sname = (self.settings.sheet_name or "").strip()

        def worker():
            lines = [f"계정: {self.account_email or '(확인 중)'}",
                     f"시트: {sname}  ({sid[:20]}…)" if sid else "시트: (미설정)", ""]
            has_scope = None
            try:
                scopes = google_client.granted_scopes(self.gauth)
                has_scope = config.SCOPE_SHEETS in scopes
                lines.append("① 스프레드시트 권한: " + ("있음 ✅" if has_scope else "없음 ❌"))
            except Exception as e:
                lines.append(f"① 스프레드시트 권한: 확인 실패 ({e})")

            sheet_err = ""
            if not sid:
                lines.append("② 시트 읽기: 건너뜀 (시트 주소 미설정)")
            else:
                try:
                    _h, rows = sheets.read_rows(self.gauth, sid, sname)
                    lines.append(f"② 시트 읽기: 성공 ✅ ({len(rows)}건)")
                except Exception as e:
                    sheet_err = str(e)
                    lines.append("② 시트 읽기: 실패 ❌")
                    lines.append("   " + sheet_err.replace("\n", "\n   ")[:400])

            # ── 다음에 할 일을 한 줄로 지정 ──
            lines.append("")
            lines.append("▶ 다음에 할 일")
            if has_scope is False:
                lines.append("   [설정] → [Google 로그아웃] 후 다시 [Google 로그인] 하세요.")
                lines.append("   그래도 안 되면 OAuth 동의 화면에 아래 권한을 추가해야 합니다:")
                lines.append("   " + config.SCOPE_SHEETS)
            elif sheet_err and ("Sheets API" in sheet_err or "SERVICE_DISABLED" in sheet_err
                                or "has not been used" in sheet_err):
                lines.append("   구글 클라우드에서 Google Sheets API 를 켜야 합니다:")
                lines.append("   " + config.SHEETS_ENABLE_URL)
            elif sheet_err:
                lines.append("   위 오류 내용을 확인하세요. 시트 주소/시트명이 맞는지도 점검하세요.")
            else:
                lines.append("   정상입니다. [불러오기] 를 눌러 사용하세요.")
            self.sig_sheet_diag.emit("\n".join(lines))

        threading.Thread(target=worker, daemon=True).start()

    def _on_sheet_diag(self, text: str):
        self.btn_cust_diag.setEnabled(True)
        self.btn_cust_diag.setText("연결 진단")
        box = QMessageBox(self)
        box.setWindowTitle("시트 연결 진단")
        box.setText(text)
        # 주소를 마우스로 긁어 복사할 수 있게
        box.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        box.exec()

    def load_sheet_async(self, manual: bool = False):
        """시트를 백그라운드로 읽어온다 (창이 멈추지 않게)."""
        if not self._sheet_ready(quiet=not manual):
            return
        self.btn_cust_load.setEnabled(False)
        self.lbl_cust.setText("고객관리 시트를 불러오는 중…")
        sid, sname = self.settings.sheet_id.strip(), self.settings.sheet_name.strip()

        def worker():
            try:
                _hdr, rows = sheets.read_rows(self.gauth, sid, sname)
                last = rows[-1].row if rows else _hdr
                self.sig_sheet_rows.emit(rows, last, "")
            except Exception as e:
                self.sig_sheet_rows.emit(None, 0, str(e))
        threading.Thread(target=worker, daemon=True).start()

    def _on_sheet_rows(self, rows, last_row, err: str):
        self.btn_cust_load.setEnabled(True)
        if rows is None:
            self.lbl_cust.setText("불러오기 실패")
            QMessageBox.warning(self, config.APP_NAME, "시트를 불러오지 못했습니다:\n" + err)
            return
        self.sheet_rows = rows
        self._sheet_last_row = last_row
        self.sheet_choices = sheets.choices(rows)
        self._sheet_pending = []
        self.refresh_customers()

    def _visible_sheet_rows(self) -> list:
        """서버 행 + 아직 전송 중인 행."""
        return list(self.sheet_rows) + list(self._sheet_pending)

    def refresh_customers(self):
        q = (self.ed_cust_find.text() or "").strip().lower() if hasattr(self, "ed_cust_find") else ""
        self.tbl_cust.setRowCount(0)
        rows = self._visible_sheet_rows()
        shown = 0
        for cr in rows:
            if q:
                hay = " ".join([cr.get("customer"), cr.get("model"),
                                cr.get("finance")]).lower()
                if q not in hay:
                    continue
            r = self.tbl_cust.rowCount()
            self.tbl_cust.insertRow(r)
            pend = cr in self._sheet_pending
            vals = [cr.seq if not pend else "…",
                    ("[등록중] " if pend else "") + cr.get("customer"),
                    cr.get("finance"), cr.get("model"),
                    cr.get("contract_date"), cr.get("deliver_date"), cr.get("status")]
            for c, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setData(Qt.UserRole, cr.row)
                self.tbl_cust.setItem(r, c, item)
            if pend:
                fg = QColor(theme.c("subtext"))
                for c in range(self.tbl_cust.columnCount()):
                    cell = self.tbl_cust.item(r, c)
                    if cell is not None:
                        cell.setForeground(fg)
            shown += 1
        total = len(rows)
        self.lbl_cust.setText(
            f"고객 {total}건" + (f" · 검색 {shown}건" if q else "")
            + f"   (시트: {self.settings.sheet_name})")

    def _sel_customer(self):
        r = self.tbl_cust.currentRow()
        if r < 0:
            return None
        it = self.tbl_cust.item(r, 0)
        if it is None:
            return None
        rownum = it.data(Qt.UserRole)
        for cr in self._visible_sheet_rows():
            if cr.row == rownum:
                return cr
        return None

    def on_customer_add(self):
        if not self._sheet_ready():
            return
        if not self.sheet_rows and not self._sheet_pending:
            QMessageBox.information(self, config.APP_NAME,
                                    "먼저 [불러오기]로 시트를 읽어주세요.")
            return
        vals = CustomerDialog.run("고객 등록", {}, self.sheet_choices, self)
        if vals is None:
            return
        # 화면에 먼저 반영 (임시 행)
        pend = sheets.CustomerRow(row=self._sheet_last_row + 1, seq="", total="")
        pend.values = dict(vals)
        self._sheet_pending.append(pend)
        self.refresh_customers()

        sid, sname = self.settings.sheet_id.strip(), self.settings.sheet_name.strip()
        last = self._sheet_last_row

        def worker():
            try:
                newrow = sheets.append_row(self.gauth, sid, sname, vals, last)
                self.sig_sheet_written.emit(pend, newrow, "")
            except Exception as e:
                self.sig_sheet_written.emit(pend, None, str(e))
        threading.Thread(target=worker, daemon=True).start()

    def on_customer_edit(self):
        if not self._sheet_ready():
            return
        cr = self._sel_customer()
        if cr is None:
            QMessageBox.information(self, config.APP_NAME, "수정할 고객을 선택하세요.")
            return
        if cr in self._sheet_pending:
            self.sig_toast.emit(config.APP_NAME, "시트에 등록 중입니다. 잠시 후 수정하세요.")
            return
        vals = CustomerDialog.run(f"고객 수정 · {cr.get('customer')}",
                                  cr.values, self.sheet_choices, self)
        if vals is None:
            return
        old = dict(cr.values)
        cr.values = dict(vals)          # 화면 먼저
        self.refresh_customers()

        sid, sname = self.settings.sheet_id.strip(), self.settings.sheet_name.strip()

        def worker():
            try:
                sheets.update_row(self.gauth, sid, sname, cr.row, vals)
                self.sig_sheet_written.emit(None, cr.row, "")
            except Exception as e:
                cr.values = old         # 롤백 (UI 갱신은 핸들러에서)
                self.sig_sheet_written.emit(None, None, str(e))
        threading.Thread(target=worker, daemon=True).start()

    def _on_sheet_written(self, pend, newrow, err: str):
        if err:
            if pend is not None and pend in self._sheet_pending:
                self._sheet_pending.remove(pend)
            self.refresh_customers()
            QMessageBox.warning(self, config.APP_NAME, "시트 저장 실패:\n" + err)
            return
        if pend is not None:
            # 임시 행을 확정 행으로 승격
            if pend in self._sheet_pending:
                self._sheet_pending.remove(pend)
            pend.row = int(newrow or pend.row)
            self.sheet_rows.append(pend)
            self._sheet_last_row = max(self._sheet_last_row, pend.row)
        self.refresh_customers()
        self.sig_toast.emit(config.APP_NAME, "고객관리 시트에 저장했습니다.")
        # 수식(순번·합계·안내멘트)이 계산된 결과를 잠시 뒤 다시 읽어온다
        QTimer.singleShot(2500, lambda: self.load_sheet_async(manual=False))

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
            ["사용", "이름", "요일", "시각", "메모"], [50, 200, 120, 80, 480])
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

        epoch = self._data_epoch   # 조회 '시작' 시점의 세대 (UI 스레드에서 캡처)

        def worker():
            from concurrent.futures import ThreadPoolExecutor
            # 토큰을 먼저 확보(갱신 1회) → 캘린더·할일을 동시에 조회
            try:
                self.gauth.valid_token()
            except Exception:
                pass

            def do_tasks():
                # 할일은 캘린더 조회(최대 75일치)를 기다리지 않고 준비되는 즉시 반영
                try:
                    self.sig_tasks_done.emit(google_client.fetch_tasks(self.gauth), "", epoch)
                except Exception as e:
                    self.sig_tasks_done.emit(None, str(e), epoch)

            def do_events():
                try:
                    self.sig_events_done.emit(
                        google_client.fetch_calendar_events(self.gauth, back_days, 14), "")
                except Exception as e:
                    self.sig_events_done.emit(None, str(e))

            with ThreadPoolExecutor(max_workers=2) as ex:
                ex.submit(do_tasks)
                ex.submit(do_events)
            # with 를 벗어나면 두 조회가 모두 끝난 상태
            self.sig_fetch_done.emit()

        threading.Thread(target=worker, daemon=True).start()

    def fetch_tasks_async(self):
        """'할일'만 다시 받아온다(캘린더 조회 없이).

        쓰기 직후 서버 기준으로 맞추는 용도 — 전체 재조회보다 훨씬 가볍다.
        """
        if not self.gauth.is_connected():
            return
        epoch = self._data_epoch

        def worker():
            try:
                self.sig_tasks_done.emit(google_client.fetch_tasks(self.gauth), "", epoch)
            except Exception as e:
                self.sig_tasks_done.emit(None, str(e), epoch)

        threading.Thread(target=worker, daemon=True).start()

    def _schedule_task_refetch(self):
        """쓰기 여러 건이 몰려도 재조회는 한 번만."""
        self._task_refetch_timer.start(TASK_REFETCH_DELAY_MS)

    def _on_fetch_done(self):
        # 캘린더 조회가 실패해도 새로고침 버튼이 잠긴 채 남지 않도록 여기서도 푼다
        self.btn_fetch.setEnabled(True)
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
                rmin = self._reminder_minutes()

                def worker():
                    for title, d in items:
                        try:
                            google_client.insert_event(self.gauth, "primary", title, d,
                                                       all_day=True, reminder_minutes=rmin)
                        except Exception:
                            pass
                threading.Thread(target=worker, daemon=True).start()

    def _reminder_minutes(self):
        """설정된 구글 캘린더 알림(분). 꺼져 있으면 None."""
        if not self.settings.cal_reminder_on:
            return None
        return max(0, int(self.settings.cal_reminder_min))

    # ------------------------------------------------------- 낙관적 UI 공통
    def _is_pending_id(self, task_id: str) -> bool:
        return bool(task_id) and str(task_id).startswith(PENDING_ID_PREFIX)

    def visible_gtasks(self) -> list:
        """서버 목록 위에 아직 확정 안 된 변경(추가/수정/삭제)을 덧씌운 화면용 목록."""
        if not self._pending_ops:
            return self.gtasks
        removed = {op.key for op in self._pending_ops if op.kind == "remove"}
        updated = {op.key: op.task for op in self._pending_ops if op.kind == "update"}
        out = [updated.get(tk.id, tk) for tk in self.gtasks if tk.id not in removed]
        out.extend(op.task for op in self._pending_ops if op.kind == "add")
        return out

    def _pending_alarm_for(self, task_id: str):
        """등록 중인 항목이 대화상자에서 지정한 알람 설정을 찾는다."""
        for op in self._pending_ops:
            if op.kind == "add" and op.key == task_id:
                return op.alarm
        return None

    def _start_pending(self, op: _PendingOp) -> None:
        """낙관적 변경을 넣고 즉시 화면에 반영."""
        op.deadline = datetime.now() + timedelta(seconds=PENDING_GRACE_SEC)
        self._pending_ops.append(op)
        self.refresh_todo()

    def _drop_pending(self, op: _PendingOp) -> None:
        try:
            self._pending_ops.remove(op)
        except ValueError:
            pass

    def _on_write_done(self, op, real, err: str):
        """구글 쓰기 결과 (UI 스레드)."""
        if err:
            # 롤백 — 낙관적으로 그렸던 행/숨김을 되돌린다
            self._drop_pending(op)
            if op.kind == "add" and self._pending_alarm and self._pending_alarm[1] is op.alarm:
                self._pending_alarm = None
            self.refresh_todo()
            self._report_write_error((op.err_prefix + " " + err).strip())
            return
        self._data_epoch += 1
        op.epoch = self._data_epoch
        op.deadline = datetime.now() + timedelta(seconds=PENDING_GRACE_SEC)
        # 추가는 실제 id 를 받았으니 임시 행을 곧바로 진짜 항목으로 바꾼다
        if op.kind == "add" and real is not None and getattr(real, "id", ""):
            self._adopt_pending_alarm(op, real.id)
            self._drop_pending(op)
            if not any(t.id == real.id for t in self.gtasks):
                self.gtasks.append(real)
            self.refresh_todo()
        self._schedule_task_refetch()

    def _adopt_pending_alarm(self, op, real_id: str) -> None:
        """추가 직후 대화상자에서 지정한 알람을 실제 구글 id 에 옮겨 붙인다."""
        src = op.alarm
        if src is None or not (src.alarm or src.ment.strip()):
            return
        a = self.task_alarms.ensure(real_id)
        a.alarm = src.alarm
        a.run_time = src.run_time
        a.ment = src.ment
        self.task_alarms.save()
        if self._pending_alarm and self._pending_alarm[1] is src:
            self._pending_alarm = None      # 타이머 경로와 중복 적용 방지

    def _report_write_error(self, msg: str) -> None:
        self._write_errors.append(msg)
        self._err_timer.start(400)          # 여러 건을 한 창에 모아 표시

    def _flush_write_errors(self) -> None:
        if not self._write_errors:
            return
        msgs, self._write_errors = self._write_errors, []
        QMessageBox.warning(self, config.APP_NAME, "\n".join(msgs))

    def _on_tasks_done(self, tasks, err: str, fetch_epoch: int = 0):
        if tasks is None:
            return
        self.gtasks = tasks
        self._prune_pending_ops(tasks, fetch_epoch)
        self.refresh_todo()

    def _prune_pending_ops(self, server: list, fetch_epoch: int) -> None:
        """서버 목록과 대조해 이미 반영된 낙관적 변경을 걷어낸다 (UI 스레드).

        경합 방지: 이 조회가 쓰기보다 **먼저 출발했다면**(fetch_epoch < op.epoch)
        새 항목이 없는 게 당연하므로 유지한다. 구글 반영이 늦는 경우까지 감안해
        deadline(유예) 안에서도 유지한다.
        """
        now = datetime.now()
        by_id = {tk.id: tk for tk in server}
        alive: list[_PendingOp] = []
        for op in self._pending_ops:
            fresh = (op.epoch == 0) or (fetch_epoch < op.epoch) or (now < op.deadline)
            if op.kind == "add":
                # 실제 id 를 받은 뒤에는 _on_write_done 에서 이미 정리된다.
                # 여기 남아 있다면 아직 전송 중이거나 응답을 못 받은 경우.
                if fresh:
                    alive.append(op)
                elif self._pending_alarm and self._pending_alarm[1] is op.alarm:
                    self._pending_alarm = None
            elif op.kind == "remove":
                if op.key not in by_id:
                    continue                # 서버에서도 사라짐 → 반영 완료
                if fresh:
                    alive.append(op)        # 아직 남아 있으면 계속 숨김
            elif op.kind == "update":
                cur = by_id.get(op.key)
                if cur is None:
                    continue                # 항목 자체가 없어짐
                same = (cur.title == op.task.title and cur.notes == op.task.notes
                        and cur.has_due == op.task.has_due and cur.due == op.task.due)
                if same:
                    continue                # 서버가 이미 새 값
                if fresh:
                    alive.append(op)
        self._pending_ops = alive

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
        for tk in self.visible_gtasks():
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
                # 등록 중인 행은 아직 저장된 알람이 없으니 대화상자 값으로 보여준다
                a = self.task_alarms.find(tk.id) or self._pending_alarm_for(tk.id)
                day = tk.due.strftime("%m-%d(%a)") if (tk.has_due and tk.due) else "기한없음"
                tm = a.run_time.strftime("%H:%M") if (a and a.alarm) else "-"
                on = "ON" if (a and a.alarm) else ""
                if a and a.ment.strip():
                    ment = a.ment.replace("\n", " ")[:60]
                else:
                    ment = (tk.notes or "").replace("\n", " ")[:60]
                pend = self._is_pending_id(tk.id)
                vals = [day, tm, ("[등록중] " if pend else "[구글] ") + tk.title, on, ment]
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
            # 전송 중인 행은 흐리게 → '아직 처리 중'임이 눈에 보이게
            if is_google and self._is_pending_id(obj.id):
                fg = QColor(theme.c("subtext"))
                for c in range(self.tbl_todo.columnCount()):
                    cell = self.tbl_todo.item(r, c)
                    if cell is not None:
                        cell.setForeground(fg)

    def _warn_if_filtered(self, due, has_due: bool) -> None:
        """추가한 항목이 현재 [표시] 필터 밖이면 목록에 안 보이므로 알려준다."""
        b = self._range_bounds()
        if b is None:
            return
        if not has_due or due is None or not (b[0] <= due < b[1]):
            self.sig_toast.emit(config.APP_NAME,
                                "추가했습니다. 현재 [표시] 필터에서는 보이지 않습니다.")

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
        for tk in self.visible_gtasks():
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
            title = title.strip()
            # 1) 네트워크보다 먼저 화면에 — 임시 id 를 가진 행을 즉시 표시
            tk = google_client.GoogleTask(
                id=PENDING_ID_PREFIX + uuid.uuid4().hex, list_id="", title=title,
                notes=notes, due=due if has_due else None, has_due=has_due)
            op = _PendingOp(kind="add", key=tk.id, task=tk, alarm=tmp,
                            err_prefix="구글 할일 추가 실패:")
            self._pending_alarm = (title, tmp)   # 기존 알람 매핑 경로도 유지
            self._start_pending(op)
            self._warn_if_filtered(due if has_due else None, has_due)

            # 2) 실제 등록은 백그라운드에서
            def worker():
                try:
                    real = google_client.insert_task(
                        self.gauth, "", title, notes, due if has_due else None)
                    self.sig_write_done.emit(op, real, "")
                except Exception as e:
                    self.sig_write_done.emit(op, None, str(e))
            threading.Thread(target=worker, daemon=True).start()
            return
        it = TodoItem()
        if EditDialog.edit_todo(it, self):
            self.todos.append(it)
            save_list(self.todo_file, self.todos)
            self.refresh_todo()

    def on_todo_edit(self):
        gt = self._sel_gtask()
        if gt is not None:
            if self._is_pending_id(gt.id):
                self.sig_toast.emit(config.APP_NAME, "구글에 등록 중입니다. 잠시 후 수정하세요.")
                return
            a = self.task_alarms.ensure(gt.id)
            ok, title, notes, due, has_due = EditDialog.edit_google_task(
                "할일 수정 (구글 Tasks)", gt.title, gt.notes, gt.due, gt.has_due, a, self)
            if not ok or not title.strip():
                return
            self.task_alarms.save()      # 알람은 로컬이라 즉시 저장(기존 동작 유지)
            # 화면부터 새 값으로 바꾸고, 구글 전송은 뒤에서
            new = replace(gt, title=title.strip(), notes=notes,
                          due=due if has_due else None, has_due=has_due)
            op = _PendingOp(kind="update", key=gt.id, task=new, err_prefix="수정 실패:")
            self._start_pending(op)

            def worker():
                try:
                    google_client.update_task(self.gauth, gt.list_id, gt.id,
                                              title, notes, due, has_due)
                    self.sig_write_done.emit(op, None, "")
                except Exception as e:
                    self.sig_write_done.emit(op, None, str(e))
            threading.Thread(target=worker, daemon=True).start()
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
            if self._is_pending_id(gt.id):
                self.sig_toast.emit(config.APP_NAME, "구글에 등록 중입니다. 잠시 후 삭제하세요.")
                return
            if QMessageBox.question(self, config.APP_NAME, "이 구글 할일을 삭제할까요?") != QMessageBox.Yes:
                return
            # 화면에서 먼저 지우고, 삭제 요청은 뒤에서
            op = _PendingOp(kind="remove", key=gt.id, err_prefix="삭제 실패:")
            self._start_pending(op)

            def worker():
                try:
                    google_client.delete_task(self.gauth, gt.list_id, gt.id)
                    self.sig_write_done.emit(op, None, "")
                except Exception as e:
                    self.sig_write_done.emit(op, None, str(e))
            threading.Thread(target=worker, daemon=True).start()
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
            ("메모 복사", self.on_todo_copy),
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

        # 2) 구글 Tasks: 화면에서 먼저 지우고, 완료 처리는 백그라운드에서
        jobs = []
        skipped = 0
        view = self.visible_gtasks()
        for tid in google_items:
            if self._is_pending_id(tid):
                skipped += 1
                continue
            gt = next((t for t in view if t.id == tid), None)
            if gt is None:
                continue
            op = _PendingOp(kind="remove", key=gt.id,
                            err_prefix=f"완료 처리 실패({gt.title}):")
            op.deadline = datetime.now() + timedelta(seconds=PENDING_GRACE_SEC)
            self._pending_ops.append(op)
            jobs.append((op, gt.list_id, gt.id))

        self.refresh_todo()          # 로컬·구글 모두 한 번에 즉시 반영
        if skipped:
            self.sig_toast.emit(config.APP_NAME,
                                f"{skipped}건은 아직 등록 중이라 건너뛰었습니다.")

        if jobs:
            def worker():
                # 한 스레드에서 순차 처리 (요청 폭주·토큰 갱신 중복 방지)
                for op, list_id, task_id in jobs:
                    try:
                        google_client.complete_task(self.gauth, list_id, task_id)
                        self.sig_write_done.emit(op, None, "")
                    except Exception as e:
                        self.sig_write_done.emit(op, None, str(e))
            threading.Thread(target=worker, daemon=True).start()

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
            self.sig_toast.emit(config.APP_NAME, "메모를 클립보드에 복사했습니다.")

    def _apply_pending_alarm(self):
        """구글 추가 직후, 방금 만든 항목에 알람 설정을 붙인다."""
        pend = getattr(self, "_pending_alarm", None)
        if not pend:
            return
        title, src = pend
        self._pending_alarm = None
        found = None
        for tk in self.gtasks:
            # 임시(등록 중) 행에는 절대 붙이지 않는다 — 실제 서버 id 에만 매핑
            if tk.title == title and not self._is_pending_id(tk.id):
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
        for tk in self.visible_gtasks():
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
        for tk in self.visible_gtasks():
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
