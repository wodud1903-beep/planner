"""묻지 않는 자동 업데이트(v1.26) — 지점장 요청:
"업데이트 할건지 물어보고있는데, 묻지않고 업데이트가 있으면 자동으로 프로그램이 업데이트 되도록".

  · 켤 때 · [업데이트 확인] · 켜 둔 동안(3시간마다) — 어느 때도 묻는 창이 없다
  · 켜 둔 채로 찾은 새 판은 '쓰지 않을 때' 바꾼다(창이 숨었거나 PC 를 3분 넘게 안 만짐 · 편집 창 없음)
  · 트레이에 숨어 있었으면 다시 켜질 때도 트레이로(update_resume.json)
  · 지난 업데이트가 실패했어도 창 대신 알림으로만
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

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

from planner import config, google_client, sheets, sync, theme, updater  # noqa: E402
from planner import startup_dialog as _sd  # noqa: E402

_sd.StartupDialog.show_for = staticmethod(lambda *a, **k: None)
ASKED = []
QMessageBox.question = staticmethod(lambda *a, **k: ASKED.append(("question", a[2] if len(a) > 2 else "")))
QMessageBox.information = staticmethod(lambda *a, **k: ASKED.append(("info", a[2] if len(a) > 2 else "")))
QMessageBox.warning = staticmethod(lambda *a, **k: ASKED.append(("warning", a[2] if len(a) > 2 else "")))
FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name
          + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


app = QApplication.instance() or QApplication([])
theme.apply_to_app(app)
google_client.GoogleAuth.is_connected = lambda self: False
sync.sync_now = lambda *a, **k: False
sheets.read_rows = lambda *a, **k: (1, [], [])
REL = {"version": "9.9.9", "asset_url": "https://example/asset", "notes": "고친 것"}
updater.check = lambda *a, **k: dict(REL)
updater.is_frozen = lambda: True
IDLE = {"sec": 5.0}
updater.idle_seconds = lambda: IDLE["sec"]

from planner.main_window import MainWindow  # noqa: E402

STARTED = []
MainWindow._start_update_real = MainWindow._start_update


def fake_start(self, res, manual):
    updater.mark_resume(tray=not self.isVisible())
    STARTED.append((res["version"], manual))


MainWindow._start_update = fake_start
TOASTS = []


def pump(sec=0.5):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


print("[1] 켤 때 — 묻지 않고 받는다")
w = MainWindow()
w.sig_toast.connect(lambda t, m: TOASTS.append(m))
w.show()
pump(5.0)                                   # 켜고 4초 뒤 저절로 확인한다 — 그 길을 그대로 본다
ok("새 판이면 바로 받는다(창 없이)", STARTED == [("9.9.9", False)] and not ASKED, (STARTED, ASKED))
ok("받는다고 진행 창(막대)으로 — 알림 창 없이(v1.27)", w._upd_prog is not None and w._upd_prog.isVisible()
   and w._upd_prog.state == "download" and not ASKED, (getattr(w, "_upd_prog", None), ASKED))

print("[2] [업데이트 확인] 을 눌러도 묻지 않는다")
w._auto_updating = False
STARTED.clear()
ASKED.clear()
w.check_update(manual=True)
pump(0.8)
ok("눌렀으면 바로 받는다 — '지금 업데이트할까요?' 를 묻지 않는다",
   STARTED == [("9.9.9", True)] and not [a for a in ASKED if a[0] == "question"], (STARTED, ASKED))

print("[3] 켜 둔 동안(3시간마다) — 쓰는 중이면 미루고, 안 쓸 때 바꾼다")
ok("켜 둔 동안 다시 확인하는 시계(3시간)", w._upd_timer.isActive()
   and w._upd_timer.interval() == 3 * 3600 * 1000, w._upd_timer.interval())
updater.clear_attempt_if_done("0")
for f in ("update_attempt.json",):
    try:
        (config.base_dir() / f).unlink()
    except OSError:
        pass
w._auto_updating = False
STARTED.clear()
IDLE["sec"] = 10.0                          # 지금 쓰는 중
w.check_update(manual=False, periodic=True)
pump(0.8)
ok("창이 보이고 PC 를 쓰는 중이면 바꾸지 않는다(미룬다)", STARTED == [] and w._pending_update is not None
   and w._upd_idle_timer.isActive(), STARTED)
dlg = QDialog(w)
dlg.setModal(True)
dlg.show()
pump(0.2)
IDLE["sec"] = 600.0
w._try_pending_update()
ok("편집 창(모달)이 떠 있으면 기다린다", STARTED == [], STARTED)
dlg.close()
pump(0.2)
w._try_pending_update()
ok("3분 넘게 안 쓰면 그때 바꾼다", STARTED == [("9.9.9", False)], STARTED)
ok("다시 켜질 때 창으로(보이던 창)", updater.take_resume_tray() is False)

print("[4] 트레이에 숨어 있으면 바로 — 다시 켜질 때도 트레이로")
w._auto_updating = False
STARTED.clear()
try:
    (config.base_dir() / "update_attempt.json").unlink()
except OSError:
    pass
w.hide()
IDLE["sec"] = 1.0                           # PC 는 쓰는 중이어도 이 창은 숨어 있다
w.check_update(manual=False, periodic=True)
pump(0.8)
ok("숨어 있으면 바로 바꾼다", STARTED == [("9.9.9", False)], STARTED)
ok("새 판은 트레이로 켜진다(표시를 남긴다)", updater.take_resume_tray() is True)
ok("표시는 한 번 읽으면 지운다", updater.take_resume_tray() is False)

print("[5] 같은 판이 두 번 실패하면 그만(켤 때마다 꺼졌다 켜지지 않게) — 알림으로만")
w._auto_updating = False
STARTED.clear()
ASKED.clear()
TOASTS.clear()
updater.note_attempt("9.9.9")
updater.note_attempt("9.9.9")
w.check_update(manual=False)
pump(0.8)
ok("두 번 실패한 판은 다시 하지 않는다", STARTED == [])
ok("창이 아니라 알림으로", not ASKED and any("건너뜁니다" in t for t in TOASTS), (ASKED, TOASTS))
(config.base_dir() / "update_status.txt").write_text("fail locked", encoding="utf-8")
ASKED.clear()
TOASTS.clear()
w._update_failed = "locked"
w._tell_update_failure()
ok("지난 업데이트 실패도 창 없이 알림으로", not ASKED and TOASTS and "잠겨" in TOASTS[-1], (ASKED, TOASTS))
w.hide()

print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
