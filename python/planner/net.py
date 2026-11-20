"""구글에 말을 걸 때 쓰는 연결 하나.

왜 따로 두나
------------
예전에는 구글을 부를 때마다 requests.get / requests.post 를 그냥 썼다. 그러면
**호출마다 새로 접속**한다 — TCP 를 맺고 TLS 악수를 하고 나서야 본론이 시작된다.
사무실 망에서 그 준비만 한 번에 0.1~0.3초다. 고객관리 시트를 한 번 불러오는 데도
여러 번 오가므로, 그 준비 시간이 그대로 쌓여 '불러오는 중' 이 길어졌다.

연결을 한 번 맺어 두고 계속 쓰면 두 번째 호출부터는 그 준비가 없다.

왜 스레드마다 따로 두나
----------------------
requests 의 Session 은 여러 스레드가 같이 쓰라고 만든 물건이 아니다. 이 앱은
화면이 멈추지 않도록 거의 모든 조회를 백그라운드 스레드에서 하고, 드라이브를
훑을 때는 여러 스레드가 동시에 돈다. 그래서 '스레드마다 제 것 하나' 로 둔다 —
서로 건드리지 않으면서 같은 스레드 안에서는 연결을 재사용한다.
"""

from __future__ import annotations

import threading

import requests

_local = threading.local()

# ---------------------------------------------------------------------------
# 읽기만 하는 스프레드시트(v1.34.2) — 이 프로그램은 여기에 **절대 쓰지 않는다**
# ---------------------------------------------------------------------------
# 지점장: "수입차 프로모션 시트가 강제로 수정된 이력이 있다. 절대 할인내역이 수정되면 안 된다."
# 프로모션 화면은 처음부터 읽기(GET)만 했지만, 로그인 권한(spreadsheets)으로는 고칠 수도 있다.
# 그래서 모든 구글 요청이 지나는 이 연결에서 막는다 — 이 시트(파일) 주소로 가는 GET 이 아닌 요청
# (값 쓰기·지우기·서식·탭 추가·드라이브 이름 바꾸기·휴지통 …)은 보내지 않고 ReadOnlySheet 를 던진다.
_READ_ONLY: set = set()
_SAFE = ("GET", "HEAD", "OPTIONS")


class ReadOnlySheet(Exception):
    """읽기 전용으로 정한 시트에 쓰려 했다 — 보내지 않았다."""


def protect(sheet_id: str) -> None:
    """이 스프레드시트를 읽기 전용으로(이 프로그램이 켜져 있는 동안)."""
    sid = str(sheet_id or "").strip()
    if len(sid) >= 20:               # 진짜 시트 id 만(짧은 글자로 엉뚱한 주소가 막히지 않게)
        _READ_ONLY.add(sid)


def is_protected(sheet_id: str) -> bool:
    return str(sheet_id or "").strip() in _READ_ONLY


def check_write(method: str, url: str) -> None:
    """읽기 전용 시트로 가는 쓰기 요청이면 ReadOnlySheet."""
    if str(method or "GET").upper() in _SAFE:
        return
    u = str(url or "")
    for sid in _READ_ONLY:
        if sid in u:
            raise ReadOnlySheet("수입차 프로모션 시트는 읽기 전용입니다 — 이 프로그램은 그 시트를 고치지 않습니다.")


class _Guarded(requests.Session):
    """보내기 직전에 check_write 를 거친다(get·post·put·patch·delete 가 모두 request 로 모인다)."""

    def request(self, method, url, *args, **kwargs):
        check_write(method, url)
        return super().request(method, url, *args, **kwargs)


def http() -> requests.Session:
    """이 스레드가 쓸 연결. 없으면 만들어 둔다."""
    s = getattr(_local, "session", None)
    if s is None:
        s = _Guarded()
        _local.session = s
    return s


def close() -> None:
    """이 스레드의 연결을 닫는다(끝낼 때 한 번). 안 닫아도 큰일은 없다."""
    s = getattr(_local, "session", None)
    if s is not None:
        try:
            s.close()
        except Exception:
            pass
        _local.session = None
