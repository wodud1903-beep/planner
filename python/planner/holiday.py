"""한국 공휴일 판별 (대체공휴일 포함).

`holidays` 라이브러리를 사용해 양력/음력(설·추석) 공휴일과
대체공휴일까지 모두 포함한다. 라이브러리를 못 불러오면
최소한의 고정 양력 공휴일이라도 빨간색으로 표시한다.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache

try:
    import holidays as _holidays  # type: ignore
except Exception:  # 라이브러리 없으면 폴백
    _holidays = None

# 폴백: 매년 날짜가 고정인 양력 공휴일(대체공휴일/음력 제외)
_FIXED = {
    (1, 1): "신정",
    (3, 1): "삼일절",
    (5, 5): "어린이날",
    (6, 6): "현충일",
    (8, 15): "광복절",
    (10, 3): "개천절",
    (10, 9): "한글날",
    (12, 25): "성탄절",
}


@lru_cache(maxsize=32)
def _kr(year: int):
    if _holidays is None:
        return None
    try:
        # KR: 설날·추석 등 음력 공휴일 + 대체공휴일(관측일) 포함
        return _holidays.country_holidays("KR", years=year)
    except Exception:
        return None


def is_holiday(d: date) -> bool:
    """해당 날짜가 (대체공휴일 포함) 공휴일이면 True."""
    h = _kr(d.year)
    if h is not None:
        return d in h
    return (d.month, d.day) in _FIXED


def holiday_name(d: date) -> str:
    h = _kr(d.year)
    if h is not None:
        return h.get(d, "") or ""
    return _FIXED.get((d.month, d.day), "")
