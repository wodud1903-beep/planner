"""오늘의 뉴스 창 — 대시보드 [오늘의 뉴스] 단추로 연다.

받아 둔 뉴스를 **바로** 보여 주고, 뒤에서 새로 받으면 그 자리에서 바꿔 끼운다
(main_window.show_news). 창을 띄운 채로 다른 일을 할 수 있게 모달로 띄우지 않는다.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout,
)

from . import config, news, theme


def colors() -> dict:
    return {
        "text": theme.c("text"), "sub": theme.c("subtext"), "line": theme.c("border"),
        "link": theme.c("accent"), "head_bg": theme.c("header_bg"), "zebra": theme.c("panel_bg"),
        "card": theme.c("panel_bg"), "box": theme.c("brief_bg"),
        "strong": theme.strong, "strong_bg": theme.strong_bg,
    }


def when_text(at: str, now: datetime | None = None) -> str:
    """'오늘 08:52 받음' · '어제 …' · '10/27 …'."""
    try:
        t = datetime.fromisoformat(at)
    except Exception:
        return ""
    now = now or datetime.now()
    d = (now.date() - t.date()).days
    day = "오늘" if d == 0 else "어제" if d == 1 else f"{t:%m/%d}"
    return f"{day} {t:%H:%M} 받음"


class NewsDialog(QDialog):
    refresh_requested = Signal()
    relogin_requested = Signal()

    def __init__(self, doc_id: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{config.APP_NAME} · 오늘의 뉴스")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setModal(False)
        self._doc_id = doc_id
        self._news: dict | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        top = QHBoxLayout()
        title = QLabel("오늘의 뉴스")
        title.setStyleSheet("font-size:17px;font-weight:bold;")
        top.addWidget(title)
        self.lbl_state = QLabel("")
        self.lbl_state.setStyleSheet(f"color:{theme.c('subtext')};")
        top.addWidget(self.lbl_state)
        top.addStretch(1)
        self.btn_login = QPushButton("구글 다시 로그인")
        self.btn_login.setToolTip("뉴스 문서를 읽을 권한을 받으려면 한 번 더 로그인합니다")
        self.btn_login.clicked.connect(self.relogin_requested.emit)
        self.btn_login.hide()
        top.addWidget(self.btn_login)
        self.btn_refresh = QPushButton("새로 받기")
        self.btn_refresh.clicked.connect(self.refresh_requested.emit)
        top.addWidget(self.btn_refresh)
        self.btn_copy = QPushButton("복사")
        self.btn_copy.setToolTip("뉴스를 글로 복사합니다(카톡에 붙여 넣기)")
        self.btn_copy.clicked.connect(self._copy)
        self.btn_copy.setMinimumWidth(self.btn_copy.fontMetrics().horizontalAdvance("복사됨 ✓") + 28)
        top.addWidget(self.btn_copy)
        btn_open = QPushButton("문서 열기")
        btn_open.clicked.connect(self._open_doc)
        top.addWidget(btn_open)
        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(self.close)
        top.addWidget(btn_close)
        root.addLayout(top)

        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)       # [기사 원문 보기] 는 브라우저로
        # 바탕은 창 색, 뉴스는 그 위의 흰 카드 — 건마다 또렷이 갈린다
        self.view.setStyleSheet(f"QTextBrowser {{ background:{theme.c('window_bg')}; border:0; }}")
        self.view.document().setDocumentMargin(4)
        root.addWidget(self.view, 1)

        scr = QGuiApplication.primaryScreen()
        g = scr.availableGeometry() if scr else None
        w = min(1100, int(g.width() * 0.8)) if g else 1000
        h = int(g.height() * 0.82) if g else 760
        self.resize(w, h)

    # ---- 바깥(main_window)이 부른다 ----
    def show_news(self, n: dict | None):
        self._news = n
        self.btn_login.hide()
        if not n or not n.get("blocks"):
            self.view.setHtml(f"<p style='color:{theme.c('subtext')};'>뉴스를 받는 중입니다…</p>")
            return
        self.view.setHtml(news.render_html(n, colors()))
        self.lbl_state.setText(when_text(n.get("at", "")))

    def set_busy(self, on: bool):
        self.btn_refresh.setEnabled(not on)
        if on:
            self.lbl_state.setText("새로 받는 중…")

    def set_error(self, msg: str, need_scope: bool = False):
        self.btn_refresh.setEnabled(True)
        self.btn_login.setVisible(need_scope)
        if need_scope:
            msg = ("뉴스 문서를 읽을 권한이 아직 없습니다.\n"
                   "[구글 다시 로그인] 을 누르고 동의 화면에서 '모두 선택' 에 체크해 주세요.")
        if self._news and self._news.get("blocks"):
            # 받아 둔 것은 그대로 두고 위에만 알린다
            self.lbl_state.setText("새로 받지 못함 — " + msg.splitlines()[0]
                                   + (f" · {when_text(self._news.get('at', ''))}" if self._news.get("at") else ""))
        else:
            self.lbl_state.setText("")
            body = "<br>".join(theme_escape(x) for x in msg.splitlines())
            self.view.setHtml(f"<p style='color:{theme.c('status_bad')};'>{body}</p>")

    # ---- 단추 ----
    def _copy(self):
        if not (self._news and self._news.get("blocks")):
            return
        QGuiApplication.clipboard().setText(news.render_text(self._news))
        self.btn_copy.setText("복사됨 ✓")
        QTimer.singleShot(1500, lambda: self.btn_copy.setText("복사"))

    def _open_doc(self):
        import webbrowser
        if self._doc_id:
            webbrowser.open(news.doc_url(self._doc_id))


def theme_escape(s: str) -> str:
    from html import escape
    return escape(s or "")
