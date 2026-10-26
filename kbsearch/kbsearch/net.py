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


def http() -> requests.Session:
    """이 스레드가 쓸 연결. 없으면 만들어 둔다."""
    s = getattr(_local, "session", None)
    if s is None:
        s = requests.Session()
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
