"""고객관리 시트 자동 백업(v1.32) — 주 1회, 고객관리 탭의 사본을 내 구글 드라이브에 새 시트로.

지점장 선택(B2): "주 1회 시트 사본을 드라이브에 저장하고 최근 몇 개만 보관".
  · 드라이브의 '사본 만들기' 는 드라이브 전체 권한이 있어야 한다(우리는 그 권한을 받지 않는다). 그래서
    Sheets 로 새 스프레드시트를 만들고(spreadsheets.create) 고객관리 탭을 그리로 복사한다(sheets.copyTo) —
    서식·드롭다운·직접 적은 값·견적서 그림 주소가 그대로 간다.
    ⚠️ 다른 탭을 참조하는 수식 칸(합계·안내멘트 등)은 사본에서 값이 안 나올 수 있다. 직접 적은 칸이 목적이다.
  · 새 시트는 이 앱이 만든 파일이라 지울 수 있다 → 최근 KEEP 개만 두고 옛것은 휴지통으로(30일 안엔 되살림).
  · 이 계정이 **고칠 수 있는** 시트만 한다 — '보기' 로만 공유받은 남의 시트를 직원 드라이브에 복사하지 않는다.
"""

from __future__ import annotations

from datetime import date, datetime

from . import config, sheets

PREFIX = "[백업] "
KEEP = 4
EVERY_DAYS = 7


def _http():
    from . import net
    return net.http()


def last_day(backups: list):
    days = []
    for b in backups or []:
        try:
            days.append(datetime.strptime(str(b.get("at", ""))[:10], "%Y-%m-%d").date())
        except ValueError:
            pass
    return max(days) if days else None


def due(settings, today: date | None = None) -> bool:
    if not getattr(settings, "sheet_backup", True) or not (getattr(settings, "sheet_id", "") or "").strip():
        return False
    today = today or date.today()
    sid = settings.sheet_id.strip()
    mine = [b for b in (getattr(settings, "sheet_backups", None) or []) if b.get("src") == sid]
    last = last_day(mine)
    return last is None or (today - last).days >= EVERY_DAYS


def run(auth, sheet_id: str, tab: str, today: date | None = None) -> dict:
    """사본을 만든다 → {id, at, src, name}. 실패하면 GoogleError."""
    today = today or date.today()
    h = sheets._headers(auth)
    meta = _http().get(config.SHEETS_BASE_URL.format(sheet_id=sheet_id), headers=h, timeout=30,
                       params={"fields": "properties(title),sheets(properties(sheetId,title))"})
    sheets._check(meta)
    j = meta.json() or {}
    title = ((j.get("properties") or {}).get("title") or "고객관리").strip()
    src = next((x.get("properties", {}) for x in j.get("sheets", [])
                if x.get("properties", {}).get("title") == tab), None)
    if src is None:
        raise sheets.GoogleError(f"'{tab}' 탭을 찾지 못해 백업하지 못했습니다.")
    name = f"{PREFIX}{title} {today.isoformat()}"
    made = _http().post(config.SHEETS_BASE_URL.format(sheet_id="").rstrip("/"), headers=h, timeout=30,
                        json={"properties": {"title": name}})
    sheets._check(made)
    mj = made.json() or {}
    new_id = mj.get("spreadsheetId", "")
    first_gid = ((mj.get("sheets") or [{}])[0].get("properties") or {}).get("sheetId", 0)
    cp = _http().post(config.SHEETS_BASE_URL.format(sheet_id=sheet_id)
                      + f"/sheets/{int(src.get('sheetId', 0))}:copyTo", headers=h, timeout=60,
                      json={"destinationSpreadsheetId": new_id})
    sheets._check(cp)
    new_gid = (cp.json() or {}).get("sheetId", 0)
    fix = _http().post(config.SHEETS_BATCH_UPDATE_URL.format(sheet_id=new_id), headers=h, timeout=30, json={
        "requests": [
            {"deleteSheet": {"sheetId": first_gid}},
            {"updateSheetProperties": {"properties": {"sheetId": new_gid, "title": tab}, "fields": "title"}},
        ]})
    sheets._check(fix)
    return {"id": new_id, "at": today.isoformat(), "src": sheet_id, "name": name}


def prune(auth, backups: list, keep: int = KEEP) -> tuple:
    """시트마다 최근 keep 개만 남긴다 → (남길 목록, 휴지통으로 보낸 id 들)."""
    by_src: dict = {}
    for b in backups or []:
        by_src.setdefault(b.get("src", ""), []).append(b)
    kept, gone = [], []
    for _src, lst in by_src.items():
        lst = sorted(lst, key=lambda b: str(b.get("at", "")))
        gone += [b["id"] for b in lst[:-keep] if b.get("id")]
        kept += lst[-keep:]
    if gone:
        try:
            from . import kb_files
            kb_files.trash(auth, gone)
        except Exception:
            pass
    return sorted(kept, key=lambda b: str(b.get("at", ""))), gone
