"""PC 시작 시 자동 실행 — HKCU\\...\\Run 에 등록한다(윈도 전용, 관리자 권한 필요 없음).

부팅으로 켜질 때는 `/tray` 를 붙여 창 없이 트레이에서 조용히 시작한다 —
빠른검색 단축키를 쓰려고 켜 두는 프로그램이라서다.
exe 를 다른 폴더로 옮겨도 다음에 켤 때 등록된 경로를 저절로 고친다(refresh).
"""

from __future__ import annotations

import sys
from pathlib import Path

from . import config

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
TRAY_ARG = "/tray"


def command() -> str:
    """등록할 명령줄. 소스로 돌릴 때는 파이썬 + main.py 를 적는다."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" {TRAY_ARG}'
    main = Path(__file__).resolve().parents[1] / "main.py"
    return f'"{sys.executable}" "{main}" {TRAY_ARG}'


def current() -> str:
    """지금 등록된 명령줄(없으면 "")."""
    if sys.platform != "win32":
        return ""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY)
        try:
            return str(winreg.QueryValueEx(key, config.APP_ID)[0] or "")
        except FileNotFoundError:
            return ""
        finally:
            winreg.CloseKey(key)
    except Exception:
        return ""


def is_on() -> bool:
    return bool(current())


def set_on(enable: bool) -> bool:
    """켜거나 끈다. 됐으면 True(윈도가 아니면 False)."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
        try:
            if enable:
                winreg.SetValueEx(key, config.APP_ID, 0, winreg.REG_SZ, command())
            else:
                try:
                    winreg.DeleteValue(key, config.APP_ID)
                except FileNotFoundError:
                    pass
        finally:
            winreg.CloseKey(key)
        return True
    except Exception:
        return False


def refresh() -> None:
    """켜져 있는데 경로가 지금 exe 와 다르면(옮겼거나 이름을 바꿨으면) 고쳐 둔다."""
    cur = current()
    if cur and cur != command():
        set_on(True)
