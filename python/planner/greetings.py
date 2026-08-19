"""인삿말 문구 보관 — 채널(유입처)별 '상담후 / 부재중' 두 가지.

원래 쓰시던 HTML 도구의 문구를 그대로 옮겨 왔다. 문구는 사람마다·시기마다
바뀌므로 앱 안에서 고칠 수 있게 하고, 계정 폴더의 greetings.json 에 저장한다
(동기화 번들에 포함돼 다른 PC 에도 따라간다).
"""

from __future__ import annotations

import json

from . import config

FILE = "greetings.json"

_AFTER_TAIL = "\n\n좋은견적 준비해서 발송드리겠습니다 :)"
_MISS_TAIL = (
    "\n부재중이셔서 통화 가능하신 시간 회신 남겨주시면, 다시한번 연락드리겠습니다.\n\n"
    "혹시라도 통화 어려우시다면 , 카톡으로 문의 남겨주셔도 상담 가능합니다.^^"
)

_A1 = "안녕하세요 차량문의 주셔서 연락드린 에이원오토 이재영 부지점장입니다.😊"


def _direct(company: str) -> str:
    return (f"안녕하세요 {company}로 차량문의 주셔서 연락드린 "
            "다이렉트팀 이재영 부지점장 입니다.😊")


DEFAULTS = [
    {"name": "에이원오토", "after": _A1 + _AFTER_TAIL, "miss": _A1 + _MISS_TAIL},
    {"name": "우리금융", "after": _direct("우리금융캐피탈") + _AFTER_TAIL,
     "miss": _direct("우리금융캐피탈") + _MISS_TAIL},
    {"name": "하나캐피탈", "after": _direct("하나캐피탈") + _AFTER_TAIL,
     "miss": _direct("하나캐피탈") + _MISS_TAIL},
    {"name": "BNK캐피탈", "after": _direct("BNK캐피탈") + _AFTER_TAIL,
     "miss": _direct("BNK캐피탈") + _MISS_TAIL},
    {"name": "롯데렌터카", "after": _direct("롯데렌탈") + _AFTER_TAIL,
     "miss": _direct("롯데렌탈") + _MISS_TAIL},
    {"name": "KB캐피탈", "after": _direct("KB캐피탈") + _AFTER_TAIL,
     "miss": _direct("KB캐피탈") + _MISS_TAIL},
]


def defaults() -> list:
    """기본 문구 사본 (원본을 건드리지 않도록 매번 새로 만든다)."""
    return [dict(d) for d in DEFAULTS]


def load() -> list:
    """저장된 문구. 파일이 없거나 깨졌으면 기본 문구를 돌려준다."""
    p = config.data_file(FILE)
    try:
        if p.exists():
            raw = json.loads(p.read_text(encoding="utf-8"))
            out = []
            for o in raw if isinstance(raw, list) else []:
                name = str(o.get("name", "")).strip()
                if not name:
                    continue
                out.append({"name": name,
                            "after": str(o.get("after", "")),
                            "miss": str(o.get("miss", ""))})
            if out:
                return out
    except Exception:
        pass
    return defaults()


def save(items: list) -> None:
    data = [{"name": (it.get("name") or "").strip(),
             "after": it.get("after") or "",
             "miss": it.get("miss") or ""}
            for it in (items or []) if (it.get("name") or "").strip()]
    config.atomic_write(config.data_file(FILE),
                        json.dumps(data, ensure_ascii=False, indent=2))
