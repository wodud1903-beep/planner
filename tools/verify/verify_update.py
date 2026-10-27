"""자동 업데이트 교체 배치 — 끝내 실패해도 프로그램이 사라지지 않는지.

예전 버그: 복사가 실패하면 원본을 .old 로 비켜 두는데, 다음 바퀴 첫 줄이 .old 를
지웠다. 60번 다 실패하면(백신이 새 파일을 잡고 있을 때 등) 새 판도 옛 판도 없었다.

윈도가 없어도 확인할 수 있게 **배치를 한 줄씩 흉내 내는 작은 해석기**로 돌린다.
배치에 쓰는 명령(set·if·goto·del·copy·ren·explorer·tasklist)만 안다.
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))

import re

from planner import updater  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name
          + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


DIR = r"C:\Users\me\AppData\Local\일정관리기"
DST = DIR + r"\일정관리기.exe"
SRC = DIR + r"\_update_일정관리기.exe"
OLD = DST + ".old"


class Box:
    """가짜 파일들 + 실패 주입."""

    def __init__(self, files, copy_fails=0, locked_dst=False, alive=None):
        self.files = dict(files)          # 경로 → 내용
        self.copy_fails = copy_fails      # 처음 몇 번의 copy 를 무조건 실패시킬지
        self.locked_dst = locked_dst      # 대상이 잠겨 덮어쓰기는 안 되고 이름 변경은 됨
        self.alive = dict(alive or {})    # pid → 몇 번 더 '아직 살아 있음' 으로 보일지
        self.killed = []
        self.launched = []

    def copy(self, a, b):
        if self.copy_fails > 0:
            self.copy_fails -= 1
            return 1
        if a not in self.files:
            return 1
        if self.locked_dst and b == DST and DST in self.files:
            return 1
        self.files[b] = self.files[a]
        return 0


def run(script: str, box: Box, max_steps=20000):
    lines = [ln.strip() for ln in script.splitlines()]
    labels = {ln[1:]: i for i, ln in enumerate(lines) if ln.startswith(":")}
    env = {}
    errorlevel = 0
    i = steps = 0

    def sub(t):
        t = re.sub(r"%(\w+)%", lambda m: env.get(m.group(1), ""), t)
        t = re.sub(r"!(\w+)!", lambda m: str(env.get(m.group(1), "")), t)
        return t

    def q(s):
        return re.findall(r'"([^"]*)"', s)

    def do(cmd):
        nonlocal errorlevel, i
        cmd = cmd.strip()
        low = cmd.lower()
        m = re.match(r'echo (.*?)\s*(>>?)\s*"([^"]*)"$', cmd, re.I)
        if m:                              # 결과 파일에 적기(기록은 덧붙이기)
            text, op, path = m.group(1).strip(), m.group(2), m.group(3)
            box.files[path] = (box.files.get(path, "") + text + "\n") if op == ">>" \
                else text + "\n"
            return
        if not cmd or low.startswith(("rem", "@echo", "echo", "setlocal", "timeout")):
            return
        if low.startswith("set /a "):
            m = re.match(r"set /a (\w+)(\+?=)(\d+)", cmd, re.I)
            k, op, v = m.group(1), m.group(2), int(m.group(3))
            env[k] = (int(env.get(k, 0)) + v) if op == "+=" else v
            return
        if low.startswith('set "'):
            k, v = cmd[5:-1].split("=", 1)
            env[k] = v
            return
        if low.startswith("tasklist"):
            pid = int(re.search(r"PID eq (\d+)", cmd).group(1))
            left = box.alive.get(pid, 0)
            if left > 0 and pid not in box.killed:
                box.alive[pid] = left - 1
                errorlevel = 0             # 아직 살아 있다
            else:
                errorlevel = 1             # 끝났다
            return
        if low.startswith("taskkill"):
            box.killed.append(int(re.search(r"/PID (\d+)", cmd).group(1)))
            return
        m = re.match(r'if (not )?"([^"]*)"=="([^"]*)" (.*)$', cmd, re.I)
        if m:
            if (m.group(2) == m.group(3)) != bool(m.group(1)):
                do(m.group(4))
            return
        if low.startswith("goto "):
            i = labels[cmd.split()[1]]
            return
        if low.startswith("if errorlevel 1 "):
            if errorlevel >= 1:
                do(cmd[len("if errorlevel 1 "):])
            return
        if low.startswith("if not errorlevel 1 "):
            if errorlevel < 1:
                do(cmd[len("if not errorlevel 1 "):])
            return
        m = re.match(r'if (not )?exist "([^"]*)" (.*)$', cmd, re.I)
        if m:
            have = m.group(2) in box.files
            if have != bool(m.group(1)):
                do(m.group(3))
            return
        m = re.match(r"if (\S+) gtr (\d+) (.*)$", cmd, re.I)
        if m:
            if int(m.group(1)) > int(m.group(2)):
                do(m.group(3))
            return
        if low.startswith("del "):
            p = q(cmd)[0]
            box.files.pop(p, None)
            return
        if low.startswith("copy "):
            a, b = q(cmd)[:2]
            errorlevel = box.copy(a, b)
            return
        if low.startswith("ren "):
            a, newname = q(cmd)[:2]
            b = a.rsplit("\\", 1)[0] + "\\" + newname
            if a in box.files and b not in box.files:
                box.files[b] = box.files.pop(a)
                errorlevel = 0
            else:
                errorlevel = 1
            return
        if low.startswith("explorer.exe"):
            p = q(cmd)[0]
            box.launched.append(box.files.get(p))
            return
        raise AssertionError("모르는 명령: " + cmd)

    while i < len(lines):
        steps += 1
        if steps > max_steps:
            raise AssertionError("끝나지 않는다")
        ln = lines[i]
        i += 1
        if ln.startswith(":"):
            continue
        do(sub(ln).replace("%~f0", "self.bat"))
    return box


STATUS = r"C:\status.txt"
SCRIPT = updater.update_script(SRC, DST, OLD, r"C:\log.txt", 4242, 0, STATUS)
SCRIPT2 = updater.update_script(SRC, DST, OLD, r"C:\log.txt", 4242, 777, STATUS)   # 부모도

print("[1] 보통 — 바로 교체되고 새 판이 뜬다")
b = run(SCRIPT, Box({DST: "v1", SRC: "v2", OLD: "v0"}))
ok("새 판으로 바뀌었다", b.files.get(DST) == "v2")
ok("새 판이 실행됐다", b.launched == ["v2"], b.launched)
ok("지지난 판(.old)은 정리", OLD not in b.files)

print("\n[2] 대상이 잠겨 있음 — 비켜 두고 교체, 직전 판은 .old 로 남는다")
b = run(SCRIPT, Box({DST: "v1", SRC: "v2"}, locked_dst=True))
ok("새 판으로 바뀌었다", b.files.get(DST) == "v2")
ok("직전 판이 .old 로 남았다(되돌릴 수단)", b.files.get(OLD) == "v1")

print("\n[3] 끝내 복사가 안 됨 — 옛 판을 되살리고 다시 띄운다 (예전엔 둘 다 사라졌다)")
b = run(SCRIPT, Box({DST: "v1", SRC: "v2"}, copy_fails=10**6))
ok("프로그램 파일이 남아 있다", b.files.get(DST) == "v1", b.files)
ok("옛 판을 다시 띄웠다", b.launched == ["v1"], b.launched)

print("\n[4] 잠김 + 끝내 실패 — 비켜 둔 원본도 지우지 않고 되돌린다")
b = run(SCRIPT, Box({DST: "v1", SRC: "v2"}, copy_fails=10**6, locked_dst=True))
ok("프로그램 파일이 남아 있다", b.files.get(DST) == "v1", b.files)

print("\n[5] 지난번 교체가 도중에 멈춰 원본이 .old 로만 남아 있음")
b = run(SCRIPT, Box({OLD: "v1", SRC: "v2"}, copy_fails=10**6))
ok("되돌려서 프로그램 파일이 있다", b.files.get(DST) == "v1", b.files)
b = run(SCRIPT, Box({OLD: "v1", SRC: "v2"}))
ok("교체가 되면 새 판", b.files.get(DST) == "v2")

print("\n[6] 결과를 남긴다 — 다음에 켤 때 알려 줄 수 있게")
b = run(SCRIPT, Box({DST: "v1", SRC: "v2"}))
ok("잘 되면 ok", b.files.get(STATUS, "").strip() == "ok", b.files.get(STATUS))
b = run(SCRIPT, Box({DST: "v1", SRC: "v2"}, copy_fails=10**6))
ok("끝내 못 바꾸면 fail locked", b.files.get(STATUS, "").strip() == "fail locked")

print("\n[7] 새 파일이 사라짐(백신이 지운 경우) — 60초 기다리지 않고 바로 옛 판으로")
b = run(SCRIPT, Box({DST: "v1"}), max_steps=400)
ok("옛 판 그대로·다시 띄움", b.files.get(DST) == "v1" and b.launched == ["v1"], (b.files, b.launched))
ok("fail missing 을 남긴다", b.files.get(STATUS, "").strip() == "fail missing")

print("\n[8] 옛 판이 늦게 끝남 — 자식·부모(한 파일 exe) 둘 다 기다린다")
b = run(SCRIPT2, Box({DST: "v1", SRC: "v2"}, alive={4242: 3, 777: 5}))
ok("기다렸다가 교체", b.files.get(DST) == "v2" and b.launched == ["v2"])
ok("제때 끝났으면 억지로 끝내지 않는다", b.killed == [], b.killed)
ok("부모가 없는 실행(PPID=0)이면 부모는 안 본다",
   run(SCRIPT, Box({DST: "v1", SRC: "v2"}, alive={777: 10**6})).killed == [])

print("\n[9] 30초가 지나도 안 끝남(v1.22.1 에서 겪은 일) — 끝내고 교체한다")
b = run(SCRIPT2, Box({DST: "v1", SRC: "v2"}, alive={4242: 10**6}))
ok("옛 판을 끝낸다", 4242 in b.killed, b.killed)
ok("부모까지 끝낸다", 777 in b.killed, b.killed)
ok("그리고 새 판으로", b.files.get(DST) == "v2" and b.launched == ["v2"], b.launched)
b = run(SCRIPT2, Box({DST: "v1", SRC: "v2"}, alive={777: 10**6}))
ok("부모만 남아도 끝내고 교체", 777 in b.killed and b.files.get(DST) == "v2")

print("\n[10] 켤 때 쓰는 도우미 — 결과 읽기 · 자동 횟수 · 방금 깔렸나")
import json as _json  # noqa: E402
import os as _os2  # noqa: E402
import tempfile as _tf  # noqa: E402
_os2.environ["APPDATA"] = _tf.mkdtemp()
from planner import config as _cfg  # noqa: E402
ok("결과 없음", updater.last_failure() == "")
(_cfg.base_dir() / "update_status.txt").write_text("fail missing\r\n", encoding="utf-8")
ok("fail missing 을 읽는다", updater.last_failure() == "missing")
ok("안내문에 이유와 할 일", "백신" in updater.failure_text("missing")
   and "받는 곳" in updater.failure_text("missing"))
updater.ack_failure()
ok("한 번 알리면 지운다", updater.last_failure() == "")
(_cfg.base_dir() / "update_status.txt").write_text("ok\r\n", encoding="utf-8")
ok("ok 는 실패가 아니다", updater.last_failure() == "")
ok("처음엔 0번", updater.attempts("v9.0.0") == 0)
updater.note_attempt("v9.0.0")
updater.note_attempt("v9.0.0")
ok("같은 판은 센다", updater.attempts("v9.0.0") == 2)
ok("다른 판은 0", updater.attempts("v9.0.1") == 0)
updater.clear_attempt_if_done("1.0.0")
ok("아직 그 판이 아니면 남긴다", updater.attempts("v9.0.0") == 2)
updater.clear_attempt_if_done("9.0.0")
ok("그 판이 되면 지운다", updater.attempts("v9.0.0") == 0)
ok("업데이트 기록이 없으면 방금 깔린 게 아니다", not updater.just_installed())
(_cfg.base_dir() / "update_log.txt").write_text("[update] start\n[update] replaced ok\n",
                                                encoding="utf-8")
ok("막 'replaced ok' 면 방금 깔렸다", updater.just_installed())
_old = _cfg.base_dir() / "update_log.txt"
_os2.utime(_old, (1, 1))
ok("오래된 기록이면 아니다", not updater.just_installed())
import subprocess as _sp  # noqa: E402
_real_run = _sp.run


class _R:
    stdout = ('"일정관리기.exe","1200","Console","1","90,000 K"\r\n'
              '"일정관리기.exe","1300","Console","1","12,000 K"\r\n')


_sp.run = lambda *a, **k: _R()
ok("tasklist 결과를 읽는다", updater._tasklist("IMAGENAME eq x") ==
   [("일정관리기.exe", 1200), ("일정관리기.exe", 1300)], updater._tasklist("x"))
_sp.run = _real_run
ok("자동 업데이트는 같은 판 두 번까지", updater.AUTO_MAX_TRIES == 2)

print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
