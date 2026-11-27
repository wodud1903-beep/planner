"""카카오톡 창 다루기 — 윈도 API(ctypes). A1Auto(kmacro Unit1.pas)의 저수준 함수를 그대로 옮겼다(v1.37).

엔진(kakao_macro)은 이 모듈의 함수만 부른다. 윈도가 아니면(리눅스 검사 등) NullWin — 창이 하나도 없고
키도 보내지 않는다. 검사(tools/verify/verify_kakao_macro.py)는 가짜 창·키 기록을 끼운다.

델파이 대응
  GetTopLevelWindow  → get_top_level_window      GetWindowTitle   → WinApi.window_text
  CleanKakaoTitle    → clean_kakao_title         IsKakaoWindowClass → is_kakao_window_class
  WindowPid          → WinApi.window_pid         IsDialogClass    → is_dialog_class
  SendKey / SendKeyCombo 의 keybd_event · MapVirtualKey → WinApi.key_event · WinApi.map_vk
  HotkeyTimer 의 GetAsyncKeyState → WinApi.async_key
"""

from __future__ import annotations

import sys

VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_DOWN = 0x28
VK_CONTROL = 0x11
VK_INSERT = 0x2D
VK_DELETE = 0x2E
VK_T = ord("T")
VK_V = ord("V")
KEYEVENTF_KEYUP = 0x0002
GA_ROOT = 2
GA_ROOTOWNER = 3

# 카카오톡 창 클래스 — 이 글자가 들어 있으면 카카오톡 창으로 본다(Pos 는 대소문자를 가린다)
KAKAO_CLASS_PARTS = ("EVA_Window", "Qt5", "QWidget")
DIALOG_CLASS = "#32770"          # 윈도 공용 대화상자(파일 열기 등)


class NullWin:
    """창도 키도 없는 자리 — 윈도가 아닐 때."""

    def foreground(self) -> int:
        return 0

    def class_name(self, h: int) -> str:
        return ""

    def window_text(self, h: int) -> str:
        return ""

    def ancestor(self, h: int, flag: int) -> int:
        return 0

    def last_active_popup(self, h: int) -> int:
        return 0

    def is_visible(self, h: int) -> bool:
        return False

    def window_pid(self, h: int) -> int:
        return 0

    def map_vk(self, vk: int) -> int:
        return 0

    def key_event(self, vk: int, scan: int, flags: int) -> None:
        pass

    def async_key(self, vk: int) -> int:
        return 0


class RealWin(NullWin):
    """진짜 윈도 API(user32)."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self._ct = ctypes
        u = ctypes.WinDLL("user32", use_last_error=True)
        u.GetForegroundWindow.restype = wintypes.HWND
        u.GetForegroundWindow.argtypes = ()
        u.GetClassNameW.restype = ctypes.c_int
        u.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
        u.GetWindowTextW.restype = ctypes.c_int
        u.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
        u.GetAncestor.restype = wintypes.HWND
        u.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
        u.GetLastActivePopup.restype = wintypes.HWND
        u.GetLastActivePopup.argtypes = (wintypes.HWND,)
        u.IsWindowVisible.restype = wintypes.BOOL
        u.IsWindowVisible.argtypes = (wintypes.HWND,)
        u.GetWindowThreadProcessId.restype = wintypes.DWORD
        u.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
        u.MapVirtualKeyW.restype = wintypes.UINT
        u.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
        u.keybd_event.restype = None
        u.keybd_event.argtypes = (wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t)
        u.GetAsyncKeyState.restype = ctypes.c_short
        u.GetAsyncKeyState.argtypes = (ctypes.c_int,)
        self._u = u
        self._wt = wintypes

    @staticmethod
    def _h(v) -> int:
        return int(v or 0)

    def foreground(self) -> int:
        return self._h(self._u.GetForegroundWindow())

    def class_name(self, h: int) -> str:
        if not h:
            return ""
        buf = self._ct.create_unicode_buffer(256)
        n = self._u.GetClassNameW(h, buf, 256)
        return buf.value if n > 0 else ""

    def window_text(self, h: int) -> str:
        if not h:
            return ""
        buf = self._ct.create_unicode_buffer(2048)
        n = self._u.GetWindowTextW(h, buf, 2048)
        return buf.value if n > 0 else ""

    def ancestor(self, h: int, flag: int) -> int:
        return self._h(self._u.GetAncestor(h, flag)) if h else 0

    def last_active_popup(self, h: int) -> int:
        return self._h(self._u.GetLastActivePopup(h)) if h else 0

    def is_visible(self, h: int) -> bool:
        return bool(self._u.IsWindowVisible(h)) if h else False

    def window_pid(self, h: int) -> int:
        if not h:
            return 0
        pid = self._wt.DWORD(0)
        self._u.GetWindowThreadProcessId(h, self._ct.byref(pid))
        return int(pid.value)

    def map_vk(self, vk: int) -> int:
        return int(self._u.MapVirtualKeyW(vk, 0))

    def key_event(self, vk: int, scan: int, flags: int) -> None:
        self._u.keybd_event(vk & 0xFF, scan & 0xFF, flags, 0)

    def async_key(self, vk: int) -> int:
        return int(self._u.GetAsyncKeyState(vk))


def default():
    """이 PC 에 맞는 것 — 윈도면 진짜, 아니면 NullWin."""
    if sys.platform == "win32":
        try:
            return RealWin()
        except Exception:
            return NullWin()
    return NullWin()


# ---------------------------------------------------------------------------
# A1Auto 의 창 판별 함수들(그대로)
# ---------------------------------------------------------------------------
def get_top_level_window(w, h: int) -> int:
    """GetTopLevelWindow — 소유자를 따라 올라간 맨 위 창(떠 있는 팝업이 있으면 그 팝업)."""
    owner = w.ancestor(h, GA_ROOTOWNER)
    if owner == 0:
        owner = w.ancestor(h, GA_ROOT)
    last_popup = w.last_active_popup(owner)
    if last_popup != 0 and w.is_visible(last_popup):
        return last_popup
    return owner


def clean_kakao_title(s: str) -> str:
    """CleanKakaoTitle — '[3] 홍길동 - 카카오톡' → '홍길동'. '입력 중...' 도 뺀다."""
    suf1, suf2 = " - KakaoTalk", " - 카카오톡"
    r = (s or "").strip()
    if r and r[0] == "[" and "]" in r:
        r = r[r.index("]") + 1:].strip()
    if r.lower().endswith(suf1.lower()):
        r = r[:len(r) - len(suf1)].strip()
    elif r.lower().endswith(suf2.lower()):
        r = r[:len(r) - len(suf2)].strip()
    return r.replace("입력 중...", "").strip()


def is_kakao_window_class(w, h: int) -> bool:
    """IsKakaoWindowClass — 창 클래스에 EVA_Window / Qt5 / QWidget 이 들어 있나."""
    if not h:
        return False
    cls = w.class_name(h)
    if not cls:
        return False
    return any(p in cls for p in KAKAO_CLASS_PARTS)


def is_dialog_class(w, h: int) -> bool:
    """IsDialogClass — 윈도 공용 대화상자(#32770 — 파일 열기 등)인가."""
    if not h:
        return False
    return w.class_name(h) == DIALOG_CLASS
