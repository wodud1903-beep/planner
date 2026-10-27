"""대시보드 — 플로우처럼 흰 카드를 늘어놓은 첫 화면.

예전 '일정 / 할일' 화면을 바꿨다. 이번 주 일정·내 할일 표는 그대로 카드에 담고,
[주간 요약] 을 눌러야 보이던 **오늘 브리핑**과 **이번 주 요약**을 늘 펼쳐 두고,
**다음 주 요약**을 더했다(지점장 요청).

    ┌ 내 할일 ─────────────────────────┐ ┌ 오늘 브리핑 ┐
    └──────────────────────────────────┘ └─────────────┘
    ┌ 이번주 일정 ┐ ┌ 이번 주 요약 ┐ ┌ 다음 주 요약 ┐
    └─────────────┘ └──────────────┘ └──────────────┘

창이 좁으면 한 줄에 하나씩 쌓는다(DashGrid). 내용(표·글)은 main_window 가 채운다.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QTextBrowser, QToolButton,
    QVBoxLayout, QWidget,
)

from . import navicons, theme

WIDE_MIN = 1100                 # 카드 칸이 이보다 넓으면 2줄 배치(위 2:1, 아래 1:1:1)


def greeting(now: datetime | None = None) -> str:
    """시간대별 인사. 이름은 모르므로 붙이지 않는다."""
    h = (now or datetime.now()).hour
    if 5 <= h < 11:
        tail = "좋은 아침이에요."
    elif 11 <= h < 14:
        tail = "점심 맛있게 드세요."
    elif 14 <= h < 18:
        tail = "오후도 힘내세요."
    else:
        tail = "오늘도 수고 많으셨어요."
    return f"안녕하세요! {tail}"


class Card(QFrame):
    """흰 둥근 카드 — 머리 줄(제목 · 건수 · 오른쪽 단추) + 몸통."""

    def __init__(self, title: str = "", parent=None, title_label: QLabel | None = None):
        super().__init__(parent)
        self.setObjectName("card")
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 12, 16, 14)
        v.setSpacing(8)
        self.head = QHBoxLayout()
        self.head.setSpacing(6)
        # 제목을 이미 가진 라벨이 있으면(이번주 일정 'N건' 처럼 남이 고쳐 쓰는 것) 그걸 쓴다
        self.lbl_title = title_label or QLabel(title)
        self.lbl_title.setObjectName("cardtitle")
        self.head.addWidget(self.lbl_title)
        self.lbl_count = QLabel("")
        self.lbl_count.setObjectName("cardcount")
        self.head.addWidget(self.lbl_count)
        self.head.addStretch(1)
        v.addLayout(self.head)
        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(6)
        v.addLayout(self.body, 1)

    def add_action(self, w: QWidget) -> QWidget:
        self.head.addWidget(w)
        return w

    def set_count(self, text: str) -> None:
        self.lbl_count.setText(text)


def text_view() -> QTextBrowser:
    """카드 안의 글 칸 — 테두리 없이 카드에 녹아든다."""
    t = QTextBrowser()
    t.setObjectName("dashtext")
    t.setOpenExternalLinks(True)
    t.setFrameShape(QFrame.NoFrame)
    return t


class ShortcutTile(QToolButton):
    """바로가기 — 둥근 칸 아이콘 + 이름(플로우 첫 화면의 앱 아이콘 줄)."""

    def __init__(self, icon_name: str, text: str, parent=None):
        super().__init__(parent)
        self.setObjectName("dashtile")
        self._icon_name = icon_name
        self.setText(text)
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setIconSize(QSize(44, 44))
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(QSize(92, 82))
        self.apply_theme()

    def apply_theme(self) -> None:
        self.setIcon(navicons.tile_icon(self._icon_name, theme.c("primary"),
                                        theme.fill_text(), 44))


class DashGrid(QWidget):
    """카드 배치 — 넓으면 위 [할일(2칸) | 브리핑] / 아래 [일정 | 이번 주 | 다음 주],
    좁으면 위에서 아래로 한 줄에 하나."""

    def __init__(self, top: list, bottom: list, parent=None):
        super().__init__(parent)
        self._top, self._bottom = list(top), list(bottom)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(16)
        self._grid.setVerticalSpacing(16)
        self._wide = None
        for c in self._top + self._bottom:
            c.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.relayout(WIDE_MIN)

    @property
    def wide(self) -> bool:
        return bool(self._wide)

    def relayout(self, width: int) -> None:
        wide = width >= WIDE_MIN
        if wide == self._wide:
            return
        self._wide = wide
        g = self._grid
        for c in self._top + self._bottom:
            g.removeWidget(c)
        for i in range(6):
            g.setColumnStretch(i, 0)
            g.setRowStretch(i, 0)
        if wide:
            g.addWidget(self._top[0], 0, 0, 1, 2)
            g.addWidget(self._top[1], 0, 2)
            for i, c in enumerate(self._bottom):
                g.addWidget(c, 1, i)
            for i in range(3):
                g.setColumnStretch(i, 1)
            g.setRowStretch(0, 1)
            g.setRowStretch(1, 1)
        else:
            for i, c in enumerate(self._top + self._bottom):
                g.addWidget(c, i, 0)
                g.setRowStretch(i, 1)
            g.setColumnStretch(0, 1)

    def resizeEvent(self, ev):          # noqa: N802 — Qt 이름 그대로
        super().resizeEvent(ev)
        self.relayout(self.width())
