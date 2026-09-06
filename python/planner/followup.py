"""계약 후 팔로업 자동 등록 (델파이 uDash 의 ExtractCustomerName / CheckFollowUps 이식).

구글 캘린더에서 "<고객명> 출고" 형태의 일정을 찾아,
출고일 + N개월 - 3일에 [내 할일]로 자동 등록한다.
이미 등록한 일정은 UID 로 기록해 두 번 만들지 않는다.
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path

from . import config
from .models import TodoItem

_COMPANY_MARKS = ("(주)", "주)", "㈜", "(유)", "주식회사", "(사)")

# 며칠 앞까지 미리 올려 둘지
AHEAD_DAYS = 14

# 제목에서 이름을 도로 꺼낸다. 이름을 따로 저장하지 않는 이유: 예전 버전이
# 만들어 둔 할일에는 그 칸이 없고, 그 할일들도 중복 판정에 넣어야 한다.
#
# 지금 쓰는 모양 : "[출고 1개월] 홍길동"
# 예전에 쓰던 모양: "[팔로업] 홍길동 (출고 1개월)"
# 캘린더에 이미 올라간 옛 제목도 읽어야 해서 둘 다 본다.
_NEW_RE = re.compile(r"^\s*\[[^\[\]]*\d+\s*개월\]\s*(.+?)\s*$")
_OLD_RE = re.compile(r"^\s*\[팔로업\]\s*(.+?)\s*(?:\(|$)")


def make_title(name: str, keyword: str, months: int) -> str:
    """팔로업 할일·캘린더 일정 제목. 이 한 곳에서만 만든다."""
    return f"[{(keyword or '출고').strip()} {int(months)}개월] {str(name).strip()}"


def followup_name(title: str) -> str:
    """팔로업 제목에서 고객명. 팔로업이 아니면 ''."""
    t = str(title or "")
    m = _NEW_RE.match(t) or _OLD_RE.match(t)
    return m.group(1).strip() if m else ""


def is_old_title(title: str) -> bool:
    """예전 '[팔로업] …' 모양인가 (바꿔 줘야 하는 제목인가)."""
    return bool(_OLD_RE.match(str(title or "")))


def rename_old(title: str, keyword: str, months: int) -> str:
    """예전 모양이면 새 모양으로. 아니면 그대로 돌려준다.

    개월 수는 **제목에 적힌 값**을 먼저 쓴다. 설정을 나중에 1→3개월로 바꿨다면
    예전에 만든 '1개월' 건까지 3개월로 둔갑시키면 안 된다.
    """
    t = str(title or "")
    if not is_old_title(t):
        return t
    name = followup_name(t)
    if not name:
        return t
    m = re.search(r"\(\s*(.*?)\s*(\d+)\s*개월\s*\)", t)
    if m:
        return make_title(name, m.group(1) or keyword, int(m.group(2)))
    return make_title(name, keyword, months)


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
            config.atomic_write(
                self.path, json.dumps(sorted(self.done), ensure_ascii=False))
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
                    tracker: FollowupTracker) -> list[TodoItem]:
    """조건에 맞는 캘린더 일정을 todos 에 등록. 추가된 TodoItem 목록 반환.

    **앞으로 2주치를 미리 올려 둔다.** 예전엔 팔로업 날짜가 되어야 할일이
    생겨서, 그날 아침에야 '오늘 전화할 곳' 을 알았다. 미리 보이면 주 단위로
    묶어서 돌릴 수 있다.

    미리 올리는 만큼 **같은 고객이 두 줄로 서지 않게** 이름으로도 막는다.
    한 고객의 출고 일정이 캘린더에 두 번 들어가 있거나(수정하며 새로 만든 경우),
    차를 두 대 뽑은 경우가 실제로 있다. 일정 UID 로만 막으면 그때 이름이 같은
    팔로업이 두 개 생긴다.
    """
    if not settings.follow_on or not cal_events:
        return []
    today = date.today()
    # 예전엔 '하루 한 번' 으로 막아 두어, 그날 늦게 만들어진 출고 일정을 새로고침해도
    # 다음 날까지 팔로업이 등록되지 않았다. 중복은 아래 tracker.done(일정별 기록)이
    # 막아 주므로 매 조회마다 검사한다.
    tracker.last_scan = today

    keyword = (settings.follow_keyword or "출고").strip() or "출고"
    added: list[TodoItem] = []

    # 이미 할일에 올라와 있는 팔로업의 고객명 (완료한 것도 센다 — 이미 연락한
    # 고객에게 또 걸 이유가 없다)
    taken = {n for n in (followup_name(t.title) for t in (todos or [])) if n}

    # 가까운 일정부터 자리를 잡게 한다. 같은 고객의 일정이 둘이면 빠른 쪽이
    # 남아야, 늦은 쪽을 보고 '이미 지났다' 고 착각하지 않는다.
    def _when(ev):
        return add_months(ev.start.date(), settings.follow_months)

    for ev in sorted(cal_events, key=lambda e: e.start):
        if not ev.uid or ev.uid in tracker.done:
            continue
        name = extract_customer_name(ev.summary, keyword)
        if not name:
            continue

        target = _when(ev) - timedelta(days=3)
        if target > today + timedelta(days=AHEAD_DAYS):
            continue  # 2주보다 더 먼 건은 아직 이르다 — 다음 조회 때 다시 본다
        if target < today - timedelta(days=14):
            tracker.done.add(ev.uid)  # 너무 오래된 건은 등록하지 않고 처리 완료로 기록
            continue
        if name in taken:
            # 같은 고객이 이미 서 있다. 이 일정은 '처리했다' 고 적어 두어야
            # 매번 다시 검사하다가 앞 팔로업을 지운 순간 뒤늦게 튀어나오지 않는다.
            tracker.done.add(ev.uid)
            continue

        ment = settings.follow_ment
        if "%s" in ment:
            ment = ment.replace("%s", name)

        it = TodoItem(
            title=make_title(name, keyword, settings.follow_months),
            run_date=target,
            run_time=settings.follow_time,
            has_time=True,
            alarm=settings.follow_alarm,
            repeats=False,
            ment=ment + "\n\n" + f"(출고일: {ev.start.strftime('%Y-%m-%d')} / 원 일정: {ev.summary})",
        )
        todos.append(it)
        tracker.done.add(ev.uid)
        taken.add(name)
        added.append(it)

    return added


# ---------------------------------------------------------------------------
# 옛 제목 바꾸기 ("[팔로업] 홍길동 (출고 1개월)" → "[출고 1개월] 홍길동")
# ---------------------------------------------------------------------------
def rename_old_todos(todos, keyword: str, months: int) -> int:
    """내 할일에 남은 옛 제목을 새 모양으로. 바꾼 개수를 돌려준다."""
    n = 0
    for it in todos or []:
        new = rename_old(it.title, keyword, months)
        if new != it.title:
            it.title = new
            n += 1
    return n


def old_title_events(cal_events, keyword: str, months: int) -> list:
    """캘린더에서 옛 제목인 일정 → [(일정, 새 제목)].

    고칠 수 있는 것만 고른다 — cal_id/event_id 가 없으면 수정 API 를 못 부른다
    (읽기 전용으로 구독한 캘린더 등).
    """
    out = []
    for ev in cal_events or []:
        if not getattr(ev, "event_id", "") or not getattr(ev, "cal_id", ""):
            continue
        new = rename_old(ev.summary, keyword, months)
        if new != ev.summary:
            out.append((ev, new))
    return out
