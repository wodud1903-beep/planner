"""켤 때 지난번 계정 폴더를 바로 연다 · 인터넷이 늦으면 붙을 때까지 다시 확인한다(v1.26).

예전: 켤 때마다 인터넷으로 계정(이메일)을 확인한 뒤에야 계정 폴더를 정했다.
  · 확인하는 동안(1~3초) 공용 폴더(대개 빈)를 보여 줬고
  · PC 를 켠 직후처럼 7~8초 안에 인터넷이 안 붙으면 **하루 종일** 공용 폴더로 지냈다
  · 그런데도 10분마다 동기화가 돌아 공용 폴더를 그 계정 묶음에 올릴 수 있었다
이제: 지난번에 확인한 계정 폴더를 켜자마자 연다(보여 주기·시트 불러오기). 동기화(올리기)는
인터넷으로 계정을 다시 확인한 다음에만 한다. 확인은 연결될 때까지 점점 길게 다시 한다.
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
import os as _os
_os.chdir(_ROOT / "python")

import json
import os
import tempfile
import time
from datetime import date

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from planner import config, google_client, sheets, sync, theme  # noqa: E402
from planner import startup_dialog as _sd  # noqa: E402
from planner.models import AppSettings, TodoItem, save_list  # noqa: E402

_sd.StartupDialog.show_for = staticmethod(lambda *a, **k: None)
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.warning = staticmethod(lambda *a, **k: None)
FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name
          + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


app = QApplication.instance() or QApplication([])
theme.apply_to_app(app)

ME = "me@example.com"


def seed_account(email, title, sheet_id):
    """그 계정 폴더에 할일 하나 · 시트 설정을 둔다."""
    config.set_account(email)
    save_list(config.data_file("todos.json"), [TodoItem(title=title, run_date=date.today())])
    s = AppSettings.load(config.data_file("plan_cfg.json"))
    s.sheet_on, s.sheet_id, s.sheet_name = True, sheet_id, "고객관리"
    s.save(config.data_file("plan_cfg.json"))
    config.set_account("")


seed_account(ME, "어제 적은 할일", "SHEET_ME")
seed_account("other@example.com", "남의 할일", "SHEET_OTHER")
# 공용 폴더에는 아무것도 없다(예전엔 확인이 늦으면 이것을 보여 줬다)
(config.base_dir() / "google_token.json").write_text(
    json.dumps({"refresh_token": "RT", "scopes": []}), encoding="utf-8")

# ---- 가짜 구글 ----
NET = {"up": False, "email": ME}
calls = {"userinfo": 0, "read_rows": [], "pull": 0, "sync_now": 0, "push": 0}


def fake_email(auth, detail=False):
    calls["userinfo"] += 1
    if not NET["up"]:
        return ("", "net") if detail else ""
    return (NET["email"], "") if detail else NET["email"]


def fake_read_rows(auth, sid, sname):
    calls["read_rows"].append(sid)
    return 1, [], []


import requests  # noqa: E402
from planner import kb_files, net  # noqa: E402


class _NoNet:
    """검사 중에는 바깥으로 한 바이트도 나가지 않게 — 진짜 구글에 가짜 토큰을 보내면
    구글이 'invalid_grant' 로 답해 로그인이 풀려 버린다."""
    def __getattr__(self, name):
        def call(*a, **k):
            raise requests.ConnectionError("검사 중 — 인터넷 없음")
        return call


for mod in (net, google_client, sheets, kb_files):
    for attr in ("http", "_http"):
        if hasattr(mod, attr):
            setattr(mod, attr, lambda: _NoNet())
google_client.GoogleAuth.valid_token = lambda self: "AT"
google_client.get_user_email = fake_email
sheets.read_rows = fake_read_rows
sync.pull = lambda a: calls.__setitem__("pull", calls["pull"] + 1) or False
sync.sync_now = lambda a: calls.__setitem__("sync_now", calls["sync_now"] + 1) or False
sync.push = lambda a: calls.__setitem__("push", calls["push"] + 1)
google_client.GoogleAuth.has_scope = lambda self, s: True
google_client.fetch_tasks = lambda a: []
google_client.fetch_calendar_events = lambda *a, **k: []

from planner.main_window import MainWindow  # noqa: E402


def pump(sec=0.6):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


print("[1] 지난번 계정 — 인터넷이 아직 없을 때 켠다")
config.remember_account(ME)
ok("확인한 계정을 맨 위 폴더에 적어 둔다", config.last_account() == ME)
w = MainWindow()
ok("켜자마자 그 계정 폴더", config.current_account() == ME, config.current_account())
ok("어제 적은 할일이 바로 보인다(공용 폴더가 아니라)",
   [t.title for t in w.todos] == ["어제 적은 할일"], [t.title for t in w.todos])
ok("그 계정의 설정(시트 주소)", w.settings.sheet_id == "SHEET_ME", w.settings.sheet_id)
ok("구글 로그인은 그대로(토큰은 맨 위 폴더)", w.gauth.is_connected())
pump(3.0)
ok("인터넷이 없으면 '연결을 기다리는 중'", "기다리는 중" in w.lbl_account.text(), w.lbl_account.text())
ok("시트는 확인을 기다리지 않고 지난번 계정 설정으로 불러온다", "SHEET_ME" in calls["read_rows"],
   calls["read_rows"])
ok("계정은 아직 '확인 안 됨'", not w._account_verified)
w.sync_now_async(manual=False)
w._do_sync_push()
pump(0.5)
ok("확인 전에는 동기화(받기·올리기) 하지 않는다 — 10분 주기도",
   calls["sync_now"] == 0 and calls["push"] == 0 and calls["pull"] == 0, calls)
ok("다시 확인하는 간격은 점점 길게(15초부터)", w.ACCOUNT_RETRY_SEC[0] == 15 and w._acct_tries >= 1)

print("[2] 인터넷이 붙는다 → 다시 확인 → 동기화")
NET["up"] = True
w._start_account_sync()                 # (다시 확인 시계가 울린 것)
pump(1.5)
ok("계정 확인됨", w._account_verified and w.account_email == ME, w.account_email)
ok("계정 줄에 이메일", w.lbl_account.text() == ME, w.lbl_account.text())
ok("확인되면 그때 받아 온다(동기화)", calls["pull"] == 1, calls)
ok("같은 폴더라 시트를 또 읽지 않는다", calls["read_rows"].count("SHEET_ME") == 1, calls["read_rows"])
w.sync_now_async(manual=False)
pump(0.8)
ok("이제 주기 동기화도 돈다", calls["sync_now"] == 1, calls)
n = calls["userinfo"]
w._start_account_sync()
pump(0.3)
ok("확인된 뒤에는 다시 묻지 않는다", calls["userinfo"] == n)
w.hide()
w.deleteLater()
pump(0.2)

print("[3] 다른 계정으로 로그인돼 있으면 — 확인되는 대로 그 계정 폴더로 바꾼다")
config.set_account("")
config.remember_account("other@example.com")
NET.update(up=True, email=ME)
calls.update(read_rows=[], pull=0)
w2 = MainWindow()
ok("처음엔 지난번 계정(other)", w2.settings.sheet_id == "SHEET_OTHER")
pump(2.5)
ok("확인된 계정(me)으로 바꾼다", config.current_account() == ME and w2.settings.sheet_id == "SHEET_ME",
   (config.current_account(), w2.settings.sheet_id))
ok("그 계정의 할일", [t.title for t in w2.todos] == ["어제 적은 할일"])
ok("시트도 그 계정 것으로 다시 읽는다", calls["read_rows"][-1:] == ["SHEET_ME"], calls["read_rows"])
ok("다음에 켤 때는 이 계정으로", config.last_account() == ME)
w2.hide()
w2.deleteLater()
pump(0.2)

print("[4] 처음 켠 PC(기록 없음) — 예전처럼 확인을 기다린다")
config.set_account("")
config.forget_account()
NET["up"] = False
calls.update(read_rows=[], pull=0)
w3 = MainWindow()
ok("공용 폴더로 시작", config.current_account() == "")
pump(2.5)
ok("계정을 모르면 시트를 먼저 읽지 않는다(기본 이름으로 오류가 나던 것)", calls["read_rows"] == [],
   calls["read_rows"])
NET["up"] = True
w3._start_account_sync()
pump(2.5)
ok("확인되면 그 계정 폴더 · 시트", config.current_account() == ME and "SHEET_ME" in calls["read_rows"],
   (config.current_account(), calls["read_rows"]))
w3.hide()
w3.deleteLater()
pump(0.2)

print("[5] 권한 문제(401)는 기다려도 안 풀린다 — 다시 하지 않는다")
config.set_account("")
config.remember_account(ME)
google_client.get_user_email = lambda auth, detail=False: ("", "auth") if detail else ""
w4 = MainWindow()
pump(1.5)
ok("'계정 확인 실패' · 다시 확인 안 함", "확인 실패" in w4.lbl_account.text() and w4._acct_tries == 0,
   w4.lbl_account.text())
ok("그래도 지난번 계정의 할일은 보인다", [t.title for t in w4.todos] == ["어제 적은 할일"])
w4.hide()

print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
