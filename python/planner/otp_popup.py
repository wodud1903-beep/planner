"""휴대폰으로 온 인증번호를 PC 화면 오른쪽 아래에 크게 띄운다(v1.31, otp.py 가 찾는다).

  · 항상 위 · 포커스를 뺏지 않는다(로그인 창에 치던 중이어도 그대로 Ctrl+V 하면 된다).
  · 뜨자마자 클립보드에 넣는다(설정에서 끌 수 있다). 번호를 눌러도 복사된다.
  · 10초 뒤 저절로 닫힌다(v1.31.1 지점장 요청 — 이미 복사돼 있다). 마우스를 올려 두면 닫지 않는다.
  · 여러 개가 오면 위로 쌓인다. 언제나 주 모니터 · 화면(작업표시줄 제외) 밖으로 나가지 않는다.

⚠️ v1.32.1 — 창을 **만들었다 지우지 않는다.** 처음 쓸 때 만든 창 몇 개를 숨겼다 다시 쓴다.
   v1.31.3 에서 'Windows fatal exception: access violation'(화면 스레드가 app.exec 안에서 꺼짐)이
   있었다. 그 판에서 새로 생긴, 자주 만들고 지우는 최상위 창은 이 팝업뿐이었다 — 부모 없는 창 +
   WA_DeleteOnClose(Qt 가 지움) + 파이썬이 쥔 참조(번호 칸 클릭 람다가 창을 되잡는 고리)가 겹쳐
   한 창을 두 번 지울 수 있었다. 이제 지우지 않으니 그런 일이 없다.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import theme

LIFE_MS = 10 * 1000
_EDGE = 16
_GAP = 10
_open: list["OtpPopup"] = []
_pool: list["OtpPopup"] = []          # 만든 창(숨긴 것 포함) — 지우지 않고 다시 쓴다
POOL_MAX = 3


class _ClickLabel(QLabel):
    """누르면 clicked — 예전엔 mousePressEvent 에 람다를 끼워 창을 되잡는 고리가 생겼다."""
    clicked = Signal()

    def mousePressEvent(self, e):          # noqa: N802 — Qt 이름
        self.clicked.emit()
        super().mousePressEvent(e)


def _screen():
    """언제나 주 모니터(v1.31.1) — 듀얼 모니터에서 마우스 따라 이쪽저쪽 뜨지 않게."""
    return QGuiApplication.primaryScreen()


class OtpPopup(QWidget):
    def __init__(self, item: dict, copied: bool = False):
        super().__init__()
        self.code = ""
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_DeleteOnClose, False)   # 닫으면 숨기기만 — 다음 번호에 다시 쓴다
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
        self.lbl_head = QLabel("📱 인증번호")
        self.lbl_head.setStyleSheet(f"color:{theme.c('subtext')};font-weight:bold;")
        top.addWidget(self.lbl_head, 1)
        self.btn_x = QPushButton("✕")
        self.btn_x.setFixedSize(30, 26)
        self.btn_x.setStyleSheet("padding:0;")
        self.btn_x.clicked.connect(self.close)
        top.addWidget(self.btn_x)
        v.addLayout(top)

        self.lbl_code = _ClickLabel("")
        self.lbl_code.setCursor(Qt.PointingHandCursor)
        self.lbl_code.setToolTip("누르면 복사")
        self.lbl_code.setStyleSheet(
            f"color:{theme.c('accent')};font-size:34px;font-weight:bold;letter-spacing:4px;")
        self.lbl_code.clicked.connect(self.copy)
        v.addWidget(self.lbl_code)

        self.lbl_body = QLabel("")
        self.lbl_body.setWordWrap(True)
        self.lbl_body.setStyleSheet(f"color:{theme.c('subtext')};font-size:12px;")
        v.addWidget(self.lbl_body)

        row = QHBoxLayout()
        self.lbl_state = QLabel("")
        self.lbl_state.setStyleSheet(f"color:{theme.c('status_ok')};font-size:12px;")
        row.addWidget(self.lbl_state, 1)
        self.btn_copy = QPushButton("복사")
        self.btn_copy.clicked.connect(self.copy)
        row.addWidget(self.btn_copy)
        v.addLayout(row)

        self._life = QTimer(self)                 # 창과 함께 사라지는 타이머(닫은 뒤에 울리지 않게)
        self._life.setSingleShot(True)
        self._life.timeout.connect(self.close)
        self.set_item(item, copied)

    def set_item(self, item: dict, copied: bool = False) -> None:
        """이 창에 새 번호를 싣는다(다시 쓸 때도 이것으로)."""
        self.code = str(item.get("code") or "")
        who = str(item.get("sender") or "").strip()
        self.lbl_head.setText("📱 인증번호" + (f" · {who}" if who else ""))
        self.lbl_code.setText(self.code)
        body = " ".join(str(item.get("body") or "").replace("[Web발신]", "").split())
        self.lbl_body.setText(body[:90] + ("…" if len(body) > 90 else ""))
        self.lbl_state.setText("복사해 두었습니다 — Ctrl+V 로 붙여 넣으세요" if copied else "")
        self._life.start(LIFE_MS)

    def enterEvent(self, e):
        # 마우스가 **정말 이 창 안에 있을 때만** 멈춘다 — 창이 뜰 때 밖에 있는 마우스로도 '들어왔다' 가 오는
        # 일이 있어(검사에서 실제로 봤다), 그대로 멈추면 10초가 지나도 닫히지 않는다.
        try:
            inside = self.rect().contains(e.position().toPoint())
        except Exception:
            inside = False
        if inside:
            self._life.stop()                     # 보는 중 — 닫지 않는다
        super().enterEvent(e)

    def leaveEvent(self, e):
        if not self._life.isActive():
            self._life.start(LIFE_MS)             # 손을 떼면 다시 10초
        super().leaveEvent(e)

    def copy(self) -> None:
        QApplication.clipboard().setText(self.code)
        self.lbl_state.setText("복사했습니다 — Ctrl+V 로 붙여 넣으세요")

    def closeEvent(self, e):
        self._life.stop()
        if self in _open:
            _open.remove(self)
        super().closeEvent(e)              # 숨기기만 한다(WA_DeleteOnClose 없음)
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


def _take(item: dict, copied: bool) -> OtpPopup:
    """숨어 있는 창을 다시 쓴다. 없으면 새로 만들고(많아야 POOL_MAX), 다 떠 있으면 가장 오래된 것을."""
    for w in _pool:
        if w not in _open and not w.isVisible():
            w.set_item(item, copied)
            return w
    if len(_pool) < POOL_MAX:
        w = OtpPopup(item, copied=copied)
        _pool.append(w)
        return w
    w = _open[0]
    _open.remove(w)
    w.set_item(item, copied)
    return w


def show(item: dict, copied: bool = False) -> OtpPopup:
    w = _take(item, copied)
    _open.append(w)
    while len(_open) > POOL_MAX:              # 많아야 셋 — 오래된 것부터 닫는다
        _open[0].close()
    w.show()
    _arrange()
    try:
        from . import crashlog
        crashlog.note("인증번호 팝업")      # 꺼짐이 또 나면 그 직전에 무엇을 했는지 보이게
    except Exception:
        pass
    return w
