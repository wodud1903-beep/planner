"""자료검색 탭 — 전자약정·심사서류 같은 업무자료를 쳐서 바로 띄운다.

`신한 전자약정` 처럼 낱말로 쳐도 되고, `ㅅㅎ ㅈㅈㅇㅈ` 처럼 초성만 쳐도 된다.
왼쪽에서 자료를 고르면 오른쪽에 본문과 체크리스트가 뜨고, 버튼 한 번으로
클립보드에 복사된다.

회사 공통 자료(관리자만 편집)와 개인 메모를 함께 검색한다. 출처는 배지로 구분한다.
"""

from __future__ import annotations

import re
from html import escape as _esc

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QSplitter, QTextBrowser,
    QTextEdit, QVBoxLayout, QWidget,
)

from . import config, kb, searchcombo, theme

ALL_CATEGORY = "전체 분류"
HEAD_MARK = "■"          # 본문에서 '한 덩어리' 의 머리글을 나타내는 표시

# 덩어리 사이를 가르는 점선.
# Qt 의 서식 있는 글은 <hr> 의 dashed 를 무시하고 실선으로 그려 버린다(확인함).
# 그래서 글자로 점선을 만든다 — 어느 글꼴에서나 똑같이 보인다.
_DOTS = "- " * 26

# 주소 끝에 붙기 쉬운 문장부호는 뺀다 — 마침표·쉼표까지 링크에 들어가면 안 열린다
_URL_RE = re.compile(r"https?://[^\s<>\"']+")


def _badge(text: str, color: str, bg: str) -> str:
    return (f"<span style='background-color:{bg};color:{color};'>"
            f"&nbsp;{text}&nbsp;</span>")


def _same(a: dict, b: dict) -> bool:
    """두 자료가 사실상 같은 내용인가 (출처 표시 등은 빼고 본다)."""
    for k in ("category", "finance", "title", "tags"):
        if (a.get(k) or "").strip() != (b.get(k) or "").strip():
            return False
    if kb.norm_body(a.get("body", "")).strip() != kb.norm_body(b.get("body", "")).strip():
        return False
    return [x.strip() for x in (a.get("checklist") or [])] == \
           [x.strip() for x in (b.get("checklist") or [])]


def _linkify(line: str) -> str:
    """한 줄을 HTML 로. 주소만 링크로 만들고 나머지는 그대로 이스케이프한다.

    통째로 이스케이프한 뒤 링크를 만들면 주소 안의 `&` 가 `&amp;` 로 바뀌어
    href 가 깨진다. 그래서 주소와 그 밖을 갈라서 따로 처리한다.
    """
    out, pos = [], 0
    for m in _URL_RE.finditer(line):
        out.append(_esc(line[pos:m.start()]))
        url = m.group(0).rstrip(".,);]")      # 문장 끝 부호는 링크에서 뺀다
        tail = m.group(0)[len(url):]
        href = _esc(url, quote=True)
        out.append(f'<a href="{href}">{_esc(url)}</a>')
        if tail:
            out.append(_esc(tail))
        pos = m.end()
    out.append(_esc(line[pos:]))
    return "".join(out)


def body_to_html(text: str) -> str:
    """본문 평문을 화면용 HTML 로.

    저장은 평문 그대로 둔다(시트에 들어가고 복사도 깨끗하다). 보기 좋게 만드는
    일은 그릴 때만 한다 — 그래야 사용자가 손으로 적은 자료에도 똑같이 걸린다.

      · `■ 머리글` 은 굵은 강조색으로, 그 **앞에 점선**을 그어 덩어리를 나눈다.
      · 주소는 눌러서 바로 열리는 링크로 바꾼다.
      · 머리글이 없는 글(고객에게 보내는 안내문)에는 선을 긋지 않는다.
    """
    txt, sub = theme.c("text"), theme.c("subtext")
    head = theme.strong("blue")
    out = [f"<div style='font-family:Malgun Gothic;color:{txt};font-size:13px;'>"]
    first_head = True
    for line in (text or "").split("\n"):
        if line.lstrip().startswith(HEAD_MARK):
            if not first_head:
                out.append(
                    f"<p style='margin:9px 0 4px 0;color:{sub};'>{_DOTS}</p>")
            first_head = False
            out.append(
                f"<p style='margin:6px 0 3px 0;font-size:14px;font-weight:bold;"
                f"color:{head};'>{_linkify(line.strip())}</p>")
        elif line.strip():
            out.append(f"<p style='margin:1px 0 1px 4px;'>{_linkify(line)}</p>")
        else:
            out.append("<p style='margin:4px 0;'>&nbsp;</p>")
    out.append("</div>")
    return "".join(out)


class _ResultList(QListWidget):
    """검색 결과 목록. 항목에 자료 dict 를 달아 둔다."""

    def fill(self, items: list) -> None:
        # 제목만 보여 준다. 캐피탈 자료는 제목과 금융사가 같아서 꼬리표를 붙이면
        # 'SK렌터카   [SK렌터카 · 캐피탈]' 처럼 같은 말이 세 번 나온다.
        self.clear()
        for it in items:
            text = it.get("title", "")
            if it.get("source") == kb.SRC_MINE:
                text += "   (내 메모)"
            li = QListWidgetItem(text)
            li.setData(Qt.UserRole, it)
            self.addItem(li)

    def current_item_data(self):
        li = self.currentItem()
        return li.data(Qt.UserRole) if li else None


class KbView(QWidget):
    """검색창 + 결과 + 내용. 탭에서도, 빠른검색 창에서도 쓴다."""

    picked = Signal(dict)          # 자료를 골랐을 때(빠른검색이 쓴다)

    def __init__(self, parent=None, compact: bool = False):
        super().__init__(parent)
        self.items: list = []
        self._compact = compact

        v = QVBoxLayout(self)
        m = 0 if compact else 10
        v.setContentsMargins(m, m, m, m)
        v.setSpacing(8)

        top = QHBoxLayout()
        self.ed_find = QLineEdit()
        self.ed_find.setPlaceholderText(
            "찾을 내용을 치세요  —  예: 신한 전자약정 · 개인 심사서류")
        self.ed_find.setClearButtonEnabled(True)
        self.ed_find.textChanged.connect(self._refilter)
        top.addWidget(self.ed_find, 1)
        self.cmb_cat = QComboBox()
        searchcombo.install(self.cmb_cat)
        self.cmb_cat.currentIndexChanged.connect(self._refilter)
        # 검색형 콤보는 안에 입력칸이 들어가 있어서 Qt 가 재는 기본 폭이 글씨보다
        # 좁다 → '전체 분류' 가 잘렸다. 항목이 바뀔 때마다 직접 재서 넓혀 준다.
        top.addWidget(self.cmb_cat, 0)
        v.addLayout(top)

        self.lst = _ResultList()
        self.lst.currentRowChanged.connect(self._show)
        self.lst.itemActivated.connect(
            lambda _i: self.picked.emit(self.lst.current_item_data() or {}))

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(6)
        self.lbl_title = QLabel("")
        self.lbl_title.setWordWrap(True)
        rv.addWidget(self.lbl_title)
        # QTextBrowser 라야 주소를 눌러 브라우저로 넘길 수 있다.
        # QTextEdit 를 물려받았으므로 toPlainText()(본문 복사)는 그대로다.
        self.txt_body = QTextBrowser()
        self.txt_body.setReadOnly(True)
        self.txt_body.setOpenExternalLinks(True)
        rv.addWidget(self.txt_body, 3)
        self.lbl_check_cap = QLabel("체크리스트")
        rv.addWidget(self.lbl_check_cap)
        self.lst_check = QListWidget()
        rv.addWidget(self.lst_check, 2)
        brow = QHBoxLayout()
        self.btn_copy_body = QPushButton("본문 복사")
        self.btn_copy_body.clicked.connect(self._copy_body)
        self.btn_copy_check = QPushButton("체크리스트 복사")
        self.btn_copy_check.clicked.connect(self._copy_check)
        brow.addWidget(self.btn_copy_body)
        brow.addWidget(self.btn_copy_check)
        brow.addStretch()
        rv.addLayout(brow)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self.lst)
        split.addWidget(right)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)
        v.addWidget(split, 1)

        self.lbl_status = QLabel("")
        v.addWidget(self.lbl_status)

        self.reload()
        self.apply_theme()

    # ------------------------------------------------------------ 데이터
    def reload(self) -> None:
        """자료를 다시 읽어 목록을 그린다(계정·공통자료가 바뀌면 다시 부른다)."""
        keep = (self.ed_find.text(), self.cmb_cat.currentText())
        self.items = kb.load_all()
        cats = kb.categories(self.items)
        self.cmb_cat.blockSignals(True)
        self.cmb_cat.clear()
        self.cmb_cat.addItem(ALL_CATEGORY, "")
        for c in cats:
            self.cmb_cat.addItem(c, c)
        i = self.cmb_cat.findText(keep[1])
        self.cmb_cat.setCurrentIndex(i if i >= 0 else 0)
        self.cmb_cat.blockSignals(False)
        self._fit_cat_width()
        self._refilter()

    def _fit_cat_width(self) -> None:
        """분류 콤보를 가장 긴 항목에 맞춘다(글씨가 잘리지 않게).

        입력칸·화살표·테두리가 먹는 여백(48px)을 더하고, 너무 커지지 않게
        상한을 둔다. 검색칸은 남는 폭을 가져가므로 그만큼 줄어든다.
        """
        fm = self.cmb_cat.fontMetrics()
        wide = max([fm.horizontalAdvance(self.cmb_cat.itemText(i))
                    for i in range(self.cmb_cat.count())] or [0])
        self.cmb_cat.setFixedWidth(max(150, min(280, wide + 48)))

    def _refilter(self) -> None:
        cat = self.cmb_cat.currentData() or ""
        found = kb.search(self.items, self.ed_find.text(), cat)
        self.lst.fill(found)
        if found:
            self.lst.setCurrentRow(0)
        else:
            self._show(-1)
        n, total = len(found), len(self.items)
        self.lbl_status.setText(
            f"{n}건 찾음 (전체 {total}건)" if self.ed_find.text().strip() or cat
            else f"전체 {total}건")

    def _show(self, _row: int) -> None:
        it = self.lst.current_item_data()
        if not it:
            self.lbl_title.setText("")
            self.txt_body.clear()
            self.lst_check.clear()
            self.btn_copy_body.setEnabled(False)
            self.btn_copy_check.setEnabled(False)
            return
        # 금융사가 제목과 같으면(캐피탈 자료) 한 번만 보여 준다
        fin = it.get("finance", "")
        if fin.strip() == it.get("title", "").strip():
            fin = ""
        tail = " · ".join(x for x in (fin, it.get("category", "")) if x)
        src = kb.SRC_NAMES.get(it.get("source", ""), "")
        col = (theme.strong("violet") if it.get("source") == kb.SRC_MINE
               else theme.strong("blue"))
        bg = (theme.strong_bg("violet") if it.get("source") == kb.SRC_MINE
              else theme.strong_bg("blue"))
        self.lbl_title.setText(
            f"<b style='font-size:15px;'>{it.get('title', '')}</b> &nbsp;"
            + (_badge(src, col, bg) if src else "")
            + (f"<br><span style='color:{theme.c('subtext')};'>{tail}</span>"
               if tail else ""))
        self.txt_body.setHtml(body_to_html(it.get("body", "")))
        checks = it.get("checklist") or []
        self.lst_check.clear()
        for c in checks:
            self.lst_check.addItem("□  " + c)
        self.lst_check.setVisible(bool(checks))
        self.lbl_check_cap.setVisible(bool(checks))
        self.btn_copy_body.setEnabled(bool(it.get("body", "").strip()))
        self.btn_copy_check.setEnabled(bool(checks))

    # ------------------------------------------------------------ 복사
    def _copy(self, text: str, what: str) -> None:
        if not text.strip():
            return
        from PySide6.QtGui import QGuiApplication
        try:
            QGuiApplication.clipboard().setText(text)
            self.lbl_status.setText(f"{what} 복사됨 ✓")
        except Exception as e:
            self.lbl_status.setText("복사 실패: " + str(e))

    def _copy_body(self) -> None:
        it = self.lst.current_item_data() or {}
        self._copy(it.get("body", ""), "본문")

    def _copy_check(self) -> None:
        it = self.lst.current_item_data() or {}
        self._copy("\n".join(it.get("checklist") or []), "체크리스트")

    def focus_search(self) -> None:
        self.ed_find.setFocus()
        self.ed_find.selectAll()

    # ------------------------------------------------------------ 테마
    def apply_theme(self) -> None:
        self.lbl_status.setStyleSheet(f"color:{theme.c('subtext')};")
        self.lbl_check_cap.setStyleSheet(
            f"color:{theme.c('subtext')};font-weight:bold;")
        self._show(self.lst.currentRow())


class KbTab(QWidget):
    """자료검색 탭 — 검색 화면 + [자료 편집]."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.account = ""
        self.on_changed = None          # 개인 메모를 고쳤을 때(동기화 예약)
        self.on_push_shared = None      # 공통 자료를 고쳤을 때(시트 업로드)

        v = QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)

        top = QHBoxLayout()
        self.lbl_title = QLabel("🔎 자료검색")
        top.addWidget(self.lbl_title)
        self.lbl_hint = QLabel("전자약정·심사서류를 미리 넣어 두고 바로 찾아 쓰세요.")
        top.addWidget(self.lbl_hint)
        top.addStretch()
        self.btn_edit = QPushButton("자료 편집")
        self.btn_edit.clicked.connect(self._edit)
        top.addWidget(self.btn_edit)
        v.addLayout(top)

        self.view = KbView(compact=True)
        v.addWidget(self.view, 1)

        self.apply_theme()

    def set_account(self, email: str) -> None:
        self.account = email or ""

    def reload(self) -> None:
        self.view.reload()

    def focus_search(self) -> None:
        self.view.focus_search()

    def _edit(self) -> None:
        admin = config.is_rates_admin(self.account)
        got = KbEditDialog.run(self.account, self)
        if got is None:
            return
        shared, mine = got
        try:
            kb.save_mine(mine)
        except Exception as e:
            QMessageBox.warning(self, config.APP_NAME, "메모 저장 실패:\n" + str(e))
        if admin:
            kb.save_shared(shared)          # 먼저 이 PC 에 반영
            if callable(self.on_push_shared):
                self.on_push_shared(shared)  # 시트로 올리기(백그라운드)
        self.view.reload()
        if callable(self.on_changed):
            try:
                self.on_changed()
            except Exception:
                pass

    def apply_theme(self) -> None:
        self.lbl_title.setStyleSheet(
            f"color:{theme.c('text')};font-size:17px;font-weight:bold;")
        self.lbl_hint.setStyleSheet(f"color:{theme.c('subtext')};")
        self.view.apply_theme()


class QuickSearch(QDialog):
    """전역 단축키로 뜨는 빠른검색 창.

    다른 프로그램을 쓰던 중에도 뜨므로, 화면 한가운데 작게 띄우고
    Enter 로 본문을 복사한 뒤 곧바로 닫는다.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("업무자료 빠른검색")
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.resize(860, 520)

        v = QVBoxLayout(self)
        v.setContentsMargins(12, 12, 12, 12)
        self.view = KbView(compact=True)
        self.view.picked.connect(self._pick)
        v.addWidget(self.view, 1)
        self.lbl = QLabel("Enter = 본문 복사 후 닫기   ·   Esc = 닫기")
        self.lbl.setStyleSheet(f"color:{theme.c('subtext')};")
        v.addWidget(self.lbl)

    def _pick(self, item: dict) -> None:
        self.view._copy_body()
        self.accept()

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key_Return, Qt.Key_Enter):
            it = self.view.lst.current_item_data()
            if it:
                self._pick(it)
                return
        super().keyPressEvent(ev)

    def popup(self) -> None:
        self.view.reload()
        self.show()
        self.raise_()
        self.activateWindow()
        self.view.focus_search()


class KbEditDialog(QDialog):
    """자료 편집 — 공통(관리자만) / 내 메모."""

    def __init__(self, account: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("업무자료 편집")
        self.resize(860, 620)
        self.admin = config.is_rates_admin(account)
        self.shared = [dict(x) for x in kb.load_shared()]
        self.mine = [dict(x) for x in kb.load_mine()]
        self._cur = -1

        root = QVBoxLayout(self)

        srow = QHBoxLayout()
        srow.addWidget(QLabel("자료 묶음"))
        self.cmb_src = QComboBox()
        searchcombo.install(self.cmb_src)
        if self.admin:
            self.cmb_src.addItem("회사 공통 (모든 직원이 봅니다)", kb.SRC_SHARED)
        self.cmb_src.addItem("내 메모 (내 계정에서만)", kb.SRC_MINE)
        self.cmb_src.currentIndexChanged.connect(self._switch)
        srow.addWidget(self.cmb_src, 1)
        root.addLayout(srow)

        if not self.admin:
            lbl = QLabel("회사 공통 자료는 관리자 계정에서만 고칠 수 있습니다.\n"
                         "이 PC 는 관리자가 저장한 자료를 받아서 검색에 씁니다.")
            lbl.setStyleSheet(f"color:{theme.c('subtext')};")
            root.addWidget(lbl)

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
        holder.setFixedWidth(240)
        body.addWidget(holder)

        right = QVBoxLayout()
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("분류"))
        self.cmb_cat = QComboBox()
        self.cmb_cat.addItem("")
        for c in kb.CATEGORIES:
            self.cmb_cat.addItem(c)
        searchcombo.install(self.cmb_cat, allow_free=True)
        self.cmb_cat.currentTextChanged.connect(self._touch)
        r1.addWidget(self.cmb_cat, 1)
        r1.addWidget(QLabel("금융사"))
        self.ed_fin = QLineEdit()
        self.ed_fin.setPlaceholderText("비우면 모든 금융사 공통")
        r1.addWidget(self.ed_fin, 1)
        right.addLayout(r1)

        right.addWidget(QLabel("제목"))
        self.ed_title = QLineEdit()
        self.ed_title.setPlaceholderText("예: 신한 전자약정")
        self.ed_title.textEdited.connect(self._title_edited)
        right.addWidget(self.ed_title)

        right.addWidget(QLabel("검색어(태그)"))
        self.ed_tags = QLineEdit()
        self.ed_tags.setPlaceholderText("띄어쓰기로 여러 개 — 예: 전자서명 모바일 약정")
        right.addWidget(self.ed_tags)

        right.addWidget(QLabel("본문"))
        self.txt_body = QTextEdit()
        right.addWidget(self.txt_body, 3)

        right.addWidget(QLabel("체크리스트 (한 줄에 하나)"))
        self.txt_check = QTextEdit()
        self.txt_check.setPlaceholderText("사업자등록증\n부가세과세표준증명원\n통장 사본")
        right.addWidget(self.txt_check, 2)
        body.addLayout(right, 1)

        hint = QLabel(
            "분류를 '심사서류' 로 하고 체크리스트를 적으면, 고객관리의 [서류] 에서\n"
            "그 목록을 그대로 불러 체크할 수 있습니다.")
        hint.setStyleSheet(f"color:{theme.c('subtext')};")
        root.addWidget(hint)

        brow = QHBoxLayout()
        self.btn_seed = QPushButton("기본 자료 불러오기")
        self.btn_seed.setToolTip(
            "앱에 들어 있는 기본 자료 중 목록에 없는 것만 덧붙입니다.\n"
            "이미 있는 제목은 건드리지 않습니다.")
        self.btn_seed.clicked.connect(self._add_seed)
        brow.addWidget(self.btn_seed)
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
        self._sync_seed_btn()

    # ---- 묶음 ----
    def _cur_list(self) -> list:
        return (self.shared if self.cmb_src.currentData() == kb.SRC_SHARED
                else self.mine)

    def _switch(self, _i: int) -> None:
        self._stash()
        self._cur = -1
        self._fill()
        self._sync_seed_btn()

    def _sync_seed_btn(self) -> None:
        """기본 자료는 회사 공통 묶음에만 넣는다(전 직원이 같은 것을 봐야 한다)."""
        on = self.cmb_src.currentData() == kb.SRC_SHARED
        self.btn_seed.setEnabled(on)
        if not on:
            self.btn_seed.setToolTip("기본 자료는 '회사 공통' 묶음에만 넣을 수 있습니다.")

    def _fill(self) -> None:
        self.lst.blockSignals(True)
        self.lst.clear()
        for it in self._cur_list():
            self.lst.addItem(it.get("title") or "(제목 없음)")
        self.lst.blockSignals(False)
        if self._cur_list():
            self.lst.setCurrentRow(0)
        else:
            self._on_row(-1)

    # ---- 편집 ----
    def _stash(self) -> None:
        lst = self._cur_list()
        if 0 <= self._cur < len(lst):
            lst[self._cur] = {
                "category": self.cmb_cat.currentText().strip(),
                "finance": self.ed_fin.text().strip(),
                "title": self.ed_title.text().strip(),
                "tags": self.ed_tags.text().strip(),
                "body": kb.norm_body(self.txt_body.toPlainText()),
                "checklist": [c.strip() for c in
                              self.txt_check.toPlainText().splitlines() if c.strip()],
            }

    def _on_row(self, row: int) -> None:
        self._stash()
        self._cur = row
        lst = self._cur_list()
        on = 0 <= row < len(lst)
        it = lst[row] if on else {}
        self.cmb_cat.setCurrentText(it.get("category", ""))
        self.ed_fin.setText(it.get("finance", ""))
        self.ed_title.setText(it.get("title", ""))
        self.ed_tags.setText(it.get("tags", ""))
        # 편집창은 **평문 그대로** 보여 준다. 여기에 서식을 입히면
        # toPlainText() 로 거둘 때 점선·머리글 장식까지 본문에 섞여 저장된다.
        self.txt_body.setPlainText(it.get("body", ""))
        self.txt_check.setPlainText("\n".join(it.get("checklist") or []))
        for w in (self.cmb_cat, self.ed_fin, self.ed_title, self.ed_tags,
                  self.txt_body, self.txt_check):
            w.setEnabled(on)

    def _touch(self, *_a) -> None:
        pass          # 값은 _stash 에서 한꺼번에 거둔다

    def _title_edited(self, txt: str) -> None:
        if 0 <= self._cur < self.lst.count():
            self.lst.item(self._cur).setText(txt.strip() or "(제목 없음)")

    def _add(self) -> None:
        self._stash()
        self._cur_list().append(
            {"category": "", "finance": "", "title": "새 자료",
             "tags": "", "body": "", "checklist": []})
        self._cur = -1
        self._fill()
        self.lst.setCurrentRow(len(self._cur_list()) - 1)
        self.ed_title.setFocus()
        self.ed_title.selectAll()

    def _add_seed(self) -> None:
        """앱 기본 자료를 목록에 반영한다.

        없는 것은 덧붙이고, **제목은 같은데 내용이 다른 것은 덮어쓸지 물어본다.**
        예전엔 겹치는 제목을 무조건 건너뛰었는데, 그러면 앱에 새로 넣은 문구가
        이미 그 제목을 갖고 있는 PC 에는 영원히 도달하지 못했다(심사서류가
        옛 내용 그대로 남아 있던 이유).

        묻지 않고 덮어쓰지는 않는다 — 고쳐 쓰신 내용이 말없이 사라지면 안 된다.
        """
        lst = self._cur_list()
        self._stash()
        cur = {(it.get("title") or "").strip(): i for i, it in enumerate(lst)}
        missing, differ = [], []
        for x in kb.SAMPLE:
            t = (x.get("title") or "").strip()
            i = cur.get(t)
            if i is None:
                missing.append(dict(x))
            elif not _same(lst[i], x):
                differ.append((i, dict(x)))

        if not missing and not differ:
            QMessageBox.information(self, config.APP_NAME,
                                    "기본 자료가 이미 모두 최신입니다.")
            return

        overwrite = False
        if differ:
            ans = QMessageBox.question(
                self, config.APP_NAME,
                f"제목이 같은데 내용이 다른 자료가 {len(differ)}건 있습니다.\n"
                f"({', '.join(x[1]['title'] for x in differ[:5])}"
                + (" 외" if len(differ) > 5 else "") + ")\n\n"
                "기본 내용으로 덮어쓸까요?\n"
                "[아니오] 를 누르면 없는 자료만 덧붙입니다.",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if ans == QMessageBox.Cancel:
                return
            overwrite = ans == QMessageBox.Yes

        if overwrite:
            for i, x in differ:
                lst[i] = x
        lst.extend(missing)
        self._cur = -1
        self._fill()

        done = []
        if missing:
            done.append(f"{len(missing)}건 추가")
        if overwrite and differ:
            done.append(f"{len(differ)}건 덮어씀")
        QMessageBox.information(
            self, config.APP_NAME,
            (" · ".join(done) if done else "바뀐 것이 없습니다") + "\n"
            "[저장] 을 눌러야 실제로 반영됩니다.")

    def _del(self) -> None:
        lst = self._cur_list()
        row = self.lst.currentRow()
        if not (0 <= row < len(lst)):
            return
        if QMessageBox.question(
                self, config.APP_NAME,
                f"'{lst[row].get('title')}' 자료를 지울까요?") != QMessageBox.Yes:
            return
        lst.pop(row)
        self._cur = -1
        self._fill()

    def _ok(self) -> None:
        self._stash()
        self.accept()

    @classmethod
    def run(cls, account: str = "", parent=None):
        """반환: (공통 목록, 내 메모 목록) 또는 None(취소)."""
        d = cls(account, parent)
        if d.exec() != QDialog.Accepted:
            return None
        return ([x for x in d.shared if (x.get("title") or "").strip()],
                [x for x in d.mine if (x.get("title") or "").strip()])
