"""'고객정보' 탭이 읽는 자료 창고.

두 가지 창고를 같은 모양으로 다룬다.

  LocalSource  — 구글 드라이브 데스크톱이 PC 에 내려받아 둔 폴더를 그냥 읽는다.
                 권한도 심사도 필요 없고 오프라인에서도 열린다. 기본값.
  DriveSource  — 구글 드라이브를 API 로 직접 조회한다. 드라이브 데스크톱이
                 없는 PC 에서도 되지만 drive.readonly 권한이 필요하다.
                 이 권한은 구글이 'restricted' 로 묶어 두어서, 배포하려면
                 앱 인증과 매년 유료 보안심사를 통과해야 한다.
                 그래서 기본으로 켜지 않는다 — 설정에서 켠 사람만 쓴다.

읽는 방법이 두 가지다.

  children(node) — 그 폴더 '바로 밑' 만 읽는다. 화면은 이걸 쓴다. 드라이브
                   웹처럼 눌러서 한 겹씩 들어간다. 폴더가 아무리 커도 즉시 뜬다.
  scan()         — 창고 전체를 훑는다. 검색할 때만, 그것도 뒤에서 조용히 돈다.

예전엔 켤 때마다 scan() 으로 트리 전체를 훑고 그 목록을 통째로 보여 줬다.
드라이브 폴더가 크면 첫 화면이 나오기까지 한참 멈춰 있었다 — 그래서 화면용
읽기와 검색용 읽기를 갈라 놓았다.
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

# 검색용으로 훑는 개수 상한. 2만에서 10만으로 올렸다 — 서류가 아주 많은 분도
# 전부 걸리게 하려는 것이다(로컬 폴더 기준 2,800건 훑기가 16ms 라 10만도 1초
# 안쪽이고, 훑는 일은 어차피 뒤에서 돈다).
MAX_FILES = 100000
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
    is_root: bool = False         # 창고의 맨 위 폴더인가
    # 검색용으로 미리 다듬어 둔 글자(hangul.prepare). 한 번 만들고 계속 쓴다.
    # 속을 빠르게 보려고 들고 있는 것일 뿐이니, 견주거나 찍을 때는 빼 둔다.
    _hay: Optional[tuple] = field(default=None, compare=False, repr=False)

    def search_text(self) -> str:
        """이 항목을 찾을 때 들여다보는 글자.

        폴더는 제 이름만, 파일은 '들어 있는 폴더 + 제 이름'. 폴더 이름으로도
        그 안의 파일이 찾히게 하려는 것이다 — '김상현' 으로 찾으면 '김상현'
        폴더 안의 계약서.pdf 도 나와야 쓸모가 있다.
        """
        return self.name if self.is_dir else f"{self.folder} {self.name}"

    def haystack(self) -> tuple:
        """검색용으로 다듬어 둔 글자. 없으면 이때 만들어 두고 계속 쓴다."""
        if self._hay is None:
            self._hay = hangul.prepare(self.search_text())
        return self._hay

    @property
    def rel(self) -> str:
        """창고 기준 이 항목의 경로. 맨 위 폴더는 빈 값."""
        if self.is_root:
            return ""
        return f"{self.folder}/{self.name}" if self.folder else self.name

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

    검색창에 한 자 칠 때마다 불리는 자리다. 그래서 항목마다 다듬어 둔 글자를
    쓰고(Node.haystack), 매번 초성을 다시 뽑지 않는다 — 그게 예전 느림의 주범
    이었다(파일 2만 개에 한 자당 147ms → 약 25ms).
    """
    q = (query or "").strip()
    if not q:
        return list(nodes)
    hit = hangul.matches_prepared
    return [n for n in nodes if hit(n.haystack(), q)]


def warm_haystacks(nodes: list) -> None:
    """검색용 글자를 미리 만들어 둔다 — 반드시 백그라운드에서 부른다.

    이 일을 첫 타자 때 화면 쪽에서 하면 그 한 자가 유독 느리다. 훑어 둘 때
    같이 해 두면 사용자는 기다리는 줄도 모른다.
    """
    for n in nodes:
        n.haystack()


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

    def scan(self, limit: int = MAX_FILES, on_batch=None) -> list:
        """창고 전체를 훑어 Node 목록을 만든다(검색용).

        os.walk + os.stat 로 하던 것을 os.scandir 로 바꿨다. walk 는 이름만 주므로
        파일마다 os.stat 을 또 불러야 했는데, 그게 파일 수만큼 늘어나는 추가
        호출이라 드라이브 폴더에서 특히 느렸다. scandir 이 주는 항목은 디렉터리를
        읽을 때 얻은 정보를 그대로 들고 있어 그 호출이 필요 없다.

        on_batch(지금까지 목록) 를 주면 폴더 하나를 끝낼 때마다 불러 준다.
        다 끝나기 전에도 찾은 것부터 보여 주려고 쓴다.
        """
        out: list = []
        if not Path(self.root).is_dir():
            return out
        stack = [(self.root, "", 0)]
        while stack:
            path, shown, depth = stack.pop()
            try:
                with os.scandir(path) as it:
                    entries = list(it)
            except OSError:
                continue
            for e in entries:
                if _skip_name(e.name):
                    continue
                try:
                    is_dir = e.is_dir()
                    st = e.stat()
                except OSError:
                    continue
                node = Node(
                    name=e.name, is_dir=is_dir, folder=shown,
                    size=0 if is_dir else st.st_size,
                    mtime=datetime.fromtimestamp(st.st_mtime),
                    key=e.path, source=self.kind)
                # 검색용 글자는 여기서 만들어 둔다. 여기는 백그라운드라 공짜지만,
                # 첫 타자 때 화면 쪽에서 하면 그 한 자가 유독 느리다.
                node.haystack()
                out.append(node)
                if is_dir and depth < MAX_DEPTH:
                    sub = f"{shown}/{e.name}" if shown else e.name
                    stack.append((e.path, sub, depth + 1))
                if len(out) >= limit:
                    return out
            if on_batch is not None:
                on_batch(out)
        return out

    # ---- 폴더 하나씩 (드라이브처럼 눌러서 들어간다) ----
    def root_node(self) -> Node:
        name = os.path.basename(self.root.rstrip("\\/")) or self.root
        return Node(name=name, is_dir=True, folder="", key=self.root,
                    source=self.kind, is_root=True)

    def _rel(self, key: str) -> str:
        try:
            r = os.path.relpath(key, self.root)
        except ValueError:
            return ""
        return "" if r == "." else r.replace("\\", "/")

    def children(self, node: Node) -> list:
        """그 폴더 '바로 밑' 만 읽는다.

        전체를 훑지 않으므로 폴더가 아무리 커도 즉시 나온다. 예전엔 켤 때마다
        트리 전체를 훑어서 드라이브 폴더가 크면 한참 멈춰 있었다.
        """
        out: list = []
        shown = self._rel(node.key)
        try:
            with os.scandir(node.key) as it:
                for e in it:
                    if _skip_name(e.name):
                        continue
                    try:
                        is_dir = e.is_dir()
                        st = e.stat()
                    except OSError:
                        continue
                    out.append(Node(
                        name=e.name, is_dir=is_dir, folder=shown,
                        size=0 if is_dir else st.st_size,
                        mtime=datetime.fromtimestamp(st.st_mtime),
                        key=e.path, source=self.kind))
        except OSError:
            return out
        return out

    def parent_of(self, node: Node):
        """상위 폴더. 창고 밖으로는 못 올라간다."""
        if os.path.normpath(node.key) == os.path.normpath(self.root):
            return None
        up = os.path.dirname(node.key.rstrip("\\/"))
        if len(os.path.normpath(up)) < len(os.path.normpath(self.root)):
            return None
        name = os.path.basename(up.rstrip("\\/")) or up
        return Node(name=name, is_dir=True, folder=self._rel(os.path.dirname(up)),
                    key=up, source=self.kind)

    def read_bytes(self, node: Node) -> bytes:
        with open(node.key, "rb") as fp:
            return fp.read()

    def local_path(self, node: Node) -> str:
        """연결 프로그램으로 열 때 쓸 실제 경로."""
        return node.key


def _skip_name(name: str) -> bool:
    """드라이브·오피스·윈도가 만드는 찌꺼기는 안 보여 준다."""
    return (name in SKIP_DIRS or name.startswith(".")
            or name.startswith("~$"))


def signature(nodes: list) -> tuple:
    """폴더 안이 바뀌었는지 싸게 견주기 위한 요약값.

    이름·크기·시각이 하나라도 달라지면 값이 달라진다. 이것만 견주면 화면을
    괜히 다시 그리지 않아도 되고, 바뀌었을 때만 조용히 갱신할 수 있다.
    """
    return tuple(sorted(
        (n.name, n.is_dir, n.size,
         int(n.mtime.timestamp()) if n.mtime else 0) for n in nodes))


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

    def scan(self, limit: int = MAX_FILES, on_batch=None) -> list:
        """창고 전체를 훑는다(검색용).

        ⚠️ on_batch 를 받는 것이 LocalSource.scan 과의 약속이다. 예전엔 이 쪽만
        빠져 있어서, 드라이브 조회 모드에서 검색을 켜면 첫 줄에서 TypeError 가
        나고 '검색 준비 실패' 만 뜬 채 영영 검색이 안 됐다.
        """
        from concurrent.futures import ThreadPoolExecutor

        from . import google_client
        root_id = google_client.drive_folder_id(self.auth, self.folder)
        if not root_id:
            return []
        out: list = []
        # 한 겹씩 내려가면서, 그 겹의 폴더들은 **한꺼번에** 물어본다.
        #
        # 예전엔 폴더 하나 묻고 답 기다리고 다음 폴더 묻기를 되풀이했다. 한 번
        # 왕복이 0.2~0.3초인데 고객 폴더가 400개면 그것만 100초다 — 검색이
        # 준비되기까지 한참 기다려야 했던 진짜 이유다. 기다리는 일(네트워크)은
        # 겹쳐서 해도 되므로 한 번에 여러 개를 묻는다.
        level = [(root_id, "")]
        depth = 0
        while level and depth <= MAX_DEPTH and len(out) < limit:
            with ThreadPoolExecutor(max_workers=self.FANOUT) as pool:
                answers = list(pool.map(
                    lambda fs: self._list_safe(fs[0]), level))
            nxt = []
            for (fid, shown), items in zip(level, answers):
                for it in items:
                    is_dir = it.get("mimeType") == google_client.DRIVE_FOLDER_MIME
                    node = Node(
                        name=it.get("name", ""), is_dir=is_dir, folder=shown,
                        size=int(it.get("size") or 0),
                        mtime=_parse_rfc3339(it.get("modifiedTime", "")),
                        key=it.get("id", ""), mime=it.get("mimeType", ""),
                        source=self.kind)
                    node.haystack()          # 검색용 글자도 여기서 만들어 둔다
                    out.append(node)
                    if is_dir:
                        sub = f"{shown}/{node.name}" if shown else node.name
                        nxt.append((node.key, sub))
                    if len(out) >= limit:
                        break
                if len(out) >= limit:
                    break
            # 한 겹을 끝낼 때마다 중간 결과를 넘긴다 — 네트워크를 타는 드라이브는
            # 다 끝나기까지 한참이라, 찾은 것부터 보여 줘야 한다.
            if on_batch is not None:
                on_batch(out)
            level = nxt
            depth += 1
        return out[:limit]

    # 한 겹에서 동시에 물어볼 폴더 수. 너무 올리면 구글이 속도를 제한한다
    # (429). 8개면 체감은 충분히 빨라지고 제한에는 걸리지 않는다.
    FANOUT = 8

    def _list_safe(self, folder_id: str) -> list:
        """폴더 하나 읽기 — 한 곳이 실패해도 전체를 멈추지 않는다.

        권한이 없는 폴더가 섞여 있을 수 있는데, 그 하나 때문에 검색 목록 전체를
        못 만들면 곤란하다.
        """
        from . import google_client
        try:
            return google_client.drive_list_folder(self.auth, folder_id)
        except Exception:
            return []

    # ---- 폴더 하나씩 ----
    def root_node(self) -> Node:
        from . import google_client
        fid = google_client.drive_folder_id(self.auth, self.folder)
        return Node(name=self.folder or "고객정보", is_dir=True, folder="",
                    key=fid, source=self.kind, is_root=True)

    def children(self, node: Node) -> list:
        from . import google_client
        if not node.key:
            return []
        shown = node.rel
        out = []
        for it in google_client.drive_list_folder(self.auth, node.key):
            is_dir = it.get("mimeType") == google_client.DRIVE_FOLDER_MIME
            out.append(Node(
                name=it.get("name", ""), is_dir=is_dir, folder=shown,
                size=int(it.get("size") or 0),
                mtime=_parse_rfc3339(it.get("modifiedTime", "")),
                key=it.get("id", ""), mime=it.get("mimeType", ""),
                source=self.kind))
        return out

    def parent_of(self, node: Node):
        # 드라이브는 부모를 되짚기보다 지나온 길을 기억해 두는 편이 싸다.
        # 화면(customer_files_tab)이 그 길을 들고 있으므로 여기서는 안 쓴다.
        return None

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
