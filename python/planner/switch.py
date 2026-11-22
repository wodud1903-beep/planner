"""켜기/끄기 스위치(v1.35) — PC 알람 표의 'ON / OFF' 글자 대신.

체크박스를 그림만 바꾼 것이라 toggled(bool) 신호 · isChecked() 를 그대로 쓴다.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QWidget

from . import theme


class Switch(QAbstractButton):
    W, H = 40, 22

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(self.W, self.H)

    def sizeHint(self):                 # noqa: N802 — Qt 이름 그대로
        return QSize(self.W, self.H)

    def paintEvent(self, _ev):          # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = self.isChecked()
        track = QColor(theme.c("accent") if on else theme.c("border"))
        if not self.isEnabled():
            track.setAlpha(110)
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        r = QRectF(0.5, 0.5, self.W - 1, self.H - 1)
        p.drawRoundedRect(r, self.H / 2, self.H / 2)
        d = self.H - 6
        x = self.W - d - 3 if on else 3
        p.setBrush(QColor(theme.fill_text()))      # 채운 면 위 글자색(테마마다 또렷한 흰색 계열)
        p.drawEllipse(QRectF(x, 3, d, d))
        p.end()


def centered(w: QWidget) -> QWidget:
    """표 칸 가운데에 놓는 그릇."""
    box = QWidget()
    h = QHBoxLayout(box)
    h.setContentsMargins(0, 0, 0, 0)
    h.addStretch(1)
    h.addWidget(w)
    h.addStretch(1)
    return box
