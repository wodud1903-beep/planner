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
    QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout,
    QWidget)

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
        self._zoom = 0.0      # 0 이면 '칸에 맞춤', 그 외는 배율

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
        self.btn_zoom_out = QPushButton("－")
        self.btn_zoom_out.setToolTip("축소 (Ctrl + 마우스 휠)")
        self.btn_zoom_out.clicked.connect(lambda: self.zoom_by(1 / 1.25))
        bar.addWidget(self.btn_zoom_out)
        self.btn_zoom_in = QPushButton("＋")
        self.btn_zoom_in.setToolTip("확대 (Ctrl + 마우스 휠)")
        self.btn_zoom_in.clicked.connect(lambda: self.zoom_by(1.25))
        bar.addWidget(self.btn_zoom_in)
        self.btn_fit = QPushButton("맞춤")
        self.btn_fit.setToolTip("칸에 맞추기 (두 번 눌러도 됩니다)")
        self.btn_fit.clicked.connect(self.zoom_fit)
        bar.addWidget(self.btn_fit)
        self.lbl_zoom = QLabel("")
        self.lbl_zoom.setMinimumWidth(52)
        self.lbl_zoom.setAlignment(Qt.AlignCenter)
        bar.addWidget(self.lbl_zoom)
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

        # 확대하면 그림이 칸보다 커지므로 스크롤 안에 담는다.
        self.view = QLabel("파일을 고르면 여기에 보입니다.")
        self.view.setAlignment(Qt.AlignCenter)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.view)
        self.scroll.setWidgetResizable(True)      # '맞춤' 일 때는 칸에 맞춘다
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.setMinimumSize(QSize(220, 220))
        self.scroll.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        v.addWidget(self.scroll, 1)

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
        self._zoom = 0.0            # 새 파일은 '맞춤' 부터
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
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
        self._zoom = 0.0            # 새 파일은 '맞춤' 부터
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
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

    # ------------------------------------------------------------ 확대
    MIN_ZOOM, MAX_ZOOM = 0.1, 8.0

    def zoom_fit(self):
        """칸에 맞춰 보기(기본)."""
        self._zoom = 0.0
        self.scroll.setWidgetResizable(True)
        # 맞춰 보는 동안에는 스크롤막대가 필요 없다. 켜 두면 막대가 생겼다
        # 사라지며 칸 크기가 흔들려 맞춤 크기가 그때그때 달라진다.
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._redraw()
        self._update_bar()

    def zoom_by(self, factor: float):
        """지금 크기를 기준으로 키우거나 줄인다."""
        if self._src is None and self._doc is None:
            return
        cur = self._zoom or self._fit_scale()
        self.set_zoom(cur * factor)

    def set_zoom(self, scale: float):
        scale = max(self.MIN_ZOOM, min(self.MAX_ZOOM, scale))
        # 확대하기 전에 지금 화면 한가운데가 그림의 어디쯤인지 기억해 둔다.
        # 그걸 안 하면 확대할 때마다 왼쪽 위 구석으로 튀어, 보고 있던 자리가
        # 화면 밖으로 사라진다.
        before = self._center_ratio()
        self._zoom = scale
        # 확대하면 그림이 칸보다 커진다 → 스크롤이 생기도록 칸을 놓아 준다
        self.scroll.setWidgetResizable(False)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._redraw()
        self._center_on(before)
        self._update_bar()

    def _center_ratio(self):
        """지금 보고 있는 한가운데가 그림 전체의 몇 % 지점인가 (0~1)."""
        hb, vb = self.scroll.horizontalScrollBar(), self.scroll.verticalScrollBar()
        vp = self.scroll.viewport().size()
        w = max(1, self.view.width()), max(1, self.view.height())
        if self.fitted:
            return 0.5, 0.5
        return ((hb.value() + vp.width() / 2) / w[0],
                (vb.value() + vp.height() / 2) / w[1])

    def _center_on(self, ratio):
        """그 지점이 다시 한가운데 오도록 스크롤을 옮긴다."""
        rx, ry = ratio
        hb, vb = self.scroll.horizontalScrollBar(), self.scroll.verticalScrollBar()
        vp = self.scroll.viewport().size()
        hb.setValue(int(self.view.width() * rx - vp.width() / 2))
        vb.setValue(int(self.view.height() * ry - vp.height() / 2))

    @property
    def zoom(self) -> float:
        """지금 배율. '맞춤' 이어도 실제 배율을 돌려준다."""
        return self._zoom or self._fit_scale()

    @property
    def fitted(self) -> bool:
        return self._zoom == 0.0

    # 배율 1.0 = '원래 크기'. 그림은 제 픽셀 크기, PDF 는 96dpi 로 친다
    # (종이 크기는 포인트(72dpi)로 오므로 화면 기준으로 환산한다).
    PDF_DPI = 96.0

    def _natural(self) -> QSize:
        """돌리기 전, 배율 1.0 일 때의 크기."""
        if self._src is not None:
            return self._src.size()
        if self._doc is not None:
            pt = self._doc.pagePointSize(self._page)
            if pt.width() > 0 and pt.height() > 0:
                k = self.PDF_DPI / 72.0
                return QSize(max(1, int(pt.width() * k)),
                             max(1, int(pt.height() * k)))
        return QSize(0, 0)

    def _fit_scale(self) -> float:
        """칸에 맞췄을 때의 배율. 그리지 않고 크기만으로 구한다."""
        nat = self._natural()
        if nat.width() <= 0 or nat.height() <= 0:
            return 1.0
        w, h = nat.width(), nat.height()
        if self._angle in (90, 270):
            w, h = h, w                 # 돌리면 가로세로가 바뀐다
        box = self._box()
        return max(0.01, min(box.width() / w, box.height() / h))

    def _render(self, scale: float):
        """그 배율로 그린 뒤 돌려서 돌려준다.

        PDF 는 보여 줄 크기로 '직접' 그린다 — 작게 그려 놓고 늘리면 글자가
        뭉개지기 때문이다. 그림은 원본을 그 크기로 줄이거나 늘린다.
        """
        nat = self._natural()
        if nat.width() <= 0:
            return None
        w = max(1, int(nat.width() * scale))
        h = max(1, int(nat.height() * scale))
        if self._src is not None:
            pix = self._src.scaled(w, h, Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation)
        else:
            img = self._doc.render(self._page, QSize(w, h))
            if not isinstance(img, QImage) or img.isNull():
                return None
            # 종이는 흰색으로 깔아 준다. 그냥 그리면 글자만 있고 배경이 비어서,
            # 어두운 화면에서는 검은 바탕에 검은 글씨가 되어 안 보인다.
            page = QImage(img.size(), QImage.Format_RGB32)
            page.fill(QColor("#FFFFFF"))
            q = QPainter(page)
            q.drawImage(0, 0, img)
            q.end()
            pix = QPixmap.fromImage(page)
        if self._angle:
            pix = pix.transformed(QTransform().rotate(self._angle),
                                  Qt.SmoothTransformation)
        return pix

    def wheelEvent(self, ev):
        """Ctrl + 휠로 확대·축소. 그냥 휠은 스크롤 그대로."""
        if ev.modifiers() & Qt.ControlModifier:
            self.zoom_by(1.25 if ev.angleDelta().y() > 0 else 1 / 1.25)
            ev.accept()
            return
        super().wheelEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        """두 번 누르면 '맞춤' 과 '원래 크기(100%)' 를 오간다."""
        if self._src is None and self._doc is None:
            return
        if self.fitted:
            self.set_zoom(1.0)
        else:
            self.zoom_fit()

    # ------------------------------------------------------------ 그리기
    def _box(self) -> QSize:
        s = self.scroll.viewport().size()
        return QSize(max(80, s.width()), max(80, s.height()))

    def _redraw(self):
        if self._src is None and self._doc is None:
            return
        scale = self._fit_scale() if self.fitted else self._zoom
        pix = self._render(max(self.MIN_ZOOM, min(scale, self.MAX_ZOOM)))
        if pix is None or pix.isNull():
            return
        self.view.setText("")
        self.view.setPixmap(pix)
        if self.fitted:
            self.view.resize(self.scroll.viewport().size())
        else:
            self.view.resize(pix.size())


    def _update_bar(self):
        has = self._src is not None or self._doc is not None
        self.btn_left.setEnabled(has)
        self.btn_right.setEnabled(has)
        for b in (self.btn_zoom_in, self.btn_zoom_out, self.btn_fit):
            b.setEnabled(has)
        self.lbl_zoom.setText(
            ("맞춤" if self.fitted else f"{self._zoom * 100:.0f}%") if has else "")
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
        if self.fitted:            # 확대 중이면 크기를 건드리지 않는다
            self._redraw()

    def apply_theme(self):
        self.view.setStyleSheet(
            f"color:{theme.c('subtext')};border:1px solid {theme.c('border')};"
            f"border-radius:6px;")
        self.lbl_page.setStyleSheet(f"color:{theme.c('subtext')};")
        self.lbl_zoom.setStyleSheet(f"color:{theme.c('subtext')};")
        self.scroll.setStyleSheet(
            f"QScrollArea {{ border:1px solid {theme.c('border')};"
            f" border-radius:6px; }}")
