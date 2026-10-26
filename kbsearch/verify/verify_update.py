"""자동 업데이트 — kb-v 릴리스만 고르기, 받은 파일 확인, 같은 판 되풀이 막기, 업데이트 창.

일정관리기 릴리스(v1.x)와 한 저장소에 섞여 있어도 이 프로그램 것(kb-v)만 고르는지,
그리고 건너뛰기 단추가 없는지를 본다. 교체 배치는 일정관리기 것과 명령이 같은지 견준다
(그쪽 배치는 tools/verify/verify_update.py 가 실패 상황까지 돌려 본다).
"""
import pathlib as _pl
import sys as _sys

_HERE = _pl.Path(__file__).resolve().parent
_sys.path.insert(0, str(_HERE.parent))

import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import requests  # noqa: E402

from kbsearch import config, updater  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name
          + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


def rel(tag, draft=False, pre=False, assets=None):
    return {"tag_name": tag, "draft": draft, "prerelease": pre, "name": tag,
            "body": f"{tag} 달라진 점",
            "assets": assets if assets is not None else [
                {"name": config.UPDATE_ASSET_NAME, "label": "", "size": 2_000_000,
                 "url": f"https://api/{tag}", "browser_download_url": f"https://dl/{tag}"}]}


print("[1] 판 번호")
ok("kb-v 머리말", updater.parse_ver("kb-v1.2.3") == (1, 2, 3))
ok("v 머리말", updater.parse_ver("v1.2") == (1, 2, 0))
ok("일정관리기 태그와 섞여도 크기 비교", updater.parse_ver("kb-v1.10.0") > updater.parse_ver("kb-v1.9.9"))

print("[2] 릴리스 고르기")
mixed = [rel("v1.30.0"), rel("kb-v1.0.3", draft=True), rel("kb-v1.0.2", pre=True),
         rel("kb-v1.0.1"), rel("kb-v0.9.0"), rel("v1.21.1")]
ok("kb-v 중 가장 높은 정식판", updater.pick_release(mixed)["tag_name"] == "kb-v1.0.1")
ok("kb-v 가 없으면 None", updater.pick_release([rel("v1.30.0")]) is None)

print("[3] 자산 고르기")
a_name = {"name": config.UPDATE_ASSET_NAME}
a_label = {"name": "default.exe", "label": config.UPDATE_ASSET_NAME}
ok("이름", updater._pick_asset([{"name": "x.zip"}, a_name]) is a_name)
ok("라벨(한글 이름이 default.exe 로 바뀐 경우)", updater._pick_asset([a_label]) is a_label)
ok("exe 가 하나뿐이면 그것", updater._pick_asset([{"name": "a.exe"}])["name"] == "a.exe")
ok("exe 가 여럿이고 이름이 안 맞으면 안 받는다",
   updater._pick_asset([{"name": "a.exe"}, {"name": "일정관리기.exe"}]) is None)


class R:
    def __init__(self, code=200, body=None, chunks=(), headers=None):
        self.status_code = code
        self._body = body
        self._chunks = chunks
        self.headers = headers or {}

    def json(self):
        return self._body

    def iter_content(self, chunk_size=0):
        yield from self._chunks


def with_get(fn, func):
    old = updater.requests.get
    updater.requests.get = fn
    try:
        return func()
    finally:
        updater.requests.get = old


print("[4] 확인")
pages = {1: [rel(f"v1.{i}.0") for i in range(100)], 2: [rel("kb-v1.0.1")] + [rel("v0.1.0")] * 3}
seen = []


def fake_get(url, headers=None, params=None, timeout=None, **kw):
    seen.append(params.get("page"))
    return R(200, pages.get(params.get("page"), []))


info = with_get(fake_get, updater.check)
ok("일정관리기 릴리스가 한 쪽을 다 채워도 다음 쪽에서 찾는다", info and info["version"] == "1.0.1",
   seen)
ok("받을 주소·크기", info["download_url"] == "https://dl/kb-v1.0.1" and info["size"] == 2_000_000)
ok("달라진 점", "달라진 점" in info["notes"])
config.APP_VERSION, _keep = "1.0.1", config.APP_VERSION
ok("같은 판이면 None", with_get(lambda *a, **k: R(200, [rel("kb-v1.0.1")]), updater.check) is None)
config.APP_VERSION = _keep


def raises(func):
    try:
        func()
        return ""
    except updater.UpdateError as e:
        return str(e)


ok("403(요청 한도 등) → 확인 못 함", "403" in with_get(lambda *a, **k: R(403, {}),
                                                  lambda: raises(updater.check)))


def boom(*a, **k):
    raise requests.ConnectionError("no net")


ok("인터넷 없음 → 확인 못 함", "인터넷" in with_get(boom, lambda: raises(updater.check)))

print("[5] 받기 — 크기·지문 확인")
data = b"MZ" + os.urandom(1_200_000)
good = {"download_url": "https://dl/x", "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest()}
chunks = [data[i:i + 65536] for i in range(0, len(data), 65536)]
prog = []
path = with_get(lambda *a, **k: R(200, chunks=chunks),
                lambda: updater.download(good, lambda g, t: prog.append((g, t))))
ok("받음", open(path, "rb").read() == data)
ok("진행률", prog and prog[-1] == (len(data), len(data)))
os.remove(path)
ok("덜 받음 → 실패", "다 받지 못" in with_get(lambda *a, **k: R(200, chunks=chunks[:-1]),
                                         lambda: raises(lambda: updater.download(good))))
bad = dict(good, sha256="0" * 64)
ok("지문 다름 → 실패", "지문" in with_get(lambda *a, **k: R(200, chunks=chunks),
                                     lambda: raises(lambda: updater.download(bad))))
ok("너무 작음 → 실패", "작습니다" in with_get(
    lambda *a, **k: R(200, chunks=[b"x" * 10]),
    lambda: raises(lambda: updater.download({"download_url": "u"}))))

print("[6] 같은 판 되풀이 막기")
ok("시도 전", not updater.just_failed("1.0.1"))
updater.note_attempt("1.0.1")
ok("방금 시도했는데 그대로면 멈춘다", updater.just_failed("1.0.1"))
ok("다른 판은 상관없음", not updater.just_failed("1.0.2"))
st = json.loads(config.data_file(updater.STATE_FILE).read_text())
st["at"] = time.time() - updater.RETRY_GUARD_SEC - 5
config.data_file(updater.STATE_FILE).write_text(json.dumps(st))
ok("오래 전 시도면 다시 받는다", not updater.just_failed("1.0.1"))

print("[7] 교체 배치 — 일정관리기 것과 명령이 같다")
_sys.path.insert(0, str(_HERE.parents[1] / "python"))
from planner import updater as pupd  # noqa: E402


def cmds(s):
    return [ln.strip() for ln in s.splitlines() if ln.strip() and not ln.strip().lower().startswith("rem")]


args = (r"C:\a\_update_업무자료검색.exe", r"C:\a\업무자료검색.exe", r"C:\a\업무자료검색.exe.old",
        r"C:\log.txt", 4242)
ok("같은 명령 순서", cmds(updater.update_script(*args)) == cmds(pupd.update_script(*args)))

print("[8] 업데이트 창 — 건너뛰기 없음")
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402
app = QApplication.instance() or QApplication([])
from kbsearch import update_ui  # noqa: E402
d = update_ui.UpdateDialog({"version": "1.0.1", "notes": "고침"})
labels = sorted(b.text() for b in d.findChildren(QPushButton))
ok("단추는 [계속(개발 실행)] 과 [종료] 뿐", labels == sorted(["계속", "종료"]), labels)
d.reject()
ok("Esc/닫기 = 종료", d.outcome == update_ui.QUIT)
updater.is_frozen = lambda: True             # exe 로 돈다고 치고
d = update_ui.UpdateDialog({"version": "1.0.1", "notes": ""}, failed_before=False)
labels = sorted(b.text() for b in d.findChildren(QPushButton))
ok("exe 에서는 [다시 시도] 와 [종료] 뿐", labels == sorted(["다시 시도", "종료"]), labels)
ok("창에 닫기 단추가 없다", not (d.windowFlags() & __import__("PySide6.QtCore").QtCore.Qt.WindowCloseButtonHint))
closed = []
d.done = lambda r: closed.append(r)
d._busy = True
d.reject()
ok("받는 중에는 Esc 무시", closed == [])
d._busy = False
d.reject()
ok("받는 중이 아니면 Esc = 종료", closed and d.outcome == update_ui.QUIT)

print()
print("실패:", FAIL if FAIL else "없음")
_sys.exit(1 if FAIL else 0)
