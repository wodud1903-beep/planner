"""v1.33 — 고객관리: '견적서 보기' 칸을 없애고 '내용' 을 넓힘 · 고객마다 서류 여러 개(지점장 요청).

가짜 구글로 메인 창을 실제로 띄워 고객 수정·추가·삭제 창을 밟는다.
  · 서류는 내 구글 드라이브 '고객서류' 폴더에 **링크 공개 없이** 올린다(kb_files.upload — 가짜로 바꿔 본다)
  · 목록은 시트 V열(앱 전용 숨김 칸)에 고객ID 와 함께 — 줄이 밀려도 남의 서류가 붙지 않게
  · 예전 견적서(S열 셀 안 그림)는 첫 서류로 함께 보이고, 빼면 S열 그림도 지운다
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

from PySide6.QtCore import QMimeData, QUrl  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import fake_google as fg  # noqa: E402

FAIL, ERRS, BOXES = [], [], []
_sys.excepthook = lambda t, v, tb: (ERRS.append("".join(traceback.format_exception(t, v, tb))),
                                    traceback.print_exception(t, v, tb))
threading.excepthook = lambda a: ERRS.append("".join(traceback.format_exception(a.exc_type, a.exc_value, a.exc_traceback)))


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


from planner import (config, customer_attach, customer_dialog, google_client, kb_attach, kb_files,  # noqa: E402
                     net, otp, sheets, theme)
from planner import startup_dialog as _sd  # noqa: E402

EMAIL = "staff@example.com"
W = fg.World(EMAIL)
_sd.StartupDialog.show_for = staticmethod(lambda *a, **k: None)
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, _k=_n, **k: BOXES.append((_k, a[2] if len(a) > 2 else ""))))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
for mod in (net, google_client, sheets, kb_files):
    for attr in ("http", "_http"):
        if hasattr(mod, attr):
            setattr(mod, attr, lambda: fg.Session(W))
google_client.GoogleAuth.valid_token = lambda self: "AT"
otp.claim = lambda *a, **k: True

# ---- 드라이브 올리기·받기·휴지통은 가짜로(무엇을 어떻게 올렸는지 적는다) ----
UPS, TRASHED, RENAMED = [], [], []


def fake_upload(auth, data, name, public, folder_name=kb_files.FOLDER_NAME):
    att = {"id": f"UP{len(UPS) + 1}", "name": name, "mime": kb_files.mime_of(name), "size": len(data)}
    UPS.append((name, public, folder_name, len(data)))
    kb_files._store(att, data)
    return att


def fake_fetch(auth, att):
    p = kb_files.cached(att)
    if p:
        return p
    from PySide6.QtCore import QBuffer, QByteArray
    im = QImage(20, 20, QImage.Format_RGB32)
    im.fill(QColor("#22aa88"))
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.WriteOnly)
    im.save(buf, "PNG")
    return kb_files._store(att, bytes(ba))


kb_files.upload = fake_upload
kb_files.fetch = fake_fetch
kb_files.trash = lambda auth, ids: TRASHED.extend(ids)
kb_files.rename_remote = lambda auth, fid, name: RENAMED.append((fid, name)) or True
VIEWED = []
kb_attach.AttachViewer.exec = lambda self: VIEWED.append([a.get("name") for a in self._atts]) or 0

LEGACY = '=IMAGE("https://drive.google.com/uc?export=view&id=LEGACY1", 1)'


def row(*cells, s="", u=""):
    r = list(cells) + [""] * (21 - len(cells))
    r[18], r[20] = s, u
    return r


TAB = "미출고차량"
W.sheets["STAFFSHEET"] = {TAB: [
    ["순번", "고객명 / 사업자", "금융사", "차종"],
    row("1", "홍길동", "KB캐피탈", "쏘렌토", s=LEGACY, u="UID-HONG"),
    row("2", "김철수", "현대캐피탈", "카니발", u="UID-KIM"),
]}
CELLS = W.sheets["STAFFSHEET"][TAB]
(config.base_dir() / "google_token.json").write_text(
    json.dumps({"refresh_token": "RT", "scopes": list(config.SCOPE_LABELS)}), encoding="utf-8")
config.remember_account(EMAIL)
config.set_account(EMAIL)
from planner.models import AppSettings  # noqa: E402
_s = AppSettings()
_s.sheet_on, _s.sheet_id, _s.sheet_name = True, "STAFFSHEET", TAB
_s.save(config.data_file("plan_cfg.json"))

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


from planner.main_window import MainWindow  # noqa: E402

w = MainWindow()
w.show()
ok("시트를 읽는다", wait(lambda: len(w.sheet_rows) == 2 and all(cr.uid for cr in w.sheet_rows)),
   [(cr.get("customer"), cr.uid) for cr in w.sheet_rows])

print("[1] 목록 — '견적서 보기' 칸을 없애고 그 폭을 '내용' 에")
w.tabs.setCurrentIndex(1)
w.resize(1700, w.height())          # 보통 사무실 화면 폭
w.refresh_customers()
pump(0.5)
t = w.tbl_cust
heads = [t.horizontalHeaderItem(i).text() for i in range(t.columnCount())]
ok("견적서 칸이 없다 · 안내멘트가 맨 끝", "견적서" not in heads and heads[-1] == "안내멘트", heads)
_note = t.columnWidth(heads.index("내용"))
_others = sum(t.columnWidth(i) for i in range(t.columnCount()) if heads[i] != "내용")
ok("'내용' 이 남는 폭을 다 받는다(다른 칸 합이 1284 → 1226 — 견적서 칸 58 만큼 더 넓다) · 기본 313",
   abs(_note + _others - t.viewport().width()) <= 2 and _others == 1226
   and "[46, 236, 116, 180, 134, 116, 116, 78, 124, 313, 80]" in (_ROOT / "python/planner/main_window.py").read_text(encoding="utf-8"),
   (_note, _others, t.viewport().width()))
ok("버튼은 안내멘트 칸에만", all(t.cellWidget(r, c) is None for r in range(t.rowCount())
                             for c in range(t.columnCount()) if c != w.COL_MENT_BTN))


def pick(name):
    for r in range(t.rowCount()):
        if t.item(r, 1) and t.item(r, 1).text().endswith(name):
            t.selectRow(r)
            t.setCurrentCell(r, 1)
            return
    raise AssertionError(name)


def mime_files(*paths, image=False):
    md = QMimeData()
    if paths:
        md.setUrls([QUrl.fromLocalFile(p) for p in paths])
    if image:
        img = QImage(24, 16, QImage.Format_RGB32)
        img.fill(QColor("#6a5ae0"))
        md.setImageData(img)
    return md


tmp = _pl.Path(tempfile.mkdtemp())
pdf = tmp / "계약확인서 스캔.pdf"
pdf.write_bytes(b"%PDF-1.4\n" + b"0" * 300)
jpg = tmp / "자동차등록증.jpg"
_img = QImage(40, 30, QImage.Format_RGB32)
_img.fill(QColor("#ffcc00"))
_img.save(str(jpg), "JPG")
txt = tmp / "메모.txt"
txt.write_text("x", encoding="utf-8")

print("[2] 고객 수정 — 서류 여러 개(붙여넣기·파일) · 옛 견적서 그림은 첫 서류로")
SEEN = {}


def edit_script(d):
    box = d.files_box
    SEEN["first"] = [a.get("name") for a in box.atts()]
    box.drop_attachments(mime_files(str(pdf), str(jpg), str(txt)))      # 탐색기에서 끌어 놓기
    box.drop_attachments(mime_files(image=True))                         # 캡처·카톡 그림 붙여넣기
    box.drop_attachments(mime_files(str(pdf)))                            # 같은 것을 또 — 안 들어간다
    SEEN["added"] = [a.get("name") for a in box.atts()]
    SEEN["bad"] = list(BOXES)
    BOXES.clear()
    box.lst.clearSelection()
    box.lst.item(1).setSelected(True)
    box.rename_attachment("계약확인서")                                    # 확장자는 그대로
    SEEN["renamed"] = box.atts()[1]["name"]
    box.lst.clearSelection()
    box.lst.item(2).setSelected(True)
    box.open_attachment(box.atts()[2])                                    # 올리기 전에도 크게 보기
    d._ok()
    return d.result()


customer_dialog.CustomerDialog.exec = lambda self: edit_script(self)
pick("홍길동")
w.on_customer_edit()
ok("옛 견적서(S열 그림)가 첫 서류로 보인다", SEEN["first"] == [customer_attach.LEGACY_NAME], SEEN["first"])
ok("그림·PDF 만 받는다(txt 는 까닭과 함께 빠진다) · 같은 것은 두 번 안 들어간다",
   len(SEEN["added"]) == 4 and SEEN["added"][1:3] == ["계약확인서 스캔.pdf", "자동차등록증.jpg"]
   and SEEN["added"][3].startswith("붙여넣은 그림") and any("메모.txt" in b[1] for b in SEEN["bad"]), SEEN)
ok("이름 바꾸기 — 확장자는 그대로", SEEN["renamed"] == "계약확인서.pdf", SEEN["renamed"])
ok("올리기 전에도 크게 보기(같은 고객의 서류를 넘겨 본다)", VIEWED and len(VIEWED[-1]) == 4, VIEWED[-1:])
ok("[저장] 하면 새 서류 3개를 올린다 — 링크 공개 없이 '고객서류' 폴더로",
   [(n, pub, f) for n, pub, f, _sz in UPS] == [("계약확인서.pdf", False, "고객서류"), ("자동차등록증.jpg", False, "고객서류"),
                                               (SEEN["added"][3], False, "고객서류")], UPS)


def vcell(r):
    row_ = CELLS[r - 1]
    return row_[21] if len(row_) > 21 else ""


ok("시트 V열에 고객ID 와 서류 목록(옛 견적서 + 새 3개)", wait(lambda: vcell(2).startswith("{")) and
   json.loads(vcell(2))["uid"] == "UID-HONG"
   and [f["name"] for f in json.loads(vcell(2))["files"]] == [customer_attach.LEGACY_NAME, "계약확인서.pdf", "자동차등록증.jpg",
                                                                SEEN["added"][3]], vcell(2)[:200])
ok("S열 옛 견적서 그림은 그대로", CELLS[1][18] == LEGACY)
ok("V열은 '앱 전용' 머리글", CELLS[0][21] == sheets.FILES_HEADER, CELLS[0][21:22])
ok("다른 고객 줄은 건드리지 않는다", vcell(3) == "")
hong = next(cr for cr in w.sheet_rows if cr.get("customer") == "홍길동")
ok("화면의 고객도 서류 4개", len(customer_attach.all_files(hong)) == 4)

print("[3] 다시 수정 — 빼면 드라이브 휴지통으로 · 옛 견적서를 빼면 S열 그림도 지운다")


def edit2(d):
    box = d.files_box
    SEEN["again"] = [a.get("name") for a in box.atts()]
    box.lst.clearSelection()
    box.lst.item(0).setSelected(True)
    box.lst.item(2).setSelected(True)
    box.remove_attachments()
    d._ok()
    return d.result()


customer_dialog.CustomerDialog.exec = lambda self: edit2(self)
UPS.clear()
pick("홍길동")
w.on_customer_edit()
ok("다시 열면 저장한 4개가 그대로(옛 견적서가 두 번 나오지 않는다)", SEEN["again"] == [
    customer_attach.LEGACY_NAME, "계약확인서.pdf", "자동차등록증.jpg", SEEN["added"][3]], SEEN["again"])
ok("남은 2개만 V열에", wait(lambda: [f["name"] for f in json.loads(vcell(2) or "{}").get("files", [])]
                         == ["계약확인서.pdf", SEEN["added"][3]]), vcell(2)[:160])
ok("옛 견적서를 뺐으니 S열 그림도 지운다", wait(lambda: CELLS[1][18] == ""), CELLS[1][18])
ok("뺀 서류는 드라이브 휴지통으로(30일 안에 되살림)", wait(lambda: sorted(TRASHED) == ["LEGACY1", "UP2"]), TRASHED)
ok("새로 올린 것은 없다", UPS == [])

print("[4] 오른쪽 단추 — [📎 첨부 서류 보기 (2개)]")
VIEWED.clear()
w.show_customer_files(hong)
ok("크게 보기 창에 그 고객의 서류를 차례로", VIEWED == [["계약확인서.pdf", SEEN["added"][3]]], VIEWED)
src = (_ROOT / "python/planner/main_window.py").read_text(encoding="utf-8")
ok("오른쪽 단추 메뉴에 들어 있다", '📎 첨부 서류 보기 ({len(att)}개)' in src)

print("[5] 새 고객 — 등록하면서 서류")


def add_script(d):
    d.widgets["customer"][0].setText("이영희")
    d.files_box.drop_attachments(mime_files(str(jpg)))
    d._ok()
    return d.result()


customer_dialog.CustomerDialog.exec = lambda self: add_script(self)
UPS.clear()
w.on_customer_add()
ok("새 줄에 고객 · 고객ID · 서류 목록", wait(lambda: len(CELLS) >= 4 and CELLS[3][1] == "이영희" and vcell(4).startswith("{")),
   CELLS[3][:3] if len(CELLS) > 3 else CELLS)
ok("V열의 고객ID 가 새 줄의 고객ID 와 같다", json.loads(vcell(4))["uid"] == CELLS[3][20] and CELLS[3][20], (vcell(4)[:80], CELLS[3][20:21]))

print("[6] 고객 삭제 — 서류 칸도 비우고, 서류는 휴지통으로")
TRASHED.clear()
wait(lambda: any(cr.get("customer") == "이영희" for cr in w.sheet_rows))
pick("이영희")
w.on_customer_del()
ok("V열을 비운다", wait(lambda: vcell(4) == ""), vcell(4))
ok("그 고객의 서류는 휴지통으로", wait(lambda: TRASHED == ["UP1"]), TRASHED)

print("[7] 다시 읽어도 — 줄이 밀려 다른 고객 칸에 가면 붙이지 않는다")
CELLS[2].extend([""] * (22 - len(CELLS[2])))
CELLS[2][21] = sheets.files_cell("UID-HONG", [{"id": "X", "name": "남의서류.pdf", "mime": "application/pdf", "size": 1}])
w.load_sheet_async(manual=False)
ok("다시 읽으면 홍길동 서류 2개", wait(lambda: any(cr.get("customer") == "홍길동" and len(cr.files()) == 2
                                              for cr in w.sheet_rows)))
kim = next(cr for cr in w.sheet_rows if cr.get("customer") == "김철수")
ok("고객ID 가 다른 줄의 목록은 그 고객에게 붙이지 않는다", kim.files() == [] and customer_attach.all_files(kim) == [])
ok("폰 웹은 같은 규칙으로 읽는다(customers.js filesFrom · legacyAtt)",
   "export function filesFrom(cell, uid" in (_ROOT / "web/js/customers.js").read_text(encoding="utf-8")
   and "readFilesCell" in (_ROOT / "web/js/sheets.js").read_text(encoding="utf-8"))

pump(0.3)
ok("끝까지 예외가 없다", not ERRS, ERRS[:1])
ok("모르는 주소로 나가지 않는다", not fg.UNKNOWN, fg.UNKNOWN[:4])
print()
print("실패:", FAIL if FAIL else "없음")
w._quitting = True
os._exit(1 if FAIL else 0)
