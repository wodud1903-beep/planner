"""애플리케이션 진입점."""

from __future__ import annotations

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from . import config
from .main_window import MainWindow

# 전역 둥근 디자인 스타일시트 (버튼/입력/표/탭/대화상자/메시지창)
GLOBAL_QSS = """
QWidget { font-family: 'Malgun Gothic'; }
QPushButton {
    background: #f2f3f5;
    border: 1px solid #d0d3d9;
    border-radius: 8px;
    padding: 5px 14px;
}
QPushButton:hover { background: #e7ebf2; }
QPushButton:pressed { background: #dbe0ea; }
QPushButton:default { border-color: #1f6feb; }
QPushButton:disabled { color: #999; background: #f5f5f5; }
QLineEdit, QComboBox, QSpinBox, QDateEdit, QTimeEdit, QTextEdit {
    border: 1px solid #d0d3d9;
    border-radius: 8px;
    padding: 4px 8px;
    background: white;
    selection-background-color: #1f6feb;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
QDateEdit:focus, QTimeEdit:focus, QTextEdit:focus { border-color: #1f6feb; }
QGroupBox {
    border: 1px solid #d8dbe0;
    border-radius: 12px;
    margin-top: 10px;
    padding: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 5px;
    color: #444;
    font-weight: bold;
}
QTabWidget::pane { border: 1px solid #d8dbe0; border-radius: 10px; top: -1px; }
QTabBar::tab {
    background: #eef0f3;
    border: 1px solid #d8dbe0;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    padding: 7px 18px;
    margin-right: 3px;
}
QTabBar::tab:selected { background: white; border-bottom-color: white; }
QTableWidget {
    border: 1px solid #dfe2e7;
    border-radius: 10px;
    gridline-color: #eceef1;
    selection-background-color: #d7e6ff;
    selection-color: #000;
}
QHeaderView::section {
    background: #f4f6f9;
    border: none;
    border-right: 1px solid #e6e8ec;
    border-bottom: 1px solid #e0e3e8;
    padding: 6px;
}
QCheckBox { spacing: 6px; }
QDialog, QMessageBox { background: #ffffff; }
QScrollBar:vertical { border: none; background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #c3c8d0; border-radius: 5px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #aab0ba; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    # 트레이로 최소화해도 프로세스가 살아있게
    app.setQuitOnLastWindowClosed(False)

    # 한글 친화 폰트 (없으면 시스템 기본)
    app.setFont(QFont("Malgun Gothic", 10))
    app.setStyleSheet(GLOBAL_QSS)

    win = MainWindow()

    # /tray 스위치로 실행되면 트레이로 시작
    if any(a.lstrip("/-").lower() == "tray" for a in sys.argv[1:]):
        win.hide()
    else:
        win.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
