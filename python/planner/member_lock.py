"""사용 제한 잠금 창(v1.40) — 지점장이 이 계정의 사용을 제한했을 때. 일정관리기 · 업무자료검색이 같은 파일을 쓴다.

지점장: "현재 로그인했던 사용자 중에 내가 계정 리스트를 보고 해당 이메일에 사용 제한할 수 있는 기능" — 앱 전체.
창은 [다시 확인](서버에 다시 묻는다 — 풀렸으면 그대로 쓴다) 과 [끝내기] 뿐이다. 닫아도 끝내기.
"""

from __future__ import annotations

import threading
from datetime import datetime

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from . import theme

TITLE = "사용 제한"


class _Relay(QObject):
    done = Signal(object)


class LockDialog(QDialog):
    """recheck() → 서버 답 {blocked, …} · 못 물으면 None. 풀렸으면 accept, [끝내기] · 닫기는 reject."""

    def __init__(self, email: str, recheck, app_name: str = "", parent=None):
        super().__init__(parent)
        self.recheck = recheck
        self.status = None
        self.setWindowTitle(f"{app_name} — {TITLE}" if app_name else TITLE)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setModal(True)
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(10)
        head = QLabel("사용이 제한된 계정입니다")
        head.setStyleSheet("font-size: 17px; font-weight: 800;")
        lay.addWidget(head)
        self.lbl_mail = QLabel(email or "")
        self.lbl_mail.setStyleSheet(f"color: {theme.strong('red')}; font-weight: 800;")
        self.lbl_mail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.lbl_mail)
        body = QLabel("관리자(지점장)가 이 계정의 사용을 제한했습니다.\n지점장에게 문의해 주세요.\n\n"
                      "제한이 풀리면 [다시 확인] 을 누르세요.")
        body.setWordWrap(True)
        lay.addWidget(body)
        self.lbl_state = QLabel("")
        self.lbl_state.setStyleSheet(f"color: {theme.c('subtext')};")
        lay.addWidget(self.lbl_state)
        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_recheck = QPushButton("다시 확인")
        self.btn_quit = QPushButton("끝내기")
        for b in (self.btn_recheck, self.btn_quit):
            b.setMinimumHeight(34)
            b.setMinimumWidth(96)
            row.addWidget(b)
        lay.addLayout(row)
        self.btn_recheck.clicked.connect(self.on_recheck)
        self.btn_quit.clicked.connect(self.reject)
        self._relay = _Relay(self)
        self._relay.done.connect(self._on_done)

    def on_recheck(self) -> None:
        self.btn_recheck.setEnabled(False)
        self.lbl_state.setText("확인하는 중…")

        def work():
            try:
                st = self.recheck()
            except Exception:
                st = None
            self._relay.done.emit(st)
        threading.Thread(target=work, daemon=True).start()

    def _on_done(self, st) -> None:
        self.btn_recheck.setEnabled(True)
        self.status = st
        if st is None:
            self.lbl_state.setText("확인하지 못했습니다 — 인터넷 연결을 확인하고 다시 눌러 주세요.")
        elif st.get("blocked"):
            self.lbl_state.setText(f"아직 제한되어 있습니다({datetime.now():%H:%M} 확인).")
        else:
            self.accept()
