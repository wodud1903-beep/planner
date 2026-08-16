"""구글 스프레드시트 고객관리 리스트 연동 (읽기 + 쓰기).

대상: '고객관리리스트' 파일의 '미출고차량' 시트.

설계 원칙 — **함수 칸은 절대 건드리지 않는다.**
  시트에는 사용자가 손으로 적는 칸과 수식으로 자동 계산되는 칸이 섞여 있다.
  한 줄을 통째로 쓰면 수식이 값으로 덮여 망가지므로,
  이 모듈은 '직접기재' 열만 **칸 단위 range** 로 기록한다.

열 구성 (헤더 행은 실행 시 자동 탐지 — 위쪽 요약행 개수가 바뀌어도 안전):
  A 순번            (자동/수식)
  B 고객명/사업자    C 금융사      D 차종        E 차량가격
  F 금융수수료       G 대리점 수당
  H 합계            (자동/수식 — 시트에 '합계 수정금지' 명시)
  I 특판/대리점      J 계약일(발주) K 출고일      L 진행현황
  M 계약조건         N 내용        O 출고유형
  P 고객센터 번호    (자동/수식)
  Q 사고접수연락처   (자동/수식)
  R 고객안내멘트     (자동/수식)
  S 견적서/계약서    T 등록완료
"""

from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import dataclass, field

import requests

from . import config
from .google_client import GoogleAuth, GoogleError

# 열 인덱스(0=A) → (필드키, 화면표시 이름)
FIELDS: list[tuple[int, str, str]] = [
    (1, "customer", "고객명 / 사업자 / (실차주)"),
    (2, "finance", "금융사"),
    (3, "model", "차종"),
    (4, "price", "차량가격"),
    (5, "fee", "금융수수료"),
    (6, "incentive", "대리점 수당"),
    (8, "channel", "특판 / 대리점"),
    (9, "contract_date", "계약일(발주)"),
    (10, "deliver_date", "출고일"),
    (11, "status", "진행현황"),
    (12, "terms", "계약조건"),
    (13, "note", "내용"),
    (14, "kind", "출고유형"),
    (18, "doc", "견적서/계약서"),        # 셀 안 이미지(=IMAGE 수식)로 넣는다
]

# 수식(자동 계산) 열 — 절대 쓰지 않는다
# A 순번, H 합계, P 고객센터, Q 사고접수, R 안내멘트, T 등록완료
FORMULA_COLS = [0, 7, 15, 16, 17, 19]
FORMULA_NAMES = ["순번", "합계", "고객센터 번호", "사고접수연락처", "고객안내멘트", "등록완료"]

# 콤보박스로 제공할 필드 (기존 시트 값에서 후보를 뽑는다)
CHOICE_FIELDS = ["finance", "channel", "status", "kind"]

# 날짜 열 (시트 서식: 2026. 8. 14)
DATE_FIELDS = ["contract_date", "deliver_date"]

COL_MENT = 17        # R 고객안내멘트 (읽기 전용, 복사용)
COL_DOC = 18         # S 견적서/계약서 (이미지)

# 금액 열 — 화면에서는 1,000 단위로 보여주고 시트에는 숫자로 넣는다
MONEY_FIELDS = ["price", "fee", "incentive"]

LAST_COL = 19                           # T

# 상단 요약(발주 현황) 범위 — N1:O4 (라벨, 값)
SUMMARY_RANGE = "N1:O4"
_A1 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def col_letter(idx: int) -> str:
    """0=A, 1=B ... 25=Z, 26=AA"""
    s = ""
    n = idx
    while True:
        s = _A1[n % 26] + s
        n = n // 26 - 1
        if n < 0:
            break
    return s


def parse_sheet_id(url_or_id: str) -> str:
    """스프레드시트 URL 을 붙여넣어도 ID 만 뽑아낸다."""
    s = (url_or_id or "").strip()
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", s)
    return m.group(1) if m else s


def digits_only(s: str) -> str:
    """'₩57,035,000' → '57035000' (숫자와 마이너스만 남긴다)."""
    t = (s or "").strip()
    neg = t.startswith("-")
    d = "".join(ch for ch in t if ch.isdigit())
    return ("-" + d) if (neg and d) else d


def fmt_money(s: str) -> str:
    """'57035000' → '57,035,000'. 숫자가 없으면 빈 문자열."""
    d = digits_only(s)
    if not d or d == "-":
        return ""
    neg = d.startswith("-")
    n = d.lstrip("-")
    return ("-" if neg else "") + f"{int(n):,}"


def fmt_date(d) -> str:
    """시트 서식(2026. 8. 14)으로. None 이면 빈 문자열."""
    if d is None:
        return ""
    return f"{d.year}. {d.month}. {d.day}"


def parse_date(s: str):
    """'2026. 8. 14' / '2026-08-14' / '2026.8.14' 등을 date 로. 못 읽으면 None."""
    t = (s or "").strip()
    if not t:
        return None
    m = re.match(r"^\s*(\d{4})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})\s*\.?\s*$", t)
    if not m:
        return None
    try:
        from datetime import date as _date
        return _date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except Exception:
        return None


@dataclass
class CustomerRow:
    """시트 한 줄. row 는 실제 시트 행 번호(1부터)."""
    row: int = 0
    seq: str = ""            # 순번 (자동)
    total: str = ""          # 합계 (자동)
    ment: str = ""           # R 고객안내멘트 (자동, 복사용)
    values: dict = field(default_factory=dict)   # 직접기재 필드키 → 값

    def get(self, key: str) -> str:
        return self.values.get(key, "")


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


def _check(r) -> None:
    if r.status_code in (200, 201):
        return
    txt = ""
    try:
        txt = r.text or ""
    except Exception:
        pass
    msg, reason = _error_detail(r)
    low = (msg + " " + reason + " " + txt).lower()

    # ① 클라우드 프로젝트에 Sheets API 가 꺼져 있음 — 재로그인으로는 절대 안 풀린다
    if "service_disabled" in low or "has not been used in project" in low:
        raise GoogleError(
            "구글 클라우드 프로젝트에서 'Google Sheets API' 가 켜져 있지 않습니다.\n"
            "아래 주소를 브라우저에 붙여넣고 [사용] 버튼을 누른 뒤,\n"
            "1~2분 기다렸다가 다시 [불러오기] 하세요.\n\n"
            f"{config.SHEETS_ENABLE_URL}\n\n"
            f"(구글 응답: {msg[:300]})")

    # ② 토큰에 스프레드시트 권한이 안 붙음 — 재로그인이 맞는 처방
    if ("access_token_scope_insufficient" in low or "insufficient" in low
            or "request had insufficient authentication scopes" in low):
        raise GoogleError(
            "로그인 토큰에 스프레드시트 권한이 없습니다.\n"
            "[설정] → [Google 로그아웃] 후 다시 [Google 로그인] 을 해주세요.\n"
            "(고객관리 시트 기능을 위해 스프레드시트 권한이 새로 추가되었습니다.)")

    if r.status_code == 401:
        raise GoogleError("구글 로그인이 만료되었습니다. [설정]에서 다시 로그인하세요.")

    if r.status_code == 403:
        # 원인을 단정하지 말고 구글 원문을 그대로 보여준다
        raise GoogleError(
            "시트 접근이 거부되었습니다 (403).\n"
            f"구글 응답: {msg[:300]}")

    if r.status_code == 404:
        raise GoogleError("시트를 찾을 수 없습니다. 설정의 시트 주소/시트명을 확인하세요.")
    raise GoogleError(f"시트 요청 실패 (HTTP {r.status_code})\n{msg[:300]}")


def _rng(sheet_name: str, a1: str) -> str:
    """시트명에 공백·한글이 있어도 안전하게 A1 표기를 만든다."""
    return urllib.parse.quote(f"'{sheet_name}'!{a1}", safe="")


def read_rows(auth: GoogleAuth, sheet_id: str, sheet_name: str):
    """시트를 읽어 (헤더행번호, [CustomerRow]) 반환.

    속도 최적화:
      - 요청 1회(batchGet)로 목록 + 상단 요약을 한꺼번에 받는다.
      - 분량이 가장 큰 R열(고객안내멘트, 한 건당 20줄 가까이)은 **빼고** 받는다.
        멘트는 목록이 뜬 뒤 read_ments() 로 뒤이어 채운다.
    헤더 행은 A열 '순번' + B열에 '고객명' 이 들어간 행으로 자동 탐지한다.
    """
    url = config.SHEETS_BATCH_GET_URL.format(sheet_id=sheet_id)
    r = requests.get(url, headers=_headers(auth), timeout=30, params=[
        ("ranges", f"'{sheet_name}'!A1:Q"),
        ("ranges", f"'{sheet_name}'!S1:T"),
        ("valueRenderOption", "FORMATTED_VALUE"),
        ("dateTimeRenderOption", "FORMATTED_STRING"),
    ])
    _check(r)
    ranges = (r.json() or {}).get("valueRanges", [])
    left = (ranges[0].get("values", []) if len(ranges) > 0 else [])    # A~Q
    right = (ranges[1].get("values", []) if len(ranges) > 1 else [])   # S~T

    # A~Q 와 S~T 를 한 줄로 합친다 (R 자리는 빈칸으로 채워 열 번호를 맞춘다)
    values = []
    for i in range(max(len(left), len(right))):
        a = list(left[i]) if i < len(left) else []
        b = list(right[i]) if i < len(right) else []
        a += [""] * (17 - len(a))      # A..Q = 17칸
        a.append("")                   # R 자리(멘트는 뒤에서 채움)
        a += b                         # S, T
        values.append(a)

    header_idx = -1
    for i, row in enumerate(values[:30]):     # 위쪽 요약행은 몇 줄 안 된다
        a = (row[0] if len(row) > 0 else "").strip()
        b = (row[1] if len(row) > 1 else "").strip()
        if a.startswith("순번") and "고객명" in b:
            header_idx = i
            break
    if header_idx < 0:
        raise GoogleError(
            f"'{sheet_name}' 시트에서 헤더(순번/고객명…)를 찾지 못했습니다.\n"
            "설정에서 시트명이 맞는지 확인하세요.")

    out: list[CustomerRow] = []
    for i in range(header_idx + 1, len(values)):
        row = values[i]
        if not any((c or "").strip() for c in row):
            continue
        def cell(idx: int) -> str:
            return (row[idx] if len(row) > idx else "") or ""
        cr = CustomerRow(row=i + 1, seq=cell(0).strip(), total=cell(7).strip(),
                         ment=cell(COL_MENT).rstrip())
        for ci, key, _label in FIELDS:
            cr.values[key] = cell(ci).strip()
        if not cr.get("customer") and not cr.seq:
            continue          # 완전히 빈 줄은 건너뜀
        out.append(cr)

    # 상단 요약(N1:O4)은 이미 받은 데이터에서 뽑는다 — 요청을 더 보내지 않는다
    summary = []
    for i in range(min(4, header_idx)):
        row = values[i] if i < len(values) else []
        label = (row[13] if len(row) > 13 else "").strip()
        value = (row[14] if len(row) > 14 else "").strip()
        if label:
            summary.append((label, value))
    return header_idx + 1, out, summary


def read_ments(auth: GoogleAuth, sheet_id: str, sheet_name: str) -> dict:
    """R열(고객안내멘트)만 따로 읽는다 → {행번호: 멘트}.

    목록을 먼저 띄운 뒤 뒤이어 부르는 용도(분량이 커서 첫 로딩을 느리게 만든다).
    """
    url = config.SHEETS_VALUES_URL.format(
        sheet_id=sheet_id, rng=_rng(sheet_name, "R1:R"))
    r = requests.get(url, headers=_headers(auth), timeout=30,
                     params={"valueRenderOption": "FORMATTED_VALUE"})
    _check(r)
    out = {}
    for i, row in enumerate((r.json() or {}).get("values", [])):
        v = (row[0] if row else "") or ""
        if v.strip():
            out[i + 1] = v.rstrip()
    return out


def next_seq(auth: GoogleAuth, sheet_id: str, sheet_name: str,
             last_row: int, rows: list) -> str:
    """새 행에 넣을 순번. A열이 수식이면 "" (건드리지 않고 수식에 맡긴다).

    A열이 그냥 숫자면 직전까지의 최대값 + 1 을 돌려준다.
    (수식 복사만 하던 예전 방식은 A열이 '값'일 때 직전 번호를 그대로 베껴 왔다)
    """
    try:
        url = config.SHEETS_VALUES_URL.format(
            sheet_id=sheet_id, rng=_rng(sheet_name, f"A{last_row}"))
        r = requests.get(url, headers=_headers(auth), timeout=20,
                         params={"valueRenderOption": "FORMULA"})
        if r.status_code == 200:
            vals = (r.json() or {}).get("values", [])
            cur = str(vals[0][0]) if (vals and vals[0]) else ""
            if cur.strip().startswith("="):
                return ""            # 수식이 알아서 계산한다
    except Exception:
        pass
    mx = 0
    for cr in rows or []:
        s = (cr.seq or "").strip()
        if s.isdigit():
            mx = max(mx, int(s))
    return str(mx + 1) if mx else ""


def choices(rows: list[CustomerRow]) -> dict:
    """기존 데이터에서 콤보박스 후보를 모은다(하드코딩하지 않기 위해)."""
    res: dict = {}
    for key in CHOICE_FIELDS:
        seen: list[str] = []
        for r in rows:
            v = r.get(key).strip()
            if v and v not in seen:
                seen.append(v)
        # 자주 쓰는 값이 위로 오도록 빈도순 정렬
        seen.sort(key=lambda v: -sum(1 for r in rows if r.get(key).strip() == v))
        res[key] = seen
    return res


def _write_cells(auth: GoogleAuth, sheet_id: str, sheet_name: str,
                 row: int, values: dict, extra: dict | None = None) -> None:
    """직접기재 열만 **칸 단위**로 기록 → 수식 칸은 손대지 않는다.

    extra: {열인덱스: 값} — 순번처럼 앱이 직접 계산해 넣는 칸.
    """
    data = []
    for ci, val in (extra or {}).items():
        data.append({"range": f"'{sheet_name}'!{col_letter(ci)}{row}",
                     "values": [[val]]})
    for ci, key, _label in FIELDS:
        if key not in values:
            continue
        val = values.get(key, "")
        if key in MONEY_FIELDS:
            # 콤마를 떼고 숫자로 보내야 시트의 통화 서식이 그대로 적용된다
            val = digits_only(val)
        a1 = f"'{sheet_name}'!{col_letter(ci)}{row}"
        data.append({"range": a1, "values": [[val]]})
    if not data:
        return
    url = config.SHEETS_BATCH_UPDATE_VALUES_URL.format(sheet_id=sheet_id)
    r = requests.post(url, headers=_headers(auth), timeout=30,
                      json={"valueInputOption": "USER_ENTERED", "data": data})
    _check(r)


def _sheet_gid(auth: GoogleAuth, sheet_id: str, sheet_name: str) -> int:
    """시트(탭) 이름 → gid. 수식 복사(copyPaste)에 필요."""
    url = config.SHEETS_BASE_URL.format(sheet_id=sheet_id)
    r = requests.get(url, headers=_headers(auth), timeout=30,
                     params={"fields": "sheets(properties(sheetId,title))"})
    _check(r)
    for sh in (r.json() or {}).get("sheets", []):
        p = sh.get("properties", {})
        if p.get("title") == sheet_name:
            return int(p.get("sheetId", 0))
    raise GoogleError(f"'{sheet_name}' 시트를 찾지 못했습니다.")


def _copy_row_style(auth: GoogleAuth, sheet_id: str, gid: int,
                    src_row: int, dst_row: int) -> None:
    """직전 행의 서식·드롭다운·조건부서식·수식을 새 행으로 복사.

    값만 써 넣으면 새 행에는 **드롭다운(데이터 확인)과 색상 규칙이 없어서**
    '대리점' 을 넣어도 시트에서 색이 안 입혀진다. 통화 서식도 마찬가지다.
    그래서 값을 쓰기 전에 직전 행의 '겉모습'을 통째로 물려받게 한다.

      - PASTE_FORMAT                : 글꼴/색/통화 서식
      - PASTE_DATA_VALIDATION       : 드롭다운 목록(색상 칩 포함)
      - PASTE_CONDITIONAL_FORMATTING: 조건부 색상 규칙
      - PASTE_FORMULA (수식 열만)    : 순번/합계/안내멘트/등록완료 등

    실패해도 값 입력은 계속 진행한다.
    """
    def rng(c0: int, c1: int, row: int):
        return {"sheetId": gid, "startRowIndex": row - 1, "endRowIndex": row,
                "startColumnIndex": c0, "endColumnIndex": c1}

    reqs = []
    # 1) 행 전체의 겉모습(서식/드롭다운/조건부서식)
    for ptype in ("PASTE_FORMAT", "PASTE_DATA_VALIDATION", "PASTE_CONDITIONAL_FORMATTING"):
        reqs.append({"copyPaste": {
            "source": rng(0, LAST_COL + 1, src_row),
            "destination": rng(0, LAST_COL + 1, dst_row),
            "pasteType": ptype,
        }})
    # 2) 수식은 수식 열에만 (값 열에 수식이 들어가면 안 된다)
    for ci in FORMULA_COLS:
        reqs.append({"copyPaste": {
            "source": rng(ci, ci + 1, src_row),
            "destination": rng(ci, ci + 1, dst_row),
            "pasteType": "PASTE_FORMULA",
        }})
    url = config.SHEETS_BATCH_UPDATE_URL.format(sheet_id=sheet_id)
    r = requests.post(url, headers=_headers(auth), timeout=30, json={"requests": reqs})
    _check(r)


def append_row(auth: GoogleAuth, sheet_id: str, sheet_name: str,
               values: dict, last_row: int, seq: str = "") -> int:
    """맨 아래에 고객 한 줄 추가. 새 행 번호를 반환.

    순서: (1) 직전 행의 서식·드롭다운·수식 복사 → (2) 직접기재 칸 + 순번 기록.
    """
    new_row = last_row + 1
    try:
        gid = _sheet_gid(auth, sheet_id, sheet_name)
        _copy_row_style(auth, sheet_id, gid, last_row, new_row)
    except Exception:
        # 서식/수식 복사가 안 되어도(권한/구조 문제) 값 입력은 진행한다
        pass
    extra = {0: seq} if seq else None      # A열 순번 (수식이면 seq="" 라 건너뜀)
    _write_cells(auth, sheet_id, sheet_name, new_row, values, extra)
    return new_row


def update_row(auth: GoogleAuth, sheet_id: str, sheet_name: str,
               row: int, values: dict) -> None:
    """기존 고객 줄 수정 — 직접기재 칸만 갱신(수식 칸 보존)."""
    _write_cells(auth, sheet_id, sheet_name, row, values)


def sheet_url(sheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"


# ---------------------------------------------------------------------------
# 견적서/계약서 이미지 — 드라이브 업로드 후 셀에 =IMAGE() 로 표시
#
# ⚠️ 구글 시트가 셀 안에 그림을 그리려면 이미지를 '링크가 있는 누구나 열람' 으로
#    공개해야 한다(시트 서버가 사용자 인증 없이 이미지를 가져오기 때문).
#    주소를 아는 사람은 볼 수 있으므로, 앱에서 최초 1회 확인을 받는다.
# ---------------------------------------------------------------------------
IMAGE_FOLDER_NAME = "일정관리기 견적서"


def _find_or_create_folder(auth: GoogleAuth, name: str) -> str:
    """드라이브에 전용 폴더를 찾거나 만든다(앱이 만든 파일만 접근하는 권한)."""
    q = (f"name='{name}' and mimeType='application/vnd.google-apps.folder'"
         " and trashed=false")
    r = requests.get(config.DRIVE_FILES_URL, headers=_headers(auth), timeout=20,
                     params={"q": q, "fields": "files(id,name)", "pageSize": 1})
    if r.status_code == 200:
        files = (r.json() or {}).get("files", [])
        if files:
            return files[0].get("id", "")
    r = requests.post(config.DRIVE_FILES_URL, headers=_headers(auth), timeout=20,
                      json={"name": name,
                            "mimeType": "application/vnd.google-apps.folder"})
    _check(r)
    return (r.json() or {}).get("id", "")


def upload_image(auth: GoogleAuth, data: bytes, filename: str) -> str:
    """PNG 바이트를 드라이브에 올리고 '링크 공개' 후 이미지 URL 을 돌려준다."""
    folder = ""
    try:
        folder = _find_or_create_folder(auth, IMAGE_FOLDER_NAME)
    except Exception:
        folder = ""

    meta = {"name": filename}
    if folder:
        meta["parents"] = [folder]

    # multipart 업로드 (메타데이터 + 파일 본문)
    boundary = "planner-img-boundary"
    body = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
        + json.dumps(meta) + f"\r\n--{boundary}\r\nContent-Type: image/png\r\n\r\n"
    ).encode("utf-8") + data + f"\r\n--{boundary}--\r\n".encode("utf-8")

    h = _headers(auth)
    h["Content-Type"] = f"multipart/related; boundary={boundary}"
    r = requests.post(config.DRIVE_UPLOAD_URL, headers=h, data=body, timeout=120,
                      params={"uploadType": "multipart", "fields": "id"})
    _check(r)
    file_id = (r.json() or {}).get("id", "")
    if not file_id:
        raise GoogleError("이미지 업로드에 실패했습니다.")

    # 시트가 이미지를 가져올 수 있도록 '링크가 있는 누구나 보기' 로 공개
    pr = requests.post(f"{config.DRIVE_FILES_URL}/{file_id}/permissions",
                       headers=_headers(auth), timeout=20,
                       json={"role": "reader", "type": "anyone"})
    if pr.status_code not in (200, 201):
        raise GoogleError(
            "이미지를 올렸지만 공개 설정에 실패해 셀에 표시할 수 없습니다.\n"
            f"(HTTP {pr.status_code})")
    return image_url(file_id)


def image_url(file_id: str) -> str:
    return f"https://drive.google.com/uc?export=view&id={file_id}"


def image_formula(url: str) -> str:
    """셀 안에 그림으로 보이게 하는 수식 (4 = 원본비율 유지하며 셀에 맞춤)."""
    return f'=IMAGE("{url}", 1)'
