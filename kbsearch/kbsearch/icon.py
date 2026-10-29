"""트레이/창 아이콘 — 돋보기.

exe 에는 kbsearch.ico 가 함께 묶인다(spec). 파일이 없으면 같은 그림을 코드로 그린다.
kbsearch.ico 도 이 그림(draw)으로 만든다 — make_icon.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPen, QPixmap

ICO_NAME = "kbsearch.ico"


def draw(size: int = 64) -> QPixmap:
    """둥근 네모(청록) + 흰 돋보기."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    k = size / 64.0
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor("#0F766E")))
    p.drawRoundedRect(QRectF(4 * k, 4 * k, 56 * k, 56 * k), 13 * k, 13 * k)
    pen = QPen(QColor("white"), max(1.5, 5.5 * k), Qt.SolidLine, Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QPointF(28 * k, 28 * k), 12.5 * k, 12.5 * k)
    p.drawLine(QPointF(37.5 * k, 37.5 * k), QPointF(48 * k, 48 * k))
    p.end()
    return pix


def _dirs() -> list:
    out = []
    if getattr(sys, "frozen", False):
        out.append(Path(sys.executable).parent)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        out.append(Path(meipass))
    out.append(Path(__file__).resolve().parents[1])
    return out


def make_icon() -> QIcon:
    for d in _dirs():
        p = d / ICO_NAME
        if p.exists():
            ic = QIcon(str(p))
            if not ic.isNull():
                return ic
    ic = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(draw(s))
    return ic
