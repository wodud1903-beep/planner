"""멘트복사 [명함복사] — 채널(캐피탈)마다 다른 명함 사진을 클립보드에(v1.36 · 채널마다 v1.36.1).

지점장: "각 캐피탈 단추에 명함 복사 — 상담후·부재중·명함복사 세 개. 미리 올려 둔 명함 사진을 클립보드에.
항상 딜레이 없이 바로 복사되도록 켜지면 먼저 불러와 두고. 명함을 안 올렸으면 단추는 꺼 두고, 올려야만 켜지게."
다시: "각각 명함을 다르게 쓰고 싶다 — 지금은 1개만 올리면 전체가 켜진다. 단추마다 다른 명함을."
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
STORE = {}          # 파일 이름 → bytes
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


def wait_idle(cards, sec=3.0):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        if not cards._busy:
            app.processEvents()
            return True
        time.sleep(0.02)
    return False


def img(color="#2563EB", w=900, h=500):
    im = QImage(w, h, QImage.Format_RGB32)
    im.fill(QColor(color))
    return im


def clip_color():
    md = QGuiApplication.clipboard().mimeData()
    if md is None or not md.hasImage():
        return None
    return QImage(md.imageData()).pixelColor(5, 5).name().upper()


config.set_account("me@example.com")
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)

print("[1] 명함을 안 올렸으면 채널마다 [명함복사] 꺼짐 · 카드마다 [명함 올리기]")
cards = bizcard.BizCards()
cards.load_local()
tab = greeting_tab.GreetingTab()
tab.set_bizcard(cards, lambda: AUTH)
names = [c.name for c in tab.cards]
ok("채널 카드마다 세 단추(상담후 · 부재중 · 명함복사)", len(tab.cards) >= 3 and all(
    [c.btn_after.text(), c.btn_miss.text(), c.btn_card.text()] == ["상담후", "부재중", "명함복사"] for c in tab.cards))
ok("모두 꺼짐", all(not c.btn_card.isEnabled() for c in tab.cards))
ok("카드마다 [명함 올리기]", all(c.btn_cardset.text() == "명함 올리기" for c in tab.cards))
ok("위의 '전체 한 장' 단추는 없다", not hasattr(tab, "btn_bizcard"))

print("[2] 한 채널에 올리면 그 채널만 켜진다")
A, B, C = tab.cards[0], tab.cards[1], tab.cards[2]
greeting_tab.BizCardDialog(cards, lambda: AUTH, name=A.name)._put(img("#2563EB"))
ok(f"'{A.name}' 만 켜짐", A.btn_card.isEnabled() and not B.btn_card.isEnabled() and not C.btn_card.isEnabled(),
   [c.btn_card.isEnabled() for c in tab.cards])
ok(f"'{A.name}' 머리 단추 '명함 ✓'", A.btn_cardset.text() == "명함 ✓" and B.btn_cardset.text() == "명함 올리기")
greeting_tab.BizCardDialog(cards, lambda: AUTH, name=B.name)._put(img("#15803D"))
ok(f"'{B.name}' 에 다른 명함 — 둘 다 켜짐, 나머지는 꺼짐",
   A.btn_card.isEnabled() and B.btn_card.isEnabled() and not C.btn_card.isEnabled())

print("[3] 누르면 그 채널의 명함이 클립보드에")
A.btn_card.click()
ok(f"'{A.name}' → 파란 명함", clip_color() == "#2563EB", clip_color())
B.btn_card.click()
ok(f"'{B.name}' → 초록 명함", clip_color() == "#15803D", clip_color())
ok("단추 '복사됨 ✓'", B.btn_card.text() == "복사됨 ✓")
ok("로그인 전엔 올리지 않는다", (lambda d: (d._put(img("#000000")), not cards.has(C.name))[1])(
    greeting_tab.BizCardDialog(cards, lambda: _Auth(False), name=C.name)))

print("[4] 계정(앱 전용 공간)에 채널마다 따로 올린다")
ok("두 장", wait_idle(cards) and sorted(STORE) == sorted([bizcard.remote_name(bizcard.key_of(A.name)),
                                                          bizcard.remote_name(bizcard.key_of(B.name))]), sorted(STORE))
ok("긴 변 1600 으로", (lambda c: (c.set_image(C.name, img("#B45309", 3200, 1800), AUTH),
                                  max(c.image(C.name).width(), c.image(C.name).height()) == 1600)[1])(cards))
wait_idle(cards)

print("[5] 다시 켜면 — 통신 없이 바로(먼저 불러와 둔다)")
CALLS.clear()
cards2 = bizcard.BizCards()
t0 = time.perf_counter()
cards2.load_local()
ms = (time.perf_counter() - t0) * 1000
ok("채널마다 이 PC 사본만으로 바로", cards2.has(A.name) and cards2.has(B.name) and cards2.has(C.name) and not CALLS,
   f"{ms:.1f}ms · 통신 {len(CALLS)}")
t0 = time.perf_counter()
ok("복사도 바로", cards2.copy(A.name) and clip_color() == "#2563EB", f"{(time.perf_counter() - t0) * 1000:.1f}ms")
src = (_ROOT / "python/planner/main_window.py").read_text(encoding="utf-8")
ok("켤 때 · 계정이 바뀔 때 이 PC 사본부터", src.count("self.bizcard.load_local()") == 2)
ok("동기화 뒤 채널 이름으로 계정과 맞춘다", "self.bizcard.sync_async(self.gauth, [" in src)

print("[6] 다른 PC 에서 바꾼 것 · 뺀 것 · 새로 올린 것")
kA, kB, kC = (bizcard.key_of(c.name) for c in (A, B, C))
STORE[bizcard.remote_name(kA)] = bizcard.to_png(img("#7C3AED"))         # A 를 바꿨다
STORE.pop(bizcard.remote_name(kB))                                      # B 를 뺐다
D = tab.cards[3]
STORE[bizcard.remote_name(bizcard.key_of(D.name))] = bizcard.to_png(img("#0F766E"))   # D 에 새로
tab.set_bizcard(cards2, lambda: AUTH)
cards2.sync_async(AUTH, names)
ok("다 받는다", wait_idle(cards2))
ok(f"'{A.name}' 바뀐 것", cards2.image(A.name) is not None and cards2.image(A.name).pixelColor(5, 5) == QColor("#7C3AED"))
ok(f"'{B.name}' 빠짐 · 단추 꺼짐", not cards2.has(B.name) and not tab.cards[1].btn_card.isEnabled())
ok(f"'{D.name}' 새로 · 단추 켜짐", cards2.has(D.name) and tab.cards[3].btn_card.isEnabled())
ok(f"'{C.name}' 그대로", cards2.has(C.name))

print("[7] 빼기 · 못 올린 것은 다음에")
greeting_tab.BizCardDialog(cards2, lambda: AUTH, name=C.name)._remove()
ok(f"'{C.name}' 빼면 계정 것도", wait_idle(cards2) and bizcard.remote_name(kC) not in STORE and not cards2.has(C.name))
google_client.drive_write_bytes = lambda *a, **k: (_ for _ in ()).throw(google_client.GoogleError("x"))
cards2.set_image(B.name, img("#15803D"), AUTH)
wait_idle(cards2)
ok("못 올렸다 — 이 PC 에는 있다", cards2.has(B.name) and bizcard.remote_name(kB) not in STORE)
google_client.drive_write_bytes = _write
cards2.sync_async(AUTH, names)
ok("다음에 맞출 때 올린다", wait_idle(cards2) and bizcard.remote_name(kB) in STORE)

print("[8] 채널 이름을 바꾸면 명함도 따라간다")
old_name = tab.cards[0].name
tab.items[0]["name"] = old_name
got = [dict(it, _orig=it["name"]) for it in tab.items]
got[0]["name"] = old_name + " 본점"
greeting_tab.GreetingEditDialog.run = classmethod(lambda cls, items, parent=None: got)
greeting_tab.greetings.save = lambda items: None
tab._edit()
ok("새 이름으로 옮긴다", cards2.has(old_name + " 본점") and not cards2.has(old_name))
ok("새 이름 카드의 단추가 켜짐", tab.cards[0].name == old_name + " 본점" and tab.cards[0].btn_card.isEnabled())
ok("저장한 문구에 _orig 가 남지 않는다", all("_orig" not in it for it in tab.items))
wait_idle(cards2)
ok("계정에서도 옮긴다", bizcard.remote_name(bizcard.key_of(old_name + " 본점")) in STORE
   and bizcard.remote_name(bizcard.key_of(old_name)) not in STORE)

print("[9] 계정마다 따로")
config.set_account("other@example.com")
cards3 = bizcard.BizCards()
cards3.load_local()
ok("다른 계정 폴더에는 명함이 없다(받기 전)", not any(cards3.has(n) for n in names))

print()
print(f"{len(FAIL)}건 실패" if FAIL else "전부 통과", flush=True)
# 앱도 끝날 때 파이썬·Qt 마무리 정리를 건너뛴다(app.py os._exit) — 검사도 같게(정리 중 꺼짐 방지)
os._exit(1 if FAIL else 0)
