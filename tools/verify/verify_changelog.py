"""변경 이력 — 원본 하나(CHANGELOG.md)가 PC·릴리스·모바일에 제대로 닿는지."""
# ⚠️ 경로를 박아 두지 않는다. 예전에는 이 검사들이 작업용 임시 폴더에만 있고
# "/home/user/planner" 를 글자 그대로 들고 있어서, 컨테이너가 다시 뜨면 통째로
# 사라졌다(실제로 두 번 겪었다). 이제 저장소 안에 살고, 자기 위치에서 뿌리를 찾는다.
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]      # tools/verify/x.py → 저장소 뿌리
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
import os as _os
_os.chdir(_ROOT / "python")                          # 'planner/...' 상대경로를 쓰는 검사용
import os, re, subprocess, sys, tempfile, time

ROOT = str(_ROOT)
os.environ.setdefault("APPDATA", tempfile.mkdtemp())
from PySide6.QtWidgets import QApplication
from planner import changelog, config

fails = []
def ok(name, cond, detail=""):
    print(("  OK  " if cond else "  ** FAIL **  ") + name + ("  " + str(detail) if detail else ""))
    if not cond: fails.append(name)

def sh(*a):
    return subprocess.run(a, cwd=ROOT, capture_output=True, text=True).stdout.strip()

app = QApplication.instance() or QApplication([])
def pump(n=20):
    for _ in range(n): app.processEvents(); time.sleep(0.01)

print("\n[A] 파일과 절")
secs = changelog.sections()
tags = [t.lstrip("v") for t in sh("git", "tag").splitlines()]
ok("CHANGELOG.md 를 찾는다", bool(changelog.text()))
ok("모든 태그에 절이 있다", set(tags) <= {s["version"] for s in secs},
   sorted(set(tags) - {s["version"] for s in secs}) or "빠진 것 없음")
# 버전을 박아 두지 않는다 — 릴리스할 때마다 이 검사가 깨진다(실제로 깨졌다).
# 확인할 것은 '내림차순인가' 이고, 맨 위는 APP_VERSION 과 같아야 한다(아래 항목).
_nums = [tuple(int(x) for x in s["version"].split(".")) for s in secs]
ok("절이 새 것부터 내림차순으로 정렬돼 있다", _nums == sorted(_nums, reverse=True),
   f"{secs[0]['version']} … {secs[-1]['version']} ({len(secs)}개)")
ok("APP_VERSION 과 최신 절이 같다", secs[0]["version"] == config.APP_VERSION,
   f"{config.APP_VERSION} vs {secs[0]['version']}")
ok("대부분의 절에 본문이 있다", sum(1 for s in secs if s["body"].strip()) >= len(secs) * 0.8,
   f"{sum(1 for s in secs if s['body'].strip())}/{len(secs)}")
ok("커밋 꼬리표가 안 섞였다",
   not re.search(r"Co-Authored-By|Claude-Session|Generated with", changelog.text()))
ok("제목 없는 절도 버텨 낸다(v1.8.0)",
   any(s["version"] == "1.8.0" for s in secs))
ok("옛 형식 'v1.1.1: 제목' 도 제목을 뽑았다",
   next(s["title"] for s in secs if s["version"] == "1.1.1").startswith("워크플로우"))

print("\n[B] 릴리스 본문 뽑기")
r = subprocess.run([sys.executable, "tools/extract_release_notes.py", "v1.11.0"],
                   cwd=ROOT, capture_output=True, text=True)
ok("최신 태그 본문이 나온다", r.returncode == 0 and len(r.stdout) > 200, f"{len(r.stdout)}자")
ok("뽑은 본문에 ■ 절이 있다", "■" in r.stdout)
ok("다음 버전 절이 섞여 들지 않았다", "## v" not in r.stdout)
r2 = subprocess.run([sys.executable, "tools/extract_release_notes.py", "v9.9.9"],
                    cwd=ROOT, capture_output=True, text=True)
ok("없는 버전은 실패한다(몰래 배포 방지)", r2.returncode != 0)

# ⚠️ v1.12.0 릴리스가 실제로 이것 때문에 실패했다. 윈도 파이썬은 화면 출력을
# cp1252 로 잡아서 '■' 하나에 UnicodeEncodeError 로 죽는다. 그래서 파일로 직접 쓴다.
env = dict(os.environ, PYTHONIOENCODING="cp1252")
outp = os.path.join(tempfile.mkdtemp(), "RN.md")
r4 = subprocess.run([sys.executable, "tools/extract_release_notes.py", "v1.11.0", outp],
                    cwd=ROOT, capture_output=True, text=True, env=env)
ok("윈도 인코딩(cp1252)에서도 파일로 써진다", r4.returncode == 0,
   (r4.stderr or "").strip()[-80:] or "OK")
ok("그 파일이 UTF-8 한글이다",
   r4.returncode == 0 and "■" in open(outp, encoding="utf-8").read())
wf0 = open(f"{ROOT}/.github/workflows/build-exe.yml", encoding="utf-8").read()
ok("워크플로가 `>` 대신 파일 이름을 넘긴다",
   "RELEASE_NOTES.md" in wf0 and "> RELEASE_NOTES.md" not in wf0)

print("\n[C] 도구")
r3 = subprocess.run([sys.executable, "tools/release.py", "--check"],
                    cwd=ROOT, capture_output=True, text=True)
ok("--check 가 통과한다", r3.returncode == 0, r3.stdout.strip() or r3.stderr.strip())
rel = open(f"{ROOT}/tools/release.py", encoding="utf-8").read()
ok("밀린 커밋은 amend 를 거절한다", "origin/main" in rel and "밀린 역사는 고쳐 쓰지 않습니다" in rel)

print("\n[D] PC 창")
w = changelog.ChangelogWindow(); w.resize(900, 650); w.show(); pump()
ok("목록이 찬다", w.lst.count() == len(secs), w.lst.count())
ok("지금 버전에 표시가 붙는다",
   any("← 지금" in w.lst.item(i).text() for i in range(w.lst.count())))
ok("본문이 ■ 렌더러로 그려진다", "■" in w.txt.toPlainText())
w.lst.setCurrentRow(5); pump()
ok("다른 버전을 눌러도 바뀐다", w.txt.toPlainText().strip().startswith("■ v"))
links = re.findall(r'href="([^"]+)"', w.txt.toHtml())
ok("링크의 & 가 안 깨진다(escape 순서)", not any("&amp;" in l for l in links))
w.close(); pump()

print("\n[E] 배관")
spec = open(f"{ROOT}/python/planner.spec", encoding="utf-8").read()
ok("exe 에 CHANGELOG.md 를 넣는다", "'../CHANGELOG.md'" in spec)
wf = open(f"{ROOT}/.github/workflows/build-exe.yml", encoding="utf-8").read()
ok("릴리스 본문을 CHANGELOG 에서 넣는다", "body_path: RELEASE_NOTES.md" in wf)
ok("CHANGELOG 가 바뀌면 exe 도 다시 빌드한다", "'CHANGELOG.md'" in wf)
# ⚠️ 워크플로를 글자 치환으로 고치다 YAML 을 깨뜨린 적이 있다(들여쓰기가 어긋나
# 'workflow_dispatch 트리거가 없다' 는 엉뚱한 오류로 나타났다). 그래서 파싱까지 본다.
try:
    import yaml
    _d = yaml.safe_load(open(f"{ROOT}/.github/workflows/build-exe.yml", encoding="utf-8"))
    _trig = _d[True] if True in _d else _d.get("on", {})
    ok("워크플로 YAML 이 파싱된다", isinstance(_d, dict))
    ok("트리거 세 개가 그대로 있다",
       {"push", "workflow_dispatch", "release"} <= set(_trig), sorted(_trig))
    _names = [st.get("name", "") for st in _d["jobs"]["build"]["steps"]]
    ok("릴리스 본문 단계가 배포 앞에 있다",
       _names.index("릴리스 본문 준비 (CHANGELOG.md 에서)")
       < _names.index("릴리스 배포 (태그 push / release / 수동입력 태그)"))
except ImportError:
    print("  (건너뜀) pyyaml 이 없어 YAML 파싱 검사는 못 했습니다")

msrc = open(f"{ROOT}/python/planner/main_window.py", encoding="utf-8").read()
ok("트레이에서 열 수 있다", '("변경 이력", self.open_changelog)' in msrc)
ok("상단바 버전을 눌러 열 수 있다", "self.btn_ver" in msrc and "open_changelog" in msrc)
ok("exe 안(_MEIPASS)도 찾아본다", "_MEIPASS" in open(
   f"{ROOT}/python/planner/changelog.py", encoding="utf-8").read())

print("\n" + ("전부 통과" if not fails else f"{len(fails)}건 실패: {fails}"))
sys.exit(1 if fails else 0)
