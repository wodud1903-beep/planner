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

print()
print("실패:", FAIL if FAIL else "없음")
_sys.exit(1 if FAIL else 0)
