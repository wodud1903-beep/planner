"""자료검색 — 회사 공통 자료를 '내 계정에서만' 고치기 · 내 계정으로 주고받기(v1.29).

지점장: "자료검색에서 회사 공통자료로 들어가 있는 것도 로그인한 계정에 한해서, 내 계정에만
자료수정을 할 수 있게 — 예를 들어 팩스번호를 본인 걸로 지정해서 저장. 업무자료검색에도 동일하게."
  · 고친 것은 계정 폴더 kb_local.json — 회사 원본(시트)·다른 직원에게는 안 간다.
  · 내 구글 드라이브 앱 공간 kb_edits.json 으로 내 다른 PC·업무자료검색(PC·웹)과 맞춘다(같은 파일·같은 규칙).
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))

import json
import os
import tempfile

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from planner import config, google_client, kb, kb_edits, sync  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


FAX_OLD, FAX_NEW = "0504-214-5287", "0504-777-1234"
SHARED = [
    {"category": "심사서류", "finance": "", "title": "개인 심사서류", "tags": "",
     "body": f"1. 신분증\n팩스 {FAX_OLD}", "checklist": ["신분증"]},
    {"category": "캐피탈", "finance": "메리츠캐피탈", "title": "메리츠캐피탈", "tags": "",
     "body": f"담당 팩스 {FAX_OLD}", "checklist": []},
    {"category": "연락처", "finance": "", "title": "보험사 사고접수 연락처", "tags": "", "body": "1588", "checklist": []},
]
kb.save_shared(SHARED)

print("[1] 내 계정에서만 고치기 — 회사 원본은 그대로")
v = kb.local_view()
ok("처음엔 고친 것 없음", len(v) == 3 and not any(x.get("_local") for x in v))
v[1]["body"] = f"담당 팩스 {FAX_NEW}"
ok("저장하면 바뀐 것", kb.set_local(v) is True)
ok("고친 한 건만 · 고친 시각", [r["key"] for r in kb.load_local()] == [("메리츠캐피탈", 0)]
   and kb.load_local()[0]["at"])
ok("회사 원본은 그대로", FAX_OLD in kb.load_shared()[1]["body"])
allv = kb.load_all()
ok("검색 화면 — 고친 것 · '공통 · 내 계정에서 고침'", FAX_NEW in allv[1]["body"]
   and allv[1]["source"] == kb.SRC_LOCAL and allv[0]["source"] == kb.SRC_SHARED
   and kb.SRC_NAMES[kb.SRC_LOCAL] == "공통 · 내 계정에서 고침")
ok("그대로 또 저장하면 안 바뀜", kb.set_local(kb.local_view()) is False)
kb.save_shared([dict(SHARED[0]), dict(SHARED[1], body=f"새 원본\n담당 팩스 {FAX_OLD}"), dict(SHARED[2])])
v = kb.local_view()
ok("회사가 원본을 새로 받아도 내 것은 남는다 · '회사가 또 고침' 표시", FAX_NEW in v[1]["body"]
   and v[1].get("_stale") is True)
v[1]["body"] = v[1]["_base"]["body"]
kb.set_local(v)
ok("원본과 같아지면 지운다(= 되돌림) · 되돌린 표식", not kb.load_local() and "메리츠캐피탈" in kb.load_local_dead())
kb.save_shared(SHARED)

print("[2] 편집 창 — 로그인한 계정이면 누구나 '회사 공통 — 내 계정에서만 고침'")
app = QApplication.instance() or QApplication([])
from planner.kb_tab import KbEditDialog  # noqa: E402

srcs = lambda d: [d.cmb_src.itemData(i) for i in range(d.cmb_src.count())]  # noqa: E731
d = KbEditDialog("staff@gmail.com", None)
ok("직원 계정 — 내 메모 · 내 계정에서만 고침(회사 공통 자체는 없음)", srcs(d) == [kb.SRC_MINE, kb.SRC_LOCAL], srcs(d))
d.reject()
d = KbEditDialog(config.KB_ADMINS[0], None)
ok("관리자 — 회사 공통 · 내 계정에서만 · 내 메모", srcs(d) == [kb.SRC_SHARED, kb.SRC_LOCAL, kb.SRC_MINE], srcs(d))
d.reject()
d = KbEditDialog("", None)
ok("로그인 안 함 — 내 메모만(고친 것이 없으면)", srcs(d) == [kb.SRC_MINE], srcs(d))
d.reject()
d = KbEditDialog("staff@gmail.com", None, select={"source": kb.SRC_SHARED, "title": "개인 심사서류",
                                                  "category": "심사서류"})
ok("자료검색에서 보던 회사 자료로 열면 그 묶음 · 그 자료", d.cmb_src.currentData() == kb.SRC_LOCAL
   and d.ed_title.text() == "개인 심사서류")
ok("회사 자료는 추가·삭제 대신 [회사 자료로 되돌리기]", not d.b_add.isEnabled() and not d.b_del.isEnabled()
   and not d.b_revert.isHidden())
d.txt_body.setPlainText(f"1. 신분증\n팩스 {FAX_NEW}")
d._ok()
got = (d.shared, list(d.local), d.mine)
ok("[저장] — 고친 것", kb.set_local(got[1]) is True and FAX_NEW in kb.load_all()[0]["body"])
ok("목록에 '(내 계정에서 고침)'", "(내 계정에서 고침)" in d._row_text(d.local[0]), d._row_text(d.local[0]))
d2 = KbEditDialog("staff@gmail.com", None, select={"source": kb.SRC_LOCAL, "title": "개인 심사서류"})
d2.revert(ask=False)
ok("[회사 자료로 되돌리기] — 원본으로", FAX_OLD in d2.local[0]["body"])
ok("되돌린 것을 저장하면 고친 것이 없어진다", kb.set_local(d2.local) and not kb.load_local())
d2.reject()

print("[3] 내 계정으로 주고받기 — kb_edits.json(업무자료검색 PC·웹과 같은 파일)")
DRIVE = {}


def find(auth, name):
    return name if name in DRIVE else None


def read(auth, fid):
    if DRIVE.get("__fail"):
        raise google_client.GoogleError("boom")
    return DRIVE[fid]


WRITES = []


def write(auth, name, content):
    WRITES.append(name)
    DRIVE[name] = content
    return name


google_client.drive_find, google_client.drive_read, google_client.drive_write = find, read, write
v = kb.local_view()
v[1]["body"] = f"담당 팩스 {FAX_NEW}"
v[2]["body"] = "내 보험 연락처 010"
kb.set_local(v)
changed = kb_edits.sync(None)
ef = json.loads(DRIVE[kb_edits.FILE])
ok("심사서류 3종 말고도 모든 회사 자료를 올린다", {"메리츠캐피탈", "보험사 사고접수 연락처"} <= set(ef["edits"])
   and FAX_NEW in ef["edits"]["메리츠캐피탈"]["item"]["body"] and ef["v"] == 1, list(ef["edits"]))
ok("앞에서 되돌린 것도 '되돌림' 으로 올린다(item=null)", ef["edits"]["개인 심사서류"]["item"] is None)
ok("올리기만 했으면 받은 것 없음", changed == [])
n = len(WRITES)
kb_edits.sync(None)
ok("바뀐 게 없으면 다시 쓰지 않는다", len(WRITES) == n)
# 다른 곳(업무자료검색 웹)에서 개인 심사서류를 고치고, 메리츠는 되돌림
ef["edits"]["개인 심사서류"] = {"item": {"title": "개인 심사서류", "body": "웹에서 고친 팩스 0504-555"},
                                "base": {"title": "개인 심사서류", "body": SHARED[0]["body"]}, "at": "2099-01-01T00:00:00Z"}
ef["edits"]["메리츠캐피탈"] = {"item": None, "base": None, "at": "2099-01-01T00:00:01Z"}
DRIVE[kb_edits.FILE] = json.dumps(ef, ensure_ascii=False)
mt = os.path.getmtime(config.data_file(kb.LOCAL_FILE))
changed = kb_edits.sync(None)
allv = {x["title"]: x for x in kb.load_all()}
ok("다른 곳에서 고친 것을 받는다(체크리스트 등은 회사 원본 것)", "웹에서 고친" in allv["개인 심사서류"]["body"]
   and allv["개인 심사서류"]["source"] == kb.SRC_LOCAL and allv["개인 심사서류"]["checklist"] == ["신분증"])
ok("다른 곳에서 되돌린 것은 여기도 되돌린다", allv["메리츠캐피탈"]["source"] == kb.SRC_SHARED
   and FAX_OLD in allv["메리츠캐피탈"]["body"])
ok("받은 제목을 알려 준다", sorted(changed) == ["개인 심사서류", "메리츠캐피탈"], changed)
ok("웹 원본 모양({제목, 본문})이어도 '회사가 또 고침' 으로 보지 않는다", not allv["개인 심사서류"].get("_stale"))
os.utime(config.data_file(kb.LOCAL_FILE), (mt, mt))
kb_edits.sync(None)
ok("받은 뒤 다시 맞춰도 파일을 또 쓰지 않는다(동기화가 맴돌지 않게)",
   os.path.getmtime(config.data_file(kb.LOCAL_FILE)) == mt)
DRIVE["__fail"] = True
n = len(WRITES)
try:
    kb_edits.sync(None)
    ok("못 읽으면 EditsError", False)
except kb_edits.EditsError:
    ok("못 읽으면 EditsError · 쓰지 않는다", len(WRITES) == n)
DRIVE.pop("__fail")
DRIVE[kb_edits.FILE] = "{깨짐"
try:
    kb_edits.sync(None)
    ok("깨진 파일이면 EditsError", False)
except kb_edits.EditsError:
    ok("깨진 파일이면 덮어쓰지 않는다", DRIVE[kb_edits.FILE] == "{깨짐")

print("[4] 일정관리기 동기화에 붙어 돈다")
import inspect  # noqa: E402
ok("받기·올리기·지금 동기화 모두 kb_edits 도 맞춘다", all("_kb_edits(auth)" in inspect.getsource(f)
                                                     for f in (sync.pull, sync.push, sync.sync_now)))
ok("실패해도 일정관리기 동기화는 그대로(따로 감싼다)", "except Exception" in inspect.getsource(sync._kb_edits))
src = (_ROOT / "python" / "planner" / "main_window.py").read_text(encoding="utf-8")
ok("고쳐 저장하면 곧 올린다(v1.30 — 그 자리에서 내 계정으로)",
   "self.tab_kb.on_local_saved = self._on_kb_local_saved" in src)

print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
