"""표 칸 꾸미기(v1.35) — 고객관리 표의 '금융사 · 차종' 두 줄 칸과 짧은 날짜.

1536 폭(노트북 125%)에서 고객 표가 넘쳐 '내용' 이 눌리고 [안내멘트 복사] 가 잘렸다.
금융사와 차종을 한 칸에 두 줄로(위: 금융사 작게 · 아래: 차종) 넣고, 날짜를
'26.11.14' 로 줄여 그만큼 폭을 돌려준다. 원래 글은 풍선 도움말로 본다.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPalette
from PySide6.QtWidgets import QApplication, QStyle, QStyledItemDelegate, QStyleOptionViewItem

from . import sheets, theme


def short_date(s) -> str:
    """'2026. 11. 14' → '26.11.14'. 날짜로 못 읽으면 받은 글 그대로."""
    d = sheets.parse_date(s)
    return f"{d:%y.%m.%d}" if d else (s or "")


def _last_line(text) -> str:
    """칸 글의 마지막 줄. ⚠️ Qt 는 그리기 직전 줄바꿈(\\n)을 U+2028(줄 구분자)로 바꿔 넘긴다 —
    \\n 만 찾으면 두 줄이 통째로 아래 줄에 다시 그려져 글자가 겹쳤다(v1.35 첫 판)."""
    t = str(text or "").replace("\u2028", "\n")
    return t.rsplit("\n", 1)[-1]


class TwoLineDelegate(QStyledItemDelegate):
    """위 줄(TOP 역할에 둔 글)은 작고 흐리게, 아래 줄(칸 글의 마지막 줄)은 보통 글씨로."""

    TOP = Qt.UserRole + 7
    PAD = 6

    def _fonts(self, base: QFont):
        top = QFont(base)
        top.setPointSizeF(max(7.5, base.pointSizeF() - 1.5))
        top.setBold(False)
        top.setWeight(QFont.Normal)
        return top, QFont(base)

    def paint(self, p, option, index):
        top = index.data(self.TOP) or ""
        if not top:
            return super().paint(p, option, index)
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        bottom = _last_line(opt.text)
        opt.text = ""
        style = opt.widget.style() if opt.widget is not None else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, p, opt.widget)   # 배경(진행현황 색)·선택색
        r = opt.rect.adjusted(self.PAD, 1, -self.PAD, -1)
        sel = bool(opt.state & QStyle.State_Selected)
        f1, f2 = self._fonts(opt.font)
        m1, m2 = QFontMetrics(f1), QFontMetrics(f2)
        h1, h2 = m1.height(), m2.height()
        y = r.top() + max(0, (r.height() - h1 - h2) // 2)
        hi = opt.palette.color(QPalette.HighlightedText)
        p.save()
        p.setFont(f1)
        p.setPen(hi if sel else QColor(theme.c("subtext")))
        p.drawText(QRect(r.left(), y, r.width(), h1), Qt.AlignLeft | Qt.AlignVCenter,
                   m1.elidedText(top, Qt.ElideRight, r.width()))
        p.setFont(f2)
        fg = index.data(Qt.ForegroundRole)
        col = hi if sel else (fg.color() if fg is not None and hasattr(fg, "color")
                              else opt.palette.color(QPalette.Text))
        p.setPen(col)
        p.drawText(QRect(r.left(), y + h1, r.width(), h2), Qt.AlignLeft | Qt.AlignVCenter,
                   m2.elidedText(bottom, Qt.ElideRight, r.width()))
        p.restore()

    def sizeHint(self, option, index):
        top = index.data(self.TOP) or ""
        sh = super().sizeHint(option, index)
        if not top:
            return sh
        bottom = _last_line(index.data())
        f1, f2 = self._fonts(option.font)
        m1, m2 = QFontMetrics(f1), QFontMetrics(f2)
        w = max(m1.horizontalAdvance(top), m2.horizontalAdvance(bottom)) + 2 * self.PAD + 2
        return QSize(w, max(sh.height(), m1.height() + m2.height() + 4))
