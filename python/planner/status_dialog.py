"""연결 상태 점검 · 처음 설정 안내 · 오류 기록 보내기 — 한 화면(v1.32).

지점장 선택(A6 · A10 · A11). 일반 직원이 "안 돼요" 할 때 캡처 한 장 · 복사 한 번으로 원인을 알 수 있게.
  · 한 줄에 하나씩 ✔ / ⚠ / ✖ 와 까닭, 바로 고칠 수 있는 단추.
  · 새 PC 에서 처음 켜면(구글 로그인 전) '처음 설정' 으로 저절로 뜬다 — 위에서부터 차례로 하면 된다.
  · [점검 결과·오류 기록 복사] — 판 번호·계정·점검 결과·지난 오류 기록을 글로 복사한다(카톡에 붙여 보내기).
    토큰·비밀번호는 넣지 않는다.
점검은 뒤에서 돈다(창이 멈추지 않게). 통신은 여기서 따로 흉내 내지 않고 실제 기능이 쓰는 함수를 그대로 부른다.
"""

from __future__ import annotations

import platform
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from . import config, crashlog, theme

OK, WARN, BAD, WAIT = "ok", "warn", "bad", "wait"
MARK = {OK: "✔", WARN: "⚠", BAD: "✖", WAIT: "…"}

# (열쇠, 이름) — 화면에 이 순서로. 처음 설정도 이 순서로 하면 된다.
ROWS = (
    ("login", "구글 로그인"),
    ("scopes", "구글 권한(동의 화면)"),
    ("sync", "동기화(내 계정 저장공간)"),
    ("sheet", "고객관리 시트"),
    ("kb", "회사 업무자료"),
    ("files", "고객 서류 폴더"),
    ("otp", "휴대폰 인증번호 받기"),
    ("update", "프로그램 판(업데이트)"),
)


def _first_line(e) -> str:
    return (str(e).strip().splitlines() or ["알 수 없는 오류"])[0][:140]


def check_login(win) -> tuple:
    if not win.gauth.is_connected():
        return BAD, "로그인되어 있지 않습니다 — 일정·시트·동기화·인증번호가 모두 여기서 시작합니다.", "login"
    who = getattr(win, "account_email", "") or ""
    if not getattr(win, "_account_verified", False):
        return WARN, (who + " · " if who else "") + "계정을 아직 인터넷으로 확인하지 못했습니다(연결을 기다리는 중).", ""
    return OK, who, ""


def check_scopes(win) -> tuple:
    if not win.gauth.is_connected():
        return WAIT, "로그인하면 확인합니다.", ""
    miss = win.gauth.missing_scopes()
    if miss:
        return BAD, ("빠진 항목: " + " · ".join(config.SCOPE_LABELS[m] for m in miss)
                     + " — 로그아웃 후 다시 로그인하며 동의 화면의 '모두 선택' 에 체크하세요."), "settings"
    if not win.gauth.scopes:
        return WARN, "예전에 로그인해 권한 목록을 모릅니다 — 안 되는 기능이 있으면 다시 로그인해 보세요.", ""
    return OK, "필요한 항목을 모두 받았습니다.", ""


def check_sync(win) -> tuple:
    if not win.gauth.is_connected():
        return WAIT, "로그인하면 확인합니다.", ""
    from . import google_client, sync
    try:
        fid = google_client.drive_find(win.gauth, sync.SYNC_FILE)
    except Exception as e:
        return BAD, _first_line(e), ""
    return OK, "내 계정에 동기화 묶음이 있습니다." if fid else "아직 올린 것이 없습니다(곧 저절로 올립니다).", ""


def check_sheet(win) -> tuple:
    s = win.settings
    sid = (s.sheet_id or "").strip()
    if not sid:
        return WARN, "시트 주소를 정하지 않았습니다 — 고객관리를 쓰려면 [설정] 에서 시트 주소를 넣으세요.", "settings"
    if not s.sheet_on:
        return WARN, "시트 주소는 있지만 '사용' 이 꺼져 있습니다.", "settings"
    if not win.gauth.is_connected():
        return WAIT, "로그인하면 확인합니다.", ""
    from . import sheets
    try:
        _hdr, rows, _sum = sheets.read_rows(win.gauth, sid, (s.sheet_name or "").strip())
    except Exception as e:
        return BAD, _first_line(e), "settings"
    ro = bool(getattr(win, "_sheet_readonly", False))
    return (WARN if ro else OK), (f"고객 {len(rows)}명을 읽었습니다."
                                  + (" 이 계정은 '보기' 만 됩니다(추가·수정 불가)." if ro else "")), ""


def check_kb(win) -> tuple:
    from . import kb
    n = len(kb.load_shared())
    if not win.gauth.is_connected():
        return (WARN if n else WAIT), f"이 PC 에 받아 둔 자료 {n}건(로그인하면 새로 받습니다).", ""
    from . import sheets
    try:
        items = sheets.read_kb(win.gauth, config.RATES_SHEET_ID)
    except Exception as e:
        return BAD, _first_line(e), ""
    if not items:
        return WARN, f"회사 자료 시트를 읽지 못했습니다 — 이 PC 에 받아 둔 {n}건으로 검색합니다.", ""
    return OK, f"회사 자료 {len(items)}건을 받을 수 있습니다.", ""


def check_files(win) -> tuple:
    from . import customer_files
    try:
        src, why = customer_files.pick_source(win.settings, win.gauth)
    except Exception as e:
        return BAD, _first_line(e), "settings"
    if src is None:
        return WARN, _first_line(why), "settings"
    kind = "인터넷(드라이브)으로 읽는 중" if src.__class__.__name__ == "DriveSource" else "이 PC 의 폴더"
    return OK, f"{kind} — {getattr(src, 'root', '') or getattr(src, 'folder', '')}", ""


def check_otp(win) -> tuple:
    s = win.settings
    if not getattr(s, "otp_on", False):
        return WARN, "꺼져 있습니다([설정] 에서 켤 수 있습니다).", "settings"
    if not win.gauth.is_connected():
        return WAIT, "로그인하면 시작합니다.", ""
    if not win.gauth.has_scope(config.SCOPE_SHEETS):
        return BAD, "구글 시트 권한 없이 로그인해 읽지 못합니다 — 다시 로그인하세요.", "settings"
    from . import otp
    try:
        rows = otp.rows_of(otp.read_top(win.gauth, (s.otp_sheet or "").strip(), (s.otp_tab or "").strip()))
    except otp.NoAccess:
        return BAD, "이 계정으로는 인증문자 시트를 볼 수 없습니다 — 시트 주인에게 공유를 요청하세요.", ""
    except Exception as e:
        return BAD, _first_line(e), "settings"
    return OK, f"인증문자 시트를 읽고 있습니다(최근 {len(rows)}줄).", ""


def check_update(win) -> tuple:
    from . import updater
    cur = "v" + config.APP_VERSION
    if not updater.is_frozen():
        return OK, cur + " (개발 실행)", ""
    try:
        info = updater.check()
    except Exception as e:
        return WARN, f"{cur} — 새 판을 확인하지 못했습니다: {_first_line(e)}", ""
    if info:
        return WARN, f"{cur} — 새 판 {info.get('version', '')} 이 있습니다(곧 저절로 받습니다).", ""
    return OK, cur + " — 최신입니다.", ""


CHECKS = {"login": check_login, "scopes": check_scopes, "sync": check_sync, "sheet": check_sheet,
          "kb": check_kb, "files": check_files, "otp": check_otp, "update": check_update}


def run_all(win, emit=None) -> dict:
    """모든 점검 → {열쇠: (상태, 까닭, 단추)}. emit(열쇠, 결과) 를 주면 하나 끝날 때마다 알린다."""
    out = {}
    for key, _name in ROWS:
        try:
            res = CHECKS[key](win)
        except Exception as e:                      # 점검이 탈나도 다른 줄은 본다
            res = (BAD, "점검하지 못했습니다: " + _first_line(e), "")
        out[key] = res
        if emit:
            emit(key, res)
    return out


def report_text(win, results: dict) -> str:
    """보내기 좋은 글 — 판·PC·계정·점검 결과·지난 오류 기록. 토큰·비밀번호는 넣지 않는다."""
    lines = [f"[{config.APP_NAME} 상태 점검] v{config.APP_VERSION}",
             f"PC: {platform.system()} {platform.release()} ({platform.machine()})",
             f"계정: {getattr(win, 'account_email', '') or '(로그인 안 됨)'}", ""]
    for key, name in ROWS:
        st, why, _a = results.get(key, (WAIT, "점검 전", ""))
        lines.append(f"{MARK.get(st, '?')} {name}: {why}")
    try:
        log = crashlog._last_session(3000)
    except Exception:
        log = ""
    lines += ["", "[지난 실행 기록]", log or "(기록 없음)"]
    return "\n".join(lines)


class StatusDialog(QDialog):
    sig_row = Signal(str, object)
    sig_done = Signal()

    def __init__(self, win, first_run: bool = False):
        super().__init__(win if isinstance(win, QWidget) else None)
        self.win = win
        self.first_run = first_run
        self.results: dict = {}
        self._running = False
        self.setWindowTitle("처음 설정" if first_run else "연결 상태 점검")
        self.setMinimumWidth(720)
        v = QVBoxLayout(self)
        head = QLabel(
            "처음 쓰시는군요. 위에서부터 차례로 하면 됩니다 — 먼저 [구글 로그인] 부터 눌러 주세요.\n"
            "나중에 [설정] → [연결 상태 점검] 에서 다시 볼 수 있습니다." if first_run else
            "무엇이 되고 안 되는지 한 번에 봅니다. 안 되는 줄의 단추를 누르면 바로 고칠 수 있습니다.")
        head.setWordWrap(True)
        head.setStyleSheet(f"color:{theme.c('subtext')};")
        v.addWidget(head)

        grid = QGridLayout()
        grid.setColumnStretch(2, 1)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        self.marks, self.whys, self.btns = {}, {}, {}
        for r, (key, name) in enumerate(ROWS):
            mk = QLabel(MARK[WAIT])
            mk.setFixedWidth(22)
            mk.setAlignment(Qt.AlignCenter)
            nm = QLabel(name)
            nm.setStyleSheet("font-weight:bold;")
            why = QLabel("점검하는 중…")
            why.setWordWrap(True)
            why.setTextInteractionFlags(Qt.TextSelectableByMouse)
            btn = QPushButton("")
            btn.hide()
            btn.clicked.connect(lambda _c=False, k=key: self._act(k))
            grid.addWidget(mk, r, 0, Qt.AlignTop)
            grid.addWidget(nm, r, 1, Qt.AlignTop)
            grid.addWidget(why, r, 2)
            grid.addWidget(btn, r, 3, Qt.AlignTop)
            self.marks[key], self.whys[key], self.btns[key] = mk, why, btn
        v.addLayout(grid)

        row = QHBoxLayout()
        self.btn_again = QPushButton("다시 점검")
        self.btn_again.clicked.connect(self.start)
        self.btn_copy = QPushButton("점검 결과·오류 기록 복사")
        self.btn_copy.setToolTip("판 번호·계정·점검 결과·지난 실행 기록을 글로 복사합니다 — 카톡에 붙여 보내 주세요.")
        self.btn_copy.clicked.connect(self.copy_report)
        self.lbl_done = QLabel("")
        self.lbl_done.setStyleSheet(f"color:{theme.c('status_ok')};")
        close = QPushButton("닫기")
        close.clicked.connect(self.accept)
        row.addWidget(self.btn_again)
        row.addWidget(self.btn_copy)
        row.addWidget(self.lbl_done, 1)
        row.addWidget(close)
        v.addLayout(row)

        self.sig_row.connect(self._on_row)
        self.sig_done.connect(self._on_done)
        self.start()

    # ---- 점검 ----
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self.btn_again.setEnabled(False)
        self.lbl_done.setText("")
        for key, _n in ROWS:
            self._paint(key, (WAIT, "점검하는 중…", ""))

        def worker():
            try:
                run_all(self.win, emit=lambda k, r: self.sig_row.emit(k, r))
            finally:
                self.sig_done.emit()
        threading.Thread(target=worker, daemon=True).start()

    def _paint(self, key: str, res: tuple) -> None:
        st, why, act = res
        col = {OK: theme.c("status_ok"), BAD: theme.c("status_bad"), WARN: theme.strong("orange")}.get(
            st, theme.c("subtext"))
        self.marks[key].setText(MARK.get(st, "?"))
        self.marks[key].setStyleSheet(f"color:{col};font-weight:bold;font-size:15px;")
        self.whys[key].setText(why)
        self.whys[key].setStyleSheet(f"color:{theme.c('text') if st != WAIT else theme.c('subtext')};")
        b = self.btns[key]
        b.setProperty("act", act)
        if act == "login":
            b.setText("구글 로그인")
            b.show()
        elif act == "settings":
            b.setText("설정 열기")
            b.show()
        else:
            b.hide()

    def _act(self, key: str) -> None:
        act = self.btns[key].property("act")
        if act == "login":
            self._do_login()
        elif act == "settings":
            self._do_settings()

    def _on_row(self, key: str, res) -> None:
        self.results[key] = tuple(res)
        self._paint(key, tuple(res))

    def _on_done(self) -> None:
        self._running = False
        self.btn_again.setEnabled(True)

    # ---- 고치기 ----
    def _do_login(self) -> None:
        self.accept()
        self.win.on_google_login_click()

    def _do_settings(self) -> None:
        self.accept()
        self.win.on_settings_click()

    # ---- 보내기 ----
    def copy_report(self) -> str:
        text = report_text(self.win, self.results)
        QApplication.clipboard().setText(text)
        self.lbl_done.setText("복사했습니다 — 카카오톡 등에 붙여 넣어 보내 주세요")
        return text
