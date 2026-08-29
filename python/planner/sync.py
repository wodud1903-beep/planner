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
          "followups.json", "ment_copied.json", "customer_notes.json",
          "terms_presets.json", "commission_rates.json", "greetings.json",
          "kb_shared.json", "kb_mine.json", "customer_docs.json"]


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
        config.atomic_write(_meta_path(), json.dumps({"updatedAt": ts}))
    except Exception:
        pass


def touch_local() -> None:
    """로컬 데이터가 바뀐 시각을 기록한다 — **오프라인에서도** 부른다.

    예전엔 push/pull 때만 시각이 올라갔는데 push 는 온라인일 때만 예약된다.
    그래서 오프라인에서 한 작업은 시각이 그대로였고, 다음 실행의 pull 이 원격을
    더 최신으로 보고 통째로 덮어써서 그날 작업이 전부 사라졌다.
    """
    _set_local_updated(_now())


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
    """올릴 번들. **없는 파일은 키 자체를 넣지 않는다.**

    예전엔 없는 파일을 "" 로 채워 올렸다. 받는 쪽은 그 "" 를 파일에 그대로 써서
    멀쩡한 데이터를 0바이트로 만들었고, 읽기가 예외를 삼켜 조용히 사라졌다.
    """
    files = {}
    for n in _FILES:
        p = config.data_dir() / n
        if not p.exists():
            continue
        try:
            txt = p.read_text(encoding="utf-8")
        except Exception:
            continue
        if txt.strip():
            files[n] = txt
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
            if n not in _FILES:
                continue
            if not (content or "").strip():
                continue      # 빈 내용으로 멀쩡한 로컬 파일을 지우지 않는다
            try:
                config.atomic_write(config.data_dir() / n, content)
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
