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
REAL_VERSION = config.APP_VERSION
config.APP_VERSION = "1.0.0"          # 아래 가짜 릴리스(kb-v1.0.1)보다 낮은 판이라고 치고
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
args2 = args + (5151, r"C:\Users\me\AppData\Roaming\KbSearch\update_status.txt")
sc = updater.update_script(*args2)
ok("부모(PPID)·결과 파일까지 넘겨도 같다(일정관리기 v1.23.1)",
   cmds(sc) == cmds(pupd.update_script(*args2)))
ok("30초 넘게 남으면 끝낸다 · 결과를 남긴다",
   "taskkill /F /PID %PID%" in sc and "echo ok> \"%STATUS%\"" in sc
   and "fail missing" in sc and "fail locked" in sc)

print("[8] 묻지 않는 업데이트 — 단추 없이 받아 바꾸고, 못 받으면 지금 판으로(kb-v1.4.0)")
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402
app = QApplication.instance() or QApplication([])
from kbsearch import update_ui  # noqa: E402
INFO = {"version": "1.0.1", "notes": "고침"}
updater.is_frozen = lambda: False
ok("소스로 돌 때는 그냥 계속", update_ui.run(INFO) == update_ui.CONTINUE)
updater.is_frozen = lambda: True             # exe 로 돈다고 치고
CALLS = []
_dl, _apply = updater.download, updater.apply_and_restart
update_ui.RETRY_WAIT_SEC = 0.01
FAILS = {"n": 0}


def fake_dl(info, progress=None):
    CALLS.append("dl")
    if FAILS["n"] > 0:
        FAILS["n"] -= 1
        raise updater.UpdateError("인터넷 연결")
    if progress:
        progress(50, 100)
    return "/tmp/new.exe"


updater.download = fake_dl
updater.apply_and_restart = lambda path, ver="": CALLS.append(("apply", path, ver))
seen_btn = []
_orig_show = update_ui.UpdateSplash.show
update_ui.UpdateSplash.show = lambda self: (seen_btn.append(len(self.findChildren(QPushButton))),
                                            _orig_show(self))[1]
out = update_ui.run(INFO, show=True, tray=False)
ok("받아서 바꾼다 → 끝낸다(RESTART)", out == update_ui.RESTART and ("apply", "/tmp/new.exe", "1.0.1") in CALLS,
   CALLS)
ok("받는 동안 창에 단추가 없다(묻지 않는다)", seen_btn and all(n == 0 for n in seen_btn), seen_btn)
ok("다시 켜질 때 창으로(트레이 아님)", updater.take_resume_tray() is False)
CALLS.clear()
(config.data_file(updater.STATE_FILE)).unlink(missing_ok=True)
FAILS["n"] = 2
out = update_ui.run(INFO, show=False, tray=True)
ok("두 번 못 받아도 세 번째에 받는다", out == update_ui.RESTART and CALLS.count("dl") == 3, CALLS)
ok("트레이로 켰으면 새 판도 트레이로", updater.take_resume_tray() is True)
CALLS.clear()
(config.data_file(updater.STATE_FILE)).unlink(missing_ok=True)
FAILS["n"] = 9
out = update_ui.run(INFO, show=False)
ok("끝내 못 받으면 지금 판으로 켠다(종료하지 않는다)", out == update_ui.CONTINUE and not any(
   isinstance(c, tuple) for c in CALLS), CALLS)
FAILS["n"] = 0
updater.note_attempt("1.0.1")                # 방금 이 판으로 바꾸려다 그대로 켜졌다
CALLS.clear()
out = update_ui.run(INFO, show=False)
ok("방금 바꾸지 못했으면 되풀이하지 않는다(몇 시간 뒤 다시)", out == update_ui.CONTINUE and CALLS == [], CALLS)
(config.data_file(updater.STATE_FILE)).unlink(missing_ok=True)
update_ui.UpdateSplash.show = _orig_show

print("[8-2] 진행 창 — 막대 · % · MB · 바꾸는 중 · 못 받으면 까닭(kb-v1.5.0)")
# 지점장 요청: "업데이트 할 때에는 프로그레스바를 만들어서 업데이트 하고 있다는 내용을 시각적으로"
from kbsearch.update_progress import UpdateProgress, notes_lines  # noqa: E402
STATES = []
_orig_prog, _orig_apply, _orig_fail = UpdateProgress.progress, UpdateProgress.applying, UpdateProgress.failed
UpdateProgress.progress = lambda self, g, t: (STATES.append(("p", g, t, self.bar.value())),
                                             _orig_prog(self, g, t))[1]
UpdateProgress.applying = lambda self: (STATES.append(("apply",)), _orig_apply(self))[1]
UpdateProgress.failed = lambda self, why: (STATES.append(("fail", why)), _orig_fail(self, why))[1]
update_ui.APPLY_SHOW_SEC = update_ui.FAIL_SHOW_SEC = 0.05


def dl_steps(info, progress=None):
    for i in range(5):
        progress(i * 10 << 20, 40 << 20)
        time.sleep(0.06)
    return "/tmp/new.exe"


updater.download = dl_steps
(config.data_file(updater.STATE_FILE)).unlink(missing_ok=True)
out = update_ui.run(dict(INFO, notes="## v1.0.1\n· 첫째 고침\n· 둘째 고침"), show=True, tray=False, corner=True)
pc = [x for x in STATES if x[0] == "p"]
ok("받는 동안 진행을 그린다(마지막은 100%)", out == update_ui.RESTART and len(pc) >= 2 and pc[-1][1] == pc[-1][2],
   pc[-1:])
ok("다 받으면 '바꾸는 중' 을 보여 준 뒤 바꾼다", ("apply",) in STATES)
mk = json.loads(config.data_file("update_resume.json").read_text(encoding="utf-8"))
ok("새 판에 넘길 표시 — 바꾸려는 판 · 달라진 것", mk.get("to") == "1.0.1" and "첫째 고침" in mk.get("notes", "")
   and mk.get("from") == config.APP_VERSION, mk)
config.APP_VERSION = "1.0.1"
r = updater.take_resume()
ok("새 판이 켜지면 '업데이트 완료'", updater.finished_update(r) == "1.0.1" and updater.take_resume() == {})
config.APP_VERSION = "1.0.0"
ok("바꾸지 못하고 옛 판으로 켜졌으면 완료라 하지 않는다", updater.finished_update(r, "1.0.1") == "")
config.data_file("last_version.json").unlink(missing_ok=True)
ok("처음 켠 판은 지난 판이 없다", updater.note_run_version() == "")
config.APP_VERSION = "1.0.1"
_prev = updater.note_run_version()
ok("판이 올라가면 완료(표시를 몰랐던 옛 판이 바꿔 줘도)", _prev == "1.0.0" and updater.finished_update({}, _prev) == "1.0.1")
ok("같은 판으로 다시 켜면 완료가 아니다", updater.finished_update({}, updater.note_run_version()) == "")
config.APP_VERSION = "1.0.0"
ok("완료 창에는 달라진 것 앞 몇 줄", notes_lines(r.get("notes")) == "· 첫째 고침\n· 둘째 고침")
STATES.clear()
(config.data_file(updater.STATE_FILE)).unlink(missing_ok=True)
FAILS["n"] = 9
updater.download = fake_dl
out = update_ui.run(INFO, show=True)
ok("끝내 못 받으면 진행 창에 까닭을 보여 주고 지금 판으로", out == update_ui.CONTINUE
   and any(x[0] == "fail" and "인터넷" in x[1] for x in STATES), STATES[-1:])
FAILS["n"] = 0
UpdateProgress.progress, UpdateProgress.applying, UpdateProgress.failed = _orig_prog, _orig_apply, _orig_fail
p = UpdateProgress("1.5.0", corner=True)
p.pop()
p.progress(10 << 20, 40 << 20)
ok("막대 25% · '10.0 / 40.0 MB' · 단추 없음", p.bar.value() == 25 and "10.0 / 40.0 MB" in p.lbl_msg.text()
   and not p.findChildren(QPushButton), p.lbl_msg.text())
from PySide6.QtGui import QGuiApplication  # noqa: E402
_g = QGuiApplication.primaryScreen().availableGeometry()
ok("켜 둔 동안은 오른쪽 아래", p.x() > _g.center().x() and p.y() > _g.center().y())
p.close()
c = UpdateProgress("1.5.0", corner=False)
c.pop()
ok("켤 때(창이 뜨기 전)는 화면 가운데", abs(c.geometry().center().x() - _g.center().x()) <= 2, (c.geometry(), _g))
c.close()
updater.download, updater.apply_and_restart = _dl, _apply

config.APP_VERSION = REAL_VERSION

print("[10] 업데이트 뒤 — 남은 옛 판 넘겨받기 · 지난 실패 알리기 (일정관리기 v1.23.1)")
import subprocess as _sp  # noqa: E402
from kbsearch import app as kapp  # noqa: E402
logf = config.base_dir() / "update_log.txt"
logf.write_text("[update] start\n[update] replaced ok\n", encoding="utf-8")
ok("방금 깔렸다(기록에 replaced ok, 10분 안)", updater.just_installed())
os.utime(logf, (time.time() - 700, time.time() - 700))
ok("오래된 기록이면 아니다", not updater.just_installed())
os.utime(logf, None)
killed = []
updater.kill_other_instances = lambda: (killed.append(1), 1)[1]
_frozen = updater.is_frozen
updater.is_frozen = lambda: True
config.APP_VERSION, _kv = "1.0.4", config.APP_VERSION
ok("대답 없는 옛 판(1.0.3 이하)이 남았으면 끝내고 이어서 뜬다",
   kapp._take_over_after_update("") is True and killed)
killed.clear()
ok("더 낮은 판이 대답해도 넘겨받는다", kapp._take_over_after_update("1.0.3") is True and killed)
killed.clear()
ok("같은·높은 판이면 보통 두 번 실행 — 있는 창만 띄운다",
   kapp._take_over_after_update("1.0.4") is False and not killed)
logf.unlink()
ok("방금 깔린 게 아니면 넘겨받지 않는다", kapp._take_over_after_update("") is False and not killed)
config.APP_VERSION = _kv
updater.is_frozen = _frozen
st = config.base_dir() / "update_status.txt"
st.write_text("fail missing\n", encoding="utf-8")
ok("지난 실패 이유", updater.last_failure() == "missing" and "백신" in updater.failure_text("missing"))
st.unlink()
# 켜져 있는 쪽이 'ok 판번호' 로 대답하는지 — 따로 띄운 프로그램(서버)에 붙어 본다
key = f"KbSearchVerify_{os.getpid()}"
srv = _sp.Popen([_sys.executable, "-c", f"""
import sys
from PySide6.QtCore import QCoreApplication, QTimer
from PySide6.QtNetwork import QLocalServer
app = QCoreApplication([])
QLocalServer.removeServer({key!r})
s = QLocalServer(); s.listen({key!r})
def on():
    c = s.nextPendingConnection()
    c.write(b"ok 9.9.9\\n"); c.flush(); c.waitForBytesWritten(300); c.disconnectFromServer()
s.newConnection.connect(on)
print("ready", flush=True)
QTimer.singleShot(8000, app.quit)
app.exec()
"""], stdout=_sp.PIPE, text=True)
srv.stdout.readline()
kapp._SINGLE_KEY = key
# ⚠️ 붙는 데 0.4초만 기다린다(앱과 같다) — 검사 PC 가 바쁘면 가끔 못 붙는다. 세 번까지 해 본다.
_rep = None
for _t in range(3):
    _rep = kapp._activate_existing()
    if _rep == "9.9.9":
        break
ok("켜져 있는 쪽이 판 번호로 대답한다", _rep == "9.9.9", _rep)
srv.kill()
kapp._SINGLE_KEY = "KbSearchVerify_none"
ok("아무것도 없으면 None", kapp._activate_existing() is None)
import inspect as _insp  # noqa: E402
src = _insp.getsource(kapp.main)
ok("끝낼 때 마무리 정리 없이 바로 끝낸다(os._exit)", "_hard_exit(app.exec())" in src
   and "os._exit" in _insp.getsource(kapp._hard_exit))
ok("끌 때 Qt 문구 처리기를 뗀다", "crashlog.remove_qt_handler" in src)

print("[9] push 때 저절로 릴리스할지 (release_plan)")
_sys.path.insert(0, str(_HERE.parent))
import release_plan as rp  # noqa: E402
ls = ("a1\trefs/tags/v1.21.2\n"
      "b2\trefs/tags/kb-v1.0.1\n"
      "b3\trefs/tags/kb-v1.0.1^{}\n")
ok("ls-remote 줄 → 태그", rp.tags_from_ls_remote(ls) == ["v1.21.2", "kb-v1.0.1"])
ok("처음 판은 낸다", rp.plan("1.0.1", []) == "kb-v1.0.1")
ok("새 판 번호면 낸다", rp.plan("1.0.2", ["kb-v1.0.1", "v1.21.2"]) == "kb-v1.0.2")
ok("이미 나간 판이면 빌드만", rp.plan("1.0.1", ["kb-v1.0.1"]) == "")
ok("더 낮은 판(옛 갈래)은 안 낸다", rp.plan("1.0.0", ["kb-v1.0.1"]) == "")
ok("일정관리기 태그는 상관없다", rp.plan("1.0.1", ["v1.30.0"]) == "kb-v1.0.1")
ok("판 번호 모양이 이상하면 안 낸다", rp.plan("1.0", []) == "")
ok("지금 APP_VERSION 을 읽는다", rp.app_version() == config.APP_VERSION)
import release_notes as rn  # noqa: E402
ok("지금 판의 변경 이력 절이 있다(없으면 릴리스가 멈춘다)", bool(rn.extract("kb-v" + config.APP_VERSION)))

print("[11] 웹 스위치(kbsearch.vercel.app [관리]) — 확실히 꺼짐일 때만 끈다")
from kbsearch import switch  # noqa: E402


class _R:
    def __init__(self, code, body):
        self.status_code, self._b = code, body

    def json(self):
        if isinstance(self._b, Exception):
            raise self._b
        return self._b


class _S:
    def __init__(self, resp):
        self.resp = resp
        self.urls = []

    def get(self, url, **k):
        self.urls.append(url)
        if isinstance(self.resp, Exception):
            raise self.resp
        return self.resp


_real_http = switch._http
for label, resp, want_off in (
        ("꺼짐", _R(200, {"on": False, "message": "점검 중"}), True),
        ("켜짐", _R(200, {"on": True, "message": ""}), False),
        ("인터넷 안 됨", OSError("down"), False),
        ("주소 없음(404)", _R(404, {}), False),
        ("JSON 아님", _R(200, ValueError("html")), False),
        ("on 이 글자 'false'", _R(200, {"on": "false"}), False),
        ("on 이 없음", _R(200, {"message": "x"}), False)):
    s_ = _S(resp)
    switch._http = lambda s_=s_: s_
    st = switch.fetch_state()
    ok(f"{label} → {'끔' if want_off else '켜 둠'}", switch.is_off(st) is want_off, st)
ok("꺼짐 안내는 웹에서 적은 말", switch.off_message({"on": False, "message": "점검 중"}) == "점검 중")
ok("안내가 비면 기본 안내", switch.off_message({"on": False, "message": ""}) == config.SERVICE_OFF_MESSAGE)
ok("주소는 웹 스위치", s_.urls[-1] == "https://kbsearch.vercel.app/api/status")
_url = config.SWITCH_URL
config.SWITCH_URL = ""
ok("주소를 비우면 보지 않는다", switch.fetch_state() is None)
config.SWITCH_URL = _url
switch._http = _real_http
import inspect as _insp  # noqa: E402
from kbsearch import app as _kapp  # noqa: E402
_src = _insp.getsource(_kapp.main)
ok("켤 때 — 업데이트를 먼저 보고 그다음 스위치", _src.index("_check_with_splash") < _src.index("switch.fetch_state"))
ok("켤 때 — 진행 창은 트레이로 켤 때도 보인다(kb-v1.5.0)", "update_ui.run(info, show=True, tray=tray_start)" in _src)
ok("켤 때 — 업데이트로 켜졌으면 '업데이트 완료'", "updater.take_resume()" in _src
   and "updater.finished_update(resume, updater.note_run_version())" in _src and "show_update_done" in _src)

print("\n[11] 배치에 깨끗한 환경 — 새 판이 옛 판의 임시 폴더(_MEI)를 물려받지 않게 (kb-v1.4.1)")
import os as _os2, tempfile as _tf2  # noqa: E402
from kbsearch import updater as _up2  # noqa: E402
_mei = _tf2.mkdtemp(prefix="_MEI")
_had = getattr(_sys, "_MEIPASS", None)
_sys._MEIPASS = _mei
_save = dict(_os2.environ)
_os2.environ.update({"_PYI_APPLICATION_HOME_DIR": _mei, "_PYI_ARCHIVE_FILE": "x.exe",
                     "_PYI_PARENT_PROCESS_LEVEL": "1", "QT_PLUGIN_PATH": _os2.path.join(_mei, "p"),
                     "PATH": _os2.pathsep.join([_os2.path.join(_mei, "q"), "/usr/bin"])})
_env = _up2.clean_env()
ok("_PYI_ 변수를 뺀다", not [k for k in _env if k.startswith("_PYI_")])
ok("새로 풀라고 알린다", _env.get("PYINSTALLER_RESET_ENVIRONMENT") == "1")
ok("옛 임시 폴더를 가리키는 값을 뺀다", "QT_PLUGIN_PATH" not in _env and _env["PATH"] == "/usr/bin", _env.get("PATH"))
_os2.environ.clear(); _os2.environ.update(_save)
if _had is None:
    del _sys._MEIPASS
else:
    _sys._MEIPASS = _had
_asrc = _insp.getsource(_up2.apply_and_restart)
ok("배치를 깨끗한 환경 · exe 폴더에서 돌린다", "env=clean_env()" in _asrc and "cwd=tdir" in _asrc)
ok("배치 안에서도 새로 풀라고 알린다",
   'set "PYINSTALLER_RESET_ENVIRONMENT=1"' in _up2.update_script("S", "C:\\a\\b.exe", "C:\\a\\b.exe.old", "L", 1, 2, "ST"))

print("\n[12] 'Failed to remove temporary directory' 경고 막기 — 부모를 먼저 끝내고 남은 폴더는 나중에(kb-v1.5.1)")
import ctypes as _ct  # noqa: E402
import shutil as _sh  # noqa: E402
import tempfile as _tf3  # noqa: E402
from kbsearch import updater as _up3  # noqa: E402
ok("개발 실행이면 부모를 건드리지 않는다", _up3.release_bootloader() is False)


class _Fn3:
    def __init__(self, impl):
        self.impl, self.restype, self.argtypes = impl, None, None

    def __call__(self, *a):
        return self.impl(*a)


class _K3:
    def __init__(self, img):
        self.term = []
        self.OpenProcess = _Fn3(lambda a, i, pid: 55)

        def q(h, f, buf, size):
            buf.value = img
            return 1
        self.QueryFullProcessImageNameW = _Fn3(q)
        self.TerminateProcess = _Fn3(lambda h, c: self.term.append(h) or 1)
        self.CloseHandle = _Fn3(lambda h: 1)


_fz3, _pl3, _ex3 = _up3.is_frozen, _sys.platform, _sys.executable
_up3.is_frozen = lambda: True
_sys.platform = "win32"
_sys.executable = os.path.join(_tf3.gettempdir(), "업무자료검색.exe")
_k = {"k": _K3(_sys.executable)}
_ct.WinDLL = lambda name, use_last_error=False: _k["k"]
ok("부모가 이 exe 면 먼저 끝낸다", _up3.release_bootloader() is True and _k["k"].term == [55])
_k["k"] = _K3(r"C:\Windows\explorer.exe")
ok("부모가 다른 프로그램이면 건드리지 않는다", _up3.release_bootloader() is False and _k["k"].term == [])
_sys.platform, _sys.executable = _pl3, _ex3
del _ct.WinDLL
_base = _tf3.mkdtemp()


def _mk(name, marker=True, age=3600):
    pth = os.path.join(_base, name)
    os.makedirs(pth, exist_ok=True)
    if marker:
        open(os.path.join(pth, _up3.TEMP_MARKER), "wb").close()
    tt = time.time() - age
    os.utime(pth, (tt, tt))
    return pth


_cur, _old = _mk("_MEIcur"), _mk("_MEIold")
_other, _fresh = _mk("_MEIother", marker=False), _mk("_MEIfresh", age=5)
_planner = os.path.join(_base, "_MEIplanner")
os.makedirs(_planner)
open(os.path.join(_planner, "planner.ico"), "wb").close()
os.utime(_planner, (time.time() - 3600, time.time() - 3600))
_sys._MEIPASS = _cur
ok("표시 파일은 kbsearch.ico(일정관리기 것과 다르다)", _up3.TEMP_MARKER == "kbsearch.ico")
ok("남은 우리 폴더만 지운다", _up3.cleanup_old_temp(120) == 1 and not os.path.exists(_old)
   and os.path.isdir(_cur) and os.path.isdir(_other) and os.path.isdir(_fresh) and os.path.isdir(_planner))
del _sys._MEIPASS
_up3.is_frozen = _fz3
_sh.rmtree(_base, ignore_errors=True)
_asrc = _insp.getsource(_kapp._hard_exit)
ok("끝낼 때(업데이트·종료 모두 _hard_exit) os._exit 전에 부모를 끝낸다",
   _asrc.index("updater.release_bootloader()") < _asrc.index("os._exit(rc)"))
_msrc = _insp.getsource(_kapp.main)
_i2 = _msrc.index("if not _take_over_after_update(reply):")
ok("두 번째 실행도 끝나기 전에", _msrc.index("updater.release_bootloader()", _i2) < _msrc.index("return 0", _i2))
ok("두 번째 실행을 받은 쪽이 몇 분 뒤 정리", "w.schedule_temp_cleanup(180)" in _msrc)
_kills = [ln for ln in _up3.update_script(*args2).splitlines() if "taskkill" in ln and not ln.lstrip().lower().startswith("rem")]
ok("교체 배치 강제 종료에 /T 없음(배치 자신까지 끝내지 않게)", _kills and not any("/T" in ln for ln in _kills), _kills)

print()
print("실패:", FAIL if FAIL else "없음")
_sys.exit(1 if FAIL else 0)
