"""구글 로그인 (OAuth 2.0 Desktop / Loopback) + 드라이브 앱 전용 공간.

일정관리기 google_client.py 에서 로그인과 appDataFolder 부분만 옮겨 왔다.
캘린더·할일은 없다. 로그인은 [동기화] 를 처음 누를 때만 한다.

흐름
----
1. 로컬 HTTP 서버(127.0.0.1:임의포트)를 띄우고 기본 브라우저로 구글 동의 화면을 연다.
2. 동의하면 구글이 http://127.0.0.1:PORT/?code=... 로 돌려보낸다.
3. code 를 access_token / refresh_token 으로 바꾸고 refresh_token 을 저장한다.
"""

from __future__ import annotations

import http.server
import json
import threading
import time
import urllib.parse
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from . import config
from .net import http as _http


class GoogleError(Exception):
    pass


class LoginCancelled(GoogleError):
    pass


# ---------------------------------------------------------------------------
# 콜백 수신용 초경량 HTTP 핸들러
# ---------------------------------------------------------------------------
class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    server_version = "KbSearchOAuth/1.0"

    def do_GET(self):  # noqa: N802
        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        code = params.get("code", [""])[0]
        err = params.get("error", [""])[0]
        # 우리가 보낸 state 를 그대로 들고 온 응답만 받는다(다른 프로그램이 끼어들지 못하게)
        want = getattr(self.server, "expect_state", "")
        if want and params.get("state", [""])[0] != want:
            self.send_response(400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("잘못된 요청입니다.".encode("utf-8"))
            return
        self.server.auth_code = code  # type: ignore[attr-defined]
        self.server.auth_error = err  # type: ignore[attr-defined]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if code:
            body = "<h2>로그인 완료</h2><p>이 창을 닫고 업무자료검색으로 돌아가세요.</p>"
        else:
            body = f"<h2>로그인 실패</h2><p>{err}</p>"
        self.wfile.write(
            ("<html><body style='font-family:sans-serif;text-align:center;"
             f"padding-top:60px'>{body}</body></html>").encode("utf-8"))

    def log_message(self, *args):
        pass


def pkce_pair() -> tuple[str, str, str]:
    """(state, code_verifier, code_challenge) — 로그인 한 번에 한 벌씩 새로 만든다."""
    import base64
    import hashlib
    import secrets
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return state, verifier, challenge


def build_auth_url(redirect: str, state: str, challenge: str) -> str:
    return config.AUTH_ENDPOINT + "?" + urllib.parse.urlencode({
        "client_id": config.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": " ".join(config.GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })


class GoogleAuth:
    """토큰 보관 + OAuth 로그인 + 자동 갱신. 로그인한 계정 이메일도 같이 둔다."""

    def __init__(self, cfg_file: Path):
        self.cfg_file = cfg_file
        self.refresh_token = ""
        self.access_token = ""
        self.email = ""
        self.token_expiry = datetime.min
        self._refresh_lock = threading.Lock()
        self._load()

    # ---- 토큰 저장 ----
    def _load(self):
        if not self.cfg_file.exists():
            return
        try:
            o = json.loads(self.cfg_file.read_text(encoding="utf-8"))
            self.refresh_token = o.get("refresh_token", "")
            self.email = o.get("email", "")
        except Exception:
            pass

    def _save(self):
        try:
            config.atomic_write(
                self.cfg_file,
                json.dumps({"refresh_token": self.refresh_token, "email": self.email},
                           ensure_ascii=False))
        except Exception:
            pass

    def is_connected(self) -> bool:
        return bool(self.refresh_token)

    def disconnect(self):
        self.refresh_token = ""
        self.access_token = ""
        self.email = ""
        self.token_expiry = datetime.min
        self._save()

    # ---- 로그인 ----
    def authorize(self, timeout_sec: int = 180,
                  cancel: Optional[threading.Event] = None) -> str:
        """브라우저 동의 흐름. 성공하면 계정 이메일을 돌려준다. 실패 시 GoogleError."""
        httpd = None
        port = 0
        for p in config.REDIRECT_PORT_RANGE:
            try:
                httpd = http.server.HTTPServer(("127.0.0.1", p), _CallbackHandler)
                port = p
                break
            except OSError:
                continue
        if httpd is None:
            raise GoogleError("로컬 콜백 포트를 열 수 없습니다.")

        httpd.auth_code = ""      # type: ignore[attr-defined]
        httpd.auth_error = ""     # type: ignore[attr-defined]
        httpd.timeout = 1
        state, verifier, challenge = pkce_pair()
        httpd.expect_state = state  # type: ignore[attr-defined]

        redirect = f"http://127.0.0.1:{port}/"
        webbrowser.open(build_auth_url(redirect, state, challenge))

        started = time.monotonic()
        try:
            while not httpd.auth_code and not httpd.auth_error:  # type: ignore[attr-defined]
                if cancel is not None and cancel.is_set():
                    raise LoginCancelled("로그인을 취소했습니다.")
                if time.monotonic() - started > timeout_sec:
                    break
                httpd.handle_request()
        finally:
            httpd.server_close()

        if httpd.auth_error:  # type: ignore[attr-defined]
            raise GoogleError(f"로그인이 거부되었습니다: {httpd.auth_error}")  # type: ignore[attr-defined]
        if not httpd.auth_code:  # type: ignore[attr-defined]
            raise GoogleError("로그인 시간이 지났습니다. 다시 [동기화] 를 눌러 주세요.")

        self._exchange_code(httpd.auth_code, redirect, verifier)  # type: ignore[attr-defined]
        self.email = fetch_email(self)
        self._save()
        return self.email

    def _exchange_code(self, code: str, redirect: str, verifier: str = "") -> None:
        data = {
            "code": code,
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect,
            "grant_type": "authorization_code",
        }
        if verifier:
            data["code_verifier"] = verifier
        resp = _http().post(config.TOKEN_ENDPOINT, data=data, timeout=30)
        if resp.status_code != 200:
            raise GoogleError(f"토큰 교환 실패: {resp.text[:300]}")
        j = resp.json()
        self.access_token = j.get("access_token", "")
        self.refresh_token = j.get("refresh_token", "") or self.refresh_token
        self.token_expiry = datetime.now() + timedelta(seconds=int(j.get("expires_in", 3600)) - 60)
        if not self.refresh_token:
            raise GoogleError("refresh_token 을 받지 못했습니다. "
                              "구글 계정의 앱 권한을 해제한 뒤 다시 시도하세요.")
        self._save()

    def _refresh(self) -> None:
        if not self.refresh_token:
            raise GoogleError("로그인되어 있지 않습니다. [동기화] 를 눌러 로그인하세요.")
        resp = _http().post(config.TOKEN_ENDPOINT, data={
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        }, timeout=30)
        if resp.status_code != 200:
            if "invalid_grant" in resp.text:
                self.refresh_token = ""
                self._save()
                raise GoogleError("구글 로그인이 만료되었습니다. [동기화] 를 눌러 다시 로그인하세요.")
            raise GoogleError(f"로그인 갱신 실패: {resp.text[:300]}")
        j = resp.json()
        self.access_token = j.get("access_token", "")
        self.token_expiry = datetime.now() + timedelta(seconds=int(j.get("expires_in", 3600)) - 60)

    def valid_token(self) -> str:
        if self.access_token and datetime.now() < self.token_expiry:
            return self.access_token
        with self._refresh_lock:
            if self.access_token and datetime.now() < self.token_expiry:
                return self.access_token
            self._refresh()
        return self.access_token

    def _headers(self) -> dict:
        return {"Authorization": "Bearer " + self.valid_token()}


def fetch_email(auth: GoogleAuth) -> str:
    """로그인 계정 이메일. 실패하면 오류 — 이메일 없이는 관리자인지·누구 메모인지 모른다."""
    last = ""
    for wait in (0, 2):
        if wait:
            time.sleep(wait)
        try:
            r = _http().get(config.USERINFO_URL, headers=auth._headers(), timeout=15)
            if r.status_code == 200:
                email = (r.json().get("email") or "").strip().lower()
                if email:
                    return email
            last = f"HTTP {r.status_code}"
        except GoogleError:
            raise
        except Exception as e:
            last = str(e)
    raise GoogleError(f"로그인한 계정의 이메일을 확인하지 못했습니다 ({last}).")


# ---------------------------------------------------------------------------
# Drive appDataFolder — 일정관리기와 같은 '앱 전용 숨김 공간'
#
# 같은 OAuth 클라이언트라 일정관리기가 쓰는 공간과 **같은 곳**이다(sync.py).
# 오류는 반드시 예외로 올린다. '못 읽음' 을 '없음' 으로 착각해 새 묶음을 쓰면
# 일정관리기의 할일·멘트까지 담긴 묶음을 덮어쓰게 된다.
# ---------------------------------------------------------------------------
def appdata_find(auth: GoogleAuth, name: str) -> Optional[str]:
    """이름으로 파일 id 를 찾는다. 없으면 None, 조회가 안 되면 GoogleError."""
    r = _http().get(config.DRIVE_FILES_URL, headers=auth._headers(), timeout=20, params={
        "spaces": "appDataFolder",
        "q": f"name='{name}'",
        "fields": "files(id,name,modifiedTime)",
    })
    if r.status_code != 200:
        raise GoogleError(f"드라이브 조회 실패 (HTTP {r.status_code})")
    files = (r.json() or {}).get("files", [])
    return files[0]["id"] if files else None


def appdata_read(auth: GoogleAuth, file_id: str) -> str:
    r = _http().get(f"{config.DRIVE_FILES_URL}/{file_id}", headers=auth._headers(),
                    timeout=30, params={"alt": "media"})
    if r.status_code != 200:
        raise GoogleError(f"드라이브에서 받지 못했습니다 (HTTP {r.status_code})")
    r.encoding = "utf-8"
    return r.text


def appdata_write(auth: GoogleAuth, name: str, content: str,
                  file_id: Optional[str] = None) -> str:
    """appDataFolder 의 파일을 갱신(id 가 없으면 새로 만든다). file_id 를 돌려준다."""
    fid = file_id
    if not fid:
        meta = _http().post(config.DRIVE_FILES_URL, headers=auth._headers(), timeout=20,
                            json={"name": name, "parents": ["appDataFolder"]})
        if meta.status_code not in (200, 201):
            raise GoogleError(f"드라이브에 파일을 만들지 못했습니다 (HTTP {meta.status_code})")
        fid = meta.json()["id"]
    hdr = auth._headers()
    hdr["Content-Type"] = "application/json; charset=UTF-8"
    up = _http().patch(f"{config.DRIVE_UPLOAD_URL}/{fid}", headers=hdr, timeout=30,
                       params={"uploadType": "media"}, data=content.encode("utf-8"))
    if up.status_code not in (200, 201):
        raise GoogleError(f"드라이브에 올리지 못했습니다 (HTTP {up.status_code})")
    return fid
