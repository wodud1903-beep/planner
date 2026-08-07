"""전역 설정·상수.

델파이 원본(uPlanData/uDash)의 값들을 그대로 옮겨왔다.
저장 위치는 %APPDATA%\\Planner (없으면 홈 디렉터리 하위).
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "일정관리기"
APP_ID = "Planner"

# ---------------------------------------------------------------------------
# 구글 OAuth (데스크톱 앱 클라이언트 내장)
#
# 데스크톱 앱에서 client_secret 은 완전한 비밀이 아니다(구글도 이를 전제로 함).
# 이 값을 앱에 내장해 두면 직원은 [Google 로그인] 버튼만 누르면 되고,
# Client ID/Secret 을 직접 입력할 필요가 없다.  ← 이번 개편의 핵심
#
# ⚠️ 이 클라이언트가 속한 구글 클라우드 프로젝트에서
#    - Google Calendar API
#    - Google Tasks API
#    두 가지가 '사용 설정'되어 있어야 하고, OAuth 동의 화면에 직원 계정이
#    테스트 사용자로 등록(또는 앱이 게시)되어 있어야 로그인할 수 있다.
# ---------------------------------------------------------------------------
GOOGLE_CLIENT_ID = "593737105209-fs5uf4btuvckv697uhnol9j6f36rj1ae.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = "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"

# 캘린더(읽기) + 할일(읽기/쓰기)
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/tasks",
]

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"

CALENDAR_LIST_URL = "https://www.googleapis.com/calendar/v3/users/me/calendarList"
CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/{cal_id}/events"
TASKLISTS_URL = "https://tasks.googleapis.com/tasks/v1/users/@me/lists"
TASKS_URL = "https://tasks.googleapis.com/tasks/v1/lists/{list_id}/tasks"
TASK_ITEM_URL = "https://tasks.googleapis.com/tasks/v1/lists/{list_id}/tasks/{task_id}"

# 콜백 서버가 시도할 포트 범위 (델파이 원본과 동일)
REDIRECT_PORT_RANGE = range(49200, 49231)

# ---------------------------------------------------------------------------
# 색상 (델파이 TColor 값을 RGB 로 환산)
# ---------------------------------------------------------------------------
# --- 델파이 스킨 'Tablet Light' 톤 (밝은 청회색 계열) ---
COLOR_TOPBAR = "#DCE6F0"       # 상단바 (연한 청회색)
COLOR_TOPBAR_TEXT = "#2C3E50"  # 상단바 글자 (짙은 남회색)
COLOR_WINDOW_BG = "#F5F7FA"    # 전체 배경
COLOR_ACCENT = "#5B8FBF"       # 포인트(선택/포커스) 색
COLOR_SELECT_BG = "#CFE0F4"    # 표 선택 행 배경
COLOR_BORDER = "#C6D3E0"       # 테두리
COLOR_HEADER_BG = "#E4ECF4"    # 표 헤더 배경

COLOR_TODAY = "#FFC98A"        # 오늘 강조 (Tablet Light 톤에 맞춘 부드러운 주황)
COLOR_TOMORROW = "#FFF2A8"     # 내일 강조 (부드러운 노랑)

# 알람 팝업: 사이렌은 주목도를 위해 진한 색 유지, 조용한 안내는 밝은 톤
COLOR_ALARM_RED = "#E05A5A"    # 알람 사이렌 빨강
COLOR_ALARM_DARK = "#3A4656"   # 알람 사이렌 어두운 배경(남회색)
COLOR_ALARM_YELLOW = "#FFE27A"  # 알람 제목 노랑
COLOR_BRIEF_BG = "#EDF2F8"     # 조용한 브리핑 배경(밝은 청회색)
COLOR_BRIEF_TEXT = "#2C3E50"   # 브리핑 글자

DAY_NAMES = ["", "일", "월", "화", "수", "목", "금", "토"]  # 1=일 .. 7=토

DEF_FOLLOW_MENT = (
    "%s 고객님, 안녕하세요.\n"
    "차량 출고 후 한 달이 지났는데 이용에 불편한 점은 없으신지요?\n"
    "필요하신 부분 있으시면 언제든 편하게 연락 주세요."
)


def data_dir() -> Path:
    """데이터 저장 폴더 (%APPDATA%\\Planner). 없으면 만든다."""
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / APP_ID
    d.mkdir(parents=True, exist_ok=True)
    return d


def data_file(name: str) -> Path:
    return data_dir() / name
