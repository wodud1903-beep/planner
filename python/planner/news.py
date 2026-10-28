"""오늘의 뉴스 — 제미나이가 매일 아침 구글 문서에 써 두는 뉴스 요약을 받아 보여 준다.

문서는 매일 통째로 새로 쓰인다(맨 위 제목 + 표 한 장: 구분 · 뉴스 제목 및 내용 · 투자
관점 분석). 표 칸 안의 글은 **마크다운 글자 그대로** 들어 있다 — `**제목**`,
`[기사 원문 보기](주소)`, `*시각*`. 그래서 받아 온 글을 다시 읽어 굵은 제목·링크·시각을
제자리에 그려 준다(문서에 진짜 굵게·링크가 있어도 같은 모양이 되게 마크다운으로 맞춘다).

받는 길은 둘이다(부르는 쪽이 권한을 보고 고른다).
  · 드라이브 내보내기(HTML) — 이미 받아 둔 drive.readonly 권한으로. 새 로그인이 필요 없다.
  · 구글 문서 API — documents.readonly 권한으로(드라이브 권한을 안 켠 사람).

켤 때 뒤에서 받아 두고(main_window), [오늘의 뉴스] 를 누르면 받아 둔 것을 바로
보여 준 뒤 새로 받아 바꿔 끼운다 — 누를 때 기다리지 않게.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from html.parser import HTMLParser
from typing import Optional

from . import config

DOCS_URL = "https://docs.googleapis.com/v1/documents/{doc_id}"
EXPORT_URL = "https://www.googleapis.com/drive/v3/files/{doc_id}/export"
CACHE_NAME = "news_cache.json"


class NeedScope(Exception):
    """뉴스 문서를 읽을 권한이 토큰에 없다 — 한 번 더 로그인하면 풀린다."""


class NewsError(Exception):
    pass


def doc_id_from(s: str) -> str:
    """문서 주소(…/document/d/<id>/edit…) 또는 id 그대로 → id."""
    s = (s or "").strip()
    m = re.search(r"/document/d/([A-Za-z0-9_-]{20,})", s)
    if m:
        return m.group(1)
    return s if re.fullmatch(r"[A-Za-z0-9_-]{20,}", s) else ""


def doc_url(doc_id: str) -> str:
    return f"https://docs.google.com/document/d/{doc_id}/edit"


# ---------------------------------------------------------------------------
# 받기 — 결과는 '블록' 목록: ("h", 글) · ("p", 글) · ("table", [[칸 글, …], …])
#        칸·문단의 글은 마크다운 글자(굵게 **, 링크 [](), 기울임 *)로 통일한다.
# ---------------------------------------------------------------------------
def _google_error(r, what: str) -> Exception:
    try:
        err = (r.json() or {}).get("error") or {}
    except Exception:
        err = {}
    msg = str(err.get("message", "") or "")
    raw = json.dumps(err, ensure_ascii=False).lower()
    if r.status_code == 403 and ("insufficient" in raw or "scope" in raw):
        return NeedScope(msg)
    if r.status_code == 403 and ("service_disabled" in raw or "has not been used" in raw
                                 or "is disabled" in raw):
        return NewsError("구글 클라우드 프로젝트에서 'Google Docs API' 가 꺼져 있습니다.\n"
                         "콘솔 → API 및 서비스 → 라이브러리에서 Google Docs API 를 사용 설정하세요.")
    if r.status_code in (403, 404):
        return NewsError("뉴스 문서를 열 수 없습니다. 지금 로그인한 구글 계정에\n"
                         "그 문서가 있는지(또는 공유됐는지) 확인해 주세요.")
    return NewsError(f"{what} 실패 (HTTP {r.status_code}) {msg}".strip())


def fetch_docs_api(auth, doc_id: str) -> dict:
    from .google_client import _http
    r = _http().get(DOCS_URL.format(doc_id=doc_id), headers=auth._headers(), timeout=20)
    if r.status_code != 200:
        raise _google_error(r, "뉴스 문서 읽기")
    j = r.json()
    return {"title": j.get("title", ""), "blocks": blocks_from_docs(j)}


def fetch_drive_export(auth, doc_id: str) -> dict:
    from .google_client import _http
    r = _http().get(EXPORT_URL.format(doc_id=doc_id), headers=auth._headers(), timeout=20,
                    params={"mimeType": "text/html"})
    if r.status_code != 200:
        raise _google_error(r, "뉴스 문서 내려받기")
    r.encoding = "utf-8"
    return {"title": "", "blocks": blocks_from_html(r.text)}


# ---- 구글 문서 API 의 JSON → 블록 ----
def _runs_md(elements) -> str:
    out = []
    for el in elements or []:
        tr = el.get("textRun")
        if not tr:
            continue
        t = tr.get("content", "")
        st = tr.get("textStyle") or {}
        url = ((st.get("link") or {}).get("url") or "")
        core = t.strip("\n")
        if core.strip() and "**" not in core and "](" not in core:
            if url:
                core = f"[{core}]({url})"
            elif st.get("bold"):
                core = f"**{core}**"
            elif st.get("italic"):
                core = f"*{core}*"
        out.append(core + ("\n" if t.endswith("\n") else ""))
    # 칸 안 줄바꿈(Shift+Enter)은 \u000b 로 온다
    return "".join(out).replace("\u000b", "\n")


def _content_md(content) -> str:
    lines = []
    for se in content or []:
        if "paragraph" in se:
            lines.append(_runs_md(se["paragraph"].get("elements")).strip("\n"))
        elif "table" in se:            # 칸 안의 표 — 글만 이어 붙인다
            for row in se["table"].get("tableRows", []):
                for c in row.get("tableCells", []):
                    lines.append(_content_md(c.get("content")))
    return "\n".join(x for x in lines if x.strip())


def blocks_from_docs(j: dict) -> list:
    out = []
    for se in ((j.get("body") or {}).get("content") or []):
        if "paragraph" in se:
            p = se["paragraph"]
            t = _runs_md(p.get("elements")).strip()
            if not t:
                continue
            style = ((p.get("paragraphStyle") or {}).get("namedStyleType") or "")
            out.append(("h" if style.startswith(("HEADING", "TITLE")) else "p", t))
        elif "table" in se:
            rows = []
            for row in se["table"].get("tableRows", []):
                rows.append([_content_md(c.get("content")) for c in row.get("tableCells", [])])
            out.append(("table", rows))
    return out


# ---- 드라이브가 내보낸 HTML → 블록 ----
class _HtmlBlocks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self._buf = []          # 지금 문단의 글
        self._tag = "p"
        self._rows = None       # 표 안이면 [[칸, …], …]
        self._cell = None       # 칸 안이면 [문단, …]
        self._href = []         # 열린 <a> 의 주소 · 시작 위치
        self._skip = 0          # <style>·<head> 안

    def _flush(self):
        t = "".join(self._buf).strip()
        self._buf = []
        if not t:
            return
        if self._cell is not None:
            self._cell.append(t)
        else:
            self.blocks.append((self._tag, t))

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("style", "script", "title"):
            self._skip += 1
        elif tag == "table":
            self._flush()
            self._rows = []
        elif tag == "tr" and self._rows is not None:
            self._rows.append([])
        elif tag in ("td", "th") and self._rows is not None:
            self._cell = []
        elif tag in ("p", "li", "div") or re.fullmatch(r"h[1-6]", tag):
            self._flush()
            self._tag = "h" if tag.startswith("h") and tag != "hr" else "p"
        elif tag == "br":
            self._buf.append("\n")
        elif tag == "a":
            self._href.append((_real_url(a.get("href", "")), len("".join(self._buf))))

    def handle_endtag(self, tag):
        if tag in ("style", "script", "title"):
            self._skip = max(0, self._skip - 1)
        elif tag == "a" and self._href:
            url, start = self._href.pop()
            full = "".join(self._buf)
            text = full[start:]
            # 글이 주소가 아닌 진짜 링크면 마크다운 링크로(주소 글자는 이미 마크다운 안에 있다)
            if url and text.strip() and not text.strip().startswith("http"):
                self._buf = [full[:start] + f"[{text}]({url})"]
        elif tag in ("td", "th") and self._cell is not None:
            self._flush()
            if self._rows:
                self._rows[-1].append("\n".join(self._cell))
            self._cell = None
        elif tag == "table" and self._rows is not None:
            self.blocks.append(("table", [r for r in self._rows if r]))
            self._rows = None
        elif tag in ("p", "li", "div") or re.fullmatch(r"h[1-6]", tag):
            self._flush()
            self._tag = "p"

    def handle_data(self, data):
        if not self._skip:
            self._buf.append(data)


def _real_url(href: str) -> str:
    """구글이 감싼 주소(https://www.google.com/url?q=진짜&sa=…) → 진짜 주소."""
    from urllib.parse import parse_qs, urlparse
    try:
        u = urlparse(href)
        if u.netloc.endswith("google.com") and u.path == "/url":
            return (parse_qs(u.query).get("q") or [""])[0]
    except Exception:
        return ""
    return href


def blocks_from_html(text: str) -> list:
    p = _HtmlBlocks()
    p.feed(text or "")
    p._flush()
    return p.blocks


# ---------------------------------------------------------------------------
# 그리기 — 블록 → 화면용 HTML(QTextBrowser)
# ---------------------------------------------------------------------------
_TOKEN = re.compile(
    r"\*\*(?P<b>.+?)\*\*"
    r"|\[(?P<at>[^\[\]]+)\]\((?P<au>https?://[^)\s]+)\)"
    r"|(?<!\*)\*(?![\s*])(?P<i>[^*\n]+?)(?<!\s)\*(?!\*)",
    re.S)


def _unescape(s: str) -> str:
    # 마크다운의 \[ \] \~ … → 글자 그대로. ** 는 건드리지 않는다(굵게 표시다)
    return re.sub(r"\\([\[\]~()#>+\-.!_`|])", r"\1", s)


def tokens(s: str) -> list:
    """한 칸의 글 → [("b"|"i"|"t", 글) | ("a", 글, 주소)]."""
    s = _unescape(s or "")
    out, pos = [], 0
    for m in _TOKEN.finditer(s):
        if m.start() > pos:
            out.append(("t", s[pos:m.start()]))
        if m.group("b") is not None:
            out.append(("b", m.group("b")))
        elif m.group("at") is not None:
            out.append(("a", m.group("at"), m.group("au")))
        else:
            out.append(("i", m.group("i")))
        pos = m.end()
    if pos < len(s):
        out.append(("t", s[pos:]))
    return out


def inline_html(s: str, link_color: str = "", sub_color: str = "") -> str:
    """칸 글 → HTML. 굵은 제목은 새 줄에서 시작하고, 링크·시각은 한 줄로 모은다
    (문서에는 '**제목**[기사 원문 보기](주소)*시각*본문' 처럼 붙어 있다)."""
    parts, prev = [], ""
    ac = f" style='color:{link_color};'" if link_color else ""
    sc = f" style='color:{sub_color};'" if sub_color else ""

    def nl():
        if parts and not parts[-1].endswith("<br>"):
            parts.append("<br>")

    for tk in tokens(s):
        kind = tk[0]
        if kind == "b":
            nl()
            parts.append(f"<b>{html.escape(tk[1].strip())}</b>")
        elif kind == "a":
            if prev == "b":
                parts.append("<br>")
            parts.append(f"<a href='{html.escape(tk[2], quote=True)}'{ac}>"
                         f"{html.escape(tk[1].strip())}</a>")
        elif kind == "i":
            if prev == "a":
                parts.append(f"<span{sc}> · </span>")
            elif prev == "b":
                parts.append("<br>")
            parts.append(f"<span{sc}>{html.escape(tk[1].strip())}</span><br>")
        else:
            t = tk[1]
            if prev in ("b", "a") and t.strip() and not t.startswith((" ", "\n")):
                t = " " + t
            if parts and parts[-1].endswith("<br>"):
                t = t.lstrip()
            parts.append(html.escape(t).replace("\n", "<br>"))
        prev = kind
    out = "".join(parts)
    out = re.sub(r"(<br>\s*){2,}", "<br>", out)
    return re.sub(r"^(<br>)+|(<br>)+$", "", out.strip())


# 구분 칸 — 호재·악재·중립을 색 알약으로
_TONE = {"호재": "green", "악재": "red", "중립": "gray"}


def _plain(s: str) -> str:
    return re.sub(r"[*\\]", "", s or "").strip()


def news_parts(cell: str) -> dict:
    """뉴스 칸 → 제목 · 링크 · 시각 · 본문(본문 안의 굵은 글은 그대로 굵게)."""
    out = {"title": "", "link": "", "url": "", "time": "", "body": ""}
    body = []
    for tk in tokens(cell):
        k = tk[0]
        if k == "b" and not out["title"]:
            out["title"] = tk[1].strip()
        elif k == "a" and not out["url"]:
            out["link"], out["url"] = tk[1].strip(), tk[2]
        elif k == "i" and not out["time"]:
            out["time"] = tk[1].strip()
        elif k == "b":
            body.append(f"<b>{html.escape(tk[1].strip())}</b>")
        elif k == "a":
            body.append(f"<a href='{html.escape(tk[2], quote=True)}'>{html.escape(tk[1])}</a>")
        else:
            body.append(html.escape(tk[1]))
    out["body"] = "".join(body).strip()
    return out


def analysis_parts(cell: str) -> list:
    """분석 칸 → [(항목, 설명)] — '**수익성 요인:** …**리스크 요인 (있음):** …'."""
    parts, label, buf = [], "", []
    for tk in tokens(cell):
        if tk[0] == "b":
            if label or "".join(buf).strip():
                parts.append((label, "".join(buf).strip()))
            label, buf = tk[1].strip().rstrip(":：").strip(), []
        elif tk[0] == "a":
            buf.append(tk[1])
        else:
            buf.append(tk[1])
    if label or "".join(buf).strip():
        parts.append((label, "".join(buf).strip()))
    return parts


def _sentences(h: str) -> str:
    # 한 문장씩 줄을 바꾼다 — 두세 문장이 한 덩어리로 붙어 있으면 눈이 길을 잃는다
    return re.sub(r"(다\.|요\.)\s+(?=\S)", r"\1<br>", h)


def _news_cards(rows: list, c: dict) -> str:
    """구분 · 뉴스 · 분석 표 → 뉴스 한 건마다 카드 한 장."""
    txt, sub, link = c["text"], c["sub"], c["link"]
    card, box = c["card"], c["box"]
    strong, strong_bg = c["strong"], c["strong_bg"]
    out = []
    for row in rows:
        if len(row) < 2 or not "".join(row).strip():
            continue
        tone_word = _plain(row[0])
        tone = _TONE.get(tone_word)
        n = news_parts(row[1])
        if not (n["title"] or n["body"]):
            continue
        badge = (f"<span style='background-color:{strong_bg(tone)};color:{strong(tone)};"
                 f"font-weight:bold;font-size:12px;'>&nbsp;{html.escape(tone_word)}&nbsp;</span>"
                 f"&nbsp;&nbsp;" if tone else "")
        meta = []
        if n["url"]:
            meta.append(f"<a href='{html.escape(n['url'], quote=True)}' style='color:{link};'>"
                        f"{html.escape(n['link'] or '기사 원문 보기')} ↗</a>")
        if n["time"]:
            meta.append(html.escape(n["time"]))
        out.append(f"<table width='100%' cellspacing='0' cellpadding='18' border='0' bgcolor='{card}'>"
                   f"<tr><td>")
        out.append(f"<p style='margin:0 0 6px 0;'>{badge}"
                   f"<span style='font-size:17px;font-weight:bold;'>{html.escape(n['title'])}</span></p>")
        if meta:
            out.append(f"<p style='margin:0 0 12px 0;font-size:12px;color:{sub};'>"
                       + " &nbsp;·&nbsp; ".join(meta) + "</p>")
        if n["body"]:
            out.append(f"<p style='margin:0 0 14px 0;line-height:170%;font-size:14px;'>"
                       f"{_sentences(n['body'])}</p>")
        ana = analysis_parts(row[2]) if len(row) > 2 else []
        if ana:
            out.append(f"<table width='100%' cellspacing='0' cellpadding='14' border='0' bgcolor='{box}'>"
                       f"<tr><td>")
            for k, (label, text) in enumerate(ana):
                col = strong("red") if "리스크" in label else strong("blue")
                mb = "0" if k == len(ana) - 1 else "10px"
                out.append(f"<p style='margin:0 0 {mb} 0;line-height:165%;font-size:13px;color:{txt};'>"
                           + (f"<span style='font-weight:bold;color:{col};'>{html.escape(label)}</span><br>"
                              if label else "")
                           + f"{_sentences(html.escape(text))}</p>")
            out.append("</td></tr></table>")
        out.append("</td></tr></table>")
        # 카드 사이 띄우기(Qt 글 상자는 표 바깥 여백을 안 받는다)
        out.append("<p style='margin:0;font-size:6px;'>&nbsp;</p>")
    return "".join(out)


def _is_news_table(rows: list) -> bool:
    return bool(rows) and len(rows[0]) >= 2 and _plain(rows[0][0]) == "구분"


def render_html(news: dict, colors: dict) -> str:
    """colors: text·sub·line·link·head_bg + strong(색이름)·strong_bg(색이름) 함수."""
    txt, sub, line = colors["text"], colors["sub"], colors["line"]
    link, head_bg = colors["link"], colors["head_bg"]
    strong, strong_bg = colors["strong"], colors["strong_bg"]
    out = [f"<div style='font-family:Malgun Gothic;color:{txt};font-size:14px;'>"]
    for b in news.get("blocks") or []:
        kind = b[0]
        if kind == "h":
            out.append(f"<p style='font-size:20px;font-weight:bold;margin:2px 0 14px 2px;'>"
                       f"{html.escape(_plain(b[1]))}</p>")
        elif kind == "p":
            out.append(f"<p style='margin:4px 0;'>{inline_html(b[1], link, sub)}</p>")
        elif kind == "table":
            rows = b[1]
            if not rows:
                continue
            if _is_news_table(rows):
                out.append(_news_cards(rows[1:], colors))
                continue
            head = all(re.fullmatch(r"\s*\*\*.*\*\*\s*", c or "") for c in rows[0]) or \
                any(_plain(c) == "구분" for c in rows[0])
            # 줄 사이 가는 선 — Qt 글 상자는 칸 테두리를 이 모양으로만 제대로 그린다
            out.append(f"<table width='100%' cellspacing='0' cellpadding='9' border='1' "
                       f"style='border-collapse:collapse;border-style:solid;border-color:{line};'>")
            widths = ["9%", "51%", "40%"] if len(rows[0]) == 3 else [""] * len(rows[0])
            for k, row in enumerate(rows):
                # 줄마다 바탕을 번갈아 — Qt 글 상자는 칸 테두리를 잘 안 그려서 줄이 섞여 보인다
                zebra = colors.get("zebra", "")
                out.append(f"<tr bgcolor='{zebra}'>" if zebra and k % 2 == 0 and not (k == 0 and head)
                           else "<tr>")
                for j, cell in enumerate(row):
                    w = f" width='{widths[j]}'" if j < len(widths) and widths[j] else ""
                    if k == 0 and head:
                        out.append(f"<th{w} bgcolor='{head_bg}' style='color:{sub};"
                                   f"font-size:13px;'>{html.escape(_plain(cell))}</th>")
                        continue
                    tone = _TONE.get(_plain(cell))
                    if tone:
                        out.append(f"<td{w} align='center' valign='top'>"
                                   f"<span style='background-color:{strong_bg(tone)};"
                                   f"color:{strong(tone)};font-weight:bold;'>"
                                   f"&nbsp;{html.escape(_plain(cell))}&nbsp;</span></td>")
                    else:
                        out.append(f"<td{w} valign='top'>{inline_html(cell, link, sub)}</td>")
                out.append("</tr>")
            out.append("</table>")
    out.append("</div>")
    return "".join(out)


def render_text(news: dict) -> str:
    """복사용 평문(카톡에 붙여 넣기)."""
    lines = []
    for b in news.get("blocks") or []:
        if b[0] == "h":
            lines += [_plain(b[1]), ""]
        elif b[0] == "p":
            lines.append(_plain_inline(b[1]))
        elif b[0] == "table":
            rows = b[1]
            body = rows[1:] if rows and any(_plain(c) == "구분" for c in rows[0]) else rows
            for row in body:
                cells = [_plain_inline(c) for c in row]
                if not any(cells):
                    continue
                if len(cells) >= 2 and cells[0] in _TONE:
                    lines.append(f"[{cells[0]}] {cells[1]}")
                    lines += cells[2:]
                else:
                    lines += cells
                lines.append("")
    return "\n".join(lines).strip() + "\n"


def _plain_inline(s: str) -> str:
    out = []
    for tk in tokens(s):
        if tk[0] == "b":
            out.append(("\n" if out else "") + tk[1].strip())
        elif tk[0] == "a":
            out.append(f"\n{tk[2]}")
        elif tk[0] == "i":
            out.append(f" ({tk[1].strip()})\n")
        else:
            out.append(tk[1])
    t = "".join(out)
    return re.sub(r"\n\s*\n+", "\n", t).strip()


# ---------------------------------------------------------------------------
# 받아 둔 것 — 켤 때 바로 보여 주려고 디스크에도 둔다
# ---------------------------------------------------------------------------
def load_cache(doc_id: str) -> Optional[dict]:
    try:
        p = config.data_dir() / CACHE_NAME
        j = json.loads(p.read_text(encoding="utf-8"))
        if j.get("docId") != doc_id:
            return None
        j["blocks"] = [tuple(b) for b in j.get("blocks") or []]
        return j
    except Exception:
        return None


def save_cache(doc_id: str, news: dict) -> None:
    try:
        p = config.data_dir() / CACHE_NAME
        config.atomic_write(p, json.dumps(
            {"docId": doc_id, "title": news.get("title", ""), "at": news.get("at", ""),
             "blocks": [list(b) for b in news.get("blocks") or []]},
            ensure_ascii=False))
    except Exception:
        pass


def fetch(auth, doc_id: str) -> dict:
    """권한을 보고 받는 길을 고른다. 결과에 받은 시각(at)을 붙인다."""
    if not doc_id:
        raise NewsError("뉴스 문서 주소를 [설정] 에서 정해 주세요.")
    if auth.has_scope(config.SCOPE_DRIVE_READ):
        try:
            news = fetch_drive_export(auth, doc_id)
        except NeedScope:
            if not auth.has_scope(config.SCOPE_DOCS_READ):
                raise
            news = fetch_docs_api(auth, doc_id)
    elif auth.has_scope(config.SCOPE_DOCS_READ):
        news = fetch_docs_api(auth, doc_id)
    else:
        raise NeedScope("documents.readonly")
    news["at"] = datetime.now().isoformat(timespec="seconds")
    return news
