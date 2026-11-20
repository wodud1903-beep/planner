"""검사용 가짜 구글 — Sheets · Drive(appDataFolder · 파일) · Calendar · Tasks · userinfo (v1.32).

일정관리기를 '일반 계정' 으로 **실제로 띄워 보는** 검사가 쓴다(verify_boot_regular · verify_v132).
v1.31.3 점검 때 임시로 만들어 오류를 찾았던 것을 정식 검사로 들였다(지점장 선택 B6) — 새 기능을 만들 때마다
일반 계정으로도 저절로 확인된다. 모든 요청을 LOG 에 남기고, 모르는 주소는 UNKNOWN 에 모은다.
"""
import json
import re
import threading
import urllib.parse

LOG = []          # (method, url)
UNKNOWN = []
LOCK = threading.Lock()


class Resp:
    def __init__(self, status=200, body=None, text=None):
        self.status_code = status
        self._body = body
        self.text = text if text is not None else (json.dumps(body, ensure_ascii=False) if body is not None else "")
        self.content = self.text.encode("utf-8")
        self.headers = {"Content-Type": "application/json"}
        self.ok = 200 <= status < 300

    def json(self):
        if self._body is not None:
            return self._body
        return json.loads(self.text)

    def raise_for_status(self):
        if not self.ok:
            import requests
            raise requests.HTTPError(str(self.status_code))

    def iter_content(self, n=65536):
        yield self.content

    def close(self):
        pass


class World:
    """한 계정이 보는 구글."""

    def __init__(self, email):
        self.email = email
        self.appdata = {}        # name -> {"id", "content"}
        self.sheets = {}         # sheet_id -> {tab: [[...]]}
        self.deny_sheets = set() # 403 을 줄 시트
        self.writes = []         # (kind, target, payload)
        self.status_all = None   # 숫자면 모든 요청에 그 상태
        self.readonly_sheets = set()   # 읽기는 되고 쓰기는 403 인 시트('보기' 로만 공유받음)
        self.can_edit = {}       # 드라이브가 알려 주는 '고칠 수 있나' {시트 id: bool}
        self.calendars = {}      # {캘린더 id: [이벤트 dict]}
        self.cal_list = []       # 내 캘린더 목록 [{id, primary?, selected?}]
        self.created = []        # 새로 만든 스프레드시트 id
        self.trashed = []
        self.gids = {}           # {시트 id: [[gid, 탭 이름], …]}
        self.merges = {}         # {시트 id: {탭: [{startRowIndex, endRowIndex, startColumnIndex, endColumnIndex}]}} (v1.34)
        self.quota_429 = 0       # 이만큼 다음 시트 요청에 429(1분 한도)를 준다(v1.34)
        self.grid_cols = {}      # {시트 id: 열 수} — 그보다 오른쪽 범위는 진짜처럼 400(격자 밖)
        self._n = 0

    def _tabs(self, sid):
        book = self.sheets[sid]
        g = self.gids.setdefault(sid, [])
        have = {t for _g, t in g}
        for t in book:
            if t not in have:
                g.append([max([x[0] for x in g] + [-1]) + 1, t])
        g[:] = [x for x in g if x[1] in book]
        return g

    def _id(self):
        self._n += 1
        return f"F{self._n}"

    # ---- 라우팅 ----
    def handle(self, method, url, params=None, headers=None, data=None, json_body=None):
        with LOCK:
            return self._handle(method, url, params or {}, data, json_body)

    def _handle(self, method, url, params, data, json_body):
        if isinstance(params, (list, tuple)):
            plist = list(params)
            pdict = {}
            for k, v in plist:
                pdict.setdefault(k, v)
        else:
            plist = list(params.items())
            pdict = dict(params)
        u = urllib.parse.unquote(url)
        LOG.append((method, u, pdict))
        if self.status_all:
            return Resp(self.status_all, {"error": {"message": "down"}})
        if "oauth2/v3/userinfo" in u or "openidconnect" in u:
            return Resp(200, {"email": self.email})
        if "oauth2.googleapis.com/token" in u:
            return Resp(200, {"access_token": "AT", "expires_in": 3600})
        # ---- Sheets ----
        if "sheets.googleapis.com" in u and u.rstrip("/").endswith("/v4/spreadsheets") and method == "POST":
            sid = "NEW" + self._id()
            self.sheets[sid] = {"Sheet1": []}
            self.created.append((sid, ((json_body or {}).get("properties") or {}).get("title", "")))
            return Resp(200, {"spreadsheetId": sid, "sheets": [{"properties": {"sheetId": self._tabs(sid)[0][0]}}]})
        m = re.search(r"/spreadsheets/([^/:?]+)(.*)$", u)
        if "sheets.googleapis.com" in u and m:
            sid, rest = m.group(1), m.group(2)
            if sid in self.readonly_sheets and method != "GET":
                return Resp(403, {"error": {"message": "The caller does not have permission", "status": "PERMISSION_DENIED"}})
            if sid in self.deny_sheets:
                return Resp(403, {"error": {"message": "The caller does not have permission", "status": "PERMISSION_DENIED"}})
            book = self.sheets.get(sid)
            if book is None:
                return Resp(404, {"error": {"message": "Requested entity was not found.", "status": "NOT_FOUND"}})
            if self.quota_429 > 0:
                self.quota_429 -= 1
                return Resp(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message":
                                            "Quota exceeded for quota metric 'Read requests' and limit 'Read requests "
                                            "per minute per user' of service 'sheets.googleapis.com'"}})
            if method == "GET" and sid in self.grid_cols and ("/values/" in rest or "/values:batchGet" in rest):
                want = [v for k, v in plist if k == "ranges"] or [rest[len("/values/"):].split("?")[0]]
                if any(self._beyond(r, self.grid_cols[sid]) for r in want):
                    return Resp(400, {"error": {"message": "Range exceeds grid limits.", "status": "INVALID_ARGUMENT"}})
            if method == "GET" and rest.startswith("/values:batchGet"):
                rngs = [v for k, v in plist if k == "ranges"]
                return Resp(200, {"valueRanges": [{"range": r, "values": self._range(book, r)} for r in rngs]})
            if method == "GET" and rest.startswith("/values/"):
                rng = rest[len("/values/"):].split("?")[0]
                vals = self._range(book, rng)
                if vals is None:
                    return Resp(400, {"error": {"message": f"Unable to parse range: {rng}", "status": "INVALID_ARGUMENT"}})
                return Resp(200, {"range": rng, "values": vals})
            if method == "GET":
                return Resp(200, {"properties": {"title": "시트"}, "sheets": [
                    dict({"properties": {"sheetId": g, "title": t, "gridProperties": {"rowCount": 1000, "columnCount": 26}}},
                         **({"merges": self.merges[sid][t]} if t in self.merges.get(sid, {}) else {}))
                    for g, t in self._tabs(sid)]})
            self.writes.append(("sheet", sid + rest, json_body if json_body is not None else data))
            # 값 쓰기는 시트에도 담는다(v1.33 — 다시 읽었을 때 그대로 보이게)
            if method == "PUT" and rest.startswith("/values/"):
                self._put(book, rest[len("/values/"):].split("?")[0], (json_body or {}).get("values") or [])
                return Resp(200, {})
            if rest.startswith("/values:batchUpdate"):
                for d in (json_body or {}).get("data", []):
                    self._put(book, d.get("range", ""), d.get("values") or [])
                return Resp(200, {})
            mm = re.match(r"/sheets/(\d+):copyTo", rest)
            if mm:
                src = next((t for g, t in self._tabs(sid) if g == int(mm.group(1))), None)
                dest = (json_body or {}).get("destinationSpreadsheetId", "")
                if src is None or dest not in self.sheets:
                    return Resp(404, {"error": {"message": "not found"}})
                name = src + "의 사본"
                self.sheets[dest][name] = [list(r) for r in book[src]]
                return Resp(200, {"sheetId": next(g for g, t in self._tabs(dest) if t == name), "title": name})
            if rest.startswith(":batchUpdate"):
                for rq in (json_body or {}).get("requests", []):
                    if "deleteDimension" in rq:
                        rg = rq["deleteDimension"]["range"]
                        tab = next(t for g, t in self._tabs(sid) if g == rg["sheetId"])
                        del book[tab][rg["startIndex"]:rg["endIndex"]]
                    elif "deleteSheet" in rq:
                        tab = next(t for g, t in self._tabs(sid) if g == rq["deleteSheet"]["sheetId"])
                        del book[tab]
                    elif "updateSheetProperties" in rq:
                        pr = rq["updateSheetProperties"]["properties"]
                        ent = next(x for x in self._tabs(sid) if x[0] == pr["sheetId"])
                        book[pr["title"]] = book.pop(ent[1])
                        ent[1] = pr["title"]
            return Resp(200, {})
        # ---- Drive ----
        if "googleapis.com/upload/drive" in u:
            m = re.search(r"/files/([^/?]+)", u)
            if m:
                for f in self.appdata.values():
                    if f["id"] == m.group(1):
                        f["content"] = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else str(data)
                        self.writes.append(("appdata", f["name"], f["content"]))
                        return Resp(200, {"id": f["id"]})
                return Resp(404, {"error": {"message": "File not found"}})
            self.writes.append(("upload", u, None))
            return Resp(200, {"id": self._id(), "name": "up"})
        if "googleapis.com/drive/v3/files" in u:
            m = re.search(r"/files/([^/?]+)", u)
            if m:
                fid = m.group(1)
                for f in self.appdata.values():
                    if f["id"] == fid:
                        if pdict.get("alt") == "media":
                            return Resp(200, text=f["content"])
                        return Resp(200, {"id": fid, "name": f["name"]})
                if fid in self.can_edit and "capabilities" in str(pdict.get("fields", "")):
                    return Resp(200, {"capabilities": {"canEdit": self.can_edit[fid]}})
                if method in ("PATCH", "DELETE") and any(fid == c[0] for c in self.created):
                    self.trashed.append(fid)
                    return Resp(200, {"id": fid})
                return Resp(404, {"error": {"message": "File not found"}})
            if method == "POST":
                name = (json_body or {}).get("name", "")
                f = {"id": self._id(), "name": name, "content": ""}
                if "appDataFolder" in ((json_body or {}).get("parents") or []):
                    self.appdata[name] = f
                return Resp(200, {"id": f["id"]})
            q = pdict.get("q", "")
            if pdict.get("spaces") == "appDataFolder":
                mm = re.search(r"name='([^']+)'", q)
                f = self.appdata.get(mm.group(1)) if mm else None
                return Resp(200, {"files": [{"id": f["id"], "name": f["name"], "modifiedTime": "2026-11-10T00:00:00Z"}] if f else []})
            return Resp(200, {"files": []})
        if "calendar/v3/users/me/calendarList" in u:
            return Resp(200, {"items": list(self.cal_list)})
        mc = re.search(r"calendar/v3/calendars/([^/]+)/events", u)
        if mc:
            cid = mc.group(1)
            if cid not in self.calendars:
                return Resp(404, {"error": {"message": "Not Found"}}) if self.calendars or self.cal_list else Resp(200, {"items": []})
            return Resp(200, {"items": list(self.calendars[cid])})
        if "calendar/v3" in u:
            return Resp(200, {"items": []})
        if "tasks.googleapis.com" in u or "/tasks/v1" in u:
            return Resp(200, {"items": []})
        if "docs.googleapis.com" in u:
            return Resp(403, {"error": {"message": "The caller does not have permission", "status": "PERMISSION_DENIED"}})
        if "api.github.com" in u:
            return Resp(404, {})
        UNKNOWN.append((method, u))
        return Resp(404, {"error": {"message": "unknown in fake"}})

    @staticmethod
    def _put(book, rng, values):
        """'탭'!A5 · A5:C5 범위에 값을 적는다(시트처럼 줄·칸을 늘려 가며)."""
        rng = rng.strip()
        tab, a1 = (rng.rsplit("!", 1) if "!" in rng else (None, rng))
        tab = tab.strip("'") if tab else next(iter(book), None)
        m = re.match(r"([A-Z]+)(\d+)", a1)
        if not m or tab is None:
            return
        c0 = 0
        for ch in m.group(1):
            c0 = c0 * 26 + ord(ch) - 64
        c0 -= 1
        r0 = int(m.group(2)) - 1
        rows = book.setdefault(tab, [])
        for i, vr in enumerate(values):
            while len(rows) <= r0 + i:
                rows.append([])
            row = rows[r0 + i]
            for j, v in enumerate(vr):
                while len(row) <= c0 + j:
                    row.append("")
                row[c0 + j] = v

    @staticmethod
    def _beyond(rng, ncols):
        """범위의 오른쪽 끝 열이 격자(ncols 열) 밖인가."""
        a1 = rng.rsplit("!", 1)[-1]
        letters = re.findall(r"[A-Z]+", a1)
        if not letters:
            return False
        n = 0
        for ch in letters[-1]:
            n = n * 26 + ord(ch) - 64
        return n > ncols

    @staticmethod
    def _range(book, rng):
        rng = rng.strip()
        tab = None
        a1 = rng
        if "!" in rng:
            tab, a1 = rng.rsplit("!", 1)
            tab = tab.strip("'")
        if tab is None:
            tab = next(iter(book), None)
        rows = book.get(tab)
        if rows is None:
            return None
        one = re.match(r"([A-Z]+)(\d+)$", a1)
        if one:                                       # 한 칸('U5') — 진짜 시트처럼 그 칸만
            a1 = f"{one.group(1)}{one.group(2)}:{one.group(1)}{one.group(2)}"
        m = re.match(r"([A-Z]+)(\d*):([A-Z]+)(\d*)$", a1)
        if not m:
            return rows

        def col(s):
            n = 0
            for ch in s:
                n = n * 26 + ord(ch) - 64
            return n - 1
        c0, r0, c1, r1 = col(m.group(1)), int(m.group(2) or 1) - 1, col(m.group(3)), (int(m.group(4)) if m.group(4) else None)
        out = []
        for row in rows[r0:r1]:
            out.append(list(row[c0:c1 + 1]))
        while out and not any(str(c).strip() for c in out[-1]):
            out.pop()
        return out


class Session:
    def __init__(self, world):
        self.w = world

    def get(self, url, **kw):
        return self.w.handle("GET", url, kw.get("params"), kw.get("headers"))

    def post(self, url, **kw):
        return self.w.handle("POST", url, kw.get("params"), kw.get("headers"), kw.get("data"), kw.get("json"))

    def put(self, url, **kw):
        return self.w.handle("PUT", url, kw.get("params"), kw.get("headers"), kw.get("data"), kw.get("json"))

    def patch(self, url, **kw):
        return self.w.handle("PATCH", url, kw.get("params"), kw.get("headers"), kw.get("data"), kw.get("json"))

    def delete(self, url, **kw):
        return self.w.handle("DELETE", url, kw.get("params"), kw.get("headers"))

    def request(self, method, url, **kw):
        return self.w.handle(method.upper(), url, kw.get("params"), kw.get("headers"), kw.get("data"), kw.get("json"))

    def close(self):
        pass
