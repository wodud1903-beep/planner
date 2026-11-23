"""멘트복사 [명함복사](v1.36) — 올려 둔 명함 사진을 클립보드에.

지점장: "각 캐피탈 단추에 명함 복사 — 상담후·부재중·명함복사 세 개. 미리 올려 둔 명함 사진을 클립보드에.
항상 딜레이 없이 바로 복사되도록 켜지면 먼저 불러와 두고. 구글 로그인 뒤 명함을 안 올렸으면 단추는 꺼 두고,
올려야만 켜지게."
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))

import hashlib
import os
import tempfile
import time

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QGuiApplication, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication([])

from planner import bizcard, config, google_client, greeting_tab  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


# ---- 가짜 계정 앱 전용 공간 ----
STORE = {}          # name → bytes
CALLS = []


def _find(auth, name):
    CALLS.append(("find", name))
    if name not in STORE:
        return None
    return {"id": "F_" + name, "md5Checksum": hashlib.md5(STORE[name]).hexdigest()}


def _read(auth, fid):
    CALLS.append(("read", fid))
    return STORE[fid[2:]]


def _write(auth, name, data, mime):
    CALLS.append(("write", name))
    STORE[name] = bytes(data)
    return "F_" + name


def _delete(auth, fid):
    CALLS.append(("delete", fid))
    STORE.pop(fid[2:], None)


google_client.drive_find_meta = _find
google_client.drive_read_bytes = _read
google_client.drive_write_bytes = _write
google_client.drive_delete = _delete


class _Auth:
    def __init__(self, on=True):
        self.on = on

    def is_connected(self):
        return self.on


AUTH = _Auth()


def wait_idle(card, sec=3.0):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        if not card._busy:
            app.processEvents()
            return True
        time.sleep(0.02)
    return False


def img(w=900, h=500, color="#2563EB"):
    im = QImage(w, h, QImage.Format_RGB32)
    im.fill(QColor(color))
    return im


config.set_account("me@example.com")

print("[1] 명함을 안 올렸으면 [명함복사] 는 꺼져 있다")
card = bizcard.BizCard()
card.load_local()
tab = greeting_tab.GreetingTab()
tab.set_bizcard(card, lambda: AUTH)
ok("채널 카드마다 세 단추(상담후 · 부재중 · 명함복사)", tab.cards and all(
    [c.btn_after.text(), c.btn_miss.text(), c.btn_card.text()] == ["상담후", "부재중", "명함복사"] for c in tab.cards))
ok("명함이 없으면 모두 꺼짐", all(not c.btn_card.isEnabled() for c in tab.cards))
ok("꺼진 단추에 무엇을 하라는지", greeting_tab.CARD_OFF_TIP in tab.cards[0].btn_card.toolTip())
ok("위 단추는 '명함 사진 올리기'", tab.btn_bizcard.text() == "명함 사진 올리기")
ok("주황색(amber) 채움", "#B45309" in tab.cards[0].btn_card.styleSheet())

print("[2] 로그인 전에는 올리지 않는다")
told = []
QMessageBox.information = staticmethod(lambda *a, **k: told.append(a[2] if len(a) > 2 else ""))
dlg = greeting_tab.BizCardDialog(card, lambda: _Auth(False))
dlg._put(img())
ok("로그인 안내", told and "로그인" in told[-1])
ok("명함은 그대로 없음", not card.has())

print("[3] 올리면 — 단추가 켜지고, 이 PC 사본 · 계정에 올린다")
dlg = greeting_tab.BizCardDialog(card, lambda: AUTH)
dlg._put(img(3200, 1800))
ok("바로 켜진다", all(c.btn_card.isEnabled() for c in tab.cards))
ok("위 단추 '명함 사진 ✓'", tab.btn_bizcard.text() == "명함 사진 ✓")
ok("이 PC 사본", (config.data_dir() / "bizcard.png").is_file())
ok("긴 변 1600 으로 줄여 둔다", max(card.image().width(), card.image().height()) == 1600,
   (card.image().width(), card.image().height()))
ok("계정(앱 전용 공간)에 올린다", wait_idle(card) and "bizcard.png" in STORE)
ok("올린 것 = 이 PC 사본", STORE.get("bizcard.png") == (config.data_dir() / "bizcard.png").read_bytes())

print("[4] 누르면 바로 클립보드에 그림")
QGuiApplication.clipboard().clear()
tab.cards[0].btn_card.click()
md = QGuiApplication.clipboard().mimeData()
ok("클립보드에 그림", md is not None and md.hasImage() and not QImage(md.imageData()).isNull())
ok("PNG 로도(카톡·다른 프로그램)", md is not None and md.hasFormat("image/png"))
ok("단추가 '복사됨 ✓'", tab.cards[0].btn_card.text() == "복사됨 ✓")
ok("아래 줄 안내", "명함 사진 복사됨" in tab.lbl_status.text())

print("[5] 다시 켜면 — 통신 없이 바로(먼저 불러와 둔다)")
CALLS.clear()
card2 = bizcard.BizCard()
t0 = time.perf_counter()
card2.load_local()
ms = (time.perf_counter() - t0) * 1000
ok("이 PC 사본만으로 바로 있다", card2.has() and not CALLS, f"{ms:.1f}ms · 통신 {len(CALLS)}")
QGuiApplication.clipboard().clear()
t0 = time.perf_counter()
ok("복사도 바로", card2.copy() and QGuiApplication.clipboard().mimeData().hasImage(),
   f"{(time.perf_counter() - t0) * 1000:.1f}ms")
src = (_ROOT / "python/planner/main_window.py").read_text(encoding="utf-8")
ok("켤 때 · 계정이 바뀔 때 이 PC 사본부터 읽는다", src.count("self.bizcard.load_local()") == 2)
ok("계정 확인 뒤 계정 것과 맞춘다", "self.bizcard.sync_async(self.gauth)" in src)

print("[6] 다른 PC 에서 바꿨으면 받아 온다")
other = bizcard.to_png(img(800, 450, "#15803D"))
STORE["bizcard.png"] = other
card2.sync_async(AUTH)
ok("받아서 바꾼다", wait_idle(card2) and card2.image().pixelColor(5, 5) == QColor("#15803D"))
ok("이 PC 사본도", (config.data_dir() / "bizcard.png").read_bytes() == other)

print("[7] 다른 PC 에서 뺐으면 이 PC 도 뺀다")
STORE.pop("bizcard.png")
tab.set_bizcard(card2, lambda: AUTH)
card2.sync_async(AUTH)
ok("빠진다", wait_idle(card2) and not card2.has() and not (config.data_dir() / "bizcard.png").exists())
ok("단추도 꺼진다", all(not c.btn_card.isEnabled() for c in tab.cards))

print("[8] 계정에 못 올린 것은 다음에 올린다 · 빼면 계정 것도 지운다")
google_client.drive_write_bytes = lambda *a, **k: (_ for _ in ()).throw(google_client.GoogleError("x"))
card2.set_image(img(), AUTH)
wait_idle(card2)
ok("못 올렸다 — 이 PC 에는 있다", card2.has() and "bizcard.png" not in STORE)
google_client.drive_write_bytes = _write
card2.sync_async(AUTH)
ok("다음에 맞출 때 올린다", wait_idle(card2) and "bizcard.png" in STORE)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
greeting_tab.BizCardDialog(card2, lambda: AUTH)._remove()
ok("빼면 계정 것도 지운다", wait_idle(card2) and "bizcard.png" not in STORE and not card2.has())

print("[9] 계정마다 따로")
STORE["bizcard.png"] = other
config.set_account("other@example.com")
card3 = bizcard.BizCard()
card3.load_local()
ok("다른 계정 폴더에는 명함이 없다(받기 전)", not card3.has())
card3.sync_async(AUTH)
ok("그 계정 것을 받는다", wait_idle(card3) and card3.has())

print()
print(f"{len(FAIL)}건 실패" if FAIL else "전부 통과", flush=True)
# 앱도 끝날 때 파이썬·Qt 마무리 정리를 건너뛴다(app.py os._exit) — 검사도 같게(정리 중 꺼짐 방지)
os._exit(1 if FAIL else 0)
