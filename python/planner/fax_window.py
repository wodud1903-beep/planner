"""받은 팩스 보기 창.

왼쪽에 최근 받은 팩스 목록, 오른쪽에 그 팩스. 알람의 [보기] 나 트레이 메뉴에서 열린다.

탭으로 만들지 않은 이유: 탭이 이미 일곱이고, 이건 늘 띄워 두는 화면이 아니라 알람에서
잠깐 열어 보는 성격이다. 그리고 받은팩스 폴더가 '고객정보' 폴더 밖에 있어도 되어야 한다.
"""

from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSplitter,
    QVBoxLayout, QWidget)

from . import config, fax_watch, theme
from .customer_files_tab import file_mime
from .file_preview import FilePreview


class FaxWindow(QDialog):
    """받은 팩스 목록 + 미리보기."""

    _open = None          # 지금 떠 있는 창 (하나만 띄운다)

    def __init__(self, folder: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("받은 팩스")
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.resize(1080, 720)
        self.folder = folder or ""

        v = QVBoxLayout(self)

        top = QHBoxLayout()
        self.lbl_where = QLabel("")
        self.lbl_where.setStyleSheet(f"color:{theme.c('subtext')};")
        top.addWidget(self.lbl_where, 1)
        self.btn_reload = QPushButton("새로고침")
        self.btn_reload.clicked.connect(self.reload)
        top.addWidget(self.btn_reload)
        self.btn_folder = QPushButton("폴더 열기")
        self.btn_folder.clicked.connect(self._open_folder)
        top.addWidget(self.btn_folder)
        v.addLayout(top)

        split = QSplitter(Qt.Horizontal)
        self.lst = QListWidget()
        self.lst.setSelectionMode(QAbstractItemView.SingleSelection)
        self.lst.currentRowChanged.connect(self._on_pick)
        split.addWidget(self.lst)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 0, 0, 0)
        # 보고 있는 팩스를 바로 카카오톡으로 넘길 수 있게 한다(고객정보와 같은 방식)
        self.pv = FilePreview(on_send=self.copy_current)
        rv.addWidget(self.pv, 1)
        self.btn_open = QPushButton("연결 프로그램으로 열기")
        self.btn_open.clicked.connect(self._open_current)
        rv.addWidget(self.btn_open)
        split.addWidget(right)
        split.setSizes([320, 760])
        v.addWidget(split, 1)

        self._items: list = []
        self.reload()

    # ------------------------------------------------------------ 목록
    def reload(self, pick: str = ""):
        """폴더를 다시 읽어 목록을 채운다. pick 을 주면 그 파일을 고른다."""
        self._items = fax_watch.FaxFolder(self.folder).recent()
        self.lst.blockSignals(True)
        self.lst.clear()
        for name, info in self._items:
            self.lst.addItem(QListWidgetItem(fax_watch.label(name, info)))
        self.lst.blockSignals(False)
        if not self._items:
            self.lbl_where.setText(
                f"받은 팩스가 없습니다 — {self.folder}" if self.folder
                else "받은팩스 폴더가 지정되지 않았습니다 ([설정] 에서 지정)")
            self.pv.show_message("받은 팩스가 없습니다.")
            return
        self.lbl_where.setText(f"{len(self._items):,}건 · {self.folder}")
        row = 0
        if pick:
            for i, (name, _info) in enumerate(self._items):
                if name == pick:
                    row = i
                    break
        self.lst.setCurrentRow(row)

    def _on_pick(self, row: int):
        name = self._name_at(row)
        if not name:
            return
        path = os.path.join(self.folder, name)
        try:
            with open(path, "rb") as fp:
                data = fp.read()
        except OSError as e:
            self.pv.show_message(f"팩스를 읽지 못했습니다:\n{e}", name)
            return
        if os.path.splitext(name)[1].lower() == ".pdf":
            self.pv.show_pdf(data, path, name)
        else:
            self.pv.show_image(data, path, name)

    def _name_at(self, row: int) -> str:
        if 0 <= row < len(self._items):
            return self._items[row][0]
        return ""

    def current_path(self) -> str:
        name = self._name_at(self.lst.currentRow())
        return os.path.join(self.folder, name) if name else ""

    # ------------------------------------------------------------ 내보내기
    def copy_current(self):
        """보고 있는 팩스를 클립보드에 파일로 올린다 (카톡에 Ctrl+V)."""
        path = self.current_path()
        if not path or not os.path.exists(path):
            return
        QApplication.clipboard().setMimeData(file_mime([path]))

    def _open_current(self):
        path = self.current_path()
        if not path:
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)          # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            QMessageBox.warning(self, config.APP_NAME, "열지 못했습니다:\n" + str(e))

    def _open_folder(self):
        if not self.folder:
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(self.folder)   # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", self.folder])
            else:
                subprocess.Popen(["xdg-open", self.folder])
        except Exception:
            pass

    def apply_theme(self):
        self.lbl_where.setStyleSheet(f"color:{theme.c('subtext')};")
        self.pv.apply_theme()

    def closeEvent(self, event):
        if FaxWindow._open is self:
            FaxWindow._open = None
        super().closeEvent(event)


def show_for(folder: str, pick: str = "", parent=None) -> "FaxWindow | None":
    """팩스 보기 창을 띄운다(이미 떠 있으면 그걸 앞으로).

    창을 여러 개 쌓지 않는다 — 팩스가 여러 건 와도 목록 하나로 보는 편이 낫다.
    """
    if not folder:
        QMessageBox.information(
            parent, config.APP_NAME,
            "받은팩스 폴더가 지정되지 않았습니다.\n"
            "[설정] → '받은팩스 폴더' 를 지정해 주세요.")
        return None
    w = FaxWindow._open
    if w is None:
        w = FaxWindow(folder, parent)
        FaxWindow._open = w
        w.show()
    else:
        if w.folder != folder:
            w.folder = folder
        w.reload(pick)
        w.show()
    if pick:
        w.reload(pick)
    w.raise_()
    w.activateWindow()
    return w
