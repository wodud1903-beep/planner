"""애플리케이션 진입점 — 업데이트 확인을 **창보다 먼저** 한다.

순서
  1. 이미 켜져 있으면 그 창을 띄우고 끝낸다(한 PC 에 하나만).
  2. 업데이트 확인 — 새 판이 있으면 받아 바꾸기 전에는 넘어가지 않는다(update_ui).
     인터넷이 안 돼 확인을 못 하면 그냥 켠다(켜 둔 동안 다시 확인한다).
  3. 서비스 스위치(config.SERVICE_ON) — 꺼진 판이면 안내만 하고 끝낸다.
  4. 메인 창. `/tray` 로 켜지면(PC 시작 시 자동 실행) 창 없이 트레이에서 시작한다.
"""

from __future__ import annotations

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

from . import config, startup, theme, updater
from .icon import make_icon
from .settings import Settings

_SINGLE_KEY = "KbSearch_SingleInstance_v1"
CHECK_WAIT_SEC = 12          # 켤 때 업데이트 확인을 기다리는 최대 시간


def _activate_existing() -> bool:
    """이미 실행 중인 것이 있으면 그 창을 띄우도록 신호를 보내고 True."""
    sock = QLocalSocket()
    sock.connectToServer(_SINGLE_KEY)
    if sock.waitForConnected(400):
        try:
            sock.write(b"show")
            sock.flush()
            sock.waitForBytesWritten(500)
            sock.disconnectFromServer()
        except Exception:
            pass
        return True
    return False


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

    if _activate_existing():
        return 0
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

    def on_second():
        conn = server.nextPendingConnection()
        if conn is not None:
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
            return 0

    # ── 서비스 스위치 ──
    if not config.SERVICE_ON:
        if not tray_start:           # 부팅 때마다 안내가 뜨지 않게, 직접 켰을 때만 알린다
            QMessageBox.information(None, config.APP_NAME, config.SERVICE_OFF_MESSAGE)
        return 0

    startup.refresh()                # exe 를 옮겼으면 자동 실행 경로를 고친다

    from .main_window import MainWindow
    win = MainWindow(settings, update_checked=checked)
    win_box["win"] = win
    if tray_start:
        win.start_in_tray()
    else:
        win.show_window()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
