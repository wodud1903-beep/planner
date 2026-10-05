#!/usr/bin/env bash
# 폰 웹앱(web/)을 올릴 수 있는 폴더로 만든다.
#
#   bash tools/build_web.sh <출력폴더> <빌드번호(커밋 sha)>
#
# GitHub Pages(pages.yml)와 Vercel(vercel.json)이 **같은 이 스크립트**를 쓴다.
# 따로 두면 한쪽만 고쳐져 두 주소의 앱이 어긋난다.
set -euo pipefail

OUT="${1:?출력 폴더를 주세요}"
SHA="${2:-}"
cd "$(dirname "$0")/.."

# 커밋 sha 를 빌드 번호로 쓴다. 서비스워커 캐시 이름이 여기서 갈리므로
# 한 커밋 = 한 세대가 되고, 세대가 섞일 수 없다.
test -n "$SHA"                          # 빌드 번호 없이 올리면 캐시가 안 갈린다
BUILD="${SHA::12}"
VER=$(sed -n 's/^APP_VERSION = "\(.*\)"$/\1/p' python/planner/config.py)
echo "빌드=$BUILD 버전=$VER"
test -n "$VER"                          # config.py 에서 못 읽으면 여기서 멈춘다

rm -rf "$OUT"
mkdir -p "$OUT"
cp -R web/. "$OUT/"
cp CHANGELOG.md "$OUT/CHANGELOG.md"     # 앱의 [정보] 화면이 읽는다
rm -rf "$OUT/verify"                    # 검사용 파일은 빼고 올린다

grep -rl '__BUILD_ID__\|__APP_VERSION__' "$OUT" \
  | xargs -r sed -i "s/__BUILD_ID__/$BUILD/g; s/__APP_VERSION__/$VER/g"
# 치환이 남았으면 배포하지 않는다 — 캐시 이름이 리터럴로 굳으면
# 다음 배포에서 새 판으로 갈아타지 못한다.
if grep -rq '__BUILD_ID__\|__APP_VERSION__' "$OUT"; then
  echo "치환이 남았다 — 배포하지 않는다" >&2
  exit 1
fi
