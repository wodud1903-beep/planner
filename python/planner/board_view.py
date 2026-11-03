"""고객 진행 보드 화면(PC) — 고객관리 탭의 [보드].

칸 = 진행현황 값(board.columns). 카드를 끌어 다른 칸에 놓으면 moved(줄, 진행현황)
신호를 낸다 — 시트에 쓰는 일은 main_window 가 기존 '고객 고치기' 길로 한다
(쓰기 직전에 그 줄에 같은 고객이 있는지 확인하는 길).
카드를 두 번 누르면 opened(줄) — 고객 수정 창.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFrame, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QScrollArea, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget,
)

from . import board, theme

ROW = Qt.UserRole
CARD = Qt.UserRole + 1
COL_W = 248


class CardDelegate(QStyledItemDelegate):
    """카드 한 장 — 흰 둥근 상자에 이름(굵게) · 금융사·차종 · 알림 한 줄."""

    H = 78

    def sizeHint(self, option, index):
        return QSize(COL_W - 24, self.H)

    def paint(self, p: QPainter, option, index):
        c = index.data(CARD) or {}
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = option.rect.adjusted(2, 3, -2, -3)
        sel = bool(option.state & QStyle.State_Selected)
        p.setPen(QPen(QColor(theme.c("accent") if sel else theme.c("border")), 1.2 if sel else 1))
        p.setBrush(QColor(theme.c("panel_bg")))
        p.drawRoundedRect(r, 10, 10)
        x, w = r.x() + 12, r.width() - 24
        f = QFont(option.font)
        f.setBold(True)
        f.setPointSizeF(max(9.5, option.font.pointSizeF() + 0.5))
        p.setFont(f)
        p.setPen(QColor(theme.c("text")))
        p.drawText(QRect(x, r.y() + 8, w, 22), Qt.AlignLeft | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(c.get("name", ""), Qt.ElideRight, w))
        f2 = QFont(option.font)
        f2.setPointSizeF(max(8.5, option.font.pointSizeF() - 0.5))
        p.setFont(f2)
        p.setPen(QColor(theme.c("subtext")))
        p.drawText(QRect(x, r.y() + 30, w, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(c.get("sub", ""), Qt.ElideRight, w))
        chip = c.get("chip", "")
        if chip:
            tone = c.get("tone", "")
            p.setPen(QColor(theme.strong(tone) if tone else theme.c("subtext")))
            if tone:
                f3 = QFont(f2)
                f3.setBold(True)
                p.setFont(f3)
            p.drawText(QRect(x, r.y() + 48, w, 18), Qt.AlignLeft | Qt.AlignVCenter, chip)
        p.restore()


class BoardList(QListWidget):
    """한 칸. 다른 칸의 카드를 받으면 dropped(줄, 이 칸의 진행현황)."""

    dropped = Signal(int, str)
    opened = Signal(int)

    def __init__(self, status: str, parent=None):
        super().__init__(parent)
        self.status = status
        self.setItemDelegate(CardDelegate(self))
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setSpacing(2)
        self.setObjectName("boardlist")
        self.itemDoubleClicked.connect(lambda it: self.opened.emit(int(it.data(ROW))))

    def dragEnterEvent(self, e):
        if isinstance(e.source(), BoardList):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if isinstance(e.source(), BoardList) and e.source() is not self:
            e.acceptProposedAction()
        else:
            e.ignore()

    def dropEvent(self, e):
        src = e.source()
        if not isinstance(src, BoardList) or src is self:
            e.ignore()
            return
        it = src.currentItem()
        if it is None:
            e.ignore()
            return
        # ⚠️ Qt 가 카드를 직접 옮기게 두지 않는다(CopyAction) — 시트에 쓰고 나서 보드를
        #    통째로 다시 그린다. 못 쓰면 원래 칸에 그대로 남아 있어야 한다.
        e.setDropAction(Qt.CopyAction)
        e.accept()
        self.dropped.emit(int(it.data(ROW)), self.status)


class BoardView(QWidget):
    moved = Signal(int, str)      # (줄, 새 진행현황)
    opened = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.lbl_hint = QLabel("카드를 끌어 다른 칸에 놓으면 시트의 진행현황이 바뀝니다 · "
                               "두 번 누르면 수정")
        self.lbl_hint.setStyleSheet(f"color:{theme.c('subtext')};")
        top.addWidget(self.lbl_hint)
        top.addStretch(1)
        self.chk_cancel = QCheckBox("취소·부결도 보기")
        self.chk_cancel.toggled.connect(lambda _on: self.set_rows(self._rows, self._today))
        top.addWidget(self.chk_cancel)
        v.addLayout(top)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.inner = QWidget()
        self.cols = QHBoxLayout(self.inner)
        self.cols.setContentsMargins(0, 4, 0, 4)
        self.cols.setSpacing(12)
        self.scroll.setWidget(self.inner)
        v.addWidget(self.scroll, 1)
        self._rows: list = []
        self._today = date.today()
        self.lists: list[BoardList] = []

    def set_rows(self, rows: list, today: date | None = None):
        self._rows = list(rows or [])
        self._today = today or date.today()
        while self.cols.count():
            it = self.cols.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.lists = []
        data = board.columns(self._rows, self._today, self.chk_cancel.isChecked())
        for col in data:
            self.cols.addWidget(self._column(col))
        if not data:
            lb = QLabel("고객관리 시트를 불러오면 진행현황별로 고객이 놓입니다.")
            lb.setStyleSheet(f"color:{theme.c('subtext')};")
            self.cols.addWidget(lb)
        self.cols.addStretch(1)

    def _column(self, col: dict) -> QWidget:
        fr = QFrame()
        fr.setObjectName("boardcol")
        fr.setFixedWidth(COL_W)
        fr.setStyleSheet(f"QFrame#boardcol {{ background:{theme.c('tab_bg')}; border-radius:12px; }}"
                         "QListWidget#boardlist { background: transparent; border: 0; }")
        v = QVBoxLayout(fr)
        v.setContentsMargins(10, 10, 10, 8)
        v.setSpacing(6)
        head = QHBoxLayout()
        title = QLabel(col["status"])
        title.setStyleSheet("font-weight:bold;font-size:11pt;")
        head.addWidget(title)
        n = QLabel(f"{col['count']}")
        n.setStyleSheet(f"color:{theme.c('subtext')};background:{theme.c('panel_bg')};"
                        "border-radius:9px;padding:1px 8px;")
        head.addWidget(n)
        head.addStretch(1)
        v.addLayout(head)
        lst = BoardList(col["status"])
        for c in col["cards"]:
            it = QListWidgetItem(c["name"])
            it.setData(ROW, c["row"])
            it.setData(CARD, c)
            it.setToolTip(" · ".join(x for x in (c["name"], c["sub"], c["chip"]) if x))
            lst.addItem(it)
        lst.dropped.connect(self._on_drop)
        lst.opened.connect(self.opened.emit)
        v.addWidget(lst, 1)
        if col.get("more"):
            more = QLabel(f"지난 출고 {col['more']}건은 목록에서")
            more.setStyleSheet(f"color:{theme.c('subtext')};font-size:9pt;")
            v.addWidget(more)
        self.lists.append(lst)
        return fr

    def _on_drop(self, row: int, status: str):
        if status == board.NO_STATUS:
            status = ""             # '진행현황 없음' 칸에 놓으면 비운다
        self.moved.emit(row, status)
