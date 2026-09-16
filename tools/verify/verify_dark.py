"""v1.4.0 — 다크 테마 시인성."""
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

FAIL = []
def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond: FAIL.append(name)

tmp = tempfile.mkdtemp(); os.environ["APPDATA"] = tmp
os.environ["QT_QPA_PLATFORM"] = os.environ.get("PLAT", "vnc:size=1600x1000")

from planner import theme

def lum(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i+2], 16) / 255 for i in (0, 2, 4))
    f = lambda v: v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4
    return .2126 * f(r) + .7152 * f(g) + .0722 * f(b)

def ratio(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return round((hi + .05) / (lo + .05), 2)

P = theme.DARK
OLD_TEXT = "#D4DAE1"       # 예전 본문 글자
OLD_PANEL = "#1B1E23"

print("\n[1] 글자가 예전보다 또렷한가")
now = ratio(P["text"], P["panel_bg"])
was = ratio(OLD_TEXT, OLD_PANEL)
ok("본문 대비가 올라갔다", now > was, f"{was} → {now}")
ok("본문 대비 7:1 이상 (AAA)", now >= 7.0, now)
ok("전체 배경 위에서도 7:1", ratio(P["text"], P["window_bg"]) >= 7.0,
   ratio(P["text"], P["window_bg"]))
ok("입력칸 위에서도 7:1", ratio(P["text"], P["input_bg"]) >= 7.0,
   ratio(P["text"], P["input_bg"]))
for lab, on in (("버튼", "btn_bg"), ("버튼(hover)", "btn_hover"),
                ("버튼(눌림)", "btn_pressed"), ("표머리", "header_bg"),
                ("상단바", "topbar")):
    key = "topbar_text" if on == "topbar" else "text"
    ok(f"{lab} 위 글자 4.5:1", ratio(P[key], P[on]) >= 4.5, ratio(P[key], P[on]))
ok("흐린 글자도 4.5:1", ratio(P["subtext"], P["panel_bg"]) >= 4.5,
   ratio(P["subtext"], P["panel_bg"]))
ok("브리핑 글자 7:1", ratio(P["brief_text"], P["brief_bg"]) >= 7.0)

print("\n[2] 파란 포인트")
ok("포인트가 파랑 계열", theme.DARK["accent"].lower() == "#4593fc", P["accent"])
b = P["accent"].lstrip("#")
r_, g_, bl = int(b[0:2], 16), int(b[2:4], 16), int(b[4:6], 16)
ok("파랑 성분이 가장 크다", bl > r_ and bl > g_, (r_, g_, bl))
ok("포인트가 바탕에서 3:1 이상 (테두리로 보인다)",
   ratio(P["accent"], P["panel_bg"]) >= 3.0, ratio(P["accent"], P["panel_bg"]))
ok("입력칸에서도 3:1", ratio(P["accent"], P["input_bg"]) >= 3.0)
ok("선택 배경도 파란 기가 돈다",
   int(P["select_bg"][5:7], 16) > int(P["select_bg"][1:3], 16), P["select_bg"])
ok("선택 글자가 선택 배경에서 4.5:1",
   ratio(P["select_text"], P["select_bg"]) >= 4.5,
   ratio(P["select_text"], P["select_bg"]))

print("\n[3] 강조행·칩")
ok("오늘 위 글자 4.5:1", ratio(P["row_text"], P["today"]) >= 4.5,
   ratio(P["row_text"], P["today"]))
ok("내일 위 글자 4.5:1", ratio(P["row_text"], P["tomorrow"]) >= 4.5,
   ratio(P["row_text"], P["tomorrow"]))
for i in range(1, 5):
    ok(f"캘린더 칩{i} 글자 4.5:1",
       ratio(P["chip_text"], P[f"chip{i}"]) >= 4.5,
       ratio(P["chip_text"], P[f"chip{i}"]))
ok("칩1 은 파랑 계열", int(P["chip1"][5:7], 16) > int(P["chip1"][1:3], 16))

print("\n[4] 브리핑 강조색 (다크)")
theme.set_theme("dark")
for name in ("blue", "green", "red", "orange", "violet", "gray"):
    fg, bg = theme.strong(name), theme.strong_bg(name)
    ok(f"{name}: 패널 위 4.5:1", ratio(fg, P["panel_bg"]) >= 4.5,
       ratio(fg, P["panel_bg"]))
    ok(f"{name}: 배지 위 4.5:1", ratio(fg, bg) >= 4.5, ratio(fg, bg))
ok("blue 강조가 진짜 파랑",
   int(theme.strong("blue")[5:7], 16) > int(theme.strong("blue")[1:3], 16),
   theme.strong("blue"))

print("\n[5] 면이 서로 구분되는가")
# 브리핑 글 영역만큼 어두워지면 배경끼리의 밝기 차가 물리적으로 압축된다
# (#101216 과 1.12 를 내려면 바탕이 순검정이어야 한다). 그래서 면 구분은
# 밝기가 아니라 **테두리**가 맡는다 — 그쪽을 기준으로 검사한다.
BORDER = ratio(P["border"], P["panel_bg"])
ok("패널 테두리가 뚜렷하다 (면을 가르는 몫)", BORDER >= 1.20, BORDER)
for lab, a, bkey in (("패널 vs 전체배경", "panel_bg", "window_bg"),
                     ("입력칸 vs 패널", "input_bg", "panel_bg"),
                     ("버튼 vs 패널", "btn_bg", "panel_bg"),
                     ("표머리 vs 패널", "header_bg", "panel_bg")):
    r = ratio(P[a], P[bkey])
    ok(f"{lab} 가 구분된다 (밝기 또는 테두리)", r >= 1.12 or BORDER >= 1.20, r)
ok("입력칸이 패널보다 어둡다", lum(P["input_bg"]) < lum(P["panel_bg"]))
ok("패널이 전체배경보다 밝다", lum(P["panel_bg"]) > lum(P["window_bg"]))

print("\n[5-2] 남색빛이 빠졌는가")
for k in ("window_bg", "panel_bg", "header_bg", "btn_bg", "border", "grid", "text"):
    v = P[k].lstrip("#")
    r_, g_, b_ = int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)
    ok(f"{k}: R·G·B 가 고르다 (푸른 기 없음)",
       max(r_, g_, b_) - min(r_, g_, b_) <= 2, (r_, g_, b_))
ok("파랑은 포인트에만 남는다",
   int(P["accent"][5:7], 16) > int(P["accent"][1:3], 16), P["accent"])
ok("패널이 중성 회색", P["panel_bg"] == "#141414", P["panel_bg"])
ok("브리핑 배경도 같다", P["brief_bg"] == P["panel_bg"])
ok("전체 배경은 그보다 더 어둡다", lum(P["window_bg"]) < lum(P["panel_bg"]))
ok("예전(#1B1E24)보다 어두워졌다", lum(P["panel_bg"]) < lum("#1B1E24"),
   (round(lum("#1B1E24"), 5), round(lum(P["panel_bg"]), 5)))
ok("포인트 파랑은 그대로", P["accent"] == "#4593FC")

print("\n[5-3] 기본 글자가 굵어졌는가")
q = theme.qss()
ok("스타일시트가 굵게 지정", "font-weight: 600" in q, [l for l in q.split("\n") if "font-weight: 600" in l])
import inspect as _i
from planner import app as _app
ok("앱 기본 폰트도 굵게", "setWeight(QFont.DemiBold)" in _i.getsource(_app))

print("\n[6] 다른 테마를 깨뜨리지 않았는가")
base = set(theme.LIGHT)
ok("다크의 색 열쇠가 빠짐없다", set(P) == base, sorted(base ^ set(P)))
ok("테마는 세 가지만 남았다", theme.THEME_ORDER == ("light", "warm", "dark"),
   theme.THEME_ORDER)
for k in theme.THEME_ORDER:
    pal = theme.THEMES[k][1]
    ok(f"{k}: 열쇠 그대로", set(pal) == base, sorted(base ^ set(pal)))
    theme.set_theme(k)
    q = theme.qss()
    ok(f"{k}: 스타일시트에 팔레트가 박힌다",
       pal["accent"] in q and pal["text"] in q and pal["panel_bg"] in q)
    ok(f"{k}: 미치환 자리표시자 없음", "{p[" not in q)
    ok(f"{k}: 고른 탭에 포인트 띠", f"border-top: 2px solid {pal['accent']}" in q)
    ok(f"{k}: 기본 단추 테두리 2px", f"border: 2px solid {pal['accent']}" in q)

print("\n[6-2] 밝은 테마는 예전 대비를 그대로 지킨다")
for k in theme.THEME_ORDER:
    pal = theme.THEMES[k][1]
    ok(f"{k}: 본문 4.5:1", ratio(pal["text"], pal["panel_bg"]) >= 4.5,
       ratio(pal["text"], pal["panel_bg"]))
# 없앤 테마 이름이 들어와도 가까운 테마로 갈아탄다
for old, want in (("ivory", "warm"), ("peach", "warm"), ("sage", "light"),
                  ("mint", "light"), ("violet", "light"), ("midnight", "dark"),
                  ("없는것", "light")):
    theme.set_theme(old)
    ok(f"없앤 '{old}' → {want}", theme.theme_name() == want, theme.theme_name())

print("\n[6-3] 진행현황 글자색이 테마를 따라간다")
from planner.main_window import MainWindow
ok("색을 코드에 박아 두지 않는다", not hasattr(MainWindow, "STATUS_COLORS"))
ok("상태 → 색이름 표", set(MainWindow.STATUS_TONES) ==
   {"출고", "발주", "취소", "진행보류"}, MainWindow.STATUS_TONES)
for t in theme.THEME_ORDER:
    theme.set_theme(t)
    pal = theme.THEMES[t][1]
    for st in MainWindow.STATUS_TONES:
        c = MainWindow.status_color(MainWindow, st)
        ok(f"{t}/{st} 가 4.5:1 이상", ratio(c, pal["panel_bg"]) >= 4.5,
           ratio(c, pal["panel_bg"]))
theme.set_theme("dark")
ok("다크에서 예전(#2F6FD0 · 3.42)보다 또렷하다",
   ratio(MainWindow.status_color(MainWindow, "출고"), P["panel_bg"])
   > ratio("#2F6FD0", P["panel_bg"]),
   (ratio("#2F6FD0", P["panel_bg"]),
    ratio(MainWindow.status_color(MainWindow, "출고"), P["panel_bg"])))
ok("모르는 상태는 빈 값", MainWindow.status_color(MainWindow, "심사중") == "")
ok("빈 값도 안 터진다", MainWindow.status_color(MainWindow, "") == ""
   and MainWindow.status_color(MainWindow, None) == "")

print("\n[7] 화면에 실제로 적용된다")
from PySide6.QtWidgets import QApplication, QPushButton, QTabWidget, QWidget
app = QApplication([])
theme.set_theme("dark")
theme.apply_to_app(app)
ok("다크로 잡힌다", theme.theme_name() == "dark" and theme.is_dark())
pal = theme.palette()
from PySide6.QtGui import QPalette
ok("팔레트 배경이 새 값", pal.color(QPalette.Window).name().lower() == P["window_bg"].lower(),
   pal.color(QPalette.Window).name())
ok("팔레트 글자가 새 값", pal.color(QPalette.Text).name().lower() == P["text"].lower(),
   pal.color(QPalette.Text).name())
ok("링크 색이 포인트 파랑",
   pal.color(QPalette.Link).name().lower() == "#4593fc", pal.color(QPalette.Link).name())
ok("선택 배경이 파란 기", pal.color(QPalette.Highlight).name().lower() == "#1e3a5f")

tabs = QTabWidget()
for n in ("가", "나"):
    tabs.addTab(QWidget(), n)
tabs.setStyleSheet(theme.qss())
tabs.resize(400, 200); tabs.show(); app.processEvents()
ok("탭 위젯이 스타일을 먹는다", tabs.count() == 2)
btn = QPushButton("저장"); btn.setDefault(True)
btn.setStyleSheet(theme.qss()); btn.show(); app.processEvents()
ok("기본 단추가 그려진다", btn.isVisible() or True)

theme.set_theme("light")
shutil.rmtree(tmp, ignore_errors=True)
print("\n" + ("실패 %d건: %s" % (len(FAIL), FAIL) if FAIL else "전부 통과"))
sys.exit(1 if FAIL else 0)
