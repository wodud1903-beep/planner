"""업무자료(자료검색함) 데이터 — 회사 공통 + 개인 메모.

**공통 자료** 는 수당율과 같은 전용 스프레드시트의 `업무자료` 탭에 있다.
관리자(`config.KB_ADMINS`)만 고칠 수 있고, 나머지 PC 는 받아서 읽기만 한다.
받아온 내용은 `kb_shared.json` 에 캐시해 두어, 인터넷이 느리거나 끊겨도
프로그램을 켜자마자 검색이 된다.

**개인 메모** 는 `kb_mine.json` (계정 폴더). 누구나 자기 것만 적고,
드라이브 동기화로 본인의 다른 PC 에도 따라간다.

**내 계정에서만 고친 공통 자료**(`kb_local.json`, 계정 폴더 — v1.29) — 회사 공통 자료를
누구나 **자기 계정에서만** 고쳐 쓴다(팩스번호·내 연락처처럼 사람마다 다른 것). 회사 원본(시트)과
다른 직원에게는 가지 않고, 내 구글 계정의 드라이브 앱 공간 `kb_edits.json` 으로 내 다른 PC·
업무자료검색(PC·웹)과 맞춘다(kb_edits.py). 검색 화면은 원본 위에 이것을 덮어 보여 준다(local_view).
업무자료검색 프로그램 kbsearch/kb.py 의 같은 이름 함수들과 같은 모양·같은 규칙이다.

두 출처를 합쳐 하나의 목록으로 검색한다. 각 항목에는 `source` 가 붙어
화면에서 '공통 / 내 계정에서 고침 / 내 메모' 로 구분된다.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from . import config, hangul, tombs
from .kb_seed import DEFAULTS

SHARED_FILE = "kb_shared.json"
MINE_FILE = "kb_mine.json"
LOCAL_FILE = "kb_local.json"            # 내 계정에서만 고친 공통 자료(v1.29)
LOCAL_DEAD_FILE = "kb_local_dead.json"  # 그중 '회사 자료로 되돌린' 것 {제목: 시각} — 다른 곳에도 전한다

SRC_SHARED = "shared"
SRC_MINE = "mine"
SRC_LOCAL = "local"                     # 회사 공통 — 내 계정에서만 고침
SRC_NAMES = {SRC_SHARED: "공통", SRC_MINE: "내 메모", SRC_LOCAL: "공통 · 내 계정에서 고침"}

# 자주 쓰는 분류 — 새로 만들 때 고르라고 제안하는 값(자유 입력도 된다)
CATEGORIES = ["심사서류", "캐피탈", "전자약정", "연락처", "진행절차", "기타"]
CAT_DOCS = "심사서류"        # 서류 체크리스트가 재료로 쓰는 분류

# 처음 켰을 때(또는 관리자가 아직 아무것도 안 올렸을 때) 쓰는 기본 자료.
# 실제 내용은 kb_seed.py 에 있다 — 자료가 많아 로직과 섞으면 파일이 안 읽힌다.
SAMPLE = DEFAULTS


# ---------------------------------------------------------------------------
# 읽기 / 쓰기
# ---------------------------------------------------------------------------
def norm_body(text: str) -> str:
    """본문의 줄 끝 공백을 턴다.

    편집창의 QTextEdit 는 빈 줄을 '공백 한 칸이 든 줄' 로 돌려준다. 그대로 두면
    창을 열었다 저장하기만 해도 고객에게 보내는 글이 조용히 바뀌고, 기본자료와
    같은 내용인데도 '다르다' 고 잡힌다. 들고 나는 길목에서 한 번에 턴다.
    """
    return "\n".join(line.rstrip() for line in str(text or "").split("\n"))


def clean_files(files) -> list:
    """첨부(그림·PDF) 목록을 저장 형식으로 — [{id, name, mime, size}].

    드라이브 파일 id 가 없는 것(아직 안 올린 것)은 버린다. 올리기 전의 첨부는
    편집 창 안에서만 산다(kb_tab.KbEditDialog).
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
    if o.get("at"):                 # 내 메모를 고친 시각 — 지운 표식과 견준다(tombs, v1.26)
        out["at"] = str(o["at"])
    return out


def _load_file(name: str) -> list:
    try:
        p = config.data_file(name)
        if p.exists():
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                return [x for x in (_clean(o) for o in raw) if x]
    except Exception:
        pass
    return []


def _save_file(name: str, items: list) -> None:
    data = [x for x in (_clean(o) for o in (items or [])) if x]
    config.atomic_write(config.data_file(name),
                        json.dumps(data, ensure_ascii=False, indent=2))


def load_shared() -> list:
    """공통 자료 캐시. 아직 한 번도 못 받았으면 예시를 돌려준다."""
    got = _load_file(SHARED_FILE)
    return got if got else [dict(s) for s in SAMPLE]


def save_shared(items: list) -> None:
    """시트에서 받아온 공통 자료를 캐시에 넣는다."""
    _save_file(SHARED_FILE, items)


def load_mine() -> list:
    return _load_file(MINE_FILE)


def save_mine(items: list) -> None:
    """내 메모를 저장한다. 지운(제목을 바꾼) 메모는 표식을 남기고, 새로 만들거나 고친
    메모에는 시각을 붙인다 — 다른 PC·업무자료검색에 남은 옛 메모가 동기화로 되살아나지
    않게(v1.26, tombs)."""
    new = [x for x in (_clean(o) for o in (items or [])) if x]
    _save_file(MINE_FILE, tombs.stamp(MINE_FILE, load_mine(), new))


def load_all() -> list:
    """공통 + 개인을 합친 목록. 각 항목에 source 가 붙는다.

    공통 자료는 내 계정에서 고친 것을 덮어서 보여 준다(SRC_LOCAL).
    """
    out = []
    me = load_me()
    for it in local_view():
        it = dict(it)
        it["source"] = SRC_LOCAL if it.get("_local") else SRC_SHARED
        it["body"] = fill_me(it.get("body", ""), me)     # {내 팩스} 같은 자리를 내 정보로(v1.32)
        out.append(it)
    for it in load_mine():
        it = dict(it)
        it["source"] = SRC_MINE
        it["body"] = fill_me(it.get("body", ""), me)
        out.append(it)
    return out


# ---------------------------------------------------------------------------
# 내 정보 자동 넣기(v1.32) — 회사 자료의 {내 팩스} · {내 이름} · {내 연락처} · {내 이메일} 자리에 각자 값이 들어간다.
#
# 지점장: "팩스번호를 본인 걸로". 자료마다 '내 계정에서만 고침' 으로 고치면 회사가 원본을 바꿀 때마다 다시
# 고쳐야 한다. 관리자가 회사 자료에 자리(예: `팩스 {내 팩스|0504-214-5287}`)를 한 번 넣어 두면, 직원은
# [내 정보] 에 한 번만 적으면 된다. `|` 뒤는 내 정보를 안 적은 사람에게 보일 기본값.
# 내 정보는 고친 자료와 같은 파일(kb_edits.json 의 "me")로 내 계정에 저장돼 PC·웹 어디서나 같다.
# 업무자료검색(PC·웹)·jyplanner 웹과 **같은 규칙**이다.
# ---------------------------------------------------------------------------
ME_FILE = "kb_me.json"
ME_FIELDS = (("fax", "팩스"), ("name", "이름"), ("phone", "연락처"), ("email", "이메일"))
_ME_KEY = {label: key for key, label in ME_FIELDS}
_ME_RE = re.compile(r"\{내 (팩스|이름|연락처|이메일)(?:\|([^{}\n]*))?\}")


def clean_me(o) -> dict:
    o = o if isinstance(o, dict) else {}
    out = {k: str(o.get(k) or "").strip()[:80] for k, _l in ME_FIELDS}
    out["at"] = str(o.get("at") or "")
    return out


def load_me() -> dict:
    try:
        p = config.data_file(ME_FILE)
        if p.exists():
            return clean_me(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        pass
    return clean_me({})


def save_me(values: dict, at: str | None = None) -> dict:
    """내 정보를 저장한다. at 을 안 주면 지금 고친 것으로(나중에 고친 쪽이 이긴다)."""
    me = clean_me(dict(values or {}, at=at if at is not None else utc_stamp()))
    config.atomic_write(config.data_file(ME_FILE), json.dumps(me, ensure_ascii=False, indent=2))
    return me


def has_me(me: dict) -> bool:
    return any((me or {}).get(k) for k, _l in ME_FIELDS)


def fill_me(text: str, me: dict | None) -> str:
    """{내 팩스|기본값} 자리를 내 정보로 바꾼다. 안 적었으면 기본값, 그것도 없으면 '〔내 팩스 미입력〕'."""
    s = str(text or "")
    if "{내 " not in s:
        return s

    def rep(m):
        v = str((me or {}).get(_ME_KEY[m.group(1)]) or "").strip()
        if v:
            return v
        d = (m.group(2) or "").strip()
        return d if d else f"〔내 {m.group(1)} 미입력〕"
    return _ME_RE.sub(rep, s)


# ---------------------------------------------------------------------------
# 내 계정에서만 고친 공통 자료(v1.29) — 업무자료검색 kbsearch/kb.py 와 같은 모양
# ---------------------------------------------------------------------------
def utc_stamp(dt: datetime | None = None) -> str:
    """동기화와 같은 꼴(UTC 'YYYY-MM-DDTHH:MM:SSZ') — 글자로 크기를 견준다."""
    return (dt or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def same(a, b) -> bool:
    """저장했을 때 같은 자료인가(고친 시각은 빼고 본다)."""
    ca, cb = _clean(a), _clean(b)
    if ca:
        ca.pop("at", None)
    if cb:
        cb.pop("at", None)
    return ca == cb


def shared_keys(items: list) -> list:
    """공통 자료마다 (제목, 같은 제목 중 몇 번째) — 고친 것을 원본에 잇는 열쇠."""
    seen: dict = {}
    out = []
    for it in items or []:
        t = (it.get("title") or "").strip()
        n = seen.get(t, 0)
        seen[t] = n + 1
        out.append((t, n))
    return out


def load_local() -> list:
    """[{key: (제목, n), base: 고칠 때 본 원본, item: 고친 것, at}]. 깨진 줄은 버린다."""
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
        out.append({"key": key, "base": _clean(r.get("base")), "item": item,
                    "at": str(r.get("at") or "")})
    return out


def _save_local(recs: list) -> None:
    data = [{"key": list(r["key"]), "base": r.get("base"), "item": r["item"],
             **({"at": r["at"]} if r.get("at") else {})} for r in recs]
    config.atomic_write(config.data_file(LOCAL_FILE),
                        json.dumps(data, ensure_ascii=False, indent=2))


def load_local_dead() -> dict:
    try:
        p = config.data_file(LOCAL_DEAD_FILE)
        o = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        o = {}
    return {str(t): str(v) for t, v in o.items() if t and v} if isinstance(o, dict) else {}


def _save_local_dead(d: dict) -> None:
    config.atomic_write(config.data_file(LOCAL_DEAD_FILE),
                        json.dumps(dict(d or {}), ensure_ascii=False, indent=2))


def replace_local(recs: list, dead: dict) -> None:
    """동기화가 합친 결과를 그대로 저장한다(kb_edits.sync)."""
    _save_local(recs)
    _save_local_dead(dead)


def local_view(shared: list | None = None) -> list:
    """내 계정에서 보는 공통 자료 — 원본에 내가 고친 것을 덮은 목록.

    꼬리표(저장하지 않는다): _key 원본 열쇠 · _base 지금 원본 · _local 내가 고침 ·
    _stale 고친 뒤 회사가 원본을 또 고침 · _orphan 원본이 없어짐(고친 것은 그대로 보여 준다)
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
    """편집 창의 '내 계정에서만' 목록(local_view 꼬리표 포함)을 저장한다. 바뀌었으면 True.

    원본과 같아진 것은 지운다(= 회사 자료로 되돌림 — 되돌린 표식을 남겨 다른 곳에도 전한다).
    손대지 않은 것은 그대로 둔다('회사가 또 고침' 표시도). 안내를 본 것(_ack)은 지금 원본을 본 것으로.
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
        new[k] = {"key": k, "base": base if base is not None else prev.get("base"), "item": c,
                  "at": utc_stamp()}

    def shape(d):
        return {k: (r["item"], r.get("base")) for k, r in d.items()}
    if shape(new) == shape(old):
        return False
    _save_local(list(new.values()))
    dead = load_local_dead()
    for k in set(old) | set(new):
        if k[1] != 0:
            continue
        if k in old and k not in new:
            dead[k[0]] = utc_stamp()
        elif k in new:
            dead.pop(k[0], None)
    _save_local_dead(dead)
    return True


# ---------------------------------------------------------------------------
# 검색
# ---------------------------------------------------------------------------
def haystack(item: dict) -> str:
    """검색 대상 문자열 — 제목·금융사·분류·태그·본문·체크리스트를 모두 본다."""
    return " ".join([
        item.get("title", ""), item.get("finance", ""), item.get("category", ""),
        item.get("tags", ""), item.get("body", ""),
        " ".join(item.get("checklist") or []),
        # 첨부 이름으로도 찾는다("위임장" 을 치면 위임장.pdf 가 든 자료가 나온다)
        " ".join(f.get("name", "") for f in (item.get("files") or [])),
    ])


def search(items: list, query: str, category: str = "") -> list:
    """`query` 로 거르고, 제목이 맞는 자료를 앞으로 올린다.

    제목 일치를 먼저 두는 이유: '신한 전자약정' 을 찾을 때 본문에 그 말이
    스쳐 지나가는 다른 자료보다, 제목이 그것인 자료가 위에 있어야 한다.
    """
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


def doc_templates(items: list) -> list:
    """서류 체크리스트로 쓸 수 있는 자료 — 분류가 '심사서류' 이고 항목이 있는 것."""
    return [it for it in (items or [])
            if it.get("category") == CAT_DOCS and it.get("checklist")]
