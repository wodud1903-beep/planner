#!/usr/bin/env python3
"""PC 앱 검사를 전부 돌린다.

    python tools/verify/run_all.py            전부
    python tools/verify/run_all.py drive files  이름에 그 말이 든 것만

⚠️ 화면이 필요한 검사가 있다(Qt 창을 실제로 띄워 본다). 화면 없는 곳에서는
   먼저 가상 화면을 띄워야 한다:

    Xvfb :99 -screen 0 1920x1200x24 -nolisten tcp &
    DISPLAY=:99 openbox &
    DISPLAY=:99 python tools/verify/run_all.py

하나라도 실패하면 0 이 아닌 값으로 끝난다.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main() -> int:
    want = [a.lower() for a in sys.argv[1:]]
    files = sorted(p for p in HERE.glob("verify_*.py"))
    if want:
        files = [p for p in files if any(w in p.stem.lower() for w in want)]
    if not files:
        print("돌릴 검사가 없습니다.", file=sys.stderr)
        return 2

    bad, t0 = [], time.time()
    for p in files:
        started = time.time()
        r = subprocess.run([sys.executable, str(p)], capture_output=True, text=True,
                           timeout=600)
        out = (r.stdout or "") + (r.returncode and (r.stderr or "") or "")
        fails = out.count("** FAIL")
        mark = "OK  " if (r.returncode == 0 and fails == 0) else "** 실패 **"
        print(f"  {mark}  {p.stem:<20} {time.time() - started:5.1f}초"
              + (f"  ({fails}건 어긋남)" if fails else ""))
        if r.returncode != 0 or fails:
            bad.append(p.stem)
            # 실패한 것만 자세히 — 다 찍으면 진짜 원인이 묻힌다
            for ln in out.splitlines():
                if "** FAIL" in ln or "Error" in ln or "Traceback" in ln:
                    print("        " + ln.strip()[:140])

    print(f"\n{len(files)}개 중 {len(files) - len(bad)}개 통과"
          f" ({time.time() - t0:.0f}초)")
    if bad:
        print("실패: " + " ".join(bad), file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
