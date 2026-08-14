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
    (18, "doc", "견적서/계약서"),
    (19, "registered", "등록완료"),
]

# 수식(자동 계산) 열 — 절대 쓰지 않는다
FORMULA_COLS = [0, 7, 15, 16, 17]      # A 순번, H 합계, P 고객센터, Q 사고접수, R 안내멘트
FORMULA_NAMES = ["순번", "합계", "고객센터 번호", "사고접수연락처", "고객안내멘트"]

# 콤보박스로 제공할 필드 (기존 시트 값에서 후보를 뽑는다)
CHOICE_FIELDS = ["finance", "channel", "status", "kind", "registered"]

LAST_COL = 19                           # T
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


@dataclass
class CustomerRow:
    """시트 한 줄. row 는 실제 시트 행 번호(1부터)."""
    row: int = 0
    seq: str = ""            # 순번 (자동)
    total: str = ""          # 합계 (자동)
    values: dict = field(default_factory=dict)   # 직접기재 필드키 → 값

    def get(self, key: str) -> str:
        return self.values.get(key, "")


def _headers(auth: GoogleAuth) -> dict:
    return {"Authorization": "Bearer " + auth.valid_token()}


def _check(r) -> None:
    if r.status_code in (200, 201):
        return
    txt = ""
    try:
        txt = r.text or ""
    except Exception:
        pass
    if r.status_code in (401, 403) or "insufficient" in txt.lower() or "scope" in txt.lower():
        raise GoogleError(
            "시트 접근 권한이 없습니다.\n"
            "[설정] → [Google 로그아웃] 후 다시 [Google 로그인] 을 해주세요.\n"
            "(고객관리 시트 기능을 위해 스프레드시트 권한이 새로 추가되었습니다.)")
    if r.status_code == 404:
        raise GoogleError("시트를 찾을 수 없습니다. 설정의 시트 주소/시트명을 확인하세요.")
    raise GoogleError(f"시트 요청 실패 (HTTP {r.status_code})")


def _rng(sheet_name: str, a1: str) -> str:
    """시트명에 공백·한글이 있어도 안전하게 A1 표기를 만든다."""
    return urllib.parse.quote(f"'{sheet_name}'!{a1}", safe="")


def read_rows(auth: GoogleAuth, sheet_id: str, sheet_name: str):
    """시트를 읽어 (헤더행번호, [CustomerRow]) 반환.

    헤더 행은 A열 '순번' + B열에 '고객명' 이 들어간 행으로 자동 탐지한다.
    """
    url = config.SHEETS_VALUES_URL.format(
        sheet_id=sheet_id, rng=_rng(sheet_name, f"A1:{col_letter(LAST_COL)}"))
    r = requests.get(url, headers=_headers(auth), timeout=30,
                     params={"valueRenderOption": "FORMATTED_VALUE",
                             "dateTimeRenderOption": "FORMATTED_STRING"})
    _check(r)
    values = (r.json() or {}).get("values", [])

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
        cr = CustomerRow(row=i + 1, seq=cell(0).strip(), total=cell(7).strip())
        for ci, key, _label in FIELDS:
            cr.values[key] = cell(ci).strip()
        if not cr.get("customer") and not cr.seq:
            continue          # 완전히 빈 줄은 건너뜀
        out.append(cr)
    return header_idx + 1, out


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
                 row: int, values: dict) -> None:
    """직접기재 열만 **칸 단위**로 기록 → 수식 칸은 손대지 않는다."""
    data = []
    for ci, key, _label in FIELDS:
        if key not in values:
            continue
        a1 = f"'{sheet_name}'!{col_letter(ci)}{row}"
        data.append({"range": a1, "values": [[values.get(key, "")]]})
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


def _copy_formulas(auth: GoogleAuth, sheet_id: str, gid: int,
                   src_row: int, dst_row: int) -> None:
    """직전 행의 수식을 새 행으로 복사 (행 참조는 구글이 자동 보정).

    ARRAYFORMULA 로 이미 자동 확장되는 시트라면 이 호출은 사실상 무해하다.
    실패해도 값 입력은 계속 진행한다(수식은 사용자가 채울 수 있으므로).
    """
    reqs = []
    for ci in FORMULA_COLS:
        reqs.append({"copyPaste": {
            "source": {"sheetId": gid, "startRowIndex": src_row - 1, "endRowIndex": src_row,
                       "startColumnIndex": ci, "endColumnIndex": ci + 1},
            "destination": {"sheetId": gid, "startRowIndex": dst_row - 1, "endRowIndex": dst_row,
                            "startColumnIndex": ci, "endColumnIndex": ci + 1},
            "pasteType": "PASTE_FORMULA",
        }})
    if not reqs:
        return
    url = config.SHEETS_BATCH_UPDATE_URL.format(sheet_id=sheet_id)
    r = requests.post(url, headers=_headers(auth), timeout=30, json={"requests": reqs})
    _check(r)


def append_row(auth: GoogleAuth, sheet_id: str, sheet_name: str,
               values: dict, last_row: int) -> int:
    """맨 아래에 고객 한 줄 추가. 새 행 번호를 반환.

    순서: (1) 직전 행의 수식을 새 행에 복사 → (2) 직접기재 칸만 기록.
    """
    new_row = last_row + 1
    try:
        gid = _sheet_gid(auth, sheet_id, sheet_name)
        _copy_formulas(auth, sheet_id, gid, last_row, new_row)
    except Exception:
        # 수식 복사가 안 되어도(권한/구조 문제) 값 입력은 진행한다
        pass
    _write_cells(auth, sheet_id, sheet_name, new_row, values)
    return new_row


def update_row(auth: GoogleAuth, sheet_id: str, sheet_name: str,
               row: int, values: dict) -> None:
    """기존 고객 줄 수정 — 직접기재 칸만 갱신(수식 칸 보존)."""
    _write_cells(auth, sheet_id, sheet_name, row, values)


def sheet_url(sheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
