"""고객정보 탭 — 폴더 한 겹씩 열기 · 상위로 · 자동 반영 · 첫 화면 속도."""
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

from planner import customer_files as cf

# ---- 큰 창고를 하나 만든다 (고객 400명 × 서류 6장 = 2400 파일) ----
root = os.path.join(tmp, "고객정보")
N_CUST, N_DOC = 400, 6
for i in range(N_CUST):
    d = os.path.join(root, f"2026-{(i % 12) + 1:02d} 고객{i:03d}")
    os.makedirs(d, exist_ok=True)
    for j in range(N_DOC):
        with open(os.path.join(d, f"서류{j}.pdf"), "wb") as fp:
            fp.write(b"%PDF" + bytes(200))
# 한 고객 밑에 더 깊은 폴더도 둔다
deep = os.path.join(root, "2026-01 고객000", "추가서류")
os.makedirs(deep, exist_ok=True)
open(os.path.join(deep, "보증보험.pdf"), "wb").write(b"%PDF")

src = cf.LocalSource(root)

print("\n[1] 첫 화면 — 한 겹만 읽으니 빨라야 한다")
t0 = time.perf_counter(); kids = src.children(src.root_node()); t_one = time.perf_counter() - t0
t0 = time.perf_counter(); allnodes = src.scan(); t_all = time.perf_counter() - t0
print(f"      한 겹 {t_one*1000:.1f}ms ({len(kids)}건) / 전체 {t_all*1000:.1f}ms ({len(allnodes)}건)")
ok("맨 위에는 고객 폴더만 보인다", len(kids) == N_CUST, len(kids))
ok("첫 화면에 파일은 안 섞인다", all(n.is_dir for n in kids))
ok("한 겹 읽기가 전체 훑기보다 훨씬 빠르다", t_one < t_all / 5,
   f"{t_one*1000:.1f}ms vs {t_all*1000:.1f}ms")

print("\n[2] 눌러서 들어가기")
c0 = [n for n in kids if n.name == "2026-01 고객000"][0]
sub = src.children(c0)
names = sorted(n.name for n in sub)
ok("그 고객 폴더 안이 나온다", len(sub) == N_DOC + 1, len(sub))
ok("하위 폴더도 보인다", "추가서류" in names, names[:3])
ok("위치가 채워진다", all(n.folder == "2026-01 고객000" for n in sub))
deepn = [n for n in sub if n.name == "추가서류"][0]
ok("더 깊이도 들어간다", [n.name for n in src.children(deepn)] == ["보증보험.pdf"])
ok("맨 위 폴더의 rel 은 빈 값", src.root_node().rel == "")
ok("하위 폴더의 rel", deepn.rel == "2026-01 고객000/추가서류", deepn.rel)

print("\n[3] 상위 폴더로")
ok("맨 위에서는 더 못 올라간다", src.parent_of(src.root_node()) is None)
up1 = src.parent_of(deepn)
ok("한 칸 위는 그 고객 폴더", up1 is not None and up1.name == "2026-01 고객000",
   up1.name if up1 else None)
up2 = src.parent_of(up1)
ok("두 칸 위는 맨 위 폴더", up2 is not None and
   os.path.normpath(up2.key) == os.path.normpath(root))
ok("창고 밖으로는 안 나간다", src.parent_of(up2) is None)

print("\n[4] 바뀐 것 알아채기")
sig1 = cf.signature(src.children(c0))
open(os.path.join(root, "2026-01 고객000", "새서류.pdf"), "wb").write(b"%PDF")
sig2 = cf.signature(src.children(c0))
ok("파일이 늘면 요약값이 달라진다", sig1 != sig2)
os.remove(os.path.join(root, "2026-01 고객000", "새서류.pdf"))
ok("되돌리면 요약값도 돌아온다", cf.signature(src.children(c0)) == sig1)
ok("안 바뀌면 그대로", cf.signature(src.children(c0)) == sig1)

print("\n[5] 화면 — 목록·상위로·자동 반영")
from PySide6.QtWidgets import QApplication
from planner import theme
app = QApplication.instance() or QApplication([])
theme.set_theme("dark"); theme.apply_to_app(app)
import planner.customer_files_tab as cft
POPUPS = []
cft.QMessageBox.warning = staticmethod(lambda *a, **k: POPUPS.append(a[2] if len(a) > 2 else ""))
from planner.customer_files_tab import CustomerFilesTab, UP_ROW

class S:
    files_dir = root; files_use_drive = False; files_drive_folder = ""
class Auth:
    def is_connected(self): return False
    def has_scope(self, s): return False

def settle(tab, secs=8.0):
    end = time.time() + secs
    while time.time() < end:
        app.processEvents()
        if not tab._listing:
            return True
        time.sleep(0.02)
    return False

tab = CustomerFilesTab(S(), Auth()); tab.resize(1100, 600); tab.show()
t0 = time.perf_counter()
tab.reload()
ok("첫 목록이 나온다", settle(tab))
print(f"      첫 화면까지 {(time.perf_counter()-t0)*1000:.0f}ms")
ok("맨 위에서는 '상위로' 줄이 없다", tab._view and tab._view[0] is not UP_ROW)
ok("상위 단추가 꺼져 있다", not tab.btn_up.isEnabled())
ok("고객 폴더가 다 나온다", tab.tbl.rowCount() == N_CUST, tab.tbl.rowCount())
ok("건수를 알려 준다", "폴더" in tab.lbl_count.text(), tab.lbl_count.text())
ok("지금 위치를 보여 준다", "고객정보" in tab.lbl_where.text(), tab.lbl_where.text())

# 폴더로 들어가기
target = [n for n in tab.rows if n.name == "2026-01 고객000"][0]
tab._enter(target)
ok("들어가진다", settle(tab))
ok("첫 줄이 '상위 폴더로'", tab._view and tab._view[0] is UP_ROW)
ok("상위 단추가 켜진다", tab.btn_up.isEnabled())
ok("그 폴더 내용 + 상위로 한 줄", tab.tbl.rowCount() == N_DOC + 1 + 1,
   tab.tbl.rowCount())
ok("첫 줄 글자에 화살표", tab.tbl.item(0, 0).text().startswith("⬆"),
   tab.tbl.item(0, 0).text())
ok("길이 이어져 보인다", "2026-01 고객000" in tab.lbl_where.text(),
   tab.lbl_where.text())

# 상위로 돌아가기
tab.go_up()
ok("올라가진다", settle(tab))
ok("다시 맨 위", tab.tbl.rowCount() == N_CUST and not tab.btn_up.isEnabled())

print("\n[6] 새로고침을 안 눌러도 반영된다")
tab._enter(target); settle(tab)
before = tab.tbl.rowCount()
open(os.path.join(root, "2026-01 고객000", "자동추가.pdf"), "wb").write(b"%PDF")
tab._poll_tick()                       # 타이머가 부르는 그 함수
ok("조용히 다시 읽는다", settle(tab))
ok("새 파일이 저절로 나타난다", tab.tbl.rowCount() == before + 1,
   (before, tab.tbl.rowCount()))
ok("이름도 목록에 있다",
   any(n.name == "자동추가.pdf" for n in tab.rows))
os.remove(os.path.join(root, "2026-01 고객000", "자동추가.pdf"))
tab._poll_tick(); settle(tab)
ok("지우면 저절로 사라진다", tab.tbl.rowCount() == before, tab.tbl.rowCount())
ok("타이머가 돌고 있다", tab._poll.isActive())
ok("로컬은 자주 본다", cft.POLL_LOCAL <= 10, cft.POLL_LOCAL)
ok("드라이브는 드물게 본다", cft.POLL_DRIVE >= 30, cft.POLL_DRIVE)

print("\n[6-2] 머리글을 눌러 줄 세우기")
tab.go_up(); settle(tab)          # 맨 위(고객 폴더 400개)로
names = lambda: [n.name for n in tab._view if n is not UP_ROW]
ok("처음엔 이름 오름차순", names() == sorted(names()), names()[:3])
tab._on_header_clicked(0); app.processEvents()
ok("한 번 더 누르면 내림차순", names() == sorted(names(), reverse=True),
   names()[:3])
ok("머리글에 화살표", "▼" in tab.tbl.horizontalHeaderItem(0).text(),
   tab.tbl.horizontalHeaderItem(0).text())
tab._on_header_clicked(0); app.processEvents()
ok("또 누르면 오름차순", names() == sorted(names()))
ok("화살표도 바뀐다", "▲" in tab.tbl.horizontalHeaderItem(0).text())

# 파일이 있는 폴더로 들어가 크기·날짜로 세워 본다
tab._enter([n for n in tab.rows if n.name == "2026-01 고객000"][0]); settle(tab)
_date_col = tab._cols.index("날짜")
_size_col = tab._cols.index("크기")
tab._on_header_clicked(_size_col); app.processEvents()
_files = [n for n in tab._view if n is not UP_ROW and not n.is_dir]
ok("크기 오름차순", [n.size for n in _files] == sorted(n.size for n in _files),
   [n.size for n in _files][:4])
ok("크기로 세워도 폴더가 먼저",
   all(n.is_dir for n in [x for x in tab._view if x is not UP_ROW][:1]))
tab._on_header_clicked(_size_col); app.processEvents()
_files = [n for n in tab._view if n is not UP_ROW and not n.is_dir]
ok("크기 내림차순", [n.size for n in _files] == sorted((n.size for n in _files),
                                                      reverse=True))
ok("내림차순에서도 폴더가 먼저",
   all(n.is_dir for n in [x for x in tab._view if x is not UP_ROW][:1]))
tab._on_header_clicked(_date_col); app.processEvents()
_files = [n for n in tab._view if n is not UP_ROW and not n.is_dir]
_ts = [n.mtime.timestamp() if n.mtime else 0 for n in _files]
ok("날짜 오름차순", _ts == sorted(_ts))
tab._on_header_clicked(_date_col); app.processEvents()
_files = [n for n in tab._view if n is not UP_ROW and not n.is_dir]
_ts = [n.mtime.timestamp() if n.mtime else 0 for n in _files]
ok("날짜 내림차순", _ts == sorted(_ts, reverse=True))
ok("'상위 폴더로' 는 늘 맨 위", tab._view[0] is UP_ROW)
# 이름으로 되돌려 둔다 (정렬 기준은 칸 번호가 아니라 칸 이름으로 들고 있다)
tab._sort_key, tab._sort_desc = "이름", False
tab._show_browse(); app.processEvents()

print("\n[7] 검색은 전체에서 — 뒤에서 훑는다")
tab.ed_search.setText("고객007")
# 타자가 멎은 뒤 잠깐(SEARCH_DELAY) 쉬었다가 찾는다 — 그 사이도 기다려 준다
end = time.time() + 20
while time.time() < end and (tab.index is None or tab._cols != tab.SEARCH_COLS):
    app.processEvents(); time.sleep(0.02)
ok("검색 목록이 만들어진다", tab.index is not None)
app.processEvents()
ok("검색 결과가 나온다", tab.tbl.rowCount() > 0, tab.tbl.rowCount())
# 머리글 글자에는 정렬 화살표가 붙으므로, 논리적인 열 이름으로 견준다
ok("검색 중에는 '위치' 열이 생긴다", tab._cols == tab.SEARCH_COLS, tab._cols)
ok("그 고객 것만", all("고객007" in (n.name + n.folder)
                      for n in cf.search(tab.index, "고객007")))
tab.ed_search.clear(); app.processEvents()
ok("지우면 다시 폴더 보기", tab._view and tab._view[0] is UP_ROW)
ok("열도 되돌아온다", tab._cols == tab.COLS, tab._cols)
ok("검색 중엔 자동갱신이 화면을 안 흔든다", True)

print("\n[8] 읽을 곳이 없을 때")
class SNone:
    files_dir = os.path.join(tmp, "없는폴더")
    files_use_drive = False; files_drive_folder = ""
t2 = CustomerFilesTab(SNone(), Auth()); t2.reload(); app.processEvents()
ok("새로고침이 잠기지 않는다", t2.btn_reload.isEnabled())
ok("타이머를 멈춘다", not t2._poll.isActive())
ok("이유를 화면에 적는다", "없" in t2.lbl_where.text(), t2.lbl_where.text())
ok("상위 단추도 꺼 둔다", not t2.btn_up.isEnabled())

shutil.rmtree(tmp, ignore_errors=True)
print("\n" + ("실패 %d건: %s" % (len(FAIL), FAIL) if FAIL else "전부 통과"))
sys.exit(1 if FAIL else 0)
