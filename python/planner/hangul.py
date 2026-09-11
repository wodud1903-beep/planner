"""한글 초성 검색 — 드롭다운에서 "ㄱㄹㅈ" 처럼 초성만 쳐도 찾게 해 준다.

한글 완성형 글자(가~힣)는 유니코드에서 규칙적으로 배열돼 있어
    (코드 - 0xAC00) // 588  →  초성 번호
로 초성을 바로 뽑을 수 있다. 별도 사전이 필요 없다.
"""

from __future__ import annotations

HANGUL_BASE = 0xAC00
HANGUL_LAST = 0xD7A3

# 초성 19자 (유니코드 배열 순서 그대로 — 순서를 바꾸면 안 된다)
CHOSUNG = (
    "ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ",
    "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ",
)
_CHOSUNG_SET = set(CHOSUNG)

# 키보드에서 겹자음을 안 치고 홑자음만 치는 사람이 많다.
# "ㅅㄴㅌ" 로도 "쏘나타"(초성 ㅆㄴㅌ)가 걸리도록 홑↔겹을 같은 것으로 본다.
_LOOSE = {"ㄲ": "ㄱ", "ㄸ": "ㄷ", "ㅃ": "ㅂ", "ㅆ": "ㅅ", "ㅉ": "ㅈ"}


def is_chosung_char(ch: str) -> bool:
    return ch in _CHOSUNG_SET


def chosung(text: str) -> str:
    """글자열의 초성 문자열. 한글이 아닌 글자는 소문자로 그대로 남긴다.

    "쏘나타 디 엣지" → "ㅆㄴㅌ ㄷ ㅇㅈ"
    """
    out = []
    for ch in text or "":
        code = ord(ch)
        if HANGUL_BASE <= code <= HANGUL_LAST:
            out.append(CHOSUNG[(code - HANGUL_BASE) // 588])
        else:
            out.append(ch.lower())
    return "".join(out)


def _loose(s: str) -> str:
    """겹자음을 홑자음으로 눕힌다(검색 비교용)."""
    return "".join(_LOOSE.get(ch, ch) for ch in s)


def _squash(s: str) -> str:
    """공백을 없애고 소문자로 — '디 엣지' 와 '디엣지' 를 같게 본다."""
    return "".join((s or "").split()).lower()


def _token_hit(hay: str, hay_cho: str, token: str) -> bool:
    tok = _squash(token)
    if not tok:
        return True
    if tok in hay:
        return True
    # 초성만 친 경우(ㄱㄴㄷ…) 또는 초성이 섞인 경우 — 초성 문자열에서 찾는다
    return _loose(tok) in hay_cho


def prepare(item: str) -> tuple:
    """찾을 대상을 미리 다듬어 둔다 — (눌린 글자, 초성).

    ⚠️ 이걸 따로 떼어 둔 이유: chosung() 은 글자 하나하나를 도는 일이라 값이
    싸지 않다. 예전엔 matches() 안에서 매번 다시 계산해서, 검색창에 한 자 칠
    때마다 파일 전체의 초성을 처음부터 다시 뽑았다. 파일 2만 개면 한 자에
    147ms — 타자가 눈에 띄게 밀렸다. 한 번 만들어 두고 쓰면 대여섯 배 빠르다.
    """
    hay = _squash(item)
    return hay, _loose(_squash(chosung(item)))


def matches_prepared(prepared: tuple, query: str) -> bool:
    """`prepare()` 로 미리 다듬어 둔 대상을 `query` 로 찾을 수 있는가."""
    q = (query or "").strip()
    if not q:
        return True
    hay, hay_cho = prepared
    return all(_token_hit(hay, hay_cho, t) for t in q.split())


def matches(item: str, query: str) -> bool:
    """`query` 로 `item` 을 찾을 수 있는가.

    - 띄어쓰기로 나눈 낱말은 **모두** 들어 있어야 한다(순서는 무관).
      "그랜저 하이" → "그랜저 하이브리드" ○, "쏘나타 하이브리드" ×
    - 낱말은 부분일치면 되고, 초성만 쳐도 된다.

    같은 대상을 여러 번 찾을 거라면 prepare() + matches_prepared() 를 쓴다.
    """
    q = (query or "").strip()
    if not q:
        return True
    return matches_prepared(prepare(item), q)


def rank(item: str, query: str) -> int:
    """정렬용 점수 — 작을수록 먼저. 완전일치 → 앞에서 시작 → 포함 → 초성."""
    q = _squash(query)
    hay = _squash(item)
    if not q:
        return 3
    if hay == q:
        return 0
    if hay.startswith(q):
        return 1
    if q in hay:
        return 2
    return 4


def filter_items(items, query: str) -> list:
    """`matches` 로 거른 뒤 `rank` 순으로 (원래 순서는 유지) 정렬한다."""
    hits = [(rank(it, query), i, it) for i, it in enumerate(items or [])
            if matches(it, query)]
    hits.sort(key=lambda x: (x[0], x[1]))
    return [it for _r, _i, it in hits]
