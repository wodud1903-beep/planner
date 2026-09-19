"""'고객정보' 탭 — 자료 창고와 검색이 제대로 도는가."""
# ⚠️ 경로를 박아 두지 않는다. 예전에는 이 검사들이 작업용 임시 폴더에만 있고
# "/home/user/planner" 를 글자 그대로 들고 있어서, 컨테이너가 다시 뜨면 통째로
# 사라졌다(실제로 두 번 겪었다). 이제 저장소 안에 살고, 자기 위치에서 뿌리를 찾는다.
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]      # tools/verify/x.py → 저장소 뿌리
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
import os as _os
_os.chdir(_ROOT / "python")                          # 'planner/...' 상대경로를 쓰는 검사용
import os, shutil, sys, tempfile
from datetime import datetime

FAIL = []
def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond: FAIL.append(name)

tmp = tempfile.mkdtemp(); os.environ["APPDATA"] = tmp
os.environ["QT_QPA_PLATFORM"] = os.environ.get("PLAT", "offscreen")

from planner import customer_files as cf
from planner import config

# ---- 가짜 드라이브 폴더를 하나 만든다 ----
root = os.path.join(tmp, "고객정보")
def put(rel, data=b"x"):
    full = os.path.join(root, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb") as fp:
        fp.write(data)
    return full

put("2026-08 김상현(신한카드)/계약서.pdf", b"%PDF-1.4 test")
put("2026-08 김상현(신한카드)/신분증.jpg", b"\xff\xd8\xff\xe0jpegish")
put("2026-08 김상현(신한카드)/사업자등록증.png", b"\x89PNG\r\n\x1a\n")
put("2026-09 이수민(KB캐피탈)/견적서.pdf")
put("2026-09 박지호/메모.txt")
os.makedirs(os.path.join(root, ".tmp.drivedownload"), exist_ok=True)
put(".tmp.drivedownload/찌꺼기.jpg")
put("~$임시.docx")

print("\n[1] 로컬 폴더 훑기")
src = cf.LocalSource(root)
ok("폴더가 있으면 쓸 수 있다", src.available())
ok("없는 폴더는 못 쓴다", not cf.LocalSource(os.path.join(tmp, "없음")).available())
ok("이유를 알려 준다", "찾을 수 없습니다" in cf.LocalSource(os.path.join(tmp, "없음")).why_not())
nodes = src.scan()
names = sorted(n.name for n in nodes)
ok("폴더 3개 + 파일 5개", len(nodes) == 8, len(nodes))
ok("드라이브 찌꺼기 폴더는 건너뛴다", ".tmp.drivedownload" not in names, names)
ok("찌꺼기 폴더 안의 파일도 안 걸린다", "찌꺼기.jpg" not in names)
ok("오피스 임시파일(~$)은 뺀다", "~$임시.docx" not in names, names)

f = [n for n in nodes if n.name == "계약서.pdf"][0]
ok("PDF 로 알아본다", f.is_pdf and f.viewable and not f.is_image)
ok("위치가 폴더 이름", f.folder == "2026-08 김상현(신한카드)", f.folder)
ok("크기 표시", f.size_text().endswith("B"), f.size_text())
ok("날짜 표시", f.date_text().startswith(str(datetime.now().year)), f.date_text())
j = [n for n in nodes if n.name == "신분증.jpg"][0]
ok("JPG 는 그림", j.is_image and j.viewable)
t = [n for n in nodes if n.name == "메모.txt"][0]
ok("txt 는 미리보기 대상 아님", not t.viewable)
d = [n for n in nodes if n.is_dir][0]
ok("폴더는 크기가 빈 값", d.size_text() == "")

print("\n[2] 검색 — 고객 이름으로 그 안의 서류까지")
r = cf.search(nodes, "김상현")
ok("폴더가 걸린다", any(n.is_dir and "김상현" in n.name for n in r))
ok("그 안의 파일도 같이 나온다",
   {n.name for n in r} >= {"계약서.pdf", "신분증.jpg", "사업자등록증.png"},
   sorted(n.name for n in r))
ok("다른 고객은 안 섞인다", not any("이수민" in n.name for n in r))
ok("초성으로도 찾는다", any(n.name == "계약서.pdf" for n in cf.search(nodes, "ㄱㅅㅎ")),
   [n.name for n in cf.search(nodes, "ㄱㅅㅎ")])
ok("파일명으로도 찾는다", {n.name for n in cf.search(nodes, "신분증")} == {"신분증.jpg"})
ok("빈 검색은 전부", len(cf.search(nodes, "")) == len(nodes))
ok("없는 말은 0건", cf.search(nodes, "존재하지않는고객") == [])

print("\n[3] 차례 — 폴더 먼저, 최근 파일 먼저")
s = cf.sort_nodes(nodes)
dirs = [i for i, n in enumerate(s) if n.is_dir]
files = [i for i, n in enumerate(s) if not n.is_dir]
ok("폴더가 전부 위", max(dirs) < min(files), (dirs, files))

print("\n[4] 읽기")
ok("파일 내용을 읽는다", src.read_bytes(f).startswith(b"%PDF"))
ok("로컬 경로를 준다", os.path.isfile(src.local_path(f)))

print("\n[5] 창고 고르기 — 로컬 우선, 드라이브는 켠 사람만")
# ⚠️ 이제 지정한 폴더가 없으면 이 PC 의 구글 드라이브에서 찾아본다(drive_path).
#    검사 도는 PC 에 드라이브가 깔려 있으면 진짜 폴더가 잡혀 답이 바뀐다.
#    여기서는 그 길을 막아 둔다 — 자동 찾기 자체는 verify_drivepath 가 본다.
from planner import drive_path as _dp   # noqa: E402
_dp._bases = lambda: []
_dp.invalidate()

class S:
    files_dir = root
    files_use_drive = False
    files_drive_folder = ""
class Auth:
    def __init__(self, conn=True, scopes=None):
        self._c, self._s = conn, scopes or []
    def is_connected(self): return self._c
    def has_scope(self, sc): return (not self._s) or sc in self._s

got, why = cf.pick_source(S(), Auth())
ok("폴더가 있으면 로컬", got is not None and got.kind == "local")

class S2(S):
    files_dir = os.path.join(tmp, "없음")
got, why = cf.pick_source(S2(), Auth())
ok("폴더가 없고 드라이브도 안 켰으면 없음", got is None)
ok("이유를 돌려준다", "이 PC 에는 없습니다" in why, why)
# 무엇을 하라는 말까지 같이 간다 (예전엔 '폴더를 찾을 수 없습니다' 뿐이었다)
ok("무엇을 하라는지도 적는다", _dp.FIX_HINT in why, why)

class S3(S2):
    files_use_drive = True
    files_drive_folder = "고객정보"
got, why = cf.pick_source(S3(), Auth(True, [config.SCOPE_DRIVE_READ]))
ok("켜고 권한 있으면 드라이브", got is not None and got.kind == "drive")
got, why = cf.pick_source(S3(), Auth(True, ["다른권한"]))
ok("권한 없으면 안 쓴다", got is None)
ok("권한 없다고 알려 준다", "권한" in why, why)
got, why = cf.pick_source(S3(), Auth(False))
ok("로그아웃이면 안 쓴다", got is None)

print("\n[6] drive.readonly 는 기본 권한이 아니다")
ok("기본 목록에 없다", config.SCOPE_DRIVE_READ not in config.GOOGLE_SCOPES,
   config.GOOGLE_SCOPES)
ok("상수는 정의돼 있다", config.SCOPE_DRIVE_READ.endswith("drive.readonly"))

import inspect
from planner import google_client
sig = inspect.signature(google_client.GoogleAuth.authorize)
ok("authorize 가 추가 권한을 받는다", "extra_scopes" in sig.parameters)
srcs = inspect.getsource(google_client.GoogleAuth.authorize)
ok("추가 권한을 실제로 붙인다", "extra_scopes" in srcs and "want" in srcs)

print("\n[7] 화면 — 만들어지고, 실패해도 잠기지 않는다")
# 폴더 훑기·상위로·자동 반영은 verify_browse.py 가 자세히 본다.
# 여기서는 '막혔을 때 사용자가 손쓸 수 있는가' 만 확인한다.
from PySide6.QtWidgets import QApplication
from planner import theme
app = QApplication.instance() or QApplication([])
theme.set_theme("dark"); theme.apply_to_app(app)
import planner.customer_files_tab as _cft
POPUPS = []
_cft.QMessageBox.warning = staticmethod(
    lambda *a, **k: POPUPS.append(a[2] if len(a) > 2 else ""))
from planner.customer_files_tab import CustomerFilesTab

class SNone:
    files_dir = os.path.join(tmp, "없는폴더")
    files_use_drive = False
    files_drive_folder = ""

t2 = CustomerFilesTab(SNone(), Auth())
t2.reload(); app.processEvents()
ok("새로고침이 잠기지 않는다", t2.btn_reload.isEnabled())
ok("이유를 화면에 적는다", "없" in t2.lbl_where.text(), t2.lbl_where.text())
ok("건수 자리에도 표시", t2.lbl_count.text() != "", t2.lbl_count.text())
ok("자동갱신 타이머를 멈춘다", not t2._poll.isActive())

# 폴더를 읽다가 터져도 풀려야 한다
t3 = CustomerFilesTab(S(), Auth())
t3._gen += 1
t3._on_listed(None, f"{t3._gen}\x00일부러 낸 오류")
ok("실패해도 새로고침이 풀린다", t3.btn_reload.isEnabled())
ok("실패를 건수 자리에 알린다", "실패" in t3.lbl_count.text(), t3.lbl_count.text())
ok("무엇이 잘못됐는지도 알려 준다",
   any("일부러 낸 오류" in m for m in POPUPS), POPUPS)

# 늦게 온 예전 결과가 새 결과를 덮지 않는다
t5 = CustomerFilesTab(S(), Auth())
t5.rows = list(nodes); t5._gen = 7
t5._on_listed([], "3\x00")
ok("지난 세대 결과는 버린다", len(t5.rows) == len(nodes), len(t5.rows))

print("\n[8] 설정을 새로 읽어도 탭이 따라간다")
# 로그인하면 창이 설정 객체를 통째로 새로 만든다. 예전엔 탭이 옛 객체를 붙들어
# 폴더를 지정해도 '0건' 이었다.
t7 = CustomerFilesTab(SNone(), Auth())
ok("창이 없으면 만들 때 받은 걸 쓴다", t7.settings.files_dir == SNone.files_dir)
t7.set_settings(S())
ok("set_settings 로 갈아끼운다", t7.settings.files_dir == root, t7.settings.files_dir)

print("\n[9] 고객관리에서 넘어올 때")
t8 = CustomerFilesTab(S(), Auth())
t8.search_for("김상현")
ok("검색칸에 이름이 들어간다", t8.ed_search.text() == "김상현", t8.ed_search.text())

shutil.rmtree(tmp, ignore_errors=True)
print("\n" + ("실패 %d건: %s" % (len(FAIL), FAIL) if FAIL else "전부 통과"))
sys.exit(1 if FAIL else 0)
