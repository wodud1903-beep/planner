"""견적서/계약서 이미지 보기 창.

시트 S열에는 `=IMAGE("주소")` 수식으로 그림이 들어 있다. 표에서 [보기] 를 누르면
그 주소의 원본을 내려받아 크게 보여준다. 시트를 열지 않고도 견적서를 확인할 수 있다.
"""

from __future__ import annotations

import threading
import webbrowser

import requests
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout,
)

from . import config, theme


def fetch_image(url: str, auth=None) -> bytes:
    """이미지 원본을 내려받는다.

    시트에 넣은 주소는 '링크가 있는 누구나 보기' 라 보통 그냥 받아진다.
    혹시 막히면 로그인 토큰을 붙여 한 번 더 시도한다(앱이 올린 파일이라 접근 가능).
    """
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200 and r.content[:2] not in (b"<h", b"<!"):
            return r.content
    except Exception:
        pass
    if auth is not None:
        try:
            r = requests.get(url, headers=auth._headers(), timeout=30)
            if r.status_code == 200:
                return r.content
        except Exception:
            pass
    return b""


class DocViewer(QDialog):
    """이미지를 받아서 보여주는 창 (받는 동안 창은 먼저 뜬다)."""

    sig_loaded = Signal(object, str)      # (bytes|None, error)

    def __init__(self, title: str, url: str, auth=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"견적서 / 계약서 · {title}")
        self.resize(880, 760)
        self._url = url

        v = QVBoxLayout(self)
        self.lbl_info = QLabel("이미지를 불러오는 중입니다…")
        self.lbl_info.setStyleSheet(f"color:{theme.c('subtext')};")
        v.addWidget(self.lbl_info)

        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.img = QLabel()
        self.img.setAlignment(Qt.AlignCenter)
        self.area.setWidget(self.img)
        v.addWidget(self.area, 1)

        row = QHBoxLayout()
        btn_web = QPushButton("브라우저에서 열기")
        btn_web.clicked.connect(lambda: webbrowser.open(self._url))
        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(self.accept)
        row.addWidget(btn_web)
        row.addStretch()
        row.addWidget(btn_close)
        v.addLayout(row)

        self.sig_loaded.connect(self._on_loaded)

        def worker():
            data = fetch_image(url, auth)
            self.sig_loaded.emit(data or None,
                                 "" if data else "이미지를 불러오지 못했습니다.")
        threading.Thread(target=worker, daemon=True).start()

    def _on_loaded(self, data, err: str):
        if not data:
            self.lbl_info.setText(
                (err or "실패") + "\n[브라우저에서 열기] 로 확인해 보세요.")
            return
        pm = QPixmap()
        if not pm.loadFromData(bytes(data)):
            self.lbl_info.setText(
                "이미지 형식을 읽지 못했습니다.\n[브라우저에서 열기] 로 확인해 보세요.")
            return
        # 창보다 크면 폭에 맞춰 줄인다(스크롤로 볼 수 있게 원본 비율 유지)
        w = max(320, self.area.viewport().width() - 8)
        if pm.width() > w:
            pm = pm.scaledToWidth(w, Qt.SmoothTransformation)
        self.img.setPixmap(pm)
        self.lbl_info.setText(f"{pm.width()} × {pm.height()}")

    @classmethod
    def show_for(cls, title: str, url: str, auth=None, parent=None):
        d = cls(title, url, auth, parent)
        d.exec()
