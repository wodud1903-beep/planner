"""수당계산기 탭 — 브랜드별로 차종·차량가를 넣으면 지급수수료를 계산한다."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

from . import commission, sheets, theme


class _BrandPage(QWidget):
    """브랜드 한 개(현대/기아)의 계산 화면."""

    def __init__(self, brand: str, parent=None):
        super().__init__(parent)
        self.brand = brand
        self.items: list = []

        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(10)

        gb = QGroupBox(f"{commission.BRAND_NAMES[brand]}  ·  3.3% 공제 후 수수료")
        form = QFormLayout(gb)
        form.setSpacing(10)

        self.cmb_car = QComboBox()
        self.cmb_car.currentIndexChanged.connect(self._on_car)
        form.addRow("차종", self.cmb_car)

        self.ed_price = QLineEdit()
        self.ed_price.setPlaceholderText("차량가를 입력하세요")
        self.ed_price.textEdited.connect(self._on_price_edited)
        form.addRow("차량가 (₩)", self.ed_price)

        self.ed_pay = QLineEdit(str(int(commission.DEF_PAY_RATE)))
        self.ed_pay.textEdited.connect(lambda _t: self.recalc())
        form.addRow("지급율 (%)", self.ed_pay)

        # 차종 수당율과 화물차 여부는 설정에서만 관리한다.
        # 계산할 때 실수로 건드리면 잘못된 금액이 나오므로 입력칸을 두지 않고,
        # 지금 적용된 값만 읽기 전용으로 보여준다.
        self.lbl_rate = QLabel("-")
        form.addRow("적용 수당율", self.lbl_rate)

        self.chk_tax = QCheckBox("면세 차량")
        self.chk_tax.toggled.connect(lambda _b: self.recalc())
        form.addRow("", self.chk_tax)
        v.addWidget(gb)

        self.lbl_result = QLabel("₩ 0")
        self.lbl_result.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_cap = QLabel("최종 지급수수료")
        row = QHBoxLayout()
        row.addWidget(self.lbl_cap)
        row.addStretch()
        row.addWidget(self.lbl_result)
        self.box_result = QGroupBox()
        self.box_result.setLayout(row)
        v.addWidget(self.box_result)

        row2 = QHBoxLayout()
        self.btn_copy = QPushButton("결과 복사")
        self.btn_copy.clicked.connect(self._copy)
        self.btn_reset = QPushButton("초기화")
        self.btn_reset.clicked.connect(self.reset)
        row2.addWidget(self.btn_copy)
        row2.addWidget(self.btn_reset)
        row2.addStretch()
        v.addLayout(row2)
        v.addStretch()

        self.apply_theme()

    # ---- 데이터 ----
    def set_items(self, items: list):
        """수당율 표를 반영 (설정에서 고치면 다시 불린다)."""
        cur = self.cmb_car.currentText()
        self.items = list(items or [])
        self.cmb_car.blockSignals(True)
        self.cmb_car.clear()
        self.cmb_car.addItem("차종을 선택하세요", -1)
        for i, (name, _r, _t) in enumerate(self.items):
            self.cmb_car.addItem(name, i)
        idx = self.cmb_car.findText(cur)
        self.cmb_car.setCurrentIndex(idx if idx > 0 else 0)
        self.cmb_car.blockSignals(False)
        self._on_car()

    def _on_car(self):
        i = self.cmb_car.currentData()
        if isinstance(i, int) and 0 <= i < len(self.items):
            _name, self._rate, self._truck = self.items[i]
            self.lbl_rate.setText(
                f"{self._rate:g} %   ({'화물차' if self._truck else '승용차'} 기준)")
        else:
            self._rate, self._truck = 0.0, False
            self.lbl_rate.setText("차종을 선택하세요")
        self.recalc()

    def _on_price_edited(self, _t: str):
        """입력하는 동안 1,000 단위로 보기 좋게 바꿔 준다."""
        txt = self.ed_price.text()
        at_end = self.ed_price.cursorPosition() >= len(txt)
        shown = sheets.fmt_money(txt)
        if shown != txt:
            self.ed_price.blockSignals(True)
            self.ed_price.setText(shown)
            self.ed_price.blockSignals(False)
            if at_end:
                self.ed_price.setCursorPosition(len(shown))
        self.recalc()

    def _num(self, ed: QLineEdit, default: float = 0.0) -> float:
        t = (ed.text() or "").replace(",", "").strip()
        try:
            return float(t)
        except Exception:
            return default

    def recalc(self):
        price = self._num(self.ed_price)
        pay = self._num(self.ed_pay, commission.DEF_PAY_RATE)
        won = commission.calc(price, getattr(self, "_rate", 0.0),
                              getattr(self, "_truck", False),
                              pay, self.chk_tax.isChecked())
        self.lbl_result.setText(f"₩ {won:,}")
        self._value = won

    def reset(self):
        self.ed_price.clear()
        self.ed_pay.setText(str(int(commission.DEF_PAY_RATE)))
        self.chk_tax.setChecked(False)
        self.cmb_car.setCurrentIndex(0)
        self.recalc()

    def _copy(self):
        QGuiApplication.clipboard().setText(str(getattr(self, "_value", 0)))
        self.lbl_cap.setText("최종 지급수수료  (복사했습니다)")

    def apply_theme(self):
        self.lbl_rate.setStyleSheet(f"color:{theme.c('subtext')};")
        self.lbl_result.setStyleSheet(
            f"font-size:24px;font-weight:bold;color:{theme.c('status_bad')};")
        self.lbl_cap.setStyleSheet(f"color:{theme.c('subtext')};")


class CommissionTab(QWidget):
    """현대 / 기아 두 브랜드를 탭으로."""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)

        self.tabs = QTabWidget()
        self.pages = {}
        for b in commission.BRANDS:
            pg = _BrandPage(b)
            self.pages[b] = pg
            self.tabs.addTab(pg, commission.BRAND_NAMES[b])
        v.addWidget(self.tabs, 1)

        self.lbl_hint = QLabel(
            "차종 수당율은 [설정] → [차종별 수당율 관리] 에서 고칠 수 있습니다.")
        v.addWidget(self.lbl_hint)

        self.reload_rates()
        self.apply_theme()

    def reload_rates(self):
        rates = commission.load_rates()
        for b, pg in self.pages.items():
            pg.set_items(rates.get(b, []))

    def apply_theme(self):
        self.lbl_hint.setStyleSheet(f"color:{theme.c('subtext')};")
        for pg in self.pages.values():
            pg.apply_theme()
