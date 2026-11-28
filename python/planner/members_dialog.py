"""회원 목록 창(v1.37 · 지점장) — 일정관리기 · 업무자료검색에 로그인한 계정을 이메일로.

목록은 서버(api/members)에서 받는다 — 지점장인지는 서버가 확인한다. [이메일 목록 복사] 로 한 줄에 하나씩 복사.
v1.40 지점장: "로그인했던 사용자 중에 계정 리스트를 보고 해당 이메일에 사용 제한" · "내가 관리자로 지정할 이메일도 —
관리자는 지금 내가 자료 수정할 수 있는 권한들을 모두". → 줄을 골라 [사용 제한] [제한 풀기] [관리자로 지정] [관리자 해제].
  · 사용 제한 = 앱 전체(일정관리기 · 업무자료검색 PC 와 폰 웹). 켜 있는 프로그램은 30분 안에 잠긴다.
  · 관리자 = 수당율 · 회사 공통 업무자료 · 인증문자 정리. 시트로 올리려면 두 시트를 그 이메일에 '편집자'로
    공유해야 한다 — 이 앱의 구글 권한으로는 남의 시트 공유를 바꿀 수 없어, 시트를 열어 주고 이메일을 복사해 둔다.
  · 지점장 줄은 바꿀 수 없다(서버도 막는다).
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from . import config, members, theme

COLS = ["이메일", "상태", "일정관리기 마지막", "업무자료검색 마지막", "판", "처음 로그인"]
SHEET_URL = "https://docs.google.com/spreadsheets/d/{}/edit"


def state_text(m: dict) -> str:
    if m.get("owner"):
        return "지점장"
    if m.get("blocked"):
        return "사용 제한"
    if m.get("admin"):
        return "관리자"
    return ""


class _Relay(QObject):
    done = Signal(object, str)
    acted = Signal(str, str, object, str)      # (일, 이메일, 상태|None, 오류)


class MembersDialog(QDialog):
    def __init__(self, auth, parent=None):
        super().__init__(parent)
        self.auth = auth
        self.rows: list = []
        self.setWindowTitle("회원 목록 — 로그인한 계정")
        self.resize(860, 520)
        lay = QVBoxLayout(self)
        self.lbl = QLabel("불러오는 중…")
        lay.addWidget(self.lbl)
        self.tbl = QTableWidget(0, len(COLS))
        self.tbl.setHorizontalHeaderLabels(COLS)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl.itemSelectionChanged.connect(self._paint_buttons)
        lay.addWidget(self.tbl, 1)
        # 고른 계정 — 사용 제한 · 관리자 지정(v1.40)
        act = QHBoxLayout()
        self.lbl_pick = QLabel("")
        act.addWidget(self.lbl_pick, 1)
        self.btn_block = QPushButton("사용 제한")
        self.btn_unblock = QPushButton("제한 풀기")
        self.btn_admin = QPushButton("관리자로 지정")
        self.btn_unadmin = QPushButton("관리자 해제")
        for b, action in ((self.btn_block, "block"), (self.btn_unblock, "unblock"), (self.btn_admin, "admin"),
                          (self.btn_unadmin, "unadmin")):
            b.clicked.connect(lambda _c=False, a=action: self.act(a))
            act.addWidget(b)
        lay.addLayout(act)
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
        self._relay.acted.connect(self._on_acted)
        self._busy = False
        self._paint_buttons()
        self.reload()

    # ------------------------------------------------------------ 목록
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
        keep = self.selected_email()
        self.rows = rows
        self.tbl.clearSelection()
        self.tbl.setRowCount(len(rows))
        for r, m in enumerate(rows):
            apps = m.get("apps") or {}
            p, k = apps.get("planner") or {}, apps.get("kb") or {}
            vers = " · ".join(x for x in (f"일정 {p.get('ver')}" if p.get("ver") else "",
                                          f"자료 {k.get('ver')}" if k.get("ver") else "") if x)
            firsts = sorted(x.get("first", "") for x in (p, k) if x.get("first"))
            cells = [m.get("email", ""), state_text(m), members.short(p.get("last", "")),
                     members.short(k.get("last", "")), vers, members.short(firsts[0]) if firsts else ""]
            tint = theme.row_tint("red") if m.get("blocked") else (
                theme.row_tint("blue") if m.get("admin") and not m.get("owner") else "")
            for c, t in enumerate(cells):
                it = QTableWidgetItem(t)
                if c:
                    it.setTextAlignment(Qt.AlignCenter)
                if tint:
                    it.setBackground(QColor(tint))
                    it.setForeground(QColor(theme.c("row_text")))
                self.tbl.setItem(r, c, it)
        self.tbl.resizeColumnsToContents()
        self.tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        np = sum(1 for m in rows if (m.get("apps") or {}).get("planner"))
        nk = sum(1 for m in rows if (m.get("apps") or {}).get("kb"))
        nb = sum(1 for m in rows if m.get("blocked"))
        na = sum(1 for m in rows if m.get("admin") and not m.get("owner"))
        self.lbl.setText(f"모두 {len(rows)}명 — 일정관리기 {np}명 · 업무자료검색 {nk}명 · 관리자 {na}명 · "
                         f"사용 제한 {nb}명 (최근 로그인 순)")
        if keep:
            for r, m in enumerate(rows):
                if m.get("email") == keep:
                    self.tbl.selectRow(r)
                    break
        self._paint_buttons()

    def emails(self) -> list:
        return [m.get("email", "") for m in self.rows if m.get("email")]

    def copy_emails(self) -> None:
        QApplication.clipboard().setText("\n".join(self.emails()))
        self.lbl.setText(f"이메일 {len(self.emails())}개를 복사했습니다(한 줄에 하나씩).")

    # ------------------------------------------------------------ 사용 제한 · 관리자 지정
    def selected(self):
        sm = self.tbl.selectionModel()
        rows = sm.selectedRows() if sm is not None else []
        if not rows:
            return None
        r = rows[0].row()
        return self.rows[r] if 0 <= r < len(self.rows) else None

    def selected_email(self) -> str:
        m = self.selected()
        return (m or {}).get("email", "")

    def _paint_buttons(self) -> None:
        m = self.selected()
        owner = bool(m and (m.get("owner") or config.is_owner(m.get("email", ""))))
        ok = m is not None and not owner and not self._busy
        self.btn_block.setEnabled(ok and not m.get("blocked"))
        self.btn_unblock.setEnabled(ok and bool(m.get("blocked")))
        self.btn_admin.setEnabled(ok and not m.get("admin"))
        self.btn_unadmin.setEnabled(ok and bool(m.get("admin")))
        if m is None:
            self.lbl_pick.setText("줄을 고르면 사용 제한 · 관리자 지정을 할 수 있습니다.")
        elif owner:
            self.lbl_pick.setText("지점장 계정은 바꿀 수 없습니다.")
        else:
            self.lbl_pick.setText(m.get("email", "") + (f" — {state_text(m)}" if state_text(m) else ""))

    def _ask(self, action: str, email: str) -> bool:
        text = {
            "block": (f"{email}\n\n이 계정의 사용을 제한할까요?\n\n"
                      "· 일정관리기 · 업무자료검색(PC)과 폰 웹을 쓸 수 없게 됩니다.\n"
                      "· 지금 켜 있는 프로그램은 30분 안에 잠깁니다(다시 켜면 바로).\n"
                      "· 관리자였다면 관리자도 풀립니다. [제한 풀기] 로 언제든 되돌릴 수 있습니다."),
            "unblock": f"{email}\n\n사용 제한을 풀까요? 다음에 켜거나 잠금 창에서 [다시 확인] 하면 다시 쓸 수 있습니다.",
            "admin": (f"{email}\n\n이 계정을 관리자로 지정할까요?\n\n"
                      "· 지점장과 같은 자료 수정 권한(수당율 · 회사 공통 업무자료 · 인증문자 정리)을 받습니다.\n"
                      "· 회원 목록 · 사용 제한 · 관리자 지정은 지점장만 합니다."),
            "unadmin": f"{email}\n\n관리자를 해제할까요? 자료 수정 권한이 없어집니다.",
        }[action]
        return QMessageBox.question(self, f"회원 — {members.ACTION_TEXT[action]}", text,
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes

    def act(self, action: str) -> None:
        m = self.selected()
        if m is None or self._busy:
            return
        email = m.get("email", "")
        if not email or m.get("owner") or config.is_owner(email):
            return
        if not self._ask(action, email):
            return
        self._busy = True
        self._paint_buttons()
        self.lbl.setText(f"{members.ACTION_TEXT[action]} — {email} …")
        auth = self.auth

        def work():
            try:
                self._relay.acted.emit(action, email, members.manage(auth, action, email), "")
            except Exception as e:
                self._relay.acted.emit(action, email, None, str(e) or "바꾸지 못했습니다.")
        threading.Thread(target=work, daemon=True).start()

    def _on_acted(self, action: str, email: str, st, err: str) -> None:
        self._busy = False
        if st is None:
            self.lbl.setText("⚠ " + err)
            self._paint_buttons()
            return
        self.lbl.setText(f"{members.ACTION_TEXT[action]} — {email} 했습니다.")
        self._paint_buttons()
        if action in ("admin", "unadmin"):
            self.share_hint(action, email)
        self.reload()

    def share_hint(self, action: str, email: str) -> None:
        """관리자 지정 · 해제 뒤 — 두 시트의 '편집자' 공유를 지점장이 직접(이 앱 권한으로는 바꿀 수 없다)."""
        QApplication.clipboard().setText(email)
        box = QMessageBox(self)
        box.setWindowTitle("시트 공유도 바꿔 주세요")
        box.setIcon(QMessageBox.Information)
        if action == "admin":
            box.setText(f"{email} 을(를) 관리자로 지정했습니다.\n\n"
                        "그 PC 의 프로그램은 다음에 켜거나 30분 안에 관리자 권한을 받습니다.\n\n"
                        "수당율 · 업무자료 · 인증문자를 시트로 올리려면 아래 두 시트를 이 이메일에 '편집자'로 "
                        "공유해 주세요(이메일은 복사해 두었습니다):\n"
                        "시트를 열고 오른쪽 위 [공유] → 붙여 넣기 → 편집자 → [보내기]")
        else:
            box.setText(f"{email} 의 관리자를 해제했습니다.\n\n"
                        "아래 두 시트에서 이 이메일의 '편집자' 공유도 빼 주세요(이메일은 복사해 두었습니다):\n"
                        "시트를 열고 오른쪽 위 [공유] → 그 이메일 → [삭제]")
        b_rates = box.addButton("수당연동용 시트 열기", QMessageBox.ActionRole)
        b_otp = box.addButton("인증문자 시트 열기", QMessageBox.ActionRole)
        box.addButton("닫기", QMessageBox.RejectRole)
        self._hint_box = box
        while True:
            box.exec()
            clicked = box.clickedButton()
            if clicked is b_rates:
                QDesktopServices.openUrl(QUrl(SHEET_URL.format(config.RATES_SHEET_ID)))
            elif clicked is b_otp:
                QDesktopServices.openUrl(QUrl(SHEET_URL.format(config.OTP_DEF_SHEET_ID)))
            else:
                break
