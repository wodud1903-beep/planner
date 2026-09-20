"""고객정보 — 파일 넣고 빼기 · 오른쪽 단추 메뉴 · 검색 속도."""
# ⚠️ 경로를 박아 두지 않는다. 예전에는 이 검사들이 작업용 임시 폴더에만 있고
# "/home/user/planner" 를 글자 그대로 들고 있어서, 컨테이너가 다시 뜨면 통째로
# 사라졌다(실제로 두 번 겪었다). 이제 저장소 안에 살고, 자기 위치에서 뿌리를 찾는다.
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]      # tools/verify/x.py → 저장소 뿌리
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
import os as _os
_os.chdir(_ROOT / "python")                          # 'planner/...' 상대경로를 쓰는 검사용
import os, shutil, sys, tempfile, time

FAIL = []
def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond: FAIL.append(name)

tmp = tempfile.mkdtemp(); os.environ["APPDATA"] = tmp
os.environ["QT_QPA_PLATFORM"] = os.environ.get("PLAT", "offscreen")

from planner import file_ops as fo, customer_files as cf

root = os.path.join(tmp, "고객정보")
def put(rel, data=b"x"):
    p = os.path.join(root, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "wb").write(data); return p
put("2026-08 김상현/계약서.pdf", b"%PDF")
put("2026-08 김상현/신분증.png", b"\x89PNG")
put("2026-09 이수민/견적서.pdf", b"%PDF")

print("\n[1] 이름 다듬기")
ok("멀쩡한 이름은 그대로", fo.safe_name("계약서.pdf") == "계약서.pdf")
ok("앞뒤 공백은 없앤다", fo.safe_name("  신분증.png  ") == "신분증.png")
for bad in ('가/나', '가\\나', '가:나', '가*나', '가?나', '가"나', '가<나', '가>나', '가|나'):
    try:
        fo.safe_name(bad); ok(f"못 쓰는 글자 거절: {bad}", False)
    except fo.OpError:
        pass
ok("못 쓰는 글자를 전부 거절한다", True)
for nm in ("", "   ", "..."):
    try:
        fo.safe_name(nm); ok(f"빈 이름 거절: {nm!r}", False)
    except fo.OpError:
        pass
ok("빈 이름을 거절한다", True)
try:
    fo.safe_name("CON.txt"); ok("윈도 예약어 거절", False)
except fo.OpError:
    ok("윈도 예약어(CON)를 거절한다", True)
try:
    fo.safe_name("가" * 300); ok("너무 긴 이름 거절", False)
except fo.OpError:
    ok("너무 긴 이름을 거절한다", True)
ok("확장자를 붙여 준다", fo.with_ext("신분증", ".png") == "신분증.png")
ok("이미 있으면 그대로", fo.with_ext("신분증.jpg", ".png") == "신분증.jpg")

print("\n[2] 겹치는 이름은 덮어쓰지 않는다")
d = os.path.join(root, "2026-08 김상현")
p1 = fo.unique_path(d, "신분증.png")
ok("이미 있으면 (2) 를 붙인다", p1.endswith("신분증 (2).png"), os.path.basename(p1))
open(p1, "wb").write(b"x")
p2 = fo.unique_path(d, "신분증.png")
ok("그다음은 (3)", p2.endswith("신분증 (3).png"), os.path.basename(p2))
os.remove(p1)
ok("없는 이름은 그대로", os.path.basename(fo.unique_path(d, "새파일.png")) == "새파일.png")

print("\n[3] 넣기 — 끌어다 놓기 / 붙여넣기")
out = os.path.join(tmp, "바탕화면"); os.makedirs(out, exist_ok=True)
src1 = os.path.join(out, "등본.pdf"); open(src1, "wb").write(b"%PDF-1")
src2 = os.path.join(out, "사진.jpg"); open(src2, "wb").write(b"\xff\xd8")
done, failed = fo.copy_in([src1, src2], d)
ok("두 개 다 들어간다", len(done) == 2 and not failed, (done, failed))
ok("원본은 그대로 있다", os.path.exists(src1))
ok("내용이 같다", open(done[0], "rb").read() == b"%PDF-1")
done2, _ = fo.copy_in([src1], d)
ok("같은 이름은 비켜서 들어간다", done2[0].endswith("등본 (2).pdf"),
   os.path.basename(done2[0]))
done3, failed3 = fo.copy_in([os.path.join(out, "없는파일.pdf")], d)
ok("없는 파일은 실패로 알려 준다", not done3 and failed3, failed3)
ok("하나 실패해도 나머지는 넣는다",
   len(fo.copy_in([os.path.join(out, "없음.x"), src2], d)[0]) == 1)
sub = os.path.join(out, "묶음"); os.makedirs(sub, exist_ok=True)
open(os.path.join(sub, "안의파일.txt"), "wb").write(b"a")
dn, _ = fo.copy_in([sub], d)
ok("폴더째 넣을 수 있다", os.path.isdir(dn[0])
   and os.path.exists(os.path.join(dn[0], "안의파일.txt")))
saved = fo.save_bytes(b"\x89PNG-clip", d, "카톡사진.png")
ok("붙여넣은 그림을 저장한다", open(saved, "rb").read() == b"\x89PNG-clip")

print("\n[3-2] 옮기기 — 서류 폴더 안에서 다른 폴더로")
# ⚠️ 옮기기는 복사와 달리 원본이 사라진다. 거절해야 할 자리를 하나씩 못 박는다.
mv_from = fo.make_folder(root, "옮기기출발")
mv_to = fo.make_folder(root, "옮기기도착")
a1 = fo.save_bytes(b"A", mv_from, "가.png")
a2 = fo.save_bytes(b"B", mv_from, "나.png")
done, failed = fo.move_in([a1, a2], mv_to, root)
ok("둘 다 옮겨진다", len(done) == 2 and not failed, (done, failed))
ok("원본 자리에서는 사라진다", not os.path.exists(a1) and not os.path.exists(a2))
ok("내용은 그대로", open(os.path.join(mv_to, "가.png"), "rb").read() == b"A")

a3 = fo.save_bytes(b"C", mv_from, "가.png")
done, _ = fo.move_in([a3], mv_to, root)
ok("겹치면 (2) 로 비켜 준다", done[0].endswith("가 (2).png"), os.path.basename(done[0]))
ok("먼저 있던 파일은 그대로", open(os.path.join(mv_to, "가.png"), "rb").read() == b"A")

fdir = fo.make_folder(mv_from, "묶음폴더")
fo.save_bytes(b"D", fdir, "안의것.png")
done, _ = fo.move_in([fdir], mv_to, root)
ok("폴더도 통째로 옮겨진다",
   os.path.isdir(os.path.join(mv_to, "묶음폴더"))
   and os.path.exists(os.path.join(mv_to, "묶음폴더", "안의것.png")))
ok("옮긴 폴더는 원래 자리에 없다", not os.path.isdir(fdir))

inner = os.path.join(mv_to, "묶음폴더")
done, failed = fo.move_in([mv_to], inner, root)
ok("자기 안으로는 못 옮긴다", not done and failed, (done, failed))
ok("그래서 폴더가 멀쩡하다", os.path.isdir(mv_to))
done, failed = fo.move_in([src1], mv_to, root)
ok("창고 밖에서 온 것은 옮기지 않는다", not done and failed, failed)
ok("창고 밖 원본은 멀쩡하다", os.path.exists(src1))
done, failed = fo.move_in([os.path.join(mv_to, "가.png")], out, root)
ok("창고 밖으로는 못 옮긴다", not done and failed, failed)
done, failed = fo.move_in([root], mv_to, root)
ok("맨 위 폴더는 못 옮긴다", not done and failed, failed)
keep = os.path.join(mv_to, "가.png")
done, failed = fo.move_in([keep], mv_to, root)
ok("이미 그 폴더에 있으면 아무 일도 안 한다",
   not done and not failed and os.path.exists(keep), (done, failed))
done, failed = fo.move_in([os.path.join(mv_from, "없는것.png")], mv_to, root)
ok("없는 파일은 실패로 알려 준다", not done and failed, failed)
shutil.rmtree(mv_from, ignore_errors=True)
shutil.rmtree(mv_to, ignore_errors=True)

print("\n[4] 빼기 — 지우기")
victim = fo.save_bytes(b"x", d, "지울것.png")
fo.delete(victim, root)
ok("파일을 지운다", not os.path.exists(victim))
vdir = fo.make_folder(d, "지울폴더")
open(os.path.join(vdir, "안의것.txt"), "wb").write(b"a")
fo.delete(vdir, root)
ok("폴더는 통째로 지운다", not os.path.exists(vdir))
try:
    fo.delete(root, root); ok("맨 위 폴더는 못 지운다", False)
except fo.OpError:
    ok("맨 위 폴더는 못 지운다", True)
try:
    fo.delete(src1, root); ok("창고 밖은 못 지운다", False)
except fo.OpError:
    ok("창고 밖은 못 지운다", True)
ok("창고 밖 파일은 멀쩡하다", os.path.exists(src1))

print("\n[5] 이름 바꾸기 · 새 폴더")
target = fo.save_bytes(b"x", d, "바꿀것.png")
newp = fo.rename(target, "바뀐것.png", root)
ok("이름이 바뀐다", os.path.exists(newp) and not os.path.exists(target))
ok("같은 이름으로 바꾸면 그대로", fo.rename(newp, "바뀐것.png", root) == newp)
try:
    fo.rename(newp, "계약서.pdf", root); ok("이미 있는 이름 거절", False)
except fo.OpError:
    ok("이미 있는 이름은 거절한다", True)
try:
    fo.rename(src1, "아무거나.pdf", root); ok("창고 밖 거절", False)
except fo.OpError:
    ok("창고 밖 이름 바꾸기는 거절한다", True)
nf = fo.make_folder(d, "추가서류")
ok("새 폴더가 생긴다", os.path.isdir(nf))
try:
    fo.make_folder(d, "추가서류"); ok("중복 폴더 거절", False)
except fo.OpError:
    ok("이미 있는 폴더는 거절한다", True)

print("\n[6] 드라이브 주소")
dn_node = cf.Node(name="김상현", is_dir=True, key="ABC123", source="drive")
ok("드라이브 폴더 주소",
   fo.drive_url(dn_node) == "https://drive.google.com/drive/folders/ABC123",
   fo.drive_url(dn_node))
fn_node = cf.Node(name="계약서.pdf", is_dir=False, key="XYZ", source="drive")
ok("드라이브 파일 주소",
   fo.drive_url(fn_node) == "https://drive.google.com/file/d/XYZ/view")
loc = cf.Node(name="김상현", is_dir=True, key="/a/b", source="local")
ok("로컬은 바로 가는 주소가 없다", fo.drive_url(loc) == "")
ok("대신 찾아 주는 주소를 만든다",
   fo.drive_search_url("김 상현").startswith("https://drive.google.com/drive/search?q="))
ok("주소에 이름이 안전하게 들어간다", "%20" in fo.drive_search_url("김 상현"))

print("\n[7] 검색 속도 — 미리 훑고, 훑는 중에도 찾아 준다")
big = os.path.join(tmp, "큰폴더")
for i in range(300):
    dd = os.path.join(big, f"2026-{(i%12)+1:02d} 고객{i:03d}")
    os.makedirs(dd, exist_ok=True)
    for j in range(5):
        open(os.path.join(dd, f"서류{j}.pdf"), "wb").write(b"%PDF")
src = cf.LocalSource(big)
t0 = time.perf_counter(); nodes = src.scan(); el = time.perf_counter() - t0
print(f"      1800건 훑기 {el*1000:.0f}ms")
ok("전부 훑는다", len(nodes) == 300 + 1500, len(nodes))
ok("빠르다(1800건 2초 안)", el < 2.0, f"{el:.2f}s")
seen = []
src.scan(on_batch=lambda got: seen.append(len(got)))
ok("중간 결과를 계속 알려 준다", len(seen) > 10, len(seen))
ok("중간 결과가 점점 늘어난다", seen == sorted(seen), seen[:5])

print("\n[8] 화면 — 탭에 붙어 있는가")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QColor
from planner import theme
app = QApplication.instance() or QApplication([])
theme.set_theme("dark"); theme.apply_to_app(app)
import planner.customer_files_tab as cft
ASKED = []
cft.QMessageBox.question = staticmethod(
    lambda *a, **k: (ASKED.append(a[2] if len(a) > 2 else ""),
                     cft.QMessageBox.Yes)[1])
cft.QMessageBox.warning = staticmethod(lambda *a, **k: None)
cft.QMessageBox.information = staticmethod(lambda *a, **k: None)
from planner.customer_files_tab import CustomerFilesTab

class S:
    files_dir = root; drive_api_on = False; files_drive_folder = ""
class Auth:
    def is_connected(self): return False
    def has_scope(self, s): return False

def settle(t, secs=8):
    end = time.time() + secs
    while time.time() < end:
        app.processEvents()
        if not t._listing: return
        time.sleep(0.02)

tab = CustomerFilesTab(S(), Auth()); tab.resize(1000, 500); tab.show()
tab.reload(); settle(tab)
ok("고칠 수 있는 상태", tab._can_edit())
ok("지금 폴더 경로를 안다", os.path.normpath(tab._cur_dir()) == os.path.normpath(root))
tab._enter([n for n in tab.rows if n.name == "2026-08 김상현"][0]); settle(tab)
ok("들어간 폴더가 대상이 된다",
   os.path.basename(tab._cur_dir()) == "2026-08 김상현", tab._cur_dir())

# 지우기 — 물어본 다음에 지운다
before = len(tab.rows)
kill = [n for n in tab.rows if n.name == "카톡사진.png"][0]
for r, n in enumerate(tab._view):
    if n is not cft.UP_ROW and n.name == kill.name:
        tab.tbl.selectRow(r); break
tab.delete_selected(); settle(tab)
ok("지우기 전에 물어본다", any("카톡사진" in a for a in ASKED), ASKED[-1:])
ok("확인하면 지워진다", not os.path.exists(kill.key))
ok("목록에서도 빠진다", len(tab.rows) == before - 1, (before, len(tab.rows)))

# 새 폴더
cft.QInputDialog.getText = staticmethod(lambda *a, **k: ("새로만든폴더", True))
tab.new_folder(); settle(tab)
ok("새 폴더가 생긴다", os.path.isdir(os.path.join(tab._cur_dir(), "새로만든폴더")))

# 끌어다 놓기
newsrc = os.path.join(out, "끌어온것.pdf"); open(newsrc, "wb").write(b"%PDF")
class U:
    def __init__(self, p): self._p = p
    def isLocalFile(self): return True
    def toLocalFile(self): return self._p
tab._drop_files([U(newsrc)]); settle(tab)
ok("끌어다 놓으면 들어간다",
   os.path.exists(os.path.join(tab._cur_dir(), "끌어온것.pdf")))
# 넣은 파일이 검색에도 걸려야 한다. 예전엔 '검색 목록을 버렸다(index is None)'
# 까지만 봤는데, 버리고 다시 만들지 않으면 검색이 비어 버린다 — 그래서 결과로 본다.
def _wait_index(t, secs=10):
    end = time.time() + secs
    while time.time() < end:
        app.processEvents()
        if t.index is not None and not t._indexing:
            return t.index
        time.sleep(0.02)
    return t.index
_idx = _wait_index(tab)
ok("넣으면 검색 목록을 다시 만든다", _idx is not None)
ok("넣은 파일이 검색에 걸린다",
   any(n.name == "끌어온것.pdf" for n in (_idx or [])),
   f"목록 {0 if _idx is None else len(_idx)}건")

# 드라이브 주소 복사 (로컬이므로 찾아 주는 주소)
tab.tbl.selectRow(1)
tab.copy_drive_url()
ok("클립보드에 드라이브 주소가 들어간다",
   "drive.google.com" in QApplication.clipboard().text(),
   QApplication.clipboard().text()[:60])

# 읽기 전용(드라이브 조회) 모드에서는 못 고친다
class SD:
    files_dir = ""; drive_api_on = True; files_drive_folder = "고객정보"
class AuthD:
    def is_connected(self): return True
    def has_scope(self, s): return True
t2 = CustomerFilesTab(SD(), AuthD())
t2.source = cf.DriveSource(AuthD(), "고객정보")
ok("드라이브 조회 모드는 고칠 수 없다", not t2._can_edit())

import inspect
print("\n[8-2] 복사해서 카카오톡으로 · 끌어내기")
from PySide6.QtCore import QUrl
from planner.customer_files_tab import file_mime, _FileTable

# 클립보드에 실리는 모양 — 파일 목록이 본체다
_png = os.path.join(tab._cur_dir(), "복사할것.png")
img2 = QImage(60, 40, QImage.Format_RGB32); img2.fill(QColor("#2F6FD0"))
img2.save(_png)
md = file_mime([_png])
ok("파일 목록으로 실린다", md.hasUrls() and
   md.urls()[0].toLocalFile() == _png, [u.toLocalFile() for u in md.urls()])
ok("경로도 글자로 실린다", md.hasText() and _png in md.text())
ok("그림이면 그림으로도 실린다", md.hasImage())
_pdf = os.path.join(tab._cur_dir(), "계약서.pdf")
open(_pdf, "wb").write(b"%PDF-1.4")
md2 = file_mime([_pdf])
ok("PDF 는 파일로만 실린다", md2.hasUrls() and not md2.hasImage())

# Ctrl+C — 고른 파일이 클립보드에 올라간다
tab.reload(); settle(tab)
tab._enter([n for n in tab.rows if n.name == "2026-08 김상현"][0]); settle(tab)
def pick(nm):
    for r, n in enumerate(tab._view):
        if n is not cft.UP_ROW and n.name == nm:
            tab.tbl.selectRow(r); return True
    return False
ok("복사할 파일을 고른다", pick("복사할것.png"))
tab.copy_selected(); app.processEvents()
cb = QApplication.clipboard().mimeData()
ok("클립보드에 파일이 올라간다", cb.hasUrls(), cb.hasUrls())
ok("그 파일이 맞다",
   cb.hasUrls() and os.path.basename(cb.urls()[0].toLocalFile()) == "복사할것.png",
   [u.toLocalFile() for u in cb.urls()] if cb.hasUrls() else None)

# 끌어낼 때도 같은 경로를 준다
ok("끌어내기가 그 파일을 준다",
   [os.path.basename(p) for p in tab._drag_paths()] == ["복사할것.png"],
   tab._drag_paths())
# 폴더는 복사·끌어내기 대상이 아니다
for r, n in enumerate(tab._view):
    if n is not cft.UP_ROW and n.is_dir:
        tab.tbl.selectRow(r); break
ok("폴더는 끌어낼 게 없다", tab._drag_paths() == [], tab._drag_paths())

# 표가 끌어낼 수 있게 돼 있는가
# ⚠️ 끌어내기를 Qt 에 맡기지 않는다(DropOnly + dragEnabled False). 맡기면 Qt 가
#    제 방식대로 QDrag 를 시작하는데, 그 길에서는 목록 안에 놓아도 아무 일이
#    안 났다(윈도에서 두 판 연속 안 먹었다). 끌기는 마우스 이벤트로 직접 한다.
ok("받기는 Qt 에 맡긴다", tab.tbl.acceptDrops()
   and tab.tbl.dragDropMode() == cft.QAbstractItemView.DropOnly,
   tab.tbl.dragDropMode())
ok("끌기는 Qt 에 안 맡긴다", not tab.tbl.dragEnabled())
ok("끌어낼 수 있는 표를 쓴다", isinstance(tab.tbl, _FileTable))
ok("Ctrl+C 를 받는다",
   "QKeySequence.Copy" in inspect.getsource(CustomerFilesTab.eventFilter))

# 같은 폴더에 도로 놓으면 사본이 생기면 안 된다
_before = len(os.listdir(tab._cur_dir()))
class U2:
    def __init__(self, p): self._p = p
    def isLocalFile(self): return True
    def toLocalFile(self): return self._p
tab._drop_files([U2(_png)]); settle(tab)
ok("같은 폴더에 도로 놓으면 사본이 안 생긴다",
   len(os.listdir(tab._cur_dir())) == _before,
   (_before, len(os.listdir(tab._cur_dir()))))

print("\n[8-3] 여러 개 고르기 (Ctrl+클릭)")
ok("여럿 고를 수 있는 표다",
   tab.tbl.selectionMode() == cft.QAbstractItemView.ExtendedSelection,
   tab.tbl.selectionMode())
tab.reload(); settle(tab)
tab._enter([n for n in tab.rows if n.name == "2026-08 김상현"][0]); settle(tab)
files = [r for r, n in enumerate(tab._view)
         if n is not cft.UP_ROW and not n.is_dir][:3]
ok("파일이 세 개 이상 있다", len(files) == 3, len(files))
tab.tbl.clearSelection()
# ⚠️ selectRow() 는 '이것만 고른다' 라서 쌓이지 않는다(Ctrl+클릭이 아니다).
#    Ctrl+클릭과 같은 일을 하려면 선택 모델에 Select 로 더해야 한다.
from PySide6.QtCore import QItemSelectionModel as _QSM
for r in files:
    tab.tbl.selectionModel().select(
        tab.tbl.model().index(r, 0), _QSM.Select | _QSM.Rows)
app.processEvents()
ok("고른 것 셋을 다 돌려준다", len(tab._selected()) == 3,
   [n.name for n in tab._selected()])
ok("끌어내기도 셋 다 싣는다", len(tab._drag_paths()) == 3, tab._drag_paths())
tab.copy_selected(); app.processEvents()
_cb = QApplication.clipboard().mimeData()
ok("복사도 셋 다 올라간다", _cb.hasUrls() and len(_cb.urls()) == 3,
   len(_cb.urls()) if _cb.hasUrls() else None)
# 아무것도 안 골랐으면 지금 줄 하나로 친다 (예전처럼 동작)
tab.tbl.clearSelection(); tab.tbl.setCurrentCell(files[0], 0); app.processEvents()
ok("하나만 있을 때도 그대로 된다", len(tab._selected()) == 1,
   [n.name for n in tab._selected()])
# '상위 폴더로' 줄은 고른 것에 안 섞인다
tab.tbl.selectAll(); app.processEvents()
ok("'상위 폴더로' 는 빼고 준다",
   all(getattr(n, "name", "") != "" for n in tab._selected())
   and len(tab._selected()) == len(tab._view) - 1,
   (len(tab._selected()), len(tab._view)))
tab.tbl.clearSelection()

print("\n[8-4] 끌어서 폴더 위에 놓으면 그 폴더로 옮긴다")
tab.reload(); settle(tab)
dst_row = next(r for r, n in enumerate(tab._view)
               if n is not cft.UP_ROW and n.name == "2026-09 이수민")
src_node = next(n for n in tab.rows if n.name == "2026-08 김상현")
moving = os.path.join(src_node.key, "계약서.pdf")
ok("옮길 파일이 있다", os.path.exists(moving))
ok("폴더 줄이 놓을 곳이 된다",
   os.path.normpath(tab._drop_folder(dst_row))
   == os.path.normpath(os.path.join(root, "2026-09 이수민")),
   tab._drop_folder(dst_row))
file_row = next((r for r, n in enumerate(tab._view)
                 if n is not cft.UP_ROW and not n.is_dir), None)
ok("파일 줄에 놓으면 지금 폴더로",
   file_row is None
   or os.path.normpath(tab._drop_folder(file_row)) == os.path.normpath(root),
   file_row if file_row is None else tab._drop_folder(file_row))
ok("빈 자리에 놓아도 지금 폴더로",
   os.path.normpath(tab._drop_folder(None)) == os.path.normpath(root))

ASKED.clear()
tab._drop_files([U(moving)], dst_row); settle(tab)
# ⚠️ 옮기기는 되돌릴 수 없다 → 반드시 먼저 묻는다
ok("옮기기 전에 물어본다", any("옮길까요" in a for a in ASKED), ASKED[-1:])
ok("어느 폴더로 가는지 말해 준다", any("이수민" in a for a in ASKED), ASKED[-1:])
ok("그 폴더로 옮겨졌다",
   os.path.exists(os.path.join(root, "2026-09 이수민", "계약서.pdf")))
ok("원래 자리에서는 사라졌다", not os.path.exists(moving))

# 바깥에서 온 파일은 **옮기지 말고 복사**해야 한다 (원본이 사라지면 큰일)
outside = os.path.join(out, "바깥것.pdf"); open(outside, "wb").write(b"%PDF")
ASKED.clear()
tab._drop_files([U(outside)], dst_row); settle(tab)
ok("바깥 파일은 복사한다(원본이 남는다)", os.path.exists(outside))
ok("복사본이 그 폴더에 들어간다",
   os.path.exists(os.path.join(root, "2026-09 이수민", "바깥것.pdf")))
ok("복사는 묻지 않는다", not any("옮길까요" in a for a in ASKED), ASKED)

# 있던 자리에 도로 놓으면 아무 일도 없다
stay = os.path.join(root, "2026-09 이수민", "바깥것.pdf")
ASKED.clear()
tab._drop_files([U(stay)], dst_row); settle(tab)
ok("제자리에 놓으면 묻지도 않는다", not ASKED and os.path.exists(stay), ASKED)

# '상위 폴더로' 줄에 놓으면 한 겹 위로 (탐색기와 같다)
tab._enter(next(n for n in tab.rows if n.name == "2026-09 이수민")); settle(tab)
up_row = next((r for r, n in enumerate(tab._view) if n is cft.UP_ROW), None)
ok("'상위 폴더로' 줄이 있다", up_row is not None)
ok("거기에 놓으면 한 겹 위로",
   os.path.normpath(tab._drop_folder(up_row)) == os.path.normpath(root),
   tab._drop_folder(up_row))
ASKED.clear()
tab._drop_files([U(stay)], up_row); settle(tab)
ok("위 폴더로 옮겨진다", os.path.exists(os.path.join(root, "바깥것.pdf")))
ok("옮기기 전에 물어봤다", any("옮길까요" in a for a in ASKED), ASKED[-1:])

# 떨어질 곳을 칠해 준다 (어디로 가는지 안 보이면 엉뚱한 폴더로 간다)
tab.reload(); settle(tab)
folder_row = next(r for r, n in enumerate(tab._view)
                  if n is not cft.UP_ROW and n.is_dir)
tab._hint_drop(folder_row)
ok("폴더 줄을 칠한다", tab._drop_row == folder_row, tab._drop_row)
plain_row = next(r for r, n in enumerate(tab._view)
                 if n is not cft.UP_ROW and not n.is_dir)
tab._hint_drop(plain_row)
ok("파일 줄은 칠하지 않는다", tab._drop_row is None, tab._drop_row)
tab._hint_drop(folder_row); tab._hint_drop(None)
ok("칠한 것은 되돌린다", tab._drop_row is None)

print("\n[8-5] 진짜 놓기 이벤트로도 되는가")
# 여기까지는 _drop_paths 를 손으로 불렀다. 실제로는 Qt 이벤트로 들어오므로
# 자리 계산(뷰포트 좌표)과 배선까지 한 번은 진짜로 굴려 본다.
from PySide6.QtCore import QMimeData, QPoint, QPointF, QUrl as _QUrl
from PySide6.QtGui import QDropEvent
tab.reload(); settle(tab)
dst_row = next(r for r, n in enumerate(tab._view)
               if n is not cft.UP_ROW and n.name == "2026-09 이수민")
src_node = next(n for n in tab.rows if n.name == "2026-08 김상현")
mv2 = fo.save_bytes(b"%PDF", src_node.key, "이벤트로옮길것.pdf")
md3 = QMimeData(); md3.setUrls([_QUrl.fromLocalFile(mv2)])
rect = tab.tbl.visualRect(tab.tbl.model().index(dst_row, 0))
pos = QPointF(rect.center())
dev = QDropEvent(pos, Qt.CopyAction, md3, Qt.LeftButton, Qt.NoModifier)
ASKED.clear()
# ⚠️ Qt 는 이 이벤트를 **뷰의 dropEvent 로** 넣어 준다. 예전엔 창 쪽
#    eventFilter 로 받으려 했는데 거기까지 오지 않았다(이 검사로 잡았다).
tab.tbl.dropEvent(dev)
ok("놓기 이벤트를 받아 준다", dev.isAccepted())
# ⚠️ 놓는 순간에는 아직 끌기 중이라 모달 창을 띄우면 안 된다 → 다음 턴으로 미룬다
ok("그 자리에서 바로 묻지 않는다", not ASKED, ASKED)
settle(tab); app.processEvents(); settle(tab)
ok("다음 턴에 묻고 옮긴다", any("옮길까요" in a for a in ASKED), ASKED[-1:])
ok("떨어뜨린 폴더로 들어갔다",
   os.path.exists(os.path.join(root, "2026-09 이수민", "이벤트로옮길것.pdf")))
esrc2 = inspect.getsource(_FileTable.dropEvent)
ok("미루는 배선이 코드에 있다",
   "QTimer.singleShot(0" in esrc2 and "_on_drop" in esrc2)
ok("뷰가 직접 받는다", all(hasattr(_FileTable, m) for m in
   ("dropEvent", "dragMoveEvent", "dragEnterEvent", "dragLeaveEvent")))
# 지나갈 때 칠해 주는 배선도 뷰에 있다
from PySide6.QtGui import QDragMoveEvent
md4 = QMimeData(); md4.setUrls([_QUrl.fromLocalFile(mv2)])
dme = QDragMoveEvent(rect.center(), Qt.CopyAction, md4, Qt.LeftButton, Qt.NoModifier)
tab.tbl.dragMoveEvent(dme)
ok("지나가면 그 폴더 줄을 칠한다", tab._drop_row == dst_row,
   (tab._drop_row, dst_row))

print("\n[8-6] 놓기 이벤트가 안 와도 옮겨진다")
# ⚠️ 실제 윈도에서 '끌어서 폴더에 놓기' 가 전혀 안 먹었다. 검사에서 dropEvent 를
#    직접 부를 때는 멀쩡했으니, 놓기 이벤트 자체가 안 오는 길이 있는 것이다.
#    그래서 이제 끌기가 끝난 **자리**를 보고 처리한다. 그 길을 여기서 못 박는다.
tab.reload(); settle(tab)
dst_row = next(r for r, n in enumerate(tab._view)
               if n is not cft.UP_ROW and n.name == "2026-09 이수민")
src_node = next(n for n in tab.rows if n.name == "2026-08 김상현")
mv3 = fo.save_bytes(b"%PDF", src_node.key, "이벤트없이옮길것.pdf")
rect = tab.tbl.visualRect(tab.tbl.model().index(dst_row, 0))
gpos = tab.tbl.viewport().mapToGlobal(rect.center())
ASKED.clear()
tab.tbl._dropped = False
tab.tbl._finish_drag_at(gpos, [mv3])
settle(tab); app.processEvents(); settle(tab)
ok("놓기 이벤트 없이도 옮긴다",
   os.path.exists(os.path.join(root, "2026-09 이수민", "이벤트없이옮길것.pdf")),
   ASKED[-1:])
ok("그때도 한 번 묻는다", any("옮길까요" in a for a in ASKED), ASKED[-1:])

# 폴더째 옮기기 — 사장님이 말한 바로 그 동작
subdir = fo.make_folder(src_node.key, "옮겨질폴더")
fo.save_bytes(b"x", subdir, "안의서류.pdf")
ASKED.clear()
tab.tbl._dropped = False
tab.tbl._finish_drag_at(gpos, [subdir])
settle(tab); app.processEvents(); settle(tab)
ok("폴더도 하위로 들어간다",
   os.path.isdir(os.path.join(root, "2026-09 이수민", "옮겨질폴더")))
ok("폴더 안의 서류도 같이 간다",
   os.path.exists(os.path.join(root, "2026-09 이수민", "옮겨질폴더", "안의서류.pdf")))

# 창 밖에서 놓으면(카카오톡 등) 손대지 않는다 — 원본이 사라지면 큰일이다
keep2 = fo.save_bytes(b"%PDF", src_node.key, "밖으로끌것.pdf")
ASKED.clear()
tab.tbl._dropped = False
tab.tbl._finish_drag_at(QPoint(-5000, -5000), [keep2])
settle(tab); app.processEvents(); settle(tab)
ok("창 밖에 놓으면 아무 일도 안 한다", os.path.exists(keep2) and not ASKED, ASKED)

# 놓기 이벤트가 온 경우에는 뒷처리가 또 하지 않는다 (두 번 옮기면 안 된다)
src2 = inspect.getsource(_FileTable.startDrag)
ok("이벤트가 왔으면 건너뛴다", "if not self._dropped" in src2)
ok("dropEvent 가 그 표시를 남긴다",
   "_dropped = True" in inspect.getsource(_FileTable.dropEvent))
ok("끄는 동안 폴더를 칠해 준다", "_track_hover" in src2)

print("\n[8-7] 진짜 마우스로 끌어 옮기기 (누르고 · 끌고 · 놓기)")
# ⚠️ 이 검사가 없어서 두 판을 헛고쳤다. dropEvent 를 직접 부르거나 끝난 자리를
#    넘겨 주는 식으로만 봤는데, 정작 **마우스로 끌면** 아무 일도 안 났다.
#    이제는 진짜 마우스 이벤트를 보낸다 — 사람이 하는 것과 같은 길이다.
from PySide6.QtGui import QMouseEvent
from PySide6.QtCore import QPointF, QEvent as _QEv

def mouse(kind, pos, buttons=Qt.LeftButton, button=Qt.LeftButton):
    vp = tab.tbl.viewport()
    ev = QMouseEvent(kind, QPointF(pos), QPointF(vp.mapToGlobal(pos)),
                     button, buttons, Qt.NoModifier)
    app.sendEvent(vp, ev)
    app.processEvents()

def center_of(row):
    return tab.tbl.visualRect(tab.tbl.model().index(row, 0)).center()

def drag_row_to(from_row, to_row):
    """사람이 하는 것처럼: 누르고 → 조금씩 끌고 → 놓는다."""
    a, b = center_of(from_row), center_of(to_row)
    mouse(_QEv.MouseButtonPress, a)
    for t in (0.25, 0.5, 0.75, 1.0):       # 중간을 거쳐 간다(끌기로 인식되게)
        mouse(_QEv.MouseMove, a + (b - a) * t, buttons=Qt.LeftButton,
              button=Qt.NoButton)
    mouse(_QEv.MouseButtonRelease, b, buttons=Qt.NoButton)
    settle(tab); app.processEvents(); settle(tab)

tab.reload(); settle(tab)
tab._enter(next(n for n in tab.rows if n.name == "2026-08 김상현")); settle(tab)
one = fo.save_bytes(b"%PDF", tab._cur_dir(), "마우스로옮길것.pdf")
fo.make_folder(tab._cur_dir(), "받을폴더")
# ⚠️ reload() 는 맨 위 폴더로 돌아간다. 지금 폴더만 다시 읽어야 한다.
def refresh():
    tab._sig = None
    tab._list_current(quiet=False)
    settle(tab)
refresh()
f_row = next(r for r, n in enumerate(tab._view)
             if n is not cft.UP_ROW and n.name == "마우스로옮길것.pdf")
d_row = next(r for r, n in enumerate(tab._view)
             if n is not cft.UP_ROW and n.name == "받을폴더")
tab.tbl.clearSelection(); tab.tbl.selectRow(f_row); app.processEvents()
ASKED.clear()
drag_row_to(f_row, d_row)
ok("마우스로 끌어 놓으면 옮겨진다",
   os.path.exists(os.path.join(tab._cur_dir(), "받을폴더", "마우스로옮길것.pdf")),
   ASKED[-1:])
ok("그 전에 물어본다", any("옮길까요" in a for a in ASKED), ASKED[-1:])
ok("원래 자리에서는 사라진다", not os.path.exists(one))

# 여러 개를 골라 두고 그중 하나를 눌러 끌면 **고른 것 전부**가 간다
m1 = fo.save_bytes(b"A", tab._cur_dir(), "여럿1.pdf")
m2 = fo.save_bytes(b"B", tab._cur_dir(), "여럿2.pdf")
refresh()
r1 = next(r for r, n in enumerate(tab._view)
          if n is not cft.UP_ROW and n.name == "여럿1.pdf")
r2 = next(r for r, n in enumerate(tab._view)
          if n is not cft.UP_ROW and n.name == "여럿2.pdf")
d_row = next(r for r, n in enumerate(tab._view)
             if n is not cft.UP_ROW and n.name == "받을폴더")
tab.tbl.clearSelection()
for r in (r1, r2):
    tab.tbl.selectionModel().select(tab.tbl.model().index(r, 0), _QSM.Select | _QSM.Rows)
app.processEvents()
ok("둘을 골라 뒀다", len(tab._selected()) == 2, [n.name for n in tab._selected()])
ASKED.clear()
drag_row_to(r1, d_row)
ok("고른 것 둘 다 옮겨진다",
   os.path.exists(os.path.join(tab._cur_dir(), "받을폴더", "여럿1.pdf"))
   and os.path.exists(os.path.join(tab._cur_dir(), "받을폴더", "여럿2.pdf")),
   ASKED[-1:])

# 끌지 않고 그냥 누르면 그 줄만 골라진다 (탐색기와 같다)
refresh()
rows = [r for r, n in enumerate(tab._view) if n is not cft.UP_ROW][:2]
tab.tbl.clearSelection()
for r in rows:
    tab.tbl.selectionModel().select(tab.tbl.model().index(r, 0), _QSM.Select | _QSM.Rows)
app.processEvents()
mouse(_QEv.MouseButtonPress, center_of(rows[0]))
mouse(_QEv.MouseButtonRelease, center_of(rows[0]), buttons=Qt.NoButton)
ok("그냥 누르면 그 줄 하나만 남는다", len(tab._selected()) == 1,
   [n.name for n in tab._selected()])

print("\n[8-8] 창 밖으로 끌어내면 카카오톡 쪽으로 넘긴다")
# ⚠️ 목록 안에서 옮기려고 Qt 의 끌기를 껐다. 그러면서 **카카오톡으로 끌어내는
#    길도 같이 죽지 않았는지** 확인한다. 창 밖으로 나가는 순간 진짜 끌기로
#    넘겨야 한다. (진짜 QDrag 는 멈추므로 넘기는 지점만 본다)
HANDOFF = []
_real_ext = cft._FileTable._external_drag
cft._FileTable._external_drag = lambda self, paths: HANDOFF.append(list(paths))
refresh()
f_row = next(r for r, n in enumerate(tab._view) if n is not cft.UP_ROW and not n.is_dir)
tab.tbl.clearSelection(); tab.tbl.selectRow(f_row); app.processEvents()
a = center_of(f_row)
mouse(_QEv.MouseButtonPress, a)
mouse(_QEv.MouseMove, a + QPoint(30, 0), buttons=Qt.LeftButton, button=Qt.NoButton)
ok("아직 창 안이면 안 넘긴다", not HANDOFF, HANDOFF)
# 창 밖 좌표로 움직인다 — globalPosition 이 창 밖이면 넘겨야 한다
vp = tab.tbl.viewport()
far = vp.mapFromGlobal(QPoint(tab.window().frameGeometry().right() + 300,
                              tab.window().frameGeometry().bottom() + 300))
mouse(_QEv.MouseMove, far, buttons=Qt.LeftButton, button=Qt.NoButton)
ok("창 밖으로 나가면 진짜 끌기로 넘긴다", len(HANDOFF) == 1, HANDOFF)
ok("넘길 때 그 파일을 실어 준다",
   HANDOFF and HANDOFF[0] and HANDOFF[0][0].endswith(tab._view[f_row].name),
   HANDOFF[:1])
mouse(_QEv.MouseButtonRelease, far, buttons=Qt.NoButton)
ok("넘긴 뒤에는 안쪽 끌기가 풀린다", not tab.tbl._idrag)
cft._FileTable._external_drag = _real_ext

print("\n[9] 메뉴에 네 가지가 다 있는가")
msrc = inspect.getsource(CustomerFilesTab._menu)
for want in ("이름 바꾸기", "삭제", "새 폴더 만들기", "드라이브 주소 복사",
             "(Ctrl+C)"):
    ok(f"메뉴: {want}", want in msrc)
esrc = inspect.getsource(CustomerFilesTab.eventFilter)
ok("Delete 키로 지운다", "Key_Delete" in esrc)
ok("Ctrl+V 로 붙여넣는다", "QKeySequence.Paste" in esrc)
ok("끌어다 놓기는 표가 받는다", "dropEvent" in inspect.getsource(_FileTable))

shutil.rmtree(tmp, ignore_errors=True)
print("\n" + ("실패 %d건: %s" % (len(FAIL), FAIL) if FAIL else "전부 통과"))
sys.exit(1 if FAIL else 0)
