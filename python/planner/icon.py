"""트레이/창 아이콘.

실행파일과 같은 폴더에 PlanManager.ico 가 있으면 그것을 쓰고,
없으면 코드로 간단한 아이콘(둥근 사각형 + 시계바늘)을 그린다.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPen, QPixmap


def _exe_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def make_icon() -> QIcon:
    search_dirs = [_exe_dir()]
    # PyInstaller onefile: 번들된 리소스는 _MEIPASS 에 풀린다
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        search_dirs.append(Path(meipass))
    for d in search_dirs:
        for name in ("PlanManager.ico", "planner.ico", "app.ico"):
            p = d / name
            if p.exists():
                return QIcon(str(p))

    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QBrush(QColor("#1F6FEB")))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(6, 6, 52, 52, 12, 12)
    # 시계 바늘
    p.setPen(QPen(QColor("white"), 5, Qt.SolidLine, Qt.RoundCap))
    center = QPointF(32, 34)
    p.drawLine(center, QPointF(32, 16))
    p.drawLine(center, QPointF(46, 34))
    p.end()
    return QIcon(pix)
