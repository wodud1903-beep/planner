"""서버 스위치 — 웹(kbsearch.vercel.app)의 [관리] 에서 지점장이 켜고 끈다.

`config.SWITCH_URL` 이 {"on": true|false, "message": "..."} 를 준다. **확실히 꺼짐
(on 이 JSON false)일 때만** 끈다. 인터넷이 안 되거나, 주소가 없어졌거나(404), 모양이
이상하면 켜짐으로 본다 — 웹 쪽 사고로 전 직원의 프로그램이 멈추면 안 된다(fail-open).

새 판을 내서 끄는 길(config.SERVICE_ON)도 그대로 있다. 둘 중 하나라도 꺼지면 꺼진다.
"""

from __future__ import annotations

from . import config
from .net import http as _http


def fetch_state(timeout: float = 6.0) -> dict | None:
    """{"on": bool, "message": str} 또는 None(못 읽음 — 켜짐으로 본다)."""
    if not config.SWITCH_URL:
        return None
    try:
        r = _http().get(config.SWITCH_URL, timeout=timeout,
                        headers={"Cache-Control": "no-cache"})
        if r.status_code != 200:
            return None
        o = r.json()
    except Exception:
        return None
    if not isinstance(o, dict) or not isinstance(o.get("on"), bool):
        return None
    msg = o.get("message")
    return {"on": o["on"], "message": msg.strip() if isinstance(msg, str) else ""}


def is_off(state: dict | None) -> bool:
    return isinstance(state, dict) and state.get("on") is False


def off_message(state: dict | None) -> str:
    return ((state or {}).get("message") or "").strip() or config.SERVICE_OFF_MESSAGE
