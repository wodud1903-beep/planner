"""갑자기 꺼지거나 멈출 때 — 그 순간을 기록해 두고, 다음에 켤 때 알려 준다.

exe 는 창 프로그램이라 오류가 나도 화면에 아무것도 안 남는다. 지점장이 겪는 건
"멈췄다가 꺼진다" 뿐이고, 원인은 짐작으로 찾아야 했다. 이제 남긴다:

  · 갑자기 꺼짐  — faulthandler 가 그 순간의 코드 위치를 적는다(윈도 치명 오류 포함)
  · 멈춤         — 화면 스레드가 15초 넘게 응답하지 않으면 모든 스레드의 위치를 적는다
  · 파이썬 오류  — 잡히지 않은 오류(단추를 눌렀다 생긴 것 포함)
  · 메모리       — 1GB·2GB… 처음 넘을 때(메모리가 바닥나 꺼지면 기록이 안 남으므로)
  · Qt 오류      — Qt 가 내는 오류 문구(qFatal 은 적은 뒤에 꺼진다)

파일: %APPDATA%\\Planner\\crash_log.txt (1MB 넘으면 앞을 자른다)

**다음에 켤 때 알려 준다** — 정상으로 끝나지 않았고(running 표시가 남음) 그 판에
**진짜 문제**가 기록돼 있으면. PC 를 그냥 끌 때(앱을 켜 둔 채)는 묻지 않는다.
알림·[기록 복사] 는 요약이다 — 무슨 일이 있었는지 목록 + 마지막 문제 때 화면이
하던 일 + 끝부분(맨 앞의 오류 종류 줄이 잘리지 않게).
"""

from __future__ import annotations

import faulthandler
import os
import sys
import threading
import time
import traceback
from datetime import datetime

from . import config

LOG_NAME = "crash_log.txt"
MARK_NAME = "running.flag"
MAX_BYTES = 1_000_000
KEEP_BYTES = 400_000
START_TAG = "===== 시작 "
FREEZE_SEC = 15                 # 이만큼 응답이 없으면 '멈춤' 으로 적는다
WATCH_EVERY = 5
MEM_STEP = 1 << 30              # 메모리가 1GB 를 넘을 때마다 한 번씩 적는다
MEM_PROBLEM = 2 << 30           # 이만큼 넘으면 '문제'(그 아래는 참고로만 적는다)
SUMMARY_MAX = 6000
QT_WARN_MAX = 50                # Qt 경고는 한 판에 이만큼만

# ⚠️ 윈도에서 faulthandler 는 **스스로 처리되는** 예외까지 'fatal' 로 적는다. COM·
#    입력기·클립보드·끌어놓기가 흔히 던지는 아래 코드는 프로그램이 멀쩡히 계속 돈다
#    (RPC_E_* = 0x8001xxxx, RPC_S_* 일부). 이것만 있는 판은 '비정상 종료' 로 치지 않는다.
HARMLESS_PREFIX = ("0x8001",)
HARMLESS_CODES = {"0x800706ba", "0x800706be", "0x406d1388"}

_fh = None
_lock = threading.Lock()
_beat = time.monotonic()
_watch_stop = threading.Event()
_qt_warns = 0


def log_path():
    return config.base_dir() / LOG_NAME


def _mark_path():
    return config.base_dir() / MARK_NAME


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def write(kind: str, text: str) -> None:
    """기록 한 덩어리 — 머리글(무엇·판·시각) + 내용."""
    global _fh
    with _lock:
        try:
            f = _fh or open(log_path(), "a", encoding="utf-8")
            f.write(f"\n----- {kind} · v{config.APP_VERSION} · {_now()} -----\n")
            f.write(text.rstrip() + "\n")
            f.flush()
            if f is not _fh:
                f.close()
        except Exception:
            pass                # 기록이 실패해도 프로그램은 계속 돈다


def _trim() -> None:
    p = log_path()
    try:
        if p.exists() and p.stat().st_size > MAX_BYTES:
            data = p.read_bytes()[-KEEP_BYTES:]
            cut = data.find(b"\n")
            p.write_bytes(data[cut + 1:] if cut >= 0 else data)
    except Exception:
        pass


def _last_session(limit: int = SUMMARY_MAX) -> str:
    """마지막 '시작' 뒤에 적힌 것(지난번 판의 기록). 없으면 "". limit=0 이면 전부."""
    try:
        txt = log_path().read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    i = txt.rfind(START_TAG)
    if i < 0:
        body = txt.strip()
    else:
        body = (txt[i:].split("\n", 1)[1] if "\n" in txt[i:] else "").strip()
    return body[-limit:] if limit else body


# ---------------------------------------------------------------------------
# 판 기록 읽기 — 무엇이 있었나, 진짜 문제인가, 요약
# ---------------------------------------------------------------------------
_FATAL_HEADS = ("Windows fatal exception:", "Fatal Python error")


def _is_head(line: str) -> bool:
    return line.startswith("----- ") or line.startswith(_FATAL_HEADS)


def _harmless(head: str) -> bool:
    """무해한 윈도 알림인가 — 'Windows fatal exception: code 0x8001010d' 같은 것."""
    if not head.startswith("Windows fatal exception: code "):
        return False
    code = head.rsplit(" ", 1)[-1].strip().lower()
    return code.startswith(HARMLESS_PREFIX) or code in HARMLESS_CODES


def _problem_head(head: str) -> bool:
    if head.startswith(_FATAL_HEADS):
        return not _harmless(head)
    if head.startswith("----- "):
        kind = head[6:].split(" · ", 1)[0]
        return not kind.startswith(("참고", "Qt 경고"))
    return False


def has_problem(text: str) -> bool:
    """그 판에 진짜 문제(치명 오류·멈춤·파이썬 오류·메모리·Qt 오류)가 있었나."""
    return any(_problem_head(ln) for ln in (text or "").splitlines() if _is_head(ln))


def summary(text: str, limit: int = SUMMARY_MAX) -> str:
    """알림·[기록 복사] 용 요약.

    ⚠️ 예전엔 끝 6000자만 잘라 보여 줘서, 스레드 목록이 길면 맨 앞의 **오류 종류 줄**
       ("Windows fatal exception: access violation")이 잘려 나갔다. 이제
       ① 그 판에 있었던 일 목록(같은 것은 ×N) ② 마지막 문제 때 **화면 스레드가 하던 일**
       ③ 끝부분 순서로 모은다.
    """
    lines = (text or "").splitlines()
    heads: list = []                    # [(줄, 횟수)] — 이어서 같은 것은 묶는다
    last = -1
    for i, ln in enumerate(lines):
        if not _is_head(ln):
            continue
        tag = ln + ("  (무해한 윈도 알림)" if _harmless(ln) else "")
        if heads and heads[-1][0] == tag:
            heads[-1][1] += 1
        else:
            heads.append([tag, 1])
        if _problem_head(ln):
            last = i
    out = ["[그 판에 있었던 일]"]
    out += [h if n == 1 else f"{h}  ×{n}" for h, n in heads[-30:]]
    if last >= 0:
        block = []
        for ln in lines[last + 1:]:
            if _is_head(ln):
                break
            block.append(ln)
        out += ["", "[마지막 문제]", lines[last]]
        cur = next((k for k, ln in enumerate(block) if ln.startswith("Current thread")), -1)
        if cur >= 0:                    # 치명 오류 — 화면 스레드 부분만 먼저
            part = []
            for ln in block[cur:]:
                if part and not ln.strip():
                    break
                part.append(ln)
            out += part[:40]
        else:                           # 우리 기록(파이썬 오류·멈춤 등) — 앞부분
            out += [ln for ln in block if ln.strip()][:40]
    head = "\n".join(out)
    room = limit - len(head) - 20
    tail = "\n".join(lines)[-room:] if room > 200 else ""
    res = head + ("\n\n[끝부분]\n" + tail if tail else "")
    return res[:limit]


def start() -> str:
    """켤 때 부른다. 지난번이 비정상으로 끝났고 기록이 있으면 그 기록을 돌려준다."""
    global _fh
    prev = ""
    try:
        if _mark_path().exists():
            raw = _last_session(limit=0)
            prev = summary(raw) if has_problem(raw) else ""
    except Exception:
        prev = ""
    _trim()
    try:
        _fh = open(log_path(), "a", encoding="utf-8")
        _fh.write(f"\n{START_TAG}v{config.APP_VERSION} · {_now()} · pid {os.getpid()} =====\n")
        _fh.flush()
        faulthandler.enable(file=_fh, all_threads=True)
    except Exception:
        _fh = None
    try:
        config.atomic_write(_mark_path(), f"{os.getpid()} {config.APP_VERSION} {_now()}")
    except Exception:
        pass
    # 원래 처리기도 그대로 부른다(적기만 하고 삼키지 않는다) — 켜자마자 나는 오류는
    # exe 가 원래대로 오류 창을 띄워야 한다.
    global _prev_hook, _prev_thread_hook
    if sys.excepthook is not _excepthook:
        _prev_hook = sys.excepthook
    if threading.excepthook is not _thread_hook:
        _prev_thread_hook = threading.excepthook
    sys.excepthook = _excepthook
    threading.excepthook = _thread_hook
    return prev


_prev_hook = sys.__excepthook__
_prev_thread_hook = threading.__excepthook__


def clean_exit(*_a) -> None:
    """정상으로 끝날 때([종료]·업데이트·윈도 끄기) — running 표시를 지운다."""
    _watch_stop.set()
    try:
        _mark_path().unlink()
    except Exception:
        pass


def _excepthook(tp, val, tb):
    write("파이썬 오류", "".join(traceback.format_exception(tp, val, tb)))
    try:
        if _prev_hook is not None and _prev_hook is not _excepthook:
            _prev_hook(tp, val, tb)
    except Exception:
        pass


def _thread_hook(args):
    if args.exc_type is SystemExit:
        return
    name = getattr(args.thread, "name", "?")
    write(f"파이썬 오류(일꾼 {name})",
          "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))
    try:
        if _prev_thread_hook is not None and _prev_thread_hook is not _thread_hook:
            _prev_thread_hook(args)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 멈춤 감시
# ---------------------------------------------------------------------------
def beat() -> None:
    """화면 스레드가 살아 있다는 표시 — 1초 타이머가 부른다."""
    global _beat
    _beat = time.monotonic()


def _mem_bytes() -> int:
    """이 프로그램이 쓰는 메모리(윈도: 커밋된 개인 메모리). 모르면 0."""
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class _PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t),
                            ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t),
                            ("PeakPagefileUsage", ctypes.c_size_t)]
            k32 = ctypes.windll.kernel32
            k32.GetCurrentProcess.restype = wintypes.HANDLE
            fn = k32.K32GetProcessMemoryInfo
            fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
            fn.restype = wintypes.BOOL
            pmc = _PMC()
            pmc.cb = ctypes.sizeof(_PMC)
            if fn(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
                return int(max(pmc.PagefileUsage, pmc.WorkingSetSize))
            return 0
        with open("/proc/self/statm") as f:
            return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    except Exception:
        return 0


def _dump_all(kind: str) -> None:
    write(kind, "아래는 그때 각 스레드가 하던 일:")
    with _lock:
        try:
            if _fh is not None:
                faulthandler.dump_traceback(file=_fh, all_threads=True)
                _fh.flush()
        except Exception:
            pass


def _watch_loop(freeze_sec: float, every: float, mem_step: int = MEM_STEP) -> None:
    dumped = False
    last = time.monotonic()
    mem_level = 0
    while not _watch_stop.wait(every):
        # 메모리 — 1GB·2GB… 처음 넘을 때 한 번씩. 메모리가 바닥나 꺼지면 faulthandler 도
        # 못 적으므로, 그 전에 '어디서 늘고 있었나' 를 남겨 둔다.
        if mem_step > 0:
            used = _mem_bytes()
            level = used // mem_step
            if level > mem_level:
                mem_level = level
                gb = f"메모리 {used / (1 << 30):.1f}GB 넘음"
                _dump_all(gb if used >= MEM_PROBLEM else f"참고 — {gb}")
        now = time.monotonic()
        # ⚠️ PC 가 잠자기에서 깨면 시계가 확 건너뛴다 — 그건 멈춤이 아니다.
        #    감시하는 이쪽도 그만큼 못 돌았으면(예정보다 한참 늦게 깼으면) 넘어간다.
        if now - last > every * 3:
            beat()
            dumped = False
        last = now
        idle = now - _beat
        if idle > freeze_sec and not dumped:
            dumped = True
            _dump_all(f"멈춤 — 화면이 {int(idle)}초째 응답 없음")
        elif idle <= freeze_sec:
            dumped = False


def start_watchdog(app=None, freeze_sec: float = FREEZE_SEC, every: float = WATCH_EVERY,
                   mem_step: int = MEM_STEP):
    """멈춤·메모리 감시를 켠다. app 이 있으면 1초마다 화면 스레드에서 beat() 를 부른다."""
    _watch_stop.clear()
    timer = None
    if app is not None:
        from PySide6.QtCore import QTimer
        timer = QTimer(app)
        timer.timeout.connect(beat)
        timer.start(1000)
    beat()
    th = threading.Thread(target=_watch_loop, args=(freeze_sec, every, mem_step),
                          name="멈춤감시", daemon=True)
    th.start()
    return timer, th


# ---------------------------------------------------------------------------
# Qt 오류 문구 · 참고 기록
# ---------------------------------------------------------------------------
def _qt_message(mode, ctx, msg) -> None:
    global _qt_warns
    try:
        from PySide6.QtCore import QtMsgType
        where = ""
        try:
            if ctx is not None and ctx.file:
                where = f"\n  ({ctx.file}:{ctx.line} {ctx.function or ''})"
        except Exception:
            pass
        if mode in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            kind = "Qt 치명 오류" if mode == QtMsgType.QtFatalMsg else "Qt 오류"
            write(kind, str(msg) + where)
        elif mode == QtMsgType.QtWarningMsg and _qt_warns < QT_WARN_MAX:
            _qt_warns += 1
            write("Qt 경고", str(msg) + where)
    except Exception:
        pass


def install_qt_handler() -> None:
    """Qt 가 내는 오류 문구를 기록에 남긴다. 창 프로그램이라 원래는 아무 데도 안 보인다."""
    try:
        from PySide6.QtCore import qInstallMessageHandler
        qInstallMessageHandler(_qt_message)
    except Exception:
        pass


def note(text: str) -> None:
    """참고 한 줄 — 문제가 아니라, 문제가 났을 때 '그 전에 무엇을 했나' 를 보려고."""
    write(f"참고 — {text}", "")


# ---------------------------------------------------------------------------
# 다음에 켤 때 알려 주기
# ---------------------------------------------------------------------------
def notice_text() -> str:
    return ("지난번에 프로그램이 비정상으로 꺼졌습니다(멈춤·갑자기 꺼짐).\n\n"
            "[기록 복사] 를 누른 뒤 카카오톡으로 보내 주시면 원인을 바로 찾을 수 있습니다.\n"
            f"(기록 파일: {log_path()})")


def show_notice(parent, prev: str) -> None:
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QMessageBox
    box = QMessageBox(parent)
    box.setWindowTitle(config.APP_NAME)
    box.setIcon(QMessageBox.Warning)
    box.setText(notice_text())
    box.setDetailedText(prev)
    copy = box.addButton("기록 복사", QMessageBox.ActionRole)
    box.addButton("닫기", QMessageBox.RejectRole)
    box.exec()
    if box.clickedButton() is copy:
        QGuiApplication.clipboard().setText(
            f"[일정관리기 v{config.APP_VERSION} 비정상 종료 기록]\n{prev}")
