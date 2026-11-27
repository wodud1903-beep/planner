"""TLS 인증서 묶음(cacert.pem)을 임시 폴더 밖에 한 벌 두고 그것을 쓴다(v1.35.1).

지점장 PC: [업데이트 확인] → '업데이트 실패: Could not find a suitable TLS CA certificate bundle,
invalid path: …\\Temp\\_MEI…\\certifi\\cacert.pem'.

한 파일 exe(PyInstaller)는 켤 때 임시 폴더(_MEI…)에 풀어 놓고 그 안의 파일을 쓴다. 트레이에 며칠
켜 둔 사이 윈도 저장 공간 센스·디스크 정리·PC 청소 프로그램이 그 폴더를 비운다 — 쓰고 있는 DLL 은
잠겨 있어 남고, 켤 때 한 번 읽고 만 cacert.pem 같은 파일만 사라진다. requests 는 보낼 때마다 그
파일이 있는지 보므로 업데이트 · 구글 연결이 모두 이 오류로 막혔다(껐다 켜면 다시 풀려서 된다).

→ 켤 때 앱 폴더(%APPDATA%\\Planner\\certs)에 복사해 두고 REQUESTS_CA_BUNDLE 로 그것을 쓰게 한다.
  임시 폴더 것이 지워져도 복사본은 남는다. 임시 폴더 것이 이미 없으면 지난번 복사본을 쓴다.
  사용자가 직접 정한 REQUESTS_CA_BUNDLE(회사 프록시 인증서 등)이 있으면 건드리지 않는다.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

ENV = "REQUESTS_CA_BUNDLE"
FILE_NAME = "cacert.pem"


def _source() -> str:
    """지금 exe 가 가진 인증서 묶음(임시 폴더 안) 경로 — 없으면 ""."""
    try:
        import certifi
        return certifi.where()
    except Exception:
        return ""


def _same(a: Path, b: str) -> bool:
    try:
        return a.stat().st_size == os.path.getsize(b) and a.read_bytes() == Path(b).read_bytes()
    except OSError:
        return False


def ensure(dest_dir) -> str:
    """복사본을 맞춰 두고 requests 가 그것을 쓰게 한다 → 쓰게 된 경로(못 했으면 "")."""
    mine = os.environ.get(ENV, "")
    if mine and os.path.isfile(mine) and not _is_ours(mine, dest_dir):
        return mine                       # 사용자가 정한 것 — 그대로
    dest = Path(dest_dir) / FILE_NAME
    src = _source()
    if src and os.path.isfile(src) and not _same(dest, src):
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(FILE_NAME + ".tmp")
            shutil.copyfile(src, tmp)
            os.replace(tmp, dest)
        except OSError:
            pass
    try:
        ok = dest.is_file() and dest.stat().st_size > 0
    except OSError:
        ok = False
    if ok:
        os.environ[ENV] = str(dest)
        return str(dest)
    if mine and not os.path.isfile(mine):
        os.environ.pop(ENV, None)         # 지난번 우리 값인데 파일이 없다 — 기본값으로
    return ""


def _is_ours(path: str, dest_dir) -> bool:
    try:
        return os.path.normcase(os.path.abspath(path)) == \
            os.path.normcase(os.path.abspath(str(Path(dest_dir) / FILE_NAME)))
    except Exception:
        return False
