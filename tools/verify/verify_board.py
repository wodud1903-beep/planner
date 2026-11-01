"""고객 진행 보드(v1.25) — 플로우의 '업무 상태' 처럼 진행현황별 칸에 고객 카드.

지점장 요청: "플로우 업무상태". 칸 = 시트에 있는 진행현황 값, 카드를 끌어 옮기면
시트 L열(진행현황)만 바뀐다 — 쓰기 직전에 그 줄에 같은 고객이 있는지 확인하는 길로.
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
from datetime import date, timedelta

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from planner import board, config, google_client, sheets, sync, theme  # noqa: E402
from planner import startup_dialog as _sd  # noqa: E402

_sd.StartupDialog.show_for = staticmethod(lambda *a, **k: None)
FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name
          + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


T = date.today()


def fmt(d):
    return f"{d.year}. {d.month}. {d.day}"


def row(n, name, status, cd=None, dd=None, fin="KB캐피탈", model="쏘나타"):
    cr = sheets.CustomerRow(row=n, total="1,000,000", center="", accident="")
    cr.values.update({"customer": name, "status": status, "finance": fin, "model": model,
                      "contract_date": fmt(cd) if cd else "", "deliver_date": fmt(dd) if dd else ""})
    cr.uid = f"uid{n:013d}"
    return cr


ROWS = [
    row(2, "김상현", "발주", T - timedelta(days=40)),
    row(3, "박영희", "발주", T - timedelta(days=3)),
    row(4, "이수진", "발주", T - timedelta(days=20), T + timedelta(days=5)),
    row(5, "정해나", "진행보류", T - timedelta(days=60)),
    row(6, "한지민", "취소", T - timedelta(days=10)),
    row(7, "최민수", "출고", T - timedelta(days=50), T - timedelta(days=4)),
    row(8, "오래된", "출고", T - timedelta(days=400), T - timedelta(days=300)),
    row(9, "남기한", "", T - timedelta(days=1)),
]

print("[1] 칸 나누기")
cols = board.columns(ROWS, T)
names = [c["status"] for c in cols]
ok("칸 = 시트에 있는 진행현황 값, 흐름 순서(없음 → 발주 → 출고 → 보류)",
   names == [board.NO_STATUS, "발주", "출고", "진행보류"], names)
ok("취소는 기본으로 숨긴다", "취소" not in names)
ok("취소도 보기", "취소" in [c["status"] for c in board.columns(ROWS, T, True)])
bal = next(c for c in cols if c["status"] == "발주")
ok("오래 묵은 건이 위로", [x["name"] for x in bal["cards"]] == ["김상현", "이수진", "박영희"],
   [x["name"] for x in bal["cards"]])
k = bal["cards"][0]
ok("40일째는 빨강", k["chip"] == "계약 40일째" and k["tone"] == "red", k)
ok("출고일이 잡힌 건은 출고 D-n(초록)", bal["cards"][1]["chip"].endswith("D-5")
   and bal["cards"][1]["tone"] == "green", bal["cards"][1])
done = next(c for c in cols if c["status"] == "출고")
ok("출고 칸은 최근 30일만, 나머지는 '외 n건'", [x["name"] for x in done["cards"]] == ["최민수"]
   and done["more"] == 1)
moved = board.columns(ROWS + [row(10, "방금옮김", "출고", T - timedelta(days=5))], T)
ok("출고일 없이 출고 칸으로 옮긴 건은 사라지지 않고 맨 위", next(
   c for c in moved if c["status"] == "출고")["cards"][0]["name"] == "방금옮김")
hold = next(c for c in cols if c["status"] == "진행보류")
ok("보류는 오래돼도 빨갛지 않다(기다리는 건)", hold["cards"][0]["tone"] == "")

print("[2] PC 고객관리 탭 — [목록] / [보드]")
app = QApplication.instance() or QApplication([])
theme.apply_to_app(app)
config.set_account("tester@example.com")
google_client.GoogleAuth.is_connected = lambda self: True
google_client.GoogleAuth.has_scope = lambda self, s: True
sync.sync_now = lambda *a, **k: (False, "")
sheets.read_rows = lambda *a, **k: (1, [], [])
from planner.main_window import MainWindow  # noqa: E402

w = MainWindow()
w.resize(1600, 900)
w.settings.sheet_on = True
w.settings.sheet_id = "SHEET"
w.sheet_rows = list(ROWS)
w._sheet_loaded = True
w.tabs.setCurrentWidget(w.tab_cust)
w.show()
w.refresh_customers()
w.btn_view_board.click()
for _ in range(10):
    app.processEvents()
ok("[보드] 를 누르면 보드", w.cust_stack.currentWidget() is w.board)
ok("칸이 그려진다", [l.status for l in w.board.lists] == names, [l.status for l in w.board.lists])
ok("다음에 켜도 보드(설정에 남긴다)", w.settings.cust_view == "board")

calls = []
_ur = sheets.update_row


def fake_update(auth, sid, sname, rown, values, name="", uid=""):
    calls.append((rown, values, name, uid))
    time.sleep(0.1)
    return rown


sheets.update_row = fake_update
w._move_customer_status(3, "출고")
ok("옮기면 화면부터 바뀐다", next(c for c in w.sheet_rows if c.row == 3).get("status") == "출고")
for _ in range(30):
    app.processEvents()
    time.sleep(0.02)
ok("시트에는 진행현황 한 칸만, 그 고객인지 확인하는 길로",
   calls == [(3, {"status": "출고"}, "박영희", "uid0000000000003")], calls)

# 못 쓰면 되돌린다
QMessageBox.warning = staticmethod(lambda *a, **k: None)


def boom(*a, **k):
    raise sheets.RowMoved(sheets.MOVED_MSG)


sheets.update_row = boom
w._move_customer_status(2, "진행보류")
for _ in range(30):
    app.processEvents()
    time.sleep(0.02)
ok("못 쓰면 원래 칸으로 되돌린다", next(c for c in w.sheet_rows if c.row == 2).get("status") == "발주")
sheets.update_row = _ur

# 끌어 놓기 → moved 신호
got = []
w.board.moved.connect(lambda r, s: got.append((r, s)))
src = w.board.lists[1]
src.setCurrentRow(0)
w.board._on_drop(int(src.currentItem().data(board_view_role := 256)), "진행보류")
ok("카드를 놓으면 (줄, 칸 이름)", got and got[-1][1] == "진행보류", got)
w.board._on_drop(9, board.NO_STATUS)
ok("'진행현황 없음' 칸에 놓으면 비운다", got[-1] == (9, ""), got[-1])

if os.environ.get("SHOT_DIR"):
    w.grab().save(os.path.join(os.environ["SHOT_DIR"], "board_pc.png"))
w.btn_view_list.click()
ok("[목록] 으로 돌아온다", w.cust_stack.currentWidget() is w.tbl_cust)
w.hide()

print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
