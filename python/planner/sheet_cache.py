"""고객 목록 저장본 — 켜자마자 지난번 목록을 보여 주고, 뒤에서 새로 읽는다(v1.26).

예전엔 켤 때마다 시트를 다 읽을 때까지(1~3초, 인터넷이 없으면 영영) 고객 목록·보드·
대시보드가 비어 있었다. 이제 마지막으로 읽은 그대로(시트에서 받은 값 그대로)를 계정
폴더에 두었다가 켜자마자 그린다. 새로 읽으면 그것으로 바꾼다.

  · 저장본으로 보이는 동안에도 고치기는 된다 — 시트에 쓰기 직전에 그 줄을 다시 읽어
    다른 고객이 와 있으면 멈추는 길(sheets.update_row)이 그대로 지킨다. 새 고객도
    실제 마지막 줄을 다시 보고 그 아래에 쓴다(sheets.append_row).
  · 출고 일정·자동 규칙·월 마감처럼 '바뀐 것을 보고 무엇을 하는' 일은 **새로 읽은
    것으로만** 한다(main_window._sheet_loaded). 어제 것을 보고 할일을 만들면 안 된다.
  · 동기화하지 않는다 — PC 마다 그때그때 읽은 것. 계정 폴더 안이라 계정끼리 섞이지 않는다.
"""

from __future__ import annotations

import json
from datetime import datetime

from . import config

FILE = "sheet_cache.json"
VER = 1


def _path():
    return config.data_file(FILE)


def save(sheet_id: str, sheet_name: str, left: list, right: list,
         ments: dict | None = None, uids: dict | None = None, docs: dict | None = None) -> None:
    """방금 읽은 것을 그대로 둔다(행 번호 키는 글자로)."""
    o = {
        "v": VER, "sheet_id": sheet_id, "sheet_name": sheet_name,
        "saved": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "left": left or [], "right": right or [],
        "ments": {str(k): v for k, v in (ments or {}).items()},
        "uids": {str(k): v for k, v in (uids or {}).items()},
        "docs": {str(k): v for k, v in (docs or {}).items()},
    }
    try:
        config.atomic_write(_path(), json.dumps(o, ensure_ascii=False))
    except OSError:
        pass


def load(sheet_id: str, sheet_name: str) -> dict | None:
    """그 시트·탭의 저장본(없거나 다른 시트 것이면 None). 행 번호 키는 숫자로 되돌린다."""
    try:
        o = json.loads(_path().read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(o, dict) or o.get("v") != VER:
        return None
    if (o.get("sheet_id") or "") != (sheet_id or "") or (o.get("sheet_name") or "") != (sheet_name or ""):
        return None
    if not isinstance(o.get("left"), list) or not o["left"]:
        return None

    def ints(d):
        out = {}
        for k, v in (d or {}).items():
            try:
                out[int(k)] = v
            except (TypeError, ValueError):
                pass
        return out
    o["ments"], o["uids"], o["docs"] = ints(o.get("ments")), ints(o.get("uids")), ints(o.get("docs"))
    return o


def clear() -> None:
    try:
        _path().unlink()
    except OSError:
        pass
