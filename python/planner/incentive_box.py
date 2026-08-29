"""대리점 수당 미니계산기 — 고객 등록·수정 창에 붙는 한 줄짜리 계산기.

수당을 알려면 [수당계산기] 탭으로 옮겨 차량가를 다시 치고, 결과를 외워서
돌아와야 했다. 그 왕복을 없앤다.

  · 차량가는 위의 '차량가격' 칸을 그대로 쓴다(고치면 즉시 다시 계산).
  · 차종은 '차종' 칸에 친 글자로 자동 추천한다. 후보가 하나일 때만 고른다 —
    '그랜저 하이브리드' 처럼 가솔린/HEV 가 갈리는 건 앱이 임의로 정하면 안 된다.
  · 결과는 [적용] 을 눌러야 '대리점 수당' 칸에 들어간다. 자동으로 넣으면
    이미 적어 둔 실제 수당을 소리 없이 덮어쓴다.

계산은 수당계산기 탭과 **같은 함수·같은 수당율표**를 쓴다(commission.py).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout,
)

from . import commission, hangul, searchcombo, theme

PICK_NONE = "차종을 선택하세요"


def flat_rates() -> list:
    """[(표시이름, 차종, 수당율, 화물여부)] — 브랜드를 합친 한 목록."""
    out = []
    rates = commission.load_rates()
    for b in commission.BRANDS:
        bn = commission.BRAND_NAMES[b]
        for name, rate, truck in rates.get(b, []):
            out.append((f"{bn} · {name}", name, rate, truck))
    return out


# 시트에는 '하이브리드' 라고 적고 수당율 표에는 'HEV' 로 적혀 있다.
# 같은 말이라고 알려 주지 않으면 '팰리세이드 하이브리드' 가 아무것도 못 고른다.
_SYNONYMS = (
    ("하이브리드", "hev"), ("하브", "hev"),
    ("일렉트릭", "ev"), ("전기", "ev"),
    ("가솔린", "가솔린"), ("휘발유", "가솔린"),
)


def _norm(s: str) -> str:
    t = (s or "").lower()
    for a, b in _SYNONYMS:
        t = t.replace(a, b)
    return t


def guess(items: list, typed: str) -> int:
    """친 차종 글자로 표에서 하나를 고른다. 못 고르면 -1.

    '쏘나타 디 엣지' 처럼 표에 없는 세부 등급까지 적는 일이 흔하다. 그래서
    전체 → 앞 낱말만 순으로 줄여가며 찾고, **후보가 정확히 하나일 때만** 고른다.
    둘 이상이면 고르지 않는다 — 가솔린인지 HEV 인지를 앱이 임의로 정하면
    금액이 조용히 틀린다.
    """
    t = (typed or "").strip()
    if not t:
        return -1
    names = [_norm(name) for _lbl, name, _r, _tr in items]
    words = t.split()
    for n in range(len(words), 0, -1):
        q = _norm(" ".join(words[:n]))
        hits = [i for i, nm in enumerate(names) if hangul.matches(nm, q)]
        if len(hits) == 1:
            return hits[0]
    return -1


class IncentiveBox(QGroupBox):
    """차종·지급율·면세로 대리점 수당을 계산해 보여주고, [적용] 로 넘긴다."""

    applied = Signal(str)          # 적용할 금액(숫자만)

    def __init__(self, parent=None):
        super().__init__("대리점 수당 계산 (차량가격 칸을 기준으로 계산합니다)", parent)
        self.items = flat_rates()
        self._price = ""
        self._value = 0
        self._picked_by_user = False

        v = QVBoxLayout(self)
        v.setContentsMargins(10, 8, 10, 10)
        v.setSpacing(7)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.cmb = QComboBox()
        self.cmb.addItem(PICK_NONE, -1)
        for i, (label, _n, _r, _t) in enumerate(self.items):
            self.cmb.addItem(label, i)
        searchcombo.install(self.cmb)
        self.cmb.currentIndexChanged.connect(self._on_pick)
        row.addWidget(self.cmb, 3)

        row.addWidget(QLabel("지급율"))
        self.ed_pay = QLineEdit(str(int(commission.DEF_PAY_RATE)))
        self.ed_pay.setFixedWidth(52)
        self.ed_pay.setAlignment(Qt.AlignRight)
        self.ed_pay.textEdited.connect(lambda _t: self.recalc())
        row.addWidget(self.ed_pay)
        row.addWidget(QLabel("%"))

        self.chk_tax = QCheckBox("면세")
        self.chk_tax.toggled.connect(lambda _b: self.recalc())
        row.addWidget(self.chk_tax)
        v.addLayout(row)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self.lbl_rate = QLabel("")
        row2.addWidget(self.lbl_rate)
        row2.addStretch()
        self.lbl_result = QLabel("₩ 0")
        row2.addWidget(self.lbl_result)
        self.btn_apply = QPushButton("적용")
        self.btn_apply.setToolTip("계산된 금액을 [대리점 수당] 칸에 넣습니다.")
        self.btn_apply.clicked.connect(self._apply)
        row2.addWidget(self.btn_apply)
        v.addLayout(row2)

        self._on_pick()
        self.apply_theme()

    # ------------------------------------------------------------ 입력
    def set_price(self, digits: str) -> None:
        """'차량가격' 칸이 바뀌면 불린다(숫자만 들어온다)."""
        self._price = digits or ""
        self.recalc()

    def suggest_model(self, typed: str) -> None:
        """'차종' 칸이 바뀌면 불린다. 사용자가 직접 고른 뒤에는 건드리지 않는다."""
        if self._picked_by_user:
            return
        i = guess(self.items, typed)
        idx = self.cmb.findData(i) if i >= 0 else 0
        if idx < 0:
            idx = 0
        if idx != self.cmb.currentIndex():
            self.cmb.blockSignals(True)
            self.cmb.setCurrentIndex(idx)
            self.cmb.blockSignals(False)
            self._on_pick(auto=True)

    # ------------------------------------------------------------ 계산
    def _on_pick(self, *_a, auto: bool = False):
        if not auto and self.cmb.currentIndex() > 0:
            self._picked_by_user = True     # 직접 고른 뒤엔 자동 추천을 멈춘다
        i = self.cmb.currentData()
        if isinstance(i, int) and 0 <= i < len(self.items):
            _lbl, _name, self._rate, self._truck = self.items[i]
            self.lbl_rate.setText(
                f"수당율 {self._rate:g} %  ·  {'화물차' if self._truck else '승용차'} 기준")
        else:
            self._rate, self._truck = 0.0, False
            self.lbl_rate.setText("차종을 고르면 계산됩니다")
        self.recalc()

    def _num(self, ed: QLineEdit, default: float = 0.0) -> float:
        t = (ed.text() or "").replace(",", "").strip()
        try:
            return float(t)
        except Exception:
            return default

    def recalc(self):
        try:
            price = float(self._price or 0)
        except Exception:
            price = 0.0
        pay = self._num(self.ed_pay, commission.DEF_PAY_RATE)
        self._value = commission.calc(price, getattr(self, "_rate", 0.0),
                                      getattr(self, "_truck", False),
                                      pay, self.chk_tax.isChecked())
        self.lbl_result.setText(f"₩ {self._value:,}")
        self.btn_apply.setEnabled(self._value > 0)

    def value(self) -> int:
        return self._value

    def _apply(self):
        if self._value > 0:
            self.applied.emit(str(self._value))

    # ------------------------------------------------------------ 테마
    def apply_theme(self):
        self.lbl_rate.setStyleSheet(f"color:{theme.c('subtext')};")
        self.lbl_result.setStyleSheet(
            f"font-size:17px;font-weight:bold;color:{theme.c('status_bad')};")
