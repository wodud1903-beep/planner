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
    asset_url = ""
    for a in rel.get("assets", []):
        if a.get("name") == config.UPDATE_ASSET_NAME:
            asset_url = a.get("url", "")  # API URL (octet-stream 으로 받으면 비공개도 OK)
            break
    if not asset_url:
        raise RuntimeError(f"릴리스에 '{config.UPDATE_ASSET_NAME}' 자산이 없습니다.")
    return {"version": tag, "asset_url": asset_url,
            "notes": rel.get("body", ""), "name": rel.get("name", tag)}


def download(asset_url: str) -> str:
    """자산을 임시 파일로 내려받고 경로 반환."""
    r = requests.get(asset_url, headers=_headers("application/octet-stream"),
                     timeout=180, stream=True)
    if r.status_code != 200:
        raise RuntimeError(f"다운로드 실패 (HTTP {r.status_code})")
    fd, path = tempfile.mkstemp(suffix=".exe", prefix="planner_upd_")
    with os.fdopen(fd, "wb") as f:
        for chunk in r.iter_content(chunk_size=1 << 16):
            if chunk:
                f.write(chunk)
    return path


def apply_and_restart(new_exe: str) -> None:
    """현재 exe 를 새 파일로 교체하고 재실행 (Windows 전용)."""
    if not is_frozen() or sys.platform != "win32":
        raise RuntimeError("실행 파일(exe) 상태에서만 자동 교체할 수 있습니다.")
    target = sys.executable
    pid = os.getpid()
    bat = os.path.join(tempfile.gettempdir(), "planner_update.bat")
    script = f"""@echo off
:waitloop
tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul
if not errorlevel 1 (
  timeout /t 1 /nobreak >nul
  goto waitloop
)
move /Y "{new_exe}" "{target}" >nul
start "" "{target}"
del "%~f0"
"""
    with open(bat, "w", encoding="utf-8") as f:
        f.write(script)
    subprocess.Popen(["cmd", "/c", bat],
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
