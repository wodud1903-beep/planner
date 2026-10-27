# 업무자료검색(kbsearch/) 작업 규칙

지점장이 정한 것(2026-10-27): **업무자료검색을 고치면 따로 말하지 않아도 릴리스해서
모든 PC 가 자동 업데이트로 받게 한다.**

## 고칠 때마다
1. `kbsearch/kbsearch/config.py` 의 `APP_VERSION` 을 올린다(고침 = 끝자리, 기능 = 가운데).
2. `kbsearch/CHANGELOG.md` 맨 위에 `## vX.Y.Z — 제목 (날짜)` 절을 적는다. 다섯 줄 안쪽, 직원이 읽을 말로.
3. `cd kbsearch && python verify/run_all.py` 가 모두 통과하는지 본다.
4. push 한다 → `build-kbsearch.yml` 이 검사·빌드 후 `kb-vX.Y.Z` 릴리스를 **저절로** 만든다
   (`release_plan.py` — 아직 안 나간 높은 판일 때만). 따로 태그를 밀지 않는다.
5. 끝나면 릴리스가 생겼는지, `releases/latest` 가 여전히 일정관리기 판(v…)인지 확인한다.

판 번호를 안 올리면 빌드만 되고 아무 PC 에도 가지 않는다. CHANGELOG 절이 없으면 빌드가 멈춘다.

## 지킬 것
- 일정관리기(`python/`, `build-exe.yml`, 루트 CHANGELOG.md)는 건드리지 않는다.
- 일정관리기의 자료검색 공용 부분(`kb_attach` · `livesearch` · `kb_tab` 의 KbView · `hangul` 등)이
  고쳐지면 `kbsearch/kbsearch/` 의 사본에도 옮긴다(README 의 '그대로 복사' 목록).
- 업데이트는 건너뛸 수 없다 — 잘못 나간 판은 모든 PC 에 깔린다. 검사가 빨가면 내지 않는다.
- 릴리스는 `make_latest: false` 를 지킨다(일정관리기 업데이트가 latest 를 본다).
