"""휴대폰 인증번호 받기(kb-v1.8.0) — 일정관리기와 똑같이 · 주소는 저절로 · 처음 설치하면 꺼짐.

지점장: "자료검색 경량 프로그램에 일정관리기와 똑같은 문자알람을 넣고 싶어. 설정 및 주소는 동일하게 자동으로
넣어 주고, 다만 사용 체크는 기본 초기 설치 시에는 해제해 줘."
  · 규칙은 일정관리기(python/planner/otp.py)와 같아야 한다 — 같은 문자를 두 쪽에 넣어 대조한다.
"""
import pathlib as _pl
import sys as _sys

_HERE = _pl.Path(__file__).resolve().parent
_sys.path.insert(0, str(_HERE.parent))
_sys.path.insert(0, str(_HERE))

import json  # noqa: E402
import os  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import urllib.parse  # noqa: E402
from datetime import date  # noqa: E402

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QEnterEvent, QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication, QGroupBox, QLabel  # noqa: E402

app = QApplication.instance() or QApplication([])

from kbsearch import config, otp, otp_popup  # noqa: E402
from kbsearch.settings import Settings  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


TODAY = date(2026, 11, 10)
D = "2026. 11. 10"
HEAD = ["일시", "", "인증번호", "맨위가 최신입니다"]
KB = "[Web발신]\n[KB캐피탈] 본인확인 인증번호[989365]를 화면에 입력해주세요"
LOGIN = "[Web발신]\n로그인 인증번호 (624562)\n"

print("[1] 일정관리기와 같은 규칙(같은 문자를 두 쪽에 넣어 본다)")
_sys.path.insert(0, str(_HERE.parents[1] / "python"))
from planner import otp as potp  # noqa: E402

bodies = [KB, LOGIN, "[현대캐피탈] 고객센터 1588-2114 인증번호 334455 입니다", "인증번호는 [4821] 입니다",
          "Your verification code is 482193.", "[신한카드] 승인번호 12345678 결제", "[KB캐피탈] 출고 안내",
          "고객님 010-1234-5678 로 연락 주세요"]
ok("인증번호 뽑기 · 보낸 곳", [otp.extract_code(b) for b in bodies] == [potp.extract_code(b) for b in bodies]
   and [otp.sender_of(b) for b in bodies] == [potp.sender_of(b) for b in bodies]
   and otp.extract_code(KB) == "989365" and otp.sender_of(KB) == "KB캐피탈")
vals = [HEAD, [D, "수신문자", KB], [D, "수신문자", LOGIN], ["2026. 11. 9", "수신문자", "인증번호 [111111]"]]
ok("시트 줄 읽기 · 오늘 것만", otp.rows_of(vals) == potp.rows_of(vals)
   and otp.items_of(otp.rows_of(vals), TODAY) == potp.items_of(potp.rows_of(vals), TODAY)
   and [i["code"] for i in otp.items_of(otp.rows_of(vals), TODAY)] == ["989365", "624562"])
k = lambda vs: [r["key"] for r in otp.rows_of([HEAD] + [[D, "", b] for b in vs])]  # noqa: E731
R = lambda vs: otp.rows_of([HEAD] + [[D, "", b] for b in vs])  # noqa: E731
cases = [(None, ["A", "B"]), (["A", "B"], ["A", "B"]), (["A", "B"], ["N", "A", "B"]), (["A", "B"], ["A", "A", "B"]),
         (["A", "B", "C"], ["B", "C"]), ([], ["N"])]
same = all([r["body"] for r in otp.new_rows(None if p is None else k(p), R(c))]
           == [r["body"] for r in potp.new_rows(None if p is None else k(p), R(c))] for p, c in cases)
ok("새로 온 줄 가리기(켤 때 있던 것 · 같은 글 두 번 · 줄 지움)", same)
ok("같은 간격 · 자리 비움 · 쉬는 시간", (otp.POLL_MS, otp.IDLE_SEC, otp.IDLE_EVERY, otp.BACKOFF_TICKS, otp.TOP_ROWS)
   == (potp.POLL_MS, potp.IDLE_SEC, potp.IDLE_EVERY, potp.BACKOFF_TICKS, potp.TOP_ROWS))
ok("같은 지점 공용 시트", config.OTP_DEF_SHEET_ID == "1krhRICtrYbDKtkLa7RC6RZ8IxrEUGm2ZhfbUtYl5_hw"
   and config.OTP_DEF_TAB == "시트1")

print("[2] 시트 읽기 — 맨 위 몇 줄만(요청 하나)")
calls = []
SHEET = {"vals": [HEAD, [D, "수신문자", LOGIN]]}


class Resp:
    status_code = 200

    def json(self):
        return {"values": SHEET["vals"]}


class Http:
    def get(self, url, **kw):
        calls.append(url)
        return Resp()


otp._http = lambda: Http()


class Auth:
    email = "me@example.com"
    scope_ok = True

    def valid_token(self):
        return "TOKEN"

    def is_connected(self):
        return True

    def has_scope(self, s):
        return self.scope_ok


otp.read_top(Auth(), "SHEETID", "시트1")
ok("'시트1'!A1:F12 만", urllib.parse.unquote(calls[-1]).endswith("/SHEETID/values/'시트1'!A1:F12"))
w = otp.Watcher()
ok("켤 때 있던 것은 띄우지 않는다", w.poll(Auth(), "SHEETID", "시트1", TODAY) == [])
SHEET["vals"] = [HEAD, [D, "수신문자", KB], [D, "수신문자", LOGIN]]
ok("새 인증번호만", [g["code"] for g in w.poll(Auth(), "SHEETID", "시트1", TODAY)] == ["989365"])

print("[3] 설정 — 주소는 저절로 · 처음 설치하면 꺼짐")
s = Settings.load()
ok("처음 설치: 꺼짐 · 지점 공용 시트 · 시트1 · 자동 복사", s.otp_on is False and s.otp_sheet == config.OTP_DEF_SHEET_ID
   and s.otp_tab == "시트1" and s.otp_copy is True)
config.data_file("settings.json").write_text(json.dumps({"theme": "dark", "kb_hot_key": "G"}), encoding="utf-8")
s = Settings.load()
ok("예전 판에서 올라와도(설정 파일에 칸이 없다) 꺼짐 · 주소는 채워짐", s.otp_on is False
   and s.otp_sheet == config.OTP_DEF_SHEET_ID and s.theme == "dark")
config.data_file("settings.json").write_text(json.dumps({"otp_on": True, "otp_sheet": "", "otp_tab": ""}),
                                            encoding="utf-8")
s = Settings.load()
ok("주소를 비워 두면 지점 기본 시트로", s.otp_on is True and s.otp_sheet == config.OTP_DEF_SHEET_ID and s.otp_tab == "시트1")

from kbsearch.settings_dialog import SettingsDialog  # noqa: E402
s = Settings()
d = SettingsDialog(s, hot_ok=True)
groups = [g.title() for g in d.findChildren(QGroupBox)]
ok("설정 창에 '휴대폰 인증번호 받기'", "휴대폰 인증번호 받기" in groups, groups)
ok("주소·탭이 미리 채워져 있고 꺼져 있다", d.ed_otp_sheet.text() == config.OTP_DEF_SHEET_ID
   and d.ed_otp_tab.text() == "시트1" and not d.chk_otp.isChecked())
d.chk_otp.setChecked(True)
d.ed_otp_sheet.setText("https://docs.google.com/spreadsheets/d/1AbC_xyz-9/edit#gid=0")
d.ed_otp_tab.setText(" 탭2 ")
d.chk_otp_copy.setChecked(False)
d._ok()
ok("켜기 · 주소를 붙여넣어도 ID 만 · 탭 다듬기 · 복사 끄기", s.otp_on and s.otp_sheet == "1AbC_xyz-9"
   and s.otp_tab == "탭2" and s.otp_copy is False, (s.otp_sheet, s.otp_tab))
d = SettingsDialog(s, hot_ok=True)
d.ed_otp_sheet.setText("")
d.ed_otp_tab.setText("")
d._ok()
ok("주소를 비우면 지점 기본 시트로 돌아간다", s.otp_sheet == config.OTP_DEF_SHEET_ID and s.otp_tab == "시트1")
s.save()
s2 = Settings.load()
ok("저장된다", (s2.otp_on, s2.otp_sheet, s2.otp_tab, s2.otp_copy) == (True, config.OTP_DEF_SHEET_ID, "시트1", False))

print("[4] 화면 — 주 모니터 오른쪽 아래 · 10초 · 마우스를 올리면 그대로")
p1 = otp_popup.show({"code": "989365", "sender": "KB캐피탈", "body": KB}, copied=True)
app.processEvents()
ok("번호를 크게 · 보낸 곳 · 복사 안내", p1.lbl_code.text() == "989365" and "KB캐피탈" in p1.lbl_head.text()
   and "Ctrl+V" in p1.lbl_state.text())
ok("항상 위 · 포커스를 뺏지 않는다", bool(p1.windowFlags() & Qt.WindowStaysOnTopHint)
   and p1.testAttribute(Qt.WA_ShowWithoutActivating))
ok("주 모니터", otp_popup._screen() is QGuiApplication.primaryScreen())
geo = otp_popup._screen().availableGeometry()
ok("오른쪽 아래(화면 안)", p1.x() + p1.width() <= geo.right() + 1 and p1.y() + p1.height() <= geo.bottom() + 1
   and p1.x() > geo.center().x() - 10)
ok("10초 뒤 닫힌다(뜬 뒤에도 센다)", otp_popup.LIFE_MS == 10000 and p1._life.isActive())
p1.enterEvent(QEnterEvent(QPointF(-400, -600), QPointF(10, 10), QPointF(10, 10)))
ok("창 밖 마우스로 온 '들어왔다' 는 무시", p1._life.isActive())
p1.enterEvent(QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5)))
ok("마우스를 올려 두면 닫지 않는다", not p1._life.isActive())
p1.copy()
ok("[복사]", QApplication.clipboard().text() == "989365")
p1.close()
ok("닫으면 목록에서 빠진다", otp_popup._open == [])

print("[5] 메인 창 — 꺼져 있으면 안 읽고, 켜면 4초마다 · 오면 띄우고 복사 · 못 읽으면 쉰다")
from kbsearch.main_window import MainWindow  # noqa: E402


class Sig:
    def __init__(self):
        self.got, self.ev = [], threading.Event()

    def emit(self, *a):
        self.got.append(a)
        self.ev.set()


class Fake:
    gauth = Auth()

    def __init__(self, st):
        self.settings = st
        self._otp = otp.Watcher()
        self._otp_busy = False
        self._otp_skip = 0
        self._otp_errs = 0
        self._otp_tick = 0
        self.sig_otp = Sig()
        self.msgs = []

    def _set_msg(self, text, kind=""):
        self.msgs.append((text, kind))


st = Settings()
f = Fake(st)
n = len(calls)
MainWindow._poll_otp(f)
ok("처음 설치(꺼짐)면 읽지 않는다", f.sig_otp.got == [] and len(calls) == n)
st.otp_on = True
MainWindow._poll_otp(f)
ok("켜면 읽는다(뒤에서)", f.sig_otp.ev.wait(5) and len(calls) == n + 1)


class NoAuth(Auth):
    def is_connected(self):
        return False


f2 = Fake(st)
f2.gauth = NoAuth()
MainWindow._poll_otp(f2)
ok("구글 로그인 전이면 읽지 않는다", f2.sig_otp.got == [])
QApplication.clipboard().setText("")
MainWindow._on_otp(f, [{"code": "445566", "sender": "", "body": ""}, {"code": "112233", "sender": "", "body": ""}], "")
app.processEvents()
ok("오면 띄우고 가장 최근 것을 클립보드에", QApplication.clipboard().text() == "445566" and len(otp_popup._open) == 2)
for x in list(otp_popup._open):
    x.close()
for i in range(3):
    MainWindow._on_otp(f, [], "시트를 찾을 수 없습니다")
ok("못 읽으면 약 30초 쉰다 · 세 번째에 한 번 알린다", f._otp_skip == otp.BACKOFF_TICKS and len(f.msgs) == 1
   and "인증문자 시트를 읽지 못했습니다" in f.msgs[0][0])
src = (_HERE.parent / "kbsearch" / "main_window.py").read_text(encoding="utf-8")
ok("4초마다 본다", "self._otp_timer.start(otp.POLL_MS)" in src)

print("[6] kb-v1.8.1 — 그 시트를 볼 수 없는 계정 · 인터넷 끊김 · 잠들었다 깸(일정관리기와 같다)")
ok("일정관리기와 같은 값", (otp.DENIED_TICKS, otp.GAP_SEC) == (potp.DENIED_TICKS, potp.GAP_SEC) == (150, 120))
fd = Fake(Settings())
MainWindow._on_otp(fd, [], "denied")
MainWindow._on_otp(fd, [], "denied")
ok("권한이 없으면 10분에 한 번만 다시 보고, 한 번만 알린다", fd._otp_skip == otp.DENIED_TICKS and len(fd.msgs) == 1
   and "볼 수 없습니다" in fd.msgs[0][0])
fn = Fake(Settings())
for i in range(5):
    MainWindow._on_otp(fn, [], "net")
ok("인터넷이 끊긴 것은 알리지 않는다", fn.msgs == [] and fn._otp_skip == otp.BACKOFF_TICKS and fn._otp_errs == 0)
st2 = Settings()
st2.otp_on = True
fs = Fake(st2)
fs.gauth = Auth()
fs.gauth.scope_ok = False
n = len(calls)
MainWindow._poll_otp(fs)
ok("시트 권한 없이 로그인했으면 읽지 않는다", len(calls) == n and not fs._otp_busy)
w2 = otp.Watcher()
SHEET["vals"] = [HEAD, [D, "수신문자", LOGIN]]
w2.poll(Auth(), "SHEETID", "시트1", TODAY, now=1000.0)
SHEET["vals"] = [HEAD, [D, "수신문자", KB], [D, "수신문자", LOGIN]]
ok("오래(2분 넘게) 못 봤다가 다시 보면 그사이 온 옛 문자는 띄우지 않는다",
   w2.poll(Auth(), "SHEETID", "시트1", TODAY, now=1000.0 + otp.GAP_SEC + 1) == [])
import inspect as _insp  # noqa: E402
_osrc = _insp.getsource(otp)
ok("net.http 를 부를 때 찾는다(검사가 가짜로 바꾸면 진짜 인터넷으로 나가지 않는다)", "return net.http()" in _osrc
   and not any(ln.startswith("from .net import http") for ln in _osrc.splitlines()))

print()
print("실패:", FAIL if FAIL else "없음")
_sys.exit(1 if FAIL else 0)
