"""출고일 자동 등록이 **실제 저장 경로에 걸려 있는지** 확인한다.

verify_deliver.py 는 규칙(plan)만 본다. 규칙이 맞아도 저장할 때 안 불리면
아무 일도 안 일어난다 — 그 배선을 여기서 본다.
구글은 가짜로 끼워 넣는다(진짜 캘린더에 일정을 만들지 않는다).
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

tmp = tempfile.mkdtemp()
os.environ["APPDATA"] = tmp
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from planner import deliver_cal, google_client, sheets, sync  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name
          + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


app = QApplication.instance() or QApplication([])


def pump(n=60):
    for _ in range(n):
        app.processEvents()
        time.sleep(0.01)


# ---- 구글을 가짜로 ----------------------------------------------------------
CALLS = []
_seq = [0]


def fake_insert(auth, cal_id, summary, day, **kw):
    """진짜 insert_event 와 **같은 모양**을 돌려준다.

    ⚠️ 여기서 대충 만든 객체를 돌려주면 안 된다. 만들어진 일정은 곧바로
       add_optimistic_event() 로 넘어가 이번주 목록에 얹히는데, 거기서 .start 를
       읽는다. 짝퉁을 돌려주니 그 자리에서 예외가 났다 —
       검사는 통과했는데 화면 쪽이 조용히 깨져 있던 셈이다.
    """
    from datetime import datetime
    _seq[0] += 1
    CALLS.append(("insert", cal_id, summary, day.isoformat(), kw.get("all_day")))
    return google_client.CalEvent(
        start=datetime(day.year, day.month, day.day), has_time=False,
        summary=summary, uid=f"UID{_seq[0]}", cal_id=cal_id,
        event_id=f"EV{_seq[0]}")


def fake_update(auth, cal_id, event_id, summary, day, **kw):
    CALLS.append(("update", cal_id, event_id, summary, day.isoformat()))


def fake_delete(auth, cal_id, event_id):
    CALLS.append(("delete", cal_id, event_id))


google_client.insert_event = fake_insert
google_client.update_event = fake_update
google_client.delete_event = fake_delete
google_client.GoogleAuth.is_connected = lambda self: True
sync.sync_now = lambda *a, **k: (False, "")
sheets.read_rows = lambda *a, **k: (1, [], [])
sheets.ensure_uid_column = lambda *a, **k: None
sheets.write_uid = lambda *a, **k: None

from planner.main_window import MainWindow  # noqa: E402

w = MainWindow()
w.settings.sheet_on = True
w.settings.sheet_id = "SHEET"
w.settings.sheet_name = "미출고차량"
w.settings.follow_keyword = "출고"
w._sheet_header_row = 1


def row(customer, deliver="", uid="u1", rownum=5):
    cr = sheets.CustomerRow(row=rownum, uid=uid)
    cr.values = {"customer": customer, "deliver_date": deliver}
    return cr


def reset():
    CALLS.clear()
    deliver_cal.save({})


print("\n[A] 출고일을 정하면 캘린더에 올라간다")
reset()
cr = row("홍길동")
w._sync_deliver_event(cr, {"customer": "홍길동", "deliver_date": ""},
                      {"customer": "홍길동", "deliver_date": "2026. 8. 20"})
pump()
ok("insert 가 불렸다", [c for c in CALLS if c[0] == "insert"], CALLS)
ins = next((c for c in CALLS if c[0] == "insert"), None)
ok("제목이 '<고객> 출고'", ins and ins[2] == "홍길동 출고", ins and ins[2])
ok("그 날짜로", ins and ins[3] == "2026-08-20", ins and ins[3])
ok("종일 일정이다", ins and ins[4] is True)
ok("만든 일정을 기록해 둔다", deliver_cal.load().get("u1", {}).get("event_id"),
   deliver_cal.load())
# 재조회를 기다리지 않고 이번주 목록에 바로 얹힌다
ok("만든 일정이 이번주 목록에 바로 보인다",
   any(getattr(e, "summary", "") == "홍길동 출고" for e in w.cal_events),
   [getattr(e, "summary", "") for e in w.cal_events])

print("\n[B] 출고일이 그대로면 아무것도 안 한다")
# ⚠️ '기존 고객은 건드리지 않는다' 가 여기서 지켜진다. 다른 칸만 고쳐 저장해도
#    출고일이 그대로면 일정이 생기면 안 된다.
reset()
deliver_cal.save({"u1": {"cal_id": "primary", "event_id": "EV1",
                         "date": "2026-08-20", "title": "홍길동 출고"}})
w._sync_deliver_event(row("홍길동", "2026. 8. 20"),
                      {"customer": "홍길동", "deliver_date": "2026. 8. 20"},
                      {"customer": "홍길동", "deliver_date": "2026. 8. 20",
                       "note": "메모만 고침"})
pump()
ok("구글을 부르지 않는다", CALLS == [], CALLS)

print("\n[C] 출고일이 바뀌면 옮긴다 (지웠다 새로 만들지 않는다)")
reset()
deliver_cal.save({"u1": {"cal_id": "primary", "event_id": "EV1",
                         "date": "2026-08-20", "title": "홍길동 출고"}})
w._sync_deliver_event(row("홍길동", "2026. 9. 1"),
                      {"customer": "홍길동", "deliver_date": "2026. 8. 20"},
                      {"customer": "홍길동", "deliver_date": "2026. 9. 1"})
pump()
ok("update 로 옮긴다", [c for c in CALLS if c[0] == "update"], CALLS)
ok("지우고 새로 만들지 않는다",
   not [c for c in CALLS if c[0] in ("delete", "insert")], CALLS)
ok("기록의 날짜가 새 날짜로 바뀐다",
   deliver_cal.load().get("u1", {}).get("date") == "2026-09-01",
   deliver_cal.load().get("u1"))

print("\n[D] 미정으로 되돌리면 지운다")
reset()
deliver_cal.save({"u1": {"cal_id": "primary", "event_id": "EV1",
                         "date": "2026-08-20", "title": "홍길동 출고"}})
w._sync_deliver_event(row("홍길동", ""),
                      {"customer": "홍길동", "deliver_date": "2026. 8. 20"},
                      {"customer": "홍길동", "deliver_date": ""})
pump()
ok("delete 가 불렸다", [c for c in CALLS if c[0] == "delete"], CALLS)
ok("기록에서도 지워진다", "u1" not in deliver_cal.load(), deliver_cal.load())

print("\n[E] 설정으로 끌 수 있다")
reset()
w.settings.deliver_to_calendar = False
w._sync_deliver_event(row("홍길동"), {"deliver_date": ""},
                      {"customer": "홍길동", "deliver_date": "2026. 8. 20"})
pump()
ok("꺼 두면 아무 일도 안 한다", CALLS == [], CALLS)
w.settings.deliver_to_calendar = True

print("\n[F] 로그인 전에는 건드리지 않는다")
reset()
google_client.GoogleAuth.is_connected = lambda self: False
w._sync_deliver_event(row("홍길동"), {"deliver_date": ""},
                      {"customer": "홍길동", "deliver_date": "2026. 8. 20"})
pump()
ok("구글에 연결돼 있지 않으면 조용하다", CALLS == [], CALLS)
google_client.GoogleAuth.is_connected = lambda self: True

print("\n[G] 저장 경로에 정말 걸려 있나 (소스에서 확인)")
src = (_ROOT / "python" / "planner" / "main_window.py").read_text(encoding="utf-8")
ok("고객 수정 저장에 걸려 있다",
   src.count("_sync_deliver_event(cr, old, merged)") == 1)
ok("고객 등록에도 걸려 있다",
   src.count("_sync_deliver_event(pend, {}, dict(vals))") == 1)

print("\n[H] 동기화 대상")
ok("deliver_events.json 이 PC 끼리 따라온다", "deliver_events.json" in sync._FILES)

print("\n" + (f"{len(FAIL)}건 실패" if FAIL else "전부 통과"))
raise SystemExit(1 if FAIL else 0)
