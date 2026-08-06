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
