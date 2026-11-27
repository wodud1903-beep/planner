"""PDF 병합(v1.37, 고객정보 탭) — F3.

지점장: "jpg, pdf 등의 파일들을 다중선택 후 pdf 병합 버튼을 만든다. 단, pdf 병합 시 파일의 순서를 지정할 수
있게 한다." — 합친 결과의 쪽 수 · 차례 · 가로 쪽 · 글자(PDF 는 그대로) · 돌린 사진 · 여러 장 TIFF ·
차례 창(끌기 · ▲▼ · 빼기) · 저장 이름('폴더명_병합_YYMMDD.pdf', 겹치면 (2)) · 다 만든 뒤 [카톡으로 복사].
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
import os as _os
_os.chdir(_ROOT / "python")

import io
import os
import tempfile
import time
from datetime import date
from pathlib import Path

os.environ["APPDATA"] = tempfile.mkdtemp()
tempfile.tempdir = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
TMP = Path(tempfile.mkdtemp())

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QModelIndex, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPageSize, QPainter, QPdfWriter  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication([])

from pypdf import PdfReader, PdfWriter  # noqa: E402

from planner import pdf_merge as pm, theme  # noqa: E402
from planner import customer_files_tab as cft  # noqa: E402
from planner.pdf_merge_dialog import MergeOrderDialog, thumbnail  # noqa: E402

theme.apply_to_app(app)
FAIL = []
BOXES = []
for _n in ("information", "warning"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, _k=_n, **k: BOXES.append((_k, a[2] if len(a) > 2 else ""))))


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


def img_bytes(w, h, color, fmt="JPG", alpha=False):
    im = QImage(w, h, QImage.Format_ARGB32 if alpha else QImage.Format_RGB32)
    im.fill(QColor(0, 0, 0, 0) if alpha else QColor(color))
    if alpha:
        p = QPainter(im)
        p.fillRect(0, 0, w // 2, h, QColor(color))
        p.end()
    ba = QByteArray()
    b = QBuffer(ba)
    b.open(QIODevice.WriteOnly)
    im.save(b, fmt)
    b.close()
    return bytes(ba.data())


def text_pdf(texts):
    ba = QByteArray()
    b = QBuffer(ba)
    b.open(QIODevice.WriteOnly)
    wr = QPdfWriter(b)
    wr.setPageSize(QPageSize(QPageSize.A4))
    p = QPainter(wr)
    f = QFont("DejaVu Sans")
    f.setPointSize(20)
    p.setFont(f)
    for i, t in enumerate(texts):
        if i:
            wr.newPage()
        p.drawText(200, 400, t)
    p.end()
    b.close()
    return bytes(ba.data())


def pages_of(data):
    r = PdfReader(io.BytesIO(data))
    out = []
    for pg in r.pages:
        mb = pg.mediabox
        # 글자 뽑기는 한글 사이에 빈칸을 끼우기도 한다 — 빈칸을 빼고 견준다
        out.append((round(float(mb.width)), round(float(mb.height)), "".join((pg.extract_text() or "").split())))
    return out


A4P, A4L = (595, 842), (842, 595)

# ===========================================================================
print("[1] 합치기 — 고른 차례 그대로 · PDF 는 글자 그대로 · 그림은 A4(가로 그림은 가로 A4)")
items = [("계약서.pdf", text_pdf(["계약-1쪽", "계약-2쪽"])), ("가로사진.jpg", img_bytes(4000, 2000, "#2563EB")),
         ("세로.png", img_bytes(800, 1200, "#15803D", "PNG")), ("견적서.pdf", text_pdf(["견적-1쪽"]))]
data, n = pm.merge(items)
pg = pages_of(data)
ok("쪽 수 2 + 1 + 1 + 1 = 5", n == 5 and len(pg) == 5, n)
ok("차례 · 글자 그대로(PDF 쪽은 그림이 되지 않는다)", [t for *_s, t in pg] == ["계약-1쪽", "계약-2쪽", "", "", "견적-1쪽"],
   [t for *_s, t in pg])
ok("가로 그림 → 가로 A4 · 세로 그림 → 세로 A4", [s[:2] for s in pg] == [A4P, A4P, A4L, A4P, A4P], [s[:2] for s in pg])
rev, _n = pm.merge(list(reversed(items)))
ok("차례를 바꾸면 결과도", [t for *_s, t in pages_of(rev)] == ["견적-1쪽", "", "", "계약-1쪽", "계약-2쪽"])
big = len(data)
ok("큰 사진은 줄여 넣는다(긴 변 3000)", pm.image_frames(img_bytes(6000, 3000, "#123456"), "x.jpg")[0].width() == 3000)
ok("투명한 PNG 도", pm.merge([("투명.png", img_bytes(300, 300, "#B45309", "PNG", alpha=True))])[1] == 1)
huge = img_bytes(9000, 8000, "#334455")
fr = pm.image_frames(huge, "큰스캔.jpg")
ok("아주 큰 스캔(9000×8000 — Qt 기본 한도 256MB 넘음)도 줄여 읽는다", len(fr) == 1 and max(fr[0].width(), fr[0].height()) == 3000,
   [f.size() for f in fr])

try:
    from PIL import Image  # 검사 파일 만들기에만 — 앱은 PIL 을 쓰지 않는다
    tif = TMP / "스캔.tif"
    frames = [Image.new("RGB", (600, 800), c) for c in ("red", "green", "blue")]
    frames[0].save(tif, save_all=True, append_images=frames[1:])
    ok("여러 장 TIFF → 장마다 한 쪽", pm.merge([("스캔.tif", tif.read_bytes())])[1] == 3)
    gif = TMP / "움짤.gif"
    frames[0].save(gif, save_all=True, append_images=frames[1:])
    ok("GIF 는 첫 장만", pm.merge([("움짤.gif", gif.read_bytes())])[1] == 1)
    rot = TMP / "폰사진.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6                                  # 오른쪽으로 90° 돌려서 보라는 표시(휴대폰 세로 사진)
    Image.new("RGB", (1200, 600), "white").save(rot, exif=exif.tobytes())
    ok("휴대폰 사진 돌림(EXIF) 바로잡기 — 가로로 저장된 세로 사진 → 세로 A4",
       pages_of(pm.merge([("폰사진.jpg", rot.read_bytes())])[0])[0][:2] == A4P)
except ImportError:
    print("  (PIL 이 없어 TIFF · GIF · EXIF 검사는 건너뜀)")

print("[2] 못 합치는 것 — 까닭을 말한다")
enc = PdfWriter()
enc.append(PdfReader(io.BytesIO(text_pdf(["비밀"]))))
enc.encrypt("pw", algorithm="RC4-128")
eb = io.BytesIO()
enc.write(eb)
for nm, dt, want in (("잠김.pdf", eb.getvalue(), "암호가 걸린 PDF"), ("깨짐.pdf", b"%PDF-1.4 garbage", "PDF 를 읽지 못했습니다"),
                     ("깨짐.jpg", b"not an image", "그림을 읽지 못했습니다"), ("메모.txt", b"hi", "그림(jpg · png …)이나 PDF 만")):
    try:
        pm.merge([nm and ("앞.pdf", text_pdf(["앞"])), (nm, dt)])
        ok(f"{nm} → 오류", False)
    except pm.MergeError as e:
        ok(f"{nm} → '{want}'", want in str(e) and nm in str(e), str(e))
try:
    pm.merge([])
    ok("빈 목록", False)
except pm.MergeError as e:
    ok("빈 목록 → '합칠 파일이 없습니다'", "합칠 파일이 없습니다" in str(e))

print("[3] 저장 이름 — '폴더명_병합_YYMMDD.pdf' · 겹치면 (2)")
ok("이름", pm.suggest_name("2026-08 김상현", date(2026, 11, 27)) == "2026-08 김상현_병합_261127.pdf")
ok("못 쓰는 글자는 뺀다", pm.suggest_name('홍/길:동*', date(2026, 1, 2)) == "홍 길 동_병합_260102.pdf")
ok("폴더 이름이 없으면 '서류'", pm.suggest_name("", date(2026, 1, 2)) == "서류_병합_260102.pdf")
(TMP / "a_병합_261127.pdf").write_bytes(b"x")
(TMP / "a_병합_261127 (2).pdf").write_bytes(b"x")
ok("겹치면 (3)", pm.unique_path(TMP, "a_병합_261127.pdf").name == "a_병합_261127 (3).pdf")
ok("합칠 수 있는 것: 그림 · PDF", [pm.can_merge(x) for x in ("a.JPG", "b.jpeg", "c.png", "d.pdf", "e.tiff", "f.webp",
                                                            "g.hwp", "h.xlsx")] == [True] * 6 + [False] * 2)

# ===========================================================================
print("[4] 차례 정하기 창 — 끌기 · ▲▼ · 빼기")
dlg = MergeOrderDialog(items)
ok("고른 차례로 시작 · 번호 · PDF 쪽 수", [dlg.list.item(i).text().split("\n")[0] for i in range(4)] ==
   ["1.  계약서.pdf", "2.  가로사진.jpg", "3.  세로.png", "4.  견적서.pdf"]
   and "PDF 2쪽" in dlg.list.item(0).text() and "그림" in dlg.list.item(1).text())
ok("작은 그림(PDF 는 첫 쪽)", all(not dlg.list.item(i).icon().isNull() for i in range(4))
   and not thumbnail("계약서.pdf", items[0][1]).isNull())
dlg.list.setCurrentRow(3)
dlg.btn_up.click()
ok("▲ 위로", dlg.names() == ["계약서.pdf", "가로사진.jpg", "견적서.pdf", "세로.png"], dlg.names())
dlg.list.setCurrentRow(0)
dlg.btn_down.click()
ok("▼ 아래로 · 번호도 다시", dlg.names() == ["가로사진.jpg", "계약서.pdf", "견적서.pdf", "세로.png"]
   and dlg.list.item(0).text().startswith("1.  가로사진.jpg"), dlg.names())
dlg.list.model().moveRow(QModelIndex(), 3, QModelIndex(), 0)
app.processEvents()
ok("끌어서 옮기기(맨 아래 → 맨 위)", dlg.names() == ["세로.png", "가로사진.jpg", "계약서.pdf", "견적서.pdf"]
   and dlg.list.item(0).text().startswith("1.  세로.png"), dlg.names())
dlg.list.setCurrentRow(1)
dlg.btn_remove.click()
ok("빼기 → 파일 3개", dlg.names() == ["세로.png", "계약서.pdf", "견적서.pdf"] and dlg.lbl_count.text() == "파일 3개")
ok("차례대로 내준다", [n for n, _d in dlg.items()] == dlg.names())
ok("버튼 [병합] [취소]", (dlg.btn_merge.text(), dlg.btn_cancel.text()) == ("병합", "취소"))

# ===========================================================================
print("[5] 고객정보 탭 — 여럿 고르고 [PDF 병합] → 차례 → 저장 → 카톡으로 복사")
root = TMP / "고객정보"
cust = root / "2026-08 김상현"
cust.mkdir(parents=True)
(cust / "계약서.pdf").write_bytes(text_pdf(["계약-1쪽", "계약-2쪽"]))
(cust / "견적서.jpg").write_bytes(img_bytes(1200, 900, "#2563EB"))
(cust / "메모.txt").write_bytes(b"memo")


class S:
    files_dir = str(root)
    drive_api_on = False
    files_drive_folder = ""


class Auth:
    def is_connected(self):
        return False

    def has_scope(self, s):
        return False


def settle(t, secs=8):
    end = time.time() + secs
    while time.time() < end:
        app.processEvents()
        if not t._listing:
            return
        time.sleep(0.02)


tab = cft.CustomerFilesTab(S(), Auth())
tab.resize(1100, 600)
tab.show()
tab.reload()
settle(tab)
tab._enter([n for n in tab.rows if n.name == "2026-08 김상현"][0])
settle(tab)


def select(names):
    tab.tbl.clearSelection()
    from PySide6.QtCore import QItemSelectionModel
    sm = tab.tbl.selectionModel()
    for r, n in enumerate(tab._view):
        if n is not cft.UP_ROW and n.name in names:
            sm.select(tab.tbl.model().index(r, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
    app.processEvents()


ok("[PDF 병합] 단추가 위 줄에", tab.btn_merge.text() == "PDF 병합" and tab.btn_merge.parent() is not None)
select(["메모.txt"])
ok("합칠 수 없는 것만 고르면 꺼짐", not tab.btn_merge.isEnabled())
select(["계약서.pdf", "견적서.jpg", "메모.txt"])
ok("그림 · PDF 를 고르면 켜짐(메모.txt 는 빠진다)", tab.btn_merge.isEnabled()
   and [n.name for n in tab._merge_nodes()] == sorted(["계약서.pdf", "견적서.jpg"], key=lambda x: [
       n.name for n in tab._view if n is not cft.UP_ROW].index(x)))
seen = {}


def fake_exec(self):
    seen["names"] = self.names()
    self.list.setCurrentRow(self.list.count() - 1)
    self.move_item(-(self.list.count() - 1))       # 마지막 것을 맨 위로
    seen["order"] = self.names()
    return QDialog.Accepted


MergeOrderDialog.exec = fake_exec
asked = {}


def fake_save(parent, title, path, filt):
    asked["path"] = path
    return path, filt


QFileDialog.getSaveFileName = staticmethod(fake_save)
tab._ask_after_merge = lambda fn, pages: (asked.setdefault("pages", pages), "copy")[1]
tab.merge_selected()
settle(tab)
want = cust / pm.suggest_name("2026-08 김상현")
ok("저장 곳 = 그 고객 폴더 · 이름 '2026-08 김상현_병합_YYMMDD.pdf'", Path(asked.get("path", "")) == want, asked.get("path"))
ok("차례 창에서 바꾼 차례대로 합쳤다", want.is_file() and
   [t for *_s, t in pages_of(want.read_bytes())] == ([""] + ["계약-1쪽", "계약-2쪽"] if seen["order"][0] == "견적서.jpg"
                                                    else ["계약-1쪽", "계약-2쪽", ""]), seen)
ok("다 만든 뒤 — 쪽 수를 알려 준다", asked.get("pages") == 3)
md = QGuiApplication.clipboard().mimeData()
ok("[카톡으로 복사] → 파일이 클립보드에", md is not None and md.hasUrls()
   and Path(md.urls()[0].toLocalFile()) == want, md.urls() if md else None)
ok("지금 폴더에 저장했으니 목록에 바로 보인다", any(n.name == want.name for n in tab.rows))
asked.clear()
select(["계약서.pdf"])
tab.merge_selected()
settle(tab)
ok("또 합치면 '(2)' 를 붙여 묻는다", Path(asked.get("path", "")).name == want.stem + " (2).pdf", asked.get("path"))
# 이름을 '.pdf' 없이 적었는데 그 이름의 PDF 가 이미 있다 — 저장 창은 붙이기 전 이름으로 물었으니 다시 묻는다
before = want.read_bytes()
QUESTIONS = []
QMessageBox.question = staticmethod(lambda *a, **k: QUESTIONS.append(a[2]) or QMessageBox.No)
QFileDialog.getSaveFileName = staticmethod(lambda parent, title, path, filt: (str(want)[:-4], filt))
select(["계약서.pdf"])
tab.merge_selected()
settle(tab)
ok("'.pdf' 를 붙인 이름이 이미 있으면 묻고 · [아니오] 면 그대로", QUESTIONS and "이미 있습니다" in QUESTIONS[-1]
   and want.read_bytes() == before, QUESTIONS)
QFileDialog.getSaveFileName = staticmethod(fake_save)
BOXES.clear()
select(["메모.txt"])
tab.merge_selected()
ok("합칠 것이 없으면 안내", BOXES and "골라 주세요" in BOXES[-1][1], BOXES[-1:])

print("[6] 인터넷으로 읽는 중(드라이브 직접) — 받아 와서 합치고 '다운로드' 에 저장")


class DriveSrc:
    kind = "drive"

    def read_bytes(self, n):
        return (cust / n.name).read_bytes()

    def local_path(self, n):
        return ""


tab.source = DriveSrc()
nodes = [n for n in tab.rows if n.name in ("계약서.pdf", "견적서.jpg")]
got, failed = tab._read_for_merge(nodes)
ok("받아 온다", not failed and sorted(n for n, _d in got) == ["견적서.jpg", "계약서.pdf"])
from PySide6.QtCore import QStandardPaths  # noqa: E402
ok("저장 곳은 '다운로드'(드라이브 폴더에는 쓸 수 없다)", tab._merge_folder(nodes) ==
   (QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
    or QStandardPaths.writableLocation(QStandardPaths.DesktopLocation) or os.path.expanduser("~")))
ok("파일 이름 앞부분은 그 고객 폴더 이름", tab._merge_base_name(nodes) == "2026-08 김상현")
ok("requirements · exe 빌드에 pypdf", "pypdf" in (_ROOT / "python/requirements.txt").read_text(encoding="utf-8")
   and "collect_submodules('pypdf')" in (_ROOT / "python/planner.spec").read_text(encoding="utf-8"))

print()
print(f"{len(FAIL)}건 실패" if FAIL else "전부 통과", flush=True)
os._exit(1 if FAIL else 0)
