"""회원 목록 창(v1.37, 관리자) — 일정관리기 · 업무자료검색에 로그인한 계정을 이메일로.

목록은 서버(api/members)에서 받는다 — 관리자인지는 서버가 확인한다. [이메일 목록 복사] 로 한 줄에 하나씩 복사.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from . import members

COLS = ["이메일", "일정관리기 마지막", "업무자료검색 마지막", "판", "처음 로그인"]


class _Relay(QObject):
    done = Signal(object, str)


class MembersDialog(QDialog):
    def __init__(self, auth, parent=None):
        super().__init__(parent)
        self.auth = auth
        self.rows: list = []
        self.setWindowTitle("회원 목록 — 로그인한 계정")
        self.resize(760, 480)
        lay = QVBoxLayout(self)
        self.lbl = QLabel("불러오는 중…")
        lay.addWidget(self.lbl)
        self.tbl = QTableWidget(0, len(COLS))
        self.tbl.setHorizontalHeaderLabels(COLS)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        lay.addWidget(self.tbl, 1)
        bot = QHBoxLayout()
        self.btn_copy = QPushButton("이메일 목록 복사")
        self.btn_reload = QPushButton("새로고침")
        self.btn_close = QPushButton("닫기")
        bot.addWidget(self.btn_copy)
        bot.addStretch(1)
        bot.addWidget(self.btn_reload)
        bot.addWidget(self.btn_close)
        lay.addLayout(bot)
        self.btn_copy.clicked.connect(self.copy_emails)
        self.btn_reload.clicked.connect(self.reload)
        self.btn_close.clicked.connect(self.close)
        self._relay = _Relay(self)
        self._relay.done.connect(self._on_done)
        self.reload()

    def reload(self) -> None:
        self.lbl.setText("불러오는 중…")
        self.btn_reload.setEnabled(False)
        auth = self.auth

        def work():
            try:
                self._relay.done.emit(members.fetch(auth), "")
            except Exception as e:
                self._relay.done.emit(None, str(e) or "목록을 받지 못했습니다.")
        threading.Thread(target=work, daemon=True).start()

    def _on_done(self, rows, err: str) -> None:
        self.btn_reload.setEnabled(True)
        if rows is None:
            self.lbl.setText("⚠ " + err)
            return
        self.rows = rows
        self.tbl.setRowCount(len(rows))
        for r, m in enumerate(rows):
            apps = m.get("apps") or {}
            p, k = apps.get("planner") or {}, apps.get("kb") or {}
            vers = " · ".join(x for x in (f"일정 {p.get('ver')}" if p.get("ver") else "",
                                          f"자료 {k.get('ver')}" if k.get("ver") else "") if x)
            firsts = sorted(x.get("first", "") for x in (p, k) if x.get("first"))
            cells = [m.get("email", ""), members.short(p.get("last", "")), members.short(k.get("last", "")),
                     vers, members.short(firsts[0]) if firsts else ""]
            for c, t in enumerate(cells):
                it = QTableWidgetItem(t)
                if c:
                    it.setTextAlignment(Qt.AlignCenter)
                self.tbl.setItem(r, c, it)
        self.tbl.resizeColumnsToContents()
        self.tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        np = sum(1 for m in rows if (m.get("apps") or {}).get("planner"))
        nk = sum(1 for m in rows if (m.get("apps") or {}).get("kb"))
        self.lbl.setText(f"모두 {len(rows)}명 — 일정관리기 {np}명 · 업무자료검색 {nk}명 (최근 로그인 순)")

    def emails(self) -> list:
        return [m.get("email", "") for m in self.rows if m.get("email")]

    def copy_emails(self) -> None:
        QApplication.clipboard().setText("\n".join(self.emails()))
        self.lbl.setText(f"이메일 {len(self.emails())}개를 복사했습니다(한 줄에 하나씩).")
