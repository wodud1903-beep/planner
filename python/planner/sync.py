"""다중 PC 동기화 — Drive appDataFolder 에 계정별 데이터 번들 저장.

전략: 할일/알람/설정/팔로업 5개 파일을 하나의 JSON 번들로 묶어
appDataFolder(사용자 눈에 안 보이는 앱 전용 공간)에 저장.
`updatedAt`(UTC) 를 비교해 더 최신인 쪽을 채택(마지막 저장 우선).

같은 사람이 여러 PC에서 번갈아 쓰는 용도에 적합하다.
(두 PC에서 동시에 오프라인 편집하면 나중에 올린 쪽이 이긴다 — 안내 필요)
"""

from __future__ import annotations

import datetime
import json

from . import config, google_client

SYNC_FILE = "planner_sync.json"
_FILES = ["todos.json", "pcalarms.json", "taskalarms.json", "plan_cfg.json",
          "followups.json", "ment_copied.json"]


def _now() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _meta_path():
    return config.data_dir() / "sync_meta.json"


def _local_updated() -> str:
    p = _meta_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8")).get("updatedAt", "")
        except Exception:
            return ""
    return ""


def _set_local_updated(ts: str) -> None:
    try:
        _meta_path().write_text(json.dumps({"updatedAt": ts}), encoding="utf-8")
    except Exception:
        pass


def migrate_legacy() -> None:
    """계정 폴더가 비어 있고 예전 공용 폴더에 데이터가 있으면 1회 복사."""
    acc = config.data_dir()
    if (acc / "todos.json").exists():
        return
    legacy = config.base_dir()
    if legacy.resolve() == acc.resolve():
        return
    copied = False
    for n in _FILES:
        src = legacy / n
        if src.exists():
            try:
                (acc / n).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
                copied = True
            except Exception:
                pass
    if copied:
        _set_local_updated(_now())  # 마이그레이션분을 최신으로 표시 → 이후 push 됨


def build_bundle() -> dict:
    files = {}
    for n in _FILES:
        p = config.data_dir() / n
        files[n] = p.read_text(encoding="utf-8") if p.exists() else ""
    return {"updatedAt": _now(), "files": files}


def pull(auth) -> bool:
    """원격 번들이 더 최신이면 로컬에 반영. 변경되면 True."""
    fid = google_client.drive_find(auth, SYNC_FILE)
    if not fid:
        return False
    txt = google_client.drive_read(auth, fid)
    try:
        b = json.loads(txt)
    except Exception:
        return False
    rup = b.get("updatedAt", "")
    if rup and rup > _local_updated():
        for n, content in (b.get("files") or {}).items():
            if n in _FILES:
                try:
                    (config.data_dir() / n).write_text(content or "", encoding="utf-8")
                except Exception:
                    pass
        _set_local_updated(rup)
        return True
    return False


def push(auth) -> None:
    """로컬 번들을 원격에 올리고 로컬 타임스탬프 갱신."""
    b = build_bundle()
    google_client.drive_write(auth, SYNC_FILE, json.dumps(b, ensure_ascii=False))
    _set_local_updated(b["updatedAt"])
