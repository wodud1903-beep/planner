#!/usr/bin/env python3
"""CHANGELOG.md 에서 그 버전 절만 잘라 낸다 — 릴리스 본문으로 쓴다.

  python tools/extract_release_notes.py v1.11.0 > RELEASE_NOTES.md

절이 없으면 **0 이 아닌 값으로 끝난다.** 그래야 변경 이력에 안 적힌 버전이 몰래
배포되는 일이 없다(릴리스 본문이 비어 있던 게 애초의 문제였다).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def extract(tag: str) -> str:
    ver = tag.strip().lstrip("v")
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    # '## v1.11.0' 로 시작하는 줄부터 다음 '## ' 줄 앞까지
    pat = re.compile(r"^## v" + re.escape(ver) + r"(?:\s|\().*?$(.*?)(?=^## |\Z)",
                     re.M | re.S)
    m = pat.search(text)
    if not m:
        return ""
    return m.group(1).strip("\n")


def main() -> int:
    if len(sys.argv) != 2:
        print("쓰는 법: extract_release_notes.py <태그>", file=sys.stderr)
        return 2
    tag = sys.argv[1]
    body = extract(tag)
    if not body:
        print(f"CHANGELOG.md 에 {tag} 절이 없습니다. "
              f"tools/release.py --from-head 로 먼저 넣어 주세요.", file=sys.stderr)
        return 1
    sys.stdout.write(body + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
