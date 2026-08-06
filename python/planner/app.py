"""애플리케이션 진입점."""

from __future__ import annotations

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from . import config
from .main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    # 트레이로 최소화해도 프로세스가 살아있게
    app.setQuitOnLastWindowClosed(False)

    # 한글 친화 폰트 (없으면 시스템 기본)
    app.setFont(QFont("Malgun Gothic", 10))

    win = MainWindow()

    # /tray 스위치로 실행되면 트레이로 시작
    if any(a.lstrip("/-").lower() == "tray" for a in sys.argv[1:]):
        win.hide()
    else:
        win.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
