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
for ch in "사진 많은 자료 사진 많은 자":
    v.ed_find.setText(v.ed_find.text() + ch)
    pump(3)
time.sleep(v.SEARCH_DELAY_MS / 1000 + 0.05)
pump(10)
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

print()
print("실패:", FAIL if FAIL else "없음")
_sys.exit(1 if FAIL else 0)
