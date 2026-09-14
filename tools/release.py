#!/usr/bin/env python3
"""릴리스 도구 — 커밋 메시지를 CHANGELOG.md 로 옮기고 버전을 올린다.

왜 이게 있나
------------
이 저장소는 커밋 메시지를 한국어로 꼼꼼히 적어 왔다(제목에 버전, 본문은 ■ 절).
그게 사실상 변경 이력인데 정작 CHANGELOG 도 릴리스 본문도 비어 있었다. 그래서
**같은 내용을 두 번 적지 않고** 커밋 메시지를 한 곳(CHANGELOG.md)으로 모은다.

쓰는 법
-------
  python tools/release.py --backfill        지난 태그 전부로 CHANGELOG.md 를 만든다(한 번)
  python tools/release.py --from-head       방금 커밋을 CHANGELOG 에 올리고 버전·태그까지
  python tools/release.py --check           CHANGELOG 와 태그·APP_VERSION 이 맞는지만 본다

--from-head 는 마지막 커밋을 고쳐 쓴다(--amend). 이미 밀어 둔 커밋이면 **거절**한다 —
밀린 역사를 고치면 남이 받은 것과 어긋난다.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"
CONFIG = ROOT / "python" / "planner" / "config.py"

HEAD_NOTE = """# 변경 이력

버전마다 무엇이 달라졌는지 적어 둔 곳입니다. PC 앱의 [변경 이력] 과 모바일 웹앱이
이 파일 하나를 읽어 보여 줍니다.

"""

# 제목에서 버전을 찾는다. 두 가지 모양을 다 받는다.
#   "제목 v1.4.3"   (요즘 쓰는 모양)
#   "v1.1.1: 제목"  (예전 모양)
_VER_TAIL = re.compile(r"\s*v(\d+\.\d+\.\d+)\s*$")
_VER_HEAD = re.compile(r"^\s*v(\d+\.\d+\.\d+)\s*[:：]?\s*")


def sh(*args: str) -> str:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout.rstrip("\n")


def parse_subject(subject: str) -> tuple[str, str]:
    """커밋 제목 → (버전, 버전을 뗀 제목). 버전이 없으면 ("", 원래제목)."""
    m = _VER_TAIL.search(subject)
    if m:
        return m.group(1), _VER_TAIL.sub("", subject).strip(" ·-—")
    m = _VER_HEAD.match(subject)
    if m:
        return m.group(1), _VER_HEAD.sub("", subject).strip(" ·-—")
    return "", subject.strip()


def clean_body(body: str) -> str:
    """커밋 본문에서 변경 이력에 안 맞는 꼬리를 떼어 낸다."""
    out = []
    for line in (body or "").splitlines():
        s = line.strip()
        # 공동작업자·세션 링크는 변경 이력에 둘 것이 아니다
        if s.startswith(("Co-Authored-By:", "Claude-Session:", "Co-authored-by:")):
            continue
        if s.startswith("🤖 Generated with"):
            continue
        out.append(line.rstrip())
    while out and not out[-1].strip():
        out.pop()
    while out and not out[0].strip():
        out.pop(0)
    return "\n".join(out)


def section(version: str, title: str, when: str, body: str) -> str:
    """CHANGELOG 한 절. 제목 줄은 '## v1.11.0 — 제목 (2026-09-13)'."""
    head = f"## v{version}"
    if title:
        head += f" — {title}"
    head += f" ({when})"
    body = clean_body(body)
    return head + "\n\n" + (body + "\n" if body else "")


def tag_sections() -> list[tuple[str, str]]:
    """태그마다 (버전, 절 글자) — 새 것부터.

    태그가 가리키는 커밋의 메시지를 그대로 쓴다. 버전이 제목에 없으면 태그 이름을 쓴다.
    """
    tags = sh("git", "tag", "--sort=v:refname").splitlines()
    out = []
    for tag in tags:
        ver = tag.lstrip("v")
        try:
            subject = sh("git", "log", "-1", "--format=%s", tag)
            body = sh("git", "log", "-1", "--format=%b", tag)
            when = sh("git", "log", "-1", "--format=%cs", tag)
        except subprocess.CalledProcessError:
            continue
        found, title = parse_subject(subject)
        # 제목의 버전과 태그가 다르면 태그를 믿는다(태그가 실제 배포된 것이다)
        if found and found != ver:
            title = subject.strip()
        out.append((ver, section(ver, title, when, body)))
    out.reverse()
    return out


def read_versions() -> list[str]:
    """CHANGELOG 에 적혀 있는 버전들 — 적힌 순서대로."""
    if not CHANGELOG.exists():
        return []
    return re.findall(r"^## v(\d+\.\d+\.\d+)", CHANGELOG.read_text(encoding="utf-8"),
                      re.M)


def app_version() -> str:
    m = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', CONFIG.read_text(encoding="utf-8"),
                  re.M)
    return m.group(1) if m else ""


def set_app_version(ver: str) -> None:
    txt = CONFIG.read_text(encoding="utf-8")
    new = re.sub(r'^APP_VERSION\s*=\s*"[^"]+"', f'APP_VERSION = "{ver}"', txt,
                 count=1, flags=re.M)
    if new == txt:
        raise SystemExit("APP_VERSION 을 못 찾았습니다: " + str(CONFIG))
    CONFIG.write_text(new, encoding="utf-8")


def cmd_backfill() -> int:
    secs = tag_sections()
    CHANGELOG.write_text(HEAD_NOTE + "\n".join(s for _v, s in secs) + "\n",
                         encoding="utf-8")
    print(f"CHANGELOG.md 를 만들었습니다 — {len(secs)}개 버전 "
          f"(최신 v{secs[0][0]} … 최초 v{secs[-1][0]})")
    return 0


def cmd_from_head() -> int:
    subject = sh("git", "log", "-1", "--format=%s")
    body = sh("git", "log", "-1", "--format=%b")
    ver, title = parse_subject(subject)
    if not ver:
        print("마지막 커밋 제목에 버전(v1.2.3)이 없습니다:\n  " + subject,
              file=sys.stderr)
        return 2
    # 이미 밀어 둔 커밋은 고쳐 쓰지 않는다
    head = sh("git", "rev-parse", "HEAD")
    try:
        remote = sh("git", "rev-parse", "origin/main")
        if head == remote:
            print("마지막 커밋이 이미 origin/main 에 올라가 있습니다.\n"
                  "밀린 역사는 고쳐 쓰지 않습니다 — 새 커밋으로 만들어 주세요.",
                  file=sys.stderr)
            return 3
    except subprocess.CalledProcessError:
        pass
    if ver in read_versions():
        print(f"v{ver} 은 이미 CHANGELOG 에 있습니다.", file=sys.stderr)
        return 4
    when = sh("git", "log", "-1", "--format=%cs")
    new_sec = section(ver, title, when, body)
    old = CHANGELOG.read_text(encoding="utf-8") if CHANGELOG.exists() else HEAD_NOTE
    if old.startswith(HEAD_NOTE):
        rest = old[len(HEAD_NOTE):]
    else:
        rest = old
    CHANGELOG.write_text(HEAD_NOTE + new_sec + "\n" + rest.lstrip("\n"),
                         encoding="utf-8")
    set_app_version(ver)
    sh("git", "add", str(CHANGELOG.relative_to(ROOT)),
       str(CONFIG.relative_to(ROOT)))
    sh("git", "commit", "--amend", "--no-edit")
    sh("git", "tag", "-f", f"v{ver}")
    print(f"v{ver} — CHANGELOG 에 넣고 APP_VERSION 을 올리고 태그를 달았습니다.\n"
          f"이제 미시면 됩니다:  git push origin main --tags")
    return 0


def cmd_check() -> int:
    bad = []
    have = set(read_versions())
    for tag in sh("git", "tag").splitlines():
        if tag.lstrip("v") not in have:
            bad.append(tag)
    if bad:
        print("CHANGELOG 에 절이 없는 태그: " + " ".join(sorted(bad)), file=sys.stderr)
    newest = read_versions()[:1]
    av = app_version()
    if newest and newest[0] != av:
        print(f"APP_VERSION({av}) 과 CHANGELOG 최신 절(v{newest[0]}) 이 다릅니다.",
              file=sys.stderr)
        bad.append("APP_VERSION")
    if not bad:
        print(f"좋습니다 — 태그 {len(have)}개 모두 절이 있고 APP_VERSION({av}) 도 맞습니다.")
    return 1 if bad else 0


def main() -> int:
    p = argparse.ArgumentParser(description="릴리스 도구")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--backfill", action="store_true",
                   help="지난 태그 전부로 CHANGELOG.md 를 다시 만든다")
    g.add_argument("--from-head", action="store_true",
                   help="방금 커밋을 CHANGELOG 에 올리고 버전·태그까지 한다")
    g.add_argument("--check", action="store_true",
                   help="CHANGELOG 와 태그·APP_VERSION 이 맞는지 본다")
    a = p.parse_args()
    if a.backfill:
        return cmd_backfill()
    if a.from_head:
        return cmd_from_head()
    return cmd_check()


if __name__ == "__main__":
    sys.exit(main())
