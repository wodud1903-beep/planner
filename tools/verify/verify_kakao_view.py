"""카톡 매크로 화면(v1.37) — A1Auto 창 · 환경설정 · 자주 쓰는 문구 + 일정관리기 '카톡 매크로' 메뉴.

지점장: "kmacro 의 카카오톡 매크로 기능을 … 일정관리기 및 자료검색 프로그램 앱에만 추가해줘. 단, 기능은 절대
수정하지 말고 기존 기능을 전부 다." / "3,4번(자주 쓰는 문구 · 발송 간격)은 구글 계정에 저장하고 자동 불러오도록."

진짜 Qt 시계 · 클립보드 · 1ms 타이머로(가짜는 윈도 창 · 키뿐) 화면에서 끝까지 한 번 돌려 보고, 글자 · 메뉴 ·
문구 창 · 환경설정 창 · 단축키 · 끌 때 할 일 · 일정관리기 연결(메뉴 · 트레이 · 인증번호 · 업데이트)을 본다.
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
import os as _os
_os.chdir(_ROOT / "python")

import inspect
import json
import os
import tempfile
import time
from pathlib import Path

os.environ["APPDATA"] = tempfile.mkdtemp()
tempfile.tempdir = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
TMP = Path(tempfile.mkdtemp())

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication([])
_f = QFont("Malgun Gothic", 10)
app.setFont(_f)

from planner import config, google_client, kakao_macro as km, kakao_win as kw, navicons, otp, otp_popup, sheets  # noqa: E402
from planner import sync, theme  # noqa: E402
from planner import kakao_macro_view as kv  # noqa: E402

theme.apply_to_app(app)
FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


def pump(sec=0.05):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


def wait(cond, sec=10.0):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    return cond()


MSGS = []
QMessageBox.information = staticmethod(lambda *a, **k: MSGS.append(a[2] if len(a) > 2 else k.get("text")))
ASK = {"answer": QMessageBox.Yes, "asked": []}


def _question(*a, **k):
    ASK["asked"].append(a[2] if len(a) > 2 else "")
    return ASK["answer"]


QMessageBox.question = staticmethod(_question)


# ---- 가짜 카카오톡(창 · 키) — 시계는 진짜 ----
KPID = 4242
MAIN = 10


class SimWin(kw.NullWin):
    def __init__(self, names, open_ms=40):
        self.w = {MAIN: ("EVA_Window_Dblclk", "카카오톡", KPID)}
        self.fg = MAIN
        self.names, self.open_ms = names, open_ms
        self.sel, self.room, self.typed = 0, None, ""
        self.sent, self.keys, self.ctrl = [], [], False
        self.pressed = set()

    def foreground(self):
        return self.fg

    def class_name(self, h):
        return self.w.get(h, ("",))[0]

    def window_text(self, h):
        return self.w.get(h, ("", ""))[1]

    def ancestor(self, h, flag):
        return h if h in self.w else 0

    def last_active_popup(self, h):
        return h if h in self.w else 0

    def is_visible(self, h):
        return h in self.w

    def window_pid(self, h):
        return self.w.get(h, ("", "", 0))[2]

    def map_vk(self, vk):
        return vk

    def async_key(self, vk):
        if vk in self.pressed:
            self.pressed.discard(vk)
            return 1
        return 0

    def key_event(self, vk, scan, flags):
        up = bool(flags & kw.KEYEVENTF_KEYUP)
        if vk == kw.VK_CONTROL:
            self.ctrl = not up
            return
        if up:
            return
        self.keys.append(vk)
        if vk == kw.VK_RETURN and self.fg == MAIN and self.sel < len(self.names):
            name = self.names[self.sel]
            QTimer.singleShot(self.open_ms, lambda: self._open(name))
        elif vk == kw.VK_V and self.ctrl and self.room:
            self.typed += QGuiApplication.clipboard().text()
        elif vk == kw.VK_RETURN and self.room and self.fg == self.room:
            self.sent.append((self.w[self.room][1], self.typed))
            self.typed = ""
        elif vk == kw.VK_ESCAPE and self.room:
            del self.w[self.room]
            self.room, self.fg, self.typed = None, MAIN, ""
        elif vk == kw.VK_DOWN and self.fg == MAIN:
            self.sel += 1

    def _open(self, name):
        h = 100 + self.sel
        self.w[h] = ("EVA_Window_Dblclk", name, KPID)
        self.room = h
        if self.fg == MAIN:
            self.fg = h


class FakeTray:
    def __init__(self):
        self.tip, self.shown = "일정관리기", []

    def toolTip(self):
        return self.tip

    def setToolTip(self, t):
        self.tip = t

    def isVisible(self):
        return True

    def icon(self):
        from PySide6.QtGui import QIcon
        return QIcon()

    def showMessage(self, title, text, *a):
        self.shown.append((title, text))


class FakeDrive:
    def __init__(self):
        self.files = {}

    def find(self, name):
        return ("F_" + name) if name in self.files else None

    def read(self, fid):
        return self.files[fid[2:]]

    def write(self, name, text):
        self.files[name] = text


DRIVE = FakeDrive()
LOGGED = {"on": False}


def make_view(names=("김민", "이영희"), armed=None):
    win = SimWin(list(names))
    prefs = km.Prefs(TMP / f"prefs_{time.time_ns()}.json")
    prefs.set_intervals(60, 60, 120)
    store = km.CustomerStore(TMP / f"cu_{time.time_ns()}.tsv")
    tray = FakeTray()
    v = kv.KakaoMacroView(tray=tray, prefs=prefs, store=store, env=kv.QtEnv(win=win),
                          io_getter=lambda: (DRIVE, "me@example.com") if LOGGED["on"] else (None, ""),
                          armed=armed)
    v.resize(900, 760)
    v.show()
    pump()
    return v, win, tray


# ===========================================================================
print("[1] 화면 — A1Auto 글자 그대로")
v, win, tray = make_view()
ok("전송방식 셋 · 처음엔 아무것도 안 고름(A1Auto 그대로)",
   v.grp_mode.title() == "전송방식" and [r.text() for r in v.rb_modes] == ["텍스트", "이미지", "이미지+텍스트"]
   and v.mode() == -1)
ok("단추 글자", (v.btn_image.text(), v.btn_start.text(), v.btn_stop.text()) ==
   ("이미지 불러오기", "매크로 시작 (INSERT)", "매크로 중지 (DELETE)"))
ok("카드 처음 글자 · 발송인원수 0", [lb.text() for lb in (v.lbl_success, v.lbl_stop, v.lbl_speed, v.lbl_skip)]
   == ["성공횟수", "중단횟수", "속도:", "건너뜀"] and v.ed_count.text() == "0")
ok("도구 메뉴 — 자주 쓰는 문구 · 발송 기록(v1.38) · 환경설정 · 수정로그", [a.text() for a in v.btn_tools.menu().actions()]
   == ["자주 쓰는 문구", "발송 기록", "환경설정", "수정로그"])
ok("진행 글 '0건 진행'", v.lbl_progress.text() == "0건 진행")
v.act_log.trigger()
ok("수정로그 → 실제 이력 창(v1.38 — A1Auto 는 '도움말 내용 생략')", v._dlg_log is not None and v._dlg_log.isVisible()
   and km.CHANGE_LOG[0][0] in v._dlg_log.text.toPlainText())
v._dlg_log.close()
ok("1초마다 카드(Timer2) — '성공: 0'", wait(lambda: v.lbl_success.text() == "성공: 0", 2.5) and v.lbl_speed.text() == "속도:")
v.rb_modes[0].click()
ok("텍스트 → 이미지 불러오기 꺼짐", not v.btn_image.isEnabled())
v.rb_modes[2].click()
ok("이미지+텍스트 → 켜짐", v.btn_image.isEnabled())
img = TMP / "명함.png"
q = QImage(300, 200, QImage.Format_RGB32)
q.fill(QColor("#2563EB"))
q.save(str(img))
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(img), ""))
v.btn_image.click()
ok("이미지 고르면 경로 · 미리보기", v.image_path() == str(img) and v.preview.has_image())

print("[2] 텍스트로 2명 — 진짜 시계 · 클립보드 · 1ms 타이머")
v.rb_modes[0].click()
v.memo.setPlainText("안녕하세요\n프로모션 안내")
v.ed_count.setText("2")
QGuiApplication.clipboard().setText("내 클립보드")
v.btn_start.click()
ok("도는 동안 시작 단추 · 전송방식 꺼짐", not v.btn_start.isEnabled() and not v.grp_mode.isEnabled() and v.busy())
ok("트레이 풍선말에 진행", wait(lambda: tray.tip.startswith("A1Auto · "), 3), tray.tip)
ok("끝까지", wait(lambda: not v.busy(), 20))
ok("두 사람에게 메시지", win.sent == [("김민", "안녕하세요\n프로모션 안내"), ("이영희", "안녕하세요\n프로모션 안내")], win.sent)
lines = v.log.toPlainText().splitlines()
ok("로그 — 성공 2줄 + '정상 종료'", len(lines) == 3 and lines[0].endswith("→ 김민 발송완료")
   and lines[2].endswith("→ 중단: 정상 종료"), lines)
blk = v.log.document().findBlockByNumber(2)
col = blk.begin().fragment().charFormat().foreground().color().name().upper()
ok("중단 줄은 빨강(테마의 강조 빨강)", col in (theme._STRONG[False]["red"].upper(), theme._STRONG[True]["red"].upper()), col)
ok("클립보드 되돌림", QGuiApplication.clipboard().text() == "내 클립보드")
ok("끝나면 풍선 알림 · 풍선말은 앱 이름으로", tray.shown[-1:] == [("A1Auto — 정상 종료", "성공 2 · 건너뜀 0 · 처리 2건")]
   and tray.tip == "일정관리기", (tray.shown, tray.tip))
ok("진행 '2 / 2' · 막대 끝까지", v.lbl_progress.text() == "2 / 2" and v.prog.value() == 1000)
ok("단추 다시 켜짐", v.btn_start.isEnabled() and v.grp_mode.isEnabled())
ok("1초 뒤 카드 '성공: 2' · 속도", wait(lambda: v.lbl_success.text() == "성공: 2", 2.5)
   and v.lbl_speed.text().endswith("건/분"), v.lbl_speed.text())

print("[3] Insert · Delete — 이 화면을 볼 때만")
arm = {"on": False}
v2, win2, tray2 = make_view(("가", "나", "다"), armed=lambda: arm["on"])
v2.rb_modes[0].click()
v2.memo.setPlainText("hi")
win2.pressed.add(kw.VK_INSERT)
pump(1.3)
ok("다른 화면일 때 Insert → 안 움직임(누른 표시도 비움)", not v2.busy() and kw.VK_INSERT not in win2.pressed)
arm["on"] = True
win2.pressed.add(kw.VK_INSERT)
ok("이 화면일 때 Insert → 시작", wait(lambda: v2.busy(), 2.5))
arm["on"] = False                    # 도는 중에 다른 메뉴로 옮겨 갔다
win2.pressed.add(kw.VK_DELETE)
ok("도는 중이면 다른 화면에 있어도 Delete → 사용자 중단(A1Auto 처럼)", wait(lambda: not v2.busy(), 5)
   and "중단: 사용자 중단" in v2.log.toPlainText())
win2.pressed.add(kw.VK_DELETE)
pump(1.3)
ok("쉬는 중 · 다른 화면이면 Delete 는 안 본다", v2.log.toPlainText().count("사용자 중단") == 1)

print("[4] 자주 쓰는 문구 — 저장 · 덮어쓰기 · 불러오기 · 삭제 · 구글 계정")
v.act_phrases.trigger()
d = v._dlg_phrases
ok("창 '자주 쓰는 문구' · 단추 다섯", d.isVisible() and d.windowTitle() == "자주 쓰는 문구"
   and [b.text() for b in (d.btn_load, d.btn_save, d.btn_delete, d.btn_refresh, d.btn_close)]
   == ["불러오기", "저장", "삭제", "새로고침", "닫기"])
MSGS.clear()
d.btn_load.click()
ok("안 고르고 불러오기 → 문구 그대로", MSGS == ["불러올 문구를 목록에서 선택해주세요."])
v.memo.setPlainText("   ")
d.btn_save.click()
ok("메시지가 비었으면", MSGS[-1] == "저장할 메시지 내용이 비어 있습니다.")
v.memo.setPlainText("첫 인사 문구")
asked_title = []
QInputDialog.getText = staticmethod(lambda *a, **k: (asked_title.append(a[1:3]) or ("  인사\n ", True)))
d.btn_save.click()
ok("제목 묻기('문구 저장' · '저장할 제목을 입력하세요:') → 저장", asked_title[-1] == ("문구 저장", "저장할 제목을 입력하세요:")
   and MSGS[-1] == "저장되었습니다: 인사" and v.prefs.get("인사") == "첫 인사 문구")
ok("목록에 보임", [d.list.item(i).text() for i in range(d.list.count())] == ["인사"])
QInputDialog.getText = staticmethod(lambda *a, **k: ("", True))
d.btn_save.click()
ok("제목이 비었으면", MSGS[-1] == "제목을 입력해주세요.")
QInputDialog.getText = staticmethod(lambda *a, **k: ("가" * 101, True))
d.btn_save.click()
ok("제목 100자 넘으면 저장 안 함", MSGS[-1].startswith("저장 실패") and len(v.prefs.titles()) == 1)
v.memo.setPlainText("고친 인사")
QInputDialog.getText = staticmethod(lambda *a, **k: ("인사", True))
ASK["answer"] = QMessageBox.No
d.btn_save.click()
ok("같은 제목 → '덮어쓸까요?' 아니오 → 그대로", ASK["asked"][-1] == "같은 제목의 문구가 이미 있습니다. 덮어쓸까요?"
   and v.prefs.get("인사") == "첫 인사 문구")
ASK["answer"] = QMessageBox.Yes
d.btn_save.click()
ok("예 → 덮어씀", v.prefs.get("인사") == "고친 인사")
v.memo.setPlainText("")
d.list.setCurrentRow(0)
d.list.itemDoubleClicked.emit(d.list.item(0))
ok("두 번 눌러 불러오기 → 메시지 칸 · '불러왔습니다: 인사' · 창 닫힘", v.memo.toPlainText() == "고친 인사"
   and MSGS[-1] == "불러왔습니다: 인사" and not d.isVisible())
v.act_phrases.trigger()
d.list.setCurrentRow(0)
ASK["answer"] = QMessageBox.Yes
d.btn_delete.click()
ok("삭제 — '\"인사\" 문구를 삭제할까요?'", ASK["asked"][-1] == '"인사" 문구를 삭제할까요?' and v.prefs.titles() == []
   and d.list.count() == 0)
DRIVE.files[km.REMOTE_NAME] = json.dumps({"v": 1, "settings": {"textsleep": 60, "nextsleep": 60, "imagesleep": 120,
                                                              "dupdays": 1, "at": "2026-11-01T00:00:00.000000Z"},
                                          "phrases": {"다른 PC 문구": {"text": "다른 PC 에서", "at": "2026-11-01T00:00:00.000000Z"}},
                                          "dead": {}}, ensure_ascii=False)
LOGGED["on"] = True
d.btn_refresh.click()
ok("[새로고침] → 구글 계정과 맞추고 목록이 저절로 다시", wait(lambda: d.list.count() == 1, 5)
   and d.list.item(0).text() == "다른 PC 문구", d.list.count())
ok("지운 '인사' 는 계정에도 지운 표시", "인사" in json.loads(DRIVE.files[km.REMOTE_NAME])["dead"])
ok("위에 저장 위치 '내 구글 계정'", "구글 계정에 저장" in v.lbl_where.text(), v.lbl_where.text())
d.btn_close.click()

print("[5] 환경설정 — 지연 셋 + 중복 일수 · [기본값] 800/800/1200 · [닫기(적용)]")
v.act_env.trigger()
e = v._dlg_env
ok("지금 값을 칸에", (e.ed1.text(), e.ed2.text(), e.ed3.text(), e.ed4.text()) == ("60", "60", "120", "1"))
ok("설명 글 그대로", all(t in [lb.text() for lb in e.findChildren(type(v.lbl_progress))] for t in (
    "텍스트 입력 전 지연시간(ms) :", "└ 채팅창이 열리고 텍스트가 입력되기 전 지연시간",
    "다음 채팅창을 열기 전 지연시간(ms) : ", "└ 이번 채팅창이 닫히고 다음 채팅창이 열리기 전 지연시간",
    "이미지 전송 후 지연시간(ms) :", "└ 이미지 전송 후 다음 작업을 수행하기 전 지연시간")))
e.btn_default.click()
ok("[기본값] → 800 / 800 / 1200", (e.ed1.text(), e.ed2.text(), e.ed3.text()) == ("800", "800", "1200"))
e.ed2.setText("abc")
e.ed4.setText("3")
e.btn_apply.click()
ok("[닫기(적용)] — 잘못 적은 칸은 700 · 저장 · 닫힘", (v.prefs.interval1, v.prefs.interval2, v.prefs.interval3, v.prefs.dupdays)
   == (800, 700, 1200, 3) and e.ed2.text() == "700" and not e.isVisible())
ok("계정에도 올림", wait(lambda: json.loads(DRIVE.files[km.REMOTE_NAME])["settings"]["nextsleep"] == 700, 5))
old = TMP / "A1Auto"
(old / "data").mkdir(parents=True)
(old / "data" / "customers.tsv").write_bytes("이름\t최초발견\t최종발송\t발송횟수\t수신거부\t메모\r\n옛고객\t\t\t2\t0\t\r\n"
                                              .encode("utf-8-sig"))
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: str(old))
e.btn_import.click()
ok("[A1Auto 기록 가져오기]", MSGS[-1] == "가져왔습니다 — 고객 1명 · 로그 0개" and "옛고객" in v.store.items, MSGS[-1])

print("[6] 로그 불러오기 · 끌 때(FormClose)")
lg = TMP / "log_2026-11-01_1000.txt"
lg.write_bytes("✅ 2026-11-01 10:00:00 → 홍길동 발송완료\r\n".encode("utf-8-sig"))
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(lg), ""))
v.btn_loadlog.click()
t = v.log.toPlainText().splitlines()
ok("'===== 불러오기: 파일 =====' 아래에 이어 붙임", t[-2:] == ["===== 불러오기: log_2026-11-01_1000.txt =====",
                                                       "✅ 2026-11-01 10:00:00 → 홍길동 발송완료"] and t[-3] == "", t[-4:])
v3, win3, tray3 = make_view(("가", "나", "다", "라"))
v3.rb_modes[0].click()
v3.memo.setPlainText("끄기 검사")
QGuiApplication.clipboard().setText("끄기 전 클립보드")
v3.btn_start.click()
ok("도는 중", wait(lambda: len(win3.sent) >= 1, 5))
path = v3.shutdown()
ok("앱을 끄면 멈춤('프로그램 종료') · 로그 파일 · 클립보드 되돌림", not v3.engine.running
   and "중단: 프로그램 종료" in Path(path).read_text(encoding="utf-8-sig")
   and QGuiApplication.clipboard().text() == "끄기 전 클립보드", path)
n = len(win3.keys)
pump(0.5)
ok("끈 뒤로는 키를 더 보내지 않는다", len(win3.keys) == n)

print("[7] 테마를 바꿔도 칸 색이 따라간다")
for th in ("dark", "light"):
    theme.set_theme(th)
    theme.apply_to_app(app)
    v.apply_theme()
    pump()
    want = QColor(theme.c("input_bg")).name()
    ok(f"{th}: 메시지 칸 바탕", v.memo.palette().color(v.memo.backgroundRole()).name() == want
       or want in v.styleSheet(), want)

# ===========================================================================
print("[8] 일정관리기 — '카톡 매크로' 메뉴 · 트레이 · 인증번호 · 업데이트 · 끄기")
from planner import startup_dialog as _sd  # noqa: E402
_sd.StartupDialog.show_for = staticmethod(lambda *a, **k: None)
config.set_account("tester@example.com")
google_client.GoogleAuth.is_connected = lambda self: False
sync.sync_now = lambda *a, **k: (False, "")
sheets.read_rows = lambda *a, **k: (1, [], [])
from planner.main_window import MainWindow, _AppDataIO  # noqa: E402
w = MainWindow()
w.show()
pump(0.3)
names = [w.tabs.tabText(i) for i in range(w.tabs.count())]
ok("메뉴 맨 끝에 '카톡 매크로'(9번째)", names[-1] == "카톡 매크로" and len(names) == 9, names)
ok("메뉴 아이콘 종이비행기", navicons.for_tab("카톡 매크로") == "send" and "send" in navicons.NAMES)
ok("앱 트레이를 함께 쓴다", w.tab_macro.tray is w.tray)
w.tabs.setCurrentWidget(w.tab_macro)
pump()
others = max(w.tabs.widget(i).minimumSizeHint().height() for i in range(w.tabs.count())
             if w.tabs.widget(i) is not w.tab_macro)
ok("이 화면이 앱 창의 최소 높이를 끌어올리지 않는다(낮은 노트북 화면 — 안은 스크롤)",
   w.tab_macro.minimumSizeHint().height() <= others, (w.tab_macro.minimumSizeHint().height(), others))
_im = w.tab_macro.btn_start.grab().toImage()
_sm = w.tab_macro.btn_stop.grab().toImage()
ok("일정관리기 쪽 카드(이름이 'pagecard' 로 바뀌어도) 시작 초록 · 중지 갈색 그대로",
   w.tab_macro.objectName() == "pagecard"
   and _im.pixelColor(12, _im.height() // 2).name() == theme.fill(kv.START_TONE).lower()
   and _sm.pixelColor(12, _sm.height() // 2).name() == theme.fill(kv.STOP_TONE).lower(),
   (_im.pixelColor(12, _im.height() // 2).name(), _sm.pixelColor(12, _sm.height() // 2).name()))
w.tabs.setCurrentWidget(w.tab_main)
pump()
ok("다른 화면이면 Insert · Delete 안 본다", not w.tab_macro.armed())
w.tabs.setCurrentWidget(w.tab_macro)
pump()
ok("카톡 매크로 화면이면 본다", w.tab_macro.armed())
ok("창을 트레이로 내려도(이 메뉴가 지금 화면이면) 본다", (w.hide(), pump(), w.tab_macro.armed())[2])
w.show()
pump()
ok("계정 확인 전에는 계정과 맞추지 않는다", w._macro_io() == (None, ""))
w._account_verified = True
google_client.GoogleAuth.is_connected = lambda self: True
io, acct = w._macro_io()
ok("확인된 뒤 — 앱 전용 공간 · 지금 계정", isinstance(io, _AppDataIO) and acct == "tester@example.com")
google_client.drive_read_bytes = lambda auth, fid: "{\"한글\": \"값\"}".encode("utf-8")
ok("계정 파일은 UTF-8 로 읽는다", io.read("x") == "{\"한글\": \"값\"}")
google_client.GoogleAuth.is_connected = lambda self: False
w._account_verified = False
src = inspect.getsource(MainWindow)
ok("동기화가 끝나면 설정 · 문구도 맞춘다", "self.tab_macro.sync()" in inspect.getsource(MainWindow._on_synced))
ok("끌 때 A1Auto 처럼(클립보드 · 기록 · 로그)", "self.tab_macro.shutdown()" in inspect.getsource(MainWindow._shutdown))
ok("테마를 바꾸면 따라간다", "self.tab_macro.apply_theme()" in inspect.getsource(MainWindow.apply_theme))
ok("매크로가 도는 중에는 자동 업데이트를 미룬다", "self.tab_macro.busy()" in inspect.getsource(MainWindow._try_pending_update))
otp.claim = lambda it, now=None: True
shown = []
otp_popup.show = lambda it, copied=False: shown.append(copied)
QGuiApplication.clipboard().setText("붙여넣을 메시지")
w.tab_macro.busy = lambda: True
w._on_otp([{"code": "123456", "sender": "x", "body": "인증번호 123456"}], "")
ok("매크로가 도는 중 인증번호 → 띄우기만(클립보드 그대로)", QGuiApplication.clipboard().text() == "붙여넣을 메시지"
   and shown == [False], shown)
w.tab_macro.busy = lambda: False
w._on_otp([{"code": "654321", "sender": "x", "body": "인증번호 654321"}], "")
ok("쉬는 중이면 예전처럼 클립보드에", QGuiApplication.clipboard().text() == "654321" and shown[-1] is True)
w._really_close = True
w._shutdown()
ok("끄기 — 단축키 타이머 멈춤", not w.tab_macro.hotkey_timer.isActive())

print()
print(f"{len(FAIL)}건 실패" if FAIL else "전부 통과", flush=True)
os._exit(1 if FAIL else 0)
