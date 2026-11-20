"""메인 창 — 자료검색 한 화면 + 트레이.

일정관리기의 '자료검색' 탭만 떼어 한 쪽짜리 창으로 만들었다. 캘린더·할일·고객관리는 없다.

  위   : [자료 편집] [동기화] [설정]
  가운데: 검색칸 · 결과 목록 · 본문/첨부 (kb_view.KbView)
  아래 : 로그인 상태 · 마지막 동기화 · 공통 자료를 저절로 받은 때

**회사 공통 자료는 로그인 없이 저절로 받는다** — 켤 때, 그리고 config.KB_AUTO_MINUTES 마다
(창을 열거나 빠른검색을 띄울 때 오래됐으면 그때도). 관리자가 일정관리기에서 고친 자료·첨부가
그대로 따라온다(auto_pull).
로그인은 [동기화] 를 처음 누를 때만 한다 — 내 메모를 구글 계정과 맞추거나, 관리자가 고친
공통 자료를 올릴 때다. 그 전에는 내 메모가 이 PC 에만 저장된다.
창을 닫으면 트레이로 내려가 빠른검색 단축키를 계속 받는다. 끄려면 트레이 → [종료].
"""

from __future__ import annotations

import base64
import sys
import threading
import time
from datetime import datetime

from PySide6.QtCore import QByteArray, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMainWindow, QMenu, QMessageBox,
    QPushButton, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from . import config, hotkey, kb, kb_files, otp, otp_popup, sheets_kb, switch, sync, theme, updater
from .google_auth import GoogleAuth, LoginCancelled
from .icon import make_icon
from .kb_view import KbEditDialog, KbView, MeInfoDialog, QuickSearch
from .settings import Settings
from .settings_dialog import SettingsDialog
from . import update_ui


def _file_ids(items: list) -> dict:
    """{첨부 id: 첨부} — 자료 목록 전체에서."""
    return {f.get("id"): f for it in (items or []) for f in (it.get("files") or [])
            if f.get("id")}


class MainWindow(QMainWindow):
    sig_login = Signal(str, str)             # (이메일, 오류)
    sig_sync = Signal(object, str)           # (sync.Result | None, 오류)
    sig_edits = Signal(object, str)     # 고친 심사서류 3종을 조용히 맞춘 결과(kb-v1.6.0)
    sig_update = Signal(object, str, bool)   # (새 판 정보 | None, 오류, 직접 눌렀나)
    sig_public = Signal(object, str)         # (공개로 받은 공통 자료 | None, 오류)
    sig_switch = Signal(object)              # 웹 스위치 상태(switch.fetch_state) | None
    sig_otp = Signal(object, str)            # 휴대폰 인증번호 — 새로 온 것 [{code, sender, body}], 오류 (kb-v1.8.0)

    STALE_SEC = 5 * 60          # 창·빠른검색을 열 때 이보다 오래됐으면 공통 자료를 다시 받는다

    def __init__(self, settings: Settings | None = None, update_checked: bool = True):
        super().__init__()
        self.settings = settings or Settings.load()
        self.gauth = GoogleAuth(config.data_file("google_token.json"))
        self._really_quit = False
        self._busy = False                  # 동기화 중
        self._editing = False               # 자료 편집 창이 떠 있다
        self._login_cancel = None           # 로그인 중이면 threading.Event
        self._upd_checking = False
        self._updating = False
        self._quick = None
        self._icon = make_icon()
        self._pulling = False               # 공통 자료를 저절로 받는 중
        # 마지막으로 받으러 간 때(time.monotonic). None = 아직 한 번도 안 감.
        # ⚠️ 0 으로 두면 안 된다 — 윈도의 monotonic 은 PC 를 켠 뒤부터 센다. 부팅 직후
        #    (자동 실행)에는 값이 5분도 안 돼 '방금 받았다' 로 보여 첫 받기를 건너뛰었다.
        self._pulled_at = None
        self._public_err = ""

        self.setWindowTitle(f"{config.APP_NAME}  v{config.APP_VERSION}")
        self.setWindowIcon(self._icon)
        self.resize(1080, 700)
        self.setMinimumSize(760, 480)
        self._restore_geometry()

        self._build_ui()
        self._build_tray()

        self.sig_login.connect(self._on_login)
        self.sig_sync.connect(self._on_sync)
        self.sig_edits.connect(self._on_edits)
        self.sig_update.connect(self._on_update)
        self.sig_public.connect(self._on_public)
        self.sig_switch.connect(self._on_switch)
        self.sig_otp.connect(self._on_otp)

        # 전역 단축키 (윈도) — 업무자료 빠른검색
        self.hotkeys = hotkey.HotkeyManager(QApplication.instance(), int(self.winId()))
        self.hotkeys.set_callback(hotkey.ID_KB, self.open_quick)
        self._hot_ok = True
        self._apply_hotkey(first=True)

        # 켜 둔 채로 지내도 몇 시간마다 업데이트를 다시 확인한다.
        # 켤 때 확인을 못 했으면(부팅 직후 인터넷이 늦게 붙는 경우가 흔하다) 1분 뒤 한 번 더.
        self._upd_timer = QTimer(self)
        self._upd_timer.timeout.connect(lambda: self.check_update(manual=False))
        self._upd_timer.start(int(config.UPDATE_CHECK_HOURS * 3600 * 1000))
        # 켜 둔 채로 찾은 새 판은 '쓰지 않을 때' 묻지 않고 바꾼다(kb-v1.4.0) — 1분마다 본다
        self._pending_update = None
        self._upd_idle_timer = QTimer(self)
        self._upd_idle_timer.timeout.connect(self._try_pending_update)
        # 지난번 실행(업데이트 · 종료 · 두 번째 실행)이 남긴 임시 폴더를 켜고 1분 뒤 조용히 지운다(kb-v1.5.1)
        self.schedule_temp_cleanup(60)
        if not update_checked:
            QTimer.singleShot(60 * 1000, lambda: self.check_update(manual=False))

        # 회사 공통 자료 — 로그인 없이 저절로 받는다(켜자마자 한 번, 그 뒤로 몇 분마다)
        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(self.auto_pull)
        self._auto_timer.start(int(config.KB_AUTO_MINUTES * 60 * 1000))
        QTimer.singleShot(1500, self._pull_if_stale)     # 창을 띄우며 이미 받았으면 건너뛴다
        # 고친 심사서류 3종 — 로그인돼 있으면 켤 때와 몇 분마다 웹과 조용히 맞춘다(kb-v1.6.0)
        # kb-v1.8.1: 공통 자료(10분)와 따로 2분마다 — 웹·일정관리기에서 고친 것이 곧 온다(작은 파일 하나)
        self._edits_timer = QTimer(self)
        self._edits_timer.timeout.connect(self.sync_edits_quiet)
        self._edits_timer.start(2 * 60 * 1000)
        QTimer.singleShot(8000, self.sync_edits_quiet)
        # 웹 스위치 — 켜 둔 채로 지내도 관리자가 끄면 몇 분 안에 멈춘다
        self._switch_checking = False
        if config.SWITCH_URL:
            self._switch_timer = QTimer(self)
            self._switch_timer.timeout.connect(self.check_switch)
            self._switch_timer.start(int(config.SWITCH_CHECK_MINUTES * 60 * 1000))

        # 휴대폰 인증번호 — 일정관리기와 같다(otp.py). 설정에서 켜면 4초마다 시트 맨 위를 본다(kb-v1.8.0).
        self._otp = otp.Watcher()
        self._otp_busy = False
        self._otp_skip = 0
        self._otp_errs = 0
        self._otp_tick = 0
        self._otp_timer = QTimer(self)
        self._otp_timer.timeout.connect(self._poll_otp)
        self._otp_timer.start(otp.POLL_MS)

        self.apply_theme()
        self.refresh_account()

    # ------------------------------------------------------------ 화면
    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._topbar = QWidget()
        self._topbar.setObjectName("topbar")
        self._topbar.setAttribute(Qt.WA_StyledBackground, True)
        tb = QHBoxLayout(self._topbar)
        tb.setContentsMargins(14, 9, 14, 9)
        self.lbl_title = QLabel("🔎 업무자료검색")
        tb.addWidget(self.lbl_title)
        self.lbl_hint = QLabel("전자약정·심사서류를 쳐서 바로 찾아 쓰세요 — 초성만 쳐도 됩니다.")
        tb.addWidget(self.lbl_hint)
        tb.addStretch()
        self.btn_edit = QPushButton("자료 편집")
        self.btn_edit.clicked.connect(self.edit)
        tb.addWidget(self.btn_edit)
        self.btn_me = QPushButton("내 정보")
        self.btn_me.setToolTip("팩스·이름·연락처를 한 번 적어 두면 회사 자료의 '내 팩스' 같은 자리에 저절로 들어갑니다.")
        self.btn_me.clicked.connect(self.edit_me)
        tb.addWidget(self.btn_me)
        self.btn_sync = QPushButton("동기화")
        self.btn_sync.setToolTip("구글에 로그인해 회사 공통 자료를 받고, 내 메모를 내 구글 계정과 맞춥니다.\n"
                                 "일정관리기와 같은 스프레드시트·같은 메모를 씁니다.")
        self.btn_sync.clicked.connect(self.sync_clicked)
        tb.addWidget(self.btn_sync)
        self.btn_settings = QPushButton("설정")
        self.btn_settings.clicked.connect(self.open_settings)
        tb.addWidget(self.btn_settings)
        root.addWidget(self._topbar)

        self.view = KbView()
        self.view.set_auth(self.gauth)
        root.addWidget(self.view, 1)

        self._footer = QWidget()
        fb = QHBoxLayout(self._footer)
        fb.setContentsMargins(14, 4, 14, 8)
        self.lbl_account = QLabel("")
        fb.addWidget(self.lbl_account)
        self.btn_logout = QPushButton("로그아웃")
        self.btn_logout.setFlat(True)
        self.btn_logout.setCursor(Qt.PointingHandCursor)
        self.btn_logout.clicked.connect(self.logout)
        fb.addWidget(self.btn_logout)
        fb.addStretch()
        self.lbl_msg = QLabel("")
        fb.addWidget(self.lbl_msg)
        root.addWidget(self._footer)

    def apply_theme(self) -> None:
        theme.set_theme(self.settings.theme)
        theme.apply_to_app(QApplication.instance())
        # 이름으로 집어 칠한다 — 그냥 칠하면 안의 글자·단추까지 밑줄(테두리)을 물려받는다
        self._topbar.setStyleSheet(
            f"QWidget#topbar {{ background:{theme.c('topbar')};"
            f" border-bottom:1px solid {theme.c('border')}; }}")
        self.lbl_title.setStyleSheet(
            f"color:{theme.c('topbar_text')};font-size:18px;font-weight:bold;background:transparent;")
        self.lbl_hint.setStyleSheet(f"color:{theme.c('subtext')};background:transparent;")
        self.lbl_account.setStyleSheet(f"color:{theme.c('subtext')};")
        self.btn_logout.setStyleSheet(
            f"QPushButton {{ border:none; background:transparent; color:{theme.c('accent')};"
            f" text-decoration: underline; padding:0 4px; }}")
        self.view.apply_theme()
        self._quick = None          # 빠른검색 창은 다음에 새 색으로 다시 만든다
        self.refresh_account()

    def _set_msg(self, text: str, kind: str = "") -> None:
        col = {"ok": theme.c("status_ok"), "bad": theme.c("status_bad")}.get(kind, theme.c("subtext"))
        self.lbl_msg.setStyleSheet(f"color:{col};")
        self.lbl_msg.setText(text)

    def refresh_account(self) -> None:
        """아래 줄(로그인 상태·마지막 동기화)과 [동기화] 단추 모양을 맞춘다."""
        meta = kb.load_meta()
        if not config.SYNC_ON:
            self.btn_sync.hide()
            self.btn_logout.hide()
            self.lbl_account.setText("자료는 이 PC 에만 저장됩니다.")
            self._sync_actions_visible(False)
            return
        last = self._when(meta.get("last_sync"))
        shared = self._shared_state(meta)
        if self.gauth.is_connected():
            who = self.gauth.email or "구글 계정"
            role = " (관리자)" if config.is_admin(who) else ""
            self.lbl_account.setText(
                f"● {who}{role}" + (f"  ·  마지막 동기화 {last}" if last else "  ·  아직 동기화 안 함")
                + f"  ·  {shared}")
            self.btn_logout.setVisible(not self._busy and self._login_cancel is None)
        else:
            self.lbl_account.setText(f"로그인 안 함  ·  {shared}  ·  내 메모는 이 PC 에만 저장 "
                                     "([동기화] 로 구글 계정과 맞춤)")
            self.btn_logout.hide()
        if self._login_cancel is not None:
            self.btn_sync.setText("로그인 취소")
            self.btn_sync.setEnabled(True)
        elif self._busy:
            self.btn_sync.setText("동기화 중…")
            self.btn_sync.setEnabled(False)
        else:
            dot = bool(meta.get("pending"))
            self.btn_sync.setText("동기화 ●" if dot else "동기화")
            self.btn_sync.setToolTip(
                ("이 PC 에서 고친 내용이 아직 동기화되지 않았습니다.\n" if dot else "")
                + "회사 공통 자료는 로그인 없이도 저절로 받습니다.\n"
                  "[동기화] 는 구글에 로그인해 내 메모를 내 구글 계정·일정관리기와 맞추고,\n"
                  "관리자 계정이면 이 PC 에서 고친 공통 자료를 시트로 올립니다.")
            self.btn_sync.setEnabled(True)
        self._sync_actions_visible(True)

    @staticmethod
    def _when(iso) -> str:
        """저장해 둔 시각 → '09:15'(오늘) 또는 '10/26 09:15'. 없으면 ""."""
        try:
            t = datetime.fromisoformat(str(iso))
        except Exception:
            return ""
        return t.strftime("%H:%M") if t.date() == datetime.now().date() else t.strftime("%m/%d %H:%M")

    def _shared_state(self, meta: dict) -> str:
        """아래 줄에 붙는 '회사 공통 자료' 상태."""
        n = len(kb.load_local())
        mine = f"  ·  내 계정에서 고친 공통 자료 {n}건" if n else ""
        return self._shared_pull_state(meta) + mine

    def _shared_pull_state(self, meta: dict) -> str:
        if meta.get("shared_dirty"):
            return "공통 자료: 이 PC 에서 고친 것을 [동기화] 로 올리기 전까지 자동 받기 멈춤"
        at = self._when(meta.get("shared_at"))
        if self._public_err and not at:
            return "공통 자료를 저절로 받지 못함 — 인터넷을 확인해 주세요"
        if at:
            return f"공통 자료 자동 받음 {at}"
        return "공통 자료 받는 중…"

    # ------------------------------------------------------------ 공통 자료 저절로 받기
    def auto_pull(self) -> None:
        """회사 공통 자료를 로그인 없이 받는다(시트 공개 CSV). 조용히 한다 — 실패해도 창을 띄우지 않는다."""
        if not config.SYNC_ON or self._pulling or self._busy:
            return
        self._pulling = True
        self._pulled_at = time.monotonic()

        def work():
            try:
                self.sig_public.emit(sheets_kb.read_kb_public(), "")
            except Exception as e:
                self.sig_public.emit(None, str(e) or "받지 못함")
        threading.Thread(target=work, daemon=True).start()

    def _pull_if_stale(self) -> None:
        if self._pulled_at is None or time.monotonic() - self._pulled_at > self.STALE_SEC:
            self.auto_pull()

    def _on_public(self, items, err: str) -> None:
        self._pulling = False
        if err:
            self._public_err = err
            self.refresh_account()
            return
        self._public_err = ""
        # 동기화·편집 중에는 파일을 건드리지 않는다 — 1분 뒤 다시 받는다
        if self._busy or self._editing:
            QTimer.singleShot(60 * 1000, self.auto_pull)
            return
        try:
            got = sync.apply_public(items)
        except Exception as e:
            self._public_err = str(e)
            self.refresh_account()
            return
        if got["changed"]:
            self.view.reload()
            if self._quick is not None and self._quick.isVisible():
                self._quick.view.reload()     # 떠 있는 빠른검색 창도 새 자료로
            self._set_msg(f"회사 공통 자료를 새로 받았습니다 ({got['count']}건)", "ok")
        self.refresh_account()

    # ------------------------------------------------------------ 웹 스위치(서버 on/off)
    def check_switch(self) -> None:
        if self._switch_checking:
            return
        self._switch_checking = True
        threading.Thread(target=lambda: self.sig_switch.emit(switch.fetch_state()),
                         daemon=True).start()

    def _on_switch(self, state) -> None:
        self._switch_checking = False
        if not switch.is_off(state):
            return
        # 편집 창처럼 다른 창이 떠 있으면 고치던 것을 잃지 않게 잠시 미룬다(업데이트와 같다)
        if QApplication.activeModalWidget() is not None or self._busy:
            QTimer.singleShot(60 * 1000, self.check_switch)
            return
        msg = switch.off_message(state)
        self._toast(msg)
        if self.isVisible():
            QMessageBox.information(self, config.APP_NAME, msg)
        self.quit_app()

    # ------------------------------------------------------------ 트레이
    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self._icon, self)
        self.tray.setToolTip(config.APP_NAME)
        m = QMenu()
        m.addAction("열기", self.show_window)
        self.act_quick = m.addAction("빠른검색", self.open_quick)
        m.addSeparator()
        self.act_sync = m.addAction("동기화", self.sync_clicked)
        m.addAction("설정", self.open_settings)
        m.addAction("업데이트 확인", lambda: self.check_update(manual=True))
        m.addSeparator()
        m.addAction("종료", self.quit_app)
        self._tray_menu = m
        self.tray.setContextMenu(m)
        self.tray.activated.connect(self._on_tray)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def _sync_actions_visible(self, on: bool) -> None:
        if hasattr(self, "act_sync"):
            self.act_sync.setVisible(on)

    def _on_tray(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_window()

    def _toast(self, text: str) -> None:
        if self.tray.isVisible():
            self.tray.showMessage(config.APP_NAME, text, self._icon, 6000)

    def show_window(self) -> None:
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
        self.view.focus_search()
        self._pull_if_stale()

    def start_in_tray(self) -> None:
        """부팅 때(/tray) — 창 없이 시작한다. 트레이가 없는 환경이면 그냥 창을 띄운다."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.show()

    def closeEvent(self, ev):
        self._save_geometry()
        if self._really_quit or not QSystemTrayIcon.isSystemTrayAvailable():
            self._shutdown()
            ev.accept()
            QApplication.instance().quit()
            return
        ev.ignore()
        self.hide()
        if not self.settings.tray_hint_shown:
            hot = (f" · 빠른검색 {self.settings.hotkey_text()}"
                   if self.settings.kb_hot_on and self._hot_ok else "")
            self._toast("트레이에서 계속 실행 중입니다" + hot
                        + "\n끄려면 트레이 아이콘 오른쪽 단추 → [종료]")
            self.settings.tray_hint_shown = True
            self._save_settings()

    def quit_app(self) -> None:
        # close() 에 맡기지 않는다 — 트레이로 숨어 있는 창은 닫기 신호를 못 받을 수 있다
        self._really_quit = True
        self._save_geometry()
        self._shutdown()
        QApplication.instance().quit()

    def _shutdown(self) -> None:
        try:
            self.hotkeys.release()
        except Exception:
            pass
        if self._login_cancel is not None:
            self._login_cancel.set()
        self.tray.hide()

    # ------------------------------------------------------------ 창 크기 기억
    def _restore_geometry(self) -> None:
        try:
            if self.settings.geometry:
                self.restoreGeometry(QByteArray(base64.b64decode(self.settings.geometry)))
        except Exception:
            pass

    def _save_geometry(self) -> None:
        try:
            if self.isVisible():
                self.settings.geometry = base64.b64encode(bytes(self.saveGeometry())).decode("ascii")
                self._save_settings()
        except Exception:
            pass

    def _save_settings(self) -> None:
        try:
            self.settings.save()
        except Exception:
            pass

    # ------------------------------------------------------------ 단축키 · 빠른검색
    def _apply_hotkey(self, first: bool = False) -> None:
        try:
            self._hot_ok = bool(self.hotkeys.apply_kb(self.settings))
        except Exception:
            self._hot_ok = False
        on = self.settings.kb_hot_on
        if sys.platform != "win32":
            self._hot_ok = True              # 윈도가 아니면 단축키가 없다 — 경고하지 않는다
        txt = self.settings.hotkey_text()
        self.act_quick.setText(f"빠른검색 ({txt})" if on and self._hot_ok else "빠른검색")
        self.tray.setToolTip(config.APP_NAME + (f" — 빠른검색 {txt}" if on and self._hot_ok else ""))
        if on and not self._hot_ok:
            self._set_msg(f"빠른검색 단축키 {txt} 를 등록하지 못했습니다 — [설정] 에서 키를 바꿔 보세요.",
                          "bad")
            if first:
                self._toast(f"빠른검색 단축키 {txt} 를 다른 프로그램이 쓰고 있습니다.\n"
                            "[설정] 에서 다른 키로 바꿔 주세요.")

    def open_quick(self) -> None:
        if self._quick is None:
            self._quick = QuickSearch(self, auth=self.gauth)
        self._quick.popup()
        self._pull_if_stale()

    # ------------------------------------------------------------ 휴대폰 인증번호(kb-v1.8.0)
    def _poll_otp(self) -> None:
        s = self.settings
        sid = str(getattr(s, "otp_sheet", "") or "").strip()
        if not getattr(s, "otp_on", False) or not sid:
            self._otp.reset()                # 다시 켜면 그때 있던 것은 '본 것' 으로
            return
        if self._otp_busy or not self.gauth.is_connected():
            return
        if not self.gauth.has_scope(config.SCOPE_SHEETS):
            return                           # 시트 권한 없이 로그인했다(로그인 때 알렸다)
        if self._otp_skip > 0:               # 방금 못 읽었다 — 조금 쉬었다가
            self._otp_skip -= 1
            return
        self._otp_tick += 1
        if otp.idle_seconds() > otp.IDLE_SEC and self._otp_tick % otp.IDLE_EVERY:
            return                           # 자리 비움 — 20초에 한 번만(시트 읽기 한도를 아낀다)
        self._otp_busy = True
        tab = str(getattr(s, "otp_tab", "") or "").strip()

        def worker():
            import requests
            items, err = [], ""
            try:
                items = self._otp.poll(self.gauth, sid, tab)
            except otp.NoAccess:
                err = "denied"               # 이 계정은 그 시트를 볼 수 없다
            except requests.RequestException:
                err = "net"                  # 인터넷이 잠깐 끊겼다 — 알리지 않는다
            except Exception as e:
                err = (str(e).splitlines() or ["error"])[0][:160] or "error"
            self.sig_otp.emit(items, err)
        threading.Thread(target=worker, daemon=True).start()

    def _on_otp(self, items, err: str) -> None:
        self._otp_busy = False
        if err == "denied":
            # 기다려도 안 풀린다 — 10분에 한 번만 다시 보고, 한 번만 알린다(kb-v1.8.1)
            self._otp_skip = otp.DENIED_TICKS
            if not getattr(self, "_otp_denied_told", False):
                self._otp_denied_told = True
                self._set_msg("이 구글 계정으로는 인증문자 시트를 볼 수 없습니다 — 시트 주인에게 공유를 요청하거나 "
                              "[설정] 에서 끄세요", "bad")
            return
        if err:
            self._otp_skip = otp.BACKOFF_TICKS
            if err == "net":
                return                       # 인터넷이 끊긴 것은 알리지 않는다(붙으면 다시 본다)
            self._otp_errs += 1
            if self._otp_errs == 3:          # 계속 못 읽으면 한 번만 알린다
                self._set_msg("인증문자 시트를 읽지 못했습니다 — [설정] 의 시트 주소·구글 로그인을 확인하세요", "bad")
            return
        self._otp_errs = 0
        self._otp_denied_told = False        # 다시 읽힌다 — 또 막히면 다시 알린다
        copy = bool(getattr(self.settings, "otp_copy", True))
        for it in reversed(items or []):     # 위가 최신 — 오래된 것부터 띄워 새 것이 맨 아래·클립보드에
            if not otp.claim(it):
                continue                     # 이 PC 의 일정관리기가 방금 띄웠다 — 두 번 띄우지 않는다(kb-v1.9.0)
            if copy:
                QApplication.clipboard().setText(it["code"])
            otp_popup.show(it, copied=copy)

    # ------------------------------------------------------------ 설정
    def open_settings(self) -> None:
        self.show_window()
        d = SettingsDialog(self.settings, hot_ok=self._hot_ok, parent=self)
        if d.exec():
            self._save_settings()
            self.apply_theme()
            self._apply_hotkey()
            if self.settings.kb_hot_on and self._hot_ok:
                self._set_msg(f"설정을 저장했습니다 — 빠른검색 {self.settings.hotkey_text()}", "ok")
            elif not self.settings.kb_hot_on:
                self._set_msg("설정을 저장했습니다 — 빠른검색 단축키 꺼짐")
            if self.settings.otp_on and not self.gauth.is_connected():
                self._set_msg("인증번호 받기를 켰습니다 — [동기화] 로 구글 로그인하면 시작합니다")

    # ------------------------------------------------------------ 자료 편집
    def _account(self) -> str:
        return self.gauth.email if self.gauth.is_connected() else ""

    def edit(self) -> None:
        if self._busy:
            QMessageBox.information(self, config.APP_NAME, "동기화가 끝난 뒤에 고쳐 주세요.")
            return
        account = self._account()
        admin = config.is_admin(account)
        old_shared, old_mine = kb.load_shared(), kb.load_mine()
        before = _file_ids(old_mine)
        if admin:
            before.update(_file_ids(old_shared))
        # 이 PC 에서만 고친 공통 자료 — 이 PC 에 둔 첨부(local-)만 내 것이다. 회사 첨부는
        # 빼도 이 PC 에서 안 보일 뿐, 드라이브 휴지통으로 보내지 않는다.
        before.update({fid: f for fid, f in _file_ids([r["item"] for r in kb.load_local()]).items()
                       if str(fid).startswith(kb_files.LOCAL_PREFIX)})
        # 편집 창이 떠 있는 동안에는 동기화를 막는다(sync_clicked). 창은 열 때 읽은 사본을
        # 들고 있어서, 그사이 동기화로 들어온 메모를 저장하면서 '지운 것' 으로 덮어쓴다.
        self._editing = True
        try:
            # 보고 있던 자료가 바로 열리게(일정관리기와 같다 — 예전엔 늘 맨 위 자료부터)
            got = KbEditDialog.run(account, self, select=self.view.lst.current_item_data())
        finally:
            self._editing = False
        if got is None:
            return
        shared, local, mine = got
        changed = local_changed = False
        try:
            if kb.clean_list(mine) != kb.clean_list(old_mine):
                kb.save_mine(mine)
                changed = True
            if admin and kb.clean_list(shared) != kb.clean_list(old_shared):
                kb.save_shared(shared, edited=True)
                changed = True
            local_changed = kb.set_local(local)
        except Exception as e:
            QMessageBox.warning(self, config.APP_NAME, "저장하지 못했습니다:\n" + str(e))
        after = _file_ids(mine)
        if admin:
            after.update(_file_ids(shared))
        after.update(_file_ids([r["item"] for r in kb.load_local()]))
        # 뺀 첨부 — 이 PC 에만 있던 것은 지금 지우고, 올린 것은 [동기화] 때 드라이브 휴지통으로
        gone = [fid for fid in before if fid not in after]
        for fid in gone:
            kb_files.drop_local(before[fid])
        ren = [(fid, name) for fid, name in (KbEditDialog.last_renamed or [])
               if fid not in gone and not str(fid).startswith(kb_files.LOCAL_PREFIX)]
        KbEditDialog.last_renamed = []
        kb.queue_remote(trash=[f for f in gone if not str(f).startswith(kb_files.LOCAL_PREFIX)],
                        renames=ren)
        self.view.reload()
        self.refresh_account()
        if changed:
            self._set_msg("이 PC 에 저장했습니다"
                          + (" — 다른 곳과 맞추려면 [동기화]" if config.SYNC_ON else ""), "ok")
        elif local_changed:
            self._set_msg("저장했습니다 — 회사 공통 자료는 나만 바뀝니다"
                          + (" (내 계정으로 곧 맞춥니다)" if self.gauth.is_connected() else ""), "ok")
        if local_changed and self.gauth.is_connected():
            self._edits_announce = True      # 올린 결과를 알린다(kb-v1.8.1 — 예전엔 됐는지 알 수 없었다)
            QTimer.singleShot(500, self.sync_edits_quiet)     # 웹·일정관리기에도 곧 반영

    # ------------------------------------------------------------ 내 정보(kb-v1.9.0)
    def edit_me(self) -> None:
        """회사 자료의 {내 팩스} 같은 자리에 들어갈 내 정보를 적는다 — 내 계정으로 일정관리기·웹과 같다."""
        account = self.gauth.email if self.gauth.is_connected() else ""
        cur = kb.load_me()
        d = MeInfoDialog(cur, account, self)
        if not d.exec():
            return
        vals = d.values()
        if all(vals.get(k, "") == cur.get(k, "") for k, _l in kb.ME_FIELDS):
            return                               # 바뀐 것이 없다 — 계정에 쓰지 않는다
        kb.save_me(vals)
        self.view.reload()
        if self._quick is not None:
            self._quick.view.reload()
        if self.gauth.is_connected() and config.SYNC_ON:
            self._set_msg("내 정보를 저장했습니다 — 내 계정으로 맞추는 중…", "ok")
            self._edits_announce = True
            QTimer.singleShot(300, self.sync_edits_quiet)
        else:
            self._set_msg("내 정보를 이 PC 에 저장했습니다 — 로그인하면 내 계정에도 맞춥니다", "ok")

    # ------------------------------------------------------------ 고친 심사서류 3종 — 조용히 맞추기
    def sync_edits_quiet(self) -> None:
        """개인·개인사업자·법인 심사서류에서 고친 것을 웹 업무자료검색과 맞춘다(sync.sync_edits).

        로그인돼 있을 때만, 조용히 한다(실패해도 창을 띄우지 않는다 — [동기화] 때 다시 한다).
        편집 창이 떠 있거나 동기화 중이면 건너뛴다.
        """
        if (not config.SYNC_ON or self._busy or self._editing or self._login_cancel is not None
                or not self.gauth.is_connected()):
            return
        self._busy = True
        self.refresh_account()

        def work():
            try:
                self.sig_edits.emit(sync.sync_edits(self.gauth), "")
            except Exception as e:
                self.sig_edits.emit([], str(e) or "실패")
        threading.Thread(target=work, daemon=True).start()

    def _on_edits(self, changed, err: str) -> None:
        self._busy = False
        told = getattr(self, "_edits_announce", False)
        self._edits_announce = False
        if changed:
            self.view.reload()
            if self._quick is not None and self._quick.isVisible():
                self._quick.view.reload()
            self._set_msg("다른 곳에서 고친 " + ", ".join(changed) + " 을(를) 받았습니다", "ok")
        elif told and not err:
            self._set_msg("내 계정에 저장했습니다 — 웹·일정관리기에도 반영됩니다", "ok")
        elif told:
            self._set_msg("이 PC 에는 저장했지만 내 계정에 올리지 못했습니다 — 잠시 뒤 다시 올립니다", "bad")
        self.refresh_account()

    # ------------------------------------------------------------ 로그인 · 동기화
    def sync_clicked(self) -> None:
        if not config.SYNC_ON:
            return
        if self._login_cancel is not None:          # 로그인 중 — [로그인 취소]
            self._login_cancel.set()
            return
        if self._busy:
            return
        if self._editing:
            self._set_msg("자료 편집 창을 닫은 뒤에 동기화해 주세요.", "bad")
            return
        if not self.gauth.is_connected():
            self.show_window()
            ans = QMessageBox.question(
                self, config.APP_NAME,
                "회사 공통 자료는 로그인 없이도 저절로 받고 있습니다.\n"
                "[동기화] 는 내 메모를 내 구글 계정·일정관리기와 맞추는 일이라 로그인이 필요합니다.\n\n"
                "브라우저가 열리면 회사에서 쓰는 구글 계정으로 로그인하고 [허용] 을 눌러 주세요.\n"
                "(일정관리기에서 쓰던 계정이면 그 메모도 함께 받습니다)\n\n로그인할까요?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if ans != QMessageBox.Yes:
                return
            self._start_login()
            return
        self._begin_sync()

    def _start_login(self) -> None:
        ev = threading.Event()
        self._login_cancel = ev
        self._set_msg("브라우저에서 로그인해 주세요…")
        self.refresh_account()

        def work():
            try:
                email = self.gauth.authorize(cancel=ev)
                self.sig_login.emit(email, "")
            except LoginCancelled:
                self.sig_login.emit("", "cancel")
            except Exception as e:
                self.sig_login.emit("", str(e))
        threading.Thread(target=work, daemon=True).start()

    def _on_login(self, email: str, err: str) -> None:
        self._login_cancel = None
        if err:
            self.refresh_account()
            if err == "cancel":
                self._set_msg("로그인을 취소했습니다.")
            else:
                self._set_msg("로그인하지 못했습니다.", "bad")
                QMessageBox.warning(self, config.APP_NAME, "로그인하지 못했습니다:\n" + err)
            return
        self._set_msg(f"{email} 로 로그인했습니다.", "ok")
        self.refresh_account()
        self.show_window()
        # 동의 화면에서 뺀 항목이 있으면 바로 알린다(kb-v1.8.1) — 예전엔 동기화가 '그냥 안 되는' 것처럼 보였다
        miss = self.gauth.missing_scopes()
        if miss:
            QMessageBox.warning(
                self, config.APP_NAME,
                "구글 로그인은 됐지만, 동의 화면에서 빠진 항목이 있어 아래 기능이 동작하지 않습니다.\n\n· "
                + "\n· ".join(miss)
                + "\n\n[로그아웃] 후 [동기화] 로 다시 로그인하면서,\n"
                  "동의 화면의 '모두 선택' 에 체크하고 [계속] 을 눌러 주세요.")
        self._begin_sync()

    def _begin_sync(self) -> None:
        email = self.gauth.email
        meta = kb.load_meta()

        # 다른 계정으로 바꿨다 — 이 PC 의 메모를 어디로 보낼지 묻는다
        prev = (meta.get("account") or "").strip().lower()
        if prev and email and prev != email and kb.load_mine():
            box = QMessageBox(self)
            box.setWindowTitle(config.APP_NAME)
            box.setIcon(QMessageBox.Question)
            box.setText(f"이 PC 의 내 메모는 {prev} 계정과 동기화돼 있었습니다.\n"
                        f"지금은 {email} 로 로그인했습니다.")
            b_reset = box.addButton(f"이 PC 메모를 비우고 {email} 것 받기", QMessageBox.AcceptRole)
            b_merge = box.addButton(f"합쳐서 {email} 에도 올리기", QMessageBox.AcceptRole)
            box.addButton("취소", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is b_reset:
                sync.reset_mine_for_account()
            elif box.clickedButton() is not b_merge:
                self._set_msg("동기화를 취소했습니다.")
                return

        # 관리자가 이 PC 에서 고친 공통 자료가 있다 — 올릴지 묻는다
        push = False
        if meta.get("shared_dirty"):
            if config.is_admin(email):
                box = QMessageBox(self)
                box.setWindowTitle(config.APP_NAME)
                box.setIcon(QMessageBox.Question)
                box.setText("이 PC 에서 고친 회사 공통 자료가 있습니다.\n\n"
                            "시트로 올리면 시트의 '업무자료' 가 이 내용으로 바뀌고,\n"
                            "모든 직원(일정관리기 포함)이 이 내용을 받습니다.")
                b_push = box.addButton("시트로 올리기", QMessageBox.AcceptRole)
                b_pull = box.addButton("올리지 않고 시트 내용 받기", QMessageBox.AcceptRole)
                box.addButton("취소", QMessageBox.RejectRole)
                box.exec()
                if box.clickedButton() is b_push:
                    push = True
                elif box.clickedButton() is not b_pull:
                    self._set_msg("동기화를 취소했습니다.")
                    return
            else:
                QMessageBox.information(
                    self, config.APP_NAME,
                    "이 PC 에서 고친 회사 공통 자료는 관리자 계정에서만 올릴 수 있습니다.\n"
                    "시트의 내용으로 바꿉니다.")

        self._busy = True
        self._set_msg("동기화 중…")
        self.refresh_account()

        def work():
            try:
                self.sig_sync.emit(sync.run(self.gauth, push_shared=push), "")
            except Exception as e:
                self.sig_sync.emit(None, str(e))
        threading.Thread(target=work, daemon=True).start()

    def _on_sync(self, res, err: str) -> None:
        self._busy = False
        self.view.reload()
        self.refresh_account()
        if err:
            self._set_msg("동기화하지 못했습니다.", "bad")
            if not self.gauth.is_connected():        # 로그인이 만료돼 풀렸다
                err += "\n\n다시 [동기화] 를 누르면 로그인 창이 열립니다."
            QMessageBox.warning(self, config.APP_NAME, "동기화하지 못했습니다.\n\n" + err)
            return
        self._pulled_at = time.monotonic()      # 방금 공통 자료도 받았다
        self._set_msg("동기화 완료 — " + res.summary(), "ok")
        extra = [x for x in [res.shared_note] + list(res.notes) if x]
        if extra:
            QMessageBox.information(self, config.APP_NAME, "\n".join(extra))
        if not self.isVisible():
            self._toast("동기화 완료 — " + res.summary())

    def logout(self) -> None:
        if self._busy or self._login_cancel is not None:
            return
        if QMessageBox.question(
                self, config.APP_NAME,
                f"{self.gauth.email or '구글 계정'} 에서 로그아웃할까요?\n"
                "이 PC 의 자료는 그대로 남고, 다음 [동기화] 때 다시 로그인합니다.") != QMessageBox.Yes:
            return
        self.gauth.disconnect()
        self._set_msg("로그아웃했습니다.")
        self.refresh_account()

    # ------------------------------------------------------------ 업데이트
    def _busy_now(self) -> bool:
        """지금 쓰는 중인가 — 편집 창(모달)·빠른검색이 떠 있거나, 창이 보이는데 PC 를 막 만졌다."""
        if QApplication.activeModalWidget() is not None:
            return True
        if self._quick is not None and self._quick.isVisible():
            return True
        if self.isVisible() and not self.isMinimized():
            idle = updater.idle_seconds()
            return idle is None or idle < self.UPDATE_IDLE_SEC
        return False

    def _try_pending_update(self) -> None:
        info = self._pending_update
        if info is None:
            self._upd_idle_timer.stop()
            return
        if self._busy_now() or self._updating:
            return                          # 1분 뒤 다시 본다
        self._pending_update = None
        self._upd_idle_timer.stop()
        self._apply_update(info, show=True)     # 진행 창(막대)을 보여 주며(kb-v1.5.0)

    def _apply_update(self, info: dict, show: bool) -> None:
        self._updating = True
        try:
            out = update_ui.run(info, show=show, tray=not self.isVisible(), corner=True)
        finally:
            self._updating = False
        if out == update_ui.RESTART:
            self.quit_app()                 # 바꾸는 배치가 기다린다

    def schedule_temp_cleanup(self, after_sec: int = 60) -> None:
        """남은 우리 임시 폴더(_MEI…)를 after_sec 뒤 뒤에서 지운다(updater.cleanup_old_temp)."""
        def run():
            threading.Thread(target=updater.cleanup_old_temp, daemon=True).start()
        QTimer.singleShot(int(after_sec * 1000), run)

    def show_update_done(self, ver: str, notes: str = "") -> None:
        """방금 업데이트로 켜졌다 — '업데이트 완료' 와 달라진 것 몇 줄을 잠깐(kb-v1.5.0)."""
        from .update_progress import UpdateProgress
        done = UpdateProgress(ver, corner=True)
        self._upd_done = done
        done.done(ver, notes)

    def check_update(self, manual: bool = False) -> None:
        if self._upd_checking or self._updating:
            return
        self._upd_checking = True

        def work():
            try:
                self.sig_update.emit(updater.check(), "", manual)
            except Exception as e:
                self.sig_update.emit(None, str(e), manual)
        threading.Thread(target=work, daemon=True).start()

    UPDATE_IDLE_SEC = 180       # 창이 보이면 PC 를 이만큼 안 만질 때 바꾼다(쓰는 중에 꺼지지 않게)

    def _on_update(self, info, err: str, manual: bool) -> None:
        self._upd_checking = False
        if info:
            if manual:
                # [업데이트 확인] — 묻지 않고 바로(받는 정도만 작은 창으로)
                self._apply_update(info, show=True)
                return
            # 켜 둔 채로 찾았다 — 쓰지 않을 때 조용히 바꾼다(편집 창이 떠 있으면 고치던 것을 잃지 않게)
            self._pending_update = info
            self._upd_idle_timer.start(60 * 1000)
            self._try_pending_update()
            return
        if manual:
            if err:
                QMessageBox.warning(self, config.APP_NAME, err)
            else:
                QMessageBox.information(self, config.APP_NAME,
                                        f"최신 버전입니다 (v{config.APP_VERSION}).")
