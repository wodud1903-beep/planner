"""PDF 병합(v1.37) — 고객정보에서 고른 그림 · PDF 를 정한 차례대로 PDF 한 개로(화면 없는 계산).

지점장(F3): "jpg, pdf 등의 파일들을 다중선택 후 pdf 병합 버튼을 만든다. 단, pdf 병합 시 파일의 순서를 지정할 수
있게 한다." 차례를 정하는 창은 pdf_merge_dialog, 단추는 customer_files_tab.

  · PDF 는 쪽을 그대로 이어 붙인다 — 글자가 그림으로 바뀌지 않는다(pypdf).
  · 그림은 A4 한 쪽에 맞춰 가운데에 넣는다. 가로로 긴 그림은 가로 A4. 휴대폰 사진의 돌림(EXIF)도 바로잡는다.
  · 여러 장짜리 TIFF(스캐너)는 장마다 한 쪽. GIF 는 첫 장만.
  · 저장 이름 '폴더명_병합_YYMMDD.pdf' — 같은 이름이 있으면 '… (2).pdf', '… (3).pdf'.
"""

from __future__ import annotations

import io
import re
from datetime import date
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMarginsF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QImageReader, QPageLayout, QPageSize, QPainter, QPdfWriter

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
PDF_EXT = {".pdf"}
MERGE_EXT = IMAGE_EXT | PDF_EXT
MULTI_FRAME_EXT = {".tif", ".tiff"}
MAX_FRAMES = 300           # 여러 장 TIFF 상한(깨진 파일에서 끝없이 돌지 않게)
DPI = 150                  # 그림 쪽의 PDF 해상도(QPdfWriter 좌표) — 그림은 제 해상도 그대로 들어간다
MAX_SIDE = 3000            # 그림 긴 변이 이보다 크면 줄인다(A4 300dpi 쯤 — 계약서 글씨가 또렷한 정도)
MARGIN_MM = 6


class MergeError(Exception):
    """합칠 수 없는 파일 — 메시지는 그대로 지점장에게 보인다."""


def kind_of(name: str) -> str:
    ext = Path(str(name)).suffix.lower()
    if ext in PDF_EXT:
        return "pdf"
    if ext in IMAGE_EXT:
        return "image"
    return ""


def can_merge(name: str) -> bool:
    return kind_of(name) != ""


_BAD = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def suggest_name(folder_name: str, today: date | None = None) -> str:
    """'폴더명_병합_YYMMDD.pdf' — 파일 이름에 못 쓰는 글자는 뺀다."""
    d = today or date.today()
    base = _BAD.sub(" ", str(folder_name or "")).strip().strip(".") or "서류"
    return f"{base}_병합_{d:%y%m%d}.pdf"


def unique_path(folder, name: str) -> Path:
    """그 폴더에 같은 이름이 있으면 '이름 (2).pdf', '이름 (3).pdf' …"""
    folder = Path(folder)
    p = folder / name
    if not p.exists():
        return p
    stem, ext = Path(name).stem, Path(name).suffix
    n = 2
    while (folder / f"{stem} ({n}){ext}").exists():
        n += 1
    return folder / f"{stem} ({n}){ext}"


# ---------------------------------------------------------------------------
# 그림 → PDF 쪽
# ---------------------------------------------------------------------------
def image_frames(data: bytes, name: str = "") -> list:
    """그림 바이트 → QImage 목록(TIFF 는 모든 장, 나머지는 첫 장). 돌림(EXIF)은 바로잡는다. 못 읽으면 []."""
    ba = QByteArray(bytes(data))
    buf = QBuffer(ba)
    buf.open(QIODevice.ReadOnly)
    multi = Path(str(name)).suffix.lower() in MULTI_FRAME_EXT
    out = []
    rd = QImageReader(buf)
    try:
        rd.setAutoTransform(True)
        rd.setDecideFormatFromContent(True)
        # ⚠️ 여러 장 TIFF 는 첫 장을 읽기 **전에** 장 수를 세어야 한다 — 읽은 뒤에 세면 Qt 의 TIFF 읽개가
        #    엉뚱한 자리에서 세다 실패해(0장) 첫 장만 들어갔다.
        total = rd.imageCount() if multi else 1
        for _i in range(max(1, min(total, MAX_FRAMES))):
            # 아주 큰 스캔은 읽을 때부터 줄여 푼다 — 통째로 풀면 Qt 기본 한도(256MB)에 걸려 못 읽는다
            # (file_preview._read_img 와 같은 까닭). 줄인 결과만 남으므로 이 읽개만 한도를 넉넉히 연다.
            size = rd.size()
            if size.isValid() and max(size.width(), size.height()) > MAX_SIDE:
                rd.setScaledSize(size.scaled(MAX_SIDE, MAX_SIDE, Qt.KeepAspectRatio))
                rd.setAllocationLimit(1024)
            else:
                rd.setScaledSize(QSize())
            img = rd.read()
            if img.isNull():
                break
            out.append(_shrink(img))
            if not multi or not rd.jumpToNextImage():
                break
    finally:
        # ⚠️ 읽개를 버퍼보다 먼저 없앤다 — TIFF 읽개는 없어질 때 버퍼를 한 번 더 만지는데, 버퍼가 먼저 닫혀
        #    있으면 프로그램이 통째로 꺼졌다(여러 장 TIFF 로 검사하다 찾음).
        del rd
        buf.close()
    return out


def _shrink(img: QImage) -> QImage:
    w, h = img.width(), img.height()
    if max(w, h) <= MAX_SIDE:
        return img
    return img.scaled(MAX_SIDE, MAX_SIDE, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def _layout_for(img: QImage) -> QPageLayout:
    orient = QPageLayout.Landscape if img.width() > img.height() else QPageLayout.Portrait
    return QPageLayout(QPageSize(QPageSize.A4), orient, QMarginsF(MARGIN_MM, MARGIN_MM, MARGIN_MM, MARGIN_MM),
                       QPageLayout.Millimeter)


def image_pdf(frames: list) -> bytes:
    """그림(들)을 A4 쪽(들)로 — 쪽마다 그림 하나, 비율 그대로 가운데."""
    if not frames:
        raise MergeError("그림이 없습니다")
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    wr = QPdfWriter(buf)
    wr.setResolution(DPI)
    wr.setCreator("일정관리기")
    wr.setPageLayout(_layout_for(frames[0]))
    p = QPainter(wr)
    try:
        for i, img in enumerate(frames):
            if i:
                wr.setPageLayout(_layout_for(img))
                wr.newPage()
            area = QRectF(0, 0, wr.width(), wr.height())
            if img.hasAlphaChannel():
                p.fillRect(area, QColor(Qt.white))
            sz = img.size().scaled(area.size().toSize(), Qt.KeepAspectRatio)
            x = (area.width() - sz.width()) / 2
            y = (area.height() - sz.height()) / 2
            p.setRenderHint(QPainter.SmoothPixmapTransform, True)
            p.drawImage(QRectF(x, y, sz.width(), sz.height()), img)
    finally:
        p.end()
        buf.close()
    return bytes(ba.data())


# ---------------------------------------------------------------------------
# 합치기
# ---------------------------------------------------------------------------
def pdf_pages(data: bytes) -> int:
    """PDF 쪽 수(못 읽으면 0) — 차례 창에 '3쪽' 으로 보인다."""
    try:
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(bytes(data)))
        if r.is_encrypted:
            r.decrypt("")
        return len(r.pages)
    except Exception:
        return 0


def merge(items: list, progress=None) -> tuple:
    """[(파일 이름, 바이트)] 를 그 차례대로 PDF 하나로 → (PDF 바이트, 쪽 수).

    progress(i, n) 가 있으면 파일마다 부른다(화면이 멈추지 않게). 못 합치는 파일이 있으면 MergeError."""
    from pypdf import PdfReader, PdfWriter
    if not items:
        raise MergeError("합칠 파일이 없습니다")
    w = PdfWriter()
    n = len(items)
    for i, (name, data) in enumerate(items):
        if progress:
            progress(i, n)
        k = kind_of(name)
        if k == "pdf":
            try:
                r = PdfReader(io.BytesIO(bytes(data)))
                if r.is_encrypted and not r.decrypt(""):
                    raise MergeError(f"'{name}' — 암호가 걸린 PDF 라 합칠 수 없습니다")
                for page in r.pages:
                    w.add_page(page)
            except MergeError:
                raise
            except Exception as e:
                raise MergeError(f"'{name}' — PDF 를 읽지 못했습니다({type(e).__name__})") from e
        elif k == "image":
            frames = image_frames(data, name)
            if not frames:
                raise MergeError(f"'{name}' — 그림을 읽지 못했습니다")
            for page in PdfReader(io.BytesIO(image_pdf(frames))).pages:
                w.add_page(page)
        else:
            raise MergeError(f"'{name}' — 그림(jpg · png …)이나 PDF 만 합칠 수 있습니다")
    if progress:
        progress(n, n)
    out = io.BytesIO()
    w.write(out)
    return out.getvalue(), len(w.pages)
