"""'고객정보' 탭 — 고객별 서류를 찾아 보는 화면.

자료가 어디서 오는지는 customer_files 가 정한다(로컬 폴더 우선, 드라이브 API
는 켠 사람만). 이 파일은 그 목록을 보여 주고 찾아 주는 일만 한다.

훑기(scan)는 딴 실에서 돈다 — 폴더가 크면 몇 초 걸리는데 그동안 창이 멈추면
안 되기 때문이다. 끝나면 시그널로 화면 실에 돌아온다.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget)

from . import config, customer_files, searchcombo, theme

_ = searchcombo   # 다른 탭과 같은 검색 위젯 관례를 따르기 위한 자리(미사용)


class CustomerFilesTab(QWidget):
    """고객 서류 찾아보기."""

    sig_scanned = Signal(object, str)     # (Node 목록|None, 오류)
    sig_preview = Signal(object, object, str)  # (Node, bytes|None, 오류)

    COLS = ["이름", "위치", "크기", "날짜"]
    WIDTHS = [300, 300, 90, 100]

    def __init__(self, settings, auth, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.auth = auth
        self.nodes: list = []
        self.source = None
        self._scanning = False
        self._preview_key = ""

        v = QVBoxLayout(self)

        # ---- 위: 어디를 보고 있는지 + 다시 읽기 ----
        top = QHBoxLayout()
        self.lbl_where = QLabel("")
        self.lbl_where.setWordWrap(False)
        top.addWidget(self.lbl_where, 1)
        self.btn_pick = QPushButton("폴더 선택")
        self.btn_pick.setToolTip(
            "구글 드라이브 데스크톱이 내려받아 둔 '고객정보' 폴더를 고르세요")
        self.btn_pick.clicked.connect(self.pick_folder)
        top.addWidget(self.btn_pick)
        self.btn_reload = QPushButton("새로고침")
        self.btn_reload.clicked.connect(self.reload)
        top.addWidget(self.btn_reload)
        v.addLayout(top)

        # ---- 검색 ----
        srow = QHBoxLayout()
        srow.addWidget(QLabel("검색:"))
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("고객명 · 폴더명 · 파일명  (초성도 됩니다)")
        self.ed_search.setClearButtonEnabled(True)
        self.ed_search.textChanged.connect(self._apply_filter)
        srow.addWidget(self.ed_search, 1)
        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet(f"color:{theme.c('subtext')};")
        srow.addWidget(self.lbl_count)
        v.addLayout(srow)

        # ---- 목록 + 미리보기 ----
        self.split = QSplitter(Qt.Horizontal)
        self.tbl = QTableWidget(0, len(self.COLS))
        self.tbl.setHorizontalHeaderLabels(self.COLS)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.verticalHeader().setDefaultSectionSize(30)
        for i, wpx in enumerate(self.WIDTHS):
            self.tbl.setColumnWidth(i, wpx)
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Interactive)
        self.tbl.itemSelectionChanged.connect(self._on_select)
        self.tbl.doubleClicked.connect(self._on_double)
        self.split.addWidget(self.tbl)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 0, 0, 0)
        self.lbl_pv_title = QLabel("")
        self.lbl_pv_title.setWordWrap(True)
        self.lbl_pv_title.setStyleSheet("font-weight:bold;")
        rv.addWidget(self.lbl_pv_title)
        self.lbl_pv = QLabel("파일을 고르면 여기에 보입니다.")
        self.lbl_pv.setAlignment(Qt.AlignCenter)
        self.lbl_pv.setMinimumSize(QSize(240, 240))
        self.lbl_pv.setStyleSheet(
            f"color:{theme.c('subtext')};border:1px solid {theme.c('border')};"
            f"border-radius:6px;")
        rv.addWidget(self.lbl_pv, 1)
        self.btn_open = QPushButton("연결 프로그램으로 열기")
        self.btn_open.setEnabled(False)
        self.btn_open.clicked.connect(self._open_current)
        rv.addWidget(self.btn_open)
        self.split.addWidget(right)
        self.split.setSizes([760, 360])
        v.addWidget(self.split, 1)

        self.sig_scanned.connect(self._on_scanned)
        self.sig_preview.connect(self._on_preview)
        self._update_where()

    # ------------------------------------------------------------ 폴더 지정
    def pick_folder(self):
        start = self.settings.files_dir or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, "고객정보 폴더 선택", start)
        if not d:
            return
        self.settings.files_dir = d
        self._save_settings()
        self.reload()

    def _save_settings(self):
        w = self.window()
        if hasattr(w, "_save_settings"):
            w._save_settings()

    # ------------------------------------------------------------ 읽기
    def reload(self):
        if self._scanning:
            return
        self.source, why = customer_files.pick_source(self.settings, self.auth)
        self._update_where()
        if self.source is None:
            self.nodes = []
            self._fill([])
            self.lbl_count.setText("")
            self.lbl_where.setText("자료를 읽을 곳이 없습니다 — [폴더 선택]")
            self.lbl_where.setToolTip(why)
            return
        self._scanning = True
        self.btn_reload.setEnabled(False)
        self.lbl_count.setText("읽는 중…")
        src = self.source

        def worker():
            try:
                self.sig_scanned.emit(src.scan(), "")
            except Exception as e:
                self.sig_scanned.emit(None, str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_scanned(self, nodes, err: str):
        self._scanning = False
        self.btn_reload.setEnabled(True)
        if nodes is None:
            self.lbl_count.setText("")
            QMessageBox.warning(self, config.APP_NAME, "자료를 읽지 못했습니다:\n" + err)
            return
        self.nodes = customer_files.sort_nodes(nodes)
        self._apply_filter()

    def _update_where(self):
        src = self.source
        if src is None:
            src, _why = customer_files.pick_source(self.settings, self.auth)
        if src is None:
            self.lbl_where.setText("자료를 읽을 곳이 없습니다 — [폴더 선택]")
            return
        if src.kind == "local":
            self.lbl_where.setText(f"폴더: {src.root}")
            self.lbl_where.setToolTip(src.root)
        else:
            name = self.settings.files_drive_folder or "(폴더 미지정)"
            self.lbl_where.setText(f"구글 드라이브: {name}")
            self.lbl_where.setToolTip("드라이브에서 직접 조회하고 있습니다")

    def search_for(self, text: str):
        """다른 탭에서 '이 고객 서류 보기' 로 넘어올 때 쓴다."""
        self.ed_search.setText(text or "")
        self.ed_search.setFocus()

    # ------------------------------------------------------------ 검색·표시
    def _apply_filter(self):
        rows = customer_files.search(self.nodes, self.ed_search.text())
        self._fill(rows)
        total = len(self.nodes)
        if len(rows) == total:
            self.lbl_count.setText(f"{total:,}건")
        else:
            self.lbl_count.setText(f"{len(rows):,} / {total:,}건")

    def _fill(self, rows: list):
        self.tbl.setRowCount(0)
        self._rows = list(rows)
        self.tbl.setRowCount(len(rows))
        for r, n in enumerate(rows):
            name = ("📁 " if n.is_dir else "") + n.name
            for c, text in enumerate(
                    (name, n.where, n.size_text(), n.date_text())):
                it = QTableWidgetItem(text)
                if c in (2, 3):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if c == 0:
                    it.setToolTip(f"{n.where}/{n.name}" if n.where else n.name)
                self.tbl.setItem(r, c, it)

    def _current(self):
        r = self.tbl.currentRow()
        if r < 0 or r >= len(getattr(self, "_rows", [])):
            return None
        return self._rows[r]

    # ------------------------------------------------------------ 미리보기
    def _on_select(self):
        n = self._current()
        self.btn_open.setEnabled(bool(n) and not n.is_dir
                                 and self.source is not None
                                 and self.source.kind == "local")
        if n is None:
            return
        self.lbl_pv_title.setText(f"{n.where}/{n.name}" if n.where else n.name)
        if n.is_dir:
            self.lbl_pv.setPixmap(QPixmap())
            self.lbl_pv.setText("폴더입니다. 두 번 누르면 이 폴더만 봅니다.")
            return
        if not n.is_image:
            self.lbl_pv.setPixmap(QPixmap())
            self.lbl_pv.setText(
                "PDF 는 미리보기가 없습니다.\n[연결 프로그램으로 열기] 를 눌러 주세요."
                if n.is_pdf else "미리보기를 지원하지 않는 형식입니다.")
            return
        self.lbl_pv.setPixmap(QPixmap())
        self.lbl_pv.setText("여는 중…")
        self._preview_key = n.key
        src = self.source

        def worker():
            try:
                self.sig_preview.emit(n, src.read_bytes(n), "")
            except Exception as e:
                self.sig_preview.emit(n, None, str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_preview(self, node, data, err: str):
        # 고르고 나서 딴 걸 고르면 늦게 온 그림이 덮어쓰지 않게 한다
        if node.key != self._preview_key:
            return
        if data is None:
            self.lbl_pv.setText("미리보기 실패:\n" + err)
            return
        pix = QPixmap()
        if not pix.loadFromData(data):
            self.lbl_pv.setText("그림을 읽지 못했습니다.")
            return
        self._show_pix(pix)

    def _show_pix(self, pix: QPixmap):
        self._pix = pix
        box = self.lbl_pv.size()
        self.lbl_pv.setText("")
        self.lbl_pv.setPixmap(pix.scaled(box, Qt.KeepAspectRatio,
                                         Qt.SmoothTransformation))

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if getattr(self, "_pix", None) and not self._pix.isNull():
            self._show_pix(self._pix)

    # ------------------------------------------------------------ 열기
    def _on_double(self, index):
        n = self._current()
        if n is None:
            return
        if n.is_dir:
            # 그 폴더만 보도록 검색칸에 폴더 이름을 넣어 준다
            self.ed_search.setText(n.name)
            return
        self._open_current()

    def _open_current(self):
        n = self._current()
        if n is None or n.is_dir or self.source is None:
            return
        path = self.source.local_path(n)
        if not path:
            QMessageBox.information(
                self, config.APP_NAME,
                "드라이브에서 직접 조회한 파일은 연결 프로그램으로 열 수 없습니다.\n"
                "폴더를 지정해 두면 PC 에 내려받아 둔 파일을 바로 열 수 있습니다.")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)          # noqa: S606  (윈도 기본 동작)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            QMessageBox.warning(self, config.APP_NAME, "열지 못했습니다:\n" + str(e))

    # ------------------------------------------------------------ 테마
    def apply_theme(self):
        self.lbl_count.setStyleSheet(f"color:{theme.c('subtext')};")
        self.lbl_pv.setStyleSheet(
            f"color:{theme.c('subtext')};border:1px solid {theme.c('border')};"
            f"border-radius:6px;")
