"""지운 표식 — 목록 파일에서 지운 항목이 동기화로 되살아나지 않게(v1.26).

인사말(greetings.json)·내 메모(kb_mine.json)는 PC 끼리 합칠 때 '양쪽에 있는 것을 다 남긴다'
(sync._MERGE 의 list). 그래서 한 PC 에서 지운 채널·메모가 다른 PC 에 남아 있으면 다음
동기화에 다시 살아났다.

이제 지울 때(이름을 바꾸면 옛 이름도) 계정 폴더의 deleted.json 에

    {"greetings.json": {"채널 이름": "2026-11-03T05:12:00Z"}, "kb_mine.json": {"메모 제목": "…"}}

를 남기고, 합칠 때 **지운 시각보다 나중에 고치지 않은 항목**은 뺀다. 항목마다 고친 시각
`at` 을 붙여 두므로, 같은 이름으로 다시 만들면(at 이 더 늦다) 그대로 산다.
표식끼리는 합집합(같은 열쇠면 늦은 시각) — 동기화 묶음에 같이 실린다(sync._FILES).

업무자료검색(kbsearch)도 같은 묶음의 kb_mine.json · deleted.json 칸을 같은 규칙으로 읽고 쓴다.
시각은 동기화와 같은 꼴(UTC 문자열)이라 글자로 크기를 견준다.
"""

from __future__ import annotations

import datetime
import json

from . import config

FILE = "deleted.json"
# 표식을 쓰는 목록 파일 → 항목의 열쇠
KEYS = {"greetings.json": "name", "kb_mine.json": "title"}
_TS = "%Y-%m-%dT%H:%M:%SZ"


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime(_TS)


def _clean(o) -> dict:
    """{파일: {열쇠: 시각}} 모양만 남긴다."""
    out: dict = {}
    if not isinstance(o, dict):
        return out
    for f, d in o.items():
        if not isinstance(d, dict):
            continue
        dd = {str(k).strip(): str(v) for k, v in d.items() if str(k).strip() and v}
        if dd:
            out[str(f)] = dd
    return out


def load() -> dict:
    try:
        return _clean(json.loads(config.data_file(FILE).read_text(encoding="utf-8")))
    except Exception:
        return {}


def save(t: dict) -> None:
    config.atomic_write(config.data_file(FILE), json.dumps(_clean(t), ensure_ascii=False, indent=2))


def merge(a, b) -> dict:
    """두 표식 묶음을 합친다 — 같은 열쇠면 늦은 시각."""
    out = _clean(a)
    for f, d in _clean(b).items():
        cur = out.setdefault(f, {})
        for k, v in d.items():
            if v > cur.get(k, ""):
                cur[k] = v
    return out


def keep(file: str, items: list, t: dict) -> list:
    """지운 표식보다 나중에 고치지 않은 항목은 뺀다."""
    key = KEYS.get(file)
    dead = (t or {}).get(file) or {}
    if not key or not dead or not isinstance(items, list):
        return items
    out = []
    for it in items:
        if isinstance(it, dict):
            k = str(it.get(key) or "").strip()
            at = str(it.get("at") or "")
            if k in dead and at <= dead[k]:
                continue
        out.append(it)
    return out


def stamp(file: str, before: list, after: list) -> list:
    """저장하기 직전에 부른다 — 사라진 열쇠는 '지움' 으로 적고, 새로 생기거나 바뀐 항목에는
    고친 시각(at)을 붙인 새 목록을 돌려준다(그대로인 항목은 원래 시각을 지킨다)."""
    key = KEYS[file]

    def body(it):
        return {k: v for k, v in it.items() if k != "at"}

    old = {}
    for it in before or []:
        if isinstance(it, dict) and str(it.get(key) or "").strip():
            old[str(it[key]).strip()] = it
    ts = now()
    out, seen = [], set()
    for it in after or []:
        if not isinstance(it, dict):
            continue
        k = str(it.get(key) or "").strip()
        if not k:
            continue
        seen.add(k)
        it = dict(it)
        prev = old.get(k)
        if prev is not None and body(prev) == body(it) and prev.get("at"):
            it["at"] = prev["at"]
        elif prev is None or body(prev) != body(it):
            it["at"] = ts
        out.append(it)
    gone = [k for k in old if k not in seen]
    if gone:
        t = load()
        d = t.setdefault(file, {})
        for k in gone:
            d[k] = ts
        save(t)
    return out
