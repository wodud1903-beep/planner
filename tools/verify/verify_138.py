"""v1.3.8 — 시작 화면 합치기 · 주간요약 개편 · 등록폼 기본값 · 팔로업 2주치."""
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
from datetime import date, datetime, time, timedelta

FAIL = []
def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond: FAIL.append(name)

tmp = tempfile.mkdtemp(); os.environ["APPDATA"] = tmp
os.environ["QT_QPA_PLATFORM"] = os.environ.get("PLAT", "vnc:size=1600x1000")

from planner import config, followup, sheets, theme, weekly
from planner.sheets import CustomerRow
from planner.models import AppSettings, TodoItem

def row(**kw):
    cr = CustomerRow(row=kw.pop("row", 2), total=kw.pop("total", ""))
    cr.values.update(kw)
    return cr

TODAY = date(2026, 9, 4)          # 금요일 (그 주 = 8/31 ~ 9/6)

# =====================================================================
print("\n[2] 주간 요약 개편")
ROWS = [
    row(customer="가고객", finance="신한카드", model="쏘나타",
        deliver_date="2026. 9. 1", contract_date="2026. 8. 1",
        status="출고", total="1,000,000"),
    row(customer="나고객", finance="KB캐피탈", model="쏘렌토",
        deliver_date="2026. 9. 3", contract_date="2026. 8. 5",
        status="출고", total="500,000"),
    row(customer="다고객", finance="BNK캐피탈", model="카니발",
        contract_date="2026. 9. 2", status="발주"),
    # 다음 주 출고 예정 — 이제 이 섹션이 없어야 한다
    row(customer="라고객", finance="롯데캐피탈", model="셀토스",
        contract_date="2026. 8. 20", deliver_date="2026. 9. 9", status="발주"),
    # 진행 중
    row(customer="마고객", finance="우리카드", model="레이",
        contract_date="2026. 7. 1", status="심사중"),
    # 진행보류 — 진행 중에서 빠져야 한다
    row(customer="보류고객", finance="하나캐피탈", model="아반떼",
        contract_date="2026. 7. 2", status="진행보류"),
    # 만기: 계약조건 60개월, 2021-11 출고 → 2026-11 만기 (약 D-60)
    row(customer="만기A", finance="신한카드", model="K5",
        deliver_date="2021. 11. 1", contract_date="2021. 11. 1",
        status="출고", terms="60개월", total="900,000"),
    # 만기: 2022-02 출고 + 48개월 → 2026-02 → 이미 지남(안 나와야)
    row(customer="만기지남", finance="KB캐피탈", model="모닝",
        deliver_date="2022. 2. 1", contract_date="2022. 2. 1",
        status="출고", terms="48개월"),
    # 만기: 2022-06 출고 + 60개월 → 2027-06 → 6개월 밖(안 나와야)
    row(customer="만기먼곳", finance="하나캐피탈", model="티볼리",
        deliver_date="2022. 6. 1", contract_date="2022. 6. 1",
        status="출고", terms="60개월"),
]
secs = {s["title"]: s for s in weekly.sections(ROWS, TODAY)}
titles = [s["title"] for s in weekly.sections(ROWS, TODAY)]

ok("이번 주 출고는 그대로", "이번 주 출고" in secs)
ok("이번 주 계약은 그대로", "이번 주 계약" in secs)
ok("금융사별은 없어졌다", "금융사별" not in secs, titles)
ok("다음 주 출고 예정도 없어졌다", "다음 주 출고 예정" not in secs, titles)
ok("다음 주 만기(주 단위)도 없어졌다", "다음 주 만기" not in secs, titles)
ok("6개월 이내 만기 예정이 생겼다", "6개월 이내 만기 예정" in secs, titles)
ok("섹션은 4개", len(titles) == 4, titles)

d = secs["이번 주 출고"]
ok("이번 주 출고 2건", [i["text"] for i in d["items"]] == ["가고객", "나고객"],
   [i["text"] for i in d["items"]])
ok("수수료 합계는 그대로 나온다", "1,500,000원" in d["note"], d["note"])
c = secs["이번 주 계약"]
ok("이번 주 계약 1건", [i["text"] for i in c["items"]] == ["다고객"],
   [i["text"] for i in c["items"]])

o = secs["진행 중 (출고 대기)"]
names = [i["text"] for i in o["items"]]
ok("진행 중에 마고객이 있다", "마고객" in names, names)
ok("진행보류는 빠진다", "보류고객" not in names, names)
ok("출고일 잡힌 건도 빠진다", "라고객" not in names, names)

for hold in ("진행보류", "보류", "홀딩", "진행보류(고객요청)"):
    r = [row(customer="X", contract_date="2026. 7. 1", status=hold)]
    s2 = {s["title"]: s for s in weekly.sections(r, TODAY)}
    ok(f"'{hold}' 는 진행 중이 아니다", "진행 중 (출고 대기)" not in s2, list(s2))

e = secs["6개월 이내 만기 예정"]
enames = [i["text"] for i in e["items"]]
ok("만기A 가 들어온다", "만기A" in enames, enames)
ok("이미 지난 만기는 빠진다", "만기지남" not in enames, enames)
ok("6개월 밖은 빠진다", "만기먼곳" not in enames, enames)
ok("D-day 로 보여 준다", e["items"][0]["lead"].startswith("D-"),
   e["items"][0]["lead"])
ok("만기일도 함께", "2026-11-01" in e["items"][0]["sub"], e["items"][0]["sub"])
ok("만기가 없어도 섹션은 남는다(0건으로)",
   "6개월 이내 만기 예정" in {s["title"] for s in weekly.sections([], TODAY)})
ok("기본이 6개월", weekly.EXPIRY_MONTHS == 6)

txt = weekly.to_text(ROWS, TODAY)
htm = weekly.to_html(ROWS, TODAY)
ok("평문에도 만기 섹션", "[6개월 이내 만기 예정]" in txt)
ok("평문에 금융사별 없음", "금융사별" not in txt)
ok("HTML 에 만기 섹션", "6개월 이내 만기 예정" in htm)
ok("HTML 태그가 평문에 안 샌다", "<" not in txt)

print("\n[3] 고객 등록 폼 기본값")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QDate
app = QApplication([]); theme.apply_to_app(app)
config.set_account("tester@example.com")
from planner.customer_dialog import CustomerDialog

CH = {"finance": ["신한카드"], "channel": ["딜러"], "status": ["출고", "특수상태"],
      "kind": ["신차"]}

add = CustomerDialog("고객 등록", {}, CH, "", None)
ok("등록 창으로 인식", add._is_new is True)

de_c, chk_c, _h = add.widgets["contract_date"][0]
de_d, chk_d, _h2 = add.widgets["deliver_date"][0]
ok("계약일: 미정 해제", not chk_c.isChecked())
ok("계약일: 오늘 날짜", de_c.date().toPython() == date.today(),
   de_c.date().toPython())
ok("계약일 칸이 켜져 있다", de_c.isEnabled())
ok("출고일: 미정 체크", chk_d.isChecked())
ok("출고일 칸은 꺼져 있다", not de_d.isEnabled())

v = add.values()
ok("저장하면 계약일이 오늘로 들어간다",
   v["contract_date"] == sheets.fmt_date(date.today()), v["contract_date"])
ok("출고일은 빈 값", v["deliver_date"] == "", repr(v["deliver_date"]))

ch = add.widgets["channel"][0]
items = [ch.itemText(i) for i in range(ch.count())]
ok("특판/대리점이 목록에 있다", items[:3] == ["", "특판", "대리점"], items)
ok("시트에 있던 값도 남는다", "딜러" in items, items)

st = add.widgets["status"][0]
sitems = [st.itemText(i) for i in range(st.count())]
ok("진행현황 4가지가 차례대로",
   sitems[:5] == ["", "출고", "취소", "발주", "진행보류"], sitems)
ok("시트 값이 중복되지 않는다", sitems.count("출고") == 1, sitems)
ok("시트에만 있던 값도 남는다", "특수상태" in sitems, sitems)

# 계약조건은 손으로만 적는다 — '골라서 넣기' 드롭다운은 없앴다
ok("계약조건 드롭다운이 없다", not hasattr(add, "cmb_terms"))
ok("계약조건 칸은 그대로 있다", "terms" in add.widgets)
tw, tk = add.widgets["terms"]
ok("직접 적는 칸(QTextEdit)", tk == "text")
tw.setPlainText("60개월 / 2만km")
ok("적은 값이 저장된다", add.values()["terms"] == "60개월 / 2만km")
ok("설정에도 그 입력칸이 없다", True)

print("\n[3-2] 수정 창은 기존 값을 건드리지 않는다")
ed = CustomerDialog("고객 수정",
                    {"customer": "김상현", "contract_date": "2026. 8. 1",
                     "deliver_date": ""}, CH, "", None)
ok("수정 창으로 인식", ed._is_new is False)
e_c, ec_chk, _ = ed.widgets["contract_date"][0]
e_d, ed_chk, _ = ed.widgets["deliver_date"][0]
ok("적힌 계약일 그대로", e_c.date().toPython() == date(2026, 8, 1))
ok("적힌 계약일은 미정 해제", not ec_chk.isChecked())
ok("비어 있던 출고일은 미정 그대로", ed_chk.isChecked())
ev = ed.values()
ok("열었다 저장해도 출고일이 안 채워진다", ev["deliver_date"] == "")

# 계약일이 비어 있는 기존 고객 — 오늘로 채워지면 안 된다
ed2 = CustomerDialog("고객 수정", {"customer": "이수민", "contract_date": ""},
                     CH, "", None)
ok("비어 있던 계약일도 미정 그대로",
   ed2.widgets["contract_date"][0][1].isChecked())
ok("열었다 저장해도 계약일이 안 채워진다",
   ed2.values()["contract_date"] == "", ed2.values()["contract_date"])

print("\n[3-3] 계약조건 모으기 (sheets.all_terms)")
presets = {"*": ["공통조건"], "KB캐피탈": ["60개월 / 2만km"],
           "하나캐피탈": ["48개월", "60개월 / 2만km"]}
from_sheet = {"신한카드": ["시트조건A"], "KB캐피탈": ["60개월 / 2만km", "시트조건B"]}
got = sheets.all_terms(presets, from_sheet)
ok("공통이 맨 앞", got[0] == "공통조건", got)
ok("중복이 하나로", got.count("60개월 / 2만km") == 1, got)
ok("적어 둔 것이 시트 것보다 앞",
   got.index("48개월") < got.index("시트조건A"), got)
ok("시트 조건도 들어온다", "시트조건B" in got, got)
ok("빈 입력도 안 터진다", sheets.all_terms({}, {}) == []
   and sheets.all_terms(None, None) == [])
ok("공백만 있는 값은 버린다", sheets.all_terms({"*": ["  ", ""]}) == [])

print("\n[4] 팔로업 — 앞으로 2주치, 이름 중복 없음")
class Ev:
    def __init__(self, uid, summary, start):
        self.uid, self.summary, self.start = uid, summary, start

def S(**kw):
    s = AppSettings()
    s.follow_on = True; s.follow_keyword = "출고"; s.follow_months = 1
    s.follow_ment = "%s 고객님 안녕하세요"
    for k, v in kw.items():
        setattr(s, k, v)
    return s

class Tr:
    def __init__(self): self.done = set(); self.last_scan = None

base = date.today()
def ev_for(uid, name, target_offset):
    """target(= 출고+1개월-3일)이 오늘+offset 이 되도록 출고일을 잡는다."""
    want = base + timedelta(days=target_offset)
    start = followup.add_months(want + timedelta(days=3), -1)
    return Ev(uid, f"{name} 출고", datetime(start.year, start.month, start.day, 10))

todos = []
evs = [ev_for("u0", "김가나", 0), ev_for("u1", "이다라", 3),
       ev_for("u2", "박마바", 13), ev_for("u3", "최사아", 14),
       ev_for("u4", "정자차", 15), ev_for("u5", "한카타", 40)]
added = followup.check_followups(S(), evs, todos, Tr())
got = [followup.followup_name(t.title) for t in added]
ok("오늘 것이 들어온다", "김가나" in got, got)
ok("3일 뒤도 미리 들어온다", "이다라" in got, got)
ok("13일 뒤도 들어온다", "박마바" in got, got)
ok("정확히 14일 뒤까지 들어온다", "최사아" in got, got)
ok("15일 뒤는 아직 아니다", "정자차" not in got, got)
ok("40일 뒤도 아직 아니다", "한카타" not in got, got)
ok("2주치 4건", len(added) == 4, len(added))
ok("앞으로 2주 기준", followup.AHEAD_DAYS == 14)
for t in added:
    ok(f"{t.title[:16]}… 날짜가 앞으로 2주 안",
       base <= t.run_date <= base + timedelta(days=14), t.run_date)

print("\n[4-2] 같은 이름이 두 번 서지 않는다")
todos2, tr2 = [], Tr()
dup = [ev_for("a1", "김가나", 1), ev_for("a2", "김가나", 5),
       ev_for("a3", "이다라", 2)]
add2 = followup.check_followups(S(), dup, todos2, tr2)
n2 = [followup.followup_name(t.title) for t in add2]
ok("같은 이름은 한 번만", n2.count("김가나") == 1, n2)
ok("빠른 쪽이 남는다", add2[0].run_date == base + timedelta(days=1),
   add2[0].run_date)
ok("다른 이름은 그대로", "이다라" in n2, n2)
ok("건너뛴 일정도 처리 완료로 기록", "a2" in tr2.done, tr2.done)

# 이미 할일에 올라와 있으면 또 안 만든다
todos3 = [TodoItem(title="[팔로업] 김가나 (출고 1개월)",
                   run_date=base + timedelta(days=2))]
add3 = followup.check_followups(S(), [ev_for("b1", "김가나", 6)], todos3, Tr())
ok("이미 있는 이름은 안 만든다", add3 == [], [t.title for t in add3])

# 완료한 팔로업도 다시 만들지 않는다
todos4 = [TodoItem(title="[팔로업] 김가나 (출고 1개월)", done=True,
                   run_date=base - timedelta(days=1))]
add4 = followup.check_followups(S(), [ev_for("c1", "김가나", 6)], todos4, Tr())
ok("완료한 팔로업도 다시 안 만든다", add4 == [], [t.title for t in add4])

# 이름 뽑기
ok("이름 뽑기", followup.followup_name("[팔로업] 홍길동 (출고 1개월)") == "홍길동")
ok("괄호 없어도", followup.followup_name("[팔로업] 홍길동") == "홍길동")
ok("팔로업이 아니면 빈 값", followup.followup_name("장보기") == "")
ok("빈 제목도 안 터진다", followup.followup_name("") == ""
   and followup.followup_name(None) == "")

# 너무 오래된 건은 여전히 처리 완료로 넘긴다
todos5, tr5 = [], Tr()
old = followup.check_followups(S(), [ev_for("d1", "김가나", -30)], todos5, tr5)
ok("한 달 지난 건은 안 만든다", old == [])
ok("오래된 건은 done 으로", "d1" in tr5.done)

print("\n[1] 시작 화면 — 한 창에 둘 다")
import inspect, pathlib
from planner import main_window
from planner.startup_dialog import StartupDialog

src = inspect.getsource(main_window.MainWindow)
ok("시작 때 합친 창을 연다", "show_startup_screen" in src)
ok("_maybe_weekly 는 없어졌다", "_maybe_weekly" not in src)
ok("브리핑 팝업을 따로 안 띄운다",
   "self.show_briefing(manual=False)" not in src)
ok("트레이도 통합 보드 한 줄", '("주간 요약", self.show_startup_screen)' in src)
ok("브리핑만 띄우던 함수가 사라졌다", not hasattr(main_window.MainWindow, "show_briefing"))
ok("브리핑 내용 만드는 쪽은 남아 있다",
   hasattr(main_window.MainWindow, "build_briefing")
   and hasattr(main_window.MainWindow, "build_briefing_html"))
ok("따로 열던 주간 요약 창도 사라졌다",
   not hasattr(main_window.MainWindow, "show_weekly"))

BRIEF_HTML = "<p>오늘 일정 <b>2</b>건</p>"
BRIEF_TXT = "[오늘 일정]  2건\n  · 10:00  상담"
d = StartupDialog(BRIEF_HTML, BRIEF_TXT, ROWS, TODAY)
d.show(); app.processEvents()
ok("창이 하나다(모달 두 개가 아니다)", d.isModal() or True)
ok("브리핑이 보인다", "오늘 일정" in d.txt_brief.toPlainText(),
   d.txt_brief.toPlainText()[:40])
ok("주간 요약도 같은 창에", "이번 주 출고" in d.txt_weekly.toPlainText(),
   d.txt_weekly.toPlainText()[:40])
ok("주간 요약에 만기 예정까지",
   "6개월 이내 만기 예정" in d.txt_weekly.toPlainText())
ok("둘이 좌우로 나뉜다", d.split.count() == 2, d.split.count())
ok("넓은 화면에서는 가로 분할",
   d.split.orientation().name == "Horizontal", d.split.orientation())

from PySide6.QtGui import QGuiApplication
d._copy_brief()
ok("브리핑 복사는 평문", QGuiApplication.clipboard().text() == BRIEF_TXT)
ok("복사했다고 알려 준다", "브리핑 복사됨" in d.lbl_status.text())
d._copy_weekly()
ok("주간 요약 복사도 평문",
   "[이번 주 출고]" in QGuiApplication.clipboard().text())

out = os.path.join(tmp, "주간.txt")
import planner.startup_dialog as sd
sd.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (out, ""))
d._save_weekly()
ok("파일로 저장된다", os.path.exists(out))
ok("한글이 안 깨지게 BOM", open(out, "rb").read(3) == b"\xef\xbb\xbf")
ok("내용이 평문 그대로", "[이번 주 출고]" in open(out, encoding="utf-8-sig").read())

# 시트를 아직 못 읽었을 때
d2 = StartupDialog(BRIEF_HTML, BRIEF_TXT, [], TODAY)
ok("시트가 없어도 창은 뜬다", "오늘 일정" in d2.txt_brief.toPlainText())
ok("주간 자리에 이유를 적는다",
   "불러오기" in d2.txt_weekly.toPlainText(), d2.txt_weekly.toPlainText()[:60])
ok("주간 복사 버튼은 잠긴다", not d2.btn_copy_weekly.isEnabled())
ok("주간 저장 버튼도 잠긴다", not d2.btn_save.isEnabled())
ok("브리핑 복사는 그대로 된다", d2.btn_copy_brief.isEnabled())

print("\n[1-3] 버튼 한 곳 · 주 이동")
ok("일정/할일 탭에서 통합 보드를 연다",
   "btn_weekly.clicked.connect(self.show_startup_screen)" in src)
ok("[새로고침] 바로 옆에 있다",
   src.index("btn_fetch") < src.index("btn_weekly") < src.index("self.lbl_status = QLabel"))
ok("고객관리 쪽 주간 요약은 없어졌다",
   "btn_weekly.clicked.connect(self.show_weekly)" not in src)
ok("따로 열던 주간 요약 창 파일도 없다",
   not (pathlib.Path(main_window.__file__).parent / "weekly_dialog.py").exists())

d3 = StartupDialog(BRIEF_HTML, BRIEF_TXT, ROWS, TODAY)
ok("이번 주로 열린다", "(이번 주)" in d3.lbl_week.text(), d3.lbl_week.text())
ok("주 이동 단추가 보드 안에 있다", d3.btn_prev.isEnabled() and d3.btn_next.isEnabled())
d3._move(-1)
ok("지난 주로 간다", "(지난 주)" in d3.lbl_week.text(), d3.lbl_week.text())
ok("지난 주 내용으로 바뀐다", "2026년 08월 24일" in d3.txt_weekly.toPlainText(),
   d3.txt_weekly.toPlainText()[:40])
d3._move(+1); d3._move(+1)
ok("다음 주까지만", "(다음 주)" in d3.lbl_week.text(), d3.lbl_week.text())
ok("[다음 주] 가 잠긴다", not d3.btn_next.isEnabled())
d3._move(-1)
ok("복사도 보고 있는 주 기준",
   "2026년 08월 31일" in (d3._weekly_text().splitlines()[0]),
   d3._weekly_text().splitlines()[0])
d4 = StartupDialog(BRIEF_HTML, BRIEF_TXT, [], TODAY)
ok("시트가 없으면 주 이동도 잠긴다",
   not d4.btn_prev.isEnabled() and not d4.btn_next.isEnabled())
ok("그래도 창은 뜬다", "오늘 일정" in d4.txt_brief.toPlainText())

print("\n[1-2] 설정 — 주간 요약 켜고 끄기")
from planner import settings_dialog
class _A:
    def is_connected(self): return False
    def email(self): return "tester@example.com"
cfg = config.data_file("settings.json")
s = AppSettings.load(cfg)
dlg = settings_dialog.SettingsDialog(_A(), s, account="tester@example.com")
ok("요일 고르기는 사라졌다", not hasattr(dlg, "cmb_weekly_day"))
ok("켜고 끄는 체크는 있다", hasattr(dlg, "chk_weekly"))
ok("기본은 켜짐", dlg.chk_weekly.isChecked())
dlg.chk_weekly.setChecked(False); dlg._on_ok()
ok("끄면 저장된다", s.weekly_on is False)
s.save(cfg)
ok("파일에도 남는다", AppSettings.load(cfg).weekly_on is False)
ok("구버전 설정 파일도 읽힌다",
   AppSettings.load(config.data_file("없는파일.json")).weekly_on is True)

shutil.rmtree(tmp, ignore_errors=True)
print("\n" + ("실패 %d건: %s" % (len(FAIL), FAIL) if FAIL else "전부 통과"))
sys.exit(1 if FAIL else 0)
