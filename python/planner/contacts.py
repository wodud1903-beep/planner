"""고객의 금융사 연락처를 화면에서 바로 꺼내 쓰기.

상담 중에 "이 고객 캐피탈 콜센터가 몇 번이더라" 를 찾으려면 지금은 자료검색
탭으로 옮겨 가 금융사를 다시 쳐야 한다. 고객 줄에 이미 금융사가 적혀 있으니
그 줄에서 바로 번호가 나와야 한다.

번호는 두 곳에서 온다. **차례가 중요하다.**

1. **시트 P·Q 열** — 고객관리 시트가 금융사에 맞춰 이미 계산해 둔 번호다.
   그 시트를 쓰시는 분이 직접 관리하는 값이라 가장 믿을 만하다.
2. **자료검색 자료** — 시트에 없을 때(수식이 비었거나 새 금융사) 쓰는 예비.

2번은 이름을 맞춰 찾아야 하는데, 여기서 **틀린 번호를 보여 주면 안 된다**.
'우리캐피탈' 은 `우리금융캐피탈` 일 수도 `JB우리캐피탈` 일 수도 있다. 후보가
둘 이상이면 하나를 고르지 않고 그대로 돌려주어, 화면이 물어보게 한다.
"""

from __future__ import annotations

import re

# "■ 연락처" 처럼 머리글로 쓰는 표시 (kb_seed 가 본문을 이렇게 만든다)
_HEAD = "■"
# "· 콜센터 : 1588-2114" 한 줄
_ITEM_RE = re.compile(r"^[·\-*]\s*(.+?)\s*[:：]\s*(.+?)\s*$")
# 전화번호로 볼 수 있는 토막 — 1588-2114 / 02-123-4567 / 010 1234 5678
_TEL_RE = re.compile(r"\d[\d\-\s]{6,}\d")

# 연락처가 들어 있는 머리글 이름
CONTACT_HEADS = ("연락처", "사고접수")


def _norm(s: str) -> str:
    """이름 비교용으로 다듬는다 — 공백·괄호·법인 표기를 턴다.

    '(주)우리금융캐피탈 (리스)' 와 '우리금융캐피탈' 이 같은 것으로 보여야 한다.
    """
    t = str(s or "")
    t = re.sub(r"\([^)]*\)", " ", t)          # 괄호 안은 부가 설명
    t = t.replace("주식회사", " ").replace("(주)", " ")
    t = re.sub(r"[\s·,/]+", "", t)
    return t.lower()


# 어느 회사에나 붙는 말 — 이것만 다른 이름은 같은 회사일 수 있다
_GENERIC = ("캐피탈", "캐피털", "렌터카", "렌트카", "렌탈", "카드", "금융",
            "오토리스", "리스", "손해보험", "화재보험", "보험", "은행")


def _core(s: str) -> str:
    """이름에서 '캐피탈·카드·금융' 같은 꼬리말을 떼어 알맹이만 남긴다.

    `우리금융캐피탈` → `우리`, `JB우리캐피탈` → `jb우리`, `신한카드` → `신한`.
    이렇게 해야 시트에 `우리캐피탈` 이라고만 적힌 줄이 **두 회사 모두의**
    후보로 잡힌다. 알맹이만 비교하지 않으면 `우리캐피탈` 이 글자가 이어지는
    `JB우리캐피탈` 하나에만 걸려, 묻지도 않고 남의 번호를 보여 준다.

    다 떼어 아무것도 안 남으면(그냥 '캐피탈') 원래 이름을 쓴다.
    """
    t = _norm(s)
    changed = True
    while changed:
        changed = False
        for w in _GENERIC:
            if len(t) > len(w) and t.endswith(w):
                t, changed = t[: -len(w)], True
                break
    return t or _norm(s)


def _same_family(a: str, b: str) -> bool:
    """알맹이가 서로의 앞뒤에 붙어 있으면 같은 계열로 본다.

    앞이나 뒤여야 한다 — 가운데에 우연히 끼는 것까지 받으면 엉뚱한 회사가 는다.
    두 글자 미만은 비교하지 않는다(한 글자는 아무 데나 걸린다).
    """
    if not a or not b or min(len(a), len(b)) < 2:
        return False
    lo, hi = (a, b) if len(a) <= len(b) else (b, a)
    return hi.startswith(lo) or hi.endswith(lo)


def sections(body: str) -> list[tuple[str, str]]:
    """본문을 '■ 머리글' 단위로 나눈다 → [(머리글, 내용)].

    머리글이 없는 앞부분은 ('', 내용) 으로 맨 앞에 온다.
    """
    out: list[tuple[str, list]] = []
    head, buf = "", []
    for line in str(body or "").split("\n"):
        if line.strip().startswith(_HEAD):
            if head or buf:
                out.append((head, buf))
            head, buf = line.strip().lstrip(_HEAD).strip(), []
        else:
            buf.append(line)
    if head or buf:
        out.append((head, buf))
    return [(h, "\n".join(b).strip()) for h, b in out]


def phones_of(item: dict) -> list[tuple[str, str]]:
    """자료 한 건에서 [(이름, 번호)] 를 뽑는다.

    '■ 연락처' 와 '■ 사고접수' 아래의 '· 콜센터 : 1588-2114' 꼴만 본다.
    본문 아무 데나 있는 숫자까지 주우면 계약조건의 금액이 전화번호로 둔갑한다.
    """
    out = []
    for head, text in sections(item.get("body", "")):
        if not any(k in head for k in CONTACT_HEADS):
            continue
        for line in text.split("\n"):
            m = _ITEM_RE.match(line.strip())
            if not m:
                continue
            label, value = m.group(1).strip(), m.group(2).strip()
            if _TEL_RE.search(value):
                out.append((label, value))
    return out


def candidates(items: list, finance: str) -> list[dict]:
    """금융사 이름으로 자료 후보를 찾는다 (연락처가 있는 것만).

    정확히 같은 이름이 있으면 그것 하나만 돌려준다. 없으면 서로 포함하는
    이름과 태그가 맞는 것을 모아 **여러 건 그대로** 돌려준다 — 하나를 임의로
    고르면 다른 캐피탈 번호로 전화를 걸게 된다.
    """
    want = _norm(finance)
    if not want:
        return []
    want_core = _core(finance)
    exact, loose = [], []
    for it in items or []:
        if not phones_of(it):
            continue
        names = [n for n in (it.get("finance", ""), it.get("title", ""))
                 if str(n or "").strip()]
        norms = [_norm(n) for n in names]
        if want in norms:
            exact.append(it)
            continue
        tags = [t for t in str(it.get("tags", "")).split() if t]
        if want in [_norm(t) for t in tags]:
            exact.append(it)
            continue
        if any(_same_family(want_core, _core(n)) for n in names + tags):
            loose.append(it)
    if exact:
        return exact[:1]
    # 이름이 긴 것이 더 구체적이다 (우리금융캐피탈 이 우리 보다 앞)
    loose.sort(key=lambda it: -len(_norm(it.get("finance") or it.get("title"))))
    return loose


def sheet_phones(cr) -> list[tuple[str, str]]:
    """고객 줄에 시트가 계산해 둔 번호 — P 고객센터 / Q 사고접수."""
    out = []
    for label, value in (("고객센터", getattr(cr, "center", "")),
                         ("사고접수", getattr(cr, "accident", ""))):
        v = str(value or "").strip()
        if v and _TEL_RE.search(v):
            out.append((label, v))
    return out


def for_customer(items: list, cr) -> tuple[list[tuple[str, str]], list[dict]]:
    """고객 한 명에게 보여 줄 (번호 목록, 못 정한 후보 목록).

    - 시트에 번호가 있으면 그것을 쓴다(후보는 비어 있다).
    - 없으면 자료에서 찾는다. 딱 하나면 그 번호를, 여럿이면 번호 없이
      후보만 돌려준다 — 화면이 어느 금융사인지 물어본다.
    """
    got = sheet_phones(cr)
    if got:
        return got, []
    cands = candidates(items, cr.get("finance"))
    if len(cands) == 1:
        return phones_of(cands[0]), []
    return [], cands


def tel_digits(number: str) -> str:
    """'1588-2114 / 1644-3000' → '15882114' (앞의 한 개만, 숫자만)."""
    m = _TEL_RE.search(str(number or ""))
    if not m:
        return ""
    return re.sub(r"\D", "", m.group(0))
