"""계정에 붙는 시트·서류 폴더 설정 — 구글 계정으로 바로 주고받기(v1.30).

지점장 요청: "PC 앱 설정에서 구글시트 주소·서류폴더 주소를 지정하면 개개인의 동기화된 계정에
실시간으로 동기화해서 웹에도 바로 반영되게."

예전(v1.29)엔 웹이 일정관리기 동기화 묶음(planner_sync.json) 안의 plan_cfg.json 을 읽었다. 그런데
  · 묶음은 자료·메모까지 들어 있어 무겁고, 2.5초 모아서 올린다 — 웹이 자주 들여다보기에 맞지 않다.
  · PC 의 서류 폴더는 이 PC 의 경로(G:\\내 드라이브\\…)라 웹은 그 값을 쓸 수 없었다.
그래서 내 구글 드라이브 앱 전용 공간(appDataFolder)에 **작은 파일 하나**를 두고 PC 와 웹이 같이 쓴다.

  account_settings.json
  {"v": 1, "updatedAt": UTC,
   "sheet":  {"id": 시트 ID, "tab": 탭 이름, "at": 바꾼 때(UTC), "by": "pc" | "web"},
   "folder": {"ref": '내 드라이브' 기준 경로("고객정보", "영업/고객정보") 또는 폴더 링크, "at", "by"}}

  · 항목마다 **나중에 바꾼 쪽(at)** 이 이긴다 — 웹에서 나중에 바꾼 것을 PC 가 덮지 않는다.
  · 값이 같으면 쓰지 않는다(시각만 달라서 오가며 다시 쓰는 일이 없게).
  · 이 PC 의 옛 설정엔 바꾼 때가 없다 — 파일에 그 항목이 없을 때만 지금 시각으로 올린다.
  · 내 드라이브 밖(이 PC 에만 있는 폴더)이면 폴더는 올리지 않는다(웹이 볼 수 없다).
  · 못 읽으면 쓰지 않는다(남의 것을 덮지 않게). 깨진 파일은 이 두 칸뿐이라 새로 쓴다.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from . import config, drive_path, google_client

FILE = "account_settings.json"


class AccountSettingsError(Exception):
    pass


def utc_stamp(dt: datetime | None = None) -> str:
    return (dt or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def local_items(settings) -> dict:
    """이 PC 설정 → 계정에 올릴 항목 {sheet?, folder?}. 정하지 않은 것은 빠진다."""
    out = {}
    sid = str(getattr(settings, "sheet_id", "") or "").strip()
    if sid:
        out["sheet"] = {"id": sid,
                        "tab": str(getattr(settings, "sheet_name", "") or "").strip() or config.DEF_SHEET_NAME,
                        "at": str(getattr(settings, "sheet_at", "") or ""), "by": "pc"}
    fallback = str(getattr(settings, "files_drive_folder", "") or "").strip() or drive_path.CUSTOMER_DIR
    ref = drive_path.web_ref(str(getattr(settings, "files_dir", "") or ""), fallback)
    if ref:
        out["folder"] = {"ref": ref, "at": str(getattr(settings, "folder_at", "") or ""), "by": "pc"}
    return out


def _same(kind: str, a: dict, b: dict) -> bool:
    if kind == "sheet":
        return (str(a.get("id") or "") == str(b.get("id") or "")
                and str(a.get("tab") or "") == str(b.get("tab") or ""))
    return str(a.get("ref") or "") == str(b.get("ref") or "")


def stamp_changes(settings, before: dict, after: dict, now: str | None = None) -> bool:
    """설정 창에서 시트·서류 폴더가 바뀌었으면 바꾼 때를 적는다. 바뀐 것이 있으면 True."""
    now = now or utc_stamp()
    changed = False
    for kind, attr in (("sheet", "sheet_at"), ("folder", "folder_at")):
        a, b = before.get(kind), after.get(kind)
        if (a is None) != (b is None) or (a is not None and not _same(kind, a, b)):
            setattr(settings, attr, now)
            changed = True
    return changed


def merge(remote, local: dict, now: str) -> tuple:
    """계정 파일(remote) + 이 PC 값(local) → (올릴 파일, 올려야 하나). 계산만 한다."""
    out = dict(remote) if isinstance(remote, dict) else {}
    push = False
    for kind, L in local.items():
        R = out.get(kind) if isinstance(out.get(kind), dict) else None
        if R is not None and _same(kind, R, L):
            continue                                  # 같은 값 — 시각만 다르면 그대로 둔다
        if R is None:
            put = dict(L, at=L.get("at") or now)      # 계정에 아직 없다 — 이 PC 값을 올린다
        elif L.get("at") and L["at"] > str(R.get("at") or ""):
            put = dict(L)                             # 이 PC 에서 나중에 바꿨다
        else:
            continue                                  # 웹·다른 PC 에서 나중에 바꿨다 — 덮지 않는다
        out[kind] = put
        push = True
    if push:
        out["v"] = 1
        out["updatedAt"] = now
    return out, push


def push(auth, settings) -> bool:
    """이 PC 의 시트·서류 폴더를 계정에 맞춘다. 올렸으면 True. 못 읽으면 AccountSettingsError(쓰지 않는다)."""
    local = local_items(settings)
    if not local:
        return False
    try:
        fid = google_client.drive_find(auth, FILE)
        text = google_client.drive_read(auth, fid) if fid else ""
    except Exception as e:
        raise AccountSettingsError(f"계정 설정을 읽지 못했습니다: {e}")
    try:
        o = json.loads(text) if (text or "").strip() else {}
    except Exception:
        o = {}
    out, need = merge(o if isinstance(o, dict) else {}, local, utc_stamp())
    if need:
        try:
            google_client.drive_write(auth, FILE, json.dumps(out, ensure_ascii=False, indent=1))
        except Exception as e:
            raise AccountSettingsError(f"계정 설정을 올리지 못했습니다: {e}")
    return need


def push_saved(auth) -> bool:
    """저장된 설정 파일(plan_cfg.json)로 맞춘다 — 동기화 때 부른다(다른 PC 에서 바꾼 것도 실린다)."""
    from .models import AppSettings
    return push(auth, AppSettings.load(config.data_dir() / "plan_cfg.json"))
