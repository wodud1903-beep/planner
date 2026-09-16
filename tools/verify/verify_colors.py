"""v1.4.1 — 앱 전체가 브리핑과 같은 색 언어를 쓰는가."""
# ⚠️ 경로를 박아 두지 않는다. 예전에는 이 검사들이 작업용 임시 폴더에만 있고
# "/home/user/planner" 를 글자 그대로 들고 있어서, 컨테이너가 다시 뜨면 통째로
# 사라졌다(실제로 두 번 겪었다). 이제 저장소 안에 살고, 자기 위치에서 뿌리를 찾는다.
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]      # tools/verify/x.py → 저장소 뿌리
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
import os as _os
_os.chdir(_ROOT / "python")                          # 'planner/...' 상대경로를 쓰는 검사용
import os, re, shutil, sys, tempfile, pathlib

FAIL = []
def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond: FAIL.append(name)

tmp = tempfile.mkdtemp(); os.environ["APPDATA"] = tmp
os.environ["QT_QPA_PLATFORM"] = os.environ.get("PLAT", "vnc:size=1600x1000")

from planner import theme

# 시작 브리핑은 모달이라, 검사에서 뜨면 processEvents 가 거기서 멈춘다.
# (실제 사용에서는 떠야 맞다 — 여기서만 막는다)
from planner import startup_dialog as _sd
_sd.StartupDialog.show_for = staticmethod(lambda *a, **k: None)

def lum(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    r, g, b = (int(h[i:i+2], 16) / 255 for i in (0, 2, 4))
    f = lambda v: v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4
    return .2126 * f(r) + .7152 * f(g) + .0722 * f(b)

def ratio(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return round((hi + .05) / (lo + .05), 2)

TONES = ("blue", "green", "red", "orange", "violet", "gray")

print("\n[1] 색 언어가 한 벌인가")
ok("강조색 6가지", set(theme._STRONG[False]) == set(TONES))
ok("밝은/어두운 두 벌이 같은 이름", set(theme._STRONG[False]) == set(theme._STRONG[True]))
ok("배지 배경도 같은 이름", set(theme._STRONG_BG[False]) == set(TONES)
   and set(theme._STRONG_BG[True]) == set(TONES))
ok("채움색이 생겼다", hasattr(theme, "fill") and hasattr(theme, "fill_hover"))
ok("채움색과 hover 가 같은 이름", set(theme._FILL) == set(theme._FILL_HOVER))

print("\n[2] 강조색 — 아홉 테마 모두 4.5:1")
for t in theme.THEME_ORDER:
    theme.set_theme(t)
    p = theme.THEMES[t][1]
    for name in TONES:
        fg = theme.strong(name)
        ok(f"{t}/{name} 패널 위", ratio(fg, p["panel_bg"]) >= 4.5,
           ratio(fg, p["panel_bg"]))
        ok(f"{t}/{name} 배지 위", ratio(fg, theme.strong_bg(name)) >= 4.5,
           ratio(fg, theme.strong_bg(name)))

print("\n[3] 채운 단추 — 흰 글자 4.5:1 / 패널과 3:1")
for name in theme._FILL:
    base, hov = theme.fill(name), theme.fill_hover(name)
    ok(f"{name}: 흰 글자", ratio("#FFFFFF", base) >= 4.5, ratio("#FFFFFF", base))
    ok(f"{name}: hover 에서도 흰 글자", ratio("#FFFFFF", hov) >= 4.5,
       ratio("#FFFFFF", hov))
    ok(f"{name}: hover 가 더 진하다", lum(hov) < lum(base))
    for t in theme.THEME_ORDER:
        theme.set_theme(t)
        p = theme.THEMES[t][1]
        ok(f"{t}/{name}: 패널과 구분", ratio(base, p["panel_bg"]) >= 3.0,
           ratio(base, p["panel_bg"]))
ok("모르는 이름은 accent 로 떨어진다", theme.fill("없는색") == theme.c("accent"))

print("\n[4] 예전보다 나아졌는가 (실제로 안 읽히던 값들)")
WAS = {
    ("light", "발주 상단현황"): ("#E08A1E", "orange"),
    ("light", "만기 이력"): ("#E08A1E", "orange"),
    ("light", "이번달출고"): ("#2E9E5B", "green"),
    ("light", "안내 이력"): ("#4A7FB5", "blue"),
    ("dark", "가망고객"): ("#7B58C4", "violet"),
    ("dark", "안내 이력"): ("#4A7FB5", "blue"),
    ("dark", "일요일"): ("#D24B4B", "red"),
    ("dark", "토요일"): ("#3D74C7", "blue"),
}
for (t, what), (old, tone) in WAS.items():
    theme.set_theme(t)
    p = theme.THEMES[t][1]
    was, now = ratio(old, p["panel_bg"]), ratio(theme.strong(tone), p["panel_bg"])
    ok(f"{t}/{what}: {was} → {now}", now > was and now >= 4.5)

for what, old, tone in (("부재중 단추", "#0D9488", "teal"),
                        ("복사됨 단추", "#16A34A", "green")):
    was, now = ratio("#FFFFFF", old), ratio("#FFFFFF", theme.fill(tone))
    ok(f"{what}: 흰 글자 {was} → {now}", now > was and now >= 4.5)

print("\n[5] 색이 코드에 박혀 있지 않은가")
SRC = pathlib.Path("planner")
# 아래 둘은 일부러 뺀다.
#  google_button.py — 구글 로고와 로그인 단추 배색은 구글이 정한 브랜드 값이라
#                     테마를 따라가면 안 된다(따라가면 로고가 아니게 된다).
#  file_preview.py  — PDF 종이는 흰색이다. 테마를 따라 칠하면 문서를 실제와
#                     다르게 보여 주는 셈이 된다(어두운 화면에서 검은 종이).
ALLOW = {"theme.py", "config.py", "kb_seed.py", "icon.py", "alarm_window.py",
         "google_client.py", "greeting_tab.py", "google_button.py",
         "file_preview.py"}
HEX = re.compile(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\b")
found = {}
for f in sorted(SRC.glob("*.py")):
    if f.name in ALLOW:
        continue
    hits = []
    for i, line in enumerate(f.read_text(encoding="utf-8").split("\n"), 1):
        code = line.split("#", 1)[0] if not HEX.search(line.split("#", 1)[0] + "#") else line
        for m in HEX.finditer(line):
            before = line[:m.start()]
            if before.count('"') % 2 == 0 and before.count("'") % 2 == 0:
                continue                    # 주석·설명글 안의 색은 봐준다
            hits.append(f"{i}: {line.strip()[:70]}")
    if hits:
        found[f.name] = hits
ok("화면 코드에 색이 박혀 있지 않다", not found,
   {k: v[:2] for k, v in found.items()})
ok("멘트복사도 흰 글자만 박혀 있다 (채움색은 테마에서)",
   'color:#FFFFFF' in (SRC / "greeting_tab.py").read_text(encoding="utf-8")
   and "#2563EB" not in (SRC / "greeting_tab.py").read_text(encoding="utf-8"))
_fp = (SRC / "file_preview.py").read_text(encoding="utf-8")
ok("PDF 종이만 흰색으로 박혀 있다",
   _fp.count("#FFFFFF") == 1 and "page.fill(QColor(\"#FFFFFF\"))" in _fp)
ok("미리보기의 나머지 색은 테마에서 온다",
   "theme.c('subtext')" in _fp and "theme.c('border')" in _fp)
ok("app.py 의 죽은 스타일시트가 사라졌다",
   "GLOBAL_QSS" not in (SRC / "app.py").read_text(encoding="utf-8"))

print("\n[6] 화면 코드가 색 이름을 쓴다")
import inspect
from PySide6.QtWidgets import QApplication
from planner import calendar_window, customer_history, google_client, sheets, sync
app = QApplication([]); theme.set_theme("dark"); theme.apply_to_app(app)
from planner import config
config.set_account("t@e.com")
google_client.GoogleAuth.is_connected = lambda self: False
sync.sync_now = lambda *a, **k: (False, "")
sheets.read_rows = lambda *a, **k: (1, [], [])
from planner.main_window import MainWindow

ok("상단 현황이 색 이름을 쓴다", hasattr(MainWindow, "SUMMARY_TONES")
   and not hasattr(MainWindow, "SUMMARY_COLORS"))
ok("상단 현황 4가지", set(MainWindow.SUMMARY_TONES.values())
   == {"orange", "violet", "blue", "green"}, MainWindow.SUMMARY_TONES)
ok("진행현황도 색 이름", hasattr(MainWindow, "STATUS_TONES")
   and not hasattr(MainWindow, "STATUS_COLORS"))
D = customer_history.CustomerHistoryDialog
ok("고객 이력도 색 이름", hasattr(D, "CAT_TONES") and not hasattr(D, "CAT_COLORS"))
ok("이력 색이 전부 아는 이름",
   {v for v in D.CAT_TONES.values() if v} <= set(TONES), D.CAT_TONES)
ok("상단 현황 색이 전부 아는 이름",
   set(MainWindow.SUMMARY_TONES.values()) <= set(TONES))
ok("진행현황 색이 전부 아는 이름",
   set(MainWindow.STATUS_TONES.values()) <= set(TONES))
csrc = inspect.getsource(calendar_window)
ok("캘린더 주말이 강조색을 쓴다", 'theme.strong("red")' in csrc
   and 'theme.strong("blue")' in csrc)
msrc = inspect.getsource(MainWindow)
ok("구글 상태 라벨도 테마 색", "theme.c('status_ok')" in msrc
   and "theme.c('status_bad')" in msrc)

print("\n[7] 테마를 바꾸면 실제로 따라간다")
from planner.greeting_tab import GreetingTab, _btn_css
seen = set()
for t in theme.THEME_ORDER:
    theme.set_theme(t)
    seen.add(_btn_css("blue"))
    ok(f"{t}: 단추 css 에 채움색", theme.fill("blue") in _btn_css("blue"))
    ok(f"{t}: hover 색도 들어간다", theme.fill_hover("blue") in _btn_css("blue"))
    ok(f"{t}: 잠긴 단추는 테마 색", theme.c("btn_bg") in _btn_css("blue"))
ok("테마마다 css 가 달라진다(잠긴 색이 다르므로)",
   len(seen) == len(theme.THEME_ORDER), len(seen))

theme.set_theme("dark")
gt = GreetingTab(); gt.reload(); app.processEvents()
ok("멘트복사 카드가 만들어진다", len(gt.cards) > 0, len(gt.cards))
card = gt.cards[0]
ok("다크에서 단추가 다크 채움색", theme.fill("blue") in card.btn_after.styleSheet())
theme.set_theme("light"); theme.apply_to_app(app)
gt.apply_theme(); app.processEvents()
ok("테마를 바꾸면 단추도 따라간다",
   theme.fill("blue") in card.btn_after.styleSheet())
ok("부재중은 청록", theme.fill("teal") in card.btn_miss.styleSheet())

# 상단 현황 HTML 이 실제로 테마 색을 쓴다
theme.set_theme("dark"); theme.apply_to_app(app)
w = MainWindow()
w._show_summary([("발주", "12"), ("가망고객", "3")])
html = w.lbl_cust_summary.text()
ok("상단 현황에 강조색이 들어간다", theme.strong("orange") in html
   and theme.strong("violet") in html, html[:120])
ok("예전 박힌 색이 안 보인다", "#E08A1E" not in html and "#7B58C4" not in html)

print("\n[8] 다른 테마를 깨뜨리지 않았는가")
base = set(theme.LIGHT)
for k in theme.THEME_ORDER:
    pal = theme.THEMES[k][1]
    ok(f"{k}: 색 열쇠 그대로", set(pal) == base, sorted(base ^ set(pal)))
    theme.set_theme(k)
    q = theme.qss()
    ok(f"{k}: 미치환 자리표시자 없음", "{p[" not in q)
    ok(f"{k}: 본문 4.5:1", ratio(pal["text"], pal["panel_bg"]) >= 4.5,
       ratio(pal["text"], pal["panel_bg"]))
ok("테마는 세 가지만 남았다", theme.THEME_ORDER == ("light", "warm", "dark"),
   theme.THEME_ORDER)

theme.set_theme("light")
shutil.rmtree(tmp, ignore_errors=True)
print("\n" + ("실패 %d건: %s" % (len(FAIL), FAIL) if FAIL else "전부 통과"))
sys.exit(1 if FAIL else 0)
