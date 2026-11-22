"""거르기 칩 줄 — '전체 12 · 심사중 2 · 가결 1 …' 처럼 눌러서 바로 거른다(v1.35).

고객관리의 진행현황, 자료검색의 분류가 같이 쓴다. 예전엔 고객은 검색칸뿐이었고
자료는 드롭다운을 열어 골라야 했다. 폰 웹은 이미 이 모양이다.

칩이 많아 한 줄에 안 들어가면 다음 줄로 넘긴다(FlowLayout).
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QLayout, QPushButton, QSizePolicy, QWidget


class FlowLayout(QLayout):
    """왼쪽부터 채우고 넘치면 다음 줄로 — Qt 예제의 흐름 배치를 줄인 것."""

    def __init__(self, parent=None, spacing: int = 6):
        super().__init__(parent)
        self._items = []
        self._sp = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):            # noqa: N802 — Qt 이름 그대로
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):                # noqa: N802
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):                # noqa: N802
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):      # noqa: N802
        return Qt.Orientations(0)

    def hasHeightForWidth(self):        # noqa: N802
        return True

    def heightForWidth(self, w):        # noqa: N802
        return self._do(QRect(0, 0, w, 0), test=True)

    def setGeometry(self, rect):        # noqa: N802
        super().setGeometry(rect)
        self._do(rect, test=False)

    def sizeHint(self):                 # noqa: N802
        return self.minimumSize()

    def minimumSize(self):              # noqa: N802
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return s + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do(self, rect: QRect, test: bool) -> int:
        x, y, line_h = rect.x(), rect.y(), 0
        for it in self._items:
            wid = it.widget()
            if wid is not None and wid.isHidden():
                continue
            hint = it.sizeHint()
            nx = x + hint.width() + self._sp
            if nx - self._sp > rect.right() + 1 and line_h > 0:
                x, y = rect.x(), y + line_h + self._sp
                nx = x + hint.width() + self._sp
                line_h = 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x = nx
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y()


class ChipBar(QWidget):
    """칩 줄. set_items([(키, 이름, 건수)]) — 첫 칩('' = 전체)은 늘 맨 앞에 둔다.

    picked(키) — 칩을 눌렀다. 같은 칩을 다시 누르면 '전체' 로 돌아간다."""

    picked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self._flow = FlowLayout(self)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._btns: dict = {}
        self._items: list = []
        self._current = ""

    @property
    def current(self) -> str:
        return self._current

    def buttons(self) -> dict:
        return dict(self._btns)

    def texts(self) -> list:
        return [b.text() for b in self._btns.values()]

    def set_items(self, items: list, all_label: str = "전체") -> None:
        """items = [(키, 이름, 건수 또는 None)] — 같은 키·이름이면 단추를 다시 만들지 않는다."""
        total = sum(n for _k, _n, n in items if isinstance(n, int))
        full = [("", all_label, total if any(isinstance(n, int) for _k, _l, n in items) else None)]
        full += [(k, lb, n) for k, lb, n in items if k != ""]
        keys = [(k, lb) for k, lb, _n in full]
        if keys != [(k, b.property("chipLabel")) for k, b in self._btns.items()]:
            for b in list(self._btns.values()):
                self._group.removeButton(b)
                self._flow.removeWidget(b)
                b.hide()
                b.setParent(None)
                b.deleteLater()
            self._btns = {}
            for k, lb, _n in full:
                b = QPushButton(lb)
                b.setObjectName("chip")
                b.setCheckable(True)
                b.setCursor(Qt.PointingHandCursor)
                b.setProperty("chipLabel", lb)
                b.clicked.connect(lambda _c=False, key=k: self._click(key))
                self._group.addButton(b)
                self._flow.addWidget(b)
                self._btns[k] = b
        for k, lb, n in full:
            self._btns[k].setText(lb if n is None else f"{lb} {n}")
        if self._current not in self._btns:
            self._current = ""
        self._btns[self._current].setChecked(True)
        self._items = full
        self.updateGeometry()

    def set_current(self, key: str, emit: bool = False) -> None:
        if key not in self._btns:
            key = ""
        self._current = key
        if key in self._btns:
            self._btns[key].setChecked(True)
        if emit:
            self.picked.emit(key)

    def _click(self, key: str) -> None:
        if key == self._current and key != "":
            key = ""                     # 같은 칩을 다시 누르면 전체로
        self.set_current(key, emit=True)

    def hasHeightForWidth(self):        # noqa: N802
        return True

    def heightForWidth(self, w):        # noqa: N802
        return self._flow.heightForWidth(w)

    def sizeHint(self):                 # noqa: N802
        w = max(200, self.width())
        return QSize(w, self._flow.heightForWidth(w))
