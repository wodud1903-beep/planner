"""설정 — 화면 테마와 빠른검색 단축키(그리고 창 위치처럼 저절로 기억하는 것).

PC 시작 시 자동 실행은 여기 두지 않는다. 윈도 레지스트리가 그 자체로 기록이다(startup.py).
이름은 일정관리기 AppSettings 의 kb_hot_* 와 같게 두어 hotkey.apply_kb 를 그대로 쓴다.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields

from . import config

FILE = "settings.json"


@dataclass
class Settings:
    theme: str = "light"
    kb_hot_on: bool = True
    kb_hot_ctrl: bool = True
    kb_hot_alt: bool = True
    kb_hot_shift: bool = False
    kb_hot_key: str = "F"
    tray_hint_shown: bool = False    # '트레이로 내려갔습니다' 안내를 한 번 보였다
    geometry: str = ""               # 창 위치·크기(Qt saveGeometry, base64)

    @classmethod
    def load(cls) -> "Settings":
        s = cls()
        try:
            p = config.data_file(FILE)
            if p.exists():
                o = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(o, dict):
                    for f in fields(cls):
                        if f.name in o and isinstance(o[f.name], type(getattr(s, f.name))):
                            setattr(s, f.name, o[f.name])
        except Exception:
            pass
        s.kb_hot_key = (s.kb_hot_key or "F").strip().upper() or "F"
        return s

    def save(self) -> None:
        config.atomic_write(config.data_file(FILE),
                            json.dumps(asdict(self), ensure_ascii=False, indent=2))

    def hotkey_text(self) -> str:
        """'Ctrl+Alt+F' 처럼 사람이 읽는 꼴."""
        mods = [n for n, on in (("Ctrl", self.kb_hot_ctrl), ("Alt", self.kb_hot_alt),
                                ("Shift", self.kb_hot_shift)) if on]
        return "+".join(mods + [self.kb_hot_key])
