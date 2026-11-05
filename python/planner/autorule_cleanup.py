"""자동 규칙을 없앤 뒤(v1.28) — 자동 규칙이 만든 할일 중 **아직 안 한 것**을 거둔다.

지점장: "자동규칙을 삭제해줘" → 물어보니 '아직 안 한 것도 지우기' 를 골랐다.

  · 자동 규칙(v1.26·1.27)이 만든 할일은 auto_done.json 에 제목이 남아 있다
    ({규칙|고객: {title, date, base, at}}). 그 제목과 같고 **아직 체크하지 않은** 할일만 지운다.
    이미 끝낸 것(체크한 것)과 직접 만든 할일은 그대로 둔다.
  · 지운 할일은 auto_rules_removed.json(이 PC 의 계정 폴더, 동기화 안 함)에 그대로 남겨 둔다 —
    혹시 필요하면 되살릴 수 있게.
  · auto_done.json 은 지우지 않는다. 아직 업데이트하지 않은 옛 판 PC 가 그 기록을 보고 같은 할일을
    다시 만들지 않는다. 옛 판이 그사이 새로 만든 것도 기록이 동기화되면 여기서 거둔다
    (main_window 가 받을 때마다 다시 본다).
  · 다른 PC 기록을 받은 뒤에만 부른다(main_window._pulled_once) — 받기 전에 할일을 고치면
    이 PC 의 옛 목록이 다른 PC 에서 고친 할일을 덮어쓴다(todos.json 은 나중에 고친 파일이 이긴다).

통신 없는 순수 계산(pick)과 파일 일(load_done · keep_removed)을 갈라 두었다.
"""

from __future__ import annotations

import json
from datetime import datetime

from . import config

DONE_FILE = "auto_done.json"              # 자동 규칙이 남긴 기록(동기화 — 지우지 않는다)
REMOVED_FILE = "auto_rules_removed.json"  # 거둔 할일 보관(이 PC 만)
KEEP_MAX = 500


def made_titles(done: dict) -> set:
    """자동 규칙이 실제로 할일을 만든 기록의 제목들."""
    out = set()
    for rec in (done or {}).values():
        if isinstance(rec, dict):
            t = str(rec.get("title") or "").strip()
            if t:
                out.add(t)
    return out


def pick(todos, done: dict) -> list:
    """지울 할일 — 자동 규칙이 만든 제목이고 아직 체크하지 않은 것."""
    titles = made_titles(done)
    if not titles:
        return []
    return [t for t in (todos or []) if not getattr(t, "done", False)
            and str(getattr(t, "title", "") or "").strip() in titles]


def load_done() -> dict:
    try:
        o = json.loads(config.data_file(DONE_FILE).read_text(encoding="utf-8"))
        return o if isinstance(o, dict) else {}
    except Exception:
        return {}


def load_removed() -> list:
    try:
        o = json.loads(config.data_file(REMOVED_FILE).read_text(encoding="utf-8"))
        return o if isinstance(o, list) else []
    except Exception:
        return []


def keep_removed(items) -> None:
    """거둔 할일을 보관 파일 끝에 붙인다(되살릴 수 있게 — 할일 모양 그대로 + 거둔 시각)."""
    when = datetime.now().strftime("%Y-%m-%d %H:%M")
    got = load_removed()
    for t in items or []:
        try:
            d = t.to_json()
        except Exception:
            d = {"title": str(getattr(t, "title", ""))}
        d["removedAt"] = when
        got.append(d)
    try:
        config.atomic_write(config.data_file(REMOVED_FILE),
                            json.dumps(got[-KEEP_MAX:], ensure_ascii=False, indent=1))
    except OSError:
        pass
