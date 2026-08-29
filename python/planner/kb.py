"""업무자료(자료검색함) 데이터 — 회사 공통 + 개인 메모.

**공통 자료** 는 수당율과 같은 전용 스프레드시트의 `업무자료` 탭에 있다.
관리자(`config.RATES_ADMINS`)만 고칠 수 있고, 나머지 PC 는 받아서 읽기만 한다.
받아온 내용은 `kb_shared.json` 에 캐시해 두어, 인터넷이 느리거나 끊겨도
프로그램을 켜자마자 검색이 된다.

**개인 메모** 는 `kb_mine.json` (계정 폴더). 누구나 자기 것만 적고,
드라이브 동기화로 본인의 다른 PC 에도 따라간다.

두 출처를 합쳐 하나의 목록으로 검색한다. 각 항목에는 `source` 가 붙어
화면에서 '공통 / 내 메모' 로 구분된다.
"""

from __future__ import annotations

import json

from . import config, hangul
from .kb_seed import DEFAULTS

SHARED_FILE = "kb_shared.json"
MINE_FILE = "kb_mine.json"

SRC_SHARED = "shared"
SRC_MINE = "mine"
SRC_NAMES = {SRC_SHARED: "공통", SRC_MINE: "내 메모"}

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
    return {
        "category": str(o.get("category", "")).strip(),
        "finance": str(o.get("finance", "")).strip(),
        "title": title,
        "tags": str(o.get("tags", "")).strip(),
        "body": norm_body(o.get("body", "")),
        "checklist": [str(c).strip() for c in checks if str(c).strip()],
    }


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
    _save_file(MINE_FILE, items)


def load_all() -> list:
    """공통 + 개인을 합친 목록. 각 항목에 source 가 붙는다."""
    out = []
    for it in load_shared():
        it = dict(it)
        it["source"] = SRC_SHARED
        out.append(it)
    for it in load_mine():
        it = dict(it)
        it["source"] = SRC_MINE
        out.append(it)
    return out


# ---------------------------------------------------------------------------
# 검색
# ---------------------------------------------------------------------------
def haystack(item: dict) -> str:
    """검색 대상 문자열 — 제목·금융사·분류·태그·본문·체크리스트를 모두 본다."""
    return " ".join([
        item.get("title", ""), item.get("finance", ""), item.get("category", ""),
        item.get("tags", ""), item.get("body", ""),
        " ".join(item.get("checklist") or []),
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
