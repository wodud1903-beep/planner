"""v1.34 — 구글 시트 한도(429 · 계정마다 1분에 60번): 읽기 줄이기 · 쉬었다 다시 · 창 없이 · 인증번호 쉬기.

지점장이 본 창: "시트를 불러오지 못했습니다: 시트 요청 실패 (HTTP 429) Quota exceeded for quota metric
'Read requests' …". 고객 목록 한 번 읽기에 요청이 7~8번이었고, 저장할 때마다 다시 읽었고, 인증번호를
4초마다 봤다(같은 계정의 다른 PC·폰까지 한 한도를 나눠 쓴다).
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
tempfile.tempdir = tempfile.mkdtemp()

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import fake_google as fg  # noqa: E402

FAIL, ERRS, BOXES = [], [], []
_ORIG_HOOK = _sys.excepthook


def _hook(t, v, tb):
    ERRS.append("".join(traceback.format_exception(t, v, tb)))
    _ORIG_HOOK(t, v, tb)


_sys.excepthook = _hook
threading.excepthook = lambda a: ERRS.append("".join(
    traceback.format_exception(a.exc_type, a.exc_value, a.exc_traceback)))


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


from planner import config, google_client, net, otp, promo, sheets, theme  # noqa: E402
from planner import startup_dialog as _sd  # noqa: E402

EMAIL = "staff@example.com"
W = fg.World(EMAIL)
_sd.StartupDialog.show_for = staticmethod(lambda *a, **k: None)
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, _k=_n, **k: BOXES.append((_k, a[2] if len(a) > 2 else ""))))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
# 시트는 '쉬었다 다시 묻는 연결'(_Patient)을 그대로 거치게 한다 — 진짜와 같은 길
for mod in (net, google_client):
    for attr in ("http", "_http"):
        if hasattr(mod, attr):
            setattr(mod, attr, lambda: fg.Session(W))
google_client.GoogleAuth.valid_token = lambda self: "AT"
SLEPT = []
sheets._sleep = lambda sec: SLEPT.append(sec)

app = QApplication.instance() or QApplication([])
theme.apply_to_app(app)


def pump(sec=0.3):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def wait(cond, sec=10.0):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.03)
    return bool(cond())


class Auth:
    def valid_token(self):
        return "AT"

    def is_connected(self):
        return True


AUTH = Auth()


def reads(sid):
    return [u for m, u, _p in fg.LOG if m == "GET" and "sheets.googleapis.com" in u and f"/spreadsheets/{sid}" in u]


def row(*cells, s="", u="", v=""):
    r = list(cells) + [""] * (22 - len(cells))
    r[17], r[18], r[20], r[21] = "안내 멘트", s, u, v
    return r


TAB = "미출고차량"
LEGACY = '=IMAGE("https://drive.google.com/uc?export=view&id=LEGACY1", 1)'
FILES = json.dumps({"uid": "UID-HONG", "files": [{"id": "F1", "name": "등록증.png"}]}, ensure_ascii=False)
W.sheets["CUST"] = {TAB: [
    ["순번", "고객명 / 사업자", "금융사", "차종"],
    row("1", "홍길동", "KB캐피탈", "쏘렌토", s=LEGACY, u="UID-HONG", v=FILES),
    row("2", "김철수", "현대캐피탈", "카니발", u="UID-KIM"),
]}

# ------------------------------------------------------------------ [1]
print("[1] 429 면 쉬었다 다시 묻는다 — 그래도 안 되면 한글로 '한도'")
W.quota_429 = 2
r = sheets._http().get(config.SHEETS_VALUES_URL.format(sheet_id="CUST", rng=sheets._rng(TAB, "A1:B2")))
ok("두 번 429 뒤 세 번째에 받는다", r.status_code == 200 and SLEPT == [4, 10], (r.status_code, SLEPT))
ok("한도에 걸린 것을 기억한다(1분)", 50 < sheets.quota_left() <= 60, sheets.quota_left())
SLEPT.clear()
W.quota_429 = 99
r = sheets._http().get(config.SHEETS_VALUES_URL.format(sheet_id="CUST", rng=sheets._rng(TAB, "A1:B2")))
ok("끝까지 429 면 34초만 쉬고 돌려준다", r.status_code == 429 and SLEPT == [4, 10, 20], SLEPT)
try:
    sheets._check(r)
    e = None
except Exception as ex:      # noqa: BLE001
    e = ex
ok("QuotaError · 한글 안내(영어 원문 대신)", isinstance(e, sheets.QuotaError) and "1분에 60번" in str(e)
   and "Quota exceeded" not in str(e), e)
W.quota_429 = 0
SLEPT.clear()
sheets._QUOTA_UNTIL = 0.0
ok("다른 응답은 그대로(쉬지 않는다)", sheets._http().get(
    config.SHEETS_VALUES_URL.format(sheet_id="NOPE", rng="A1")).status_code == 404 and SLEPT == [])

# ------------------------------------------------------------------ [2]
print("[2] S·U·V 를 한 번에 — 격자 밖이면 하나씩")
n0 = len(reads("CUST"))
docs, uids, files = sheets.read_extras(AUTH, "CUST", TAB)
ok("요청 한 번", len(reads("CUST")) == n0 + 1, len(reads("CUST")) - n0)
ok("S 수식 · U 고객ID · V 서류", docs.get(2) == LEGACY and uids == {2: "UID-HONG", 3: "UID-KIM"}
   and files == {2: FILES}, (docs, uids, files))
W.grid_cols["CUST"] = 21              # U 까지만 있는 시트(V 없음)
docs, uids, files = sheets.read_extras(AUTH, "CUST", TAB)
ok("V 가 없으면 — 그림·고객ID 는 읽고 서류는 빈 값", docs.get(2) == LEGACY and uids.get(3) == "UID-KIM" and files == {},
   (docs, uids, files))
W.grid_cols["CUST"] = 20              # T 까지만
docs, uids, files = sheets.read_extras(AUTH, "CUST", TAB)
ok("U 도 없으면 — 그림만", docs.get(2) == LEGACY and uids == {} and files == {})
del W.grid_cols["CUST"]

# ------------------------------------------------------------------ [3]
print("[3] 인증번호 · 프로모션도 같은 한도를 본다")
W.sheets[config.OTP_DEF_SHEET_ID] = {"시트1": [["일시", "", "인증번호"]]}
W.quota_429 = 1
try:
    otp.read_top(AUTH, config.OTP_DEF_SHEET_ID, "시트1")
    e = None
except Exception as ex:      # noqa: BLE001
    e = ex
ok("인증번호 읽기는 쉬지 않고 바로 QuotaError(4초 뒤 또 본다)", isinstance(e, sheets.QuotaError) and SLEPT == [], (e, SLEPT))
W.sheets[config.PROMO_DEF_SHEET_ID] = {config.PROMO_DEF_TAB: [[], [], [], ["", "모델", "차량가"], ["", "E300", "1"]]}
W.quota_429 = 1
try:
    promo.read(AUTH, config.PROMO_DEF_SHEET_ID, config.PROMO_DEF_TAB)
    e = None
except Exception as ex:      # noqa: BLE001
    e = ex
ok("프로모션도 한도면 같은 한글 안내", isinstance(e, sheets.QuotaError) and "1분에 60번" in str(e), e)
sheets._QUOTA_UNTIL = 0.0
n0 = len(reads(config.PROMO_DEF_SHEET_ID))
promo.read(AUTH, config.PROMO_DEF_SHEET_ID, config.PROMO_DEF_TAB)
promo.read(AUTH, config.PROMO_DEF_SHEET_ID, config.PROMO_DEF_TAB)
ok("프로모션 — 병합·탭 번호는 한 번만 묻는다(두 번 읽어 요청 3번)", len(reads(config.PROMO_DEF_SHEET_ID)) - n0 == 3,
   len(reads(config.PROMO_DEF_SHEET_ID)) - n0)

# ------------------------------------------------------------------ [4]
print("[4] 메인 창 — 고객 목록 읽기 요청 수 · 저장 뒤 한 번만 · 한도면 창 없이 저절로 다시")
(config.base_dir() / "google_token.json").write_text(
    json.dumps({"refresh_token": "RT", "scopes": list(config.SCOPE_LABELS)}), encoding="utf-8")
config.remember_account(EMAIL)
config.set_account(EMAIL)
from planner.models import AppSettings  # noqa: E402
_s = AppSettings()
_s.sheet_on, _s.sheet_id, _s.sheet_name = True, "CUST", TAB
_s.otp_on = False
_s.save(config.data_file("plan_cfg.json"))
otp.claim = lambda item, now=None: True
n_start = len(reads("CUST"))
from planner.main_window import MainWindow  # noqa: E402

w = MainWindow()
w.show()
ok("계정 확인", wait(lambda: w._account_verified, 10), w.account_email)
ok("고객 목록이 온다", wait(lambda: w._sheet_loaded and len(w.sheet_rows) == 2 and not w._sheet_loading), len(w.sheet_rows))
pump(0.8)
first = len(reads("CUST")) - n_start
ok("처음 읽기 — 요청 6번 안쪽(예전 8번 · 드롭다운 포함)", first <= 6, first)
hong = next(c for c in w.sheet_rows if c.get("customer") == "홍길동")
ok("그림(S) · 고객ID(U) · 서류(V) 가 줄에 붙는다", hong.values.get("doc") == LEGACY and hong.uid == "UID-HONG"
   and len(hong.files()) == 1, (hong.values.get("doc"), hong.uid, hong.files()))

calls = []
orig_load = w.load_sheet_async
w.load_sheet_async = lambda manual=False: calls.append(manual) or orig_load(manual=manual)
w._reload_after_save(200)
w._reload_after_save(200)
w._reload_after_save(200)
pump(0.6)
ok("잇달아 세 번 저장해도 다시 읽기는 한 번", calls == [False], calls)
ok("다시 읽기가 끝난다", wait(lambda: not w._sheet_loading))
pump(0.5)
n1 = len(reads("CUST"))
w.load_sheet_async(manual=False)
ok("두 번째부터 — 요청 3번(목록 · 안내멘트 · S/U/V), 드롭다운은 30분에 한 번",
   wait(lambda: not w._sheet_loading) and (pump(0.6) or True) and len(reads("CUST")) - n1 == 3, len(reads("CUST")) - n1)
n2 = len(reads("CUST"))
w.load_sheet_async(manual=True)
ok("[불러오기] 를 누르면 드롭다운까지 새로", wait(lambda: not w._sheet_loading) and (pump(0.6) or True)
   and len(reads("CUST")) - n2 >= 4, len(reads("CUST")) - n2)
w.load_sheet_async = orig_load

# 한도 — 창 없이, 저절로 다시
BOXES.clear()
W.quota_429 = 99
sheets.quota_left_orig = sheets.quota_left
w.load_sheet_async(manual=True)
ok("한도면 오류 창을 띄우지 않는다", wait(lambda: getattr(w, "_quota_retries", 0) == 1) and BOXES == [], BOXES)
ok("목록은 그대로 · 상태 줄에 '한도 · 저절로 다시'", len(w.sheet_rows) == 2 and "한도" in w.lbl_cust.text()
   and "다시 읽습니다" in w.lbl_cust.text(), w.lbl_cust.text())
W.quota_429 = 0
sheets._QUOTA_UNTIL = 0.0
w._quota_retries = 0
w.load_sheet_async(manual=False)
ok("풀리면 다시 읽힌다", wait(lambda: not w._sheet_loading and w._quota_retries == 0) and len(w.sheet_rows) == 2)

# 인증번호 — 한도에 걸려 쉬는 동안은 읽지 않는다
w.settings.otp_on = True
w._otp_skip = 0
w._otp_busy = False
sheets.note_quota(30)
n3 = len(reads(config.OTP_DEF_SHEET_ID))
w._poll_otp()
pump(0.3)
ok("한도에 걸린 동안 인증번호는 쉰다", len(reads(config.OTP_DEF_SHEET_ID)) == n3)
sheets._QUOTA_UNTIL = 0.0
W.quota_429 = 1
w._otp_errs = 0
w._poll_otp()
ok("인증번호가 한도에 걸리면 조용히 쉰다(오류로 세지 않는다)", wait(lambda: not w._otp_busy)
   and w._otp_errs == 0 and w._otp_skip == otp.BACKOFF_TICKS, (w._otp_errs, w._otp_skip))
W.quota_429 = 0
sheets._QUOTA_UNTIL = 0.0
w.settings.otp_on = False

pump(0.3)
ok("끝까지 예외가 없다", not ERRS, ERRS[:2])
ok("모르는 주소로 나가지 않는다", not fg.UNKNOWN, fg.UNKNOWN[:5])
w._quitting = True
w.close()
print()
print("실패:", FAIL if FAIL else "없음")
_sys.exit(1 if FAIL else 0)
