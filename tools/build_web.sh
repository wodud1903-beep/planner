#!/usr/bin/env bash
# 폰 웹앱(web/)을 올릴 수 있는 폴더로 만든다.
#
#   bash tools/build_web.sh <출력폴더> <빌드번호(커밋 sha)> [pages]
#
# GitHub Pages(pages.yml)와 Vercel(vercel.json)이 **같은 이 스크립트**를 쓴다.
# 따로 두면 한쪽만 고쳐져 두 주소의 앱이 어긋난다.
#
# 세 번째에 pages 를 주면 옛 주소(github.io)용 — 앱 대신 새 주소
# (jyplanner.vercel.app)로 옮겨 주는 화면을 올린다(로그인 서버가 거기에만 있다).
set -euo pipefail

OUT="${1:?출력 폴더를 주세요}"
SHA="${2:-}"
KIND="${3:-}"
NEW_HOME="https://jyplanner.vercel.app/"
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

# 첫 로딩 — 모듈을 한꺼번에 받게 미리 알려 준다(modulepreload).
# 안 알리면 boot.js → 그 import → 또 그 import … 차례로 찾느라 왕복이 여러 번 생긴다.
PRE=""
while IFS= read -r f; do
  PRE+="<link rel=\"modulepreload\" href=\"./${f}\">"
done < <(cd "$OUT" && find js -name '*.js' | sort)
sed -i "s#<!--MODULEPRELOAD-->#${PRE}#" "$OUT/index.html"
grep -q 'rel="modulepreload"' "$OUT/index.html"     # 못 넣었으면 여기서 멈춘다

if [ "$KIND" = "pages" ]; then
  # 옛 주소 — 앱을 띄우지 않고 새 주소로 옮긴다. 보던 화면(#…)은 그대로 들고 간다.
  # 이 주소에 남은 서비스워커·캐시는 지운다(남겨 두면 옛 판이 계속 뜬다).
  # 홈 화면 아이콘으로 열어도 한 번은 이 화면을 거쳐 새 주소로 간다.
  python3 - "$OUT/index.html" "$NEW_HOME" <<'PY'
import re, sys
path, home = sys.argv[1], sys.argv[2]
s = open(path, encoding="utf-8").read()
s = re.sub(r'<link rel="(modulepreload|preconnect)"[^>]*>\n?', "", s)   # 옮기기만 하는 화면이다
move = f"""<script>
(function () {{
  var to = "{home}" + location.hash;
  var go = function () {{ location.replace(to); }};
  var wait = setTimeout(go, 1500);
  var jobs = [];
  try {{
    if (navigator.serviceWorker) jobs.push(navigator.serviceWorker.getRegistrations()
      .then(function (rs) {{ return Promise.all(rs.map(function (r) {{ return r.unregister(); }})); }}));
    if (window.caches) jobs.push(caches.keys()
      .then(function (ks) {{ return Promise.all(ks.map(function (k) {{ return caches.delete(k); }})); }}));
  }} catch (e) {{}}
  Promise.all(jobs).then(function () {{ clearTimeout(wait); go(); }}, go);
}})();
</script>"""
note = f"""<div style="font:16px/1.6 system-ui,sans-serif;padding:48px 20px;text-align:center;color:#252839">
<p style="font-size:18px;font-weight:700;margin:0 0 6px">일정관리기 주소가 바뀌었습니다</p>
<p style="margin:0 0 18px;color:#575d76">잠시 뒤 새 주소로 넘어갑니다.</p>
<p><a href="{home}" style="color:#4434b8;font-weight:700">{home}</a></p>
<p style="color:#575d76;font-size:14px">홈 화면 아이콘은 새 주소에서 다시 추가해 주세요.</p></div>"""
s = s.replace('<meta charset="utf-8">', '<meta charset="utf-8">\n' + move, 1)
s = s.replace('<div id="app"></div>', note, 1)
s = s.replace('<script type="module" src="./js/boot.js"></script>', "", 1)
assert "location.replace" in s and "boot.js\"></script>" not in s
open(path, "w", encoding="utf-8").write(s)
PY
fi

grep -rl '__BUILD_ID__\|__APP_VERSION__' "$OUT" \
  | xargs -r sed -i "s/__BUILD_ID__/$BUILD/g; s/__APP_VERSION__/$VER/g"
# 치환이 남았으면 배포하지 않는다 — 캐시 이름이 리터럴로 굳으면
# 다음 배포에서 새 판으로 갈아타지 못한다.
if grep -rq '__BUILD_ID__\|__APP_VERSION__' "$OUT"; then
  echo "치환이 남았다 — 배포하지 않는다" >&2
  exit 1
fi
