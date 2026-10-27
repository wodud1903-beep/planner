#!/usr/bin/env python3
"""push 때 **저절로 릴리스할지** 정한다 — 새 판 번호면 그 태그를, 아니면 빈 글자를 낸다.

    git ls-remote --tags origin 'kb-v*' | python kbsearch/release_plan.py

규칙
  · config.py 의 APP_VERSION 으로 태그(kb-vX.Y.Z)를 만든다.
  · 그 태그가 이미 있으면 내지 않는다(같은 판을 두 번 내지 않는다 — 빌드만 한다).
  · 이미 나간 kb-v 중 가장 높은 판보다 낮거나 같으면 내지 않는다
    (옛 갈래에서 밀어도 낮은 판이 나가지 않게. 어차피 PC 들은 높은 판만 받는다).
  · 낼 판인데 CHANGELOG.md 에 그 절이 없으면 **실패**한다 — 무엇이 달라졌는지 안 적힌
    판이 모든 PC 에 깔리지 않게(업데이트 창이 그 절을 보여 준다).

그래서 '릴리스한다' = APP_VERSION 을 올리고 CHANGELOG 절을 적어 push 하는 것이다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREFIX = "kb-v"


def parse(v: str) -> tuple:
    v = v.strip()
    if v.lower().startswith(PREFIX):
        v = v[len(PREFIX):]
    v = v.lstrip("vV")
    parts = []
    for x in v.split("."):
        n = "".join(ch for ch in x if ch.isdigit())
        parts.append(int(n) if n else 0)
    return tuple((parts + [0, 0, 0])[:3])


def app_version() -> str:
    text = (HERE / "kbsearch" / "config.py").read_text(encoding="utf-8")
    m = re.search(r'^APP_VERSION = "([^"]+)"', text, re.M)
    return m.group(1) if m else ""


def tags_from_ls_remote(text: str) -> list:
    """`git ls-remote --tags` 출력 → 태그 이름들 (주석 태그의 ^{} 줄은 합친다)."""
    out = []
    for line in (text or "").splitlines():
        ref = line.split("\t")[-1].strip()
        if not ref.startswith("refs/tags/"):
            continue
        name = ref[len("refs/tags/"):]
        if name.endswith("^{}"):
            name = name[:-3]
        if name not in out:
            out.append(name)
    return out


def plan(version: str, tags: list) -> str:
    """낼 태그(kb-vX.Y.Z) 또는 ""."""
    if not re.fullmatch(r"\d+\.\d+\.\d+", version or ""):
        return ""
    tag = PREFIX + version
    kb = [t for t in tags if t.lower().startswith(PREFIX)]
    if tag in kb:
        return ""
    if kb and parse(version) <= max(parse(t) for t in kb):
        return ""
    return tag


def main() -> int:
    ver = app_version()
    tag = plan(ver, tags_from_ls_remote(sys.stdin.read()))
    if tag:
        sys.path.insert(0, str(HERE))
        from release_notes import extract
        if not extract(tag):
            print(f"APP_VERSION 을 {ver} 로 올렸는데 kbsearch/CHANGELOG.md 에 '## v{ver}' 절이 없습니다.\n"
                  "무엇이 달라졌는지 적은 뒤 다시 push 하세요(그 절이 업데이트 창에 보입니다).",
                  file=sys.stderr)
            return 1
    print(tag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
