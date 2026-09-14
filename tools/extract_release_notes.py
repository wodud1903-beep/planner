#!/usr/bin/env python3
"""CHANGELOG.md 에서 그 버전 절만 잘라 낸다 — 릴리스 본문으로 쓴다.

  python tools/extract_release_notes.py v1.11.0 RELEASE_NOTES.md

절이 없으면 **0 이 아닌 값으로 끝난다.** 그래야 변경 이력에 안 적힌 버전이 몰래
배포되는 일이 없다(릴리스 본문이 비어 있던 게 애초의 문제였다).

⚠️ 파일 이름을 주면 **UTF-8 로 직접 쓴다.** 화면으로 내보내고 `>` 로 받게 하면 안 된다 —
   윈도 파이썬은 화면 출력을 cp1252 로 잡아서 '■' 하나에 UnicodeEncodeError 로 죽는다
   (실제로 v1.12.0 릴리스가 이걸로 실패했다). 한국어 본문을 다루니 인코딩을 못 박는다.
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
    if len(sys.argv) not in (2, 3):
        print("쓰는 법: extract_release_notes.py <태그> [출력파일]", file=sys.stderr)
        return 2
    tag = sys.argv[1]
    body = extract(tag)
    if not body:
        print(f"CHANGELOG.md 에 {tag} 절이 없습니다. "
              f"tools/release.py --from-head 로 먼저 넣어 주세요.", file=sys.stderr)
        return 1
    out = body + "\n"
    if len(sys.argv) == 3:
        Path(sys.argv[2]).write_text(out, encoding="utf-8")
        return 0
    # 화면으로 낼 때도 UTF-8 을 못 박는다 (윈도 cp1252 회피)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
