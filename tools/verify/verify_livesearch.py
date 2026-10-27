"""검색칸 — 한글 마지막 글자(조합 중)까지 **키를 더 누르지 않아도** 찾는지.

예전 증상: "전자약정" 을 다 쳐도 결과는 "전자약" 기준이었고, 스페이스·방향키를 한 번
더 눌러야 "정" 까지 들어가 검색이 끝났다. 한글 입력기가 마지막 글자를 '조합 중'
으로 들고 있는데 Qt 의 textChanged 는 그 글자를 빼고 알려 주기 때문이다.

진짜 입력기 대신 입력기가 보내는 이벤트(QInputMethodEvent)를 그대로 만들어 보낸다.
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
import os as _os
_os.chdir(_ROOT / "python")

import os
import tempfile
import time

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QInputMethodEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox  # noqa: E402

from planner import hangul, kb  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name
          + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


app = QApplication.instance() or QApplication([])


def pump(n=10):
    for _ in range(n):
        app.processEvents()
        time.sleep(0.005)


def ime(widget, preedit="", commit=""):
    """입력기가 보내는 이벤트 하나 — 조합 중 글자(preedit)와 확정 글자(commit)."""
    ev = QInputMethodEvent(preedit, [])
    if commit:
        ev.setCommitString(commit)
    QApplication.sendEvent(widget, ev)
    pump()


def type_korean(widget, syllables):
    """'전자약정' 을 한 글자씩: 앞 글자를 확정하며 다음 글자 조합을 시작한다.
    마지막 글자는 **조합 중인 채로** 둔다(키를 더 누르지 않은 상태)."""
    prev = ""
    for ch in syllables:
        ime(widget, preedit=ch, commit=prev)
        prev = ch


print("[1] 끝 글자 너그럽게 맞추기 (hangul)")
ok("시 → 신한", hangul.matches("신한 전자약정", "시"))
ok("전자약저 → 전자약정(정 을 치는 도중)", hangul.matches("신한 전자약정", "전자약저"))
ok("전자약ㅈ → 전자약정", hangul.matches("신한 전자약정", "전자약ㅈ"))
ok("ㅅ → 쏘나타(홑자음으로 겹자음)", hangul.matches("쏘나타", "ㅅ"))
ok("받침 있는 글자는 넓히지 않는다(신 ≠ 시작)", not hangul.matches("시작", "신"))
ok("초성만 검색은 그대로", hangul.matches("김상현", "ㄱㅅㅎ") and not hangul.matches("김상현", "ㄱㅅㅈ"))
ok("엉뚱한 건 여전히 안 걸린다", not hangul.matches("신한 전자약정", "정자"))

print("\n[2] 입력칸 — 조합 중 글자까지 알려 준다")
from planner.livesearch import LiveLineEdit  # noqa: E402

le = LiveLineEdit()
le.show()
got = []
le.liveText.connect(got.append)
type_korean(le, "전자약정")
ok("확정된 글은 '전자약'", le.text() == "전자약", le.text())
ok("보이는 글(live_text)은 '전자약정'", le.live_text() == "전자약정", le.live_text())
ok("마지막으로 알린 글도 '전자약정'", got and got[-1] == "전자약정", got[-3:])
ok("두 번 들어간 글('…정정')을 알리지 않는다", not any("정정" in g or "약약" in g for g in got), got)
n = len(got)
ime(le, preedit="", commit="정")      # 스페이스 등으로 조합이 끝남
ok("조합이 끝나도 같은 글이면 다시 찾지 않는다", len(got) == n and le.text() == "전자약정", got[n:])
le.setText("")
ok("코드가 비우면 조합 글자도 없다", le.live_text() == "")

print("\n[2-2] 입력기 이벤트 **안에서는** 알리지 않는다(윈도에서 멈추던 원인) — 끝나면 한 번")
got.clear()
QApplication.sendEvent(le, QInputMethodEvent("가", []))       # pump 없이
ok("이벤트 안에서는 아직 안 알렸다", got == [], got)
pump()
ok("이벤트가 끝나자마자 한 번 알린다", got == ["가"], got)
for ch in ("나", "다", "라"):                                  # 빠르게 여러 번
    QApplication.sendEvent(le, QInputMethodEvent(ch, []))
pump()
ok("몰려 와도 마지막 것 한 번만", got[-1] == "라" and len(got) == 2, got)
# 신호를 막고 비운 뒤(고객정보 탭이 그렇게 한다) 같은 글을 다시 쳐도 찾는다
le.setText("abc")
pump()
got.clear()
le.blockSignals(True)
le.clear()
le.blockSignals(False)
le.setText("abc")
pump()
ok("지운 뒤 같은 글을 다시 쳐도 다시 찾는다", got == ["abc"], got)

print("\n[3] 자료검색 — 마지막 글자를 치는 중에도 결과가 맞다")
from planner.kb_tab import KbView  # noqa: E402

kb.save_shared([
    {"category": "전자약정", "title": "신한 전자약정", "body": "가"},
    {"category": "약관", "title": "현대 전자약관", "body": "나"},
    {"category": "심사서류", "title": "개인 심사서류", "body": "다"},
])
view = KbView()
view.show()
pump()
def settle():
    """타자가 멎은 뒤(검색 대기 120ms) 결과가 나온다."""
    time.sleep(view.SEARCH_DELAY_MS / 1000 + 0.05)
    pump()


type_korean(view.ed_find, "전자약정")
settle()
titles = [view.lst.item(i).text() for i in range(view.lst.count())]
ok("키를 더 안 눌러도 '신한 전자약정' 만", titles == ["신한 전자약정"], titles)
view.ed_find.setText("")
pump()
type_korean(view.ed_find, "전자약")
settle()
titles = [view.lst.item(i).text() for i in range(view.lst.count())]
ok("'전자약' 까지는 둘 다", len(titles) == 2, titles)
view.ed_find.setText("")
ime(view.ed_find, preedit="시")      # "신" 을 치는 도중
settle()
titles = [view.lst.item(i).text() for i in range(view.lst.count())]
ok("'신' 을 치는 도중('시')에도 0건으로 깜빡이지 않는다", "신한 전자약정" in titles, titles)
view.ed_find.setText("")
pump()
type_korean(view.ed_find, "개인")
view.flush_search()                 # Enter 를 바로 누르면(빠른검색) 기다리지 않고 찾는다
titles = [view.lst.item(i).text() for i in range(view.lst.count())]
ok("기다리는 검색을 바로 끝낼 수 있다(빠른검색 Enter)", titles == ["개인 심사서류"], titles)

print("\n[4] 고객정보·고객 검색칸도 같은 입력칸")
import inspect  # noqa: E402

from planner import customer_files_tab, main_window  # noqa: E402
src_f = inspect.getsource(customer_files_tab.CustomerFilesTab)
ok("고객정보 검색칸은 LiveLineEdit", "self.ed_search = LiveLineEdit()" in src_f)
ok("고객정보 검색은 조합 중 글자까지 본다", "self.ed_search.text()" not in src_f)
src_m = inspect.getsource(main_window.MainWindow)
ok("고객 검색칸은 LiveLineEdit", "self.ed_cust_find = LiveLineEdit()" in src_m)
ok("고객 검색은 조합 중 글자까지 본다", "ed_cust_find.text()" not in src_m)

print("\n[5] 검색 드롭다운 — 조합 중에도 목록이 걸러진다")
from planner import searchcombo  # noqa: E402

cb = QComboBox()
for t in ["신한캐피탈", "현대캐피탈", "우리금융캐피탈"]:
    cb.addItem(t)
cs = searchcombo.install(cb)
cb.show()
cb.lineEdit().setFocus()
pump()
ok("콤보 입력칸도 LiveLineEdit", isinstance(cb.lineEdit(), LiveLineEdit))
cb.lineEdit().clear()                # 고른 값을 지우고 새로 친다
ime(cb.lineEdit(), preedit="우")
pop = cs._comp.popup()
rows = [cs._comp.completionModel().index(i, 0).data()
        for i in range(cs._comp.completionModel().rowCount())]
ok("'우' 를 치는 도중에 우리금융캐피탈만", rows == ["우리금융캐피탈"],
   (rows, cb.lineEdit().hasFocus(), cb.lineEdit().live_text()))

print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
