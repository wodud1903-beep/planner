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

from PySide6.QtCore import QBuffer, QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QFileDialog, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from . import config, customer_files, file_ops, theme
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
    sig_index_progress = Signal(int)           # 훑는 중 몇 건까지 왔나
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
        self._partial: list = []      # 아직 훑는 중일 때 지금까지 찾은 것
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
        # 오른쪽 단추 메뉴 · 바깥에서 끌어다 놓기
        self.tbl.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tbl.customContextMenuRequested.connect(self._menu)
        self.tbl.setAcceptDrops(True)
        self.tbl.setDragDropMode(QAbstractItemView.DropOnly)
        self.tbl.viewport().setAcceptDrops(True)
        self.tbl.installEventFilter(self)
        self.tbl.viewport().installEventFilter(self)
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
        self.sig_index_progress.connect(self._on_index_progress)
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
        self._partial = []
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
        # 검색은 트리 전체를 봐야 한다. 사용자가 글자를 칠 때까지 기다리지 말고
        # 지금부터 뒤에서 훑어 둔다 — 예전엔 첫 글자를 친 뒤에야 시작해서
        # '훑는 중' 을 한참 기다려야 했다.
        self._ensure_index()

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
        self._ensure_index()
        # 아직 다 못 훑었어도 지금까지 찾은 것으로 바로 보여 준다.
        # 기다리게 하지 않는 편이 낫고, 대개 찾는 것은 이미 그 안에 있다.
        self._show_search(q)

    def search_for(self, text: str):
        """고객관리에서 '이 고객 서류 보기' 로 넘어올 때 쓴다."""
        self.ed_search.setText(text or "")
        self.ed_search.setFocus()

    def _ensure_index(self):
        """검색용 전체 목록을 뒤에서 만든다(한 번만).

        폴더 하나를 끝낼 때마다 중간 결과를 받아 두어서, 다 끝나기 전에도
        검색이 먹는다.
        """
        if self._indexing or self.index is not None or self.source is None:
            return
        self._indexing = True
        self._partial = []
        src = self.source

        def worker():
            try:
                def batch(got):
                    # 목록은 계속 자라므로 그때그때 복사해 넘긴다
                    self._partial = list(got)
                    self.sig_index_progress.emit(len(got))
                self.sig_indexed.emit(src.scan(on_batch=batch), "")
            except Exception as e:
                self.sig_indexed.emit(None, str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_index_progress(self, n: int):
        if not self.ed_search.text().strip():
            return
        self._show_search(self.ed_search.text().strip(), partial=True)

    def _on_indexed(self, nodes, err: str):
        self._indexing = False
        if nodes is None:
            self.lbl_count.setText("검색 준비 실패")
            return
        self.index = customer_files.sort_nodes(nodes)
        q = self.ed_search.text().strip()
        if q:
            self._show_search(q)

    def _show_search(self, q: str, partial: bool = False):
        pool = self.index if self.index is not None else self._partial
        hits = customer_files.search(pool, q)
        self._set_columns(self.SEARCH_COLS, self.SEARCH_WIDTHS)
        self._fill(hits, up=False, with_where=True)
        self.btn_up.setEnabled(False)
        if self.index is None:
            self.lbl_count.setText(f"{len(hits):,}건 (훑는 중 {len(pool):,})")
            self.lbl_where.setText("검색 결과 — 아직 훑는 중이라 더 나올 수 있습니다")
        else:
            self.lbl_count.setText(f"{len(hits):,} / {len(pool):,}건")
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


    # ---------------------------------------------------------------- 파일 넣고 빼기
    #
    # 여기 있는 일은 전부 로컬 폴더에만 한다. 드라이브를 API 로 직접 조회하는
    # 모드는 읽기 권한(drive.readonly)뿐이라 고칠 수 없다.
    def _can_edit(self) -> bool:
        return self.source is not None and self.source.kind == "local"

    def _cur_dir(self) -> str:
        """지금 보고 있는 폴더의 실제 경로. 없으면 빈 값."""
        if not self._can_edit() or not self.path:
            return ""
        return self.path[-1].key

    def _no_edit_msg(self):
        QMessageBox.information(
            self, config.APP_NAME,
            "드라이브에서 직접 조회하는 중에는 파일을 고칠 수 없습니다.\n"
            "[설정] 에서 서류 폴더를 지정하면 넣고 뺄 수 있습니다.")

    def eventFilter(self, obj, ev):
        """끌어다 놓기와 Ctrl+V·Delete 를 표에서 받는다."""
        t = ev.type()
        if t == QEvent.KeyPress:
            if ev.matches(QKeySequence.Paste):
                self.paste_clipboard()
                return True
            if ev.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                self.delete_selected()
                return True
            if ev.key() == Qt.Key_F2:
                self.rename_selected()
                return True
        elif t in (QEvent.DragEnter, QEvent.DragMove):
            if ev.mimeData().hasUrls() and self._can_edit():
                ev.acceptProposedAction()
                return True
        elif t == QEvent.Drop:
            if ev.mimeData().hasUrls():
                self._drop_files(ev.mimeData().urls())
                ev.acceptProposedAction()
                return True
        return super().eventFilter(obj, ev)

    def _drop_files(self, urls):
        if not self._can_edit():
            self._no_edit_msg()
            return
        folder = self._cur_dir()
        paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
        paths = [p for p in paths if p]
        if not folder or not paths:
            return
        done, failed = file_ops.copy_in(paths, folder)
        self._after_change(f"{len(done)}건을 넣었습니다.", failed)

    def paste_clipboard(self):
        """Ctrl+V — 카톡에서 복사한 그림이나, 탐색기에서 복사한 파일을 넣는다."""
        if not self._can_edit():
            self._no_edit_msg()
            return
        folder = self._cur_dir()
        if not folder:
            return
        md = QGuiApplication.clipboard().mimeData()
        # 1) 탐색기에서 '복사' 한 파일들
        if md.hasUrls():
            paths = [u.toLocalFile() for u in md.urls() if u.isLocalFile()]
            paths = [p for p in paths if p]
            if paths:
                done, failed = file_ops.copy_in(paths, folder)
                self._after_change(f"{len(done)}건을 넣었습니다.", failed)
                return
        # 2) 카카오톡 등에서 복사한 그림 — 이름을 물어보고 저장한다
        if md.hasImage():
            img = QGuiApplication.clipboard().image()
            if img.isNull():
                return
            name, okp = QInputDialog.getText(
                self, "그림 붙여넣기",
                "저장할 파일 이름을 적어 주세요.\n(확장자를 안 적으면 .png 로 저장합니다)",
                text=self._suggest_name())
            if not okp:
                return
            try:
                name = file_ops.with_ext(name.strip(), ".png")
                buf = QBuffer()
                buf.open(QBuffer.WriteOnly)
                fmt = os.path.splitext(name)[1].lstrip(".").upper() or "PNG"
                if fmt in ("JPG", "JPEG"):
                    fmt = "JPG"
                elif fmt not in ("PNG", "BMP"):
                    fmt = "PNG"
                    name = os.path.splitext(name)[0] + ".png"
                img.save(buf, fmt)
                path = file_ops.save_bytes(bytes(buf.data()), folder, name)
            except file_ops.OpError as e:
                QMessageBox.warning(self, config.APP_NAME, str(e))
                return
            self._after_change(f"{os.path.basename(path)} 을(를) 저장했습니다.", [])
            return
        QMessageBox.information(
            self, config.APP_NAME,
            "붙여넣을 그림이나 파일이 없습니다.\n"
            "카카오톡에서 사진을 복사하거나, 탐색기에서 파일을 복사한 뒤 눌러 주세요.")

    def _suggest_name(self) -> str:
        """지금 폴더 이름을 따서 기본 파일 이름을 제안한다."""
        from datetime import date
        base = self.path[-1].name if len(self.path) > 1 else "서류"
        return f"{base} {date.today():%m%d}.png"

    def delete_selected(self):
        n = self._current()
        if n is None:
            return
        if not self._can_edit():
            self._no_edit_msg()
            return
        what = "폴더" if n.is_dir else "파일"
        extra = ("\n\n폴더 안의 파일도 전부 지워집니다." if n.is_dir else "")
        if QMessageBox.question(
                self, config.APP_NAME,
                f"{what} '{n.name}' 을(를) 지울까요?{extra}\n\n"
                "구글 드라이브에서도 지워지고, 되돌릴 수 없습니다.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            file_ops.delete(n.key, self.source.root)
        except file_ops.OpError as e:
            QMessageBox.warning(self, config.APP_NAME, str(e))
            return
        self._after_change(f"'{n.name}' 을(를) 지웠습니다.", [])

    def rename_selected(self):
        n = self._current()
        if n is None:
            return
        if not self._can_edit():
            self._no_edit_msg()
            return
        new, okp = QInputDialog.getText(self, "이름 바꾸기", "새 이름:", text=n.name)
        if not okp or not new.strip():
            return
        try:
            file_ops.rename(n.key, new.strip(), self.source.root)
        except file_ops.OpError as e:
            QMessageBox.warning(self, config.APP_NAME, str(e))
            return
        self._after_change("", [])

    def new_folder(self):
        if not self._can_edit():
            self._no_edit_msg()
            return
        folder = self._cur_dir()
        if not folder:
            return
        name, okp = QInputDialog.getText(self, "새 폴더", "폴더 이름:")
        if not okp or not name.strip():
            return
        try:
            file_ops.make_folder(folder, name.strip())
        except file_ops.OpError as e:
            QMessageBox.warning(self, config.APP_NAME, str(e))
            return
        self._after_change("", [])

    def copy_drive_url(self):
        """다른 사람에게 보여 줄 드라이브 주소를 복사한다."""
        n = self._current() or (self.path[-1] if self.path else None)
        if n is None:
            return
        url = file_ops.drive_url(n)
        if url:
            QApplication.clipboard().setText(url)
            self._toast(f"드라이브 주소를 복사했습니다:\n{url}")
            return
        # 로컬 폴더에는 드라이브가 매기는 번호가 없어 바로 가는 주소를 만들 수 없다.
        # 대신 그 이름으로 찾아 주는 주소를 주고, 그 사실을 분명히 알린다.
        url = file_ops.drive_search_url(n.name)
        QApplication.clipboard().setText(url)
        QMessageBox.information(
            self, config.APP_NAME,
            "이 폴더는 PC 에 내려받아 둔 폴더라, 드라이브에서 바로 가는 주소를\n"
            "만들 수 없습니다(드라이브가 매기는 파일 번호를 알 수 없습니다).\n\n"
            "대신 드라이브에서 이 이름을 찾아 주는 주소를 복사했습니다:\n"
            f"{url}\n\n"
            "바로 가는 주소가 필요하면 드라이브에서 해당 폴더를 우클릭 →\n"
            "[링크 복사] 를 쓰시는 편이 정확합니다.")

    def _toast(self, msg: str):
        w = self.window()
        if hasattr(w, "sig_toast"):
            w.sig_toast.emit(config.APP_NAME, msg.replace("\n", " "))
        else:
            QMessageBox.information(self, config.APP_NAME, msg)

    def _after_change(self, msg: str, failed: list):
        """넣거나 뺀 뒤 — 목록과 검색 목록을 다시 읽는다."""
        self.index = None            # 검색 목록이 낡았다
        self._partial = []
        self._sig = None             # 무조건 다시 그리게
        self._list_current(quiet=False)
        if failed:
            QMessageBox.warning(
                self, config.APP_NAME,
                "일부는 넣지 못했습니다:\n\n" + "\n".join(failed[:10]))
        elif msg:
            self._toast(msg)

    def _menu(self, pos):
        m = QMenu(self)
        n = self._current()
        editable = self._can_edit()
        if n is not None:
            a = m.addAction("이름 바꾸기")
            a.setEnabled(editable)
            a.triggered.connect(self.rename_selected)
            a = m.addAction("삭제")
            a.setEnabled(editable)
            a.triggered.connect(self.delete_selected)
            m.addSeparator()
        a = m.addAction("새 폴더 만들기")
        a.setEnabled(editable)
        a.triggered.connect(self.new_folder)
        a = m.addAction("붙여넣기 (Ctrl+V)")
        a.setEnabled(editable)
        a.triggered.connect(self.paste_clipboard)
        m.addSeparator()
        m.addAction("드라이브 주소 복사").triggered.connect(self.copy_drive_url)
        m.exec(self.tbl.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------ 테마
    def apply_theme(self):
        self.lbl_count.setStyleSheet(f"color:{theme.c('subtext')};")
        self.pv.apply_theme()
