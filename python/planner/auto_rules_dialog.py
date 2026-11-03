"""[자동 규칙] 편집 창(v1.26, auto_rules.py).

왼쪽 규칙 목록 · 오른쪽 고치기. 규칙 하나 =
  언제(진행현황이 바뀌면 / 출고일 기준 / 만기일 기준) · 진행현황 말 · 며칠(앞은 −) ·
  할일 제목 · 멘트(고객에게 보낼 글 — {고객} {차종} {금융사} {출고일} {만기일} {계약일} 이 채워진다)
"""

from __future__ import annotations

import uuid

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
    QSpinBox, QVBoxLayout, QWidget,
)

from . import auto_rules, config

HELP = ("멘트에 {고객} {차종} {금융사} {출고일} {만기일} {계약일} 을 쓰면 그 고객 것으로 채워집니다.\n"
        "할일은 [내 할일] 에 멘트와 함께 생기고, 알람 시각은 팔로업과 같습니다(설정).\n"
        "한 고객에 같은 규칙은 한 번만 — 지운 할일은 다시 만들지 않습니다.")


class AutoRulesDialog(QDialog):
    def __init__(self, rules: list, on: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("자동 규칙 — 진행현황·날짜가 바뀌면 할일이 저절로")
        self.resize(900, 560)
        self.rules = [dict(r) for r in rules]
        self._cur = -1
        v = QVBoxLayout(self)
        self.chk_on = QCheckBox("자동 규칙 쓰기 (고객 시트를 새로 읽을 때마다 확인합니다)")
        self.chk_on.setChecked(on)
        v.addWidget(self.chk_on)
        body = QHBoxLayout()
        left = QVBoxLayout()
        self.lst = QListWidget()
        self.lst.currentRowChanged.connect(self._pick)
        left.addWidget(self.lst, 1)
        row = QHBoxLayout()
        b_add = QPushButton("규칙 추가")
        b_add.clicked.connect(self._add)
        b_del = QPushButton("삭제")
        b_del.clicked.connect(self._del)
        b_def = QPushButton("기본값으로")
        b_def.clicked.connect(self._defaults)
        for b in (b_add, b_del, b_def):
            row.addWidget(b)
        left.addLayout(row)
        body.addLayout(left, 2)

        self.form = QWidget()
        f = QFormLayout(self.form)
        self.chk_rule = QCheckBox("이 규칙 쓰기")
        f.addRow(self.chk_rule)
        self.cmb_kind = QComboBox()
        for k, label in auto_rules.KINDS.items():
            self.cmb_kind.addItem(label, k)
        f.addRow("언제", self.cmb_kind)
        self.ed_word = QLineEdit()
        self.ed_word.setPlaceholderText("예: 가결, 승인  (쉼표로 여럿 — 하나라도 새로 들어가면)")
        f.addRow("진행현황 말", self.ed_word)
        self.sp_days = QSpinBox()
        self.sp_days.setRange(-365, 365)
        self.sp_days.setSuffix(" 일")
        self.sp_days.setToolTip("기준일에서 며칠 뒤(앞이면 −). 진행현황 규칙은 바뀐 날 기준")
        f.addRow("며칠 뒤(앞은 −)", self.sp_days)
        self.ed_title = QLineEdit()
        f.addRow("할일 제목", self.ed_title)
        self.ed_ment = QPlainTextEdit()
        self.ed_ment.setMinimumHeight(160)
        f.addRow("멘트", self.ed_ment)
        hl = QLabel(HELP)
        hl.setWordWrap(True)
        f.addRow(hl)
        body.addWidget(self.form, 3)
        v.addLayout(body, 1)
        self.cmb_kind.currentIndexChanged.connect(self._kind_changed)
        for w in (self.chk_rule,):
            w.toggled.connect(lambda _x: self._stash())
        for w in (self.ed_word, self.ed_title):
            w.textEdited.connect(lambda _x: self._stash())
        self.sp_days.valueChanged.connect(lambda _x: self._stash())
        self.ed_ment.textChanged.connect(self._stash)

        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Save).setText("저장")
        bb.button(QDialogButtonBox.Cancel).setText("취소")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self._fill()

    # ---- 목록 ----
    def _fill(self, keep: int = 0) -> None:
        self.lst.blockSignals(True)
        self.lst.clear()
        for r in self.rules:
            it = QListWidgetItem(("✓ " if r.get("on", True) else "✗ ") + auto_rules.describe(r))
            self.lst.addItem(it)
        self.lst.blockSignals(False)
        self._cur = -1
        if self.rules:
            self.lst.setCurrentRow(max(0, min(keep, len(self.rules) - 1)))
        self.form.setEnabled(bool(self.rules))

    def _pick(self, row: int) -> None:
        self._cur = -1                      # 채우는 동안 _stash 가 덮지 않게
        if not (0 <= row < len(self.rules)):
            return
        r = self.rules[row]
        self.chk_rule.setChecked(bool(r.get("on", True)))
        i = self.cmb_kind.findData(r.get("kind"))
        self.cmb_kind.setCurrentIndex(max(0, i))
        self.ed_word.setText(r.get("word", ""))
        self.sp_days.setValue(int(r.get("days") or 0))
        self.ed_title.setText(r.get("title", ""))
        self.ed_ment.setPlainText(r.get("ment", ""))
        self._cur = row
        self._kind_changed()

    def _kind_changed(self, *_a) -> None:
        self.ed_word.setEnabled(self.cmb_kind.currentData() == "status")
        self._stash()

    def _stash(self) -> None:
        if not (0 <= self._cur < len(self.rules)):
            return
        r = self.rules[self._cur]
        r.update({"on": self.chk_rule.isChecked(), "kind": self.cmb_kind.currentData(),
                  "word": self.ed_word.text().strip(), "days": self.sp_days.value(),
                  "title": self.ed_title.text().strip(), "ment": self.ed_ment.toPlainText()})
        it = self.lst.item(self._cur)
        if it is not None:
            it.setText(("✓ " if r["on"] else "✗ ") + auto_rules.describe(r))

    def _add(self) -> None:
        self.rules.append({"id": "r" + uuid.uuid4().hex[:8], "on": True, "kind": "status",
                           "word": "", "days": 0, "title": "[할일] {고객}", "ment": ""})
        self._fill(len(self.rules) - 1)

    def _del(self) -> None:
        row = self.lst.currentRow()
        if not (0 <= row < len(self.rules)):
            return
        if QMessageBox.question(self, config.APP_NAME, "이 규칙을 지울까요?\n(이미 만든 할일은 그대로 둡니다)") \
                != QMessageBox.Yes:
            return
        self.rules.pop(row)
        self._fill(row)

    def _defaults(self) -> None:
        if QMessageBox.question(self, config.APP_NAME, "규칙을 처음 기본값으로 되돌릴까요?") != QMessageBox.Yes:
            return
        self.rules = [dict(r) for r in auto_rules.DEFAULT_RULES]
        self._fill()

    def result_rules(self) -> list:
        return [r for r in (auto_rules.clean_rule(x) for x in self.rules) if r]

    @classmethod
    def run(cls, rules: list, on: bool, parent=None):
        d = cls(rules, on, parent)
        if d.exec() != QDialog.Accepted:
            return None
        return d.result_rules(), d.chk_on.isChecked()
