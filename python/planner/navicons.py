"""왼쪽 메뉴의 선 아이콘 — 코드로 그린다.

이모지는 윈도 판마다 모양·색이 달라 메뉴가 들쭉날쭉하고, 테마색을 따르지 못한다.
윈도 아이콘 글꼴(Segoe Fluent Icons)은 윈도10 에 없다. 그래서 24칸 바둑판 위에
가는 선으로 직접 그린다 — 어느 PC 에서나 같고, 색은 부르는 쪽이 테마에서 넘겨준다.

새 메뉴(기능)가 생기면 `TAB_ICONS` 에 탭 이름 → 아이콘 이름 한 줄을 더한다.
표에 없는 탭은 기본 아이콘(점)으로 나온다.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

# 탭 이름 → 아이콘
TAB_ICONS = {
    "대시보드": "grid",
    "고객관리": "people",
    "고객정보": "folder",
    "멘트복사": "chat",
    "자료검색": "search",
    "수당계산기": "calc",
    "PC 알람": "bell",
}


def for_tab(name: str) -> str:
    return TAB_ICONS.get(name, "dot")


# ---------------------------------------------------------------------------
# 그리기 — 모두 24×24 바둑판 기준
# ---------------------------------------------------------------------------
def _tasks(p: QPainter):
    p.drawRoundedRect(QRectF(3.5, 3.5, 17, 17), 4, 4)
    path = QPainterPath(QPointF(7.5, 12.2))
    path.lineTo(10.6, 15.2)
    path.lineTo(16.5, 9)
    p.drawPath(path)


def _calendar(p: QPainter):
    p.drawRoundedRect(QRectF(3.5, 5, 17, 15.5), 3.5, 3.5)
    p.drawLine(QPointF(3.5, 10), QPointF(20.5, 10))
    p.drawLine(QPointF(8, 3), QPointF(8, 7))
    p.drawLine(QPointF(16, 3), QPointF(16, 7))
    for x in (8, 12, 16):
        p.drawPoint(QPointF(x, 14.5))
    for x in (8, 12):
        p.drawPoint(QPointF(x, 17.5))


def _people(p: QPainter):
    p.drawEllipse(QPointF(9.5, 8.5), 3.4, 3.4)
    path = QPainterPath(QPointF(3.5, 19.5))
    path.cubicTo(3.5, 15, 15.5, 15, 15.5, 19.5)
    p.drawPath(path)
    p.drawArc(QRectF(13.6, 5.4, 6, 6.2), -70 * 16, 220 * 16)
    tail = QPainterPath(QPointF(17.5, 14.6))
    tail.cubicTo(19.5, 15.2, 20.6, 16.8, 20.6, 19.5)
    p.drawPath(tail)


def _folder(p: QPainter):
    path = QPainterPath(QPointF(3.5, 7))
    path.quadTo(3.5, 5, 5.5, 5)
    path.lineTo(9.5, 5)
    path.lineTo(11.5, 7.5)
    path.lineTo(18.5, 7.5)
    path.quadTo(20.5, 7.5, 20.5, 9.5)
    path.lineTo(20.5, 17.5)
    path.quadTo(20.5, 19.5, 18.5, 19.5)
    path.lineTo(5.5, 19.5)
    path.quadTo(3.5, 19.5, 3.5, 17.5)
    path.closeSubpath()
    p.drawPath(path)


def _chat(p: QPainter):
    path = QPainterPath(QPointF(7, 4.5))
    path.lineTo(17, 4.5)
    path.quadTo(20.5, 4.5, 20.5, 8)
    path.lineTo(20.5, 12.5)
    path.quadTo(20.5, 16, 17, 16)
    path.lineTo(11, 16)
    path.lineTo(7, 19.5)
    path.lineTo(7, 16)
    path.quadTo(3.5, 16, 3.5, 12.5)
    path.lineTo(3.5, 8)
    path.quadTo(3.5, 4.5, 7, 4.5)
    p.drawPath(path)
    p.drawLine(QPointF(8, 9), QPointF(16, 9))
    p.drawLine(QPointF(8, 12), QPointF(13, 12))


def _search(p: QPainter):
    p.drawEllipse(QPointF(10.5, 10.5), 6, 6)
    p.drawLine(QPointF(15, 15), QPointF(20, 20))


def _calc(p: QPainter):
    p.drawRoundedRect(QRectF(5, 3.5, 14, 17), 3, 3)
    p.drawRoundedRect(QRectF(8, 6.5, 8, 3.5), 1, 1)
    for y in (13.5, 17):
        for x in (8.8, 12, 15.2):
            p.drawPoint(QPointF(x, y))


def _bell(p: QPainter):
    path = QPainterPath(QPointF(6, 16.5))
    path.lineTo(6, 11)
    path.cubicTo(6, 7.2, 8.6, 5, 12, 5)
    path.cubicTo(15.4, 5, 18, 7.2, 18, 11)
    path.lineTo(18, 16.5)
    path.lineTo(19.5, 17.5)
    path.lineTo(4.5, 17.5)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(12, 3), QPointF(12, 5))
    p.drawArc(QRectF(10, 18, 4, 3), 180 * 16, 180 * 16)


def _gear(p: QPainter):
    p.drawEllipse(QPointF(12, 12), 2.8, 2.8)
    # 톱니 8개를 한 길로 — 톱니 끝 반지름 8.6, 골 6.6
    path = QPainterPath()
    n = 8
    for i in range(n):
        a0 = i * 2 * math.pi / n
        for da, r in ((-0.42, 6.6), (-0.24, 8.6), (0.24, 8.6), (0.42, 6.6)):
            pt = QPointF(12 + r * math.cos(a0 + da), 12 + r * math.sin(a0 + da))
            if i == 0 and da < -0.4:
                path.moveTo(pt)
            else:
                path.lineTo(pt)
    path.closeSubpath()
    p.drawPath(path)


def _plus(p: QPainter):
    p.drawLine(QPointF(12, 5), QPointF(12, 19))
    p.drawLine(QPointF(5, 12), QPointF(19, 12))


def _history(p: QPainter):
    p.drawArc(QRectF(4, 4, 16, 16), 200 * 16, -310 * 16)
    p.drawLine(QPointF(12, 8), QPointF(12, 12))
    p.drawLine(QPointF(12, 12), QPointF(15, 14))
    head = QPainterPath(QPointF(3, 8))
    head.lineTo(4.6, 11.2)
    head.lineTo(7.6, 9.6)
    p.drawPath(head)


def _collapse(p: QPainter):
    for x in (0, 5):
        path = QPainterPath(QPointF(13 + x - 4, 7))
        path.lineTo(8 + x - 4, 12)
        path.lineTo(13 + x - 4, 17)
        p.drawPath(path)


def _expand(p: QPainter):
    for x in (0, 5):
        path = QPainterPath(QPointF(7 + x, 7))
        path.lineTo(12 + x, 12)
        path.lineTo(7 + x, 17)
        p.drawPath(path)


def _grid(p: QPainter):
    for x, y in ((4, 4), (13, 4), (4, 13), (13, 13)):
        p.drawRoundedRect(QRectF(x, y, 7, 7), 2, 2)


def _dot(p: QPainter):
    p.drawEllipse(QPointF(12, 12), 4, 4)


_DRAW = {
    "tasks": _tasks, "calendar": _calendar, "people": _people, "folder": _folder,
    "chat": _chat, "search": _search, "calc": _calc, "bell": _bell, "gear": _gear,
    "plus": _plus, "history": _history, "collapse": _collapse, "expand": _expand,
    "grid": _grid, "dot": _dot,
}

NAMES = tuple(_DRAW)


def pixmap(name: str, color: str, size: int = 20, dpr: float = 2.0,
           width: float = 1.7) -> QPixmap:
    """아이콘 한 장. dpr 배로 크게 그려 고해상도 화면에서도 선이 깨끗하다."""
    px = int(round(size * dpr))
    pix = QPixmap(px, px)
    pix.fill(Qt.transparent)
    pix.setDevicePixelRatio(dpr)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(size / 24.0, size / 24.0)
    pen = QPen(QColor(color), width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    _DRAW.get(name, _dot)(p)
    p.end()
    return pix


def tile_icon(name: str, bg: str, fg: str, size: int = 44) -> QIcon:
    """바로가기 칸 — 둥근 네모 바탕에 흰 선 아이콘(대시보드)."""
    ic = QIcon()
    for dpr in (1.0, 2.0):
        px = int(round(size * dpr))
        pix = QPixmap(px, px)
        pix.fill(Qt.transparent)
        pix.setDevicePixelRatio(dpr)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(bg))
        p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.28, size * 0.28)
        inner = size * 0.56
        off = (size - inner) / 2
        p.translate(off, off)
        p.scale(inner / 24.0, inner / 24.0)
        p.setPen(QPen(QColor(fg), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        _DRAW.get(name, _dot)(p)
        p.end()
        ic.addPixmap(pix)
    return ic


def icon(name: str, color: str, selected: str = "", size: int = 20) -> QIcon:
    """보통 색 + (있으면) 고른 항목 색. 목록은 고른 줄에서 Selected 쪽을 쓴다."""
    ic = QIcon()
    for dpr in (1.0, 2.0):
        ic.addPixmap(pixmap(name, color, size, dpr), QIcon.Normal)
        if selected:
            ic.addPixmap(pixmap(name, selected, size, dpr), QIcon.Selected)
    return ic
