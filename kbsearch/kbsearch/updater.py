"""자동 업데이트 — **건너뛸 수 없다.** 새 판이 있으면 받아 바꾸기 전에는 쓰지 못한다.

일정관리기 updater.py 의 받기·교체 방식을 그대로 쓰되, 릴리스를 고르는 법이 다르다.
  · 일정관리기와 같은 저장소에 릴리스를 낸다. 태그 머리말(kb-v)로 가른다.
    일정관리기가 보는 releases/latest 를 건드리지 않으려고, 목록을 받아 kb-v 만 고른다.
  · 자산은 이름(또는 라벨)이 '업무자료검색.exe' 인 것만 받는다. kb-v 릴리스에 exe 가
    하나뿐이면 그것을 쓴다(깃허브가 한글 이름을 default.exe 로 바꾸는 경우).

**왜 건너뛸 수 없나** — 나중에 서비스를 끄거나(config.SERVICE_ON) 동기화를 닫을
(config.SYNC_ON) 때 새 판을 내는 것으로 모든 PC 를 따르게 하려는 것이다.
인터넷이 안 돼 확인 자체를 못 하면 그냥 쓰게 둔다 — 자료가 이 PC 에 있어 혼자서도
검색은 돼야 한다. 켜 둔 동안 몇 시간마다 다시 확인한다(main_window).

**같은 판을 끝없이 다시 받지 않게** — 바꾸고 다시 켰는데 판이 그대로면(교체 실패,
또는 태그와 안의 판 번호가 다른 릴리스) 자동으로 또 받지 않고 [다시 시도] 를 기다린다.
"""

from __future__ import annotations

import hashlib
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

STATE_FILE = "update_state.json"
RETRY_GUARD_SEC = 30 * 60


class UpdateError(Exception):
    pass


def _token() -> str:
    """비공개 저장소로 바꿨을 때만 쓴다 — 그 PC 의 %APPDATA%\\KbSearch\\gh_token.txt."""
    try:
        p = config.base_dir() / "gh_token.txt"
        if p.exists():
            return p.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return ""


def _headers(accept: str) -> dict:
    h = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28",
         "User-Agent": f"{config.APP_ID}/{config.APP_VERSION}"}
    t = _token()
    if t:
        h["Authorization"] = "Bearer " + t
    return h


def parse_ver(s: str) -> tuple:
    """'kb-v1.2.3' · 'v1.2.3' · '1.2.3' → (1, 2, 3)."""
    s = (s or "").strip()
    if s.lower().startswith(config.UPDATE_TAG_PREFIX):
        s = s[len(config.UPDATE_TAG_PREFIX):]
    s = s.lstrip("vV")
    parts = []
    for x in s.split("."):
        num = "".join(ch for ch in x if ch.isdigit())
        parts.append(int(num) if num else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def _pick_asset(assets: list) -> dict | None:
    for a in assets:
        if config.UPDATE_ASSET_NAME in (a.get("name"), a.get("label")):
            return a
    exes = [a for a in assets
            if (a.get("name") or "").lower().endswith(".exe")
            or (a.get("label") or "").lower().endswith(".exe")]
    return exes[0] if len(exes) == 1 else None


def pick_release(releases: list) -> dict | None:
    """kb-v 릴리스 중 판 번호가 가장 높은 것(초안·미리보기는 뺀다)."""
    best = None
    for rel in releases or []:
        tag = str(rel.get("tag_name") or "")
        if not tag.lower().startswith(config.UPDATE_TAG_PREFIX):
            continue
        if rel.get("draft") or rel.get("prerelease"):
            continue
        if best is None or parse_ver(tag) > parse_ver(best.get("tag_name", "")):
            best = rel
    return best


def check(timeout=(5, 10)) -> dict | None:
    """새 판이 있으면 dict, 없으면 None. 확인을 못 하면 UpdateError."""
    url = f"https://api.github.com/repos/{config.UPDATE_REPO}/releases"
    rel = None
    # 일정관리기 릴리스와 섞여 있어 한 쪽에 kb-v 가 없을 수 있다 — 나올 때까지 몇 쪽 넘긴다
    for page in (1, 2, 3):
        try:
            r = requests.get(url, headers=_headers("application/vnd.github+json"),
                             params={"per_page": 100, "page": page}, timeout=timeout)
        except requests.RequestException as e:
            raise UpdateError(f"업데이트를 확인하지 못했습니다(인터넷 연결): {e}")
        if r.status_code != 200:
            raise UpdateError(f"업데이트를 확인하지 못했습니다 (HTTP {r.status_code})")
        try:
            batch = r.json()
        except ValueError:
            raise UpdateError("업데이트 정보를 읽지 못했습니다.")
        if not isinstance(batch, list):
            raise UpdateError("업데이트 정보를 읽지 못했습니다.")
        rel = pick_release(batch)
        if rel is not None or len(batch) < 100:
            break
    if not rel or parse_ver(rel.get("tag_name", "")) <= parse_ver(config.APP_VERSION):
        return None
    asset = _pick_asset(rel.get("assets") or [])
    if not asset:
        raise UpdateError(f"{rel.get('tag_name')} 릴리스에 {config.UPDATE_ASSET_NAME} 가 없습니다.")
    ver = ".".join(str(x) for x in parse_ver(rel.get("tag_name", "")))
    digest = str(asset.get("digest") or "")
    return {"version": ver, "tag": rel.get("tag_name", ""),
            "api_url": asset.get("url", ""),
            "download_url": asset.get("browser_download_url", ""),
            "size": int(asset.get("size") or 0),
            "sha256": digest[7:].lower() if digest.startswith("sha256:") else "",
            "notes": rel.get("body", "") or "", "name": rel.get("name", "") or ""}


def _rm(path: str) -> None:
    try:
        os.remove(path)
    except Exception:
        pass


def download(info: dict, progress=None) -> str:
    """새 exe 를 임시 파일로 받아 경로를 돌려준다. progress(받은 바이트, 전체) 를 부른다.

    **받은 크기와 지문(sha256)을 반드시 확인한다.** 연결이 끊겨도 iter_content 는
    예외 없이 끝나서, 확인하지 않으면 반쪽짜리 exe 가 설치된다.
    """
    if _token() and info.get("api_url"):
        url, hdr = info["api_url"], _headers("application/octet-stream")
    else:
        url = info.get("download_url") or info.get("api_url", "")
        hdr = {"User-Agent": f"{config.APP_ID}/{config.APP_VERSION}",
               "Accept": "application/octet-stream"}
    try:
        r = requests.get(url, headers=hdr, timeout=(10, 60), stream=True)
    except requests.RequestException as e:
        raise UpdateError(f"새 버전을 받지 못했습니다(인터넷 연결): {e}")
    if r.status_code != 200:
        raise UpdateError(f"새 버전을 받지 못했습니다 (HTTP {r.status_code})")
    expect = int(info.get("size") or r.headers.get("Content-Length") or 0)
    fd, path = tempfile.mkstemp(suffix=".exe", prefix="kbsearch_upd_")
    got = 0
    sha = hashlib.sha256()
    try:
        with os.fdopen(fd, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                if chunk:
                    f.write(chunk)
                    sha.update(chunk)
                    got += len(chunk)
                    if progress:
                        progress(got, expect)
    except Exception as e:
        _rm(path)
        raise UpdateError(f"받는 중에 연결이 끊겼습니다: {e}")
    if expect and got != expect:
        _rm(path)
        raise UpdateError(f"다 받지 못했습니다 ({got:,} / {expect:,} 바이트). 다시 시도해 주세요.")
    if got < 1_000_000:        # 정상 exe 는 수십 MB — 1MB 미만이면 비정상
        _rm(path)
        raise UpdateError(f"받은 파일이 너무 작습니다 ({got:,} 바이트).")
    if info.get("sha256") and sha.hexdigest() != info["sha256"]:
        _rm(path)
        raise UpdateError("받은 파일의 지문이 릴리스와 다릅니다. 다시 시도해 주세요.")
    return path


# ---------------------------------------------------------------------------
# 같은 판 되풀이 막기
# ---------------------------------------------------------------------------
def _state() -> dict:
    try:
        p = config.data_file(STATE_FILE)
        if p.exists():
            o = json.loads(p.read_text(encoding="utf-8"))
            return o if isinstance(o, dict) else {}
    except Exception:
        pass
    return {}


def note_attempt(version: str) -> None:
    try:
        config.atomic_write(config.data_file(STATE_FILE), json.dumps(
            {"target": version, "from": config.APP_VERSION, "at": time.time()}))
    except Exception:
        pass


def just_failed(version: str) -> bool:
    """방금(30분 안) 이 판으로 바꾸려다 그대로 이 판에서 다시 켜졌는가."""
    st = _state()
    return (st.get("target") == version and st.get("from") == config.APP_VERSION
            and time.time() - float(st.get("at") or 0) < RETRY_GUARD_SEC)


def log_path() -> str:
    return str(config.base_dir() / "update_log.txt")


# ---------------------------------------------------------------------------
# 교체 (일정관리기와 같은 배치)
# ---------------------------------------------------------------------------
def apply_and_restart(new_exe: str, version: str = "") -> None:
    """지금 exe 를 새 파일로 바꾸고 다시 켠다(윈도 전용). 부른 쪽은 곧바로 끝내야 한다.

    배치가 이 프로세스가 끝나기를 기다렸다가 바꾸고, 잠겨 있으면 이름 바꾸기로 비켜 놓고,
    끝내 안 되면 옛 판을 제자리에 되돌려 다시 띄운다(일정관리기 updater 설명과 같다).
    """
    if not is_frozen() or sys.platform != "win32":
        raise UpdateError("실행 파일(exe) 상태에서만 자동으로 바꿀 수 있습니다.")
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
    shutil.move(new_exe, staged)      # 대상과 같은 폴더로(같은 볼륨 보장)

    note_attempt(version)
    bat = os.path.join(tempfile.gettempdir(), "kbsearch_update.bat")
    script = update_script(staged, target, old_full, log_path(), os.getpid())
    # cmd 는 배치를 시스템 ANSI 코드페이지로 읽는다(한글 경로 대응)
    try:
        with open(bat, "w", encoding="mbcs") as f:
            f.write(script)
    except (LookupError, UnicodeEncodeError):
        with open(bat, "w", encoding="utf-8") as f:
            f.write("chcp 65001 >nul\n" + script)
    subprocess.Popen(["cmd", "/c", bat],
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def update_script(staged: str, target: str, old_full: str, log: str, pid: int) -> str:
    """교체 배치 본문 — 일정관리기 updater.update_script 와 같은 순서·같은 안전장치."""
    base = ntpath.basename(target)
    old_name = ntpath.basename(old_full)
    return f"""@echo off
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
rem    직전 판(.old) 지우기는 고리 밖에서 한 번만 한다(비켜 둔 원본을 지우지 않게).
if not exist "%DST%" if exist "%OLD%" ren "%OLD%" "{base}" >nul 2>&1
del "%OLD%" >nul 2>&1
set /a N=0
:copyloop
copy /Y "%SRC%" "%DST%" >nul 2>&1
if not errorlevel 1 goto copied
if exist "%DST%" if not exist "%OLD%" ren "%DST%" "{old_name}" >nul 2>&1
copy /Y "%SRC%" "%DST%" >nul 2>&1
if not errorlevel 1 goto copied
set /a N+=1
if !N! gtr 60 goto giveup
timeout /t 1 /nobreak >nul
goto copyloop
:copied
echo [update] replaced ok >> "%LOG%"

rem 3) 새 버전 실행 (탐색기 컨텍스트 = 더블클릭과 같은 깨끗한 환경)
timeout /t 2 /nobreak >nul
explorer.exe "%DST%"
echo [update] relaunched >> "%LOG%"

rem 4) 정리 — 직전 버전(%OLD%)은 남겨 둔다(새 exe 가 못 뜰 때 되돌릴 수단)
del "%SRC%" >nul 2>&1
goto done
:giveup
echo [update] GIVE UP - target still locked >> "%LOG%"
if not exist "%DST%" if exist "%OLD%" ren "%OLD%" "{base}" >nul 2>&1
if exist "%DST%" echo [update] old version restored >> "%LOG%"
if exist "%DST%" explorer.exe "%DST%"
:done
del "%~f0" >nul 2>&1
"""
