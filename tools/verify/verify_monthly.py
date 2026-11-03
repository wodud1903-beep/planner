"""월 마감 리포트(v1.26 — monthly.py · monthly_dialog.py · sheets.write_tab).

지점장 요청 ⑨: 출고·수수료를 금융사별·차종별로 집계하고, 지난달 대비를 시트 새 탭으로.
  · 매달 1일 이후 처음 새로 읽을 때 지난달 것을 '월마감' 탭에 저절로(한 달에 한 번, 다른 PC 도)
  · 대시보드 [월 마감] — 달을 골라 [복사](카톡 보고) · [시트에 적기]
  · 같은 이름의 탭에 사람이 만든 다른 표가 있으면 덮어쓰지 않는다
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
import os as _os
_os.chdir(_ROOT / "python")

import os
import tempfile
import time
from datetime import date

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from planner import config, google_client, monthly, sheets, sync, theme  # noqa: E402
from planner import startup_dialog as _sd  # noqa: E402

_sd.StartupDialog.show_for = staticmethod(lambda *a, **k: None)
QMessageBox.information = staticmethod(lambda *a, **k: None)
FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name
          + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


def row(n, name, fin, model, dd, cd="", total="", status="출고"):
    cr = sheets.CustomerRow(row=n, seq=str(n), total=total, center="", accident="")
    cr.values.update({"customer": name, "finance": fin, "model": model, "status": status,
                      "deliver_date": dd, "contract_date": cd})
    return cr


ROWS = [
    row(2, "김상현", "KB캐피탈", "쏘나타", "2026. 10. 3", "2026. 9. 1", "500,000"),
    row(3, "박영희", "KB캐피탈", "그랜저", "2026. 10. 15", "2026. 10. 2", "700,000"),
    row(4, "이수진", "현대캐피탈", "쏘나타", "2026. 10. 30", "2026. 10. 9", "300,000"),
    row(5, "취소손님", "IM캐피탈", "G70", "2026. 10. 20", "2026. 10. 1", "900,000", "취소"),
    row(6, "구월출고", "현대캐피탈", "아반떼", "2026. 9. 12", "2026. 8. 30", "400,000"),
    row(7, "십일월", "KB캐피탈", "K5", "2026. 11. 2", "2026. 10. 25", "250,000"),
]

print("[1] 한 달 숫자")
s = monthly.stats(ROWS, 2026, 10)
ok("출고 = 출고일이 그달 · 취소 제외", s["count"] == 3, s["count"])
ok("수수료 = H열 합계의 합", s["fee"] == 1_500_000, s["fee"])
ok("신규 계약 = 계약일이 그달(취소 제외)", s["contracts"] == 3, s["contracts"])
ok("금융사별(많은 순) · 대수·수수료", s["by_fin"] == [("KB캐피탈", 2, 1_200_000), ("현대캐피탈", 1, 300_000)],
   s["by_fin"])
ok("차종별", s["by_model"] == [("쏘나타", 2), ("그랜저", 1)], s["by_model"])
rep = monthly.report(ROWS, 2026, 10)
ok("지난달(9월)과 견준다", rep["prev"]["count"] == 1 and rep["prev"]["fee"] == 400_000)
ok("최근 12개월 추이(이번 달부터)", rep["hist"][0] == ("2026-10", 3, 1_500_000, 3) and len(rep["hist"]) == 12,
   rep["hist"][:2])
ok("1월의 지난달은 작년 12월", monthly.prev_month(2027, 1) == (2026, 12))

print("[2] 카톡 보고 글")
txt = monthly.render_text(rep)
lines = txt.splitlines()
ok("제목", lines[0] == "2026년 10월 마감")
ok("출고 · 지난달 대비", "· 출고 3대 (지난달 1대 · +2, +200%)" in lines, txt)
ok("수수료 · 지난달 대비", "· 수수료 1,500,000원 (지난달 400,000원 · +1,100,000원, +275%)" in lines, txt)
ok("금융사별 비중", "· KB캐피탈 2대 1,200,000원 · 67%" in lines, txt)
ok("차종별", "쏘나타 2 · 그랜저 1" in lines, txt)

print("[3] 시트 '월마감' 탭에 적을 표")
v = monthly.sheet_values(rep, date(2026, 11, 1), "고객관리")
ok("A1 제목(덮어쓰기 지킴 말 '마감 리포트' 가 들어 있다)", v[0][0] == "2026년 10월 마감 리포트")
ok("요약 — 숫자는 숫자로", ["출고(대)", 3, 1, 2] in v and ["수수료(원)", 1_500_000, 400_000, 1_100_000] in v)
ok("금융사별 표", ["KB캐피탈", 2, 1_200_000, 67] in v)
ok("출고 목록", ["2026-10-15", "박영희", "KB캐피탈", "그랜저", 700_000] in v)
ok("최근 12개월", ["2026-10", 3, 1_500_000, 3] in v)

print("[4] 시트에 쓰기 — 없으면 만들고, 남의 표는 덮어쓰지 않는다")
CALLS = []
STATE = {"titles": ["고객관리"], "a1": ""}


class _R:
    def __init__(self, j, code=200):
        self._j, self.status_code, self.text = j, code, ""

    def json(self):
        return self._j


class _S:
    def get(self, url, **k):
        CALLS.append(("GET", url))
        if "fields" in (k.get("params") or {}):
            return _R({"sheets": [{"properties": {"title": t, "sheetId": i}}
                                  for i, t in enumerate(STATE["titles"])]})
        return _R({"values": [[STATE["a1"]]]} if STATE["a1"] else {})

    def post(self, url, **k):
        CALLS.append(("POST", url, k.get("json")))
        if "batchUpdate" in url:
            STATE["titles"].append(k["json"]["requests"][0]["addSheet"]["properties"]["title"])
        return _R({})

    def put(self, url, **k):
        CALLS.append(("PUT", url, k.get("params"), k.get("json")))
        return _R({})


sheets._http = lambda: _S()
google_client.GoogleAuth.valid_token = lambda self: "AT"
auth = google_client.GoogleAuth(config.base_dir() / "google_token.json")
sheets.write_tab(auth, "SID", monthly.TAB, v, guard="마감 리포트")
ok("탭이 없으면 만든다", any(c[0] == "POST" and "batchUpdate" in c[1] for c in CALLS))
put = [c for c in CALLS if c[0] == "PUT"][-1]
ok("값 그대로(RAW) · 표 전체", put[2] == {"valueInputOption": "RAW"} and put[3]["values"][0][0]
   == "2026년 10월 마감 리포트", put[2])
ok("다른 탭(고객관리)에는 쓰지 않는다", all("고객관리" not in c[1] for c in CALLS if c[0] in ("PUT", "POST")))
CALLS.clear()
STATE["a1"] = "2026년 9월 마감 리포트"
sheets.write_tab(auth, "SID", monthly.TAB, v, guard="마감 리포트")
ok("우리가 적은 탭이면 새로 적는다", any(c[0] == "PUT" for c in CALLS))
CALLS.clear()
STATE["a1"] = "직원별 실적표"
try:
    sheets.write_tab(auth, "SID", monthly.TAB, v, guard="마감 리포트")
    stopped = False
except google_client.GoogleError as e:
    stopped = "덮어쓰지 않았습니다" in str(e)
ok("사람이 만든 같은 이름의 탭은 덮어쓰지 않는다", stopped and not any(c[0] == "PUT" for c in CALLS))

print("[5] 일정관리기 — 매달 한 번 저절로 · [월 마감] 창")
app = QApplication.instance() or QApplication([])
theme.apply_to_app(app)
config.set_account("tester@example.com")
google_client.GoogleAuth.is_connected = lambda self: True
google_client.GoogleAuth.has_scope = lambda self, s: True
sync.sync_now = lambda *a, **k: False
sync.push = lambda *a, **k: None
sheets.read_rows = lambda *a, **k: (1, [], [])
WROTE = []
sheets.write_tab = lambda auth, sid, tab, values, guard="": WROTE.append((sid, tab, values[0][0], guard))
from planner.main_window import MainWindow  # noqa: E402

w = MainWindow()
w.settings.sheet_on, w.settings.sheet_id, w.settings.sheet_name = True, "SID", "고객관리"
w.sheet_rows = list(ROWS)
w._sheet_loaded = True
w._account_verified = False
w._maybe_auto_monthly()
ok("계정을 확인하기 전에는 쓰지 않는다", not WROTE)
w._account_verified = True
w._maybe_auto_monthly()
for _ in range(30):
    app.processEvents()
    time.sleep(0.02)
t = date.today()
py, pm = monthly.prev_month(t.year, t.month)
ok("지난달 마감을 '월마감' 탭에 적는다", len(WROTE) == 1 and WROTE[0][1] == monthly.TAB
   and WROTE[0][2] == f"{py}년 {pm}월 마감 리포트" and WROTE[0][3] == "마감 리포트", WROTE)
ok("적은 달을 남긴다(다른 PC 도 안 적게 — 설정 동기화)", w.settings.monthly_last == f"{py}-{pm:02d}")
w._maybe_auto_monthly()
for _ in range(10):
    app.processEvents()
ok("한 달에 한 번만", len(WROTE) == 1)
w.settings.monthly_on = False
w.settings.monthly_last = ""
w._maybe_auto_monthly()
ok("끄면 안 적는다", len(WROTE) == 1)
from planner.monthly_dialog import MonthlyDialog  # noqa: E402

d = MonthlyDialog(ROWS, date(2026, 11, 3), on_write=lambda y, m: WROTE.append(("dlg", y, m)))
ok("월초에 열면 지난달부터", d.month() == (2026, 10))
d._copy()
ok("[복사] 는 카톡 보고 글", QGuiApplication.clipboard().text() == monthly.render_text(monthly.report(ROWS, 2026, 10)))
d.btn_write.click()
ok("[시트에 적기]", WROTE[-1] == ("dlg", 2026, 10))
d.cmb.setCurrentIndex(0)
ok("이번 달도 볼 수 있다(진행 중)", d.month() == (2026, 11) and "2026년 11월 마감" in d.txt.toPlainText())
d.close()
w.hide()

print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
