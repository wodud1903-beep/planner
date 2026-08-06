"""화면 최상단 중앙에 뜨는 알람 팝업 (델파이 uAlarm 이식).

- 항상 위 + 포커스를 뺏지 않고 표시
- 멘트가 있으면 [멘트 복사] 버튼으로 클립보드에 복사
- 사이렌 모드: 빨강/어둠 깜빡임 + 비프음, [5분 뒤 다시]
- 조용한 모드(브리핑): 깜빡임·소리 없음
- 여러 개가 동시에 뜨면 아래로 쌓인다
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from . import config

_open_alarms: list["AlarmWindow"] = []


class AlarmWindow(QWidget):
    def __init__(self, title: str, ment: str, stack_index: int, siren: bool = True):
        super().__init__()
        self._siren = siren
        self._blink = 0
        self._snooze_left = 0

        self.setWindowFlags(
            Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedWidth(620)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 상단 바
        self.bar = QLabel("일정 알람" if siren else "안내")
        self.bar.setAlignment(Qt.AlignCenter)
        self.bar.setFixedHeight(30)
        self.bar.setStyleSheet(
            f"background:{config.COLOR_ALARM_DARK};color:#dddddd;font-weight:bold;")
        root.addWidget(self.bar)

        body = QWidget()
        body.setStyleSheet(f"background:{config.COLOR_ALARM_DARK};")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(18, 14, 18, 14)

        self.lbl_title = QLabel(title)
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setStyleSheet(
            "color:#FFFF60;font-size:16px;font-weight:bold;")
        bl.addWidget(self.lbl_title)

        self.txt = QTextEdit()
        self.txt.setReadOnly(True)
        self.txt.setPlainText(ment)
        self.txt.setStyleSheet(
            "background:#2a2a2a;color:#f0f0f0;border:1px solid #555;")
        self.txt.setFixedHeight(120)
        if ment.strip():
            bl.addWidget(self.txt)
        else:
            self.txt.hide()

        btns = QHBoxLayout()
        self.btn_copy = QPushButton("멘트 복사")
        self.btn_copy.clicked.connect(self._copy)
        self.btn_snooze = QPushButton("5분 뒤 다시")
        self.btn_snooze.clicked.connect(self._snooze)
        self.btn_ok = QPushButton("확인")
        self.btn_ok.clicked.connect(self._dismiss)
        for b in (self.btn_copy, self.btn_snooze, self.btn_ok):
            b.setFixedHeight(34)
        if ment.strip():
            btns.addWidget(self.btn_copy)
        else:
            self.btn_copy.hide()
        if siren:
            btns.addWidget(self.btn_snooze)
        else:
            self.btn_snooze.hide()
        btns.addWidget(self.btn_ok)
        bl.addLayout(btns)

        root.addWidget(body)

        # 위치: 상단 중앙, 여러 개면 아래로 쌓기
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        x = screen.left() + (screen.width() - self.width()) // 2
        y = screen.top() + 20 + stack_index * (self.height() + 10)
        self.move(x, y)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        if siren:
            self._timer.start(500)
            QApplication.beep()

        self._snooze_timer = QTimer(self)
        self._snooze_timer.timeout.connect(self._snooze_tick)

    # ---- 사이렌 깜빡임 ----
    def _tick(self):
        self._blink += 1
        if self._blink % 2 == 1:
            self.bar.setStyleSheet(
                f"background:{config.COLOR_ALARM_RED};color:#fff;font-weight:bold;")
            self.centralwidget_bg(config.COLOR_ALARM_RED)
            self.lbl_title.setStyleSheet("color:#fff;font-size:16px;font-weight:bold;")
        else:
            self.bar.setStyleSheet(
                f"background:{config.COLOR_ALARM_DARK};color:#ddd;font-weight:bold;")
            self.centralwidget_bg(config.COLOR_ALARM_DARK)
            self.lbl_title.setStyleSheet(
                f"color:{config.COLOR_ALARM_YELLOW};font-size:16px;font-weight:bold;")
        self.raise_()
        if self._blink % 3 == 0:
            QApplication.beep()

    def centralwidget_bg(self, color: str):
        # 본문 배경 갱신 (bar 아래 body 위젯)
        body = self.layout().itemAt(1).widget()
        if body:
            body.setStyleSheet(f"background:{color};")

    def _copy(self):
        try:
            QApplication.clipboard().setText(self.txt.toPlainText())
            self.btn_copy.setText("복사됨 ✔")
        except Exception:
            self.btn_copy.setText("복사 실패")

    def _snooze(self):
        self._timer.stop()
        self._snooze_left = 5 * 60
        self._snooze_timer.start(1000)
        self.hide()

    def _snooze_tick(self):
        self._snooze_left -= 1
        if self._snooze_left > 0:
            return
        self._snooze_timer.stop()
        self._blink = 0
        self.show_no_activate()
        if self._siren:
            self._timer.start(500)
            QApplication.beep()

    def stop(self):
        self._timer.stop()
        self._snooze_timer.stop()

    def _dismiss(self):
        self.stop()
        self.close()

    def show_no_activate(self):
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.show()
        self.raise_()

    def closeEvent(self, event):
        self.stop()
        if self in _open_alarms:
            _open_alarms.remove(self)
        super().closeEvent(event)


def popup(title: str, ment: str, stack_index: int, siren: bool = True) -> AlarmWindow:
    w = AlarmWindow(title, ment, stack_index, siren)
    _open_alarms.append(w)
    w.show_no_activate()
    return w


def close_all():
    for w in list(_open_alarms):
        w.stop()
        w.close()
