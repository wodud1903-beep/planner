"""검사용 가짜 구글(시트·드라이브) — 실제 요청 모양 그대로 받아 흉내 낸다(네트워크 없음).

kbsearch 의 google_auth · sheets_kb · kb_files 는 모두 `net.http()` 로 요청한다.
install() 이 그 세 모듈의 `_http` 를 이 가짜로 바꿔 끼운다.
"""

from __future__ import annotations

import itertools
import json
import urllib.parse

from kbsearch import config, google_auth, kb_files, sheets_kb


class Resp:
    def __init__(self, code=200, body=None, content=b"", headers=None, text=None):
        self.status_code = code
        self._body = body
        self.headers = headers or {}
        if text is not None:
            self.text = text
            self.content = text.encode("utf-8")
        else:
            self.content = content
            self.text = json.dumps(body, ensure_ascii=False) if body is not None else ""
        self.encoding = "utf-8"

    def json(self):
        if self._body is not None:
            return self._body
        return json.loads(self.text) if self.text else {}


class FakeAuth:
    def __init__(self, email="me@example.com"):
        self.email = email

    def is_connected(self):
        return True

    def valid_token(self):
        return "tok"

    def _headers(self):
        return {"Authorization": "Bearer tok"}


class FakeGoogle:
    def __init__(self):
        self.calls = []                 # (메서드, 주소)
        # 시트
        self.tab = True                 # 업무자료 탭이 있나
        self.kb_rows = []               # A:F
        self.kb_g = []                  # G
        self.sheet_code = 200           # 읽기 응답 코드(403 등을 흉내)
        self.put_values = None
        # 드라이브 앱 전용 공간
        self.appdata = {}               # id → {"name", "content"}
        self.appdata_find_code = 200
        self.appdata_read_code = 200
        self.appdata_writes = 0
        # 드라이브 일반 파일(첨부)
        self.files = {}                 # id → bytes
        self.public = set()
        self.trashed = []
        self.renamed = []
        self._ids = itertools.count(1)
        self._pending_upload = {}

    # ---- 끼우기 ----
    def install(self):
        for m in (google_auth, sheets_kb, kb_files):
            m._http = lambda: self
        return self

    # ---- requests.Session 흉내 ----
    def get(self, url, headers=None, params=None, timeout=None, **kw):
        self.calls.append(("GET", url))
        return self._route("GET", url, params=params)

    def post(self, url, headers=None, params=None, json=None, data=None, timeout=None, **kw):
        self.calls.append(("POST", url))
        return self._route("POST", url, params=params, body=json, data=data, headers=headers)

    def put(self, url, headers=None, params=None, json=None, data=None, timeout=None, **kw):
        self.calls.append(("PUT", url))
        return self._route("PUT", url, params=params, body=json, data=data)

    def patch(self, url, headers=None, params=None, json=None, data=None, timeout=None, **kw):
        self.calls.append(("PATCH", url))
        return self._route("PATCH", url, params=params, body=json, data=data)

    def count(self, method, part):
        return sum(1 for m, u in self.calls if m == method and part in u)

    # ---- 길 고르기 ----
    def _route(self, method, url, params=None, body=None, data=None, headers=None):
        params = dict(params or {}) if not isinstance(params, list) else dict(params)
        if url.startswith("https://sheets.googleapis.com"):
            return self._sheets(method, url, body)
        if url.startswith(config.DRIVE_UPLOAD_URL):
            return self._upload(method, url, params, body, data, headers)
        if url.startswith("upload://"):
            fid = f"f{next(self._ids)}"
            self.files[fid] = bytes(data or b"")
            return Resp(200, {"id": fid})
        if url.startswith(config.DRIVE_FILES_URL):
            return self._drive(method, url, params, body)
        if url.startswith("https://drive.google.com/uc"):
            fid = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("id", [""])[0]
            if fid in self.public and fid in self.files:
                return Resp(200, content=self.files[fid], headers={"Content-Type": "image/png"})
            return Resp(200, text="<html>no</html>", headers={"Content-Type": "text/html"})
        return Resp(404, {"error": {"message": "unknown " + url}})

    def _sheets(self, method, url, body):
        rng = urllib.parse.unquote(url.split("/values/")[1]) if "/values/" in url else ""
        if method == "GET" and "/values/" in url:
            if not self.tab:
                return Resp(400, {"error": {"message": "Unable to parse range: '업무자료'!A1:F"}})
            if self.sheet_code != 200:
                return Resp(self.sheet_code, {"error": {"message": "The caller does not have permission"}})
            if "!G" in rng:
                return Resp(200, {"values": [[x] for x in self.kb_g]})
            return Resp(200, {"values": self.kb_rows})
        if method == "GET":           # 시트 정보
            sheets = [{"properties": {"sheetId": 7, "title": config.KB_TAB,
                                      "gridProperties": {"columnCount": 26}}}] if self.tab else []
            return Resp(200, {"sheets": sheets})
        if method == "POST" and url.endswith(":batchUpdate"):
            self.tab = True
            return Resp(200, {})
        if method == "POST" and url.endswith(":clear"):
            self.kb_rows, self.kb_g = [], []
            return Resp(200, {})
        if method == "PUT":
            self.put_values = body["values"]
            self.kb_rows = [r[:6] for r in body["values"]]
            self.kb_g = [r[6] if len(r) > 6 else "" for r in body["values"]]
            return Resp(200, {})
        return Resp(400, {"error": {"message": "?"}})

    def _drive(self, method, url, params, body):
        rest = url[len(config.DRIVE_FILES_URL):].strip("/")
        if method == "GET" and not rest:
            if params.get("spaces") == "appDataFolder":
                if self.appdata_find_code != 200:
                    return Resp(self.appdata_find_code, {"error": {"message": "boom"}})
                name = params.get("q", "").split("'")[1]
                hits = [{"id": i, "name": f["name"]} for i, f in self.appdata.items()
                        if f["name"] == name]
                return Resp(200, {"files": hits})
            return Resp(200, {"files": [{"id": "folder1", "name": "업무자료"}]})
        if method == "GET" and rest:
            fid = rest.split("/")[0]
            if fid in self.appdata:
                if self.appdata_read_code != 200:
                    return Resp(self.appdata_read_code, {"error": {"message": "boom"}})
                return Resp(200, text=self.appdata[fid]["content"])
            if fid in self.files:
                return Resp(200, content=self.files[fid])
            return Resp(404, {"error": {"message": "nf"}})
        if method == "POST" and not rest:
            if (body or {}).get("parents") == ["appDataFolder"]:
                fid = f"a{next(self._ids)}"
                self.appdata[fid] = {"name": body["name"], "content": ""}
                return Resp(200, {"id": fid})
            return Resp(200, {"id": "folder1"})
        if method == "POST" and rest.endswith("/permissions"):
            self.public.add(rest.split("/")[0])
            return Resp(200, {})
        if method == "PATCH":
            fid = rest.split("/")[0]
            if (body or {}).get("trashed"):
                self.trashed.append(fid)
            if (body or {}).get("name"):
                self.renamed.append((fid, body["name"]))
            return Resp(200, {})
        return Resp(400, {"error": {"message": "?"}})

    def _upload(self, method, url, params, body, data, headers):
        rest = url[len(config.DRIVE_UPLOAD_URL):].strip("/")
        if method == "PATCH" and rest in self.appdata:      # 앱 전용 공간 내용 쓰기
            self.appdata[rest]["content"] = (data or b"").decode("utf-8")
            self.appdata_writes += 1
            return Resp(200, {"id": rest})
        if method == "POST" and params.get("uploadType") == "resumable":
            return Resp(200, {}, headers={"Location": "upload://x"})
        return Resp(400, {"error": {"message": "?"}})
