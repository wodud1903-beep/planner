"""업무자료 데이터 — 회사 공통 + 내 메모. **이 PC 에만** 저장한다.

일정관리기 kb.py 를 옮겨 오되, 계정별 폴더 대신 이 PC 의 폴더 하나(%APPDATA%\\KbSearch)를
쓴다. 로그인 없이 쓰는 것이 기본이라서다. 다른 곳과 주고받는 일은 [동기화] 가 맡는다(sync.py).

**공통 자료**(`kb_shared.json`) — 일정관리기와 같은 스프레드시트의 `업무자료` 탭에서 받아 둔 것.
  아직 한 번도 못 받았으면, 이 PC 에 일정관리기가 받아 둔 것이 있으면 그것을, 없으면
  앱에 든 기본 자료를 쓴다. 관리자 계정이면 여기서 고치고 [동기화] 때 시트로 올린다.
**내 메모**(`kb_mine.json`) — 누구나 자기 것만 적는다. [동기화] 때 내 구글 계정으로 간다.
**이 PC 에서만 고친 공통 자료**(`kb_local.json`) — 관리자가 아닌 PC(로그인 안 함 포함)에서 공통
  자료를 고치면 원본은 그대로 두고 고친 것만 여기 둔다. 팩스번호·내 연락처처럼 사람마다 다른 것을
  고쳐 쓰라고 있다. 시트·드라이브·다른 PC 로는 **가지 않고**, 공통 자료를 새로 받아도 남는다.
  검색 화면은 원본 위에 이것을 덮어 보여 준다(local_view).

`kb_meta.json` 에는 동기화가 알아야 할 것을 둔다:
  shared_dirty  : 이 PC 에서 공통 자료를 고쳤고 아직 시트로 안 올렸다(관리자)
  deleted       : 지우거나 이름을 바꾼 메모 제목 — 동기화가 다른 PC 의 옛 것을 되살리지 않게
  pending       : 마지막 동기화 뒤에 이 PC 에서 고친 것이 있다(단추에 점을 찍는다)
  account       : 이 PC 의 메모가 마지막으로 동기화된 구글 계정
  last_sync     : 마지막으로 동기화한 때
  trash/renames : 로그인하지 않은 채 빼거나 이름을 바꾼 '이미 올린' 첨부 — 동기화 때 드라이브에 반영
"""

from __future__ import annotations

import json
from datetime import datetime

from . import config, hangul
from .kb_seed import DEFAULTS

SHARED_FILE = "kb_shared.json"
MINE_FILE = "kb_mine.json"
LOCAL_FILE = "kb_local.json"
META_FILE = "kb_meta.json"

SRC_SHARED = "shared"
SRC_MINE = "mine"
SRC_LOCAL = "local"             # 이 PC 에서만 고친 공통 자료
SRC_NAMES = {SRC_SHARED: "공통", SRC_MINE: "내 메모", SRC_LOCAL: "공통 · 이 PC 에서 고침"}

# 자주 쓰는 분류 — 새로 만들 때 고르라고 제안하는 값(자유 입력도 된다)
CATEGORIES = ["심사서류", "캐피탈", "전자약정", "연락처", "진행절차", "기타"]

# 처음 켰을 때 쓰는 기본 자료(일정관리기와 같은 것)
SAMPLE = DEFAULTS


# ---------------------------------------------------------------------------
# 다듬기
# ---------------------------------------------------------------------------
def norm_body(text: str) -> str:
    """본문의 줄 끝 공백을 턴다(편집창이 빈 줄을 '공백 한 칸' 으로 돌려준다)."""
    return "\n".join(line.rstrip() for line in str(text or "").split("\n"))


def clean_files(files) -> list:
    """첨부(그림·PDF) 목록을 저장 형식으로 — [{id, name, mime, size}].

    id 가 없는 것(편집 창 안에만 있는 것)은 버린다. 이 PC 에만 둔 첨부는
    `local-` 로 시작하는 id 를 갖는다(kb_files.store_local) — 동기화 때 드라이브로 올라간다.
    """
    out = []
    for f in files or []:
        if not isinstance(f, dict):
            continue
        fid = str(f.get("id", "")).strip()
        name = str(f.get("name", "")).strip()
        if not fid or not name:
            continue
        try:
            size = max(0, int(f.get("size") or 0))
        except (TypeError, ValueError):
            size = 0
        out.append({"id": fid, "name": name,
                    "mime": str(f.get("mime", "")).strip(), "size": size})
    return out


def _clean(o) -> dict | None:
    """저장 형식으로 다듬는다. 제목이 없으면 버린다(검색이 안 되는 자료)."""
    if not isinstance(o, dict):
        return None
    title = str(o.get("title", "")).strip()
    if not title:
        return None
    checks = o.get("checklist") or []
    if isinstance(checks, str):
        checks = checks.splitlines()
    out = {
        "category": str(o.get("category", "")).strip(),
        "finance": str(o.get("finance", "")).strip(),
        "title": title,
        "tags": str(o.get("tags", "")).strip(),
        "body": norm_body(o.get("body", "")),
        "checklist": [str(c).strip() for c in checks if str(c).strip()],
    }
    files = clean_files(o.get("files"))
    if files:                       # 첨부가 없는 자료는 예전 모양 그대로 둔다
        out["files"] = files
    return out


def clean_list(items) -> list:
    return [x for x in (_clean(o) for o in (items or [])) if x]


def same(a, b) -> bool:
    """저장했을 때 같은 자료인가(표시용 꼬리표는 빼고 본다)."""
    return _clean(a) == _clean(b)


def _parse(text: str) -> list:
    try:
        raw = json.loads(text)
    except Exception:
        return []
    return clean_list(raw) if isinstance(raw, list) else []


def dumps(items: list) -> str:
    """파일·동기화 묶음에 넣는 모양(일정관리기와 같다)."""
    return json.dumps(clean_list(items), ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 파일
# ---------------------------------------------------------------------------
def _load_file(name: str) -> list:
    try:
        p = config.data_file(name)
        if p.exists():
            return _parse(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def _save_file(name: str, items: list) -> None:
    config.atomic_write(config.data_file(name), dumps(items))


def _import_planner_shared() -> list:
    """이 PC 의 일정관리기가 받아 둔 공통 자료(가장 최근 것). 없으면 [].

    공통 자료는 누구에게나 같은 회사 자료라 가져와도 된다. 일정관리기는 계정별
    폴더에 두므로 그 아래를 다 보고 가장 최근에 받은 것을 쓴다.
    (내 메모는 개인 것이라 가져오지 않는다 — [동기화] 로 받는다)
    """
    root = config.appdata() / config.PLANNER_APP_ID
    try:
        cands = [root / SHARED_FILE]
        acc = root / "accounts"
        if acc.is_dir():
            cands += list(acc.glob("*/" + SHARED_FILE))
        cands = [p for p in cands if p.is_file()]
        cands.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for p in cands:
            got = _parse(p.read_text(encoding="utf-8"))
            if got:
                return got
    except Exception:
        pass
    return []


def has_shared_cache() -> bool:
    return bool(_load_file(SHARED_FILE))


def load_shared() -> list:
    """공통 자료. 받아 둔 것이 없으면 일정관리기 것 → 기본 자료 순으로."""
    got = _load_file(SHARED_FILE)
    if got:
        return got
    got = _import_planner_shared()
    if got:
        try:
            _save_file(SHARED_FILE, got)     # 한 번 가져오면 그다음부터는 이 PC 의 것
        except Exception:
            pass
        return got
    return [dict(s) for s in SAMPLE]


def save_shared(items: list, edited: bool = False) -> None:
    """공통 자료를 저장한다. edited=True 면 이 PC 에서 고친 것(관리자) — 시트로 올릴 것."""
    _save_file(SHARED_FILE, items)
    if edited:
        update_meta(shared_dirty=True, pending=True)


def load_mine() -> list:
    return _load_file(MINE_FILE)


def save_mine(items: list, track: bool = True) -> None:
    """내 메모를 저장한다.

    track=True(사용자가 고친 것)면 사라진 제목을 '지운 것' 으로 적어 둔다 — 동기화가
    다른 PC·일정관리기에 남은 옛 메모를 다시 끌고 오지 않게. 이름을 바꾼 것도
    옛 제목이 사라진 것이라 같이 걸린다. 같은 제목으로 다시 만들면 그 표시는 지운다.
    """
    new = clean_list(items)
    if track:
        before = {it["title"] for it in load_mine()}
        after = {it["title"] for it in new}
        meta = load_meta()
        dead = dict(meta.get("deleted") or {})
        stamp = datetime.now().isoformat(timespec="seconds")
        for t in before - after:
            dead[t] = stamp
        for t in after:
            dead.pop(t, None)
        _save_file(MINE_FILE, new)
        update_meta(deleted=dead, pending=True)
        return
    _save_file(MINE_FILE, new)


def deleted_titles() -> set:
    return set((load_meta().get("deleted") or {}).keys())


def load_all() -> list:
    """공통 + 내 메모를 합친 목록. 각 항목에 source 가 붙는다.

    공통 자료는 이 PC 에서 고친 것을 덮어서 보여 준다(SRC_LOCAL).
    """
    out = []
    for it in local_view():
        it = dict(it)
        it["source"] = SRC_LOCAL if it.get("_local") else SRC_SHARED
        out.append(it)
    for it in load_mine():
        it = dict(it)
        it["source"] = SRC_MINE
        out.append(it)
    return out


# ---------------------------------------------------------------------------
# 이 PC 에서만 고친 공통 자료
# ---------------------------------------------------------------------------
def shared_keys(items: list) -> list:
    """공통 자료마다 (제목, 같은 제목 중 몇 번째) — 이 PC 에서 고친 것을 원본에 잇는 열쇠.

    제목으로 잇는다. 고친 쪽 제목을 바꿔도 열쇠는 원본 제목 그대로다.
    """
    seen: dict = {}
    out = []
    for it in items or []:
        t = (it.get("title") or "").strip()
        n = seen.get(t, 0)
        seen[t] = n + 1
        out.append((t, n))
    return out


def load_local() -> list:
    """[{key: (제목, n), base: 고칠 때 본 원본, item: 고친 것}]. 깨진 줄은 버린다."""
    try:
        p = config.data_file(LOCAL_FILE)
        raw = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    except Exception:
        raw = []
    out = []
    for r in raw if isinstance(raw, list) else []:
        if not isinstance(r, dict):
            continue
        k, item = r.get("key"), _clean(r.get("item"))
        if not item or not isinstance(k, list) or len(k) != 2:
            continue
        try:
            key = (str(k[0]).strip(), int(k[1]))
        except (TypeError, ValueError):
            continue
        out.append({"key": key, "base": _clean(r.get("base")), "item": item})
    return out


def _save_local(recs: list) -> None:
    data = [{"key": list(r["key"]), "base": r.get("base"), "item": r["item"]} for r in recs]
    config.atomic_write(config.data_file(LOCAL_FILE),
                        json.dumps(data, ensure_ascii=False, indent=2))


def local_view(shared: list | None = None) -> list:
    """이 PC 에서 보는 공통 자료 — 원본에 이 PC 에서 고친 것을 덮은 목록.

    자료마다 붙는 꼬리표(저장하지 않는다):
      _key    : 원본 열쇠(shared_keys)
      _base   : 지금 원본(없으면 None)
      _local  : 이 PC 에서 고친 것
      _stale  : 고친 뒤에 회사가 원본을 또 고쳤다
      _orphan : 원본이 없어졌다(회사가 지웠거나 제목을 바꿨다) — 고친 것은 그대로 보여 준다
    """
    shared = load_shared() if shared is None else shared
    recs = {r["key"]: r for r in load_local()}
    out = []
    for it, k in zip(shared, shared_keys(shared)):
        r = recs.pop(k, None)
        if r is None:
            x = dict(it)
        else:
            x = dict(r["item"])
            x["_local"] = True
            if r.get("base") is not None and _clean(it) != r["base"]:
                x["_stale"] = True
        x["_key"], x["_base"] = k, dict(it)
        out.append(x)
    for k, r in recs.items():
        x = dict(r["item"])
        x.update(_key=k, _base=None, _local=True, _orphan=True)
        out.append(x)
    return out


def set_local(items: list) -> bool:
    """편집 창의 '이 PC 에서만' 목록(local_view 꼬리표 포함)을 저장한다. 바뀌었으면 True.

    원본과 같아진 것은 지운다(= 회사 자료로 되돌림). 손대지 않은 것은 그대로 둔다 —
    '회사가 또 고침' 표시도 지킨다. 다만 편집 창에서 그 안내를 본 것(_ack)은 지금 원본을
    본 것으로 적는다(그대로 쓰겠다는 뜻).
    """
    old = {r["key"]: r for r in load_local()}
    new: dict = {}
    for it in items or []:
        k, c = it.get("_key"), _clean(it)
        if not k or not c:
            continue
        k = (str(k[0]).strip(), int(k[1]))
        base = _clean(it.get("_base")) if it.get("_base") else None
        prev = old.get(k)
        if base is not None and c == base:
            continue
        if prev is not None and prev["item"] == c and not it.get("_ack"):
            new[k] = prev
            continue
        if base is None and prev is None:
            continue
        new[k] = {"key": k, "base": base if base is not None else prev.get("base"), "item": c}

    def shape(d):
        return {k: (r["item"], r.get("base")) for k, r in d.items()}
    if shape(new) == shape(old):
        return False
    _save_local(list(new.values()))
    return True


def local_file_ids() -> set:
    """이 PC 에서만 고친 공통 자료가 쓰는 첨부 id — 동기화가 지우거나 휴지통에 넣지 않게."""
    return {f.get("id") for r in load_local() for f in (r["item"].get("files") or [])
            if f.get("id")}


# ---------------------------------------------------------------------------
# 동기화 상태
# ---------------------------------------------------------------------------
def load_meta() -> dict:
    try:
        p = config.data_file(META_FILE)
        if p.exists():
            o = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(o, dict):
                return o
    except Exception:
        pass
    return {}


def update_meta(**kw) -> dict:
    m = load_meta()
    m.update(kw)
    config.atomic_write(config.data_file(META_FILE),
                        json.dumps(m, ensure_ascii=False, indent=2))
    return m


def queue_remote(trash=(), renames=()) -> None:
    """로그인 없이 빼거나 이름을 바꾼 '이미 올린' 첨부를 동기화 때 반영하려고 적어 둔다."""
    m = load_meta()
    t = list(m.get("trash") or [])
    for fid in trash or ():
        if fid and fid not in t:
            t.append(fid)
    r = [list(x) for x in (m.get("renames") or []) if isinstance(x, (list, tuple)) and len(x) == 2]
    for fid, name in renames or ():
        r = [x for x in r if x[0] != fid] + [[fid, name]]
    update_meta(trash=t, renames=r)


# ---------------------------------------------------------------------------
# 검색
# ---------------------------------------------------------------------------
def haystack(item: dict) -> str:
    """검색 대상 문자열 — 제목·금융사·분류·태그·본문·체크리스트·첨부 이름을 모두 본다."""
    return " ".join([
        item.get("title", ""), item.get("finance", ""), item.get("category", ""),
        item.get("tags", ""), item.get("body", ""),
        " ".join(item.get("checklist") or []),
        " ".join(f.get("name", "") for f in (item.get("files") or [])),
    ])


def search(items: list, query: str, category: str = "") -> list:
    """`query` 로 거르고, 제목이 맞는 자료를 앞으로 올린다."""
    cat = (category or "").strip()
    q = (query or "").strip()
    hits = []
    for i, it in enumerate(items or []):
        if cat and it.get("category", "") != cat:
            continue
        if q and not hangul.matches(haystack(it), q):
            continue
        # 0 = 제목이 맞음, 1 = 태그·금융사, 2 = 그 밖(본문 등)
        if not q:
            tier = 1
        elif hangul.matches(it.get("title", ""), q):
            tier = 0
        elif hangul.matches(it.get("finance", "") + " " + it.get("tags", ""), q):
            tier = 1
        else:
            tier = 2
        hits.append((tier, hangul.rank(it.get("title", ""), q), i, it))
    hits.sort(key=lambda x: (x[0], x[1], x[2]))
    return [it for _t, _r, _i, it in hits]


def categories(items: list) -> list:
    """자료에 실제로 쓰인 분류 (검색 화면의 거르개용)."""
    seen = []
    for it in items or []:
        c = (it.get("category") or "").strip()
        if c and c not in seen:
            seen.append(c)
    return seen
