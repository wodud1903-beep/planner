"""메인 화면 (델파이 uDash 이식).

탭1: 이번주 일정(구글 캘린더) + 내 할일(로컬 + 구글 Tasks)
탭2: PC 알람 (요일/시간 반복)
트레이 상주, 1초 타이머로 알람 감시, 시작 시 오늘 브리핑.
카카오톡 스케줄러는 제거했다.  구글 연동은 [Google 로그인] 한 번으로 끝난다.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import uuid
import webbrowser
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from html import escape as html_escape

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QFrame, QHBoxLayout, QHeaderView,
    QLabel, QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea, QSystemTrayIcon,
    QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import (
    alarm_window, backup_dialog, changelog, config, contacts, crashlog, customer_docs,
    dashboard, deliver_cal, drive_path, followup,
    google_client, hotkey, kb, navicons, searchcombo, sheets, sync, theme, updater,
    weekly,
)
from .calendar_window import CalendarWindow
from .customer_dialog import CustomerDialog
from .commission_tab import CommissionTab
from .customer_files_tab import CustomerFilesTab
from .customer_history import CustomerHistoryDialog
from .greeting_tab import GreetingTab
from .kb_tab import KbTab, QuickSearch
from .livesearch import LiveLineEdit
from .doc_viewer import DocViewer
from .edit_dialog import EditDialog
from .google_button import GoogleSignInButton
from .icon import make_icon
from .models import (
    AppSettings, PcAlarm, TaskAlarm, TaskAlarmStore, TodoItem, load_list, save_list,
)
from .settings_dialog import SettingsDialog
from .sidebar import Sidebar

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


# Qt 가 "제한 없음" 으로 치는 크기값. PySide6 이 Q_SIZE_MAX 를 내보내지
# 않아 직접 적어 둔다(Qt 정의값 그대로).
Q_SIZE_MAX = 16777215


class MainWindow(QMainWindow):
    # 백그라운드 스레드 → UI 마샬링
    sig_tasks_done = Signal(object, str, int)   # (할일목록|None, 오류, 조회시작 epoch)
    sig_events_done = Signal(object, str)
    sig_fetch_done = Signal()
    sig_toast = Signal(str, str)
    # 출고 일정 처리 결과 (uid, cal_id, event_id, 날짜, 제목, 오류)
    sig_deliver_cal = Signal(str, str, str, str, str, str)
    # 방금 만든 출고 일정 (CalEvent) — 재조회 없이 목록에 얹는다
    sig_deliver_new = Signal(object)
    sig_account = Signal(str)          # 로그인 계정 이메일 확인됨
    sig_google_login = Signal(bool, str)   # 메인 화면 [Google 로그인] 결과 (성공, 오류)
    sig_synced = Signal(bool)          # Drive 동기화 완료(변경 여부)
    sig_update = Signal(object, str, bool)  # (릴리스정보|None, 오류, 수동여부)
    sig_write_done = Signal(object, object, str)   # (_PendingOp, 실제결과|None, 오류)
    sig_sheet_rows = Signal(object, object, str)   # (행목록|None, 마지막행, 오류)
    sig_sheet_written = Signal(object, object, str)  # (임시행, 실제행번호|None, 오류)
    sig_sheet_ments = Signal(object)                 # {행번호: 고객안내멘트}
    sig_sheet_docs = Signal(object)                  # {행번호: S열 =IMAGE() 수식}
    sig_sheet_uids = Signal(object)                  # {행번호: U열 고객ID}
    sig_sheet_rates = Signal(object)                 # 공유 수당율 표
    sig_sheet_kb = Signal(object)                    # 공유 업무자료 목록
    sig_sync_done = Signal(bool, str, bool)          # (바뀜, 오류, 수동여부)
    sig_sheet_deleted_fail = Signal(object, str)     # (되살릴 행, 오류)

    # 창을 이보다 좁히지는 못하게 한다. 고객관리 표의 열 폭 합(약 996)보다는
    # 좁아도 되지만(가로 스크롤이 생길 뿐), 여기서 더 줄이면 어느 탭이든
    # 버튼 줄이 서로 겹쳐 못 쓰게 된다.
    MIN_WIDTH = 1040                # 왼쪽 메뉴(216) 몫만큼 넓혔다 — 좁으면 메뉴를 접는다
    MIN_HEIGHT = 660                # 세로는 끌어서 바꾸되, 왼쪽 메뉴가 겹치지 않을 만큼은
    TITLE_KEEP = 60                 # 제목표시줄이 화면 아래쪽에 적어도 이만큼은 남게
    # 기본 폭. 1570 은 쓰시는 분이 정해 주신 값(상단바 시절) — 고객명 236 · 내용 255
    # 를 넣고도 남는 폭이다. v1.22 에 왼쪽 메뉴와 카드 여백이 생기며 표 자리가
    # LAYOUT_EXTRA 만큼 줄었으므로 그만큼 더한다(표가 들어가는 폭은 그대로).
    BASE_W = 1570
    LAYOUT_EXTRA = 276              # 메뉴 216 + 카드 바깥·안쪽 여백 − 예전 여백
    DEFAULT_W = BASE_W + LAYOUT_EXTRA
    LAYOUT_VER = 2                  # window.json 에 적는 배치 판(1 = 상단바 시절)
    # 창 폭 기억 — 이 PC 에만 둔다. plan_cfg.json 은 다른 PC 로 동기화되는데,
    # 모니터가 작은 PC 가 화면에 맞춰 줄인 폭이 큰 모니터 PC 로 넘어가면
    # 켤 때마다 서로 창을 좁히게 된다.
    WIN_FILE = "window.json"

    def __init__(self):
        super().__init__()
        self.setWindowTitle(config.APP_NAME)
        # 창 크기 — 가로·세로 모두 끌어서 맞춘다(v1.22.2 부터 세로도. 예전엔 세로를
        # 못 바꾸게 막았는데 "세로도 키우고 싶다" 고 하셨다). 늘어난 세로는 '내 할일'
        # 표가 받는다('이번주 일정' 은 최대 300 이라 허옇게 남지 않는다).
        # ⚠️ 단 하나 지키는 것 — **제목표시줄이 화면 밖으로 나가지 않게.** 제목표시줄이
        #    밖에 있으면 창을 끌어 옮길 수도, 닫을 수도 없다(_keep_on_screen).
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        _avail = self._screen_avail()
        # 고객관리 표(차량가격·내용까지)가 가로 스크롤 없이 들어가는 폭(DEFAULT_W).
        # 화면이 좁으면 어차피 아래 min 이 화면 폭으로 깎으므로 작은 노트북에서도
        # 안전하다(그때는 왼쪽 메뉴를 접으면 표 자리가 넓어진다).
        _w = min(self.DEFAULT_W, _avail.width() - 20)
        _h = min(920, _avail.height() - 60)
        # 보통 크기의 세로 — 지난번에 맞춰 둔 값(없으면 920). 최대화를 풀면 이리 돌아온다
        self._normal_h = self._saved_height(_h, _avail)
        self._normal_w = _w          # 마지막으로 쓰던 보통 가로(아래에서 덮어씀)
        self._maximized = False
        self._snapping = False
        self._keeping = False
        # 옮기거나 키운 뒤 '제목표시줄이 화면 안인가' 를 한 번만 본다(끄는 동안 계속 안 부르게)
        self._keep_timer = QTimer(self)
        self._keep_timer.setSingleShot(True)
        self._keep_timer.setInterval(0)
        self._keep_timer.timeout.connect(self._keep_on_screen)
        # ⚠️ 세로 상한은 걸지 않는다(setMaximumHeight 로 화면 높이를 걸면 최대화가
        #    반쪽이 되거나 죽는다 — 창관리자는 최대화할 때도 상한을 지킨다).
        #    화면보다 커지는 것은 _keep_on_screen 이 줄인다. 하한은 왼쪽 메뉴가
        #    겹치지 않을 만큼만.
        self.setMinimumHeight(min(self.MIN_HEIGHT, _avail.height() - 60))
        self.setMaximumHeight(Q_SIZE_MAX)
        # 가로 상한은 걸지 않는다. 창관리자는 '이 창이 얼마나 커질 수 있는가' 를
        # 이 값으로 판단하는데, 화면폭보다 작은 상한이 걸려 있으면 최대화가
        # 반쪽이 되거나(가로가 그 값에서 멈춤) 최대화 단추 자체가 죽는다.
        # 화면 밖으로 나가지 않게 하는 일은 창관리자가 알아서 한다.
        _lo, _hi = self._width_bounds(_avail)
        self.setMinimumWidth(_lo)
        self.setMaximumWidth(Q_SIZE_MAX)
        self._centered_once = False
        # 폭을 끄는 동안 계속 저장하지 않도록, 멈춘 뒤 한 번만 쓴다
        self._width_timer = QTimer(self)
        self._width_timer.setSingleShot(True)
        self._width_timer.timeout.connect(self._remember_width)
        # 지난번에 맞춰 둔 폭이 있으면 그대로 연다(매번 다시 끌지 않도록)
        self._normal_w = self._saved_width(_w, _avail)
        self.resize(self._normal_w, self._normal_h)
        # 지난번에 최대화로 쓰던 사람은 최대화로 열어 준다
        self._want_maximized = self._saved_maximized()
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
        self._sheet_loaded = False       # 첫 시트 로딩 완료 여부(브리핑 대기용)
        self._fired_cal_alarms: set = set()   # (일정, 분) — 중복 알람 방지
        # 안내멘트를 복사한 적 있는 고객 (시작 시 저장분을 읽어온다)
        self._ment_copied: set = self._load_ment_log()
        # 고객ID → [{date, text}] — 이력 타임라인의 직접 메모
        self._notes: dict = self._load_notes()
        # 고객ID → {template, items[]} — 심사서류 체크리스트
        self._docs: dict = self._load_docs()

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
        self.sig_deliver_cal.connect(self._on_deliver_cal)
        self.sig_deliver_new.connect(self.add_optimistic_event)
        self.sig_account.connect(self._on_account_ready)
        self.sig_google_login.connect(self._on_google_login_done)
        self.sig_synced.connect(self._on_synced)
        self.sig_update.connect(self._on_update_checked)
        self.sig_write_done.connect(self._on_write_done)
        self.sig_sheet_rows.connect(self._on_sheet_rows)
        self.sig_sheet_written.connect(self._on_sheet_written)
        self.sig_sheet_ments.connect(self._on_sheet_ments)
        self.sig_sheet_docs.connect(self._on_sheet_docs)
        self.sig_sheet_uids.connect(self._on_sheet_uids)
        self.sig_sheet_rates.connect(self._on_sheet_rates)
        self.sig_sheet_kb.connect(self._on_sheet_kb)
        self.sig_sync_done.connect(self._on_sync_done)
        self.sig_sheet_deleted_fail.connect(self._on_sheet_delete_fail)

        # 동기화 푸시 디바운스 타이머
        self._sync_timer = QTimer(self)
        self._sync_timer.setSingleShot(True)
        self._sync_timer.timeout.connect(self._do_sync_push)

        # 주기 동기화 — 앱을 켜 둔 채 지내도 다른 PC 의 변경을 받는다.
        # 예전엔 켜는 순간에만 받아서, 하루 종일 띄워 두면 영영 못 봤다.
        self._sync_poll = QTimer(self)
        self._sync_poll.timeout.connect(lambda: self.sync_now_async(manual=False))
        self._sync_poll.start(10 * 60 * 1000)

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

        # 시작 시 업데이트 확인 — 새 판이 있으면 **묻지 않고** 받아서 깐다(v1.23.1, 요청).
        # 지난 업데이트가 실패했으면 먼저 그 이유를 알려 준다.
        updater.clear_attempt_if_done(config.APP_VERSION)
        # 지난 업데이트가 실패했으면 이번에는 자동으로 다시 하지 않는다 — 안내를 읽는 중에
        # 창이 꺼지지 않게(같은 이유로 또 실패하기 쉽다). 다음에 켤 때 한 번 더 해 본다.
        self._update_failed = updater.last_failure()
        QTimer.singleShot(3000, self._tell_update_failure)
        QTimer.singleShot(4000, lambda: self.check_update(manual=False))

        # 창이 뜬 직후 고객관리 시트를 자동으로 불러온다.
        # (백그라운드 스레드라 시작이 느려지지 않는다. 브리핑의 '안내멘트 미발송'
        #  안내에 필요하므로 너무 늦지 않게 시작한다)
        QTimer.singleShot(800, self._auto_load_sheet)

        self.chk_startup.setChecked(_startup_set())

        # 전역 단축키 (Windows) — 창 열기 + 업무자료 빠른검색
        self.hotkeys = hotkey.HotkeyManager(
            QApplication.instance(), int(self.winId()), self._on_hotkey)
        self.hotkeys.set_callback(hotkey.ID_KB, self.open_kb_search)
        self._kb_quick = None
        QTimer.singleShot(0, self._apply_hotkeys)

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
        self.show_startup_screen()

    # ------------------------------------------------------------ 시작 화면
    def show_startup_screen(self):
        """오늘 브리핑 + 주간 요약을 한 창에 띄운다.

        예전에는 브리핑(항상 위로 뜨는 알람 팝업)과 주간 요약(모달 창)을 잇달아
        띄웠다. 모달이 입력을 전부 가로채서, **위에 보이는 브리핑의 [확인] 은
        안 눌리고 뒤에 깔린 주간 요약만 눌렸다.** 창을 하나로 합쳐 없앤다.

        주간 요약은 설정에서 끌 수 있고(weekly_on), 시트를 아직 못 읽었으면
        그 자리에 이유를 적는다.
        """
        # 이미 떠 있으면 또 띄우지 않는다. 이 창은 모달이라 위에 하나가 더
        # 겹치면 아래 것의 [확인] 이 안 눌린다 — 예전에 브리핑과 주간 요약을
        # 따로 띄웠을 때 겪은 그 문제가 같은 창끼리 다시 생긴다.
        # (시작 브리핑 타이머가 도는 중에 [주간 요약] 을 누르면 실제로 겹친다)
        if getattr(self, "_startup_open", False):
            return
        from .startup_dialog import StartupDialog
        rows = self.sheet_rows if self.settings.weekly_on else []
        self._startup_open = True
        try:
            StartupDialog.show_for(self.build_briefing_html(),
                                   self.build_briefing(),
                                   rows, date.today(), self)
        finally:
            self._startup_open = False

    def _on_hotkey(self):
        self.show_window()

    def _apply_hotkeys(self):
        """두 전역 단축키를 설정대로 등록한다(한쪽 실패가 다른 쪽을 막지 않는다)."""
        try:
            self.hotkeys.apply(self.settings)
        except Exception:
            pass
        try:
            self.hotkeys.apply_kb(self.settings)
        except Exception:
            pass

    # ------------------------------------------------------------ 테마
    def _apply_side_theme(self):
        self.sidebar.apply_theme()      # 메뉴 아이콘을 새 테마 색으로 다시 그린다
        for t in getattr(self, "dash_tiles", []):
            t.apply_theme()
        self.refresh_dashboard()        # 카드 글의 색도 테마를 따른다

    def apply_theme(self):
        theme.set_theme(getattr(self.settings, "theme", "")
                        or ("dark" if self.settings.dark_mode else "light"))
        app = QApplication.instance()
        if app:
            theme.apply_to_app(app)   # 스타일시트 + 팔레트 함께
        self._apply_side_theme()
        if hasattr(self, "btn_google"):
            self.btn_google.apply_theme()   # 구글 단추는 제 배색을 따로 쓴다
        self.refresh_calendar()
        self.refresh_todo()
        self.refresh_alarm()
        if getattr(self, "_summary_data", None):
            self._show_summary(self._summary_data)   # 색상 다시 계산
        if hasattr(self, "tbl_cust"):
            self.tbl_cust.setStyleSheet(self._cust_table_css())
            self.refresh_customers()
        if hasattr(self, "tab_comm"):
            self.tab_comm.apply_theme()
        if hasattr(self, "tab_files"):
            self.tab_files.apply_theme()
        if hasattr(self, "tab_greet"):
            self.tab_greet.apply_theme()
        if hasattr(self, "tab_kb"):
            self.tab_kb.apply_theme()
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
        # 계정 확인이 (성공이든 실패든) 끝났다 — 이제부터 틱 백업이 이 폴더를 본다
        self._account_checked = True
        if not email:
            # 계정을 확인하지 못하면 어느 폴더가 이 사람 데이터인지 알 수 없다.
            # 이때 동기화를 강행하면 공용 폴더(대개 비어 있음)를 번들로 올려
            # 다른 PC 의 데이터까지 지워버린다. 그래서 아예 건너뛴다.
            self.lbl_account.setText("계정 확인 실패 — 동기화를 건너뜁니다")
            self._backup(manual=False)
            self.fetch_all_async()
            return
        self.account_email = email
        config.set_account(email)
        self.lbl_account.setText(email)
        sync.migrate_legacy()
        self.reload_data()   # 계정 폴더 기준으로 다시 로드
        # 이제야 이 계정의 시트 설정을 알 수 있다 → 바로 불러오기 시도
        self._auto_load_sheet()
        self.fetch_rates_async()      # 공유 수당율(전용 시트)도 함께 받아온다
        self.fetch_kb_async()         # 공유 업무자료도 같은 시트에서 받아온다
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

    def sync_now_async(self, manual: bool = False):
        """받고 → 합쳐서 올린다. 주기 타이머와 [지금 동기화] 가 함께 쓴다."""
        if not self.gauth.is_connected():
            if manual:
                QMessageBox.information(
                    self, config.APP_NAME,
                    "구글에 연결되어 있지 않습니다.\n[설정] 에서 Google 로그인을 먼저 해 주세요.")
            return
        if getattr(self, "_syncing", False):
            return                      # 앞의 동기화가 아직 도는 중
        self._syncing = True

        def worker():
            changed, err = False, ""
            try:
                changed = sync.sync_now(self.gauth)
            except Exception as e:
                err = str(e).splitlines()[0][:120]
            self.sig_sync_done.emit(changed, err, manual)
        threading.Thread(target=worker, daemon=True).start()

    def _on_sync_done(self, changed: bool, err: str, manual: bool):
        self._syncing = False
        if changed:
            self.reload_data()
            self.refresh_calendar()
            self.refresh_todo()
            self.refresh_alarm()
        if not manual:
            if changed:
                self.sig_toast.emit(config.APP_NAME,
                                    "다른 PC의 변경사항을 받았습니다.")
            return
        if err:
            QMessageBox.warning(self, config.APP_NAME, "동기화 실패:\n" + err)
        elif changed:
            QMessageBox.information(self, config.APP_NAME,
                                    "다른 PC의 변경사항을 받아 반영했습니다.")
        else:
            QMessageBox.information(self, config.APP_NAME,
                                    "이미 최신입니다. 이 PC의 내용도 올렸습니다.")

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
        self._docs = self._load_docs()
        if hasattr(self, "tab_greet"):
            self.tab_greet.reload()      # 계정이 바뀌면 그 계정의 문구로
        if hasattr(self, "tab_kb"):
            self.tab_kb.set_account(getattr(self, "account_email", ""))
            self.tab_kb.reload()
        if hasattr(self, "tab_files"):
            # 설정 객체를 통째로 새로 읽었으므로 탭에도 새것을 넘긴다.
            # (탭은 창의 설정을 직접 보기도 하지만, 여기서도 확실히 맞춰 둔다)
            self.tab_files.set_settings(self.settings)
            self._files_loaded = False       # 계정이 바뀌면 폴더도 달라진다
        # 설정 파생 UI 반영
        self.chk_autofetch.blockSignals(True)
        self.chk_autofetch.setChecked(self.settings.auto_fetch)
        self.chk_autofetch.blockSignals(False)
        self.apply_theme()
        self._apply_hotkeys()
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
                # exists() 도 결국 stat 이다. 한 번만 부르고 없으면 넘어간다.
                m = max(m, f.stat().st_mtime)
            except OSError:
                pass
        return m

    # 파일이 바뀌었는지 다시 보는 간격(초). 1초 타이머마다 보면 파일 다섯 개를
    # 하루 43만 번 들여다보게 되는데, 바뀌자마자 올려야 할 만큼 급한 일이 아니다
    # (어차피 올리는 것도 2.5초 미뤄 두고 모아서 한다).
    AUTOSYNC_EVERY = 5

    def _maybe_autosync(self):
        """로컬 데이터 파일이 바뀌었으면(어느 경로로든) 업로드 예약."""
        if not self.gauth.is_connected():
            return
        self._autosync_tick = getattr(self, "_autosync_tick", 0) + 1
        if self._autosync_tick % self.AUTOSYNC_EVERY:
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
        if isinstance(goto, date):
            self._cal_win.goto_date(goto)

    # ⚠️ 캘린더 창은 CalendarWindow 쪽에서 **따로 뜨는 창**으로 만든다
    #    (Qt.Window). 예전엔 이 창의 자식 위젯이라 이 창보다 넓게 만들어도
    #    넘치는 만큼 잘려 나갔다 — 오른쪽 일정 열이 통째로 안 보이고, 손으로
    #    창을 넓혀야 나타났다. 그때는 여는 김에 이 창을 340px 넓혀 자리를
    #    만들어 줬는데, 이 창 크기가 제멋대로 바뀌는 게 더 불편했다.
    #    이제 캘린더는 제 크기를 스스로 갖고, 이 창은 건드리지 않는다.

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
            # 교체 배치가 실행됨 → 바로 끝낸다(배치가 우리가 끝나기를 기다린다).
            # ⚠️ QApplication.quit() 로 끝내면 파이썬 마무리 정리에서 멈춰 프로그램이 남는
            #    일이 있었다 — 그러면 새 판이 '이미 실행 중' 으로 보고 꺼졌다(v1.22.1 무한
            #    업데이트). 저장할 것은 _shutdown 에서 끝내고 곧바로 끝낸다.
            self._really_close = True
            self._shutdown()
            crashlog.clean_exit()
            crashlog.shutdown()
            os._exit(0)
        if err:
            if manual:
                QMessageBox.warning(self, config.APP_NAME, "업데이트 실패:\n" + err)
            elif getattr(self, "_auto_updating", False):
                self._auto_updating = False
                self.sig_toast.emit(config.APP_NAME, "자동 업데이트를 받지 못했습니다 — 다음에 켤 때 "
                                                     "다시 해 봅니다.")
            return
        if not res:
            if manual:
                QMessageBox.information(self, config.APP_NAME,
                                       f"현재 최신 버전입니다. (v{config.APP_VERSION})")
            return
        if not updater.is_frozen():
            if manual:
                QMessageBox.information(
                    self, config.APP_NAME,
                    "개발 모드에서는 자동 교체가 되지 않습니다.\n"
                    f"릴리스에서 {config.UPDATE_ASSET_NAME} 를 받아 사용하세요.")
            return
        if not manual:
            # 켤 때 — 묻지 않고 받는다. 단 같은 판에서 두 번 실패했으면 그만둔다
            # (안 그러면 켤 때마다 꺼졌다 켜지기를 되풀이한다). 그때는 한 번 알린다.
            ver = res["version"]
            if getattr(self, "_update_failed", ""):
                return
            if updater.attempts(ver) >= updater.AUTO_MAX_TRIES:
                if not getattr(self, "_auto_stop_told", False):
                    self._auto_stop_told = True
                    QMessageBox.information(
                        self, config.APP_NAME,
                        f"새 버전 {ver} 자동 업데이트가 {updater.AUTO_MAX_TRIES}번 실패해 "
                        "이번에는 건너뜁니다.\n트레이 아이콘 → [업데이트 확인] 으로 다시 하거나, "
                        "받는 곳에서 직접 받아 주세요.")
                return
            updater.note_attempt(ver)
            self._auto_updating = True
            self.sig_toast.emit(config.APP_NAME, f"새 버전 {ver} 을(를) 받는 중입니다 — "
                                                 "다 받으면 저절로 다시 켜집니다.")
            self._start_update(res, manual=False)
            return
        msg = (f"새 버전 {res['version']} 이(가) 있습니다. (현재 v{config.APP_VERSION})\n\n"
               f"{(res.get('notes') or '').strip()[:300]}\n\n지금 업데이트할까요?")
        if QMessageBox.question(self, config.APP_NAME, msg) != QMessageBox.Yes:
            return
        self.sig_toast.emit(config.APP_NAME, "업데이트 다운로드 중...")
        self._start_update(res, manual=True)

    def _start_update(self, res, manual: bool):
        def worker():
            try:
                path = updater.download(res["asset_url"])
                updater.apply_and_restart(path)
                self.sig_update.emit("__applied__", "", manual)
            except Exception as e:
                self.sig_update.emit(None, str(e), manual)
        threading.Thread(target=worker, daemon=True).start()

    def _tell_update_failure(self):
        """지난 업데이트를 마치지 못했으면(배치가 남긴 결과) 이유와 받는 곳을 알려 준다."""
        reason = getattr(self, "_update_failed", "") or updater.last_failure()
        if not reason:
            return
        updater.ack_failure()
        box = QMessageBox(self)
        box.setWindowTitle(config.APP_NAME)
        box.setIcon(QMessageBox.Warning)
        box.setText(updater.failure_text(reason))
        go = box.addButton("받는 곳 열기", QMessageBox.ActionRole)
        box.addButton("닫기", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is go:
            webbrowser.open(f"https://github.com/{config.UPDATE_REPO}/releases/latest")

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 왼쪽 메뉴 — 플로우처럼 모든 메뉴를 한 줄에(v1.22). 예전 상단바의 계정·버전·
        # 'PC 시작 시 실행' 과 [설정]·[캘린더 열기] 도 이리로 옮겼다(이름은 그대로).
        self.sidebar = Sidebar(config.APP_NAME)
        outer.addWidget(self.sidebar)
        self.lbl_account = self.sidebar.lbl_account
        # 버전을 눌러 변경 이력을 연다 — 업데이트하고 '뭐가 바뀌었나' 를 바로 보게
        self.btn_ver = self.sidebar.btn_ver
        self.btn_ver.setText(f"v{config.APP_VERSION}")
        self.btn_ver.setToolTip("이 버전과 지난 버전에서 무엇이 바뀌었는지 봅니다")
        self.btn_ver.clicked.connect(self.open_changelog)
        self.chk_startup = self.sidebar.chk_startup
        self.chk_startup.toggled.connect(lambda on: _set_startup(on))
        self.btn_settings = self.sidebar.btn_settings
        self.btn_settings.clicked.connect(self.on_settings_click)
        self.btn_calendar = self.sidebar.btn_calendar
        # ⚠️ 람다로 감싼다 — 단추는 눌림 여부(False)를 넘겨, open_calendar 가 그걸 '갈 날짜' 로
        #    받아 오류가 났다(v1.22.1 기록: 'bool' object has no attribute 'year').
        self.btn_calendar.clicked.connect(lambda: self.open_calendar())
        self.sidebar.btn_primary.clicked.connect(self.quick_add_todo)

        # 오른쪽 — 쪽 제목줄 + 흰 카드(탭 내용)
        area = QWidget()
        area.setObjectName("pagearea")
        rv = QVBoxLayout(area)
        rv.setContentsMargins(22, 14, 20, 18)
        rv.setSpacing(10)
        head = QHBoxLayout()
        head.setContentsMargins(2, 0, 2, 0)
        self.lbl_page = QLabel("")
        self.lbl_page.setObjectName("pagetitle")
        head.addWidget(self.lbl_page)
        head.addStretch(1)
        self.lbl_today = QLabel("")
        self.lbl_today.setObjectName("pagedate")
        head.addWidget(self.lbl_today)
        rv.addLayout(head)

        # 화면 보관함 — QTabWidget 그대로 두고 **탭 막대만 숨긴다**. 고르는 일은 왼쪽
        # 메뉴가 한다. 탭으로 찾아가는 코드(캘린더 → '해당 일정으로 이동' 등)는
        # 그대로 돌고, 메뉴는 탭 순서를 따라 그린다(_sync_nav).
        # 사람마다 자주 쓰는 메뉴가 달라 끌어서 순서를 바꾸게 하고, 그 순서를 기억한다.
        # (설정에 담아 두므로 사무실 PC 와 집 PC 가 같은 배치가 된다)
        self.tabs = QTabWidget()
        self.tabs.setObjectName("pages")
        self.tabs.tabBar().hide()
        rv.addWidget(self.tabs, 1)
        outer.addWidget(area, 1)

        self.tab_main = self._build_main_tab()
        self.tabs.addTab(self.tab_main, "대시보드")
        # 탭 순서를 사람이 바꿀 수 있으므로 번호로 찾으면 안 된다.
        # 캘린더에서 '해당 일정으로 이동' 할 때 이 위젯으로 찾는다.
        self.tab_cust = self._build_customer_tab()
        self.tabs.addTab(self.tab_cust, "고객관리")
        # 고객별 서류 — 고객관리 바로 옆에 둔다(같은 고객을 두고 오가므로).
        # 폴더가 크면 훑는 데 몇 초 걸리므로, 켤 때가 아니라 탭을 처음 열 때 읽는다.
        self.tab_files = CustomerFilesTab(self.settings, self.gauth)
        self.tabs.addTab(self.tab_files, "고객정보")
        self._files_loaded = False
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.tab_greet = GreetingTab()
        self.tab_greet.on_changed = self._touch_sync
        self.tabs.addTab(self.tab_greet, "멘트복사")
        self.tab_kb = KbTab()
        self.tab_kb.set_auth(self.gauth)        # 첨부(그림·PDF) 올리기·받기
        self.tab_kb.on_changed = self._touch_sync
        self.tab_kb.on_push_shared = self._push_kb_shared
        self.tabs.addTab(self.tab_kb, "자료검색")
        self.tab_comm = CommissionTab()
        self.tabs.addTab(self.tab_comm, "수당계산기")
        self.tabs.addTab(self._build_alarm_tab(), "PC 알람")
        # 쪽 제목줄이 이름을 크게 보여 주므로 화면 안의 작은 제목('💬 멘트 복사' 등)은
        # 숨긴다 — 같은 이름이 두 번 나와 어수선했다. 설명·[편집] 단추는 그대로.
        for t in (self.tab_greet, self.tab_kb):
            t.lbl_title.hide()
        self._pad_pages()
        # 지난번에 맞춰 둔 순서로 되돌린 뒤부터 바뀜을 기록한다
        # (되돌리는 동안 나는 tabMoved 까지 저장하면 순서가 뒤엉킨다)
        self._restore_tab_order()
        self.tabs.tabBar().tabMoved.connect(self._remember_tab_order)
        self.tabs.tabBar().tabMoved.connect(lambda *_a: self._sync_nav())
        self.tabs.currentChanged.connect(self._on_page_changed)
        self.sidebar.navigate.connect(self.tabs.setCurrentIndex)
        self.sidebar.nav.orderChanged.connect(self._on_nav_reordered)
        self.sidebar.set_collapsed(bool(getattr(self.settings, "side_collapsed", False)))
        self.sidebar.collapsedChanged.connect(self._on_side_collapsed)
        self._sync_nav()
        self._on_page_changed(self.tabs.currentIndex())

    def _pad_pages(self):
        """화면마다 흰 카드 한 장 + 고른 안쪽 여백. 대시보드는 카드 여러 장이라 바탕 그대로."""
        for i in range(self.tabs.count()):
            page = self.tabs.widget(i)
            if page is self.tab_main:
                continue
            page.setObjectName("pagecard")
            page.setAttribute(Qt.WA_StyledBackground, True)
            lay = page.layout()
            if lay is not None:
                lay.setContentsMargins(18, 16, 18, 16)

    # ------------------------------------------------------------ 왼쪽 메뉴
    def _sync_nav(self):
        """메뉴를 지금 탭 순서대로 다시 그린다."""
        pages = [(self.tabs.tabText(i), navicons.for_tab(self.tabs.tabText(i)))
                 for i in range(self.tabs.count())]
        self.sidebar.set_pages(pages, self.tabs.currentIndex())

    def _on_page_changed(self, idx: int):
        self.sidebar.select(idx)
        self._paint_page_title()
        self._paint_today()

    def _paint_page_title(self):
        """쪽 제목 — 대시보드는 인사말(플로우처럼), 다른 화면은 메뉴 이름."""
        idx = self.tabs.currentIndex()
        if idx >= 0 and self.tabs.widget(idx) is self.tab_main:
            text = dashboard.greeting()
        else:
            text = self.tabs.tabText(idx) if idx >= 0 else ""
        if self.lbl_page.text() != text:
            self.lbl_page.setText(text)

    def _paint_today(self):
        d = date.today()
        self.lbl_today.setText(f"{d.month}월 {d.day}일 ({'월화수목금토일'[d.weekday()]})")

    def _on_nav_reordered(self, names: list):
        """메뉴를 끌어 옮겼다 → 탭도 같은 순서로, 그리고 기억한다."""
        self._move_tabs(names)
        self._remember_tab_order()
        self._sync_nav()

    def _on_side_collapsed(self, on: bool):
        try:
            self.settings.side_collapsed = bool(on)
            self._save_settings()
        except Exception:
            pass

    def quick_add_todo(self):
        """[＋ 할일 추가] — 어느 화면에서든 대시보드로 가서 바로 적는다."""
        self.tabs.setCurrentWidget(self.tab_main)
        self.on_todo_add()

    # ------------------------------------------------------------ 탭 순서
    def _tab_names(self) -> list:
        return [self.tabs.tabText(i) for i in range(self.tabs.count())]

    # 이름을 바꾼 메뉴 — 저장된 순서의 옛 이름을 새 이름으로 읽는다(안 그러면 맨 끝으로 밀린다)
    _TAB_RENAMED = {"일정 / 할일": "대시보드"}

    def _restore_tab_order(self):
        """설정에 적힌 순서대로 탭을 옮긴다."""
        want = [self._TAB_RENAMED.get(str(x), str(x))
                for x in (getattr(self.settings, "tab_order", None) or [])]
        if want:
            self._move_tabs(want)

    def _move_tabs(self, want: list):
        """이름 순서대로 탭을 옮긴다(저장은 하지 않는다).

        판을 바꾼 뒤 탭이 늘거나 줄 수 있으므로 **이름으로** 맞춘다. 목록에 없는
        탭(새로 생긴 것)은 건드리지 않고 제자리에 둔다 — 새 기능이 눈에 안 띄는
        맨 끝으로 밀리지 않게.
        """
        self._tab_moving = True
        try:
            at = 0
            for name in want:
                cur = self._tab_names()
                if name not in cur:
                    continue            # 없어진 탭
                i = cur.index(name)
                if i != at:
                    self.tabs.tabBar().moveTab(i, at)
                at += 1
        except Exception:
            pass
        finally:
            self._tab_moving = False

    def _remember_tab_order(self, *args):
        if getattr(self, "_tab_moving", False):
            return
        try:
            self.settings.tab_order = self._tab_names()
            self._save_settings()
        except Exception:
            pass

    def open_files_for(self, name: str):
        """'고객정보' 탭으로 건너가 그 고객 이름으로 찾아 둔다."""
        if not hasattr(self, "tab_files"):
            return
        self.tabs.setCurrentWidget(self.tab_files)   # 여기서 첫 훑기가 돈다
        self.tab_files.search_for(name)

    def _on_tab_changed(self, idx: int):
        """'고객정보' 탭은 처음 열 때 한 번 읽는다(그 뒤엔 [새로고침])."""
        if (not self._files_loaded and hasattr(self, "tab_files")
                and self.tabs.widget(idx) is self.tab_files):
            self._files_loaded = True
            self.tab_files.reload()

    def _build_main_tab(self) -> QWidget:
        """대시보드 — 플로우 첫 화면처럼 흰 카드를 늘어놓는다(v1.23, dashboard.py).

        예전 '일정 / 할일' 화면의 표·단추는 **그대로** 카드에 담았다(이름·연결 그대로).
        [주간 요약] 을 눌러야 보이던 오늘 브리핑·이번 주 요약을 늘 펼쳐 두고, 다음 주
        요약을 더했다. 내용은 refresh_dashboard() 가 모아서 그린다.
        """
        w = QWidget()
        w.setObjectName("dashpage")
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        scroll.setWidget(body)
        outer.addWidget(scroll)
        v = QVBoxLayout(body)
        v.setContentsMargins(2, 0, 8, 8)
        v.setSpacing(12)

        # 위 조작줄
        # [설정]·[캘린더 열기] 는 왼쪽 메뉴로 옮겼다(어느 화면에서든 쓰는 것이라)
        row = QHBoxLayout()
        self.btn_fetch = QPushButton("새로고침")
        self.btn_fetch.clicked.connect(self.fetch_all_async)
        row.addWidget(self.btn_fetch)
        # 켤 때 뜨는 그 화면(오늘 브리핑 + 주간 요약)을 언제든 다시 연다.
        # 예전엔 브리핑은 트레이에, 주간 요약은 고객관리 탭에 따로 있어서
        # 같은 내용을 두 군데서 찾아야 했다.
        self.btn_weekly = QPushButton("주간 요약")
        self.btn_weekly.setToolTip(
            "오늘 브리핑과 이번 주 요약을 한 화면으로 — 켤 때 나오는 그 화면입니다")
        self.btn_weekly.clicked.connect(self.show_startup_screen)
        row.addWidget(self.btn_weekly)
        self.lbl_status = QLabel("")
        row.addWidget(self.lbl_status)
        # 로그인 전에는 여기서 바로 로그인할 수 있게 한다. 예전엔 [설정] 을 열어야
        # 로그인 단추가 나와서, 처음 받은 사람은 그걸 찾지 못했다.
        self.btn_google = GoogleSignInButton()
        self.btn_google.clicked.connect(self.on_google_login_click)
        self.btn_google.hide()          # update_google_status() 가 켜고 끈다
        row.addWidget(self.btn_google)
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

        # 바로가기 — 플로우 첫 화면의 앱 아이콘 줄. 탭은 아직 안 만들었으므로 누를 때 찾는다.
        tiles = QHBoxLayout()
        tiles.setSpacing(4)
        self.dash_tiles = []
        for icon_name, text, go in (
                ("calendar", "캘린더", lambda: self.open_calendar()),
                ("people", "고객관리", lambda: self.tabs.setCurrentWidget(self.tab_cust)),
                ("folder", "고객정보", lambda: self.tabs.setCurrentWidget(self.tab_files)),
                ("search", "자료검색", lambda: self.tabs.setCurrentWidget(self.tab_kb)),
                ("chat", "멘트복사", lambda: self.tabs.setCurrentWidget(self.tab_greet)),
                ("calc", "수당계산기", lambda: self.tabs.setCurrentWidget(self.tab_comm))):
            t = dashboard.ShortcutTile(icon_name, text)
            t.clicked.connect(go)
            tiles.addWidget(t)
            self.dash_tiles.append(t)
        tiles.addStretch()
        v.addLayout(tiles)

        # ---- 내 할일 ----
        self.card_todo = dashboard.Card("내 할일")
        self.btn_todo_add = QPushButton("＋ 할일 추가")
        self.btn_todo_add.setObjectName("dashprimary")
        self.btn_todo_add.setCursor(Qt.PointingHandCursor)
        self.btn_todo_add.clicked.connect(self.on_todo_add)
        self.card_todo.add_action(self.btn_todo_add)
        for text, slot in [
            ("수정", self.on_todo_edit), ("삭제", self.on_todo_del),
            ("완료", self.on_todo_done), ("메모 복사", self.on_todo_copy),
        ]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            self.card_todo.add_action(b)
        # 전체 선택/해제
        self.btn_todo_all = QPushButton("전체선택")
        self.btn_todo_all.clicked.connect(self._toggle_all_todo_checks)
        self.card_todo.add_action(self.btn_todo_all)
        # 맨 왼쪽에 체크박스 열(선택) 추가 → 여러 건 일괄 완료
        self.tbl_todo = self._make_table(
            ["선택", "날짜", "시각", "할일", "알람", "메모"], [46, 110, 70, 300, 56, 200],
            stretch_last=False)
        # 카드 폭에 맞춘다 — '할일' 칸이 남는 폭을 받는다(가로 스크롤이 생기지 않게)
        self.tbl_todo.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.tbl_todo.doubleClicked.connect(self._on_todo_dblclick)
        # 우클릭 컨텍스트 메뉴 (버튼과 동일한 동작)
        self.tbl_todo.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tbl_todo.customContextMenuRequested.connect(self._todo_context_menu)
        self.card_todo.body.addWidget(self.tbl_todo)

        # ---- 오늘 브리핑 · 이번 주 요약 · 다음 주 요약 ----
        def text_card(title, what):
            c = dashboard.Card(title)
            btn = QPushButton("복사")
            btn.setObjectName("cardbtn")
            btn.setToolTip("이 카드의 내용을 글로 복사합니다(카톡에 붙여 넣기)")
            btn.clicked.connect(lambda: self._copy_dash(what))
            c.add_action(btn)
            t = dashboard.text_view()
            c.body.addWidget(t)
            return c, t

        self.card_brief, self.txt_dash_brief = text_card("오늘 브리핑", "brief")

        # ---- 이번주 일정 ----
        self.lbl_week = QLabel("이번주 일정")
        self.card_sched = dashboard.Card(title_label=self.lbl_week)
        self.tbl_week = self._make_table(["날짜", "시각", "구분", "내용"], [104, 70, 80, 160])
        self.tbl_week.setColumnHidden(2, True)    # 늘 '일정' 이라 카드에서는 접어 둔다
        # 일정을 더블클릭하면 캘린더 창이 그 날짜로 열린다 (바로 수정·삭제 가능)
        self.tbl_week.doubleClicked.connect(self._on_week_dblclick)
        self.card_sched.body.addWidget(self.tbl_week)

        self.card_this, self.txt_dash_week = text_card("이번 주 요약", "week")
        self.card_next, self.txt_dash_next = text_card("다음 주 요약", "next")

        for c in (self.card_todo, self.card_brief):
            c.setMinimumHeight(330)
        for c in (self.card_sched, self.card_this, self.card_next):
            c.setMinimumHeight(320)
        self.dash_grid = dashboard.DashGrid([self.card_todo, self.card_brief],
                                            [self.card_sched, self.card_this, self.card_next])
        v.addWidget(self.dash_grid, 1)

        # 일정·할일·시트가 한꺼번에 바뀌어도 한 번만 그린다
        self._dash_timer = QTimer(self)
        self._dash_timer.setSingleShot(True)
        self._dash_timer.setInterval(120)
        self._dash_timer.timeout.connect(self._paint_dashboard)
        return w

    # ------------------------------------------------------------ 대시보드 내용
    def refresh_dashboard(self):
        t = getattr(self, "_dash_timer", None)
        if t is not None:
            t.start()

    def _paint_dashboard(self):
        today = date.today()
        try:
            self.txt_dash_brief.setHtml(self.build_briefing_html(with_head=False))
            n_cal, n_todo = self._brief_today_counts
            self.card_brief.set_count(f"오늘 일정 {n_cal} · 할일 {n_todo}")
        except Exception as e:
            self.txt_dash_brief.setPlainText(f"브리핑을 만들지 못했습니다: {e}")
        mon, sun = weekly.week_range(today)
        self.card_this.set_count(f"{mon:%m/%d} ~ {sun:%m/%d}")
        if self.sheet_rows:
            self.txt_dash_week.setHtml(weekly.to_html(self.sheet_rows, today, head=False))
        else:
            self.txt_dash_week.setHtml(self._dash_need_sheet())
        nmon, nsun = weekly.week_range(today + timedelta(days=7))
        self.card_next.set_count(f"{nmon:%m/%d} ~ {nsun:%m/%d}")
        html = weekly.render_html("", self._next_week_sections())
        if not self.sheet_rows:
            html += self._dash_need_sheet("출고 예정·계약은 ")
        self.txt_dash_next.setHtml(html)
        self.card_todo.set_count(f"{self.tbl_todo.rowCount()}건")

    def _dash_need_sheet(self, lead: str = "") -> str:
        return (f"<p style='color:{theme.c('subtext')};'>{html_escape(lead)}"
                "고객관리 시트를 읽은 뒤에 만들어집니다.<br>"
                "[고객관리] 에서 [불러오기] 를 눌러 주세요.</p>")

    def _next_week_sections(self) -> list:
        """다음 주(월~일) — 구글 일정 · 할일 · (시트) 출고 예정 · 계약."""
        today = date.today()
        mon, sun = weekly.week_range(today + timedelta(days=7))
        evs = sorted((ev for ev in self.cal_events if mon <= ev.start.date() <= sun),
                     key=lambda e: e.start)
        secs = [{
            "icon": "📅", "title": "다음 주 일정", "color": "blue",
            "items": [{"lead": self._d_label(ev.start.date()), "text": ev.summary,
                       "sub": ev.time_text() if ev.has_time else ""} for ev in evs[:20]],
            "count": len(evs), "more": max(0, len(evs) - 20),
            "empty": "다음 주 일정이 없습니다",
        }]
        todo = []
        for it in self.todos:
            if it.done or it.repeats:
                continue
            if it.run_date and mon <= it.run_date <= sun:
                todo.append((it.run_date, it.title))
        for tk in self.visible_gtasks():
            if tk.has_due and tk.due and mon <= tk.due <= sun:
                todo.append((tk.due, tk.title))
        todo.sort(key=lambda x: x[0])
        secs.append({
            "icon": "✅", "title": "다음 주 할일", "color": "green",
            "items": [{"lead": self._d_label(d), "text": t} for d, t in todo[:20]],
            "count": len(todo), "more": max(0, len(todo) - 20),
            "empty": "다음 주가 마감인 할일이 없습니다",
        })
        if self.sheet_rows:
            secs += weekly.sections(self.sheet_rows, mon, word="다음 주", week_only=True)
        return secs

    def _copy_dash(self, what: str):
        today = date.today()
        if what == "brief":
            text = self.build_briefing()
        elif what == "week":
            text = (weekly.to_text(self.sheet_rows, today) if self.sheet_rows
                    else "고객관리 시트를 읽은 뒤에 만들어집니다.")
        else:
            nmon, nsun = weekly.week_range(today + timedelta(days=7))
            text = weekly.render_text(f"{nmon:%Y년 %m월 %d일} ~ {nsun:%m월 %d일} 다음 주 요약",
                                      self._next_week_sections())
        QGuiApplication.clipboard().setText(text)
        self.lbl_status.setText("복사됨 ✓  카카오톡에 붙여 넣으세요")

    # ------------------------------------------------------ 고객관리(구글 시트)
    def _build_customer_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        row = QHBoxLayout()
        self.btn_cust_load = QPushButton("불러오기")
        self.btn_cust_load.clicked.connect(lambda: self.load_sheet_async(manual=True))
        row.addWidget(self.btn_cust_load)
        # 표를 더블클릭하면 [수정] 이 열린다.
        # [서류]·[이력] 은 버튼 줄에서 뺐다(내용 칸에 적으신다고 하셔서).
        # 다만 지워 버리지는 않고 **우클릭 메뉴에 남겨** 둔다 — 이력에는 그동안
        # 적어 두신 상담 메모가 들어 있어, 길이 아예 없으면 그 기록에 닿을 수 없다.
        for text, slot in [("고객 추가", self.on_customer_add),
                           ("삭제", self.on_customer_del)]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        self.btn_cust_open = QPushButton("시트 열기")
        self.btn_cust_open.clicked.connect(self._open_sheet)
        row.addWidget(self.btn_cust_open)
        # [주간 요약] 은 [대시보드] 의 [새로고침] 옆으로 옮겼다.
        # 브리핑과 한 화면이 되었으니 하루를 여는 자리에 있는 편이 맞다.
        row.addStretch()
        row.addWidget(QLabel("검색:"))
        # 한글 마지막 글자(조합 중)까지 바로 찾는다 — livesearch.py 설명
        self.ed_cust_find = LiveLineEdit()
        self.ed_cust_find.setPlaceholderText("고객명 · 차종 · 금융사")
        self.ed_cust_find.setFixedWidth(220)
        self.ed_cust_find.liveText.connect(lambda _t: self.refresh_customers())
        row.addWidget(self.ed_cust_find)
        v.addLayout(row)

        # 상단 발주 현황 (시트 N1:O4) — 켜자마자 제일 먼저 눈에 들어와야 하는 줄이라
        # 글자를 키우고 패널 배경을 깔아 한 덩어리로 보이게 한다(_show_summary).
        self.lbl_cust_summary = QLabel("")
        self.lbl_cust_summary.setTextFormat(Qt.RichText)
        self.lbl_cust_summary.hide()
        v.addWidget(self.lbl_cust_summary)

        self.lbl_cust = QLabel("고객관리 시트를 불러오려면 [불러오기]를 누르세요.")
        v.addWidget(self.lbl_cust)

        # 안내멘트·견적서는 버튼만 들어가므로 버튼 폭이면 충분하다.
        # '내용' 은 길어서 다 못 보여 준다 — 남는 폭을 이 열이 받고, 좁아지면
        # 이 열부터 줄어든다(_fit_cust_columns). 잘린 부분은 툴팁으로 본다.
        #
        # 고객명(236) · 내용(255) · 안내멘트(80) 는 쓰시는 분이 직접 정해 주신 값.
        # 안내멘트가 80 인 이유 — 복사하면 단추 글자가 '복사' → '✓ 복사' 로
        # 길어지는데, 68 일 때 그 체크표시가 잘렸다.
        # 나머지 폭은 눈대중이 아니라 실제로 그려 보고 sizeHintForColumn 으로
        # 잰 값이다. 기준으로 삼은 '가장 긴 현실적인 값' —
        #   금융사 '우리금융캐피탈' · 차종 '카니발 9인승 하이리무진'
        #   금액 '₩145,800,000' · 날짜 '2026. 12. 31'
        # 잘려도 되는 건 '내용' 뿐이므로, 글씨 크기를 건드리면 여기도 다시 재야 한다.
        self.tbl_cust = self._make_table(
            ["순번", "고객명 / 사업자", "금융사", "차종", "차량가격",
             "계약일", "출고일", "진행현황", "수수료", "내용", "안내멘트", "견적서"],
            [46, 236, 116, 180, 134, 116, 116, 78, 124, 255, 80, 58],
            stretch_last=False)
        # 11pt 는 커 보인다 하셔서 한 단계 내린다(기본 글씨와 같은 10pt)
        # 고객관리는 열이 많아 글자를 한 단계 작게 둔다(10pt) — 키우면 열이 잘린다.
        # 대신 한 칸 높이는 넉넉히 해서 눈이 편하게 한다.
        self.tbl_cust.setStyleSheet(self._cust_table_css())
        self.tbl_cust.verticalHeader().setDefaultSectionSize(40)
        self.tbl_cust.doubleClicked.connect(self._on_cust_dblclick)
        self.tbl_cust.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tbl_cust.customContextMenuRequested.connect(self._cust_context_menu)
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

    # 진행현황 색 — 줄 전체에 연한 색을 깐다(v1.20.4). 예전엔 진행현황 칸의
    # 글자색만 바꿔서 발주·출고·취소가 한눈에 안 갈렸다.
    # 색을 여기에 박아 두면 다크 화면에서 대비가 3.4:1 까지 떨어져 안 읽혔다.
    # 테마가 들고 있는 강조색을 쓰면 밝은 화면·어두운 화면 각각에 맞는 밝기로 나온다.
    STATUS_TONES = {"출고": "blue", "발주": "green", "취소": "red",
                    "진행보류": "gray"}

    def status_color(self, status: str) -> str:
        """진행현황 글자색. 아는 상태가 아니면 빈 값(기본 글자색을 쓴다)."""
        tone = self.STATUS_TONES.get((status or "").strip())
        return theme.strong(tone) if tone else ""

    def _cust_table_css(self) -> str:
        """고객 표 — 글씨 10pt + **진한 선택색**.

        ⚠️ 줄마다 진행현황 색을 깔자 '출고'(연파랑) 줄이 기본 선택색과 거의 같아졌다
           (대비 1.05). 출고 줄을 눌러도 골랐는지 안 보인다. 그래서 이 표만
           선택색을 진한 파랑 + 흰 글자로 바꿔 어떤 연한 줄 색과도 확실히 갈리게 한다.
        """
        return ("QTableWidget { font-size: 10pt; "
                f"selection-background-color: {theme.fill('blue')}; "
                f"selection-color: {theme.fill_text()}; }}")

    def status_row_color(self, status: str) -> str:
        """그 상태의 줄 전체에 까는 연한 색. 모르는 상태면 빈 값(칠하지 않는다)."""
        tone = self.STATUS_TONES.get((status or "").strip())
        return theme.row_tint(tone) if tone else ""

    # 고객표에서 버튼이 들어가는 열 (더블클릭으로 창을 열면 안 되는 자리)
    COL_STATUS = 7
    COL_FEE = 8
    COL_NOTE = 9
    # 금액 열은 오른쪽 정렬 (차량가격·수수료)
    MONEY_COLS = (4, 8)
    # 짧은 값이라 가운데로 모아야 읽기 좋은 열 (순번·계약일·출고일·진행현황)
    CENTER_COLS = (0, 5, 6, 7)
    COL_MENT_BTN = 10
    COL_DOC_BTN = 11

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
        self.on_customer_edit()

    # ---- 우클릭 메뉴 (연락처 · 자료 · 편집) ----
    def _cust_context_menu(self, pos):
        idx = self.tbl_cust.indexAt(pos)
        if idx.isValid():
            self.tbl_cust.selectRow(idx.row())
        cr = self._sel_customer()
        menu = QMenu(self)

        if cr is not None:
            fin = cr.get("finance").strip()
            nums, cands = contacts.for_customer(kb.load_all(), cr)
            if nums:
                head = menu.addAction(f"📞 {fin or '금융사'} 연락처")
                head.setEnabled(False)
                for label, value in nums:
                    a = menu.addAction(f"     {label}   {value}")
                    a.triggered.connect(
                        lambda _c=False, lb=label, v=value: self._copy_phone(lb, v))
            elif cands:
                # 어느 금융사인지 확실하지 않다 — 고르게 한다.
                # 임의로 하나를 고르면 다른 캐피탈로 전화를 걸게 된다.
                sub = menu.addMenu(f"📞 연락처 — '{fin}' 후보 {len(cands)}곳")
                for it in cands[:8]:
                    name = it.get("finance") or it.get("title")
                    m2 = sub.addMenu(name)
                    for label, value in contacts.phones_of(it):
                        a = m2.addAction(f"{label}   {value}")
                        a.triggered.connect(
                            lambda _c=False, lb=f"{name} {label}", v=value:
                            self._copy_phone(lb, v))
            else:
                a = menu.addAction("📞 연락처 없음 (자료검색에 금융사 자료를 넣어 두세요)")
                a.setEnabled(False)
            menu.addSeparator()
            if fin:
                a = menu.addAction(f"🔎 자료검색에서 '{fin}' 열기")
                a.triggered.connect(lambda _c=False, f=fin: self.open_kb_for(f))
            a = menu.addAction("🚑 보험사 사고접수 연락처")
            a.triggered.connect(lambda: self.open_kb_for("보험사 사고접수"))
            name = (cr.values.get("customer") or "").strip()
            if name:
                a = menu.addAction(f"📁 고객정보에서 '{name}' 서류 보기")
                a.triggered.connect(
                    lambda _c=False, n=name: self.open_files_for(n))
            menu.addSeparator()

        for text, slot in [("수정", self.on_customer_edit),
                           ("이력", self.on_customer_history),
                           ("서류", self.on_customer_docs),
                           ("삭제", self.on_customer_del)]:
            menu.addAction(text).triggered.connect(slot)
        menu.exec(self.tbl_cust.viewport().mapToGlobal(pos))

    def _copy_phone(self, label: str, value: str) -> None:
        QGuiApplication.clipboard().setText(value)
        self.sig_toast.emit(config.APP_NAME, f"{label} {value} 복사됨")

    def open_kb_for(self, query: str) -> None:
        """자료검색 **탭** 을 그 말로 열어 준다 (탭이 없으면 조용히 넘어간다).

        이름을 open_kb_search 로 짓지 않는다 — 그건 전역 단축키가 부르는
        빠른검색 창이고, 인자도 없다. 같은 이름을 두면 나중 정의가 앞의 것을
        조용히 덮어써 단축키가 죽는다(v1.2.5 에서 겪었다).
        """
        tab = getattr(self, "tab_kb", None)
        if tab is None:
            return
        i = self.tabs.indexOf(tab)
        if i >= 0:
            self.tabs.setCurrentIndex(i)
        tab.search_for(query)

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
        # ⚠️ 계정이 확인되기 **전**에는 공용 폴더의 설정을 들고 있다. 거기엔
        # 시트 이름이 기본값('미출고차량')으로 남아 있어서, 여기서 먼저 불러오면
        # 설정에 적어 둔 이름('고객관리')이 아니라 기본값으로 조회해 오류창이 떴다.
        # 게다가 _auto_load_started 가 켜져 버려, 계정이 확인된 뒤 다시 불러오지도
        # 못했다. 구글에 연결돼 있으면 계정 확인을 기다린다.
        if self.gauth.is_connected() and not getattr(self, "account_email", ""):
            if tries < 12:
                QTimer.singleShot(1500, lambda: self._auto_load_sheet(tries + 1))
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

    def fetch_kb_async(self):
        """공유 업무자료를 전용 스프레드시트에서 받아온다(수당율과 같은 방식).

        실패하면 조용히 넘어가고 이 PC 에 저장된 마지막 자료로 검색한다 —
        인터넷이 끊겨도 자료검색은 되어야 한다.
        """
        if not self.gauth.is_connected():
            return

        def worker():
            try:
                items = sheets.read_kb(self.gauth, config.RATES_SHEET_ID)
                if items:
                    self.sig_sheet_kb.emit(items)
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def _on_sheet_kb(self, items: list):
        """공유 업무자료 도착 → 캐시에 저장하고 검색 화면을 갱신."""
        try:
            if items != kb.load_shared():
                kb.save_shared(items)
                if hasattr(self, "tab_kb"):
                    self.tab_kb.reload()
        except Exception:
            pass

    def _push_kb_shared(self, items: list):
        """관리자가 고친 공통 자료를 시트로 올린다(백그라운드)."""
        if not self.gauth.is_connected():
            self.sig_toast.emit(config.APP_NAME,
                                "구글에 연결되지 않아 이 PC 에만 저장했습니다.")
            return

        def worker():
            try:
                sheets.write_kb(self.gauth, config.RATES_SHEET_ID, items)
                self.sig_toast.emit(config.APP_NAME, "공통 업무자료를 올렸습니다.")
            except Exception as e:
                self.sig_toast.emit(config.APP_NAME, "업무자료 올리기 실패: " + str(e))
        threading.Thread(target=worker, daemon=True).start()

    def open_kb_search(self):
        """전역 단축키 → 빠른검색 창."""
        if getattr(self, "_kb_quick", None) is None:
            self._kb_quick = QuickSearch(self)
        self._kb_quick.popup()

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
        self._sheet_pending = []
        self._sheet_loaded = True
        self._show_summary(summary)
        self.refresh_customers()
        self.refresh_dashboard()

    # 상단 현황 항목별 강조색. 색을 여기 박아 두면 테마를 못 따라가 밝은 화면에서
    # 2.5:1(발주·만기)까지 떨어졌다. 브리핑과 같은 색 이름을 쓴다.
    SUMMARY_TONES = {
        "발주": "orange",        # 진행 중
        "가망고객": "violet",     # 잠재
        "지난달출고": "blue",     # 지난 실적
        "이번달출고": "green",    # 이번 실적
    }

    def _show_summary(self, summary):
        """시트 N1:O4 의 발주 현황 + 이번달 실적을 목록 위에 표시.

        발주 현황(N1:O4)이 없는 시트도 있으므로, 요약이 비어 있어도 이번달 실적
        줄은 그린다. (예전엔 요약이 없으면 여기서 바로 빠져나가 실적이 아예 안 보였다)
        """
        self._summary_data = list(summary or [])
        parts = []
        for label, value in (summary or []):
            tone = self.SUMMARY_TONES.get(label.strip())
            col = theme.strong(tone) if tone else theme.c("accent")
            parts.append(
                f"<span style='color:{theme.c('subtext')};font-size:13px;'>{label}</span>"
                f"&nbsp;<span style='color:{col};font-size:23px;"
                f"font-weight:bold;'>{value}</span>")
        line1 = "&nbsp;&nbsp;&nbsp;&nbsp;·&nbsp;&nbsp;&nbsp;&nbsp;".join(parts)

        # 이번달 실적 (출고일 기준) — 지난달 대비 증감과 금융사 분포
        st = sheets.month_stats(self.sheet_rows, date.today())
        sub = theme.c("subtext")
        acc = theme.c("accent")
        fee = f"₩{st['cur_fee']:,}" if st["cur_fee"] else "₩0"
        big = "font-size:16px;font-weight:bold;"
        bits = [f"<span style='color:{sub};'>이번달 출고</span>&nbsp;"
                f"<span style='color:{acc};{big}'>{st['cur_cnt']}건</span>",
                f"<span style='color:{sub};'>수수료</span>&nbsp;"
                f"<span style='color:{acc};{big}'>{fee}</span>"]
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
        # 한 덩어리로 보이게 패널을 깔고 여백을 준다 — 켜자마자 제일 먼저 읽히는 줄
        self.lbl_cust_summary.setStyleSheet(
            f"background:{theme.c('panel_bg')};border:1px solid {theme.c('border')};"
            f"border-radius:10px;padding:10px 14px;")
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
        q = (self.ed_cust_find.live_text() or "").strip().lower() if hasattr(self, "ed_cust_find") else ""
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
            price = sheets.fmt_money(cr.get("price"))
            # 내용은 여러 줄일 수 있다 — 표에서는 한 줄로 이어 붙인다
            note = " ".join((cr.get("note") or "").split())
            vals = [cr.seq if not pend else "…",
                    ("[등록중] " if pend else "") + cr.get("customer"),
                    cr.get("finance"), cr.get("model"),
                    (f"₩{price}" if price else ""),
                    cr.get("contract_date"), cr.get("deliver_date"), status,
                    (f"₩{fee}" if fee else ""), note]
            for c, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setData(Qt.UserRole, cr.row)
                if c in self.MONEY_COLS:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                elif c in self.CENTER_COLS:
                    item.setTextAlignment(Qt.AlignCenter)
                if c == self.COL_NOTE and note:
                    item.setToolTip(cr.get("note"))   # 잘린 부분은 툴팁으로
                self.tbl_cust.setItem(r, c, item)
            # 진행현황: 출고=파랑 / 발주=초록 / 취소=빨강 / 진행보류=회색 — **줄 전체**
            row_bg = self.status_row_color(status)
            if row_bg and not pend:
                bg = QColor(row_bg)
                # 단추가 들어가는 칸(안내멘트·견적서)은 항목이 없다. 빈 항목을
                # 만들어 같이 칠해야 단추 둘레가 흰 채로 남지 않는다.
                for c in range(self.tbl_cust.columnCount()):
                    cell = self.tbl_cust.item(r, c)
                    if cell is None:
                        cell = QTableWidgetItem("")
                        cell.setData(Qt.UserRole, cr.row)
                        self.tbl_cust.setItem(r, c, cell)
                    cell.setBackground(bg)
                # ⚠️ 진행현황 글자는 **본문색 + 굵게**. 색 배경 위에 색 글자를 두면
                #    4.3:1 로 떨어져 오히려 안 읽혔다(재 봤다). 색은 줄이 말해 준다.
                cell = self.tbl_cust.item(r, self.COL_STATUS)
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

    # '내용' 열은 창 폭에 따라 늘었다 줄었다 한다. 이보다 좁아지면 아무 글자도
    # 안 보여 차라리 가로 스크롤이 낫다.
    NOTE_MIN_W = 70

    def _fit_cust_columns(self):
        """남거나 모자라는 폭을 '내용' 열이 받아 낸다.

        다른 열은 전부 글자가 다 보여야 하는 값(고객명·금융사·차종·금액·날짜)이라
        건드리지 않는다. 내용만 길어서 어차피 다 못 보여 주므로, 늘어날 때도
        줄어들 때도 이 열이 맡는다. 잘린 부분은 툴팁으로 본다.
        """
        if getattr(self, "_fitting_cols", False):
            return          # 폭을 바꾸면 스크롤바가 생겼다 사라지며 다시 불린다
        self._fitting_cols = True
        try:
            col = self.COL_NOTE
            vp = self.tbl_cust.viewport().width()
            others = sum(self.tbl_cust.columnWidth(i)
                         for i in range(self.tbl_cust.columnCount()) if i != col)
            self.tbl_cust.setColumnWidth(col, max(self.NOTE_MIN_W, vp - others))
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
        res = CustomerDialog.run("고객 등록", {}, self.sheet_choices, "", self)
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
        # 등록하면서 출고일까지 넣었으면 그것도 캘린더에 올린다
        # (새 고객이라 '예전 값' 은 빈 것으로 본다)
        self._sync_deliver_event(pend, {}, dict(vals))

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
                                 cr.values, self.sheet_choices, cr.ment, self)
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
        self._sync_deliver_event(cr, old, merged)

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
                # 고치기 **전** 이름·ID 로 그 고객이 아직 그 줄에 있는지 확인하고 쓴다
                # (그 사이 시트가 정렬됐거나 폰에서 고객을 넣고 뺐을 수 있다)
                cr.row = sheets.update_row(self.gauth, sid, sname, cr.row, v,
                                           name=old.get("customer", ""), uid=cr.uid)
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

    # ------------------------------------------------- 캘린더 → 고객으로 이동
    def _rows_named(self, name: str) -> list:
        """고객 칸이 이 이름을 가리키는 줄들.

        ⚠️ 시트의 고객 칸은 "박성일 / 박가네 백년약초" 처럼 슬래시로 여러 조각이다.
           캘린더 제목에서 뽑히는 것은 그중 한 조각(사람 이름)뿐이라
           **통째로 비교하면 못 찾는다.** 조각으로 갈라 견준다.
        """
        want = (name or "").strip()
        if not want:
            return []
        out = []
        for cr in self._visible_sheet_rows():
            cell = (cr.get("customer") or "").strip()
            if not cell:
                continue
            parts = [p.strip() for p in cell.split("/") if p.strip()]
            if cell == want or want in parts:
                out.append(cr)
        return out

    def open_customer_by_name(self, name: str, parent=None):
        """캘린더에서 넘어온 이름으로 그 고객의 출고정보를 연다."""
        parent = parent or self
        if not self._sheet_ready(quiet=True):
            QMessageBox.information(
                parent, config.APP_NAME,
                "고객관리 시트가 연결돼 있지 않습니다.\n"
                "[설정] 에서 시트를 지정하고 [불러오기] 해 주세요.")
            return
        found = self._rows_named(name)
        if not found:
            QMessageBox.information(
                parent, config.APP_NAME,
                f"'{name}' 고객을 고객관리에서 찾지 못했습니다.\n"
                "이름이 바뀌었거나 다른 시트에 있을 수 있습니다.")
            return
        if len(found) > 1:
            # ⚠️ 말없이 첫 번째를 열지 않는다. 동명이인이 있는데 남의 고객 창을
            #    열어 고치면 조용한 사고가 된다.
            items = [f"{cr.get('customer')}  ·  {cr.get('model') or ''}"
                     f"  ·  {cr.get('deliver_date') or '출고일 미정'}" for cr in found]
            from PySide6.QtWidgets import QInputDialog
            pick, okd = QInputDialog.getItem(
                parent, config.APP_NAME,
                f"'{name}' 으로 찾은 고객이 {len(found)}명입니다. 누구를 열까요?",
                items, 0, False)
            if not okd:
                return
            cr = found[items.index(pick)]
        else:
            cr = found[0]

        # 고객관리 탭으로 옮기고 그 줄을 고른 뒤 수정 창을 연다
        tab = getattr(self, "tab_cust", None)
        if tab is not None:
            i = self.tabs.indexOf(tab)
            if i >= 0:
                self.tabs.setCurrentIndex(i)
        self._select_customer_row(cr)
        self.raise_()
        self.activateWindow()
        self.on_customer_edit()

    def _select_customer_row(self, cr) -> bool:
        """고객표에서 그 줄을 골라 보이게 한다."""
        for r in range(self.tbl_cust.rowCount()):
            it = self.tbl_cust.item(r, 0)
            if it is not None and it.data(Qt.UserRole) == cr.row:
                self.tbl_cust.selectRow(r)
                self.tbl_cust.scrollToItem(it)
                return True
        return False

    # ------------------------------------------------- 출고일 → 구글 캘린더
    def _sync_deliver_event(self, cr, old_values: dict, new_values: dict) -> None:
        """출고일이 정해지거나 바뀌면 구글 캘린더에 맞춰 준다.

        무엇을 할지는 deliver_cal.plan() 이 정한다(통신 없는 순수 계산).
        여기서는 그 결정을 실제로 실행하기만 한다.

        ⚠️ 시트 저장은 이미 끝난 뒤다. 여기서 실패해도 화면을 막지 않는다 —
           캘린더에 못 올렸다고 고객 수정이 취소되면 안 된다.
        """
        if not getattr(self.settings, "deliver_to_calendar", True):
            return
        if not self.gauth.is_connected():
            return

        keyword = (self.settings.follow_keyword or "출고").strip() or "출고"
        customer = (new_values.get("customer") or "").strip()
        book = deliver_cal.load()
        # uid 는 기록을 붙들어 두는 열쇠다. 없으면 여기서 발급한다.
        uid = self._ensure_uid(cr)
        if not uid:
            return
        act = deliver_cal.plan(uid, customer,
                               old_values.get("deliver_date", ""),
                               new_values.get("deliver_date", ""),
                               book.get(uid), keyword)
        if act[0] == "none":
            return

        rmin = self._reminder_minutes()

        def worker():
            try:
                if act[0] == "create":
                    _kind, title, when = act
                    ev = google_client.insert_event(
                        self.gauth, "primary", title, when, all_day=True,
                        reminder_minutes=rmin)
                    self.sig_deliver_new.emit(ev)     # 이번주 목록에 바로 얹는다
                    self.sig_deliver_cal.emit(
                        uid, ev.cal_id or "primary", ev.event_id or "",
                        when.isoformat(), title, "")
                elif act[0] in ("move", "rename"):
                    _kind, cal_id, event_id, title, when = act
                    google_client.update_event(self.gauth, cal_id, event_id,
                                               title, when, all_day=True)
                    self.sig_deliver_cal.emit(uid, cal_id, event_id,
                                              when.isoformat(), title, "")
                elif act[0] == "delete":
                    _kind, cal_id, event_id = act
                    google_client.delete_event(self.gauth, cal_id, event_id)
                    self.sig_deliver_cal.emit(uid, "", "", "", "", "")
            except Exception as e:
                self.sig_deliver_cal.emit(uid, "", "", "", "",
                                          str(e).splitlines()[0][:120])
        threading.Thread(target=worker, daemon=True).start()

    def _on_deliver_cal(self, uid: str, cal_id: str, event_id: str,
                        when: str, title: str, err: str) -> None:
        """출고 일정 처리 결과 — 기록을 남기거나 지운다. (UI 실뜨개)"""
        if err:
            # 조용히 넘기지 않는다. 캘린더에 안 올라갔는데 올라간 줄 알면
            # 출고 당일에야 알게 된다.
            self.sig_toast.emit(config.APP_NAME,
                                "출고 일정을 캘린더에 반영하지 못했습니다.\n" + err)
            return
        book = deliver_cal.load()
        if event_id:
            from datetime import date as _date
            book = deliver_cal.remember(book, uid, cal_id, event_id,
                                        _date.fromisoformat(when), title)
        else:
            book = deliver_cal.forget(book, uid)
        deliver_cal.save(book)

    def _ensure_uid(self, cr) -> str:
        """고객의 불변 ID. 없으면 그 고객에게만 발급하고 시트에도 적는다.

        v1.1.25 이전에 등록된 고객은 ID 가 없다. 전체를 한꺼번에 채우면 수백 셀
        쓰기가 되고 중간에 실패하면 절반만 적히므로, 실제로 필요할 때 한 명씩 준다.
        """
        uid = (cr.uid or "").strip()
        if uid:
            return uid
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
                # 새 ID 가 발급돼 지금 적은 메모·서류가 안 보이게 된다.
                self.sig_toast.emit(
                    config.APP_NAME,
                    "고객ID를 시트에 기록하지 못했습니다.\n"
                    "지금 남긴 메모·서류가 다음에 안 보일 수 있습니다.\n"
                    + str(e).splitlines()[0][:80])
        threading.Thread(target=worker, daemon=True).start()
        return uid

    def on_customer_docs(self):
        """선택한 고객의 심사서류 체크리스트."""
        if not self._sheet_ready():
            return
        cr = self._sel_customer()
        if cr is None:
            QMessageBox.information(self, config.APP_NAME, "서류를 볼 고객을 선택하세요.")
            return
        if cr in self._sheet_pending:
            self.sig_toast.emit(config.APP_NAME, "시트에 등록 중입니다. 잠시 후 여세요.")
            return
        self._open_docs_for(cr, self)

    def _open_docs_for(self, cr, parent):
        """서류 창을 띄우고 바뀐 내용을 저장한다(고객관리·이력 창에서 함께 쓴다)."""
        uid = self._ensure_uid(cr)
        before = customer_docs.record(self._docs, uid)
        after = customer_docs.CustomerDocsDialog.run(
            cr, before, kb.doc_templates(kb.load_all()), parent)
        if after != before:
            if after.get("items"):
                self._docs[uid] = after
            else:
                self._docs.pop(uid, None)
            self._save_docs()
            self.refresh_customers()      # 표의 서류 진행도 표시를 갱신

    def _load_docs(self) -> dict:
        return customer_docs.load()

    def _save_docs(self):
        try:
            customer_docs.save(self._docs)
        except Exception:
            pass
        self._touch_sync()

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

        uid = self._ensure_uid(cr)
        notes = self._notes.get(uid, [])
        new_notes = CustomerHistoryDialog.run(
            cr, notes, self._ment_key(cr) in self._ment_copied, self,
            on_docs=lambda dlg: self._open_docs_for(cr, dlg))
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
                # 정렬된 시트에서 다른 고객을 지우지 않도록 지우기 직전에 확인한다
                cr.row = sheets.clear_row(self.gauth, sid, sname, cr.row,
                                          name=cr.get("customer"), uid=cr.uid)
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

    # 표 글자 크기와 한 칸 높이 — 한 곳에서 정한다.
    # 하루 종일 들여다보는 화면이라 조금 크게 잡았다(예전 9pt/기본높이 → 11pt/38px).
    TABLE_PT = 11
    ROW_H = 38

    def _make_table(self, headers, widths, stretch_last: bool = True) -> QTableWidget:
        """표 하나.

        stretch_last=False 면 지정한 폭을 그대로 지킨다. 마지막 열이 버튼 열
        (안내멘트)인 표에서 켜 두면 버튼 칸만 늘어나 보기 나쁘다.
        """
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.setStyleSheet(f"QTableWidget {{ font-size: {self.TABLE_PT}pt; }}")
        t.verticalHeader().setDefaultSectionSize(self.ROW_H)
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
            # 브리핑과 주간 요약이 한 화면이 되어 메뉴도 한 줄로 합쳤다
            ("주간 요약", self.show_startup_screen),
            ("지금 백업", lambda: self._backup(manual=True)),
            ("업데이트 확인", lambda: self.check_update(manual=True)),
            ("변경 이력", self.open_changelog),
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
            self.lbl_status.setStyleSheet(f"color:{theme.c('status_ok')};")
            self.btn_google.hide()
        else:
            # 단추가 바로 옆에 있으므로 '설정으로 가라'는 안내는 필요 없다
            self.lbl_status.setText("구글: 로그인 필요")
            self.lbl_status.setStyleSheet(f"color:{theme.c('status_bad')};")
            self.btn_google.set_busy(False)
            self.btn_google.apply_theme()
            self.btn_google.show()

    # 설정 창을 거치지 않고 바로 로그인한다. 창이 멈추지 않게 딴 실에서 돌리고,
    # 끝나면 _sig_google_login 으로 화면 실에 돌아온다.
    def on_google_login_click(self):
        if self.gauth.is_connected():
            return
        self.btn_google.set_busy(True)

        # 설정에서 '드라이브에서 직접 조회' 를 켜 두었으면 그 권한도 같이 받는다
        extra = ([config.SCOPE_DRIVE_READ]
                 if getattr(self.settings, "drive_api_on", True) else [])

        def worker():
            try:
                self.gauth.authorize(extra_scopes=extra)
                self.sig_google_login.emit(True, "")
            except Exception as e:
                self.sig_google_login.emit(False, str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_google_login_done(self, ok: bool, err: str):
        self.btn_google.set_busy(False)
        self.update_google_status()
        if not ok:
            QMessageBox.warning(self, config.APP_NAME, "로그인 실패:\n" + err)
            return
        # 로그인 직후엔 켤 때 연결돼 있던 것과 같은 일을 해 줘야 한다 —
        # 계정 확인 → 계정 폴더 정하기 → 동기화 → 일정/할일·고객 목록.
        # _start_account_sync 가 그 줄을 통째로 밟는다(끝에서 fetch_all_async).
        self._reset_sheet_cache()
        self._start_account_sync()

    def _on_autofetch_toggled(self, on: bool):
        self.settings.auto_fetch = on
        self._save_settings()

    def on_settings_click(self):
        was_connected = self.gauth.is_connected()
        prev_theme = (getattr(self.settings, "theme", "")
                      or ("dark" if self.settings.dark_mode else "light"))
        prev_sheet = (self.settings.sheet_id.strip(), self.settings.sheet_name.strip())
        prev_files = (self.settings.files_dir.strip(),
                      self.settings.drive_api_on,
                      self.settings.files_drive_folder.strip())
        dlg = SettingsDialog(self.gauth, self.settings, self,
                             account=getattr(self, 'account_email', ''),
                             on_backup=self.open_backup,
                             on_sync=lambda: self.sync_now_async(manual=True))
        accepted = dlg.exec() == SettingsDialog.Accepted
        if accepted:
            self._save_settings()
            self._apply_hotkeys()
            self.followup_tracker.last_scan = None  # 설정이 바뀌었으니 다시 스캔
            now_theme = (getattr(self.settings, "theme", "")
                         or ("dark" if self.settings.dark_mode else "light"))
            if now_theme != prev_theme:
                self.apply_theme()   # 고른 테마를 즉시 반영
            if hasattr(self, "tab_comm"):
                self.tab_comm.reload_rates()   # 수당율을 고쳤을 수 있다
            self.fetch_rates_async()
            # 서류 폴더를 바꿨으면 '고객정보' 탭을 다시 읽는다.
            # 예전엔 설정에서 폴더를 지정해도 탭이 그대로여서, 다시 켜기 전엔
            # 아무것도 안 나왔다.
            now_files = (self.settings.files_dir.strip(),
                         self.settings.drive_api_on,
                         self.settings.files_drive_folder.strip())
            if now_files != prev_files and hasattr(self, "tab_files"):
                self.tab_files.set_settings(self.settings)
                self._files_loaded = True
                self.tab_files.reload()
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
        self.lbl_status.setStyleSheet(f"color:{theme.c('status_bad')};")

    def _rename_old_followups(self):
        """예전 '[팔로업] …' 제목을 '[출고 1개월] 홍길동' 으로 바꾼다.

        할일과 구글 캘린더 양쪽을 고친다. 옛 제목이 하나도 없으면 아무 일도
        일어나지 않으므로, 한 번 정리된 뒤에는 그냥 지나간다.
        """
        kw = (self.settings.follow_keyword or "출고").strip() or "출고"
        mo = int(self.settings.follow_months or 1)

        n = followup.rename_old_todos(self.todos, kw, mo)
        if n:
            self._save_todos()
            self._touch_sync()
            self.refresh_todo()

        if not self.gauth.is_connected():
            return
        jobs = followup.old_title_events(self.cal_events, kw, mo)
        if not jobs:
            if n:
                self.sig_toast.emit(config.APP_NAME, f"팔로업 제목 {n}건을 정리했습니다.")
            return
        # 화면에 먼저 반영해 두면, 캘린더 응답을 기다리는 동안에도 새 제목이 보인다
        for ev, new in jobs:
            ev.summary = new
        self.refresh_calendar()
        items = [(ev.cal_id, ev.event_id, new, ev.start.date(), ev.has_time,
                  ev.start.time() if ev.has_time else None) for ev, new in jobs]

        def worker():
            done = 0
            for cal_id, event_id, title, day, has_time, tm in items:
                try:
                    google_client.update_event(
                        self.gauth, cal_id, event_id, title, day,
                        start_time=tm, all_day=not has_time)
                    done += 1
                except Exception:
                    pass          # 못 고친 건은 다음 새로고침 때 다시 시도된다
            if done:
                self.sig_toast.emit(config.APP_NAME,
                                    f"팔로업 제목 {done + n}건을 정리했습니다.")
        threading.Thread(target=worker, daemon=True).start()

    def _run_followups(self):
        """캘린더에서 팔로업 대상을 찾아 내 할일로 자동 등록."""
        self._rename_old_followups()
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
        self.refresh_dashboard()

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
        self.refresh_dashboard()

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
        # 자리는 알람 창이 열린 알람들을 보고 정한다(늘 화면 안).
        alarm_window.popup(title, ment)

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
        if getattr(self, "_today_shown", None) != today:     # 자정이 지나면 제목줄 날짜도
            self._today_shown = today
            self._paint_today()
            self.refresh_dashboard()        # 오늘·이번 주·다음 주가 바뀐다
        self._paint_page_title()            # 인사말은 시간대 따라(바뀔 때만 다시 쓴다)
        if self.last_backup != today and self._tick_backup_ok():
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

    def _docs_missing_customers(self):
        """아직 안 받은 심사서류가 남아 있는 고객.

        반환: [(행, 미제출 서류 이름들, 전체 개수)] — 많이 남은 순.

        진행 중인 계약(계약·발주 등)만 본다. 출고까지 끝났거나 취소된 건은
        이제 받을 서류가 없으므로 띄우면 소음이 된다.
        """
        out = []
        for cr in getattr(self, "sheet_rows", []) or []:
            uid = (getattr(cr, "uid", "") or "").strip()
            if not uid:
                continue                      # 서류를 한 번도 안 연 고객
            if not customer_docs.is_open_status(cr.get("status")):
                continue
            rec = customer_docs.record(self._docs, uid)
            left = customer_docs.missing(rec)
            if left:
                out.append((cr, left, len(rec.get("items") or [])))
        out.sort(key=lambda x: len(x[1]), reverse=True)
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
            secs.append({"icon": "🔔", "title": "만기 재계약", "color": "violet",
                         "items": items, "count": len(exp),
                         "more": more if more > 0 else 0,
                         "hint": "[고객관리] 탭에서 [이력] 로 상담 내역을 확인하고 "
                                 "재계약을 준비하세요."})

        # ---- 서류 미비 (진행 중인 계약에 아직 안 받은 서류가 있음) ----
        short = self._docs_missing_customers()
        if short:
            items = []
            for cr, left, total in short[:12]:
                items.append({"lead": f"{total - len(left)}/{total}",
                              "text": cr.get("customer"),
                              "sub": " · ".join(left[:3])
                                     + (f" 외 {len(left) - 3}" if len(left) > 3 else "")})
            more = len(short) - 12
            secs.append({"icon": "📄", "title": "서류 미비", "color": "orange",
                         "items": items, "count": len(short),
                         "more": more if more > 0 else 0,
                         "hint": "[고객관리] 탭에서 [서류] 를 눌러 미제출 목록을 "
                                 "복사해 고객에게 보내세요."})

        # ---- 고객정보 폴더를 못 찾았다 ----
        # 이 폴더가 없으면 [고객정보] 탭이 통째로 빈 화면이 된다. 그 탭을 열어야
        # 비로소 알게 되는 것이 문제라, 켤 때 한 번 눈에 띄게 알린다.
        #
        # ⚠️ PC 에 폴더가 없어도 인터넷으로 읽히면 화면은 똑같이 나온다. 그때까지
        #    빨간 줄을 띄우면 멀쩡한 것을 고장 났다고 말하는 셈이라, **정말 읽을
        #    곳이 없을 때만** 띄운다(pick_source 가 그 판단을 이미 한다).
        from . import customer_files
        if customer_files.pick_source(self.settings, self.gauth)[0] is None:
            hint = ("폴더 이름을 바꿔 두면 PC 를 바꿔도 따로 지정할 필요가 "
                    "없습니다. 다른 곳에 두셨다면 [설정] → 서류 폴더에서 "
                    "직접 고르셔도 됩니다.")
            if not drive_path.installed():
                hint = drive_path.INSTALL_HINT + " " + hint
            secs.append({
                "icon": "📁", "title": "고객정보 폴더를 찾지 못했습니다", "color": "red",
                "items": [{"lead": "확인", "text": drive_path.FIX_HINT}],
                "count": 1, "hint": hint})

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
        secs.append({"icon": "🗓", "title": "이번주 요약", "color": "gray",
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
    def build_briefing_html(self, with_head: bool = True) -> str:
        """with_head=False 면 맨 위 날짜·건수 줄을 뺀다(대시보드 카드는 머리 줄에 쓴다)."""
        secs = self._briefing_sections()
        cnt_cal, cnt_todo = self._brief_today_counts
        d = date.today()
        esc = html_escape
        txt, sub_c, line_c = theme.c("text"), theme.c("subtext"), theme.c("border")

        out = [f"<div style='font-family:Malgun Gothic;color:{txt};'>"]
        # 날짜 머리글
        if with_head:
            out.append(
                f"<p style='margin:0 0 2px 0;font-size:20px;font-weight:bold;color:{txt};'>"
                f"{d:%Y년 %m월 %d일} ({self._WEEKDAY_KO[d.weekday()]})</p>"
                f"<p style='margin:0 0 10px 0;font-size:13px;color:{sub_c};'>"
                f"오늘 일정 <b style='color:{theme.strong('blue')};'>{cnt_cal}</b>건"
                f" &nbsp;·&nbsp; 할일 <b style='color:{theme.strong('green')};'>{cnt_todo}</b>건</p>")

        for k, s in enumerate(secs):
            col = theme.strong(s["color"])
            bg = theme.strong_bg(s["color"])
            n = s.get("count", len(s["items"]))
            badge = (f"<span style='background-color:{bg};color:{col};font-size:12px;"
                     f"font-weight:bold;'>&nbsp;{n}건&nbsp;</span>" if n else
                     f"<span style='color:{sub_c};font-size:12px;'>&nbsp;0건&nbsp;</span>")
            if with_head or k:
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

    # 브리핑만 따로 띄우던 알람 팝업(show_briefing)은 없앴다.
    # 주간 요약과 한 화면(show_startup_screen)이 되어 부르는 곳이 없어졌다.
    # 만드는 쪽(build_briefing / build_briefing_html)은 그 화면이 그대로 쓴다.

    # ------------------------------------------------------------ 백업
    # 자동 백업이 실패하면 이만큼 쉬었다가 다시 해 본다(초)
    BACKUP_RETRY_SEC = 600

    def _tick_backup_ok(self) -> bool:
        """1초 타이머가 지금 자동 백업을 해도 되나.

        ⚠️ 구글에 연결된 PC 는 계정 확인이 끝나야 **그 사람의** 폴더를 안다.
           예전엔 켜자마자(1초) 여기서 백업해서 공용 폴더를 백업했다.
           계정 확인이 끝나면 _on_account_ready 가 직접 백업한다.
        또 실패한 뒤에는 BACKUP_RETRY_SEC 동안 쉰다 — 예전엔 디스크가 가득 차거나
        권한이 없으면 **매초** 파일을 다시 쓰려 했다.
        """
        if self.gauth.is_connected() and not getattr(self, "_account_checked", False):
            return False
        return datetime.now() >= getattr(self, "_backup_retry_at", datetime.min)

    def _backup(self, manual: bool):
        try:
            self._do_backup(manual)
            self._backup_retry_at = datetime.min
        except Exception as e:
            # 백업이 실패해도 앱은 계속 돌아야 한다. last_backup 을 세우지 않으므로
            # 다음 기회에 다시 시도한다 — 단 틱마다가 아니라 잠시 쉬었다가.
            self._backup_retry_at = datetime.now() + timedelta(seconds=self.BACKUP_RETRY_SEC)
            if manual:
                QMessageBox.warning(self, config.APP_NAME, "백업 실패:\n" + str(e))

    def _do_backup(self, manual: bool):
        # 담는 파일은 동기화 대상(sync._FILES)과 같은 목록을 쓴다.
        # 예전엔 할일·알람 3개만 담아서, 설정·고객메모·멘트문구는 백업에 없었다.
        # 되돌릴 수 없는 데이터가 생기지 않도록 한 목록만 본다.
        bk_dir = backup_dialog.backup_dir()
        backup_dialog.make_backup()
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

    def open_backup(self):
        """백업/복원 창. 되돌린 뒤에는 화면과 동기화를 함께 맞춘다."""
        def after_restore():
            self.reload_data()          # 파일 → 모델 → 화면
            self.refresh_calendar()
            self.refresh_todo()
            self.refresh_alarm()
            self._touch_sync()          # 되돌린 상태를 다른 PC 에도 전파
        backup_dialog.BackupDialog(self, on_restored=after_restore).exec()

    def open_changelog(self):
        """변경 이력 창을 연다."""
        changelog.show_for(self)

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

    def _screen_avail(self):
        """이 창이 올라가 있는 모니터의 쓸 수 있는 넓이.

        ⚠️ primaryScreen 을 쓰면 안 된다. 모니터를 두 대 쓰는 분이 보조 모니터로
        창을 옮겨 최대화하면, 그쪽 해상도가 주 모니터와 달라 '화면만큼 커졌나' 를
        잘못 재고 세로가 도로 줄어든다(_is_max 참고).
        """
        scr = self.screen() or QGuiApplication.primaryScreen()
        return scr.availableGeometry()

    # ---- 창 크기 기억 (가로·세로) ----
    def _width_bounds(self, avail):
        """이 화면에서 허용되는 (최소, 최대) 폭."""
        lo = min(self.MIN_WIDTH, avail.width() - 20)
        return lo, max(lo, avail.width() - 20)

    def _win_path(self):
        """폭을 적어 두는 파일.

        계정 폴더(config.data_file)가 아니라 **공용 폴더**에 둔다. 계정 폴더는
        로그인해야 정해지는데 창은 그 전에 이미 떠 있고, 그 폴더는 다른 PC 로
        동기화까지 된다. 창 폭은 이 PC 의 모니터에 달린 값이라 둘 다 곤란하다.
        """
        return config.base_dir() / self.WIN_FILE

    def _saved_width(self, default: int, avail) -> int:
        """지난번에 맞춰 둔 폭. 없거나 이 화면에 안 맞으면 기본값."""
        lo, hi = self._width_bounds(avail)
        want = default
        try:
            p = self._win_path()
            if p.exists():
                saved = json.loads(p.read_text(encoding="utf-8")) or {}
                got = int(saved.get("width", 0))
                # 상단바 시절에 맞춰 둔 폭이면 왼쪽 메뉴 몫을 한 번 더해 준다 —
                # 안 그러면 업데이트하자마자 고객관리 표에 가로 스크롤이 생긴다.
                if got > 0 and int(saved.get("layout", 1)) < self.LAYOUT_VER:
                    got += self.LAYOUT_EXTRA
                if got > 0:
                    want = got
        except Exception:
            pass                        # 파일이 깨졌으면 조용히 기본값
        return max(lo, min(hi, want))

    def _saved_height(self, default: int, avail) -> int:
        """지난번에 맞춰 둔 세로. 없거나(세로를 못 바꾸던 시절) 이 화면에 안 맞으면 기본값."""
        lo = min(self.MIN_HEIGHT, avail.height() - 60)
        want = default
        try:
            p = self._win_path()
            if p.exists():
                got = int((json.loads(p.read_text(encoding="utf-8")) or {}).get("height", 0))
                if got > 0:
                    want = got
        except Exception:
            pass
        # 제목표시줄까지 화면에 들어오게 — 큰 모니터에서 맞춘 세로를 노트북에서 열 때
        return max(lo, min(avail.height() - 40, want))

    def _saved_maximized(self) -> bool:
        try:
            p = self._win_path()
            if p.exists():
                return bool((json.loads(p.read_text(encoding="utf-8")) or {})
                            .get("maximized", False))
        except Exception:
            pass
        return False

    def _later_keep(self):
        timer = getattr(self, "_keep_timer", None)
        if timer is not None and getattr(self, "_centered_once", False):
            timer.start()

    def _keep_on_screen(self):
        """제목표시줄이 화면 밖으로 나가지 않게 — 세로를 마음대로 바꿀 수 있게 하면서 지킨다.

        · 창이 화면보다 크면 화면 높이까지 줄인다(위아래가 다 안 보이면 제목줄도 밖이다)
        · 제목표시줄 가운데가 어느 모니터에도 없으면, 이 창의 모니터 안으로 옮긴다
          (모니터를 위아래로 붙여 쓰면 위 모니터에 걸친 것은 정상이다 — 그래서
          '이 모니터 위쪽 밖' 이 아니라 '어느 모니터에도 없음' 을 본다)
        최대화 중에는 건드리지 않는다.
        """
        if self._keeping or self._is_max() or not self.isVisible():
            return
        self._keeping = True
        try:
            avail = self._screen_avail()
            fg = self.frameGeometry()
            if fg.height() > avail.height():
                extra = fg.height() - avail.height()
                self.resize(self.width(), max(self.minimumHeight(), self.height() - extra))
                fg = self.frameGeometry()
            title = QPoint(fg.left() + fg.width() // 2, fg.top() + 10)
            if QGuiApplication.screenAt(title) is None or fg.top() > avail.bottom() - self.TITLE_KEEP:
                top = min(max(fg.top(), avail.top()), avail.bottom() - self.TITLE_KEEP)
                left = min(max(fg.left(), avail.left() - fg.width() + 240),
                           avail.right() - 240)
                self.move(left, top)
        except Exception:
            pass
        finally:
            self._keeping = False

    # 창이 '거의 화면만큼' 커졌으면 최대화로 친다. 창틀·제목줄 때문에 화면보다
    # 조금 작게 잡히므로 여유를 둔다.
    MAX_SLACK_W, MAX_SLACK_H = 20, 40

    def _is_max(self) -> bool:
        """최대화(또는 전체화면) 상태인가.

        ⚠️ 창 상태 비트만 믿으면 안 된다. 최대화를 누르면 '커졌다'(resize)가
        '최대화됨'(state)보다 **먼저** 오는 창관리자가 있다(윈도가 그렇다).
        그 틈에 세로를 되돌려 버려서, 가로만 커지고 세로는 제자리로 돌아갔다.
        그래서 크기도 함께 본다 — 화면을 거의 채웠으면 최대화로 친다.
        """
        if (self.isMaximized() or self.isFullScreen()
                or (self.windowState() & (Qt.WindowMaximized
                                          | Qt.WindowFullScreen))):
            return True
        try:
            av = self._screen_avail()
        except Exception:
            return False
        # '화면만큼' 이지 '화면보다 크게' 가 아니다. 화면보다 훌쩍 큰 창은
        # 최대화가 아니라 그냥 억지로 키운 것이므로 되돌려야 한다.
        return (abs(self.width() - av.width()) <= self.MAX_SLACK_W
                and abs(self.height() - av.height()) <= self.MAX_SLACK_H)

    def changeEvent(self, event):
        """최대화 ↔ 보통이 바뀌면 '보통' 크기를 되살린다(_apply_size_mode)."""
        if event.type() == QEvent.WindowStateChange:
            self._apply_size_mode()
        super().changeEvent(event)

    def _apply_size_mode(self):
        """최대화 ↔ 보통. 가로 하한만 다시 걸고, 제목줄은 _keep_on_screen 이 지킨다.

        창 상태 알림(changeEvent)만 믿지 않고 resizeEvent 에서도 부른다.
        몇 번을 불러도 상태가 그대로면 아무 일도 하지 않는다.
        """
        now_max = self._is_max()
        if now_max == getattr(self, "_maximized", False):
            return
        self._maximized = now_max
        if now_max:
            return
        avail = self._screen_avail()
        lo, _hi = self._width_bounds(avail)
        self.setMinimumWidth(lo)
        # ⚠️ 여기서 크기를 되돌리지 않는다. 최대화를 풀면 윈도가 원래 크기로 되돌려
        #    준다. 세로를 못 바꾸던 시절엔 여기서 '보통' 크기로 조였는데, 이제는 화면을
        #    거의 채우게 끌었다가 다시 줄이는 손을 거꾸로 잡아채게 된다.
        self._later_keep()

    def _remember_width(self) -> None:
        try:
            # 최대화 중이면 그때의 크기가 아니라 '보통' 크기를 적어 둔다.
            # 안 그러면 최대화를 풀었을 때 화면 가득한 크기가 그대로 굳는다.
            mx = self._is_max()
            w = self._normal_w if mx else self.width()
            h = self._normal_h if mx else self.height()
            config.atomic_write(self._win_path(),
                                json.dumps({"width": w, "height": h, "maximized": mx,
                                            "layout": self.LAYOUT_VER}))
        except Exception:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._snapping:
            # 창 상태 알림을 못 받은 경우에도 제약이 어긋난 채로 남지 않게 한다
            self._apply_size_mode()
        # 뜨기 전(_saved_width 로 맞추는 중)에는 저장하지 않는다 — 그러면 화면에
        # 맞춰 줄인 값이 그대로 굳어 다음에 켤 때 더는 못 넓힌다.
        if getattr(self, "_centered_once", False):
            if not self._is_max():
                self._normal_w = self.width()   # 최대화가 아닐 때만 '보통' 크기
                self._normal_h = self.height()
            self._width_timer.start(600)     # 끄는 중에는 계속 불린다 → 멈추면 저장
            self._later_keep()

    def moveEvent(self, event):
        super().moveEvent(event)
        self._later_keep()

    def showEvent(self, event):
        # 창틀 크기는 화면에 뜬 뒤에야 정확히 알 수 있다 → 첫 표시 때 한 번 더 맞춘다.
        # (이후 사용자가 옮긴 위치는 그대로 둔다)
        super().showEvent(event)
        if not getattr(self, "_centered_once", False):
            self._centered_once = True
            self._center_on_screen()
            self._keep_on_screen()
            # 다른 모니터로 옮기거나(해상도·배율이 다르다) 모니터를 뺐을 때도 다시 본다
            try:
                self.windowHandle().screenChanged.connect(lambda *_a: self._later_keep())
            except Exception:
                pass
            # 지난번에 최대화로 쓰던 사람은 최대화로 열어 준다.
            # 자리를 잡은 뒤에 해야 최대화를 풀었을 때 제자리로 돌아온다.
            if getattr(self, "_want_maximized", False):
                self._want_maximized = False
                self.showMaximized()

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
        # 창 크기를 바꾸자마자 끄면 저장 타이머(600ms)가 못 돌고 끝난다.
        # 그러면 방금 맞춘 폭이 다음에 켤 때 사라진다 — 여기서 마저 적어 둔다.
        if self._width_timer.isActive():
            self._width_timer.stop()
            self._remember_width()
        try:
            self.hotkeys.release()
        except Exception:
            pass
        alarm_window.close_all()
        self.tray.hide()
