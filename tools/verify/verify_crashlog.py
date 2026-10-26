"""비정상 종료 기록 — 멈춤·꺼짐·파이썬 오류를 남기고, 다음에 켤 때 알려 주는지.

지점장이 겪은 건 "자료검색을 쓰다가 멈췄다가 꺼진다" 뿐이었다. exe 는 창 프로그램이라
화면에 아무것도 안 남아 원인을 짐작으로 찾아야 했다. 이제 그 순간을 적어 둔다.
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))

import os
import tempfile
import threading
import time

os.environ["APPDATA"] = tempfile.mkdtemp()

from planner import config, crashlog  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name
          + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


def log():
    try:
        return crashlog.log_path().read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def restart():
    """프로그램을 다시 켠 것처럼 — 열린 기록 파일을 닫고 start() 를 다시 부른다."""
    if crashlog._fh is not None:
        import faulthandler
        faulthandler.disable()
        crashlog._fh.close()
        crashlog._fh = None
    return crashlog.start()


print("[1] 처음 켤 때 — 알릴 것이 없다")
prev = crashlog.start()
ok("처음엔 알릴 것 없음", prev == "")
ok("'도는 중' 표시를 남긴다", crashlog._mark_path().exists())
ok("기록 파일에 시작 줄", crashlog.START_TAG in log())

print("\n[2] 정상 종료 → 다음에 켜도 묻지 않는다")
crashlog.clean_exit()
ok("정상 종료면 표시를 지운다", not crashlog._mark_path().exists())
ok("다음에 켜도 알리지 않는다", restart() == "")

print("\n[3] 그냥 꺼짐(윈도를 끔·작업관리자) + 기록 없음 → 묻지 않는다")
ok("기록이 없으면 알리지 않는다", restart() == "")

print("\n[4] 파이썬 오류가 기록되고, 비정상으로 끝나면 다음에 알린다")
try:
    raise ValueError("자료검색 시험 오류")
except ValueError:
    crashlog._excepthook(*_sys.exc_info())
ok("잡히지 않은 오류를 적는다", "자료검색 시험 오류" in log() and "파이썬 오류" in log())


def boom():
    raise RuntimeError("일꾼 스레드 오류")


th = threading.Thread(target=boom, name="받기")
th.start()
th.join()
ok("일꾼 스레드 오류도 적는다", "일꾼 스레드 오류" in log() and "받기" in log())
prev = restart()                               # clean_exit 없이 다시 켬 = 비정상 종료
ok("다음에 켜면 지난번 기록을 돌려준다(알림)", "자료검색 시험 오류" in prev, prev[:80])
ok("판 번호가 적혀 있다", f"v{config.APP_VERSION}" in prev)
ok("그 전 판의 기록은 섞이지 않는다", restart() == "" or "자료검색 시험 오류" not in restart())

print("\n[5] 멈춤 감시 — 화면 스레드가 응답하지 않으면 그때 상황을 적는다")
crashlog.clean_exit()
restart()
crashlog.start_watchdog(app=None, freeze_sec=0.4, every=0.1)   # 박동을 안 보내 '멈춘' 화면


def stuck():
    time.sleep(1.2)                # 이 스레드가 화면이라 치자 — 1.2초 막혀 있다


stuck()
crashlog._watch_stop.set()
txt = log()
ok("멈췄다고 적는다", "멈춤" in txt and "응답 없음" in txt, txt[-200:])
ok("그때 각 스레드가 하던 일을 적는다(코드 위치)",
   "File" in txt and "stuck" in txt, txt[-300:])
ok("한 번 멈춤에 한 번만", txt.count("응답 없음") == 1, txt.count("응답 없음"))
prev = restart()
ok("멈춘 채 꺼졌으면 다음에 알린다", "멈춤" in prev)

print("\n[6] 파일이 너무 커지면 앞을 자른다")
crashlog.clean_exit()
with open(crashlog.log_path(), "a", encoding="utf-8") as f:
    f.write("x" * (crashlog.MAX_BYTES + 10))
restart()
ok("1MB 를 넘지 않게", crashlog.log_path().stat().st_size < crashlog.MAX_BYTES,
   crashlog.log_path().stat().st_size)

print("\n[7] 알림 문구")
t = crashlog.notice_text()
ok("무슨 일이었는지 · 무엇을 하면 되는지 · 파일 위치", "비정상" in t and "기록 복사" in t
   and str(crashlog.log_path()) in t)
crashlog.clean_exit()

print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
