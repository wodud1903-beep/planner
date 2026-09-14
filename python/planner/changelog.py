"""변경 이력 — 버전마다 무엇이 달라졌는지 보여 준다.

원본은 저장소 맨 위의 **CHANGELOG.md 하나**다. 그 파일을 PC 앱(여기), 모바일 웹앱,
릴리스 본문이 모두 읽는다. 커밋 메시지를 옮겨 담은 것이라 같은 내용을 두 번 적지 않는다
(tools/release.py 참고).

본문의 `■ 머리글` 관례를 그대로 두는 것이 중요하다 — 업무자료 화면이 쓰는
kb_tab.body_to_html 을 **그대로 재사용**할 수 있어서, 그리는 코드를 새로 만들 필요가 없다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
    QSplitter, QTextBrowser, QVBoxLayout, QWidget)

from . import config, theme
from .kb_tab import body_to_html

FILE = "CHANGELOG.md"

# '## v1.11.0 — 제목 (2026-09-13)'
_SEC = re.compile(r"^## v(\d+\.\d+\.\d+)(?:\s*[—-]\s*(.*?))?\s*(?:\(([^)]*)\))?\s*$")


def _candidates() -> list:
    """CHANGELOG.md 가 있을 만한 자리들 — 앞쪽이 먼저다."""
    here = Path(__file__).resolve()
    out = []
    # 1) exe 로 묶였을 때 (PyInstaller 가 풀어 놓는 자리)
    base = getattr(sys, "_MEIPASS", "")
    if base:
        out.append(Path(base) / FILE)
    # 2) 소스에서 돌릴 때 — python/planner/ 에서 두 칸 위가 저장소 맨 위
    out.append(here.parents[2] / FILE)
    out.append(here.parents[1] / FILE)
    # 3) 옆에 복사해 둔 경우
    out.append(here.parent / FILE)
    return out


def text() -> str:
    """CHANGELOG.md 내용. 못 찾으면 빈 글자."""
    for p in _candidates():
        try:
            if p.is_file():
                return p.read_text(encoding="utf-8")
        except OSError:
            continue
    return ""


def sections(src: str = "") -> list:
    """[{version, title, date, body}] — 적힌 순서(새 것부터) 그대로."""
    src = src if src else text()
    out: list = []
    cur = None
    for line in src.splitlines():
        m = _SEC.match(line)
        if m:
            if cur is not None:
                out.append(cur)
            cur = {"version": m.group(1), "title": (m.group(2) or "").strip(),
                   "date": (m.group(3) or "").strip(), "body": ""}
            continue
        if cur is not None:
            cur["body"] += line + "\n"
    if cur is not None:
        out.append(cur)
    for s in out:
        s["body"] = s["body"].strip("\n")
    return out


def label(sec: dict) -> str:
    """목록에 보여 줄 한 줄."""
    head = "v" + sec["version"]
    if sec.get("date"):
        head += f"  ({sec['date']})"
    return head


class ChangelogWindow(QDialog):
    """왼쪽에 버전 목록, 오른쪽에 그 버전의 변경 내용."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("변경 이력")
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.resize(980, 700)

        v = QVBoxLayout(self)
        top = QHBoxLayout()
        self.lbl_now = QLabel(f"지금 쓰는 버전: v{config.APP_VERSION}")
        self.lbl_now.setStyleSheet("font-weight:bold;")
        top.addWidget(self.lbl_now)
        top.addStretch()
        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet(f"color:{theme.c('subtext')};")
        top.addWidget(self.lbl_count)
        v.addLayout(top)

        split = QSplitter(Qt.Horizontal)
        self.lst = QListWidget()
        self.lst.currentRowChanged.connect(self._show)
        split.addWidget(self.lst)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 0, 0, 0)
        self.txt = QTextBrowser()
        self.txt.setOpenExternalLinks(True)
        rv.addWidget(self.txt, 1)
        split.addWidget(right)
        split.setSizes([260, 720])
        v.addWidget(split, 1)

        row = QHBoxLayout()
        row.addStretch()
        self.btn_close = QPushButton("닫기")
        self.btn_close.clicked.connect(self.accept)
        row.addWidget(self.btn_close)
        v.addLayout(row)

        self._secs = sections()
        self._fill()

    def _fill(self):
        self.lst.clear()
        if not self._secs:
            self.lbl_count.setText("변경 이력을 찾지 못했습니다")
            self.txt.setHtml(body_to_html(
                "변경 이력 파일(CHANGELOG.md)을 찾지 못했습니다.\n"
                "저장소에서 받은 판이 아니라면 안 들어 있을 수 있습니다."))
            return
        self.lbl_count.setText(f"{len(self._secs)}개 버전")
        now = config.APP_VERSION
        for s in self._secs:
            it = QListWidgetItem(label(s))
            if s["version"] == now:
                f = it.font()
                f.setBold(True)
                it.setFont(f)
                it.setText(label(s) + "  ← 지금")
            self.lst.addItem(it)
        self.lst.setCurrentRow(0)

    def _show(self, row: int):
        if not (0 <= row < len(self._secs)):
            return
        s = self._secs[row]
        head = f"■ v{s['version']}"
        if s["title"]:
            head += f" — {s['title']}"
        if s["date"]:
            head += f"   ({s['date']})"
        self.txt.setHtml(body_to_html(head + "\n" + s["body"]))

    def apply_theme(self):
        self.lbl_count.setStyleSheet(f"color:{theme.c('subtext')};")
        self._show(self.lst.currentRow())


def show_for(parent=None) -> "ChangelogWindow":
    w = ChangelogWindow(parent)
    w.exec()
    return w
