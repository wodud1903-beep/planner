"""휴대폰 인증번호를 PC 에서 바로(v1.31) — MacroDroid 가 쌓는 '인증문자' 시트를 몇 초마다 본다.

지점장: "PC 앱에서 실시간으로 인증번호를 받고 싶어(MacroDroid 로 스프레드시트에 보내는 것까지는 해 놨다)."
시트 모양(실제와 같게): 1행 머리글 [일시, "", 인증번호, 맨위가 최신입니다] · 2행부터 [날짜, 수신문자, 본문] · 맨 위가 최신.
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))

import os
import tempfile
import threading
import urllib.parse
from datetime import date

os.environ["APPDATA"] = tempfile.mkdtemp()
tempfile.tempdir = tempfile.mkdtemp()     # 인증번호 표식(jy_otp_claims)이 앞선 실행·다른 검사와 섞이지 않게(v1.32)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

app = QApplication.instance() or QApplication([])

from planner import config, otp, otp_popup  # noqa: E402
from planner.models import AppSettings  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


TODAY = date(2026, 11, 9)
D = "2026. 11. 9"
HEAD = ["일시", "", "인증번호", "맨위가 최신입니다"]
KB = "[Web발신]\n[KB캐피탈] 본인확인 인증번호[989365]를 화면에 입력해주세요"
LOGIN = "[Web발신]\n로그인 인증번호 (624562)\n"

print("[1] 문자에서 인증번호·보낸 곳 뽑기")
cases = {
    KB: "989365",
    LOGIN: "624562",
    "[Web발신]\n[현대캐피탈] 고객센터 1588-2114 인증번호 334455 입니다": "334455",
    "인증번호는 [4821] 입니다": "4821",
    "Your verification code is 482193.": "482193",
    "[신한카드] 승인번호 12345678 결제": "12345678",
    "[Web발신]\n[KB캐피탈] 출고 일정을 안내드립니다": "",
    "고객님 010-1234-5678 로 연락 주세요": "",
}
got = {k: otp.extract_code(k) for k in cases}
ok("인증·승인·코드 뒤 숫자 · 괄호 안 숫자 · 전화번호는 아님", got == cases,
   {k[:20]: v for k, v in got.items() if v != cases[k]})
ok("보낸 곳 — [Web발신] 말고 첫 대괄호", otp.sender_of(KB) == "KB캐피탈" and otp.sender_of(LOGIN) == "")

print("[2] 시트 줄 → 문자 · 새로 온 줄 가리기")
rows = otp.rows_of([HEAD, [D, "수신문자", KB], [D, "수신문자", LOGIN], []])
ok("머리글·빈 줄은 빼고 가장 긴 칸을 본문으로", [r["body"] for r in rows] == [KB.strip(), LOGIN.strip()]
   and rows[0]["date"] == D)
ok("머리글이 없는 시트도", len(otp.rows_of([[D, "수신문자", KB]])) == 1)
# v1.32: 본문이 날짜 칸보다 짧은 문자("인증 1234")는 날짜가 본문으로 뽑혀 번호를 놓쳤다
_short = otp.rows_of([HEAD, ["2026. 11. 10", "수신문자", "인증 1234"], ["2026. 11. 10", "수신문자", "4821"]])
ok("짧은 문자도 본문을 제대로 고른다(날짜 칸을 본문으로 삼지 않는다)",
   [r["body"] for r in _short] == ["인증 1234", "4821"] and otp.extract_code(_short[0]["body"]) == "1234",
   [r["body"] for r in _short])
ok("칸이 날짜 하나뿐인 줄은 그 칸이 본문", otp.rows_of([["인증번호 123456"]])[0]["body"] == "인증번호 123456")


def R(*bodies):
    return otp.rows_of([HEAD] + [[D, "수신문자", b] for b in bodies])


k = lambda rs: [r["key"] for r in rs]  # noqa: E731
A, B, C, N1, N2 = "인증번호 [111111]", "인증번호 [222222]", "인증번호 [333333]", "인증번호 [444444]", "인증번호 [555555]"
old = R(A, B, C)
ok("처음 읽은 것은 띄우지 않는다(켤 때 이미 있던 문자)", otp.new_rows(None, old) == [])
ok("그대로면 새 것 없음", otp.new_rows(k(old), R(A, B, C)) == [])
ok("맨 위에 하나 들어오면 그것만", [r["body"] for r in otp.new_rows(k(old), R(N1, A, B, C))] == [N1])
ok("두 개가 한꺼번에", [r["body"] for r in otp.new_rows(k(old), R(N2, N1, A, B))] == [N2, N1])
ok("같은 문자가 또 와도(같은 글) 자리로 가린다", [r["body"] for r in otp.new_rows(k(old), R(A, A, B, C))] == [A])
ok("누가 줄을 지웠으면 띄우지 않는다", otp.new_rows(k(old), R(B, C)) == [])
ok("비어 있던 시트에 처음 들어오면 띄운다", [r["body"] for r in otp.new_rows([], R(N1))] == [N1])
items = otp.items_of(otp.rows_of([[D, "수신문자", KB], ["2026. 11. 8", "수신문자", LOGIN],
                                   [D, "수신문자", "[KB캐피탈] 출고 안내"]]), TODAY)
ok("인증번호가 있고 오늘 온 것만 띄운다", [i["code"] for i in items] == ["989365"] and items[0]["sender"] == "KB캐피탈")

print("[3] 시트 읽기 — 맨 위 몇 줄만(요청 하나)")
calls = []


class Resp:
    status_code = 200

    def __init__(self, vals):
        self.vals = vals

    def json(self):
        return {"values": self.vals}


SHEET = {"vals": [HEAD, [D, "수신문자", LOGIN]]}


class Http:
    def get(self, url, **kw):
        calls.append((url, kw))
        return Resp(SHEET["vals"])


otp._http = lambda: Http()


class Auth:
    scope_ok = True

    def valid_token(self):
        return "TOKEN"

    def is_connected(self):
        return True

    def has_scope(self, s):
        return self.scope_ok


otp.read_top(Auth(), "SHEETID", "시트1")
url = urllib.parse.unquote(calls[-1][0])
ok("'시트1'!A1:F12 만 읽는다", url.endswith("/SHEETID/values/'시트1'!A1:F12"), url[-40:])
otp.read_top(Auth(), "SHEETID", "")
ok("탭을 비우면 첫 번째 탭(시트 이름 없이)", urllib.parse.unquote(calls[-1][0]).endswith("/values/A1:F12"))

w = otp.Watcher()
ok("켤 때 — 있던 것은 '본 것'", w.poll(Auth(), "SHEETID", "", TODAY) == [])
SHEET["vals"] = [HEAD, [D, "수신문자", KB], [D, "수신문자", LOGIN]]
got = w.poll(Auth(), "SHEETID", "", TODAY)
ok("새 인증번호가 오면 그것만", [g["code"] for g in got] == ["989365"])
ok("다시 보면 또 띄우지 않는다", w.poll(Auth(), "SHEETID", "", TODAY) == [])
SHEET["vals"] = [HEAD, [D, "수신문자", "인증번호 [777777]"], [D, "수신문자", KB]]
ok("다른 시트로 바꾸면 그 시트의 지금 것은 '본 것'", w.poll(Auth(), "OTHER", "", TODAY) == [])
# v1.31.3 — PC 가 잠들었다 깨거나 인터넷이 한참 끊겼다 붙으면, 그사이 온 옛 문자는 띄우지 않는다
w2 = otp.Watcher()
SHEET["vals"] = [HEAD, [D, "수신문자", LOGIN]]
w2.poll(Auth(), "SHEETID", "", TODAY, now=1000.0)
SHEET["vals"] = [HEAD, [D, "수신문자", KB], [D, "수신문자", LOGIN]]
ok("오래(2분 넘게) 못 봤다가 다시 보면 그사이 온 것은 띄우지 않는다",
   w2.poll(Auth(), "SHEETID", "", TODAY, now=1000.0 + otp.GAP_SEC + 1) == [])
SHEET["vals"] = [HEAD, [D, "수신문자", "인증번호 [246810]"], [D, "수신문자", KB], [D, "수신문자", LOGIN]]
ok("그 뒤 새로 온 것은 다시 띄운다(자리 비움 20초 간격은 그대로 이어 본다)",
   [g["code"] for g in w2.poll(Auth(), "SHEETID", "", TODAY, now=1000.0 + otp.GAP_SEC + 21)] == ["246810"])


class Resp403(Resp):
    status_code = 403


class Http403:
    def get(self, url, **kw):
        calls.append((url, kw))
        return Resp403([])


_keep_http = otp._http
otp._http = lambda: Http403()
try:
    otp.read_top(Auth(), "SHEETID", "")
    ok("권한이 없으면 NoAccess", False)
except otp.NoAccess:
    ok("권한이 없으면(403 · 404) NoAccess", True)
otp._http = _keep_http
import inspect as _insp  # noqa: E402
_osrc = _insp.getsource(otp)
ok("net.http 를 부를 때 찾는다(검사가 net.http 를 가짜로 바꾸면 진짜 인터넷으로 나가지 않는다)",
   "return net.http()" in _osrc
   and not any(ln.startswith("from .net import http") for ln in _osrc.splitlines()))

print("[4] 화면 — 오른쪽 아래 · 항상 위 · 포커스 안 뺏음 · 복사")
QApplication.clipboard().setText("")
p1 = otp_popup.show({"code": "989365", "sender": "KB캐피탈", "body": KB}, copied=True)
app.processEvents()
ok("번호를 크게 · 보낸 곳", p1.lbl_code.text() == "989365" and "KB캐피탈" in p1.lbl_head.text())
ok("항상 위 · 포커스를 뺏지 않는다", bool(p1.windowFlags() & Qt.WindowStaysOnTopHint)
   and p1.testAttribute(Qt.WA_ShowWithoutActivating))
ok("복사해 두었다고 알린다", "Ctrl+V" in p1.lbl_state.text())
geo = otp_popup._screen().availableGeometry()
ok("언제나 주 모니터(듀얼 모니터에서 마우스 따라 다니지 않게)",
   otp_popup._screen() is __import__("PySide6.QtGui", fromlist=["QGuiApplication"]).QGuiApplication.primaryScreen())
from planner import alarm_window  # noqa: E402
ok("일정 알람도 주 모니터", alarm_window._pick_screen() is otp_popup._screen())
ok("화면 오른쪽 아래(화면 안)", p1.x() + p1.width() <= geo.right() + 1 and p1.y() + p1.height() <= geo.bottom() + 1
   and p1.x() > geo.center().x() - 10, (p1.x(), p1.y(), geo.right(), geo.bottom()))
p1.copy()
ok("[복사] 하면 클립보드에", QApplication.clipboard().text() == "989365")
ps = [otp_popup.show({"code": str(100000 + i), "body": ""}) for i in range(4)]
app.processEvents()
ok("많아야 셋 — 오래된 것부터 닫는다", len(otp_popup._open) == 3 and p1 not in otp_popup._open)
ok("쌓이면 위로(새 것이 맨 아래)", otp_popup._open[-1].y() > otp_popup._open[0].y())
for x in list(otp_popup._open):
    x.close()
ok("닫으면 목록에서 빠진다", otp_popup._open == [])
ok("10초 뒤 저절로 닫힌다(v1.31.1)", otp_popup.LIFE_MS == 10000 and ps[-1]._life.isSingleShot())
from PySide6.QtCore import QEvent, QPointF  # noqa: E402
from PySide6.QtGui import QEnterEvent  # noqa: E402
ph = otp_popup.show({"code": "121212", "body": ""})
app.processEvents()
ok("뜬 뒤에도 10초를 센다(창 밖 마우스로 온 '들어왔다' 는 무시 — v1.31.2)", ph._life.isActive())
ph.enterEvent(QEnterEvent(QPointF(-400, -600), QPointF(10, 10), QPointF(10, 10)))
ok("창 밖이면 멈추지 않는다", ph._life.isActive())
ph.enterEvent(QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5)))
ok("마우스를 올려 두면 닫지 않는다", not ph._life.isActive())
ph.leaveEvent(QEvent(QEvent.Leave))
ok("손을 떼면 다시 10초", ph._life.isActive() and ph._life.interval() == 10000)
ph.close()

print("[5] 설정 — 켜기 · 시트 주소 · 자동 복사(PC 끼리 따라간다)")
s = AppSettings()
ok("기본은 켜짐 · 지점 공용 인증문자 시트 · 시트1 · 자동 복사(v1.31.1)", s.otp_on is True and s.otp_copy is True
   and s.otp_sheet == config.OTP_DEF_SHEET_ID == "1krhRICtrYbDKtkLa7RC6RZ8IxrEUGm2ZhfbUtYl5_hw" and s.otp_tab == "시트1")
import json  # noqa: E402
pv = config.data_dir() / "plan_cfg_v1310.json"
pv.write_text(json.dumps({"otpOn": False, "otpSheet": "", "otpTab": "", "otpCopy": True}), encoding="utf-8")
sv = AppSettings.load(pv)
ok("v1.31.0 이 적어 둔 기본 꺼짐·빈 주소는 → 켜짐 · 기본 시트", sv.otp_on is True
   and sv.otp_sheet == config.OTP_DEF_SHEET_ID and sv.otp_tab == "시트1")
pv.write_text(json.dumps({"otpEnabled": False, "otpSheet": "MYSHEET", "otpTab": ""}), encoding="utf-8")
sv = AppSettings.load(pv)
ok("각자 끄거나 다른 시트로 바꾼 것은 그대로(다른 시트는 탭을 비우면 첫 탭)", sv.otp_on is False
   and sv.otp_sheet == "MYSHEET" and sv.otp_tab == "")
from planner import settings_dialog  # noqa: E402


class _A:
    def is_connected(self):
        return False

    def email(self):
        return "tester@example.com"


dlg = settings_dialog.SettingsDialog(_A(), s, account="tester@example.com")
dlg.chk_otp.setChecked(True)
dlg.ed_otp_sheet.setText("https://docs.google.com/spreadsheets/d/1AbCdEfGh_ijk-LMN/edit#gid=0")
dlg.ed_otp_tab.setText(" 시트1 ")
dlg.chk_otp_copy.setChecked(False)
dlg._on_ok()
ok("주소를 붙여넣어도 ID 만 · 탭 이름 다듬기", s.otp_on and s.otp_sheet == "1AbCdEfGh_ijk-LMN" and s.otp_tab == "시트1"
   and s.otp_copy is False, (s.otp_sheet, s.otp_tab))
pth = config.data_dir() / "plan_cfg_otp.json"
s.save(pth)
s2 = AppSettings.load(pth)
ok("설정 파일에 남는다", (s2.otp_on, s2.otp_sheet, s2.otp_tab, s2.otp_copy) == (True, "1AbCdEfGh_ijk-LMN", "시트1", False))
dlg = settings_dialog.SettingsDialog(_A(), s, account="tester@example.com")
ok("설정 창에 지금 시트가 보인다", dlg.ed_otp_sheet.text() == "1AbCdEfGh_ijk-LMN")
dlg.ed_otp_sheet.setText("")
dlg.ed_otp_tab.setText("")
dlg._on_ok()
ok("주소를 비우면 지점 기본 시트로 돌아간다(탭도 시트1)", s.otp_sheet == config.OTP_DEF_SHEET_ID and s.otp_tab == "시트1")

print("[6] 메인 창 — 4초마다 보고, 오면 띄우고 복사 · 못 읽으면 쉬었다가")
from planner.main_window import MainWindow  # noqa: E402


class Sig:
    def __init__(self):
        self.got, self.ev = [], threading.Event()

    def emit(self, *a):
        self.got.append(a)
        self.ev.set()


class Fake:
    gauth = Auth()
    _account_verified = True

    def __init__(self, st):
        self.settings = st
        self._otp = otp.Watcher()
        self._otp_busy = False
        self._otp_skip = 0
        self._otp_errs = 0
        self._otp_tick = 0
        self.sig_otp = Sig()
        self.lbl_status = QLabel("")

    def _maybe_clean_otp(self):
        pass


st = AppSettings()
st.otp_on = False
f = Fake(st)
MainWindow._poll_otp(f)
ok("꺼져 있으면 읽지 않는다", f.sig_otp.got == [] and not f._otp_busy)
st.otp_on, st.otp_sheet = True, "SHEETID"
n = len(calls)
MainWindow._poll_otp(f)
f.sig_otp.ev.wait(5)
ok("켜면 읽는다(뒤에서)", len(calls) == n + 1 and f.sig_otp.got == [([], "")] and f._otp_busy)
QApplication.clipboard().setText("")
MainWindow._on_otp(f, [{"code": "445566", "sender": "", "body": "인증번호 [445566]"},
                       {"code": "112233", "sender": "", "body": "인증번호 [112233]"}], "")
app.processEvents()
ok("오면 띄우고 가장 최근 것을 클립보드에", not f._otp_busy and QApplication.clipboard().text() == "445566"
   and len(otp_popup._open) == 2 and otp_popup._open[-1].code == "445566")
for x in list(otp_popup._open):
    x.close()
st.otp_copy = False
QApplication.clipboard().setText("그대로")
MainWindow._on_otp(f, [{"code": "998877", "sender": "", "body": ""}], "")
ok("자동 복사를 끄면 클립보드는 그대로", QApplication.clipboard().text() == "그대로" and len(otp_popup._open) == 1)
for x in list(otp_popup._open):
    x.close()
for i in range(3):
    MainWindow._on_otp(f, [], "시트를 찾을 수 없습니다")
ok("못 읽으면 약 30초 쉰다 · 세 번째에 한 번 알린다", f._otp_skip == otp.BACKOFF_TICKS
   and "인증문자 시트를 읽지 못했습니다" in f.lbl_status.text())
f.sig_otp = Sig()
MainWindow._poll_otp(f)
ok("쉬는 동안은 읽지 않는다", f.sig_otp.got == [] and f._otp_skip == otp.BACKOFF_TICKS - 1)

# v1.31.3 — 그 시트를 볼 수 없는 직원 PC · 인터넷 끊김 · 시트 권한 없이 로그인
fd = Fake(AppSettings())
fd.sig_toast = Sig()
MainWindow._on_otp(fd, [], "denied")
MainWindow._on_otp(fd, [], "denied")
ok("권한이 없으면 10분에 한 번만 다시 보고, 한 번만 알린다", fd._otp_skip == otp.DENIED_TICKS == 150
   and len(fd.sig_toast.got) == 1 and "볼 수 없어" in fd.sig_toast.got[0][1] and fd.lbl_status.text() == "")
MainWindow._on_otp(fd, [], "")
MainWindow._on_otp(fd, [], "denied")
ok("다시 읽히다 또 막히면 다시 알린다", len(fd.sig_toast.got) == 2)
fn = Fake(AppSettings())
for i in range(5):
    MainWindow._on_otp(fn, [], "net")
ok("인터넷이 끊긴 것은 알리지 않는다(쉬었다가 다시)", fn.lbl_status.text() == "" and fn._otp_skip == otp.BACKOFF_TICKS
   and fn._otp_errs == 0)
fs = Fake(AppSettings())
fs.gauth = Auth()
fs.gauth.scope_ok = False
n_calls = len(calls)
MainWindow._poll_otp(fs)
ok("시트 권한 없이 로그인했으면 읽지 않는다(상태 줄이 다시 로그인하라고 알린다)",
   not fs._otp_busy and len(calls) == n_calls and fs.sig_otp.got == [])
_p = otp.Watcher.poll


def _deny(self, *a, **k):
    raise otp.NoAccess("HTTP 403")


otp.Watcher.poll = _deny
fw = Fake(AppSettings())
MainWindow._poll_otp(fw)
fw.sig_otp.ev.wait(5)
ok("일꾼이 권한 없음을 'denied' 로 알린다", fw.sig_otp.got == [([], "denied")], fw.sig_otp.got)
import requests as _rq  # noqa: E402


def _cut(self, *a, **k):
    raise _rq.ConnectionError("끊김")


otp.Watcher.poll = _cut
fw = Fake(AppSettings())
MainWindow._poll_otp(fw)
fw.sig_otp.ev.wait(5)
ok("인터넷 끊김은 'net' 으로", fw.sig_otp.got == [([], "net")], fw.sig_otp.got)
otp.Watcher.poll = _p
f._otp_skip = 0
f._otp_busy = False
_idle = otp.idle_seconds
otp.idle_seconds = lambda: 999.0
got_ticks = []
for t in range(10):
    f.sig_otp = Sig()
    MainWindow._poll_otp(f)
    if f.sig_otp.ev.wait(3):
        got_ticks.append(t)
    f._otp_busy = False
ok("자리 비움(2분 넘게 안 만짐)이면 다섯 번에 한 번만(약 20초)", len(got_ticks) == 2, got_ticks)
otp.idle_seconds = lambda: 3.0
f.sig_otp = Sig()
MainWindow._poll_otp(f)
ok("다시 만지면 바로 4초마다", f.sig_otp.ev.wait(3))
otp.idle_seconds = _idle
ok("윈도가 아니면(모르면) 쓰는 중으로 본다", _sys.platform == "win32" or otp.idle_seconds() == 0.0)
src = (_ROOT / "python" / "planner" / "main_window.py").read_text(encoding="utf-8")
ok("4초마다 본다", "self._otp_timer.start(otp.POLL_MS)" in src and otp.POLL_MS == 4000)
ok("인증번호를 기록(crashlog)에 남기지 않는다", "crashlog" not in (_ROOT / "python" / "planner" / "otp.py").read_text(encoding="utf-8").split('"""', 2)[2])

print()
print("실패:", FAIL if FAIL else "없음")
_sys.exit(1 if FAIL else 0)
