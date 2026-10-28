"""오늘의 뉴스 — 제미나이가 매일 아침 구글 문서에 쓰는 뉴스를 대시보드에서 본다.

지점장 요청: "대시보드 새로고침·주간요약 우측에 '오늘의 뉴스' 버튼. 누르면 뉴스를
업데이트. 누를 때 딜레이가 없도록 첫 로딩 때 같이 받아 와 줘."

실제 문서 모양(2026-10-28): 제목 한 줄 + 표(구분 · 뉴스 제목 및 내용 · 투자 관점 분석).
표 칸의 글은 마크다운 글자 그대로다 — **제목**[기사 원문 보기](주소)*시각*본문.
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
import os as _os
_os.chdir(_ROOT / "python")

import os
import tempfile
import threading
import time
from datetime import datetime

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from planner import config, google_client, news, news_dialog, sheets, sync, theme  # noqa: E402
from planner import startup_dialog as _sd  # noqa: E402

_sd.StartupDialog.show_for = staticmethod(lambda *a, **k: None)
FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name
          + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


DOC = "1KhvgFvtETklf2wAoJjSzCJLh3iyKCYB19LaH_j03rqI"
URL1 = "https://www.hankyung.com/article/202610289272g"
CELL1 = (r"**\[속보\] SK하이닉스, 3분기 영업익 83조 돌파…사상 최대 실적**"
         f"[기사 원문 보기]({URL1})*2026-10-28 08:30 KST*"
         "SK하이닉스가 3분기 영업이익 83조 원을 돌파하며 분기 사상 최대 실적을 달성했습니다.")
ANAL1 = ("**수익성 요인:** 압도적인 실적 서프라이즈는 주가 재평가 모멘텀을 제공합니다."
         "**리스크 요인 (있음):** 단기 실적 정점(피크아웃) 우려.")
CELL2 = (r"**반도체 실적 호조에도…기업 경기 전망 2개월 연속 '부정적'**"
         "[기사 원문 보기](https://www.yna.co.kr/view/AKR20261027167600003)*2026-10-28 06:00 KST*"
         r"반도체 수출 호조에도 10\~20% 제조업 심리가 위축됐습니다.")


def para(text, style="NORMAL_TEXT", **ts):
    return {"paragraph": {"paragraphStyle": {"namedStyleType": style},
                          "elements": [{"textRun": {"content": text + "\n", "textStyle": ts}}]}}


def cell(text):
    return {"content": [para(text)]}


DOCS_JSON = {"title": "daily_news", "body": {"content": [
    {"sectionBreak": {}},
    para("**주요 경제 및 증시 뉴스 요약**", "HEADING_1"),
    {"table": {"tableRows": [
        {"tableCells": [cell("**구분**"), cell("**뉴스 제목 및 내용**"), cell("**투자 관점 분석**")]},
        {"tableCells": [cell(" **호재**"), cell(CELL1), cell(ANAL1)]},
        {"tableCells": [cell(" **악재**"), cell(CELL2), cell("**수익성 요인:** 증시 상단 제약.")]},
    ]}},
    para(""),
]}}

print("[1] 문서 주소 → id")
ok("편집 주소에서 id", news.doc_id_from(
    f"https://docs.google.com/document/d/{DOC}/edit?usp=drive_link") == DOC)
ok("id 그대로도", news.doc_id_from(DOC) == DOC)
ok("엉뚱한 글은 빈 값", news.doc_id_from("뉴스") == "")
ok("기본 문서는 지점장님 뉴스 문서", config.DEF_NEWS_DOC == DOC)

print("[2] 구글 문서 API 의 모양 → 블록")
B = news.blocks_from_docs(DOCS_JSON)
ok("제목 · 표", [b[0] for b in B] == ["h", "table"], [b[0] for b in B])
ok("표 3줄 × 3칸", len(B[1][1]) == 3 and all(len(r) == 3 for r in B[1][1]))
ok("칸 글은 마크다운 글자 그대로", B[1][1][1][1] == CELL1)
real = {"body": {"content": [{"paragraph": {"elements": [
    {"textRun": {"content": "진짜 굵게", "textStyle": {"bold": True}}},
    {"textRun": {"content": " 원문", "textStyle": {"link": {"url": "https://a.kr/x"}}}},
    {"textRun": {"content": "\n", "textStyle": {}}}]}}]}}
ok("문서의 진짜 굵게·링크도 같은 모양(마크다운)으로 맞춘다",
   news.blocks_from_docs(real) == [("p", "**진짜 굵게**[ 원문](https://a.kr/x)")],
   news.blocks_from_docs(real))

print("[3] 칸 글 그리기 — 제목 · 링크 · 시각 · 본문")
h = news.inline_html(CELL1)
ok("제목은 굵게, 역슬래시는 지운다", h.startswith("<b>[속보] SK하이닉스, 3분기 영업익 83조 돌파…사상 최대 실적</b>"), h[:80])
ok("[기사 원문 보기] 는 진짜 링크", f"<a href='{URL1}'>기사 원문 보기</a>" in h)
ok("제목 다음 줄에 링크 · 시각", "</b><br><a " in h and "</a><span> · </span><span>2026-10-28 08:30 KST</span><br>SK하이닉스가" in h, h)
ok("마크다운 글자가 남지 않는다", "**" not in h and "](" not in h and "\\[" not in h)
a = news.inline_html(ANAL1)
ok("분석 칸 — 항목마다 새 줄", a.startswith("<b>수익성 요인:</b> 압도적인") and "<br><b>리스크 요인 (있음):</b> 단기" in a, a)
ok("\\~ 같은 이스케이프도 글자로", "10~20%" in news.inline_html(CELL2))

print("[4] 화면 HTML")
theme.set_theme("light")
html = news.render_html({"blocks": B}, news_dialog.colors())
ok("제목 줄", "주요 경제 및 증시 뉴스 요약</p>" in html and "**" not in html)
ok("붙은 3칸 표가 아니라 뉴스 한 건마다 카드 한 장(가독성)",
   html.count("cellpadding='18'") == 2 and "<th" not in html and "구분" not in html.replace("구분선", ""))
ok("카드 사이를 띄운다", html.count("font-size:6px;'>&nbsp;</p>") == 2)
ok("제목은 크게", "font-size:17px;font-weight:bold;'>[속보] SK하이닉스" in html)
ok("본문은 줄 간격 넉넉히 · 한 문장씩", "line-height:170%" in html)
P = news.analysis_parts(ANAL1)
ok("분석은 항목마다 따로(수익성 · 리스크)", [x[0] for x in P] == ["수익성 요인", "리스크 요인 (있음)"]
   and P[1][1].startswith("단기"), P)
ok("분석은 연한 상자 안에, 리스크는 빨강", "cellpadding='14'" in html
   and f"color:{theme.strong('red')};'>리스크 요인 (있음)</span><br>" in html)
NP = news.news_parts(CELL1)
ok("뉴스 칸 나누기 — 제목·링크·시각·본문", NP["title"].startswith("[속보]") and NP["url"] == URL1
   and NP["time"] == "2026-10-28 08:30 KST" and NP["body"].startswith("SK하이닉스가"), NP)
ok("다른 표는 예전처럼 표로", "<table" in news.render_html(
   {"blocks": [("table", [["가", "나"], ["1", "2"]])]}, news_dialog.colors()))
ok("호재·악재는 색 알약", "&nbsp;호재&nbsp;" in html and "&nbsp;악재&nbsp;" in html
   and theme.strong("green") in html and theme.strong("red") in html)
ok("기사 링크가 살아 있다", f"href='{URL1}'" in html)
txt = news.render_text({"blocks": B})
ok("복사 글 — [호재] 제목 · 링크 · 분석", txt.startswith("주요 경제 및 증시 뉴스 요약\n\n[호재] [속보] SK하이닉스")
   and URL1 in txt and "리스크 요인 (있음):" in txt and "**" not in txt, txt[:160])

print("[5] 드라이브가 내보낸 HTML → 같은 블록")
EXPORT = f"""<html><head><style>.c1{{font-weight:700}}</style></head><body>
<h1 class="c3"><span>**주요 경제 및 증시 뉴스 요약**</span></h1>
<table><tr><td><p><span>**구분**</span></p></td><td><p><span>**뉴스 제목 및 내용**</span></p></td>
<td><p><span>**투자 관점 분석**</span></p></td></tr>
<tr><td><p><span> **호재**</span></p></td>
<td><p><span>**\\[속보\\] SK하이닉스, 3분기 영업익 83조 돌파…사상 최대 실적**[기사 원문 보기](</span><span><a href="https://www.google.com/url?q={URL1}&amp;sa=D&amp;ust=1">{URL1}</a></span><span>)*2026-10-28 08:30 KST*SK하이닉스가 3분기 영업이익 83조 원을 돌파하며 분기 사상 최대 실적을 달성했습니다.</span></p></td>
<td><p><span>{ANAL1}</span></p></td></tr></table><p></p></body></html>"""
BH = news.blocks_from_html(EXPORT)
ok("제목 · 표", [b[0] for b in BH] == ["h", "table"], BH[:1])
ok("내보낸 HTML 의 칸 글이 문서 글과 같다", BH[1][1][1][1] == CELL1, BH[1][1][1][1][:90])
ok("style 안의 글은 안 섞인다", "font-weight" not in str(BH))
ok("진짜 링크(주소가 아닌 글)는 마크다운 링크로",
   news.blocks_from_html('<p><a href="https://www.google.com/url?q=https://x.kr/a&amp;sa=D">원문</a></p>')
   == [("p", "[원문](https://x.kr/a)")])

print("[6] 받는 길 — 권한을 보고 고른다")


class FakeAuth:
    def __init__(self, scopes):
        self.scopes = scopes

    def has_scope(self, s):
        return s in self.scopes


calls = []
_de, _da = news.fetch_drive_export, news.fetch_docs_api
news.fetch_drive_export = lambda a, d: calls.append("drive") or {"blocks": BH}
news.fetch_docs_api = lambda a, d: calls.append("docs") or {"blocks": B}
n = news.fetch(FakeAuth([config.SCOPE_DRIVE_READ, config.SCOPE_DOCS_READ]), DOC)
ok("드라이브 읽기 권한이 있으면 그걸로(새 로그인 없이)", calls == ["drive"] and n.get("at"), calls)
calls.clear()
news.fetch(FakeAuth([config.SCOPE_DOCS_READ]), DOC)
ok("없으면 문서 읽기 권한으로", calls == ["docs"], calls)
try:
    news.fetch(FakeAuth(["openid"]), DOC)
    ok("둘 다 없으면 '다시 로그인' (NeedScope)", False)
except news.NeedScope:
    ok("둘 다 없으면 '다시 로그인' (NeedScope)", True)
news.fetch_drive_export, news.fetch_docs_api = _de, _da
ok("문서 읽기는 기본 권한에 들어 있다(새로 로그인하는 사람은 저절로)",
   config.SCOPE_DOCS_READ in config.GOOGLE_SCOPES)
ok("드라이브 읽기(제한됨)는 여전히 기본에 없다", config.SCOPE_DRIVE_READ not in config.GOOGLE_SCOPES)


class R:
    def __init__(self, code, err):
        self.status_code = code
        self._e = err

    def json(self):
        return {"error": self._e}


ok("권한 모자람(403 scope) → NeedScope", isinstance(news._google_error(
    R(403, {"status": "PERMISSION_DENIED", "details": [{"reason": "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}]}), "x"),
    news.NeedScope))
ok("Docs API 가 꺼진 프로젝트면 켜라고 알려 준다", "Google Docs API" in str(news._google_error(
    R(403, {"message": "Google Docs API has not been used in project 5937 before or it is disabled.",
            "details": [{"reason": "SERVICE_DISABLED"}]}), "x")))
ok("남의 문서(404) → 계정 확인 안내", "계정" in str(news._google_error(R(404, {"message": "nf"}), "x")))

print("[7] 받아 둔 것 — 켤 때 바로 보이게 디스크에")
config.set_account("tester@example.com")
news.save_cache(DOC, {"blocks": B, "at": "2026-10-28T08:52:00"})
c = news.load_cache(DOC)
ok("다시 읽으면 그대로", c and c["blocks"] == B and c["at"] == "2026-10-28T08:52:00")
ok("다른 문서로 바꾸면 옛것을 안 보인다", news.load_cache("x" * 30) is None)
ok("받은 시각 말", news_dialog.when_text("2026-10-28T08:52:00", datetime(2026, 10, 28, 9, 0)) == "오늘 08:52 받음"
   and news_dialog.when_text("2026-10-27T08:52:00", datetime(2026, 10, 28, 9, 0)).startswith("어제"))

print("[8] 대시보드 단추 · 켤 때 미리 받기 · 누르면 바로")
app = QApplication.instance() or QApplication([])
theme.apply_to_app(app)
google_client.GoogleAuth.is_connected = lambda self: False
sync.sync_now = lambda *a, **k: (False, "")
sheets.read_rows = lambda *a, **k: (1, [], [])
from planner.main_window import MainWindow  # noqa: E402

w = MainWindow()
w.resize(1600, 900)
w.show()
for _ in range(10):
    app.processEvents()
xs = [b.mapTo(w, b.rect().topLeft()) for b in (w.btn_fetch, w.btn_weekly, w.btn_news)]
order = [b.text() for _, b in sorted(zip([p.x() for p in xs], (w.btn_fetch, w.btn_weekly, w.btn_news)),
                                     key=lambda t: t[0])]
same_row = abs(xs[0].y() - xs[2].y()) < 6 and w.btn_news.isVisible()
ok("[새로고침] [주간 요약] 오른쪽에 [오늘의 뉴스]",
   order == ["새로고침", "주간 요약", "오늘의 뉴스"] and same_row, order)

google_client.GoogleAuth.is_connected = lambda self: True
got = threading.Event()
slow = {"n": 0}


def fake_fetch(auth, doc_id):
    slow["n"] += 1
    time.sleep(0.3)                      # 통신하는 척
    got.set()
    return {"blocks": B, "at": datetime.now().isoformat(timespec="seconds")}


news.fetch = fake_fetch
w.settings.news_doc = f"https://docs.google.com/document/d/{DOC}/edit"
w._on_fetch_done()                       # 켤 때의 첫 새로고침이 끝난 순간
ok("새로고침이 끝나면 뉴스도 뒤에서 받는다", got.wait(3) and slow["n"] == 1)
for _ in range(30):
    app.processEvents()
    time.sleep(0.02)
w._on_fetch_done()
ok("저절로는 10분에 한 번까지만", slow["n"] == 1, slow["n"])

t0 = time.monotonic()
w.show_news()
dt = time.monotonic() - t0
dlg = w._news_dlg
ok("누르면 기다리지 않고 바로 뜬다", dlg.isVisible() and dt < 0.25, f"{dt * 1000:.0f}ms")
ok("받아 둔 뉴스가 곧장 보인다", "SK하이닉스" in dlg.view.toPlainText())
ok("띄운 뒤 새로 받는다(늘)", got.wait(3))
for _ in range(40):
    app.processEvents()
    time.sleep(0.02)
ok("새로 받은 것으로 바꾸고 시각을 적는다", slow["n"] == 2 and "받음" in dlg.lbl_state.text(), dlg.lbl_state.text())
ok("창을 띄운 채로 다른 일을 할 수 있다(모달 아님)", not dlg.isModal())

dlg.set_error("x", need_scope=True)
ok("권한이 모자라면 [구글 다시 로그인] 단추", dlg.btn_login.isVisible())
ok("받아 둔 뉴스는 지우지 않는다", "SK하이닉스" in dlg.view.toPlainText())
dlg._copy()
ok("[복사] 는 카톡용 글", QGuiApplication.clipboard().text().startswith("주요 경제 및 증시 뉴스 요약"))
if os.environ.get("SHOT_DIR"):
    dlg.show_news({"blocks": B, "at": "2026-10-28T08:52:00"})
    dlg.grab().save(os.path.join(os.environ["SHOT_DIR"], "news.png"))
dlg.close()
w.hide()

print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
