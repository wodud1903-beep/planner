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
# 단축키마다 다른 번호를 준다. 같은 번호로 두 개를 등록하면 나중 것이
# 앞의 것을 밀어내 창 열기와 자료검색이 서로를 꺼 버린다.
ID_WINDOW = 0xB001      # 창 빠르게 열기
ID_KB = 0xB002          # 업무자료 빠른검색
_HOTKEY_ID = ID_WINDOW  # 구버전 이름(호환용)


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
    """등록한 단축키 번호별로 콜백을 갈라 부른다."""

    def __init__(self):
        super().__init__()
        self.callbacks: dict = {}          # {단축키 번호: 부를 함수}

    def nativeEventFilter(self, event_type, message):  # noqa: N802
        if sys.platform == "win32" and event_type == "windows_generic_MSG":
            try:
                import ctypes
                from ctypes import wintypes
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY:
                    cb = self.callbacks.get(int(msg.wParam))
                    if cb:
                        cb()
            except Exception:
                pass
        return False


class HotkeyManager:
    """설정에 맞춰 전역 단축키를 등록/해제한다.

    단축키를 여러 개 다룬다(창 열기 / 업무자료 빠른검색). 번호(id)로 구분하며,
    하나를 다시 등록해도 다른 것은 그대로 살아 있다.
    """

    def __init__(self, app, hwnd: int, callback: Callable[[], None] = None):
        self._app = app
        self._hwnd = int(hwnd)
        self._active: set = set()          # 지금 등록돼 있는 번호
        self._filter: Optional[_HotkeyFilter] = None
        if sys.platform == "win32":
            self._filter = _HotkeyFilter()
            app.installNativeEventFilter(self._filter)
        if callback is not None:
            self.set_callback(ID_WINDOW, callback)

    # ---- 콜백 등록 ----
    def set_callback(self, hid: int, callback: Callable[[], None]) -> None:
        if self._filter is not None:
            self._filter.callbacks[int(hid)] = callback

    # ---- 낱개 등록/해제 ----
    def register(self, hid: int, mods: int, key_name: str) -> bool:
        """하나를 (다시) 등록한다. 성공 여부 반환."""
        self.release(hid)
        if sys.platform != "win32" or mods == 0:
            return False               # 조합키 없이 단독 등록은 막는다
        try:
            import ctypes
            ok = ctypes.windll.user32.RegisterHotKey(
                self._hwnd, int(hid), mods, vk_from_name(key_name))
            if ok:
                self._active.add(int(hid))
            return bool(ok)
        except Exception:
            return False

    def release(self, hid: int = None):
        """번호 하나를 해제한다. 번호를 안 주면 전부 해제."""
        targets = list(self._active) if hid is None else [int(hid)]
        for t in targets:
            if t in self._active and sys.platform == "win32":
                try:
                    import ctypes
                    ctypes.windll.user32.UnregisterHotKey(self._hwnd, t)
                except Exception:
                    pass
            self._active.discard(t)

    def is_on(self, hid: int) -> bool:
        return int(hid) in self._active

    # ---- 설정에서 읽어 적용 ----
    @staticmethod
    def _mods_of(ctrl: bool, alt: bool, shift: bool) -> int:
        mods = 0
        if ctrl:
            mods |= MOD_CONTROL
        if alt:
            mods |= MOD_ALT
        if shift:
            mods |= MOD_SHIFT
        return mods

    def apply(self, settings) -> bool:
        """창 열기 단축키를 설정대로 재등록."""
        if not settings.hot_on:
            self.release(ID_WINDOW)
            return False
        return self.register(
            ID_WINDOW,
            self._mods_of(settings.hot_ctrl, settings.hot_alt, settings.hot_shift),
            settings.hot_key)

    def apply_kb(self, settings) -> bool:
        """업무자료 빠른검색 단축키를 설정대로 재등록."""
        if not getattr(settings, "kb_hot_on", False):
            self.release(ID_KB)
            return False
        return self.register(
            ID_KB,
            self._mods_of(getattr(settings, "kb_hot_ctrl", True),
                          getattr(settings, "kb_hot_alt", True),
                          getattr(settings, "kb_hot_shift", False)),
            getattr(settings, "kb_hot_key", "F"))
