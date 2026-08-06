"""계약 후 팔로업 자동 등록 (델파이 uDash 의 ExtractCustomerName / CheckFollowUps 이식).

구글 캘린더에서 "<고객명> 출고" 형태의 일정을 찾아,
출고일 + N개월 - 3일에 [내 할일]로 자동 등록한다.
이미 등록한 일정은 UID 로 기록해 두 번 만들지 않는다.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .models import TodoItem

_COMPANY_MARKS = ("(주)", "주)", "㈜", "(유)", "주식회사", "(사)")


def _looks_like_company(s: str) -> bool:
    return any(m in s for m in _COMPANY_MARKS)


def _looks_like_name(s: str) -> bool:
    """사람 이름다운가: 공백 없는 한글 2~5자."""
    if not (2 <= len(s) <= 5):
        return False
    return all("가" <= c <= "힣" for c in s)


def extract_customer_name(summary: str, keyword: str) -> str:
    """캘린더 제목에서 고객명을 뽑는다. 형식에 안 맞으면 ''."""
    t = (summary or "").strip()
    if not t.endswith(keyword):
        return ""
    t = t[: len(t) - len(keyword)].strip()
    if not t:
        return ""

    if "/" in t:
        left, _, right = t.partition("/")
        left, right = left.strip(), right.strip()
        if not left or not right:
            return ""
        if _looks_like_company(left) and not _looks_like_company(right):
            result = right
        elif _looks_like_company(right) and not _looks_like_company(left):
            result = left
        elif _looks_like_name(left):
            result = left
        elif _looks_like_name(right):
            result = right
        else:
            result = left
    else:
        # 슬래시 없으면 남은 부분 전체가 이름이어야 한다
        result = t

    return result if _looks_like_name(result) else ""


class FollowupTracker:
    """이미 팔로업을 만든 캘린더 일정 UID 를 followups.json 에 보관."""

    def __init__(self, path: Path):
        self.path = path
        self.done: set[str] = set()
        self.last_scan: date | None = None
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self.done = set(str(x) for x in data)
            except Exception:
                pass

    def save(self):
        try:
            self.path.write_text(json.dumps(sorted(self.done), ensure_ascii=False),
                                 encoding="utf-8")
        except Exception:
            pass


def add_months(d: date, months: int) -> date:
    """d 에 months 개월을 더한다 (말일 보정)."""
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    # 해당 월의 마지막 날 보정
    import calendar
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def check_followups(settings, cal_events, todos: list[TodoItem],
                    tracker: FollowupTracker) -> int:
    """조건에 맞는 캘린더 일정을 todos 에 등록. 추가된 건수 반환."""
    if not settings.follow_on or not cal_events:
        return 0
    today = date.today()
    if tracker.last_scan == today:
        return 0
    tracker.last_scan = today

    keyword = (settings.follow_keyword or "출고").strip() or "출고"
    added = 0

    for ev in cal_events:
        if not ev.uid or ev.uid in tracker.done:
            continue
        name = extract_customer_name(ev.summary, keyword)
        if not name:
            continue

        target = add_months(ev.start.date(), settings.follow_months) - timedelta(days=3)
        if target > today:
            continue  # 아직 등록할 때가 아니면 다음 날 다시 검사
        if target < today - timedelta(days=14):
            tracker.done.add(ev.uid)  # 너무 오래된 건은 등록하지 않고 처리 완료로 기록
            continue

        ment = settings.follow_ment
        if "%s" in ment:
            ment = ment.replace("%s", name)

        it = TodoItem(
            title=f"[팔로업] {name} ({keyword} {settings.follow_months}개월)",
            run_date=target,
            run_time=settings.follow_time,
            has_time=True,
            alarm=settings.follow_alarm,
            repeats=False,
            ment=ment + "\n\n" + f"(출고일: {ev.start.strftime('%Y-%m-%d')} / 원 일정: {ev.summary})",
        )
        todos.append(it)
        tracker.done.add(ev.uid)
        added += 1

    return added
