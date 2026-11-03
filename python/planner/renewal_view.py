"""만기 재계약 목록 화면(PC) — 고객관리 탭의 [재계약] (v1.26, renewals.py).

만기가 N개월 안에 오는(또는 막 지난) 고객을 급한 순으로. 줄마다 상태(미연락 → 연락함 →
상담중 → 재계약 / 안 함)와 [멘트 복사]. 위 줄에 '연락함 4 · 상담중 2 · 재계약 3(성공 60%)'.
고객을 두 번 누르면 opened(줄) — 고객 수정 창(보드와 같다).
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import auto_rules, renewals, theme

COLS = ["만기일", "남은 날", "고객", "차종", "금융사", "상태", "안내"]


def dday(left: int) -> str:
    return f"D-{left}" if left > 0 else ("오늘 만기" if left == 0 else f"{-left}일 지남")


class RenewalView(QWidget):
    status_changed = Signal(object, object, str)    # (고객 줄, 만기일, 새 상태)
    copy_requested = Signal(object, object)          # (고객 줄, 만기일)
    opened = Signal(int)                             # 시트 줄 번호
    months_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        top.addWidget(QLabel("만기"))
        self.cmb_months = QComboBox()
        for m in (1, 2, 3, 4, 6, 12):
            self.cmb_months.addItem(f"{m}개월 안", m)
        self.cmb_months.currentIndexChanged.connect(
            lambda _i: self.months_changed.emit(int(self.cmb_months.currentData() or 4)))
        top.addWidget(self.cmb_months)
        self.chk_hide = QCheckBox("재계약·안 함 숨기기")
        self.chk_hide.toggled.connect(lambda _on: self._paint())
        top.addWidget(self.chk_hide)
        top.addSpacing(12)
        self.lbl_sum = QLabel("")
        top.addWidget(self.lbl_sum, 1)
        v.addLayout(top)
        self.tbl = QTableWidget(0, len(COLS))
        self.tbl.setHorizontalHeaderLabels(COLS)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.verticalHeader().setDefaultSectionSize(40)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hh = self.tbl.horizontalHeader()
        for i, w in enumerate([110, 86, 220, 170, 130, 110, 110]):
            self.tbl.setColumnWidth(i, w)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        self.tbl.cellDoubleClicked.connect(self._dbl)
        v.addWidget(self.tbl, 1)
        self.lbl_hint = QLabel("만기가 다가오는 고객입니다. [멘트 복사] 로 안내 글을 복사해 카카오톡으로 "
                               "보내고, 상태를 바꿔 두세요(다른 PC·폰 알림에도 반영됩니다).")
        self.lbl_hint.setWordWrap(True)
        v.addWidget(self.lbl_hint)
        self._rows, self._store, self._today, self._months = [], {}, date.today(), 4
        self.items = []

    # ---- 채우기 ----
    def set_months(self, months: int) -> None:
        i = self.cmb_months.findData(int(months or 4))
        self.cmb_months.blockSignals(True)
        self.cmb_months.setCurrentIndex(i if i >= 0 else self.cmb_months.findData(4))
        self.cmb_months.blockSignals(False)
        self._months = int(self.cmb_months.currentData() or 4)

    def set_data(self, rows, store: dict, today: date | None = None, months: int | None = None) -> None:
        self._rows = list(rows or [])
        self._store = store if store is not None else {}
        self._today = today or date.today()
        if months:
            self.set_months(months)
        self._paint()

    def _paint(self) -> None:
        self._months = int(self.cmb_months.currentData() or self._months or 4)
        allx = renewals.targets(self._rows, self._today, self._months, self._store)
        c = renewals.counts(allx)
        rate = f" (성공률 {c['성공률']}%)" if c["성공률"] is not None else ""
        self.lbl_sum.setText(
            f"{self._months}개월 안 만기 {c['전체']}명 · 미연락 {c['미연락']} · 연락함 {c['연락함']} · "
            f"상담중 {c['상담중']} · 재계약 {c['재계약']} · 안 함 {c['안 함']}{rate}")
        self.items = [x for x in allx if not (self.chk_hide.isChecked() and x[3] in renewals.CLOSED)]
        t = self.tbl
        t.setRowCount(len(self.items))
        for r, (cr, d, left, st) in enumerate(self.items):
            vals = [f"{d:%Y-%m-%d}", dday(left), (cr.get("customer") or "").strip(),
                    (cr.get("model") or "").strip(), (cr.get("finance") or "").strip()]
            for ci, txt in enumerate(vals):
                it = QTableWidgetItem(txt)
                it.setData(Qt.UserRole, cr.row)
                if ci == 1:
                    tone = "red" if left <= 30 else ("orange" if left <= 60 else "")
                    if tone and st not in renewals.CLOSED:
                        it.setForeground(QColor(theme.strong(tone)))
                if st in renewals.CLOSED:
                    it.setForeground(QColor(theme.c("subtext")))
                t.setItem(r, ci, it)
            cmb = QComboBox()
            cmb.addItems(renewals.STATUSES)
            cmb.setCurrentText(st)
            cmb.currentTextChanged.connect(lambda s, cr=cr, d=d: self.status_changed.emit(cr, d, s))
            t.setCellWidget(r, 5, cmb)
            b = QPushButton("멘트 복사")
            b.setToolTip("이 고객의 이름·차종·금융사·만기일을 채운 안내 글을 복사합니다"
                         " (아직 '미연락' 이면 '연락함' 으로 바꿉니다)")
            b.clicked.connect(lambda _c=False, cr=cr, d=d: self.copy_requested.emit(cr, d))
            t.setCellWidget(r, 6, b)

    def _dbl(self, r: int, _c: int) -> None:
        it = self.tbl.item(r, 0)
        if it is not None and it.data(Qt.UserRole):
            self.opened.emit(int(it.data(Qt.UserRole)))

    # 시험용
    def row_of(self, name: str) -> int:
        for r, (cr, _d, _l, _s) in enumerate(self.items):
            if auto_rules.short_name(cr) == name or (cr.get("customer") or "").strip() == name:
                return r
        return -1
