"""고객 서류 첨부(v1.33) — 견적서·자동차등록증·계약확인서 등을 고객마다 여러 개.

지점장 요청: "고객관리 추가·수정 팝업에서 견적서 1개만 올릴 수 있는데, 등록증이나 계약확인서 같은
서류까지 여러 개 — 자료검색처럼." 그래서 자료검색 첨부 부품(kb_attach.AttachList · AttachViewer ·
kb_files)을 그대로 쓴다. 넣는 법도 같다 — Ctrl+V(캡처·카톡 그림·탐색기 파일) · 끌어다 놓기 ·
[파일 추가…]. 그림과 PDF.

  · 어디에 두나 — 파일은 **내 구글 드라이브 '고객서류' 폴더**에 올린다. **링크 공개를 하지 않는다**
    (등록증·계약서는 개인정보다). 이 계정으로 로그인한 일정관리기·폰 웹에서만 열린다.
  · 목록은 고객관리 시트의 **V열(앱 전용 숨김 칸)** 에 고객ID 와 함께 적는다(sheets.COL_FILES).
  · 예전 견적서(S열 셀 안 그림)는 첫 서류로 함께 보인다. 빼면 S열 그림도 지운다(예전 [지우기] 와 같다).
"""

from __future__ import annotations

import hashlib
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QInputDialog, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from . import config, crashlog, kb_files, sheets, theme
from .kb_attach import AttachList, AttachViewer

FOLDER_NAME = "고객서류"
NEW_PREFIX = "new-"                    # 아직 올리지 않은 서류의 임시 번호
LEGACY_NAME = "견적서(시트 그림).png"


def legacy_att(doc_cell: str) -> dict | None:
    """S열의 옛 견적서 그림 → 첨부 하나(없으면 None)."""
    fid = sheets.doc_file_id(doc_cell)
    if not fid:
        return None
    return {"id": fid, "name": LEGACY_NAME, "mime": "image/png", "size": 0, "_sheet": True}


def all_files(cr) -> list:
    """이 고객의 서류 전부 — 시트 V열 목록 + (거기 없으면) S열 옛 견적서 그림을 맨 앞에."""
    files = list(cr.files()) if hasattr(cr, "files") else []
    old = legacy_att(cr.get("doc")) if hasattr(cr, "get") else None
    if old and old["id"] not in {f["id"] for f in files}:
        files.insert(0, old)
    return files


def is_new(att: dict) -> bool:
    return str(att.get("id") or "").startswith(NEW_PREFIX)


# ---------------------------------------------------------------------------
# 받아서 크게 보기 — 편집 창과 고객 목록(우클릭 [서류 보기])이 함께 쓴다
# ---------------------------------------------------------------------------
class AttachOpener(QObject):
    """서류를 뒤에서 받아 두고, 크게 보기 창(돌리기·확대·PDF 장 넘기기·← →)을 띄운다."""

    _sig = Signal(str, str, str)       # (id, 경로, 오류)

    def __init__(self, parent_widget, auth_getter):
        super().__init__(parent_widget)
        self._w = parent_widget
        self._auth = auth_getter
        self._inflight: set = set()
        self._viewer = None
        self._want = None              # (첨부, 목록) — 받으면 바로 연다
        self._sig.connect(self._done)

    def fetch(self, att: dict) -> None:
        fid = att.get("id", "")
        if not fid or fid in self._inflight or kb_files.cached(att) or is_new(att):
            return
        self._inflight.add(fid)
        auth = self._auth()

        def worker():
            try:
                p = kb_files.fetch(auth, att)
                self._sig.emit(fid, str(p), "")
            except Exception as e:
                self._sig.emit(fid, "", (str(e).splitlines() or ["받지 못했습니다"])[0][:120])
        threading.Thread(target=worker, daemon=True).start()

    def _done(self, fid: str, path: str, err: str) -> None:
        self._inflight.discard(fid)
        if self._viewer is not None:
            self._viewer.loaded(fid, err)
        if self._want and self._want[0].get("id") == fid:
            att, atts = self._want
            self._want = None
            if err:
                QMessageBox.information(self._w, config.APP_NAME, f"서류를 받지 못했습니다:\n{err}")
            else:
                self.open(att, atts)

    def open(self, att: dict, atts: list) -> None:
        p = kb_files.cached(att)
        if not p:
            self._want = (att, atts)
            self.fetch(att)
            return
        try:
            data = p.read_bytes()
        except OSError as e:
            QMessageBox.information(self._w, config.APP_NAME, f"서류를 열지 못했습니다:\n{e}")
            return
        crashlog.note(f"고객 서류 크게 보기 {att.get('name', '')}")
        dlg = AttachViewer(att, data, parent=self._w, atts=list(atts), fetch=self.fetch)
        del data
        dlg.setAttribute(Qt.WA_DeleteOnClose, False)   # exec() 안에서 지워지지 않게 — 닫은 뒤 deleteLater
        self._viewer = dlg
        try:
            dlg.exec()
        finally:
            self._viewer = None
            dlg.deleteLater()


# ---------------------------------------------------------------------------
# 편집 창의 서류 칸
# ---------------------------------------------------------------------------
class CustomerFilesBox(QWidget):
    """고객 추가·수정 창의 '서류' 칸 — 작은 그림 줄 + [붙여넣기] [파일 추가…] [크게 보기] [이름 바꾸기] [빼기]."""

    def __init__(self, files: list, auth=None, parent=None):
        super().__init__(parent)
        self.auth = auth
        self._orig = [dict(f) for f in (files or [])]
        self.opener = AttachOpener(self, lambda: self.auth)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.lbl = QLabel("")
        self.lbl.setWordWrap(True)
        self.lbl.setStyleSheet(f"color:{theme.c('subtext')};")
        v.addWidget(self.lbl)
        self.lst = AttachList(self, editable=True, open_on_double=True)
        self.lst.setMinimumHeight(self.lst.gridSize().height() + 12)
        self.lst.setMaximumHeight(2 * self.lst.gridSize().height() + 16)
        v.addWidget(self.lst)
        row = QHBoxLayout()
        self.btn_paste = QPushButton("붙여넣기 (Ctrl+V)")
        self.btn_paste.clicked.connect(self.paste_attachments)
        self.btn_add = QPushButton("파일 추가…")
        self.btn_add.clicked.connect(self._add_files)
        self.btn_open = QPushButton("크게 보기")
        self.btn_open.clicked.connect(self._open_selected)
        self.btn_ren = QPushButton("이름 바꾸기")
        self.btn_ren.clicked.connect(lambda: self.rename_attachment())
        self.btn_del = QPushButton("빼기")
        self.btn_del.clicked.connect(self.remove_attachments)
        for b in (self.btn_paste, self.btn_add, self.btn_open, self.btn_ren, self.btn_del):
            row.addWidget(b)
        row.addStretch()
        v.addLayout(row)
        self.lst.fill([dict(f) for f in self._orig])
        self.lst.itemSelectionChanged.connect(self._paint)
        self._paint()
        for f in self._orig:                  # 작은 그림이 바로 보이게 받아 둔다
            self.opener.fetch(f)
        self.opener._sig.connect(lambda fid, _p, err: self.lst.refresh(fid, err))

    # ---- 보이기 ----
    def _paint(self) -> None:
        n = self.lst.count()
        new = sum(1 for a in self.lst.atts() if is_new(a))
        self.lbl.setText(
            (f"서류 {n}개" + (f" — 새로 넣은 {new}개는 [저장] 하면 내 구글 드라이브에 올라갑니다" if new else "")
             if n else "견적서·자동차등록증·계약확인서 등 — Ctrl+V(캡처·카톡 그림·파일) · 끌어다 놓기 · [파일 추가…]")
            + "\n그림·PDF · 링크 공개 없이 내 계정에만 · 두 번 누르면 크게 보기")
        sel = len(self.lst.selected_rows())
        self.btn_open.setEnabled(n > 0)
        self.btn_ren.setEnabled(sel == 1)
        self.btn_del.setEnabled(sel > 0)

    def atts(self) -> list:
        return self.lst.atts()

    # ---- 넣기 ----
    def drop_attachments(self, md) -> None:
        got, bad = kb_files.from_mime(md)
        have = {(a.get("name"), int(a.get("size") or 0)) for a in self.atts()}
        have |= {a.get("_sha") for a in self.atts() if a.get("_sha")}
        items = self.atts()
        added = 0
        for name, data in got:
            sha = hashlib.sha1(data).hexdigest()
            if sha in have or (name, len(data)) in have:
                continue                       # 같은 것을 두 번 넣지 않는다
            have.add(sha)
            att = {"id": NEW_PREFIX + sha[:16], "name": name, "mime": kb_files.mime_of(name),
                   "size": len(data), "_sha": sha}
            try:
                kb_files._store(att, data)     # 올리기 전에도 작은 그림·크게 보기가 되게
            except OSError:
                att["_data"] = data
            items.append(att)
            added += 1
        if added:
            self.lst.fill(items)
            self._paint()
        if bad:
            QMessageBox.information(self, config.APP_NAME, "넣지 못한 것:\n" + "\n".join(bad[:10]))
        elif not got:
            QMessageBox.information(
                self, config.APP_NAME,
                "붙여 넣을 그림이나 PDF 가 없습니다.\n"
                "캡처·카카오톡에서 그림을 복사하거나, 탐색기에서 파일을 복사한 뒤 눌러 주세요.")

    def paste_attachments(self) -> None:
        from PySide6.QtGui import QGuiApplication
        self.drop_attachments(QGuiApplication.clipboard().mimeData())

    def _add_files(self) -> None:
        from PySide6.QtCore import QMimeData, QUrl
        paths, _f = QFileDialog.getOpenFileNames(
            self, "고객 서류 — 그림·PDF", "", "그림·PDF (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.pdf)")
        if not paths:
            return
        md = QMimeData()
        md.setUrls([QUrl.fromLocalFile(p) for p in paths])
        self.drop_attachments(md)

    # ---- 고치기 ----
    def remove_attachments(self) -> None:
        rows = set(self.lst.selected_rows())
        if not rows:
            return
        self.lst.fill([a for i, a in enumerate(self.atts()) if i not in rows])
        self._paint()

    def rename_attachment(self, new_name: str | None = None) -> None:
        rows = self.lst.selected_rows()
        if len(rows) != 1:
            QMessageBox.information(self, config.APP_NAME, "이름을 바꿀 서류를 하나 고르세요.")
            return
        atts = self.atts()
        att = dict(atts[rows[0]])
        old = att.get("name", "")
        if not isinstance(new_name, str):
            import os
            stem, ext = os.path.splitext(old)
            txt, okd = QInputDialog.getText(self, "서류 이름 바꾸기",
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
        kb_files.rename_cache(att, name)
        att["name"] = name
        if not is_new(att):
            att.setdefault("_was", old)        # [저장] 때 드라이브의 파일 이름도 바꾼다
        atts[rows[0]] = att
        self.lst.fill(atts)
        self.lst.item(rows[0]).setSelected(True)

    # ---- 보기 ----
    def open_attachment(self, att: dict) -> None:
        self.opener.open(att, self.atts())

    def _open_selected(self) -> None:
        atts = self.atts()
        if not atts:
            return
        rows = self.lst.selected_rows()
        self.open_attachment(atts[rows[0]] if rows else atts[0])

    # ---- 저장 ----
    def pending(self) -> list:
        return [a for a in self.atts() if is_new(a)]

    def upload_pending(self, customer: str = "") -> bool:
        """[저장] 전에 새 서류를 올린다. 다 됐으면 True(하나라도 못 올리면 창을 닫지 않는다)."""
        todo = self.pending()
        if not todo:
            return True
        if self.auth is None or not self.auth.is_connected():
            QMessageBox.warning(self, config.APP_NAME,
                                "서류를 올리려면 구글 로그인이 필요합니다.\n[설정] 에서 로그인해 주세요.")
            return False
        from PySide6.QtWidgets import QApplication, QProgressDialog
        prog = QProgressDialog("서류를 내 구글 드라이브에 올리는 중…", None, 0, len(todo), self)
        prog.setWindowTitle(config.APP_NAME)
        prog.setMinimumDuration(0)
        prog.setValue(0)
        atts = self.atts()
        errors = []
        for n, att in enumerate(todo, 1):
            prog.setLabelText(f"서류를 올리는 중… ({n}/{len(todo)})  {att.get('name', '')}")
            box = {}

            def work(a=att, out=box):
                try:
                    p = kb_files.cached(a)
                    data = p.read_bytes() if p else a.get("_data", b"")
                    out["att"] = kb_files.upload(self.auth, data, a["name"], False, FOLDER_NAME)
                except Exception as e:
                    out["err"] = str(e)
            th = threading.Thread(target=work, daemon=True)
            th.start()
            while th.is_alive():                 # 창이 굳지 않게 돌려 가며 기다린다
                QApplication.processEvents()
                th.join(0.05)
            if "att" in box:
                i = next(k for k, a in enumerate(atts) if a.get("id") == att.get("id"))
                atts[i] = box["att"]
            else:
                errors.append(f"{att.get('name', '')}: {box.get('err', '')}")
            prog.setValue(n)
        prog.close()
        self.lst.fill(atts)
        self._paint()
        if errors:
            QMessageBox.warning(self, config.APP_NAME,
                                "올리지 못한 서류가 있습니다(다시 [저장] 하면 남은 것만 올립니다):\n\n"
                                + "\n".join(errors[:6]))
            return False
        crashlog.note(f"고객 서류 {len(todo)}개 올림" + (f" ({customer})" if customer else ""))
        return True

    def result(self) -> dict:
        """저장할 것 — {files: 올린 서류 목록, changed, removed: 뺀 파일 id, renamed: [(id, 새 이름)]}."""
        cur = [a for a in self.atts() if not is_new(a)]
        files = sheets.clean_files(cur)
        before = sheets.clean_files(self._orig)
        ids = {f["id"] for f in files}
        return {
            "files": files,
            "changed": [(f["id"], f["name"]) for f in files] != [(f["id"], f["name"]) for f in before],
            "removed": [f["id"] for f in before if f["id"] not in ids],
            "renamed": [(a["id"], a["name"]) for a in cur if a.get("_was")],
        }
