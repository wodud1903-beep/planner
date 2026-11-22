"""자료검색 즐겨찾기 · 최근 본 자료(v1.35 — 지점장이 고른 K3).

  · 즐겨찾기(★): 설정(plan_cfg.json)에 둔다 — 동기화 묶음에 실려 다른 PC 에도 같다.
  · 최근 본 자료: 이 PC 에만 둔다(kb_recent.json). 볼 때마다 설정을 다시 쓰고 동기화하면 무겁다.

자료를 가리키는 열쇠는 제목이다(내 메모는 앞에 'm:'). 폰 웹(자료 탭 해시)과 같은 모양이다.
빠른검색 창과 자료검색 탭이 같은 표를 본다(모듈 하나에 둔다).
"""

from __future__ import annotations

import json

from . import config, kb

RECENT_MAX = 5
_favs: list = []
_recent: list = []
_loaded_recent = False
on_favs_changed = None          # 즐겨찾기를 바꿨을 때(main_window 가 설정 저장 · 동기화)


def key(it: dict) -> str:
    return ("m:" if (it or {}).get("source") == kb.SRC_MINE else "") + str((it or {}).get("title", "")).strip()


def _recent_file():
    return config.data_dir() / "kb_recent.json"


def _load_recent() -> None:
    global _recent, _loaded_recent
    _loaded_recent = True
    try:
        got = json.loads(_recent_file().read_text(encoding="utf-8"))
        _recent = [str(x) for x in got if isinstance(x, str)][:RECENT_MAX] if isinstance(got, list) else []
    except Exception:
        _recent = []


def set_favs(keys) -> None:
    """설정에서 읽은 즐겨찾기(계정이 바뀌면 다시 부른다). 최근 본 자료도 다시 읽는다."""
    global _favs
    _favs = [str(k) for k in (keys or []) if str(k).strip()]
    _load_recent()


def favs() -> list:
    return list(_favs)


def recent() -> list:
    if not _loaded_recent:
        _load_recent()
    return list(_recent)


def is_fav(it: dict) -> bool:
    return key(it) in _favs


def toggle_fav(it: dict) -> bool:
    """즐겨찾기 넣기/빼기 — 넣었으면 True."""
    k = key(it)
    if not k:
        return False
    if k in _favs:
        _favs.remove(k)
        on = False
    else:
        _favs.append(k)
        on = True
    if callable(on_favs_changed):
        try:
            on_favs_changed(list(_favs))
        except Exception:
            pass
    return on


def touch(it: dict) -> None:
    """방금 본(누른 · 복사한) 자료 — 최근 목록 맨 앞으로."""
    global _recent
    k = key(it)
    if not k:
        return
    if not _loaded_recent:
        _load_recent()
    _recent = [k] + [x for x in _recent if x != k]
    _recent = _recent[:RECENT_MAX]
    try:
        _recent_file().write_text(json.dumps(_recent, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def arrange(items: list) -> list:
    """검색어 없이 '전체' 를 볼 때의 차례 — 즐겨찾기(고른 차례) → 최근 본 것 → 나머지(원래 차례)."""
    by_key = {}
    for it in items or []:
        by_key.setdefault(key(it), it)
    head, seen = [], set()
    for k in list(_favs) + recent():
        it = by_key.get(k)
        if it is not None and id(it) not in seen:
            head.append(it)
            seen.add(id(it))
    return head + [it for it in items if id(it) not in seen]


def mark_of(it: dict) -> str:
    """목록 줄 앞 표시 — '★' 즐겨찾기 · '🕘' 최근 본 것 · '' 그 밖."""
    k = key(it)
    if k in _favs:
        return "★"
    if k in recent():
        return "🕘"
    return ""
