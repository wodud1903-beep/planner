"""'고객정보' 폴더에 파일을 넣고 빼는 일.

화면(Qt)과 떼어 놓아 따로 시험할 수 있게 했다. 여기서 하는 일은 전부 로컬
폴더에 대한 것이다 — 그 폴더는 구글 드라이브 데스크톱이 알아서 올려 준다.
드라이브를 API 로 직접 조회하는 모드는 읽기 전용이라 여기 오지 않는다.

지우는 것은 되돌릴 수 없으므로, 부르는 쪽에서 반드시 먼저 물어봐야 한다.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

# 윈도에서 파일 이름에 못 쓰는 글자
BAD_CHARS = r'\/:*?"<>|'
_BAD_RE = re.compile("[" + re.escape(BAD_CHARS) + "]")

# 윈도가 예약해 둔 이름 (CON.txt 같은 것도 안 된다)
RESERVED = {"CON", "PRN", "AUX", "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10))}


class OpError(Exception):
    """사용자에게 그대로 보여 줄 수 있는 말썽."""


def safe_name(name: str) -> str:
    """파일 이름으로 쓸 수 있게 다듬는다. 못 쓰면 OpError."""
    name = (name or "").strip().strip(".")
    if not name:
        raise OpError("이름이 비어 있습니다.")
    if _BAD_RE.search(name):
        raise OpError(f"이름에 다음 글자는 쓸 수 없습니다:  {BAD_CHARS}")
    stem = name.split(".")[0].upper()
    if stem in RESERVED:
        raise OpError(f"'{stem}' 은(는) 윈도가 쓰는 이름이라 쓸 수 없습니다.")
    if len(name) > 200:
        raise OpError("이름이 너무 깁니다.")
    return name


def unique_path(folder: str, name: str) -> str:
    """같은 이름이 있으면 '이름 (2).png' 처럼 비켜 준다.

    덮어쓰기는 하지 않는다 — 사무실에서 올린 서류를 말없이 지우면 안 된다.
    """
    base, ext = os.path.splitext(name)
    p = os.path.join(folder, name)
    i = 2
    while os.path.exists(p):
        p = os.path.join(folder, f"{base} ({i}){ext}")
        i += 1
    return p


def _inside(folder: str, path: str) -> bool:
    """path 가 folder 안에 있는가 (창고 밖을 건드리지 않게)."""
    try:
        a = os.path.normcase(os.path.abspath(folder))
        b = os.path.normcase(os.path.abspath(path))
        return b == a or b.startswith(a + os.sep)
    except Exception:
        return False


def delete(path: str, root: str) -> None:
    """파일이나 폴더를 지운다. 창고(root) 밖이면 거절한다."""
    if not _inside(root, path):
        raise OpError("이 폴더 밖은 지울 수 없습니다.")
    if os.path.normcase(os.path.abspath(path)) == os.path.normcase(
            os.path.abspath(root)):
        raise OpError("맨 위 폴더는 지울 수 없습니다.")
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
    except OSError as e:
        raise OpError(f"지우지 못했습니다: {e}") from e


def rename(path: str, new_name: str, root: str) -> str:
    """이름을 바꾸고 새 경로를 돌려준다."""
    if not _inside(root, path):
        raise OpError("이 폴더 밖은 바꿀 수 없습니다.")
    name = safe_name(new_name)
    folder = os.path.dirname(path)
    target = os.path.join(folder, name)
    if os.path.normcase(target) == os.path.normcase(path):
        return path                     # 그대로면 아무 일도 안 한다
    if os.path.exists(target):
        raise OpError(f"'{name}' 이(가) 이미 있습니다.")
    try:
        os.rename(path, target)
    except OSError as e:
        raise OpError(f"이름을 바꾸지 못했습니다: {e}") from e
    return target


def make_folder(parent: str, name: str) -> str:
    """새 폴더를 만들고 그 경로를 돌려준다."""
    n = safe_name(name)
    target = os.path.join(parent, n)
    if os.path.exists(target):
        raise OpError(f"'{n}' 이(가) 이미 있습니다.")
    try:
        os.makedirs(target)
    except OSError as e:
        raise OpError(f"폴더를 만들지 못했습니다: {e}") from e
    return target


def copy_in(sources: list, folder: str) -> tuple:
    """바깥에서 끌어다 놓은 파일·폴더를 이 폴더로 복사한다.

    (넣은 경로 목록, 안 된 것 설명 목록) 을 돌려준다. 하나가 실패해도 나머지는
    계속 넣는다 — 여러 장을 한꺼번에 끌어다 놓는 일이 흔하기 때문이다.
    """
    done, failed = [], []
    for src in sources:
        try:
            if not os.path.exists(src):
                failed.append(f"{os.path.basename(src)} — 찾을 수 없습니다")
                continue
            if _inside(src, folder):
                failed.append(f"{os.path.basename(src)} — 자기 안으로는 넣을 수 없습니다")
                continue
            name = os.path.basename(src.rstrip("\\/"))
            target = unique_path(folder, name)
            if os.path.isdir(src):
                shutil.copytree(src, target)
            else:
                shutil.copy2(src, target)
            done.append(target)
        except Exception as e:
            failed.append(f"{os.path.basename(src)} — {e}")
    return done, failed


def save_bytes(data: bytes, folder: str, name: str) -> str:
    """붙여넣은 그림 등을 파일로 저장하고 그 경로를 돌려준다."""
    n = safe_name(name)
    target = unique_path(folder, n)
    try:
        with open(target, "wb") as fp:
            fp.write(data)
    except OSError as e:
        raise OpError(f"저장하지 못했습니다: {e}") from e
    return target


def with_ext(name: str, ext: str) -> str:
    """확장자가 없으면 붙여 준다('신분증' → '신분증.png')."""
    name = (name or "").strip()
    if not name:
        return name
    if os.path.splitext(name)[1]:
        return name
    return name + ext


# ---------------------------------------------------------------------------
# 드라이브 주소
# ---------------------------------------------------------------------------
def drive_url(node) -> str:
    """드라이브에서 직접 조회한 항목의 주소. 아니면 빈 값."""
    if getattr(node, "source", "") != "drive" or not getattr(node, "key", ""):
        return ""
    if node.is_dir:
        return f"https://drive.google.com/drive/folders/{node.key}"
    return f"https://drive.google.com/file/d/{node.key}/view"


def drive_search_url(name: str) -> str:
    """로컬 폴더만 있을 때 쓰는 차선책 — 드라이브에서 그 이름을 찾아 주는 주소.

    로컬 폴더에는 드라이브가 매기는 파일 번호(id)가 없어서 바로 가는 주소를
    만들 수 없다. 대신 드라이브에서 그 이름으로 찾아 주는 주소를 준다.
    """
    from urllib.parse import quote
    return "https://drive.google.com/drive/search?q=" + quote(name or "")
