"""'Failed to remove temporary directory … _MEI…' 경고 막기(v1.28.1) — 지점장 PC, 업데이트 뒤.

한 파일 exe 는 '풀어 놓는 부모' 와 '도는 자식' 둘이다. 자식이 끝나면 부모가 임시 폴더를 지우는데,
백신 등이 파일을 잡고 있으면 15초(1초 × 15번) 다시 해 본 뒤 경고 창을 띄운다(부트로더 pyi_main.c).
  · 끝나기 직전(업데이트 · 종료 · 두 번째 실행) 부모를 먼저 끝낸다 — 지우기를 안 하니 경고도 없다
    (부모가 정말 이 exe 일 때만)
  · 남은 우리 임시 폴더(표시 파일 planner.ico)는 켜고 1분 뒤 · 두 번째 실행 뒤 조용히 지운다
  · 교체 배치의 강제 종료에서 /T(딸린 프로세스까지)를 뺐다 — 배치 자신이 옛 판의 딸린 프로세스였다
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))

import ctypes
import inspect
import os
import shutil
import sys
import tempfile
import time

os.environ["APPDATA"] = tempfile.mkdtemp()

from planner import updater  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


print("[1] 부모(풀어 놓는 쪽)를 먼저 끝낸다 — 정말 이 exe 일 때만")
ok("개발 실행(소스)이면 아무것도 안 한다", updater.release_bootloader() is False)


class _Fn:
    def __init__(self, impl):
        self.impl, self.restype, self.argtypes = impl, None, None

    def __call__(self, *a):
        return self.impl(*a)


class FakeK32:
    def __init__(self, parent_image, can_open=True):
        self.parent_image, self.can_open = parent_image, can_open
        self.terminated, self.closed, self.opened = [], [], []
        self.OpenProcess = _Fn(lambda acc, inh, pid: (self.opened.append(pid) or 77) if self.can_open else 0)

        def qimg(h, flags, buf, size):
            buf.value = self.parent_image
            return 1
        self.QueryFullProcessImageNameW = _Fn(qimg)
        self.TerminateProcess = _Fn(lambda h, code: self.terminated.append(h) or 1)
        self.CloseHandle = _Fn(lambda h: self.closed.append(h) or 1)


_frozen, _plat, _exe = updater.is_frozen, sys.platform, sys.executable
updater.is_frozen = lambda: True
sys.platform = "win32"
sys.executable = os.path.join(tempfile.gettempdir(), "일정관리기.exe")
FAKE = {}
ctypes.WinDLL = lambda name, use_last_error=False: FAKE["k"]
try:
    from ctypes import wintypes as _w  # noqa: F401  (리눅스에서도 들여올 수 있는지)
    can_test = True
except Exception as e:                       # 아주 옛 파이썬
    can_test = False
    print("   (wintypes 없음 — 윈도 부분 시험 건너뜀)", e)
if can_test:
    FAKE["k"] = FakeK32(sys.executable)
    ok("부모가 이 exe 면 끝낸다", updater.release_bootloader() is True and FAKE["k"].terminated == [77]
       and FAKE["k"].closed == [77] and FAKE["k"].opened == [os.getppid()])
    FAKE["k"] = FakeK32(sys.executable.upper())
    ok("경로 대소문자만 다르면 같은 exe", updater.release_bootloader() is True or sys.platform == "win32")
    FAKE["k"] = FakeK32(r"C:\Windows\explorer.exe")
    ok("부모가 다른 프로그램(탐색기 등)이면 건드리지 않는다", updater.release_bootloader() is False
       and FAKE["k"].terminated == [] and FAKE["k"].closed == [77])
    FAKE["k"] = FakeK32(sys.executable, can_open=False)
    ok("부모를 못 열면(이미 끝남 등) 그냥 넘어간다", updater.release_bootloader() is False)
sys.platform, sys.executable = _plat, _exe
del ctypes.WinDLL

print("[2] 남은 우리 임시 폴더를 지운다 — 지금 것 · 남의 것 · 막 생긴 것은 두고")
base = tempfile.mkdtemp()


def mk(name, marker=True, age=3600):
    p = os.path.join(base, name)
    os.makedirs(os.path.join(p, "PySide6"), exist_ok=True)
    with open(os.path.join(p, "PySide6", "Qt6Core.dll"), "wb") as f:
        f.write(b"x" * 100)
    if marker:
        open(os.path.join(p, updater.TEMP_MARKER), "wb").close()
    t = time.time() - age
    os.utime(p, (t, t))
    return p


cur = mk("_MEI00003ec02")
old1 = mk("_MEI00005a082")
old2 = mk("_MEI12345")
other = mk("_MEI99999", marker=False)                 # 다른 프로그램(PyInstaller)의 것
fresh = mk("_MEI55555", age=10)                       # 막 풀어 놓은 것(두 번째 실행이 아직 도는 중일 수 있다)
notmei = mk("planner_tmp")
sys._MEIPASS = cur
n = updater.cleanup_old_temp(min_age_sec=120)
ok("지난 실행의 우리 폴더 2개를 지운다", n == 2 and not os.path.exists(old1) and not os.path.exists(old2), n)
ok("지금 쓰는 폴더는 그대로", os.path.isdir(cur))
ok("다른 프로그램의 _MEI 폴더는 그대로(표시 파일 없음)", os.path.isdir(other))
ok("막 생긴 폴더는 그대로(조금 뒤 다시)", os.path.isdir(fresh))
ok("_MEI 가 아닌 폴더는 그대로", os.path.isdir(notmei))
ok("다시 해도 더 지울 것이 없다", updater.cleanup_old_temp(min_age_sec=120) == 0)
updater.is_frozen = lambda: False
ok("개발 실행이면 아무것도 안 지운다", updater.cleanup_old_temp(min_age_sec=0) == 0 and os.path.isdir(fresh))
updater.is_frozen = _frozen
del sys._MEIPASS
shutil.rmtree(base, ignore_errors=True)

print("[3] 끝나는 길마다 부모를 먼저 · 켤 때 · 두 번째 실행 뒤 정리")
from planner import app as _app  # noqa: E402
src = inspect.getsource(_app.main)
i2 = src.index("if not _take_over_after_update(reply):")
ok("두 번째 실행 — 끝나기 전에 부모를 끝낸다", src.index("updater.release_bootloader()", i2) < src.index("return 0", i2))
ok("보통 종료 — os._exit 전에", src.rindex("updater.release_bootloader()") < src.rindex("os._exit(rc)"))
ok("두 번째 실행을 받은 쪽이 몇 분 뒤 정리", "win.schedule_temp_cleanup(180)" in src)
mw = (_ROOT / "python" / "planner" / "main_window.py").read_text(encoding="utf-8")
seg = mw[mw.index('if res == "__applied__":'):mw.index("if err:", mw.index('if res == "__applied__":'))]
ok("업데이트로 끝날 때 — os._exit 전에", seg.index("updater.release_bootloader()") < seg.index("os._exit(0)"))
ok("켜고 1분 뒤 남은 폴더 정리", "self.schedule_temp_cleanup(60)" in mw)

print("[4] 교체 배치 — 강제 종료에 /T 를 쓰지 않는다(배치 자신까지 끝내지 않게)")
sc = updater.update_script("S", r"C:\a\일정관리기.exe", r"C:\a\일정관리기.exe.old", "L", 11, 22, "ST")
_kills = [ln for ln in sc.splitlines() if "taskkill" in ln and not ln.lstrip().lower().startswith("rem")]
ok("/T 없음", _kills and not any("/T" in ln for ln in _kills), _kills)
ok("옛 판과 부모를 끝내는 줄", "taskkill /F /PID %PID%" in sc and 'taskkill /F /PID %PPID%' in sc)

print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
