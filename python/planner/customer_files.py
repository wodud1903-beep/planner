"""'고객정보' 탭이 읽는 자료 창고.

두 가지 창고를 같은 모양으로 다룬다.

  LocalSource  — 구글 드라이브 데스크톱이 PC 에 내려받아 둔 폴더를 그냥 읽는다.
                 권한도 심사도 필요 없고 오프라인에서도 열린다. 기본값.
  DriveSource  — 구글 드라이브를 API 로 직접 조회한다. 드라이브 데스크톱이
                 없는 PC 에서도 되지만 drive.readonly 권한이 필요하다.
                 이 권한은 구글이 'restricted' 로 묶어 두어서, 배포하려면
                 앱 인증과 매년 유료 보안심사를 통과해야 한다.
                 그래서 기본으로 켜지 않는다 — 설정에서 켠 사람만 쓴다.

폴더를 먼저 보여 주고 그 안의 파일을 보여 주는 식이 아니라, 창고 전체를 한 번
훑어 두고(scan) 그 목록에서 찾는다. 고객 이름으로 찾을 때 폴더를 하나씩 열어
볼 이유가 없기 때문이다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import hangul

# 보여 줄 파일 종류. 그 외(엑셀·한글 문서 등)도 목록에는 나오지만
# 미리보기는 안 되고 '연결 프로그램으로 열기' 만 된다.
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
PDF_EXT = {".pdf"}
VIEWABLE_EXT = IMAGE_EXT | PDF_EXT

# 한 번에 너무 많이 훑어 창이 멈추지 않도록 하는 상한.
MAX_FILES = 20000
MAX_DEPTH = 8

# 훑지 않는 폴더 — 드라이브 데스크톱·윈도가 만드는 것들
SKIP_DIRS = {".tmp.drivedownload", ".tmp.driveupload", ".git",
             "$RECYCLE.BIN", "System Volume Information", "__pycache__"}


@dataclass
class Node:
    """파일 하나(또는 폴더 하나)."""
    name: str
    is_dir: bool
    folder: str = ""              # 보여 줄 상위 폴더 경로(창고 기준 상대경로)
    size: int = 0
    mtime: Optional[datetime] = None
    key: str = ""                 # 로컬이면 절대경로, 드라이브면 file id
    mime: str = ""
    source: str = "local"

    @property
    def ext(self) -> str:
        return os.path.splitext(self.name)[1].lower()

    @property
    def is_image(self) -> bool:
        return (not self.is_dir) and (
            self.ext in IMAGE_EXT or self.mime.startswith("image/"))

    @property
    def is_pdf(self) -> bool:
        return (not self.is_dir) and (
            self.ext in PDF_EXT or self.mime == "application/pdf")

    @property
    def viewable(self) -> bool:
        return self.is_image or self.is_pdf

    @property
    def where(self) -> str:
        """목록에 보여 줄 위치. 창고 바로 밑이면 빈 값."""
        return self.folder

    def size_text(self) -> str:
        if self.is_dir:
            return ""
        n = float(self.size)
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024 or unit == "GB":
                return f"{n:,.0f} {unit}" if unit == "B" else f"{n:,.1f} {unit}"
            n /= 1024
        return ""

    def date_text(self) -> str:
        return f"{self.mtime:%Y-%m-%d}" if self.mtime else ""


def search(nodes: list, query: str) -> list:
    """폴더명·파일명으로 거른다. 초성('ㄱㅅㅎ')도 걸린다.

    폴더 안에 든 파일은 그 폴더 이름으로도 찾히게 한다 — '김상현' 으로 찾으면
    '김상현' 폴더 안의 계약서.pdf 도 나와야 쓸모가 있다.
    """
    q = (query or "").strip()
    if not q:
        return list(nodes)
    out = []
    for n in nodes:
        hay = n.name if n.is_dir else f"{n.folder} {n.name}"
        if hangul.matches(hay, q):
            out.append(n)
    return out


def sort_nodes(nodes: list) -> list:
    """폴더 먼저, 그 다음 최근 파일부터."""
    return sorted(
        nodes,
        key=lambda n: (not n.is_dir,
                       -(n.mtime.timestamp() if n.mtime else 0),
                       n.name.lower()))


# ---------------------------------------------------------------------------
# 로컬 폴더 (구글 드라이브 데스크톱이 내려받아 둔 그 폴더)
# ---------------------------------------------------------------------------
class LocalSource:
    kind = "local"
    label = "로컬 폴더"

    def __init__(self, root: str):
        self.root = (root or "").strip()

    def available(self) -> bool:
        return bool(self.root) and Path(self.root).is_dir()

    def why_not(self) -> str:
        if not self.root:
            return "폴더가 지정되지 않았습니다."
        p = Path(self.root)
        if not p.exists():
            return f"폴더를 찾을 수 없습니다:\n{self.root}"
        if not p.is_dir():
            return f"폴더가 아닙니다:\n{self.root}"
        return ""

    def scan(self, limit: int = MAX_FILES) -> list:
        """창고 전체를 훑어 Node 목록을 만든다."""
        root = Path(self.root)
        out: list = []
        if not root.is_dir():
            return out
        base = str(root)
        for dirpath, dirnames, filenames in os.walk(base):
            # 건너뛸 폴더는 내려가지도 않는다
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS
                           and not d.startswith(".")]
            rel = os.path.relpath(dirpath, base)
            depth = 0 if rel == "." else rel.count(os.sep) + 1
            if depth > MAX_DEPTH:
                dirnames[:] = []
                continue
            shown = "" if rel == "." else rel.replace("\\", "/")
            for d in dirnames:
                out.append(Node(name=d, is_dir=True, folder=shown,
                                key=os.path.join(dirpath, d),
                                mtime=_mtime(os.path.join(dirpath, d)),
                                source=self.kind))
            for f in filenames:
                if f.startswith("~$") or f.startswith("."):
                    continue
                full = os.path.join(dirpath, f)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                out.append(Node(name=f, is_dir=False, folder=shown,
                                size=st.st_size,
                                mtime=datetime.fromtimestamp(st.st_mtime),
                                key=full, source=self.kind))
                if len(out) >= limit:
                    return out
        return out

    def read_bytes(self, node: Node) -> bytes:
        with open(node.key, "rb") as fp:
            return fp.read()

    def local_path(self, node: Node) -> str:
        """연결 프로그램으로 열 때 쓸 실제 경로."""
        return node.key


def _mtime(path: str):
    try:
        return datetime.fromtimestamp(os.stat(path).st_mtime)
    except OSError:
        return None


# ---------------------------------------------------------------------------
# 구글 드라이브 API
# ---------------------------------------------------------------------------
class DriveSource:
    kind = "drive"
    label = "구글 드라이브"

    def __init__(self, auth, folder: str = ""):
        self.auth = auth
        self.folder = (folder or "").strip()   # 폴더 이름 또는 폴더 id

    def available(self) -> bool:
        from . import config
        return bool(self.auth) and self.auth.is_connected() \
            and self.auth.has_scope(config.SCOPE_DRIVE_READ)

    def why_not(self) -> str:
        from . import config
        if not self.auth or not self.auth.is_connected():
            return "구글에 로그인되어 있지 않습니다."
        if not self.auth.has_scope(config.SCOPE_DRIVE_READ):
            return ("드라이브 읽기 권한이 없습니다.\n"
                    "[설정] → '드라이브에서 직접 조회' 를 켜고 다시 로그인해 주세요.")
        if not self.folder:
            return "조회할 드라이브 폴더가 지정되지 않았습니다."
        return ""

    def scan(self, limit: int = MAX_FILES) -> list:
        from . import google_client
        root_id = google_client.drive_folder_id(self.auth, self.folder)
        if not root_id:
            return []
        out: list = []
        # 폴더를 하나씩 내려가며 훑는다 (넓이 우선 — 얕은 자료가 먼저 보인다)
        queue = [(root_id, "", 0)]
        while queue and len(out) < limit:
            fid, shown, depth = queue.pop(0)
            if depth > MAX_DEPTH:
                continue
            for it in google_client.drive_list_folder(self.auth, fid):
                is_dir = it.get("mimeType") == google_client.DRIVE_FOLDER_MIME
                node = Node(
                    name=it.get("name", ""), is_dir=is_dir, folder=shown,
                    size=int(it.get("size") or 0),
                    mtime=_parse_rfc3339(it.get("modifiedTime", "")),
                    key=it.get("id", ""), mime=it.get("mimeType", ""),
                    source=self.kind)
                out.append(node)
                if is_dir:
                    sub = f"{shown}/{node.name}" if shown else node.name
                    queue.append((node.key, sub, depth + 1))
                if len(out) >= limit:
                    break
        return out

    def read_bytes(self, node: Node) -> bytes:
        from . import google_client
        return google_client.drive_download(self.auth, node.key)

    def local_path(self, node: Node) -> str:
        return ""          # 드라이브 파일은 로컬 경로가 없다


def _parse_rfc3339(s: str):
    if not s:
        return None
    try:
        return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None


# ---------------------------------------------------------------------------
def pick_source(settings, auth):
    """설정을 보고 쓸 창고를 고른다 — 로컬이 먼저, 안 되면 드라이브.

    (창고, 안내문) 을 돌려준다. 둘 다 못 쓰면 (None, 이유).
    """
    local = LocalSource(getattr(settings, "files_dir", "") or "")
    if local.available():
        return local, ""
    drive = DriveSource(auth, getattr(settings, "files_drive_folder", "") or "")
    if getattr(settings, "files_use_drive", False) and drive.available():
        return drive, ""
    # 못 쓰는 이유는 로컬 쪽을 먼저 알려 준다(그쪽이 기본이므로)
    why = local.why_not()
    if getattr(settings, "files_use_drive", False):
        why += "\n\n드라이브 조회도 쓸 수 없습니다 — " + drive.why_not()
    return None, why
