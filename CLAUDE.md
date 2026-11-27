# 일정관리기(planner) 작업 규칙

지점장에게 알리는 말(답장 · 진행 상황 · CHANGELOG · 커밋)은 **한국어로** 쓴다.

## 고칠 때마다(PC 앱 `python/`)
1. `python/planner/config.py` 의 `APP_VERSION` 을 올린다(고침 = 끝자리, 기능 = 가운데).
2. 루트 `CHANGELOG.md` 맨 위에 `## vX.Y.Z — 제목 (날짜)` 절 — 다섯 줄 안쪽, 직원이 읽을 말로.
3. `DISPLAY=:99 QT_QPA_PLATFORM=offscreen python tools/verify/run_all.py` 가 모두 통과해야 낸다.
   웹(`web/`)을 고쳤으면 `web/verify/verify_logic.mjs` · `verify_api.mjs` · `verify_web.mjs` 도.
4. main 에 push → `build-exe.yml` 을 `release_tag` 로 돌려 릴리스(exe) — 웹은 main 에서 저절로 배포된다.

## 카톡 매크로(`kakao_*.py`)
- **고칠 때마다 `kakao_macro.CHANGE_LOG` 맨 위에 한 절을 더한다**(날짜 · 판 · 직원이 읽을 말 다섯 줄 안쪽).
  매크로 화면 도구 → 수정로그에 그대로 보인다(지점장 v1.38 요청: "수정로그는 앞으로 너가 직접 업데이트해서 올려줘").
- `kakao_win.py` · `kakao_macro.py` · `kakao_history.py` · `kakao_macro_view.py` · `members.py` 는 업무자료검색
  (`kbsearch/kbsearch/`)과 **글자 하나 다르지 않은 사본**이다 — 고치면 그쪽에도 옮기고 업무자료검색도 낸다.
- A1Auto 동작(키 순서 · 기다리는 시간 · 로그 줄 · customers.tsv 모양)은 바꾸지 않는다. 바꾼 것은 kakao_macro 맨 위
  'A1Auto 와 다른 것' 에 적는다.

## 지킬 것
- 저장소는 공개 — 토큰 · 비밀번호 · 개인 정보는 넣지 않는다. 검사 자료는 지어낸 것만.
- 수입차 프로모션 시트는 읽기만 한다(쓰기 권한 · 쓰는 코드를 넣지 않는다).
