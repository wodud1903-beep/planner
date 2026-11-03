"""지운 인사말·내 메모가 동기화로 되살아나지 않는다(v1.26 — tombs.py · deleted.json).

예전: 인사말·내 메모는 PC 끼리 합칠 때 양쪽 것을 다 남겨서, 한 PC 에서 지운 것이 다른 PC 에
남아 있으면 다음 동기화에 다시 살아났다. 이제 지울 때 표식을 남기고, 합칠 때 그 표식보다
나중에 고치지 않은 항목은 뺀다. 같은 이름으로 다시 만들면 살아 있다.
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

PC_A, PC_B = tempfile.mkdtemp(), tempfile.mkdtemp()
os.environ["APPDATA"] = PC_A

from planner import config, greetings, kb, sync, tombs  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name
          + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


ME = "me@example.com"
CLOCK = [time.time() - 10000]
_TICK = [0]


def _fake_now():
    """검사에서는 한 번 부를 때마다 1분씩 간다(사람은 같은 초에 지우고 다시 만들지 않는다)."""
    _TICK[0] += 1
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(CLOCK[0] + _TICK[0] * 60))


tombs.now = _fake_now


def on(pc):
    """그 PC 로 옮겨 간다(같은 계정)."""
    os.environ["APPDATA"] = pc
    config.set_account(ME)


def tick(*names):
    """방금 고친 파일의 시각을 한 칸씩 늦춘다(같은 초에 두 번 고쳐도 순서가 서게)."""
    CLOCK[0] += 60
    for n in names:
        p = config.data_file(n)
        if p.exists():
            os.utime(p, (CLOCK[0], CLOCK[0]))


def names(items, key):
    return [it[key] for it in items]


BUNDLE = {}


def push():
    BUNDLE.clear()
    BUNDLE.update(sync.merged_bundle(dict(BUNDLE) if BUNDLE else None))


def pull():
    return sync.apply_remote(dict(BUNDLE))


print("[1] 표식 계산")
t = tombs.merge({"greetings.json": {"가": "2026-11-01T00:00:00Z"}},
                {"greetings.json": {"가": "2026-11-02T00:00:00Z", "나": "2026-10-01T00:00:00Z"}})
ok("합치면 늦은 시각 · 양쪽 열쇠 다", t == {"greetings.json": {"가": "2026-11-02T00:00:00Z",
                                                          "나": "2026-10-01T00:00:00Z"}}, t)
items = [{"name": "가"}, {"name": "나", "at": "2026-10-05T00:00:00Z"}, {"name": "다"}]
ok("표식보다 나중에 고친 것만 남는다", names(tombs.keep("greetings.json", items, t), "name") == ["나", "다"])

print("[2] 인사말 — A 에서 지우면 B 에서도 사라진다")
on(PC_A)
greetings.save([{"name": "에이원오토", "after": "a", "miss": "m"},
                {"name": "우리금융", "after": "b", "miss": "n"},
                {"name": "KB캐피탈", "after": "c", "miss": "o"}])
tick("greetings.json")
push()
on(PC_B)
pull()
ok("B 가 A 의 채널을 받는다", names(greetings.load(), "name") == ["에이원오토", "우리금융", "KB캐피탈"])
on(PC_A)
cur = greetings.load()
greetings.save([g for g in cur if g["name"] != "우리금융"])
tick("greetings.json", tombs.FILE)
ok("지우면 표식이 남는다", "우리금융" in tombs.load().get("greetings.json", {}), tombs.load())
push()
ok("올린 묶음에도 없다", "우리금융" not in json.dumps(json.loads(BUNDLE["files"]["greetings.json"]),
                                                    ensure_ascii=False))
on(PC_B)
# B 는 그 사이 다른 채널 문구를 고쳤다(B 의 파일이 더 최신 — 예전엔 여기서 되살아났다)
g = greetings.load()
g[2]["after"] = "B 에서 고침"
greetings.save(g)
tick("greetings.json")
pull()
ok("B 에서도 '우리금융' 이 사라진다(되살아나지 않는다)",
   names(greetings.load(), "name") == ["에이원오토", "KB캐피탈"], names(greetings.load(), "name"))
ok("B 에서 고친 문구는 그대로", greetings.load()[1]["after"] == "B 에서 고침")
push()
ok("B 가 올려도 되살아나지 않는다",
   "우리금융" not in [x["name"] for x in json.loads(BUNDLE["files"]["greetings.json"])])
on(PC_A)
pull()
ok("A 도 그대로", names(greetings.load(), "name") == ["에이원오토", "KB캐피탈"], names(greetings.load(), "name"))

print("[3] 같은 이름으로 다시 만들면 산다")
on(PC_B)
greetings.save(greetings.load() + [{"name": "우리금융", "after": "새 문구", "miss": ""}])
tick("greetings.json")
push()
on(PC_A)
pull()
ok("다시 만든 '우리금융' 이 A 에 온다", "우리금융" in names(greetings.load(), "name"),
   names(greetings.load(), "name"))
ok("새 문구로", next(x for x in greetings.load() if x["name"] == "우리금융")["after"] == "새 문구")

print("[4] 이름을 바꾸면 옛 이름은 '지움'")
on(PC_A)
g = greetings.load()
for x in g:
    if x["name"] == "KB캐피탈":
        x["name"] = "KB캐피탈(새)"
greetings.save(g)
tick("greetings.json", tombs.FILE)
push()
on(PC_B)
pull()
ok("B 에 옛 이름이 남지 않는다", "KB캐피탈" not in names(greetings.load(), "name")
   and "KB캐피탈(새)" in names(greetings.load(), "name"), names(greetings.load(), "name"))

print("[5] 내 메모(kb_mine) — 업무자료검색과 같은 칸")
on(PC_A)
kb.save_mine([{"category": "기타", "title": "팩스번호", "body": "02-000"},
              {"category": "기타", "title": "지울메모", "body": "x"}])
tick(kb.MINE_FILE)
push()
on(PC_B)
pull()
ok("B 가 메모를 받는다", names(kb.load_mine(), "title") == ["팩스번호", "지울메모"])
on(PC_A)
kb.save_mine([m for m in kb.load_mine() if m["title"] != "지울메모"])
tick(kb.MINE_FILE, tombs.FILE)
push()
on(PC_B)
m = kb.load_mine()
m[0]["body"] = "02-111"           # B 에서 다른 메모를 고쳤다(더 최신)
kb.save_mine(m)
tick(kb.MINE_FILE)
pull()
ok("지운 메모는 B 에서도 사라진다", names(kb.load_mine(), "title") == ["팩스번호"], names(kb.load_mine(), "title"))
ok("B 에서 고친 것은 그대로", kb.load_mine()[0]["body"] == "02-111")
ok("고친 시각(at)이 붙는다", bool(kb.load_mine()[0].get("at")))
ok("묶음에 지운 표식 칸이 실린다", tombs.FILE in BUNDLE["files"] and tombs.FILE in sync._FILES)

print("[6] 옛 판이 올린 묶음(표식 칸 없음)이 와도 표식은 남는다")
on(PC_B)
old = {"updatedAt": "2099-01-01T00:00:00Z",
       "files": {kb.MINE_FILE: json.dumps([{"category": "기타", "title": "팩스번호", "body": "02-111"},
                                           {"category": "기타", "title": "지울메모", "body": "x"}],
                                          ensure_ascii=False)},
       "times": {kb.MINE_FILE: "2099-01-01T00:00:00Z"}}
sync.apply_remote(old)
ok("옛 판이 되살려 보낸 메모도 이 PC 에서는 뺀다", names(kb.load_mine(), "title") == ["팩스번호"],
   names(kb.load_mine(), "title"))
ok("표식은 그대로", "지울메모" in tombs.load().get(kb.MINE_FILE, {}))

print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
