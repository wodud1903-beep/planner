"""이름이 같은 '고객정보' 폴더가 여럿일 때 — 내 드라이브 바로 밑 것을 고른다(v1.35.2).

지점장: "jyplanner 가 모바일에서는 고객서류가 잘 나오는데 PC 웹에서는 폴더가 안 나와."
드라이브에 '고객정보' 가 다섯 개(옛 복사본·백업). 이름으로 찾을 때 '가장 최근 수정' 을 골랐는데,
폴더의 수정 시각은 안에 고객 폴더를 넣어도 바뀌지 않아 '계약고객' 하나 든 옛 복사본이 뽑혔다.
PC 앱의 '인터넷으로 읽기'(google_client.drive_folder_id)도 같은 규칙이었다.
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))

import os
import tempfile
import types

os.environ["APPDATA"] = tempfile.mkdtemp()

from planner import google_client as gc  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


F = "application/vnd.google-apps.folder"
# 지점장 드라이브와 같은 모양(가짜 id): 수정 시각은 옛 복사본이 더 늦다
FOLDERS = [
    {"id": "OLD_COPY", "parent": "SOMEWHERE", "mod": "2026-09-10T03:02:10Z"},
    {"id": "OLD_COPY2", "parent": "ELSEWHERE", "mod": "2026-09-10T03:01:04Z"},
    {"id": "REAL", "parent": "root", "mod": "2026-09-10T02:56:46Z"},
    {"id": "BACKUP", "parent": "PC_BACKUP", "mod": "2026-09-09T13:35:08Z"},
]
asked = []


class _R:
    def __init__(self, code, js):
        self.status_code, self._js = code, js

    def json(self):
        return self._js


def _get(url, params=None, **k):
    q = (params or {}).get("q", "")
    asked.append(q)
    if "name='고객정보'" not in q:
        return _R(404, {})
    hits = [f for f in FOLDERS if "'root' in parents" not in q or f["parent"] == "root"]
    hits.sort(key=lambda f: f["mod"], reverse=True)
    return _R(200, {"files": [{"id": f["id"], "name": "고객정보", "modifiedTime": f["mod"]} for f in hits]})


gc._http = lambda: types.SimpleNamespace(get=_get)
auth = types.SimpleNamespace(_headers=lambda: {})

print("[1] 이름이 같은 폴더가 여럿 — 내 드라이브 바로 밑 것")
got = gc.drive_folder_id(auth, "고객정보")
ok("옛 복사본(가장 최근 수정)이 아니라 내 드라이브\\고객정보", got == "REAL", got)
ok("내 드라이브 바로 밑에서 먼저 찾는다", asked and "'root' in parents" in asked[0], asked)

print("[2] 내 드라이브 바로 밑에 없으면 — 예전처럼 어디든 가장 최근 것")
FOLDERS[2]["parent"] = "SALES"
asked.clear()
got = gc.drive_folder_id(auth, "고객정보")
ok("가장 최근 것", got == "OLD_COPY", got)
ok("두 번 묻는다(바로 밑 → 어디든)", len(asked) == 2 and "'root' in parents" not in asked[1], asked)

print("[3] 없으면 빈 값")
FOLDERS.clear()
ok("빈 값", gc.drive_folder_id(auth, "고객정보") == "")

print("[4] 웹(jyplanner)도 같은 규칙")
js = (_ROOT / "web" / "js" / "drive.js").read_text(encoding="utf-8")
ok("이름으로 찾을 때 root 먼저", 'return (await childFolder(name, "root")) || childFolder(name, "");' in js)
ok("경로의 G: · 내 드라이브 앞머리를 뗀다", "export function driveSegs" in js)
docs = (_ROOT / "web" / "js" / "ui" / "docs.js").read_text(encoding="utf-8")
ok("예전 규칙으로 찾아 둔 폴더(저장본)는 버린다", "cached.rule === ROOT_RULE" in docs and "rule: ROOT_RULE" in docs)

print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
