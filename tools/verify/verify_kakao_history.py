"""카톡 매크로 발송 기록 · 발송 로그 — 내 구글 계정에 올려 다른 PC 에서도 자동으로(v1.38) · 수정로그.

지점장: "1. 매크로 메뉴에서 수정로그는 현재 비어 있는데, 앞으로 너가 직접 업데이트해서 올려줘.
2. 자주 쓰는 문구 및 고객 발송 로그는 원래 PC 에 저장했었는데, 로그인된 구글 드라이브에 올려서 자동으로 불러올 수
있도록 리스트를 만들어줘."
PC 두 대(A · B)가 가짜 계정 하나를 함께 쓰며 합치기 규칙을 보고, 화면(도구 → 발송 기록 · 수정로그)을 눌러 본다.
업무자료검색 verify_macro_history 는 이 파일의 사본이다(불러오는 곳만 다르다).
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
import os as _os
_os.chdir(_ROOT / "python")

import hashlib
import json
import os
import re
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

os.environ["APPDATA"] = tempfile.mkdtemp()
tempfile.tempdir = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
TMP = Path(tempfile.mkdtemp())

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication([])

from planner import kakao_history as kh, kakao_macro as km, kakao_win as kw  # noqa: E402
from planner import kakao_macro_view as kv  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


def wait(cond, sec=10.0):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    return cond()


MSGS = []
QMessageBox.information = staticmethod(lambda *a, **k: MSGS.append(a[2] if len(a) > 2 else ""))
QMessageBox.warning = staticmethod(lambda *a, **k: MSGS.append(a[2] if len(a) > 2 else ""))


class Drive:
    """가짜 앱 전용 공간 — 판(md5)도 준다."""

    def __init__(self):
        self.files, self.reads, self.writes = {}, 0, 0

    def meta(self, name):
        if name not in self.files:
            return None, ""
        return "F_" + name, hashlib.md5(self.files[name].encode("utf-8")).hexdigest()

    def find(self, name):
        return ("F_" + name) if name in self.files else None

    def read(self, fid):
        self.reads += 1
        return self.files[fid[2:]]

    def write(self, name, text):
        self.writes += 1
        self.files[name] = text


def pc(tag):
    """PC 한 대 — 제 A1Auto 폴더(customers.tsv · logs · device.json)."""
    d = TMP / tag
    (d / "data").mkdir(parents=True)
    (d / "logs").mkdir()
    os.environ["COMPUTERNAME"] = f"{tag}-PC"
    book = kh.HistoryBook(tsv=d / "data" / "customers.tsv", logs=d / "logs", device_file=d / "device.json")
    return d, book


def sync(book, io, acct="me@example.com"):
    return book.apply(book.prepare(io, acct))


def store(d):
    st = km.CustomerStore(d / "data" / "customers.tsv")
    st.load()
    return st


NOW = datetime.now().replace(microsecond=0)
T1 = km.stamp(NOW - timedelta(hours=2))
T0 = km.stamp(NOW - timedelta(days=40))

# ===========================================================================
print("[1] 로그 줄 읽기 — A1Auto 모양 그대로(예전 ANSI 로그의 '?' 도)")
ok("✅ 발송", kh.parse_line(f"✅ {T1} → 홍길동 발송완료") == (T1, "ok", "홍길동", ""))
ok("⏭ 건너뜀(중복이면 이름도)", kh.parse_line(f"⏭ {T1} → 건너뜀: 최근 1일 내 발송함: 김 민") == (T1, "skip", "김 민",
                                                                                     "최근 1일 내 발송함: 김 민"))
ok("⏭ 건너뜀(이름 없음)", kh.parse_line(f"⏭ {T1} → 건너뜀: 채팅방 이름 확인 실패") == (T1, "skip", "", "채팅방 이름 확인 실패"))
ok("❌ 중단", kh.parse_line(f"❌ {T1} → 중단: 정상 종료") == (T1, "stop", "", "정상 종료"))
ok("예전 A1Auto 가 ANSI 로 저장해 이모지가 '?' 가 된 줄", kh.parse_line(f"? {T1} → 이영희 발송완료") == (T1, "ok", "이영희", ""))
ok("로그 줄이 아니면 None", all(kh.parse_line(x) is None for x in ("", "===== 불러오기: a.txt =====", "✅ 예전 로그",
                                                               f"✅ {T1} → 뭔가 다른 글")))
ok("같은 글이면 같은 id(어디서 읽든 한 번)", kh.make_event(T1, "ok", "홍길동", "", "a")[0]
   == kh.make_event(T1, "ok", "홍길동", "", "b")[0] != kh.make_event(T1, "ok", "홍길동2", "", "a")[0])

print("[2] 이 PC 의 표(device.json) — 처음 한 번 만들고 그대로")
dfile = TMP / "dev" / "device.json"
os.environ["COMPUTERNAME"] = "사무실PC"
a1 = kh.device(dfile)
os.environ["COMPUTERNAME"] = "다른이름"
ok("같은 표 · PC 이름", kh.device(dfile) == a1 and a1[1] == "사무실PC" and len(a1[0]) == 12, a1)

# ===========================================================================
print("[3] PC A — 예전 기록(customers.tsv · logs) · 새로 보낸 줄을 계정에 올린다")
A, ba = pc("A")
B, bb = pc("B")
ok("두 PC 의 표가 다르다", ba.me != bb.me and ba.pc == "A-PC" and bb.pc == "B-PC")
(A / "data" / "customers.tsv").write_bytes(("이름\t최초발견\t최종발송\t발송횟수\t수신거부\t메모\r\n"
                                            f"김민\t{T0}\t{T1}\t3\t0\t\r\n"
                                            f"박철수\t{T0}\t\t0\t0\t\r\n").encode("utf-8-sig"))
old_log = (f"✅ {T0} → 김민 발송완료\r\n⏭ {T0} → 건너뜀: 채팅방 이름 확인 실패\r\n❌ {T0} → 중단: 정상 종료\r\n")
(A / "logs" / "log_old.txt").write_bytes(old_log.replace("✅", "?").replace("⏭", "?").replace("❌", "?").encode("cp949"))
live = f"✅ {T1} → 김민 발송완료"
ok("매크로가 찍은 줄은 바로 파일에 덧붙인다", ba.note(live) and ba.new_path.is_file() and not ba.note("아무 글"))
(A / "logs" / "log_today.txt").write_bytes(("﻿" + live + "\r\n").encode("utf-8"))   # 닫을 때 쓴 같은 줄
G = Drive()
r = sync(ba, G)
doc = json.loads(G.files[kh.REMOTE_NAME])
ok("계정에 올렸다 · 이 PC 이름", r == "applied" and G.writes == 1 and doc["devices"] == {ba.me: "A-PC"}, doc["devices"])
ok("고객: 처음 본 날 · 마지막 발송 · 이 PC 가 보낸 횟수", doc["customers"]["김민"] == [T0, T1, {ba.me: 3}, 0, ""]
   and doc["customers"]["박철수"] == [T0, "", {}, 0, ""], doc["customers"])
kinds = sorted((e[2], e[3]) for e in doc["events"])
ok("로그: 예전 ANSI 로그 3줄 + 오늘 1줄(새 줄 · 로그 파일에 겹친 같은 줄은 한 번)",
   kinds == [("ok", "김민"), ("ok", "김민"), ("skip", ""), ("stop", "")] and len(doc["events"]) == 4, kinds)
ok("새것이 앞", doc["events"][0][1] == T1 and doc["events"][-1][1] == T0)
ok("맞춘 줄은 비운다 · 사본(customers.sync.json)", not ba.new_path.exists() and ba.sync_path.is_file()
   and ba.load_mirror()["account"] == "me@example.com")
reads = G.reads
ok("다시 맞춰도 그대로 — 계정 판이 같으면 받지도 않는다", sync(ba, G) == "same" and G.reads == reads and G.writes == 1)

print("[4] PC B — 로그인하면 A 의 기록을 저절로 불러온다(중복 발송 막기도 PC 사이에서)")
ok("B 는 처음 — 받아서 customers.tsv 에", sync(bb, G) == "applied")
sb = store(B)
ok("A 에서 보낸 김민 · 횟수 3 · 마지막 발송", "김민" in sb.items and sb.items["김민"].send_count == 3
   and km.stamp(sb.items["김민"].last_sent) == T1)
ok("B 에서도 '최근 1일 내 발송함' 으로 건너뛴다", sb.sent_within_days("김민", 1))
doc = json.loads(G.files[kh.REMOTE_NAME])
ok("B 는 보낸 게 없어 제 PC 이름만 더했다(고객 · 로그 그대로)", G.writes == 2 and doc["devices"] == {ba.me: "A-PC", bb.me: "B-PC"}
   and doc["customers"]["김민"][2] == {ba.me: 3} and len(doc["events"]) == 4)
sb.register_sent("김민")
sb.register_sent("새고객")
bb.note(f"✅ {km.stamp(NOW)} → 김민 발송완료")
sync(bb, G)
doc = json.loads(G.files[kh.REMOTE_NAME])
ok("B 가 보낸 것은 B 몫으로 — 합 4(A 몫을 두 번 세지 않는다)", doc["customers"]["김민"][2] == {ba.me: 3, bb.me: 1}
   and doc["customers"]["새고객"][2] == {bb.me: 1}, doc["customers"]["김민"])
sync(ba, G)
sa = store(A)
ok("A 도 저절로 — 김민 4번 · 새고객", sa.items["김민"].send_count == 4 and sa.items["새고객"].send_count == 1)
for _ in range(3):
    sync(ba, G)
    sync(bb, G)
doc = json.loads(G.files[kh.REMOTE_NAME])
ok("몇 번을 맞춰도 늘지 않는다", doc["customers"]["김민"][2] == {ba.me: 3, bb.me: 1} and store(A).items["김민"].send_count == 4
   and store(B).items["김민"].send_count == 4)
ok("두 PC 이름", doc["devices"] == {ba.me: "A-PC", bb.me: "B-PC"})
ok("발송 로그도 합쳐졌다(A 4줄 + B 1줄)", len(doc["events"]) == 5 and sum(1 for e in doc["events"] if e[5] == bb.me) == 1)

print("[5] 수신거부 · 메모(엑셀에서 고친 것) — 고친 PC 것이 이긴다 · 안 고친 PC 는 계정 것을 받는다")
sa = store(A)
sa.items["박철수"].memo = "VIP — 연락은 오후"
sa.items["박철수"].opt_out = True
sa.save()
sync(ba, G)
sync(bb, G)
sb = store(B)
ok("B 에 메모 · 수신거부", sb.items["박철수"].memo == "VIP — 연락은 오후" and sb.items["박철수"].opt_out)
sb.items["박철수"].opt_out = False
sb.save()
sync(bb, G)
sync(ba, G)
ok("B 에서 수신거부를 풀면 A 도 풀린다(한쪽이 켜져 있으면 계속 켜지는 일 없이)", not store(A).items["박철수"].opt_out
   and store(A).items["박철수"].memo == "VIP — 연락은 오후")

print("[6] 그사이 이 PC 가 바뀌면 쓰지 않고 다시 · 매크로가 도는 중이면 끝난 뒤")
ba.note(f"⏭ {km.stamp(NOW)} → 건너뜀: 채팅방 이름 확인 실패")
plan = ba.prepare(G, "me@example.com")
sa = store(A)
sa.register_sent("김민")                 # 맞추는 사이에 보냈다
ok("customers.tsv 가 바뀌었으면 'stale' — 방금 보낸 것을 덮지 않는다", ba.apply(plan) == "stale"
   and store(A).items["김민"].send_count == 5)
sync(ba, G)
ok("다음에 맞추면 올라간다", json.loads(G.files[kh.REMOTE_NAME])["customers"]["김민"][2] == {ba.me: 4, bb.me: 1})

print("[7] 로그인 전 · 다른 계정 · 깨진 계정 파일")
C, bc = pc("C")
bc.note(f"✅ {T1} → 오프라인 발송완료")
plan = bc.prepare(None, "")
ok("로그인 전 — 이 PC 것만 정리(계정은 건드리지 않음)", not plan.online and bc.apply(plan) == "applied"
   and any(e[3] == "오프라인" for e in bc.snapshot()["events"]))
ok("…다음에 로그인하면 올라간다", sync(bc, G) == "applied"
   and any(e[3] == "오프라인" for e in json.loads(G.files[kh.REMOTE_NAME])["events"]))
G2 = Drive()
sync(bc, G2, "other@example.com")
ok("다른 계정으로 맞추면 이 PC 기록을 그 계정에 새로(앞 계정의 판 · 기준은 버린다)",
   bc.load_mirror()["account"] == "other@example.com" and "오프라인" in json.dumps(G2.files[kh.REMOTE_NAME],
                                                                               ensure_ascii=False))
G3 = Drive()
G3.files[kh.REMOTE_NAME] = "{깨짐"
try:
    bc.prepare(G3, "x@example.com")
    ok("깨진 계정 파일 → 오류", False)
except kh.HistoryError as e:
    ok("깨진 계정 파일은 덮지 않는다(오류로 알림)", G3.files[kh.REMOTE_NAME] == "{깨짐" and "깨져" in str(e))
F, bf = pc("F")
GF = Drive()
sync(bf, GF)
ok("매크로를 안 쓴 계정엔 파일을 만들지 않는다(PC 이름만으로는 안 올림)", GF.files == {} and GF.writes == 0)
keep = kh.EVENTS_MAX
kh.EVENTS_MAX = 3
D, bd = pc("D")
for i in range(6):
    bd.note(f"✅ {km.stamp(NOW - timedelta(minutes=i))} → 손님{i} 발송완료")
sync(bd, Drive())
ev = bd.load_mirror()["doc"]["events"]
ok("로그는 최근 EVENTS_MAX 줄까지(오래된 것부터 버림)", [e[3] for e in ev] == ["손님0", "손님1", "손님2"], [e[3] for e in ev])
kh.EVENTS_MAX = keep

print("[8] customers.tsv 는 다 쓴 뒤 바꿔 끼운다(반쯤 쓴 파일이 없게)")
st = km.CustomerStore(TMP / "atomic" / "customers.tsv")
st.register_sent("가")
ok("임시 파일이 남지 않는다 · 모양 그대로", not list((TMP / "atomic").glob("*.tmp"))
   and (TMP / "atomic" / "customers.tsv").read_bytes().startswith(b"\xef\xbb\xbf" + km.TSV_HEADER.encode()))

# ===========================================================================
print("[9] 화면 — 도구 → 발송 기록(발송 로그 · 고객 목록) · 수정로그")
E, be = pc("E")
(E / "data" / "customers.tsv").write_bytes(("이름\t최초발견\t최종발송\t발송횟수\t수신거부\t메모\r\n"
                                            f"=위험한방\t{T0}\t{T1}\t2\t0\t\r\n"
                                            f"홍길동\t{T0}\t{T0}\t1\t0\t단골\r\n"
                                            f"안보낸방\t{T0}\t\t0\t0\t\r\n").encode("utf-8-sig"))
be.note(f"✅ {T1} → =위험한방 발송완료")
be.note(f"✅ {T0} → 홍길동 발송완료")
be.note(f"⏭ {T1} → 건너뜀: 최근 1일 내 발송함: 홍길동")
be.note(f"❌ {T1} → 중단: 정상 종료")
LOGGED = {"on": True}
GV = Drive()
win = kw.NullWin()
v = kv.KakaoMacroView(prefs=km.Prefs(TMP / "pv.json"), store=km.CustomerStore(E / "data" / "customers.tsv"),
                      env=kv.QtEnv(win=win), history=be,
                      io_getter=lambda: (GV, "me@example.com") if LOGGED["on"] else (None, ""))
v.show()
ok("도구 메뉴 — 자주 쓰는 문구 · 발송 기록 · 환경설정 · 수정로그",
   [a.text() for a in v.btn_tools.menu().actions()] == ["자주 쓰는 문구", "발송 기록", "환경설정", "수정로그"])
ok("화면 위 — 발송 기록도 계정에", "발송 기록: 내 구글 계정" in v.lbl_where.text(), v.lbl_where.text())
v.add_log(f"✅ {km.stamp(NOW)} → 방금보낸분 발송완료", "ok")
ok("매크로가 찍은 줄 → 발송 기록에도", any(e[3] == "방금보낸분" for e in be.snapshot()["events"]))
v.act_hist.trigger()
d = v._dlg_hist
ok("발송 기록 창", d is not None and d.isVisible() and d.windowTitle() == "발송 기록"
   and [d.tabs.tabText(i) for i in range(d.tabs.count())] == ["발송 로그", "고객 목록"])
ok("열자마자 계정과 맞춘다 · 끝나면 다시 그린다", wait(lambda: kh.REMOTE_NAME in GV.files and v.hist_worker.state[0] == "ok")
   and "내 구글 계정과 맞췄습니다" in d.lbl_state.text(), d.lbl_state.text())
ok("발송 로그(최근 30일) — 시각 · 결과 · 이름 · 내용 · PC · 새것이 위",
   d.m_log.heads == ("시각", "결과", "이름", "내용", "PC") and d.m_log.rowCount() == 4
   and d.m_log.rows[0][2] == "방금보낸분" and d.m_log.rows[0][4] == "이 PC", [r[:3] for r in d.m_log.rows])
ok("건너뜀 · 중단은 색으로", d.m_log.data(d.m_log.index([r[5] for r in d.m_log.rows].index("stop"), 1), Qt.ForegroundRole)
   is not None)
d.cb_period.setCurrentIndex(len(d.PERIODS) - 1)
ok("기간 '전체' — 40일 전 줄도", d.m_log.rowCount() == 5)
d.cb_kind.setCurrentIndex(2)
ok("결과 '건너뜀'만", d.m_log.rowCount() == 1 and d.m_log.rows[0][1] == "건너뜀")
d.cb_kind.setCurrentIndex(0)
d.ed_find.setText("홍길동")
ok("찾기(이름 · 내용)", wait(lambda: d.m_log.rowCount() == 2, 2))
d.ed_find.setText("")
wait(lambda: d.m_log.rowCount() == 5, 2)
d.tabs.setCurrentIndex(1)
ok("고객 목록 — 보낸 적 있는 사람만 · 마지막 발송 늦은 것이 위",
   [r[0] for r in d.m_cu.rows][:2] == ["=위험한방", "홍길동"] and "안보낸방" not in [r[0] for r in d.m_cu.rows]
   and d.m_cu.rows[0][2] == 2 and d.m_cu.rows[1][5] == "단골", [r[:3] for r in d.m_cu.rows])
d.chk_sent.setChecked(False)
ok("'보낸 적 있는 사람만' 을 끄면 다", "안보낸방" in [r[0] for r in d.m_cu.rows])
ok("횟수에 마우스 → PC 마다", d.m_cu.data(d.m_cu.index(0, 2), Qt.ToolTipRole) == "이 PC 2번")
d.t_cu.sortByColumn(2, Qt.AscendingOrder)
ok("머리를 누르면 그 칸으로 정렬(횟수는 숫자로)", [r[2] for r in d.m_cu.rows] == sorted(r[2] for r in d.m_cu.rows))
row = [r[0] for r in d.m_cu.rows].index("홍길동")
d._show_person(d.m_cu.index(row, 0))
ok("고객을 두 번 누르면 그 사람의 발송 로그", d.tabs.currentIndex() == 0 and d.ed_find.text() == "홍길동"
   and d.m_log.rowCount() == 2)
out = TMP / "내보내기.csv"
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(out), ""))
d.tabs.setCurrentIndex(1)
d.export()
txt = out.read_bytes()
ok("엑셀로 저장 — UTF-8 BOM · 머리 · 보이는 줄 그대로 · '=' 로 시작하는 이름은 글자로",
   txt.startswith(b"\xef\xbb\xbf") and "이름,마지막 발송,발송 횟수" in txt.decode("utf-8-sig")
   and "'=위험한방" in txt.decode("utf-8-sig") and MSGS and "저장했습니다" in MSGS[-1], txt[:120])
noext = TMP / "확장자없음"
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(noext), ""))
d.export()
ok("확장자를 지웠으면 .csv 를 붙인다", (TMP / "확장자없음.csv").is_file() and not noext.exists())
LOGGED["on"] = False
d.reload()
ok("로그인 전 — '이 PC 기록만' 안내", "이 PC 기록만" in d.lbl_state.text(), d.lbl_state.text())
LOGGED["on"] = True
d.close()

print("[10] 매크로가 도는 동안은 이 PC 파일을 쓰지 않는다 — 끝나면 저절로 다시")
writes = GV.writes
be.note(f"✅ {km.stamp(NOW)} → 도는중손님 발송완료")
v.engine.running = True
v.sync_history()
ok("도는 중 — 미뤄 둔다", v._history_wanted and not v.hist_worker.busy() and GV.writes == writes)
v.hist_worker._finished(be.prepare(None, ""), "")
ok("맞추는 사이 매크로가 돌기 시작했으면 '맞추는 중' 으로 남겨 두지 않는다", v.hist_worker.state[0] == "idle"
   and v._history_wanted)
v.engine.running = False
ok("끝나면 1초 타이머가 보고 맞춘다", wait(lambda: GV.writes > writes and not v._history_wanted, 5))
st_e = store(E)
st_e.items["다른PC손님"] = km.Customer("다른PC손님")
st_e.items["다른PC손님"].send_count, st_e.items["다른PC손님"].last_sent = 1, NOW
st_e.save()
v.sync_history()
ok("맞춘 뒤엔 매크로 색인도 다시 읽는다(다른 PC 에서 보낸 사람 건너뛰기)",
   wait(lambda: "다른PC손님" in v.store.items and not v.hist_worker.busy(), 5))

print("[11] 수정로그 — '도움말 내용 생략' 대신 실제 이력(새것이 위)")
v.act_log.trigger()
dl = v._dlg_log
html = dl.text.toPlainText()
ok("수정로그 창 — 판마다 날짜 · 고친 것", dl.isVisible() and dl.windowTitle() == "수정로그" and "도움말 내용 생략" not in html
   and km.CHANGE_LOG[0][1] in html and km.CHANGE_LOG[0][2][0] in html, html[:200])
days = [c[0] for c in km.CHANGE_LOG]
ok("새것이 위(날짜가 내려간다)", days == sorted(days, reverse=True), days)
ok("절마다 한 줄 이상 다섯 줄 안쪽 · 한 줄 90자 안쪽",
   all(1 <= len(c[2]) <= 5 and all(0 < len(t) <= 90 for t in c[2]) for c in km.CHANGE_LOG))
ok("절마다 어느 판인지(일정관리기 · 업무자료검색 판 번호)", all(re.search(r"\d+\.\d+", c[1]) for c in km.CHANGE_LOG)
   and "일정관리기 v" in km.CHANGE_LOG[0][1] and "업무자료검색 v" in km.CHANGE_LOG[0][1], km.CHANGE_LOG[0][1])
ok("글로도(change_log_text)", km.change_log_text().startswith(f"■ {days[0]}  {km.CHANGE_LOG[0][1]}\n  · "))
dl.close()
v.shutdown()

print()
print(f"{len(FAIL)}건 실패" if FAIL else "전부 통과", flush=True)
os._exit(1 if FAIL else 0)
