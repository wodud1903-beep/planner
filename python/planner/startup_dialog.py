"""시작 화면 — 오늘 브리핑과 주간 요약을 한 장에.

예전에는 둘을 따로 띄웠다. 브리핑은 '항상 위' 로 뜨는 알람 팝업이고 주간
요약은 모달 창이라, **브리핑이 위에 보이는데 눌리지는 않았다.** 모달이 입력을
전부 가로채고 있었기 때문이다. 뒤에 깔린 주간 요약의 [확인] 만 눌렸다.

창을 하나로 합치면 그 문제가 사라지고, 오늘 할 일과 이번 주 흐름을 한눈에
같이 볼 수 있다. 화면이 좁으면 좌우가 아니라 위아래로 접힌다.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QSplitter, QTextBrowser, QVBoxLayout, QWidget,
)

from . import config, theme, weekly

# 이보다 좁으면 좌우로 나눠 봤자 둘 다 못 읽는다 → 위아래로 쌓는다
SIDE_BY_SIDE_MIN = 900


class StartupDialog(QDialog):
    """오늘 브리핑(왼쪽) + 주간 요약(오른쪽)."""

    def __init__(self, brief_html: str, brief_text: str,
                 rows: list | None, today: date, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{config.APP_NAME} · 오늘 시작")
        self._brief_text = brief_text or ""
        self._rows = rows or []
        self._today = today
        self._show_weekly = bool(self._rows)

        root = QVBoxLayout(self)

        wide = True
        try:
            scr = (parent.screen() if parent else None) or QGuiApplication.primaryScreen()
            wide = scr.availableGeometry().width() >= SIDE_BY_SIDE_MIN
        except Exception:
            pass
        self.split = QSplitter(Qt.Horizontal if wide else Qt.Vertical)
        root.addWidget(self.split, 1)

        self.txt_brief = self._pane("오늘 브리핑", brief_html)
        if self._show_weekly:
            self.txt_weekly = self._pane(
                "주간 요약", weekly.to_html(self._rows, today))
            self.split.setSizes([520, 520] if wide else [420, 420])
        else:
            # 시트를 아직 못 읽었다 — 주간 요약은 만들 수 없으니 이유를 적어 둔다
            self.txt_weekly = self._pane(
                "주간 요약",
                f"<p style='color:{theme.c('subtext')};'>"
                "고객관리 시트를 읽은 뒤에 만들어집니다.<br>"
                "[고객관리] 탭에서 [불러오기] 를 누른 다음 "
                "[주간 요약] 버튼으로 보실 수 있습니다.</p>")

        row = QHBoxLayout()
        self.btn_copy_brief = QPushButton("브리핑 복사")
        self.btn_copy_brief.clicked.connect(self._copy_brief)
        row.addWidget(self.btn_copy_brief)
        self.btn_copy_weekly = QPushButton("주간 요약 복사")
        self.btn_copy_weekly.clicked.connect(self._copy_weekly)
        self.btn_copy_weekly.setEnabled(self._show_weekly)
        row.addWidget(self.btn_copy_weekly)
        self.btn_save = QPushButton("주간 요약 저장…")
        self.btn_save.clicked.connect(self._save_weekly)
        self.btn_save.setEnabled(self._show_weekly)
        row.addWidget(self.btn_save)
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet(f"color:{theme.c('subtext')};")
        row.addWidget(self.lbl_status, 1)
        btn_ok = QPushButton("확인")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.accept)
        row.addWidget(btn_ok)
        root.addLayout(row)

        self.resize(1180 if wide else 700, 820)

    def _pane(self, title: str, html: str) -> QTextBrowser:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        cap = QLabel(title)
        cap.setStyleSheet(
            f"color:{theme.c('subtext')};font-weight:bold;padding:2px 4px;")
        v.addWidget(cap)
        txt = QTextBrowser()
        txt.setOpenExternalLinks(True)
        txt.setHtml(html)
        v.addWidget(txt, 1)
        self.split.addWidget(box)
        return txt

    # ---- 내보내기 ----
    def _weekly_text(self) -> str:
        return weekly.to_text(self._rows, self._today)

    def _copy_brief(self):
        QGuiApplication.clipboard().setText(self._brief_text)
        self.lbl_status.setText("브리핑 복사됨 ✓")

    def _copy_weekly(self):
        QGuiApplication.clipboard().setText(self._weekly_text())
        self.lbl_status.setText("주간 요약 복사됨 ✓")

    def _save_weekly(self):
        path, _f = QFileDialog.getSaveFileName(
            self, "주간 요약 저장", weekly.file_name(self._today),
            "텍스트 파일 (*.txt)")
        if not path:
            return
        try:
            # utf-8-sig — 메모장·엑셀이 한글을 깨뜨리지 않게 BOM 을 붙인다
            with open(path, "w", encoding="utf-8-sig", newline="\r\n") as f:
                f.write(self._weekly_text())
        except Exception as e:
            QMessageBox.warning(self, config.APP_NAME, f"저장하지 못했습니다.\n{e}")
            return
        self.lbl_status.setText(f"저장됨 ✓  {path}")

    @classmethod
    def show_for(cls, brief_html: str, brief_text: str, rows, today: date,
                 parent=None):
        d = cls(brief_html, brief_text, rows, today, parent)
        d.exec()
        return d
