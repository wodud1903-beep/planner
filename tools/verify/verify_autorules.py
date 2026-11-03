"""진행현황 자동 규칙 · 만기 재계약 목록(v1.26 — auto_rules.py · renewals.py · renewal_view.py).

지점장 요청: "자동화 업무를 하고싶어" → 고른 것 ⑥ 진행현황 자동 규칙 · ⑦ 만기 재계약 캠페인.
  · '가결' 이 되면 승인 안내 할일, 출고 전날 준비 · 다음 날 감사 인사, 만기 90·30일 전 재계약 안내
  · 할일은 [내 할일](멘트 복사·알람). 한 고객 한 규칙 한 번 — 지운 할일은 되살리지 않는다
  · 만기 재계약 목록: 상태(미연락·연락함·상담중·재계약·안 함) · [멘트 복사] → '연락함'
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
from datetime import date, timedelta

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from planner import auto_rules, config, google_client, renewals, sheets, sync, theme  # noqa: E402
from planner import startup_dialog as _sd  # noqa: E402

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


R = auto_rules.DEFAULT_RULES

print("[1] 처음 켠 날 — 지금 상태는 '본 것' 으로만(쌓인 '가결' 이 몰려오지 않게)")
rows = [row(2, "김상현", "가결", T - timedelta(days=5)),
        row(3, "박영희", "발주", T - timedelta(days=3)),
        row(4, "이수진", "출고대기", T - timedelta(days=20), T + timedelta(days=5))]
acts, seen = auto_rules.plan(rows, R, {}, None, T)
ok("처음엔 진행현황 규칙으로 할일을 만들지 않는다", not [a for a in acts if a["key"].startswith("approved")],
   [a["key"] for a in acts])
ok("본 것을 적는다", seen == {"uid:U2": "가결", "uid:U3": "발주", "uid:U4": "출고대기"}, seen)
prep = [a for a in acts if a["key"].startswith("deliver_prep")]
ok("날짜 규칙은 처음에도 앞으로 올 날짜만 — 출고 전날 할일", len(prep) == 1
   and prep[0]["date"] == T + timedelta(days=4) and prep[0]["title"] == "[내일 출고] 이수진", prep)
thanks = [a for a in acts if a["key"].startswith("deliver_thanks")]
ok("출고 다음 날 감사 인사", thanks and thanks[0]["date"] == T + timedelta(days=6))
ok("멘트에 고객·차종이 채워진다", "이수진 고객님" in thanks[0]["ment"] and "쏘나타" in thanks[0]["ment"],
   thanks[0]["ment"])

print("[2] 진행현황이 바뀌면 — '발주' → '가결' 이면 승인 안내")
rows[1].values["status"] = "가결"
acts2, seen2 = auto_rules.plan(rows, R, {}, seen, T)
ap = [a for a in acts2 if a["key"].startswith("approved")]
ok("바뀐 고객만(원래 가결이던 김상현은 아니다)", [a["title"] for a in ap] == ["[승인 안내] 박영희"],
   [a["title"] for a in ap])
ok("오늘 할일 · 멘트에 금융사", ap[0]["date"] == T and "KB캐피탈" in ap[0]["ment"])
done = {ap[0]["key"]: {"title": ap[0]["title"], "date": T.isoformat(), "at": "x"}}
acts3, _ = auto_rules.plan(rows, R, done, seen, T)
ok("한 번 만든 것은 다시 만들지 않는다(지웠어도)", not [a for a in acts3 if a["key"].startswith("approved")])
newc = row(5, "새고객", "승인", T)
acts4, _ = auto_rules.plan(rows + [newc], R, {}, seen2, T)
ok("새로 들어온 고객이 이미 '승인' 이면 만든다", [a["title"] for a in acts4 if a["key"].startswith("approved")]
   == ["[승인 안내] 새고객"])
cancel = row(6, "취소손님", "가결 후 취소", T)
acts5, _ = auto_rules.plan([cancel], R, {}, {"uid:U6": "발주"}, T)
ok("취소된 건은 만들지 않는다", not acts5)

print("[3] 출고일이 바뀌면 할일도 옮기고, 미정이면 거둔다")
prev = {"deliver_prep|uid:U4": {"title": "[내일 출고] 이수진", "date": (T + timedelta(days=4)).isoformat(),
                                 "base": (T + timedelta(days=5)).isoformat(), "at": "a"}}
rows[2].values["deliver_date"] = fmt(T + timedelta(days=9))
acts6, _ = auto_rules.plan(rows, R, prev, seen2, T)
mv = [a for a in acts6 if a["key"] == "deliver_prep|uid:U4"]
ok("출고일이 바뀌면 '옮김'", mv and mv[0]["op"] == "move" and mv[0]["date"] == T + timedelta(days=8), mv)
rows[2].values["deliver_date"] = ""
acts7, _ = auto_rules.plan(rows, R, prev, seen2, T)
rm = [a for a in acts7 if a["key"] == "deliver_prep|uid:U4"]
ok("미정으로 되돌리면 '거둠'", rm and rm[0]["op"] == "remove", rm)
gone = {"deliver_prep|uid:U4": dict(prev["deliver_prep|uid:U4"], gone=1, base="")}
acts8, _ = auto_rules.plan(rows, R, gone, seen2, T)
ok("거둔 뒤에는 다시 거두지 않는다", not [a for a in acts8 if a["key"] == "deliver_prep|uid:U4"])
rows[2].values["deliver_date"] = fmt(T + timedelta(days=3))
acts9, _ = auto_rules.plan(rows, R, gone, seen2, T)
ok("다시 정하면 새로 만든다", [a["op"] for a in acts9 if a["key"] == "deliver_prep|uid:U4"] == ["add"])
past = row(7, "지난출고", "출고", T - timedelta(days=60), T - timedelta(days=10))
acts10, _ = auto_rules.plan([past], R, {}, {}, T)
ok("이미 지난 날짜는 만들지 않고 '처리함' 으로만", {a["op"] for a in acts10} == {"mark"}, acts10)

print("[4] 만기 — 2주 앞부터 · 재계약으로 정리하면 거둔다")
exp95 = row(8, "만기손님", "출고", T - timedelta(days=1000), T - timedelta(days=36 * 30), "36개월")
ed = sheets.expiry_date(exp95)
left = (ed - T).days
acts11, _ = auto_rules.plan([exp95], R, {}, {}, T)
want = [r["id"] for r in R if r["kind"] == "expiry" and -7 <= left + r["days"] <= 14]
got = [a["key"].split("|")[0] for a in acts11 if a["op"] == "add"]
ok("만기일 ± 며칠이 2주 안에 들어오는 규칙만", got == want, (left, got, want))
e2 = row(9, "D-90손님", "출고", None, None, "")
e2.values["deliver_date"] = fmt(T - timedelta(days=1)) if False else ""
d90 = T + timedelta(days=95)
# 만기 95일 뒤 → D-90 할일은 5일 뒤(2주 안) — 만들고, D-30 은 아직
e2.values.update({"deliver_date": fmt(date(d90.year - 3, d90.month, min(d90.day, 28))), "terms": "36개월"})
ed2 = sheets.expiry_date(e2)
acts12, _ = auto_rules.plan([e2], R, {}, {}, T)
ok("D-90 할일 — 만기 95일 전후면 5일쯤 뒤로", [a["title"] for a in acts12 if a["op"] == "add"] == ["[만기 D-90] D-90손님"],
   ((ed2 - T).days, [a.get("title") for a in acts12 if a["op"] == "add"]))
ok("만기일이 멘트에", ed2.isoformat() in [a for a in acts12 if a["op"] == "add"][0]["ment"])
k90 = [a for a in acts12 if a["op"] == "add"][0]["key"]
rec = {k90: {"title": "[만기 D-90] D-90손님", "date": "x", "base": ed2.isoformat(), "at": "a"}}
acts13, _ = auto_rules.plan([e2], R, rec, {}, T, closed=lambda cr, d: True)
ok("재계약·안 함으로 정리하면 남은 만기 할일을 거둔다",
   [(a["op"], a.get("keep")) for a in acts13 if a["key"] == k90] == [("remove", True)], acts13)

print("[5] 재계약 목록 계산")
store = {}
items = renewals.targets([e2, exp95, past], T, 4, store)
ok("N개월 안 만기만(지난 것도 한 달은) · 급한 순", [auto_rules.short_name(x[0]) for x in items]
   == [n for n in ["만기손님", "D-90손님"] if n in [auto_rules.short_name(x[0]) for x in items]],
   [(auto_rules.short_name(x[0]), x[2]) for x in items])
renewals.set_status(store, e2, ed2, "재계약")
ok("상태를 적으면 그 만기일 열쇠로", renewals.key(e2, ed2) in store and store[renewals.key(e2, ed2)]["s"] == "재계약")
ok("정리한 건은 숨길 수 있다", all(x[3] != "재계약" for x in renewals.targets([e2, exp95], T, 4, store, True)))
c = renewals.counts(renewals.targets([e2, exp95], T, 4, store))
ok("요약 — 재계약 성공률", c["재계약"] == 1 and c["성공률"] == 100, c)
ok("멘트 채우기", "D-90손님 고객님" in renewals.ment(e2, ed2) and ed2.isoformat() in renewals.ment(e2, ed2))
ok("열쇠는 알림 서버(brief.js renewKey)와 같은 모양", renewals.key(e2, ed2) == f"uid:U9|{ed2.isoformat()}")

print("[6] 동기화 — 자동 규칙 기록·재계약 상태는 합친다(같은 열쇠면 나중 것)")
ok("동기화 대상", {"auto_done.json", "renewals.json"} <= set(sync._FILES)
   and auto_rules.SEEN_FILE not in sync._FILES)
a = json.dumps({"k1": {"s": "연락함", "at": "2026-11-01T00:00:00Z"}, "k2": {"s": "상담중", "at": "2026-11-01T00:00:00Z"}})
b = json.dumps({"k1": {"s": "재계약", "at": "2026-11-02T00:00:00Z"}, "k3": {"s": "안 함", "at": "2026-10-01T00:00:00Z"}})
m = json.loads(sync.merge_text("renewals.json", a, b))
ok("양쪽 열쇠를 다 · 같은 열쇠는 at 이 늦은 쪽", m["k1"]["s"] == "재계약" and set(m) == {"k1", "k2", "k3"}, m)

print("[7] 일정관리기 — [내 할일] 로 만든다 · [재계약] 화면")
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
w.settings.sheet_on = True
w.settings.sheet_id = "SHEET"
rows = [row(2, "김상현", "발주", T - timedelta(days=5)),
        row(4, "이수진", "출고대기", T - timedelta(days=20), T + timedelta(days=5)),
        e2]
w.sheet_rows = rows
w._sheet_loaded = True
w.todos = []
n1 = w._run_auto_rules()
titles = [t.title for t in w.todos]
ok("처음 — 날짜 규칙 할일만(출고 전날·감사·만기 D-90)", set(titles) == {"[내일 출고] 이수진", "[출고 감사] 이수진",
   "[만기 D-90] D-90손님"}, titles)
t0 = next(t for t in w.todos if t.title == "[출고 감사] 이수진")
ok("할일에 멘트·알람(팔로업과 같은 시각)", "이수진 고객님" in t0.ment and t0.alarm == w.settings.follow_alarm
   and t0.run_time == w.settings.follow_time)
ok("기록을 남긴다(auto_done.json)", "deliver_thanks|uid:U4" in auto_rules.load_done())
rows[0].values["status"] = "가결"
w._run_auto_rules()
ok("'가결' 이 되면 승인 안내 할일", "[승인 안내] 김상현" in [t.title for t in w.todos])
before = len(w.todos)
w._run_auto_rules()
ok("다시 돌려도 늘지 않는다", len(w.todos) == before)
w.todos = [t for t in w.todos if t.title != "[승인 안내] 김상현"]       # 사용자가 지웠다
w._run_auto_rules()
ok("지운 할일은 되살리지 않는다", "[승인 안내] 김상현" not in [t.title for t in w.todos])
rows[1].values["deliver_date"] = fmt(T + timedelta(days=8))
w._run_auto_rules()
prep = [t for t in w.todos if t.title == "[내일 출고] 이수진"]
ok("출고일을 바꾸면 할일 날짜도 옮긴다(새로 만들지 않고)", len(prep) == 1 and prep[0].run_date == T + timedelta(days=7),
   [(t.title, t.run_date) for t in prep])
w.settings.auto_on = False
rows[0].values["status"] = "발주"
w._run_auto_rules()
rows[0].values["status"] = "승인"
w._run_auto_rules()
ok("자동 규칙을 끄면 아무것도 안 한다", "[승인 안내] 김상현" not in [t.title for t in w.todos])
w.settings.auto_on = True
w._sheet_loaded = False
rows.append(row(10, "저장본손님", "가결", T))
n = w._run_auto_rules()
ok("저장해 둔 목록(새로 읽기 전)으로는 돌리지 않는다", n == 0)
w._sheet_loaded = True

w.show()
w.tabs.setCurrentWidget(w.tab_cust)
w.btn_view_renew.click()
for _ in range(10):
    app.processEvents()
ok("[재계약] 을 누르면 재계약 목록", w.cust_stack.currentWidget() is w.renew)
ok("다음에 켤 때도(설정에 남긴다)", w.settings.cust_view == "renew")
r = w.renew.row_of("D-90손님")
ok("만기가 다가오는 고객이 보인다", r >= 0, [auto_rules.short_name(x[0]) for x in w.renew.items])
w.renew.tbl.cellWidget(r, 6).click()
for _ in range(5):
    app.processEvents()
clip = QApplication.clipboard().text()
ok("[멘트 복사] — 이름·만기일을 채운 안내", "D-90손님 고객님" in clip and ed2.isoformat() in clip, clip[:60])
ok("복사하면 '연락함' 으로", renewals.status(w._renewals, e2, ed2) == "연락함")
ok("상태는 파일에(동기화)", renewals.load().get(renewals.key(e2, ed2), {}).get("s") == "연락함")
r = w.renew.row_of("D-90손님")
w.renew.tbl.cellWidget(r, 5).setCurrentText("재계약")
for _ in range(10):
    app.processEvents()
ok("상태를 '재계약' 으로", renewals.status(w._renewals, e2, ed2) == "재계약")
ok("재계약으로 정리하면 남은 만기 할일을 거둔다", "[만기 D-90] D-90손님" not in [t.title for t in w.todos],
   [t.title for t in w.todos])
if os.environ.get("SHOT_DIR"):
    w.grab().save(os.path.join(os.environ["SHOT_DIR"], "renewals_pc.png"))
w.btn_view_list.click()
w.hide()

print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
