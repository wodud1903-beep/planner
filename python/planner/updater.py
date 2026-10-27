"""자동 업데이트 — GitHub 릴리스의 최신 exe 확인 후 교체·재실행.

동작:
  1. releases/latest 에서 최신 태그(vX.Y.Z)와 자산(일정관리기.exe) 확인
  2. 현재 버전보다 높으면 exe 다운로드 → 교체 배치 실행 → 앱 종료 → 새 버전 시작

주의:
  - 저장소가 '비공개'면 자산 다운로드에 읽기 토큰이 필요하다.
    config.GITHUB_TOKEN 또는 %APPDATA%\\Planner\\gh_token.txt 에 토큰을 넣거나,
    저장소를 공개로 전환하면 토큰 없이 동작한다.
  - 릴리스는 버전 태그(예: v1.1.0)로 만들어야 하고, 자산 이름이 '일정관리기.exe' 여야 한다.
"""

from __future__ import annotations

import json
import ntpath
import os
import shutil
import subprocess
import sys
import tempfile
import time

import requests

from . import config


def _token() -> str:
    if config.GITHUB_TOKEN:
        return config.GITHUB_TOKEN.strip()
    try:
        p = config.base_dir() / "gh_token.txt"
        if p.exists():
            return p.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return ""


def _headers(accept: str) -> dict:
    h = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
    t = _token()
    if t:
        h["Authorization"] = "Bearer " + t
    return h


def _parse_ver(s: str) -> tuple:
    s = (s or "").strip().lstrip("vV")
    parts = []
    for x in s.split("."):
        num = "".join(ch for ch in x if ch.isdigit())
        parts.append(int(num) if num else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def check():
    """최신 릴리스 확인. 새 버전이 있으면 dict, 없으면 None, 오류면 예외."""
    url = f"https://api.github.com/repos/{config.UPDATE_REPO}/releases/latest"
    r = requests.get(url, headers=_headers("application/vnd.github+json"), timeout=20)
    if r.status_code == 404:
        raise RuntimeError("릴리스를 찾을 수 없습니다(비공개 저장소면 토큰이 필요).")
    if r.status_code != 200:
        raise RuntimeError(f"업데이트 확인 실패 (HTTP {r.status_code})")
    rel = r.json()
    tag = rel.get("tag_name", "")
    if _parse_ver(tag) <= _parse_ver(config.APP_VERSION):
        return None
    # 자산 선택: 이름 또는 라벨이 일치하는 것 우선, 없으면 첫 번째 .exe
    # (GitHub 이 한글 파일명을 default.exe 로 바꾸고 원래 이름을 label 에 넣는 경우 대비)
    assets = rel.get("assets", [])
    asset_url = ""
    for a in assets:
        if a.get("name") == config.UPDATE_ASSET_NAME or a.get("label") == config.UPDATE_ASSET_NAME:
            asset_url = a.get("url", "")
            break
    if not asset_url:
        for a in assets:
            nm = (a.get("name") or "").lower()
            lb = (a.get("label") or "").lower()
            if nm.endswith(".exe") or lb.endswith(".exe"):
                asset_url = a.get("url", "")
                break
    if not asset_url:
        raise RuntimeError("릴리스에 exe 자산이 없습니다.")
    return {"version": tag, "asset_url": asset_url,
            "notes": rel.get("body", ""), "name": rel.get("name", tag)}


def _rm(path: str) -> None:
    try:
        os.remove(path)
    except Exception:
        pass


def download(asset_url: str) -> str:
    """자산을 임시 파일로 내려받고 경로 반환.

    **받은 크기를 반드시 검증한다.** stream=True 로 받다가 연결이 끊겨도
    iter_content 는 예외 없이 정상 종료한다. 예전엔 검증이 없어 절반짜리 exe 가
    그대로 설치되고, 교체 배치가 백업본까지 지워 앱이 아예 실행되지 않았다.
    """
    r = requests.get(asset_url, headers=_headers("application/octet-stream"),
                     timeout=180, stream=True)
    if r.status_code != 200:
        raise RuntimeError(f"다운로드 실패 (HTTP {r.status_code})")
    expect = int(r.headers.get("Content-Length") or 0)
    fd, path = tempfile.mkstemp(suffix=".exe", prefix="planner_upd_")
    got = 0
    try:
        with os.fdopen(fd, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                if chunk:
                    f.write(chunk)
                    got += len(chunk)
    except Exception as e:
        _rm(path)
        raise RuntimeError(f"다운로드 중 연결이 끊겼습니다: {e}")

    if expect and got != expect:
        _rm(path)
        raise RuntimeError(
            f"다운로드가 완전하지 않습니다 ({got:,} / {expect:,} 바이트).\n"
            "네트워크 상태를 확인한 뒤 다시 시도하세요.")
    if got < 1_000_000:        # 정상 exe 는 50MB 안팎 — 1MB 미만이면 비정상
        _rm(path)
        raise RuntimeError(f"받은 파일이 너무 작습니다 ({got:,} 바이트).")
    return path


def apply_and_restart(new_exe: str) -> None:
    """현재 exe 를 새 파일로 교체하고 재실행 (Windows 전용).

    안정화 설계(이번 개편):
      1) 새 파일을 대상 폴더(같은 볼륨)에 스테이징.
      2) 교체 배치를 실행하고 앱은 즉시 종료한다.
      3) 배치는 **PID 로 이전 프로세스가 완전히 끝날 때까지 대기**한 뒤 교체 →
         "앱이 안 죽어서 잠금이 안 풀리는" 상황을 확실히 처리.
      4) 잠금이 남아 있어도 **rename 트릭**(실행 중인 exe 도 이름 변경은 허용)으로
         기존 파일을 비켜 놓고 새 파일을 제자리에 둔다.
      5) 이전 프로세스가 끝난 뒤 재실행하므로 **중복 실행 방지(단일 인스턴스)** 와
         충돌하지 않는다.
      6) 배치는 시스템 기본 코드페이지(mbcs)로 저장 → **한글이 포함된 경로**도
         cmd 가 정상 인식(UTF-8 로 저장하면 한글 경로에서 모든 파일 작업 실패).
      7) 진행 상황을 %APPDATA%\\Planner\\update_log.txt 에 기록 → 문제 진단 용이.
    """
    if not is_frozen() or sys.platform != "win32":
        raise RuntimeError("실행 파일(exe) 상태에서만 자동 교체할 수 있습니다.")
    target = sys.executable
    tdir = os.path.dirname(target) or "."
    base = os.path.basename(target)
    staged = os.path.join(tdir, "_update_" + base)
    old_full = target + ".old"
    try:
        if os.path.exists(staged):
            os.remove(staged)
    except Exception:
        pass
    shutil.move(new_exe, staged)      # 대상과 같은 폴더로 이동(같은 볼륨 보장)

    pid = os.getpid()
    ppid = _parent_if_bootloader()
    log, status = str(_log_path()), str(_status_path())
    try:
        os.remove(status)              # 지난 결과는 지운다(이번 결과만 남게)
    except Exception:
        pass

    bat = os.path.join(tempfile.gettempdir(), "planner_update.bat")
    script = update_script(staged, target, old_full, log, pid, ppid, status)
    # cmd 는 배치를 시스템 ANSI 코드페이지로 읽으므로 mbcs 로 저장(한글 경로 대응).
    try:
        with open(bat, "w", encoding="mbcs") as f:
            f.write(script)
    except (LookupError, UnicodeEncodeError):
        # 폴백: mbcs 불가 환경이면 UTF-8 + chcp 65001
        with open(bat, "w", encoding="utf-8") as f:
            f.write("chcp 65001 >nul\n" + script)
    subprocess.Popen(["cmd", "/c", bat],
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def update_script(staged: str, target: str, old_full: str, log: str, pid: int,
                  ppid: int = 0, status: str = "") -> str:
    """교체 배치 본문. apply_and_restart 가 파일로 써서 돌린다.

    따로 떼어 둔 것은 검사(tools/verify/verify_update.py)가 이 글을 그대로 받아
    가짜 파일들 위에서 한 줄씩 돌려 보기 위해서다 — 윈도 없이도 '끝내 실패하면
    프로그램이 사라지는가' 를 확인할 수 있다.

    ppid — 한 파일 exe(PyInstaller)는 프로세스가 둘이다(풀어 놓는 부모 + 실제로 도는
    자식). 자식(pid)만 기다리면 부모가 아직 exe 를 쥐고 있을 수 있어 둘 다 기다린다.
    status — 결과 한 줄(ok / fail missing / fail locked). 다음에 켤 때 읽고 알려 준다.
    """
    # 배치는 윈도에서만 돈다 — 경로도 윈도 규칙(ntpath)으로 자른다
    # (윈도에선 os.path 가 곧 ntpath 라 같고, 검사 환경에서도 똑같이 나온다)
    base = ntpath.basename(target)
    old_name = ntpath.basename(old_full)
    status = status or ntpath.join(ntpath.dirname(log), "update_status.txt")
    return f"""@echo off
setlocal enableextensions enabledelayedexpansion
set "SRC={staged}"
set "DST={target}"
set "OLD={old_full}"
set "LOG={log}"
set "STATUS={status}"
set "PID={pid}"
set "PPID={ppid}"
echo [update] start SRC=%SRC% DST=%DST% PID=%PID% PPID=%PPID% > "%LOG%"

rem 1) 이전(현재) 프로세스가 완전히 끝날 때까지 대기 — 자식(PID)과 부모(PPID) 모두.
rem    30초가 지나도 남아 있으면 **끝내 버린다**. 예전엔 40초 뒤 그냥 넘어갔는데,
rem    옛 판이 남아 있으면 새 판이 떠도 '이미 실행 중' 으로 보고 옛 창만 불러온 뒤
rem    스스로 꺼졌다 → 업데이트를 해도 계속 옛 판(v1.22.1 무한 업데이트).
set /a N=0
:waitproc
tasklist /FI "PID eq %PID%" 2>nul | find "%PID%" >nul
if errorlevel 1 goto waitparent
set /a N+=1
if !N! gtr 30 goto forcekill
timeout /t 1 /nobreak >nul
goto waitproc
:waitparent
if "%PPID%"=="0" goto gone
tasklist /FI "PID eq %PPID%" 2>nul | find "%PPID%" >nul
if errorlevel 1 goto gone
set /a N+=1
if !N! gtr 30 goto forcekill
timeout /t 1 /nobreak >nul
goto waitparent
:forcekill
echo [update] old process still running after 30s - ending it >> "%LOG%"
taskkill /F /T /PID %PID% >nul 2>&1
if not "%PPID%"=="0" taskkill /F /T /PID %PPID% >nul 2>&1
timeout /t 2 /nobreak >nul
:gone
echo [update] old process ended (waited !N!s) >> "%LOG%"
timeout /t 1 /nobreak >nul

rem 2) 새 파일로 교체 (최대 60회 재시도, 잠겨 있으면 rename 트릭)
rem    ⚠️ 직전 판(.old) 지우기는 **고리 밖에서 한 번만** 한다. 예전엔 고리 첫 줄에
rem       있어서, 원본을 .old 로 비켜 둔 다음 바퀴에 그 원본을 지웠다 — 끝내 복사가
rem       안 되면 새 판도 옛 판도 없어 프로그램이 아예 사라졌다.
rem    지난번 교체가 도중에 멈춰 원본이 .old 로만 남아 있으면 먼저 되돌린다.
if not exist "%DST%" if exist "%OLD%" ren "%OLD%" "{base}" >nul 2>&1
del "%OLD%" >nul 2>&1
set /a N=0
:copyloop
rem 받아 둔 새 파일이 없어졌으면(백신이 지운 경우가 많다) 기다려도 소용없다
if not exist "%SRC%" goto srcgone
copy /Y "%SRC%" "%DST%" >nul 2>&1
if not errorlevel 1 goto copied
rem 아직 잠겨 있으면: 실행 파일도 '이름 변경'은 허용됨 → 비켜 놓고 복사
rem (이미 비켜 뒀으면 다시 비키지 않는다 — 비켜 둔 원본을 덮지 않게)
if exist "%DST%" if not exist "%OLD%" ren "%DST%" "{old_name}" >nul 2>&1
copy /Y "%SRC%" "%DST%" >nul 2>&1
if not errorlevel 1 goto copied
set /a N+=1
if !N! gtr 60 goto giveup
timeout /t 1 /nobreak >nul
goto copyloop
:copied
echo [update] replaced ok >> "%LOG%"
echo ok> "%STATUS%"

rem 3) 새 버전 실행 (탐색기 컨텍스트 = 더블클릭과 동일한 깨끗한 환경)
timeout /t 2 /nobreak >nul
explorer.exe "%DST%"
echo [update] relaunched >> "%LOG%"

rem 4) 정리 — 직전 버전(%OLD%)은 남겨둔다.
rem     새 exe 가 못 뜨는 경우 되돌릴 수단이 이것뿐이라 지우면 안 된다.
del "%SRC%" >nul 2>&1
goto done
:srcgone
echo [update] NEW FILE MISSING - removed by antivirus? >> "%LOG%"
echo fail missing> "%STATUS%"
goto restore
:giveup
echo [update] GIVE UP - target still locked >> "%LOG%"
echo fail locked> "%STATUS%"
:restore
rem 원본을 비켜 둔 채 끝내지 않는다 — 제자리로 되돌리고 옛 판을 다시 띄운다
if not exist "%DST%" if exist "%OLD%" ren "%OLD%" "{base}" >nul 2>&1
if exist "%DST%" echo [update] old version restored >> "%LOG%"
if exist "%DST%" explorer.exe "%DST%"
:done
del "%~f0" >nul 2>&1
"""


# ---------------------------------------------------------------------------
# 업데이트 뒤처리 — 결과 알림 · 남은 옛 판 넘겨받기 · 자동 업데이트 횟수
# ---------------------------------------------------------------------------
AUTO_MAX_TRIES = 2              # 같은 판을 자동으로 이만큼 시도해도 안 되면 그만(매번 꺼지지 않게)


def _log_path():
    return config.base_dir() / "update_log.txt"


def _status_path():
    return config.base_dir() / "update_status.txt"


def _attempt_path():
    return config.base_dir() / "update_attempt.json"


def _no_window() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _tasklist(filt: str) -> list:
    """[(이미지 이름, pid)] — 윈도 tasklist. 못 읽으면 []."""
    try:
        out = subprocess.run(["tasklist", "/FI", filt, "/FO", "CSV", "/NH"],
                             capture_output=True, text=True, encoding="mbcs",
                             errors="replace", timeout=10,
                             creationflags=_no_window()).stdout
    except Exception:
        return []
    rows = []
    for ln in out.splitlines():
        parts = [x.strip().strip('"') for x in ln.split('","')]
        if len(parts) >= 2 and parts[1].strip('"').isdigit():
            rows.append((parts[0].strip('"'), int(parts[1].strip('"'))))
    return rows


def _parent_if_bootloader() -> int:
    """부모 프로세스가 같은 exe(한 파일 exe 의 풀어 놓는 쪽)이면 그 pid, 아니면 0.

    ⚠️ 그냥 부모를 넘기면 안 된다 — 개발 실행이면 부모가 탐색기·명령창일 수 있고,
       배치가 30초 뒤 그것까지 끝내 버린다.
    """
    try:
        ppid = os.getppid()
        me = os.path.basename(sys.executable).lower()
        for name, pid in _tasklist(f"PID eq {ppid}"):
            if pid == ppid and name.lower() == me:
                return ppid
    except Exception:
        pass
    return 0


def kill_other_instances() -> int:
    """같은 exe 로 도는 다른 프로세스(남아 있는 옛 판)를 끝낸다. 끝낸 수."""
    if sys.platform != "win32":
        return 0
    me = {os.getpid(), os.getppid()}
    name = os.path.basename(sys.executable)
    n = 0
    for _nm, pid in _tasklist(f"IMAGENAME eq {name}"):
        if pid in me:
            continue
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True,
                           timeout=10, creationflags=_no_window())
            n += 1
        except Exception:
            pass
    return n


def just_installed(window_sec: int = 600) -> bool:
    """방금 업데이트 배치가 이 exe 를 깔고 띄웠는가(옛 배치도 'replaced ok' 를 적는다)."""
    try:
        p = _log_path()
        if not p.exists() or time.time() - p.stat().st_mtime > window_sec:
            return False
        return "replaced ok" in p.read_text(encoding="mbcs" if sys.platform == "win32"
                                            else "utf-8", errors="replace")
    except Exception:
        return False


def last_failure() -> str:
    """지난 업데이트가 실패했으면 그 이유('missing' / 'locked'), 아니면 ""."""
    try:
        p = _status_path()
        if not p.exists():
            return ""
        txt = p.read_text(encoding="utf-8", errors="replace").strip()
        if txt.startswith("fail"):
            return txt.split()[-1] if len(txt.split()) > 1 else "unknown"
    except Exception:
        pass
    return ""


def ack_failure() -> None:
    try:
        _status_path().unlink()
    except Exception:
        pass


def failure_text(reason: str) -> str:
    why = {"missing": "받아 둔 새 프로그램 파일이 사라졌습니다 — 백신(바이러스 검사)이 "
                      "지웠을 수 있습니다.",
           "locked": "프로그램 파일이 잠겨 있어 바꾸지 못했습니다."}.get(
        reason, "프로그램 파일을 바꾸지 못했습니다.")
    return (f"지난 업데이트를 마치지 못해 이전 판(v{config.APP_VERSION})으로 켜졌습니다.\n\n"
            f"{why}\n\n[받는 곳 열기] 를 눌러 최신 판을 직접 받아, 지금 쓰는 프로그램 파일과 "
            "바꿔 주세요(프로그램을 완전히 끈 뒤).")


def _parse_attempt() -> dict:
    try:
        return json.loads(_attempt_path().read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def attempts(version: str) -> int:
    d = _parse_attempt()
    return int(d.get("count", 0)) if d.get("version") == version else 0


def note_attempt(version: str) -> None:
    n = attempts(version) + 1
    try:
        config.atomic_write(_attempt_path(), json.dumps(
            {"version": version, "count": n, "at": time.strftime("%Y-%m-%d %H:%M:%S")}))
    except Exception:
        pass


def clear_attempt_if_done(current: str) -> None:
    """지금 판이 시도하던 판 이상이면(업데이트가 됐으면) 기록을 지운다."""
    d = _parse_attempt()
    if d and _parse_ver(d.get("version", "")) <= _parse_ver(current):
        try:
            _attempt_path().unlink()
        except Exception:
            pass

