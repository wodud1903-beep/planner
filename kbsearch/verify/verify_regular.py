"""일반(관리자가 아닌) 계정에서의 오류들(kb-v1.8.1 점검에서 찾아 고친 것).

  · 구글 동의 화면에서 항목을 빼고 로그인하면 아무 말 없이 동기화만 안 됐다 → 로그인 직후 알린다.
  · 회사 자료를 '내 계정에서만' 고쳐 저장한 뒤 계정에 올라갔는지 알 수 없었다 → 결과를 알린다.
  · 웹·일정관리기에서 고친 것을 10분마다만 받았다 → 2분마다.
"""
import pathlib as _pl
import sys as _sys

_HERE = _pl.Path(__file__).resolve().parent
_sys.path.insert(0, str(_HERE.parent))
_sys.path.insert(0, str(_HERE))

import json  # noqa: E402
import os  # noqa: E402
import tempfile  # noqa: E402

os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from kbsearch import config, google_auth  # noqa: E402
from kbsearch.main_window import MainWindow  # noqa: E402

FAIL = []


def ok(name, cond, extra=""):
    print(("  OK  " if cond else "  ** FAIL ** ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


SH, AD, FL = config.SCOPE_SHEETS, "https://www.googleapis.com/auth/drive.appdata", "https://www.googleapis.com/auth/drive.file"
print("[1] 로그인할 때 빠진 권한")
ok("이름표가 요청하는 권한을 다 덮는다",
   all(sc in config.SCOPE_LABELS for sc in config.GOOGLE_SCOPES if sc not in ("openid", "email")))
tok = config.data_file("google_token.json")


def auth_with(scopes, rt="RT"):
    tok.write_text(json.dumps({"refresh_token": rt, "email": "staff@example.com", "scopes": scopes}), encoding="utf-8")
    return google_auth.GoogleAuth(tok)


ok("다 받았으면 없음", auth_with(["openid", SH, AD, FL]).missing_scopes() == [])
a = auth_with(["openid", SH])
ok("동기화·첨부를 뺐다", len(a.missing_scopes()) == 2 and "동기화" in a.missing_scopes()[0], a.missing_scopes())
ok("모르는 옛 토큰(권한 목록 없음)은 알리지 않는다", auth_with([]).missing_scopes() == [] and auth_with([]).has_scope(SH))
ok("시트 권한이 빠졌는지 안다", not auth_with([AD, FL]).has_scope(SH) and auth_with([SH]).has_scope(SH))
a = auth_with([SH, AD])
a._save()
ok("받은 권한을 저장해 둔다", json.loads(tok.read_text(encoding="utf-8"))["scopes"] == [SH, AD])
a.disconnect()
ok("로그아웃하면 지운다", json.loads(tok.read_text(encoding="utf-8"))["scopes"] == [])


class R:
    status_code = 200
    text = ""

    def json(self):
        return {"access_token": "AT", "refresh_token": "RT2", "expires_in": 3600, "scope": f"openid {SH}"}


class H:
    def post(self, *a, **k):
        return R()


google_auth._http = lambda: H()
a = auth_with([])
a._exchange_code("code", "http://127.0.0.1/")
ok("로그인(토큰 교환) 때 실제로 받은 권한을 적는다", a.scopes == ["openid", SH] and len(a.missing_scopes()) == 2)
src = (_HERE.parent / "kbsearch" / "main_window.py").read_text(encoding="utf-8")
i = src.index("def _on_login")
ok("로그인 직후 빠진 권한을 알린다(모두 선택)", "missing_scopes()" in src[i:i + 1600] and "모두 선택" in src[i:i + 1600])

print("[2] 고친 자료 — 올린 결과를 알린다 · 2분마다 받는다")


class V:
    def reload(self):
        pass


class Fake:
    def __init__(self):
        self._busy = True
        self._edits_announce = False
        self._quick = None
        self.view = V()
        self.msgs = []

    def _set_msg(self, t, k=""):
        self.msgs.append((t, k))

    def refresh_account(self):
        pass


f = Fake()
f._edits_announce = True
MainWindow._on_edits(f, [], "")
ok("고쳐 저장한 뒤 올렸으면 알린다", f.msgs == [("내 계정에 저장했습니다 — 웹·일정관리기에도 반영됩니다", "ok")]
   and f._busy is False and f._edits_announce is False, f.msgs)
f = Fake()
f._edits_announce = True
MainWindow._on_edits(f, [], "Drive 403")
ok("못 올렸으면 그렇게 알린다(이 PC 에는 저장됨)", len(f.msgs) == 1 and f.msgs[0][1] == "bad" and "올리지 못했습니다" in f.msgs[0][0])
f = Fake()
MainWindow._on_edits(f, [], "Drive 403")
MainWindow._on_edits(f, [], "")
ok("저절로 맞출 때(몇 분마다)는 조용히", f.msgs == [])
f = Fake()
MainWindow._on_edits(f, ["메리츠캐피탈"], "")
ok("다른 곳에서 고친 것을 받으면 알린다", "메리츠캐피탈" in f.msgs[0][0] and "받았습니다" in f.msgs[0][0])
ok("2분마다 맞춘다", "self._edits_timer.start(2 * 60 * 1000)" in src)
ok("저장 뒤 결과를 알리게 표시한다", "self._edits_announce = True" in src)

print()
print("실패:", FAIL if FAIL else "없음")
_sys.exit(1 if FAIL else 0)
