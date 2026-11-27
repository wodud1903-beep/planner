"""인삿말 탭 — 채널별 인삿말을 한 번 눌러 클립보드에 복사한다.

쓰시던 HTML 도구를 그대로 옮긴 화면이다. 채널마다 [상담후] / [부재중] / [명함복사]
세 버튼이 있고, 누르면 그 문구(명함은 그림)가 복사되며 버튼이 잠깐 초록으로 바뀐다.
문구는 [문구 편집] 에서, 명함 사진은 카드마다 [명함] 에서 올린다(v1.36 — bizcard, 채널마다 따로 v1.36.1).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy, QTextEdit, QVBoxLayout,
    QWidget,
)

from . import config, greetings, theme
from .ment_templates import TemplateSection

# 파랑 = 상담후, 청록 = 부재중, 초록 = 복사됨.
# 색을 여기 박아 두면 흰 글자가 안 읽힌다 — 예전 값은 부재중 3.74:1,
# 복사됨 3.30:1 로 아홉 테마 **전부에서** 기준(4.5:1) 미달이었다.
# theme.fill() 은 그 조건을 만족하도록 고른 값이다.
TONE_AFTER = "blue"
TONE_MISS = "teal"
TONE_OK = "green"
TONE_CARD = "amber"       # 명함복사(v1.36)
CARD_OFF_TIP = "이 채널의 명함 사진을 먼저 올려 주세요 — 카드 오른쪽 위 [명함 올리기]"

COLS = 2                  # 한 줄에 카드 몇 개
_FLASH_MS = 1200


def _btn_css(tone: str) -> str:
    return (f"QPushButton{{background:{theme.fill(tone)};color:#FFFFFF;border:none;"
            f"border-radius:10px;padding:10px 8px;font-size:14px;font-weight:bold;}}"
            f"QPushButton:hover{{background:{theme.fill_hover(tone)};}}"
            f"QPushButton:disabled{{background:{theme.c('btn_bg')};"
            f"color:{theme.c('subtext')};}}")


class _CopyButton(QPushButton):
    """누르면 문구를 복사하고 잠깐 '복사됨' 으로 바뀌는 버튼."""

    def __init__(self, label: str, tone: str, parent=None):
        super().__init__(label, parent)
        self._label = label
        self._tone = tone
        self._text = ""
        self.setMinimumHeight(46)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(_btn_css(tone))
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._restore)

    def apply_theme(self) -> None:
        """테마를 바꾸면 단추 색도 따라간다."""
        self.setStyleSheet(_btn_css(self._tone))

    def set_message(self, text: str) -> None:
        self._text = text or ""
        self.setToolTip(self._text or "(문구가 비어 있습니다)")
        self.setEnabled(bool(self._text.strip()))

    def flash(self) -> None:
        self.setText("복사됨 ✓")
        self.setStyleSheet(_btn_css(TONE_OK))
        self._timer.start(_FLASH_MS)

    def _restore(self) -> None:
        self.setText(self._label)
        self.setStyleSheet(_btn_css(self._tone))

    @property
    def message(self) -> str:
        return self._text


class _ChannelCard(QFrame):
    def __init__(self, on_copy, on_card=None, on_edit_card=None, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        # 가로만 늘어나고 세로는 내용 높이 그대로 — 카드마다 크기가 달라지지 않게
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 12)
        v.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(6)
        self.lbl = QLabel("")
        head.addWidget(self.lbl, 1)
        # 이 채널의 명함 사진(v1.36.1 — 채널마다 다른 명함)
        self.btn_cardset = QPushButton("명함 올리기")
        self.btn_cardset.setCursor(Qt.PointingHandCursor)
        self.btn_cardset.setToolTip("이 채널의 [명함복사] 로 복사할 명함 사진을 올리거나 바꿉니다")
        self.btn_cardset.clicked.connect(lambda _c=False: on_edit_card(self) if on_edit_card else None)
        head.addWidget(self.btn_cardset)
        v.addLayout(head)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_after = _CopyButton("상담후", TONE_AFTER)
        self.btn_miss = _CopyButton("부재중", TONE_MISS)
        for b, state in ((self.btn_after, "상담후"), (self.btn_miss, "부재중")):
            b.clicked.connect(lambda _c=False, bb=b, st=state: on_copy(self, bb, st))
            row.addWidget(b, 1)
        # 명함복사(v1.36) — 올려 둔 명함 사진을 클립보드에. 명함이 없으면 꺼 둔다(set_card)
        self.btn_card = _CopyButton("명함복사", TONE_CARD)
        self.btn_card.clicked.connect(lambda _c=False: on_card(self, self.btn_card) if on_card else None)
        row.addWidget(self.btn_card, 1)
        self.set_card(False)
        v.addLayout(row)

        self.name = ""

    def set_card(self, on: bool) -> None:
        self.btn_card.setEnabled(bool(on))
        self.btn_card.setToolTip(f"{self.name} 명함 사진을 클립보드에 — 카톡 대화창에서 Ctrl+V" if on else CARD_OFF_TIP)
        self.btn_cardset.setText("명함 ✓" if on else "명함 올리기")

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
        self.btn_cardset.setStyleSheet(
            f"QPushButton{{background:{theme.c('window_bg')};color:{theme.strong('orange')};"
            f"border:1px solid {theme.c('border')};border-radius:8px;padding:3px 10px;font-size:12px;font-weight:bold;}}"
            f"QPushButton:hover{{background:{theme.c('btn_hover')};}}")
        # 단추 색도 함께 — 카드만 바꾸면 안 눌린 단추가 예전 색으로 남는다
        self.btn_after.apply_theme()
        self.btn_miss.apply_theme()
        self.btn_card.apply_theme()


class GreetingEditDialog(QDialog):
    """문구 편집 — 채널 목록 + 두 문구."""

    def __init__(self, items: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("멘트 문구 편집")
        self.resize(720, 560)
        # _orig = 열 때의 이름 — 이름을 바꾸면 그 채널의 명함도 새 이름으로 옮긴다(v1.36.1)
        self.items = [dict(it, _orig=it.get("name", "")) for it in items]
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
                "_orig": self.items[self._cur].get("_orig", ""),
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


class BizCardDialog(QDialog):
    """명함 사진 — 보기 · [사진 고르기…] · [붙여넣기] · [빼기]. 올리면 내 구글 계정(앱 전용 공간)에도 둔다."""

    def __init__(self, card, auth_getter, parent=None, name: str = ""):
        super().__init__(parent)
        self._name = name
        self.setWindowTitle(f"명함 사진 — {name}" if name else "명함 사진")
        self.resize(520, 460)
        self._card = card
        self._auth = auth_getter
        v = QVBoxLayout(self)
        hint = QLabel(f"'{name}' 카드의 [명함복사] 를 누르면 이 사진이 클립보드에 들어갑니다(카톡 대화창에서 Ctrl+V).\n"
                      "채널마다 다른 명함을 올릴 수 있습니다. 내 구글 계정에 저장되어 같은 계정의 다른 PC 에도 따라갑니다.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{theme.c('subtext')};")
        v.addWidget(hint)
        self.lbl_img = QLabel()
        self.lbl_img.setAlignment(Qt.AlignCenter)
        self.lbl_img.setMinimumHeight(280)
        self.lbl_img.setStyleSheet(f"background:{theme.c('panel_bg')};border:1px dashed {theme.c('border')};"
                                   f"border-radius:10px;color:{theme.c('subtext')};")
        v.addWidget(self.lbl_img, 1)
        row = QHBoxLayout()
        self.btn_pick = QPushButton("사진 고르기…")
        self.btn_pick.clicked.connect(self._pick)
        self.btn_paste = QPushButton("붙여넣기(Ctrl+V)")
        self.btn_paste.clicked.connect(self._paste)
        self.btn_del = QPushButton("빼기")
        self.btn_del.clicked.connect(self._remove)
        for b in (self.btn_pick, self.btn_paste, self.btn_del):
            row.addWidget(b)
        row.addStretch(1)
        close = QPushButton("닫기")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        v.addLayout(row)
        QShortcut(QKeySequence.Paste, self, activated=self._paste)
        self._paint()

    def _paint(self) -> None:
        img = self._card.image(self._name)
        if img is None:
            self.lbl_img.setPixmap(QPixmap())
            self.lbl_img.setText("아직 명함 사진이 없습니다.\n[사진 고르기…] 로 고르거나, 캡처한 그림을 Ctrl+V")
        else:
            pm = QPixmap.fromImage(img).scaled(460, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.lbl_img.setPixmap(pm)
        self.btn_del.setEnabled(img is not None)
        self.btn_pick.setText("다른 사진으로…" if img is not None else "사진 고르기…")

    def _ready(self) -> bool:
        auth = self._auth() if callable(self._auth) else None
        if auth is None or not auth.is_connected():
            QMessageBox.information(self, config.APP_NAME,
                                    "명함 사진은 구글 로그인 뒤에 올릴 수 있습니다.\n[설정] 에서 Google 로그인을 먼저 해 주세요.")
            return False
        return True

    def _put(self, img: QImage) -> None:
        if not self._ready():
            return
        err = self._card.set_image(self._name, img, self._auth())
        if err:
            QMessageBox.warning(self, config.APP_NAME, err)
        self._paint()

    def _pick(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "명함 사진 고르기", "",
                                              "그림 (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if path:
            self._put(QImage(path))

    def _paste(self) -> None:
        md = QGuiApplication.clipboard().mimeData()
        img = QImage()
        if md is not None and md.hasImage():
            img = QImage(md.imageData())
        elif md is not None and md.hasUrls():
            for u in md.urls():
                if u.isLocalFile():
                    img = QImage(u.toLocalFile())
                    if not img.isNull():
                        break
        if img.isNull():
            QMessageBox.information(self, config.APP_NAME, "클립보드에 그림이 없습니다.")
            return
        self._put(img)

    def _remove(self) -> None:
        if QMessageBox.question(self, config.APP_NAME,
                                f"'{self._name}' 명함 사진을 뺄까요? (다른 PC 에서도 빠집니다)") != QMessageBox.Yes:
            return
        auth = self._auth() if callable(self._auth) else None
        self._card.remove(self._name, auth)
        self._paint()


class GreetingTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: list = []
        self.cards: list = []
        self.bizcard = None              # 명함 사진(main_window 가 set_bizcard 로 넣는다)
        self.auth_getter = None          # 명함을 올릴 때 쓸 구글 로그인
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
        # 고객 안내 문구(v1.35) — 출고 안내 · 출고 1개월 · 재계약 멘트도 여기서 보고·고치고·복사
        self.templates = TemplateSection()
        wrap.addWidget(self.templates)
        wrap.addStretch(1)
        self.scroll.setWidget(inner)
        v.addWidget(self.scroll, 1)

        self.lbl_status = QLabel("파란색 = 상담후   ·   청록색 = 부재중   ·   주황색 = 명함")
        v.addWidget(self.lbl_status)

        self.reload()
        self.apply_theme()

    def set_bizcard(self, card, auth_getter=None) -> None:
        """명함 사진(bizcard.BizCard) — 생기거나 빠지면 [명함복사] 를 켜고 끈다."""
        self.bizcard = card
        self.auth_getter = auth_getter
        card.changed.connect(self._paint_card)
        self._paint_card()

    def _paint_card(self, *_a) -> None:
        for c in self.cards:
            c.set_card(bool(self.bizcard and self.bizcard.has(c.name)))

    def _edit_bizcard(self, card: "_ChannelCard") -> None:
        if self.bizcard is None:
            return
        BizCardDialog(self.bizcard, self.auth_getter, self, name=card.name).exec()

    def set_template_specs(self, specs: list) -> None:
        """아래 '고객 안내 문구' 카드들(main_window 가 무엇을 할지 넣어 준다)."""
        self.templates.set_specs(specs)

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
            card = _ChannelCard(self._copy, self._copy_card, self._edit_bizcard)
            card.set_channel(ch)
            card.set_card(bool(self.bizcard and self.bizcard.has(card.name)))
            self.grid.addWidget(card, i // COLS, i % COLS)
            self.cards.append(card)
        for col in range(COLS):
            self.grid.setColumnStretch(col, 1)
        self.apply_theme()

    def _edit(self) -> None:
        got = GreetingEditDialog.run(self.items, self)
        if got is None:
            return
        if self.bizcard is not None:
            auth = self.auth_getter() if callable(self.auth_getter) else None
            for it in got:
                old, new = (it.get("_orig") or "").strip(), (it.get("name") or "").strip()
                if old and new and old != new:
                    self.bizcard.rename(old, new, auth)
        self.items = [{k: v for k, v in it.items() if k != "_orig"} for it in got]
        try:
            greetings.save(self.items)
        except Exception as e:
            QMessageBox.warning(self, config.APP_NAME, "문구 저장 실패:\n" + str(e))
        self._rebuild()
        self._paint_card()
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

    def _copy_card(self, card: "_ChannelCard", btn: "_CopyButton") -> None:
        if self.bizcard is None or not self.bizcard.copy(card.name):
            self.lbl_status.setText(CARD_OFF_TIP)
            return
        btn.flash()
        self.lbl_status.setText(f"{card.name} — 명함 사진 복사됨 ✓ (카톡 대화창에서 Ctrl+V)")

    # ---- 테마 ----
    def apply_theme(self) -> None:
        self.lbl_title.setStyleSheet(
            f"color:{theme.c('text')};font-size:17px;font-weight:bold;")
        self.lbl_hint.setStyleSheet(f"color:{theme.c('subtext')};")
        self.lbl_status.setStyleSheet(f"color:{theme.c('subtext')};")
        if hasattr(self, "templates"):
            self.templates.apply_theme()
        for c in self.cards:
            c.apply_theme()
