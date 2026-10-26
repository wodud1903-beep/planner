"""전역 설정·상수 — 업무자료검색.

일정관리기(python/planner)에서 '자료검색' 화면만 떼어 낸 가벼운 프로그램이다.
데이터는 이 PC 의 %APPDATA%\\KbSearch 에만 둔다. 로그인은 [동기화] 를 누를 때만 한다.
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "업무자료검색"
APP_ID = "KbSearch"
APP_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# 서비스 스위치 — **자동 업데이트로 끄고 켠다.**
#
# 업데이트는 건너뛸 수 없다(updater.py). 그래서 이 값을 바꿔 새 판을 내면
# 모든 PC 가 그 판으로 바뀌면서 그대로 따른다.
#   SERVICE_ON = False : 프로그램이 안내만 띄우고 끝난다(업데이트 확인은 계속 한다 —
#                        다시 켜는 판을 내면 그 판으로 바뀌며 살아난다).
#   SYNC_ON    = False : 검색·편집은 그대로, [동기화](구글 로그인·시트·드라이브)만 사라진다.
#                        구글 쪽(시트·클라우드 프로젝트)을 닫기 전에 이 판을 먼저 낸다.
# ---------------------------------------------------------------------------
SERVICE_ON = True
SERVICE_OFF_MESSAGE = (
    "업무자료검색 서비스가 종료되었습니다.\n"
    "그동안 이용해 주셔서 감사합니다.")
SYNC_ON = True

# ---------------------------------------------------------------------------
# 자동 업데이트 — 일정관리기와 같은 저장소의 릴리스를 쓰되, 태그 머리말로 가른다.
#   일정관리기: v1.21.1         업무자료검색: kb-v1.0.0
# ⚠️ 릴리스는 '최신(latest)' 으로 표시하지 않는다(워크플로의 make_latest: false).
#    일정관리기 업데이트는 releases/latest 를 보므로, 이 프로그램 릴리스가 latest 가
#    되면 일정관리기 PC 들이 새 판을 못 찾는다.
# ---------------------------------------------------------------------------
UPDATE_REPO = "wodud1903-beep/planner"
UPDATE_TAG_PREFIX = "kb-v"
UPDATE_ASSET_NAME = "업무자료검색.exe"
UPDATE_CHECK_HOURS = 3          # 켜 둔 채로 지내도 이 간격으로 다시 확인한다

# ---------------------------------------------------------------------------
# 구글 OAuth — 일정관리기와 **같은 클라이언트**.
#   · 클라우드 프로젝트·동의 화면·테스트 사용자 설정을 그대로 쓴다.
#   · 드라이브 앱 전용 공간(appDataFolder)이 클라이언트(프로젝트)별이라, 같은
#     클라이언트여야 일정관리기의 '내 메모' 를 같이 볼 수 있다(sync.py).
# 권한은 동기화에 필요한 것만 묻는다(캘린더·할일은 묻지 않는다).
# ---------------------------------------------------------------------------
GOOGLE_CLIENT_ID = "593737105209-fs5uf4btuvckv697uhnol9j6f36rj1ae.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = "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"
GOOGLE_SCOPES = [
    "openid",
    "email",
    # 회사 공통 자료 — 스프레드시트 '업무자료' 탭 읽기(관리자는 쓰기)
    "https://www.googleapis.com/auth/spreadsheets",
    # 내 메모 — 일정관리기와 같은 동기화 묶음(planner_sync.json)
    "https://www.googleapis.com/auth/drive.appdata",
    # 첨부(그림·PDF) — 앱이 올린 파일에만 접근하는 최소 권한
    "https://www.googleapis.com/auth/drive.file",
]

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
# 일정관리기와 같은 범위 — 동시에 로그인해도 비어 있는 다음 포트를 쓴다
REDIRECT_PORT_RANGE = range(49200, 49231)

GOOGLE_PROJECT_NUMBER = GOOGLE_CLIENT_ID.split("-")[0]
SHEETS_ENABLE_URL = (
    "https://console.developers.google.com/apis/api/sheets.googleapis.com/overview"
    f"?project={GOOGLE_PROJECT_NUMBER}"
)

DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
DRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
SHEETS_BASE_URL = "https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
SHEETS_VALUES_URL = SHEETS_BASE_URL + "/values/{rng}"
SHEETS_BATCH_UPDATE_URL = SHEETS_BASE_URL + ":batchUpdate"

# 회사 공통 업무자료 — 일정관리기와 **같은 스프레드시트·같은 탭**.
# (일정관리기 config.RATES_SHEET_ID — 수당율과 업무자료가 같이 든 전용 파일)
KB_SHEET_ID = "1PSjqA7wvIBHusjYHFfD9cLKP-EbtdFrCkNqlZHz2jm0"
KB_TAB = "업무자료"

# 회사 공통 자료를 고칠 수 있는 계정(일정관리기 RATES_ADMINS 와 같다)
KB_ADMINS = ("wodud1903@gmail.com",)

# 일정관리기의 드라이브 동기화 묶음 — '내 메모'(kb_mine.json) 칸만 같이 쓴다
PLANNER_SYNC_FILE = "planner_sync.json"
PLANNER_APP_ID = "Planner"      # 처음 켤 때 이 PC 의 일정관리기 공통 자료를 가져온다


def is_admin(email: str) -> bool:
    return (email or "").strip().lower() in KB_ADMINS


def atomic_write(path, text: str) -> None:
    """임시파일에 쓴 뒤 교체 — 도중에 죽어도 원본이 깨지지 않는다."""
    p = Path(path)
    tmp = p.with_name(p.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def appdata() -> Path:
    return Path(os.environ.get("APPDATA") or str(Path.home()))


def base_dir() -> Path:
    """데이터 폴더 (%APPDATA%\\KbSearch). 계정별로 나누지 않는다 — 이 PC 의 것이다."""
    d = appdata() / APP_ID
    d.mkdir(parents=True, exist_ok=True)
    return d


def data_file(name: str) -> Path:
    return base_dir() / name
