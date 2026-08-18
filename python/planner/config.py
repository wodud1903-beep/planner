"""전역 설정·상수.

델파이 원본(uPlanData/uDash)의 값들을 그대로 옮겨왔다.
저장 위치는 %APPDATA%\\Planner (없으면 홈 디렉터리 하위).
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "일정관리기"
APP_ID = "Planner"
APP_VERSION = "1.2.4"

# 자동 업데이트: 이 저장소의 최신 릴리스를 확인
UPDATE_REPO = "wodud1903-beep/planner"
# 비공개 저장소면 릴리스 자산 다운로드에 읽기 권한 토큰이 필요.
# 우선순위: (1) 빌드 시 주입된 내장 토큰(_secret.py) → (2) %APPDATA%\Planner\gh_token.txt
# _secret.py 는 git 에 커밋하지 않고, GitHub Actions 의 UPDATE_TOKEN 시크릿에서 빌드 때만 생성된다.
try:
    from ._secret import UPDATE_TOKEN as GITHUB_TOKEN  # noqa: F401
except Exception:
    GITHUB_TOKEN = ""
UPDATE_ASSET_NAME = "일정관리기.exe"

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

# 권한(scope):
#  - openid/email : 로그인 계정 이메일 식별(계정별 저장/동기화)
#  - calendar     : 캘린더 목록 + 일정 읽기/쓰기(캘린더 창에서 일정 추가)
#  - tasks        : 할일 읽기/쓰기
#  - drive.appdata: 다중 PC 동기화용 앱 전용 저장공간(사용자 눈에 안 보임)
#  - spreadsheets : 고객관리 스프레드시트 읽기/쓰기
# ⚠️ 구글 클라우드 프로젝트에서 Calendar / Tasks / Drive / Sheets API 사용설정 필요.
# ⚠️ spreadsheets 권한은 나중에 추가되었다. 기존 사용자는 [설정] → Google 다시 로그인을
#    한 번 해야 시트 기능을 쓸 수 있다(다른 기능은 재로그인 없이 그대로 동작).
GOOGLE_SCOPES = [
    "openid",
    "email",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/drive.appdata",
    "https://www.googleapis.com/auth/spreadsheets",
    # 견적서/계약서 이미지 업로드 — 앱이 만든 파일에만 접근하는 최소 권한
    "https://www.googleapis.com/auth/drive.file",
]

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

# 클라우드 프로젝트 번호 (클라이언트 ID 앞부분) — API 사용설정 안내에 쓴다
GOOGLE_PROJECT_NUMBER = GOOGLE_CLIENT_ID.split("-")[0]
SHEETS_ENABLE_URL = (
    "https://console.developers.google.com/apis/api/sheets.googleapis.com/overview"
    f"?project={GOOGLE_PROJECT_NUMBER}"
)
SCOPE_SHEETS = "https://www.googleapis.com/auth/spreadsheets"

CALENDAR_LIST_URL = "https://www.googleapis.com/calendar/v3/users/me/calendarList"
CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/{cal_id}/events"
TASKLISTS_URL = "https://tasks.googleapis.com/tasks/v1/users/@me/lists"
TASKS_URL = "https://tasks.googleapis.com/tasks/v1/lists/{list_id}/tasks"
TASK_ITEM_URL = "https://tasks.googleapis.com/tasks/v1/lists/{list_id}/tasks/{task_id}"

# Drive appDataFolder (앱 전용 숨김 폴더) — 동기화용
DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
DRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"

# Google Sheets (고객관리 리스트 연동)
SHEETS_BASE_URL = "https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
SHEETS_VALUES_URL = SHEETS_BASE_URL + "/values/{rng}"
SHEETS_BATCH_GET_URL = SHEETS_BASE_URL + "/values:batchGet"
SHEETS_BATCH_UPDATE_VALUES_URL = SHEETS_BASE_URL + "/values:batchUpdate"
SHEETS_BATCH_UPDATE_URL = SHEETS_BASE_URL + ":batchUpdate"

# 기본 고객관리 시트 (설정에서 변경 가능)
DEF_SHEET_ID = "1L6UwkuywIEAffPvQX9GWwsP8Ix_6fP8uakNFfV1iAm8"
DEF_SHEET_NAME = "미출고차량"

# 차종별 수당율 전용 스프레드시트 — **고정**.
# 수당율은 회사가 한 곳에서 관리하는 값이라, 각 PC 가 어떤 고객관리 시트를 쓰든
# 항상 이 파일 하나만 바라본다. (고객관리 시트에 두면 시트를 바꾼 PC 끼리
# 서로 다른 수당율을 쓰게 된다)
RATES_SHEET_ID = "1PSjqA7wvIBHusjYHFfD9cLKP-EbtdFrCkNqlZHz2jm0"

# 수당율을 고칠 수 있는 계정. 모두가 같은 값을 쓰는 회사 기준값이라,
# 직원이 실수로 바꾸지 못하도록 관리자 계정에서만 편집을 허용한다.
RATES_ADMINS = ("wodud1903@gmail.com",)


def is_rates_admin(email: str) -> bool:
    return (email or "").strip().lower() in RATES_ADMINS

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


def atomic_write(path, text: str) -> None:
    """임시파일에 쓴 뒤 교체 — 도중에 죽어도 원본이 깨지지 않는다.

    예전엔 write_text 로 바로 덮어써서, 저장 중 강제종료/정전이 나면 파일이
    반쯤 잘린 채 남았다. 읽는 쪽은 예외를 삼키고 빈 목록을 돌려주므로
    다음 저장에서 그 빈 상태가 확정돼 할일이 통째로 사라졌다.
    """
    p = Path(path)
    tmp = p.with_name(p.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)          # 같은 볼륨이면 원자적으로 교체된다


def base_dir() -> Path:
    """앱 최상위 폴더 (%APPDATA%\\Planner)."""
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / APP_ID
    d.mkdir(parents=True, exist_ok=True)
    return d


# 현재 로그인 계정(이메일) — 로그인 후 설정됨. 계정별로 데이터를 분리 저장한다.
_current_account: str = ""


def set_account(email: str) -> None:
    global _current_account
    _current_account = (email or "").strip().lower()


def _safe(email: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-@" else "_" for ch in email)


def data_dir() -> Path:
    """데이터 저장 폴더.

    로그인 계정이 있으면 계정별 하위 폴더(accounts/<email>)에 저장해
    한 PC에서 계정을 바꿔도 데이터가 섞이지 않게 한다.
    로그인 전이나 미연결이면 공용 폴더를 쓴다.
    """
    d = base_dir()
    if _current_account:
        d = d / "accounts" / _safe(_current_account)
    d.mkdir(parents=True, exist_ok=True)
    return d


def data_file(name: str) -> Path:
    return data_dir() / name


SCOPE_DRIVE_FILE = "https://www.googleapis.com/auth/drive.file"
