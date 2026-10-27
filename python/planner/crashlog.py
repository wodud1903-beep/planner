"""갑자기 꺼지거나 멈출 때 — 그 순간을 기록해 두고, 다음에 켤 때 알려 준다.

exe 는 창 프로그램이라 오류가 나도 화면에 아무것도 안 남는다. 지점장이 겪는 건
"멈췄다가 꺼진다" 뿐이고, 원인은 짐작으로 찾아야 했다. 이제 남긴다:

  · 갑자기 꺼짐  — faulthandler 가 그 순간의 코드 위치를 적는다(윈도 치명 오류 포함)
  · 멈춤         — 화면 스레드가 15초 넘게 응답하지 않으면 모든 스레드의 위치를 적는다
  · 파이썬 오류  — 잡히지 않은 오류(단추를 눌렀다 생긴 것 포함)

파일: %APPDATA%\\Planner\\crash_log.txt (1MB 넘으면 앞을 자른다)

**다음에 켤 때 알려 준다** — 정상으로 끝나지 않았고(running 표시가 남음) 그 판에
기록된 것이 있으면. PC 를 그냥 끌 때(앱을 켜 둔 채)는 기록이 없으므로 묻지 않는다.
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

_fh = None
_lock = threading.Lock()
_beat = time.monotonic()
_watch_stop = threading.Event()


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


def _last_session() -> str:
    """마지막 '시작' 뒤에 적힌 것(지난번 판의 기록). 없으면 ""."""
    try:
        txt = log_path().read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    i = txt.rfind(START_TAG)
    if i < 0:
        return txt.strip()[-6000:]
    body = txt[i:].split("\n", 1)[1] if "\n" in txt[i:] else ""
    return body.strip()[-6000:]


def start() -> str:
    """켤 때 부른다. 지난번이 비정상으로 끝났고 기록이 있으면 그 기록을 돌려준다."""
    global _fh
    prev = ""
    try:
        if _mark_path().exists():
            prev = _last_session()
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


def _watch_loop(freeze_sec: float, every: float) -> None:
    dumped = False
    last = time.monotonic()
    while not _watch_stop.wait(every):
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
            write(f"멈춤 — 화면이 {int(idle)}초째 응답 없음", "아래는 그때 각 스레드가 하던 일:")
            with _lock:
                try:
                    if _fh is not None:
                        faulthandler.dump_traceback(file=_fh, all_threads=True)
                        _fh.flush()
                except Exception:
                    pass
        elif idle <= freeze_sec:
            dumped = False


def start_watchdog(app=None, freeze_sec: float = FREEZE_SEC, every: float = WATCH_EVERY):
    """멈춤 감시를 켠다. app 이 있으면 1초마다 화면 스레드에서 beat() 를 부른다."""
    _watch_stop.clear()
    timer = None
    if app is not None:
        from PySide6.QtCore import QTimer
        timer = QTimer(app)
        timer.timeout.connect(beat)
        timer.start(1000)
    beat()
    th = threading.Thread(target=_watch_loop, args=(freeze_sec, every),
                          name="멈춤감시", daemon=True)
    th.start()
    return timer, th


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
