"""휴대폰으로 온 인증번호를 PC 화면 오른쪽 아래에 크게 띄운다(v1.31, otp.py 가 찾는다).

  · 항상 위 · 포커스를 뺏지 않는다(로그인 창에 치던 중이어도 그대로 Ctrl+V 하면 된다).
  · 뜨자마자 클립보드에 넣는다(설정에서 끌 수 있다). 번호를 눌러도 복사된다.
  · 10초 뒤 저절로 닫힌다(v1.31.1 지점장 요청 — 이미 복사돼 있다). 마우스를 올려 두면 닫지 않는다.
  · 여러 개가 오면 위로 쌓인다. 언제나 주 모니터 · 화면(작업표시줄 제외) 밖으로 나가지 않는다.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import theme

LIFE_MS = 10 * 1000
_EDGE = 16
_GAP = 10
_open: list["OtpPopup"] = []


def _screen():
    """언제나 주 모니터(v1.31.1) — 듀얼 모니터에서 마우스 따라 이쪽저쪽 뜨지 않게."""
    return QGuiApplication.primaryScreen()


class OtpPopup(QWidget):
    def __init__(self, item: dict, copied: bool = False):
        super().__init__()
        self.code = str(item.get("code") or "")
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setFixedWidth(340)
        self.setObjectName("otp")
        self.setStyleSheet(
            f"#otp{{background:{theme.c('panel_bg')};border:2px solid {theme.c('accent')};border-radius:16px;}}"
            f"QLabel{{background:transparent;color:{theme.c('text')};}}"
            f"QPushButton{{background:{theme.c('btn_bg')};color:{theme.c('text')};border:1px solid {theme.c('border')};"
            f"border-radius:10px;padding:6px 14px;font-weight:bold;}}"
            f"QPushButton:hover{{background:{theme.c('btn_hover')};}}")
        self.setAttribute(Qt.WA_StyledBackground, True)

        v = QVBoxLayout(self)
        v.setContentsMargins(18, 12, 12, 14)
        v.setSpacing(6)
        top = QHBoxLayout()
        who = str(item.get("sender") or "").strip()
        self.lbl_head = QLabel("📱 인증번호" + (f" · {who}" if who else ""))
        self.lbl_head.setStyleSheet(f"color:{theme.c('subtext')};font-weight:bold;")
        top.addWidget(self.lbl_head, 1)
        self.btn_x = QPushButton("✕")
        self.btn_x.setFixedSize(30, 26)
        self.btn_x.setStyleSheet("padding:0;")
        self.btn_x.clicked.connect(self.close)
        top.addWidget(self.btn_x)
        v.addLayout(top)

        self.lbl_code = QLabel(self.code)
        self.lbl_code.setCursor(Qt.PointingHandCursor)
        self.lbl_code.setToolTip("누르면 복사")
        self.lbl_code.setStyleSheet(
            f"color:{theme.c('accent')};font-size:34px;font-weight:bold;letter-spacing:4px;")
        self.lbl_code.mousePressEvent = lambda e: self.copy()
        v.addWidget(self.lbl_code)

        body = " ".join(str(item.get("body") or "").replace("[Web발신]", "").split())
        self.lbl_body = QLabel(body[:90] + ("…" if len(body) > 90 else ""))
        self.lbl_body.setWordWrap(True)
        self.lbl_body.setStyleSheet(f"color:{theme.c('subtext')};font-size:12px;")
        v.addWidget(self.lbl_body)

        row = QHBoxLayout()
        self.lbl_state = QLabel("복사해 두었습니다 — Ctrl+V 로 붙여 넣으세요" if copied else "")
        self.lbl_state.setStyleSheet(f"color:{theme.c('status_ok')};font-size:12px;")
        row.addWidget(self.lbl_state, 1)
        self.btn_copy = QPushButton("복사")
        self.btn_copy.clicked.connect(self.copy)
        row.addWidget(self.btn_copy)
        v.addLayout(row)

        self._life = QTimer(self)                 # 창과 함께 사라지는 타이머(닫은 뒤에 울리지 않게)
        self._life.setSingleShot(True)
        self._life.timeout.connect(self.close)
        self._life.start(LIFE_MS)

    def enterEvent(self, e):
        self._life.stop()                         # 보는 중 — 닫지 않는다
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._life.start(LIFE_MS)                 # 손을 떼면 다시 10초
        super().leaveEvent(e)

    def copy(self) -> None:
        QApplication.clipboard().setText(self.code)
        self.lbl_state.setText("복사했습니다 — Ctrl+V 로 붙여 넣으세요")

    def closeEvent(self, e):
        if self in _open:
            _open.remove(self)
        super().closeEvent(e)
        _arrange()


def _arrange() -> None:
    """오른쪽 아래부터 위로 쌓는다(새 것이 맨 아래)."""
    if not _open:
        return
    geo = _screen().availableGeometry()
    y = geo.bottom() - _EDGE
    for w in reversed(_open):
        w.adjustSize()
        h = w.sizeHint().height()
        y -= h
        w.move(geo.right() - w.width() - _EDGE, max(geo.top() + _EDGE, y))
        y -= _GAP


def show(item: dict, copied: bool = False) -> OtpPopup:
    w = OtpPopup(item, copied=copied)
    _open.append(w)
    while len(_open) > 3:                     # 많아야 셋 — 오래된 것부터 닫는다
        _open[0].close()
    w.show()
    _arrange()
    return w
