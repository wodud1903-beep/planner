"""업데이트 실패 'Could not find a suitable TLS CA certificate bundle' 막기(v1.35.1) — 지점장 PC.

며칠 켜 둔 사이 청소 프로그램이 임시 폴더(_MEI…)의 certifi\\cacert.pem 을 지웠다. requests 는 보낼 때마다
그 파일이 있는지 봐서 업데이트·구글 연결이 막혔다. → 켤 때 %APPDATA%\\Planner\\certs 에 복사해 두고
REQUESTS_CA_BUNDLE 로 그것을 쓴다(planner/cabundle.py).
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))

import os
import shutil
import tempfile
import types

os.environ.pop("REQUESTS_CA_BUNDLE", None)
os.environ.pop("CURL_CA_BUNDLE", None)

import certifi  # noqa: E402
import requests  # noqa: E402
from requests.adapters import HTTPAdapter  # noqa: E402

from planner import cabundle  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


def verify_for(url="https://api.github.com/x"):
    """requests 가 실제로 쓸 verify 값(환경 변수 반영) → 어댑터가 그 파일을 찾는지."""
    s = requests.Session()
    v = s.merge_environment_settings(url, {}, None, True, None)["verify"]
    conn = types.SimpleNamespace()
    try:
        HTTPAdapter().cert_verify(conn, url, v, None)
        return v, ""
    except OSError as e:
        return v, str(e)


real = certifi.where()
tmp = tempfile.mkdtemp()
mei = os.path.join(tmp, "Temp", "_MEI0000666c2", "certifi")
os.makedirs(mei)
fake_src = os.path.join(mei, "cacert.pem")
shutil.copyfile(real, fake_src)
appdir = os.path.join(tmp, "AppData", "Planner", "certs")
certifi.where = lambda: fake_src          # exe 안이면 임시 폴더 경로를 준다

print("[1] 고치기 전 — 임시 폴더 파일이 지워지면 지점장 PC 와 같은 오류")
_, err = verify_for()
ok("처음엔 된다", err == "")
os.rename(fake_src, fake_src + ".gone")
err = ""
try:
    HTTPAdapter().cert_verify(types.SimpleNamespace(), "https://api.github.com/x", fake_src, None)
except OSError as e:
    err = str(e)
ok("지워지면 'Could not find a suitable TLS CA certificate bundle'", "Could not find a suitable TLS CA" in err, err)
os.rename(fake_src + ".gone", fake_src)

print("[2] 켤 때 복사해 두고 그것을 쓴다")
got = cabundle.ensure(appdir)
dest = os.path.join(appdir, "cacert.pem")
ok("복사본 경로를 돌려준다", got == dest, got)
ok("내용이 같다", open(dest, "rb").read() == open(fake_src, "rb").read())
ok("REQUESTS_CA_BUNDLE = 복사본", os.environ.get("REQUESTS_CA_BUNDLE") == dest)
os.remove(fake_src)                       # 청소 프로그램이 임시 폴더를 비웠다
v, err = verify_for()
ok("임시 폴더 것이 지워져도 requests 는 복사본을 찾는다", err == "" and v == dest, (v, err))

print("[3] 다음에 켤 때")
os.environ.pop("REQUESTS_CA_BUNDLE", None)
ok("임시 폴더 것이 없어도 지난번 복사본을 쓴다", cabundle.ensure(appdir) == dest)
shutil.copyfile(real, fake_src)
with open(fake_src, "ab") as f:
    f.write(b"\n# new\n")                 # 새 판의 인증서 묶음이 바뀌었다
cabundle.ensure(appdir)
ok("새 판 것으로 바꿔 둔다", open(dest, "rb").read() == open(fake_src, "rb").read())
ok("임시 파일(.tmp)을 남기지 않는다", os.listdir(appdir) == ["cacert.pem"], os.listdir(appdir))

print("[4] 사용자가 정한 인증서(회사 프록시 등)는 그대로")
own = os.path.join(tmp, "corp.pem")
shutil.copyfile(real, own)
os.environ["REQUESTS_CA_BUNDLE"] = own
ok("건드리지 않는다", cabundle.ensure(appdir) == own and os.environ["REQUESTS_CA_BUNDLE"] == own)
os.environ.pop("REQUESTS_CA_BUNDLE", None)

print("[5] 복사도 못 하고 원본도 없으면 기본값(예전 그대로)")
os.remove(fake_src)
empty = os.path.join(tmp, "nowhere")
os.environ["REQUESTS_CA_BUNDLE"] = os.path.join(empty, "cacert.pem")   # 지난번 우리 값인데 파일 없음
ok("빈 값을 돌려준다", cabundle.ensure(empty) == "")
ok("없는 경로를 환경 변수에 남기지 않는다", "REQUESTS_CA_BUNDLE" not in os.environ)
certifi.where = lambda: (_ for _ in ()).throw(RuntimeError("x"))
ok("certifi 가 터져도 앱은 켜진다", cabundle.ensure(empty) == "")

print("[6] 앱이 켜질 때 맨 먼저 부른다")
src = (_ROOT / "python" / "planner" / "app.py").read_text(encoding="utf-8")
body = src[src.index("def main() -> int:"):]
ok("QApplication 보다 먼저", body.index("cabundle.ensure(") < body.index("QApplication(sys.argv)"))
ok("앱 폴더(base_dir)/certs 에", 'cabundle.ensure(config.base_dir() / "certs")' in body)

print("[7] 고객 서류 '받기 실패' — 까닭을 첫 줄에(지점장: 최근 저장한 고객 두 명 서류)")
os.environ["APPDATA"] = tempfile.mkdtemp()
from planner import kb_files  # noqa: E402


class _R:
    def __init__(self, code, body=b"", ctype="image/png"):
        self.status_code, self.content, self.headers = code, body, {"Content-Type": ctype}


class _Auth:
    def __init__(self, on=True):
        self.on = on

    def is_connected(self):
        return self.on

    def _headers(self):
        return {"Authorization": "Bearer x"}


def _first_line(fn):
    try:
        fn()
        return ""
    except kb_files.KbFileError as e:
        return str(e).splitlines()[0]


_cert = OSError("Could not find a suitable TLS CA certificate bundle, invalid path: C:\\x\\cacert.pem")
kb_files._http = lambda: types.SimpleNamespace(get=lambda *a, **k: (_ for _ in ()).throw(_cert))
m = _first_line(lambda: kb_files.fetch(_Auth(), {"id": "C1", "name": "계약서.jpg"}))
ok("인증서 파일이 없으면 '껐다 켜 주세요'", "보안 인증서 파일이 지워졌습니다" in m and "다시 켜" in m, m)
m = _first_line(lambda: kb_files.fetch(_Auth(False), {"id": "C1", "name": "계약서.jpg"}))
ok("로그인 안 됨보다 연결 오류가 먼저", "보안 인증서" in m, m)
kb_files._http = lambda: types.SimpleNamespace(
    get=lambda url, **k: _R(404) if "googleapis" in url else _R(200, b"<html>", "text/html"))
m = _first_line(lambda: kb_files.fetch(_Auth(), {"id": "C2", "name": "견적서.pdf"}))
ok("다른 계정이 올린 파일이면 그렇게", "이 구글 계정으로는 볼 수 없는 파일" in m and "404" in m, m)
kb_files._http = lambda: types.SimpleNamespace(
    get=lambda url, **k: _R(401) if "googleapis" in url else _R(200, b"<html>", "text/html"))
m = _first_line(lambda: kb_files.fetch(_Auth(), {"id": "C3", "name": "견적서.pdf"}))
ok("로그인 만료면 다시 로그인", "로그인이 만료" in m, m)
m = _first_line(lambda: kb_files.fetch(_Auth(False), {"id": "C3", "name": "견적서.pdf"}))
ok("로그인 안 됐으면 그렇게", "로그인이 되어 있지 않습니다" in m, m)
kb_files._http = lambda: types.SimpleNamespace(get=lambda url, **k: _R(200, b"\x89PNGdata"))
ok("되면 받는다", kb_files.fetch(_Auth(), {"id": "C4", "name": "등록증.png"}).read_bytes() == b"\x89PNGdata")

shutil.rmtree(tmp, ignore_errors=True)
print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
