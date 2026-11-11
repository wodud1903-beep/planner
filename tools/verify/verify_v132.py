"""v1.32 — 내 정보 자리 · 인증번호 한 번만/지난 문자 지우기 · 시트 백업 · 지점 캘린더 · 설정 탭 · 업데이트 우회 길.

앞쪽은 조각별(순수 함수 + 가짜 구글), 뒤쪽은 **관리자 계정으로 메인 창을 실제로 띄워** 이어지는지 본다.
(일반 계정으로 띄우는 것은 verify_boot_regular.py)
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
import os as _os
_os.chdir(_ROOT / "python")

import base64
import json
import os
import tempfile
import threading
import time
import traceback
from datetime import date, datetime, timedelta

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
tempfile.tempdir = tempfile.mkdtemp()            # 인증번호 표식(jy_otp_claims)이 다른 검사와 섞이지 않게

from PySide6.QtWidgets import QApplication, QMessageBox, QTabWidget  # noqa: E402

import fake_google as fg  # noqa: E402

FAIL, ERRS, BOXES = [], [], []
_ORIG_HOOK = _sys.excepthook


def _hook(t, v, tb):
    ERRS.append("".join(traceback.format_exception(t, v, tb)))
    _ORIG_HOOK(t, v, tb)             # 검사 글 자체가 죽은 것도 화면에 보이게


_sys.excepthook = _hook
threading.excepthook = lambda a: ERRS.append("".join(
    traceback.format_exception(a.exc_type, a.exc_value, a.exc_traceback)))


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


from planner import (config, google_client, kb, kb_edits, kb_files, models, net, otp, settings_dialog,  # noqa: E402
                     sheet_backup, sheets, theme, updater)
from planner import startup_dialog as _sd  # noqa: E402

ADMIN = config.RATES_ADMINS[0]
W = fg.World(ADMIN)
_sd.StartupDialog.show_for = staticmethod(lambda *a, **k: None)
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, _k=_n, **k: BOXES.append((_k, a[2] if len(a) > 2 else ""))))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
for mod in (net, google_client, sheets, kb_files):
    for attr in ("http", "_http"):
        if hasattr(mod, attr):
            setattr(mod, attr, lambda: fg.Session(W))
google_client.GoogleAuth.valid_token = lambda self: "AT"

app = QApplication.instance() or QApplication([])
theme.apply_to_app(app)


def pump(sec=0.3):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def wait(cond, sec=8.0):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.03)
    return bool(cond())


class Auth:
    scopes = list(config.SCOPE_LABELS)

    def valid_token(self):
        return "AT"

    def is_connected(self):
        return True


AUTH = Auth()
TODAY = date(2026, 11, 10)

# ------------------------------------------------------------------ [1]
print("[1] 내 정보 자리 — {내 팩스|기본값}")
ME = {"fax": "0504-111-2222", "name": "홍길동", "phone": "010-1234-5678", "email": ""}
ok("적어 둔 것은 그 자리에", kb.fill_me("팩스 {내 팩스} / 담당 {내 이름} {내 연락처}", ME)
   == "팩스 0504-111-2222 / 담당 홍길동 010-1234-5678")
ok("기본값이 있어도 내 것이 먼저", kb.fill_me("팩스 {내 팩스|0504-214-5287}", ME) == "팩스 0504-111-2222")
ok("안 적었으면 회사가 적어 둔 기본값", kb.fill_me("팩스 {내 팩스|0504-214-5287}", {}) == "팩스 0504-214-5287")
ok("기본값도 없으면 빈칸이 아니라 '미입력' 표시", kb.fill_me("메일 {내 이메일}", ME) == "메일 〔내 이메일 미입력〕")
ok("모르는 자리·보통 중괄호는 그대로", kb.fill_me("{내 주소} {고객명} {}", ME) == "{내 주소} {고객명} {}")
ok("자리가 없는 글은 손대지 않는다", kb.fill_me("1. 신분증\n2. 등본", ME) == "1. 신분증\n2. 등본")
ok("여러 줄 · 같은 자리 여러 번", kb.fill_me("{내 팩스}\n{내 팩스|x}", ME) == "0504-111-2222\n0504-111-2222")
saved = kb.save_me({"fax": " 0504-111-2222 ", "name": "홍길동", "junk": "x"})
ok("저장 — 빈칸을 다듬고 모르는 칸은 버린다 · 고친 시각을 적는다",
   saved["fax"] == "0504-111-2222" and "junk" not in saved and saved["at"].endswith("Z") and kb.load_me() == saved)
ok("load_all 이 본문에 내 정보를 채운다(화면·복사용)",
   "fill_me" in (_ROOT / "python/planner/kb.py").read_text(encoding="utf-8").split("def load_all")[1].split("\ndef ")[0])

print("[2] 내 정보 — 계정으로 맞추기(나중에 고친 쪽)")
L = dict(ME, at="2026-11-10T01:00:00Z")
me, push, pull = kb_edits.merge_me(L, None, "2026-11-10T02:00:00Z")
ok("드라이브에 없고 이 PC 에 있으면 올린다(옛 판이 빼먹었어도 다시)", push and not pull and me["fax"] == ME["fax"])
me, push, pull = kb_edits.merge_me({}, None, "now")
ok("둘 다 없으면 아무것도 안 한다", not push and not pull)
R = {"fax": "0504-999-0000", "name": "", "phone": "", "email": "", "at": "2026-11-10T03:00:00Z"}
me, push, pull = kb_edits.merge_me(L, R, "now")
ok("드라이브가 나중이면 받는다", pull and not push and me["fax"] == "0504-999-0000")
me, push, pull = kb_edits.merge_me(dict(L, at="2026-11-10T04:00:00Z"), R, "now")
ok("이 PC 가 나중이면 올린다", push and not pull and me["fax"] == ME["fax"])
me, push, pull = kb_edits.merge_me(L, dict(L, at="2026-01-01T00:00:00Z"), "now")
ok("값이 같으면 시각만 달라도 가만히", not push and not pull)

# ------------------------------------------------------------------ [3]
print("[3] 인증번호 — 한 PC 에서 한 번만(일정관리기 + 업무자료검색)")
it = {"code": "123456", "date": "2026. 11. 10", "body": "인증번호 [123456]"}
ok("처음 본 쪽은 띄운다", otp.claim(it) is True)
ok("다른 프로그램이 방금 띄웠으면 안 띄운다", otp.claim(it) is False)
ok("다른 번호는 띄운다", otp.claim(dict(it, code="654321", body="인증번호 [654321]")) is True)
ok("2분이 지나면 같은 번호라도 다시 띄운다(같은 번호가 또 온 것)", otp.claim(it, now=time.time() + otp.CLAIM_SEC + 5) is True)
ok("메인 창은 claim 을 거쳐 띄운다",
   "otp.claim(" in (_ROOT / "python/planner/main_window.py").read_text(encoding="utf-8"))

print("[4] 지난 문자 지우기 — 오늘·어제만 남긴다(지점장: 2일만 지나도)")
col = lambda *days: [["일시"]] + [[d] for d in days]  # noqa: E731
ok("KEEP_DAYS = 2", otp.KEEP_DAYS == 2)
ok("오늘·어제뿐이면 지울 것이 없다", otp.old_tail(col("2026. 11. 10", "2026. 11. 9"), TODAY) is None)
ok("그제부터 지운다", otp.old_tail(col("2026. 11. 10", "2026. 11. 9", "2026. 11. 8", "2026. 11. 1"), TODAY) == (3, 5))
ok("전부 옛것이어도 머리글(1행)은 남긴다", otp.old_tail(col("2026. 10. 1", "2026. 9. 1"), TODAY) == (1, 3))
ok("날짜를 못 읽는 줄을 만나면 거기서 멈춘다(그 위는 안 지운다)",
   otp.old_tail(col("2026. 11. 10", "2026. 10. 1", "메모", "2026. 9. 1"), TODAY) == (4, 5))
ok("맨 아래 빈 줄은 옛 줄과 함께 지운다", otp.old_tail(col("2026. 11. 10", "2026. 10. 1", "", ""), TODAY) == (2, 5))
ok("빈 줄만 있으면 지우지 않는다", otp.old_tail(col("2026. 11. 10", "", ""), TODAY) is None)
ok("머리글뿐 · 빈 시트", otp.old_tail([["일시"]], TODAY) is None and otp.old_tail([], TODAY) is None)

otp._http = lambda: fg.Session(W)
W.sheets["OTPX"] = {"시트1": [["일시", "", "인증번호", "맨위가 최신입니다"],
                             ["2026. 11. 10", "수신문자", "인증번호 111111"],
                             ["2026. 11. 9", "수신문자", "인증번호 222222"],
                             ["2026. 11. 8", "수신문자", "인증번호 333333"],
                             ["2026. 10. 30", "수신문자", "인증번호 444444"]]}
n = otp.clean_old(AUTH, "OTPX", "시트1", TODAY)
ok("시트에서 지난 두 줄을 지운다", n == 2 and len(W.sheets["OTPX"]["시트1"]) == 3
   and W.sheets["OTPX"]["시트1"][-1][0] == "2026. 11. 9", (n, W.sheets["OTPX"]["시트1"]))
ok("다시 하면 지울 것이 없다(쓰지 않는다)", otp.clean_old(AUTH, "OTPX", "시트1", TODAY) == 0)
ok("탭 이름을 안 적으면 첫 탭", otp.clean_old(AUTH, "OTPX", "", TODAY + timedelta(days=5)) == 2)

# ------------------------------------------------------------------ [5]
print("[5] 고객관리 시트 자동 백업 — 주 1회 · 최근 4개")
sheet_backup._http = lambda: fg.Session(W)
S = models.AppSettings()
S.sheet_id, S.sheet_name = "CUST", "미출고차량"
ok("처음엔 백업할 때다", sheet_backup.due(S, TODAY))
S.sheet_backups = [{"id": "a", "at": "2026-11-05", "src": "CUST"}]
ok("7일이 안 지났으면 아니다", not sheet_backup.due(S, TODAY))
ok("7일째부터", sheet_backup.due(S, date(2026, 11, 12)))
S.sheet_backups = [{"id": "a", "at": "2026-11-09", "src": "OTHER"}]
ok("다른 시트의 사본은 세지 않는다(시트를 바꾸면 바로 한 번)", sheet_backup.due(S, TODAY))
S.sheet_backup = False
ok("끄면 안 한다", not sheet_backup.due(S, TODAY))
S.sheet_backup, S.sheet_id = True, ""
ok("시트를 안 정했으면 안 한다", not sheet_backup.due(S, TODAY))

W.sheets["CUST"] = {"미출고차량": [["순번", "고객명"], ["1", "홍길동"], ["2", "김철수"]], "월마감": [["x"]]}
rec = sheet_backup.run(AUTH, "CUST", "미출고차량", TODAY)
new = W.sheets.get(rec["id"], {})
ok("새 스프레드시트를 만들어 고객관리 탭만 복사한다", list(new) == ["미출고차량"] and new["미출고차량"] == W.sheets["CUST"]["미출고차량"],
   list(new))
ok("이름에 [백업] · 원본 제목 · 날짜", rec["name"].startswith(sheet_backup.PREFIX) and rec["name"].endswith("2026-11-10")
   and rec["src"] == "CUST" and rec["at"] == "2026-11-10", rec)
ok("원본 시트는 건드리지 않는다(복사 요청만)", [t for k, t, _p in W.writes if k == "sheet" and t.startswith("CUST")]
   == [f"CUST/sheets/{W.gids['CUST'][0][0]}:copyTo"], [t for k, t, _p in W.writes if k == "sheet" and t.startswith("CUST")])
try:
    sheet_backup.run(AUTH, "CUST", "없는탭", TODAY)
    ok("탭이 없으면 까닭을 말한다", False)
except sheets.GoogleError as e:
    ok("탭이 없으면 까닭을 말한다(빈 사본을 남기지 않는다)", "없는탭" in str(e) and len(W.created) == 1, str(e))
lst = [{"id": f"b{i}", "at": f"2026-10-{i:02d}", "src": "CUST"} for i in range(1, 7)] + [{"id": "o1", "at": "2026-01-01", "src": "OTHER"}]
gone_ids = []
kb_files.trash = lambda auth, ids: gone_ids.extend(ids)
kept, gone = sheet_backup.prune(AUTH, lst)
ok("시트마다 최근 4개만 남기고 옛것은 휴지통으로", gone == ["b1", "b2"] and gone_ids == ["b1", "b2"]
   and [b["id"] for b in kept] == ["o1", "b3", "b4", "b5", "b6"], (gone, [b["id"] for b in kept]))

# ------------------------------------------------------------------ [6]
print("[6] 지점 공유 캘린더")
P = settings_dialog.parse_calendar_id
BR = "abc123@group.calendar.google.com"
ok("ID 그대로", P(" " + BR + " ") == BR)
ok("embed 주소(src=)", P("https://calendar.google.com/calendar/embed?src=abc123%40group.calendar.google.com&ctz=Asia%2FSeoul") == BR)
cid = base64.urlsafe_b64encode(BR.encode()).decode().rstrip("=")
ok("공유 주소(cid= 암호처럼 보이는 것)", P("https://calendar.google.com/calendar/u/0?cid=" + cid) == BR)
ok("빈 값", P("") == "" and P(None) == "")

now = datetime.now().astimezone().replace(microsecond=0)
ev = lambda s, i, h=1: {"id": i, "summary": s, "start": {"dateTime": (now + timedelta(hours=h)).isoformat()}}  # noqa: E731
W.cal_list = [{"id": "me@x", "primary": True}]
W.calendars = {"me@x": [ev("내 일정", "m1")], BR: [ev("지점 회의", "b1", 2)]}
google_client.set_branch_calendar("")
evs = google_client.fetch_calendar_events(AUTH)
ok("안 정했으면 내 일정만", [e.summary for e in evs] == ["내 일정"])
google_client.set_branch_calendar(BR)
evs = google_client.fetch_calendar_events(AUTH)
ok("정하면 함께 — 앞에 [지점] · branch 표시", [(e.summary, e.branch) for e in evs] == [("내 일정", False), ("[지점] 지점 회의", True)],
   [(e.summary, e.branch) for e in evs])
W.cal_list.append({"id": BR, "selected": True})
evs = google_client.fetch_calendar_events(AUTH)
ok("내 목록에 이미 있어도 두 번 읽지 않는다", [e.summary for e in evs] == ["내 일정", "[지점] 지점 회의"])
W.cal_list.pop()
del W.calendars[BR]
evs = google_client.fetch_calendar_events(AUTH)
ok("공유받지 못한 계정 — 내 일정은 그대로, 오류 창 없이 까닭만 남긴다",
   [e.summary for e in evs] == ["내 일정"] and "공유" in google_client.branch_calendar_error(),
   google_client.branch_calendar_error())
google_client.set_branch_calendar("")

# ------------------------------------------------------------------ [7]
print("[7] 설정 — 새 칸 · 탭")
S = models.AppSettings()
ok("기본값 — 지난 문자 지우기·시트 백업 켜짐 · 지점 캘린더는 회사 기본값",
   S.otp_clean and S.sheet_backup and S.sheet_backups == [] and S.branch_cal == config.DEF_BRANCH_CAL)
S.otp_clean, S.sheet_backup, S.branch_cal = False, False, BR
S.sheet_backups = [{"id": "x", "at": "2026-11-10", "src": "CUST", "name": "n"}]
_CFG = _pl.Path(tempfile.mkdtemp()) / "plan_cfg.json"


def _load(obj):
    _CFG.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return models.AppSettings.load(_CFG)


S2 = _load(S.to_json())
ok("저장하고 다시 읽어도 그대로", (S2.otp_clean, S2.sheet_backup, S2.branch_cal, S2.sheet_backups)
   == (False, False, BR, S.sheet_backups))
S3 = _load({"sheetBackups": ["깨진 것", {"at": "id 없음"}, {"id": "ok"}]})
ok("옛 설정 파일(새 칸 없음) · 깨진 백업 기록", S3.otp_clean and S3.sheet_backup and S3.sheet_backups == [{"id": "ok"}])

d = settings_dialog.SettingsDialog(AUTH, models.AppSettings(), None, account="staff@example.com")
titles = [d.tabs.tabText(i) for i in range(d.tabs.count())]
ok("탭 다섯 개로 나눴다", isinstance(d.tabs, QTabWidget) and titles == ["계정·동기화", "고객관리", "알림·일정", "인증번호", "화면·기타"], titles)
ok("직원 PC — '지난 문자 지우기' 는 흐리게(관리자 PC 가 지운다)", not d.chk_otp_clean.isEnabled())
d.ed_branch_cal.setText("https://calendar.google.com/calendar/embed?src=abc123%40group.calendar.google.com")
d.chk_sheet_backup.setChecked(False)
d._on_ok()
ok("확인 — 주소를 붙여넣어도 ID 만 · 백업 끔 · 직원은 지우기 설정을 못 바꾼다",
   d.settings.branch_cal == BR and d.settings.sheet_backup is False and d.settings.otp_clean is True)
d2 = settings_dialog.SettingsDialog(AUTH, models.AppSettings(), None, account=ADMIN)
ok("관리자 PC — '지난 문자 지우기' 를 켜고 끌 수 있다", d2.chk_otp_clean.isEnabled() and d2.chk_otp_clean.isChecked())
d.deleteLater()
d2.deleteLater()

# ------------------------------------------------------------------ [8]
print("[8] 업데이트 — 저장소가 비공개가 돼도(우회 길)")


class R:
    def __init__(self, code, body=None):
        self.status_code, self._b = code, body

    def json(self):
        return self._b


CALLS = []
PROXY = {"code": 200, "body": {"tag": "v99.0.0", "name": "새 판", "notes": "· 고침", "asset_url": config.UPDATE_PROXY_URL + "&dl=1"}}
GH = {"code": 404}


def fake_get(url, **kw):
    CALLS.append((url, dict(kw.get("headers") or {})))
    if "api.github.com" in url:
        return R(GH["code"], {})
    return R(PROXY["code"], PROXY["body"])


updater.requests.get = fake_get
updater._token = lambda: ""
v = updater.check()
ok("깃허브가 404(비공개)면 우회 길로 묻는다", v and v["version"] == "v99.0.0" and "dl=1" in v["asset_url"], v)
ok("우회 길에는 계정·토큰을 보내지 않는다", all("Authorization" not in h for u, h in CALLS if "api.github.com" not in u))
PROXY["body"] = dict(PROXY["body"], tag="v" + config.APP_VERSION)
ok("같은 판이면 새 판 없음", updater.check() is None)
PROXY["code"] = 503
try:
    updater.check()
    ok("우회 길도 준비가 안 됐으면 전과 같이 알린다", False)
except RuntimeError as e:
    ok("우회 길도 준비가 안 됐으면 전과 같이 알린다", "릴리스" in str(e), str(e))
GH["code"], n0 = 200, len(CALLS)
PROXY["code"] = 200
ok("공개 저장소일 때는 우회 길을 쓰지 않는다(지금과 똑같다)",
   updater.check() is None and all("api.github.com" in u for u, _h in CALLS[n0:]) and len(CALLS) == n0 + 1, CALLS[n0:])
ok("내려받기 — 토큰은 깃허브 주소에만 붙인다",
   "api.github.com" in (_ROOT / "python/planner/updater.py").read_text(encoding="utf-8").split("def download")[1].split("\ndef ")[0])
js = (_ROOT / "api/update.js").read_text(encoding="utf-8")
ok("서버 함수 — 토큰은 환경 변수에서만 · 없으면 503 · 응답에 토큰을 싣지 않는다",
   "process.env.GITHUB_UPDATE_TOKEN" in js and "503" in js and "not_configured" in js and "ghp_" not in js and "github_pat_" not in js)

# ------------------------------------------------------------------ [9]
print("[9] 관리자 계정으로 실제로 켠다 — 지난 문자 지우기 · 시트 백업 · 지점 캘린더")
day = lambda n: (date.today() - timedelta(days=n)).strftime("%Y. %-m. %-d")  # noqa: E731
W.sheets[config.RATES_SHEET_ID] = {"업무자료": [["분류", "금융사", "제목", "태그", "본문", "체크리스트"],
                                              ["심사서류", "", "개인 심사서류", "", "팩스 {내 팩스|0504-214-5287}", ""]],
                                   "수당율": [["차종", "수당율"], ["쏘렌토", "1.2"]]}
W.sheets[config.OTP_DEF_SHEET_ID] = {"시트1": [["일시", "", "인증번호", "맨위가 최신입니다"],
                                             [day(0), "수신문자", "인증번호 (111111)"],
                                             [day(1), "수신문자", "인증번호 (222222)"],
                                             [day(2), "수신문자", "인증번호 (333333)"],
                                             [day(9), "수신문자", "인증번호 (444444)"]]}
W.sheets["MYSHEET"] = {"미출고차량": [["순번", "고객명 / 사업자"], ["1", "홍길동"]]}
W.can_edit["MYSHEET"] = True
W.calendars[BR] = [ev("지점 회의", "b1", 2)]
W.created.clear()
W.writes.clear()
(config.base_dir() / "google_token.json").write_text(
    json.dumps({"refresh_token": "RT", "scopes": list(config.SCOPE_LABELS) + [config.SCOPE_DRIVE_READ]}),
    encoding="utf-8")
otp.claim = lambda item, now=None: True

from planner.main_window import MainWindow  # noqa: E402

w = MainWindow()
w.show()
ok("계정 확인(관리자)", wait(lambda: w._account_verified, 10), w.account_email)
ok("관리자 PC 가 2일 지난 문자를 지운다 — 오늘·어제만 남는다",
   wait(lambda: len(W.sheets[config.OTP_DEF_SHEET_ID]["시트1"]) == 3, 12)
   and W.sheets[config.OTP_DEF_SHEET_ID]["시트1"][-1][0] == day(1), W.sheets[config.OTP_DEF_SHEET_ID]["시트1"])
n_del = len([1 for k, t, _p in W.writes if k == "sheet" and config.OTP_DEF_SHEET_ID in t])
pump(5)
ok("한 번 지우면 6시간 동안은 다시 하지 않는다",
   len([1 for k, t, _p in W.writes if k == "sheet" and config.OTP_DEF_SHEET_ID in t]) == n_del == 1, n_del)


def script_settings(dlg):
    dlg.chk_sheet.setChecked(True)
    dlg.ed_sheet_id.setText("https://docs.google.com/spreadsheets/d/MYSHEET/edit")
    dlg.ed_branch_cal.setText(BR)
    dlg._on_ok()
    return dlg.result()


settings_dialog.SettingsDialog.exec = lambda self: script_settings(self)
w.on_settings_click()
ok("내 시트(고칠 수 있음) — 단추가 켜져 있다", wait(lambda: w._sheet_can_edit is True, 10)
   and all(b.isEnabled() for b in w._cust_write_btns))
ok("처음 읽으면 사본을 하나 만든다", wait(lambda: len(w.settings.sheet_backups) == 1 and len(W.created) == 1, 10),
   (w.settings.sheet_backups, W.created))
ok("사본에 고객관리 탭이 들어 있다", W.created and list(W.sheets[W.created[0][0]]) == ["미출고차량"]
   and W.created[0][1].startswith(sheet_backup.PREFIX))
w.load_sheet_async() if hasattr(w, "load_sheet_async") else None
pump(3)
ok("다시 읽어도 이번 주엔 또 만들지 않는다", len(W.created) == 1, W.created)
ok("지점 캘린더 일정이 [지점] 으로 함께 보인다", wait(lambda: any(e.summary == "[지점] 지점 회의" for e in w.cal_events), 10),
   [e.summary for e in w.cal_events])
ok("팔로업·중복 정리는 내 일정에만(지점 일정은 뺀다)", all(not e.branch for e in w._own_events())
   and len(w._own_events()) == len(w.cal_events) - 1)

print("[10] 새 PC 첫 실행 안내 — 한 번만")
flag = config.base_dir() / "first_run.done"
ok("이미 로그인된 PC 는 띄우지 않았다", not flag.exists() and getattr(w, "_status_dlg", None) is None)
w.gauth.is_connected = lambda: False
w._maybe_first_run()
dlg = getattr(w, "_status_dlg", None)
ok("로그인 전이면 '처음 설정' 을 띄운다", dlg is not None and dlg.isVisible() and flag.exists()
   and "처음" in dlg.windowTitle() + "".join(x.text() for x in dlg.findChildren(type(w.lbl_status))), dlg and dlg.windowTitle())
dlg.close()
w._status_dlg = None
w._maybe_first_run()
ok("두 번째부터는 띄우지 않는다", getattr(w, "_status_dlg", None) is None)

pump(0.5)
ok("끝까지 예외가 없다", not ERRS, ERRS[:2])
ok("모르는 주소로 나가지 않는다", not fg.UNKNOWN, fg.UNKNOWN[:5])
w._quitting = True
w.close()
print()
print("실패:", FAIL if FAIL else "없음")
_sys.exit(1 if FAIL else 0)
