"""왼쪽 메뉴(사이드바) — 플로우처럼 모든 메뉴를 왼쪽 한 줄에.

예전에는 위쪽에 가로 탭 7개가 있었고, [설정]·[캘린더 열기] 같은 전체 기능은
'일정 / 할일' 탭의 단추 줄에 섞여 있었다. 이제 한곳에 모은다:

    머리      앱 이름 + 로그인한 계정
    주 단추   [＋ 할일 추가] — 어느 화면에서든 바로
    메뉴      탭과 1:1. 끌어서 순서를 바꾼다(그 순서는 설정에 남아 다른 PC 도 같다)
    바로가기  [캘린더] [설정]
    바닥      버전(누르면 변경 이력) · PC 시작 시 실행 · 접기

**화면(탭) 자체는 main_window 의 QTabWidget 그대로다.** 탭 막대만 숨기고 이 메뉴가
대신 고른다 — 그래서 '해당 일정으로 이동' 처럼 탭으로 찾아가는 코드는 손대지 않는다.
기능이 늘면 탭을 하나 더하고 navicons.TAB_ICONS 에 아이콘 한 줄이면 메뉴에 붙는다.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFrame, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QVBoxLayout,
)

from . import navicons, theme
from .icon import make_icon


class NavList(QListWidget):
    """메뉴 목록 — 끌어서 순서를 바꾸면 이름 순서를 알린다."""

    orderChanged = Signal(list)
    ROW_H = 40

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("navlist")
        self.setIconSize(QSize(20, 20))
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setUniformItemSizes(True)
        self.setCursor(Qt.PointingHandCursor)

    def names(self) -> list:
        return [self.item(i).data(Qt.UserRole) for i in range(self.count())]

    def dropEvent(self, ev):            # noqa: N802 — Qt 이름 그대로
        # ⚠️ 옮기는 도중에 '지금 줄' 이 잠깐씩 바뀐다. 그때마다 화면을 바꾸면 엉뚱한
        #    화면으로 건너뛴다 — 옮기는 동안은 입을 막고, 끝난 뒤 순서만 알린다.
        #    (어느 줄을 고를지는 받는 쪽이 탭을 옮긴 뒤 다시 맞춘다)
        before = self.names()
        self.blockSignals(True)
        try:
            super().dropEvent(ev)
        finally:
            self.blockSignals(False)
        if self.names() != before:
            self.orderChanged.emit(self.names())

    def move_row(self, src: int, dst: int) -> None:
        """끌어 놓기와 같은 일을 코드로(검사·단축키용)."""
        if src == dst or not (0 <= src < self.count()) or not (0 <= dst < self.count()):
            return
        self.blockSignals(True)
        try:
            self.insertItem(dst, self.takeItem(src))
        finally:
            self.blockSignals(False)
        self.orderChanged.emit(self.names())


class Sidebar(QFrame):
    navigate = Signal(int)              # 메뉴에서 고른 줄(= 탭 번호)
    collapsedChanged = Signal(bool)

    W_OPEN = 216
    W_SHUT = 64

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self._collapsed = False
        self._pages: list = []          # [(이름, 아이콘 이름)]

        v = QVBoxLayout(self)
        v.setContentsMargins(12, 16, 12, 12)
        v.setSpacing(4)

        head = QHBoxLayout()
        head.setContentsMargins(4, 0, 0, 0)
        head.setSpacing(9)
        self.lbl_logo = QLabel()
        self.lbl_logo.setPixmap(make_icon().pixmap(28, 28))
        self.lbl_logo.setFixedSize(28, 28)
        head.addWidget(self.lbl_logo)
        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("sidetitle")
        head.addWidget(self.lbl_title, 1)
        v.addLayout(head)

        self.lbl_account = QLabel("")
        self.lbl_account.setObjectName("sideaccount")
        self.lbl_account.setWordWrap(True)
        self.lbl_account.setContentsMargins(4, 2, 0, 0)
        v.addWidget(self.lbl_account)
        v.addSpacing(12)

        self.btn_primary = QPushButton("할일 추가")
        self.btn_primary.setObjectName("sideprimary")
        self.btn_primary.setCursor(Qt.PointingHandCursor)
        self.btn_primary.setIconSize(QSize(18, 18))
        self.btn_primary.setToolTip("어느 화면에서든 바로 할일을 적습니다")
        v.addWidget(self.btn_primary)
        v.addSpacing(12)

        self.lbl_menu = QLabel("메뉴")
        self.lbl_menu.setObjectName("sidecaption")
        v.addWidget(self.lbl_menu)
        self.nav = NavList()
        self.nav.setToolTip("끌어서 순서를 바꿀 수 있습니다")
        self.nav.currentRowChanged.connect(self._on_row)
        v.addWidget(self.nav)
        v.addStretch(1)

        line = QFrame()
        line.setObjectName("sideline")
        v.addWidget(line)
        v.addSpacing(4)
        self.btn_calendar = self._side_button("캘린더", "calendar",
                                              "달력 창을 엽니다 — 일정 보기·추가·수정")
        v.addWidget(self.btn_calendar)
        self.btn_settings = self._side_button("설정", "gear",
                                              "구글 연결·알람·단축키·테마 등")
        v.addWidget(self.btn_settings)
        v.addSpacing(6)

        foot = QHBoxLayout()
        foot.setContentsMargins(0, 0, 0, 0)
        foot.setSpacing(2)
        self.btn_ver = QPushButton("")
        self.btn_ver.setObjectName("sidesmall")
        self.btn_ver.setCursor(Qt.PointingHandCursor)
        foot.addWidget(self.btn_ver)
        foot.addStretch(1)
        self.btn_fold = QPushButton("")
        self.btn_fold.setObjectName("sidesmall")
        self.btn_fold.setCursor(Qt.PointingHandCursor)
        self.btn_fold.setIconSize(QSize(16, 16))
        self.btn_fold.clicked.connect(lambda: self.set_collapsed(not self._collapsed))
        foot.addWidget(self.btn_fold)
        v.addLayout(foot)
        self.chk_startup = QCheckBox("PC 시작 시 실행")
        self.chk_startup.setObjectName("sidecheck")
        v.addWidget(self.chk_startup)

        self.setFixedWidth(self.W_OPEN)
        self.apply_theme()

    # ---- 만들기 ----
    def _side_button(self, text: str, icon_name: str, tip: str) -> QPushButton:
        b = QPushButton(text)
        b.setObjectName("sidebtn")
        b.setCursor(Qt.PointingHandCursor)
        b.setIconSize(QSize(20, 20))
        b.setToolTip(tip)
        b.setProperty("full_text", text)
        b.setProperty("icon_name", icon_name)
        return b

    # ---- 메뉴 ----
    def set_pages(self, pages: list, current: int = 0) -> None:
        """메뉴를 탭 순서대로 다시 채운다. pages = [(이름, 아이콘 이름)]."""
        self._pages = list(pages)
        normal, sel = theme.c("subtext"), theme.c("nav_sel_text")
        self.nav.blockSignals(True)
        try:
            self.nav.clear()
            for name, icon_name in self._pages:
                it = QListWidgetItem(navicons.icon(icon_name, normal, sel),
                                     "" if self._collapsed else name)
                it.setData(Qt.UserRole, name)
                it.setToolTip(name)
                it.setSizeHint(QSize(0, NavList.ROW_H))
                self.nav.addItem(it)
            if 0 <= current < self.nav.count():
                self.nav.setCurrentRow(current)
        finally:
            self.nav.blockSignals(False)
        # 줄 수만큼만 높이를 잡는다 — 남는 자리는 아래 바로가기 쪽 여백이 된다
        self.nav.setFixedHeight(max(1, self.nav.count()) * (NavList.ROW_H + 2) + 4)

    def select(self, row: int) -> None:
        """탭이 코드로 바뀌었을 때 메뉴 표시만 따라간다(다시 알리지 않는다)."""
        if self.nav.currentRow() == row:
            return
        self.nav.blockSignals(True)
        try:
            self.nav.setCurrentRow(row)
        finally:
            self.nav.blockSignals(False)

    def _on_row(self, row: int) -> None:
        if row >= 0:
            self.navigate.emit(row)

    # ---- 접기 ----
    def is_collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, on: bool) -> None:
        on = bool(on)
        changed = on != self._collapsed
        self._collapsed = on
        self.setFixedWidth(self.W_SHUT if on else self.W_OPEN)
        for w in (self.lbl_title, self.lbl_account, self.lbl_menu,
                  self.btn_ver, self.chk_startup):
            w.setVisible(not on)
        self.btn_primary.setText("" if on else "할일 추가")
        for b in (self.btn_calendar, self.btn_settings):
            b.setText("" if on else b.property("full_text"))
        for i in range(self.nav.count()):
            it = self.nav.item(i)
            it.setText("" if on else it.data(Qt.UserRole))
        self.btn_fold.setToolTip("메뉴 펼치기" if on else "메뉴 접기 — 아이콘만 남깁니다")
        self._paint_icons()
        if changed:
            self.collapsedChanged.emit(on)

    # ---- 테마 ----
    def _paint_icons(self) -> None:
        normal = theme.c("topbar_text")
        self.btn_primary.setIcon(navicons.icon("plus", theme.fill_text()))
        for b in (self.btn_calendar, self.btn_settings):
            b.setIcon(navicons.icon(b.property("icon_name"), normal))
        self.btn_fold.setIcon(navicons.icon(
            "expand" if self._collapsed else "collapse", theme.c("subtext"), size=16))

    def apply_theme(self) -> None:
        self._paint_icons()
        if self._pages:
            self.set_pages(self._pages, self.nav.currentRow())
