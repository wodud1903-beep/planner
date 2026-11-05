"""만기 재계약 목록(v1.26 — renewals.py · renewal_view.py) · 자동 규칙 없애기(v1.28).

  · 재계약 목록: 상태(미연락·연락함·상담중·재계약·안 함) · [멘트 복사] → '연락함' · 상태는 동기화
  · 진행현황 자동 규칙은 없앴다(지점장 "자동규칙을 삭제해줘") — [자동 규칙] 단추가 없고,
    자동 규칙이 만든 할일 중 **아직 안 한 것**은 지운다(지점장 선택). 끝낸 것·직접 만든 것은 그대로,
    지운 것은 이 PC 에 남겨 둔다. 다른 PC 기록을 받은 뒤에만.
  (예전 verify_autorules 의 재계약 부분을 옮겼다)
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
from datetime import date, timedelta

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton  # noqa: E402

from planner import autorule_cleanup, config, google_client, renewals, sheets, sync, theme  # noqa: E402
from planner import startup_dialog as _sd  # noqa: E402
from planner.models import AppSettings, TodoItem  # noqa: E402

_sd.StartupDialog.show_for = staticmethod(lambda *a, **k: None)
QMessageBox.information = staticmethod(lambda *a, **k: None)
FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name
          + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


T = date.today()


def fmt(d):
    return f"{d.year}. {d.month}. {d.day}" if d else ""


def row(n, name, status, cd=None, dd=None, terms="", uid=None, model="쏘나타", fin="KB캐피탈"):
    cr = sheets.CustomerRow(row=n, seq=str(n), total="", center="", accident="")
    cr.values.update({"customer": name, "status": status, "finance": fin, "model": model,
                      "contract_date": fmt(cd), "deliver_date": fmt(dd), "terms": terms})
    cr.uid = uid if uid is not None else f"U{n}"
    return cr


exp95 = row(8, "만기손님", "출고", T - timedelta(days=1000), T - timedelta(days=36 * 30), "36개월")
e2 = row(9, "D-90손님", "출고", None, None, "")
d90 = T + timedelta(days=95)
e2.values.update({"deliver_date": fmt(date(d90.year - 3, d90.month, min(d90.day, 28))), "terms": "36개월"})
ed2 = sheets.expiry_date(e2)
past = row(7, "지난출고", "출고", T - timedelta(days=60), T - timedelta(days=10))

print("[1] 재계약 목록 계산")
store = {}
items = renewals.targets([e2, exp95, past], T, 4, store)
names = [renewals.short_name(x[0]) for x in items]
ok("N개월 안 만기만(지난 것도 한 달은) · 급한 순", names == [n for n in ["만기손님", "D-90손님"] if n in names],
   [(renewals.short_name(x[0]), x[2]) for x in items])
renewals.set_status(store, e2, ed2, "재계약")
ok("상태를 적으면 그 만기일 열쇠로", renewals.key(e2, ed2) in store and store[renewals.key(e2, ed2)]["s"] == "재계약")
ok("정리한 건은 숨길 수 있다", all(x[3] != "재계약" for x in renewals.targets([e2, exp95], T, 4, store, True)))
c = renewals.counts(renewals.targets([e2, exp95], T, 4, store))
ok("요약 — 재계약 성공률", c["재계약"] == 1 and c["성공률"] == 100, c)
ok("멘트 채우기", "D-90손님 고객님" in renewals.ment(e2, ed2) and ed2.isoformat() in renewals.ment(e2, ed2))
ok("열쇠는 알림 서버(brief.js renewKey)와 같은 모양", renewals.key(e2, ed2) == f"uid:U9|{ed2.isoformat()}")
ok("고객ID 가 없으면 순번|이름", renewals.cust_key(row(3, "박영희", "출고", uid="")) == "3|박영희")
ok("이름만(회사 이름 떼고)", renewals.short_name(row(4, "박성일 / 박가네 백년약초", "출고")) == "박성일")

print("[2] 동기화 — 재계약 상태는 합친다(같은 열쇠면 나중 것)")
ok("동기화 대상", "renewals.json" in sync._FILES)
a = json.dumps({"k1": {"s": "연락함", "at": "2026-11-01T00:00:00Z"}, "k2": {"s": "상담중", "at": "2026-11-01T00:00:00Z"}})
b = json.dumps({"k1": {"s": "재계약", "at": "2026-11-02T00:00:00Z"}, "k3": {"s": "안 함", "at": "2026-10-01T00:00:00Z"}})
m = json.loads(sync.merge_text("renewals.json", a, b))
ok("양쪽 열쇠를 다 · 같은 열쇠는 at 이 늦은 쪽", m["k1"]["s"] == "재계약" and set(m) == {"k1", "k2", "k3"}, m)
ok("자동 규칙 기록은 계속 주고받는다(옛 판 PC 가 다시 만들지 않게)", "auto_done.json" in sync._FILES)

print("[3] 자동 규칙을 없앴다 — 만든 할일 중 아직 안 한 것만 고른다")
DONE = {"approved|uid:U2": {"title": "[승인 안내] 김상현", "date": T.isoformat(), "at": "a"},
        "deliver_prep|uid:U4": {"title": "[내일 출고] 이수진", "date": T.isoformat(), "at": "a"},
        "renew_90|uid:U9|x": {"title": "[만기 D-90] D-90손님", "date": T.isoformat(), "at": "a"},
        "deliver_thanks|uid:U7": {"skip": 1, "date": T.isoformat(), "at": "a"}}       # 만들지 않은 기록
todos = [TodoItem(title="[승인 안내] 김상현", run_date=T),
         TodoItem(title="[내일 출고] 이수진", run_date=T + timedelta(days=3)),     # 날짜를 손으로 옮겼어도
         TodoItem(title="[만기 D-90] D-90손님", run_date=T, done=True),          # 이미 끝낸 것
         TodoItem(title="[출고 1개월] 김상현", run_date=T),                       # 팔로업(자동 규칙 아님)
         TodoItem(title="거래처 전화", run_date=T)]                               # 직접 만든 것
gone = autorule_cleanup.pick(todos, DONE)
ok("자동 규칙이 만든, 아직 안 한 것만", [t.title for t in gone] == ["[승인 안내] 김상현", "[내일 출고] 이수진"],
   [t.title for t in gone])
ok("기록이 없으면 아무것도 고르지 않는다", autorule_cleanup.pick(todos, {}) == [])

print("[4] 설정 — 자동 규칙 칸을 없앴다(옛 판 PC 에는 '끔' 으로 보인다)")
p = config.data_file("plan_cfg_test.json")
p.write_text(json.dumps({"autoOn": True, "autoRules": [{"id": "x"}], "theme": "warm"}), encoding="utf-8")
s_ = AppSettings.load(p)
ok("옛 설정 파일(autoOn·autoRules 가 있음)도 읽힌다", s_.theme == "warm" and not hasattr(s_, "auto_rules"))
s_.save(p)
saved = json.loads(p.read_text(encoding="utf-8"))
ok("새로 적는 설정에는 규칙표가 없고 '끔' 만 남는다", saved.get("autoOn") is False and "autoRules" not in saved, saved.get("autoOn"))
import importlib.util  # noqa: E402
ok("자동 규칙 모듈·편집 창이 없다", importlib.util.find_spec("planner.auto_rules") is None
   and importlib.util.find_spec("planner.auto_rules_dialog") is None)

print("[5] 일정관리기 — 단추가 없고, 받은 뒤 만든 할일을 지운다 · [재계약] 화면")
app = QApplication.instance() or QApplication([])
theme.apply_to_app(app)
config.set_account("tester@example.com")
google_client.GoogleAuth.is_connected = lambda self: True
google_client.GoogleAuth.has_scope = lambda self, s: True
sync.sync_now = lambda *a, **k: False
sync.push = lambda *a, **k: None
sheets.read_rows = lambda *a, **k: (1, [], [])
from planner.main_window import MainWindow  # noqa: E402

w = MainWindow()
w.resize(1500, 900)
ok("[자동 규칙] 단추가 없다", not [b for b in w.findChildren(QPushButton) if b.text() == "자동 규칙"]
   and not hasattr(w, "btn_auto_rules") and not hasattr(w, "_run_auto_rules"))
config.atomic_write(config.data_file(autorule_cleanup.DONE_FILE), json.dumps(DONE, ensure_ascii=False))
w.todos = [TodoItem(title=t.title, run_date=t.run_date, done=t.done) for t in todos]
w._pulled_once = False
TOASTS = []
w.sig_toast.connect(lambda t, m_: TOASTS.append(m_))
ok("다른 PC 기록을 받기 전에는 지우지 않는다", w._cleanup_auto_rule_todos() == 0 and len(w.todos) == 5)
w._fetch_after_sync = w.fetch_all_async
w.fetch_all_async = lambda *a, **k: None
w._on_synced(False)                         # 받았다 → 그때 지운다
for _ in range(10):
    app.processEvents()
w.fetch_all_async = w._fetch_after_sync
left = [t.title for t in w.todos]
ok("받은 뒤 — 자동 규칙이 만든, 안 한 할일 2건을 지운다", left == ["[만기 D-90] D-90손님", "[출고 1개월] 김상현", "거래처 전화"],
   left)
ok("끝낸 것 · 팔로업 · 직접 만든 할일은 그대로", "거래처 전화" in left and "[출고 1개월] 김상현" in left
   and "[만기 D-90] D-90손님" in left)
saved_todos = json.loads(config.data_file("todos.json").read_text(encoding="utf-8"))
ok("할일 파일에도 저장(동기화로 다른 PC 도)", [t["title"] for t in saved_todos] == left)
kept = autorule_cleanup.load_removed()
ok("지운 할일은 이 PC 에 남겨 둔다(되살릴 수 있게)", [k["title"] for k in kept] == ["[승인 안내] 김상현", "[내일 출고] 이수진"]
   and all(k.get("removedAt") for k in kept), kept)
ok("지웠다고 한 번 알린다", any("2건" in m_ for m_ in TOASTS), TOASTS)
ok("기록(auto_done.json)은 남겨 둔다(옛 판 PC 가 다시 만들지 않게)", config.data_file(autorule_cleanup.DONE_FILE).exists())
ok("다시 받아도 더 지우지 않는다", w._cleanup_auto_rule_todos() == 0)
w.todos.append(TodoItem(title="[승인 안내] 김상현", run_date=T))   # 아직 옛 판인 PC 가 그사이 또 만들었다
w._sync_after = w.reload_data
w.reload_data = lambda: None
w._on_sync_done(True, "", False)
for _ in range(10):
    app.processEvents()
w.reload_data = w._sync_after
ok("옛 판 PC 가 그사이 만든 것도 동기화 때 거둔다", "[승인 안내] 김상현" not in [t.title for t in w.todos],
   [t.title for t in w.todos])

w.settings.sheet_on = True
w.settings.sheet_id = "SHEET"
w.sheet_rows = [row(2, "김상현", "발주", T - timedelta(days=5)), e2]
w._sheet_loaded = True
w.show()
w.tabs.setCurrentWidget(w.tab_cust)
w.btn_view_renew.click()
for _ in range(10):
    app.processEvents()
ok("[재계약] 을 누르면 재계약 목록", w.cust_stack.currentWidget() is w.renew)
ok("다음에 켤 때도(설정에 남긴다)", w.settings.cust_view == "renew")
r = w.renew.row_of("D-90손님")
ok("만기가 다가오는 고객이 보인다", r >= 0, [renewals.short_name(x[0]) for x in w.renew.items])
w.renew.tbl.cellWidget(r, 6).click()
for _ in range(5):
    app.processEvents()
clip = QApplication.clipboard().text()
ok("[멘트 복사] — 이름·만기일을 채운 안내", "D-90손님 고객님" in clip and ed2.isoformat() in clip, clip[:60])
ok("복사하면 '연락함' 으로", renewals.status(w._renewals, e2, ed2) == "연락함")
ok("상태는 파일에(동기화)", renewals.load().get(renewals.key(e2, ed2), {}).get("s") == "연락함")
r = w.renew.row_of("D-90손님")
n_before = len(w.todos)
w.renew.tbl.cellWidget(r, 5).setCurrentText("재계약")
for _ in range(10):
    app.processEvents()
ok("상태를 '재계약' 으로", renewals.status(w._renewals, e2, ed2) == "재계약")
ok("상태를 바꿔도 할일을 만들거나 지우지 않는다(자동 규칙 없음)", len(w.todos) == n_before)
if os.environ.get("SHOT_DIR"):
    w.grab().save(os.path.join(os.environ["SHOT_DIR"], "renewals_pc.png"))
w.btn_view_list.click()
w.hide()

print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
