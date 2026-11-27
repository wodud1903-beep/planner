"""카톡 매크로(A1Auto 옮김) — 엔진이 델파이 원본과 같게 움직이는지(업무자료검색 사본 — 일정관리기 verify_kakao_macro 와 같다).

지점장: "kmacro 의 카카오톡 매크로 기능을 delphi 코드를 현재 일정관리기 파이썬 코드에 맞게 변환해서 추가 …
단, 기능은 절대 수정하지 말고 기존 기능을 전부 다 추가해줘." / "1,2 삭제하고 3,4번은 구글 계정에 저장하고
자동 불러오도록 해줘."

가짜 윈도(창 · 앞에 있는 창 · 누른 키)와 가짜 시계로 카카오톡을 흉내 내고 A1Auto(Unit1.pas · Unit2 · Unit3 ·
CustomerDB.pas)의 순서 · 기다리는 시간 · 멈추는 까닭 · 로그 글 · customers.tsv 모양을 하나씩 대조한다.
"""
import pathlib as _pl
import sys as _sys

_HERE = _pl.Path(__file__).resolve().parent
_sys.path.insert(0, str(_HERE.parent))

import heapq
import json
import os
import re
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

os.environ["APPDATA"] = tempfile.mkdtemp()
TMP = Path(tempfile.mkdtemp())

from kbsearch import kakao_macro as km, kakao_win as kw  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


# ---------------------------------------------------------------------------
# 가짜 시계 · 클립보드 · 1ms 타이머
# ---------------------------------------------------------------------------
T0 = 5_000_000          # GetTickCount 는 0 보다 크다


class FakeEnv:
    def __init__(self):
        self.t = T0
        self.base = datetime(2026, 11, 27, 9, 30, 0)
        self.q = []
        self.seq = 0
        self.pending = []
        self.clip = "원래 클립보드"
        self.clip_fail = 0
        self.clip_sets = []
        self.on_clip = None
        self.win = None

    def tick(self):
        return self.t

    def now(self):
        return self.base + timedelta(milliseconds=self.t - T0)

    def at(self, ms, fn):
        self.seq += 1
        heapq.heappush(self.q, (self.t + ms, self.seq, fn))

    def every(self, ms, fn):
        def run():
            fn()
            self.at(ms, run)
        self.at(ms, run)

    def delay(self, ms):
        """델파이 Delay — 기다리는 동안 일(타이머 · 창 변화)이 돈다."""
        end = self.t + ms
        while self.q and self.q[0][0] <= end:
            due, _s, fn = heapq.heappop(self.q)
            if due > self.t:
                self.t = due
            fn()
        if end > self.t:
            self.t = end

    def clip_get(self):
        return self.clip

    def clip_set(self, s):
        if self.clip_fail > 0:
            self.clip_fail -= 1
            raise RuntimeError("다른 프로그램이 클립보드를 쥐고 있음")
        self.clip = s
        self.clip_sets.append(s)
        if self.on_clip:
            self.on_clip(s)

    def later(self, fn):
        self.pending.append(fn)


# ---------------------------------------------------------------------------
# 가짜 윈도 API + 카카오톡 흉내
# ---------------------------------------------------------------------------
KAKAO_PID, NOTE_PID = 5000, 7000
MAIN, NOTEPAD, NOTE_DLG, KAKAO_DLG, KAKAO_MSGBOX = 100, 300, 301, 900, 950
NAMES = {kw.VK_RETURN: "ENTER", kw.VK_ESCAPE: "ESC", kw.VK_DOWN: "DOWN", kw.VK_T: "T", kw.VK_V: "V"}
KAKAO_CLS = "EVA_Window_Dblclk"


class FakeWin(kw.NullWin):
    def __init__(self, env):
        self.env = env
        self.w = {}
        self.fg = 0
        self.raw = []           # (시각, vk, scan, flags)
        self.keys = []          # (시각, 'ENTER' · '^V' …, 그때 앞에 있던 창)
        self.ctrl = False
        self.pressed = set()    # GetAsyncKeyState 가 눌렸다고 할 키
        self.on_key = None
        self.add(NOTEPAD, "Notepad", "제목 없음 - 메모장", pid=NOTE_PID)
        self.add(NOTE_DLG, kw.DIALOG_CLASS, "다른 이름으로 저장", pid=NOTE_PID, owner=NOTEPAD)

    def add(self, h, cls, title="", pid=KAKAO_PID, owner=None, popup=None, visible=True):
        self.w[h] = dict(cls=cls, title=title, pid=pid, owner=owner, popup=popup, visible=visible)

    def foreground(self):
        return self.fg

    def class_name(self, h):
        return self.w[h]["cls"] if h in self.w else ""

    def window_text(self, h):
        return self.w[h]["title"] if h in self.w else ""

    def ancestor(self, h, flag):
        if h not in self.w:
            return 0
        if flag == kw.GA_ROOT:
            return h
        cur, seen = h, set()
        while self.w.get(cur, {}).get("owner") and cur not in seen:
            seen.add(cur)
            cur = self.w[cur]["owner"]
        return cur

    def last_active_popup(self, h):
        if h not in self.w:
            return 0
        return self.w[h]["popup"] or h

    def is_visible(self, h):
        return bool(self.w.get(h, {}).get("visible"))

    def window_pid(self, h):
        return self.w[h]["pid"] if h in self.w else 0

    def map_vk(self, vk):
        return (vk * 7) % 251 or 1

    def key_event(self, vk, scan, flags):
        self.raw.append((self.env.t, vk, scan, flags))
        up = bool(flags & kw.KEYEVENTF_KEYUP)
        if vk == kw.VK_CONTROL:
            self.ctrl = not up
            return
        if up:
            return
        name = ("^" if self.ctrl else "") + NAMES.get(vk, hex(vk))
        self.keys.append((self.env.t, name, self.fg))
        if self.on_key:
            self.on_key(name)

    def async_key(self, vk):
        if vk in self.pressed:
            self.pressed.discard(vk)
            return 1
        return 0


class KakaoSim:
    """친구 목록(본 창) → Enter = 채팅방 창 · ESC = 닫기 · ↓ = 다음 친구 · Ctrl+T = 파일 열기 창."""

    def __init__(self, win, env, friends):
        self.win, self.env, self.friends = win, env, friends
        self.sel = 0
        self.room = None
        self.dialog = None
        self.typed = ""
        self.dlg_name = ""
        self.sent = []          # (방 이름, 'text' | 'image', 내용)
        win.add(MAIN, KAKAO_CLS, "카카오톡")
        win.fg = MAIN
        win.on_key = self.key

    def friend(self):
        return self.friends[self.sel] if 0 <= self.sel < len(self.friends) else None

    def key(self, name):
        fg = self.win.fg
        if name == "ENTER":
            if fg == MAIN and self.room is None:
                f = self.friend()
                if f and f.get("open") is not None:
                    self.env.at(f["open"], lambda f=f: self._open(f))
            elif self.room and fg == self.room:
                if self.typed:
                    self.sent.append((self.win.w[self.room]["title"], "text", self.typed))
                    self.typed = ""
            elif self.dialog and fg == self.dialog:
                path = self.dlg_name
                self.env.at(30, lambda: self._attach(path))
        elif name == "^V":
            clip = self.env.clip or ""
            if self.room and fg == self.room:
                self.typed += clip
            elif self.dialog and fg == self.dialog:
                self.dlg_name = clip
        elif name == "^T":
            if self.room and fg == self.room:
                f = self.friend()
                if f and f.get("dlg") is not None:
                    self.env.at(f["dlg"], self._dlg)
        elif name == "ESC":
            if self.dialog and fg == self.dialog:
                self._close_dlg()
            elif self.room and fg == self.room:
                self._close_room()
        elif name == "DOWN":
            if fg == MAIN:
                self.sel += 1

    def _open(self, f):
        h = 200 + self.sel
        self.win.add(h, KAKAO_CLS, f.get("title", f["name"]))
        self.room = h
        if self.win.fg == MAIN:
            self.win.fg = h

    def _dlg(self):
        if not self.room:
            return
        self.win.add(KAKAO_DLG, kw.DIALOG_CLASS, "열기", owner=self.room)
        self.win.w[self.room]["popup"] = KAKAO_DLG
        self.dialog = KAKAO_DLG
        self.dlg_name = ""
        if self.win.fg == self.room:
            self.win.fg = KAKAO_DLG

    def _close_dlg(self):
        if self.room:
            self.win.w[self.room]["popup"] = None
        self.win.w.pop(KAKAO_DLG, None)
        if self.win.fg == self.dialog:
            self.win.fg = self.room
        self.dialog = None

    def _attach(self, path):
        if not self.dialog:
            return
        if path and os.path.isfile(path):
            self.sent.append((self.win.w[self.room]["title"], "image", path))
        self._close_dlg()

    def _close_room(self):
        self.win.w.pop(self.room, None)
        if self.win.fg == self.room:
            self.win.fg = MAIN
        self.room = None
        self.typed = ""


# ---------------------------------------------------------------------------
# 가짜 화면
# ---------------------------------------------------------------------------
MSG = "안녕하세요 고객님\n이번 달 프로모션 안내드립니다"


class FakeUi:
    def __init__(self, mode=0, msg=MSG, img="", count="3"):
        self.mode_, self.msg, self.img, self.count = mode, msg, img, count
        self.messages, self.logs, self.progress, self.hints, self.balloons = [], [], [], [], []
        self.stats, self.running_states = {}, []

    def message_text(self):
        return self.msg

    def image_path(self):
        return self.img

    def mode(self):
        return self.mode_

    def count_text(self):
        return self.count

    def set_running(self, on):
        self.running_states.append(on)

    def set_stats(self, success, stop, skip, speed):
        for k, v in (("success", success), ("stop", stop), ("skip", skip), ("speed", speed)):
            if v is not None:
                self.stats[k] = v

    def set_progress(self, pct, text):
        self.progress.append((pct, text))

    def add_log(self, text, kind):
        self.logs.append((kind, text))

    def log_text(self):
        return "".join(t + "\r\n" for _k, t in self.logs)

    def show_message(self, text):
        self.messages.append(text)

    def tray_hint(self, text):
        self.hints.append(text)

    def tray_balloon(self, title, text):
        self.balloons.append((title, text))


_N = [0]


def make(friends, mode=0, count="3", img="", store=None, prefs=None, msg=MSG):
    env = FakeEnv()
    win = FakeWin(env)
    env.win = win
    sim = KakaoSim(win, env, friends)
    ui = FakeUi(mode=mode, msg=msg, img=img, count=count)
    _N[0] += 1
    if store is None:
        store = km.CustomerStore(TMP / f"cu{_N[0]}.tsv", now=env.now)
    else:
        store._now = env.now
    if prefs is None:
        prefs = km.Prefs(TMP / f"prefs{_N[0]}.json")
    eng = km.MacroEngine(ui, env, store, prefs)
    return env, win, sim, ui, eng


def run(env, eng, limit_ms=900_000):
    """메시지 루프 — 1ms 타이머가 남아 있는 동안."""
    end = env.t + limit_ms
    while env.t < end and env.pending:
        fn = env.pending.pop(0)
        env.delay(1)
        fn()


def seq(win):
    return [k for _t, k, _h in win.keys]


def kinds(ui):
    return [k for k, _t in ui.logs]


def friends(*names, open_ms=120, dlg=150):
    return [dict(name=n, open=open_ms, dlg=dlg) for n in names]


STAMP = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"
KAKAO_WINS = {MAIN, KAKAO_DLG, KAKAO_MSGBOX} | set(range(200, 260))


def only_kakao(win):
    return all(h in KAKAO_WINS for _t, _k, h in win.keys)


IMG = TMP / "명함 사진.png"
IMG.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)

# ===========================================================================
print("[1] 시작 전 확인(Button1Click) — 문구 그대로 · 아무것도 건드리지 않는다")
for mode, img, want in ((-1, "", "실행할 모드를 선택해 주세요."),
                        (1, "", "이미지를 불러와주세요. (이미지 경로가 비어있습니다.)"),
                        (2, "   ", "이미지를 불러와주세요. (이미지 경로가 비어있습니다.)"),
                        (1, str(TMP / "없는 그림.png"), "선택한 이미지 파일이 존재하지 않습니다. 경로를 다시 확인해주세요.")):
    env, win, sim, ui, eng = make(friends("김민"), mode=mode, img=img)
    eng.button1_click()
    ok(f"모드 {mode} · 경로 {img[-8:]!r} → '{want[:18]}…'",
       ui.messages == [want] and not eng.running and not win.keys and env.clip == "원래 클립보드"
       and not ui.running_states, ui.messages)

env, win, sim, ui, eng = make(friends("김민"), mode=0)
ui.start_block = lambda: "카톡 매크로는 구글 로그인을 해야 쓸 수 있습니다."
eng.button1_click()
ok("구글 로그인 전 → 시작하지 않고 까닭을 알린다(예전 비밀번호 인증 대신)",
   ui.messages == ["카톡 매크로는 구글 로그인을 해야 쓸 수 있습니다."] and not eng.running and not win.keys
   and env.clip == "원래 클립보드")
win.pressed.add(kw.VK_INSERT)
eng.hotkey_timer()
ok("Insert 로도 마찬가지", len(ui.messages) == 2 and not eng.running)
ui.start_block = lambda: ""
eng.button1_click()
ok("로그인하면 시작", eng.running)
eng.button2_click()

# ===========================================================================
print("[2] 텍스트 · 3명(발송인원수 3) — Enter → 방 확인 → Ctrl+V · Enter → ESC → 다음 지연 → ↓")
env, win, sim, ui, eng = make(friends("김민", "김민수", "이영희"), count="3")
first_store = eng.store
eng.button1_click()
ok("시작하면 클립보드에 메시지(텍스트 모드는 시작 때도 넣는다)", env.clip == MSG and ui.running_states == [True])
ok("카드 0 으로 · 진행 '0 / 3'", ui.stats == {"success": "성공: 0", "stop": "중단: 0", "skip": "건너뜀: 0",
                                          "speed": "0.0건/분"} and ui.progress[-1] == (0.0, "0 / 3"), ui.stats)
ok("트레이 풍선말 'A1Auto · 0 / 3'", ui.hints[-1] == "A1Auto · 0 / 3")
run(env, eng)
one = ["ENTER", "^V", "ENTER", "ESC", "DOWN"]
ok("키 순서(한 사람마다 같다)", seq(win) == one * 3, seq(win))
ok("세 사람에게 메시지 그대로", sim.sent == [(n, "text", MSG) for n in ("김민", "김민수", "이영희")], sim.sent)
ok("'김민' 다음 '김민수' 도 보낸다(이름 정확히 같을 때만 중복)", len(sim.sent) == 3)
ok("로그: 성공 3줄 + '정상 종료' 중단 1줄(빨강)", kinds(ui) == ["ok", "ok", "ok", "stop"]
   and all(re.fullmatch(f"✅ {STAMP} → {n} 발송완료", t) for (k, t), n in zip(ui.logs, ("김민", "김민수", "이영희")))
   and re.fullmatch(f"❌ {STAMP} → 중단: 정상 종료", ui.logs[-1][1]), ui.logs)
ok("끝나면 풍선 알림 'A1Auto — 정상 종료' · '성공 3 · 건너뜀 0 · 처리 3건'",
   ui.balloons == [("A1Auto — 정상 종료", "성공 3 · 건너뜀 0 · 처리 3건")], ui.balloons)
ok("클립보드 되돌림", env.clip == "원래 클립보드")
ok("단추 다시 켜짐", ui.running_states == [True, False] and not eng.running)
ok("카톡 창에만 키를 보냈다", only_kakao(win))
t = {k: [tt for tt, kk, _h in win.keys if kk == k] for k in ("ENTER", "^V", "ESC", "DOWN")}
ent_list, ent_room = t["ENTER"][0::2], t["ENTER"][1::2]
ok("Enter → (10 · min(700,300)=300 · 방 확인) → 메시지 넣고 50 → Ctrl+V", t["^V"][0] - ent_list[0] == 10 + 300 + 50,
   t["^V"][0] - ent_list[0])
ok("Ctrl+V → 10 → Enter", ent_room[0] - t["^V"][0] == 10)
ok("Enter → 10 · 200 → ESC", t["ESC"][0] - ent_room[0] == 210)
ok("ESC → 10 · 다음 채팅창 지연 700 → ↓", all(d - e == 710 for e, d in zip(t["ESC"], t["DOWN"])))
i0 = next(i for i, r in enumerate(win.raw) if r[0] == t["^V"][0] and r[1] == kw.VK_CONTROL)
raw = win.raw[i0:i0 + 4]
ok("Ctrl+V = Ctrl 누름 · V 누름 · (10) · V 뗌 · Ctrl 뗌 — 스캔 코드는 MapVirtualKey",
   [(r[1], r[3]) for r in raw] == [(kw.VK_CONTROL, 0), (kw.VK_V, 0), (kw.VK_V, 2), (kw.VK_CONTROL, 2)]
   and all(r[2] == win.map_vk(r[1]) for r in raw) and raw[2][0] - raw[1][0] == 10, raw)
mid = [p for p in ui.progress if "현재: 김민수" in p[1]]
ok("진행 '1 / 3 · 남은 약 …초 · 현재: 김민수'", any(re.fullmatch(r"1 / 3 · 남은 약 \d+초 · 현재: 김민수", p[1]) for p in mid)
   and ui.progress[-1] == (1.0, "3 / 3"), [p[1] for p in mid][:2])
ok("트레이 풍선말도 같은 글", ui.hints[-1] == "A1Auto · 3 / 3" and any("현재: 이영희" in h for h in ui.hints))
eng.timer2_timer()
ok("1초마다 카드(Timer2) — 성공 3 · 중단 1 · 건너뜀 0 · 분당 속도",
   ui.stats["success"] == "성공: 3" and ui.stats["stop"] == "중단: 1" and ui.stats["skip"] == "건너뜀: 0"
   and re.fullmatch(r"\d+\.\d건/분", ui.stats["speed"]), ui.stats)
st = km.CustomerStore(first_store.path)
st.load()
ok("고객 색인 — 셋 다 등록 · 보낸 횟수 1 · 최종발송 시각", st.count() == 3 and all(
    st.items[n].send_count == 1 and st.items[n].last_sent and st.items[n].first_seen for n in ("김민", "김민수", "이영희")))

# ===========================================================================
print("[3] 중복 발송 막기 — 최근 N일(기본 1) · 3번 연달아 건너뛰면 안전 중단")
env, win, sim, ui, eng = make(friends("김민", "김민수", "이영희"), count="3", store=first_store)
eng.button1_click()
run(env, eng)
ok("셋 다 건너뜀(보내지 않음)", sim.sent == [])
ok("로그: 건너뜀 3줄(호박색) + '연속 3회 실패 — 안전 중단'", kinds(ui) == ["skip", "skip", "skip", "stop"]
   and all(re.fullmatch(f"⏭ {STAMP} → 건너뜀: 최근 1일 내 발송함: {n}", t)
           for (k, t), n in zip(ui.logs, ("김민", "김민수", "이영희")))
   and ui.logs[-1][1].endswith("→ 중단: 연속 3회 실패 — 안전 중단"), ui.logs)
ok("세 번째는 다음 방으로 가지 않고 멈춘다(A1Auto 그대로)", seq(win) == ["ENTER", "ESC", "DOWN"] * 2 + ["ENTER"], seq(win))
ok("풍선 '성공 0 · 건너뜀 3 · 처리 2건'", ui.balloons == [("A1Auto — 연속 3회 실패 — 안전 중단", "성공 0 · 건너뜀 3 · 처리 2건")],
   ui.balloons)
pre = km.Prefs(TMP / "dup0.json")
pre.set_intervals(700, 700, 1200, dupdays=0)
env, win, sim, ui, eng = make(friends("김민"), count="1", store=first_store, prefs=pre)
eng.button1_click()
run(env, eng)
ok("중복 일수 0 = 검사 안 함 → 다시 보낸다 · 횟수 2", len(sim.sent) == 1 and first_store.items["김민"].send_count == 2)
first_store.items["김민수"].last_sent = env.now() - timedelta(hours=25)
ok("25시간 전에 보냈으면 1일 검사에 안 걸린다", not first_store.sent_within_days("김민수", 1)
   and first_store.sent_within_days("김민수", 2))

# ===========================================================================
print("[4] 방 이름 확인 실패 → 건너뜀 · 성공하면 연속 실패 0 · 기다림 max(2000, 텍스트 지연×3)")
fr = [dict(name="가", open=None), dict(name="나", open=None), dict(name="다", open=100),
      dict(name="라", open=None), dict(name="마", open=None), dict(name="바", open=None), dict(name="사", open=100)]
env, win, sim, ui, eng = make(fr, count="0")
eng.button1_click()
run(env, eng)
ok("가·나 건너뜀 → 다 보냄(연속 0) → 라·마·바 건너뜀 → 안전 중단", kinds(ui) == ["skip", "skip", "ok", "skip", "skip", "skip", "stop"]
   and ui.logs[0][1].endswith("건너뜀: 채팅방 이름 확인 실패") and [s[0] for s in sim.sent] == ["다"], ui.logs)
ent = [tt for tt, kk, _h in win.keys if kk == "ENTER"]
esc = [tt for tt, kk, _h in win.keys if kk == "ESC"]
wait = esc[0] - ent[0] - 310
ok("방 기다림 2100ms(80ms 마다 확인)", 2100 <= wait < 2100 + 80, wait)
pre = km.Prefs(TMP / "slow.json")
pre.set_intervals(1000, 700, 1200)
env, win, sim, ui, eng = make([dict(name="가", open=None)], count="1", prefs=pre)
eng.button1_click()
run(env, eng)
ent = [tt for tt, kk, _h in win.keys if kk == "ENTER"]
esc = [tt for tt, kk, _h in win.keys if kk == "ESC"]
ok("텍스트 지연 1000 → 방 기다림 3000 · 짧은 대기는 300 까지만", 3000 <= esc[0] - ent[0] - 310 < 3080, esc[0] - ent[0] - 310)
ok("발송인원수 1 — 건너뛰어도 한 명 처리로 '정상 종료'", ui.logs[-1][1].endswith("중단: 정상 종료"))
fr = [dict(name="단톡", open=100, title="카카오톡")]
env, win, sim, ui, eng = make(fr, count="1")
eng.button1_click()
run(env, eng)
ok("방 제목이 '카카오톡' 이면 이름 확인 실패", ui.logs[0][1].endswith("채팅방 이름 확인 실패"))

# ===========================================================================
print("[5] 카톡 창 이탈 → 즉시 중단(오발송 방지) · 다른 창으로는 키가 하나도 안 간다")
env, win, sim, ui, eng = make(friends("김민"), count="0")
win.fg = NOTEPAD
eng.button1_click()
run(env, eng)
ok("시작할 때 메모장이 앞 → Enter 도 안 보내고 멈춤", not win.keys and ui.logs[-1][1].endswith("중단: 카카오톡 창 이탈 — 오발송 방지"))
env, win, sim, ui, eng = make(friends("김민", open_ms=500), count="0")
env.at(200, lambda: setattr(win, "fg", NOTEPAD))
eng.button1_click()
run(env, eng)
ok("방을 기다리는 중에 메모장 → 멈춤(Enter 하나만)", seq(win) == ["ENTER"] and ui.logs[-1][1].endswith("카카오톡 창 이탈 — 오발송 방지"))
env, win, sim, ui, eng = make(friends("김민"), count="0")
env.on_clip = lambda s: env.at(55, lambda: setattr(win, "fg", NOTEPAD)) if s == MSG and len(env.clip_sets) > 1 else None
eng.button1_click()
run(env, eng)
ok("Ctrl+V 와 Enter 사이에 메모장 → Enter 는 안 보내고 멈춤", seq(win) == ["ENTER", "^V"] and sim.sent == []
   and ui.logs[-1][1].endswith("카카오톡 창 이탈 — 오발송 방지") and only_kakao(win), seq(win))
env, win, sim, ui, eng = make(friends("김민"), count="0")
env.at(400, lambda: setattr(win, "fg", NOTE_DLG))
eng.button1_click()
run(env, eng)
ok("메모장의 '저장' 대화상자(다른 프로그램) → 카톡으로 안 본다", ui.logs[-1][1].endswith("카카오톡 창 이탈 — 오발송 방지")
   and only_kakao(win))
env, win, sim, ui, eng = make(friends("김민"), count="0")
win.add(KAKAO_MSGBOX, kw.DIALOG_CLASS, "카카오톡", owner=MAIN)
win.fg = KAKAO_MSGBOX
ok("카톡이 띄운 알림 창(소유자가 카톡) → 카톡으로 본다 · 그 프로세스를 기억(KakaoPid)",
   eng.is_kakao_foreground() and eng.kakao_pid == KAKAO_PID)
win.add(400, "Qt683QWindowIcon", "일정관리기", pid=8000)
win.fg = 400
ok("일정관리기 창(Qt6)은 카톡이 아니다 — 매크로 중에 누르면 멈춘다", not eng.is_kakao_foreground())
win.add(401, "Qt5152QWindowIcon", "카카오톡", pid=8100)
win.fg = 401
ok("클래스에 Qt5 · QWidget · EVA_Window 가 들어 있으면 카톡(A1Auto 그대로)", eng.is_kakao_foreground())
win.fg = 0
ok("앞 창이 없으면 아니다", not eng.is_kakao_foreground())

# ===========================================================================
print("[6] 이미지 — 경로를 클립보드에 → Ctrl+T → 파일 열기 창 확인 → Ctrl+V → Enter → 이미지 지연")
env, win, sim, ui, eng = make(friends("김민", "이영희"), mode=1, img=str(IMG), count="2")
eng.button1_click()
ok("이미지 모드는 시작 때 클립보드를 안 바꾼다", env.clip == "원래 클립보드")
run(env, eng)
ok("키 순서", seq(win) == ["ENTER", "^T", "^V", "ENTER", "ESC", "DOWN"] * 2, seq(win))
ok("두 사람에게 그림", sim.sent == [("김민", "image", str(IMG)), ("이영희", "image", str(IMG))], sim.sent)
ok("Ctrl+V 는 파일 열기 창에서(경로 붙여넣기)", [h for _t, k, h in win.keys if k == "^V"] == [KAKAO_DLG] * 2)
tt = {k: [x for x, kk, _h in win.keys if kk == k] for k in ("^T", "^V", "ENTER", "ESC")}
ok("경로 넣고 100 → Ctrl+T", tt["^T"][0] - tt["ENTER"][0] >= 310 + 100)
ok("창이 뜨면 150 → Ctrl+V → 200 → Enter", tt["ENTER"][1] - tt["^V"][0] == 210 and 150 <= tt["^V"][0] - tt["^T"][0] - 150 < 150 + 60 + 10,
   tt["^V"][0] - tt["^T"][0])
ok("Enter → 10 · 이미지 지연 1200 → ESC", tt["ESC"][0] - tt["ENTER"][1] == 1210, tt["ESC"][0] - tt["ENTER"][1])
ok("로그 '✅ … → 김민 발송완료'", kinds(ui) == ["ok", "ok", "stop"] and ui.logs[0][1].endswith("→ 김민 발송완료"))
ok("끝나면 클립보드 되돌림", env.clip == "원래 클립보드")
env, win, sim, ui, eng = make([dict(name="김민", open=100, dlg=None)], mode=1, img=str(IMG), count="1")
eng.button1_click()
run(env, eng)
tt = {k: [x for x, kk, _h in win.keys if kk == k] for k in ("^T", "ESC")}
ok("파일 열기 창이 안 뜨면 건너뜀 — max(3000, 이미지 지연) 기다림(60ms 마다)",
   ui.logs[0][1].endswith("건너뜀: 파일 열기 창이 열리지 않음") and 3010 <= tt["ESC"][0] - tt["^T"][0] < 3010 + 60,
   tt["ESC"][0] - tt["^T"][0])
ok("창이 안 떴으면 Ctrl+V · Enter 를 안 보낸다(경로가 메시지로 가지 않게)", seq(win) == ["ENTER", "^T", "ESC", "DOWN"], seq(win))
pre = km.Prefs(TMP / "img4000.json")
pre.set_intervals(700, 700, 4000)
env, win, sim, ui, eng = make([dict(name="김민", open=100, dlg=None)], mode=1, img=str(IMG), count="1", prefs=pre)
eng.button1_click()
run(env, eng)
tt = {k: [x for x, kk, _h in win.keys if kk == k] for k in ("^T", "ESC")}
ok("이미지 지연 4000 → 창 기다림도 4000", 4010 <= tt["ESC"][0] - tt["^T"][0] < 4010 + 60, tt["ESC"][0] - tt["^T"][0])

# ===========================================================================
print("[7] 이미지+텍스트 — 그림 보내고 이미지 지연 → 메시지 넣고 150 → Ctrl+V → 200 → Enter → 500")
env, win, sim, ui, eng = make(friends("김민"), mode=2, img=str(IMG), count="1")
eng.button1_click()
run(env, eng)
ok("키 순서", seq(win) == ["ENTER", "^T", "^V", "ENTER", "^V", "ENTER", "ESC", "DOWN"], seq(win))
ok("그림 다음 메시지", sim.sent == [("김민", "image", str(IMG)), ("김민", "text", MSG)], sim.sent)
tt = [x for x, kk, _h in win.keys]
ok("그림 Enter → 10 · 1200 · 150 → Ctrl+V", tt[4] - tt[3] == 10 + 1200 + 150, tt[4] - tt[3])
ok("Ctrl+V → 10 · 200 → Enter → 10 · 500 → ESC", tt[5] - tt[4] == 210 and tt[6] - tt[5] == 510)
ok("끝나면 클립보드 되돌림", env.clip == "원래 클립보드")

# ===========================================================================
print("[8] 발송인원수 0 = 끝까지 · Delete(1초마다 확인) = 지금 사람까지 마치고 '사용자 중단'")
env, win, sim, ui, eng = make(friends("가", "나", "다", "라", "마", "바"), count="0")
env.every(1000, eng.hotkey_timer)
fired = []


def _press_delete(s):
    # 두 번째 사람 메시지를 클립보드에 넣은 직후(Ctrl+V 50ms 전)에 Delete — A1Auto 는 여기서 클립보드를 바로
    # 되돌려 Ctrl+V 가 원래 글을 보냈다
    if s == MSG and len(env.clip_sets) == 3 and not fired:
        fired.append(1)
        win.pressed.add(kw.VK_DELETE)
        env.at(20, eng.hotkey_timer)


env.on_clip = _press_delete
eng.button1_click()
run(env, eng)
ok("인원수 0 → 진행 'N건 진행'(남은 시간 없음)", any(p[1] == "1건 진행" for p in ui.progress)
   and not any("남은 약" in p[1] for p in ui.progress))
ok("Delete → 바로 '사용자 중단' 줄 · 그 사람 '발송완료' 는 그 뒤(A1Auto 그대로)", kinds(ui) == ["ok", "stop", "ok"]
   and ui.logs[1][1].endswith("→ 중단: 사용자 중단") and ui.logs[2][1].endswith("→ 나 발송완료") and not eng.running, ui.logs)
ok("누른 사람까지는 마친다 — 메시지가 그대로 갔다(원래 클립보드 글이 아니라)",
   sim.sent == [("가", "text", MSG), ("나", "text", MSG)], sim.sent)
ok("그 사람도 ESC · ↓ 까지 마치고 멈춘다", seq(win) == one * 2, seq(win))
ok("클립보드는 그 사람 차례가 끝난 뒤 되돌림", env.clip == "원래 클립보드")
ok("풍선은 누른 때의 숫자 '성공 1 · 건너뜀 0 · 처리 1건'(A1Auto 그대로)",
   ui.balloons == [("A1Auto — 사용자 중단", "성공 1 · 건너뜀 0 · 처리 1건")], ui.balloons)
eng.timer2_timer()
ok("1초 뒤 카드는 실제 수 '성공: 2'", ui.stats["success"] == "성공: 2")

# ===========================================================================
print("[9] 실행 중 Insert 는 무시(겹쳐 돌지 않게) · 쉬는 중 Insert = 시작 · Delete = 중단 로그")
env, win, sim, ui, eng = make(friends("가", "나", "다"), count="3")
env.every(1000, eng.hotkey_timer)
env.at(1500, lambda: win.pressed.add(kw.VK_INSERT))
env.at(2500, eng.button1_click)
eng.button1_click()
run(env, eng)
ok("세 사람 그대로 · 숫자도 처음부터 안 돌아감", [s[0] for s in sim.sent] == ["가", "나", "다"] and kinds(ui) == ["ok", "ok", "ok", "stop"]
   and ui.running_states == [True, False] and eng.success_count == 3, kinds(ui))
env, win, sim, ui, eng = make(friends("가", "나"), count="0")
env.on_clip = lambda s: (win.pressed.update({kw.VK_DELETE}), env.at(5, eng.hotkey_timer),
                         env.at(8, eng.button1_click)) if s == MSG and len(env.clip_sets) == 2 else None
eng.button1_click()
run(env, eng)
ok("중단 뒤 그 사람 차례가 끝나기 전에 누른 시작도 무시", [s[0] for s in sim.sent] == ["가"] and not eng.running
   and ui.running_states == [True, False], (sim.sent, ui.running_states))
env, win, sim, ui, eng = make(friends("가", "나"), count="2")
win.pressed.add(kw.VK_INSERT)
eng.hotkey_timer()
ok("Insert → 시작", eng.running)
run(env, eng)
ok("두 사람 보내고 끝", len(sim.sent) == 2 and not eng.running)
n_stop = eng.stop_count
win.pressed.add(kw.VK_DELETE)
eng.hotkey_timer()
ok("쉬는 중 Delete → '사용자 중단' 로그 · 중단 수 +1 · 풍선(A1Auto 그대로)",
   ui.logs[-1][1].endswith("중단: 사용자 중단") and eng.stop_count == n_stop + 1
   and ui.balloons[-1][0] == "A1Auto — 사용자 중단")
env, win, sim, ui, eng = make(friends("가"), count="1")
win.pressed.update({kw.VK_INSERT, kw.VK_DELETE})
eng.hotkey_timer()
ok("둘 다 눌렸으면 시작했다가 바로 중단(순서 그대로)", not eng.running and ui.running_states == [True, False])
run(env, eng)
ok("…그래서 아무에게도 안 보낸다", sim.sent == [] and not win.keys)

# ===========================================================================
print("[10] 클립보드 — 다른 프로그램이 쥐고 있으면 100ms 뒤 다시(5번까지) · 글이 없었으면 되돌리지 않는다")
env, win, sim, ui, eng = make(friends("가"), count="1")
env.clip_fail, t0 = 3, env.t
eng.set_clipboard_safe("x")
ok("세 번 실패 → 네 번째에 넣음(300ms)", env.clip == "x" and env.t - t0 == 300)
env.clip_fail, t0 = 9, env.t
eng.set_clipboard_safe("y")
ok("다섯 번 다 실패 → 포기(500ms) · 오류 없이", env.clip == "x" and env.t - t0 == 500)
env, win, sim, ui, eng = make(friends("가"), count="1")
env.clip = None
eng.button1_click()
run(env, eng)
ok("시작 전 클립보드에 글이 없었다 → 되돌리지 않는다(메시지가 남는다)", env.clip == MSG)

# ===========================================================================
print("[11] 작은 함수 — CleanKakaoTitle · FormatRemain · 속도 · StrToIntDef")
for s, want in (("[3] 홍길동 - 카카오톡", "홍길동"), ("홍길동 - KakaoTalk", "홍길동"), ("홍길동 - kakaotalk", "홍길동"),
                ("  김민수 입력 중...  ", "김민수"), ("입력 중...홍길동", "홍길동"), ("[공지] 팀방", "팀방"),
                ("카카오톡", "카카오톡"), ("", ""), ("[12] 이영희", "이영희")):
    ok(f"CleanKakaoTitle({s!r}) = {want!r}", kw.clean_kakao_title(s) == want, kw.clean_kakao_title(s))
for sec, want in ((0, "0초"), (42.4, "42초"), (42.5, "43초"), (59.6, "60초"), (60, "1분 0초"), (260.9, "4분 20초"),
                  (-5, "0초"), (3725, "62분 5초")):
    ok(f"FormatRemain({sec}) = {want}", km.format_remain(sec) == want, km.format_remain(sec))
ok("속도 '2.0건/분' · 0분이면 '0.0건/분'", km.speed_text(3, 1.5) == "2.0건/분" and km.speed_text(0, 0) == "0.0건/분")
for s, d, want in ((" 12", 0, 12), ("12 ", 0, 0), ("abc", 700, 700), ("", 0, 0), ("-5", 0, -5), ("+7", 0, 7), (None, 3, 3)):
    ok(f"StrToIntDef({s!r}, {d}) = {want}", km.str_to_int_def(s, d) == want)

# ===========================================================================
print("[12] customers.tsv — A1Auto 가 쓴 파일을 그대로 읽고 같은 모양으로 쓴다")
p = TMP / "a1" / "data" / "customers.tsv"
p.parent.mkdir(parents=True)
p.write_bytes(("이름\t최초발견\t최종발송\t발송횟수\t수신거부\t메모\r\n"
               "김민\t2026-11-01 10:00:00\t2026-11-26 09:00:00\t3\t0\t메모 있음\r\n"
               "\r\n"
               "박철수\t2026-10-01 08:00:00\t\t0\t1\t\r\n"
               " 이영희 \t2026-11-02 11:11:11\t2026-11-20 12:00:00\t1\t0\t\r\n"
               "최지\t2026-9-3\t\t\t\t\r\n").encode("utf-8-sig"))
NOW = datetime(2026, 11, 27, 9, 30, 0)
st = km.CustomerStore(p, now=lambda: NOW)
st.load()
k = st.items
ok("넷 읽음(빈 줄 · 머리줄 건너뜀)", st.count() == 4 and set(k) == {"김민", "박철수", "이영희", "최지"}, sorted(k))
ok("값 그대로", k["김민"].send_count == 3 and k["김민"].last_sent == datetime(2026, 11, 26, 9) and k["김민"].memo == "메모 있음"
   and k["박철수"].opt_out and k["박철수"].last_sent is None and k["최지"].first_seen == datetime(2026, 9, 3))
ok("24.5시간 전 → 1일 중복 아님 · 2일이면 중복 · 0일 = 검사 안 함 · 모르는 이름 아님",
   not st.sent_within_days("김민", 1) and st.sent_within_days("김민", 2) and not st.sent_within_days("김민", 0)
   and not st.sent_within_days("없는사람", 5) and not st.sent_within_days("박철수", 5))
k["김민"].memo = "탭\t섞인\r\n메모"
st.save()
raw = p.read_bytes()
txt = raw.decode("utf-8-sig")
ok("UTF-8 BOM · 줄 끝 CRLF · 머리줄", raw.startswith(b"\xef\xbb\xbf") and txt.startswith(km.TSV_HEADER + "\r\n")
   and txt.endswith("\r\n") and "\n" not in txt.replace("\r\n", ""))
ok("줄 모양 '김민\\t2026-11-01 10:00:00\\t2026-11-26 09:00:00\\t3\\t0\\t탭 섞인  메모'",
   "김민\t2026-11-01 10:00:00\t2026-11-26 09:00:00\t3\t0\t탭 섞인  메모\r\n" in txt
   and "박철수\t2026-10-01 08:00:00\t\t0\t1\t\r\n" in txt and "최지\t2026-09-03 00:00:00\t\t0\t0\t\r\n" in txt, txt)
st2 = km.CustomerStore(p)
st2.load()
ok("다시 읽어도 같다", {n: (c.first_seen, c.last_sent, c.send_count, c.opt_out) for n, c in st2.items.items()}
   == {n: (c.first_seen, c.last_sent, c.send_count, c.opt_out) for n, c in st.items.items()})
st.register_seen("새고객")
st.register_seen("김민")
ok("처음 본 방 → 등록(최초발견 = 지금) · 아는 방은 그대로", st.items["새고객"].first_seen == NOW and st.items["새고객"].send_count == 0
   and st.items["김민"].send_count == 3)
st.register_sent("김민")
st.register_sent("모르는방")
ok("보냄 → 횟수 +1 · 최종발송 = 지금 · 처음 보는 이름도 등록", st.items["김민"].send_count == 4 and st.items["김민"].last_sent == NOW
   and st.items["모르는방"].send_count == 1 and st.items["모르는방"].first_seen == NOW)
st3 = km.CustomerStore(p)
st3.load()
ok("보낼 때마다 바로 저장(도중에 꺼져도 남는다)", st3.items["김민"].send_count == 4 and "모르는방" in st3.items)
p2 = TMP / "hdr.tsv"
p2.write_bytes("김민\t\t\t1\t0\t\r\n이름\t\t\t2\t0\t\r\n".encode("utf-8"))
st4 = km.CustomerStore(p2)
st4.load()
ok("머리줄은 첫 줄일 때만 건너뛴다 · BOM 없어도 읽는다", set(st4.items) == {"김민", "이름"})
blocked = TMP / "막힘"
blocked.write_text("파일")
st5 = km.CustomerStore(blocked / "customers.tsv")
st5.register_sent("가")
ok("못 쓰면(엑셀에 열림 등) 넘어가고 표시만 — 발송은 계속", st5.dirty and st5.items["가"].send_count == 1)
p3 = TMP / "shared.tsv"
a = km.CustomerStore(p3)
a.load()
b = km.CustomerStore(p3)
b.register_sent("업무자료검색에서 보낸 사람")
a.flush()
c3 = km.CustomerStore(p3)
c3.load()
ok("중단 · 닫기 때는 못 쓴 것이 있을 때만 저장 — 다른 프로그램이 쓴 기록을 덮지 않는다",
   "업무자료검색에서 보낸 사람" in c3.items)
env, win, sim, ui, eng = make(friends("가"), count="1", store=km.CustomerStore(p3))
eng.store.items.clear()
ok("엔진을 만들 때 색인을 읽는다(빈 색인으로 덮어쓰지 않게)", km.CustomerStore(p3).path == p3)
eng2 = km.MacroEngine(FakeUi(), env, km.CustomerStore(p3), km.Prefs(TMP / "p_x.json"))
ok("…읽힘", "업무자료검색에서 보낸 사람" in eng2.store.items)

print("[13] [A1Auto 기록 가져오기] — 예전 폴더의 data · logs")
old = TMP / "A1Auto_old"
(old / "data").mkdir(parents=True)
(old / "logs").mkdir()
(old / "data" / "customers.tsv").write_bytes(("이름\t최초발견\t최종발송\t발송횟수\t수신거부\t메모\r\n"
                                              "김민\t2025-01-01 00:00:00\t2026-11-27 08:00:00\t9\t0\t\r\n"
                                              "옛고객\t2025-02-02 00:00:00\t\t0\t0\t\r\n").encode("utf-8-sig"))
(old / "logs" / "log_2026-11-01_1000.txt").write_text("✅ 예전 로그", encoding="utf-8")
mine = km.CustomerStore(TMP / "mine.tsv", now=lambda: NOW)
mine.register_sent("김민")
n_cu, n_log = km.import_a1auto(mine, old)
ok("고객 합침(최초발견은 이른 쪽 · 최종발송은 늦은 쪽 · 횟수는 큰 쪽) · 로그 옮김",
   n_cu == 2 and n_log == 1 and mine.items["김민"].send_count == 9 and mine.items["김민"].first_seen == datetime(2025, 1, 1)
   and mine.items["김민"].last_sent == NOW and "옛고객" in mine.items
   and (km.logs_dir() / "log_2026-11-01_1000.txt").is_file(), (n_cu, n_log))
ok("두 번 가져와도 로그는 한 번", km.import_a1auto(mine, old)[1] == 0)
ok("A1Auto 폴더가 아니면 (-1, 0)", km.import_a1auto(mine, TMP / "없는폴더") == (-1, 0))

# ===========================================================================
print("[14] 로그 — 닫을 때 logs\\log_YYYY-MM-DD_HHNN.txt · [로그 불러오기]")
env, win, sim, ui, eng = make(friends("가"), count="1")
eng.button1_click()
run(env, eng)
path = eng.form_close(ui.log_text())
ok("파일 이름", Path(path).name == "log_" + env.now().strftime("%Y-%m-%d_%H%M") + ".txt" and Path(path).parent == km.logs_dir(),
   path)
b = Path(path).read_bytes()
ok("UTF-8 BOM · CRLF · 로그 그대로(✅ ❌ 도 안 깨짐)", b.startswith(b"\xef\xbb\xbf") and km.load_log_text(path) == ui.log_text()
   and "✅" in km.load_log_text(path))
ok("로그가 비었으면 안 쓴다", eng.form_close("") == "")
old_log = TMP / "ansi.txt"
old_log.write_bytes("✅ 2026-01-01 → 홍길동 발송완료".replace("✅", "?").encode("cp949"))
ok("예전 A1Auto 의 ANSI(CP949) 로그도 읽는다", km.load_log_text(old_log) == "? 2026-01-01 → 홍길동 발송완료")
env, win, sim, ui, eng = make(friends("가"), count="1")
eng.button1_click()
env.clip = MSG
eng.form_close("")
ok("닫을 때도 클립보드 되돌림", env.clip == "원래 클립보드")

# ===========================================================================
print("[15] 발송 간격 · 자주 쓰는 문구 — 내 구글 계정(앱 전용 공간) + 이 PC 사본")
pr = km.Prefs(TMP / "pr_default.json")
ok("처음 값 700 / 700 / 1200 · 중복 1일(jy.ini 못 읽을 때 그대로)",
   (pr.interval1, pr.interval2, pr.interval3, pr.dupdays) == (700, 700, 1200, 1))
ok("[기본값] 단추 800 / 800 / 1200(A1Auto 그대로 — 처음 값과 다르다)", km.DEFAULT_BUTTON == {"textsleep": 800,
                                                                                    "nextsleep": 800, "imagesleep": 1200})
ini = TMP / "jy.ini"
ini.write_bytes(b"[jy]\r\ntextsleep=900\r\nnextsleep=850\r\nimagesleep=1500\r\n")
ok("C:\\jy.ini 가 있으면 처음 한 번 그 값으로", pr.seed_from_ini(str(ini))
   and (pr.interval1, pr.interval2, pr.interval3, pr.dupdays) == (900, 850, 1500, 1))
ok("…두 번째는 안 한다", not pr.seed_from_ini(str(ini)))
ini2 = TMP / "jy2.ini"
ini2.write_bytes("[JY]\r\nTextSleep = 650\r\ndupdays=3\r\nimagesleep=abc\r\n".encode("utf-16"))
pr2 = km.Prefs(TMP / "pr_ini2.json")
ok("대소문자 · UTF-16 · 잘못된 값은 기본값", pr2.seed_from_ini(str(ini2))
   and (pr2.interval1, pr2.interval2, pr2.interval3, pr2.dupdays) == (650, 700, 1200, 3))
ok("jy.ini 가 없으면 그대로", not km.Prefs(TMP / "pr_none.json").seed_from_ini(str(TMP / "없음.ini")))
pr.set_intervals(1000, 900, 2000, dupdays=2)
again = km.Prefs(TMP / "pr_default.json")
ok("고치면 이 PC 사본에 바로(인터넷 없어도 다음에 켜면 그대로)", (again.interval1, again.interval2, again.interval3, again.dupdays)
   == (1000, 900, 2000, 2))
pr.put("인사", "안녕하세요\n고객님")
pr.put("안내", "프로모션 안내")
pr.put("인사", "안녕하세요(고침)")
ok("문구 저장 · 덮어쓰기 · 목록 순서(처음 저장한 순서)", pr.titles() == ["인사", "안내"] and pr.get("인사") == "안녕하세요(고침)")
pr.delete("안내")
ok("삭제", pr.titles() == ["인사"] and pr.get("안내") == "" and "안내" in pr.data["dead"])
ok("제목 정리(앞뒤 공백 · 줄바꿈)", km.clean_title("  첫\r\n인사 ") == "첫인사")


class FakeDrive:
    def __init__(self):
        self.files, self.calls = {}, []

    def find(self, name):
        self.calls.append(("find", name))
        return ("F_" + name) if name in self.files else None

    def read(self, fid):
        self.calls.append(("read", fid))
        return self.files[fid[2:]]

    def write(self, name, text):
        self.calls.append(("write", name))
        self.files[name] = text


A = FakeDrive()
pc1 = km.Prefs(TMP / "pc1.json")
ok("아무것도 안 정했으면 계정에 쓰지 않는다", not pc1.sync_once(A, "me@example.com") and not A.files)
pc1.put("인사", "PC1 인사")
pc1.set_intervals(900, 900, 1500)
pc1.sync_once(A, "me@example.com")
rem = json.loads(A.files[km.REMOTE_NAME])
ok("PC1 → 계정에 올림(kakao_macro.json — 간격 · 문구)", rem["settings"]["textsleep"] == 900 and rem["phrases"]["인사"]["text"] == "PC1 인사"
   and "account" not in rem)
pc2 = km.Prefs(TMP / "pc2.json")
pc2.seed_from_ini(str(ini))
ch = pc2.sync_once(A, "me@example.com")
ok("PC2(jy.ini 로 시작) → 계정 값을 따른다 · 문구도 자동으로", ch and (pc2.interval1, pc2.interval2, pc2.interval3) == (900, 900, 1500)
   and pc2.get("인사") == "PC1 인사")
pc2.delete("인사")
pc2.put("안내", "PC2 안내")
pc2.sync_once(A, "me@example.com")
pc1.sync_once(A, "me@example.com")
ok("PC2 에서 지운 것 · 더한 것 → PC1 도", pc1.titles() == ["안내"] and pc1.get("안내") == "PC2 안내")
pc1.put("안내", "PC1 이 먼저 고침")
pc2.put("안내", "PC2 가 나중에 고침")
pc1.sync_once(A, "me@example.com")
pc2.sync_once(A, "me@example.com")
pc1.sync_once(A, "me@example.com")
ok("같은 제목을 두 PC 에서 고치면 나중 것", pc1.get("안내") == pc2.get("안내") == "PC2 가 나중에 고침")
pc1.put("인사", "다시 만든 인사")
pc1.sync_once(A, "me@example.com")
pc2.sync_once(A, "me@example.com")
ok("지웠던 제목을 나중에 다시 만들면 살아난다", pc2.get("인사") == "다시 만든 인사")
pc2.set_intervals(1100, 1100, 1300, dupdays=0)
pc2.sync_once(A, "me@example.com")
pc1.sync_once(A, "me@example.com")
ok("간격도 나중에 고친 쪽", (pc1.interval1, pc1.interval3, pc1.dupdays) == (1100, 1300, 0))
A.files[km.REMOTE_NAME] = "{깨짐"
n = len(A.calls)
ok("계정 것이 깨졌으면 덮어쓰지 않는다", not pc1.sync_once(A, "me@example.com")
   and not [c for c in A.calls[n:] if c[0] == "write"])
B = FakeDrive()
B.files[km.REMOTE_NAME] = json.dumps({"v": 1, "settings": {"textsleep": 500, "nextsleep": 500, "imagesleep": 900, "dupdays": 1,
                                                          "at": "2026-01-01T00:00:00.000000Z"},
                                      "phrases": {"B 문구": {"text": "B", "at": "2026-01-01T00:00:00.000000Z"}}, "dead": {}})
pc1b = km.Prefs(TMP / "pc1.json")
pc1b.sync_once(B, "other@example.com")
ok("다른 계정으로 바꾸면 그 계정 것으로 — 앞 계정 문구를 올리지 않는다", pc1b.titles() == ["B 문구"] and pc1b.interval1 == 500
   and "인사" not in json.loads(B.files[km.REMOTE_NAME])["phrases"])
same = km.Prefs(TMP / "pc1.json")
ok("일정관리기 · 업무자료검색은 같은 사본(%APPDATA%\\A1Auto\\kakao_macro.json)",
   km.prefs_file() == Path(os.environ["APPDATA"]) / "A1Auto" / "kakao_macro.json" and same.titles() == ["B 문구"])


class SlowDrive(FakeDrive):
    def __init__(self, prefs):
        super().__init__()
        self.prefs = prefs

    def write(self, name, text):
        self.prefs.put("맞추는 중에 저장", "살아야 한다")
        super().write(name, text)


pc3 = km.Prefs(TMP / "pc3.json")
pc3.put("처음", "1")
S = SlowDrive(pc3)
pc3.sync_once(S, "me@example.com")
ok("맞추는 사이에 고친 것도 살린다(다음에 올라간다)", pc3.titles() == ["처음", "맞추는 중에 저장"])
pc3.sync_once(S, "me@example.com")
ok("…다음 맞추기에 올라감", "맞추는 중에 저장" in json.loads(S.files[km.REMOTE_NAME])["phrases"])

# ===========================================================================
print("[16] 서버 기능은 없다 — 킬스위치 · 비밀번호 · 서버 주소")
srcs = [_HERE.parent / "kbsearch" / f for f in ("kakao_macro.py", "kakao_win.py", "kakao_macro_view.py", "kakao_history.py")]
srcs = [s for s in srcs if s.is_file()]
bad_words = ("http://", "https://", "dothome", ".php", "sv.txt", "pwhash", "AppPwHash", "del.bat", "서버 점검 중",
             "비밀번호를 입력", "프로그램 인증", "URLDownloadToFile", "kmacro_public", "jy2 hansome")
hits = [(s.name, w) for s in srcs for w in bad_words if w in s.read_text(encoding="utf-8")]
ok(f"{len(srcs)}개 파일에 서버 주소 · 비밀번호 · 킬스위치 흔적 없음", not hits and len(srcs) >= 2, hits)

print()
print(f"{len(FAIL)}건 실패" if FAIL else "전부 통과", flush=True)
_sys.exit(1 if FAIL else 0)
