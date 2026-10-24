"""PC 구글 로그인 · 자동 백업 — 이번 점검에서 고친 것.

[A] 로그인: state 가 다른 응답은 받지 않는다, PKCE(S256) 를 쓴다, 토큰 파일은
    안전하게(원자적으로) 쓴다.
[B] 자동 백업: 계정 확인 전에는 하지 않는다(엉뚱한 공용 폴더를 백업하던 문제),
    실패하면 매초가 아니라 잠시 쉬었다가 다시 한다.
"""
import pathlib as _pl
_ROOT = _pl.Path(__file__).resolve().parents[2]
import sys as _sys
_sys.path.insert(0, str(_ROOT / "python"))
import os as _os
_os.chdir(_ROOT / "python")

import base64
import hashlib
import os
import tempfile
import threading
import time
import types
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from planner import config, google_client  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name
          + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


print("[A1] 동의 화면 주소에 state 와 PKCE 가 붙는다")
state, verifier, challenge = google_client.pkce_pair()
url = google_client.build_auth_url("http://127.0.0.1:9/", ["x-extra"], state, challenge)
q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
ok("state", q.get("state") == state)
ok("code_challenge_method=S256", q.get("code_challenge_method") == "S256")
want = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
ok("challenge = SHA256(verifier)", q.get("code_challenge") == want)
ok("verifier 길이 43~128", 43 <= len(verifier) <= 128, len(verifier))
ok("추가 권한도 담긴다", "x-extra" in q.get("scope", ""))
ok("매번 새로 만든다", google_client.pkce_pair()[0] != state)

print("\n[A2] 콜백 — state 가 다르면 받지 않고, 맞으면 받는다 · 교환에 verifier 를 보낸다")
seen = {}
google_client.webbrowser.open = lambda u: seen.setdefault("url", u)
tok_file = config.data_file("google_token.json")
auth = google_client.GoogleAuth(tok_file)
auth._exchange_code = lambda code, redirect, verifier="": seen.update(
    code=code, redirect=redirect, verifier=verifier)
err = []


def go():
    try:
        auth.authorize(timeout_sec=20)
    except Exception as e:
        err.append(e)


th = threading.Thread(target=go, daemon=True)
th.start()
for _ in range(200):
    if "url" in seen:
        break
    time.sleep(0.02)
q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(seen["url"]).query))
cb = q["redirect_uri"]


def hit(params):
    try:
        with urllib.request.urlopen(cb + "?" + urllib.parse.urlencode(params), timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


ok("다른 state 로 온 코드는 거절(400)", hit({"code": "EVIL", "state": "nope"}) == 400)
ok("state 없는 요청도 거절", hit({"code": "EVIL"}) == 400)
ok("맞는 state 는 받는다(200)", hit({"code": "GOOD", "state": q["state"]}) == 200)
th.join(10)
ok("끼어든 코드가 아니라 맞는 코드로 교환", seen.get("code") == "GOOD", seen.get("code"))
dig = base64.urlsafe_b64encode(hashlib.sha256(seen.get("verifier", "").encode()).digest()).rstrip(b"=").decode()
ok("교환에 verifier 를 보낸다(challenge 와 짝)", dig == q["code_challenge"])
ok("오류 없이 끝남", not err, err)

print("\n[A3] 토큰 파일은 원자적으로 쓴다")
calls = []
_orig = config.atomic_write
config.atomic_write = lambda p, t: (calls.append(p), _orig(p, t))
auth.refresh_token = "R"
auth._save()
config.atomic_write = _orig
ok("atomic_write 를 쓴다", calls and calls[0] == tok_file)
ok("다시 읽힌다", google_client.GoogleAuth(tok_file).refresh_token == "R")

print("\n[B] 자동 백업 — 계정 확인 전엔 안 하고, 실패하면 쉬었다가")
from planner.main_window import MainWindow  # noqa: E402


class G:
    def __init__(self, on):
        self.on = on

    def is_connected(self):
        return self.on


fake = types.SimpleNamespace(gauth=G(True), BACKUP_RETRY_SEC=MainWindow.BACKUP_RETRY_SEC)
tick_ok = lambda: MainWindow._tick_backup_ok(fake)  # noqa: E731
ok("연결됐는데 계정 확인 전 → 틱 백업 안 함", tick_ok() is False)
fake._account_checked = True
ok("계정 확인 뒤 → 틱 백업 함", tick_ok() is True)
fake2 = types.SimpleNamespace(gauth=G(False), BACKUP_RETRY_SEC=600)
ok("연결 안 된 PC 는 바로 함(계정 구분이 없다)", MainWindow._tick_backup_ok(fake2) is True)

n = {"c": 0}


def boom(manual):
    n["c"] += 1
    raise OSError("디스크 가득")


fake._do_backup = boom
MainWindow._backup(fake, manual=False)
ok("실패하면 다시 시도 시각을 미룬다",
   fake._backup_retry_at > datetime.now() + timedelta(seconds=500))
ok("미룬 동안은 틱 백업 안 함", tick_ok() is False)
fake._backup_retry_at = datetime.now() - timedelta(seconds=1)
ok("시간이 지나면 다시 함", tick_ok() is True)
fake._do_backup = lambda manual: None
MainWindow._backup(fake, manual=False)
ok("성공하면 미룸이 풀린다", fake._backup_retry_at == datetime.min)

print()
if FAIL:
    print(f"{len(FAIL)}건 실패")
    raise SystemExit(1)
print("전부 통과")
