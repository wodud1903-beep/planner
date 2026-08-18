"""차종별 수당율 관리 창 — 설정에서 연다.

수당율은 제조사 정책에 따라 수시로 바뀐다. 프로그램을 새로 받지 않고도
직접 고칠 수 있어야 해서 별도 창으로 뺐다.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from . import commission, config, theme


class _BrandTable(QWidget):
    def __init__(self, items: list, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)

        self.tbl = QTableWidget(0, 3)
        self.tbl.setHorizontalHeaderLabels(["차종", "수당율 (%)", "화물차"])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        hh = self.tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl.setColumnWidth(1, 110)
        self.tbl.setColumnWidth(2, 80)
        v.addWidget(self.tbl, 1)

        row = QHBoxLayout()
        b_add = QPushButton("차종 추가")
        b_add.clicked.connect(self.add_row)
        b_del = QPushButton("선택 삭제")
        b_del.clicked.connect(self.del_row)
        row.addWidget(b_add)
        row.addWidget(b_del)
        row.addStretch()
        v.addLayout(row)

        self.set_items(items)

    def set_items(self, items: list):
        self.tbl.setRowCount(0)
        for name, rate, truck in (items or []):
            self._append(name, rate, truck)

    def _append(self, name: str, rate: float, truck: bool):
        r = self.tbl.rowCount()
        self.tbl.insertRow(r)
        self.tbl.setItem(r, 0, QTableWidgetItem(str(name)))
        it = QTableWidgetItem(f"{float(rate):g}")
        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.tbl.setItem(r, 1, it)
        chk = QTableWidgetItem()
        chk.setFlags(chk.flags() | Qt.ItemIsUserCheckable)
        chk.setCheckState(Qt.Checked if truck else Qt.Unchecked)
        chk.setTextAlignment(Qt.AlignCenter)
        self.tbl.setItem(r, 2, chk)

    def add_row(self):
        self._append("새 차종", 5.0, False)
        self.tbl.scrollToBottom()
        self.tbl.setCurrentCell(self.tbl.rowCount() - 1, 0)
        self.tbl.editItem(self.tbl.item(self.tbl.rowCount() - 1, 0))

    def del_row(self):
        r = self.tbl.currentRow()
        if r >= 0:
            self.tbl.removeRow(r)

    def items(self) -> list:
        """(차종, 수당율, 화물여부) 목록. 이름이 없거나 숫자가 아니면 건너뛴다."""
        out = []
        for r in range(self.tbl.rowCount()):
            name = (self.tbl.item(r, 0).text() if self.tbl.item(r, 0) else "").strip()
            if not name:
                continue
            raw = (self.tbl.item(r, 1).text() if self.tbl.item(r, 1) else "").strip()
            try:
                rate = float(raw.replace("%", "").strip())
            except Exception:
                continue
            truck = (self.tbl.item(r, 2) is not None
                     and self.tbl.item(r, 2).checkState() == Qt.Checked)
            out.append((name, rate, truck))
        return out


class RateDialog(QDialog):
    """브랜드별 수당율 표를 고치는 창."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("차종별 수당율 관리")
        self.resize(620, 660)

        v = QVBoxLayout(self)
        lbl = QLabel(
            "수당율을 고치면 [수당계산기] 탭에 바로 반영됩니다.\n"
            "'화물차' 를 체크하면 공급가를 1.1 로, 아니면 1.1572 로 나눠 계산합니다.")
        lbl.setStyleSheet(f"color:{theme.c('subtext')};")
        v.addWidget(lbl)

        rates = commission.load_rates()
        self.tabs = QTabWidget()
        self.pages = {}
        for b in commission.BRANDS:
            pg = _BrandTable(rates.get(b, []))
            self.pages[b] = pg
            self.tabs.addTab(pg, commission.BRAND_NAMES[b])
        v.addWidget(self.tabs, 1)

        row = QHBoxLayout()
        b_reset = QPushButton("기본값으로 되돌리기")
        b_reset.clicked.connect(self._reset)
        row.addWidget(b_reset)
        row.addStretch()
        b_ok = QPushButton("저장")
        b_ok.setDefault(True)
        b_ok.clicked.connect(self._ok)
        b_cancel = QPushButton("취소")
        b_cancel.clicked.connect(self.reject)
        row.addWidget(b_ok)
        row.addWidget(b_cancel)
        v.addLayout(row)

    def _reset(self):
        if QMessageBox.question(
                self, config.APP_NAME,
                "직접 고친 내용을 버리고 기본 수당율로 되돌릴까요?") != QMessageBox.Yes:
            return
        d = commission.default_rates()
        for b, pg in self.pages.items():
            pg.set_items(d.get(b, []))

    def _ok(self):
        rates = {b: pg.items() for b, pg in self.pages.items()}
        empty = [commission.BRAND_NAMES[b] for b, v in rates.items() if not v]
        if empty:
            QMessageBox.information(
                self, config.APP_NAME,
                f"{' · '.join(empty)} 의 차종이 하나도 없습니다.\n"
                "최소 한 개는 남겨 주세요.")
            return
        commission.save_rates(rates)
        self.accept()
