"""[Google 계정으로 로그인] 단추.

구글 로고는 브랜드 표시라 테마와 상관없이 늘 제 색(파랑·초록·노랑·빨강)으로
그린다. 단추의 배경·테두리·글자색만 밝은 화면/어두운 화면에 맞춰 바꾼다
(구글이 안내하는 두 가지 배색 그대로다).

로고는 파일로 두지 않고 코드가 그린다 — exe 하나로 배포하므로 딸린 파일이
없어야 하고, icon.py 도 같은 방식이다.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QPushButton

from . import theme

# 구글 'G' 마크 (18×18 기준). 네 조각이 각각 제 색을 갖는다.
_G_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 18">
<path fill="#4285F4" d="M17.64 9.2045c0-.6381-.0573-1.2518-.1636-1.8409H9v3.4814h4.8436c-.2086
 1.125-.8427 2.0782-1.7959 2.7164v2.2581h2.9087c1.7018-1.5668 2.6836-3.874 2.6836-6.615z"/>
<path fill="#34A853" d="M9 18c2.43 0 4.4673-.806 5.9564-2.1805l-2.9087-2.2581c-.8059.54-1.8368
 .859-3.0477.859-2.344 0-4.3282-1.5831-5.036-3.7104H.9574v2.3318C2.4382 15.9832 5.4818 18 9 18z"/>
<path fill="#FBBC05" d="M3.964 10.71c-.18-.54-.2822-1.1168-.2822-1.71s.1023-1.17.2823-1.71V4.9582H
 .9573A8.9965 8.9965 0 0 0 0 9c0 1.4523.3477 2.8268.9573 4.0418L3.964 10.71z"/>
<path fill="#EA4335" d="M9 3.5795c1.3214 0 2.5077.4541 3.4405 1.346l2.5813-2.5814C13.4632.8918
 11.426 0 9 0 5.4818 0 2.4382 2.0168.9573 4.9582L3.964 7.29C4.6718 5.1627 6.656 3.5795 9 3.5795z"/>
</svg>"""


def google_g_icon(px: int = 18) -> QIcon:
    """구글 'G' 마크. 그리지 못하면 빈 아이콘을 돌려준다(단추는 글자로 남는다)."""
    try:
        from PySide6.QtSvg import QSvgRenderer
        pix = QPixmap(px, px)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        QSvgRenderer(_G_SVG.encode("utf-8")).render(p)
        p.end()
        return QIcon(pix)
    except Exception:
        return QIcon()


def button_css() -> str:
    """구글이 안내하는 배색 — 어두운 화면과 밝은 화면 두 벌."""
    if theme.is_dark():
        bg, border, fg = "#131314", "#8E918F", "#E3E3E3"
        hover, pressed = "#1E1F20", "#282A2C"
    else:
        bg, border, fg = "#FFFFFF", "#747775", "#1F1F1F"
        hover, pressed = "#F2F2F2", "#E8E8E8"
    return (
        f"QPushButton {{ background:{bg}; color:{fg};"
        f" border:1px solid {border}; border-radius:4px;"
        f" padding:6px 16px; font-weight:600; text-align:center; }}"
        f"QPushButton:hover {{ background:{hover}; }}"
        f"QPushButton:pressed {{ background:{pressed}; }}"
        f"QPushButton:disabled {{ color:{theme.c('subtext')};"
        f" border-color:{theme.c('border')}; }}")


class GoogleSignInButton(QPushButton):
    """로그인 전에만 보이는 [Google 계정으로 로그인] 단추."""

    LABEL = "Google 계정으로 로그인"
    BUSY = "로그인 중…"

    def __init__(self, parent=None):
        super().__init__(self.LABEL, parent)
        self.setIcon(google_g_icon(18))
        self.setIconSize(QSize(18, 18))
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(34)
        self.setToolTip("구글 계정으로 로그인하면 일정·할일·고객관리가 연결됩니다")
        self.apply_theme()

    def apply_theme(self):
        self.setStyleSheet(button_css())

    def set_busy(self, busy: bool):
        """로그인 창이 떠 있는 동안 두 번 눌리지 않게 잠근다."""
        self.setEnabled(not busy)
        self.setText(self.BUSY if busy else self.LABEL)
