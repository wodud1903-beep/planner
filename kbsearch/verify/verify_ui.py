"""화면 — 로그인 없이 편집·저장, 설정 세 가지, 빠른검색, [동기화] 흐름.

Qt 창을 실제로 띄운다(화면이 없으면 offscreen). 구글은 fake_google 로 흉내 낸다.
"""
import pathlib as _pl
import sys as _sys

_HERE = _pl.Path(__file__).resolve().parent
_sys.path.insert(0, str(_HERE.parent))
_sys.path.insert(0, str(_HERE))

import json  # noqa: E402
import os  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QMimeData, QTimer  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton  # noqa: E402

app = QApplication.instance() or QApplication([])

from fake_google import FakeGoogle  # noqa: E402
from kbsearch import config, kb, kb_files, theme  # noqa: E402
from kbsearch.main_window import MainWindow  # noqa: E402
from kbsearch.settings import Settings  # noqa: E402
from kbsearch.settings_dialog import SettingsDialog  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name
          + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


def pump(sec=0.2):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def later(fn, ms=50):
    """모달 창이 뜬 뒤에 할 일 — exec() 안에서 돈다."""
    QTimer.singleShot(ms, fn)


def modal():
    return QApplication.activeModalWidget()


def click(*texts):
    """뜬 창에서 차례로 단추를 누른다(다음 창이 뜨면 거기서 다음 것을)."""
    m = modal()
    names = [b.text() for b in m.findChildren(QPushButton)] if m else []
    for b in (m.findChildren(QPushButton) if m else []):
        if b.text() == texts[0]:
            if texts[1:]:
                later(lambda: click(*texts[1:]))
            b.click()
            return
    ok(f"'{texts[0]}' 단추가 있다", False, names)
    if m:
        m.reject()                  # 못 찾으면 창을 닫아 검사가 멈추지 않게


# 알림 창(information·warning)은 띄우지 않고 적어 둔다 — 검사가 그 창에서 멈추지 않게
NOTICES = []
QMessageBox.information = staticmethod(lambda *a, **k: NOTICES.append(a[2]) or QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: NOTICES.append(a[2]) or QMessageBox.Ok)

w = MainWindow(Settings.load())
w.show_window()
pump()

print("[1] 처음 — 로그인 없이")
ok("자료가 보인다(기본 자료)", len(w.view.items) == len(kb.SAMPLE))
ok("로그인 안 함 안내", "로그인 안 함" in w.lbl_account.text())
ok("[동기화] 단추", w.btn_sync.isVisible() and w.btn_sync.text() == "동기화")
ok("로그아웃은 숨김", not w.btn_logout.isVisible())

print("[2] [자료 편집] — 로그인 없이 메모 + 그림 첨부")
img = QImage(30, 20, QImage.Format_RGB32)
img.fill(QColor("#2563EB"))


def do_edit():
    d = modal()
    ok("관리자가 아니면 '내 메모' 묶음만", d.cmb_src.count() == 1)
    d._add()
    d.ed_title.setText("내 전자약정 메모")
    d.txt_body.setPlainText("내가 적은 본문")
    md = QMimeData()
    md.setImageData(img)
    d.drop_attachments(md)
    ok("첨부 한 개 들어옴", d.lst_att.count() == 1)
    d._ok()


later(do_edit)
w.edit()
pump()
mine = kb.load_mine()
ok("이 PC 에 저장", [x["title"] for x in mine] == ["내 전자약정 메모"])
att = (mine[0].get("files") or [{}])[0]
ok("첨부는 이 PC 에만(local-)", str(att.get("id", "")).startswith(kb_files.LOCAL_PREFIX))
ok("첨부 파일이 PC 에 있다", kb_files.cached(att) is not None)
ok("동기화 점", w.btn_sync.text() == "동기화 ●")
w.view.ed_find.setText("ㄴ ㅈㅈㅇㅈ ㅁㅁ")
pump(0.1)
ok("초성으로 바로 찾음", w.view.lst.count() >= 1 and
   "내 전자약정 메모" in w.view.lst.item(0).text())

print("[3] 빠른검색 — Enter 로 본문 복사")
w.open_quick()
pump(0.1)
q = w._quick
q.view.ed_find.setText("내 전자약정")
pump(0.1)
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
q.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
pump(0.1)
ok("본문이 복사됨", QGuiApplication.clipboard().text() == "내가 적은 본문")
ok("창이 닫힘", not q.isVisible())

print("[4] 설정 — 세 가지만")
d = SettingsDialog(w.settings, hot_ok=True, parent=w)
groups = [g.title() for g in d.findChildren(__import__("PySide6.QtWidgets").QtWidgets.QGroupBox)]
ok("시작프로그램 · 테마 · 빠른검색 단축키", groups == ["시작 프로그램", "화면 테마", "업무자료 빠른검색 단축키"],
   groups)
d.chk_ctrl.setChecked(False)
d.chk_alt.setChecked(False)
d.chk_shift.setChecked(False)
d._ok()
ok("조합키 없이 단축키는 막는다", d.result() == 0 and "Ctrl" in d.lbl_hot.text())


def do_settings():
    s = modal()
    s.cmb_theme.setCurrentIndex(s.cmb_theme.findData("dark"))
    s.cmb_key.setCurrentIndex(s.cmb_key.findText("G"))
    s._ok()


later(do_settings)
w.open_settings()
pump()
saved = json.loads(config.data_file("settings.json").read_text(encoding="utf-8"))
ok("테마 저장·적용", saved["theme"] == "dark" and theme.is_dark())
ok("단축키 저장", saved["kb_hot_key"] == "G" and w.settings.hotkey_text() == "Ctrl+Alt+G")

print("[5] [동기화] — 로그인을 묻고, 아니오면 아무것도 안 한다")
asked = []
_q = QMessageBox.question
QMessageBox.question = staticmethod(lambda *a, **k: (asked.append(a[2]), QMessageBox.No)[1])
w.sync_clicked()
QMessageBox.question = _q
ok("로그인할지 묻는다", asked and "로그인" in asked[0])
ok("로그인 안 시작", w._login_cancel is None)

print("[6] 로그인된 뒤 [동기화] — 첨부 올리고 메모를 묶음에")
g = FakeGoogle().install()
g.kb_rows = [["캐피탈", "신한", "신한 전자약정", "", "시트 본문", ""]]
w.gauth.refresh_token = "r"
w.gauth.email = "staff@example.com"
w.gauth.valid_token = lambda: "tok"
w.refresh_account()
ok("계정 표시 · 로그아웃 보임", "staff@example.com" in w.lbl_account.text() and w.btn_logout.isVisible())
w.sync_clicked()
for _ in range(100):
    pump(0.05)
    if not w._busy:
        break
ok("동기화 완료 안내", "동기화 완료" in w.lbl_msg.text(), w.lbl_msg.text())
ok("공통 자료가 시트 것으로", [x["title"] for x in kb.load_shared()] == ["신한 전자약정"])
ok("첨부를 올렸다", g.files and not str(kb.load_mine()[0]["files"][0]["id"]).startswith("local-"))
ok("점이 꺼짐 · 마지막 동기화", w.btn_sync.text() == "동기화" and "마지막 동기화" in w.lbl_account.text())
ok("화면도 새 자료", any(x["title"] == "신한 전자약정" for x in w.view.items))

print("[7] 관리자 — 고친 공통 자료는 올릴지 묻는다")
w.gauth.email = "wodud1903@gmail.com"
kb.save_shared([{"title": "관리자가 고친 것", "body": "b"}], edited=True)
# 계정이 바뀌었으니 메모를 어떻게 할지 먼저 묻고, 그다음 공통 자료를 올릴지 묻는다
later(lambda: click("합쳐서 wodud1903@gmail.com 에도 올리기", "시트로 올리기"))
w.sync_clicked()
for _ in range(100):
    pump(0.05)
    if not w._busy:
        break
ok("시트로 올림", g.put_values and g.put_values[1][2] == "관리자가 고친 것", w.lbl_msg.text())
ok("계정이 바뀐 것을 알린다", any("이전 계정" in n for n in NOTICES), NOTICES[-1:])

print("[8] 다른 계정으로 바꾸면 메모를 어떻게 할지 묻는다")
w.gauth.email = "other@example.com"
later(lambda: click("취소"))
w.sync_clicked()
pump(0.2)
ok("취소하면 동기화 안 함", "취소" in w.lbl_msg.text() and not w._busy)

print("[9] 업데이트 — 다른 창이 떠 있으면 잠시 미룬다")
from kbsearch import update_ui  # noqa: E402
shown = []
_run = update_ui.UpdateDialog.run
update_ui.UpdateDialog.run = classmethod(lambda cls, info, parent=None: shown.append(info) or update_ui.QUIT)
import kbsearch.main_window as mw  # noqa: E402
mw.UpdateDialog = update_ui.UpdateDialog
_am = QApplication.activeModalWidget
QApplication.activeModalWidget = staticmethod(lambda: w)
w._on_update({"version": "9.9.9"}, "", False)
ok("모달이 있으면 안 띄움", shown == [])
QApplication.activeModalWidget = _am
quit_called = []
w.quit_app = lambda: quit_called.append(1)
w._on_update({"version": "9.9.9"}, "", False)
ok("없으면 업데이트 창 → 종료(건너뛰기 없음)", shown and quit_called)
update_ui.UpdateDialog.run = _run

print("[10] 동기화를 끈 판(SYNC_ON=False)")
config.SYNC_ON = False
w.refresh_account()
ok("[동기화] 가 사라진다", not w.btn_sync.isVisible() and "이 PC 에만" in w.lbl_account.text())
config.SYNC_ON = True

print()
print("실패:", FAIL if FAIL else "없음")
_sys.exit(1 if FAIL else 0)
