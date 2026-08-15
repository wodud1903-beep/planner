"""애플리케이션 진입점."""

from __future__ import annotations

import sys

from PySide6.QtGui import QFont
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from . import config, theme
from .main_window import MainWindow

# 중복 실행 방지용 로컬 소켓 이름 (한 사용자당 하나만 실행)
_SINGLE_KEY = "Planner_SingleInstance_v1"


def _activate_existing() -> bool:
    """이미 실행 중인 인스턴스가 있으면 그 창을 띄우도록 신호를 보내고 True."""
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

# 전역 스타일시트 — 델파이 스킨 'Tablet Light' 톤 (밝은 청회색 + 은은한 라운드)
GLOBAL_QSS = """
QWidget { font-family: 'Malgun Gothic'; color: #2C3E50; }
QMainWindow, QWidget#central { background: #F5F7FA; }
QPushButton {
    background: #EAF1F8;
    border: 1px solid #B4C6D8;
    border-radius: 7px;
    padding: 5px 14px;
    color: #2C3E50;
}
QPushButton:hover { background: #DCE8F4; }
QPushButton:pressed { background: #CCDDEE; }
QPushButton:default { border: 1px solid #5B8FBF; }
QPushButton:disabled { color: #9AA7B4; background: #EEF1F5; border-color: #D2DBE4; }
QLineEdit, QComboBox, QSpinBox, QDateEdit, QTimeEdit, QTextEdit {
    border: 1px solid #B4C6D8;
    border-radius: 7px;
    padding: 4px 8px;
    background: #FFFFFF;
    selection-background-color: #5B8FBF;
    selection-color: #FFFFFF;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
QDateEdit:focus, QTimeEdit:focus, QTextEdit:focus { border: 1px solid #5B8FBF; }
QGroupBox {
    border: 1px solid #C6D3E0;
    border-radius: 10px;
    margin-top: 10px;
    padding: 10px;
    background: #FBFCFE;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 5px;
    color: #46596B;
    font-weight: bold;
}
QTabWidget::pane { border: 1px solid #C6D3E0; border-radius: 9px; top: -1px; background: #FFFFFF; }
QTabBar::tab {
    background: #DCE6F0;
    border: 1px solid #C6D3E0;
    border-top-left-radius: 9px;
    border-top-right-radius: 9px;
    padding: 7px 18px;
    margin-right: 3px;
    color: #46596B;
}
QTabBar::tab:selected { background: #FFFFFF; color: #2C3E50; border-bottom-color: #FFFFFF; }
QTableWidget {
    border: 1px solid #C6D3E0;
    border-radius: 9px;
    background: #FFFFFF;
    gridline-color: #E3EAF1;
    selection-background-color: #CFE0F4;
    selection-color: #1A2A38;
}
QHeaderView::section {
    background: #E4ECF4;
    color: #46596B;
    border: none;
    border-right: 1px solid #D2DDE8;
    border-bottom: 1px solid #C6D3E0;
    padding: 6px;
}
QCheckBox { spacing: 6px; }
QDialog, QMessageBox { background: #F5F7FA; }
QScrollBar:vertical { border: none; background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #B8C9DA; border-radius: 5px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #9FB4C8; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)

    # ── 중복 실행 방지 ──
    # 이미 실행 중이면 기존 창만 띄우고 이 프로세스는 즉시 종료한다.
    if _activate_existing():
        return 0
    # 이전 비정상 종료로 남은 소켓 잔재 정리 후 서버로 대기
    QLocalServer.removeServer(_SINGLE_KEY)
    _server = QLocalServer()
    _server.listen(_SINGLE_KEY)

    # 트레이로 최소화해도 프로세스가 살아있게
    app.setQuitOnLastWindowClosed(False)

    # 한글 친화 폰트 (없으면 시스템 기본)
    app.setFont(QFont("Malgun Gothic", 10))
    # 저장된 테마(라이트/다크) 선호를 미리 반영 (계정별 설정은 로그인 후 재적용)
    try:
        from .models import AppSettings
        theme.set_theme(AppSettings.load(config.data_file("plan_cfg.json")).dark_mode)
    except Exception:
        theme.set_theme(False)
    # 스타일시트 + 팔레트를 함께 적용 (팔레트를 안 주면 윈도우 시스템 다크 테마가
    # 스크롤 영역 등 스타일시트가 닿지 않는 표면으로 새어 나온다)
    theme.apply_to_app(app)

    win = MainWindow()

    # 두 번째 실행이 신호를 보내오면 기존 창을 앞으로 띄운다.
    def _on_second_instance():
        conn = _server.nextPendingConnection()
        if conn is not None:
            conn.disconnectFromServer()
        win.show_window()

    _server.newConnection.connect(_on_second_instance)

    # /tray 스위치로 실행되면 트레이로 시작
    if any(a.lstrip("/-").lower() == "tray" for a in sys.argv[1:]):
        win.hide()
    else:
        win.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
