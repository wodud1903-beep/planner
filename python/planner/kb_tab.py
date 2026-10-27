"""자료검색 탭 — 전자약정·심사서류 같은 업무자료를 쳐서 바로 띄운다.

`신한 전자약정` 처럼 낱말로 쳐도 되고, `ㅅㅎ ㅈㅈㅇㅈ` 처럼 초성만 쳐도 된다.
왼쪽에서 자료를 고르면 오른쪽에 본문과 체크리스트가 뜨고, 버튼 한 번으로
클립보드에 복사된다.

회사 공통 자료(관리자만 편집)와 개인 메모를 함께 검색한다. 출처는 배지로 구분한다.
"""

from __future__ import annotations

import re
import threading
from html import escape as _esc

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QSplitter, QTextBrowser,
    QTextEdit, QVBoxLayout, QWidget,
)

from . import config, crashlog, kb, kb_files, searchcombo, theme
from .clipfiles import file_mime
from .kb_attach import AttachList, AttachViewer
from .livesearch import LiveLineEdit

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
    # 첨부는 비교하지 않는다 — 기본 자료에는 첨부가 없어서, 첨부를 붙인 자료가
    # 전부 '내용이 다르다' 로 잡혀 덮어쓸지 묻게 된다(덮어써도 첨부는 남긴다).
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
    SEARCH_DELAY_MS = 120
    _sig_fetched = Signal(str, str, str)   # (첨부 id, PC 경로, 오류) — 받기 끝

    def __init__(self, parent=None, compact: bool = False):
        super().__init__(parent)
        self.items: list = []
        self._compact = compact
        self.auth = None               # 첨부를 받을 때 쓰는 구글 로그인(set_auth)
        self._inflight: set = set()    # 받는 중인 첨부 id
        self._errs: dict = {}          # id → 받기 실패 이유
        self._want_copy: list = []     # 받기가 끝나면 복사할 첨부(Ctrl+C 를 먼저 누른 경우)
        self._want_open = None         # 받기가 끝나면 크게 볼 첨부
        self._sig_fetched.connect(self._on_fetched)

        v = QVBoxLayout(self)
        m = 0 if compact else 10
        v.setContentsMargins(m, m, m, m)
        v.setSpacing(8)

        top = QHBoxLayout()
        # 한글 마지막 글자(조합 중)까지 바로 찾는다 — livesearch.py 설명
        self.ed_find = LiveLineEdit()
        self.ed_find.setPlaceholderText(
            "찾을 내용을 치세요  —  예: 신한 전자약정 · 개인 심사서류")
        self.ed_find.setClearButtonEnabled(True)
        # 타자가 멎으면 한 번만 찾는다(120ms) — 폰 웹앱과 같은 방식. 한 글자마다
        # 목록·첨부를 다시 그리면 무거운 자료에서 타자가 밀렸다.
        self._find_timer = QTimer(self)
        self._find_timer.setSingleShot(True)
        self._find_timer.setInterval(self.SEARCH_DELAY_MS)
        self._find_timer.timeout.connect(self._refilter)
        self.ed_find.liveText.connect(lambda _t: self._find_timer.start())
        top.addWidget(self.ed_find, 1)
        self.cmb_cat = QComboBox()
        searchcombo.install(self.cmb_cat)
        self.cmb_cat.currentIndexChanged.connect(self._refilter)
        # 검색형 콤보는 안에 입력칸이 들어가 있어서 Qt 가 재는 기본 폭이 글씨보다
        # 좁다 → '전체 분류' 가 잘렸다. 항목이 바뀔 때마다 직접 재서 넓혀 준다.
        top.addWidget(self.cmb_cat, 0)
        v.addLayout(top)

        self.lst = _ResultList()
        # 왼쪽 자료 목록 글씨를 키운다 — 상담 중에 훑는 목록이라 잘 보여야 한다
        self.lst.setStyleSheet(
            "QListWidget { font-size: 12pt; }"
            "QListWidget::item { padding: 6px 4px; }")
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
        # 체크리스트는 이 화면에 보여 주지 않는다(지점장 요청). 자료에는 그대로 남아
        # 고객관리 [서류] 의 체크 목록 재료로 쓰인다 — 편집 창의 칸도 그대로다.
        # 첨부(그림·PDF) — 골라서 Ctrl+C 또는 끌어서 카톡으로, 두 번 누르면 크게
        self.lbl_att_cap = QLabel("첨부")
        rv.addWidget(self.lbl_att_cap)
        self.lst_att = AttachList(self)
        self.lst_att.setMinimumHeight(176)
        rv.addWidget(self.lst_att, 2)
        brow = QHBoxLayout()
        self.btn_copy_body = QPushButton("본문 복사")
        self.btn_copy_body.clicked.connect(self._copy_body)
        self.btn_copy_att = QPushButton("첨부 복사")
        self.btn_copy_att.setToolTip(
            "고른 첨부(안 고르면 전부)를 복사합니다. 카카오톡 대화창에서 Ctrl+V 로 붙여 넣으세요.\n"
            "첨부를 끌어서 카톡 창에 놓아도 됩니다.")
        self.btn_copy_att.clicked.connect(lambda: self.copy_attachments())
        brow.addWidget(self.btn_copy_body)
        brow.addWidget(self.btn_copy_att)
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

    def _refilter(self, *_a) -> None:
        cat = self.cmb_cat.currentData() or ""
        q = self.ed_find.live_text()
        found = kb.search(self.items, q, cat)
        # ⚠️ 목록을 다시 채우는 동안에는 '고른 줄이 바뀜' 신호를 막는다. 안 막으면
        #    비우는 순간 '아무것도 안 고름' 이 와서 오른쪽(첨부 줄)을 비웠다가 다시
        #    채운다 — 검색할 때마다 첨부를 통째로 다시 그리던 이유다. 다 채운 뒤 한 번만 보여 준다.
        self.lst.blockSignals(True)
        try:
            self.lst.fill(found)
            if found:
                self.lst.setCurrentRow(0)
        finally:
            self.lst.blockSignals(False)
        self._show(self.lst.currentRow() if found else -1)
        n, total = len(found), len(self.items)
        self.lbl_status.setText(
            f"{n}건 찾음 (전체 {total}건)" if q.strip() or cat
            else f"전체 {total}건")

    def _show(self, _row: int) -> None:
        it = self.lst.current_item_data()
        if not it:
            self.lbl_title.setText("")
            self.txt_body.clear()
            self.btn_copy_body.setEnabled(False)
            self._fill_attachments({})
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
        self.btn_copy_body.setEnabled(bool(it.get("body", "").strip()))
        self._fill_attachments(it)

    # ------------------------------------------------------------ 첨부
    def set_auth(self, auth) -> None:
        """첨부를 받을 때 쓸 구글 로그인(없어도 공개 첨부는 받는다)."""
        self.auth = auth

    @staticmethod
    def _att_key(it: dict) -> tuple:
        return (it.get("source", ""), it.get("title", ""),
                tuple((f.get("id"), f.get("name")) for f in (it.get("files") or [])))

    def _fill_attachments(self, it: dict) -> None:
        # ⚠️ 같은 자료면 줄을 다시 만들지 않는다. 검색어를 칠 때마다 첫 자료가 같아도
        #    첨부 줄을 갈아엎어서, 큰 그림이 붙은 자료에서 타자마다 멈칫했다.
        key = self._att_key(it)
        if key == getattr(self, "_att_shown", None) and self.lst_att.count() == len(key[2]):
            return
        self._att_shown = key
        files = [dict(f) for f in (it.get("files") or [])]
        for f in files:
            if f.get("id") in self._errs:
                f["_err"] = self._errs[f["id"]]
        self.lst_att.fill(files)
        on = bool(files)
        self.lbl_att_cap.setText(
            f"첨부 ({len(files)})  —  골라서 Ctrl+C 또는 끌어서 카톡으로 · 두 번 누르면 크게"
            if on else "첨부")
        self.lbl_att_cap.setVisible(on)
        self.lst_att.setVisible(on)
        self.btn_copy_att.setVisible(on)
        # 보자마자 받아 둔다 — 그림이 바로 보이고, Ctrl+C 를 기다리게 하지 않게
        for f in files:
            if not kb_files.cached(f) and f.get("id") not in self._errs:
                self._fetch_async(f)

    def _fetch_async(self, att: dict) -> None:
        fid = att.get("id", "")
        if not fid or fid in self._inflight:
            return
        self._inflight.add(fid)
        auth = self.auth

        def worker():
            try:
                p = kb_files.fetch(auth, att)
                self._sig_fetched.emit(fid, str(p), "")
            except Exception as e:
                self._sig_fetched.emit(fid, "", str(e).splitlines()[0][:120])
        threading.Thread(target=worker, daemon=True).start()

    def _on_fetched(self, fid: str, path: str, err: str) -> None:
        self._inflight.discard(fid)
        if err:
            self._errs[fid] = err
        self.lst_att.refresh(fid, err)
        if self._want_copy and not any(a.get("id") in self._inflight for a in self._want_copy):
            want, self._want_copy = self._want_copy, []
            # ⚠️ 하나라도 못 받았으면 여기서 멈춘다. 다시 copy_attachments 를 부르면
            #    또 받으러 가고, 또 실패하고… 끝없이 돈다.
            if any(not kb_files.cached(a) for a in want):
                self.lbl_status.setText("첨부를 받지 못해 복사하지 못했습니다"
                                        + (f": {err}" if err else "."))
            else:
                self.copy_attachments(want)
        if self._want_open is not None and self._want_open.get("id") == fid:
            att, self._want_open = self._want_open, None
            if not err:
                self.open_attachment(att)
            else:
                self.lbl_status.setText("첨부를 받지 못했습니다: " + err)

    def attach_paths(self, atts: list) -> list:
        """카톡으로 보낼 PC 경로. 아직 안 받은 것은 받기를 시작하고 뺀다."""
        out, missing = [], 0
        for a in atts or []:
            p = kb_files.cached(a)
            if p:
                out.append(str(p))
            else:
                missing += 1
                self._errs.pop(a.get("id"), None)     # 다시 해 본다
                self._fetch_async(a)
        if missing and not out:
            self.lbl_status.setText("첨부를 받는 중입니다 — 잠시 뒤 다시 해 주세요.")
        return out

    def copy_attachments(self, atts: list | None = None) -> None:
        """고른 첨부(없으면 전부)를 클립보드에 — 카톡 대화창에서 Ctrl+V."""
        if atts is None:
            atts = self.lst_att.selected_atts() or self.lst_att.atts()
        if not atts:
            return
        if any(not kb_files.cached(a) for a in atts):
            # 아직 받는 중 — 다 받으면 그때 복사한다(누른 것을 잊지 않는다)
            self._want_copy = list(atts)
            for a in atts:
                if not kb_files.cached(a):
                    self._errs.pop(a.get("id"), None)
                    self._fetch_async(a)
            if not any(a.get("id") in self._inflight for a in atts):
                self._want_copy = []
                self.lbl_status.setText("첨부를 받지 못해 복사하지 못했습니다.")
                return
            self.lbl_status.setText("첨부를 받는 중입니다 — 받는 대로 복사합니다…")
            return
        paths = [str(kb_files.cached(a)) for a in atts]
        from PySide6.QtGui import QGuiApplication
        QGuiApplication.clipboard().setMimeData(file_mime(paths))
        what = atts[0].get("name", "") if len(atts) == 1 else f"첨부 {len(atts)}개"
        self.lbl_status.setText(f"{what} 복사됨 ✓  카카오톡에서 Ctrl+V 로 붙여 넣으세요.")

    def open_attachment(self, att: dict) -> None:
        """두 번 누르기 — 크게 보기(돌리기·PDF 장 넘기기) + [카톡으로 보내기]."""
        p = kb_files.cached(att)
        if not p:
            self._want_open = att
            self._errs.pop(att.get("id"), None)
            self._fetch_async(att)
            self.lbl_status.setText("첨부를 받는 중입니다…")
            return
        try:
            data = p.read_bytes()
        except OSError as e:
            self.lbl_status.setText("첨부를 열지 못했습니다: " + str(e))
            return
        crashlog.note(f"크게 보기 {att.get('name', '')} ({kb_files.size_text(len(data))})")
        # 창은 닫히면 스스로 없어진다(WA_DeleteOnClose) — 원본을 든 채 남지 않는다
        dlg = AttachViewer(att, data, on_send=lambda a=att: self.copy_attachments([a]),
                           parent=self)
        del data
        dlg.exec()

    def save_attachment_as(self, att: dict) -> None:
        """오른쪽 단추 [다른 이름으로 저장] — 바탕화면 등에 파일로 꺼내 둔다."""
        p = kb_files.cached(att)
        if not p:
            self._errs.pop(att.get("id"), None)
            self._fetch_async(att)
            self.lbl_status.setText("첨부를 받는 중입니다 — 잠시 뒤 다시 해 주세요.")
            return
        import os
        import shutil
        from PySide6.QtWidgets import QFileDialog
        dest, _f = QFileDialog.getSaveFileName(
            self, "다른 이름으로 저장",
            os.path.join(os.path.expanduser("~"), "Desktop", att.get("name", p.name)))
        if not dest:
            return
        try:
            shutil.copyfile(p, dest)
            self.lbl_status.setText(f"저장했습니다: {dest}")
        except OSError as e:
            self.lbl_status.setText("저장하지 못했습니다: " + str(e))

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

    def focus_search(self) -> None:
        self.ed_find.setFocus()
        self.ed_find.selectAll()

    def search_for(self, query: str) -> None:
        """다른 화면에서 넘어올 때 — 그 말로 찾아 첫 건을 펼친다.

        분류 거르개는 '전체' 로 되돌린다. 남아 있으면 찾는 자료가 그 분류가
        아닐 때 '0건' 만 뜨고 왜 그런지 알 수 없다.
        """
        self.cmb_cat.setCurrentIndex(0)
        self.ed_find.setText(str(query or "").strip())
        self.flush_search()             # 넘어온 말은 기다리지 않고 바로 찾는다
        self.focus_search()

    def flush_search(self) -> None:
        """기다리는 검색이 있으면 지금 한다(Enter 를 바로 누른 경우 등)."""
        if self._find_timer.isActive():
            self._find_timer.stop()
            self._refilter()

    # ------------------------------------------------------------ 테마
    def apply_theme(self) -> None:
        self.lbl_status.setStyleSheet(f"color:{theme.c('subtext')};")
        self.lbl_att_cap.setStyleSheet(
            f"color:{theme.c('subtext')};font-weight:bold;")
        self._att_shown = None          # 테마가 바뀌면 PDF·받는 중 표시 색도 다시
        self._show(self.lst.currentRow())


def _file_ids(items: list) -> set:
    return {f.get("id") for it in (items or []) for f in (it.get("files") or [])
            if f.get("id")}


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

    def set_auth(self, auth) -> None:
        """첨부를 올리고 받을 때 쓰는 구글 로그인."""
        self.view.set_auth(auth)

    def reload(self) -> None:
        self.view.reload()

    def focus_search(self) -> None:
        self.view.focus_search()

    def search_for(self, query: str) -> None:
        self.view.search_for(query)

    def _edit(self) -> None:
        admin = config.is_rates_admin(self.account)
        auth = self.view.auth
        before = _file_ids(kb.load_mine()) | (_file_ids(kb.load_shared()) if admin else set())
        got = KbEditDialog.run(self.account, self, auth=auth)
        if got is None:
            return
        shared, mine = got
        # 자료에서 뺀 첨부는 드라이브 휴지통으로(30일 안엔 되살릴 수 있다) — 뒤에서
        gone = before - _file_ids(mine) - (_file_ids(shared) if admin else set())
        if gone and auth is not None and auth.is_connected():
            threading.Thread(target=kb_files.trash, args=(auth, sorted(gone)),
                             daemon=True).start()
        # 이름을 바꾼 첨부는 드라이브의 파일 이름도 맞춘다(드라이브에서 찾아볼 때) — 뒤에서
        ren = [r for r in (getattr(KbEditDialog, "last_renamed", []) or []) if r[0] not in gone]
        KbEditDialog.last_renamed = []
        if ren and auth is not None and auth.is_connected():
            def _rename(pairs=ren):
                for fid, name in pairs:
                    kb_files.rename_remote(auth, fid, name)
            threading.Thread(target=_rename, daemon=True).start()
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
        # 첨부를 받으려면 구글 로그인이 있어야 한다(없어도 공개 첨부는 받는다)
        self.view.set_auth(getattr(parent, "gauth", None))
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
            self.view.flush_search()     # 치자마자 Enter 면 마지막 글자까지 찾은 뒤에
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


class _BodyEdit(QTextEdit):
    """본문 칸. 글자는 글자로, **그림·파일을 붙이면 첨부로** 보낸다.

    네이버 메모처럼 쓰다가 Ctrl+V 하면 된다. 예전엔 그림을 붙이면 본문 안에
    보이지 않는 빈 글자(￼)로 섞여 들어가 저장할 때 사라졌다.

    ⚠️ 글자가 같이 들어 있으면 **글자가 먼저**다. 엑셀·워드에서 칸을 복사하면
       글자와 함께 그 모양을 찍은 그림도 실려 오는데, 그걸 첨부로 받으면
       붙여 넣으려던 글이 안 들어간다.
    """

    def __init__(self, on_files, parent=None):
        super().__init__(parent)
        self._on_files = on_files
        self.setAcceptRichText(False)

    @staticmethod
    def _local_files(md) -> bool:
        return md is not None and md.hasUrls() and any(u.isLocalFile() for u in md.urls())

    def canInsertFromMimeData(self, md):     # noqa: N802 — Qt 이름
        if self._local_files(md) or md.hasImage():
            return True
        return super().canInsertFromMimeData(md)

    def insertFromMimeData(self, md):        # noqa: N802
        if self._local_files(md):
            self._on_files(md)
            return
        if md.hasText() and md.text().strip():
            self.insertPlainText(md.text())
            return
        if md.hasImage():
            self._on_files(md)
            return
        super().insertFromMimeData(md)


class KbEditDialog(QDialog):
    """자료 편집 — 공통(관리자만) / 내 메모."""

    def __init__(self, account: str = "", parent=None, auth=None):
        super().__init__(parent)
        self.setWindowTitle("업무자료 편집")
        self.resize(900, 720)
        self.auth = auth
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
        self.txt_body = _BodyEdit(self.drop_attachments)
        right.addWidget(self.txt_body, 3)

        # 첨부(그림·PDF) — 본문 칸이나 여기서 Ctrl+V, 탐색기에서 끌어다 놓기
        self.lbl_att = QLabel("첨부 (그림·PDF) — 본문 칸에서 Ctrl+V 해도 여기로 들어옵니다")
        right.addWidget(self.lbl_att)
        arow = QHBoxLayout()
        self.lst_att = AttachList(self, editable=True)
        self.lst_att.setFixedHeight(184)
        arow.addWidget(self.lst_att, 1)
        abtn = QVBoxLayout()
        self.btn_att_paste = QPushButton("붙여넣기 (Ctrl+V)")
        self.btn_att_paste.clicked.connect(self.paste_attachments)
        self.btn_att_add = QPushButton("파일 추가…")
        self.btn_att_add.clicked.connect(self._add_files)
        self.btn_att_ren = QPushButton("이름 바꾸기")
        self.btn_att_ren.setToolTip("고른 첨부의 이름을 바꿉니다 (두 번 누르기 · F2 도 됩니다)")
        self.btn_att_ren.clicked.connect(self.rename_attachment)
        self.btn_att_del = QPushButton("빼기")
        self.btn_att_del.clicked.connect(self.remove_attachments)
        for b in (self.btn_att_paste, self.btn_att_add, self.btn_att_ren, self.btn_att_del):
            abtn.addWidget(b)
        abtn.addStretch()
        arow.addLayout(abtn)
        right.addLayout(arow)

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
                # 첨부는 이 창의 줄(lst_att)이 들고 있다 — 아직 안 올린 것도 함께
                "files": self.lst_att.atts(),
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
        self.lst_att.fill(list(it.get("files") or []))
        for w in (self.cmb_cat, self.ed_fin, self.ed_title, self.ed_tags,
                  self.txt_body, self.txt_check, self.lst_att,
                  self.btn_att_paste, self.btn_att_add, self.btn_att_ren, self.btn_att_del):
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
                if lst[i].get("files"):       # 내용만 기본으로 — 붙여 둔 첨부는 그대로
                    x["files"] = lst[i]["files"]
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

    # ---- 첨부 ----
    def _editing(self) -> bool:
        return 0 <= self._cur < len(self._cur_list())

    def drop_attachments(self, md) -> None:
        """붙여넣기·끌어다 놓기로 들어온 그림·파일을 지금 자료의 첨부로."""
        if not self._editing():
            QMessageBox.information(self, config.APP_NAME, "먼저 왼쪽에서 자료를 고르세요.")
            return
        got, bad = kb_files.from_mime(md)
        # 같은 것을 두 번 붙이지 않는다 — 붙여 넣은 그림은 이름에 시각이 붙어
        # 이름으로는 못 가린다. 아직 안 올린 것은 **내용**으로, 올린 것은 이름·크기로 본다.
        import hashlib
        have = set()
        for a in self.lst_att.atts():
            if a.get("_data"):
                have.add(hashlib.sha1(a["_data"]).hexdigest())
            have.add((a.get("name"), int(a.get("size") or 0)))
        for name, data in got:
            if hashlib.sha1(data).hexdigest() in have or (name, len(data)) in have:
                continue
            have.add(hashlib.sha1(data).hexdigest())
            att = {"id": "", "name": name, "mime": kb_files.mime_of(name),
                   "size": len(data), "_data": data}
            items = self.lst_att.atts() + [att]
            self.lst_att.fill(items)
        if bad:
            QMessageBox.information(self, config.APP_NAME,
                                    "넣지 못한 것:\n" + "\n".join(bad[:10]))
        elif not got:
            QMessageBox.information(
                self, config.APP_NAME,
                "붙여 넣을 그림이나 PDF 가 없습니다.\n"
                "카카오톡·캡처에서 그림을 복사하거나, 탐색기에서 파일을 복사한 뒤 눌러 주세요.")

    def paste_attachments(self) -> None:
        from PySide6.QtGui import QGuiApplication
        self.drop_attachments(QGuiApplication.clipboard().mimeData())

    def _add_files(self) -> None:
        if not self._editing():
            return
        from PySide6.QtCore import QMimeData, QUrl
        from PySide6.QtWidgets import QFileDialog
        paths, _f = QFileDialog.getOpenFileNames(
            self, "첨부할 그림·PDF", "",
            "그림·PDF (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.pdf)")
        if not paths:
            return
        md = QMimeData()
        md.setUrls([QUrl.fromLocalFile(p) for p in paths])
        self.drop_attachments(md)

    def remove_attachments(self) -> None:
        rows = set(self.lst_att.selected_rows())
        if not rows:
            return
        keep = [a for i, a in enumerate(self.lst_att.atts()) if i not in rows]
        self.lst_att.fill(keep)

    def rename_attachment(self, new_name: str | None = None) -> None:
        """고른 첨부 하나의 이름을 바꾼다. 확장자는 지킨다(kb_files.fix_name).

        올리기 전이면 그 이름으로 올라가고, 이미 올린 것이면 [저장] 때 드라이브의
        파일 이름도 같이 바꾼다. 카톡으로 보낼 때도 새 이름으로 간다.
        new_name 을 주면 묻지 않는다(검사용).
        """
        rows = self.lst_att.selected_rows()
        if not rows:
            li = self.lst_att.currentItem()
            rows = [self.lst_att.row(li)] if li is not None else []
        if len(rows) != 1:
            QMessageBox.information(self, config.APP_NAME, "이름을 바꿀 첨부를 하나 고르세요.")
            return
        atts = self.lst_att.atts()
        att = dict(atts[rows[0]])
        old = att.get("name", "")
        if new_name is None:
            import os
            from PySide6.QtWidgets import QInputDialog
            stem, ext = os.path.splitext(old)
            txt, okd = QInputDialog.getText(self, "첨부 이름 바꾸기",
                                            f"새 이름 (확장자 {ext} 는 그대로 둡니다):", text=stem)
            if not okd:
                return
            new_name = txt
        name = kb_files.fix_name(new_name, old)
        if not name or name == old:
            return
        if any(a.get("name") == name for i, a in enumerate(atts) if i != rows[0]):
            QMessageBox.information(self, config.APP_NAME, f"'{name}' 은(는) 이미 있습니다.")
            return
        att["name"] = name
        if att.get("id"):
            att.setdefault("_was", old)          # [저장] 때 드라이브·캐시 이름도 바꾼다
        atts[rows[0]] = att
        self.lst_att.fill(atts)
        self.lst_att.item(rows[0]).setSelected(True)

    def _pending(self) -> list:
        """아직 안 올린 첨부 → [(묶음 이름, 자료, 첨부)]."""
        out = []
        for src, lst in ((kb.SRC_SHARED, self.shared), (kb.SRC_MINE, self.mine)):
            for it in lst:
                for att in it.get("files") or []:
                    if not att.get("id"):
                        out.append((src, it, att))
        return out

    def _upload_pending(self) -> bool:
        """[저장] 전에 새 첨부를 올린다. 다 됐으면 True.

        하나라도 실패하면 창을 닫지 않는다. 이미 올라간 것은 첨부 정보로 바뀌어 있어
        다시 누르면 남은 것만 올린다.
        """
        todo = self._pending()
        if not todo:
            return True
        if self.auth is None or not self.auth.is_connected():
            QMessageBox.warning(self, config.APP_NAME,
                                "첨부를 올리려면 구글 로그인이 필요합니다.\n[설정] 에서 로그인해 주세요.")
            return False
        from PySide6.QtWidgets import QApplication, QProgressDialog
        prog = QProgressDialog("첨부를 구글 드라이브에 올리는 중…", None, 0, len(todo), self)
        prog.setWindowTitle(config.APP_NAME)
        prog.setMinimumDuration(0)
        prog.setValue(0)
        errors = []
        for n, (src, it, att) in enumerate(todo, 1):
            prog.setLabelText(f"첨부를 올리는 중… ({n}/{len(todo)})  {att.get('name', '')}")
            box = {}

            def work(a=att, pub=(src == kb.SRC_SHARED), out=box):
                try:
                    out["att"] = kb_files.upload(self.auth, a["_data"], a["name"], pub)
                except Exception as e:
                    out["err"] = str(e)
            th = threading.Thread(target=work, daemon=True)
            th.start()
            while th.is_alive():                 # 창이 굳지 않게 돌려 가며 기다린다
                QApplication.processEvents()
                th.join(0.05)
            if "att" in box:
                files = it.get("files") or []
                for i, a in enumerate(files):
                    if a is att:
                        files[i] = box["att"]
            else:
                errors.append(box.get("err") or att.get("name", ""))
            prog.setValue(n)
        prog.close()
        if errors:
            QMessageBox.warning(self, config.APP_NAME,
                                "첨부를 올리지 못했습니다(저장하지 않았습니다):\n"
                                + "\n".join(errors[:6])
                                + "\n\n인터넷을 확인한 뒤 [저장] 을 다시 눌러 주세요."
                                  " 이미 올라간 것은 다시 올리지 않습니다.")
            # 줄을 다시 그린다(올라간 것은 이제 id 가 있다). _on_row 를 부르면 안 된다 —
            # 그건 먼저 화면의 옛 줄로 자료를 덮어써(_stash) 올라간 것을 잊게 만든다.
            if self._editing():
                self.lst_att.fill(list(self._cur_list()[self._cur].get("files") or []))
            return False
        return True

    def renamed(self) -> list:
        """이름을 바꾼 '이미 올린' 첨부 → [(id, 새 이름)]."""
        out = []
        for lst in (self.shared, self.mine):
            for it in lst:
                for a in it.get("files") or []:
                    if a.get("id") and a.get("_was") and a.get("_was") != a.get("name"):
                        out.append((a["id"], a["name"]))
        return out

    def _ok(self) -> None:
        self._stash()
        if not self._upload_pending():
            return
        # 받아 둔 파일도 새 이름으로 — 카톡에 새 이름으로 가고, 다시 받지 않는다
        for fid, name in self.renamed():
            kb_files.rename_cache({"id": fid, "name": name}, name)
        self.accept()

    @classmethod
    def run(cls, account: str = "", parent=None, auth=None):
        """반환: (공통 목록, 내 메모 목록) 또는 None(취소).

        이름을 바꾼 첨부는 KbTab 이 드라이브 이름도 바꿀 수 있게 `last_renamed` 에 남긴다.
        """
        d = cls(account, parent, auth=auth)
        if d.exec() != QDialog.Accepted:
            return None
        cls.last_renamed = d.renamed()
        return ([x for x in d.shared if (x.get("title") or "").strip()],
                [x for x in d.mine if (x.get("title") or "").strip()])

    last_renamed: list = []
