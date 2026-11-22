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

from PySide6.QtCore import QEvent, QSize, Qt
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


class AutoText(QTextBrowser):
    """카드 안의 글 칸 — 글 길이만큼 키가 자란다(v1.35).

    예전엔 카드 높이가 정해져 있어 브리핑이 길면 **카드 안에서 따로 스크롤**해야
    했다(바깥 화면도 스크롤이라 두 겹). 이제 글 칸이 글만큼 자라고, 화면 전체가
    한 번에 스크롤된다. 너무 긴 묶음은 'N건 더 보기' 로 접어 둔다(main_window).

    글 속 링크(브리핑의 고객·일정 이름)는 브라우저로 열지 않고 anchorClicked 로
    넘긴다 — 누르면 그 고객 창 · 일정으로 간다.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dashtext")
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # 링크는 밑줄 없이 — 글자색은 그리는 쪽(HTML)이 정한다
        self.document().setDefaultStyleSheet("a { text-decoration: none; }")
        self.document().documentLayout().documentSizeChanged.connect(self._fit)
        self.setFixedHeight(60)

    def _fit(self, *_a) -> None:
        h = int(self.document().size().height() + 0.99) + 2 * self.frameWidth() + 2
        h = max(40, h)
        if h != self.height():
            self.setFixedHeight(h)

    def wheelEvent(self, ev):            # noqa: N802 — 안에서 스크롤할 것이 없으니 바깥 화면이 받게
        ev.ignore()


def text_view() -> QTextBrowser:
    """카드 안의 글 칸 — 테두리 없이 카드에 녹아든다(키는 글만큼)."""
    return AutoText()


class RowActions(QWidget):
    """표의 줄에 마우스를 올리면 그 줄 오른쪽 끝에 뜨는 작은 단추 묶음(v1.35).

    '내 할일' 카드 머리에 [수정][삭제][완료][메모 복사][전체선택] 이 늘 늘어서 있어
    어수선했다. 이제 완료는 줄 앞 체크박스로, 나머지는 그 줄에 마우스를 올렸을
    때만 보인다. `actions` = [(글자, 풍선 도움말, 함수)] — 함수는 그 줄을 고른 뒤 부른다.
    """

    def __init__(self, table, actions: list, parent=None):
        super().__init__(parent or table.viewport())
        self.setObjectName("rowacts")
        self._table = table
        self._row = -1
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        self.buttons = []
        for text, tip, fn in actions:
            b = QToolButton()
            b.setObjectName("rowact")
            b.setText(text)
            b.setToolTip(tip)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c=False, f=fn: self._run(f))
            h.addWidget(b)
            self.buttons.append(b)
        self.hide()
        vp = table.viewport()
        vp.setMouseTracking(True)
        table.setMouseTracking(True)
        vp.installEventFilter(self)
        table.verticalScrollBar().valueChanged.connect(lambda _v: self._place(-1))

    @property
    def row(self) -> int:
        return self._row

    def _run(self, fn) -> None:
        r = self._row
        if r < 0 or r >= self._table.rowCount():
            return
        self._table.selectRow(r)
        fn()

    def _place(self, row: int) -> None:
        t = self._table
        if row < 0 or row >= t.rowCount():
            self._row = -1
            self.hide()
            return
        self._row = row
        self.adjustSize()
        rect = t.visualRect(t.model().index(row, 0))
        vp = t.viewport()
        x = max(0, vp.width() - self.width() - 6)
        y = rect.top() + max(0, (rect.height() - self.height()) // 2)
        self.move(x, y)
        self.show()
        self.raise_()

    def hover_at(self, pos) -> None:
        """뷰포트 좌표 pos 의 줄에 단추를 띄운다(검사에서도 부른다)."""
        if not self._table.viewport().rect().contains(pos):
            self._place(-1)
            return
        idx = self._table.indexAt(pos)
        self._place(idx.row() if idx.isValid() else -1)

    def eventFilter(self, obj, ev):      # noqa: N802
        et = ev.type()
        if et == QEvent.MouseMove:
            self.hover_at(ev.position().toPoint())
        elif et == QEvent.Leave:
            # 단추 위로 옮겨 간 것이면 그대로 둔다(단추는 뷰포트의 자식이라 Leave 가 온다)
            if not self.underMouse():
                self._place(-1)
        return False


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
