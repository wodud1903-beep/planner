"""주간 요약 창 — 보고, 복사하고, 파일로 남긴다.

브리핑은 알람 팝업(작고 잠깐 뜨는 창)이면 충분하지만, 주간 요약은 보면서
캐피탈에 전화를 걸거나 다음 주 일정을 잡는 화면이다. 닫히지 않고 떠 있어야
하고, 지난 주와 견줘 볼 수 있어야 한다. 그래서 별도 창으로 둔다.
"""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QTextBrowser, QVBoxLayout,
)

from . import config, theme, weekly


class WeeklyDialog(QDialog):
    def __init__(self, rows: list, today: date, expiry_months: int = 3, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{config.APP_NAME} · 주간 요약")
        self.resize(720, 760)
        self._rows = rows or []
        self._today = today
        self._months = expiry_months
        self._offset = 0                  # 0=이번 주, -1=지난 주 …

        v = QVBoxLayout(self)

        nav = QHBoxLayout()
        self.btn_prev = QPushButton("← 지난 주")
        self.btn_prev.clicked.connect(lambda: self._move(-1))
        self.btn_next = QPushButton("다음 주 →")
        self.btn_next.clicked.connect(lambda: self._move(+1))
        self.lbl_week = QLabel("")
        self.lbl_week.setStyleSheet("font-weight:bold;")
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.lbl_week, 1)
        nav.addWidget(self.btn_next)
        v.addLayout(nav)

        self.txt = QTextBrowser()
        self.txt.setOpenExternalLinks(True)
        v.addWidget(self.txt, 1)

        row = QHBoxLayout()
        self.btn_copy = QPushButton("복사")
        self.btn_copy.clicked.connect(self._copy)
        self.btn_save = QPushButton("파일로 저장…")
        self.btn_save.clicked.connect(self._save)
        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(self.accept)
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet(f"color:{theme.c('subtext')};")
        row.addWidget(self.btn_copy)
        row.addWidget(self.btn_save)
        row.addWidget(self.lbl_status, 1)
        row.addWidget(btn_close)
        v.addLayout(row)

        self._render()

    # ---- 주 이동 ----
    def _base(self) -> date:
        """지금 보고 있는 주 안의 아무 날 — 요약 함수들은 이 날로 주를 정한다."""
        return self._today + timedelta(days=7 * self._offset)

    def _move(self, step: int) -> None:
        # 앞으로는 다음 주까지만. 그 뒤는 아직 아무 일도 안 일어나 빈 화면이다.
        self._offset = max(-52, min(1, self._offset + step))
        self._render()

    def _render(self) -> None:
        base = self._base()
        self.txt.setHtml(weekly.to_html(self._rows, base, self._months))
        mon, sun = weekly.week_range(base)
        tag = {0: " (이번 주)", -1: " (지난 주)", 1: " (다음 주)"}.get(self._offset, "")
        self.lbl_week.setText(f"{mon:%Y-%m-%d} ~ {sun:%m-%d}{tag}")
        self.btn_next.setEnabled(self._offset < 1)
        self.lbl_status.setText("")

    # ---- 내보내기 ----
    def _text(self) -> str:
        return weekly.to_text(self._rows, self._base(), self._months)

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self._text())
        self.lbl_status.setText("복사됨 ✓")

    def _save(self) -> None:
        name = weekly.file_name(self._base())
        path, _f = QFileDialog.getSaveFileName(
            self, "주간 요약 저장", name, "텍스트 파일 (*.txt)")
        if not path:
            return
        try:
            # utf-8-sig — 메모장·엑셀이 한글을 깨뜨리지 않게 BOM 을 붙인다
            with open(path, "w", encoding="utf-8-sig", newline="\r\n") as f:
                f.write(self._text())
        except Exception as e:
            QMessageBox.warning(self, config.APP_NAME, f"저장하지 못했습니다.\n{e}")
            return
        self.lbl_status.setText(f"저장됨 ✓  {path}")

    @classmethod
    def show_for(cls, rows: list, today: date, expiry_months: int = 3, parent=None):
        d = cls(rows, today, expiry_months, parent)
        d.exec()
        return d
