"""자료검색 첨부(그림·PDF) — 구글 드라이브에 올리고, 받아서 PC 에 캐시한다.

자료 하나에 `files: [{id, name, mime, size}]` 가 붙는다(kb.clean_files).
파일 본체는 드라이브 **`업무자료` 폴더**에 있다. 앱이 만든 폴더·파일이라 지금 쓰는
권한(drive.file)으로 충분하다 — 권한을 새로 묻지 않는다.

**누가 볼 수 있나**
  · 회사 공통 자료의 첨부는 다른 직원 계정에서도 보여야 하므로 올린 뒤
    '링크가 있는 누구나 보기' 로 연다(견적서 이미지와 같은 방식).
  · 내 메모의 첨부는 열지 않는다 — 내 계정에서만 보인다.

**받기** — 먼저 내 로그인으로 드라이브에 묻고, 안 되면 공개 주소로 받는다.
다른 직원이 관리자가 올린 파일을 받을 때가 그 경우다: drive.file 권한은 '이 앱이
그 사람 계정으로 만든 파일' 만 보게 해 주므로 API 로는 못 읽고, 공개 주소로는 된다.
받은 파일은 `%APPDATA%\\Planner\\kb_files\\<id>\\<원래 이름>` 에 둔다. 원래 이름을
지키는 이유는 카카오톡으로 보낼 때 그 이름 그대로 가기 때문이다.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

from . import config
from .net import http as _http

FOLDER_NAME = "업무자료"
MAX_BYTES = 25 * 1024 * 1024            # 한 파일 25MB 까지

IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp"}
PDF_TYPES = {".pdf": "application/pdf"}
ALLOWED = {**IMAGE_TYPES, **PDF_TYPES}

PUBLIC_URL = "https://drive.google.com/uc?export=download&id={id}"


class KbFileError(Exception):
    """사용자에게 그대로 보여 줄 수 있는 말썽."""


# ---------------------------------------------------------------------------
# 종류
# ---------------------------------------------------------------------------
def mime_of(name: str) -> str:
    """이름의 확장자로 본 종류. 첨부로 받지 않는 종류면 ""."""
    return ALLOWED.get(os.path.splitext(name or "")[1].lower(), "")


def is_image(att: dict) -> bool:
    return str(att.get("mime", "")).startswith("image/") or \
        os.path.splitext(att.get("name", ""))[1].lower() in IMAGE_TYPES


def is_pdf(att: dict) -> bool:
    return att.get("mime") == "application/pdf" or \
        att.get("name", "").lower().endswith(".pdf")


def size_text(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.1f}MB"
    return f"{max(1, n // 1024)}KB"


# ---------------------------------------------------------------------------
# 캐시
# ---------------------------------------------------------------------------
_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _safe(part: str) -> str:
    s = _BAD.sub("_", str(part or "")).strip().strip(".")
    return s[:120] or "파일"


def cache_dir() -> Path:
    d = config.base_dir() / "kb_files"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_path(att: dict) -> Path:
    return cache_dir() / _safe(att.get("id", "")) / _safe(att.get("name", ""))


def cached(att: dict) -> Path | None:
    """이미 받아 둔 파일이면 그 경로. 없으면 None."""
    p = cache_path(att)
    try:
        if p.exists() and p.stat().st_size > 0:
            return p
    except OSError:
        pass
    return None


def _store(att: dict, data: bytes) -> Path:
    p = cache_path(att)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".part")
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, p)                  # 받다 만 파일이 '받은 것' 으로 보이지 않게
    return p


# ---------------------------------------------------------------------------
# 드라이브
# ---------------------------------------------------------------------------
def _folder(auth) -> str:
    from . import sheets               # sheets 가 google_client 를 끌어온다 — 쓸 때만
    fid = sheets._find_or_create_folder(auth, FOLDER_NAME)
    if not fid:
        raise KbFileError(f"드라이브에 '{FOLDER_NAME}' 폴더를 만들지 못했습니다.")
    return fid


def upload(auth, data: bytes, name: str, public: bool) -> dict:
    """한 파일을 올리고 첨부 정보({id, name, mime, size})를 돌려준다.

    public=True(회사 공통 자료)면 '링크가 있는 누구나 보기' 로 연다.
    올린 파일은 캐시에도 넣어 둔다 — 올린 사람이 다시 받을 일이 없게.
    """
    mime = mime_of(name)
    if not mime:
        raise KbFileError(f"'{name}' — 그림(png·jpg 등)과 PDF 만 넣을 수 있습니다.")
    if not data:
        raise KbFileError(f"'{name}' — 빈 파일입니다.")
    if len(data) > MAX_BYTES:
        raise KbFileError(f"'{name}' — {size_text(len(data))}. "
                          f"한 파일 {size_text(MAX_BYTES)} 까지 넣을 수 있습니다.")
    folder = _folder(auth)
    # 이어올리기(resumable) — 큰 PDF 도 한 번에 올라간다
    h = dict(auth._headers())
    h.update({"Content-Type": "application/json; charset=UTF-8",
              "X-Upload-Content-Type": mime,
              "X-Upload-Content-Length": str(len(data))})
    r = _http().post(config.DRIVE_UPLOAD_URL, headers=h, timeout=30,
                     params={"uploadType": "resumable", "fields": "id"},
                     data=json.dumps({"name": name, "parents": [folder],
                                      "mimeType": mime}).encode("utf-8"))
    loc = (r.headers.get("Location") or "") if r.status_code == 200 else ""
    if not loc:
        raise KbFileError(f"'{name}' — 올리기를 시작하지 못했습니다 (HTTP {r.status_code}).")
    up = _http().put(loc, headers={"Content-Type": mime}, data=data, timeout=300)
    if up.status_code not in (200, 201):
        raise KbFileError(f"'{name}' — 올리지 못했습니다 (HTTP {up.status_code}).")
    fid = (up.json() or {}).get("id", "")
    if not fid:
        raise KbFileError(f"'{name}' — 올리지 못했습니다(파일 번호 없음).")
    if public:
        pr = _http().post(f"{config.DRIVE_FILES_URL}/{fid}/permissions",
                          headers=auth._headers(), timeout=20,
                          json={"role": "reader", "type": "anyone"})
        if pr.status_code not in (200, 201):
            trash(auth, [fid])         # 다른 직원이 못 보는 첨부를 남기지 않는다
            raise KbFileError(
                f"'{name}' — 올렸지만 공개 설정에 실패해 다른 직원이 볼 수 없습니다 "
                f"(HTTP {pr.status_code}). 다시 시도해 주세요.")
    att = {"id": fid, "name": name, "mime": mime, "size": len(data)}
    try:
        _store(att, data)
    except OSError:
        pass
    return att


def fetch(auth, att: dict) -> Path:
    """첨부를 PC 에 받아 그 경로를 돌려준다(받아 둔 것이 있으면 그대로)."""
    p = cached(att)
    if p:
        return p
    fid = att.get("id", "")
    if not fid:
        raise KbFileError("첨부 정보가 잘못됐습니다.")
    data = None
    # 1) 내 로그인으로 — 내가 올린 파일(내 메모 첨부 포함)
    try:
        if auth is not None and auth.is_connected():
            r = _http().get(f"{config.DRIVE_FILES_URL}/{fid}", headers=auth._headers(),
                            timeout=60, params={"alt": "media"})
            if r.status_code == 200 and r.content:
                data = r.content
    except Exception:
        data = None
    # 2) 공개 주소로 — 관리자가 올린 공통 자료 첨부
    if data is None:
        try:
            r = _http().get(PUBLIC_URL.format(id=fid), timeout=60)
            ctype = (r.headers.get("Content-Type") or "").lower()
            # 공개가 아니거나 지워진 파일이면 구글이 **HTML 안내 화면**을 준다
            if r.status_code == 200 and r.content and "text/html" not in ctype:
                data = r.content
        except Exception:
            data = None
    if data is None:
        raise KbFileError(f"'{att.get('name', '')}' 을(를) 받지 못했습니다.\n"
                          "인터넷 연결을 확인하거나, 올린 사람에게 파일이 남아 있는지 물어보세요.")
    return _store(att, data)


def trash(auth, ids) -> None:
    """드라이브 휴지통으로(30일 안에 되살릴 수 있다). 실패해도 넘어간다."""
    for fid in ids or []:
        try:
            _http().patch(f"{config.DRIVE_FILES_URL}/{fid}", headers=auth._headers(),
                          timeout=20, json={"trashed": True})
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 클립보드 · 끌어다 놓기 → 넣을 파일
# ---------------------------------------------------------------------------
def pasted_name(ext: str = ".png") -> str:
    return f"붙여넣은 그림 {datetime.now():%m%d_%H%M%S}{ext}"


def from_mime(md) -> tuple:
    """QMimeData → ([(이름, 바이트)], [안 된 것 설명]).

    · 파일(탐색기에서 복사·끌기): 그림·PDF 만 받는다
    · 그림(카카오톡·캡처 도구에서 복사): PNG 로 담는다
    파일이 있으면 파일을 먼저 본다 — 그림 파일을 복사하면 둘 다 들어오는데,
    파일 쪽이 원래 이름·화질을 그대로 갖고 있다.
    """
    got, bad = [], []
    if md is None:
        return got, bad
    if md.hasUrls():
        for u in md.urls():
            if not u.isLocalFile():
                continue
            p = u.toLocalFile()
            name = os.path.basename(p)
            if os.path.isdir(p):
                bad.append(f"{name} — 폴더는 넣을 수 없습니다")
                continue
            if not mime_of(name):
                bad.append(f"{name} — 그림과 PDF 만 넣을 수 있습니다")
                continue
            try:
                size = os.path.getsize(p)
                if size > MAX_BYTES:
                    bad.append(f"{name} — {size_text(size)}, {size_text(MAX_BYTES)} 까지")
                    continue
                with open(p, "rb") as f:
                    got.append((name, f.read()))
            except OSError as e:
                bad.append(f"{name} — {e}")
        if got or bad:
            return got, bad
    if md.hasImage():
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        from PySide6.QtGui import QImage
        img = md.imageData()
        if isinstance(img, QImage) and not img.isNull():
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QIODevice.WriteOnly)
            img.save(buf, "PNG")
            buf.close()
            got.append((pasted_name(".png"), bytes(ba)))
    return got, bad
