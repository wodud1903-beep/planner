"""자료검색 즐겨찾기(v1.35 — 지점장이 고른 K3).

  · 즐겨찾기(★): 설정(plan_cfg.json)에 둔다 — 동기화 묶음에 실려 다른 PC 에도 같다.
  · 최근 본 자료(🕘)는 v1.35.3 에서 없앴다(지점장: "자료검색 상단의 최근 목록은 삭제").
    예전에 이 PC 에 적어 둔 kb_recent.json 은 읽지 않는다(켤 때 지운다).

자료를 가리키는 열쇠는 제목이다(내 메모는 앞에 'm:'). 폰 웹(자료 탭 해시)과 같은 모양이다.
빠른검색 창과 자료검색 탭이 같은 표를 본다(모듈 하나에 둔다).
"""

from __future__ import annotations

from . import config, kb

_favs: list = []
on_favs_changed = None          # 즐겨찾기를 바꿨을 때(main_window 가 설정 저장 · 동기화)


def key(it: dict) -> str:
    return ("m:" if (it or {}).get("source") == kb.SRC_MINE else "") + str((it or {}).get("title", "")).strip()


def set_favs(keys) -> None:
    """설정에서 읽은 즐겨찾기(계정이 바뀌면 다시 부른다)."""
    global _favs
    _favs = [str(k) for k in (keys or []) if str(k).strip()]
    try:                                    # 옛 판(v1.35.0~2)이 남긴 '최근 본 자료' 파일
        (config.data_dir() / "kb_recent.json").unlink(missing_ok=True)
    except OSError:
        pass


def favs() -> list:
    return list(_favs)


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


def arrange(items: list) -> list:
    """검색어 없이 '전체' 를 볼 때의 차례 — 즐겨찾기(고른 차례) → 나머지(원래 차례)."""
    by_key = {}
    for it in items or []:
        by_key.setdefault(key(it), it)
    head, seen = [], set()
    for k in list(_favs):
        it = by_key.get(k)
        if it is not None and id(it) not in seen:
            head.append(it)
            seen.add(id(it))
    return head + [it for it in items if id(it) not in seen]


def mark_of(it: dict) -> str:
    """목록 줄 앞 표시 — '★' 즐겨찾기 · '' 그 밖."""
    return "★" if key(it) in _favs else ""
