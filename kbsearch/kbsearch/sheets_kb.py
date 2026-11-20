"""회사 공통 업무자료 — 스프레드시트 '업무자료' 탭 읽기·쓰기.

일정관리기 sheets.py 의 업무자료 부분(read_kb / write_kb)을 그대로 옮겨 왔다.
**같은 스프레드시트·같은 탭·같은 열 모양**이라 두 프로그램이 같은 자료를 본다.

  A 카테고리  B 금융사  C 제목  D 태그  E 본문  F 체크리스트(줄바꿈)
  G 첨부(앱 전용) — {"title": 제목, "files": [{id, name, mime, size}]} JSON

일정관리기와 다른 점
  · 읽기 실패를 조용히 삼키지 않는다. [동기화] 를 누른 사람에게 '시트에 접근할 수 없다'
    를 알려야 한다. 탭이 아직 없는 것만 None 으로 돌려준다.
  · **로그인 없이 읽는 길**(read_kb_public)이 있다. 시트가 '링크가 있는 모든 사용자 —
    뷰어' 로 열려 있어서, 공개 CSV 로 받으면 로그인 없이 같은 내용이 온다. 회사 공통 자료를
    켜 둔 동안 저절로 맞추는 데 쓴다(sync.pull_shared_public).
"""

from __future__ import annotations

import csv
import io
import json
import urllib.parse

from . import config, kb
from .google_auth import GoogleAuth, GoogleError
from .kb_files import LOCAL_PREFIX
from .net import http as _http

KB_HEADER = ["카테고리", "금융사", "제목", "태그", "본문", "체크리스트(줄바꿈)",
             "첨부(앱 전용 · 지우지 마세요)"]
KB_COLS = "A1:F"
# G 첨부 — A:F 와 **따로** 읽는다. 탭이 F 열까지만 있으면 G 범위는 격자 밖이라 400 이 나고,
# 같이 묶어 읽으면 자료 목록까지 통째로 실패한다(일정관리기에서 겪은 그 사고).
KB_FILES_COL = "G"


def _headers(auth: GoogleAuth) -> dict:
    return {"Authorization": "Bearer " + auth.valid_token()}


def _error_detail(r) -> tuple[str, str]:
    """구글 오류 응답에서 (사람이 읽는 메시지, reason 코드) 를 뽑는다."""
    msg, reason = "", ""
    try:
        j = r.json() or {}
        err = j.get("error", {})
        if isinstance(err, dict):
            msg = err.get("message", "") or ""
            reason = err.get("status", "") or ""
            for d in err.get("details", []) or []:
                if isinstance(d, dict) and d.get("reason"):
                    reason = d["reason"]
                    break
        elif isinstance(err, str):
            msg = err
            reason = j.get("error_description", "") or ""
    except Exception:
        pass
    if not msg:
        try:
            msg = (r.text or "")[:300]
        except Exception:
            msg = ""
    return msg, reason


def check(r) -> None:
    if r.status_code in (200, 201):
        return
    txt = ""
    try:
        txt = r.text or ""
    except Exception:
        pass
    msg, reason = _error_detail(r)
    low = (msg + " " + reason + " " + txt).lower()
    if "service_disabled" in low or "has not been used in project" in low:
        raise GoogleError(
            "구글 클라우드 프로젝트에서 'Google Sheets API' 가 켜져 있지 않습니다.\n"
            "관리자에게 아래 주소에서 [사용] 을 눌러 달라고 해 주세요.\n\n"
            f"{config.SHEETS_ENABLE_URL}")
    if ("access_token_scope_insufficient" in low
            or "request had insufficient authentication scopes" in low):
        raise GoogleError(
            "로그인할 때 스프레드시트 권한이 빠졌습니다.\n"
            "[로그아웃] 후 다시 [동기화] 를 눌러, 동의 화면의 항목을 모두 체크해 주세요.")
    if r.status_code == 401:
        raise GoogleError("구글 로그인이 만료되었습니다. [로그아웃] 후 다시 [동기화] 하세요.")
    if r.status_code == 403:
        raise GoogleError(
            "업무자료 시트에 접근할 수 없습니다 (403).\n"
            "로그인한 계정이 시트에 초대되어 있는지 관리자에게 확인해 주세요.\n"
            f"구글 응답: {msg[:300]}")
    if r.status_code == 404:
        raise GoogleError("업무자료 시트를 찾을 수 없습니다 (404).")
    raise GoogleError(f"시트 요청 실패 (HTTP {r.status_code})\n{msg[:300]}")


def _rng(tab: str, a1: str) -> str:
    """시트명에 공백·한글이 있어도 안전하게 A1 표기를 만든다."""
    return urllib.parse.quote(f"'{tab}'!{a1}", safe="")


def _missing_tab(r) -> bool:
    """탭이 아직 없어서 범위를 못 읽은 것인가(400 Unable to parse range)."""
    if r.status_code != 400:
        return False
    msg, _reason = _error_detail(r)
    return "parse range" in (msg or "").lower()


def find_or_create_folder(auth: GoogleAuth, name: str) -> str:
    """드라이브에 전용 폴더를 찾거나 만든다(앱이 만든 파일만 접근하는 권한)."""
    q = (f"name='{name}' and mimeType='application/vnd.google-apps.folder'"
         " and trashed=false")
    r = _http().get(config.DRIVE_FILES_URL, headers=_headers(auth), timeout=20,
                    params={"q": q, "fields": "files(id,name)", "pageSize": 1})
    if r.status_code == 200:
        files = (r.json() or {}).get("files", [])
        if files:
            return files[0].get("id", "")
    r = _http().post(config.DRIVE_FILES_URL, headers=_headers(auth), timeout=20,
                     json={"name": name,
                           "mimeType": "application/vnd.google-apps.folder"})
    check(r)
    return (r.json() or {}).get("id", "")


def _files_cell(title: str, files: list) -> str:
    files = kb.clean_files(files)
    if not files:
        return ""
    return json.dumps({"title": title, "files": files}, ensure_ascii=False)


def _files_from(cell: str, title: str) -> list:
    """G 칸 → 첨부 목록. 제목이 다르거나 못 읽으면 []."""
    try:
        o = json.loads(cell) if (cell or "").strip() else None
    except Exception:
        return []
    if not isinstance(o, dict) or str(o.get("title", "")).strip() != title:
        return []
    return kb.clean_files(o.get("files"))


def read_kb(auth: GoogleAuth, sheet_id: str = config.KB_SHEET_ID,
            tab: str = config.KB_TAB):
    """공통 업무자료를 읽는다. 탭이 없거나 비었으면 None, 못 읽으면 GoogleError."""
    url = config.SHEETS_VALUES_URL.format(sheet_id=sheet_id, rng=_rng(tab, KB_COLS))
    r = _http().get(url, headers=_headers(auth), timeout=20)
    if _missing_tab(r):
        return None
    check(r)
    rows = (r.json() or {}).get("values", [])
    gcol: list = []
    try:
        rg = _http().get(config.SHEETS_VALUES_URL.format(
            sheet_id=sheet_id, rng=_rng(tab, f"{KB_FILES_COL}1:{KB_FILES_COL}")),
            headers=_headers(auth), timeout=20)
        if rg.status_code == 200:
            gcol = [str((x[0] if x else "") or "")
                    for x in (rg.json() or {}).get("values", [])]
    except Exception:
        gcol = []
    return items_from_rows(rows, gcol)


def items_from_rows(rows: list, gcol: list) -> list | None:
    """A:F 행들 + G 열 → 자료 목록. 빈 줄·머리글은 건너뛴다. 하나도 없으면 None."""
    out = []
    for i, row in enumerate(rows):
        vals = [str(x).strip() for x in row] + [""] * 6
        category, finance, title, tags, body, checks = vals[:6]
        if not title or title == "제목":       # 빈 줄·머리글
            continue
        it = {
            "category": category,
            "finance": finance,
            "title": title,
            "tags": tags,
            "body": body,
            "checklist": [c.strip() for c in checks.splitlines() if c.strip()],
        }
        files = _files_from(gcol[i] if i < len(gcol) else "", title)
        if files:
            it["files"] = files
        out.append(it)
    return out or None


# ---------------------------------------------------------------------------
# 로그인 없이 — 공개 CSV
# ---------------------------------------------------------------------------
PUBLIC_CSV_URL = ("https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq"
                  "?tqx=out:csv&headers=1&sheet={tab}")


class NotPublic(Exception):
    """공개로 못 읽었다(시트가 잠겼거나 인터넷이 안 됨). 화면에 크게 알릴 일은 아니다."""


def read_kb_public(sheet_id: str = config.KB_SHEET_ID, tab: str = config.KB_TAB):
    """공통 업무자료를 **로그인 없이** 읽는다. 비었으면 None, 못 읽으면 NotPublic.

    ⚠️ 이 주소는 탭 이름이 틀리면 오류 대신 **첫 탭(수당율)을 준다.** 그대로 쓰면
       수당율 표가 업무자료를 덮어쓴다. 그래서 머리글이 업무자료의 것과 같을 때만 받는다.
    ⚠️ 시트가 잠겨 있으면 구글이 로그인 화면(HTML)을 200 으로 준다 — 종류(CSV)를 본다.
    """
    url = PUBLIC_CSV_URL.format(sheet_id=sheet_id, tab=urllib.parse.quote(tab, safe=""))
    try:
        r = _http().get(url, timeout=20)
    except Exception as e:
        raise NotPublic(f"인터넷 연결: {e}")
    ctype = (r.headers.get("Content-Type") or "").lower()
    if r.status_code != 200 or "csv" not in ctype:
        raise NotPublic(f"공개로 읽지 못했습니다 (HTTP {r.status_code}, {ctype or '종류 없음'})")
    try:
        text = r.content.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text)))
    except Exception as e:
        raise NotPublic(f"내용을 읽지 못했습니다: {e}")
    if not rows:
        return None
    head = [str(x).strip() for x in rows[0]]
    if head[:3] != KB_HEADER[:3]:
        raise NotPublic("업무자료 탭이 아닌 것이 왔습니다(탭 이름이 바뀌었을 수 있습니다).")
    body = rows[1:]
    return items_from_rows([r[:6] for r in body], [(r[6] if len(r) > 6 else "") for r in body])


def write_kb(auth: GoogleAuth, items: list, sheet_id: str = config.KB_SHEET_ID,
             tab: str = config.KB_TAB) -> None:
    """공통 업무자료를 덮어쓴다. 탭이 없으면 만든다."""
    for it in items or []:
        for f in it.get("files") or []:
            if str(f.get("id", "")).startswith(LOCAL_PREFIX):
                # 다른 직원이 받을 수 없는 첨부를 시트에 싣지 않는다(sync 가 먼저 올린다)
                raise GoogleError(f"'{f.get('name', '')}' 첨부가 아직 올라가지 않았습니다.")
    meta = _http().get(config.SHEETS_BASE_URL.format(sheet_id=sheet_id),
                       headers=_headers(auth), timeout=30,
                       params={"fields": "sheets(properties(sheetId,title,"
                                         "gridProperties(columnCount)))"})
    check(meta)
    props = {(sh.get("properties", {}) or {}).get("title"): (sh.get("properties", {}) or {})
             for sh in (meta.json() or {}).get("sheets", [])}
    if tab not in props:
        r = _http().post(config.SHEETS_BATCH_UPDATE_URL.format(sheet_id=sheet_id),
                         headers=_headers(auth), timeout=30,
                         json={"requests": [{"addSheet": {"properties": {"title": tab}}}]})
        check(r)
    else:
        p = props[tab]
        ncol = int(((p.get("gridProperties") or {}).get("columnCount")) or 26)
        if ncol < 7:
            r = _http().post(config.SHEETS_BATCH_UPDATE_URL.format(sheet_id=sheet_id),
                             headers=_headers(auth), timeout=30,
                             json={"requests": [{"appendDimension": {
                                 "sheetId": p.get("sheetId", 0), "dimension": "COLUMNS",
                                 "length": 7 - ncol}}]})
            check(r)

    # 지운 자료까지 반영되도록 비우고 새로 쓴다
    rc = _http().post(
        config.SHEETS_BASE_URL.format(sheet_id=sheet_id)
        + "/values/" + _rng(tab, "A1:G10000") + ":clear",
        headers=_headers(auth), timeout=30, json={})
    check(rc)

    values = [list(KB_HEADER)]
    for it in (items or []):
        title = (it.get("title") or "").strip()
        if not title:
            continue
        values.append([
            it.get("category", ""), it.get("finance", ""), it.get("title", ""),
            it.get("tags", ""), it.get("body", ""),
            "\n".join(it.get("checklist") or []),
            _files_cell(title, it.get("files") or []),
        ])
    url = config.SHEETS_VALUES_URL.format(
        sheet_id=sheet_id, rng=_rng(tab, f"A1:G{len(values)}"))
    r = _http().put(url, headers=_headers(auth), timeout=30,
                    params={"valueInputOption": "RAW"},
                    json={"values": values})
    check(r)
