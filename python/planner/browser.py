"""주소를 열 때 쓰는 브라우저 — 크롬을 먼저 찾는다.

윈도우 기본 브라우저가 엣지로 잡혀 있는 경우가 많아, 자료검색의 링크나
[시트 열기] 를 누르면 평소 쓰지 않는 브라우저가 떴다. 로그인 상태도 달라
매번 다시 로그인해야 했다.

그래서 **크롬이 깔려 있으면 크롬으로** 연다. 크롬을 못 찾으면 예전처럼
윈도우 기본 브라우저로 넘긴다(크롬이 없는 PC 에서도 링크는 열려야 한다).
"""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser

# 한 번 찾으면 기억해 둔다. 못 찾았으면 "" 를 기억해 매번 뒤지지 않는다.
_cached: str | None = None

# 설치 위치가 바뀌는 일이 거의 없는 표준 경로들
_WIN_PATHS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)
_MAC_PATHS = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",)
_NIX_NAMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")


def _from_registry() -> str:
    """윈도우 레지스트리에서 chrome.exe 경로를 읽는다. 못 찾으면 ""."""
    if sys.platform != "win32":
        return ""
    try:
        import winreg
    except Exception:
        return ""
    spots = (
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
        (winreg.HKEY_CURRENT_USER,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
    )
    for hive, key in spots:
        try:
            with winreg.OpenKey(hive, key) as k:
                path = winreg.QueryValueEx(k, "")[0]
            path = str(path).strip().strip('"')
            if path and os.path.exists(path):
                return path
        except Exception:
            continue
    return ""


def chrome_path() -> str:
    """크롬 실행파일 경로. 없으면 ""."""
    global _cached
    if _cached is not None:
        return _cached

    found = ""
    if sys.platform == "win32":
        found = _from_registry()
        if not found:
            spots = list(_WIN_PATHS)
            local = os.environ.get("LOCALAPPDATA")
            if local:          # 관리자 권한 없이 설치하면 여기에 깔린다
                spots.append(os.path.join(
                    local, r"Google\Chrome\Application\chrome.exe"))
            found = next((p for p in spots if os.path.exists(p)), "")
    elif sys.platform == "darwin":
        found = next((p for p in _MAC_PATHS if os.path.exists(p)), "")
    else:
        from shutil import which
        found = next((w for w in (which(n) for n in _NIX_NAMES) if w), "")

    _cached = found
    return found


def open_url(url: str) -> bool:
    """주소를 크롬으로 연다. 크롬이 없으면 기본 브라우저로. 열었으면 True.

    크롬 실행이 실패해도 링크는 열려야 하므로 반드시 기본 브라우저로 넘긴다.
    """
    u = (url or "").strip()
    if not u:
        return False
    exe = chrome_path()
    if exe:
        try:
            subprocess.Popen([exe, u], close_fds=True)
            return True
        except Exception:
            pass          # 크롬을 못 띄웠으면 아래 기본 브라우저로
    try:
        return bool(webbrowser.open(u))
    except Exception:
        return False
