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

# 진짜 구글에 나가지 않게 가짜를 먼저 끼운다(켜자마자 공통 자료를 저절로 받으러 간다).
# 처음엔 시트 탭이 없는 것으로 — 받아도 바뀌는 게 없다.
g0 = FakeGoogle().install()
g0.tab = False
# 부팅 직후를 흉내 낸다 — 윈도의 monotonic 은 PC 를 켠 뒤부터 세서 처음엔 작다
import kbsearch.main_window as _mw  # noqa: E402
_real_mono = _mw.time.monotonic
_mw.time.monotonic = lambda: 30.0

w = MainWindow(Settings.load())
w.show_window()
pump(2.0)

_mw.time.monotonic = _real_mono

print("[1] 처음 — 로그인 없이")
ok("켜자마자 공통 자료를 받으러 간다(로그인 없이 · 부팅 직후에도)", g0.public_reads == 1,
   g0.public_reads)
ok("시트가 비었으면 기본 자료 그대로", len(w.view.items) == len(kb.SAMPLE))
ok("로그인 안 함 안내", "로그인 안 함" in w.lbl_account.text())
ok("[동기화] 단추", w.btn_sync.isVisible() and w.btn_sync.text() == "동기화")
ok("로그아웃은 숨김", not w.btn_logout.isVisible())

print("[2] [자료 편집] — 로그인 없이 메모 + 그림 첨부")
img = QImage(30, 20, QImage.Format_RGB32)
img.fill(QColor("#2563EB"))


def do_edit():
    d = modal()
    srcs = [d.cmb_src.itemData(i) for i in range(d.cmb_src.count())]
    ok("관리자가 아니면 '공통 — 이 PC 에서만' · '내 메모' 묶음", srcs == [kb.SRC_LOCAL, kb.SRC_MINE], srcs)
    d.cmb_src.setCurrentIndex(d.cmb_src.findData(kb.SRC_MINE))
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
pump(0.3)                               # 검색은 타자가 멎은 뒤(120ms) 한 번
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

print("[11] 로그인 없이 — 관리자가 일정관리기에서 고친 공통 자료·첨부가 저절로 온다")
w.gauth.disconnect()
w.refresh_account()
g = FakeGoogle().install()
g.kb_rows = [["캐피탈", "메리츠", "메리츠캐피탈", "", "메리츠 본문", ""]]
png = b"\x89PNG\r\n\x1a\n" + b"m" * 300
g.files["PUB1"] = png
g.public.add("PUB1")                    # 공통 자료의 첨부는 '링크가 있는 누구나 보기'
att = {"id": "PUB1", "name": "법인전자약정1.png", "mime": "image/png", "size": len(png)}
g.kb_g = [json.dumps({"title": "메리츠캐피탈", "files": [att]}, ensure_ascii=False)]
w.auto_pull()
for _ in range(60):
    pump(0.05)
    if not w._pulling:
        break
pump(0.2)
ok("새 자료가 화면에", any(x["title"] == "메리츠캐피탈" for x in w.view.items))
ok("안내", "새로 받았습니다" in w.lbl_msg.text(), w.lbl_msg.text())
ok("아래 줄에 받은 때", "공통 자료 자동 받음" in w.lbl_account.text(), w.lbl_account.text())
w.view.ed_find.setText("메리츠")
w.view.flush_search()
pump(0.5)
ok("첨부를 로그인 없이 받는다(공개 주소)", kb_files.cached(att) is not None)
ok("첨부 줄에 보인다", w.view.lst_att.count() == 1)
kb.save_shared(kb.load_shared() + [{"title": "관리자 수정", "body": "b"}], edited=True)
g.kb_rows = [["캐피탈", "", "시트 새것", "", "", ""]]
w.auto_pull()
for _ in range(60):
    pump(0.05)
    if not w._pulling:
        break
ok("이 PC 에서 고친 공통 자료가 있으면 덮어쓰지 않는다",
   any(x["title"] == "관리자 수정" for x in kb.load_shared()))
ok("멈춘 까닭을 보여 준다", "자동 받기 멈춤" in w.lbl_account.text())
kb.update_meta(shared_dirty=False)
n = g.public_reads
w._pulled_at = None
w.show_window()
for _ in range(60):
    pump(0.05)
    if not w._pulling:
        break
ok("창을 열 때 오래됐으면 다시 받는다", g.public_reads == n + 1)
ok("받은 것으로 바뀜", [x["title"] for x in kb.load_shared()] == ["시트 새것"])
n = g.public_reads
w.show_window()
pump(0.2)
ok("방금 받았으면 또 받지 않는다", g.public_reads == n)
g.public_csv = "html"
w._pulled_at = None
kb.update_meta(shared_at="")
w.auto_pull()
for _ in range(60):
    pump(0.05)
    if not w._pulling:
        break
ok("못 받아도 창을 띄우지 않고 조용히 알린다", "받지 못함" in w.lbl_account.text()
   and not any("받지 못" in n_ for n_ in NOTICES[-1:]))
config.SYNC_ON = False
n = g.public_reads
w.auto_pull()
pump(0.2)
ok("동기화를 끈 판은 받으러 가지 않는다", g.public_reads == n)
config.SYNC_ON = True

print("[12] 로그인 없이 — 회사 공통 자료(팩스번호)를 이 PC 에서만 고친다")
FAX_OLD, FAX_NEW = "0504-214-5287", "0504-000-1111"
g.public_csv = "ok"
g.kb_rows = [["심사서류", "", "개인 심사서류", "", f"1. 면허증\n팩스- {FAX_OLD}", "면허증"],
             ["캐피탈", "메리츠", "메리츠캐피탈", "", "메리츠 본문", ""]]
g.kb_g = []
w._pulled_at = None
w.auto_pull()
for _ in range(60):
    pump(0.05)
    if not w._pulling:
        break
ok("시트 자료를 받음", [x["title"] for x in kb.load_shared()] == ["개인 심사서류", "메리츠캐피탈"])
w.view.ed_find.setText("개인 심사서류")
w.view.flush_search()
pump(0.2)
seen = {}


def do_local_edit():
    d = modal()
    seen["src"] = d.cmb_src.currentData()
    seen["title"] = d.ed_title.text()
    seen["btns"] = (d.b_add.isEnabled(), d.b_del.isEnabled(), d.b_revert.isVisible())
    d.txt_body.setPlainText(f"1. 면허증\n팩스- {FAX_NEW}")
    md = QMimeData()
    md.setImageData(img)
    d.drop_attachments(md)
    d._ok()


later(do_local_edit)
w.edit()
pump()
ok("보던 공통 자료가 '이 PC 에서만' 묶음으로 열린다",
   seen.get("src") == kb.SRC_LOCAL and seen.get("title") == "개인 심사서류", seen)
ok("추가·삭제는 막고 [회사 자료로 되돌리기] 를 보인다", seen.get("btns") == (False, False, True), seen)
ok("원본(공통 자료)은 그대로", FAX_OLD in kb.load_shared()[0]["body"]
   and not kb.load_meta().get("shared_dirty"))
rec = kb.load_local()
ok("이 PC 에만 적힘 · 첨부도 이 PC 에", len(rec) == 1 and FAX_NEW in rec[0]["item"]["body"]
   and str(rec[0]["item"]["files"][0]["id"]).startswith(kb_files.LOCAL_PREFIX))
lat = rec[0]["item"]["files"][0] if rec else {}
ok("첨부 파일이 PC 에 있다", kb_files.cached(lat) is not None)
ok("저장 안내", "이 PC 에서만" in w.lbl_msg.text(), w.lbl_msg.text())
w.view.ed_find.setText("개인 심사서류")
w.view.flush_search()
pump(0.3)
cur = w.view.lst.current_item_data() or {}
ok("검색 화면은 고친 팩스번호 · '이 PC 에서 고침' 배지", FAX_NEW in cur.get("body", "")
   and "이 PC 에서 고침" in w.view.lbl_title.text(), w.view.lbl_title.text())
ok("아래 줄에 건수", "이 PC 에서만 고친 공통 자료 1건" in w.lbl_account.text(), w.lbl_account.text())

g.kb_rows[0][4] = f"1. 면허증\n2. 등본\n팩스- {FAX_OLD}"
w._pulled_at = None
w.auto_pull()
for _ in range(60):
    pump(0.05)
    if not w._pulling:
        break
w.view.ed_find.setText("개인 심사서류")
w.view.flush_search()
pump(0.3)
cur = w.view.lst.current_item_data() or {}
ok("회사가 원본을 고쳐 새로 받아도 내 팩스번호는 남는다", FAX_NEW in cur.get("body", ""))
ok("'회사에서 새로 고침' 을 알린다", "새로 고쳤습니다" in w.view.lbl_title.text(), w.view.lbl_title.text())


def do_revert():
    d = modal()
    seen["note"] = d.lbl_note.isVisible() and "새로 고쳤습니다" in d.lbl_note.text()
    d.revert(ask=False)
    seen["body"] = d.txt_body.toPlainText()
    d._ok()


later(do_revert)
w.edit()
pump()
ok("편집 창에도 안내", seen.get("note") is True)
ok("되돌리면 회사의 새 내용", "2. 등본" in seen.get("body", "") and FAX_OLD in seen.get("body", ""))
ok("이 PC 기록을 지움 · 이 PC 첨부도 지움", kb.load_local() == [] and kb_files.cached(lat) is None)
w.view.ed_find.setText("개인 심사서류")
w.view.flush_search()
pump(0.3)
cur = w.view.lst.current_item_data() or {}
ok("검색 화면도 회사 자료로", cur.get("source") == kb.SRC_SHARED and "2. 등본" in cur.get("body", ""))
ok("아래 줄 건수도 사라짐", "이 PC 에서만 고친" not in w.lbl_account.text())

print("[13] 웹 스위치 — 켜 둔 채로 있어도 관리자가 끄면 멈춘다")
from kbsearch import switch as _switch  # noqa: E402
_real_fetch = _switch.fetch_state
quit_called.clear()
_switch.fetch_state = lambda timeout=6.0: {"on": True, "message": ""}
w.check_switch()
pump(0.3)
ok("켜짐이면 그대로", not quit_called)
_switch.fetch_state = lambda timeout=6.0: None
w.check_switch()
pump(0.3)
ok("못 읽으면 그대로(fail-open)", not quit_called)
_switch.fetch_state = lambda timeout=6.0: {"on": False, "message": "오늘은 쉽니다"}
QApplication.activeModalWidget = staticmethod(lambda: w)
w.check_switch()
pump(0.3)
ok("편집 창 등이 떠 있으면 미룬다", not quit_called)
QApplication.activeModalWidget = _am
n0 = len(NOTICES)
w.check_switch()
pump(0.3)
ok("꺼짐이면 안내하고 끝낸다", quit_called and any("오늘은 쉽니다" in x for x in NOTICES[n0:]), NOTICES[n0:])
ok("5분마다 다시 본다", w._switch_timer.interval() == config.SWITCH_CHECK_MINUTES * 60 * 1000)
_switch.fetch_state = _real_fetch

print()
print("실패:", FAIL if FAIL else "없음")
_sys.exit(1 if FAIL else 0)
