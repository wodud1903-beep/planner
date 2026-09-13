"""받은팩스 폴더를 지켜보는 일 — 화면(Qt)과 떼어 놓아 따로 시험할 수 있게 했다.

휴대폰 모바일팩스에서 받은 팩스를 '공유 → 드라이브 저장' 으로 넣으면, 구글 드라이브
데스크톱이 PC 의 그 폴더로 내려받는다. 여기서는 그 폴더를 잠깐씩 다시 읽어 **새로 생긴
파일**을 찾아낸다.

왜 폴링인가
-----------
QFileSystemWatcher 를 안 쓴다. 대상이 구글 드라이브 가상 파일시스템이라 변경 통지가
안 오는 경우가 있다. 폴더 하나 훑기는 싸서(수 ms) 10초에 한 번이면 부담이 없다.

이 모듈이 막아 주는 세 가지
---------------------------
1. **반쯤 내려온 파일** — 드라이브는 파일을 조금씩 내려받는다. 크기가 연속 두 번 같아야
   '다 왔다'로 본다. 안 그러면 깨진 PDF 를 열게 된다.
2. **켤 때마다 옛 팩스가 쏟아지는 것** — 폴더를 처음 지정한 때는 그때 있던 것을 전부
   '이미 봤음' 으로 표시한다.
3. **같은 팩스 두 번** — 본 것을 열쇠(이름+크기+시각)로 남긴다. 그 열쇠는 PC 사이에
   합집합으로 합쳐지므로(sync), 사무실에서 본 팩스가 집 PC 에서 다시 뜨지 않는다.
"""

from __future__ import annotations

import os
from datetime import datetime

from .customer_files import VIEWABLE_EXT, _skip_name

# 팩스로 들어올 수 있는 파일만 본다. 팩스는 PDF 아니면 TIFF 로 오는 일이 흔하다.
# (VIEWABLE_EXT 에 tif/tiff 가 포함돼 있어야 한다 — customer_files 참고)
FAX_EXT = set(VIEWABLE_EXT)


def scan(folder: str) -> dict:
    """폴더 바로 밑의 팩스 파일 목록. 이름 → (크기, 수정시각).

    하위 폴더는 보지 않는다 — 받은팩스는 한 겹이고, 깊이 들어가면 괜히 느려진다.
    """
    out: dict = {}
    if not folder:
        return out
    try:
        with os.scandir(folder) as it:
            for e in it:
                if _skip_name(e.name):
                    continue            # 드라이브 임시파일·숨김·오피스 찌꺼기
                if os.path.splitext(e.name)[1].lower() not in FAX_EXT:
                    continue
                try:
                    if e.is_dir():
                        continue
                    st = e.stat()
                except OSError:
                    continue
                out[e.name] = (st.st_size, st.st_mtime)
    except OSError:
        return out                      # 폴더가 없거나 권한이 없으면 조용히 빈 목록
    return out


def key_of(name: str, info: tuple) -> str:
    """'이 팩스를 이미 봤나' 를 가리는 열쇠.

    이름만으로는 안 된다 — 같은 이름으로 다른 팩스가 올 수 있다(모바일팩스가 날짜만으로
    이름을 붙이는 경우). 크기와 시각을 함께 넣어 서로 다른 팩스를 구분한다.
    시각은 초 단위로 자른다 — 드라이브가 내려받으며 소수점이 미세하게 달라질 수 있다.
    """
    size, mtime = info
    return f"{name}\x00{int(size)}\x00{int(mtime)}"


def is_settled(prev: dict, cur: dict, name: str) -> bool:
    """다 내려왔는가 — 크기가 직전과 같아야 한다.

    직전 기록에 없으면(이번에 처음 보였으면) 아직 판단하지 않는다. 다음 차례에 크기가
    그대로면 그때 '다 왔다' 로 본다. 그래서 알람이 한 박자 늦지만, 깨진 파일을 여는
    것보다 낫다.
    """
    if name not in cur:
        return False
    if name not in prev:
        return False
    return prev[name][0] == cur[name][0] and cur[name][0] > 0


def new_faxes(prev: dict, cur: dict, seen: set) -> list:
    """알릴 만한 새 팩스 이름 목록 — 다 내려왔고, 아직 안 본 것.

    시각이 새것부터 오게 돌려준다.
    """
    out = []
    for name, info in cur.items():
        if not is_settled(prev, cur, name):
            continue
        if key_of(name, info) in seen:
            continue
        out.append(name)
    out.sort(key=lambda n: cur[n][1], reverse=True)
    return out


def mark_all_seen(cur: dict, seen: set) -> set:
    """지금 있는 것을 전부 '이미 봤음' 으로 — 폴더를 처음 지정했을 때 쓴다."""
    for name, info in cur.items():
        seen.add(key_of(name, info))
    return seen


def label(name: str, info: tuple) -> str:
    """알람에 보여 줄 한 줄."""
    size, mtime = info
    when = datetime.fromtimestamp(mtime).strftime("%m/%d %H:%M")
    kb = max(1, int(size) // 1024)
    return f"{name}  ({when} · {kb:,} KB)"


class FaxFolder:
    """폴더 하나를 지켜보는 상태. 화면 쪽에서 이걸 하나 들고 tick() 만 부른다."""

    def __init__(self, folder: str = "", seen=None):
        self.folder = folder or ""
        self.seen: set = set(seen or ())
        self.last: dict = {}
        self.primed = False        # 첫 훑기를 끝냈는가

    def set_folder(self, folder: str) -> None:
        """폴더가 바뀌면 처음부터 다시 — 새 폴더의 기존 파일로 알람하지 않는다."""
        folder = folder or ""
        if folder == self.folder:
            return
        self.folder = folder
        self.last = {}
        self.primed = False

    def tick(self) -> list:
        """한 번 훑는다. 알릴 새 팩스 [(이름, 정보)] 를 돌려준다.

        첫 훑기(primed 전)에는 아무것도 알리지 않고 지금 있는 것을 전부 봤음으로 표시한다.
        """
        cur = scan(self.folder)
        if not self.primed:
            self.last = cur
            mark_all_seen(cur, self.seen)
            self.primed = True
            return []
        names = new_faxes(self.last, cur, self.seen)
        got = [(n, cur[n]) for n in names]
        for n, info in got:
            self.seen.add(key_of(n, info))
        self.last = cur
        return got

    def recent(self, limit: int = 50) -> list:
        """최근 팩스 [(이름, 정보)] — 새 것부터. 보기 창 목록에 쓴다."""
        cur = scan(self.folder)
        items = sorted(cur.items(), key=lambda kv: kv[1][1], reverse=True)
        return items[:limit]

    def path_of(self, name: str) -> str:
        return os.path.join(self.folder, name) if self.folder and name else ""
