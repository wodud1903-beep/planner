"""자료검색 화면 — 멈췄다가 꺼지던 문제(일정관리기 v1.21.2) 고친 것이 이 프로그램에도 있는지.

일정관리기 tools/verify/verify_kbfiles.py [14] · verify_livesearch.py [2-2] 를 옮겨 왔다.
  · 큰 그림을 작게 풀고, 같은 파일은 다시 풀지 않는다
  · 검색어만 바뀌고 같은 자료면 첨부 줄을 다시 만들지 않는다 · 검색은 타자가 멎은 뒤 한 번
  · 크게 보기 창·오른쪽 단추 메뉴는 다 쓰면 없앤다
  · 입력기 이벤트 안에서는 알리지 않는다(끝난 뒤 한 번)
"""
import pathlib as _pl
import sys as _sys

_HERE = _pl.Path(__file__).resolve().parent
_sys.path.insert(0, str(_HERE.parent))

import inspect  # noqa: E402
import os  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QEvent, QIODevice  # noqa: E402
from PySide6.QtGui import QColor, QImage, QInputMethodEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from kbsearch import kb, kb_attach, kb_files  # noqa: E402
from kbsearch.kb_attach import AttachViewer  # noqa: E402
from kbsearch.kb_view import KbView  # noqa: E402
from kbsearch.livesearch import LiveLineEdit  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name
          + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


def pump(n=10):
    for _ in range(n):
        app.processEvents()
        time.sleep(0.005)


def png_bytes(color, w, h):
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QColor(color))
    ba = QByteArray()
    b = QBuffer(ba)
    b.open(QIODevice.WriteOnly)
    img.save(b, "PNG")
    return bytes(ba)


print("[1] 큰 그림을 작게 풀고, 다시 풀지 않는다")
big = png_bytes("#884422", 4000, 3000)              # 폰 사진만 한 그림
bigs = []
for i in range(10):
    a = {"id": f"BIG{i}", "name": f"사진{i}.png", "mime": "image/png", "size": len(big)}
    kb_files._store(a, big)
    bigs.append(a)
img = kb_attach._decode_small(path=str(kb_files.cached(bigs[0])))
ok("처음부터 작게 푼다(4000×3000 을 통째로 풀지 않음)",
   img is not None and max(img.width(), img.height()) <= kb_attach.THUMB,
   (img.width(), img.height()) if img is not None else None)
kb_attach._THUMBS.clear()
n0 = kb_attach.decode_count
kb_attach.icon_for(bigs[0])
kb_attach.icon_for(bigs[0])
ok("같은 파일은 두 번째에 다시 풀지 않는다", kb_attach.decode_count - n0 == 1)

print("[2] 검색할 때 첨부 줄을 갈아엎지 않는다 · 검색은 타자가 멎은 뒤 한 번")
kb.save_shared([{"category": "전자약정", "title": "사진 많은 자료", "body": "본문", "files": bigs},
                {"category": "기타", "title": "다른 자료", "body": "x"}])
v = KbView()
v.show()
pump(30)
v.lst.setCurrentRow(0)
pump(20)
rebuilt = []
_orig = v.lst_att.fill
v.lst_att.fill = lambda files, _f=_orig: (rebuilt.append(len(files)), _f(files))[1]
searches = []
_ref = v._refilter
v._refilter = lambda *a, _r=_ref: (searches.append(1), _r(*a))[1]
v._find_timer.timeout.disconnect()
v._find_timer.timeout.connect(v._refilter)
n0 = kb_attach.decode_count
# ⚠️ 검사에서는 기다림을 1초로 늘린다. 120ms 그대로 두면 느린 검사 PC(윈도 CI)에서 글자 사이가
#    120ms 를 넘을 때가 있어 검색이 두 번 돈다 — 앱은 맞게 한 것인데 검사가 빨개졌다.
#    여기서 보려는 것은 '칠 때마다 다시 기다린다' 는 동작이고, 실제 값(120ms)은 아래에서 따로 본다.
ok("실제 기다림은 120ms", KbView.SEARCH_DELAY_MS == 120 and v._find_timer.interval() == 120)
v._find_timer.setInterval(1000)
for ch in "사진 많은 자료 사진 많은 자":
    v.ed_find.setText(v.ed_find.text() + ch)
    pump(3)
time.sleep(1.1)
pump(10)
v._find_timer.setInterval(KbView.SEARCH_DELAY_MS)
ok("같은 자료면 첨부 줄을 다시 만들지 않는다", rebuilt == [], rebuilt)
ok("검색은 타자가 멎은 뒤 한 번", len(searches) == 1, len(searches))
ok("찾은 것", [v.lst.item(i).text() for i in range(v.lst.count())] == ["사진 많은 자료"])
ok("20자를 쳐도 그림을 다시 풀지 않는다", kb_attach.decode_count - n0 == 0)
v.ed_find.setText("다른")
v.flush_search()
ok("기다리는 검색을 바로 끝낼 수 있다(빠른검색 Enter)",
   [v.lst.item(i).text() for i in range(v.lst.count())] == ["다른 자료"])

print("[3] 다 쓴 창·메뉴는 없앤다")
gone = []
av = AttachViewer({"id": "BIG0", "name": "사진0.png"}, big, on_send=lambda: None, parent=v)
av.destroyed.connect(lambda *_: gone.append(1))
av.show()
pump()
pv = av.preview
av.done(0)
ok("닫으면 그림을 놓는다", pv._src is None and pv._img_data is None)
for _ in range(20):
    pump(2)
    QApplication.sendPostedEvents(None, 0)
ok("닫힌 크게 보기 창은 없어진다", gone == [1])
v.ed_find.setText("사진")
v.flush_search()
pump(5)
m = v.lst_att.menu_for(v.lst_att.item(0))
dead = []
m.destroyed.connect(lambda *_: dead.append(1))
m.deleteLater()
for _ in range(10):
    pump(2)
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
ok("오른쪽 단추 메뉴도 없앤다", dead == [1])
ok("메뉴를 띄운 뒤 deleteLater 한다",
   "m.deleteLater()" in inspect.getsource(kb_attach.AttachList.contextMenuEvent))

print("[4] 입력기 이벤트 안에서는 알리지 않는다 — 끝나면 한 번")
le = LiveLineEdit()
got = []
le.liveText.connect(got.append)
le.show()
pump()
QApplication.sendEvent(le, QInputMethodEvent("가", []))
ok("이벤트 안에서는 아직 안 알렸다", got == [], got)
pump()
ok("끝나자마자 한 번 알린다", got == ["가"], got)
for ch in ("나", "다", "라"):
    QApplication.sendEvent(le, QInputMethodEvent(ch, []))
pump()
ok("몰려 와도 마지막 것 한 번만", got[-1] == "라" and len(got) == 2, got)
le.setText("abc")
pump()
got.clear()
le.blockSignals(True)
le.clear()
le.blockSignals(False)
le.setText("abc")
pump()
ok("지운 뒤 같은 글을 다시 쳐도 다시 찾는다", got == ["abc"], got)

print("[5] 크게 보기 — 휠로 끝까지 키워도 메모리가 안 터진다 (일정관리기 v1.22.1)")
# 휴대폰 사진(4000×3000)을 휠로 15번 굴리면 32000×24000 그림을 만들어 9GB 를 쓰고 꺼졌다.
from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QWheelEvent  # noqa: E402
from kbsearch.file_preview import FilePreview  # noqa: E402


def wheel(wdg, delta=120):
    ev = QWheelEvent(QPointF(wdg.rect().center()), QPointF(wdg.mapToGlobal(wdg.rect().center())),
                     QPoint(0, 0), QPoint(0, delta), Qt.NoButton, Qt.NoModifier,
                     Qt.NoScrollPhase, False)
    QApplication.sendEvent(wdg, ev)


def settle(pv_):
    time.sleep(pv_.WHEEL_MS / 1000 + 0.03)
    app.processEvents()


photo = QImage(4000, 3000, QImage.Format_RGB32)
photo.fill(QColor("#88AA44"))
_b = QBuffer()
_b.open(QBuffer.WriteOnly)
photo.save(_b, "JPG")
PHOTO = bytes(_b.data())
del photo
pv9 = FilePreview()
pv9.resize(900, 700)
pv9.show()
app.processEvents()
pv9.show_image(PHOTO, "photo", "사진.jpg")
app.processEvents()
r0 = pv9.redraws
for _ in range(30):
    wheel(pv9.view)                 # 빠르게 30칸
settle(pv9)
pm = pv9.view.pixmap()
ok("그린 그림이 예산 안(넓이·한 변)", pm.width() * pm.height() <= pv9.MAX_PIXELS
   and max(pm.width(), pm.height()) <= pv9.MAX_SIDE, (pm.width(), pm.height()))
ok("빠르게 30칸 굴려도 한 번만 그린다", pv9.redraws - r0 == 1, pv9.redraws - r0)
r1 = pv9.redraws
for _ in range(5):
    wheel(pv9.view)
    settle(pv9)
ok("끝에서 더 굴려도 다시 그리지 않는다", pv9.redraws == r1)
scan = QImage(9000, 8000, QImage.Format_RGB32)
scan.fill(QColor("#FFFFFF"))
_b = QBuffer()
_b.open(QBuffer.WriteOnly)
scan.save(_b, "PNG")
SCAN = bytes(_b.data())
del scan
ok("아주 큰 스캔(9000×8000)도 작게 풀어 열린다", pv9.show_image(SCAN, "scan", "스캔")
   and pv9._src is not None and pv9._src.width() * pv9._src.height() <= pv9.MAX_PIXELS)
ok("크게 보기를 열 때 참고 기록을 남긴다",
   "crashlog.note(" in inspect.getsource(KbView.open_attachment))

print("[6] 첨부 칸은 한 줄 높이 — 남는 자리는 본문이 (일정관리기 v1.23.0)")
from PySide6.QtCore import QMimeData, QUrl  # noqa: E402
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent, QGuiApplication  # noqa: E402
from kbsearch import config  # noqa: E402
from kbsearch.kb_view import KbEditDialog  # noqa: E402
three = []
for i, nm in enumerate(("근보증서 예시.png", "신분증 앞.png", "약정서.pdf")):
    a = {"id": f"ROW{i}", "name": nm, "size": 1000,
         "mime": "application/pdf" if nm.endswith(".pdf") else "image/png"}
    cp = kb_files.cache_path(a)
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_bytes(png_bytes("#2563EB", 300, 420) if nm.endswith(".png") else b"%PDF-1.4\n")
    three.append(a)
kb.save_shared([{"category": "캐피탈", "title": "MG캐피탈", "body": "본문\n" * 30, "files": three},
                {"category": "기타", "title": "첨부 없는 자료", "body": "x"}])
v5 = KbView()
v5.resize(1200, 800)
v5.show()
pump(20)
v5.lst.setCurrentRow([v5.lst.item(i).text() for i in range(v5.lst.count())].index("MG캐피탈"))
pump(20)
la = v5.lst_att
ok("첨부 3개", la.count() == 3, la.count())
ok("높이 = 한 줄(예전 최소 176 보다 낮다)", la.height() == la.row_height() and la.height() < 176,
   (la.height(), la.row_height()))
rects = [la.visualItemRect(la.item(i)) for i in range(3)]
ok("한 줄로 늘어선다", len({r.top() for r in rects}) == 1)
h_att, h_body = la.height(), v5.txt_body.height()
v5.resize(1200, 1100)
pump(20)
ok("창을 키워도 첨부 칸은 그대로", la.height() == h_att)
ok("늘어난 자리는 본문이 쓴다", v5.txt_body.height() >= h_body + 250, (h_body, v5.txt_body.height()))
v5.lst.setCurrentRow([v5.lst.item(i).text() for i in range(v5.lst.count())].index("첨부 없는 자료"))
pump(10)
ok("첨부 없는 자료는 칸을 숨긴다", not la.isVisible())
v5.hide()

print("[7] 끌어다 놓기 — 탐색기에서 편집 창 첨부 칸으로 (진짜 끌기 알림으로)")
_dd = os.path.join(tempfile.mkdtemp(), "끌어온 사진.png")
with open(_dd, "wb") as f:
    f.write(png_bytes("#B45309", 40, 30))
ADMIN = config.KB_ADMINS[0]
kb.save_shared([{"category": "캐피탈", "title": "메리츠캐피탈", "body": "가"},
                {"category": "캐피탈", "title": "가 먼저", "body": "나"}])
kb.save_mine([{"category": "심사서류", "title": "개인 심사서류", "body": "다"},
              {"category": "기타", "title": "내 메모 둘", "body": "라"}])
d6 = KbEditDialog(ADMIN, None)
d6.show()
pump(10)
d6.lst.setCurrentRow(0)
pump(5)


def drag_into(target, path):
    vp = target.viewport()
    m = QMimeData()
    m.setUrls([QUrl.fromLocalFile(path)])
    pos = vp.rect().center()
    acts = Qt.CopyAction | Qt.MoveAction | Qt.LinkAction
    e1 = QDragEnterEvent(pos, acts, m, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(vp, e1)
    e2 = QDragMoveEvent(pos, acts, m, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(vp, e2)
    e3 = QDropEvent(QPointF(pos), acts, m, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(vp, e3)
    pump(5)
    return e1.isAccepted(), e3.isAccepted()


n0 = d6.lst_att.count()
acc = drag_into(d6.lst_att, _dd)
ok("첨부 칸이 끌어 온 파일을 받는다", acc == (True, True), acc)
ok("첨부가 하나 늘었다 · 이름 그대로", d6.lst_att.count() == n0 + 1
   and d6.lst_att.atts()[-1].get("name") == "끌어온 사진.png")
d6.reject()

print("[8] [자료 편집] 은 보던 자료부터 · 편집 창은 넉넉한 세로")
d7 = KbEditDialog(ADMIN, None, select={"source": kb.SRC_SHARED, "title": "메리츠캐피탈",
                                       "category": "캐피탈"})
ok("공통 자료 — 그 자료가 골라져 있다", d7.ed_title.text() == "메리츠캐피탈"
   and d7.cmb_src.currentData() == kb.SRC_SHARED, d7.ed_title.text())
d7.reject()
d8 = KbEditDialog(ADMIN, None, select={"source": kb.SRC_MINE, "title": "내 메모 둘",
                                       "category": "기타"})
ok("내 메모 — 묶음도 바꿔서 그 자료", d8.ed_title.text() == "내 메모 둘"
   and d8.cmb_src.currentData() == kb.SRC_MINE)
d8.reject()
d9 = KbEditDialog("", None, select={"source": kb.SRC_SHARED, "title": "메리츠캐피탈"})
ok("로그인 안 함(관리자 아님)이면 공통 자료를 '이 PC 에서만' 묶음에서 연다",
   d9.ed_title.text() == "메리츠캐피탈" and d9.cmb_src.currentData() == kb.SRC_LOCAL,
   d9.ed_title.text())
d9.reject()
d10 = KbEditDialog(ADMIN, None, select={"source": kb.SRC_SHARED, "title": "없는 자료"})
ok("못 찾으면 맨 위", d10.lst.currentRow() == 0)
_av = QGuiApplication.primaryScreen().availableGeometry()
ok("편집 창 세로가 넉넉하다", d10.height() >= min(1040, int(_av.height() * 0.8))
   or d10.height() >= _av.height() - 40, (d10.height(), _av.height()))
d10.reject()
ok("[이름 바꾸기] 단추가 눌림 여부(False)를 새 이름으로 받지 않는다",
   "lambda: self.rename_attachment()" in inspect.getsource(KbEditDialog.__init__))
import kbsearch.main_window as _mw  # noqa: E402
ok("메인 창 [자료 편집] 이 보던 자료를 넘긴다",
   "select=self.view.lst.current_item_data()" in inspect.getsource(_mw.MainWindow.edit))

print("[9] 묶음을 바꿔도 다른 묶음의 같은 줄을 덮어쓰지 않는다")
for who, first in ((ADMIN, kb.SRC_SHARED), ("", kb.SRC_LOCAL)):
    d = KbEditDialog(who, None)
    d.cmb_src.setCurrentIndex(d.cmb_src.findData(first))
    d.lst.setCurrentRow(1)
    d.ed_title.setText("가 먼저 (고침)")
    d.cmb_src.setCurrentIndex(d.cmb_src.findData(kb.SRC_MINE))
    ok(f"{'관리자' if who else '로그인 안 함'} — 내 메모 그대로",
       [x["title"] for x in d.mine] == ["개인 심사서류", "내 메모 둘"], [x["title"] for x in d.mine])
    lst = d.shared if first == kb.SRC_SHARED else d.local
    ok(f"{'관리자' if who else '로그인 안 함'} — 고친 것은 원래 묶음에",
       [x["title"] for x in lst] == ["메리츠캐피탈", "가 먼저 (고침)"], [x["title"] for x in lst])
    d.reject()
d = KbEditDialog("", None)
d.lst.setCurrentRow(1)
d.ed_title.setText("가 먼저 (고침)")
d.lst.setCurrentRow(0)
ok("고친 줄에 '이 PC 에서 고침' 표시", d.lst.item(1).text().endswith("(이 PC 에서 고침)"), d.lst.item(1).text())
d._add()
d._del()
ok("'이 PC 에서만' 묶음은 더하거나 지우지 않는다", len(d.local) == 2)
d.lst.setCurrentRow(1)
d.revert(ask=False)
ok("[회사 자료로 되돌리기]", d.local[1]["title"] == "가 먼저" and not d.lst.item(1).text().endswith(")"))
_m = QMimeData()
_m.setUrls([QUrl.fromLocalFile(_dd)])
d.drop_attachments(_m)
d.lst.setCurrentRow(0)
ok("첨부만 붙여도 고친 것으로 본다", d.lst.item(1).text().endswith("(이 PC 에서 고침)"), d.lst.item(1).text())
d.reject()
d = KbEditDialog(ADMIN, None)
ok("관리자는 이 PC 에서 고친 게 없으면 그 묶음을 안 보인다", d.cmb_src.findData(kb.SRC_LOCAL) < 0)
d.reject()

print()
print("실패:", FAIL if FAIL else "없음")
_sys.exit(1 if FAIL else 0)
