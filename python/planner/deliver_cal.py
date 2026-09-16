"""출고일을 구글 캘린더에 자동으로 올린다.

고객의 출고일이 '미정' 이 아닌 날짜로 정해지면 그 날짜에 종일 일정을 만든다.
제목은 `followup.deliver_title` 이 만드는 "<고객> 출고" 모양이라,
**기존 팔로업 기계가 그대로 물려받아** [출고 1개월] 할일까지 저절로 만든다.

무엇을 할지 정하는 것(plan)과 실제로 통신하는 것을 갈라 놓았다.
plan() 은 통신을 하지 않는 순수 계산이라 시트도 구글도 없이 시험할 수 있다 —
'날짜가 바뀌면 옮기고, 미정으로 되돌리면 지운다' 같은 규칙이 어긋나기 쉬운 자리다.

내가 만든 일정을 도로 찾으려고 `deliver_events.json` 에 적어 둔다.
  {고객ID: {"cal_id":…, "event_id":…, "date":"2026-08-20", "title":…}}
고객ID(시트 U열)로 붙들어 둔다 — 순번도 이름도 바뀔 수 있다.
sync 대상이라 사무실 PC 와 집 PC 가 같은 기록을 본다.

⚠️ 여기 적히지 않은 일정(예전에 손으로 만든 것)은 **건드리지 않는다.**
"""

from __future__ import annotations

import json
from datetime import date

from . import config, followup, sheets

FILE = "deliver_events.json"


# ---------------------------------------------------------------------------
# 기록
# ---------------------------------------------------------------------------
def load() -> dict:
    try:
        p = config.data_file(FILE)
        if p.exists():
            o = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(o, dict):
                return {str(k): v for k, v in o.items() if isinstance(v, dict)}
    except Exception:
        pass
    return {}


def save(data: dict) -> None:
    try:
        config.atomic_write(config.data_file(FILE),
                            json.dumps(data or {}, ensure_ascii=False, indent=2))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 무엇을 할지 (통신 없음)
# ---------------------------------------------------------------------------
def plan(uid: str, customer: str, old_value: str, new_value: str,
         record: dict | None, keyword: str = "출고") -> tuple:
    """출고일이 바뀌었을 때 할 일.

    돌려주는 것 — 첫 칸이 무엇을 할지다.
      ("none",)                                      할 것 없음
      ("create", 제목, 날짜)                          새로 만든다
      ("move",   cal_id, event_id, 제목, 날짜)         있는 일정을 옮긴다
      ("rename", cal_id, event_id, 제목, 날짜)         날짜는 그대로, 제목만 고친다
      ("delete", cal_id, event_id)                    지운다

    ⚠️ 날짜가 바뀌었을 때 지웠다 새로 만들지 않고 **옮긴다.** 눈에 보이는 결과는
       같지만 일정 UID 가 그대로라 팔로업 할일이 두 번 생기지 않는다
       (followup.check_followups 는 UID 로 '이미 처리했다' 를 기억한다).
    """
    rec = record if isinstance(record, dict) else None
    cal_id = str((rec or {}).get("cal_id") or "")
    event_id = str((rec or {}).get("event_id") or "")
    have = bool(rec and cal_id and event_id)

    new_d = sheets.parse_date(new_value)
    old_d = sheets.parse_date(old_value)

    # 이름이 되읽히지 않으면(영문 상호 등) 만들지 않는다.
    # 다만 이미 만들어 둔 것이 있으면 치운다 — 뜻 모를 줄을 남기지 않는다.
    if not followup.deliver_ok(customer, keyword):
        return ("delete", cal_id, event_id) if have else ("none",)

    title = followup.deliver_title(customer, keyword)

    if new_d is None:
        # 미정으로 되돌렸다
        return ("delete", cal_id, event_id) if have else ("none",)

    if not have:
        # 기록이 없다 → 새로 만든다.
        # ⚠️ 출고일이 **바뀌었을 때만** 만든다. 안 그러면 다른 칸만 고쳐 저장해도
        #    기존 고객 전부에게 일정이 생긴다(그건 하지 않기로 한 것이다).
        return ("create", title, new_d) if old_d != new_d else ("none",)

    was = str((rec or {}).get("date") or "")
    same_day = (was == new_d.isoformat())
    same_title = (str((rec or {}).get("title") or "") == title)
    if same_day and same_title:
        return ("none",)
    if same_day:
        return ("rename", cal_id, event_id, title, new_d)
    return ("move", cal_id, event_id, title, new_d)


def remember(data: dict, uid: str, cal_id: str, event_id: str,
             when: date, title: str) -> dict:
    data = dict(data or {})
    data[str(uid)] = {"cal_id": cal_id, "event_id": event_id,
                      "date": when.isoformat(), "title": title}
    return data


def forget(data: dict, uid: str) -> dict:
    data = dict(data or {})
    data.pop(str(uid), None)
    return data
