"""[출고 1개월] 이 2개·3개씩 쌓이던 문제(v1.26.1) — 지점장: "출고 1개월 이 계속 2개씩 등록돼".

원인: 켤 때 캘린더를 받자마자 팔로업을 검사했는데 그때는 다른 PC 기록을 받기 전이라
사무실 PC · 집 PC 가 같은 고객의 일정을 저마다 캘린더에 올렸다.
  · 다른 PC 기록을 받기 전에는 팔로업을 만들지 않는다
  · 캘린더에 이미 그 고객의 팔로업이 있으면 캘린더에 또 올리지 않는다
  · 이미 겹친 일정(같은 캘린더 · 같은 날 · 같은 제목)과 할일은 하나만 남긴다
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
import os as _os
_os.chdir(_ROOT / "python")

import os
import tempfile
import time
from datetime import date, datetime, timedelta

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from planner import followup, google_client, sheets, sync, theme, updater  # noqa: E402
from planner import startup_dialog as _sd  # noqa: E402
from planner.google_client import CalEvent  # noqa: E402
from planner.models import TodoItem  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


def ev(uid, title, day, cal="primary", eid=None):
    return CalEvent(start=datetime(day.year, day.month, day.day), has_time=False, summary=title,
                    uid=uid, cal_id=cal, event_id=eid if eid is not None else uid)


T = date.today()
print("[1] 겹친 일정 골라내기")
d1, d2 = T + timedelta(days=8), T + timedelta(days=9)
evs = [ev("a", "[출고 1개월] 김명준", d1), ev("b", "[출고 1개월] 김명준", d1),
       ev("c", "[출고 1개월] 김명준", d1), ev("d", "[출고 1개월] 차경민", d2),
       ev("e", "[출고 1개월] 차경민", d2), ev("f", "[출고 1개월] 김경인", d2),
       ev("g", "양주 패밀리데이", d2), ev("h", "양주 패밀리데이", d2),
       ev("i", "[출고 1개월] 김경인", d1),                      # 다른 날 — 겹침 아님
       ev("j", "[출고 1개월] 김경인", d2, cal="work@x"),         # 다른 캘린더 — 겹침 아님
       ev("k", "[출고 1개월] 차경민", d2, eid="")]               # 지울 수 없는 것
extra = followup.duplicate_events(evs)
ok("같은 날 같은 제목만 — 첫 것만 남긴다", sorted(e.uid for e in extra) == ["b", "c", "e"],
   [e.uid for e in extra])
ok("팔로업이 아닌 일정은 건드리지 않는다", not any(e.summary == "양주 패밀리데이" for e in extra))
ok("캘린더의 팔로업 고객명", followup.calendar_names(evs) == {"김명준", "차경민", "김경인"},
   followup.calendar_names(evs))

print("[2] 겹친 할일 — 끝낸 것을 남긴다")
t1 = TodoItem(title="[출고 1개월] 김명준", run_date=d1)
t2 = TodoItem(title="[출고 1개월] 김명준", run_date=d1, done=True)
t3 = TodoItem(title="[출고 1개월] 김명준", run_date=d2)
t4 = TodoItem(title="장보기", run_date=d1)
t5 = TodoItem(title="장보기", run_date=d1)
dt = followup.duplicate_todos([t1, t2, t3, t4, t5])
ok("하나만 빠진다(끝낸 건 남김)", len(dt) == 1 and dt[0] is t1, dt)

print("[3] 메인 창 — 받기 전엔 안 만들고, 캘린더에 있으면 또 안 올린다")
_sd.StartupDialog.show_for = staticmethod(lambda *a, **k: None)
QMessageBox.information = staticmethod(lambda *a, **k: None)
app = QApplication.instance() or QApplication([])
theme.apply_to_app(app)
google_client.GoogleAuth.is_connected = lambda self: False
sync.sync_now = lambda *a, **k: False
sheets.read_rows = lambda *a, **k: (1, [], [])
updater.check = lambda *a, **k: None
INS, DEL = [], []
google_client.insert_event = lambda auth, cal, title, d, **k: INS.append((title, d))
google_client.delete_event = lambda auth, cal, eid: DEL.append(eid)

from planner.main_window import MainWindow  # noqa: E402


def pump(sec=0.5):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


w = MainWindow()
w.gauth.is_connected = lambda: True
w.settings.follow_on = True
w.settings.follow_to_calendar = True
w.settings.follow_months = 1
w.todos = []
# 출고 일정 둘(고객 둘) + 다른 PC 가 이미 올린 '김명준' 팔로업 일정 둘(겹침)
ship = T - timedelta(days=20)
target = followup.add_months(ship, 1) - timedelta(days=3)
w.cal_events = [ev("s1", "김명준 출고", ship), ev("s2", "차경민 출고", ship),
                ev("f1", "[출고 1개월] 김명준", target), ev("f2", "[출고 1개월] 김명준", target)]
ok("켜자마자(받기 전)는 아직 받지 않은 상태", w._pulled_once is False)
w._run_followups()
pump(0.3)
ok("다른 PC 기록을 받기 전엔 할일도 일정도 만들지 않는다", w.todos == [] and INS == [] and DEL == [],
   (w.todos, INS, DEL))
w._pulled_once = True
w._run_followups()
pump(0.6)
names = sorted(followup.followup_name(t.title) for t in w.todos)
ok("받은 뒤에는 할일을 만든다", names == ["김명준", "차경민"], names)
ok("캘린더에 이미 있는 김명준은 또 올리지 않는다 — 차경민만", INS == [("[출고 1개월] 차경민", target)], INS)
ok("겹쳐 있던 김명준 일정은 하나만 남기고 지운다", DEL == ["f2"], DEL)
ok("화면에서도 빠졌다", [e.uid for e in w.cal_events].count("f1") == 1
   and "f2" not in [e.uid for e in w.cal_events])
INS.clear()
DEL.clear()
w._run_followups()
pump(0.4)
ok("다시 조회해도 더 만들지 않는다", INS == [] and DEL == [] and len(w.todos) == 2, (INS, DEL))
ok("받고 나면(_on_synced) 검사할 수 있게 된다",
   "self._pulled_once = True" in __import__("inspect").getsource(MainWindow._on_synced))
w.hide()

print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
