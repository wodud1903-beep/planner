"""받은 팩스 — 알람과 보기. 실제로 재현해서 못 박는다."""
# ⚠️ 경로를 박아 두지 않는다. 예전에는 이 검사들이 작업용 임시 폴더에만 있고
# "/home/user/planner" 를 글자 그대로 들고 있어서, 컨테이너가 다시 뜨면 통째로
# 사라졌다(실제로 두 번 겪었다). 이제 저장소 안에 살고, 자기 위치에서 뿌리를 찾는다.
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]      # tools/verify/x.py → 저장소 뿌리
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
import os as _os
_os.chdir(_ROOT / "python")                          # 'planner/...' 상대경로를 쓰는 검사용
import os, sys, tempfile, time, json, shutil

from PIL import Image, ImageDraw
from PySide6.QtWidgets import QApplication
from planner import fax_watch, customer_files as cf, sync
from planner.file_preview import FilePreview
from planner.models import AppSettings

fails = []
def ok(name, cond, detail=""):
    print(("  OK  " if cond else "  ** FAIL **  ") + name + ("  " + str(detail) if detail else ""))
    if not cond: fails.append(name)

app = QApplication.instance() or QApplication([])
def pump(n=15):
    for _ in range(n): app.processEvents(); time.sleep(0.01)

def make_tif(path, pages=3):
    ims = []
    for i in range(pages):
        im = Image.new("1", (1728, 1100), 1); d = ImageDraw.Draw(im)
        for y in range(200 + i*40, 900, 60): d.line([100, y, 1600, y], fill=0, width=3)
        ims.append(im)
    ims[0].save(path, save_all=True, append_images=ims[1:], compression="group4")

def make_pdf(path):
    open(path, "wb").write(
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]>>endobj\n"
        b"trailer<</Root 1 0 R>>")

# ---------------------------------------------------------------- [A] 감시
print("\n[A] 폴더를 지켜보다 새 팩스를 잡는다")
d = tempfile.mkdtemp()
make_pdf(os.path.join(d, "옛날팩스.pdf"))
f = fax_watch.FaxFolder(d)
ok("첫 훑기에서는 기존 파일로 알리지 않는다", f.tick() == [], "(처음 지정할 때 쏟아지면 안 됨)")
ok("기존 파일은 '봤음' 으로 표시된다", len(f.seen) == 1, len(f.seen))

make_pdf(os.path.join(d, "새팩스.pdf"))
first = f.tick()
ok("막 생긴 파일은 아직 안 알린다(다 왔는지 모른다)", first == [], first)
got = f.tick()
ok("한 박자 뒤 '다 왔다' 로 보고 알린다", [n for n, _ in got] == ["새팩스.pdf"], got)
ok("같은 팩스를 두 번 알리지 않는다", f.tick() == [])

# 커지는 중인 파일
p_grow = os.path.join(d, "내려받는중.pdf")
open(p_grow, "wb").write(b"%PDF-1.4\n" + b"x" * 100)
f.tick()
open(p_grow, "ab").write(b"y" * 5000)          # 아직 커지는 중
ok("크기가 커지는 중이면 안 알린다", f.tick() == [], "(깨진 PDF 방지)")
ok("크기가 멎으면 그때 알린다", [n for n, _ in f.tick()] == ["내려받는중.pdf"])

# 찌꺼기·엉뚱한 확장자
open(os.path.join(d, ".tmp.drivedownload"), "wb").write(b"x")
open(os.path.join(d, "~$문서.pdf"), "wb").write(b"x")
open(os.path.join(d, "메모.txt"), "wb").write(b"x")
f.tick(); ok("드라이브 찌꺼기·숨김·txt 는 무시한다", f.tick() == [])

# 재시작해도 다시 안 뜬다
f2 = fax_watch.FaxFolder(d, seen=f.seen)
f2.tick()
ok("껐다 켜도 본 팩스는 다시 안 뜬다", f2.tick() == [])

# 폴더를 바꾸면 그 폴더의 기존 파일로 알리지 않는다
d2 = tempfile.mkdtemp(); make_pdf(os.path.join(d2, "다른폴더팩스.pdf"))
f2.set_folder(d2)
ok("폴더를 바꾸면 거기 있던 것으로 안 알린다", f2.tick() == [])

# ---------------------------------------------------------------- [B] 여러 장 TIFF
print("\n[B] 여러 장 TIFF 팩스 — 장이 다 보인다")
tif = os.path.join(d, "3장팩스.tif")
make_tif(tif, 3)
ok("tif 를 미리보기 가능으로 본다", cf.Node(name="a.tif", is_dir=False).viewable)
ok("tiff 도 마찬가지", cf.Node(name="a.tiff", is_dir=False).viewable)
ok("팩스 감시가 tif 를 본다", ".tif" in fax_watch.FAX_EXT and ".pdf" in fax_watch.FAX_EXT)

pv = FilePreview(); pv.resize(700, 560); pv.show(); pump()
data = open(tif, "rb").read()
ok("여러 장 TIFF 가 열린다", pv.show_image(data, tif, "3장팩스.tif")); pump()
ok("장 수를 제대로 센다", pv.page_count == 3, pv.page_count)
ok("장 넘기기 단추가 보인다", pv.btn_next.isVisible())
import hashlib
from PySide6.QtCore import QBuffer
def sig(pix):
    img = pix.toImage(); b = QBuffer(); b.open(QBuffer.WriteOnly); img.save(b, "PNG")
    return hashlib.sha256(bytes(b.data())).hexdigest()[:12]
seen_pages = {}
for pg in (0, 1, 2):
    pv.go_page(pg); pump(3); seen_pages[pg] = sig(pv._src)
ok("세 장이 서로 다른 그림이다", len(set(seen_pages.values())) == 3, seen_pages)
pv.go_page(99); pump(3); ok("범위 밖은 마지막 장에 멈춘다", pv._page == 2, pv._page)
pv.go_page(-9); pump(3); ok("범위 밖은 첫 장에 멈춘다", pv._page == 0, pv._page)
one = os.path.join(d, "한장.png"); Image.new("L", (400, 300), 200).save(one)
pv.show_image(open(one, "rb").read(), one, "한장.png"); pump()
ok("한 장짜리는 장 넘기기를 숨긴다", pv.page_count == 1 and not pv.btn_next.isVisible())
# 수명 문제(예전에 여기서 segfault 났다)
for i in range(30):
    pv.show_image(data, tif, "t"); pv.go_page(i % 3)
    pv.show_image(open(one, "rb").read(), one, "o"); pump(1)
ok("여러 파일을 30번 오가도 안 죽는다", True)

# ---------------------------------------------------------------- [C] 알람
print("\n[C] 알람 — 조용한 안내 + [보기]")
from planner import alarm_window
clicked = []
w = alarm_window.popup("팩스 도착", "수신팩스.pdf (09/13 10:20 · 12 KB)", 0,
                       siren=False, action=("보기", lambda: clicked.append(1)))
pump()
ok("조용한 안내로 뜬다(사이렌 아님)", w._siren is False)
ok("[보기] 단추가 있다", w.btn_act.isVisible() and w.btn_act.text() == "보기")
ok("5분 뒤 다시 단추는 없다", not w.btn_snooze.isVisible())
w.btn_act.click(); pump()
ok("[보기] 를 누르면 시킨 일을 한다", clicked == [1])
ok("누르면 팝업이 닫힌다", w not in alarm_window._open_alarms)
w2 = alarm_window.popup("보통 알람", "내용", 0)
pump(); ok("[보기] 를 안 주면 단추가 안 생긴다", not w2.btn_act.isVisible())
alarm_window.close_all(); pump()

# ---------------------------------------------------------------- [D] 보기 창
print("\n[D] 받은 팩스 창")
from planner import fax_window
fw = fax_window.FaxWindow(d); fw.resize(900, 600); fw.show(); pump()
names = [n for n, _ in fw._items]
ok("목록에 팩스가 찬다", len(names) >= 3, names[:4])
ok("새 것이 위로 온다", fw._items[0][1][1] >= fw._items[-1][1][1])
ok("txt 같은 것은 목록에 없다", not any(n.endswith(".txt") for n in names))
fw.reload(pick="3장팩스.tif"); pump()
ok("특정 팩스를 골라서 열 수 있다", fw._name_at(fw.lst.currentRow()) == "3장팩스.tif")
ok("고른 팩스가 미리보기에 뜬다", fw.pv.page_count == 3, fw.pv.page_count)
ok("현재 경로를 알려 준다", fw.current_path().endswith("3장팩스.tif"))
empty = tempfile.mkdtemp()
fe = fax_window.FaxWindow(empty); pump()
ok("빈 폴더면 조용히 '없습니다'", fe._items == [])
fw.close(); fe.close(); pump()

# ---------------------------------------------------------------- [E] 설정·동기화
print("\n[E] 설정과 다중 PC")
s = AppSettings()
ok("기본은 폴더 없음 · 알림 켬", s.fax_dir == "" and s.fax_watch is True)
tmp = os.path.join(tempfile.mkdtemp(), "c.json")
from pathlib import Path
s.fax_dir = d; s.fax_watch = False; s.save(Path(tmp))
ok("설정이 저장·복원된다", AppSettings.load(Path(tmp)).fax_dir == d)
ok("동기화 목록에 들어 있다", "fax_seen.json" in sync._FILES)
ok("합집합으로 합쳐진다(읽은 것이 안 되살아남)",
   sync._MERGE.get("fax_seen.json") == ("set", None))

msrc = open(str(_ROOT / "python" / "planner") + "/main_window.py", encoding="utf-8").read()
ok("탭이 보이든 말든 도는 별도 타이머다", "_fax_poll" in msrc and "FAX_POLL_MS" in msrc)
ok("고객정보 탭 폴링을 쓰지 않는다", "self._fax = fax_watch.FaxFolder" in msrc)
ok("트레이에서 열 수 있다", '("받은 팩스", self.open_fax)' in msrc)
ok("여러 건은 팝업 하나로 묶는다", "팩스 {len(got)}건 도착" in msrc)

print("\n" + ("전부 통과" if not fails else f"{len(fails)}건 실패: {fails}"))
sys.exit(1 if fails else 0)
