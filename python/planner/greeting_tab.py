"""인삿말 탭 — 채널별 인삿말을 한 번 눌러 클립보드에 복사한다.

쓰시던 HTML 도구를 그대로 옮긴 화면이다. 채널마다 [상담후] / [부재중]
두 버튼이 있고, 누르면 그 문구가 복사되며 버튼이 잠깐 초록으로 바뀐다.
문구는 [문구 편집] 에서 직접 고칠 수 있다.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy, QTextEdit, QVBoxLayout,
    QWidget,
)

from . import config, greetings, theme

# 원본 도구와 같은 색 — 파랑 = 상담후, 청록 = 부재중, 초록 = 복사됨
COL_AFTER = "#2563EB"
COL_AFTER_H = "#1D4ED8"
COL_MISS = "#0D9488"
COL_MISS_H = "#0F766E"
COL_OK = "#16A34A"

COLS = 2                  # 한 줄에 카드 몇 개
_FLASH_MS = 1200


def _btn_css(base: str, hover: str) -> str:
    return (f"QPushButton{{background:{base};color:#FFFFFF;border:none;"
            f"border-radius:10px;padding:10px 8px;font-size:14px;font-weight:bold;}}"
            f"QPushButton:hover{{background:{hover};}}")


class _CopyButton(QPushButton):
    """누르면 문구를 복사하고 잠깐 '복사됨' 으로 바뀌는 버튼."""

    def __init__(self, label: str, base: str, hover: str, parent=None):
        super().__init__(label, parent)
        self._label = label
        self._base, self._hover = base, hover
        self._text = ""
        self.setMinimumHeight(46)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(_btn_css(base, hover))
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._restore)

    def set_message(self, text: str) -> None:
        self._text = text or ""
        self.setToolTip(self._text or "(문구가 비어 있습니다)")
        self.setEnabled(bool(self._text.strip()))

    def flash(self) -> None:
        self.setText("복사됨 ✓")
        self.setStyleSheet(_btn_css(COL_OK, COL_OK))
        self._timer.start(_FLASH_MS)

    def _restore(self) -> None:
        self.setText(self._label)
        self.setStyleSheet(_btn_css(self._base, self._hover))

    @property
    def message(self) -> str:
        return self._text


class _ChannelCard(QFrame):
    def __init__(self, on_copy, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        # 가로만 늘어나고 세로는 내용 높이 그대로 — 카드마다 크기가 달라지지 않게
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 12)
        v.setSpacing(8)

        self.lbl = QLabel("")
        v.addWidget(self.lbl)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_after = _CopyButton("상담후", COL_AFTER, COL_AFTER_H)
        self.btn_miss = _CopyButton("부재중", COL_MISS, COL_MISS_H)
        for b, state in ((self.btn_after, "상담후"), (self.btn_miss, "부재중")):
            b.clicked.connect(lambda _c=False, bb=b, st=state: on_copy(self, bb, st))
            row.addWidget(b, 1)
        v.addLayout(row)

        self.name = ""

    def set_channel(self, ch: dict) -> None:
        self.name = (ch.get("name") or "").strip()
        self.lbl.setText(self.name)
        self.btn_after.set_message(ch.get("after", ""))
        self.btn_miss.set_message(ch.get("miss", ""))

    def apply_theme(self) -> None:
        self.setStyleSheet(
            f"QFrame{{background:{theme.c('panel_bg')};"
            f"border:1px solid {theme.c('border')};border-radius:12px;}}")
        self.lbl.setStyleSheet(
            f"color:{theme.c('text')};font-size:15px;font-weight:bold;"
            "background:transparent;border:none;")


class GreetingEditDialog(QDialog):
    """문구 편집 — 채널 목록 + 두 문구."""

    def __init__(self, items: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("멘트 문구 편집")
        self.resize(720, 560)
        self.items = [dict(it) for it in items]
        self._cur = -1

        root = QVBoxLayout(self)
        body = QHBoxLayout()
        root.addLayout(body, 1)

        left = QVBoxLayout()
        self.lst = QListWidget()
        self.lst.currentRowChanged.connect(self._on_row)
        left.addWidget(self.lst, 1)
        lrow = QHBoxLayout()
        b_add = QPushButton("추가")
        b_add.clicked.connect(self._add)
        b_del = QPushButton("삭제")
        b_del.clicked.connect(self._del)
        lrow.addWidget(b_add)
        lrow.addWidget(b_del)
        left.addLayout(lrow)
        holder = QWidget()
        holder.setLayout(left)
        holder.setFixedWidth(200)
        body.addWidget(holder)

        right = QVBoxLayout()
        right.addWidget(QLabel("채널 이름"))
        self.ed_name = QLineEdit()
        self.ed_name.textEdited.connect(self._name_edited)
        right.addWidget(self.ed_name)
        right.addWidget(QLabel("상담후 문구"))
        self.ed_after = QTextEdit()
        right.addWidget(self.ed_after, 1)
        right.addWidget(QLabel("부재중 문구"))
        self.ed_miss = QTextEdit()
        right.addWidget(self.ed_miss, 1)
        body.addLayout(right, 1)

        hint = QLabel("문구는 이 PC 에 저장되고, 로그인한 계정으로 다른 PC 에도 동기화됩니다.")
        hint.setStyleSheet(f"color:{theme.c('subtext')};")
        root.addWidget(hint)

        brow = QHBoxLayout()
        b_reset = QPushButton("기본 문구로 되돌리기")
        b_reset.clicked.connect(self._reset)
        brow.addWidget(b_reset)
        brow.addStretch()
        ok = QPushButton("저장")
        ok.setDefault(True)
        ok.clicked.connect(self._ok)
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.reject)
        brow.addWidget(ok)
        brow.addWidget(cancel)
        root.addLayout(brow)

        self._fill()
        if self.items:
            self.lst.setCurrentRow(0)

    # ---- 목록 ----
    def _fill(self) -> None:
        self.lst.blockSignals(True)
        self.lst.clear()
        for it in self.items:
            self.lst.addItem(it.get("name") or "(이름 없음)")
        self.lst.blockSignals(False)

    def _stash(self) -> None:
        """지금 보고 있던 채널의 편집 내용을 목록에 반영."""
        if 0 <= self._cur < len(self.items):
            self.items[self._cur] = {
                "name": self.ed_name.text().strip(),
                "after": self.ed_after.toPlainText(),
                "miss": self.ed_miss.toPlainText(),
            }

    def _on_row(self, row: int) -> None:
        self._stash()
        self._cur = row
        if 0 <= row < len(self.items):
            it = self.items[row]
            self.ed_name.setText(it.get("name", ""))
            self.ed_after.setPlainText(it.get("after", ""))
            self.ed_miss.setPlainText(it.get("miss", ""))
        else:
            self.ed_name.clear()
            self.ed_after.clear()
            self.ed_miss.clear()

    def _name_edited(self, txt: str) -> None:
        if 0 <= self._cur < self.lst.count():
            self.lst.item(self._cur).setText(txt.strip() or "(이름 없음)")

    def _add(self) -> None:
        self._stash()
        self.items.append({"name": "새 채널", "after": "", "miss": ""})
        self._fill()
        self.lst.setCurrentRow(len(self.items) - 1)

    def _del(self) -> None:
        row = self.lst.currentRow()
        if not (0 <= row < len(self.items)):
            return
        if QMessageBox.question(self, config.APP_NAME,
                                f"'{self.items[row].get('name')}' 채널을 지울까요?"
                                ) != QMessageBox.Yes:
            return
        self.items.pop(row)
        self._cur = -1
        self._fill()
        self.lst.setCurrentRow(min(row, len(self.items) - 1))

    def _reset(self) -> None:
        if QMessageBox.question(self, config.APP_NAME,
                                "고친 문구를 버리고 기본 문구로 되돌릴까요?"
                                ) != QMessageBox.Yes:
            return
        self.items = greetings.defaults()
        self._cur = -1
        self._fill()
        self.lst.setCurrentRow(0)

    def _ok(self) -> None:
        self._stash()
        if not [it for it in self.items if (it.get("name") or "").strip()]:
            QMessageBox.warning(self, config.APP_NAME, "채널이 하나도 없습니다.")
            return
        self.accept()

    @classmethod
    def run(cls, items: list, parent=None):
        d = cls(items, parent)
        if d.exec() == QDialog.Accepted:
            d._stash()
            return [it for it in d.items if (it.get("name") or "").strip()]
        return None


class GreetingTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: list = []
        self.cards: list = []
        # 문구를 고치면 알려 준다(메인 창이 Drive 동기화를 예약한다)
        self.on_changed = None

        v = QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)

        top = QHBoxLayout()
        self.lbl_title = QLabel("💬 멘트 복사")
        top.addWidget(self.lbl_title)
        self.lbl_hint = QLabel("버튼을 누르면 문구가 클립보드에 바로 복사됩니다.")
        top.addWidget(self.lbl_hint)
        top.addStretch()
        self.btn_edit = QPushButton("문구 편집")
        self.btn_edit.clicked.connect(self._edit)
        top.addWidget(self.btn_edit)
        v.addLayout(top)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        inner.setObjectName("dlgbody")
        # 격자를 세로 상자 안에 넣고 남는 공간은 아래 여백이 가져간다.
        # (격자에 setRowStretch 로 여백을 주면, 채널이 늘어나 그 줄에 카드가
        #  들어왔을 때 그 줄만 혼자 커져 카드 크기가 들쭉날쭉해진다)
        wrap = QVBoxLayout(inner)
        wrap.setContentsMargins(2, 2, 2, 2)
        wrap.setSpacing(0)
        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(10)
        wrap.addLayout(self.grid)
        wrap.addStretch(1)
        self.scroll.setWidget(inner)
        v.addWidget(self.scroll, 1)

        self.lbl_status = QLabel("파란색 = 상담후   ·   청록색 = 부재중")
        v.addWidget(self.lbl_status)

        self.reload()
        self.apply_theme()

    # ---- 데이터 ----
    def reload(self) -> None:
        """저장된 문구를 다시 읽어 카드를 그린다(계정이 바뀌면 다시 부른다)."""
        self.items = greetings.load()
        self._rebuild()

    def _rebuild(self) -> None:
        for c in self.cards:
            self.grid.removeWidget(c)
            c.setParent(None)
            c.deleteLater()
        self.cards = []
        for i, ch in enumerate(self.items):
            card = _ChannelCard(self._copy)
            card.set_channel(ch)
            self.grid.addWidget(card, i // COLS, i % COLS)
            self.cards.append(card)
        for col in range(COLS):
            self.grid.setColumnStretch(col, 1)
        self.apply_theme()

    def _edit(self) -> None:
        got = GreetingEditDialog.run(self.items, self)
        if got is None:
            return
        self.items = got
        try:
            greetings.save(self.items)
        except Exception as e:
            QMessageBox.warning(self, config.APP_NAME, "문구 저장 실패:\n" + str(e))
        self._rebuild()
        self.lbl_status.setText("문구를 저장했습니다.")
        if callable(self.on_changed):
            try:
                self.on_changed()
            except Exception:
                pass

    # ---- 복사 ----
    def _copy(self, card: "_ChannelCard", btn: "_CopyButton", state: str) -> None:
        text = btn.message
        if not text.strip():
            return
        try:
            QGuiApplication.clipboard().setText(text)
        except Exception as e:
            self.lbl_status.setText("복사 실패: " + str(e))
            return
        btn.flash()
        self.lbl_status.setText(f"{card.name}({state}) 복사됨 ✓")

    # ---- 테마 ----
    def apply_theme(self) -> None:
        self.lbl_title.setStyleSheet(
            f"color:{theme.c('text')};font-size:17px;font-weight:bold;")
        self.lbl_hint.setStyleSheet(f"color:{theme.c('subtext')};")
        self.lbl_status.setStyleSheet(f"color:{theme.c('subtext')};")
        for c in self.cards:
            c.apply_theme()
