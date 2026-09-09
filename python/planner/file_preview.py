"""파일 미리보기 — 그림과 PDF, 돌려 보기까지.

그림은 받은 바이트를 그대로 그리고, PDF 는 Qt 가 페이지를 그림으로 그려 준다
(QtPdf). 스캔한 서류는 눕혀 찍힌 게 흔해서 돌려 보기가 꼭 필요하다.

돌린 각도는 파일마다 따로 기억한다 — 목록을 오가도 그 각도가 유지된다.
창 크기가 바뀌면 다시 맞춰 그린다.
"""

from __future__ import annotations

from PySide6.QtCore import QBuffer, QByteArray, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from . import theme

try:                                  # QtPdf 가 없는 환경에서도 그림은 보이게
    from PySide6.QtPdf import QPdfDocument
    HAVE_PDF = True
except Exception:                     # pragma: no cover
    QPdfDocument = None
    HAVE_PDF = False


class FilePreview(QWidget):
    """그림·PDF 를 보여 주고, 돌리고, PDF 는 장을 넘긴다."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0                 # 지금 보고 있는 것의 각도
        self._angles: dict = {}         # 파일별로 기억해 둔 각도
        self._key = ""
        self._src = None                # 원본 QPixmap (그림일 때)
        self._doc = None                # QPdfDocument (PDF 일 때)
        self._buf = None                # PDF 바이트 — 문서가 사는 동안 붙들어 둔다
        self._page = 0

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)

        self.lbl_title = QLabel("")
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setStyleSheet("font-weight:bold;")
        v.addWidget(self.lbl_title)

        # ---- 돌리기 · 장 넘기기 ----
        bar = QHBoxLayout()
        self.btn_left = QPushButton("↺ 왼쪽")
        self.btn_left.setToolTip("왼쪽으로 90도 돌리기")
        self.btn_left.clicked.connect(lambda: self.rotate(-90))
        bar.addWidget(self.btn_left)
        self.btn_right = QPushButton("↻ 오른쪽")
        self.btn_right.setToolTip("오른쪽으로 90도 돌리기")
        self.btn_right.clicked.connect(lambda: self.rotate(90))
        bar.addWidget(self.btn_right)
        bar.addStretch()
        self.btn_prev = QPushButton("◀")
        self.btn_prev.setToolTip("이전 장")
        self.btn_prev.clicked.connect(lambda: self.go_page(self._page - 1))
        bar.addWidget(self.btn_prev)
        self.lbl_page = QLabel("")
        self.lbl_page.setAlignment(Qt.AlignCenter)
        self.lbl_page.setMinimumWidth(64)
        bar.addWidget(self.lbl_page)
        self.btn_next = QPushButton("▶")
        self.btn_next.setToolTip("다음 장")
        self.btn_next.clicked.connect(lambda: self.go_page(self._page + 1))
        bar.addWidget(self.btn_next)
        v.addLayout(bar)

        self.view = QLabel("파일을 고르면 여기에 보입니다.")
        self.view.setAlignment(Qt.AlignCenter)
        self.view.setMinimumSize(QSize(220, 220))
        self.view.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        v.addWidget(self.view, 1)

        self.apply_theme()
        self._update_bar()

    # ------------------------------------------------------------ 보여 주기
    def show_message(self, text: str, title: str = ""):
        self._src = None
        self._doc = None
        self._buf = None
        self._key = ""
        self.lbl_title.setText(title)
        self.view.setPixmap(QPixmap())
        self.view.setText(text)
        self._update_bar()

    def show_image(self, data: bytes, key: str, title: str = "") -> bool:
        pix = QPixmap()
        if not pix.loadFromData(data):
            self.show_message("그림을 읽지 못했습니다.", title)
            return False
        self._doc = None
        self._buf = None
        self._src = pix
        self._key = key
        self._angle = self._angles.get(key, 0)
        self.lbl_title.setText(title)
        self._redraw()
        self._update_bar()
        return True

    def show_pdf(self, data: bytes, key: str, title: str = "") -> bool:
        if not HAVE_PDF:
            self.show_message(
                "이 버전에서는 PDF 미리보기를 쓸 수 없습니다.\n"
                "[연결 프로그램으로 열기] 를 눌러 주세요.", title)
            return False
        buf = QBuffer()
        buf.setData(QByteArray(data))
        if not buf.open(QBuffer.ReadOnly):
            self.show_message("PDF 를 열지 못했습니다.", title)
            return False
        doc = QPdfDocument(self)
        err = doc.load(buf)
        # 잠긴 PDF 등은 여기서 걸린다
        if doc.pageCount() <= 0:
            self.show_message(
                f"PDF 를 읽지 못했습니다. ({err})\n"
                "[연결 프로그램으로 열기] 를 눌러 주세요.", title)
            return False
        self._src = None
        self._doc = doc
        self._buf = buf                 # 문서가 이 버퍼를 계속 읽는다
        self._key = key
        self._angle = self._angles.get(key, 0)
        self._page = 0
        self.lbl_title.setText(title)
        self._redraw()
        self._update_bar()
        return True

    # ------------------------------------------------------------ 조작
    def rotate(self, delta: int):
        if self._src is None and self._doc is None:
            return
        self._angle = (self._angle + delta) % 360
        if self._key:
            self._angles[self._key] = self._angle
        self._redraw()

    def go_page(self, page: int):
        if self._doc is None:
            return
        page = max(0, min(page, self._doc.pageCount() - 1))
        if page == self._page:
            return
        self._page = page
        self._redraw()
        self._update_bar()

    @property
    def page_count(self) -> int:
        return self._doc.pageCount() if self._doc is not None else 0

    @property
    def angle(self) -> int:
        return self._angle

    # ------------------------------------------------------------ 그리기
    def _box(self) -> QSize:
        s = self.view.size()
        return QSize(max(80, s.width()), max(80, s.height()))

    def _redraw(self):
        pix = None
        if self._src is not None:
            pix = self._src
        elif self._doc is not None:
            pix = self._render_page()
        if pix is None or pix.isNull():
            return
        if self._angle:
            pix = pix.transformed(QTransform().rotate(self._angle),
                                  Qt.SmoothTransformation)
        self.view.setText("")
        self.view.setPixmap(pix.scaled(self._box(), Qt.KeepAspectRatio,
                                       Qt.SmoothTransformation))

    def _render_page(self):
        """PDF 한 장을 지금 칸 크기에 맞춰 그린다.

        미리 정한 크기로 그리면 흐릿해지므로, 보여 줄 크기를 계산해 그 크기로
        바로 그린다. 돌려 볼 때는 가로세로가 바뀌므로 그 점을 감안한다.
        """
        doc, box = self._doc, self._box()
        pt = doc.pagePointSize(self._page)
        if pt.width() <= 0 or pt.height() <= 0:
            return None
        bw, bh = box.width(), box.height()
        if self._angle in (90, 270):
            bw, bh = bh, bw
        scale = min(bw / pt.width(), bh / pt.height())
        scale = max(0.1, min(scale, 6.0))
        size = QSize(max(1, int(pt.width() * scale)),
                     max(1, int(pt.height() * scale)))
        img = doc.render(self._page, size)
        if not isinstance(img, QImage) or img.isNull():
            return None
        # 종이는 흰색으로 깔아 준다. 그냥 그리면 글자만 있고 배경이 비어 있어서,
        # 어두운 화면에서는 검은 바탕에 검은 글씨가 되어 아무것도 안 보였다.
        page = QImage(img.size(), QImage.Format_RGB32)
        page.fill(QColor("#FFFFFF"))
        p = QPainter(page)
        p.drawImage(0, 0, img)
        p.end()
        return QPixmap.fromImage(page)

    def _update_bar(self):
        has = self._src is not None or self._doc is not None
        self.btn_left.setEnabled(has)
        self.btn_right.setEnabled(has)
        n = self.page_count
        multi = n > 1
        self.btn_prev.setVisible(multi)
        self.btn_next.setVisible(multi)
        self.lbl_page.setVisible(multi)
        if multi:
            self.btn_prev.setEnabled(self._page > 0)
            self.btn_next.setEnabled(self._page < n - 1)
            self.lbl_page.setText(f"{self._page + 1} / {n}")

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._redraw()

    def apply_theme(self):
        self.view.setStyleSheet(
            f"color:{theme.c('subtext')};border:1px solid {theme.c('border')};"
            f"border-radius:6px;")
        self.lbl_page.setStyleSheet(f"color:{theme.c('subtext')};")
