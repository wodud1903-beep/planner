"""고객 이력 타임라인.

한 고객에게 지금까지 무슨 일이 있었는지 한 화면에 모아 보여준다.

두 가지를 합쳐 보여준다.
  - **자동 이력**: 계약일·출고일·안내멘트 발송·만기 예정일처럼 시트와 앱이
    이미 알고 있는 것들. 저장하지 않고 열 때마다 만들므로 항상 최신이다.
  - **직접 메모**: '오늘 통화함 — 보증금 문의' 같이 사람이 남기는 기록.
    customer_notes.json 에 고객ID 기준으로 저장하고 다른 PC 와도 동기화한다.

고객ID(시트 U열, 숨김)로 묶기 때문에 고객명이나 순번을 바꿔도 이력이 끊기지 않는다.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QVBoxLayout,
)

from . import config, sheets, theme


def _auto_events(cr, ment_sent: bool) -> list[tuple]:
    """시트에서 파생되는 이력. [(날짜|None, 분류, 내용)]"""
    out = []
    d = sheets.parse_date(cr.get("contract_date"))
    if d:
        out.append((d, "계약", f"계약(발주) — {cr.get('finance')} {cr.get('model')}".strip()))
    d = sheets.parse_date(cr.get("deliver_date"))
    if d:
        out.append((d, "출고", "차량 출고"))
        if ment_sent:
            out.append((d, "안내", "고객안내멘트 발송함"))
    exp = sheets.expiry_date(cr)
    if exp:
        n = sheets.contract_months(cr.get("terms"))
        left = (exp - date.today()).days
        tail = f"D-{left}" if left > 0 else ("오늘" if left == 0 else f"{-left}일 지남")
        out.append((exp, "만기", f"계약 만기 예정 ({n}개월, {tail})"))
    return out


class CustomerHistoryDialog(QDialog):
    """고객 한 명의 이력 + 메모."""

    CAT_COLORS = {
        "계약": "#7B58C4", "출고": "#2E9E5B", "안내": "#4A7FB5",
        "만기": "#E08A1E", "메모": None,       # 메모는 기본색
    }

    def __init__(self, cr, notes: list, ment_sent: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"고객 이력 · {cr.get('customer')}")
        self.resize(560, 620)
        self._cr = cr
        self._notes = list(notes or [])
        self._ment_sent = ment_sent

        root = QVBoxLayout(self)

        head = QLabel(
            f"<b style='font-size:15px;'>{cr.get('customer')}</b><br>"
            f"<span style='color:{theme.c('subtext')};'>"
            f"{cr.get('finance')} · {cr.get('model')} · {cr.get('status')}</span>")
        head.setWordWrap(True)
        root.addWidget(head)

        self.lst = QListWidget()
        self.lst.setAlternatingRowColors(True)
        root.addWidget(self.lst, 1)

        # ---- 메모 추가 ----
        row = QHBoxLayout()
        self.ed = QLineEdit()
        self.ed.setPlaceholderText("메모를 입력하고 Enter (예: 통화함 — 보증금 문의)")
        self.ed.returnPressed.connect(self._add)
        btn_add = QPushButton("추가")
        btn_add.clicked.connect(self._add)
        row.addWidget(self.ed, 1)
        row.addWidget(btn_add)
        root.addLayout(row)

        row2 = QHBoxLayout()
        btn_del = QPushButton("선택한 메모 삭제")
        btn_del.clicked.connect(self._del)
        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(self.accept)
        row2.addWidget(btn_del)
        row2.addStretch()
        row2.addWidget(btn_close)
        root.addLayout(row2)

        self._refresh()
        self.ed.setFocus()

    def _refresh(self):
        """자동 이력 + 메모를 시간 역순으로 합쳐 다시 그린다."""
        items = _auto_events(self._cr, self._ment_sent)
        for i, n in enumerate(self._notes):
            d = sheets.parse_date(n.get("date", "")) or None
            items.append((d, "메모", n.get("text", ""), i))

        # 날짜 없는 항목은 맨 아래로
        items.sort(key=lambda t: (t[0] is not None, t[0] or date.min), reverse=True)

        self.lst.clear()
        if not items:
            self.lst.addItem("아직 기록이 없습니다. 아래에 첫 메모를 남겨보세요.")
            return
        for it in items:
            d, cat, text = it[0], it[1], it[2]
            when = d.strftime("%Y-%m-%d") if d else "날짜 미상"
            li = QListWidgetItem(f"{when}   [{cat}]  {text}")
            col = self.CAT_COLORS.get(cat)
            if col:
                from PySide6.QtGui import QColor
                li.setForeground(QColor(col))
            # 메모만 삭제 대상 — 자동 이력은 지울 수 없다
            li.setData(Qt.UserRole, it[3] if cat == "메모" else None)
            self.lst.addItem(li)

    def _add(self):
        t = self.ed.text().strip()
        if not t:
            return
        self._notes.append({"date": date.today().strftime("%Y-%m-%d"), "text": t})
        self.ed.clear()
        self._refresh()

    def _del(self):
        li = self.lst.currentItem()
        idx = li.data(Qt.UserRole) if li else None
        if idx is None:
            QMessageBox.information(self, config.APP_NAME,
                                    "삭제할 메모를 고르세요.\n(자동 이력은 지울 수 없습니다)")
            return
        if QMessageBox.question(self, config.APP_NAME,
                                "이 메모를 지울까요?") != QMessageBox.Yes:
            return
        del self._notes[idx]
        self._refresh()

    def notes(self) -> list:
        return list(self._notes)

    @classmethod
    def run(cls, cr, notes: list, ment_sent: bool, parent=None):
        """반환: 바뀐 메모 목록 (창을 닫으면 항상 반영)."""
        d = cls(cr, notes, ment_sent, parent)
        d.exec()
        return d.notes()
