"""화면 최상단 중앙에 뜨는 알람 팝업 (델파이 uAlarm 이식 + 둥근 디자인).

- 항상 위 + 포커스를 뺏지 않고 표시
- 멘트가 있으면 [멘트 복사] 버튼으로 클립보드에 복사
- 사이렌 모드: 빨강/어둠 깜빡임 + 비프음, [5분 뒤 다시]
- 조용한 모드(브리핑): 깜빡임·소리 없음, 메모가 내용에 맞춰 커져 스크롤 불필요
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

# 메모 기본 높이의 약 4배
_MEMO_SIREN = 340
_MEMO_QUIET_MIN = 340


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
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedWidth(640)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # 둥근 카드
        self.card = QWidget()
        self.card.setObjectName("card")
        self._set_card_bg(config.COLOR_ALARM_DARK)
        outer.addWidget(self.card)

        root = QVBoxLayout(self.card)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 상단 바 (둥근 윗모서리)
        self.bar = QLabel("일정 알람" if siren else "안내")
        self.bar.setObjectName("bar")
        self.bar.setAlignment(Qt.AlignCenter)
        self.bar.setFixedHeight(34)
        self._set_bar_bg(config.COLOR_ALARM_DARK)
        root.addWidget(self.bar)

        body = QVBoxLayout()
        body.setContentsMargins(20, 16, 20, 18)
        body.setSpacing(12)

        self.lbl_title = QLabel(title)
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setStyleSheet(
            f"color:{config.COLOR_ALARM_YELLOW};font-size:17px;font-weight:bold;background:transparent;")
        body.addWidget(self.lbl_title)

        self.txt = QTextEdit()
        self.txt.setReadOnly(True)
        self.txt.setPlainText(ment)
        self.txt.setStyleSheet(
            "QTextEdit{background:#2a2a2a;color:#f0f0f0;border:1px solid #555;"
            "border-radius:10px;padding:8px;}")
        if ment.strip():
            self.txt.setFixedHeight(self._memo_height(ment, siren))
            body.addWidget(self.txt)
        else:
            self.txt.hide()

        btns = QHBoxLayout()
        btns.setSpacing(10)
        self.btn_copy = QPushButton("멘트 복사")
        self.btn_copy.clicked.connect(self._copy)
        self.btn_snooze = QPushButton("5분 뒤 다시")
        self.btn_snooze.clicked.connect(self._snooze)
        self.btn_ok = QPushButton("확인")
        self.btn_ok.clicked.connect(self._dismiss)
        for b in (self.btn_copy, self.btn_snooze, self.btn_ok):
            b.setFixedHeight(38)
            b.setStyleSheet(
                "QPushButton{background:#4a4a4a;color:#fff;border:none;border-radius:10px;"
                "padding:6px 14px;font-weight:bold;} QPushButton:hover{background:#5a5a5a;}")
        if ment.strip():
            btns.addWidget(self.btn_copy)
        else:
            self.btn_copy.hide()
        if siren:
            btns.addWidget(self.btn_snooze)
        else:
            self.btn_snooze.hide()
        btns.addWidget(self.btn_ok)
        body.addLayout(btns)

        root.addLayout(body)

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

    # ---- 메모 높이 계산 ----
    def _memo_height(self, ment: str, siren: bool) -> int:
        if siren:
            return _MEMO_SIREN
        # 브리핑: 내용 줄 수에 맞춰 확장(스크롤 없이 다 보이게), 화면 높이로 제한
        screen = QGuiApplication.primaryScreen().availableGeometry()
        lines = ment.count("\n") + 1
        needed = 40 + lines * 22
        return max(_MEMO_QUIET_MIN, min(needed, screen.height() - 220))

    # ---- 스타일 헬퍼 ----
    def _set_card_bg(self, color: str):
        self.card.setStyleSheet(
            f"#card{{background:{color};border-radius:16px;}}")

    def _set_bar_bg(self, color: str):
        self.bar.setStyleSheet(
            f"#bar{{background:{color};color:#ddd;font-weight:bold;"
            "border-top-left-radius:16px;border-top-right-radius:16px;}")

    # ---- 사이렌 깜빡임 ----
    def _tick(self):
        self._blink += 1
        if self._blink % 2 == 1:
            self._set_card_bg(config.COLOR_ALARM_RED)
            self._set_bar_bg(config.COLOR_ALARM_RED)
            self.lbl_title.setStyleSheet(
                "color:#fff;font-size:17px;font-weight:bold;background:transparent;")
        else:
            self._set_card_bg(config.COLOR_ALARM_DARK)
            self._set_bar_bg(config.COLOR_ALARM_DARK)
            self.lbl_title.setStyleSheet(
                f"color:{config.COLOR_ALARM_YELLOW};font-size:17px;font-weight:bold;background:transparent;")
        self.raise_()
        if self._blink % 3 == 0:
            QApplication.beep()

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
