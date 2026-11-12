"""일반(관리자가 아닌) 계정으로 일정관리기를 **실제로 켜 본다**(v1.32 — 지점장 선택 B6).

가짜 구글(fake_google.py)을 붙여 메인 창을 띄우고, 새 직원 PC 에서 흔한 흐름을 그대로 밟는다.
새 기능을 만들 때마다 이 검사가 일반 계정으로도 예외·이상한 요청·회사 시트 쓰기가 없는지 본다.
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
import os as _os
_os.chdir(_ROOT / "python")

import json
import os
import tempfile
import threading
import time
import traceback

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import fake_google as fg  # noqa: E402

EMAIL = "staff@example.com"
W = fg.World(EMAIL)
ERRS, BOXES, FAIL = [], [], []
_sys.excepthook = lambda t, v, tb: ERRS.append("".join(traceback.format_exception(t, v, tb)))
threading.excepthook = lambda a: ERRS.append("".join(
    traceback.format_exception(a.exc_type, a.exc_value, a.exc_traceback)))


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


from planner import config, google_client, kb, kb_files, kb_tab, net, otp, otp_popup, settings_dialog, sheets, theme  # noqa: E402
from planner import startup_dialog as _sd  # noqa: E402

_sd.StartupDialog.show_for = staticmethod(lambda *a, **k: None)
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, _k=_n, **k: BOXES.append((_k, a[2] if len(a) > 2 else ""))))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
for mod in (net, google_client, sheets, kb_files):
    for attr in ("http", "_http"):
        if hasattr(mod, attr):
            setattr(mod, attr, lambda: fg.Session(W))
google_client.GoogleAuth.valid_token = lambda self: "AT"
otp.claim = lambda item, now=None: True          # 임시 폴더 표식은 다른 검사와 섞이지 않게

KBROWS = [["분류", "금융사", "제목", "태그", "본문", "체크리스트"],
          ["심사서류", "", "개인 심사서류", "", "1. 신분증\n팩스 {내 팩스|0504-214-5287}", "신분증"],
          ["캐피탈", "메리츠캐피탈", "메리츠캐피탈", "", "담당 팩스 0504-214-5287", ""]]
W.sheets[config.RATES_SHEET_ID] = {"업무자료": KBROWS, "수당율": [["차종", "수당율"], ["쏘렌토", "1.2"]]}
TODAY = time.strftime("%Y. %-m. %-d")
OTPROWS = [["일시", "", "인증번호", "맨위가 최신입니다"], [TODAY, "수신문자", "로그인 인증번호 (111111)"]]
W.sheets[config.OTP_DEF_SHEET_ID] = {"시트1": OTPROWS}
(config.base_dir() / "google_token.json").write_text(
    json.dumps({"refresh_token": "RT", "scopes": list(config.SCOPE_LABELS) + [config.SCOPE_DRIVE_READ]}),
    encoding="utf-8")

app = QApplication.instance() or QApplication([])
theme.apply_to_app(app)


def pump(sec=0.6):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def wait(cond, sec=12.0):
    end = time.time() + sec
    while time.time() < end and not cond():
        pump(0.1)
    return cond()


from planner.main_window import MainWindow  # noqa: E402

print("[1] 켜기 — 새 직원 PC(일반 계정)")
otp.POLL_MS = 400
w = MainWindow()
w.show()
ok("계정을 확인하고 회사 자료를 받는다", wait(lambda: w._account_verified and len(kb.load_shared()) == 2),
   (w.lbl_account.text(), len(kb.load_shared())))
pump(1.5)
ok("예외가 없다", ERRS == [], ERRS[:1])
ok("모르는 주소로 나가지 않는다", fg.UNKNOWN == [], fg.UNKNOWN[:3])
ok("회사 시트(수당연동용 · 인증문자)에 쓰지 않는다", not any(k == "sheet" for k, _t, _p in W.writes),
   [(k, t) for k, t, _p in W.writes])
ok("내 계정 앱 공간에만 쓴다", {t for k, t, _p in W.writes if k == "appdata"} <= {
    "planner_sync.json", "account_settings.json", "kb_edits.json"})
ok("상태 줄 — 권한이 다 있으면 평소대로", w.lbl_status.text().startswith("구글: 연결됨  ("), w.lbl_status.text())
ok("관리자 전용: 회사 공통 묶음이 없다 · 수당율 단추가 꺼져 있다",
   not config.is_kb_admin(EMAIL) and not config.is_rates_admin(EMAIL))
ok("이미 로그인된 PC 는 '처음 설정' 을 띄우지 않는다", getattr(w, "_status_dlg", None) is None)

print("[2] 인증번호 — 새 문자가 오면 띄우고 복사 · 직원 PC 는 시트를 지우지 않는다")
OTPROWS.insert(1, [TODAY, "수신문자", "[KB캐피탈] 본인확인 인증번호[989365]를 화면에 입력해주세요"])
ok("팝업이 뜬다", wait(lambda: [p.code for p in otp_popup._open] == ["989365"]), [p.code for p in otp_popup._open])
ok("클립보드에 복사", QApplication.clipboard().text() == "989365")
ok("일반 계정은 지난 문자를 지우지 않는다(관리자 PC 만)", not getattr(w, "_otp_cleaning", False)
   and not any(":batchUpdate" in t for k, t, _p in W.writes if k == "sheet"))
for p in list(otp_popup._open):
    p.close()

print("[3] 자료검색 — 내 정보 자리 · 내 계정에서만 고치기")
allv = {x["title"]: x for x in kb.load_all()}
ok("내 정보를 안 적었으면 회사가 적어 둔 기본값", "팩스 0504-214-5287" in allv["개인 심사서류"]["body"])
kb.save_me({"fax": "0504-777-1234"})
ok("적으면 그 자리에 내 것", "팩스 0504-777-1234" in {x["title"]: x for x in kb.load_all()}["개인 심사서류"]["body"])


def script_edit(d):
    d.cmb_src.setCurrentIndex(d.cmb_src.findData(kb.SRC_LOCAL))
    d.lst.setCurrentRow(1)
    d.txt_body.setPlainText("담당 팩스 0504-999-0000")
    d._ok()
    return d.result()


kb_tab.KbEditDialog.exec = lambda self: script_edit(self)
w.tab_kb._edit()
ok("저장하면 그 자리에서 내 계정(kb_edits.json)에 — 내 정보도 함께",
   wait(lambda: "kb_edits.json" in W.appdata and "0504-999-0000" in W.appdata["kb_edits.json"]["content"]
        and '"me"' in W.appdata["kb_edits.json"]["content"]))
ok("자료검색 위에 알린다", wait(lambda: "내 계정에 저장했습니다" in w.tab_kb.lbl_hint.text()), w.tab_kb.lbl_hint.text())
ok("회사 시트에는 쓰지 않는다", not any(config.RATES_SHEET_ID in t for k, t, _p in W.writes if k == "sheet"))

print("[4] 설정 — 시트·서류 폴더를 넣으면 내 계정으로 · '보기' 만 되는 시트")
W.sheets["STAFFSHEET"] = {"미출고차량": [["순번", "고객명 / 사업자"], ["1", "홍길동"]]}
W.can_edit["STAFFSHEET"] = False
W.readonly_sheets.add("STAFFSHEET")      # 진짜 구글처럼 — 써 보면 403


def script_settings(d):
    d.chk_sheet.setChecked(True)
    d.ed_sheet_id.setText("https://docs.google.com/spreadsheets/d/STAFFSHEET/edit")
    d._on_ok()
    return d.result()


settings_dialog.SettingsDialog.exec = lambda self: script_settings(self)
w.on_settings_click()
ok("계정 설정 파일에 시트가 올라간다", wait(lambda: "STAFFSHEET" in W.appdata.get("account_settings.json", {}).get("content", "")))
ok("고객을 읽는다", wait(lambda: len(w.sheet_rows) == 1), len(w.sheet_rows))
ok("'보기' 로만 공유받은 시트 — 추가·삭제 단추가 꺼진다", wait(lambda: w._sheet_can_edit is False)
   and all(not b.isEnabled() for b in w._cust_write_btns) and "보기" in w._cust_write_btns[0].toolTip())
BOXES.clear()
w.on_customer_add()
ok("눌러도 까닭을 알리고 쓰지 않는다", BOXES and "'보기' 만" in BOXES[-1][1]
   and not any("STAFFSHEET" in t for k, t, _p in W.writes if k == "sheet"),
   (BOXES[-1:], [t for k, t, _p in W.writes if k == "sheet"]))
ok("보기 전용 시트는 백업하지 않는다(남의 시트를 직원 드라이브에 복사하지 않는다)", W.created == [])

print("[5] 연결 상태 점검 — 한 화면에 ✔/✖")
W.deny_sheets.add(config.PROMO_DEF_SHEET_ID)          # 직원 계정 — 프로모션 시트를 아직 공유받지 못했다(v1.34)
d = w.open_status()
ok("점검이 끝난다", wait(lambda: not d._running and len(d.results) == 9), len(d.results))
ok("공유받지 못한 프로모션 시트는 ✖ + '뷰어' 공유 안내", d.results["promo"][0] == "bad"
   and "뷰어" in d.results["promo"][1], d.results["promo"])
ok("로그인 · 권한 · 동기화 · 회사 자료 · 인증번호는 ✔", all(d.results[k][0] == "ok" for k in ("login", "scopes", "sync", "kb", "otp")),
   {k: v[0] for k, v in d.results.items()})
ok("보기 전용 시트는 ⚠ 로 알린다", d.results["sheet"][0] == "warn" and "보기" in d.results["sheet"][1], d.results["sheet"])
txt = d.copy_report()
ok("[점검 결과·오류 기록 복사] — 판·계정·결과가 글로", config.APP_VERSION in txt and EMAIL in txt and "구글 로그인" in txt
   and QApplication.clipboard().text() == txt)
ok("토큰은 넣지 않는다", "RT" not in txt.split() and "refresh_token" not in txt and "AT" not in txt.split())
d.close()
pump(0.5)
ok("끝까지 예외가 없다", ERRS == [], ERRS[:1])
ok("끝까지 모르는 주소로 나가지 않는다", fg.UNKNOWN == [], fg.UNKNOWN[:3])

print()
print("실패:", FAIL if FAIL else "없음")
os._exit(1 if FAIL else 0)
