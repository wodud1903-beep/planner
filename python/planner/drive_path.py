"""이 PC 의 구글 드라이브에서 '내 드라이브 \\ 고객정보' 를 스스로 찾아낸다.

PC 를 바꿀 때마다 [폴더 선택]을 다시 해 주던 일을 없애려는 것이다.

찾는 곳을 이 순서로 본다.
  1. 레지스트리 — 드라이브 데스크톱이 적어 두는 마운트 위치(HKCU\\Software\\Google\\DriveFS)
  2. G: — 기본 문자. 사무실·집 PC 둘 다 여기다.
  3. 나머지 드라이브 문자 — G 가 이미 쓰이고 있으면 다른 문자로 붙는다
  4. 홈 폴더 — 옛 '백업 및 동기화' 가 쓰던 ~\\Google Drive

⚠️ 찾은 경로를 **설정 파일에 적어 두지 않는다.** 설정은 PC 끼리 따라다니므로
   (sync), G: 로 붙은 PC 가 적어 둔 경로가 H: 인 PC 로 건너가면 오히려 더
   틀린다. 그래서 쓸 때마다 그 PC 에서 찾는다. 손으로 지정한 값이 있으면
   그쪽이 언제나 먼저다 — 자동으로 찾은 것이 사람이 정한 것을 덮으면 안 된다.
"""

from __future__ import annotations

import os
import time

# 드라이브 데스크톱이 만드는 내 드라이브 폴더 이름 (한국어/영어 윈도)
MY_DRIVE_NAMES = ("내 드라이브", "My Drive")
# 서류를 모아 두는 폴더 이름
CUSTOMER_DIR = "고객정보"

# 못 찾았을 때 화면마다 같은 말로 안내한다 (사장님이 정한 문구)
FIX_HINT = "내 드라이브 → 고객정보 폴더로 폴더명을 변경해주세요."

# 드라이브 문자를 훑는 순서. G 가 기본이고, 이미 쓰이고 있으면 그 뒤 문자로
# 붙는다. A·B 는 옛 플로피 자리라 건드리지 않는다(드라이브가 헛돌 수 있다).
_LETTERS = "GHIJKLMNOPQRSTUVWXYZDEFC"

# 같은 것을 1분에 한 번만 찾는다. 목록을 새로고침할 때마다 26개 문자를
# 두드리면 느려진다.
_TTL_SEC = 60
_cache: tuple = (0.0, None)


def invalidate() -> None:
    """찾아 둔 것을 버린다(설정을 바꿨거나 검사에서 쓴다)."""
    global _cache
    _cache = (0.0, None)


# ---------------------------------------------------------------- 찾을 곳
def _registry_mounts() -> list:
    """드라이브 데스크톱이 레지스트리에 적어 둔 마운트 위치.

    윈도가 아니거나 못 읽으면 빈 목록. 여기서 실패해도 아래 문자 훑기가 있다.
    """
    out = []
    try:
        import json
        import winreg                      # 윈도에만 있다
    except Exception:
        return out
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\DriveFS")
    except OSError:
        return out
    with key:
        for name in ("DefaultMountPoint", "MountPoint"):
            try:
                v, _t = winreg.QueryValueEx(key, name)
            except OSError:
                continue
            if isinstance(v, str) and v.strip():
                out.append(v.strip())
        # 계정별 설정은 JSON 한 덩어리로 들어 있다
        try:
            raw, _t = winreg.QueryValueEx(key, "PerAccountPreferences")
        except OSError:
            raw = ""
        try:
            data = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
        except ValueError:
            data = {}
        for item in (data.get("per_account_preferences") or []):
            v = (item.get("value") or {}).get("mount_point_path")
            if isinstance(v, str) and v.strip():
                out.append(v.strip())
    return out


def _letter_mounts() -> list:
    """드라이브 문자. G: 부터 본다."""
    return [c + ":\\" for c in _LETTERS]


def _home_mounts() -> list:
    """옛 '백업 및 동기화' 가 쓰던 홈 폴더 자리."""
    home = os.path.expanduser("~")
    return [os.path.join(home, n) for n in
            ("Google Drive", "GoogleDrive", "내 드라이브", "My Drive")]


def _bases() -> list:
    """찾아볼 곳 전부. 앞에 있을수록 먼저 본다.

    검사에서 이 함수를 갈아 끼운다 — 진짜 드라이브 문자를 두드리지 않으려고.
    """
    return _registry_mounts() + _letter_mounts() + _home_mounts()


def _isdir(p: str) -> bool:
    try:
        return bool(p) and os.path.isdir(p)
    except OSError:
        return False        # 네트워크 드라이브가 끊겨 있으면 여기로 온다


# ---------------------------------------------------------------- 찾기
def my_drive_roots() -> list:
    """이 PC 에서 '내 드라이브' 로 보이는 폴더들. 없으면 빈 목록."""
    out = []
    for base in _bases():
        if not _isdir(base):
            continue
        for nm in MY_DRIVE_NAMES:
            p = os.path.join(base, nm)
            if _isdir(p) and p not in out:
                out.append(p)
        # 내 드라이브를 **폴더째** 마운트해 둔 경우가 있다. 그때는 그 폴더가
        # 곧 내 드라이브다. 다만 아무 폴더나 집어 오지 않도록, 서류 폴더가
        # 실제로 그 안에 있을 때만 인정한다.
        if _isdir(os.path.join(base, CUSTOMER_DIR)) and base not in out:
            out.append(base)
    return out


def find(sub: str = CUSTOMER_DIR) -> str:
    """'내 드라이브 \\ 고객정보' 의 실제 경로. 못 찾으면 빈 문자열."""
    now = time.monotonic()
    when, got = _cache
    if got is not None and (now - when) < _TTL_SEC and got.get("sub") == sub:
        return got.get("path", "")
    path = ""
    for root in my_drive_roots():
        p = os.path.join(root, sub)
        if _isdir(p):
            path = p
            break
    globals()["_cache"] = (now, {"sub": sub, "path": path})
    return path


def detect(sub: str = CUSTOMER_DIR) -> tuple:
    """(찾은 경로, 못 찾은 이유). 찾았으면 이유는 빈 문자열."""
    p = find(sub)
    if p:
        return p, ""
    roots = my_drive_roots()
    if roots:
        return "", (f"구글 드라이브는 찾았지만 그 안에 '{sub}' 폴더가 없습니다.\n"
                    f"{roots[0]}\n" + FIX_HINT)
    return "", ("이 PC 에서 구글 드라이브(내 드라이브)를 찾지 못했습니다.\n"
                "구글 드라이브 데스크톱이 켜져 있는지 확인해 주세요.\n" + FIX_HINT)


def resolve(settings, sub: str = CUSTOMER_DIR) -> tuple:
    """쓸 폴더를 정한다 — (경로, 자동으로 찾았나, 못 찾은 이유).

    손으로 지정한 폴더가 **살아 있으면 언제나 그쪽**이다. 비어 있거나 이 PC 엔
    없는 경로(다른 PC 에서 지정한 것)일 때만 찾아 나선다.
    """
    manual = (getattr(settings, "files_dir", "") or "").strip()
    if manual and _isdir(manual):
        return manual, False, ""
    path, why = detect(sub)
    if path:
        return path, True, ""
    if manual:
        why = (f"지정해 두신 폴더가 이 PC 에는 없습니다:\n{manual}\n\n" + why)
    return "", False, why
