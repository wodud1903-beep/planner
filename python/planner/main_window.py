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
from html import escape as html_escape
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton, QSystemTrayIcon,
    QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import (
    alarm_window, config, followup, google_client, hotkey, searchcombo, sheets,
    sync, theme, updater,
)
from .calendar_window import CalendarWindow
from .customer_dialog import CustomerDialog
from .commission_tab import CommissionTab
from .customer_history import CustomerHistoryDialog
from .greeting_tab import GreetingTab
from .doc_viewer import DocViewer
from .edit_dialog import EditDialog
from .icon import make_icon
from .models import (
    AppSettings, PcAlarm, TaskAlarm, TaskAlarmStore, TodoItem, load_list, save_list,
)
from .settings_dialog import SettingsDialog, load_terms_presets

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


def _next_weekday(from_date: date, weekdays: str) -> date:
    """반복 할일의 다음 차례 날짜. weekdays 는 '1'=일 … '7'=토 문자열."""
    days = {c for c in (weekdays or "") if c.isdigit()}
    if not days:
        return from_date + timedelta(days=7)
    for n in range(1, 8):
        d = from_date + timedelta(days=n)
        if str(d.isoweekday() % 7 + 1) in days:
            return d
    return from_date + timedelta(days=7)


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
    sig_sheet_ments = Signal(object)                 # {행번호: 고객안내멘트}
    sig_sheet_docs = Signal(object)                  # {행번호: S열 =IMAGE() 수식}
    sig_sheet_uids = Signal(object)                  # {행번호: U열 고객ID}
    sig_sheet_rates = Signal(object)                 # 공유 수당율 표
    sig_sheet_deleted_fail = Signal(object, str)     # (되살릴 행, 오류)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(config.APP_NAME)
        # 최대화 버튼 제거 + 크기 고정. 세로를 늘려 '내 할일'을 더 많이 보이게.
        # 단, 작은 화면에서도 잘리지 않도록 화면 크기에 맞춰 고정값을 정한다.
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, False)
        _avail = QGuiApplication.primaryScreen().availableGeometry()
        # 고객관리 표(수수료·견적서 포함)가 가로 스크롤 없이 들어가는 폭
        _w = min(1120, _avail.width() - 20)
        _h = min(920, _avail.height() - 60)
        self.setFixedSize(_w, _h)
        self._centered_once = False
        self._center_on_screen()

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
        self._sheet_header_row = 0
        self._sheet_pending: list = []   # 아직 시트에 안 올라간 행
        self._summary_data: list = []    # 상단 현황 (테마 전환 시 다시 그린다)
        self._terms_map: dict = {}       # 금융사 → 자주 쓴 계약조건
        self._sheet_loaded = False       # 첫 시트 로딩 완료 여부(브리핑 대기용)
        self._fired_cal_alarms: set = set()   # (일정, 분) — 중복 알람 방지
        # 안내멘트를 복사한 적 있는 고객 (시작 시 저장분을 읽어온다)
        self._ment_copied: set = self._load_ment_log()
        # 고객ID → [{date, text}] — 이력 타임라인의 직접 메모
        self._notes: dict = self._load_notes()

        # 저장된 테마 반영
        theme.set_theme(getattr(self.settings, 'theme', '')
                        or ('dark' if self.settings.dark_mode else 'light'))

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
        self.sig_sheet_ments.connect(self._on_sheet_ments)
        self.sig_sheet_docs.connect(self._on_sheet_docs)
        self.sig_sheet_uids.connect(self._on_sheet_uids)
        self.sig_sheet_rates.connect(self._on_sheet_rates)
        self.sig_sheet_deleted_fail.connect(self._on_sheet_delete_fail)

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
        self._brief_waits = 0
        if self.gauth.is_connected():
            # 백업은 계정이 정해진 뒤에(_on_account_ready) 한다.
            # 여기서 하면 계정 폴더가 아직 안 정해져 엉뚱한 폴더를 백업한다.
            self._start_account_sync()               # 끝에서 fetch_all_async 호출
            # 네트워크가 아주 느려도 이 시점엔 무조건 표시
            QTimer.singleShot(15000, lambda: self._do_startup_brief(force=True))
        else:
            # 미연결이면 계정 구분이 없으니 지금 백업해도 폴더가 맞다
            self._backup(manual=False)
            QTimer.singleShot(600, lambda: self._do_startup_brief(force=True))

        # 시작 시 조용히 업데이트 확인
        QTimer.singleShot(4000, lambda: self.check_update(manual=False))

        # 창이 뜬 직후 고객관리 시트를 자동으로 불러온다.
        # (백그라운드 스레드라 시작이 느려지지 않는다. 브리핑의 '안내멘트 미발송'
        #  안내에 필요하므로 너무 늦지 않게 시작한다)
        QTimer.singleShot(800, self._auto_load_sheet)

        self.chk_startup.setChecked(_startup_set())

        # 전역 단축키 (Windows)
        self.hotkeys = hotkey.HotkeyManager(
            QApplication.instance(), int(self.winId()), self._on_hotkey)
        QTimer.singleShot(0, lambda: self.hotkeys.apply(self.settings))

        # 1초 타이머
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)
        self.timer.start(1000)

    def _do_startup_brief(self, force: bool = False):
        """시작 브리핑을 한 번만 표시 (데이터 로딩 후 또는 타임아웃 시).

        안내멘트 미발송 안내를 담으려면 시트가 필요하므로, 아직 안 왔으면
        잠깐(최대 3회 = 약 6초) 기다렸다가 표시한다.
        """
        if not self._startup_brief_pending:
            return
        if (not force and self.settings.sheet_on and not self._sheet_loaded
                and self._brief_waits < 3):
            self._brief_waits += 1
            QTimer.singleShot(2000, self._do_startup_brief)
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
        theme.set_theme(getattr(self.settings, "theme", "")
                        or ("dark" if self.settings.dark_mode else "light"))
        app = QApplication.instance()
        if app:
            theme.apply_to_app(app)   # 스타일시트 + 팔레트 함께
        self._apply_topbar_theme()
        self.refresh_calendar()
        self.refresh_todo()
        self.refresh_alarm()
        if getattr(self, "_summary_data", None):
            self._show_summary(self._summary_data)   # 색상 다시 계산
        if hasattr(self, "tbl_cust"):
            self.refresh_customers()
        if hasattr(self, "tab_comm"):
            self.tab_comm.apply_theme()
        if hasattr(self, "tab_greet"):
            self.tab_greet.apply_theme()
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
        if not email:
            # 계정을 확인하지 못하면 어느 폴더가 이 사람 데이터인지 알 수 없다.
            # 이때 동기화를 강행하면 공용 폴더(대개 비어 있음)를 번들로 올려
            # 다른 PC 의 데이터까지 지워버린다. 그래서 아예 건너뛴다.
            self.lbl_account.setText("· 계정 확인 실패 — 동기화를 건너뜁니다")
            self._backup(manual=False)
            self.fetch_all_async()
            return
        self.account_email = email
        config.set_account(email)
        self.lbl_account.setText(f"· {email}")
        sync.migrate_legacy()
        self.reload_data()   # 계정 폴더 기준으로 다시 로드
        # 이제야 이 계정의 시트 설정을 알 수 있다 → 바로 불러오기 시도
        self._auto_load_sheet()
        self.fetch_rates_async()      # 공유 수당율(전용 시트)도 함께 받아온다
        # 계정 폴더가 정해진 뒤에야 '그 사람의' 데이터를 백업할 수 있다
        self._backup(manual=False)

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
        self._ment_copied = self._load_ment_log()
        self._notes = self._load_notes()
        if hasattr(self, "tab_greet"):
            self.tab_greet.reload()      # 계정이 바뀌면 그 계정의 문구로
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
        """데이터 변경 후 호출 → 잠시 뒤 Drive 로 업로드(디바운스).

        업로드는 온라인일 때만 하지만, **로컬이 바뀐 시각은 항상** 남긴다.
        안 그러면 오프라인에서 한 작업이 다음 실행의 pull 에 덮어써진다.
        """
        sync.touch_local()
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
    def open_calendar(self, goto: date | None = None):
        if not self.gauth.is_connected():
            QMessageBox.information(self, config.APP_NAME,
                                    "먼저 [설정]에서 Google 로그인 하세요.")
            return
        if self._cal_win is None:
            self._cal_win = CalendarWindow(self.gauth, self)
        self._cal_win.show()
        self._cal_win.raise_()
        self._cal_win.activateWindow()
        if goto is not None:
            self._cal_win.goto_date(goto)

    def _on_week_dblclick(self, index):
        """이번주 일정을 더블클릭 → 캘린더 창을 그 날짜로 연다."""
        r = index.row()
        d = self.week_dates[r] if 0 <= r < len(self.week_dates) else None
        self.open_calendar(goto=d)

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
        self.tab_greet = GreetingTab()
        self.tab_greet.on_changed = self._touch_sync
        self.tabs.addTab(self.tab_greet, "멘트복사")
        self.tab_comm = CommissionTab()
        self.tabs.addTab(self.tab_comm, "수당계산기")
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
        searchcombo.install(self.cmb_range)
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
        # 일정을 더블클릭하면 캘린더 창이 그 날짜로 열린다 (바로 수정·삭제 가능)
        self.tbl_week.doubleClicked.connect(self._on_week_dblclick)
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
                           ("수정", self.on_customer_edit),
                           ("삭제", self.on_customer_del)]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        self.btn_cust_open = QPushButton("시트 열기")
        self.btn_cust_open.clicked.connect(self._open_sheet)
        row.addWidget(self.btn_cust_open)
        row.addStretch()
        row.addWidget(QLabel("검색:"))
        self.ed_cust_find = QLineEdit()
        self.ed_cust_find.setPlaceholderText("고객명 · 차종 · 금융사")
        self.ed_cust_find.setFixedWidth(220)
        self.ed_cust_find.textChanged.connect(lambda _t: self.refresh_customers())
        row.addWidget(self.ed_cust_find)
        v.addLayout(row)

        # 상단 발주 현황 (시트 N1:O4)
        self.lbl_cust_summary = QLabel("")
        self.lbl_cust_summary.setTextFormat(Qt.RichText)
        self.lbl_cust_summary.hide()
        v.addWidget(self.lbl_cust_summary)

        self.lbl_cust = QLabel("고객관리 시트를 불러오려면 [불러오기]를 누르세요.")
        v.addWidget(self.lbl_cust)

        # 안내멘트는 [복사] 버튼만 들어가므로 버튼 폭이면 충분하다(96→62).
        # 거기서 아낀 폭을 고객명·금융사·차종·날짜에 나눠 줬다.
        # 전체 폭은 그대로라 가로 스크롤이 더 늘지 않는다.
        # 수수료(합계)와 견적서 보기를 함께 보여준다.
        # 가로 스크롤이 생기지 않도록 폭 합계를 창 너비 안에 맞춘다(_fit_cust_columns).
        self.tbl_cust = self._make_table(
            ["순번", "고객명 / 사업자", "금융사", "차종", "계약일", "출고일",
             "진행현황", "수수료", "안내멘트", "견적서"],
            [44, 196, 96, 148, 92, 92, 70, 104, 76, 78],
            stretch_last=False)
        self.tbl_cust.doubleClicked.connect(self._on_cust_dblclick)
        # 표가 실제 크기를 갖는 시점은 탭을 처음 열 때다. 그 전에 계산한 폭은
        # 화면과 안 맞아 오른쪽에 흰 칸이 남는다 → 크기가 바뀔 때마다 다시 맞춘다.
        self.tbl_cust.viewport().installEventFilter(self)
        v.addWidget(self.tbl_cust)
        return w

    def eventFilter(self, obj, ev):
        if (ev.type() == QEvent.Resize
                and hasattr(self, "tbl_cust") and obj is self.tbl_cust.viewport()):
            self._fit_cust_columns()
        return super().eventFilter(obj, ev)

    # 진행현황 색상 (글자만 — 배경은 건드리지 않는다)
    STATUS_COLORS = {"출고": "#2F6FD0", "발주": "#4FA45C", "취소": "#D23B3B"}

    # 고객표에서 버튼이 들어가는 열 (더블클릭으로 창을 열면 안 되는 자리)
    COL_STATUS = 6
    COL_FEE = 7
    # 짧은 값이라 가운데로 모아야 읽기 좋은 열 (순번·계약일·출고일·진행현황)
    CENTER_COLS = (0, 4, 5, 6)
    COL_MENT_BTN = 8
    COL_DOC_BTN = 9

    def _ment_key(self, cr) -> str:
        """안내멘트 복사 이력 키.

        고객ID(시트 U열)가 있으면 그것을 쓴다. 순번·고객명은 언제든 바뀌어서,
        이름을 조금만 고쳐도 '보냄' 표시가 사라지고 브리핑이 다시 알려 왔다.
        ID 가 아직 없는 고객만 예전 방식(순번+고객명)으로 식별한다.
        """
        uid = (getattr(cr, "uid", "") or "").strip()
        if uid:
            return "uid:" + uid
        return f"{cr.seq}|{cr.get('customer')}".strip()

    def _migrate_ment_keys(self):
        """예전 키(순번+고객명)로 남은 '보냄' 기록을 고객ID 키로 옮긴다.

        이 작업이 없으면 이번 판올림 직후 이미 보낸 고객이 전부 '미발송' 으로 되살아난다.
        """
        changed = False
        for cr in self.sheet_rows:
            uid = (getattr(cr, "uid", "") or "").strip()
            if not uid:
                continue
            old_key = f"{cr.seq}|{cr.get('customer')}".strip()
            new_key = "uid:" + uid
            if old_key in self._ment_copied and new_key not in self._ment_copied:
                self._ment_copied.add(new_key)
                changed = True
        if changed:
            self._save_ment_log()

    def _load_ment_log(self) -> set:
        try:
            import json
            p = config.data_file("ment_copied.json")
            if p.exists():
                return set(json.loads(p.read_text(encoding="utf-8")) or [])
        except Exception:
            pass
        return set()

    def _save_ment_log(self):
        try:
            import json
            config.atomic_write(
                config.data_file("ment_copied.json"),
                json.dumps(sorted(self._ment_copied), ensure_ascii=False))
        except Exception:
            pass
        self._touch_sync()

    # ---- 고객 메모 (이력 타임라인) ----
    def _load_notes(self) -> dict:
        try:
            import json
            p = config.data_file("customer_notes.json")
            if p.exists():
                o = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(o, dict):
                    return o
        except Exception:
            pass
        return {}

    def _save_notes(self):
        try:
            import json
            config.atomic_write(
                config.data_file("customer_notes.json"),
                json.dumps(self._notes, ensure_ascii=False, indent=2))
        except Exception:
            pass
        self._touch_sync()

    def _copy_customer_ment(self, cr):
        """고객안내멘트를 클립보드로 복사하고 '보냄' 표시를 남긴다."""
        if not (cr.ment or "").strip():
            QMessageBox.information(
                self, config.APP_NAME,
                "이 고객의 안내멘트가 아직 비어 있습니다.\n"
                "시트에서 자동 생성된 뒤 [불러오기] 하면 복사할 수 있습니다.")
            return
        QApplication.clipboard().setText(cr.ment)
        self._ment_copied.add(self._ment_key(cr))
        self._save_ment_log()
        self.refresh_customers()
        self.sig_toast.emit(config.APP_NAME,
                            f"{cr.get('customer')} 안내멘트를 복사했습니다.")

    def _on_cust_dblclick(self, index):
        # 버튼이 놓인 열(안내멘트·견적서)에서는 창을 열지 않는다
        if index.column() in (self.COL_MENT_BTN, self.COL_DOC_BTN):
            return
        self.on_customer_history()

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

    def _auto_load_sheet(self, tries: int = 0):
        """시작 후 고객관리 시트를 자동으로 불러온다.

        구글 계정 확인이 끝나야 **그 계정의 설정**(시트 사용 여부·주소)을 알 수 있는데,
        그건 네트워크 왕복이라 몇 초 걸린다. 예전에는 시작 0.8초에 딱 한 번만
        시도하고, 아직 설정을 모르면 조용히 포기해 버려서 불러오기가 아예
        일어나지 않았다. 이제 준비될 때까지 잠깐씩 다시 확인한다.
        """
        if getattr(self, "_auto_load_started", False) or self._sheet_loaded:
            return
        if self._sheet_ready(quiet=True):
            self._auto_load_started = True
            self.load_sheet_async(manual=False)
            return
        if tries < 12:                       # 약 20초까지 기다려 본다
            QTimer.singleShot(1500, lambda: self._auto_load_sheet(tries + 1))

    def load_sheet_async(self, manual: bool = False):
        """시트를 백그라운드로 읽어온다 (창이 멈추지 않게)."""
        if not self._sheet_ready(quiet=not manual):
            return
        self.btn_cust_load.setEnabled(False)
        self.lbl_cust.setText("고객관리 시트를 불러오는 중…")
        sid, sname = self.settings.sheet_id.strip(), self.settings.sheet_name.strip()

        def worker():
            try:
                # 1) 목록 + 요약 (요청 1회, 분량 큰 안내멘트는 제외)
                _hdr, rows, summary = sheets.read_rows(self.gauth, sid, sname)
                last = rows[-1].row if rows else _hdr
                self.sig_sheet_rows.emit((rows, summary, _hdr), last, "")
                # 2) 안내멘트는 목록을 띄운 뒤 뒤이어 채운다
                try:
                    ments = sheets.read_ments(self.gauth, sid, sname)
                    if ments:
                        self.sig_sheet_ments.emit(ments)
                except Exception:
                    pass
                # 3) 견적서/계약서(S열)는 수식 그대로 읽어야 '이미지 있음' 을 안다
                try:
                    docs = sheets.read_docs(self.gauth, sid, sname)
                    if docs:
                        self.sig_sheet_docs.emit(docs)
                except Exception:
                    pass
                # 4) 고객ID(U열) — 아직 U열이 없는 시트면 그냥 빈 값이다.
                #    목록 조회에 묶으면 U열 없는 시트에서 목록까지 통째로 실패한다.
                try:
                    uids = sheets.read_uids(self.gauth, sid, sname)
                    if uids:
                        self.sig_sheet_uids.emit(uids)
                except Exception:
                    pass
            except Exception as e:
                self.sig_sheet_rows.emit(None, 0, str(e))
        threading.Thread(target=worker, daemon=True).start()

    def _on_sheet_ments(self, ments: dict):
        """안내멘트가 뒤늦게 도착 → 해당 행에 채우고 복사 버튼을 살린다."""
        changed = False
        for cr in self.sheet_rows:
            m = ments.get(cr.row)
            if m and m != cr.ment:
                cr.ment = m
                changed = True
        if changed:
            self.refresh_customers()

    def _reset_sheet_cache(self):
        """다른 시트/탭으로 바뀌었을 때 — 캐시한 행 정보를 모두 버린다."""
        self.sheet_rows = []
        self._sheet_pending = []
        self._sheet_last_row = 0
        self._sheet_header_row = 0
        self._sheet_loaded = False
        self.sheet_choices = {}
        self._terms_map = {}
        self.lbl_cust_summary.hide()
        self._summary_data = []
        self.refresh_customers()

    def _on_sheet_uids(self, uids: dict):
        """고객ID(U열)가 뒤늦게 도착 → 채우고, 옛 '보냄' 기록을 ID 키로 옮긴다."""
        changed = False
        for cr in self.sheet_rows:
            v = uids.get(cr.row)
            if v and cr.uid != v:
                cr.uid = v
                changed = True
        if changed:
            self._migrate_ment_keys()
            self.refresh_customers()

    def fetch_rates_async(self):
        """공유 수당율을 전용 스프레드시트에서 받아온다.

        고객관리 시트를 안 쓰는 PC 도 계산기는 쓰므로, 시트 연동 여부와 상관없이
        구글에 연결돼 있으면 받아온다. 권한이 없거나 실패하면 조용히 넘어가고
        이 PC 에 저장된 마지막 값으로 계산한다.
        """
        if not self.gauth.is_connected():
            return

        def worker():
            try:
                rates = sheets.read_rates(self.gauth, config.RATES_SHEET_ID)
                if rates:
                    self.sig_sheet_rates.emit(rates)
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def _on_sheet_rates(self, rates: dict):
        """공유 수당율이 도착 → 이 PC 에도 저장하고 계산기에 반영."""
        try:
            from . import commission
            if rates != commission.load_rates():
                commission.save_rates(rates)
                if hasattr(self, "tab_comm"):
                    self.tab_comm.reload_rates()
        except Exception:
            pass

    def _on_sheet_docs(self, docs: dict):
        """S열 수식(견적서/계약서)이 뒤늦게 도착 → 해당 행에 채우고 표를 다시 그린다.

        표는 이미 그려진 뒤에 이 값이 도착한다. 다시 그리지 않으면 [보기] 버튼이
        '이미지 없음(—)' 상태로 굳어 눌러도 아무 반응이 없다.
        """
        changed = False
        for cr in self.sheet_rows:
            v = docs.get(cr.row)
            if v and cr.values.get("doc") != v:
                cr.values["doc"] = v
                changed = True
        if changed:
            self.refresh_customers()

    def _on_sheet_rows(self, payload, last_row, err: str):
        self.btn_cust_load.setEnabled(True)
        if payload is None:
            self.lbl_cust.setText("불러오기 실패")
            QMessageBox.warning(self, config.APP_NAME, "시트를 불러오지 못했습니다:\n" + err)
            return
        rows, summary, hdr = payload
        self.sheet_rows = rows
        self._sheet_last_row = last_row
        self._sheet_header_row = hdr
        self.sheet_choices = sheets.choices(rows)
        self._terms_map = sheets.merge_terms(
            load_terms_presets(), sheets.terms_by_finance(rows))
        self._sheet_pending = []
        self._sheet_loaded = True
        self._show_summary(summary)
        self.refresh_customers()

    # 상단 현황 항목별 강조색 (없는 항목은 기본 강조색)
    SUMMARY_COLORS = {
        "발주": "#E08A1E",        # 주황 — 진행 중
        "가망고객": "#7B58C4",     # 보라 — 잠재
        "지난달출고": "#4A7FB5",   # 파랑 — 지난 실적
        "이번달출고": "#2E9E5B",   # 초록 — 이번 실적
    }

    def _show_summary(self, summary):
        """시트 N1:O4 의 발주 현황 + 이번달 실적을 목록 위에 표시.

        발주 현황(N1:O4)이 없는 시트도 있으므로, 요약이 비어 있어도 이번달 실적
        줄은 그린다. (예전엔 요약이 없으면 여기서 바로 빠져나가 실적이 아예 안 보였다)
        """
        self._summary_data = list(summary or [])
        parts = []
        for label, value in (summary or []):
            col = self.SUMMARY_COLORS.get(label.strip(), theme.c("accent"))
            parts.append(
                f"<span style='color:{theme.c('subtext')};'>{label}</span>"
                f"&nbsp;<span style='color:{col};font-size:15px;"
                f"font-weight:bold;'>{value}</span>")
        line1 = "&nbsp;&nbsp;&nbsp;·&nbsp;&nbsp;&nbsp;".join(parts)

        # 이번달 실적 (출고일 기준) — 지난달 대비 증감과 금융사 분포
        st = sheets.month_stats(self.sheet_rows, date.today())
        sub = theme.c("subtext")
        acc = theme.c("accent")
        fee = f"₩{st['cur_fee']:,}" if st["cur_fee"] else "₩0"
        bits = [f"<span style='color:{sub};'>이번달 출고</span>&nbsp;"
                f"<span style='color:{acc};font-weight:bold;'>{st['cur_cnt']}건</span>",
                f"<span style='color:{sub};'>수수료</span>&nbsp;"
                f"<span style='color:{acc};font-weight:bold;'>{fee}</span>"]
        if st["prev_cnt"] or st["prev_fee"]:
            diff = st["cur_fee"] - st["prev_fee"]
            pct = (diff / st["prev_fee"] * 100) if st["prev_fee"] else 0
            col = theme.c("status_ok") if diff >= 0 else theme.c("status_bad")
            arrow = "▲" if diff >= 0 else "▼"
            bits.append(f"<span style='color:{sub};'>지난달 대비</span>&nbsp;"
                        f"<span style='color:{col};font-weight:bold;'>"
                        f"{arrow}{abs(pct):.0f}%</span>"
                        f"<span style='color:{sub};'> (지난달 {st['prev_cnt']}건)</span>")
        if st["by_finance"]:
            top = sorted(st["by_finance"].items(), key=lambda kv: -kv[1])[:4]
            dist = " · ".join(f"{f} {n}" for f, n in top)
            bits.append(f"<span style='color:{sub};'>{dist}</span>")
        line2 = "&nbsp;&nbsp;&nbsp;·&nbsp;&nbsp;&nbsp;".join(bits)

        self.lbl_cust_summary.setText((line1 + "<br>" + line2) if line1 else line2)
        self.lbl_cust_summary.show()

    def _visible_sheet_rows(self) -> list:
        """서버 행 + 아직 전송 중인 행 — 순번 내림차순(최근 등록이 맨 위)."""
        allrows = list(self.sheet_rows) + list(self._sheet_pending)

        def key(cr):
            s = (cr.seq or "").strip()
            # 전송 중(순번 미정)인 행은 항상 맨 위로
            return (1, 0) if cr in self._sheet_pending else (
                0, int(s) if s.isdigit() else -1)

        return sorted(allrows, key=key, reverse=True)

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
            status = cr.get("status")
            fee = sheets.fmt_money(cr.total)
            vals = [cr.seq if not pend else "…",
                    ("[등록중] " if pend else "") + cr.get("customer"),
                    cr.get("finance"), cr.get("model"),
                    cr.get("contract_date"), cr.get("deliver_date"), status,
                    (f"₩{fee}" if fee else "")]
            for c, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setData(Qt.UserRole, cr.row)
                if c == self.COL_FEE:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                elif c in self.CENTER_COLS:
                    item.setTextAlignment(Qt.AlignCenter)
                self.tbl_cust.setItem(r, c, item)
            # 진행현황: 출고=파랑 / 발주=연초록 / 취소=빨강, 굵게 (글자만)
            col = self.STATUS_COLORS.get(status.strip())
            if col:
                cell = self.tbl_cust.item(r, self.COL_STATUS)
                cell.setForeground(QColor(col))
                f = cell.font()
                f.setBold(True)
                cell.setFont(f)
            # 안내멘트 복사 버튼 (+ 보낸 적 있으면 표시)
            done = self._ment_key(cr) in self._ment_copied
            # 글자가 길면 칸을 넘어 잘린다. 보낸 표시는 앞의 체크와 초록색으로만 한다.
            btn = QPushButton("✓ 복사" if done else "복사")
            btn.setEnabled(not pend)
            btn.setToolTip("고객안내멘트를 클립보드로 복사합니다"
                           + ("\n(이미 복사한 적이 있습니다)" if done else ""))
            if done:
                btn.setStyleSheet(f"color:{theme.c('status_ok')};")
            btn.clicked.connect(lambda _c=False, row=cr: self._copy_customer_ment(row))
            self.tbl_cust.setCellWidget(r, self.COL_MENT_BTN, btn)

            # 견적서/계약서 보기 — 시트에 이미지가 등록된 고객만 누를 수 있다
            has_doc = bool(sheets.doc_url(cr.get("doc")))
            dbtn = QPushButton("보기" if has_doc else "—")
            dbtn.setEnabled(has_doc and not pend)
            dbtn.setToolTip("등록된 견적서/계약서 이미지를 크게 봅니다"
                            if has_doc else "등록된 견적서/계약서가 없습니다")
            dbtn.clicked.connect(lambda _c=False, row=cr: self._show_customer_doc(row))
            self.tbl_cust.setCellWidget(r, self.COL_DOC_BTN, dbtn)

            if pend:
                fg = QColor(theme.c("subtext"))
                for c in range(self.COL_MENT_BTN):
                    cell = self.tbl_cust.item(r, c)
                    if cell is not None:
                        cell.setForeground(fg)
            shown += 1
        self._fit_cust_columns()
        total = len(rows)
        self.lbl_cust.setText(
            f"고객 {total}건" + (f" · 검색 {shown}건" if q else "")
            + f"   (시트: {self.settings.sheet_name})")

    def _fit_cust_columns(self):
        """표 오른쪽에 남는 흰 여백을 고객명 열이 흡수하게 한다.

        폭을 고정하면 창보다 좁을 때 오른쪽이 허옇게 비고, 열을 늘리는 방식
        (Stretch)으로 두면 창보다 넓을 때 그 열이 되레 찌그러진다.
        그래서 '남을 때만' 더해 준다.
        """
        if getattr(self, "_fitting_cols", False):
            return          # 폭을 바꾸면 스크롤바가 생겼다 사라지며 다시 불린다
        self._fitting_cols = True
        try:
            vp = self.tbl_cust.viewport().width()
            used = sum(self.tbl_cust.columnWidth(i)
                       for i in range(self.tbl_cust.columnCount()))
            base = getattr(self, "_cust_name_w", None)
            if base is None:
                base = self._cust_name_w = self.tbl_cust.columnWidth(1)
            spare = vp - (used - self.tbl_cust.columnWidth(1) + base)
            self.tbl_cust.setColumnWidth(1, base + max(0, spare))
        except Exception:
            pass
        finally:
            self._fitting_cols = False

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
        res = CustomerDialog.run("고객 등록", {}, self.sheet_choices, "", self,
                                 terms_map=self._terms_map)
        if res is None:
            return
        vals, img, _cleared = res
        if img and not self._confirm_image_share():
            return
        # 행 번호를 **먼저 예약**한다. 추가는 API 왕복이 여러 번이라 몇 초가 걸리는데,
        # 그 사이 두 번째 추가가 같은 번호를 집어 앞 고객을 덮어썼다(과거 실제 버그).
        last = self._sheet_last_row
        self._sheet_last_row = last + 1

        # 화면에 먼저 반영 (임시 행)
        uid = sheets.new_uid()          # 메모/이력을 붙들어 둘 불변 ID
        pend = sheets.CustomerRow(row=last + 1, seq="", total="", uid=uid)
        pend.values = dict(vals)
        self._sheet_pending.append(pend)
        self.refresh_customers()

        sid, sname = self.settings.sheet_id.strip(), self.settings.sheet_name.strip()
        name = (vals.get("customer") or "고객").replace("/", "_")[:40]

        rows_snapshot = list(self.sheet_rows)
        hdr_row = self._sheet_header_row

        def worker():
            try:
                v = dict(vals)
                if img:
                    url = sheets.upload_image(
                        self.gauth, img,
                        f"견적서_{name}_{datetime.now():%Y%m%d_%H%M%S}.png")
                    v["doc"] = sheets.image_formula(url)
                # 순번은 앱이 계산해서 넣는다(A열이 수식이면 "" → 수식에 맡김)
                seq = sheets.next_seq(self.gauth, sid, sname, last, rows_snapshot)
                try:
                    # U열이 없는 시트면 여기서 만들어 둔다(실패해도 등록은 진행)
                    if hdr_row:
                        sheets.ensure_uid_column(self.gauth, sid, sname, hdr_row)
                except Exception:
                    pass
                newrow = sheets.append_row(self.gauth, sid, sname, v, last,
                                           seq=seq, uid=uid)
                self.sig_sheet_written.emit(pend, newrow, "")
            except Exception as e:
                self.sig_sheet_written.emit(pend, None, str(e))
        threading.Thread(target=worker, daemon=True).start()

    def _confirm_image_share(self) -> bool:
        """이미지를 셀 안 그림으로 넣으려면 '링크 공개'가 필요하다는 사실을 1회 확인."""
        if getattr(self, "_img_share_ok", False):
            return True
        r = QMessageBox.question(
            self, config.APP_NAME,
            "셀 안에 그림으로 보이게 하려면 이미지를 구글 드라이브에 올린 뒤\n"
            "'링크가 있는 누구나 보기' 로 공개해야 합니다.\n"
            "(구글 시트가 이미지를 가져올 때 로그인 정보를 쓰지 못하기 때문입니다)\n\n"
            "주소를 아는 사람은 해당 견적서를 볼 수 있습니다. 계속할까요?")
        if r != QMessageBox.Yes:
            return False
        self._img_share_ok = True
        return True

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
        res = CustomerDialog.run(f"고객 수정 · {cr.get('customer')}",
                                 cr.values, self.sheet_choices, cr.ment, self,
                                 terms_map=self._terms_map)
        if res is None:
            return
        vals, img, doc_cleared = res
        if img and not self._confirm_image_share():
            return
        old = dict(cr.values)
        # 다이얼로그는 손대지 않은 칸(견적서, 못 읽은 날짜)의 키를 아예 안 준다.
        # 화면에도 기존 값을 그대로 유지해야 표가 빈칸으로 보이지 않는다.
        merged = dict(cr.values)
        merged.update(vals)
        if doc_cleared:
            merged["doc"] = ""
        cr.values = merged              # 화면 먼저
        self.refresh_customers()

        sid, sname = self.settings.sheet_id.strip(), self.settings.sheet_name.strip()
        name = (vals.get("customer") or "고객").replace("/", "_")[:40]

        def worker():
            try:
                v = dict(vals)
                if img:
                    url = sheets.upload_image(
                        self.gauth, img,
                        f"견적서_{name}_{datetime.now():%Y%m%d_%H%M%S}.png")
                    v["doc"] = sheets.image_formula(url)
                elif doc_cleared:
                    v["doc"] = ""       # 지우기를 누른 경우에만 S열을 비운다
                sheets.update_row(self.gauth, sid, sname, cr.row, v)
                self.sig_sheet_written.emit(None, cr.row, "")
            except Exception as e:
                cr.values = old         # 롤백 (UI 갱신은 핸들러에서)
                self.sig_sheet_written.emit(None, None, str(e))
        threading.Thread(target=worker, daemon=True).start()

    def _show_customer_doc(self, cr):
        """등록된 견적서/계약서 이미지를 크게 본다."""
        url = sheets.doc_url(cr.get("doc"))
        if not url:
            QMessageBox.information(
                self, config.APP_NAME,
                "이 고객에게 등록된 견적서/계약서가 없습니다.\n"
                "[수정] 에서 이미지를 붙여넣어 등록할 수 있습니다.")
            return
        DocViewer.show_for(cr.get("customer"), url, self.gauth, self)

    def on_customer_history(self):
        """선택한 고객의 이력 타임라인."""
        if not self._sheet_ready():
            return
        cr = self._sel_customer()
        if cr is None:
            QMessageBox.information(self, config.APP_NAME, "이력을 볼 고객을 선택하세요.")
            return
        if cr in self._sheet_pending:
            self.sig_toast.emit(config.APP_NAME, "시트에 등록 중입니다. 잠시 후 여세요.")
            return

        uid = (cr.uid or "").strip()
        if not uid:
            # v1.1.25 이전에 등록된 고객은 ID 가 없다. 이력을 처음 열 때 그 고객에게만
            # 발급한다(전체 일괄 쓰기는 수백 셀 쓰기가 되고 중간에 실패하면 절반만 적힌다).
            uid = sheets.new_uid()
            cr.uid = uid
            sid = self.settings.sheet_id.strip()
            sname = self.settings.sheet_name.strip()
            hdr = self._sheet_header_row

            def worker():
                try:
                    if hdr:
                        sheets.ensure_uid_column(self.gauth, sid, sname, hdr)
                    sheets.write_uid(self.gauth, sid, sname, cr.row, uid)
                except Exception as e:
                    # 조용히 넘기면 안 된다. ID 가 시트에 안 남으면 다음에 열 때
                    # 새 ID 가 발급돼 지금 적은 메모를 찾지 못하게 된다.
                    self.sig_toast.emit(
                        config.APP_NAME,
                        "고객ID를 시트에 기록하지 못했습니다.\n"
                        "지금 남긴 메모가 다음에 안 보일 수 있습니다.\n"
                        + str(e).splitlines()[0][:80])
            threading.Thread(target=worker, daemon=True).start()

        notes = self._notes.get(uid, [])
        new_notes = CustomerHistoryDialog.run(
            cr, notes, self._ment_key(cr) in self._ment_copied, self)
        if new_notes != notes:
            if new_notes:
                self._notes[uid] = new_notes
            else:
                self._notes.pop(uid, None)
            self._save_notes()

    def on_customer_del(self):
        if not self._sheet_ready():
            return
        cr = self._sel_customer()
        if cr is None:
            QMessageBox.information(self, config.APP_NAME, "삭제할 고객을 선택하세요.")
            return
        if cr in self._sheet_pending:
            self.sig_toast.emit(config.APP_NAME, "시트에 등록 중입니다. 잠시 후 삭제하세요.")
            return
        if QMessageBox.question(
                self, config.APP_NAME,
                f"'{cr.get('customer')}' 의 입력 내용을 모두 지울까요?\n"
                "(합계·안내멘트 같은 함수 칸은 그대로 두고, 직접 입력한 값만 지웁니다)"
        ) != QMessageBox.Yes:
            return

        # 화면에서 먼저 지우고, 시트 반영은 뒤에서
        try:
            self.sheet_rows.remove(cr)
        except ValueError:
            pass
        self.refresh_customers()

        sid, sname = self.settings.sheet_id.strip(), self.settings.sheet_name.strip()

        def worker():
            try:
                sheets.clear_row(self.gauth, sid, sname, cr.row)
                self.sig_sheet_written.emit(None, cr.row, "")
            except Exception as e:
                self.sig_sheet_deleted_fail.emit(cr, str(e))
        threading.Thread(target=worker, daemon=True).start()

    def _on_sheet_delete_fail(self, cr, err: str):
        """삭제 실패 → 지웠던 행을 되살린다."""
        if cr not in self.sheet_rows:
            self.sheet_rows.append(cr)
        self.refresh_customers()
        QMessageBox.warning(self, config.APP_NAME, "삭제 실패:\n" + err)

    def _on_sheet_written(self, pend, newrow, err: str):
        if err:
            if pend is not None and pend in self._sheet_pending:
                self._sheet_pending.remove(pend)
                # 예약해 둔 행 번호를 돌려준다 — 단 그 뒤에 다른 추가가 더 큰 번호를
                # 가져갔으면 그대로 둬야 그 추가가 덮어써지지 않는다.
                if self._sheet_last_row == pend.row:
                    self._sheet_last_row = pend.row - 1
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

    def _make_table(self, headers, widths, stretch_last: bool = True) -> QTableWidget:
        """표 하나.

        stretch_last=False 면 지정한 폭을 그대로 지킨다. 마지막 열이 버튼 열
        (안내멘트)인 표에서 켜 두면 버튼 칸만 늘어나 보기 나쁘다.
        """
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.SingleSelection)
        t.setShowGrid(True)
        for i, wdt in enumerate(widths):
            t.setColumnWidth(i, wdt)
        t.horizontalHeader().setStretchLastSection(stretch_last)
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
        prev_theme = (getattr(self.settings, "theme", "")
                      or ("dark" if self.settings.dark_mode else "light"))
        prev_sheet = (self.settings.sheet_id.strip(), self.settings.sheet_name.strip())
        dlg = SettingsDialog(self.gauth, self.settings, self,
                             account=getattr(self, 'account_email', ''))
        accepted = dlg.exec() == SettingsDialog.Accepted
        if accepted:
            self._save_settings()
            self.hotkeys.apply(self.settings)
            self.followup_tracker.last_scan = None  # 설정이 바뀌었으니 다시 스캔
            now_theme = (getattr(self.settings, "theme", "")
                         or ("dark" if self.settings.dark_mode else "light"))
            if now_theme != prev_theme:
                self.apply_theme()   # 고른 테마를 즉시 반영
            if hasattr(self, "tab_comm"):
                self.tab_comm.reload_rates()   # 수당율을 고쳤을 수 있다
            self.fetch_rates_async()
            # 계약조건 목록을 고쳤을 수 있으니 다시 합쳐 둔다
            self._terms_map = sheets.merge_terms(
                load_terms_presets(), sheets.terms_by_finance(self.sheet_rows))
            now_sheet = (self.settings.sheet_id.strip(),
                         self.settings.sheet_name.strip())
            if now_sheet != prev_sheet:
                # 시트/탭이 바뀌면 들고 있던 행 번호는 전부 무의미하다.
                # 안 비우면 이전 탭의 행 번호로 새 탭에 써서 엉뚱한 줄을 덮어쓴다.
                self._reset_sheet_cache()
                if self.gauth.is_connected():
                    self.load_sheet_async(manual=False)
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
                except google_client.PartialResult as p:
                    # 일부 캘린더만 실패 — 받아온 만큼은 쓰되 안내는 한다
                    self.sig_events_done.emit(p.data, p.message)
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
        if events is None:
            self._report_fetch_error(err)
            return
        self.cal_events = events
        self.refresh_calendar()
        self._run_followups()
        if err:
            # 일부 캘린더만 실패한 경우 — 빠진 일정이 있다는 걸 알려야 한다.
            # (예전엔 조용히 삼켜서 '오늘 일정 없음' 으로 보였고 알람도 안 울렸다)
            self._report_fetch_error(err)

    def _report_fetch_error(self, err: str):
        """조회 실패를 사용자에게 보인다.

        예전엔 err 을 받아만 두고 한 번도 쓰지 않아, 토큰이 죽어도 화면은 어제
        데이터를 그대로 보여주고 상태는 초록색 '연결됨' 이었다. 그 사이 일정 알람이
        전부 멈춰도 알 길이 없었다.
        """
        if not err:
            return
        msg = err.splitlines()[0][:80]
        if not self.gauth.is_connected():
            msg = "연결이 끊겼습니다 — [설정] → Google 로그인"
        self.lbl_status.setText("구글: " + msg)
        self.lbl_status.setStyleSheet("color:#c00;")

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
            self._report_fetch_error(err)
            return
        if fetch_epoch and fetch_epoch < self._data_epoch:
            # 이 조회는 최근 쓰기보다 먼저 출발했다 — 방금 추가한 할일이 없는
            # 낡은 목록이므로 버린다. (예전엔 그대로 덮어써서 새 할일이 사라졌고,
            # 사용자가 다시 추가해 구글에 중복이 생겼다)
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

        # 1) 로컬 할일: 완료 = 목록에서 제거.
        #    단 반복 할일은 지우지 않고 **다음 차례로 넘긴다**
        #    (예전엔 반복 여부를 안 봐서 완료 한 번에 반복 설정이 영구 삭제됐다)
        if local_ids:
            keep = []
            for t in self.todos:
                if id(t) not in local_ids:
                    keep.append(t)
                elif t.repeats:
                    t.run_date = _next_weekday(t.run_date or date.today(), t.weekdays)
                    keep.append(t)
            self.todos = keep
            save_list(self.todo_file, self.todos)
            self._touch_sync()

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
        # 4) 구글 캘린더 시간 일정 (정시) — 분당 1회만.
        #    tick 이 1초라 예전엔 0초·1초에 두 번 울려 팝업을 두 번 닫아야 했다.
        minute_key = now.replace(second=0, microsecond=0)
        for ev in self.cal_events:
            if (ev.has_time and ev.start.date() == now.date()
                    and ev.start.hour == now.hour and ev.start.minute == now.minute):
                key = (ev.uid or ev.summary, minute_key)
                if key in self._fired_cal_alarms:
                    continue
                self._fired_cal_alarms.add(key)
                self.fire_alarm("[구글] " + ev.summary, "")
        if len(self._fired_cal_alarms) > 200:      # 오래된 기록 정리
            self._fired_cal_alarms = {
                k for k in self._fired_cal_alarms
                if k[1] > now - timedelta(hours=2)}

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
    def _ment_due_customers(self, today):
        """안내멘트를 아직 안 보낸 고객 — 출고일 ~ 출고일+2일 구간만.

        반환: [(행, 출고일, 출고 후 며칠째)]
        """
        out = []
        for cr in self.sheet_rows:
            d = sheets.parse_date(cr.get("deliver_date"))
            if d is None:
                continue
            dday = (today - d).days
            if not (0 <= dday <= 2):
                continue
            if self._ment_key(cr) in self._ment_copied:
                continue          # 이미 보냄
            out.append((cr, d, dday))
        out.sort(key=lambda x: x[1])
        return out

    def _expiring_customers(self, today):
        """만기가 다가온(또는 막 지난) 재계약 대상.

        반환: [(행, 만기일, D-day)] — 급한 순.
        """
        months = int(getattr(self.settings, "expiry_months", 0) or 0)
        if months <= 0:
            return []                      # 0 = 기능 끔
        ahead = months * 31
        out = []
        for cr in self.sheet_rows:
            if cr.get("status").strip() == "취소":
                continue                   # 취소된 계약은 만기도 재계약도 없다
            d = sheets.expiry_date(cr)
            if d is None:
                continue                   # 계약조건에 개월 수가 없으면 계산 불가
            left = (d - today).days
            # 이미 지난 건도 한 달간은 남겨 둔다 — 놓친 건이 조용히 사라지면 안 된다
            if not (-30 <= left <= ahead):
                continue
            out.append((cr, d, left))
        out.sort(key=lambda x: x[2])
        return out

    # ---------------------------------------------------------------- 브리핑
    # 브리핑은 '읽는 화면' 이 아니라 '훑는 화면' 이다. 그래서 내용을 먼저
    # 섹션 데이터로 만들고, 그걸 색·크기·이모지를 입힌 HTML 로 그린다.
    # (평문도 같은 데이터에서 뽑는다 — 두 벌을 따로 고치다 어긋나지 않게)
    _WEEKDAY_KO = ("월", "화", "수", "목", "금", "토", "일")

    def _briefing_sections(self) -> list:
        today = date.today()
        secs = []

        # ---- 오늘 일정 ----
        items = [{"lead": ev.time_text(), "text": ev.summary}
                 for ev in self.cal_events if ev.start.date() == today]
        cnt_cal = len(items)
        secs.append({"icon": "📅", "title": "오늘 일정", "color": "blue",
                     "items": items, "empty": "오늘 잡힌 일정이 없습니다"})

        # ---- 오늘 할일 ----
        items = []
        for it in self.todos:
            if not it.done and it.run_date == today:
                items.append({"lead": it.run_time.strftime("%H:%M"), "text": it.title})
        for tk in self.visible_gtasks():
            if tk.has_due and tk.due == today:
                items.append({"lead": "", "text": tk.title})
        cnt_todo = len(items)
        secs.append({"icon": "✅", "title": "오늘 할일", "color": "green",
                     "items": items, "empty": "오늘 할일이 없습니다"})

        # ---- 안내멘트 미발송 (출고일 ~ 출고일+2일) ----
        due = self._ment_due_customers(today)
        if due:
            items = []
            for cr, d, dday in due:
                tag = "오늘 출고" if dday == 0 else f"출고 {dday}일차"
                items.append({"lead": tag, "text": cr.get("customer"),
                              "sub": d.strftime("%m-%d")})
            secs.append({"icon": "💬", "title": "안내멘트 미발송", "color": "red",
                         "items": items,
                         "hint": "[고객관리] 탭에서 [복사] 를 눌러 안내멘트를 보내세요."})

        # ---- 만기 재계약 ----
        exp = self._expiring_customers(today)
        if exp:
            items = []
            for cr, d, left in exp[:12]:
                tag = (f"D-{left}" if left > 0 else
                       ("오늘 만기" if left == 0 else f"{-left}일 지남"))
                items.append({"lead": tag, "text": cr.get("customer"),
                              "sub": f"{d:%Y-%m-%d}"})
            more = len(exp) - 12
            secs.append({"icon": "🔔", "title": "만기 재계약", "color": "orange",
                         "items": items, "count": len(exp),
                         "more": more if more > 0 else 0,
                         "hint": "[고객관리] 탭에서 [이력] 로 상담 내역을 확인하고 "
                                 "재계약을 준비하세요."})

        # ---- 이번주 요약 (오늘~+7일) ----
        week_end = today + timedelta(days=7)
        wk_cal = sorted([e for e in self.cal_events
                         if today <= e.start.date() < week_end], key=lambda e: e.start)
        wk_todo = []
        for it in self.todos:
            if not it.done and it.run_date and today <= it.run_date < week_end:
                wk_todo.append((it.run_date, it.run_time.strftime("%H:%M"), it.title))
        for tk in self.visible_gtasks():
            if tk.has_due and tk.due and today <= tk.due < week_end:
                wk_todo.append((tk.due, "", tk.title))
        wk_todo.sort(key=lambda x: (x[0], x[1]))

        items = []
        for e in wk_cal[:12]:
            items.append({"lead": self._d_label(e.start.date()),
                          "text": e.summary, "sub": e.time_text(), "kind": "일정"})
        for d, tm, title in wk_todo[:12]:
            items.append({"lead": self._d_label(d), "text": title,
                          "sub": tm, "kind": "할일"})
        secs.append({"icon": "🗓", "title": "이번주 요약", "color": "violet",
                     "items": items, "count": len(wk_cal) + len(wk_todo),
                     "note": f"일정 {len(wk_cal)}건 / 할일 {len(wk_todo)}건",
                     "more": max(0, len(wk_cal) - 12) + max(0, len(wk_todo) - 12),
                     "empty": "이번주에 남은 일이 없습니다"})

        self._brief_today_counts = (cnt_cal, cnt_todo)
        return secs

    def _d_label(self, d: date) -> str:
        return f"{d:%m-%d}({self._WEEKDAY_KO[d.weekday()]})"

    # ---- 평문 (복사·기존 호출 호환) ----
    def build_briefing(self) -> str:
        secs = self._briefing_sections()
        cnt_cal, cnt_todo = self._brief_today_counts
        d = date.today()
        lines = [f"{d:%Y년 %m월 %d일} ({self._WEEKDAY_KO[d.weekday()]})", ""]
        for s in secs:
            n = s.get("count", len(s["items"]))
            lines.append(f"[{s['title']}]  {n}건" if n else f"[{s['title']}]")
            if s.get("note"):
                lines.append(f"  {s['note']}")
            if not s["items"]:
                lines.append(f"  ({s.get('empty', '없음')})")
            for it in s["items"]:
                lead = (it.get("lead") or "").strip()
                sub = (it.get("sub") or "").strip()
                tail = f"  ({sub})" if sub else ""
                lines.append(f"  · {lead + '  ' if lead else ''}{it['text']}{tail}")
            if s.get("more"):
                lines.append(f"  … 외 {s['more']}건")
            if s.get("hint"):
                lines.append(f"  → {s['hint']}")
            lines.append("")
        lines.append(f"오늘: 일정 {cnt_cal}건 / 할일 {cnt_todo}건")
        return "\n".join(lines)

    # ---- 색·크기·이모지를 입힌 화면용 ----
    def build_briefing_html(self) -> str:
        secs = self._briefing_sections()
        cnt_cal, cnt_todo = self._brief_today_counts
        d = date.today()
        esc = html_escape
        txt, sub_c, line_c = theme.c("text"), theme.c("subtext"), theme.c("border")

        out = [f"<div style='font-family:Malgun Gothic;color:{txt};'>"]
        # 날짜 머리글
        out.append(
            f"<p style='margin:0 0 2px 0;font-size:20px;font-weight:bold;color:{txt};'>"
            f"{d:%Y년 %m월 %d일} ({self._WEEKDAY_KO[d.weekday()]})</p>"
            f"<p style='margin:0 0 10px 0;font-size:13px;color:{sub_c};'>"
            f"오늘 일정 <b style='color:{theme.strong('blue')};'>{cnt_cal}</b>건"
            f" &nbsp;·&nbsp; 할일 <b style='color:{theme.strong('green')};'>{cnt_todo}</b>건</p>")

        for s in secs:
            col = theme.strong(s["color"])
            bg = theme.strong_bg(s["color"])
            n = s.get("count", len(s["items"]))
            badge = (f"<span style='background-color:{bg};color:{col};font-size:12px;"
                     f"font-weight:bold;'>&nbsp;{n}건&nbsp;</span>" if n else
                     f"<span style='color:{sub_c};font-size:12px;'>&nbsp;0건&nbsp;</span>")
            out.append(f"<hr style='border:1px solid {line_c};'>")
            out.append(
                f"<p style='margin:8px 0 4px 0;font-size:16px;font-weight:bold;color:{col};'>"
                f"{s['icon']} {esc(s['title'])} &nbsp;{badge}</p>")
            if s.get("note"):
                out.append(f"<p style='margin:0 0 4px 6px;font-size:12px;color:{sub_c};'>"
                           f"{esc(s['note'])}</p>")
            if not s["items"]:
                out.append(f"<p style='margin:2px 0 6px 12px;font-size:13px;color:{sub_c};'>"
                           f"{esc(s.get('empty', '없음'))}</p>")
            for it in s["items"]:
                lead = (it.get("lead") or "").strip()
                sub = (it.get("sub") or "").strip()
                head = (f"<span style='background-color:{bg};color:{col};font-weight:bold;'>"
                        f"&nbsp;{esc(lead)}&nbsp;</span>&nbsp;" if lead else "")
                tail = (f" <span style='color:{sub_c};font-size:12px;'>{esc(sub)}</span>"
                        if sub else "")
                out.append(
                    f"<p style='margin:3px 0 3px 12px;font-size:14px;color:{txt};'>"
                    f"{head}<b>{esc(it['text'])}</b>{tail}</p>")
            if s.get("more"):
                out.append(f"<p style='margin:2px 0 4px 12px;font-size:12px;color:{sub_c};'>"
                           f"… 외 {s['more']}건</p>")
            if s.get("hint"):
                out.append(
                    f"<p style='margin:6px 0 8px 12px;font-size:13px;color:{col};'>"
                    f"👉 {esc(s['hint'])}</p>")
        out.append("</div>")
        return "".join(out)

    def show_briefing(self, manual: bool):
        alarm_window.popup("오늘 브리핑", self.build_briefing(), 0, siren=False,
                           html=self.build_briefing_html())

    # ------------------------------------------------------------ 백업
    def _backup(self, manual: bool):
        try:
            self._do_backup(manual)
        except Exception as e:
            # 백업이 실패해도 앱은 계속 돌아야 한다. last_backup 을 세우지 않으므로
            # 다음 기회에 다시 시도한다(예전엔 여기서 터지면 매 초 예외가 났다).
            if manual:
                QMessageBox.warning(self, config.APP_NAME, "백업 실패:\n" + str(e))

    def _do_backup(self, manual: bool):
        bk_dir = config.data_dir() / "backup"
        bk_dir.mkdir(parents=True, exist_ok=True)
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

    def _center_on_screen(self):
        """창을 모니터 가운데로 옮긴다.

        위치를 지정하지 않으면 창이 화면 왼쪽 위에 붙어 제목표시줄이 화면 밖으로
        올라가는 일이 있다. 그러면 창을 끌어 옮길 수가 없다.
        """
        try:
            scr = self.screen() or QGuiApplication.primaryScreen()
            avail = scr.availableGeometry()
            fg = self.frameGeometry()
            if fg.width() <= 1 or fg.height() <= 1:     # 아직 표시 전
                fg.setSize(self.size())
            fg.moveCenter(avail.center())
            # 제목표시줄과 왼쪽 가장자리가 화면 밖으로 나가지 않게
            if fg.top() < avail.top():
                fg.moveTop(avail.top())
            if fg.left() < avail.left():
                fg.moveLeft(avail.left())
            self.move(fg.topLeft())
        except Exception:
            pass

    def showEvent(self, event):
        # 창틀 크기는 화면에 뜬 뒤에야 정확히 알 수 있다 → 첫 표시 때 한 번 더 맞춘다.
        # (이후 사용자가 옮긴 위치는 그대로 둔다)
        super().showEvent(event)
        if not getattr(self, "_centered_once", False):
            self._centered_once = True
            self._center_on_screen()

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        if self._really_close:
            event.accept()
            return
        # 설정에 따라 묻지 않고 바로 처리한다 (기본: 트레이로 내림)
        if self.settings.close_to_tray:
            event.ignore()
            self.hide()
            self.tray.showMessage(config.APP_NAME, "트레이에서 계속 실행 중입니다.",
                                  self._app_icon, 3000)
            return
        self._shutdown()
        event.accept()
        QApplication.quit()

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
