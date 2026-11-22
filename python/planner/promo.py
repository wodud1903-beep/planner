"""수입차 프로모션 조건표 — 회사 프로모션 시트의 '수입차 프로모션' 탭을 읽어 브랜드별 표로(v1.34).

지점장: "4행을 제목으로 쓰고 각각의 할인표를 불러오고 싶어. 모델명을 자료검색처럼 실시간 검색하면
바로 해당 열에 맞는 정보가 나오게." 시트 모양(2026-11 기준):

  · 세 블록이 옆으로 나란히 — B:G 벤츠 · I:N BMW · P:U 아우디. 블록 사이는 빈 열 하나.
  · 2~3행: 블록 제목("벤츠 11월 프로모션 ***** 11/03 (화) 기준 *****")과 묶음 제목
    ("기본값 변동 X" 가 모델·차량가 위에, "11월 프로모션" 이 할인 칸 위에 — 셀 병합).
  · 4행: 열 제목 — 블록마다 다르다(벤츠 MBF·프로모션 / BMW 현금·제휴사 / 아우디 현금 할인·제휴사 할인).
    **그대로** 쓴다. 블록은 이 줄의 '빈 칸으로 나뉜 덩어리' 로 찾는다 — 브랜드가 늘어도 따라간다.
  · 5행부터: 모델 한 줄씩. 첫 칸만 있는 짧은 줄은 구역 이름(전기차 라인업 · 고성능 라인업 …),
    여러 줄 글은 안내(재구매·트레이드인 · 이번달 특별 이슈).

읽기만 한다(시트를 고치지 않는다). 받은 값은 그대로 계정 폴더에 두었다가(promo_cache.json) 탭을 열자마자
보여 주고, 뒤에서 새로 읽는다. 해석은 늘 받은 값에서 다시 한다 — 해석을 고쳐도 저장본이 따라온다.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
from datetime import datetime, timedelta

from . import config, hangul, net, sheets
from .google_client import GoogleError

CACHE_FILE = "promo_cache.json"
CACHE_VER = 1
READ_COLS = "A1:AZ"        # 지금은 U 까지 — 브랜드가 늘어도 읽히게 넉넉히
STALE_SEC = 10 * 60        # 탭을 다시 열 때 이만큼 지났으면 새로 읽는다
META_SEC = 6 * 3600        # 셀 병합·탭 번호는 이만큼에 한 번만 묻는다
_META: dict = {}           # {(시트, 탭): (병합, 탭 번호, 받은 때)}


# 회사 프로모션 시트는 켤 때부터 읽기 전용(v1.34.2) — 화면을 열기 전이라도 어떤 기능도 여기에 쓰지 못한다
net.protect(config.PROMO_DEF_SHEET_ID)


class PromoError(GoogleError):
    """프로모션 시트를 못 읽음 — 사람이 읽는 말."""


# ---------------------------------------------------------------------------
# 브랜드
# ---------------------------------------------------------------------------
# (열쇠, 보이는 이름, 알아보는 말) — 블록 제목에서 찾는다. 검색칸에 이 말을 치면 그 브랜드만.
BRANDS = (
    ("benz", "벤츠", ("benz", "벤츠", "mercedes", "메르세데스")),
    ("bmw", "BMW", ("bmw", "비엠", "비엠더블유")),
    ("audi", "아우디", ("audi", "아우디")),
    ("volvo", "볼보", ("volvo", "볼보")),
    ("porsche", "포르쉐", ("porsche", "포르쉐")),
    ("lexus", "렉서스", ("lexus", "렉서스")),
    ("lr", "랜드로버", ("landrover", "land rover", "랜드로버")),
)
# 검색칸에서 브랜드로 읽는 말 — 한글은 앞부분만 쳐도("벤", "아우") 된다(치는 도중에 0건으로 깜빡이지 않게)
_BRAND_WORDS = {w.replace(" ", ""): k for k, _n, ws in BRANDS for w in ws if " " not in w}
_BRAND_KO = {w: k for w, k in _BRAND_WORDS.items() if re.match(r"[가-힣]", w)}


def brand_of(text: str):
    """블록 제목에서 브랜드(열쇠, 이름) — 모르면 None."""
    low = re.sub(r"\s+", "", (text or "").lower())
    for key, name, words in BRANDS:
        if any(w.replace(" ", "") in low for w in words):
            return key, name
    return None


def brand_token(tok: str) -> str:
    """검색 낱말이 브랜드 이름이면 그 열쇠("" = 아님)."""
    t = hangul._squash(tok)
    if not t:
        return ""
    if t in _BRAND_WORDS:
        return _BRAND_WORDS[t]
    if re.match(r"[가-힣]", t):
        for w, k in _BRAND_KO.items():
            if w.startswith(t):
                return k
    return ""


# ---------------------------------------------------------------------------
# 글 다듬기
# ---------------------------------------------------------------------------
def _cell(row, i) -> str:
    try:
        v = row[i]
    except (IndexError, TypeError):
        return ""
    return str(v if v is not None else "").replace("\r\n", "\n").replace("\r", "\n")


def clean_title(s: str) -> str:
    """'벤츠 11월 프로모션      ***** 11/03 (화) 기준 *****' → '벤츠 11월 프로모션 11/03 (화) 기준'."""
    s = re.sub(r"\*{2,}", " ", s or "")
    return re.sub(r"\s+", " ", s).strip()


def clean_head(s: str) -> str:
    return re.sub(r"[ \t]+", " ", (s or "").replace("\n", " ")).strip()


_RE_NUM = re.compile(r"^[\d,.\s%+\-원만]+$")


def is_number(s: str) -> bool:
    """'4,900,000' · '0' · '0%' · '4%추가'(아님) — 오른쪽에 붙일 칸인가."""
    t = (s or "").strip()
    return bool(t) and bool(re.search(r"\d", t)) and bool(_RE_NUM.match(t))


# 할인 칸에 숫자 대신 적힌 말 — 눈에 띄게(재고 없음·종료 등은 빨강, 신형은 파랑)
_BAD_WORDS = ("재고없음", "재고 없음", "종료", "단종", "재고 0")
_NEW_WORDS = ("신형", "연식변경", "신규")


def tone_of(s: str) -> str:
    t = (s or "").strip()
    if not t or is_number(t):
        return ""
    if any(w in t for w in _BAD_WORDS):
        return "red"
    if any(w in t for w in _NEW_WORDS):
        return "blue"
    return ""


# ---------------------------------------------------------------------------
# 해석
# ---------------------------------------------------------------------------
def _runs(cells: list) -> list:
    """빈 칸으로 나뉜 덩어리 [(시작 열, 너비)] — 4행 열 제목에서 블록을 찾는다."""
    out, start = [], None
    for i, v in enumerate(list(cells) + [""]):
        if str(v or "").strip():
            if start is None:
                start = i
        elif start is not None:
            if i - start >= 2:               # 한 칸짜리는 블록이 아니다(메모 등)
                out.append((start, i - start))
            start = None
    return out


_RE_HEAD = re.compile(r"모델|차\s*종|차량\s*가")


def header_row(values: list) -> int:
    """열 제목 줄(0부터) — 처음 10줄 가운데 '모델·차종·차량가' 가 두 블록 이상 있는 줄. 없으면 4행."""
    best = -1
    for i, row in enumerate((values or [])[:10]):
        hits = sum(1 for c in (row or []) if _RE_HEAD.search(str(c or "")))
        if hits >= 2:
            return i
        if hits == 1 and best < 0:
            best = i
    return best if best >= 0 else 3


def _merge_spans(merges: list, row: int, c0: int, width: int) -> dict:
    """그 줄에서 블록 안의 병합 {시작 열(블록 안): 너비}."""
    out = {}
    for m in merges or []:
        try:
            r0, r1, k0, k1 = (int(x) for x in m)
        except Exception:
            continue
        if r0 <= row < r1 and c0 <= k0 < c0 + width:
            out[k0 - c0] = max(1, min(k1, c0 + width) - k0)
    return out


def _kind(cells: list) -> str:
    first = cells[0].strip()
    rest = [c for c in cells[1:] if c.strip()]
    if rest or not first:
        return "model"
    if "\n" in first or len(first) > 40:
        return "note"
    # 모델 이름엔 거의 늘 영문·숫자가 있다 — 한글만 있는 짧은 줄은 구역 이름
    if not re.search(r"[A-Za-z0-9]", first):
        return "section"
    return "model"


def parse(values: list, merges: list | None = None) -> list:
    """시트 값 → 블록 목록.

    블록 = {key, brand, title, groups[(시작, 너비, 글)], headers[6], rows[...]}
    줄 = {kind: model|section|note, cells[너비], section, row(시트 행 번호), hay(검색용)}
    """
    values = values or []
    if not values:
        return []
    hi = header_row(values)
    heads = [str(c or "") for c in (values[hi] if hi < len(values) else [])]
    blocks = []
    used = set()
    for bi, (c0, width) in enumerate(_runs(heads)):
        headers = [clean_head(_cell(heads, c0 + k)) for k in range(width)]
        # 블록 제목 · 묶음 제목 — 열 제목 위의 줄들
        titles, groups = [], []
        for r in range(0, hi):
            cells = [_cell(values[r], c0 + k).strip() for k in range(width)]
            filled = [(k, t) for k, t in enumerate(cells) if t]
            if not filled:
                continue
            if len(filled) == 1 and filled[0][0] == 0:
                t = clean_title(filled[0][1])
                if t and t != ".":
                    titles.append(t)
                continue
            # 여러 칸 → 묶음 제목(병합을 알면 그 너비, 모르면 다음 묶음 앞까지)
            spans = _merge_spans(merges, r, c0, width)
            for j, (k, t) in enumerate(filled):
                nxt = filled[j + 1][0] if j + 1 < len(filled) else width
                groups.append((k, spans.get(k, nxt - k), clean_title(t)))
        b = brand_of(" ".join(titles)) or brand_of(" ".join(g[2] for g in groups))
        if b is None or b[0] in used:
            first = (titles[0].split() or [""])[0] if titles else ""
            b = (f"b{bi}", first or f"브랜드 {bi + 1}")
        used.add(b[0])
        rows, section = [], ""
        for r in range(hi + 1, len(values)):
            cells = [_cell(values[r], c0 + k) for k in range(width)]
            if not any(c.strip() for c in cells):
                continue
            kind = _kind(cells)
            if kind == "section":
                section = cells[0].strip()
            cells = [c.strip() if kind != "note" else c.strip("\n ") for c in cells]
            if kind == "model":
                cells = [re.sub(r"\s*\n\s*", " ", c) for c in cells]
            # 찾는 곳: 모델 이름(또는 안내 글) + 구역 이름. \x1f 로 나눠 두 글이 이어 붙어 걸리지 않게
            hay = cells[0] + ("\x1f" + section if section and kind != "section" else "")
            rows.append({"kind": kind, "cells": cells, "section": section if kind != "section" else "",
                         "row": r + 1, "prep": hangul.prepare(hay)})
        blocks.append({"key": b[0], "brand": b[1], "title": " · ".join(titles),
                       "groups": groups, "headers": headers, "rows": rows, "col": c0})
    return blocks


def model_count(blocks: list) -> int:
    return sum(1 for b in blocks for r in b["rows"] if r["kind"] == "model" and r["cells"][0])


# ---------------------------------------------------------------------------
# 찾기
# ---------------------------------------------------------------------------
def split_query(query: str) -> tuple:
    """검색 글 → (브랜드 열쇠 모음, 나머지 글). '벤츠 e300' → ({'benz'}, 'e300')."""
    brands, rest = set(), []
    for tok in (query or "").split():
        k = brand_token(tok)
        if k:
            brands.add(k)
        else:
            rest.append(tok)
    return brands, " ".join(rest)


def search(blocks: list, query: str = "", brand: str = "") -> list:
    """보일 것 [(블록, 줄 목록)] — 맞는 모델 줄 + 그 줄이 든 구역 이름. 브랜드는 고른 것(또는 친 것)만.

    · 검색이 비면 그 브랜드의 모든 줄(구역·안내 포함) 그대로.
    · 검색 글은 모델 이름(+ 구역 이름)에서 찾는다 — 자료검색과 같은 방식(초성 · 띄어 쓴 낱말은 모두 · 끝 글자 조합 중).
      '전기차' 처럼 구역 이름을 치면 그 구역이 통째로, '트레이드' 처럼 안내 글을 치면 그 안내가 나온다.
    """
    typed, text = split_query(query)
    allow = typed or ({brand} if brand else None)
    out = []
    for b in blocks:
        if allow is not None and b["key"] not in allow:
            continue
        if not text.strip():
            rows = list(b["rows"])
        else:
            rows, shown_sec = [], set()
            sec_rows = {r["cells"][0]: r for r in b["rows"] if r["kind"] == "section"}
            for r in b["rows"]:
                if r["kind"] == "section":
                    continue
                if not hangul.matches_prepared(r["prep"], text):
                    continue
                sec = r.get("section") or ""
                if sec and sec not in shown_sec and sec in sec_rows:
                    shown_sec.add(sec)
                    rows.append(sec_rows[sec])
                rows.append(r)
        if rows:
            out.append((b, rows))
    return out


def hit_count(found: list) -> dict:
    """{브랜드 열쇠: 맞은 모델 줄 수}."""
    return {b["key"]: sum(1 for r in rows if r["kind"] == "model") for b, rows in found}


def row_text(block: dict, row: dict) -> str:
    """한 줄을 카톡에 붙이기 좋게 — 'E300 4M+ AMG Line [26MY] · 차량가격 99,000,000 · MBF 13,900,000 …'."""
    cells = row.get("cells") or []
    if row.get("kind") != "model":
        return (cells[0] if cells else "").strip()
    parts = [cells[0]] if cells and cells[0] else []
    for k in range(1, len(cells)):
        v = cells[k].strip()
        if not v:
            continue
        h = block["headers"][k] if k < len(block["headers"]) else ""
        parts.append(f"{h} {v}" if h else v)
    return " · ".join(parts)


# ---------------------------------------------------------------------------
# 읽기 · 저장본
# ---------------------------------------------------------------------------
def _range(tab: str) -> str:
    tab = (tab or "").strip()
    if not tab:
        return urllib.parse.quote(READ_COLS, safe="")
    return sheets._rng(tab, READ_COLS)


def _fail(r, sheet_id: str, tab: str):
    """구글 응답 → 알아듣는 말. 권한(403)은 '보기' 공유면 된다고 알려 준다(편집 권한은 필요 없다)."""
    msg, reason = sheets._error_detail(r)
    low = (msg + " " + reason).lower()
    if r.status_code == 403 and "scope" not in low and "service_disabled" not in low \
            and "has not been used" not in low:
        raise PromoError(
            "이 구글 계정으로는 프로모션 시트를 볼 수 없습니다.\n"
            "시트 주인에게 이 계정을 '뷰어'(보기)로 공유해 달라고 하세요.")
    if r.status_code == 404:
        raise PromoError("프로모션 시트를 찾지 못했습니다 — [설정] → [화면·기타] 의 시트 주소를 확인하세요.")
    if r.status_code == 400 and "parse range" in low:
        raise PromoError(f"시트에 '{tab}' 탭이 없습니다 — [설정] → [화면·기타] 의 탭 이름을 확인하세요.")
    sheets._check(r)          # 권한 범위·로그인 만료·API 꺼짐 등은 고객 시트와 같은 말로
    raise PromoError(f"프로모션 시트를 읽지 못했습니다 (HTTP {r.status_code}).")


class _GetOnly:
    """GET 만 되는 연결(v1.34.2) — 이 모듈은 시트를 읽기만 한다. 다른 것을 부르면 그 자리에서 멈춘다."""

    def __init__(self, s):
        self._s = s

    def get(self, *a, **k):
        return self._s.get(*a, **k)

    def __getattr__(self, name):
        raise net.ReadOnlySheet("수입차 프로모션은 읽기만 합니다 — " + name + " 은(는) 쓸 수 없습니다.")


def _http():
    return _GetOnly(net.http())


def read(auth, sheet_id: str, tab: str) -> dict:
    """시트에서 받은 그대로 {values, merges, at}. 못 읽으면 PromoError(또는 GoogleError)."""
    sheet_id = (sheet_id or "").strip()
    net.protect(sheet_id)              # 이 시트는 이 프로그램 어디에서도 쓰지 못하게(net.check_write)
    if not sheet_id:
        raise PromoError("프로모션 시트 주소가 비어 있습니다 — [설정] → [화면·기타] 에서 넣어 주세요.")
    if auth is None or not auth.is_connected():
        raise PromoError("구글 로그인 후 볼 수 있습니다 — [설정] 에서 Google 로그인을 해 주세요.")
    hdr = sheets._headers(auth)
    url = config.SHEETS_VALUES_URL.format(sheet_id=sheet_id, rng=_range(tab))
    r = _http().get(url, headers=hdr, timeout=30, params={
        "valueRenderOption": "FORMATTED_VALUE", "dateTimeRenderOption": "FORMATTED_STRING"})
    if r.status_code != 200:
        _fail(r, sheet_id, tab)
    values = (r.json() or {}).get("values", []) or []
    # 셀 병합(묶음 제목 너비) · 탭 번호(시트 열기) — 못 받아도 괜찮다(다음 묶음 앞까지로 본다).
    # 거의 안 바뀌므로 6시간에 한 번만 묻는다(v1.34 — 시트 읽기 한도 1분 60번을 아낀다)
    key = (sheet_id, (tab or "").strip())
    memo = _META.get(key)
    if memo and time.time() - memo[2] < META_SEC:
        return {"values": values, "merges": memo[0], "gid": memo[1],
                "at": datetime.now().strftime("%Y-%m-%d %H:%M")}
    merges, gid, got = [], None, False
    try:
        m = _http().get(config.SHEETS_BASE_URL.format(sheet_id=sheet_id), headers=hdr, timeout=20,
                           params={"fields": "sheets(properties(title,sheetId),merges)"})
        if m.status_code == 200:
            for sh in (m.json() or {}).get("sheets", []) or []:
                title = ((sh.get("properties") or {}).get("title") or "")
                if (tab or "").strip() and title != tab.strip():
                    continue
                gid = (sh.get("properties") or {}).get("sheetId")
                for g in sh.get("merges", []) or []:
                    merges.append([g.get("startRowIndex", 0), g.get("endRowIndex", 0),
                                   g.get("startColumnIndex", 0), g.get("endColumnIndex", 0)])
                break
            got = True
    except Exception:
        merges = []
    if got:
        _META[key] = (merges, gid, time.time())
    return {"values": values, "merges": merges, "gid": gid,
            "at": datetime.now().strftime("%Y-%m-%d %H:%M")}


def save_cache(sheet_id: str, tab: str, raw: dict) -> None:
    o = {"v": CACHE_VER, "sheet_id": sheet_id, "tab": tab, "gid": raw.get("gid"),
         "values": raw.get("values") or [], "merges": raw.get("merges") or [], "at": raw.get("at", "")}
    try:
        config.atomic_write(config.data_file(CACHE_FILE), json.dumps(o, ensure_ascii=False))
    except OSError:
        pass


def load_cache(sheet_id: str, tab: str):
    """그 시트·탭의 저장본(없거나 다른 시트 것이면 None)."""
    try:
        o = json.loads(config.data_file(CACHE_FILE).read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(o, dict) or o.get("v") != CACHE_VER:
        return None
    if (o.get("sheet_id") or "") != (sheet_id or "") or (o.get("tab") or "") != (tab or ""):
        return None
    if not isinstance(o.get("values"), list) or not o["values"]:
        return None
    return {"values": o["values"], "merges": o.get("merges") or [], "gid": o.get("gid"),
            "at": o.get("at", "")}


# ---------------------------------------------------------------------------
# 바뀐 곳(v1.35 — 지점장이 고른 P1): **같은 달 판끼리만** 견준다
# ---------------------------------------------------------------------------
# 회사가 달 중간에 조건을 고치면(11/03 판 → 11/20 판) 바뀐 칸을 노랗게, 새로 생긴 모델은 '신규',
# 빠진 모델은 이름으로 알린다. 달이 바뀌면(11월 → 12월 프로모션) 표 전체가 새것이라 표시하지 않는다.
#
# 브랜드마다 '지금 판' 과 '전 판' 을 들고 있는다. 새로 읽은 표가 지금 판과 같으면 그대로 두어
# 표시가 계속 남고(다음에 시트가 바뀔 때까지), 다르면 지금 판이 전 판이 되고 새 표가 지금 판이다.
# 달은 블록 제목('벤츠 11월 프로모션 · 11/03 (화) 기준')에서 읽고, 없으면 받은 때(한국 시각)의 달.
#
# ⚠️ web/js/promo.js 가 똑같이 옮겼다 — 같은 입력이면 같은 답(vectors.json 'promo_track').
_KST = timedelta(hours=9)
_RE_MONTH = re.compile(r"([0-9]{1,2})\s*월")
_RE_MD = re.compile(r"([0-9]{1,2})\s*/\s*([0-9]{1,2})")


def title_month(title: str) -> int:
    """'벤츠 11월 프로모션 · 11/03 (화) 기준' → 11. 'N월' 이 없으면 'M/D' 의 M, 그것도 없으면 0."""
    t = str(title or "")
    m = _RE_MONTH.search(t)
    if m and 1 <= int(m.group(1)) <= 12:
        return int(m.group(1))
    m = _RE_MD.search(t)
    if m and 1 <= int(m.group(1)) <= 12:
        return int(m.group(1))
    return 0


def title_date(title: str) -> str:
    """제목의 기준일 '11/03' (없으면 '')."""
    m = _RE_MD.search(str(title or ""))
    if m and 1 <= int(m.group(1)) <= 12 and 1 <= int(m.group(2)) <= 31:
        return f"{int(m.group(1)):02d}/{int(m.group(2)):02d}"
    return ""


def _kst(ms) -> datetime:
    return datetime(1970, 1, 1) + timedelta(milliseconds=int(ms or 0)) + _KST


def _md(ms) -> str:
    d = _kst(ms)
    return f"{d.month:02d}/{d.day:02d}"


def row_keys(block: dict) -> list:
    """block['rows'] 와 같은 자리의 열쇠 — 모델 줄은 '구역␟모델␟몇 번째', 나머지는 ''."""
    seen, out = {}, []
    for r in block.get("rows") or []:
        cells = r.get("cells") or [""]
        if r.get("kind") != "model" or not cells[0]:
            out.append("")
            continue
        base = (r.get("section") or "") + "\x1f" + cells[0]
        n = seen.get(base, 0)
        seen[base] = n + 1
        out.append(f"{base}\x1f{n}")
    return out


def snap(block: dict) -> dict:
    """견주려고 남겨 두는 판 — 제목 · 달 · 기준일 · 열 제목 · 모델 줄."""
    rows, order = {}, []
    for k, r in zip(row_keys(block), block.get("rows") or []):
        if k:
            rows[k] = [str(c) for c in r.get("cells") or []]
            order.append(k)
    t = str(block.get("title") or "")
    return {"title": t, "month": title_month(t), "date": title_date(t),
            "headers": [str(h) for h in block.get("headers") or []], "rows": rows, "order": order}


def _same_snap(a: dict, b: dict) -> bool:
    def canon(s):
        return (s.get("title"), s.get("headers"), s.get("order"),
                [s.get("rows", {}).get(k) for k in s.get("order") or []])
    return canon(a) == canon(b)


def same_month(prev: dict, prev_at, cur: dict, cur_at) -> bool:
    a, b = int(prev.get("month") or 0), int(cur.get("month") or 0)
    if a and b:
        return a == b
    pa, ca = _kst(prev_at), _kst(cur_at)
    return (pa.year, pa.month) == (ca.year, ca.month)


def _col_ids(headers: list) -> list:
    seen, out = {}, []
    for i, h in enumerate(headers or []):
        h = str(h or "").strip()
        if not h:
            out.append(f"\x1f#{i}")
            continue
        n = seen.get(h, 0)
        seen[h] = n + 1
        out.append(f"{h}\x1f{n}")
    return out


def diff(prev: dict, cur: dict) -> dict:
    """전 판 → 지금 판: {changed: {줄 열쇠: [바뀐 칸 번호]}, new: [새 줄 열쇠], gone: [빠진 모델 이름], count}."""
    pid = {c: j for j, c in enumerate(_col_ids(prev.get("headers")))}
    cid = _col_ids(cur.get("headers"))
    prows, crows = prev.get("rows") or {}, cur.get("rows") or {}
    changed, new = {}, []
    for k in cur.get("order") or []:
        cells = crows.get(k) or []
        if k not in prows:
            new.append(k)
            continue
        old = prows[k]
        cols = []
        for i in range(1, len(cells)):
            j = pid.get(cid[i] if i < len(cid) else f"\x1f#{i}", -1)
            was = old[j] if 0 <= j < len(old) else ""
            if str(was).strip() != str(cells[i]).strip():
                cols.append(i)
        if cols:
            changed[k] = cols
    gone = [(prows.get(k) or [""])[0] for k in prev.get("order") or [] if k not in crows]
    return {"changed": changed, "new": new, "gone": gone, "count": len(changed) + len(new)}


def mark_of(h: dict):
    """한 브랜드의 기록 → 보여 줄 바뀐 곳(없으면 None). 다른 달 판끼리는 None."""
    if not isinstance(h, dict):
        return None
    prev, cur = h.get("prev"), h.get("cur")
    if not isinstance(prev, dict) or not isinstance(cur, dict):
        return None
    pa, ca = h.get("prev_at") or 0, h.get("cur_at") or 0
    if not same_month(prev, pa, cur, ca):
        return None
    d = diff(prev, cur)
    if not d["count"] and not d["gone"]:
        return None
    a = prev.get("date") or _md(pa)
    z = cur.get("date") or _md(ca)
    if a == z:                       # 제목의 기준일은 그대로인데 값이 바뀌었다 — 받은 날로
        a, z = _md(pa), _md(ca)
    d["from"], d["to"] = a, z
    return d


def track(history, blocks: list, now_ms: int):
    """새로 읽은 표 → (새 기록, {브랜드 열쇠: 바뀐 곳 또는 None}).

    기록 = {열쇠: {"cur": 판, "cur_at": ms, "prev": 판 | None, "prev_at": ms}} — 표에서 빠진 브랜드는 버린다."""
    old = history if isinstance(history, dict) else {}
    hist, marks = {}, {}
    for b in blocks or []:
        s = snap(b)
        h = old.get(b.get("key"))
        if not isinstance(h, dict) or not isinstance(h.get("cur"), dict):
            h = {"cur": s, "cur_at": int(now_ms), "prev": None, "prev_at": 0}
        elif not _same_snap(h["cur"], s):
            h = {"cur": s, "cur_at": int(now_ms), "prev": h["cur"], "prev_at": int(h.get("cur_at") or 0)}
        hist[b.get("key")] = h
        marks[b.get("key")] = mark_of(h)
    return hist, marks


def marks_from(history) -> dict:
    """저장해 둔 기록만으로(새로 읽기 전) 보여 줄 바뀐 곳."""
    return {k: mark_of(h) for k, h in (history or {}).items()} if isinstance(history, dict) else {}


def change_text(m) -> str:
    """'11/03 → 11/20 바뀐 모델 3개 · 빠진 모델: A, B'(없으면 '')."""
    if not m:
        return ""
    bits = [f"{m['from']} → {m['to']} " + (f"바뀐 모델 {m['count']}개" if m["count"] else "바뀜")]
    gone = m.get("gone") or []
    if gone:
        bits.append("빠진 모델: " + ", ".join(gone[:5]) + (f" 외 {len(gone) - 5}개" if len(gone) > 5 else ""))
    return " · ".join(bits)


MARKS_FILE = "promo_marks.json"


def load_marks(sheet_id: str, tab: str) -> dict:
    """이 PC 에 남긴 기록(그 시트·탭 것만)."""
    try:
        o = json.loads(config.data_file(MARKS_FILE).read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(o, dict) or o.get("sheet_id") != sheet_id or o.get("tab") != tab:
        return {}
    h = o.get("hist")
    return h if isinstance(h, dict) else {}


def save_marks(sheet_id: str, tab: str, hist: dict) -> None:
    try:
        config.atomic_write(config.data_file(MARKS_FILE),
                            json.dumps({"sheet_id": sheet_id, "tab": tab, "hist": hist}, ensure_ascii=False))
    except OSError:
        pass


def sheet_url(sheet_id: str, gid=None) -> str:
    u = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
    return u + (f"#gid={int(gid)}" if isinstance(gid, int) else "")
