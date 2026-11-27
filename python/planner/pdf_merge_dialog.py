"""PDF 병합 — 차례 정하기 창 · 다 만든 뒤 창(v1.37, 고객정보 탭).

지점장(F3): "다중선택 후 pdf 병합 버튼 — 단, pdf 병합 시 파일의 순서를 지정할 수 있게."
  · 고른 파일이 작은 그림과 함께 줄지어 나온다(PDF 는 첫 쪽 · 쪽 수).
  · 끌어서 옮기거나 [▲ 위로] [▼ 아래로], 넣지 않을 것은 [빼기].
  · [병합] → 저장할 곳 묻기(지금 폴더 · '폴더명_병합_YYMMDD.pdf') → 만들기 → [폴더 열기] [카톡으로 복사].
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QImageReader, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout,
)

from . import pdf_merge, theme

try:                                     # QtPdf 가 없으면 PDF 는 기본 그림으로
    from PySide6.QtPdf import QPdfDocument
except Exception:                        # pragma: no cover
    QPdfDocument = None

THUMB = 56


def _blank(text: str) -> QPixmap:
    pm = QPixmap(THUMB, THUMB)
    pm.fill(QColor(theme.c("header_bg")))
    p = QPainter(pm)
    p.setPen(QColor(theme.c("subtext")))
    p.drawRect(0, 0, THUMB - 1, THUMB - 1)
    p.drawText(pm.rect(), Qt.AlignCenter, text)
    p.end()
    return pm


def thumbnail(name: str, data: bytes) -> QPixmap:
    """작은 그림 — 그림은 줄여서, PDF 는 첫 쪽. 못 그리면 'PDF' · '그림' 글자 칸."""
    kind = pdf_merge.kind_of(name)
    try:
        if kind == "image":
            ba = QByteArray(bytes(data))
            buf = QBuffer(ba)
            buf.open(QIODevice.ReadOnly)
            rd = QImageReader(buf)
            try:
                rd.setAutoTransform(True)
                sz = rd.size()
                if sz.isValid() and max(sz.width(), sz.height()) > THUMB * 2:
                    rd.setScaledSize(sz.scaled(THUMB * 2, THUMB * 2, Qt.KeepAspectRatio))
                img = rd.read()
            finally:
                del rd                    # ⚠️ 읽개 먼저(pdf_merge.image_frames 설명 — TIFF 가 꺼짐)
                buf.close()
            if not img.isNull():
                return QPixmap.fromImage(img.scaled(THUMB, THUMB, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        elif kind == "pdf" and QPdfDocument is not None:
            buf = QBuffer()
            buf.setData(QByteArray(bytes(data)))
            buf.open(QIODevice.ReadOnly)
            doc = QPdfDocument()
            doc.load(buf)
            try:
                if doc.pageCount() > 0:
                    ps = doc.pagePointSize(0)
                    s = QSize(int(ps.width()), int(ps.height())).scaled(THUMB * 2, THUMB * 2, Qt.KeepAspectRatio)
                    img = doc.render(0, s)
                    if not img.isNull():
                        bg = QImage(img.size(), QImage.Format_RGB32)
                        bg.fill(QColor(Qt.white))
                        p = QPainter(bg)
                        p.drawImage(0, 0, img)
                        p.end()
                        return QPixmap.fromImage(bg.scaled(THUMB, THUMB, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            finally:
                doc.close()
    except Exception:
        pass
    return _blank("PDF" if kind == "pdf" else "그림")


class MergeOrderDialog(QDialog):
    """차례 정하기 — items = [(이름, 바이트)] (고른 차례 그대로 시작)."""

    def __init__(self, items: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PDF 병합 — 차례 정하기")
        self.setModal(True)
        self.resize(520, 520)
        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        tip = QLabel("위에서부터 이 차례대로 PDF 한 개로 합칩니다.\n끌어서 옮기거나 [▲ 위로] [▼ 아래로] 로 바꾸세요.")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        mid = QHBoxLayout()
        self.list = QListWidget()
        self.list.setIconSize(QSize(THUMB, THUMB))
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setSpacing(2)
        mid.addWidget(self.list, 1)
        side = QVBoxLayout()
        self.btn_up = QPushButton("▲ 위로")
        self.btn_down = QPushButton("▼ 아래로")
        self.btn_remove = QPushButton("빼기")
        for b in (self.btn_up, self.btn_down, self.btn_remove):
            side.addWidget(b)
        side.addStretch(1)
        mid.addLayout(side)
        lay.addLayout(mid, 1)
        bot = QHBoxLayout()
        self.lbl_count = QLabel("")
        bot.addWidget(self.lbl_count, 1)
        self.btn_merge = QPushButton("병합")
        self.btn_merge.setObjectName("primary")
        self.btn_merge.setDefault(True)
        self.btn_cancel = QPushButton("취소")
        bot.addWidget(self.btn_merge)
        bot.addWidget(self.btn_cancel)
        lay.addLayout(bot)

        self._data = {}
        for i, (name, data) in enumerate(items):
            key = f"{i}:{name}"
            self._data[key] = (name, data)
            it = QListWidgetItem(QIcon(thumbnail(name, data)), "")
            it.setData(Qt.UserRole, key)
            self.list.addItem(it)
        self.list.setCurrentRow(0)
        self._renumber()

        self.btn_up.clicked.connect(lambda: self.move_item(-1))
        self.btn_down.clicked.connect(lambda: self.move_item(1))
        self.btn_remove.clicked.connect(self.remove)
        self.btn_merge.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        self.list.model().rowsMoved.connect(lambda *_a: self._renumber())

    def _label(self, row: int, key: str) -> str:
        name, data = self._data[key]
        if pdf_merge.kind_of(name) == "pdf":
            n = pdf_merge.pdf_pages(data)
            what = f"PDF {n}쪽" if n else "PDF"
        else:
            what = "그림"
        return f"{row + 1}.  {name}\n      {what}"

    def _renumber(self) -> None:
        for r in range(self.list.count()):
            it = self.list.item(r)
            it.setText(self._label(r, it.data(Qt.UserRole)))
        n = self.list.count()
        self.lbl_count.setText(f"파일 {n}개")
        self.btn_merge.setEnabled(n > 0)
        self.btn_remove.setEnabled(n > 0)

    def move_item(self, delta: int) -> None:
        r = self.list.currentRow()
        t = r + delta
        if r < 0 or not (0 <= t < self.list.count()):
            return
        it = self.list.takeItem(r)
        self.list.insertItem(t, it)
        self.list.setCurrentRow(t)
        self._renumber()

    def remove(self) -> None:
        r = self.list.currentRow()
        if r < 0:
            return
        self.list.takeItem(r)
        self.list.setCurrentRow(min(r, self.list.count() - 1))
        self._renumber()

    def items(self) -> list:
        """지금 차례의 [(이름, 바이트)]."""
        return [self._data[self.list.item(r).data(Qt.UserRole)] for r in range(self.list.count())]

    def names(self) -> list:
        return [n for n, _d in self.items()]
