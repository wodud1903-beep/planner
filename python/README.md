# 일정관리기 (Python / PySide6 판)

델파이(PlanManager)로 만든 **일정관리기**를 Python + Qt(PySide6)로 다시 만든 버전입니다.
디자인은 그대로 유지하면서, 직원들이 쓰기 어렵던 **구글 연동을 "한 번 클릭 로그인"으로** 바꿨고,
카카오톡 스케줄러는 제거했습니다.

## ✨ 무엇이 달라졌나

| | 델파이(기존) | Python(이번) |
|---|---|---|
| 구글 캘린더 | ICS 주소를 직접 복사·붙여넣기 | **Google 로그인 → 캘린더 API 실시간** |
| 구글 로그인 | Client ID/Secret 을 직접 입력 | **버튼 한 번** (클라이언트 내장) |
| 구글 할일 | Tasks API (동일) | Tasks API (동일) |
| 카카오톡 스케줄러 | 있음 | **제거** |
| 실행 파일 | 직접 컴파일 필요 | **GitHub Actions 가 .exe 자동 빌드** |

기능(이번주 일정, 내 할일, PC 요일 알람, 최상단 알람 팝업, 트레이 상주,
오늘 브리핑, 자동 백업, PC 시작 시 실행)은 그대로입니다.

## 🖥️ 화면

- 상단 다크 바 + **일정 / 할일**, **PC 알람** 두 개 탭
- 오늘은 주황, 내일은 노랑으로 강조
- 알람은 화면 최상단 중앙에 팝업(항상 위, 포커스 안 뺏음), `멘트 복사`로 카톡에 붙여넣기

## 📥 직원용 — 설치 없이 실행

1. 저장소 **Releases** 또는 **Actions → Build Windows EXE → Artifacts** 에서
   `일정관리기.exe` 를 내려받습니다.
2. 더블클릭으로 실행합니다. (설치 불필요, 단일 실행파일)
3. **[Google 로그인]** 버튼 → 브라우저에서 회사 구글 계정으로 동의 → 끝.
   이후 캘린더·할일이 자동으로 보입니다.

## ⚙️ 관리자 — 최초 1회 구글 설정

앱에는 데스크톱용 OAuth 클라이언트가 내장되어 있습니다
(`planner/config.py` 의 `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`).
이 클라이언트가 속한 **구글 클라우드 프로젝트**에서 아래만 확인하면 직원들은 바로 로그인됩니다.

1. [Google Cloud Console](https://console.cloud.google.com) → 해당 프로젝트 선택
2. **API 및 서비스 → 라이브러리** 에서 두 가지 "사용 설정"
   - **Google Calendar API**
   - **Google Tasks API**
3. **OAuth 동의 화면**
   - 테스트 모드면 **테스트 사용자**에 직원들의 구글 이메일을 추가(최대 100명), 또는
   - **앱 게시(Publish)** 로 전환
4. 직원 계정으로 [Google 로그인] 이 되는지 확인

> 내 클라이언트로 바꾸고 싶으면 `config.py` 의 두 값만 교체하면 됩니다.

## 🧑‍💻 개발자 — 소스로 실행

```bash
cd python
python -m pip install -r requirements.txt
python -m planner        # 또는  python main.py
```

Python 3.10+ 권장. 저장 위치: `%APPDATA%\Planner\`
(`todos.json`, `pcalarms.json`, `taskalarms.json`, `google_token.json`, `backup\`)

## 🏗️ 직접 exe 빌드

- **자동**: `python/` 아래 코드를 `main` 에 push 하면 GitHub Actions(windows-latest)가
  PyInstaller 로 `일정관리기.exe` 를 빌드해 **Artifacts** 에 올립니다.
  버전 태그(`v1.0.0` 등)를 push 하면 **Release** 에도 첨부됩니다.
- **로컬(Windows)**:
  ```bash
  cd python
  pip install -r requirements.txt pyinstaller
  pyinstaller planner.spec --noconfirm --clean
  # dist\일정관리기.exe 생성
  ```

## 🔄 v1.1 추가 기능

1. **계정별 저장 + 다중 PC 동기화** — 로그인한 구글 계정별로 데이터를 분리 저장하고,
   Drive 앱 전용 공간(appDataFolder)에 동기화해 여러 PC에서 같은 계정으로 쓰면 자동 동기화됩니다.
   (같은 사람이 번갈아 쓰는 용도. 두 PC에서 동시에 오프라인 편집 시 나중에 저장한 쪽이 우선)
2. **캘린더 창** — 상단 [캘린더 열기]로 월 달력을 띄우고, 날짜를 클릭(더블클릭)해 구글 캘린더에
   일정을 직접 추가. [브라우저에서 열기]로 실제 구글 캘린더로도 이동. 설정에서
   **팔로업을 구글 캘린더에도 등록**(on/off) 가능.
3. **주간 브리핑** — 시작 브리핑에 오늘 요약 + 이번주(7일) 일정·할일 요약이 함께 표시됩니다.
4. **자동 업데이트** — 시작 시(그리고 트레이 [업데이트 확인]) GitHub 릴리스를 확인해 새 버전이
   있으면 내려받아 교체·재실행합니다.
5. **다크 모드** — 설정에서 토글.
6. **빠른 필터** — 상단 [표시: 이번주 / 다음주 / 전체]로 일정·할일 범위를 즉시 전환.

### ⚙️ v1.1 준비사항 (관리자 1회)
- **구글 클라우드 → API 사용 설정**: 기존 Calendar/Tasks 에 더해 **Google Drive API** 를 켭니다.
- **권한 재동의**: 권한(scope)이 늘어나 직원은 **[설정] → Google 로그아웃 후 다시 로그인** 한 번 필요.
- **자동 업데이트용 릴리스**: 저장소에 버전 태그(예: `v1.1.0`)로 릴리스를 만들고 자산에
  `일정관리기.exe` 를 올립니다(태그를 push 하면 CI가 자동 첨부).
  - 저장소가 **비공개**면 앱이 자산을 받으려면 읽기 토큰이 필요합니다:
    `%APPDATA%\Planner\gh_token.txt` 에 `contents:read` 권한의 파인그레인드 토큰을 넣거나,
    저장소를 공개로 전환하세요. (없으면 업데이트 확인만 실패하고 앱 동작엔 지장 없음)

## 📂 구조

```
python/
  main.py                  PyInstaller 엔트리
  planner.spec             빌드 스펙(단일 exe, 콘솔 없음)
  planner.ico              앱/트레이 아이콘
  requirements.txt
  planner/
    app.py                 QApplication 시작
    config.py              상수·색상·OAuth 클라이언트·저장경로
    models.py              할일/PC알람/Task알람 (JSON 호환)
    google_client.py       OAuth 로그인 + 캘린더/Tasks API
    main_window.py         메인 창(2탭·트레이·타이머)
    alarm_window.py        최상단 알람 팝업
    edit_dialog.py         할일/알람/구글할일 편집창
    icon.py                아이콘 로드/생성
```
