"""명함 사진 — 멘트복사 채널마다 [명함복사] 가 클립보드에 넣는 그림(v1.36 · 채널마다 따로 v1.36.1).

지점장 요청(v1.36): "각 캐피탈 단추에 명함 복사 — 미리 올려 둔 명함 사진을 클립보드에. 항상 딜레이 없이 바로
복사되도록 켜지면 먼저 불러와 두고. 명함을 안 올렸으면 단추는 꺼 두고, 올려야만 켜지게."
다시(v1.36.1): "각각 명함을 다르게 쓰고 싶다 — 지금은 명함 1개만 올리면 전체가 켜진다. 단추마다 다른 명함을."
→ **채널(캐피탈)마다 명함 한 장씩**. 그 채널에 올린 것이 있어야 그 채널의 [명함복사] 가 켜진다.

  · 어디에 두나 — 내 구글 계정의 **앱 전용 공간**(appDataFolder, 드라이브 목록에 안 보인다)에 채널마다
    bizcard_<열쇠>.png. 다른 PC 에서 같은 계정으로 로그인하면 따라온다. 이 PC 에는 계정 폴더의
    bizcards\\<열쇠>.png 에 사본, bizcards.json 에 맞춘 기록. 열쇠 = 채널 이름의 해시(이름을 바꾸면 옮긴다).
  · 언제 읽나 — 켜자마자(그리고 계정이 바뀔 때) 이 PC 사본을 모두 메모리(QImage)로 — 누르면 통신 없이 바로.
    계정이 확인되면 뒤에서 계정 것과 맞춘다.
  · 크기 — 긴 변 1600px 로 줄여 PNG.
  · v1.36.0 의 '모든 채널 한 장'(bizcard.png)은 더 쓰지 않는다(채널마다 다시 올린다).

채널마다 맞추는 규칙(기록: md5 이 PC 사본 · synced 마지막으로 계정과 같았던 md5 · pending 'upload'/'delete'):
  · pending 이 있으면 그것부터.
  · 계정에 없고 이 PC 에 있다: 전에 맞춘 적 있으면(synced == md5) 다른 PC 에서 뺀 것 → 이 PC 도 뺀다.
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

MAX_SIDE = 1600


def key_of(name: str) -> str:
    """채널 이름 → 파일 열쇠(이름에 쓸 수 없는 글자 걱정 없게 해시)."""
    return hashlib.sha1(str(name or "").strip().encode("utf-8")).hexdigest()[:16]


def remote_name(key: str) -> str:
    return f"bizcard_{key}.png"


def _dir():
    return config.data_dir() / "bizcards"


def _local_path(key: str):
    return _dir() / f"{key}.png"


def _meta_path():
    return config.data_dir() / "bizcards.json"


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


class BizCards(QObject):
    """채널마다 명함 사진 한 장 — 메모리에 들고 있다가 바로 클립보드로."""

    changed = Signal(str)               # 그 채널 이름("" = 여럿이 한꺼번에)
    _remote = Signal(object)            # 뒤 작업 결과 {열쇠: 바이트(b"" = 빠짐)} → 화면 쪽

    def __init__(self, parent=None):
        super().__init__(parent)
        self._imgs: dict = {}           # 열쇠 → (QImage, png 바이트)
        self._lock = threading.Lock()
        self._meta_lock = threading.RLock()
        self._busy = False
        self._again = None
        self._remote.connect(self._on_remote)

    # ---- 읽기 ----
    def load_local(self) -> None:
        """이 PC 사본을 모두 메모리로(켤 때 · 계정이 바뀔 때). 통신 없음."""
        self._imgs = {}
        try:
            files = list(_dir().glob("*.png")) if _dir().is_dir() else []
        except OSError:
            files = []
        for p in files:
            try:
                data = p.read_bytes()
            except OSError:
                continue
            img = QImage.fromData(data)
            if not img.isNull():
                self._imgs[p.stem] = (img, data)
        self.changed.emit("")

    def _put_mem(self, key: str, data: bytes) -> None:
        img = QImage.fromData(data) if data else QImage()
        if img.isNull():
            self._imgs.pop(key, None)
        else:
            self._imgs[key] = (img, data)

    def has(self, name: str) -> bool:
        return key_of(name) in self._imgs

    def image(self, name: str):
        got = self._imgs.get(key_of(name))
        return got[0] if got else None

    # ---- 복사 ----
    def copy(self, name: str) -> bool:
        """그 채널의 명함을 클립보드에 — 카톡 대화창에 Ctrl+V. 없으면 False."""
        got = self._imgs.get(key_of(name))
        if not got:
            return False
        img, png = got
        md = QMimeData()
        md.setImageData(img)
        md.setData("image/png", QByteArray(png))
        QGuiApplication.clipboard().setMimeData(md)
        return True

    # ---- 바꾸기 ----
    def set_image(self, name: str, img: QImage, auth=None) -> str:
        """그 채널의 새 명함 — 이 PC 사본을 바꾸고 계정에 올린다(뒤에서). 오류면 그 글, 되면 ""."""
        if img is None or img.isNull():
            return "그림을 읽지 못했습니다(png · jpg 를 골라 주세요)."
        key = key_of(name)
        data = to_png(img)
        try:
            self._write_local(key, data)
        except OSError as e:
            return f"이 PC 에 저장하지 못했습니다: {e}"
        self._save_meta(key, name=str(name).strip(), md5=_md5(data), pending="upload")
        self._put_mem(key, data)
        self.changed.emit(str(name))
        self.sync_async(auth)
        return ""

    def remove(self, name: str, auth=None) -> None:
        """그 채널의 명함을 뺀다 — 이 PC 사본과 계정 것 모두."""
        key = key_of(name)
        try:
            _local_path(key).unlink(missing_ok=True)
        except OSError:
            pass
        self._save_meta(key, md5="", pending="delete")
        self._put_mem(key, b"")
        self.changed.emit(str(name))
        self.sync_async(auth)

    def rename(self, old: str, new: str, auth=None) -> None:
        """채널 이름을 바꿨다 — 명함도 새 이름으로 옮긴다."""
        ok_, nk = key_of(old), key_of(new)
        if ok_ == nk or ok_ not in self._imgs:
            return
        img, data = self._imgs[ok_]
        try:
            self._write_local(nk, data)
        except OSError:
            return
        self._save_meta(nk, name=str(new).strip(), md5=_md5(data), pending="upload")
        self._put_mem(nk, data)
        self.remove(old, auth)
        self.changed.emit("")

    # ---- 계정과 맞추기 ----
    def sync_async(self, auth, names=None) -> None:
        if auth is None or not auth.is_connected():
            return
        with self._lock:
            if names is not None:
                self._names = list(names)
            if self._busy:
                self._again = auth
                return
            self._busy = True
            self._again = None
        threading.Thread(target=self._sync, args=(auth,), daemon=True).start()

    def _sync(self, auth) -> None:
        try:
            got = self.sync_once(auth, getattr(self, "_names", []))
        except Exception:
            got = {}
        self._remote.emit(got)

    def sync_once(self, auth, names=()) -> dict:
        """계정과 한 번 맞춘다(뒤 작업) → 이 PC 에서 바뀐 것 {열쇠: 새 바이트 또는 b""(빠짐)}."""
        out = {}
        keys = {key_of(n) for n in names or [] if str(n).strip()} | set(self._load_meta_all())
        try:
            keys |= {p.stem for p in _dir().glob("*.png")} if _dir().is_dir() else set()
        except OSError:
            pass
        for key in sorted(keys):
            try:
                r = self._sync_key(auth, key)
            except Exception:
                continue                      # 이 채널만 다음에 — 나머지는 계속
            if r is not None:
                out[key] = r
        return out

    def _sync_key(self, auth, key: str):
        meta = self._load_meta_all().get(key, {})
        p = _local_path(key)
        try:
            local = p.read_bytes() if p.is_file() else b""
        except OSError:
            local = b""
        lmd5 = _md5(local)
        pend = meta.get("pending", "")
        remote = google_client.drive_find_meta(auth, remote_name(key))
        if pend == "delete":
            if remote:
                google_client.drive_delete(auth, remote["id"])
            self._drop_meta(key)
            return None
        if pend == "upload" and local:
            google_client.drive_write_bytes(auth, remote_name(key), local, "image/png")
            self._save_meta(key, md5=lmd5, synced=lmd5, pending="")
            return None
        if not remote:
            if local and meta.get("synced") == lmd5:
                p.unlink(missing_ok=True)      # 다른 PC 에서 뺐다
                self._drop_meta(key)
                return b""
            if local:
                google_client.drive_write_bytes(auth, remote_name(key), local, "image/png")
                self._save_meta(key, md5=lmd5, synced=lmd5, pending="")
            return None
        rmd5 = str(remote.get("md5Checksum") or "")
        if rmd5 and rmd5 == lmd5:
            if meta.get("synced") != lmd5:
                self._save_meta(key, md5=lmd5, synced=lmd5, pending="")
            return None
        data = google_client.drive_read_bytes(auth, remote["id"])
        if not data or QImage.fromData(data).isNull():
            return None
        self._write_local(key, data)
        dmd5 = _md5(data)
        self._save_meta(key, md5=dmd5, synced=rmd5 or dmd5, pending="")
        return data

    def _on_remote(self, got) -> None:
        with self._lock:
            self._busy = False
            again = self._again
            self._again = None
        if got:
            for key, data in got.items():
                self._put_mem(key, data)
            self.changed.emit("")
        if again is not None:
            self.sync_async(again)

    # ---- 파일 ----
    @staticmethod
    def _write_local(key: str, data: bytes) -> None:
        p = _local_path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, p)

    def _load_meta_all(self) -> dict:
        with self._meta_lock:
            try:
                o = json.loads(_meta_path().read_text(encoding="utf-8"))
                return o if isinstance(o, dict) else {}
            except Exception:
                return {}

    def _write_meta_all(self, o: dict) -> None:
        try:
            _meta_path().parent.mkdir(parents=True, exist_ok=True)
            _meta_path().write_text(json.dumps(o, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def _save_meta(self, key: str, **kw) -> None:
        with self._meta_lock:
            o = self._load_meta_all()
            cur = o.get(key) if isinstance(o.get(key), dict) else {}
            cur.update(kw)
            o[key] = cur
            self._write_meta_all(o)

    def _drop_meta(self, key: str) -> None:
        with self._meta_lock:
            o = self._load_meta_all()
            o.pop(key, None)
            self._write_meta_all(o)
