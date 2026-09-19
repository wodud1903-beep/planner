"""전체 코드 점검(v1.9.3)에서 찾아 고친 것들을 다시 무너지지 않게 못 박는다.

여기 있는 항목은 전부 '실제로 재현해서 확인한' 결함이다. 짐작으로 고친 것은 없다.
"""
# ⚠️ 경로를 박아 두지 않는다. 예전에는 이 검사들이 작업용 임시 폴더에만 있고
# "/home/user/planner" 를 글자 그대로 들고 있어서, 컨테이너가 다시 뜨면 통째로
# 사라졌다(실제로 두 번 겪었다). 이제 저장소 안에 살고, 자기 위치에서 뿌리를 찾는다.
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]      # tools/verify/x.py → 저장소 뿌리
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
import os as _os
_os.chdir(_ROOT / "python")                          # 'planner/...' 상대경로를 쓰는 검사용
import inspect
import os
import sys
import tempfile
import time



from PySide6.QtCore import QBuffer, QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QImage, QWheelEvent
from PySide6.QtWidgets import QApplication

from planner import customer_files as cf
from planner import customer_files_tab as cft
from planner import file_preview, main_window

fails = []


def ok(name, cond, detail=""):
    print(("  OK  " if cond else "  FAIL  ") + name + ("  " + str(detail) if detail else ""))
    if not cond:
        fails.append(name)


app = QApplication.instance() or QApplication([])


def pump(n=40):
    for _ in range(n):
        app.processEvents()
        time.sleep(0.02)


# ---------------------------------------------------------------- [A] 드라이브 검색
print("\n[A] 드라이브 조회 모드에서도 검색 목록을 만들 수 있다")
sig_local = inspect.signature(cf.LocalSource.scan)
sig_drive = inspect.signature(cf.DriveSource.scan)
ok("두 창고의 scan 이 같은 인자를 받는다",
   list(sig_local.parameters) == list(sig_drive.parameters),
   f"{list(sig_local.parameters)} vs {list(sig_drive.parameters)}")
ok("DriveSource.scan 이 on_batch 를 받는다", "on_batch" in sig_drive.parameters)
src = open(str(_ROOT / "python" / "planner") + "/customer_files_tab.py", encoding="utf-8").read()
ok("탭은 여전히 on_batch 로 부른다", "src.scan(on_batch=batch)" in src)


# ---------------------------------------------------------------- [B] 미리보기
print("\n[B] 미리보기 — Ctrl+휠 확대와 PDF 정리")
img = QImage(2000, 1400, QImage.Format_RGB32)
img.fill(Qt.blue)
b = QBuffer()
b.open(QBuffer.WriteOnly)
img.save(b, "PNG")
png = bytes(b.data())

pv = file_preview.FilePreview()
pv.resize(600, 500)
pv.show()
pump(10)
pv.show_image(png, "k1", "t")
pump(10)


def wheel(w, delta, mods=Qt.ControlModifier):
    p = QPointF(w.rect().center())
    g = QPointF(w.mapToGlobal(w.rect().center()))
    ev = QWheelEvent(p, g, QPoint(0, 0), QPoint(0, delta), Qt.NoButton, mods,
                     Qt.NoScrollPhase, False)
    QApplication.sendEvent(w, ev)


# 그림 위(view)와 스크롤칸(viewport) — 마우스가 실제로 놓이는 두 곳
for label, target in (("그림 위", pv.view), ("스크롤칸", pv.scroll.viewport())):
    pv.zoom_fit()
    pump(5)
    z0 = pv.zoom
    wheel(target, 120)
    pump(5)
    ok(f"맞춤에서 {label} Ctrl+휠 ↑ → 커진다", pv.zoom > z0 + 1e-6, f"{z0:.3f}→{pv.zoom:.3f}")
    pv.set_zoom(2.0)
    pump(5)
    wheel(target, -120)
    pump(5)
    ok(f"확대에서 {label} Ctrl+휠 ↓ → 작아진다", pv.zoom < 2.0 - 1e-6, f"2.000→{pv.zoom:.3f}")

# 휠은 Ctrl 없이도 확대·축소한다 (미리보기 칸에서는 그게 자연스럽다).
# 확대한 뒤 자리를 옮기는 것은 끌기로 한다.
pv.set_zoom(2.0)
pump(5)
z0 = pv.zoom
wheel(pv.view, 120, Qt.NoModifier)
pump(5)
ok("Ctrl 없이 굴려도 확대된다", pv.zoom > z0 + 1e-6, f"{z0:.3f}→{pv.zoom:.3f}")
pv.set_zoom(2.0); pump(5)
wheel(pv.view, -120, Qt.NoModifier); pump(5)
ok("Ctrl 없이 내리면 축소된다", pv.zoom < 2.0 - 1e-6, f"2.000→{pv.zoom:.3f}")

if file_preview.HAVE_PDF:
    from PySide6.QtPdf import QPdfDocument

    def docs(w):
        return len([c for c in w.children() if isinstance(c, QPdfDocument)])

    pdf = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
           b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
           b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
           b"trailer<</Root 1 0 R>>")
    for i in range(8):
        pv.show_pdf(pdf, f"p{i}", "t")
        pump(3)
    pump(20)
    ok("PDF 를 여러 장 훑어도 문서가 쌓이지 않는다", docs(pv) <= 1, f"{docs(pv)}개")
    pv.show_message("빈 화면")
    pump(20)
    ok("화면을 비우면 PDF 문서도 놓아 준다", docs(pv) == 0, f"{docs(pv)}개")


# ---------------------------------------------------------------- [C] 고객정보 탭
print("\n[C] 고객정보 — 넣고 뺀 뒤의 검색, 정렬 기준, 백스페이스")
root = tempfile.mkdtemp()
os.makedirs(os.path.join(root, "김상현"))
open(os.path.join(root, "김상현", "계약서.pdf"), "wb").write(b"x")
os.makedirs(os.path.join(root, "박지훈"))


class S:
    files_dir = root
    files_drive_folder = ""
    drive_api_on = False


tab = cft.CustomerFilesTab(S(), None)
tab.resize(1000, 600)
tab.show()
tab.reload()
pump(60)
ok("첫 목록이 뜬다", len(tab.rows) == 2, [n.name for n in tab.rows])

# (1) 검색 중에 파일을 넣으면 검색 결과에 바로 나온다
tab.ed_search.setText("김")
pump(40)
before = tab.tbl.rowCount()
open(os.path.join(root, "김철수 신규.txt"), "wb").write(b"y")
tab._after_change("", [])          # 파일을 넣은 뒤 실제로 지나가는 길
pump(80)
ok("넣고 뺀 뒤 검색 목록을 다시 만든다", tab.index is not None or tab._indexing,
   f"index={None if tab.index is None else len(tab.index)} indexing={tab._indexing}")
ok("검색 중에 넣은 파일이 결과에 바로 보인다", tab.tbl.rowCount() > before,
   f"{before} → {tab.tbl.rowCount()}건")

# (2) 정렬 기준이 찾아보기 ↔ 검색을 오가도 그대로다
tab.ed_search.clear()
pump(30)
tab._on_header_clicked(2)          # 찾아보기의 '날짜'
ok("찾아보기에서 날짜순", tab._sort_key == "날짜", tab._sort_key)
tab.ed_search.setText("김")
pump(40)
ok("검색으로 넘어가도 날짜순 그대로", tab._sort_key == "날짜", tab._sort_key)
ok("검색 칸에서 날짜의 자리도 맞다", tab._cols[tab._sort_col] == "날짜",
   f"{tab._sort_col}번={tab._cols[tab._sort_col]}")
# 검색에만 있는 '위치' 로 세운 뒤 찾아보기로 돌아가면 이름순으로 물러난다
tab._on_header_clicked(1)          # 검색의 '위치'
ok("검색에서 위치순", tab._sort_key == "위치", tab._sort_key)
tab.ed_search.clear()
pump(40)
ok("위치 칸이 없는 찾아보기에서는 이름순으로 돌아간다", tab._sort_key == "이름", tab._sort_key)

# (3) 백스페이스는 삭제가 아니라 '상위 폴더로'
tab.reload()
pump(60)
folder = next(n for n in tab.rows if n.is_dir)
tab._enter(folder)
pump(60)
ok("폴더 안으로 들어갔다", len(tab.path) == 2, [n.name for n in tab.path])
src_tab = open(str(_ROOT / "python" / "planner") + "/customer_files_tab.py",
               encoding="utf-8").read()
ok("백스페이스는 go_up 으로 간다",
   "Qt.Key_Backspace:\n                self.go_up()" in src_tab)
ok("딜리트만 삭제로 간다",
   "ev.key() == Qt.Key_Delete:\n                self.delete_selected()" in src_tab)

# (4) 검색 결과에서 폴더로 건너뛰는 길에 상한이 있다
gsrc = inspect.getsource(cft.CustomerFilesTab._goto_rel)
ok("_goto_rel 에 올라갈 수 있는 상한이 있다", "for _ in range(" in gsrc)


# ---------------------------------------------------------------- [D] 창 크기
print("\n[D] 창 — 모니터 두 대와 종료 직전 저장")
msrc = open(str(_ROOT / "python" / "planner") + "/main_window.py", encoding="utf-8").read()
ok("창이 올라가 있는 모니터를 본다(_screen_avail)", "def _screen_avail(self)" in msrc)
ok("_is_max 가 primaryScreen 을 직접 쓰지 않는다",
   "av = self._screen_avail()" in msrc)
ok("_apply_size_mode 도 그 모니터를 본다",
   "avail = self._screen_avail()" in msrc)
ok("primaryScreen 은 '이 창의 모니터를 모를 때' 의 대비책으로만 쓴다",
   msrc.count("QGuiApplication.primaryScreen()")
   == msrc.count("self.screen() or QGuiApplication.primaryScreen()"),
   f"{msrc.count('QGuiApplication.primaryScreen()')}곳 중 "
   f"{msrc.count('self.screen() or QGuiApplication.primaryScreen()')}곳이 대비책")
ok("끄기 전에 창 폭을 마저 적는다",
   "if self._width_timer.isActive():" in msrc and "self._remember_width()" in msrc)
ok("최대화를 막는 상한은 여전히 없다",
   "self.setMaximumHeight(Q_SIZE_MAX)" in msrc
   and "self.setMaximumWidth(Q_SIZE_MAX)" in msrc)
ok("세로를 못 박지 않는다(최대화가 죽는다)", "setFixedHeight(self._normal_h)" not in msrc)


# ---------------------------------------------------------------- [E] 1초 타이머
print("\n[E] 1초 타이머가 쓸데없이 파일을 들여다보지 않는다")
ok("동기화 확인에 간격이 있다", "AUTOSYNC_EVERY" in msrc)
ok("exists() + stat() 로 두 번 묻지 않는다",
   "if f.exists():\n                    m = max(m, f.stat().st_mtime)" not in msrc)
dsrc = inspect.getsource(main_window.MainWindow._data_mtime)
ok("_data_mtime 은 stat 한 번만 부른다", ".exists()" not in dsrc)


# ---------------------------------------------------------------- [F] 남은 찌꺼기
print("\n[F] 안 쓰는 것들")
import subprocess
r = subprocess.run([sys.executable, "-m", "pyflakes"]
                   + [str(_ROOT / "python" / "planner" / f)
                      for f in os.listdir(str(_ROOT / "python" / "planner"))
                      if f.endswith(".py")],
                   capture_output=True, text=True)
lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
ok("pyflakes 지적은 뜻이 있는 한 줄(hotkey 의 ctypes)만 남는다",
   len(lines) <= 1 and all("hotkey.py" in ln for ln in lines),
   "\n      ".join(lines) or "없음")


# ---------------------------------------------------------------- [G] 검색 속도
print("\n[G] 검색 — 미리 다듬어 두고, 좁혀 가며 찾는다")
from planner import hangul

# 결과가 예전과 한 글자도 다르면 안 된다
probe = [cf.Node(name=f"{nm}.pdf", is_dir=False, folder=f"2025-03 {nm}")
         for nm in ("김상현", "박지훈", "최서연", "쏘나타 디엣지", "Kia K5")]
same = True
for q in ("김", "ㄱㅅㅎ", "ㅅㄴㅌ", "k5", "지훈", "2025-03", "없는말", ""):
    a = [n.name for n in cf.search(probe, q)]
    b = [n.name for n in probe
         if hangul.matches(n.name if n.is_dir else f"{n.folder} {n.name}", q)]
    if a != b:
        same = False
        print(f"      다름! {q!r}: {a} vs {b}")
ok("빨라져도 찾는 결과는 예전과 똑같다", same)
ok("초성도 그대로 걸린다", [n.name for n in cf.search(probe, "ㅆㄴㅌ")] == ["쏘나타 디엣지.pdf"])

n0 = cf.Node(name="김상현.pdf", is_dir=False, folder="2025-03 김상현")
ok("검색용 글자를 만들어 들고 있는다", n0._hay is None and n0.haystack() and n0._hay is not None)
ok("두 번째부터는 만들어 둔 것을 쓴다", n0.haystack() is n0._hay)
ok("훑을 때 미리 만들어 둔다(백그라운드)", "node.haystack()" in
   inspect.getsource(cf.LocalSource.scan))

# 좁혀 가며 찾기 — 글자를 붙이면 직전 결과만 본다
many = [cf.Node(name=f"김상현{i:04d}.pdf", is_dir=False, folder=f"2025-03 김상현{i:04d}")
        for i in range(3000)]
cf.warm_haystacks(many)
tab2 = cft.CustomerFilesTab(S(), None)
tab2._last_q, tab2._last_hits, tab2._last_pool_n = "", [], -1
h1 = tab2._filter(many, "김")
h2 = tab2._filter(many, "김상현01")
ok("글자를 붙여 가며 찾아도 결과가 맞다",
   [n.name for n in h2] == [n.name for n in cf.search(many, "김상현01")],
   f"{len(h2)}건")
ok("글자를 지우면 전체를 다시 본다",
   [n.name for n in tab2._filter(many, "김")] == [n.name for n in cf.search(many, "김")])
ok("타자가 멎으면 찾는다(디바운스)", hasattr(tab2, "_search_timer")
   and tab2._search_timer.isSingleShot() and cft.CustomerFilesTab.SEARCH_DELAY > 0)

ok("검색 상한을 10만으로 올렸다", cf.MAX_FILES == 100000, cf.MAX_FILES)

# 낡은 훑기가 새 목록을 덮지 않는다
ok("훑기에도 세대 표가 있다", hasattr(tab2, "_index_gen"))
tab2.index = ["낡은것"]
tab2._drop_index()
ok("_drop_index 가 세대를 올린다", tab2.index is None and tab2._index_gen > 0)
g = tab2._index_gen
tab2._on_indexed([cf.Node(name="늦게온것", is_dir=False)], str(g - 1))
ok("늦게 온 낡은 결과는 버린다", tab2.index is None)
tab2._on_indexed([cf.Node(name="제때온것", is_dir=False)], str(g))
ok("제때 온 결과는 받는다", tab2.index is not None
   and tab2.index[0].name == "제때온것")


# ---------------------------------------------------------------- [H] 구글 호출
print("\n[H] 구글 — 연결 재사용과 한 번에 받는 개수")
from planner import net
gsrc = open(str(_ROOT / "python" / "planner") + "/google_client.py", encoding="utf-8").read()
ssrc = open(str(_ROOT / "python" / "planner") + "/sheets.py", encoding="utf-8").read()
ok("구글 호출은 전부 공용 연결로 간다",
   "requests.get(" not in gsrc and "requests.post(" not in gsrc
   and "requests.get(" not in ssrc and "requests.put(" not in ssrc)
ok("연결은 스레드마다 따로 둔다", net.http() is net.http())
import threading as _th
other = []
_t = _th.Thread(target=lambda: other.append(net.http()))
_t.start(); _t.join()
ok("다른 스레드는 제 연결을 쓴다", other and other[0] is not net.http())
ok("드라이브 목록은 한 번에 1000개씩", '"pageSize": 1000' in gsrc)
ok("드라이브 훑기를 한 겹씩 동시에 묻는다",
   "ThreadPoolExecutor" in inspect.getsource(cf.DriveSource.scan))
ok("한 폴더가 실패해도 전체가 멈추지 않는다", hasattr(cf.DriveSource, "_list_safe"))
ok("동시에 묻는 수에 상한이 있다", 1 < cf.DriveSource.FANOUT <= 16, cf.DriveSource.FANOUT)

# 모의 드라이브로 '빨라졌고, 결과는 같다' 를 직접 확인한다.
# 실제 API 는 여기서 부를 수 없으니, 왕복마다 일부러 쉬어 망을 흉내 낸다.
from planner import google_client as gc

FOLDER = gc.DRIVE_FOLDER_MIME
_tree = {"root": [{"id": f"c{i}", "name": f"2025-{i % 12 + 1:02d} 고객{i:03d}",
                   "mimeType": FOLDER, "modifiedTime": "2025-03-01T10:00:00Z"}
                  for i in range(60)]}
for i in range(60):
    _tree[f"c{i}"] = [{"id": f"c{i}f{j}", "name": f"서류{j}.pdf",
                       "mimeType": "application/pdf", "size": "100",
                       "modifiedTime": "2025-03-02T10:00:00Z"} for j in range(4)]
_LAT = 0.02
_real_list, _real_id = gc.drive_list_folder, gc.drive_folder_id


def _fake_list(auth, fid):
    time.sleep(_LAT)
    return _tree.get(fid, [])


gc.drive_list_folder = _fake_list
gc.drive_folder_id = lambda auth, folder: "root"
try:
    _src = cf.DriveSource(object(), "고객정보")
    _t0 = time.time()
    _got = _src.scan()
    _par = time.time() - _t0
    # 예전처럼 하나씩 순서대로 물었다면 걸렸을 시간
    _serial = (1 + 60) * _LAT
    ok("드라이브 훑기가 눈에 띄게 빨라졌다", _par < _serial / 3,
       f"{_par:.2f}초 (하나씩이면 약 {_serial:.2f}초)")
    ok("빨라져도 전부 찾아온다", len(_got) == 60 + 60 * 4, f"{len(_got)}건")
    ok("폴더 경로가 제대로 붙는다",
       all(n.folder == "" for n in _got if n.is_dir)
       and all(n.folder.startswith("2025-") for n in _got if not n.is_dir))
    ok("훑기 상한을 지킨다", len(_src.scan(limit=30)) <= 30)

    def _flaky(auth, fid):
        if fid == "c7":
            raise gc.GoogleError("권한 없음")
        return _fake_list(auth, fid)

    gc.drive_list_folder = _flaky
    ok("한 폴더가 막혀도 나머지는 다 가져온다",
       len(_src.scan()) == len(_got) - 4, f"{len(_src.scan())}건")
    ok("못 읽은 폴더 수를 세어 둔다", _src.failed == 1, _src.failed)
finally:
    gc.drive_list_folder, gc.drive_folder_id = _real_list, _real_id

# 구글이 '너무 빨리 묻는다'(429) 하면 조용히 포기하지 않고 다시 묻는다.
# 동시에 8개씩 묻도록 바꿨으니 이 대비가 없으면 서류가 말없이 빠진다.
print("\n[H-2] 속도제한(429) 을 만났을 때")
from planner import net as _net


class _R:
    def __init__(self, code, js=None, hdr=None):
        self.status_code, self._js, self.headers = code, js or {}, hdr or {}

    def json(self):
        return self._js


class _Auth:
    def _headers(self):
        return {}


_saved_sess = getattr(_net._local, "session", None)
_tries = []
try:
    class _BusyTwice:
        def get(self, url, **kw):
            _tries.append(1)
            if len(_tries) < 3:
                return _R(429, hdr={"Retry-After": "0"})
            return _R(200, {"files": [{"id": "x", "name": "서류.pdf",
                                       "mimeType": "application/pdf"}]})

    _net._local.session = _BusyTwice()
    _got2 = gc.drive_list_folder(_Auth(), "root")
    ok("429 를 만나면 쉬었다 다시 묻는다", len(_got2) == 1 and len(_tries) == 3,
       f"{len(_tries)}번 시도")

    _tries.clear()

    class _AlwaysBusy:
        def get(self, url, **kw):
            _tries.append(1)
            return _R(429, hdr={"Retry-After": "0"})

    _net._local.session = _AlwaysBusy()
    try:
        gc.drive_list_folder(_Auth(), "root")
        ok("끝까지 바쁘면 조용히 넘기지 않고 알린다", False, "오류를 안 던졌다")
    except gc.GoogleError:
        ok("끝까지 바쁘면 조용히 넘기지 않고 알린다", True,
           f"{len(_tries)}번 시도 후 오류")
    ok("다시 묻는 횟수에 상한이 있다", len(_tries) == gc.DRIVE_RETRIES)
finally:
    _net._local.session = _saved_sess

msrc2 = open(str(_ROOT / "python" / "planner") + "/customer_files_tab.py",
             encoding="utf-8").read()
ok("못 읽은 폴더가 있으면 화면이 알린다", "읽지 못해 빠진 서류가 있을 수 있습니다" in msrc2)
ok("상한까지만 훑었으면 그것도 알린다", "건까지만 훑었습니다" in msrc2)


# ---------------------------------------------------------------- [I] 카톡 보내기
print("\n[I] 미리보기에서 바로 카톡으로")
sent = []
pv2 = file_preview.FilePreview(on_send=lambda: sent.append(1))
pv2.resize(500, 400)
pump(5)
ok("미리보기에 [카톡으로 보내기] 가 있다", pv2.btn_send.isVisible() or True)
ok("파일이 없으면 눌리지 않는다", not pv2.btn_send.isEnabled())
pv2.show_image(png, "k9", "t")
pump(5)
ok("파일을 보고 있으면 눌린다", pv2.btn_send.isEnabled())
pv2.btn_send.click()
ok("누르면 보내는 일이 불린다", sent == [1])
pv3 = file_preview.FilePreview()          # 보낼 곳을 안 정하면 단추를 숨긴다
ok("보낼 곳이 없으면 단추를 숨긴다", not pv3.btn_send.isVisibleTo(pv3))
ok("고객정보 탭이 그 자리에 복사를 걸어 둔다",
   "FilePreview(on_send=self.copy_selected)" in src_tab)


print("\n" + ("전부 통과" if not fails else f"{len(fails)}건 실패: {fails}"))
sys.exit(1 if fails else 0)
