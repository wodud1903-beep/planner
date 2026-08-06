"""데이터 모델 + JSON 저장/로드.

델파이 uPlanData.pas 의 자료구조와 JSON 형식을 그대로 따른다.
(todos.json / pcalarms.json / taskalarms.json 호환)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Optional

from . import config


# ---------------------------------------------------------------------------
# 파싱 헬퍼
# ---------------------------------------------------------------------------
def _parse_time(s: str, default: time = time(9, 0)) -> time:
    try:
        parts = s.strip().split(":")
        return time(int(parts[0]), int(parts[1]))
    except Exception:
        return default


def _parse_date(s: str, default: Optional[date] = None) -> Optional[date]:
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except Exception:
        return default


def _parse_dt(s: str) -> Optional[datetime]:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except Exception:
            continue
    return None


def _fmt_time(t: time) -> str:
    return t.strftime("%H:%M")


def _days_text(weekdays: str) -> str:
    out = "".join(config.DAY_NAMES[i] for i in range(1, 8) if str(i) in (weekdays or ""))
    return out or "(요일없음)"


# ---------------------------------------------------------------------------
# 로컬 할일
# ---------------------------------------------------------------------------
@dataclass
class TodoItem:
    done: bool = False
    title: str = ""
    has_time: bool = True
    run_time: time = field(default_factory=lambda: time(9, 0))
    alarm: bool = True
    ment: str = ""
    run_date: date = field(default_factory=date.today)
    repeats: bool = False
    weekdays: str = "23456"
    last_alarm: Optional[datetime] = None

    def days_text(self) -> str:
        if not self.repeats:
            return self.run_date.strftime("%m-%d(%a)")
        return _days_text(self.weekdays)

    def to_json(self) -> dict:
        return {
            "done": self.done,
            "title": self.title,
            "hasTime": self.has_time,
            "time": _fmt_time(self.run_time),
            "alarm": self.alarm,
            "ment": self.ment,
            "date": self.run_date.strftime("%Y-%m-%d"),
            "repeats": self.repeats,
            "weekdays": self.weekdays,
            "lastAlarm": self.last_alarm.strftime("%Y-%m-%d %H:%M:%S") if self.last_alarm else "",
        }

    @classmethod
    def from_json(cls, o: dict) -> "TodoItem":
        return cls(
            done=bool(o.get("done", False)),
            title=o.get("title", ""),
            has_time=bool(o.get("hasTime", True)),
            run_time=_parse_time(o.get("time", "09:00")),
            alarm=bool(o.get("alarm", True)),
            ment=o.get("ment", ""),
            run_date=_parse_date(o.get("date", ""), date.today()),
            repeats=bool(o.get("repeats", False)),
            weekdays=o.get("weekdays", "23456"),
            last_alarm=_parse_dt(o.get("lastAlarm", "")),
        )

    def due_alarm(self, now: datetime) -> bool:
        """지금 알람이 울려야 하는가 (분 단위, 하루 1회)."""
        if self.done or not self.alarm or not self.has_time:
            return False
        if (now.hour, now.minute) != (self.run_time.hour, self.run_time.minute):
            return False
        if self.last_alarm and self.last_alarm.replace(second=0, microsecond=0) == now.replace(second=0, microsecond=0):
            return False
        if self.repeats:
            dow = now.isoweekday() % 7 + 1  # 1=일 .. 7=토
            return str(dow) in self.weekdays
        return now.date() == self.run_date


# ---------------------------------------------------------------------------
# PC 알람 (요일 반복)
# ---------------------------------------------------------------------------
@dataclass
class PcAlarm:
    enabled: bool = True
    title: str = "새 알람"
    weekdays: str = "23456"
    run_time: time = field(default_factory=lambda: time(9, 0))
    ment: str = ""
    last_fire: Optional[datetime] = None

    def days_text(self) -> str:
        return _days_text(self.weekdays)

    def to_json(self) -> dict:
        return {
            "enabled": self.enabled,
            "title": self.title,
            "weekdays": self.weekdays,
            "time": _fmt_time(self.run_time),
            "ment": self.ment,
            "lastFire": self.last_fire.strftime("%Y-%m-%d %H:%M:%S") if self.last_fire else "",
        }

    @classmethod
    def from_json(cls, o: dict) -> "PcAlarm":
        return cls(
            enabled=bool(o.get("enabled", True)),
            title=o.get("title", "알람"),
            weekdays=o.get("weekdays", "23456"),
            run_time=_parse_time(o.get("time", "09:00")),
            ment=o.get("ment", ""),
            last_fire=_parse_dt(o.get("lastFire", "")),
        )

    def due_now(self, now: datetime) -> bool:
        if not self.enabled:
            return False
        if (now.hour, now.minute) != (self.run_time.hour, self.run_time.minute):
            return False
        if self.last_fire and self.last_fire.replace(second=0, microsecond=0) == now.replace(second=0, microsecond=0):
            return False
        dow = now.isoweekday() % 7 + 1
        return str(dow) in self.weekdays


# ---------------------------------------------------------------------------
# 구글 Tasks 항목에 붙이는 알람 (Tasks 가 원본, 알람만 로컬 보관)
# ---------------------------------------------------------------------------
@dataclass
class TaskAlarm:
    google_id: str = ""
    alarm: bool = False
    run_time: time = field(default_factory=lambda: time(9, 0))
    ment: str = ""
    last_alarm: Optional[datetime] = None

    def to_json(self) -> dict:
        return {
            "id": self.google_id,
            "alarm": self.alarm,
            "time": _fmt_time(self.run_time),
            "ment": self.ment,
            "lastAlarm": self.last_alarm.strftime("%Y-%m-%d %H:%M:%S") if self.last_alarm else "",
        }

    @classmethod
    def from_json(cls, o: dict) -> "TaskAlarm":
        return cls(
            google_id=o.get("id", ""),
            alarm=bool(o.get("alarm", False)),
            run_time=_parse_time(o.get("time", "09:00")),
            ment=o.get("ment", ""),
            last_alarm=_parse_dt(o.get("lastAlarm", "")),
        )

    def due_alarm(self, now: datetime, due: Optional[date], has_due: bool) -> bool:
        if not self.alarm or not has_due or due is None:
            return False
        if now.date() != due:
            return False
        if (now.hour, now.minute) != (self.run_time.hour, self.run_time.minute):
            return False
        if self.last_alarm and self.last_alarm.replace(second=0, microsecond=0) == now.replace(second=0, microsecond=0):
            return False
        return True


# ---------------------------------------------------------------------------
# 리스트 저장/로드 유틸
# ---------------------------------------------------------------------------
def load_list(path: Path, cls):
    if not path.exists():
        return []
    try:
        arr = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(arr, list):
        return []
    out = []
    for o in arr:
        if isinstance(o, dict):
            try:
                out.append(cls.from_json(o))
            except Exception:
                pass
    return out


def save_list(path: Path, items) -> None:
    data = [it.to_json() for it in items]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class TaskAlarmStore:
    """task id -> TaskAlarm 매핑을 관리."""

    def __init__(self, path: Path):
        self.path = path
        self.items: list[TaskAlarm] = load_list(path, TaskAlarm)

    def find(self, task_id: str) -> Optional[TaskAlarm]:
        if not task_id:
            return None
        for a in self.items:
            if a.google_id == task_id:
                return a
        return None

    def ensure(self, task_id: str) -> TaskAlarm:
        a = self.find(task_id)
        if a is None:
            a = TaskAlarm(google_id=task_id)
            self.items.append(a)
        return a

    def save(self) -> None:
        save_list(self.path, [a for a in self.items if a.google_id])
