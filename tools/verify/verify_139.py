"""v1.3.9 — 팔로업 제목 바꾸기 · 설정창 가로 30%."""
# ⚠️ 경로를 박아 두지 않는다. 예전에는 이 검사들이 작업용 임시 폴더에만 있고
# "/home/user/planner" 를 글자 그대로 들고 있어서, 컨테이너가 다시 뜨면 통째로
# 사라졌다(실제로 두 번 겪었다). 이제 저장소 안에 살고, 자기 위치에서 뿌리를 찾는다.
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]      # tools/verify/x.py → 저장소 뿌리
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
import os as _os
_os.chdir(_ROOT / "python")                          # 'planner/...' 상대경로를 쓰는 검사용
import os, shutil, sys, tempfile
from datetime import date, datetime, timedelta

FAIL = []
def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond: FAIL.append(name)

tmp = tempfile.mkdtemp(); os.environ["APPDATA"] = tmp
os.environ["QT_QPA_PLATFORM"] = os.environ.get("PLAT", "vnc:size=1600x1000")

from planner import config, followup, theme
from planner.models import AppSettings, TodoItem

print("\n[3] 제목 모양")
ok("새 제목", followup.make_title("홍길동", "출고", 1) == "[출고 1개월] 홍길동",
   followup.make_title("홍길동", "출고", 1))
ok("개월 수가 바뀌면 따라간다",
   followup.make_title("홍길동", "출고", 3) == "[출고 3개월] 홍길동")
ok("키워드가 바뀌면 따라간다",
   followup.make_title("홍길동", "계약", 1) == "[계약 1개월] 홍길동")
ok("키워드가 비면 출고", followup.make_title("홍길동", "", 1) == "[출고 1개월] 홍길동")
ok("'팔로업' 이라는 말이 없다", "팔로업" not in followup.make_title("홍길동", "출고", 1))

print("\n[3-2] 이름 꺼내기 — 새 모양·옛 모양 둘 다")
ok("새 모양", followup.followup_name("[출고 1개월] 홍길동") == "홍길동")
ok("새 모양 3개월", followup.followup_name("[출고 3개월] 김상현") == "김상현")
ok("옛 모양", followup.followup_name("[팔로업] 홍길동 (출고 1개월)") == "홍길동")
ok("옛 모양 괄호 없음", followup.followup_name("[팔로업] 홍길동") == "홍길동")
for junk in ("", None, "장보기", "[중요] 회의", "[메모] 전화하기", "출고 1개월"):
    ok(f"{junk!r} 은 팔로업이 아니다", followup.followup_name(junk) == "",
       followup.followup_name(junk))
ok("'[중요] 회의' 를 잘못 잡지 않는다", followup.followup_name("[중요] 회의") == "")
ok("개월이 든 괄호만 인정", followup.followup_name("[출고] 홍길동") == "")

print("\n[3-3] 옛 제목 → 새 제목")
ok("기본", followup.rename_old("[팔로업] 홍길동 (출고 1개월)", "출고", 1)
   == "[출고 1개월] 홍길동")
ok("제목에 적힌 개월을 지킨다",
   followup.rename_old("[팔로업] 홍길동 (출고 1개월)", "출고", 3)
   == "[출고 1개월] 홍길동",
   followup.rename_old("[팔로업] 홍길동 (출고 1개월)", "출고", 3))
ok("제목에 적힌 키워드도 지킨다",
   followup.rename_old("[팔로업] 홍길동 (계약 6개월)", "출고", 1)
   == "[계약 6개월] 홍길동")
ok("괄호가 없으면 설정값으로",
   followup.rename_old("[팔로업] 홍길동", "출고", 2) == "[출고 2개월] 홍길동")
ok("이미 새 모양이면 그대로",
   followup.rename_old("[출고 1개월] 홍길동", "출고", 1) == "[출고 1개월] 홍길동")
ok("팔로업이 아니면 안 건드린다",
   followup.rename_old("장보기", "출고", 1) == "장보기")
ok("빈 제목도 안 터진다", followup.rename_old("", "출고", 1) == ""
   and followup.rename_old(None, "출고", 1) == "")
ok("옛 모양 판별", followup.is_old_title("[팔로업] 홍길동 (출고 1개월)"))
ok("새 모양은 옛 모양이 아니다", not followup.is_old_title("[출고 1개월] 홍길동"))

print("\n[3-4] 새로 만드는 팔로업은 새 제목")
class Ev:
    def __init__(self, uid, summary, start):
        self.uid, self.summary, self.start = uid, summary, start
        self.cal_id, self.event_id, self.has_time = "primary", "e" + uid, False
class Tr:
    def __init__(self): self.done = set(); self.last_scan = None
def S(**kw):
    s = AppSettings()
    s.follow_on = True; s.follow_keyword = "출고"; s.follow_months = 1
    s.follow_ment = "%s 고객님"
    for k, v in kw.items(): setattr(s, k, v)
    return s

base = date.today()
def ev_for(uid, name, off, months=1):
    """target(= 출고 + months개월 - 3일)이 오늘+off 가 되도록 출고일을 잡는다."""
    want = base + timedelta(days=off)
    st = followup.add_months(want + timedelta(days=3), -months)
    return Ev(uid, f"{name} 출고", datetime(st.year, st.month, st.day, 10))

todos = []
added = followup.check_followups(S(), [ev_for("u1", "김상현", 2)], todos, Tr())
ok("새로 만든 제목이 새 모양", added[0].title == "[출고 1개월] 김상현",
   added[0].title)
ok("'팔로업' 이라는 말이 없다", "팔로업" not in added[0].title)
ok("이름이 도로 나온다", followup.followup_name(added[0].title) == "김상현")

# 3개월 설정
t2 = []
a2 = followup.check_followups(S(follow_months=3),
                              [ev_for("u2", "이수민", 2, months=3)], t2, Tr())
ok("개월 설정을 따른다", a2[0].title == "[출고 3개월] 이수민", a2[0].title)

# 옛 제목 할일이 있으면 중복으로 막힌다 (이름으로 보기 때문)
t3 = [TodoItem(title="[팔로업] 김상현 (출고 1개월)", run_date=base)]
a3 = followup.check_followups(S(), [ev_for("u3", "김상현", 2)], t3, Tr())
ok("옛 제목 할일도 중복으로 잡는다", a3 == [], [t.title for t in a3])

print("\n[3-5] 이미 쌓인 할일 제목 바꾸기")
todos4 = [
    TodoItem(title="[팔로업] 김상현 (출고 1개월)", run_date=base),
    TodoItem(title="[팔로업] 이수민 (출고 3개월)", run_date=base, done=True),
    TodoItem(title="[출고 1개월] 박지호", run_date=base),
    TodoItem(title="장보기", run_date=base),
]
n = followup.rename_old_todos(todos4, "출고", 1)
ok("2건을 바꿨다", n == 2, n)
ok("첫 건", todos4[0].title == "[출고 1개월] 김상현", todos4[0].title)
ok("완료한 것도 바꾼다", todos4[1].title == "[출고 3개월] 이수민", todos4[1].title)
ok("개월 수를 지킨다", "3개월" in todos4[1].title)
ok("이미 새 모양은 그대로", todos4[2].title == "[출고 1개월] 박지호")
ok("팔로업 아닌 건 안 건드린다", todos4[3].title == "장보기")
ok("다시 돌려도 안 바뀐다", followup.rename_old_todos(todos4, "출고", 1) == 0)
ok("빈 목록도 안 터진다", followup.rename_old_todos([], "출고", 1) == 0
   and followup.rename_old_todos(None, "출고", 1) == 0)

print("\n[3-6] 캘린더 일정 골라내기")
class CEv:
    def __init__(self, summary, cal_id="primary", event_id="e1"):
        self.summary, self.cal_id, self.event_id = summary, cal_id, event_id
evs = [
    CEv("[팔로업] 김상현 (출고 1개월)"),
    CEv("[출고 1개월] 박지호", event_id="e2"),
    CEv("김상현 출고", event_id="e3"),
    CEv("[팔로업] 최유진 (출고 1개월)", cal_id="", event_id="e4"),   # 못 고침
    CEv("[팔로업] 정민아 (출고 1개월)", event_id=""),                 # 못 고침
]
jobs = followup.old_title_events(evs, "출고", 1)
ok("고칠 건 1개", len(jobs) == 1, [(e.summary, t) for e, t in jobs])
ok("바뀔 제목", jobs[0][1] == "[출고 1개월] 김상현", jobs[0][1])
ok("이미 새 모양은 안 고른다", not any(e.summary.startswith("[출고") for e, _ in jobs))
ok("원래 출고 일정은 안 건드린다",
   not any(e.summary == "김상현 출고" for e, _ in jobs))
ok("고칠 수 없는 건 뺀다(캘린더 ID 없음)",
   not any(e.event_id in ("e4", "") for e, _ in jobs))
ok("빈 목록도 안 터진다", followup.old_title_events([], "출고", 1) == []
   and followup.old_title_events(None, "출고", 1) == [])

print("\n[3-7] 메인 창에 연결됐는가")
import inspect
from PySide6.QtWidgets import QApplication
from planner import google_client, sheets, sync
app = QApplication([]); theme.apply_to_app(app)
config.set_account("tester@example.com")
google_client.GoogleAuth.is_connected = lambda self: False
sync.sync_now = lambda *a, **k: (False, "")
sheets.read_rows = lambda *a, **k: (1, [], [])
from planner.main_window import MainWindow

src = inspect.getsource(MainWindow)
ok("제목 정리를 부른다", "_rename_old_followups" in src)
ok("팔로업 검사 전에 먼저 돈다",
   src.index("self._rename_old_followups()") < src.index("followup.check_followups"))
ok("캘린더도 고친다", "google_client.update_event" in
   inspect.getsource(MainWindow._rename_old_followups))
fsrc = inspect.getsource(followup)
ok("제목은 make_title 한 곳에서만 만든다",
   fsrc.count('f"[') == 1 and 'f"[{' in fsrc,
   [l.strip() for l in fsrc.splitlines() if 'f"[' in l])
# main_window 에 남은 '[팔로업]' 이 설명글뿐인지 (코드에서 쓰는 값이 아닌지) 본다
import ast
from planner import main_window as _mw
_tree = ast.parse(open(_mw.__file__, encoding="utf-8").read())
# clean=False — 들여쓰기를 다듬지 않은 '소스 그대로' 여야 아래 상수와 맞는다
_docs = {ast.get_docstring(n, clean=False) for n in ast.walk(_tree)
         if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef))}
_live = [n.value for n in ast.walk(_tree)
         if isinstance(n, ast.Constant) and isinstance(n.value, str)
         and "[팔로업]" in n.value and n.value not in _docs]
ok("main_window 는 제목을 직접 짓지 않는다 (설명글에만 남음)", _live == [],
   [v[:40] for v in _live])

w = MainWindow()
w.todos.append(TodoItem(title="[팔로업] 한지우 (출고 1개월)", run_date=base))
w.cal_events = []
w._rename_old_followups()
ok("창에서 부르면 할일 제목이 바뀐다",
   w.todos[-1].title == "[출고 1개월] 한지우", w.todos[-1].title)
ok("두 번 불러도 그대로", (w._rename_old_followups(),
                        w.todos[-1].title)[1] == "[출고 1개월] 한지우")

print("\n[4] 설정 창 가로 30% 넓게")
from planner import settings_dialog
class _A:
    def is_connected(self): return False
    def email(self): return "tester@example.com"
s = AppSettings.load(config.data_file("settings.json"))
d = settings_dialog.SettingsDialog(_A(), s, account="tester@example.com")
ok("최소 폭 560 → 728 (30%)", d.minimumWidth() == 728, d.minimumWidth())
ok("여는 폭 620 → 806 (30%)", d.width() == 806, d.width())
ok("예전보다 확실히 넓다", d.width() >= int(620 * 1.29), d.width())
ok("높이는 그대로 화면에 맞춘다", d.height() <= 1000, d.height())

# 좁은 화면에서는 화면 밖으로 안 나간다
from PySide6.QtGui import QGuiApplication
scr = QGuiApplication.primaryScreen().availableGeometry()
ok("화면 안에 든다", d.width() <= scr.width(), (d.width(), scr.width()))

# 부모가 있어도 폭은 그대로
d2 = settings_dialog.SettingsDialog(_A(), s, parent=w, account="tester@example.com")
ok("부모가 있어도 806", d2.width() == 806, d2.width())
ok("안내문이 접히지 않을 만큼 넓다", d2.width() > d2.minimumWidth() - 1)

shutil.rmtree(tmp, ignore_errors=True)
print("\n" + ("실패 %d건: %s" % (len(FAIL), FAIL) if FAIL else "전부 통과"))
sys.exit(1 if FAIL else 0)
