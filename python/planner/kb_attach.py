"""자료검색 첨부 칸 — 작은 그림 줄, 크게 보기 창, 카톡으로 보내기.

보기 화면(KbView)과 편집 창(KbEditDialog)이 같은 줄(AttachList)을 쓴다.
  · 보기: 골라서 **Ctrl+C** → 카카오톡 대화창에서 Ctrl+V. **끌어서** 카톡 창에 놓아도 된다.
          두 번 누르면 크게 보기(돌리기·PDF 장 넘기기 — 고객정보 탭의 미리보기 그대로).
  · 편집: Ctrl+V · 탐색기에서 끌어다 놓기로 넣는다(넣는 일은 편집 창이 맡는다).

카톡으로 보내는 모양(파일 목록 + 그림 하나면 그림)은 고객정보 탭과 같은
clipfiles.file_mime 을 쓴다.
"""

from __future__ import annotations

import os
from collections import OrderedDict

from PySide6.QtCore import QBuffer, QByteArray, QItemSelectionModel, QRect, QSize, Qt
from PySide6.QtGui import (
    QColor, QDrag, QFont, QIcon, QImageReader, QKeySequence, QPainter, QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QListView, QListWidget,
    QListWidgetItem, QMenu, QPushButton, QVBoxLayout,
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


# 작은 그림 캐시 — (경로, 크기, 수정시각) → QIcon. 같은 파일은 다시 풀지 않는다.
_THUMBS: OrderedDict = OrderedDict()
_THUMB_MAX = 300
decode_count = 0                # 실제로 그림을 푼 횟수(검사가 본다)


def _decode_small(data: bytes | None = None, path: str = ""):
    """그림을 **작게 풀어** QImage 로. 원본 크기로는 풀지 않는다.

    ⚠️ 예전엔 QPixmap.load 로 원본을 통째로 푼 뒤 줄였다. 폰 사진·스캔 한 장이
       수십~백MB 라, 검색칸에 한 글자 칠 때마다 첨부 전부를 그렇게 풀어 화면이
       멈추고, 끝내 메모리가 바닥나 프로그램이 꺼졌다. 읽개에게 처음부터 작은
       크기로 풀라고 하면(setScaledSize) JPEG 는 몇 분의 일 시간·메모리로 끝난다.
    ⚠️ 읽개가 버퍼를 가리키므로 **읽개 먼저, 버퍼 나중** 에 없앤다
       (file_preview._read_img 의 segfault 기록 그대로).
    """
    global decode_count
    decode_count += 1
    buf = None
    if data is not None:
        buf = QBuffer()
        buf.setData(QByteArray(bytes(data)))
        buf.open(QBuffer.ReadOnly)
        r = QImageReader(buf)
    else:
        r = QImageReader(path)
    r.setAutoTransform(True)            # 폰 사진의 회전 정보(EXIF)를 따른다
    sz = r.size()
    if sz.isValid() and (sz.width() > THUMB or sz.height() > THUMB):
        r.setScaledSize(sz.scaled(THUMB, THUMB, Qt.KeepAspectRatio))
    img = r.read()
    del r                               # 읽개 먼저
    del buf                             # 버퍼 나중
    return None if img.isNull() else img


def _thumb_from(path_or_data) -> QIcon | None:
    """그림 → 작은 그림. **늘 THUMB×THUMB 정사각형**에 가운데 맞춰 그린다.

    ⚠️ 크기를 그림마다 다르게 두면 줄이 첫 항목 크기로 칸을 잡아서(uniformItemSizes)
       키 큰 항목(PDF 표시)의 이름이 잘려 안 보였다.
    """
    if isinstance(path_or_data, (bytes, bytearray)):
        key = ("data", len(path_or_data), hash(bytes(path_or_data[:4096])),
               hash(bytes(path_or_data[-4096:])))
        src = {"data": bytes(path_or_data)}
    else:
        path = str(path_or_data)
        try:
            st = os.stat(path)
        except OSError:
            return None
        key = (os.path.normcase(path), st.st_size, st.st_mtime_ns)
        src = {"path": path}
    ic = _THUMBS.get(key)
    if ic is not None:
        _THUMBS.move_to_end(key)
        return ic
    img = _decode_small(**src)
    if img is None:
        return None
    sm = QPixmap.fromImage(img)
    if sm.width() > THUMB or sm.height() > THUMB:     # 크기를 못 읽는 형식 대비
        sm = sm.scaled(THUMB, THUMB, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    out = QPixmap(THUMB, THUMB)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.drawPixmap((THUMB - sm.width()) // 2, (THUMB - sm.height()) // 2, sm)
    p.end()
    ic = QIcon(out)
    _THUMBS[key] = ic
    while len(_THUMBS) > _THUMB_MAX:
        _THUMBS.popitem(last=False)
    return ic


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
      owner.save_attachment_as(att)      : 오른쪽 단추 [다른 이름으로 저장]
      owner.rename_attachment()          : 편집 창 — 두 번 누르기 · F2 · [이름 바꾸기]
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
        if self._editable and ev.key() == Qt.Key_F2 and hasattr(self._owner, "rename_attachment"):
            self._owner.rename_attachment()
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
        # 편집 창에서는 두 번 누르면 이름 바꾸기, 보기 화면에서는 크게 보기
        if self._editable:
            fn = getattr(self._owner, "rename_attachment", None)
            if callable(fn):
                self.setCurrentItem(li)
                fn()
            return
        fn = getattr(self._owner, "open_attachment", None)
        if callable(fn):
            fn(li.data(Qt.UserRole) or {})

    # ---- 오른쪽 단추 ----
    def menu_for(self, li) -> QMenu | None:
        """그 첨부 위에서 오른쪽 단추를 눌렀을 때의 메뉴(띄우지는 않는다 — 검사가 쓴다)."""
        if li is None:
            return None
        if not li.isSelected():          # 고르지 않은 것 위에서 누르면 그것만 고른다
            self.clearSelection()
            li.setSelected(True)
        # ⚠️ 그냥 setCurrentItem 하면 여럿 고른 것이 그 하나로 줄어든다(선택을 새로 짠다)
        self.setCurrentItem(li, QItemSelectionModel.NoUpdate)
        att = li.data(Qt.UserRole) or {}
        o = self._owner
        m = QMenu(self)
        if self._editable:
            if hasattr(o, "rename_attachment"):
                m.addAction("이름 바꾸기 (F2)", o.rename_attachment)
            if hasattr(o, "remove_attachments"):
                m.addAction("빼기 (Delete)", o.remove_attachments)
            return m
        n = len(self.selectedItems())
        if hasattr(o, "copy_attachments"):
            a = m.addAction(("복사하기" if n <= 1 else f"{n}개 복사하기")
                            + " (Ctrl+C) — 카카오톡에 붙여넣기",
                            lambda: o.copy_attachments(self.selected_atts()))
            m.setDefaultAction(a)
        if hasattr(o, "open_attachment"):
            m.addAction("크게 보기", lambda a=att: o.open_attachment(a))
        if hasattr(o, "save_attachment_as"):
            m.addAction("다른 이름으로 저장…", lambda a=att: o.save_attachment_as(a))
        return m

    def contextMenuEvent(self, ev):  # noqa: N802
        m = self.menu_for(self.itemAt(ev.pos()))
        if m is not None and m.actions():
            m.exec(ev.globalPos())
        if m is not None:
            m.deleteLater()              # 누를 때마다 메뉴가 쌓이지 않게

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
    """첨부 하나를 크게 — 돌리기·확대·PDF 장 넘기기 + [카톡으로 보내기].

    창 위 막대에 **최대화** 단추가 있고, [전체 화면](F11)으로 화면 가득 볼 수 있다.
    전체 화면에서는 Esc 나 F11 로 돌아온다(Esc 를 한 번 더 누르면 닫힌다).
    ⚠️ QDialog 는 윈도에서 기본으로 최대화 단추가 없다 — 창 모양을 직접 정해 준다.
    """

    def __init__(self, att: dict, data: bytes, on_send=None, parent=None):
        super().__init__(parent)
        from .file_preview import FilePreview
        self.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint
                            | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
        # ⚠️ 닫으면 **없앤다.** 예전엔 닫아도 창이 원본 그림·PDF 를 든 채 남아,
        #    열 때마다 메모리가 쌓여 끝내 프로그램이 꺼졌다.
        self.setAttribute(Qt.WA_DeleteOnClose, True)
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
        self.btn_full = QPushButton("전체 화면 (F11)")
        self.btn_full.setToolTip("화면 가득 보기 — Esc 나 F11 로 돌아옵니다")
        self.btn_full.clicked.connect(self.toggle_full)
        row.addWidget(self.btn_full)
        row.addStretch()
        b = QPushButton("닫기")
        b.clicked.connect(self.accept)
        row.addWidget(b)
        v.addLayout(row)

    def done(self, r):              # 닫기·Esc·[닫기] 모두 여기를 지난다
        try:
            self.preview._drop_doc()     # PDF 문서를 먼저 닫고(버퍼를 놓게 한 뒤)
            self.preview._drop_img()     # 그림도 놓는다
        except Exception:
            pass
        super().done(r)

    def toggle_full(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            self.btn_full.setText("전체 화면 (F11)")
        else:
            self.showFullScreen()
            self.btn_full.setText("전체 화면 끝내기 (Esc)")

    def keyPressEvent(self, ev):    # noqa: N802
        if ev.key() == Qt.Key_F11:
            self.toggle_full()
            return
        if ev.key() == Qt.Key_Escape and self.isFullScreen():
            self.toggle_full()               # 전체 화면이면 먼저 돌아오기만 한다
            return
        super().keyPressEvent(ev)
