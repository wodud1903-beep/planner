#!/usr/bin/env python3
"""업무자료검색 검사를 전부 돌린다.

    python verify/run_all.py          (kbsearch/ 에서)

화면이 없는 곳에서는 QT_QPA_PLATFORM=offscreen 으로 돈다(각 검사가 알아서 정한다).
[sync]·[update] 검사는 일정관리기 코드(python/planner)도 불러 서로 맞는지 견준다.
하나라도 실패하면 0 이 아닌 값으로 끝난다.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    bad, t0 = [], time.time()
    files = sorted(HERE.glob("verify_*.py"))
    for p in files:
        started = time.time()
        r = subprocess.run([sys.executable, str(p)], capture_output=True, text=True, timeout=300)
        out = (r.stdout or "") + (r.stderr or "")
        fails = out.count("** FAIL")
        good = r.returncode == 0 and fails == 0
        print(f"  {'OK  ' if good else '** 실패 **'}  {p.stem:<16} {time.time() - started:5.1f}초"
              + (f"  ({fails}건 어긋남)" if fails else ""))
        if not good:
            bad.append(p.stem)
            for ln in out.splitlines():
                if "** FAIL" in ln or "Error" in ln or "Traceback" in ln:
                    print("        " + ln.strip()[:140])
    print(f"\n{len(files)}개 중 {len(files) - len(bad)}개 통과 ({time.time() - t0:.0f}초)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
