"""전역 단축키 (Windows 전용, 델파이 uDash 의 RegisterHotKey 이식).

QAbstractNativeEventFilter 로 WM_HOTKEY 메시지를 받아 콜백을 부른다.
Windows 가 아니면 아무 것도 하지 않는다.
"""

from __future__ import annotations

import sys
from typing import Callable, Optional

from PySide6.QtCore import QAbstractNativeEventFilter

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
WM_HOTKEY = 0x0312
_HOTKEY_ID = 0xB001


def vk_from_name(name: str) -> int:
    """'A'~'Z' 또는 'F1'~'F12' → 가상키 코드."""
    s = (name or "A").strip().upper()
    if len(s) == 1 and "A" <= s <= "Z":
        return ord(s)
    if s.startswith("F"):
        try:
            n = int(s[1:])
            if 1 <= n <= 12:
                return 0x70 + (n - 1)  # VK_F1 = 0x70
        except ValueError:
            pass
    return ord("A")


class _HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback: Callable[[], None]):
        super().__init__()
        self._callback = callback

    def nativeEventFilter(self, event_type, message):  # noqa: N802
        if sys.platform == "win32" and event_type == "windows_generic_MSG":
            try:
                import ctypes
                from ctypes import wintypes
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY and msg.wParam == _HOTKEY_ID:
                    self._callback()
            except Exception:
                pass
        return False


class HotkeyManager:
    """설정에 맞춰 전역 단축키를 등록/해제한다."""

    def __init__(self, app, hwnd: int, callback: Callable[[], None]):
        self._app = app
        self._hwnd = int(hwnd)
        self._registered = False
        self._filter: Optional[_HotkeyFilter] = None
        if sys.platform == "win32":
            self._filter = _HotkeyFilter(callback)
            app.installNativeEventFilter(self._filter)

    def _mods(self, settings) -> int:
        mods = 0
        if settings.hot_ctrl:
            mods |= MOD_CONTROL
        if settings.hot_alt:
            mods |= MOD_ALT
        if settings.hot_shift:
            mods |= MOD_SHIFT
        return mods

    def apply(self, settings) -> bool:
        """설정대로 재등록. 성공 여부 반환(비Windows/조합없음/충돌 시 False)."""
        self.release()
        if sys.platform != "win32" or not settings.hot_on:
            return False
        mods = self._mods(settings)
        if mods == 0:  # 조합키 없이 단독 등록은 막는다
            return False
        try:
            import ctypes
            ok = ctypes.windll.user32.RegisterHotKey(
                self._hwnd, _HOTKEY_ID, mods, vk_from_name(settings.hot_key))
            self._registered = bool(ok)
            return self._registered
        except Exception:
            return False

    def release(self):
        if self._registered and sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.user32.UnregisterHotKey(self._hwnd, _HOTKEY_ID)
            except Exception:
                pass
        self._registered = False
