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

    def __init__(self, files, copy_fails=0, locked_dst=False):
        self.files = dict(files)          # 경로 → 내용
        self.copy_fails = copy_fails      # 처음 몇 번의 copy 를 무조건 실패시킬지
        self.locked_dst = locked_dst      # 대상이 잠겨 덮어쓰기는 안 되고 이름 변경은 됨
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
            errorlevel = 1                 # 옛 프로세스는 이미 끝났다
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


SCRIPT = updater.update_script(SRC, DST, OLD, r"C:\log.txt", 4242)

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

print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
