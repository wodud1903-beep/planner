"""켤 때 테마 — 설정의 테마로 앱 전체가 칠해지는가(v1.28).

지점장: "업데이트 할때마다 테마가 계속 바뀌어. 설정에는 들어가면 내 테마로 되있으나, 실제로 나오는
테마는 다른테마로 나와서 테마를 바꿔서 설정후 다시 재설정해야 원래테마가 나오고있어."

까닭: app.py 가 계정이 정해지기 전에 **공용 폴더**의 설정으로 앱 전체 배색(스타일시트·팔레트)을
칠하고, 본창은 계정 설정의 테마 이름만 바꿨다. v1.26 부터 지난번 계정 폴더를 바로 열어, 계정이
같으면 다시 칠하지(reload_data → apply_theme) 않아 그대로 남았다.
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
import os as _os
_os.chdir(_ROOT / "python")

import json
import os
import tempfile
import time

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from planner import app as _app_mod  # noqa: E402
from planner import config, google_client, sheets, sync, theme, updater  # noqa: E402
from planner import startup_dialog as _sd  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


ME = "jijum@example.com"
base = config.base_dir()
(base / "plan_cfg.json").write_text(json.dumps({"theme": "light"}), encoding="utf-8")   # 공용 폴더(옛 기본)
acc = base / "accounts" / config._safe(ME)
acc.mkdir(parents=True, exist_ok=True)
(acc / "plan_cfg.json").write_text(json.dumps({"theme": "warm"}), encoding="utf-8")     # 내 설정 — 따뜻한
(base / "last_account.json").write_text(json.dumps({"email": ME}), encoding="utf-8")

print("[1] 켤 때 먼저 그리는 테마(app.py)")
ok("지난번 계정 설정의 테마(따뜻한)", _app_mod._startup_theme() == "warm", _app_mod._startup_theme())
ok("account_file 은 지금 계정을 바꾸지 않는다", config.current_account() == ""
   and config.account_file(ME, "plan_cfg.json") == acc / "plan_cfg.json")
(base / "last_account.json").unlink()
ok("지난번 계정이 없으면 공용 폴더 설정", _app_mod._startup_theme() == "light")
(base / "last_account.json").write_text(json.dumps({"email": ME}), encoding="utf-8")

print("[2] 본창 — 계정 설정의 테마로 앱 전체(스타일시트·팔레트)를 칠한다")
_sd.StartupDialog.show_for = staticmethod(lambda *a, **k: None)
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.warning = staticmethod(lambda *a, **k: None)
google_client.GoogleAuth.is_connected = lambda self: True
google_client.get_user_email = lambda auth, detail=False: ((ME, "") if detail else ME)
sync.sync_now = lambda *a, **k: False
sync.pull = lambda *a, **k: False
sync.push = lambda *a, **k: None
sheets.read_rows = lambda *a, **k: (1, [], [])
updater.check = lambda *a, **k: None
app = QApplication.instance() or QApplication([])
# 예전 app.py 처럼 일부러 다른 테마(공용 폴더의 light)로 앱 전체를 칠해 둔다 — 고쳐졌으면 본창이 바로잡는다
theme.set_theme("light")
theme.apply_to_app(app)
from planner.main_window import MainWindow  # noqa: E402


def pump(sec=0.3):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def painted_as(name):
    theme.set_theme(name)
    want_qss, want_bg = theme.qss(), theme.c("window_bg").lower()
    return want_qss, want_bg


w = MainWindow()
cur = theme.theme_name()
ok("설정의 테마(따뜻한)", w.settings.theme == "warm" and cur == "warm", (w.settings.theme, cur))
q_now, bg_now = app.styleSheet(), app.palette().color(QPalette.Window).name().lower()
want_qss, want_bg = painted_as("warm")
ok("앱 전체 스타일시트도 따뜻한 테마", q_now == want_qss)
ok("앱 전체 팔레트(바탕색)도 따뜻한 테마", bg_now == want_bg, (bg_now, want_bg))
theme.set_theme("warm")
w.show()
pump(0.5)
w._on_account_ready(ME, "")            # 인터넷으로 같은 계정 확인 — v1.26 부터 다시 칠하지 않는 길
pump(0.5)
ok("같은 계정으로 확인된 뒤에도 그대로 따뜻한 테마", app.styleSheet() == want_qss and theme.theme_name() == "warm")
w.hide()

print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
