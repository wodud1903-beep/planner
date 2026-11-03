"""인삿말 문구 보관 — 채널(유입처)별 '상담후 / 부재중' 두 가지.

원래 쓰시던 HTML 도구의 문구를 그대로 옮겨 왔다. 문구는 사람마다·시기마다
바뀌므로 앱 안에서 고칠 수 있게 하고, 계정 폴더의 greetings.json 에 저장한다
(동기화 번들에 포함돼 다른 PC 에도 따라간다).
"""

from __future__ import annotations

import json

from . import config, tombs

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
                g = {"name": name,
                     "after": str(o.get("after", "")),
                     "miss": str(o.get("miss", ""))}
                if o.get("at"):
                    g["at"] = str(o["at"])     # 고친 시각 — 지운 표식과 견준다(tombs)
                out.append(g)
            if out:
                return out
    except Exception:
        pass
    return defaults()


def _saved() -> list:
    """지금 파일에 든 그대로(없으면 빈 목록 — 기본 문구는 '저장한 것' 이 아니다)."""
    try:
        raw = json.loads(config.data_file(FILE).read_text(encoding="utf-8"))
        return [o for o in raw if isinstance(o, dict)] if isinstance(raw, list) else []
    except Exception:
        return []


def save(items: list) -> None:
    data = [{"name": (it.get("name") or "").strip(),
             "after": it.get("after") or "",
             "miss": it.get("miss") or "",
             **({"at": it["at"]} if it.get("at") else {})}
            for it in (items or []) if (it.get("name") or "").strip()]
    # 지운(이름을 바꾼) 채널은 표식을 남기고, 새로 생기거나 고친 채널엔 시각을 붙인다 —
    # 다른 PC 에 남은 옛 채널이 동기화로 되살아나지 않게(v1.26)
    data = tombs.stamp(FILE, _saved(), data)
    config.atomic_write(config.data_file(FILE),
                        json.dumps(data, ensure_ascii=False, indent=2))
