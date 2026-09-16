"""미리보기 돌리기 · PDF 보기 · 창 크기 두 가지."""
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

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QImage, QPainter, QColor, QPdfWriter, QPageSize
from PySide6.QtCore import QSizeF, QBuffer, QByteArray
app = QApplication([])
f = QFont("Malgun Gothic", 10); f.setWeight(QFont.DemiBold); app.setFont(f)
from planner import theme

# 시작 브리핑은 모달이라, 검사에서 뜨면 processEvents 가 거기서 멈춘다.
# (실제 사용에서는 떠야 맞다 — 여기서만 막는다)
from planner import startup_dialog as _sd
_sd.StartupDialog.show_for = staticmethod(lambda *a, **k: None)
theme.set_theme("dark"); theme.apply_to_app(app)
from planner.file_preview import FilePreview, HAVE_PDF

# ---- 진짜 PDF 3장을 만든다 ----
pdf_path = os.path.join(tmp, "계약서.pdf")
w = QPdfWriter(pdf_path)
w.setPageSize(QPageSize(QPageSize.A4))
p = QPainter(w)
for i in range(3):
    if i:
        w.newPage()
    p.setFont(QFont("Malgun Gothic", 48))
    p.drawText(600, 1200, f"{i+1} 장")
p.end()
PDF = open(pdf_path, "rb").read()

# ---- 가로로 긴 그림(눕혀 찍힌 서류를 흉내) ----
img = QImage(800, 400, QImage.Format_RGB32); img.fill(QColor("#2F6FD0"))
pp = QPainter(img); pp.setPen(QColor("#fff")); pp.setFont(QFont("Malgun Gothic", 40))
pp.drawText(60, 220, "신분증"); pp.end()
buf = QBuffer(); buf.open(QBuffer.WriteOnly); img.save(buf, "PNG")
IMG = bytes(buf.data())

print("\n[1] 그림 미리보기 + 돌리기")
pv = FilePreview(); pv.resize(360, 360); pv.show(); app.processEvents()
ok("돌리기 단추는 처음엔 꺼져 있다", not pv.btn_left.isEnabled())
ok("그림을 연다", pv.show_image(IMG, "k1", "신분증.png"))
ok("돌리기 단추가 켜진다", pv.btn_left.isEnabled() and pv.btn_right.isEnabled())
ok("처음엔 0도", pv.angle == 0)
pv.rotate(90);  ok("오른쪽 한 번 → 90", pv.angle == 90, pv.angle)
pv.rotate(90);  ok("두 번 → 180", pv.angle == 180, pv.angle)
pv.rotate(-90); ok("왼쪽 한 번 → 90", pv.angle == 90, pv.angle)
for _ in range(3): pv.rotate(90)
ok("한 바퀴 돌면 0", pv.angle == 0, pv.angle)
pv.rotate(-90); ok("0에서 왼쪽 → 270", pv.angle == 270, pv.angle)

# 돌리면 실제로 가로세로가 바뀐다
pv.rotate(90)                       # 0도
app.processEvents()
w0 = pv.view.pixmap().width(); h0 = pv.view.pixmap().height()
pv.rotate(90); app.processEvents()  # 90도
w1 = pv.view.pixmap().width(); h1 = pv.view.pixmap().height()
ok("가로 그림이 세로로 선다", (w0 > h0) and (h1 > w1), (w0, h0, w1, h1))

print("\n[2] 각도는 파일마다 따로 기억한다")
ok("지금 90도", pv.angle == 90)
pv.show_image(IMG, "k2", "다른파일.png")
ok("새 파일은 0도로 시작", pv.angle == 0, pv.angle)
pv.show_image(IMG, "k1", "신분증.png")
ok("돌려 뒀던 파일로 돌아오면 그 각도", pv.angle == 90, pv.angle)

print("\n[3] PDF 미리보기")
ok("QtPdf 를 쓸 수 있다", HAVE_PDF)
ok("PDF 를 연다", pv.show_pdf(PDF, "p1", "계약서.pdf"))
ok("3장으로 읽는다", pv.page_count == 3, pv.page_count)
app.processEvents()
ok("첫 장이 그려진다",
   pv.view.pixmap() is not None and not pv.view.pixmap().isNull())
ok("장 표시가 나온다", pv.lbl_page.text() == "1 / 3", pv.lbl_page.text())
ok("장 넘김 단추가 보인다", pv.btn_next.isVisible() and pv.btn_prev.isVisible())
ok("첫 장에선 이전이 꺼져 있다", not pv.btn_prev.isEnabled())
pv.go_page(1); app.processEvents()
ok("다음 장으로", pv.lbl_page.text() == "2 / 3", pv.lbl_page.text())
ok("가운데 장에선 둘 다 켜짐", pv.btn_prev.isEnabled() and pv.btn_next.isEnabled())
pv.go_page(99); app.processEvents()
ok("마지막 장을 넘어가지 않는다", pv.lbl_page.text() == "3 / 3", pv.lbl_page.text())
ok("마지막 장에선 다음이 꺼짐", not pv.btn_next.isEnabled())
pv.go_page(-5); app.processEvents()
ok("첫 장보다 앞으로는 못 간다", pv.lbl_page.text() == "1 / 3", pv.lbl_page.text())

print("\n[4] PDF 도 돌아간다")
pv.show_pdf(PDF, "p1", "계약서.pdf"); app.processEvents()
a0 = pv.view.pixmap()
pw, ph = a0.width(), a0.height()
pv.rotate(90); app.processEvents()
a1 = pv.view.pixmap()
ok("세로 A4 가 눕는다", (ph > pw) and (a1.width() > a1.height()),
   (pw, ph, a1.width(), a1.height()))
ok("PDF 각도도 기억된다", pv.angle == 90)

print("\n[5] 그림이 아닌 것 · 깨진 것")
ok("깨진 그림은 알려 준다", not pv.show_image(b"not an image", "x", "깨짐.png"))
ok("돌리기 단추가 다시 꺼진다", not pv.btn_left.isEnabled())
ok("깨진 PDF 도 알려 준다", not pv.show_pdf(b"%PDF-broken", "y", "깨짐.pdf"))
pv.show_message("폴더입니다.", "어떤폴더")
ok("안내만 띄울 수도 있다", "폴더" in pv.view.text())
ok("한 장짜리면 장 표시를 감춘다", not pv.lbl_page.isVisible())

print("\n[6] 고객정보 탭에 붙어 있는가")
root = os.path.join(tmp, "고객정보")
os.makedirs(os.path.join(root, "김상현"), exist_ok=True)
open(os.path.join(root, "김상현", "계약서.pdf"), "wb").write(PDF)
open(os.path.join(root, "김상현", "신분증.png"), "wb").write(IMG)
class S:
    files_dir = root; files_use_drive = False; files_drive_folder = ""
class Auth:
    def is_connected(self): return False
    def has_scope(self, s): return False
from planner.customer_files_tab import CustomerFilesTab
tab = CustomerFilesTab(S(), Auth()); tab.resize(1000, 500); tab.show()
tab.reload()
end = time.time() + 8
while time.time() < end and tab._listing:
    app.processEvents(); time.sleep(0.02)
ok("탭이 미리보기 위젯을 쓴다", isinstance(tab.pv, FilePreview))
tab._enter([n for n in tab.rows if n.is_dir][0])
end = time.time() + 8
while time.time() < end and tab._listing:
    app.processEvents(); time.sleep(0.02)
pdf_node = [n for n in tab.rows if n.name == "계약서.pdf"][0]
ok("PDF 도 미리보기 대상", pdf_node.viewable and pdf_node.is_pdf)
tab._preview_key = pdf_node.key      # 고른 그 파일이라는 표시(늦게 온 결과 걸러내기)
tab._on_preview(pdf_node, PDF, "")
app.processEvents()
ok("탭에서 PDF 가 열린다", tab.pv.page_count == 3, tab.pv.page_count)
# 고르고 나서 딴 걸 골랐으면 늦게 온 결과는 버려야 한다
tab._preview_key = "다른파일"
tab._on_preview(pdf_node, PDF, "")
ok("늦게 온 미리보기는 버린다", tab.pv.page_count == 3)
png_node = [n for n in tab.rows if n.name == "신분증.png"][0]
tab._preview_key = png_node.key
tab._on_preview(png_node, IMG, "")
app.processEvents()
ok("탭에서 그림도 열린다", tab.pv._src is not None)
tab.apply_theme()
ok("테마를 바꿔도 안 터진다", True)

print("\n[6-2] 확대해서 보기")
pv2 = FilePreview(); pv2.resize(400, 400); pv2.show(); app.processEvents()
ok("확대 단추는 처음엔 꺼져 있다", not pv2.btn_zoom_in.isEnabled())
pv2.show_image(IMG, "z", "신분증.png"); app.processEvents()
ok("확대 단추가 켜진다", pv2.btn_zoom_in.isEnabled() and pv2.btn_fit.isEnabled())
ok("처음엔 '맞춤'", pv2.fitted and pv2.lbl_zoom.text() == "맞춤", pv2.lbl_zoom.text())
_fit_w = pv2.view.pixmap().width()
pv2.zoom_by(1.25); app.processEvents()
ok("확대하면 배율이 잡힌다", not pv2.fitted and pv2.zoom > 0, pv2.zoom)
ok("확대하면 그림이 커진다", pv2.view.pixmap().width() > _fit_w,
   (_fit_w, pv2.view.pixmap().width()))
ok("배율을 % 로 보여 준다", "%" in pv2.lbl_zoom.text(), pv2.lbl_zoom.text())
_big = pv2.view.pixmap().width()
pv2.zoom_by(1 / 1.25); app.processEvents()
ok("축소하면 다시 작아진다", pv2.view.pixmap().width() < _big)
pv2.set_zoom(1.0); app.processEvents()
ok("100% 는 원본 크기", pv2.view.pixmap().width() == 800,
   pv2.view.pixmap().width())
pv2.set_zoom(999); ok("너무 크게는 안 간다", pv2.zoom <= pv2.MAX_ZOOM, pv2.zoom)
pv2.set_zoom(0.001); ok("너무 작게도 안 간다", pv2.zoom >= pv2.MIN_ZOOM, pv2.zoom)
pv2.zoom_fit(); app.processEvents()
ok("'맞춤' 으로 되돌아온다", pv2.fitted and pv2.view.pixmap().width() == _fit_w,
   (pv2.view.pixmap().width(), _fit_w))
pv2.mouseDoubleClickEvent(None); app.processEvents()
ok("두 번 누르면 100%", abs(pv2.zoom - 1.0) < 1e-6, pv2.zoom)
pv2.mouseDoubleClickEvent(None); app.processEvents()
ok("또 누르면 맞춤", pv2.fitted)
# 확대해도 돌리기가 같이 먹는다
pv2.set_zoom(2.0); pv2.rotate(90); app.processEvents()
ok("확대 + 돌리기", pv2.angle == 90 and pv2.view.pixmap().height() > 0)
# PDF 도 확대된다 — 늘리는 게 아니라 그 크기로 다시 그린다
pv2.show_pdf(PDF, "zp", "계약서.pdf"); app.processEvents()
ok("PDF 도 '맞춤' 으로 시작", pv2.fitted)
_pfit = pv2.view.pixmap().width()
pv2.set_zoom(pv2._fit_scale() * 2); app.processEvents()
ok("PDF 를 확대하면 커진다", pv2.view.pixmap().width() > _pfit,
   (_pfit, pv2.view.pixmap().width()))
ok("새 파일을 열면 맞춤으로 돌아온다",
   (pv2.show_image(IMG, "z2", "다른.png"), pv2.fitted)[1])
ok("스크롤 안에 담겨 있다", pv2.view.parent() is pv2.scroll.viewport())

print("\n[6-3] 확대한 그림을 끌어서 옮겨 보기")
from PySide6.QtCore import QEvent, QPointF, QPoint, Qt
from PySide6.QtGui import QMouseEvent
pv3 = FilePreview(); pv3.resize(300, 300); pv3.show(); app.processEvents()
pv3.show_image(IMG, "pan", "신분증.png"); app.processEvents()
ok("맞춤일 때는 옮길 자리가 없다", not pv3._can_pan())
pv3.set_zoom(3.0); app.processEvents()
ok("확대하면 옮길 수 있다", pv3._can_pan())
hb = pv3.scroll.horizontalScrollBar(); vb = pv3.scroll.verticalScrollBar()
hb.setValue(120); vb.setValue(90); app.processEvents()
_h0, _v0 = hb.value(), vb.value()

def _mouse(kind, gx, gy, btn=Qt.LeftButton, buttons=Qt.LeftButton):
    return QMouseEvent(kind, QPointF(5, 5), QPointF(gx, gy),
                       btn, buttons, Qt.NoModifier)

pv3.eventFilter(pv3.view, _mouse(QEvent.MouseButtonPress, 500, 500))
ok("끌기 시작을 잡는다", pv3._pan_from is not None)
# 오른쪽 아래로 끌면 그림이 따라오고 스크롤은 반대로 준다
pv3.eventFilter(pv3.view, _mouse(QEvent.MouseMove, 540, 530))
app.processEvents()
ok("끄는 만큼 가로가 움직인다", hb.value() == _h0 - 40, (hb.value(), _h0 - 40))
ok("끄는 만큼 세로가 움직인다", vb.value() == _v0 - 30, (vb.value(), _v0 - 30))
pv3.eventFilter(pv3.view, _mouse(QEvent.MouseButtonRelease, 540, 530,
                                 Qt.LeftButton, Qt.NoButton))
ok("놓으면 끌기가 끝난다", pv3._pan_from is None)
# 맞춤으로 돌아가면 끌어도 아무 일 없다
pv3.zoom_fit(); app.processEvents()
pv3.eventFilter(pv3.view, _mouse(QEvent.MouseButtonPress, 500, 500))
ok("맞춤에서는 끌기가 시작되지 않는다", pv3._pan_from is None)
ok("확대하면 손 모양 커서", (pv3.set_zoom(3.0),
                            pv3.view.cursor().shape() == Qt.OpenHandCursor)[1],
   pv3.view.cursor().shape())
pv3.zoom_fit(); app.processEvents()
ok("맞춤이면 보통 커서", pv3.view.cursor().shape() == Qt.ArrowCursor,
   pv3.view.cursor().shape())

print("\n[7] 창 크기 — 보통과 최대화 둘뿐")
from planner import config, google_client, sheets, sync
google_client.GoogleAuth.is_connected = lambda self: False
sync.sync_now = lambda *a, **k: (False, "")
sheets.read_rows = lambda *a, **k: (1, [], [])
config.set_account("t@e.com")
import inspect
from planner.main_window import MainWindow
src = inspect.getsource(MainWindow)
ok("최대화 단추를 켠다",
   "WindowMaximizeButtonHint, True" in src, )
ok("창 상태가 바뀌면 반응한다", "WindowStateChange" in src)
# 세로를 못 박으면(setFixedHeight) 창관리자가 최대화를 막는다 — 그게 최대화가
# 안 먹던 원인이었다. 대신 상한을 열어 두고 resizeEvent 가 되돌린다.
ok("창 세로를 못 박지 않는다", "self.setFixedHeight(" not in src)
ok("세로 상한을 열어 둔다", "setMaximumHeight(Q_SIZE_MAX)" in src)
ok("최대화 여부를 적어 둔다", '"maximized"' in src)
ok("켤 때 지난 상태를 되살린다", "_saved_maximized" in src
   and "showMaximized" in src)
# 실제 동작(되돌리기·제약)은 verify_reg [E] 가 살아 있는 창으로 확인한다.

shutil.rmtree(tmp, ignore_errors=True)
print("\n" + ("실패 %d건: %s" % (len(FAIL), FAIL) if FAIL else "전부 통과"))
sys.exit(1 if FAIL else 0)
