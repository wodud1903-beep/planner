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

import os
import shutil
import subprocess
import sys
import tempfile

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
    old_name = base + ".old"          # ren 은 경로 없이 파일명만
    old_full = target + ".old"
    try:
        if os.path.exists(staged):
            os.remove(staged)
    except Exception:
        pass
    shutil.move(new_exe, staged)      # 대상과 같은 폴더로 이동(같은 볼륨 보장)

    pid = os.getpid()
    try:
        log = str(config.base_dir() / "update_log.txt")
    except Exception:
        log = os.path.join(tdir, "update_log.txt")

    bat = os.path.join(tempfile.gettempdir(), "planner_update.bat")
    script = f"""@echo off
setlocal enableextensions enabledelayedexpansion
set "SRC={staged}"
set "DST={target}"
set "OLD={old_full}"
set "LOG={log}"
set "PID={pid}"
echo [update] start SRC=%SRC% DST=%DST% PID=%PID% > "%LOG%"

rem 1) 이전(현재) 프로세스가 완전히 끝날 때까지 대기 (최대 40초)
set /a N=0
:waitproc
tasklist /FI "PID eq %PID%" 2>nul | find "%PID%" >nul
if errorlevel 1 goto gone
set /a N+=1
if !N! gtr 40 goto gone
timeout /t 1 /nobreak >nul
goto waitproc
:gone
echo [update] old process ended (waited !N!s) >> "%LOG%"
timeout /t 1 /nobreak >nul

rem 2) 새 파일로 교체 (최대 60회 재시도, 잠겨 있으면 rename 트릭)
set /a N=0
:copyloop
del "%OLD%" >nul 2>&1
copy /Y "%SRC%" "%DST%" >nul 2>&1
if not errorlevel 1 goto copied
rem 아직 잠겨 있으면: 실행 파일도 '이름 변경'은 허용됨 → 비켜 놓고 복사
ren "%DST%" "{old_name}" >nul 2>&1
copy /Y "%SRC%" "%DST%" >nul 2>&1
if not errorlevel 1 goto copied
set /a N+=1
if !N! gtr 60 goto giveup
timeout /t 1 /nobreak >nul
goto copyloop
:copied
echo [update] replaced ok >> "%LOG%"

rem 3) 새 버전 실행 (탐색기 컨텍스트 = 더블클릭과 동일한 깨끗한 환경)
timeout /t 2 /nobreak >nul
explorer.exe "%DST%"
echo [update] relaunched >> "%LOG%"

rem 4) 정리 — 직전 버전(%OLD%)은 남겨둔다.
rem     새 exe 가 못 뜨는 경우 되돌릴 수단이 이것뿐이라 지우면 안 된다.
del "%SRC%" >nul 2>&1
goto done
:giveup
echo [update] GIVE UP - target still locked >> "%LOG%"
:done
del "%~f0" >nul 2>&1
"""
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
