"""명함 사진(v1.36) — 멘트복사 [명함복사] 가 클립보드에 넣는 그림.

지점장 요청: "멘트복사 각 캐피탈 단추에 명함 복사를 하나 — 미리 올려 둔 명함 사진을 클립보드에.
항상 딜레이 없이 바로 복사되도록 프로그램이 켜지면 명함 사진은 먼저 불러와 두고. 구글에 로그인하고
명함을 올리지 않았으면 단추는 꺼 두고, 올려야만 켜지게."

  · 어디에 두나 — 내 구글 계정의 **앱 전용 공간**(appDataFolder, 드라이브 목록에 안 보인다)에 bizcard.png
    하나. 다른 PC 에서 같은 계정으로 로그인하면 따라온다. 이 PC 에는 계정 폴더에 사본(bizcard.png)을 둔다.
  · 언제 읽나 — 켜자마자 이 PC 사본을 메모리(QImage)로 읽어 둔다(단추를 누르면 바로 복사 — 통신 없음).
    계정이 확인되면 뒤에서 계정 것과 맞춘다(다른 PC 에서 바꿨으면 받아 오고, 못 올린 것은 올린다).
  · 크기 — 긴 변 1600px 로 줄여 PNG 로 둔다(카톡에 붙여도 충분히 선명하고 가볍다).

맞추는 규칙(bizcard.json 에 적어 둔다 — md5: 이 PC 사본, synced: 마지막으로 계정과 같았던 md5,
pending: 'upload' / 'delete' — 올리거나 지우다 못 한 것):
  · pending 이 있으면 그것부터 한다.
  · 계정에 없고 이 PC 에 있다: 전에 맞춘 적 있으면(synced == md5) 다른 PC 에서 지운 것 → 이 PC 도 지운다.
    맞춘 적 없으면 → 올린다.
  · 계정 것과 이 PC 것이 다르다 → 계정 것을 받는다(다른 PC 에서 바꿨다).
"""

from __future__ import annotations

import hashlib
import json
import os
import threading

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMimeData, QObject, Qt, Signal
from PySide6.QtGui import QGuiApplication, QImage

from . import config, google_client

REMOTE_NAME = "bizcard.png"
MAX_SIDE = 1600


def _local_path():
    return config.data_dir() / "bizcard.png"


def _meta_path():
    return config.data_dir() / "bizcard.json"


def _md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest() if data else ""


def to_png(img: QImage) -> bytes:
    """긴 변 MAX_SIDE 로 줄여 PNG 바이트로."""
    if img.width() > MAX_SIDE or img.height() > MAX_SIDE:
        img = img.scaled(MAX_SIDE, MAX_SIDE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    buf = QByteArray()
    io = QBuffer(buf)
    io.open(QIODevice.WriteOnly)
    img.save(io, "PNG")
    io.close()
    return bytes(buf.data())


class BizCard(QObject):
    """명함 사진 한 장 — 메모리에 들고 있다가 바로 클립보드로."""

    changed = Signal()                  # 생겼다 · 바뀌었다 · 없어졌다
    _remote = Signal(object, str)       # (받은 바이트 또는 None, 할 일) — 뒤 작업 → 화면 쪽

    def __init__(self, parent=None):
        super().__init__(parent)
        self._img: QImage | None = None
        self._png = b""
        self._lock = threading.Lock()
        self._busy = False
        self._again = None
        self._remote.connect(self._on_remote)

    # ---- 읽기 ----
    def load_local(self) -> None:
        """이 PC 사본을 메모리로(켤 때 · 계정이 바뀔 때). 통신 없음."""
        data = b""
        try:
            p = _local_path()
            if p.is_file():
                data = p.read_bytes()
        except OSError:
            data = b""
        self._set(data)

    def _set(self, data: bytes) -> None:
        img = QImage.fromData(data) if data else QImage()
        if img.isNull():
            self._img, self._png = None, b""
        else:
            self._img, self._png = img, data
        self.changed.emit()

    def has(self) -> bool:
        return self._img is not None

    def image(self):
        return self._img

    # ---- 복사 ----
    def copy(self) -> bool:
        """클립보드에 명함 그림 — 카톡 대화창에 Ctrl+V. 없으면 False."""
        if self._img is None:
            return False
        md = QMimeData()
        md.setImageData(self._img)
        md.setData("image/png", QByteArray(self._png))
        QGuiApplication.clipboard().setMimeData(md)
        return True

    # ---- 바꾸기 ----
    def set_image(self, img: QImage, auth=None) -> str:
        """새 명함 — 이 PC 사본을 바꾸고 계정에 올린다(뒤에서). 오류면 그 글, 되면 ""."""
        if img is None or img.isNull():
            return "그림을 읽지 못했습니다(png · jpg 를 골라 주세요)."
        data = to_png(img)
        try:
            self._write_local(data)
        except OSError as e:
            return f"이 PC 에 저장하지 못했습니다: {e}"
        self._save_meta(md5=_md5(data), pending="upload")
        self._set(data)
        self.sync_async(auth)
        return ""

    def remove(self, auth=None) -> None:
        """명함을 뺀다 — 이 PC 사본과 계정 것 모두."""
        try:
            _local_path().unlink(missing_ok=True)
        except OSError:
            pass
        self._save_meta(md5="", pending="delete")
        self._set(b"")
        self.sync_async(auth)

    # ---- 계정과 맞추기 ----
    def sync_async(self, auth) -> None:
        if auth is None or not auth.is_connected():
            return
        with self._lock:
            if self._busy:
                self._again = auth
                return
            self._busy = True
            self._again = None
        threading.Thread(target=self._sync, args=(auth,), daemon=True).start()

    def _sync(self, auth) -> None:
        got, what = None, ""
        try:
            got, what = self.sync_once(auth)
        except Exception:
            got, what = None, ""
        self._remote.emit(got, what)

    def sync_once(self, auth):
        """계정과 한 번 맞춘다(뒤 작업) → (새로 받은 바이트 또는 None, 'got'/'gone'/'')."""
        meta = self._load_meta()
        local = b""
        try:
            p = _local_path()
            if p.is_file():
                local = p.read_bytes()
        except OSError:
            local = b""
        lmd5 = _md5(local)
        pend = meta.get("pending", "")
        remote = google_client.drive_find_meta(auth, REMOTE_NAME)
        if pend == "delete":
            if remote:
                google_client.drive_delete(auth, remote["id"])
            self._save_meta(md5="", synced="", pending="")
            return None, ""
        if pend == "upload" and local:
            google_client.drive_write_bytes(auth, REMOTE_NAME, local, "image/png")
            self._save_meta(md5=lmd5, synced=lmd5, pending="")
            return None, ""
        if not remote:
            if local and meta.get("synced") == lmd5:
                # 다른 PC 에서 지웠다
                _local_path().unlink(missing_ok=True)
                self._save_meta(md5="", synced="", pending="")
                return b"", "gone"
            if local:
                google_client.drive_write_bytes(auth, REMOTE_NAME, local, "image/png")
                self._save_meta(md5=lmd5, synced=lmd5, pending="")
            return None, ""
        rmd5 = str(remote.get("md5Checksum") or "")
        if rmd5 and rmd5 == lmd5:
            if meta.get("synced") != lmd5:
                self._save_meta(md5=lmd5, synced=lmd5, pending="")
            return None, ""
        data = google_client.drive_read_bytes(auth, remote["id"])
        if not data or QImage.fromData(data).isNull():
            return None, ""
        self._write_local(data)
        dmd5 = _md5(data)
        self._save_meta(md5=dmd5, synced=rmd5 or dmd5, pending="")
        return data, "got"

    def _on_remote(self, data, what: str) -> None:
        with self._lock:
            self._busy = False
            again = self._again
            self._again = None
        if what == "got" and data:
            self._set(data)
        elif what == "gone":
            self._set(b"")
        if again is not None:
            self.sync_async(again)

    # ---- 파일 ----
    @staticmethod
    def _write_local(data: bytes) -> None:
        p = _local_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, p)

    @staticmethod
    def _load_meta() -> dict:
        try:
            o = json.loads(_meta_path().read_text(encoding="utf-8"))
            return o if isinstance(o, dict) else {}
        except Exception:
            return {}

    def _save_meta(self, **kw) -> None:
        o = self._load_meta()
        o.update(kw)
        try:
            _meta_path().write_text(json.dumps(o), encoding="utf-8")
        except OSError:
            pass
