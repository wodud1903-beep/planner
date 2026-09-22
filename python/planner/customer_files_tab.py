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

from PySide6.QtCore import QBuffer, QEvent, QMimeData, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QCursor, QDrag, QGuiApplication, QImage, QKeySequence)
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



class _FileTable(QTableWidget):
    """바깥으로 끌어낼 수 있는 목록.

    고른 파일을 그대로 끌어다 카카오톡 대화창에 놓으면 그 파일이 전송된다.
    끌고 나가는 것은 '파일'이라야 한다 — 그림 데이터만 실으면 받는 쪽이
    이름도 원본 화질도 모른 채 다시 만들어 낸다.
    """

    def __init__(self, cols, on_drag_paths, on_drop=None, on_hover=None,
                 on_back=None, parent=None):
        super().__init__(0, cols, parent)
        self._on_drag_paths = on_drag_paths
        self._on_drop = on_drop            # (경로들, 줄번호) — 놓았을 때
        self._on_hover = on_hover          # (줄번호|None) — 지나갈 때 칠하기
        self._on_back = on_back            # 마우스 뒤로가기 단추 → 상위 폴더
        self._dropped = False              # 이번 끌기에서 놓기 이벤트가 왔는가
        self._press = None                 # 누른 자리(뷰포트 좌표)
        self._idrag = False                # 목록 안에서 끌고 있는 중인가
        self._idrag_paths: list = []
        self._click_row = None             # 눌렀지만 아직 선택을 안 바꾼 줄

    # ---------------------------------------------------------------- 끌기
    #
    # ⚠️ **목록 안에서 옮기는 일은 Qt 의 끌어다놓기(QDrag)에 맡기지 않는다.**
    #    두 번 고쳤는데도 윈도에서 안 먹었다. 처음엔 창 쪽 eventFilter 로 받으려
    #    했고(이벤트가 거기까지 안 왔다), 다음엔 뷰의 dropEvent 로 받고 끌기가
    #    끝난 자리까지 봤는데(v1.20.0) 그래도 아무 일도 나지 않았다.
    #    그래서 Qt 의 그 길을 아예 쓰지 않는다 — 누르고·끌고·놓는 **마우스 이벤트만**
    #    가지고 우리가 직접 한다. 이건 안 올 수가 없는 이벤트다.
    #
    #    바깥(카카오톡·탐색기·바탕화면)으로 끌어내는 것은 여전히 QDrag 라야 한다.
    #    그래서 커서가 **목록 밖으로 나가는 순간** 그때 진짜 끌기로 넘긴다.
    #    ⚠️ 처음에는 '창 밖으로 나가면' 으로 했는데 그러면 카카오톡으로 못 끈다 —
    #       카톡 창이 앱 위에 겹쳐 있거나 앱이 최대화돼 있으면 커서가 창 안에
    #       머문 채로 남기 때문이다. 목록을 벗어나는 순간으로 바꿔야 한다.
    def mousePressEvent(self, e):          # noqa: N802
        # 마우스 옆 단추(뒤로/앞으로)로 상위 폴더에 간다 — 브라우저·탐색기와 같다.
        if e.button() in (Qt.BackButton, Qt.ForwardButton):
            if e.button() == Qt.BackButton and self._on_back:
                self._on_back()
            e.accept()                     # 앞으로 단추는 하는 일 없이 삼킨다
            return
        self._idrag = False
        self._click_row = None
        if e.button() == Qt.LeftButton:
            self._press = self._pt(e)
            row = self._row_at_point(self._press)
            picked = {i.row() for i in self.selectedIndexes()}
            plain = not (e.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier))
            if row is not None and row in picked and len(picked) > 1 and plain:
                # ⚠️ 여러 개를 골라 두고 그중 하나를 누른 것이다. 여기서 기본
                #    동작을 부르면 **그 줄 하나만 남기고 선택이 풀려서**, 끌어도
                #    한 개만 옮겨진다. 끌 수도 있으니 선택을 그대로 둔다.
                #    끌지 않고 그냥 놓으면 그때 이 줄만 고른다(탐색기와 같다).
                self._click_row = row
                return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):           # noqa: N802
        if not (e.buttons() & Qt.LeftButton):
            super().mouseMoveEvent(e)
            return
        p = self._pt(e)
        if not self._idrag and self._press is not None:
            if (p - self._press).manhattanLength() >= QApplication.startDragDistance():
                if self._row_at_point(self._press) is not None:
                    paths = self._on_drag_paths()
                    if paths:
                        self._idrag = True
                        self._idrag_paths = list(paths)
                        self.setCursor(Qt.DragMoveCursor)
        if not self._idrag:
            super().mouseMoveEvent(e)
            return
        # 목록 밖으로 나갔다 → 여기서부터는 진짜 끌어내기(카카오톡·바탕화면)
        if not self.viewport().rect().contains(p):
            paths = self._idrag_paths
            self._end_idrag()
            self._external_drag(paths)
            return
        if self._on_hover:                 # 어느 폴더 위인지 칠해 준다
            self._on_hover(self._row_at_point(p)
                           if self.viewport().rect().contains(p) else None)
        # 고무줄 선택이 같이 돌지 않게 기본 동작은 부르지 않는다

    def mouseReleaseEvent(self, e):        # noqa: N802
        if not self._idrag:
            self._press = None
            if self._click_row is not None and e.button() == Qt.LeftButton:
                row, self._click_row = self._click_row, None
                self.clearSelection()      # 끌지 않았다 → 이제 이 줄만 고른다
                self.selectRow(row)
                self.setCurrentCell(row, 0)
                e.accept()
                return
            super().mouseReleaseEvent(e)
            return
        p = self._pt(e)
        paths = self._idrag_paths
        self._end_idrag()
        if self.viewport().rect().contains(p) and self._on_drop and paths:
            row = self._row_at_point(p)
            # 묻는 창은 다음 턴에 — 마우스를 놓는 도중에 모달을 띄우지 않는다
            QTimer.singleShot(0, lambda q=list(paths), r=row: self._on_drop(q, r))
        e.accept()

    def _pt(self, e):
        try:
            return e.position().toPoint()
        except AttributeError:             # 옛 Qt
            return e.pos()

    def _end_idrag(self):
        self._idrag = False
        self._click_row = None
        self._idrag_paths = []
        self._press = None
        self.unsetCursor()
        if self._on_hover:
            self._on_hover(None)

    def _external_drag(self, paths: list):
        """창 밖으로 끌어냈다 — 카카오톡·탐색기가 받을 수 있게 진짜 끌기로."""
        if not paths:
            return
        drag = QDrag(self)
        drag.setMimeData(file_mime(paths))
        icon = self.style().standardIcon(self.style().SP_FileIcon)
        pm = icon.pixmap(32, 32)
        if not pm.isNull():
            drag.setPixmap(pm)
        drag.exec(Qt.CopyAction)

    def startDrag(self, actions):
        paths = self._on_drag_paths()
        if not paths:
            return
        drag = QDrag(self)
        drag.setMimeData(file_mime(paths))
        # 끌고 다니는 동안 무엇을 쥐고 있는지 보이게 한다
        icon = self.style().standardIcon(self.style().SP_FileIcon)
        pm = icon.pixmap(32, 32)
        if not pm.isNull():
            drag.setPixmap(pm)

        # ⚠️ 여기가 핵심이다. 제 목록 안에 놓았는데도 **놓기 이벤트가 오지 않는
        #    경우가 있다**(윈도에서 실제로 그랬다 — 검사에서 dropEvent 를 직접
        #    불러 봤을 때는 멀쩡했는데 진짜로 끌어 놓으면 아무 일도 안 났다).
        #    그래서 이벤트가 오기를 기다리지 않는다. 끌기가 끝난 **자리**를 보고
        #    우리 목록 안이면 우리가 처리한다. 창 밖(카카오톡 등)이면 손대지 않는다.
        self._dropped = False
        hover = QTimer(self)                 # 끄는 동안 어느 폴더 위인지 칠한다
        hover.timeout.connect(self._track_hover)
        hover.start(60)
        try:
            drag.exec(Qt.CopyAction)
        finally:
            hover.stop()
            if self._on_hover:
                self._on_hover(None)
        if not self._dropped:
            self._finish_drag_at(QCursor.pos(), paths)

    def _track_hover(self):
        """끌고 다니는 동안 커서 밑의 폴더를 칠한다(놓기 이벤트와 무관하게)."""
        if not self._on_hover:
            return
        p = self.viewport().mapFromGlobal(QCursor.pos())
        self._on_hover(self._row_at_point(p)
                       if self.viewport().rect().contains(p) else None)

    def _finish_drag_at(self, gpos, paths):
        """끌기가 끝난 자리로 처리한다. 창 밖이면 아무 일도 안 한다."""
        p = self.viewport().mapFromGlobal(gpos)
        if not self.viewport().rect().contains(p):
            return                           # 밖으로 끌어냈다 — 받은 쪽이 알아서
        row = self._row_at_point(p)
        if self._on_drop and paths:
            QTimer.singleShot(0, lambda q=list(paths), r=row: self._on_drop(q, r))

    # ---- 받기 ----
    # ⚠️ 이 넷은 **이 자리에 있어야 한다.** 예전엔 창 쪽 eventFilter 로 받았는데,
    #    끌어다 놓기 이벤트는 Qt 가 뷰의 이 함수들로 바로 넣어 주기 때문에
    #    필터까지 오지 않는 길이 있다. 검사에서 놓기 이벤트를 보내 봤더니
    #    필터가 한 번도 안 불렸다 — 그래서 뷰가 직접 받는다.
    def _row_at_point(self, pos) -> int:
        idx = self.indexAt(pos)
        return idx.row() if idx.isValid() else None

    def _row_at(self, e) -> int:
        try:
            pos = e.position().toPoint()
        except AttributeError:             # 옛 Qt
            pos = e.pos()
        return self._row_at_point(pos)

    def dragEnterEvent(self, e):           # noqa: N802
        self.dragMoveEvent(e)

    def dragMoveEvent(self, e):            # noqa: N802
        if not e.mimeData().hasUrls():
            e.ignore()
            return
        if self._on_hover:
            self._on_hover(self._row_at(e))
        e.acceptProposedAction()

    def dragLeaveEvent(self, e):           # noqa: N802
        if self._on_hover:
            self._on_hover(None)
        e.accept()

    def dropEvent(self, e):                # noqa: N802
        if not e.mimeData().hasUrls():
            super().dropEvent(e)
            return
        row = self._row_at(e)
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if self._on_hover:
            self._on_hover(None)
        e.acceptProposedAction()
        self._dropped = True               # startDrag 의 뒷처리가 또 하지 않게
        # ⚠️ 여기서 바로 물어보면 안 된다. 놓는 순간은 아직 끌기가 끝나기 전이라
        #    그 위에 모달 창을 띄우면 마우스를 쥔 채로 굳는다. 다음 턴으로 미룬다.
        if self._on_drop and paths:
            QTimer.singleShot(0, lambda p=paths, r=row: self._on_drop(p, r))


def file_mime(paths: list) -> QMimeData:
    """파일을 클립보드·드래그에 실을 형태로 담는다.

    - 파일 목록(urls)  : 카카오톡·탐색기가 '파일'로 받는다. 이게 본체다.
    - 글자(경로)        : 경로를 글자로 받는 곳이 있다.
    - 그림(그림 파일일 때): 파일을 못 받고 그림만 받는 곳(한글·워드 등)을 위해.
    """
    md = QMimeData()
    md.setUrls([QUrl.fromLocalFile(p) for p in paths])
    md.setText("\n".join(paths))
    if len(paths) == 1:
        img = QImage(paths[0])
        if not img.isNull():
            md.setImageData(img)
    return md


class CustomerFilesTab(QWidget):
    """고객 서류 찾아보기."""

    sig_listed = Signal(object, str)           # (Node 목록|None, "세대\0오류")
    sig_indexed = Signal(object, str)          # (Node 목록|None, "훑기번호\0오류")
    sig_index_progress = Signal(int)           # 훑는 중 (훑기번호)
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
        self._index_gen = 0           # 몇 번째 훑기인가(낡은 결과 버리기)
        self._sig = None              # 지금 폴더의 요약값(바뀜 감지)
        self._preview_key = ""
        self._drop_row = None         # 끌어다 놓는 동안 칠해 둔 줄
        # 정렬 기준은 '몇 번째 칸' 이 아니라 '어느 칸 이름' 으로 들고 있는다.
        # 찾아보기는 칸이 3개(이름·크기·날짜)인데 검색은 4개(이름·위치·크기·날짜)
        # 라서, 번호로 기억하면 검색으로 넘어가는 순간 날짜가 크기로 바뀌었다.
        self._sort_key = "이름"
        self._sort_desc = False
        self._view: list = []
        # 글자를 덧붙여 칠 때 직전 결과만 다시 거르기 위한 기억(_filter)
        self._last_q = ""
        self._last_hits: list = []
        self._last_pool_n = -1
        self._index_failed = 0        # 훑다가 못 읽은 폴더 수

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
        # 끌어낼 때는 폴더까지 싣는다 — 안쪽에서 폴더를 다른 폴더로 옮기는 데
        # 쓴다. 카카오톡처럼 폴더를 못 받는 곳은 그냥 무시한다(탐색기도 같다).
        self.tbl = _FileTable(len(self.COLS), self._drag_all_paths,
                              on_drop=self._drop_paths, on_hover=self._hint_drop,
                              on_back=self.go_up)
        self.tbl.setHorizontalHeaderLabels(self.COLS)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        # Ctrl+클릭으로 여럿, Shift+클릭으로 사이를 한꺼번에 고른다(탐색기와 같다).
        # 여럿 고른 채로 복사·삭제·끌어내기·옮기기가 다 된다.
        self.tbl.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.verticalHeader().setDefaultSectionSize(30)
        # 남는 폭은 '이름' 이 받는다. 마지막 칸(날짜)을 늘리면 날짜가 허옇게
        # 넓어지고 정작 긴 폴더 이름이 잘린다.
        self.tbl.horizontalHeader().setStretchLastSection(False)
        hdr0 = self.tbl.horizontalHeader()
        hdr0.setSectionsClickable(True)
        hdr0.sectionClicked.connect(self._on_header_clicked)
        self.tbl.itemSelectionChanged.connect(self._on_select)
        self.tbl.doubleClicked.connect(self._on_double)
        # 오른쪽 단추 메뉴 · 바깥에서 끌어다 놓기
        self.tbl.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tbl.customContextMenuRequested.connect(self._menu)
        self.tbl.setAcceptDrops(True)
        # ⚠️ 받기만 Qt 에 맡긴다(DropOnly). 끌어내기를 Qt 에 맡기면(DragDrop)
        #    Qt 가 제 방식대로 QDrag 를 시작해 버리는데, 그 길에서는 목록 안에
        #    놓아도 아무 일이 안 났다. 끌기는 _FileTable 이 마우스 이벤트로
        #    직접 한다(거기 주석 참고). setDragDropMode 가 dragEnabled 를 같이
        #    켜고 끄므로 순서가 중요하다 — 모드를 먼저 정하고 꺼야 한다.
        self.tbl.setDragDropMode(QAbstractItemView.DropOnly)
        self.tbl.setDragEnabled(False)
        self.tbl.setDefaultDropAction(Qt.CopyAction)
        self.tbl.viewport().setAcceptDrops(True)
        self.tbl.installEventFilter(self)
        self.tbl.viewport().installEventFilter(self)
        self._cols = []
        self._set_columns(self.COLS, self.WIDTHS)
        self.split.addWidget(self.tbl)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 0, 0, 0)
        # 미리보기에서 본 서류를 그 자리에서 바로 카카오톡으로 보낸다.
        # 보낼 수 없는 경우(드라이브 직접 조회 중 등)의 안내는 copy_selected 가
        # 이미 맡고 있으므로 한 곳에 모아 둔다.
        self.pv = FilePreview(on_send=self.copy_selected)
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

        # 타자가 멎으면 찾는다 (한 자마다 전부 훑지 않게)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._run_search)

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
        self._drop_index()                 # 창고가 바뀌면 검색 목록도 버린다
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
        first = self._sig is None
        changed = (sig != self._sig)
        self._sig = sig
        self.rows = customer_files.sort_nodes(nodes)
        if changed and not first and self.index is not None:
            # 폴더 안이 바뀌었다 → 검색 목록도 낡았다. 사무실에서 올린 서류가
            # 집 PC 로 동기화돼 들어오면 검색에도 나와야 한다. 예전엔 검색 목록을
            # 켤 때 한 번만 만들어서, 하루 종일 띄워 두면 새 서류가 검색에
            # 영영 안 나왔다.
            self._drop_index()
        self._start_poll()
        # 검색은 트리 전체를 봐야 한다. 사용자가 글자를 칠 때까지 기다리지 말고
        # 지금부터 뒤에서 훑어 둔다 — 예전엔 첫 글자를 친 뒤에야 시작해서
        # '훑는 중' 을 한참 기다려야 했다.
        #
        # ⚠️ 이 두 줄은 검색 중에도 반드시 지나가야 한다. 예전엔 검색 중이면
        #    여기서 그냥 돌아가 버려서, 파일을 넣거나 지운 직후(_after_change 가
        #    검색 목록을 버린 상태)에 검색 목록을 다시 만들 사람이 아무도 없었다.
        #    그러면 찾은 것이 0건으로 비거나 지운 파일이 계속 보였다.
        self._ensure_index()
        q = self.ed_search.text().strip()
        if q:
            # 검색 중이면 화면은 검색 결과를 지킨다 — 다만 방금 읽은 내용으로
            # 다시 그려 준다(넣고 뺀 것이 바로 보이게).
            self._show_search(q)
            return
        if changed:
            self._show_browse()

    def _show_browse(self):
        keep = self._selected_name()
        self._set_columns(self.COLS, self.WIDTHS)
        self._mark_sort_header()
        self._fill(self._sorted(self.rows), up=len(self.path) > 1)
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
            self._search_timer.stop()
            self._show_browse()
            return
        self._ensure_index()
        # 한 자 칠 때마다 곧바로 훑지 않고 아주 잠깐 기다린다. 빠르게 치거나
        # 키를 누른 채 두면 그 사이 글자는 건너뛰고 마지막 것만 찾는다 —
        # 한 자당 한 번씩 전부 훑으면 서류가 많을 때 타자가 밀린다.
        self._search_timer.start(self.SEARCH_DELAY)

    # 마지막 타자 뒤 이만큼 쉬면 찾기 시작한다(밀리초). 사람이 다음 자를 치는
    # 간격보다는 짧아서 기다린다는 느낌은 들지 않는다.
    SEARCH_DELAY = 130

    def _run_search(self):
        q = self.ed_search.text().strip()
        if q:
            # 아직 다 못 훑었어도 지금까지 찾은 것으로 바로 보여 준다.
            # 기다리게 하지 않는 편이 낫고, 대개 찾는 것은 이미 그 안에 있다.
            self._show_search(q)

    def _filter(self, pool: list, q: str) -> list:
        """찾기 — 글자를 덧붙이는 중이면 직전 결과만 다시 거른다.

        '김' → '김상' → '김상현' 처럼 글자를 붙여 갈 때, 뒤 글자는 앞 글자를
        만족하는 것 중에서만 나올 수 있다. 그래서 전체를 다시 훑지 않고 직전에
        찾아 둔 것만 본다. '김' 에서 300건이 남았으면 그다음 자는 10만건이 아니라
        300건만 보므로 거의 공짜다.

        창고를 다시 읽었거나(목록 크기가 달라짐) 글자를 지운 경우에는 믿을 수
        없으니 전체를 다시 본다.
        """
        n = len(pool)
        if (self._last_q and q.startswith(self._last_q) and n == self._last_pool_n):
            base = self._last_hits
        else:
            base = pool
        hits = customer_files.search(base, q)
        self._last_q, self._last_hits, self._last_pool_n = q, hits, n
        return hits

    def search_for(self, text: str):
        """고객관리에서 '이 고객 서류 보기' 로 넘어올 때 쓴다."""
        self.ed_search.setText(text or "")
        self.ed_search.setFocus()

    def _drop_index(self):
        """검색 목록이 낡았다 — 버리고 다시 만들게 한다.

        표(_index_gen)를 올려 두는 것이 핵심이다. 지금 돌고 있는 훑기가 있으면
        그 결과는 낡은 것이므로, 나중에 도착해도 받지 않는다. '훑는 중' 표시도
        내려 두어야 새 훑기가 바로 시작할 수 있다.
        """
        self.index = None
        self._partial = []
        self._indexing = False
        self._index_gen += 1
        self._last_q = ""            # 좁혀 가며 찾던 기억도 함께 버린다
        self._last_hits = []
        self._last_pool_n = -1

    def _ensure_index(self):
        """검색용 전체 목록을 뒤에서 만든다(한 번만).

        폴더 하나를 끝낼 때마다 중간 결과를 받아 두어서, 다 끝나기 전에도
        검색이 먹는다.
        """
        if self._indexing or self.index is not None or self.source is None:
            return
        self._indexing = True
        self._partial = []
        # ⚠️ 몇 번째 훑기인지 표를 달아 보낸다.
        #
        # 훑는 데는 시간이 걸린다. 그 사이에 파일을 넣거나 지우면 검색 목록을
        # 버리고 새로 훑기 시작하는데, 그때 **먼저 떠난 훑기가 나중에 도착**해서
        # 새 목록을 낡은 것으로 덮어써 버렸다. 그러면 방금 넣은 서류가 검색에
        # 안 나온다. 폴더 읽기(_gen)에는 이 표가 있었는데 훑기에는 없었다.
        self._index_gen += 1
        gen = self._index_gen
        src = self.source

        def worker():
            try:
                def batch(got):
                    # 목록은 계속 자라므로 그때그때 복사해 넘긴다
                    if gen == self._index_gen:
                        self._partial = list(got)
                        self.sig_index_progress.emit(gen)
                self.sig_indexed.emit(src.scan(on_batch=batch), str(gen))
            except Exception as e:
                self.sig_indexed.emit(None, f"{gen}\x00{e}")

        threading.Thread(target=worker, daemon=True).start()

    def _on_index_progress(self, gen: int):
        if gen != self._index_gen:
            return                      # 먼저 떠났다가 늦게 온 훑기
        if not self.ed_search.text().strip():
            return
        self._show_search(self.ed_search.text().strip(), partial=True)

    def _on_indexed(self, nodes, err: str):
        gen, _, msg = (err or "").partition("\x00")
        if gen.isdigit() and int(gen) != self._index_gen:
            return                      # 낡은 훑기 결과로 새 목록을 덮지 않는다
        self._indexing = False
        if nodes is None:
            self.lbl_count.setText("검색 준비 실패")
            return
        self.index = customer_files.sort_nodes(nodes)
        # 못 읽은 폴더가 있었는지 기억해 둔다 — 그 폴더의 서류는 검색에 안 나오는데,
        # 말해 주지 않으면 '서류가 없다' 고 오해하게 된다.
        self._index_failed = int(getattr(self.source, "failed", 0) or 0)
        q = self.ed_search.text().strip()
        if q:
            self._show_search(q)

    def _show_search(self, q: str, partial: bool = False):
        pool = self.index if self.index is not None else self._partial
        hits = self._filter(pool, q)
        self._set_columns(self.SEARCH_COLS, self.SEARCH_WIDTHS)
        self._mark_sort_header()
        self._fill(self._sorted(hits), up=False, with_where=True)
        self.btn_up.setEnabled(False)
        if self.index is None:
            self.lbl_count.setText(f"{len(hits):,}건 (훑는 중 {len(pool):,})")
            self.lbl_where.setText("검색 결과 — 아직 훑는 중이라 더 나올 수 있습니다")
            return
        self.lbl_count.setText(f"{len(hits):,} / {len(pool):,}건")
        nf = getattr(self, "_index_failed", 0)
        if nf:
            self.lbl_where.setText(
                f"검색 결과 — 폴더 {nf}곳을 읽지 못해 빠진 서류가 있을 수 있습니다")
            self.lbl_where.setToolTip(
                "권한이 없거나 잠시 연결이 막힌 폴더입니다.\n"
                "[새로고침] 을 누르면 다시 읽습니다.")
        elif len(pool) >= customer_files.MAX_FILES:
            self.lbl_where.setText(
                f"검색 결과 — {customer_files.MAX_FILES:,}건까지만 훑었습니다")
            self.lbl_where.setToolTip(
                "서류가 상한보다 많아 뒷부분은 검색에 안 나옵니다.")
        else:
            self.lbl_where.setText("검색 결과 — 전체에서 찾았습니다")
            self.lbl_where.setToolTip("")



    # ------------------------------------------------ 복사해서 카카오톡으로
    #
    # 고른 파일을 클립보드에 '파일' 로 올린다. 카카오톡 대화창에서 Ctrl+V 하면
    # 그 파일이 붙고, 목록에서 그대로 끌어다 놓아도 전송된다.
    # 드라이브를 API 로 조회하는 중에는 PC 에 파일이 없으므로 안 된다.
    def _drag_paths(self) -> list:
        """끌어내기·복사에 실을 **파일** 경로. 고른 것이 여럿이면 여럿 다.

        폴더는 뺀다 — 카카오톡은 폴더를 받지 못한다. 폴더를 옮기는 일은
        안쪽 끌어다 놓기(_move_into)가 따로 맡는다.
        """
        if self.source is None:
            return []
        out = []
        for n in self._selected():
            if n.is_dir:
                continue
            p = self.source.local_path(n)
            if p and os.path.exists(p):
                out.append(p)
        return out

    def _drag_all_paths(self) -> list:
        """폴더까지 포함해 고른 것 전부의 경로 — 안쪽에서 옮길 때 쓴다."""
        if self.source is None:
            return []
        out = []
        for n in self._selected():
            p = self.source.local_path(n)
            if p and os.path.exists(p):
                out.append(p)
        # ⚠️ 인터넷으로 읽는 중(드라이브 API)에는 PC 에 파일이 없어 경로가 없다.
        #    그러면 끌기가 **아무 일도 없이** 끝난다 — 고장 난 것처럼 보인다.
        #    왜 안 되는지 한 번은 말해 준다.
        if not out and self._selected() and not self._can_edit():
            self._toast("인터넷으로 읽는 중에는 끌어서 옮길 수 없습니다. "
                        "구글 드라이브를 켜 두면 됩니다.")
        return out

    def copy_selected(self):
        """Ctrl+C — 고른 파일을 클립보드에 올린다(여럿도 된다)."""
        picked = self._selected()
        if not picked:
            return
        paths = self._drag_paths()
        if not paths:
            if all(n.is_dir for n in picked):
                self._toast("폴더는 복사할 수 없습니다. 파일을 골라 주세요.")
                return
            QMessageBox.information(
                self, config.APP_NAME,
                "이 파일은 PC 에 없어서 복사할 수 없습니다.\n"
                "[설정] 에서 서류 폴더를 지정하면 복사·끌어내기가 됩니다.")
            return
        QApplication.clipboard().setMimeData(file_mime(paths))
        what = (os.path.basename(paths[0]) if len(paths) == 1
                else f"{len(paths)}개")
        self._toast(f"{what} — 복사했습니다. "
                    "카카오톡에서 Ctrl+V 로 붙여 넣으세요.")

    # ---------------------------------------------------------------- 정렬
    #
    # 머리글을 누르면 그 기준으로 줄을 세운다. 같은 머리글을 또 누르면 거꾸로.
    # 폴더는 늘 위에 둔다(윈도 탐색기와 같다) — 폴더와 파일이 섞이면 찾기 어렵다.
    def _on_header_clicked(self, col: int):
        name = self._cols[col] if col < len(self._cols) else ""
        if name not in ("이름", "크기", "날짜", "위치"):
            return
        if name == self._sort_key:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_key, self._sort_desc = name, False
        q = self.ed_search.text().strip()
        if q:
            self._show_search(q)
        else:
            self._show_browse()

    @property
    def _sort_col(self) -> int:
        """지금 칸 구성에서 정렬 기준이 몇 번째인가. 없으면 -1(화살표 없음)."""
        try:
            return self._cols.index(self._sort_key)
        except ValueError:
            return -1

    def _sorted(self, rows: list) -> list:
        name = self._sort_key
        if name == "크기":
            key = lambda n: (not n.is_dir, n.size)
        elif name == "날짜":
            key = lambda n: (not n.is_dir,
                             n.mtime.timestamp() if n.mtime else 0)
        elif name == "위치":
            key = lambda n: (not n.is_dir, n.folder.lower(), n.name.lower())
        else:                                   # 이름 (모르는 기준도 여기로)
            key = lambda n: (not n.is_dir, n.name.lower())
        out = sorted(rows, key=key, reverse=self._sort_desc)
        if self._sort_desc:
            # 거꾸로 세워도 폴더는 위에 남는다
            out = ([n for n in out if n.is_dir]
                   + [n for n in out if not n.is_dir])
        return out

    def _mark_sort_header(self):
        """어느 기준으로 세웠는지 머리글에 화살표로 알린다."""
        for i, nm in enumerate(self._cols):
            item = self.tbl.horizontalHeaderItem(i)
            if item is None:
                continue
            if i == self._sort_col:
                item.setText(nm + ("  ▼" if self._sort_desc else "  ▲"))
            else:
                item.setText(nm)

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
        # 지금 칸 구성에 없는 기준('위치' 는 검색에만 있다)이면 이름순으로 돌아간다
        if self._sort_key not in self._cols:
            self._sort_key, self._sort_desc = "이름", False

    def _fill(self, rows: list, up: bool = False, with_where: bool = False):
        self._drop_row = None          # 줄을 새로 만드니 칠해 둔 표시도 없어진다
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
        view = self._view
        if r < 0 or r >= len(view):
            return None
        n = view[r]
        return None if n is UP_ROW else n

    def _selected(self) -> list:
        """고른 것 전부(Ctrl·Shift 로 여럿). 차례는 화면에 보이는 차례 그대로.

        '상위 폴더로' 줄은 진짜 항목이 아니므로 빼고 준다.
        """
        out = []
        for r in sorted({i.row() for i in self.tbl.selectedIndexes()}):
            if 0 <= r < len(self._view):
                n = self._view[r]
                if n is not UP_ROW:
                    out.append(n)
        if out:
            return out
        n = self._current()          # 고른 것이 없으면 지금 줄 하나로 친다
        return [n] if n is not None else []

    def _selected_name(self) -> str:
        n = self._current()
        return n.name if n else ""

    def _restore_selection(self, name: str):
        if not name:
            return
        for r, n in enumerate(self._view):
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
        root = getattr(self.source, "root", "") or self.settings.files_drive_folder
        if getattr(self.source, "auto", False):
            # 폴더를 지정하지 않았는데도 보이는 이유를 적어 둔다. 안 적으면
            # '어디를 읽고 있는지' 를 알 길이 없다.
            crumbs += "   (구글 드라이브에서 자동으로 찾음)"
        elif self.source.kind == "drive":
            # PC 에 받아 둔 것이 없어 인터넷으로 읽는 중이다. 느린 이유를 밝힌다.
            crumbs += "   (인터넷으로 읽는 중 — 구글 드라이브를 켜 두면 빠릅니다)"
        self.lbl_where.setText(crumbs)
        self.lbl_where.setToolTip(root)

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
        view = self._view
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
        # 창고보다 깊이 들어갈 일이 없으므로 그만큼만 올라간다. 상한을 안 두면
        # parent_of 가 끝을 못 알아볼 때 여기서 영영 돌게 된다.
        for _ in range(customer_files.MAX_DEPTH + 2):
            if up is None:
                break
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
            if ev.matches(QKeySequence.Copy):
                self.copy_selected()
                return True
            if ev.matches(QKeySequence.Paste):
                self.paste_clipboard()
                return True
            if ev.key() == Qt.Key_Delete:
                self.delete_selected()
                return True
            # 백스페이스는 탐색기와 같이 '상위 폴더로' 다. 예전엔 이것도 삭제라,
            # 위로 올라가려고 누른 사람에게 지울지 묻는 창이 떴다.
            if ev.key() == Qt.Key_Backspace:
                self.go_up()
                return True
            if ev.key() == Qt.Key_F2:
                self.rename_selected()
                return True
        # 끌어다 놓기는 표(_FileTable)가 직접 받는다 — 여기로 오지 않는 길이
        # 있기 때문이다. 그쪽 주석 참고.
        return super().eventFilter(obj, ev)

    # ------------------------------------------- 끌어다 놓기(받기 · 옮기기)
    def _drop_folder(self, row) -> str:
        """그 줄에 놓았을 때 들어갈 폴더의 실제 경로.

        폴더 줄이면 그 폴더 안으로, '상위 폴더로' 줄이면 한 겹 위로
        (탐색기와 같다). 파일 줄이나 빈 자리면 지금 보고 있는 폴더.
        """
        if row is not None and 0 <= row < len(self._view):
            n = self._view[row]
            if n is UP_ROW:
                if len(self.path) >= 2:
                    return self.path[-2].key
                return ""
            if n.is_dir and n.key:
                return n.key
        return self._cur_dir()

    def _hint_drop(self, row):
        """떨어질 폴더 줄을 칠한다(칠한 것은 반드시 되돌린다)."""
        if row is not None and not (0 <= row < len(self._view)):
            row = None
        if row is not None:
            n = self._view[row]
            if not (n is UP_ROW or (n.is_dir and n.key)):
                row = None              # 파일 위에서는 칠하지 않는다
        prev = getattr(self, "_drop_row", None)
        if prev == row:
            return
        from PySide6.QtGui import QBrush, QColor
        if prev is not None and prev < self.tbl.rowCount():
            for c in range(self.tbl.columnCount()):
                it = self.tbl.item(prev, c)
                if it is not None:
                    it.setBackground(QBrush())      # 원래대로
                    it.setForeground(QBrush())
        if row is not None:
            # ⚠️ 고른 줄(파란 배경)과 **확실히 달라야** 한다. 옅은 색으로 하면
            #    끌고 가는 중에 '고른 것' 과 '떨어질 곳' 이 구별되지 않는다.
            #    진한 초록 + 흰 글자 — 세 테마 모두에서 한눈에 갈린다.
            bg, fg = QColor(theme.fill("green")), QColor(theme.fill_text())
            for c in range(self.tbl.columnCount()):
                it = self.tbl.item(row, c)
                if it is not None:
                    it.setBackground(bg)
                    it.setForeground(fg)
        self._drop_row = row

    def _drop_files(self, urls, row=None):
        """끌어다 놓은 것(QUrl 목록)을 받는다."""
        self._drop_paths([u.toLocalFile() for u in urls if u.isLocalFile()], row)

    def _drop_paths(self, paths, row=None):
        if not self._can_edit():
            self._no_edit_msg()
            return
        folder = self._drop_folder(row)
        paths = [p for p in paths if p]
        if not folder or not paths:
            return
        root = self.source.root
        # ⚠️ 우리 목록에서 끌어낸 것이면 **옮기고**, 바깥(탐색기·카카오톡)에서
        #    온 것이면 **복사한다.** 같은 동작에 두 뜻이 있는 셈이라, 어느
        #    쪽인지는 '그 파일이 서류 폴더 안에 있느냐' 로 가른다.
        #    바깥 파일을 옮겨 버리면 원본이 사라진다 — 그건 절대 안 된다.
        inside = [p for p in paths if file_ops.inside(root, p)]
        outside = [p for p in paths if p not in inside]
        if outside:
            done, failed = file_ops.copy_in(outside, folder)
            self._after_change(f"{len(done)}건을 넣었습니다.", failed)
        if inside:
            self._move_into(inside, folder)

    def _move_into(self, paths: list, folder: str):
        """서류 폴더 안에서 다른 폴더로 옮긴다 — 묻고 나서."""
        moving = [p for p in paths
                  if os.path.normcase(os.path.dirname(os.path.abspath(p)))
                  != os.path.normcase(os.path.abspath(folder))]
        if not moving:
            return                      # 있던 자리에 도로 놓았다 — 아무 일도 없다
        where = os.path.basename(folder.rstrip("\\/")) or folder
        what = (f"'{os.path.basename(moving[0])}' 을(를)" if len(moving) == 1
                else f"{len(moving)}개를")
        # ⚠️ 반드시 묻는다. 목록을 누르다 손이 밀리면 서류가 통째로 다른 고객
        #    폴더로 들어가는데, 옮긴 뒤에는 어디로 갔는지 찾기 어렵다.
        if QMessageBox.question(
                self, config.APP_NAME,
                f"{what} '{where}' 폴더로 옮길까요?\n\n"
                "구글 드라이브에서도 같이 옮겨집니다.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes) != QMessageBox.Yes:
            return
        done, failed = file_ops.move_in(moving, folder, self.source.root)
        self._after_change(f"{len(done)}개를 '{where}' 로 옮겼습니다."
                           if done else "", failed)

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
        picked = self._selected()
        if not picked:
            return
        if not self._can_edit():
            self._no_edit_msg()
            return
        has_dir = any(n.is_dir for n in picked)
        extra = ("\n\n폴더 안의 파일도 전부 지워집니다." if has_dir else "")
        if len(picked) == 1:
            n = picked[0]
            what = f"{'폴더' if n.is_dir else '파일'} '{n.name}' 을(를)"
        else:
            names = " · ".join(n.name for n in picked[:5])
            if len(picked) > 5:
                names += f" 외 {len(picked) - 5}개"
            what = f"{len(picked)}개({names})를"
        if QMessageBox.question(
                self, config.APP_NAME,
                f"{what} 지울까요?{extra}\n\n"
                "구글 드라이브에서도 지워지고, 되돌릴 수 없습니다.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No) != QMessageBox.Yes:
            return
        failed = []
        n_ok = 0
        for n in picked:
            try:
                file_ops.delete(n.key, self.source.root)
                n_ok += 1
            except file_ops.OpError as e:
                failed.append(f"{n.name} — {e}")
        msg = (f"'{picked[0].name}' 을(를) 지웠습니다." if n_ok == 1
               else f"{n_ok}개를 지웠습니다.")
        self._after_change(msg if n_ok else "", failed)

    def rename_selected(self):
        picked = self._selected()
        if len(picked) > 1:
            # 여러 개를 한 이름으로 바꿀 수는 없다. 말없이 하나만 바꾸면
            # 나머지는 왜 그대로인지 알 길이 없다.
            self._toast("이름은 하나씩만 바꿀 수 있습니다.")
            return
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
        self._drop_index()           # 검색 목록이 낡았다
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
        picked = self._selected()
        many = len(picked) > 1
        tail = f"  ({len(picked)}개)" if many else ""
        editable = self._can_edit()
        if any(not x.is_dir for x in picked):
            a = m.addAction(f"복사{tail}  (Ctrl+C)")
            a.setToolTip("카카오톡 대화창에서 Ctrl+V 로 붙여 넣을 수 있습니다")
            a.triggered.connect(self.copy_selected)
            m.addSeparator()
        if n is not None:
            a = m.addAction("이름 바꾸기")
            # 여러 개를 한 이름으로 바꿀 수는 없다
            a.setEnabled(editable and not many)
            a.triggered.connect(self.rename_selected)
            a = m.addAction(f"삭제{tail}")
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
