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
# 교체 (일정관리기와 같은 배치 — update_script 는 일정관리기 것을 그대로 옮겼다)
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
    status = str(_status_path())
    try:
        os.remove(status)              # 지난 결과는 지운다(이번 결과만 남게)
    except Exception:
        pass
    bat = os.path.join(tempfile.gettempdir(), "kbsearch_update.bat")
    script = update_script(staged, target, old_full, log_path(), os.getpid(),
                           _parent_if_bootloader(), status)
    # cmd 는 배치를 시스템 ANSI 코드페이지로 읽는다(한글 경로 대응)
    try:
        with open(bat, "w", encoding="mbcs") as f:
            f.write(script)
    except (LookupError, UnicodeEncodeError):
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
# 업데이트 뒤처리 — 결과 · 남은 옛 판 넘겨받기 (일정관리기 v1.23.1 과 같다)
#
# 옛 판이 끝나지 않고 남아 있으면 새 판이 '이미 실행 중' 으로 보고 옛 창만 불러온 뒤
# 스스로 꺼진다 → 업데이트를 해도 계속 옛 판. 막는 길 셋:
#   · 배치가 자식(PID)과 한 파일 exe 의 부모(PPID)를 다 기다리고, 30초 넘으면 끝낸다
#   · 새 판이 방금 깔렸는데(기록 'replaced ok', 10분 안) 남은 쪽이 대답이 없거나 낮은 판이면
#     그것을 끝내고 이어서 뜬다(app._take_over_after_update)
#   · 끝낼 때 파이썬 마무리 정리 없이 바로 끝낸다(app.main 의 os._exit)
# ---------------------------------------------------------------------------
def _status_path():
    return config.base_dir() / "update_status.txt"


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
    """방금 업데이트 배치가 이 exe 를 깔고 띄웠는가(배치가 'replaced ok' 를 적는다)."""
    try:
        p = config.base_dir() / "update_log.txt"
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


def failure_text(reason: str) -> str:
    """업데이트 창에 보일 '지난번에 왜 안 됐나'."""
    return {"missing": "받아 둔 새 프로그램 파일이 사라졌습니다 — 백신(바이러스 검사)이 "
                       "지웠을 수 있습니다.",
            "locked": "프로그램 파일이 잠겨 있어 바꾸지 못했습니다."}.get(
        reason, "프로그램 파일을 바꾸지 못했습니다.")


RELEASES_URL = f"https://github.com/{config.UPDATE_REPO}/releases"
