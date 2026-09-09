"""'고객정보' 탭 — 고객별 서류를 드라이브처럼 눌러서 찾아본다.

화면은 폴더 한 겹만 읽는다(customer_files.children). 그래서 창고가 아무리 커도
첫 화면이 바로 뜬다. 예전엔 켤 때마다 트리 전체를 훑어서 드라이브 폴더가 크면
한참 멈춰 있었다.

검색은 트리 전체를 봐야 하므로 뒤에서 조용히 훑어 둔다(scan). 훑는 동안에도
폴더를 눌러 다니는 데는 지장이 없고, 다 되면 그때부터 검색이 먹는다.

폴더가 바뀌었는지는 잠깐씩 다시 읽어 견준다. 사무실에서 넣은 서류가 집 PC 에
동기화되면 [새로고침] 을 누르지 않아도 목록에 나타난다.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget)

from . import config, customer_files, theme
from .file_preview import FilePreview

# 목록 맨 윗줄에 놓는 '상위 폴더로' 자리. 진짜 파일이 아니라 표시용 표식이다.
UP_ROW = "<<up>>"

# 폴더가 바뀌었는지 다시 읽어 보는 간격(초).
# 로컬 폴더는 싸니까 자주, 드라이브 API 는 네트워크를 타니까 드물게.
POLL_LOCAL = 5
POLL_DRIVE = 45


def _one_line(text: str) -> str:
    s = " ".join((text or "").split())
    return s if len(s) <= 90 else s[:88] + "…"


class CustomerFilesTab(QWidget):
    """고객 서류 찾아보기."""

    sig_listed = Signal(object, str)           # (Node 목록|None, "세대\0오류")
    sig_indexed = Signal(object, str)          # (Node 목록|None, 오류)
    sig_preview = Signal(object, object, str)  # (Node, bytes|None, 오류)

    COLS = ["이름", "크기", "날짜"]
    WIDTHS = [420, 100, 110]
    SEARCH_COLS = ["이름", "위치", "크기", "날짜"]
    SEARCH_WIDTHS = [300, 280, 100, 110]

    def __init__(self, settings, auth, parent=None):
        super().__init__(parent)
        self._settings = settings
        self.auth = auth
        self.source = None
        self.path: list = []          # 맨 위 폴더부터 지금 보고 있는 폴더까지
        self.rows: list = []          # 지금 표에 있는 것들(맨 위 '상위로' 제외)
        self.index = None             # 검색용 전체 목록(뒤에서 만든다)
        self._indexing = False
        self._listing = False
        self._gen = 0
        self._sig = None              # 지금 폴더의 요약값(바뀜 감지)
        self._preview_key = ""

        v = QVBoxLayout(self)

        # ---- 위: 지금 어디를 보고 있나 ----
        top = QHBoxLayout()
        self.btn_up = QPushButton("⬆ 상위 폴더")
        self.btn_up.clicked.connect(self.go_up)
        self.btn_up.setEnabled(False)
        top.addWidget(self.btn_up)
        self.lbl_where = QLabel("")
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
        self.ed_search.setPlaceholderText(
            "고객명 · 폴더명 · 파일명 — 전체에서 찾습니다 (초성도 됩니다)")
        self.ed_search.setClearButtonEnabled(True)
        self.ed_search.textChanged.connect(self._on_search_changed)
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
        # 남는 폭은 '이름' 이 받는다. 마지막 칸(날짜)을 늘리면 날짜가 허옇게
        # 넓어지고 정작 긴 폴더 이름이 잘린다.
        self.tbl.horizontalHeader().setStretchLastSection(False)
        self.tbl.itemSelectionChanged.connect(self._on_select)
        self.tbl.doubleClicked.connect(self._on_double)
        self._cols = []
        self._set_columns(self.COLS, self.WIDTHS)
        self.split.addWidget(self.tbl)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 0, 0, 0)
        self.pv = FilePreview()
        rv.addWidget(self.pv, 1)
        self.btn_open = QPushButton("연결 프로그램으로 열기")
        self.btn_open.setEnabled(False)
        self.btn_open.clicked.connect(self._open_current)
        rv.addWidget(self.btn_open)
        self.split.addWidget(right)
        self.split.setSizes([820, 340])
        v.addWidget(self.split, 1)

        self.sig_listed.connect(self._on_listed)
        self.sig_indexed.connect(self._on_indexed)
        self.sig_preview.connect(self._on_preview)

        # 뒤에서 조용히 다시 읽어 바뀐 게 있으면 반영한다
        self._poll = QTimer(self)
        self._poll.timeout.connect(self._poll_tick)

        self.apply_theme()
        self._update_where()

    # ⚠️ 설정을 '복사해 두면' 안 된다 — 로그인하면 창이 설정 객체를 통째로 새로
    # 읽는다(reload_data). 예전엔 이 탭이 옛 객체를 붙들어, 폴더를 지정해도
    # 늘 '0건' 이었다. 그래서 늘 창이 지금 쓰는 설정을 본다.
    @property
    def settings(self):
        w = self.window()
        if w is not self:
            s = getattr(w, "settings", None)
            if s is not None:
                return s
        return self._settings

    def set_settings(self, s):
        self._settings = s

    # ------------------------------------------------------------ 폴더 지정
    def pick_folder(self):
        start = self.settings.files_dir or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, "고객정보 폴더 선택", start)
        if not d:
            return
        self.settings.files_dir = d
        self._settings.files_dir = d
        w = self.window()
        if hasattr(w, "_save_settings"):
            w._save_settings()
        self.reload()

    # ------------------------------------------------------------ 읽기
    def reload(self):
        """창고를 다시 잡고 맨 위 폴더부터 보여 준다."""
        self.source, why = customer_files.pick_source(self.settings, self.auth)
        self.index = None                  # 창고가 바뀌면 검색 목록도 버린다
        self._sig = None
        if self.source is None:
            self._poll.stop()
            self._listing = False
            self.btn_reload.setEnabled(True)
            self.path = []
            self.rows = []
            self._fill([])
            self.lbl_count.setText("읽을 곳 없음")
            self.lbl_where.setText("자료를 읽을 곳이 없습니다 — " + _one_line(why))
            self.lbl_where.setToolTip(why)
            self.lbl_where.setStyleSheet(f"color:{theme.c('status_bad')};")
            self.btn_up.setEnabled(False)
            return
        self.lbl_where.setStyleSheet("")
        self.ed_search.blockSignals(True)
        self.ed_search.clear()
        self.ed_search.blockSignals(False)
        self._open_root()

    def _open_root(self):
        try:
            root = self.source.root_node()
        except Exception as e:
            self.lbl_count.setText("읽기 실패")
            QMessageBox.warning(self, config.APP_NAME,
                                "창고를 열지 못했습니다:\n" + str(e))
            return
        self.path = [root]
        self._list_current(quiet=False)

    def go_up(self):
        if len(self.path) <= 1:
            return
        self.path.pop()
        self._list_current(quiet=False)

    def _enter(self, node):
        self.path.append(node)
        self._list_current(quiet=False)

    def _list_current(self, quiet: bool):
        """지금 폴더 한 겹만 읽는다. quiet 면 화면을 흔들지 않는다."""
        if not self.path or self.source is None:
            return
        node = self.path[-1]
        self._gen += 1
        gen = self._gen
        # quiet 여부와 상관없이 '읽는 중' 으로 잡아 둔다. 안 그러면 조용한
        # 갱신끼리 겹쳐 돌고, 끝나기 전에 다음 폴링이 또 들어온다.
        self._listing = True
        if not quiet:
            self.btn_reload.setEnabled(False)
            self.lbl_count.setText("읽는 중…")
            self._update_where()
        src = self.source

        def worker():
            # 무슨 일이 있어도 답을 한 번은 보낸다 — 안 보내면 단추가 잠긴 채 남는다
            try:
                got = src.children(node)
            except Exception as e:
                self.sig_listed.emit(None, f"{gen}\x00{e}")
            else:
                self.sig_listed.emit(got, f"{gen}\x00")

        threading.Thread(target=worker, daemon=True).start()

    def _on_listed(self, nodes, err: str):
        gen, _, msg = (err or "").partition("\x00")
        if gen.isdigit() and int(gen) != self._gen:
            return                      # 늦게 온 예전 결과는 버린다
        self._listing = False
        self.btn_reload.setEnabled(True)
        if nodes is None:
            self.lbl_count.setText("읽기 실패")
            QMessageBox.warning(self, config.APP_NAME,
                                "폴더를 읽지 못했습니다:\n" + msg)
            return
        sig = customer_files.signature(nodes)
        changed = (sig != self._sig)
        self._sig = sig
        self.rows = customer_files.sort_nodes(nodes)
        if self.ed_search.text().strip():
            return                      # 검색 중이면 화면은 검색 결과를 지킨다
        if changed:
            self._show_browse()
        self._start_poll()

    def _show_browse(self):
        keep = self._selected_name()
        self._set_columns(self.COLS, self.WIDTHS)
        self._fill(self.rows, up=len(self.path) > 1)
        self.btn_up.setEnabled(len(self.path) > 1)
        self._update_where()
        n_dir = sum(1 for n in self.rows if n.is_dir)
        n_file = len(self.rows) - n_dir
        if not self.rows:
            self.lbl_count.setText("빈 폴더")
        else:
            self.lbl_count.setText(f"폴더 {n_dir} · 파일 {n_file}")
        self._restore_selection(keep)

    # ---- 바뀐 것 자동 반영 ----
    def _start_poll(self):
        if self.source is None:
            self._poll.stop()
            return
        sec = POLL_DRIVE if self.source.kind == "drive" else POLL_LOCAL
        self._poll.start(sec * 1000)

    def _poll_tick(self):
        # 이미 읽는 중이거나 창이 안 보이면 건너뛴다 — 괜히 일하지 않는다
        if self._listing or not self.isVisible() or self.source is None:
            return
        if self.ed_search.text().strip():
            return                      # 검색 중에는 화면을 흔들지 않는다
        self._list_current(quiet=True)

    # ------------------------------------------------------------ 검색
    def _on_search_changed(self):
        q = self.ed_search.text().strip()
        if not q:
            self._show_browse()
            return
        if self.index is None:
            self._ensure_index()
            self.lbl_count.setText("전체를 훑는 중…")
            return
        self._show_search(q)

    def search_for(self, text: str):
        """고객관리에서 '이 고객 서류 보기' 로 넘어올 때 쓴다."""
        self.ed_search.setText(text or "")
        self.ed_search.setFocus()

    def _ensure_index(self):
        """검색용 전체 목록을 뒤에서 만든다(한 번만)."""
        if self._indexing or self.source is None:
            return
        self._indexing = True
        src = self.source

        def worker():
            try:
                self.sig_indexed.emit(src.scan(), "")
            except Exception as e:
                self.sig_indexed.emit(None, str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_indexed(self, nodes, err: str):
        self._indexing = False
        if nodes is None:
            self.lbl_count.setText("검색 준비 실패")
            return
        self.index = customer_files.sort_nodes(nodes)
        q = self.ed_search.text().strip()
        if q:
            self._show_search(q)

    def _show_search(self, q: str):
        hits = customer_files.search(self.index or [], q)
        self._set_columns(self.SEARCH_COLS, self.SEARCH_WIDTHS)
        self._fill(hits, up=False, with_where=True)
        self.btn_up.setEnabled(False)
        self.lbl_count.setText(f"{len(hits):,} / {len(self.index or []):,}건")
        self.lbl_where.setText("검색 결과 — 전체에서 찾았습니다")

    # ------------------------------------------------------------ 표
    def _set_columns(self, cols, widths):
        if self._cols == list(cols):
            return
        self._cols = list(cols)
        self.tbl.setColumnCount(len(cols))
        self.tbl.setHorizontalHeaderLabels(list(cols))
        hdr = self.tbl.horizontalHeader()
        for i, wpx in enumerate(widths):
            self.tbl.setColumnWidth(i, wpx)
            hdr.setSectionResizeMode(i, QHeaderView.Interactive)
        # '이름' 이 남는 폭을 받아 긴 폴더 이름이 안 잘리게 한다
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)

    def _fill(self, rows: list, up: bool = False, with_where: bool = False):
        self.tbl.setRowCount(0)
        self._view = ([UP_ROW] if up else []) + list(rows)
        self.tbl.setRowCount(len(self._view))
        for r, n in enumerate(self._view):
            if n is UP_ROW:
                it = QTableWidgetItem("⬆  ..  (상위 폴더로)")
                it.setToolTip("두 번 누르면 상위 폴더로 올라갑니다")
                self.tbl.setItem(r, 0, it)
                for c in range(1, self.tbl.columnCount()):
                    self.tbl.setItem(r, c, QTableWidgetItem(""))
                continue
            name = ("📁 " if n.is_dir else "") + n.name
            cells = ([name, n.where, n.size_text(), n.date_text()]
                     if with_where else [name, n.size_text(), n.date_text()])
            right = {2, 3} if with_where else {1, 2}   # 크기·날짜만 오른쪽 정렬
            for c, text in enumerate(cells):
                it = QTableWidgetItem(text)
                if c in right:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if c == 0:
                    it.setToolTip(f"{n.where}/{n.name}" if n.where else n.name)
                self.tbl.setItem(r, c, it)

    def _current(self):
        r = self.tbl.currentRow()
        view = getattr(self, "_view", [])
        if r < 0 or r >= len(view):
            return None
        n = view[r]
        return None if n is UP_ROW else n

    def _selected_name(self) -> str:
        n = self._current()
        return n.name if n else ""

    def _restore_selection(self, name: str):
        if not name:
            return
        for r, n in enumerate(getattr(self, "_view", [])):
            if n is not UP_ROW and n.name == name:
                self.tbl.selectRow(r)
                return

    def _update_where(self):
        if self.source is None:
            self.lbl_where.setText("자료를 읽을 곳이 없습니다 — [폴더 선택]")
            return
        if not self.path:
            return
        # 지나온 길을 그대로 보여 준다 — 드라이브 주소줄처럼
        crumbs = " / ".join(n.name for n in self.path)
        self.lbl_where.setText(crumbs)
        self.lbl_where.setToolTip(
            getattr(self.source, "root", "") or self.settings.files_drive_folder)

    # ------------------------------------------------------------ 미리보기
    def _on_select(self):
        n = self._current()
        self.btn_open.setEnabled(bool(n) and not n.is_dir
                                 and self.source is not None
                                 and self.source.kind == "local")
        if n is None:
            return
        title = f"{n.where}/{n.name}" if n.where else n.name
        if n.is_dir:
            self._preview_key = ""
            self.pv.show_message("폴더입니다. 두 번 누르면 들어갑니다.", title)
            return
        if not n.viewable:
            self._preview_key = ""
            self.pv.show_message(
                "미리보기를 지원하지 않는 형식입니다.\n"
                "[연결 프로그램으로 열기] 를 눌러 주세요.", title)
            return
        self.pv.show_message("여는 중…", title)
        self._preview_key = n.key
        src = self.source

        def worker():
            try:
                self.sig_preview.emit(n, src.read_bytes(n), "")
            except Exception as e:
                self.sig_preview.emit(n, None, str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_preview(self, node, data, err: str):
        if node.key != self._preview_key:
            return                      # 그새 딴 걸 골랐다
        title = f"{node.where}/{node.name}" if node.where else node.name
        if data is None:
            self.pv.show_message("미리보기 실패:\n" + err, title)
            return
        if node.is_pdf:
            self.pv.show_pdf(data, node.key, title)
        else:
            self.pv.show_image(data, node.key, title)

    # ------------------------------------------------------------ 열기
    def _on_double(self, index):
        view = getattr(self, "_view", [])
        r = index.row()
        if 0 <= r < len(view) and view[r] is UP_ROW:
            self.go_up()
            return
        n = self._current()
        if n is None:
            return
        if n.is_dir:
            # 검색 결과에서 폴더를 누르면 그 폴더로 들어간다
            if self.ed_search.text().strip():
                self.ed_search.blockSignals(True)
                self.ed_search.clear()
                self.ed_search.blockSignals(False)
                self._goto_rel(n)
                return
            self._enter(n)
            return
        self._open_current()

    def _goto_rel(self, node):
        """검색 결과에서 고른 폴더로 곧장 옮겨간다(로컬만 길을 되짚을 수 있다)."""
        up = getattr(self.source, "parent_of", None)
        chain = [node]
        cur = node
        while up is not None:
            parent = self.source.parent_of(cur)
            if parent is None:
                break
            chain.append(parent)
            cur = parent
        chain.reverse()
        if chain and self.path:
            root = self.path[0]
            self.path = [root] + [c for c in chain if c.key != root.key]
        self._list_current(quiet=False)

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
        self.pv.apply_theme()
