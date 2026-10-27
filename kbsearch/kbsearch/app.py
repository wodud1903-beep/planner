"""애플리케이션 진입점 — 업데이트 확인을 **창보다 먼저** 한다.

순서
  1. 이미 켜져 있으면 그 창을 띄우고 끝낸다(한 PC 에 하나만).
  2. 업데이트 확인 — 새 판이 있으면 받아 바꾸기 전에는 넘어가지 않는다(update_ui).
     인터넷이 안 돼 확인을 못 하면 그냥 켠다(켜 둔 동안 다시 확인한다).
  3. 서비스 스위치(config.SERVICE_ON) — 꺼진 판이면 안내만 하고 끝낸다.
  4. 메인 창. `/tray` 로 켜지면(PC 시작 시 자동 실행) 창 없이 트레이에서 시작한다.
"""

from __future__ import annotations

import os
import sys
import threading
import time

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QFont
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QAbstractSpinBox, QApplication, QComboBox, QLabel, QLineEdit, QMessageBox,
    QVBoxLayout, QWidget,
)

from . import config, crashlog, startup, theme, updater
from .icon import make_icon
from .settings import Settings

_SINGLE_KEY = "KbSearch_SingleInstance_v1"
CHECK_WAIT_SEC = 12          # 켤 때 업데이트 확인을 기다리는 최대 시간


def _activate_existing():
    """이미 실행 중인 것이 있으면 그 창을 띄우도록 신호를 보낸다(일정관리기 v1.23.1 과 같다).

    반환: None(없음) / ""(있지만 대답이 없음 — 옛 판이거나 멈춘 것) /
    판 번호(1.0.4 부터는 'ok 판번호' 로 대답한다).
    """
    sock = QLocalSocket()
    sock.connectToServer(_SINGLE_KEY)
    if not sock.waitForConnected(400):
        return None
    reply = ""
    try:
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(500)
        if sock.waitForReadyRead(1200):
            got = bytes(sock.readAll()).decode("ascii", "ignore").split()
            if len(got) >= 2 and got[0] == "ok":
                reply = got[1]
        sock.disconnectFromServer()
    except Exception:
        pass
    return reply


def _take_over_after_update(reply) -> bool:
    """방금 업데이트로 깔린 새 판인데 옛 판이 아직 남아 있으면 그것을 끝내고 이어서 뜬다.

    ⚠️ 일정관리기가 v1.22.1 → v1.23.0 에서 겪은 일: 옛 판이 끝나지 않고 남아, 새 판이 떠도
       '이미 실행 중' 으로 보고 옛 창만 불러온 뒤 스스로 꺼졌다 → 업데이트를 해도 계속 옛 판.
       방금 깔린 것(업데이트 기록이 막 'replaced ok')이고, 남은 쪽이 대답이 없거나(옛 판)
       더 낮은 판이면 새 판이 이긴다. 그 밖(보통 두 번 실행)은 있는 창만 띄우고 끝낸다.
    """
    if not updater.is_frozen() or not updater.just_installed():
        return False
    if reply and updater.parse_ver(reply) >= updater.parse_ver(config.APP_VERSION):
        return False
    return updater.kill_other_instances() > 0


def _hard_exit(rc: int) -> None:
    """파이썬의 마무리 정리(위젯·Qt 객체를 하나씩 지우기)를 건너뛰고 바로 끝낸다.

    그 정리 중에 멈추면 프로그램이 남아 업데이트·다음 실행을 막는다(일정관리기 v1.23.1).
    저장할 것은 이미 다 저장했다(바뀔 때마다 저장).
    """
    crashlog.shutdown()
    try:
        sys.stdout and sys.stdout.flush()
        sys.stderr and sys.stderr.flush()
    except Exception:
        pass
    os._exit(rc)


class _NoWheelOnCombo(QObject):
    """드롭다운·숫자 칸 위에서 휠을 굴려도 값이 바뀌지 않게 막는다(일정관리기와 같다)."""

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Wheel:
            if isinstance(obj, QComboBox):
                if not obj.view().isVisible():
                    ev.ignore()
                    return True
            elif isinstance(obj, QLineEdit) and isinstance(obj.parent(), QComboBox):
                ev.ignore()
                return True
            elif isinstance(obj, QAbstractSpinBox):
                ev.ignore()
                return True
        return super().eventFilter(obj, ev)


def _check_with_splash(app, quiet: bool):
    """업데이트를 확인한다 → (새 판 정보 | None, 확인했나).

    오래 걸리면(0.5초 넘게) '업데이트 확인 중…' 작은 창을 띄운다. quiet(부팅)면 안 띄운다.
    """
    box: dict = {}

    def work():
        try:
            box["info"] = updater.check()
        except Exception as e:
            box["err"] = str(e)
    th = threading.Thread(target=work, daemon=True)
    th.start()
    th.join(0.5)
    splash = None
    if th.is_alive() and not quiet:
        splash = QWidget(None, Qt.SplashScreen | Qt.WindowStaysOnTopHint)
        v = QVBoxLayout(splash)
        v.setContentsMargins(28, 20, 28, 20)
        v.addWidget(QLabel(f"{config.APP_NAME} — 업데이트 확인 중…"))
        splash.setWindowIcon(make_icon())
        splash.show()
    started = time.monotonic()
    while th.is_alive() and time.monotonic() - started < CHECK_WAIT_SEC:
        app.processEvents()
        th.join(0.05)
    if splash is not None:
        splash.close()
    if "info" in box:
        return box["info"], True
    return None, False


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    tray_start = any(a.lstrip("/-").lower() == "tray" for a in sys.argv[1:])

    # (단, 방금 업데이트로 깔렸는데 옛 판이 남아 있으면 그것을 끝내고 이어서 뜬다)
    reply = _activate_existing()
    if reply is not None:
        if not _take_over_after_update(reply):
            return 0
        time.sleep(1.5)                 # 끝낸 옛 판이 소켓·파일을 놓을 때까지
    # 갑자기 꺼짐·멈춤을 기록한다(crashlog.py — 일정관리기와 같다). 두 번째 실행은 위에서 빠졌다.
    prev_crash = crashlog.start()
    crashlog.install_qt_handler()       # Qt 의 오류 문구도 같은 기록에(창 프로그램이라 안 보인다)
    app.aboutToQuit.connect(crashlog.clean_exit)
    app.aboutToQuit.connect(crashlog.remove_qt_handler)   # 정리 중 문구가 파이썬을 안 부르게
    app.commitDataRequest.connect(crashlog.clean_exit)      # 윈도를 끌 때도 정상 종료
    QLocalServer.removeServer(_SINGLE_KEY)
    server = QLocalServer()
    server.listen(_SINGLE_KEY)

    app.setQuitOnLastWindowClosed(False)
    font = QFont("Malgun Gothic", 10)
    font.setWeight(QFont.DemiBold)
    app.setFont(font)
    nowheel = _NoWheelOnCombo(app)
    app.installEventFilter(nowheel)
    app.setWindowIcon(make_icon())

    settings = Settings.load()
    theme.set_theme(settings.theme)
    theme.apply_to_app(app)

    win_box: dict = {}

    # 'ok 판번호' 로 대답한다 — 업데이트로 막 깔린 새 판이 '남은 옛 판인가' 를 가린다.
    def on_second():
        conn = server.nextPendingConnection()
        if conn is not None:
            try:
                conn.write(f"ok {config.APP_VERSION}\n".encode("ascii"))
                conn.flush()
                conn.waitForBytesWritten(300)
            except Exception:
                pass
            conn.disconnectFromServer()
        w = win_box.get("win")
        if w is not None:
            w.show_window()
        elif not config.SERVICE_ON:
            pass                     # 곧 안내를 띄우고 끝난다
    server.newConnection.connect(on_second)

    # ── 업데이트 (건너뛸 수 없다) ──
    info, checked = _check_with_splash(app, quiet=tray_start)
    if info:
        from .update_ui import CONTINUE, UpdateDialog
        if UpdateDialog.run(info) != CONTINUE:
            crashlog.clean_exit()        # 업데이트로 끝나는 것도 정상 종료다
            _hard_exit(0)                # 바꾸는 배치가 기다린다 — 남지 않고 바로 끝난다

    # ── 서비스 스위치 ──
    if not config.SERVICE_ON:
        if not tray_start:           # 부팅 때마다 안내가 뜨지 않게, 직접 켰을 때만 알린다
            QMessageBox.information(None, config.APP_NAME, config.SERVICE_OFF_MESSAGE)
        crashlog.clean_exit()
        return 0

    startup.refresh()                # exe 를 옮겼으면 자동 실행 경로를 고친다

    from .main_window import MainWindow
    win = MainWindow(settings, update_checked=checked)
    win_box["win"] = win
    crashlog.start_watchdog(app)        # 화면이 15초 넘게 멈추면 그때 상황을 적는다
    if prev_crash:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2500, lambda: crashlog.show_notice(win, prev_crash))
    if tray_start:
        win.start_in_tray()
    else:
        win.show_window()
    _hard_exit(app.exec())


if __name__ == "__main__":
    sys.exit(main())
