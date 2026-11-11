"""동기화 — 시트 공통 자료 받기·올리기, 일정관리기 묶음의 '내 메모' 칸만 고치기.

가장 중요한 것: **일정관리기 묶음의 다른 칸(할일·멘트·고객메모…)을 한 글자도 바꾸지 않는다.**
그리고 묶음을 못 읽으면 쓰지 않는다. 마지막에 일정관리기의 실제 sync 코드에 우리가
쓴 묶음을 넣어 보고, 일정관리기가 메모를 받아 가는지까지 본다.
"""
import pathlib as _pl
import sys as _sys

_HERE = _pl.Path(__file__).resolve().parent
_sys.path.insert(0, str(_HERE.parent))
_sys.path.insert(0, str(_HERE))

import json  # noqa: E402
import os  # noqa: E402
import tempfile  # noqa: E402

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fake_google import FakeAuth, FakeGoogle  # noqa: E402
from kbsearch import config, kb, kb_files, sheets_kb, sync  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name
          + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


def fresh():
    os.environ["APPDATA"] = tempfile.mkdtemp()
    return FakeGoogle().install()


def memo(title, body="본문", files=None):
    it = {"category": "기타", "finance": "", "title": title, "tags": "", "body": body,
          "checklist": []}
    if files:
        it["files"] = files
    return it


PLANNER_FILES = {
    "todos.json": json.dumps([{"title": "할일1"}], ensure_ascii=False),
    "greetings.json": json.dumps([{"name": "인사"}], ensure_ascii=False),
    "customer_notes.json": json.dumps({"u1": [{"text": "메모"}]}, ensure_ascii=False),
}


def planner_bundle(mine_items, mine_time="2026-01-01T00:00:00Z"):
    files = dict(PLANNER_FILES)
    files["kb_mine.json"] = json.dumps(mine_items, ensure_ascii=False, indent=2)
    times = {n: "2025-12-31T10:00:00Z" for n in PLANNER_FILES}
    times["kb_mine.json"] = mine_time
    return {"updatedAt": "2025-12-31T10:00:00Z", "files": files, "times": times}


def put_bundle(g, b):
    g.appdata["a0"] = {"name": config.PLANNER_SYNC_FILE,
                       "content": json.dumps(b, ensure_ascii=False)}


def get_bundle(g):
    return json.loads(g.appdata["a0"]["content"])


# ---------------------------------------------------------------------------
print("[1] 로그인 없이 — 기본 자료 · 일정관리기 공통 자료 가져오기")
fresh()
ok("받은 적 없으면 기본 자료", len(kb.load_shared()) == len(kb.SAMPLE))
fresh()
pl = config.appdata() / "Planner" / "accounts" / "x@y.com"
pl.mkdir(parents=True)
(pl / "kb_shared.json").write_text(json.dumps([memo("회사자료A"), memo("회사자료B")],
                                              ensure_ascii=False), encoding="utf-8")
got = kb.load_shared()
ok("이 PC 일정관리기 공통 자료를 가져온다", [x["title"] for x in got] == ["회사자료A", "회사자료B"])
ok("가져온 것은 이 프로그램 폴더에 남는다", kb.has_shared_cache())
ok("내 메모는 가져오지 않는다", kb.load_mine() == [])

print("[2] 내 메모 — 지우기·이름 바꾸기 표시")
fresh()
kb.save_mine([memo("가"), memo("나")])
kb.save_mine([memo("가")])
ok("지운 제목을 기록", kb.deleted_titles() == {"나"})
kb.save_mine([memo("가 새이름")])
ok("이름 바꾼 옛 제목도 기록", kb.deleted_titles() == {"나", "가"})
kb.save_mine([memo("가 새이름"), memo("나")])
ok("같은 제목을 다시 만들면 표시를 지운다", kb.deleted_titles() == {"가"})
ok("고치면 동기화 점이 켜진다", kb.load_meta().get("pending") is True)

print("[3] 받기 + 내 메모 합치기 — 일정관리기 칸은 그대로")
g = fresh()
g.kb_rows = [sheets_kb.KB_HEADER[:6], ["캐피탈", "신한", "신한 전자약정", "", "본문1", ""],
             ["심사서류", "", "개인 심사서류", "", "본문2", "등본\n초본"]]
g.kb_g = ["", "", ""]
original = planner_bundle([memo("일정관리기에서 쓴 메모")])
put_bundle(g, original)
kb.save_mine([memo("여기서 쓴 메모")])
res = sync.run(FakeAuth())
ok("공통 자료 받음", res.shared_pulled == 2 and kb.load_shared()[1]["checklist"] == ["등본", "초본"])
titles = [x["title"] for x in kb.load_mine()]
ok("양쪽 메모를 다 가진다", set(titles) == {"여기서 쓴 메모", "일정관리기에서 쓴 메모"}, titles)
ok("새로 들어온 메모 수", res.mine_added == 1, res.mine_added)
b = get_bundle(g)
ok("묶음에 합친 메모", {x["title"] for x in json.loads(b["files"]["kb_mine.json"])} == set(titles))
ok("일정관리기 다른 칸은 한 글자도 안 바뀜",
   all(b["files"][n] == original["files"][n] for n in PLANNER_FILES))
ok("다른 칸 시각도 그대로", all(b["times"][n] == original["times"][n] for n in PLANNER_FILES))
ok("묶음 시각(updatedAt)은 건드리지 않는다", b["updatedAt"] == original["updatedAt"])
ok("내 메모 칸 시각은 새로", b["times"]["kb_mine.json"] > original["times"]["kb_mine.json"])
ok("동기화 점이 꺼진다", kb.load_meta().get("pending") is False)
ok("계정을 기억", kb.load_meta().get("account") == "me@example.com")

print("[4] 바뀐 게 없으면 묶음을 다시 쓰지 않는다")
before = g.appdata_writes
sync.run(FakeAuth())
ok("쓰기 없음", g.appdata_writes == before, g.appdata_writes - before)

print("[5] 지운 메모는 되살리지 않는다")
kb.save_mine([x for x in kb.load_mine() if x["title"] != "일정관리기에서 쓴 메모"])
sync.run(FakeAuth())
ok("이 PC 에서 안 돌아옴", "일정관리기에서 쓴 메모" not in [x["title"] for x in kb.load_mine()])
ok("묶음에서도 빠짐", "일정관리기에서 쓴 메모" not in get_bundle(g)["files"]["kb_mine.json"])

print("[6] 원격이 더 최근이면 같은 제목은 원격 내용")
g = fresh()
kb.save_mine([memo("공용", body="옛 내용")])
put_bundle(g, planner_bundle([memo("공용", body="새 내용")], mine_time="2099-01-01T00:00:00Z"))
sync.run(FakeAuth())
ok("원격 새 내용이 이김", kb.load_mine()[0]["body"] == "새 내용")

print("[7] 묶음을 못 읽으면 절대 쓰지 않는다")
for label, setup in [
    ("찾기 실패(500)", lambda gg: setattr(gg, "appdata_find_code", 500)),
    ("받기 실패(500)", lambda gg: setattr(gg, "appdata_read_code", 500)),
    ("깨진 내용", lambda gg: gg.appdata["a0"].update(content="{깨짐")),
]:
    g = fresh()
    put_bundle(g, planner_bundle([memo("남의 것")]))
    keep = g.appdata["a0"]["content"]
    setup(g)
    kb.save_mine([memo("내 것")])
    try:
        sync.run(FakeAuth())
        raised = False
    except sync.SyncError:
        raised = True
    ok(f"{label} → 멈춤", raised)
    ok(f"{label} → 묶음 안 씀", g.appdata_writes == 0 and
       (g.appdata["a0"]["content"] == keep or label == "깨진 내용"))
    ok(f"{label} → 이 PC 메모 그대로", [x["title"] for x in kb.load_mine()] == ["내 것"])

print("[8] 묶음이 정말 없으면 새로 만든다(내 메모 칸만)")
g = fresh()
kb.save_mine([memo("첫 메모")])
sync.run(FakeAuth())
ok("새 묶음", len(g.appdata) == 1)
b = json.loads(next(iter(g.appdata.values()))["content"])
ok("내 메모 칸만", list(b["files"]) == ["kb_mine.json"] and "kb_mine.json" in b["times"])

print("[9] 이 PC 에만 둔 첨부 — 올린 뒤에 내보낸다")
g = fresh()
png = b"\x89PNG\r\n\x1a\n" + b"x" * 200
att = kb_files.store_local(png, "그림.png")
ok("로그인 없이 넣으면 local- id", att["id"].startswith(kb_files.LOCAL_PREFIX))
ok("이 PC 에 있다", kb_files.cached(att) is not None)
kb.save_mine([memo("첨부 메모", files=[att]), memo("같은 그림", files=[dict(att)])])
res = sync.run(FakeAuth())
mine = kb.load_mine()
ids = [f["id"] for it in mine for f in it.get("files", [])]
ok("진짜 id 로 바뀜", ids and not any(i.startswith("local-") for i in ids), ids)
ok("같은 그림은 한 번만 올림", res.uploaded == 1 and len(set(ids)) == 1, res.uploaded)
ok("내 메모 첨부는 공개하지 않는다", not g.public)
ok("묶음에 local- 이 실리지 않음", "local-" not in next(iter(g.appdata.values()))["content"])
ok("이 PC 사본 정리", not (kb_files.cache_dir() / att["id"]).exists())
ok("올린 것은 새 id 로 캐시", kb_files.cached(mine[0]["files"][0]) is not None)

print("[10] 관리자 — 이 PC 에서 고친 공통 자료를 시트로")
g = fresh()
att = kb_files.store_local(png, "공지.png")
kb.save_shared([memo("공지", files=[att]), memo("절차")], edited=True)
ok("고치면 올릴 것 표시", kb.load_meta().get("shared_dirty") is True)
res = sync.run(FakeAuth("wodud1903@gmail.com"), push_shared=True)
ok("올림", res.shared_pushed == 2)
ok("공통 첨부는 공개", len(g.public) == 1)
ok("시트 G열에 진짜 id", g.put_values and "local-" not in json.dumps(g.put_values, ensure_ascii=False)
   and json.loads(g.put_values[1][6])["files"][0]["id"] in g.public)
ok("표시 지움", kb.load_meta().get("shared_dirty") is False)

print("[11] 관리자가 아니면 올리지 않는다")
g = fresh()
g.kb_rows = [["캐피탈", "", "시트 것", "", "", ""]]
kb.save_shared([memo("고친 것")], edited=True)
res = sync.run(FakeAuth("staff@example.com"), push_shared=True)
ok("시트 쓰기 없음", g.put_values is None and res.shared_pushed == -1)
ok("시트 내용으로 바뀜", [x["title"] for x in kb.load_shared()] == ["시트 것"])

print("[12] 시트 오류는 알린다 · 탭이 없으면 이 PC 자료를 둔다")
g = fresh()
g.sheet_code = 403
g.public_csv = "html"           # 공개로도 못 읽는 경우
try:
    sync.run(FakeAuth())
    msg = ""
except sync.SyncError as e:
    msg = str(e)
ok("403 · 공개도 안 됨 → 알림", "403" in msg, msg[:60])
g = fresh()
g.sheet_code = 403
g.kb_rows = [["캐피탈", "", "공개로 받은 것", "", "", ""]]
res = sync.run(FakeAuth("notinvited@example.com"))
ok("403 이어도 시트가 공개면 공개로 받는다", res.shared_pulled == 1
   and [x["title"] for x in kb.load_shared()] == ["공개로 받은 것"])
g = fresh()
g.tab = False
kb.save_shared([memo("이 PC 공통")])
res = sync.run(FakeAuth())
ok("탭 없음 → 그대로 두고 안내", [x["title"] for x in kb.load_shared()] == ["이 PC 공통"]
   and res.shared_note)

print("[12-2] 로그인 없이 — 공개 CSV 로 공통 자료 받기")
g = fresh()
g.kb_rows = [sheets_kb.KB_HEADER[:6],
             ["캐피탈", "메리츠", "메리츠캐피탈", "", "본문\n여러 줄, 쉼표 \"따옴표\"", "등본\n초본"]]
att = {"id": "PUB1", "name": "법인전자약정1.png", "mime": "image/png", "size": 9}
g.kb_g = ["", json.dumps({"title": "메리츠캐피탈", "files": [att]}, ensure_ascii=False)]
got = sheets_kb.read_kb_public()
ok("로그인 없이 받음 — 여러 줄 본문·따옴표 그대로", got and got[0]["body"] == '본문\n여러 줄, 쉼표 "따옴표"', got)
ok("첨부(G열)도 함께", got[0].get("files") == [att])
ok("체크리스트", got[0]["checklist"] == ["등본", "초본"])
ok("인증 머리 없이 요청", g.count("GET", "docs.google.com") == 1)
r = sync.apply_public(got)
ok("이 PC 에 맞춤", r["changed"] and [x["title"] for x in kb.load_shared()] == ["메리츠캐피탈"])
ok("받은 때를 적는다", bool(kb.load_meta().get("shared_at")))
ok("같으면 다시 쓰지 않는다", sync.apply_public(sheets_kb.read_kb_public())["changed"] is False)
kb.save_shared([memo("관리자가 고친 것")], edited=True)
r = sync.apply_public(sheets_kb.read_kb_public())
ok("관리자가 고친 게 남아 있으면 덮어쓰지 않는다", r["skipped"] == "dirty"
   and kb.load_shared()[0]["title"] == "관리자가 고친 것")
kb.update_meta(shared_dirty=False)
ok("시트가 비었으면 그대로 둔다", sync.apply_public(None)["skipped"] == "empty"
   and kb.load_shared()[0]["title"] == "관리자가 고친 것")
for mode, why in (("html", "잠긴 시트(로그인 화면)"), ("firsttab", "다른 탭(수당율)이 옴")):
    g.public_csv = mode
    try:
        sheets_kb.read_kb_public()
        hit = False
    except sheets_kb.NotPublic:
        hit = True
    ok(f"{why} → 받지 않음", hit)
g.public_csv = "ok"
g.tab = False
ok("탭이 없으면 None", sheets_kb.read_kb_public() is None)

print("[13] 미뤄 둔 첨부 휴지통 · 이름 바꾸기")
g = fresh()
kb.save_mine([memo("남은 것", files=[{"id": "keep1", "name": "a.png", "mime": "image/png", "size": 1}])])
kb.queue_remote(trash=["gone1", "keep1"], renames=[("ren1", "새이름.png")])
sync.run(FakeAuth())
ok("뺀 것만 휴지통", g.trashed == ["gone1"], g.trashed)
ok("이름 바꾸기", ("ren1", "새이름.png") in g.renamed)
ok("대기열 비움", not kb.load_meta().get("trash") and not kb.load_meta().get("renames"))

print("[14] 계정을 바꿔 비우기")
kb.save_mine([memo("A 계정 것")])
sync.reset_mine_for_account()
ok("메모 비움 · 계정 잊음", kb.load_mine() == [] and not kb.load_meta().get("account"))

print("[15] 일정관리기가 우리가 쓴 묶음을 받아 간다(일정관리기 실제 코드)")
g = fresh()
put_bundle(g, planner_bundle([memo("원래 메모")]))
kb.save_mine([memo("업무자료검색에서 쓴 메모")])
sync.run(FakeAuth())
ours = get_bundle(g)
_sys.path.insert(0, str(_HERE.parents[1] / "python"))
from planner import config as pconfig, sync as psync  # noqa: E402
pconfig.set_account("me@example.com")
acc = pconfig.data_dir()
(acc / "todos.json").write_text(PLANNER_FILES["todos.json"], encoding="utf-8")
(acc / "kb_mine.json").write_text(json.dumps([memo("원래 메모")], ensure_ascii=False), encoding="utf-8")
os.utime(acc / "kb_mine.json", (1735689600, 1735689600))      # 2025-01-01 — 묶음보다 옛것
psync.apply_remote(ours)
pm = json.loads((acc / "kb_mine.json").read_text(encoding="utf-8"))
ok("일정관리기가 새 메모를 받음", {x["title"] for x in pm} == {"원래 메모", "업무자료검색에서 쓴 메모"})
ok("일정관리기 할일은 그대로", (acc / "todos.json").read_text(encoding="utf-8") == PLANNER_FILES["todos.json"])
out = psync.merged_bundle(ours)
ok("일정관리기가 다시 올려도 우리 메모가 남는다",
   "업무자료검색에서 쓴 메모" in out["files"]["kb_mine.json"])

print("[16] 이 PC 에서만 고친 공통 자료(팩스번호 등) — 시트로 안 가고, 새로 받아도 남는다")
g = fresh()
FAX_OLD, FAX_NEW = "0504-214-5287", "0504-000-1111"
base = {"category": "심사서류", "finance": "", "title": "개인 심사서류", "tags": "",
        "body": f"1. 면허증\n팩스- {FAX_OLD}", "checklist": ["면허증"]}
kb.save_shared([base, memo("메리츠캐피탈", "메리츠 본문")])
v = kb.local_view()
ok("처음엔 고친 것 없음", len(v) == 2 and not any(x.get("_local") for x in v))
img = b"\x89PNG\r\n\x1a\n" + b"L" * 200
la = kb_files.store_local(img, "내 명함.png")
e = dict(v[0])
e["body"] = f"1. 면허증\n팩스- {FAX_NEW}"
e["files"] = [la]
ok("저장하면 바뀐 것", kb.set_local([e, v[1]]) is True)
ok("고친 한 건만 적힘", [r["key"] for r in kb.load_local()] == [("개인 심사서류", 0)])
ok("원본(공통 자료)은 그대로", FAX_OLD in kb.load_shared()[0]["body"])
allv = kb.load_all()
ok("검색 화면은 고친 것 · '이 PC 에서 고침'", FAX_NEW in allv[0]["body"]
   and allv[0]["source"] == kb.SRC_LOCAL and allv[1]["source"] == kb.SRC_SHARED)
ok("그대로 또 저장하면 안 바뀜", kb.set_local(kb.local_view()) is False)
m = kb.load_meta()
ok("올릴 것·동기화 점으로 치지 않는다", not m.get("shared_dirty") and not m.get("pending"))

g.kb_rows = [["심사서류", "", "개인 심사서류", "", f"1. 면허증\n2. 등본\n팩스- {FAX_OLD}", "면허증"],
             ["기타", "", "메리츠캐피탈", "", "메리츠 본문", ""]]
r = sync.apply_public(sheets_kb.read_kb_public())
v = kb.local_view()
ok("회사가 고친 원본을 받아도 이 PC 에서 고친 것이 남는다",
   r["changed"] and FAX_NEW in v[0]["body"] and v[0].get("_local"))
ok("'회사가 또 고침' 표시", v[0].get("_stale") is True)
ok("이 PC 첨부를 지우지 않는다", kb_files.cached(la) is not None)
ok("손대지 않고 저장하면 표시가 남는다", kb.set_local(v) is False and kb.local_view()[0].get("_stale"))
v = kb.local_view()
v[0]["_ack"] = True
ok("안내를 보고 저장하면 지금 원본을 본 것으로", kb.set_local(v) is True
   and not kb.local_view()[0].get("_stale") and FAX_NEW in kb.local_view()[0]["body"])

put_bundle(g, planner_bundle([]))
kb.save_mine([memo("같은 그림 메모", files=[dict(la)])])
sync.run(FakeAuth())
ok("직원 동기화 — 시트에 쓰지 않는다", g.put_values is None)
ok("동기화 뒤에도 이 PC 에서 고친 것", FAX_NEW in kb.local_view()[0]["body"])
ok("내 메모의 같은 그림은 올리되 이 PC 사본은 남긴다",
   not kb_files.is_local(kb.load_mine()[0]["files"][0]) and kb_files.cached(la) is not None)
sync.reset_mine_for_account()
ok("계정을 바꿔 메모를 비워도 이 PC 첨부는 남는다", kb_files.cached(la) is not None)
kb.save_shared(kb.load_shared(), edited=True)
sync.run(FakeAuth(config.KB_ADMINS[0]), push_shared=True)
sent = json.dumps(g.put_values, ensure_ascii=False)
ok("관리자가 올려도 시트로 가는 것은 원본", g.put_values and FAX_NEW not in sent and FAX_OLD in sent)

g.kb_rows = [["심사서류", "", "개인 심사서류 안내", "", "새 제목", ""]]
sync.apply_public(sheets_kb.read_kb_public())
v = kb.local_view()
ok("회사가 제목을 바꾸면 고친 것을 따로 보여 준다(잃지 않는다)",
   [x["title"] for x in v] == ["개인 심사서류 안내", "개인 심사서류"] and v[1].get("_orphan"))
ok("원본이 없어져도 첨부는 남는다", kb_files.cached(la) is not None)
kb.set_local([v[0]])                    # 편집 창의 [회사 자료로 되돌리기] = 목록에서 뺌
ok("되돌리면 지운다", kb.load_local() == [] and len(kb.local_view()) == 1)
kb.save_shared([base])
v = kb.local_view()
e = dict(v[0])
e["body"] = "고침"
kb.set_local([e])
v = kb.local_view()
v[0] = {**v[0]["_base"], "_key": v[0]["_key"], "_base": v[0]["_base"]}
ok("원본과 같아지면 지운다", kb.set_local(v) is True and kb.load_local() == [])
config.data_file(kb.LOCAL_FILE).write_text("[{\"key\": 3}, \"x\", {}]", encoding="utf-8")
ok("깨진 파일은 무시", kb.load_local() == [] and len(kb.local_view()) == 1)

print("[17] 지운 표식 — 일정관리기와 서로 지운 메모를 되살리지 않는다(kb-v1.4.0 · 일정관리기 v1.26)")
g = fresh()
kb.save_mine([memo("남길 메모"), memo("일정관리기에서 지울 메모")])
b0 = planner_bundle([memo("남길 메모"), memo("일정관리기에서 지울 메모")])
put_bundle(g, b0)
sync.run(FakeAuth())
# 일정관리기에서 지웠다 — 묶음의 메모에서 빠지고 지운 표식이 실렸다(인사말 표식도 함께)
b = get_bundle(g)
b["files"]["kb_mine.json"] = json.dumps([memo("남길 메모")], ensure_ascii=False)
b["files"]["deleted.json"] = json.dumps({"kb_mine.json": {"일정관리기에서 지울 메모": "2099-01-01T00:00:00Z"},
                                         "greetings.json": {"옛 채널": "2099-01-01T00:00:00Z"}},
                                        ensure_ascii=False)
b["times"]["kb_mine.json"] = "2000-01-01T00:00:00Z"     # 이 PC 쪽이 더 최근인 척(예전엔 여기서 되살아났다)
put_bundle(g, b)
sync.run(FakeAuth())
ok("일정관리기에서 지운 메모가 이 PC 에서도 사라진다", [x["title"] for x in kb.load_mine()] == ["남길 메모"],
   [x["title"] for x in kb.load_mine()])
ok("묶음에도 되살려 보내지 않는다", "일정관리기에서 지울 메모" not in get_bundle(g)["files"]["kb_mine.json"])
ok("일정관리기의 다른 표식(인사말)은 그대로 싣는다",
   "옛 채널" in json.loads(get_bundle(g)["files"]["deleted.json"]).get("greetings.json", {}))
# 이 PC 에서 지웠다 → 표식이 묶음에 실리고, 일정관리기(실제 코드)도 지운다
kb.save_mine([memo("남길 메모"), memo("여기서 지울 메모")])
sync.run(FakeAuth())
kb.save_mine([memo("남길 메모")])
sync.run(FakeAuth())
tb = json.loads(get_bundle(g)["files"]["deleted.json"])
ok("이 PC 에서 지운 제목이 표식으로 묶음에", "여기서 지울 메모" in tb.get("kb_mine.json", {}), tb)
from planner import config as pconfig, sync as psync  # noqa: E402
pconfig.set_account("tomb@example.com")
acc = pconfig.data_dir()
(acc / "kb_mine.json").write_text(json.dumps([memo("남길 메모"), memo("여기서 지울 메모")], ensure_ascii=False),
                                  encoding="utf-8")
os.utime(acc / "kb_mine.json", (4102444800, 4102444800))   # 2100 — 일정관리기 쪽이 더 최근이어도
psync.apply_remote(get_bundle(g))
pm = [x["title"] for x in json.loads((acc / "kb_mine.json").read_text(encoding="utf-8"))]
ok("일정관리기(실제 코드)도 이 PC 에서 지운 메모를 뺀다", pm == ["남길 메모"], pm)
# 같은 제목으로 다시 만들면(고친 시각이 늦다) 산다
at0 = [x for x in kb.load_mine() if x["title"] == "남길 메모"][0].get("at")
kb.save_mine([dict([x for x in kb.load_mine() if x["title"] == "남길 메모"][0]),
              memo("여기서 지울 메모", body="다시 만듦")])
it = [x for x in kb.load_mine() if x["title"] == "여기서 지울 메모"][0]
ok("다시 만든 메모에는 고친 시각(at)", bool(it.get("at")))
tb["kb_mine.json"]["여기서 지울 메모"] = "2000-01-01T00:00:00Z"   # 지운 때가 더 옛날
bb = get_bundle(g)
bb["files"]["deleted.json"] = json.dumps(tb, ensure_ascii=False)
put_bundle(g, bb)
sync.run(FakeAuth())
ok("다시 만든 메모는 지워지지 않는다", "여기서 지울 메모" in [x["title"] for x in kb.load_mine()])
ok("안 바뀐 메모의 고친 시각은 그대로", at0 and
   [x for x in kb.load_mine() if x["title"] == "남길 메모"][0].get("at") == at0)

print("[18] 고친 심사서류 3종 — 내 구글 계정으로 웹 업무자료검색과 주고받기(kb-v1.6.0)")
import shutil  # noqa: E402
import subprocess  # noqa: E402

g = fresh()
put_bundle(g, planner_bundle([]))
FAX_OLD = "0504-214-5287"
docs = [{"category": "심사서류", "finance": "", "title": t, "tags": "", "checklist": ["신분증"],
         "body": f"1. 신분증\n팩스 {FAX_OLD}"} for t in kb.SYNC_TITLES]
kb.save_shared(docs + [memo("메리츠캐피탈", "메리츠 본문")])


def edits_file():
    for f in g.appdata.values():
        if f["name"] == sync.EDITS_FILE:
            return json.loads(f["content"])
    return None


def set_body(title, body):
    v = kb.local_view()
    for x in v:
        if x["title"] == title or (x.get("_key") or ("",))[0] == title:
            x["body"] = body
    return kb.set_local(v)


T1, T2, T3 = kb.SYNC_TITLES
set_body(T1, "1. 신분증\n팩스 0504-000-1111")
set_body("메리츠캐피탈", "나만 쓰는 메리츠")
r1 = kb.load_local()
ok("고친 것에 고친 시각(at)", all(r.get("at") for r in r1))
w0 = g.appdata_writes
res = sync.run(FakeAuth())
ef = edits_file()
ok("[동기화] 하면 드라이브 앱 공간의 kb_edits.json 에 올린다", ef and ef["v"] == 1
   and "0504-000-1111" in ef["edits"][T1]["item"]["body"])
ok("심사서류 말고 고친 것도 내 계정으로 올린다(kb-v1.7.0)", ef["edits"].get("메리츠캐피탈", {}).get("item", {}).get("body")
   == "나만 쓰는 메리츠" and len(ef["edits"]) == 2, list(ef["edits"]))
ok("일정관리기 묶음은 그대로(따로 쓰는 파일)", "kb_edits.json" not in get_bundle(g)["files"])
w1 = g.appdata_writes
sync.run(FakeAuth())
ok("바뀐 게 없으면 다시 쓰지 않는다", g.appdata_writes == w1, (w0, w1, g.appdata_writes))

# 웹에서 개인사업자 심사서류를 고치고, 개인 심사서류는 되돌림(웹 모양 — base 는 {title, body})
fid = next(i for i, f in g.appdata.items() if f["name"] == sync.EDITS_FILE)
o = edits_file()
o["edits"][T2] = {"item": {"category": "심사서류", "finance": "", "title": T2, "tags": "",
                           "body": "1. 신분증\n팩스 0504-555-6666"},
                  "base": {"title": T2, "body": f"1. 신분증\n팩스 {FAX_OLD}"}, "at": "2026-01-01T00:00:00Z"}
o["edits"][T1] = {"item": None, "base": None, "at": "2099-01-01T00:00:01Z"}
g.appdata[fid]["content"] = json.dumps(o, ensure_ascii=False)
changed = sync.sync_edits(FakeAuth())
v = {x["title"]: x for x in kb.local_view()}
ok("웹에서 고친 것을 받는다", FAX_OLD not in v[T2]["body"] and "0504-555-6666" in v[T2]["body"]
   and v[T2].get("_local"), changed)
ok("받은 제목을 알려 준다", sorted(changed) == sorted([T1, T2]), changed)
ok("체크리스트 등은 회사 원본 것을 그대로", v[T2].get("checklist") == ["신분증"])
ok("웹 원본 모양({제목, 본문})이어도 '회사가 또 고침' 으로 보지 않는다", not v[T2].get("_stale"))
ok("웹에서 되돌린 것은 이 PC 도 되돌린다", not v[T1].get("_local") and FAX_OLD in v[T1]["body"])
ok("내가 고친 다른 자료도 그대로", v["메리츠캐피탈"]["body"] == "나만 쓰는 메리츠")
w2 = g.appdata_writes
sync.sync_edits(FakeAuth())
ok("받은 뒤 다시 맞춰도 오가며 다시 쓰지 않는다", g.appdata_writes == w2)

# 이 PC 에서 되돌리면 웹에도 되돌림을 전한다
v = kb.local_view()
for x in v:
    if x.get("_key") == (T2, 0):
        x.update({k: x["_base"][k] for k in ("body",)})
kb.set_local(v)
ok("되돌린 표식", T2 in kb.load_local_dead())
sync.sync_edits(FakeAuth())
ok("되돌림도 올린다(item=null · 나중 시각)", edits_file()["edits"][T2]["item"] is None
   and edits_file()["edits"][T2]["at"] > "2026")
# 웹이 더 나중에 같은 자료를 다시 고침 → 받음 / 이 PC 가 나중이면 올림
o = edits_file()
o["edits"][T3] = {"item": {"title": T3, "body": "옛 웹"}, "base": None, "at": "2000-01-01T00:00:00Z"}
g.appdata[fid]["content"] = json.dumps(o, ensure_ascii=False)
set_body(T3, "1. 신분증\n팩스 0504-999-0000")
sync.sync_edits(FakeAuth())
ok("이 PC 가 나중에 고쳤으면 이 PC 것이 이긴다", "0504-999-0000" in edits_file()["edits"][T3]["item"]["body"]
   and "0504-999-0000" in [x for x in kb.local_view() if x["title"] == T3][0]["body"])
# 이 PC 에만 둔 첨부는 올리지 않는다
la = kb_files.store_local(b"\x89PNG\r\n\x1a\n" + b"Q" * 50, "명함.png")
v = kb.local_view()
for x in v:
    if x["title"] == T3:
        x["files"] = [la]
kb.set_local(v)
sync.sync_edits(FakeAuth())
ok("이 PC 에만 있는 첨부(local-)는 드라이브 쪽에 싣지 않는다",
   not edits_file()["edits"][T3]["item"].get("files")
   and [x for x in kb.local_view() if x["title"] == T3][0].get("files"))
# 못 읽으면 쓰지 않는다
g.appdata_read_code = 500
w3 = g.appdata_writes
try:
    sync.sync_edits(FakeAuth())
    ok("못 읽으면 SyncError", False)
except sync.SyncError:
    ok("못 읽으면 SyncError · 쓰지 않는다", g.appdata_writes == w3)
g.appdata_read_code = 200
g.appdata[fid]["content"] = "{깨짐"
try:
    sync.sync_edits(FakeAuth())
    ok("깨진 파일이면 SyncError", False)
except sync.SyncError:
    ok("깨진 파일이면 SyncError · 덮어쓰지 않는다", g.appdata[fid]["content"] == "{깨짐")

# 웹(public/sync.js)과 같은 규칙인지 — 같은 상황을 두 쪽에 넣어 본다
node = shutil.which("node")
js = _HERE.parent / "web" / "public" / "sync.js"
if node and js.exists():
    cases = [
        ([{"key": [T1, 0], "base": None, "item": {"title": T1, "body": "웹"}, "at": "2026-11-07T01:00:00Z"}], {},
         {T1: {"item": {"title": T1, "body": "PC"}, "base": None, "at": "2026-11-07T02:00:00Z"}}),
        ([{"key": [T1, 0], "base": None, "item": {"title": T1, "body": "웹"}, "at": "2026-11-07T05:00:00Z"}], {},
         {T1: {"item": {"title": T1, "body": "PC"}, "base": None, "at": "2026-11-07T02:00:00Z"}}),
        ([], {T2: "2026-11-07T05:00:00Z"},
         {T2: {"item": {"title": T2, "body": "PC"}, "base": None, "at": "2026-11-07T02:00:00Z"}}),
        ([{"key": [T3, 0], "base": None, "item": {"title": T3, "body": "옛"}, "at": ""}], {},
         {T3: {"item": {"title": T3, "body": "PC"}, "base": None, "at": "2026-11-01T00:00:00Z"}}),
        ([{"key": [T3, 0], "base": None, "item": {"title": T3, "body": "옛"}, "at": ""}], {}, {}),
        # 심사서류 말고 다른 회사 자료(팩스번호 등)도 같은 규칙 · 같은 제목 둘째 것은 이 PC 에만
        ([{"key": ["메리츠캐피탈", 0], "base": None, "item": {"title": "메리츠캐피탈", "body": "내 팩스"},
           "at": "2026-11-09T01:00:00Z"},
          {"key": ["메리츠캐피탈", 1], "base": None, "item": {"title": "메리츠캐피탈", "body": "둘째"},
           "at": "2026-11-09T01:00:00Z"}], {},
         {"메리츠캐피탈": {"item": {"title": "메리츠캐피탈", "body": "옛 팩스"}, "base": None,
                      "at": "2026-11-08T00:00:00Z"}}),
        ([], {}, {"우리카드": {"item": {"title": "우리카드", "body": "웹에서 고침"}, "base": None,
                           "at": "2026-11-09T02:00:00Z"}}),
        ([], {"우리카드": "2026-11-09T03:00:00Z"},
         {"우리카드": {"item": {"title": "우리카드", "body": "웹에서 고침"}, "base": None,
                    "at": "2026-11-09T02:00:00Z"}}),
    ]
    code = ("import('" + js.as_uri() + "').then((S) => { const cs = JSON.parse(process.argv[1]);"
            " console.log(JSON.stringify(cs.map(([r, d, e]) => { const m = S.mergeEdits(r, d, e, 'NOW');"
            " return [m.recs.map((x) => [x.key[0], x.item.body]), Object.keys(m.dead), m.pushNeeded,"
            " m.changedTitles]; }))); })")
    out = subprocess.run([node, "-e", code, json.dumps(cases, ensure_ascii=False)],
                         capture_output=True, text=True, encoding="utf-8", timeout=60)
    js_res = json.loads(out.stdout or "null")
    py_res = []
    for recs, dead, rem in cases:
        recs = [dict(r, key=tuple(r["key"]), item=kb._clean(r["item"])) for r in recs]
        m = sync.merge_edits(recs, dead, rem, "NOW", [])
        py_res.append([[[r["key"][0], r["item"]["body"]] for r in m["recs"]], list(m["dead"]), m["push"],
                       m["changed"]])
    ok("웹과 같은 규칙(누가 이기나 · 되돌림 · 올릴지 · 받은 제목)", js_res == py_res,
       out.stderr[-300:] if js_res != py_res else "")
    # 일정관리기(python/planner/kb_edits.py)도 같은 파일을 같은 규칙으로 — 실제 코드로 대조
    from planner import kb_edits as pke  # noqa: E402
    pl_res = []
    for recs, dead, rem in cases:
        recs = [dict(r, key=tuple(r["key"]), item=kb._clean(r["item"])) for r in recs]
        m = pke.merge(recs, dead, rem, "NOW", [])
        pl_res.append([[[r["key"][0], r["item"]["body"]] for r in m["recs"]], list(m["dead"]), m["push"],
                       m["changed"]])
    same_case = lambda a, b: sorted(map(json.dumps, a[0])) == sorted(map(json.dumps, b[0])) and a[1:] == b[1:]  # noqa: E731
    ok("일정관리기와 같은 규칙(누가 이기나 · 되돌림 · 올릴지 · 받은 제목)",
       len(pl_res) == len(py_res) and all(same_case(a, b) for a, b in zip(pl_res, py_res)),
       (pl_res, py_res) if pl_res != py_res else "")
else:
    print("   (node 없음 — 웹 규칙 대조 건너뜀)")

print("[19] 내 정보 — {내 팩스} 자리 · 계정 파일의 me 를 지우지 않는다(kb-v1.9.0)")
ME = {"fax": "0504-111-2222", "name": "홍길동", "phone": "", "email": ""}
ok("자리 채우기(일정관리기와 같다)", kb.fill_me("팩스 {내 팩스|0504-214-5287} 담당 {내 이름} {내 이메일}", ME)
   == "팩스 0504-111-2222 담당 홍길동 〔내 이메일 미입력〕" and kb.fill_me("팩스 {내 팩스|0504}", {}) == "팩스 0504")
kb.save_shared([memo("자리 자료", "팩스 {내 팩스|0504-214-5287}")])
kb.save_me({})
ok("안 적었으면 회사 기본값으로 보인다", next(x for x in kb.load_all() if x["title"] == "자리 자료")["body"] == "팩스 0504-214-5287")
kb.save_me(ME)
ok("적으면 내 것으로 보인다(목록·복사)", next(x for x in kb.load_all() if x["title"] == "자리 자료")["body"] == "팩스 0504-111-2222")
ok("편집 창이 읽는 원본은 자리 그대로", next(x for x in kb.local_view() if x["title"] == "자리 자료")["body"]
   == "팩스 {내 팩스|0504-214-5287}")
# 일정관리기·웹에서 적은 내 정보가 이미 계정 파일에 있다 → 여기서 자료를 고쳐 올려도 지우지 않는다
fid = next(i for i, f in g.appdata.items() if f["name"] == sync.EDITS_FILE)
g.appdata[fid]["content"] = json.dumps({"v": 1, "edits": {}})   # 앞 검사가 일부러 깨 둔 파일을 새것으로
o = edits_file()
o["me"] = {"fax": "0504-999-0000", "name": "", "phone": "", "email": "", "at": "2099-01-01T00:00:00Z"}
g.appdata[fid]["content"] = json.dumps(o, ensure_ascii=False)
set_body("자리 자료", "팩스 {내 팩스|0504-214-5287}\n이 PC 에서 덧붙임")
changed = sync.sync_edits(FakeAuth())
ef = edits_file()
ok("자료를 올려도 계정 파일의 내 정보(me)를 지우지 않는다(예전엔 지웠다)",
   ef.get("me", {}).get("fax") == "0504-999-0000" and "이 PC 에서 덧붙임" in ef["edits"]["자리 자료"]["item"]["body"], ef.get("me"))
ok("계정 것이 나중이면 받는다 — 화면도", "내 정보" in changed and kb.load_me()["fax"] == "0504-999-0000"
   and "0504-999-0000" in next(x for x in kb.load_all() if x["title"] == "자리 자료")["body"], changed)
kb.save_me(dict(ME, fax="0504-333-4444"), at="2100-01-01T00:00:00Z")   # 계정 것(2099)보다 나중에 고쳤다
sync.sync_edits(FakeAuth())
ok("이 PC 에서 나중에 고치면 올린다", edits_file()["me"]["fax"] == "0504-333-4444")
o = edits_file()
del o["me"]                      # 예전 판(웹·일정관리기 v1.31 까지)이 빼먹고 썼다
g.appdata[fid]["content"] = json.dumps(o, ensure_ascii=False)
w = g.appdata_writes
sync.sync_edits(FakeAuth())
ok("계정 파일에서 빠졌으면 이 PC 것을 다시 올린다", edits_file().get("me", {}).get("fax") == "0504-333-4444" and g.appdata_writes == w + 1)
w = g.appdata_writes
sync.sync_edits(FakeAuth())
ok("같으면 다시 쓰지 않는다", g.appdata_writes == w)
src = (_pl.Path(__file__).resolve().parents[1] / "kbsearch" / "kb.py").read_text(encoding="utf-8")
psrc = (_pl.Path(__file__).resolve().parents[2] / "python" / "planner" / "kb.py").read_text(encoding="utf-8")
grab = lambda t: t[t.index("def fill_me"):t.index("return _ME_RE.sub(rep, s)")]  # noqa: E731
ok("채우기 규칙이 일정관리기와 글자까지 같다", grab(src) == grab(psrc) and "_ME_RE = re.compile(" in src)

print()
print("실패:", FAIL if FAIL else "없음")
_sys.exit(1 if FAIL else 0)
