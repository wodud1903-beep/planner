"""멘트복사 탭의 '고객 안내 문구' 묶음(v1.35 — 지점장이 고른 M2).

예전엔 복사하는 글이 여기저기 흩어져 있었다.
  · 인삿말(상담후·부재중)          — 멘트복사 탭
  · 고객 안내멘트(출고 안내)        — 고객관리 표의 [복사] (시트 R열 수식이 만든다)
  · 출고 1개월 안내멘트             — 대시보드 단추 · 글은 [설정] → [알림·일정]
  · 재계약 안내멘트                 — 고객관리 [재계약] 의 [멘트 복사] · 글은 고칠 수 없었다
이제 멘트복사 탭 아래에 모아 **보고(미리보기) · 고치고 · 복사**한다. 고객 이름이 들어가는
글은 [고객 골라 복사] 로 고객을 고르면 그 자리를 채워 복사한다.

화면은 카드 한 장에 글 하나. 무엇을 할지(복사·고치기)는 main_window 가 넣어 준다(spec).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from . import hangul, theme
from .livesearch import LiveLineEdit


def preview(text: str, lines: int = 3) -> str:
    """카드에 보여 줄 앞 몇 줄(빈 줄은 건너뛴다)."""
    got = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    out = "\n".join(got[:lines])
    return out + (" …" if len(got) > lines else "")


class TemplateCard(QFrame):
    """글 하나 — 제목 · 도움말 · 앞 세 줄 미리보기 · 단추들.

    spec = {"key", "title", "hint", "text": () → 글,
            "buttons": [(이름, 풍선 도움말, 함수(카드))] — 첫 단추가 주 단추(채운 색)}"""

    def __init__(self, spec: dict, parent=None):
        super().__init__(parent)
        self.spec = spec
        self.setObjectName("mentcard")
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 10, 14, 12)
        v.setSpacing(6)
        self.lbl_title = QLabel(spec.get("title", ""))
        v.addWidget(self.lbl_title)
        self.lbl_hint = QLabel(spec.get("hint", ""))
        self.lbl_hint.setWordWrap(True)
        v.addWidget(self.lbl_hint)
        self.lbl_preview = QLabel("")
        self.lbl_preview.setWordWrap(True)
        self.lbl_preview.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_preview.setObjectName("mentpreview")
        v.addWidget(self.lbl_preview, 1)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.buttons = []
        for i, (label, tip, fn) in enumerate(spec.get("buttons", [])):
            b = QPushButton(label)
            b.setToolTip(tip)
            b.setCursor(Qt.PointingHandCursor)
            if i == 0:
                b.setObjectName("dashprimary")
            b.clicked.connect(lambda _c=False, f=fn: f(self))
            row.addWidget(b)
            self.buttons.append(b)
        row.addStretch(1)
        v.addLayout(row)
        self.refresh()
        self.apply_theme()

    def refresh(self) -> None:
        get = self.spec.get("text")
        self.lbl_preview.setText(preview(get() if callable(get) else ""))

    def apply_theme(self) -> None:
        self.setStyleSheet(
            f"QFrame#mentcard {{ background:{theme.c('panel_bg')}; border:1px solid {theme.c('border')};"
            " border-radius:12px; }")
        self.lbl_title.setStyleSheet(f"color:{theme.c('text')};font-size:15px;font-weight:bold;")
        self.lbl_hint.setStyleSheet(f"color:{theme.c('subtext')};font-size:12px;")
        self.lbl_preview.setStyleSheet(
            f"color:{theme.c('text')};background:{theme.c('window_bg')};border-radius:8px;padding:8px;")


class TemplateSection(QWidget):
    """'고객 안내 문구' — 카드 여러 장(한 줄에 두 장)."""

    COLS = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 14, 0, 0)
        v.setSpacing(8)
        self.lbl_head = QLabel("고객 안내 문구")
        v.addWidget(self.lbl_head)
        self.lbl_sub = QLabel("고객에게 보내는 글을 여기서 보고 고치고 복사합니다. "
                              "고객 이름이 들어가는 글은 [고객 골라 복사] 로 이름을 채워 복사합니다.")
        self.lbl_sub.setWordWrap(True)
        v.addWidget(self.lbl_sub)
        self.grid = QGridLayout()
        self.grid.setSpacing(10)
        v.addLayout(self.grid)
        self.cards: list = []
        self.apply_theme()

    def set_specs(self, specs: list) -> None:
        for c in self.cards:
            self.grid.removeWidget(c)
            c.hide()
            c.setParent(None)
            c.deleteLater()
        self.cards = []
        for i, spec in enumerate(specs):
            card = TemplateCard(spec)
            self.grid.addWidget(card, i // self.COLS, i % self.COLS)
            self.cards.append(card)
        for col in range(self.COLS):
            self.grid.setColumnStretch(col, 1)

    def card(self, key: str):
        return next((c for c in self.cards if c.spec.get("key") == key), None)

    def refresh(self) -> None:
        for c in self.cards:
            c.refresh()

    def apply_theme(self) -> None:
        self.lbl_head.setStyleSheet(f"color:{theme.c('text')};font-size:16px;font-weight:bold;")
        self.lbl_sub.setStyleSheet(f"color:{theme.c('subtext')};")
        for c in self.cards:
            c.apply_theme()


class TemplateEditDialog(QDialog):
    """글 고치기 — 큰 글 칸 + 쓸 수 있는 자리표 + [기본 문구로] [저장] [취소]."""

    def __init__(self, title: str, text: str, default: str, help_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(620, 420)
        self._default = default
        v = QVBoxLayout(self)
        lb = QLabel(help_text)
        lb.setWordWrap(True)
        lb.setStyleSheet(f"color:{theme.c('subtext')};")
        v.addWidget(lb)
        self.ed = QTextEdit()
        self.ed.setPlainText(text)
        self.ed.setAcceptRichText(False)
        self.ed.setStyleSheet("font-size: 11pt;")
        v.addWidget(self.ed, 1)
        row = QHBoxLayout()
        b_def = QPushButton("기본 문구로 되돌리기")
        b_def.clicked.connect(lambda: self.ed.setPlainText(self._default))
        row.addWidget(b_def)
        row.addStretch(1)
        ok = QPushButton("저장")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.reject)
        row.addWidget(ok)
        row.addWidget(cancel)
        v.addLayout(row)

    def text(self) -> str:
        return self.ed.toPlainText().strip()

    @classmethod
    def run(cls, title: str, text: str, default: str, help_text: str, parent=None):
        d = cls(title, text, default, help_text, parent)
        if d.exec() != QDialog.Accepted:
            return None
        return d.text()


class CustomerPicker(QDialog):
    """고객 고르기 — 이름 · 차종 · 금융사로 찾는다(초성도 된다). 두 번 누르거나 [고르기]."""

    def __init__(self, title: str, rows: list, label, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(460, 520)
        self._rows = list(rows)
        self._label = label
        self._hay = [hangul.prepare(label(cr)) for cr in self._rows]
        v = QVBoxLayout(self)
        self.ed = LiveLineEdit()
        self.ed.setPlaceholderText("고객명 · 차종 · 금융사 (초성도 됩니다)")
        self.ed.setClearButtonEnabled(True)
        self.ed.liveText.connect(lambda _t: self._fill())
        v.addWidget(self.ed)
        self.lst = QListWidget()
        self.lst.itemDoubleClicked.connect(lambda _it: self.accept())
        v.addWidget(self.lst, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton("고르기")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.reject)
        row.addWidget(ok)
        row.addWidget(cancel)
        v.addLayout(row)
        self._fill()

    def _fill(self) -> None:
        q = (self.ed.live_text() or "").strip()
        self.lst.clear()
        for i, cr in enumerate(self._rows):
            if q and not hangul.matches_prepared(self._hay[i], q):
                continue
            it = QListWidgetItem(self._label(cr))
            it.setData(Qt.UserRole, i)
            self.lst.addItem(it)
        if self.lst.count():
            self.lst.setCurrentRow(0)

    def picked(self):
        it = self.lst.currentItem()
        return self._rows[int(it.data(Qt.UserRole))] if it is not None else None

    @classmethod
    def run(cls, title: str, rows: list, label, parent=None):
        d = cls(title, rows, label, parent)
        if d.exec() != QDialog.Accepted:
            return None
        return d.picked()
