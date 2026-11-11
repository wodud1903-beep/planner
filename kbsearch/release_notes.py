#!/usr/bin/env python3
"""kbsearch/CHANGELOG.md 에서 그 판의 절만 잘라 릴리스 본문으로 쓴다.

    python kbsearch/release_notes.py kb-v1.0.0 RELEASE_NOTES.md

절이 없으면 0 이 아닌 값으로 끝난다 — 변경 이력에 안 적힌 판이 몰래 배포되지 않게.
파일로 쓸 때는 UTF-8 로 직접 쓴다(윈도 화면 출력은 cp1252 라 한글에서 죽는다).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREFIX = "kb-v"


def version_of(tag: str) -> str:
    t = tag.strip()
    if t.lower().startswith(PREFIX):
        t = t[len(PREFIX):]
    return t.lstrip("vV")


def extract(tag: str) -> str:
    ver = version_of(tag)
    text = (HERE / "CHANGELOG.md").read_text(encoding="utf-8")
    pat = re.compile(r"^## v" + re.escape(ver) + r"(?:\s|\().*?$(.*?)(?=^## |\Z)", re.M | re.S)
    m = pat.search(text)
    return m.group(1).strip("\n") if m else ""


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print("쓰는 법: release_notes.py <태그> [출력파일]", file=sys.stderr)
        return 2
    body = extract(sys.argv[1])
    if not body:
        print(f"kbsearch/CHANGELOG.md 에 {sys.argv[1]} 절(## v{version_of(sys.argv[1])})이 없습니다.",
              file=sys.stderr)
        return 1
    if len(sys.argv) == 3:
        Path(sys.argv[2]).write_text(body + "\n", encoding="utf-8")
        return 0
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.stdout.write(body + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
