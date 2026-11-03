"""[월 마감] 창(v1.26, monthly.py) — 달을 골라 보고 [복사](카톡 보고) · [시트에 적기]."""

from __future__ import annotations

from datetime import date

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from . import monthly


class MonthlyDialog(QDialog):
    def __init__(self, rows, today: date | None = None, on_write=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("월 마감 리포트")
        self.resize(560, 620)
        self._rows = list(rows or [])
        self._on_write = on_write
        today = today or date.today()
        v = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("달"))
        self.cmb = QComboBox()
        y, m = today.year, today.month
        for _ in range(13):
            self.cmb.addItem(f"{y}년 {m}월" + (" (이번 달 — 아직 진행 중)" if (y, m) == (today.year, today.month)
                                               else ""), (y, m))
            y, m = monthly.prev_month(y, m)
        self.cmb.setCurrentIndex(1 if today.day <= 10 else 0)   # 월초엔 지난달부터
        self.cmb.currentIndexChanged.connect(lambda _i: self._paint())
        top.addWidget(self.cmb, 1)
        v.addLayout(top)
        self.txt = QPlainTextEdit()
        self.txt.setReadOnly(True)
        v.addWidget(self.txt, 1)
        self.lbl = QLabel("")
        self.lbl.setWordWrap(True)
        v.addWidget(self.lbl)
        row = QHBoxLayout()
        self.btn_copy = QPushButton("복사 (카톡 보고)")
        self.btn_copy.clicked.connect(self._copy)
        row.addWidget(self.btn_copy)
        self.btn_write = QPushButton("시트 '월마감' 탭에 적기")
        self.btn_write.setToolTip("고객 시트에 '월마감' 탭을 만들어(있으면 새로) 이 달의 표를 적습니다 — "
                                  "고객 줄이 있는 탭은 건드리지 않습니다")
        self.btn_write.clicked.connect(self._write)
        self.btn_write.setEnabled(on_write is not None)
        row.addWidget(self.btn_write)
        row.addStretch()
        b = QPushButton("닫기")
        b.clicked.connect(self.accept)
        row.addWidget(b)
        v.addLayout(row)
        self._paint()

    def month(self) -> tuple[int, int]:
        return tuple(self.cmb.currentData())

    def _paint(self) -> None:
        y, m = self.month()
        self.rep = monthly.report(self._rows, y, m)
        self.txt.setPlainText(monthly.render_text(self.rep) if self._rows
                              else "고객관리 시트를 읽은 뒤에 만들어집니다.")
        self.lbl.setText(f"{len(self._rows)}명으로 계산했습니다." if self._rows else "")

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.txt.toPlainText())
        self.lbl.setText("복사했습니다 — 카카오톡 보고방에 붙여 넣으세요.")

    def _write(self) -> None:
        if callable(self._on_write):
            self.lbl.setText("시트에 적는 중…")
            self._on_write(*self.month())

    def written(self, err: str = "") -> None:
        self.lbl.setText(("시트에 적지 못했습니다: " + err) if err
                         else f"시트의 '{monthly.TAB}' 탭에 적었습니다.")
