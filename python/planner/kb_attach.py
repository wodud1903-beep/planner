"""자료검색 첨부 칸 — 작은 그림 줄, 크게 보기 창, 카톡으로 보내기.

보기 화면(KbView)과 편집 창(KbEditDialog)이 같은 줄(AttachList)을 쓴다.
  · 보기: 골라서 **Ctrl+C** → 카카오톡 대화창에서 Ctrl+V. **끌어서** 카톡 창에 놓아도 된다.
          두 번 누르면 크게 보기(돌리기·PDF 장 넘기기 — 고객정보 탭의 미리보기 그대로).
  · 편집: Ctrl+V · 탐색기에서 끌어다 놓기로 넣는다(넣는 일은 편집 창이 맡는다).

카톡으로 보내는 모양(파일 목록 + 그림 하나면 그림)은 고객정보 탭과 같은
clipfiles.file_mime 을 쓴다.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QDrag, QFont, QIcon, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QListView, QListWidget,
    QListWidgetItem, QPushButton, QVBoxLayout,
)

from . import kb_files, theme
from .clipfiles import file_mime

THUMB = 112                     # 작은 그림 한 변(px)


# ---------------------------------------------------------------------------
# 작은 그림
# ---------------------------------------------------------------------------
def _badge_icon(text: str, fg: str, fill: str) -> QIcon:
    """그림이 아직 없을 때·PDF 일 때 쓰는 네모 표시."""
    pm = QPixmap(THUMB, THUMB)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    r = QRect(14, 4, THUMB - 28, THUMB - 8)
    p.setPen(QColor(theme.c("border")))
    p.setBrush(QColor(theme.c("panel_bg")))
    p.drawRoundedRect(r, 6, 6)
    band = QRect(r.left(), r.top() + r.height() // 2 - 12, r.width(), 24)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(fill))
    p.drawRect(band)
    f = QFont()
    f.setBold(True)
    f.setPointSize(10)
    p.setFont(f)
    p.setPen(QColor(fg))
    p.drawText(band, Qt.AlignCenter, text)
    p.end()
    return QIcon(pm)


def _thumb_from(path_or_data) -> QIcon | None:
    """그림 → 작은 그림. **늘 THUMB×THUMB 정사각형**에 가운데 맞춰 그린다.

    ⚠️ 크기를 그림마다 다르게 두면 줄이 첫 항목 크기로 칸을 잡아서(uniformItemSizes)
       키 큰 항목(PDF 표시)의 이름이 잘려 안 보였다.
    """
    pm = QPixmap()
    if isinstance(path_or_data, (bytes, bytearray)):
        pm.loadFromData(bytes(path_or_data))
    else:
        pm.load(str(path_or_data))
    if pm.isNull():
        return None
    sm = pm.scaled(THUMB, THUMB, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    out = QPixmap(THUMB, THUMB)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.drawPixmap((THUMB - sm.width()) // 2, (THUMB - sm.height()) // 2, sm)
    p.end()
    return QIcon(out)


def icon_for(att: dict) -> QIcon:
    """첨부 하나의 작은 그림. 그림이면 실제 그림, PDF 면 PDF 표시."""
    if kb_files.is_pdf(att):
        return _badge_icon("PDF", theme.strong("red"), theme.strong_bg("red"))
    data = att.get("_data")
    if data:
        ic = _thumb_from(data)
        if ic:
            return ic
    p = kb_files.cached(att) if att.get("id") else None
    if p:
        ic = _thumb_from(p)
        if ic:
            return ic
    if att.get("_err"):
        return _badge_icon("받기 실패", theme.strong("red"), theme.strong_bg("red"))
    return _badge_icon("받는 중…", theme.strong("gray"), theme.strong_bg("gray"))


def label_for(att: dict) -> str:
    name = att.get("name", "")
    return name if len(name) <= 18 else name[:16] + "…"


def tip_for(att: dict) -> str:
    bits = [att.get("name", "")]
    if att.get("size"):
        bits.append(kb_files.size_text(int(att["size"])))
    if not att.get("id"):
        bits.append("저장할 때 올립니다")
    if att.get("_err"):
        bits.append(att["_err"])
    return "\n".join(bits)


# ---------------------------------------------------------------------------
# 첨부 줄
# ---------------------------------------------------------------------------
class AttachList(QListWidget):
    """작은 그림 줄. 항목마다 첨부 dict 를 달아 둔다(Qt.UserRole).

    owner 가 알아야 할 것(있을 때만 부른다):
      owner.attach_paths(atts) -> [경로]  : 카톡으로 보낼 PC 경로(없으면 받기 시작)
      owner.copy_attachments()           : Ctrl+C
      owner.open_attachment(att)         : 두 번 누르기
      owner.drop_attachments(QMimeData)  : 편집 창에서 끌어다 놓기·붙여넣기
    """

    def __init__(self, owner, editable: bool = False, parent=None):
        super().__init__(parent)
        self._owner = owner
        self._editable = editable
        self.setViewMode(QListView.IconMode)
        self.setIconSize(QSize(THUMB, THUMB))
        self.setGridSize(QSize(THUMB + 34, THUMB + 46))   # 이름 두 줄까지
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setWrapping(True)
        self.setWordWrap(True)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        if editable:
            self.setAcceptDrops(True)
            self.setDragDropMode(QAbstractItemView.DropOnly)
        else:
            self.setDragEnabled(True)
            self.setDragDropMode(QAbstractItemView.DragOnly)
        self.itemDoubleClicked.connect(self._dbl)

    # ---- 채우기 ----
    def fill(self, files: list) -> None:
        self.clear()
        for att in files or []:
            li = QListWidgetItem(icon_for(att), label_for(att))
            li.setData(Qt.UserRole, att)
            li.setToolTip(tip_for(att))
            self.addItem(li)

    def refresh(self, att_id: str, err: str = "") -> None:
        """받기가 끝난 첨부의 그림만 다시 그린다(못 받았으면 그 이유를 달아 둔다).

        ⚠️ 항목에 단 dict 는 꺼낼 때마다 **사본**이 나온다(PySide 가 바꿔 담는다).
           꺼낸 것을 고쳐도 항목은 그대로라, 고친 것을 다시 넣어 줘야 한다.
        """
        for i in range(self.count()):
            li = self.item(i)
            att = li.data(Qt.UserRole) or {}
            if att.get("id") == att_id:
                if err:
                    att["_err"] = err
                else:
                    att.pop("_err", None)
                li.setData(Qt.UserRole, att)
                li.setIcon(icon_for(att))
                li.setToolTip(tip_for(att))

    def selected_rows(self) -> list:
        return sorted({self.row(li) for li in self.selectedItems()})

    def atts(self) -> list:
        return [self.item(i).data(Qt.UserRole) for i in range(self.count())]

    def selected_atts(self) -> list:
        return [li.data(Qt.UserRole) for li in self.selectedItems()]

    # ---- 카톡으로 ----
    def startDrag(self, actions):   # noqa: N802 — Qt 이름
        """밖으로 끌기 — 카카오톡 대화창·바탕화면에 놓으면 그 파일이 간다."""
        fn = getattr(self._owner, "attach_paths", None)
        paths = fn(self.selected_atts()) if callable(fn) else []
        if not paths:
            return
        drag = QDrag(self)
        drag.setMimeData(file_mime(paths))
        li = self.currentItem()
        if li is not None:
            drag.setPixmap(li.icon().pixmap(THUMB // 2, THUMB // 2))
        drag.exec(Qt.CopyAction)

    def keyPressEvent(self, ev):    # noqa: N802
        if ev.matches(QKeySequence.Copy) and hasattr(self._owner, "copy_attachments"):
            self._owner.copy_attachments()
            return
        if (self._editable and ev.matches(QKeySequence.Paste)
                and hasattr(self._owner, "paste_attachments")):
            self._owner.paste_attachments()
            return
        if self._editable and ev.key() in (Qt.Key_Delete, Qt.Key_Backspace) \
                and hasattr(self._owner, "remove_attachments"):
            self._owner.remove_attachments()
            return
        super().keyPressEvent(ev)

    def _dbl(self, li):
        fn = getattr(self._owner, "open_attachment", None)
        if callable(fn):
            fn(li.data(Qt.UserRole) or {})

    # ---- 편집 창: 끌어다 놓기 ----
    def _wants(self, md) -> bool:
        return bool(md) and (md.hasUrls() or md.hasImage())

    def dragEnterEvent(self, ev):   # noqa: N802
        if self._editable and self._wants(ev.mimeData()):
            ev.acceptProposedAction()
        else:
            super().dragEnterEvent(ev)

    def dragMoveEvent(self, ev):    # noqa: N802
        if self._editable and self._wants(ev.mimeData()):
            ev.acceptProposedAction()
        else:
            super().dragMoveEvent(ev)

    def dropEvent(self, ev):        # noqa: N802
        fn = getattr(self._owner, "drop_attachments", None)
        if self._editable and callable(fn) and self._wants(ev.mimeData()):
            ev.acceptProposedAction()
            fn(ev.mimeData())
            return
        super().dropEvent(ev)


# ---------------------------------------------------------------------------
# 크게 보기
# ---------------------------------------------------------------------------
class AttachViewer(QDialog):
    """첨부 하나를 크게 — 돌리기·확대·PDF 장 넘기기 + [카톡으로 보내기]."""

    def __init__(self, att: dict, data: bytes, on_send=None, parent=None):
        super().__init__(parent)
        from .file_preview import FilePreview
        self.setWindowTitle(att.get("name", "첨부"))
        self.resize(920, 760)
        v = QVBoxLayout(self)
        self.preview = FilePreview(self, on_send=on_send)
        v.addWidget(self.preview, 1)
        key = att.get("id") or att.get("name", "")
        if kb_files.is_pdf(att):
            shown = self.preview.show_pdf(data, key, att.get("name", ""))
        else:
            shown = self.preview.show_image(data, key, att.get("name", ""))
        if not shown:
            self.preview.show_message("이 파일을 보여 줄 수 없습니다.", att.get("name", ""))
        row = QHBoxLayout()
        row.addStretch()
        b = QPushButton("닫기")
        b.clicked.connect(self.accept)
        row.addWidget(b)
        v.addLayout(row)
