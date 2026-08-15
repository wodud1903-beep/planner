"""고객 등록/수정 대화상자 (구글 시트 '미출고차량' 연동).

직접기재 항목만 입력받는다. 수식으로 자동 계산되는 항목
(순번·합계·고객센터 번호·사고접수연락처·고객안내멘트)은 안내만 하고
프로그램이 건드리지 않는다.

금융사·특판/대리점·진행현황·출고유형·등록완료는 콤보박스로 제공하되,
후보 목록은 **기존 시트 데이터에서 뽑아** 쓴다(값을 코드에 박지 않는다).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QTextEdit, QVBoxLayout, QWidget,
)

from . import config, sheets


class CustomerDialog(QDialog):
    #  key            라벨            위젯종류
    #  ("combo" 는 기존 값 후보를 넣고 직접 입력도 가능하게 editable)
    LAYOUT = [
        ("customer", "고객명 / 사업자", "line"),
        ("finance", "금융사", "combo"),
        ("model", "차종", "line"),
        ("price", "차량가격", "line"),
        ("fee", "금융수수료", "line"),
        ("incentive", "대리점 수당", "line"),
        ("channel", "특판 / 대리점", "combo"),
        ("contract_date", "계약일(발주)", "line"),
        ("deliver_date", "출고일", "line"),
        ("status", "진행현황", "combo"),
        ("terms", "계약조건", "text"),
        ("note", "내용", "text"),
        ("kind", "출고유형", "combo"),
        ("doc", "견적서/계약서", "line"),
        ("registered", "등록완료", "combo"),
    ]

    def __init__(self, caption: str, values: dict, choices: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(caption)
        self.resize(560, 720)
        self.widgets: dict = {}

        root = QVBoxLayout(self)

        # 스크롤 영역 (항목이 많아 작은 화면에서도 잘리지 않게)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        # 스타일시트 배경이 확실히 칠해지도록 (설정창과 동일한 패턴)
        inner.setObjectName("dlgbody")
        inner.setAttribute(Qt.WA_StyledBackground, True)
        form = QFormLayout(inner)

        for key, label, kind in self.LAYOUT:
            cur = (values or {}).get(key, "")
            if kind == "combo":
                w = QComboBox()
                w.setEditable(True)          # 목록에 없는 값도 직접 입력 가능
                items = (choices or {}).get(key, [])
                w.addItem("")
                for it in items:
                    w.addItem(it)
                w.setCurrentText(cur)
            elif kind == "text":
                w = QTextEdit()
                w.setMinimumHeight(64)
                w.setPlainText(cur)
            else:
                w = QLineEdit()
                w.setText(cur)
            self.widgets[key] = (w, kind)
            form.addRow(label, w)

        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        # 자동 계산 안내
        gb = QGroupBox("자동 계산 (시트 수식 — 프로그램이 입력하지 않음)")
        gl = QVBoxLayout(gb)
        gl.addWidget(QLabel(" · " + "   · ".join(sheets.FORMULA_NAMES)))
        root.addWidget(gb)

        row = QHBoxLayout()
        row.addStretch()
        ok = QPushButton("저장")
        ok.setDefault(True)
        ok.clicked.connect(self._ok)
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.reject)
        row.addWidget(ok)
        row.addWidget(cancel)
        root.addLayout(row)

    def _ok(self):
        if not self.values().get("customer", "").strip():
            QMessageBox.information(self, config.APP_NAME, "고객명을 입력하세요.")
            return
        self.accept()

    def values(self) -> dict:
        out = {}
        for key, (w, kind) in self.widgets.items():
            if kind == "combo":
                out[key] = w.currentText().strip()
            elif kind == "text":
                out[key] = w.toPlainText().strip()
            else:
                out[key] = w.text().strip()
        return out

    @classmethod
    def run(cls, caption: str, values: dict, choices: dict, parent=None):
        d = cls(caption, values, choices, parent)
        if d.exec() != QDialog.Accepted:
            return None
        return d.values()
