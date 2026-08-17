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
    config.atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2))


@dataclass
class AppSettings:
    """전역 설정 (설정창에서 편집, plan_cfg.json 에 저장). 델파이 TAppSettings 호환."""
    auto_fetch: bool = False
    # 계약 후 팔로업
    follow_on: bool = True
    follow_keyword: str = "출고"
    follow_months: int = 1
    follow_alarm: bool = True
    follow_time: time = field(default_factory=lambda: time(10, 0))
    follow_ment: str = config.DEF_FOLLOW_MENT
    # 팔로업을 구글 캘린더에도 등록
    follow_to_calendar: bool = False
    # 전역 단축키
    hot_on: bool = True
    hot_ctrl: bool = True
    hot_alt: bool = True
    hot_shift: bool = False
    hot_key: str = "A"
    # 화면 테마
    dark_mode: bool = False
    # 창 닫기(X) 동작: True=트레이로 내려감, False=완전 종료
    close_to_tray: bool = True
    # 구글 캘린더 알림(리마인더) — PC 를 꺼도 휴대폰으로 알림이 온다
    cal_reminder_on: bool = True
    cal_reminder_min: int = 30
    # 만기 재계약 알림: 만기 몇 개월 전부터 브리핑에 띄울지 (0 = 끔)
    expiry_months: int = 3
    # 구글 시트 고객관리 연동
    sheet_on: bool = False
    sheet_id: str = config.DEF_SHEET_ID
    sheet_name: str = config.DEF_SHEET_NAME

    def to_json(self) -> dict:
        return {
            "autoFetch": self.auto_fetch,
            "followOn": self.follow_on,
            "followKeyword": self.follow_keyword,
            "followMonths": self.follow_months,
            "followAlarm": self.follow_alarm,
            "followTime": _fmt_time(self.follow_time),
            "followMent": self.follow_ment,
            "followToCalendar": self.follow_to_calendar,
            "hotOn": self.hot_on,
            "hotCtrl": self.hot_ctrl,
            "hotAlt": self.hot_alt,
            "hotShift": self.hot_shift,
            "hotKey": self.hot_key,
            "darkMode": self.dark_mode,
            "closeToTray": self.close_to_tray,
            "calReminderOn": self.cal_reminder_on,
            "calReminderMin": self.cal_reminder_min,
            "expiryMonths": self.expiry_months,
            "sheetOn": self.sheet_on,
            "sheetId": self.sheet_id,
            "sheetName": self.sheet_name,
        }

    @classmethod
    def load(cls, path: Path) -> "AppSettings":
        s = cls()
        if not path.exists():
            return s
        try:
            o = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return s
        if not isinstance(o, dict):
            return s
        s.auto_fetch = bool(o.get("autoFetch", False))
        s.follow_on = bool(o.get("followOn", True))
        s.follow_keyword = o.get("followKeyword", "출고")
        s.follow_months = int(o.get("followMonths", 1) or 1)
        s.follow_alarm = bool(o.get("followAlarm", True))
        s.follow_time = _parse_time(o.get("followTime", "10:00"), time(10, 0))
        s.follow_ment = o.get("followMent", config.DEF_FOLLOW_MENT)
        s.follow_to_calendar = bool(o.get("followToCalendar", False))
        s.hot_on = bool(o.get("hotOn", True))
        s.hot_ctrl = bool(o.get("hotCtrl", True))
        s.hot_alt = bool(o.get("hotAlt", True))
        s.hot_shift = bool(o.get("hotShift", False))
        s.hot_key = o.get("hotKey", "A")
        s.dark_mode = bool(o.get("darkMode", False))
        s.close_to_tray = bool(o.get("closeToTray", True))
        s.cal_reminder_on = bool(o.get("calReminderOn", True))
        try:
            s.cal_reminder_min = int(o.get("calReminderMin", 30))
        except Exception:
            s.cal_reminder_min = 30
        # 구버전 설정 파일에는 이 키가 없다 → 기본 3개월.
        # 이 파일은 Drive 로 다른 PC 에도 전파되므로 없는 키에 절대 터지면 안 된다.
        try:
            s.expiry_months = max(0, min(24, int(o.get("expiryMonths", 3))))
        except Exception:
            s.expiry_months = 3
        s.sheet_on = bool(o.get("sheetOn", False))
        s.sheet_id = o.get("sheetId", config.DEF_SHEET_ID) or config.DEF_SHEET_ID
        s.sheet_name = o.get("sheetName", config.DEF_SHEET_NAME) or config.DEF_SHEET_NAME
        return s

    def save(self, path: Path) -> None:
        try:
            config.atomic_write(
                path, json.dumps(self.to_json(), ensure_ascii=False, indent=2))
        except Exception:
            pass


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
