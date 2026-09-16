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
    files_dir = root; files_use_drive = False; files_drive_folder = ""
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
    files_dir = ""; files_use_drive = True; files_drive_folder = "고객정보"
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
ok("표가 끌어내기를 켰다", tab.tbl.dragEnabled())
ok("받기·보내기 둘 다 한다",
   tab.tbl.dragDropMode() == cft.QAbstractItemView.DragDrop,
   tab.tbl.dragDropMode())
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

print("\n[9] 메뉴에 네 가지가 다 있는가")
msrc = inspect.getsource(CustomerFilesTab._menu)
for want in ("이름 바꾸기", "삭제", "새 폴더 만들기", "드라이브 주소 복사",
             "복사  (Ctrl+C)"):
    ok(f"메뉴: {want}", want in msrc)
esrc = inspect.getsource(CustomerFilesTab.eventFilter)
ok("Delete 키로 지운다", "Key_Delete" in esrc)
ok("Ctrl+V 로 붙여넣는다", "QKeySequence.Paste" in esrc)
ok("끌어다 놓기를 받는다", "QEvent.Drop" in esrc)

shutil.rmtree(tmp, ignore_errors=True)
print("\n" + ("실패 %d건: %s" % (len(FAIL), FAIL) if FAIL else "전부 통과"))
sys.exit(1 if FAIL else 0)
