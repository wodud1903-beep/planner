"""업데이트 뒤 'Failed to remove temporary directory … _MEI…' 경고와 함께 안 켜지던 것(v1.26.2).

한 파일 exe 가 풀어 놓은 임시 폴더 정보(_PYI_… 환경 변수)가 교체 배치 → 새 판으로 넘어가면
새 판이 끝나는 옛 판의 임시 폴더를 물려받아 쓴다. 배치에는 깨끗한 환경을 넘긴다.
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
import inspect
import os
import sys
import tempfile

os.environ["APPDATA"] = tempfile.mkdtemp()
from planner import updater  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


mei = tempfile.mkdtemp(prefix="_MEI")
sys._MEIPASS = mei
os.environ.update({
    "_PYI_APPLICATION_HOME_DIR": mei, "_PYI_ARCHIVE_FILE": "/x/일정관리기.exe",
    "_PYI_PARENT_PROCESS_LEVEL": "1", "_MEIPASS2": mei,
    "QT_PLUGIN_PATH": os.path.join(mei, "PySide6", "plugins"),
    "PATH": os.pathsep.join([os.path.join(mei, "PySide6"), "/usr/bin", "/bin"]),
    "USERPROFILE": "/home/이재영",
})
env = updater.clean_env()
print("[1] 배치에 넘기는 환경")
ok("_PYI_ · _MEIPASS 변수를 뺀다", not [k for k in env if k.startswith(("_PYI_", "_MEIPASS"))],
   [k for k in env if k.startswith("_")])
ok("새로 풀라고 알린다(PYINSTALLER_RESET_ENVIRONMENT=1)", env.get("PYINSTALLER_RESET_ENVIRONMENT") == "1")
ok("옛 임시 폴더를 가리키는 값(QT_PLUGIN_PATH)은 뺀다", "QT_PLUGIN_PATH" not in env)
ok("PATH 에서 옛 임시 폴더만 뺀다", env["PATH"].split(os.pathsep) == ["/usr/bin", "/bin"], env["PATH"])
ok("다른 값은 그대로(한글 경로 포함)", env.get("USERPROFILE") == "/home/이재영")
ok("지금 프로그램의 환경은 건드리지 않는다", "_PYI_ARCHIVE_FILE" in os.environ)

print("[2] 배치를 그 환경으로 돌린다")
src = inspect.getsource(updater.apply_and_restart)
ok("배치에 clean_env 를 넘긴다", "env=clean_env()" in src)
ok("exe 폴더에서 돌린다", "cwd=tdir" in src)
scr = updater.update_script("S", r"C:\a\일정관리기.exe", r"C:\a\일정관리기.exe.old", "L", 1, 2, "ST")
ok("배치 안에서도 새로 풀라고 알린다", 'set "PYINSTALLER_RESET_ENVIRONMENT=1"' in scr)

print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
