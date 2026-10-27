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

from . import config, hotkey, kb, kb_files, sheets_kb, sync, theme, updater
from .google_auth import GoogleAuth, LoginCancelled
from .icon import make_icon
from .kb_view import KbEditDialog, KbView, QuickSearch
from .settings import Settings
from .settings_dialog import SettingsDialog
from .update_ui import CONTINUE, UpdateDialog


def _file_ids(items: list) -> dict:
    """{첨부 id: 첨부} — 자료 목록 전체에서."""
    return {f.get("id"): f for it in (items or []) for f in (it.get("files") or [])
            if f.get("id")}


class MainWindow(QMainWindow):
    sig_login = Signal(str, str)             # (이메일, 오류)
    sig_sync = Signal(object, str)           # (sync.Result | None, 오류)
    sig_update = Signal(object, str, bool)   # (새 판 정보 | None, 오류, 직접 눌렀나)
    sig_public = Signal(object, str)         # (공개로 받은 공통 자료 | None, 오류)

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
        self.sig_update.connect(self._on_update)
        self.sig_public.connect(self._on_public)

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
        if not update_checked:
            QTimer.singleShot(60 * 1000, lambda: self.check_update(manual=False))

        # 회사 공통 자료 — 로그인 없이 저절로 받는다(켜자마자 한 번, 그 뒤로 몇 분마다)
        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(self.auto_pull)
        self._auto_timer.start(int(config.KB_AUTO_MINUTES * 60 * 1000))
        QTimer.singleShot(1500, self._pull_if_stale)     # 창을 띄우며 이미 받았으면 건너뛴다

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
        shared, mine = got
        after = _file_ids(mine)
        if admin:
            after.update(_file_ids(shared))
        # 뺀 첨부 — 이 PC 에만 있던 것은 지금 지우고, 올린 것은 [동기화] 때 드라이브 휴지통으로
        gone = [fid for fid in before if fid not in after]
        for fid in gone:
            kb_files.drop_local(before[fid])
        ren = [(fid, name) for fid, name in (KbEditDialog.last_renamed or [])
               if fid not in gone and not str(fid).startswith(kb_files.LOCAL_PREFIX)]
        KbEditDialog.last_renamed = []
        kb.queue_remote(trash=[f for f in gone if not str(f).startswith(kb_files.LOCAL_PREFIX)],
                        renames=ren)
        changed = False
        try:
            if kb.clean_list(mine) != kb.clean_list(old_mine):
                kb.save_mine(mine)
                changed = True
            if admin and kb.clean_list(shared) != kb.clean_list(old_shared):
                kb.save_shared(shared, edited=True)
                changed = True
        except Exception as e:
            QMessageBox.warning(self, config.APP_NAME, "저장하지 못했습니다:\n" + str(e))
        self.view.reload()
        self.refresh_account()
        if changed:
            self._set_msg("이 PC 에 저장했습니다"
                          + (" — 다른 곳과 맞추려면 [동기화]" if config.SYNC_ON else ""), "ok")

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

    def _on_update(self, info, err: str, manual: bool) -> None:
        self._upd_checking = False
        if info:
            # 편집 창처럼 다른 창이 떠 있으면 고치던 것을 잃지 않게 잠시 미룬다
            modal = QApplication.activeModalWidget()
            if modal is not None and not manual:
                QTimer.singleShot(2 * 60 * 1000, lambda: self.check_update(manual=False))
                return
            self._updating = True
            out = UpdateDialog.run(info, self if self.isVisible() else None)
            self._updating = False
            if out != CONTINUE:
                self.quit_app()
            return
        if manual:
            if err:
                QMessageBox.warning(self, config.APP_NAME, err)
            else:
                QMessageBox.information(self, config.APP_NAME,
                                        f"최신 버전입니다 (v{config.APP_VERSION}).")
