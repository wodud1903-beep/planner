"""업데이트 창 — 새 판을 받아 바꾸고 다시 켠다. **건너뛰기 단추가 없다.**

고를 수 있는 것은 [다시 시도](받기에 실패했을 때)와 [종료] 뿐이다. 창을 닫아도 종료다.
업데이트 없이 계속 쓰는 길은 소스로 돌릴 때(개발자)뿐이다 — exe 가 아니라 바꿀 수 없다.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QTextBrowser, QVBoxLayout,
)

from . import config, theme, updater

RESTART = "restart"      # 바꾸는 배치를 띄웠다 — 앱을 끝내야 한다
QUIT = "quit"            # 사용자가 [종료] 를 골랐다
CONTINUE = "continue"    # 소스로 돌리는 중이라 그냥 계속(개발자)


class UpdateDialog(QDialog):
    _sig_progress = Signal(int, int)
    _sig_done = Signal(str, str)          # (받은 파일 경로, 오류)

    def __init__(self, info: dict, parent=None, failed_before: bool = False):
        super().__init__(parent)
        self.info = info
        self.outcome = QUIT
        self._busy = False
        self.setWindowTitle(f"{config.APP_NAME} 업데이트")
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.CustomizeWindowHint
                            | Qt.WindowStaysOnTopHint)
        self.setModal(True)
        self.resize(520, 380)

        v = QVBoxLayout(self)
        self.lbl = QLabel(
            f"<b style='font-size:15px;'>새 버전 v{info.get('version', '')} 이 나왔습니다.</b><br>"
            f"업데이트한 뒤에 계속 쓸 수 있습니다. (지금 v{config.APP_VERSION})")
        self.lbl.setWordWrap(True)
        v.addWidget(self.lbl)

        notes = (info.get("notes") or "").strip()
        self.txt = QTextBrowser()
        self.txt.setPlainText(notes or "달라진 점이 적혀 있지 않습니다.")
        v.addWidget(self.txt, 1)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        v.addWidget(self.bar)
        self.lbl_state = QLabel("")
        self.lbl_state.setWordWrap(True)
        v.addWidget(self.lbl_state)

        row = QHBoxLayout()
        row.addStretch()
        self.btn_go = QPushButton("다시 시도")
        self.btn_go.clicked.connect(self.start)
        row.addWidget(self.btn_go)
        self.btn_quit = QPushButton("종료")
        self.btn_quit.clicked.connect(self._quit)
        row.addWidget(self.btn_quit)
        v.addLayout(row)

        self._sig_progress.connect(self._on_progress)
        self._sig_done.connect(self._on_done)

        if not updater.is_frozen():
            # 개발 중(소스 실행)에는 바꿀 exe 가 없다 — 알리고 계속 쓰게 둔다
            self.bar.hide()
            self.lbl_state.setText("소스에서 실행 중이라 자동으로 바꿀 수 없습니다. "
                                   "저장소에서 새 코드를 받아 주세요.")
            self.btn_go.setText("계속")
            self.btn_go.clicked.disconnect()
            self.btn_go.clicked.connect(self._continue)
        elif failed_before:
            # 방금 바꾸려다 그대로 이 판으로 켜졌다 — 저절로 또 받지 않는다(무한 반복 방지)
            self.lbl_state.setText(
                "조금 전 업데이트가 적용되지 않았습니다. 다른 창에서 이 프로그램을 쓰고 있지 "
                "않은지 확인한 뒤 [다시 시도] 를 눌러 주세요.\n기록: " + updater.log_path())
            self.lbl_state.setStyleSheet(f"color:{theme.strong('red')};")
        else:
            self.btn_go.setEnabled(False)
            QTimer.singleShot(300, self.start)

    # ---- 받기 ----
    def start(self) -> None:
        if self._busy:
            return
        self._busy = True
        self.btn_go.setEnabled(False)
        self.lbl_state.setStyleSheet(f"color:{theme.c('subtext')};")
        self.lbl_state.setText("새 버전을 받는 중…")
        info = dict(self.info)

        def work():
            try:
                path = updater.download(info, lambda g, t: self._sig_progress.emit(g, t))
                self._sig_done.emit(path, "")
            except Exception as e:
                self._sig_done.emit("", str(e))
        threading.Thread(target=work, daemon=True).start()

    def _on_progress(self, got: int, total: int) -> None:
        if total > 0:
            self.bar.setValue(min(100, int(got * 100 / total)))
            self.lbl_state.setText(f"새 버전을 받는 중… {got / 1048576:.1f} / {total / 1048576:.1f} MB")
        else:
            self.bar.setRange(0, 0)

    def _on_done(self, path: str, err: str) -> None:
        self._busy = False
        if err:
            self.bar.setRange(0, 100)
            self.bar.setValue(0)
            self.lbl_state.setStyleSheet(f"color:{theme.strong('red')};")
            self.lbl_state.setText(err + "\n[다시 시도] 를 누르거나 [종료] 하세요.")
            self.btn_go.setEnabled(True)
            return
        self.bar.setRange(0, 100)
        self.bar.setValue(100)
        self.lbl_state.setText("바꾸는 중입니다 — 잠시 뒤 새 버전이 저절로 켜집니다.")
        QApplication.processEvents()
        try:
            updater.apply_and_restart(path, self.info.get("version", ""))
        except Exception as e:
            self.lbl_state.setStyleSheet(f"color:{theme.strong('red')};")
            self.lbl_state.setText(f"바꾸지 못했습니다: {e}")
            self.btn_go.setEnabled(True)
            return
        self.outcome = RESTART
        self.done(QDialog.Accepted)

    # ---- 나가기 ----
    def _continue(self) -> None:
        self.outcome = CONTINUE
        self.done(QDialog.Accepted)

    def _quit(self) -> None:
        self.outcome = QUIT
        self.done(QDialog.Rejected)

    def reject(self) -> None:          # Esc — 받는 중에는 무시, 아니면 종료와 같다
        if self._busy:
            return
        self._quit()

    def closeEvent(self, ev):
        if self._busy:
            ev.ignore()
            return
        if self.outcome not in (RESTART, CONTINUE):
            self.outcome = QUIT
        super().closeEvent(ev)

    @classmethod
    def run(cls, info: dict, parent=None) -> str:
        """창을 띄우고 결과(RESTART / QUIT / CONTINUE)를 돌려준다."""
        d = cls(info, parent, failed_before=updater.just_failed(info.get("version", "")))
        d.exec()
        return d.outcome
