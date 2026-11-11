"""v1.32.1 — 직원 계정 설정이 켤 때마다 초기화되던 것(지점장 보고).

원인: 설정 창 **안에서** 구글 로그인하면 계정을 다시 확인하지 않아, 고친 설정이 공용(또는 앞사람) 폴더에
저장됐다. 다음에 켜면 그 계정 폴더로 옮겨 가는데, 로그인 전에 만들어진 기본 설정이 '더 최신' 으로 보여
구글 계정에 있던 설정을 받지 않고 오히려 기본값으로 덮어 올렸다.

여기서는 가짜 구글로 메인 창을 실제로 여러 번 켜며 본다(PC 1차 저장 · 구글 계정 2차 저장 · 자동 불러오기).
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
import shutil
import tempfile
import threading
import time
import traceback

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
tempfile.tempdir = tempfile.mkdtemp()

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import fake_google as fg  # noqa: E402

FAIL, ERRS = [], []
_sys.excepthook = lambda t, v, tb: (ERRS.append("".join(traceback.format_exception(t, v, tb))),
                                    traceback.print_exception(t, v, tb))
threading.excepthook = lambda a: ERRS.append("".join(traceback.format_exception(a.exc_type, a.exc_value, a.exc_traceback)))


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


from planner import (account_settings, config, google_client, kb_files, models, net, otp,  # noqa: E402
                     settings_dialog, sheets, sync, theme)
from planner import startup_dialog as _sd  # noqa: E402

W = fg.World("staff@example.com")
_sd.StartupDialog.show_for = staticmethod(lambda *a, **k: None)
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: None))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
for mod in (net, google_client, sheets, kb_files):
    for attr in ("http", "_http"):
        if hasattr(mod, attr):
            setattr(mod, attr, lambda: fg.Session(W))
google_client.GoogleAuth.valid_token = lambda self: "AT"
otp.claim = lambda *a, **k: True


def fake_authorize(self, timeout_sec=120, extra_scopes=None):
    self.refresh_token = "RT"
    self.scopes = list(config.SCOPE_LABELS)
    self._save()


google_client.GoogleAuth.authorize = fake_authorize
W.sheets["STAFFSHEET"] = {"내고객": [["순번", "고객명 / 사업자"], ["1", "홍길동"]]}
W.sheets["BOSSSHEET"] = {"지점장": [["순번", "고객명 / 사업자"], ["1", "김사장"]]}
app = QApplication.instance() or QApplication([])
theme.apply_to_app(app)

from planner.main_window import MainWindow  # noqa: E402


def pump(sec):
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


OPEN = []


def boot():
    """프로그램을 켠다(앞의 창은 닫는다 — PC 를 다시 켠 것과 같다)."""
    for w in OPEN:
        w._quitting = True
        w.hide()
        w.deleteLater()
    OPEN.clear()
    pump(0.3)
    config.set_account("")
    w = MainWindow()
    w.show()
    OPEN.append(w)
    pump(1.5)
    return w


def wipe_pc():
    """PC 를 지웠다(새 PC · 복원 프로그램) — 이 PC 의 저장은 없고 구글 계정만 남는다."""
    shutil.rmtree(config.base_dir(), ignore_errors=True)


def dialog(w, script):
    settings_dialog.SettingsDialog.exec = lambda self: script(self)
    w.on_settings_click()


def enter(d, sid="STAFFSHEET", tab="내고객", folder=r"G:\내 드라이브\영업\고객정보"):
    d.chk_sheet.setChecked(True)
    d.ed_sheet_id.setText(f"https://docs.google.com/spreadsheets/d/{sid}/edit")
    d.ed_sheet_name.setText(tab)
    d.ed_files_dir.setText(folder)


def bundle_cfg():
    f = W.appdata.get("planner_sync.json")
    return json.loads(json.loads(f["content"])["files"]["plan_cfg.json"]) if f else {}


def acct_file():
    f = W.appdata.get("account_settings.json")
    return json.loads(f["content"]) if f else {}


S = lambda w: (w.settings.sheet_id, w.settings.sheet_name, w.settings.files_dir)  # noqa: E731
WANT = ("STAFFSHEET", "내고객", r"G:\내 드라이브\영업\고객정보")

print("[1] 새 PC — 설정 창 안에서 로그인하고 바로 시트·탭·서류 폴더를 정한다")
w = boot()
ok("처음엔 로그인 전", not w.gauth.is_connected() and not w._account_verified)


def s1(d):
    d._on_login_click()
    pump(0.5)
    enter(d)
    d._on_ok()
    return d.result()


dialog(w, s1)
ok("닫으면 그 계정을 확인하고 그 계정 폴더로 옮긴다(예전엔 확인하지 않았다)",
   wait(lambda: w._account_verified and config.current_account() == "staff@example.com"), config.current_account())
ok("고친 설정이 그 계정 폴더에 저장된다", wait(lambda: S(w) == WANT and models.AppSettings.load(
    config.base_dir() / "accounts" / "staff@example.com" / "plan_cfg.json").sheet_id == "STAFFSHEET"), S(w))
ok("2차 — 구글 계정 설정 파일에 올라간다", wait(lambda: acct_file().get("sheet", {}).get("id") == "STAFFSHEET"), acct_file())
w.sync_now_async()
ok("2차 — 동기화 묶음(모든 설정)에도", wait(lambda: bundle_cfg().get("sheetId") == "STAFFSHEET"))

print("[2] 다시 켠다(×3) — 그대로")
for i in range(3):
    w = boot()
    ok(f"{i + 1}번째 — 시트·탭·서류 폴더 그대로", wait(lambda: w._account_verified) and S(w) == WANT, S(w))

print("[3] PC 를 지웠다 → 설정 창에서 로그인만 하고 [확인] — 구글 계정에서 저절로 불러온다")
wipe_pc()
w = boot()
ok("지운 PC — 아무것도 없다", S(w) == ("", config.DEF_SHEET_NAME, ""), S(w))


def s3(d):
    d._on_login_click()
    pump(0.5)
    d._on_ok()                       # 아무것도 고치지 않고 [확인] — 예전엔 기본값을 저장해 계정 것을 덮었다
    return d.result()


dialog(w, s3)
ok("로그인 후 저절로 불러온다", wait(lambda: S(w) == WANT), S(w))
ok("구글 계정의 설정을 기본값으로 덮어 올리지 않는다", bundle_cfg().get("sheetId") == "STAFFSHEET" and
   acct_file().get("sheet", {}).get("id") == "STAFFSHEET")
w = boot()
ok("다시 켜도 그대로", wait(lambda: w._account_verified) and S(w) == WANT, S(w))

print("[4] 묶음의 설정이 이미 빈 값으로 덮여 있어도(예전 판이 망가뜨린 것) — 계정 설정 파일에서 되살린다")
f = W.appdata["planner_sync.json"]
b = json.loads(f["content"])
c = json.loads(b["files"]["plan_cfg.json"])
c.update(sheetId="", sheetName=config.DEF_SHEET_NAME, filesDir="")
c.pop("sheetAt", None)
c.pop("folderAt", None)
b["files"]["plan_cfg.json"] = json.dumps(c)
b["times"]["plan_cfg.json"] = "2099-01-01T00:00:00Z"
f["content"] = json.dumps(b)
wipe_pc()
w = boot()
w.on_google_login_click()
ok("메인 창에서 로그인 — 시트·탭을 계정 설정 파일에서 받는다", wait(lambda: S(w)[:2] == WANT[:2]), S(w))
ok("서류 폴더는 '내 드라이브' 기준 이름으로(이 PC 에 그 폴더가 없으면 인터넷으로 읽기용)",
   w.settings.files_drive_folder == "고객정보" and w.settings.files_dir == "", (w.settings.files_dir, w.settings.files_drive_folder))
w.sync_now_async()
ok("되살린 것을 다시 묶음에 올린다", wait(lambda: bundle_cfg().get("sheetId") == "STAFFSHEET"))

print("[5] 관리자가 쓰던 PC 에서 설정 창으로 직원 계정으로 바꾼다 — 관리자 설정을 덮지 않는다")
wipe_pc()
W.email = "boss@example.com"
W.appdata.clear()
w = boot()


def s5a(d):
    d._on_login_click()
    pump(0.5)
    enter(d, "BOSSSHEET", "지점장", r"G:\내 드라이브\지점")
    d._on_ok()
    return d.result()


dialog(w, s5a)
ok("관리자 설정", wait(lambda: S(w)[0] == "BOSSSHEET" and config.current_account() == "boss@example.com"), S(w))
boss_drive = dict(W.appdata)
w._sync_timer.stop() if hasattr(w, "_sync_timer") else None
W.appdata = {}                       # 직원 계정의 드라이브(비어 있다)


def s5b(d):
    d._on_login_click()              # 연결 해제
    ok("로그아웃하는 그 순간부터 지금 폴더로 동기화하지 않는다", not w._account_verified)
    W.email = "staff@example.com"
    d._on_login_click()              # 직원으로 로그인
    pump(0.5)
    enter(d)
    d._on_ok()
    return d.result()


dialog(w, s5b)
ok("직원 계정 폴더로 옮겨 그 설정으로", wait(lambda: config.current_account() == "staff@example.com" and S(w) == WANT), S(w))
boss = models.AppSettings.load(config.base_dir() / "accounts" / "boss@example.com" / "plan_cfg.json")
ok("관리자 폴더의 설정은 그대로", (boss.sheet_id, boss.sheet_name) == ("BOSSSHEET", "지점장"), (boss.sheet_id, boss.sheet_name))
w.sync_now_async()
pump(2)
ok("직원 드라이브에 관리자 설정이 올라가지 않는다", bundle_cfg().get("sheetId") == "STAFFSHEET"
   and "BOSSSHEET" not in json.dumps(W.appdata, ensure_ascii=False))
w = boot()
ok("다시 켜면 직원 계정 · 직원 설정", wait(lambda: w._account_verified) and config.current_account() == "staff@example.com"
   and S(w) == WANT, (config.current_account(), S(w)))

print("[6] 설정 합치기 규칙(계산)")
new = {"sheetId": "", "sheetName": "미출고차량", "filesDir": "", "filesDriveFolder": "고객정보", "theme": "dark",
       "monthlyLast": "2026-09"}
old = {"sheetId": "S1", "sheetName": "탭", "sheetOn": True, "filesDir": "G:\\x", "filesDriveFolder": "x",
       "sheetAt": "2026-11-01T00:00:00Z", "theme": "light", "monthlyLast": "2026-10", "branchCal": "b@g"}
m = sync.merge_cfg(new, old)
ok("빈 시트·폴더는 값 있는 쪽 · 다른 칸(테마)은 최신 쪽 · 월 마감은 늦은 달 · 지점 캘린더도",
   (m["sheetId"], m["sheetName"], m["filesDir"], m["theme"], m["monthlyLast"], m["branchCal"])
   == ("S1", "탭", "G:\\x", "dark", "2026-10", "b@g"), m)
m = sync.merge_cfg(dict(new, sheetAt="2026-11-05T00:00:00Z"), old)
ok("일부러 지웠으면(바꾼 때가 더 나중) 지운 것이 이긴다", m["sheetId"] == "", m)
m = sync.merge_cfg(dict(new, sheetId="S2", sheetName="새탭"), old)
ok("양쪽 다 값이 있으면 최신 쪽", (m["sheetId"], m["sheetName"]) == ("S2", "새탭"))
st = models.AppSettings()
ok("계정 설정 받기 — 이 PC 가 나중에 바꾼 것은 덮지 않는다",
   account_settings.adopt(models.AppSettings(sheet_id="MINE", sheet_at="2026-12-01T00:00:00Z"),
                          {"sheet": {"id": "WEB", "tab": "t", "at": "2026-11-01T00:00:00Z"}}) == [])
st = models.AppSettings(sheet_id="OLD", sheet_at="2026-10-01T00:00:00Z")
ok("계정 것이 나중이면 받는다(웹에서 바꾼 시트)", account_settings.adopt(
    st, {"sheet": {"id": "WEB", "tab": "t", "at": "2026-11-01T00:00:00Z"}}) == ["sheet"] and st.sheet_id == "WEB")
st = models.AppSettings()
account_settings.adopt(st, {"folder": {"ref": "https://drive.google.com/drive/folders/1AbC_dEf-123", "at": "t"}})
ok("폴더 링크면 폴더 id 로", st.files_drive_folder == "1AbC_dEf-123", st.files_drive_folder)

pump(0.5)
ok("끝까지 예외가 없다", not ERRS, ERRS[:1])
print()
print("실패:", FAIL if FAIL else "없음")
for w in OPEN:
    w._quitting = True
os._exit(1 if FAIL else 0)
