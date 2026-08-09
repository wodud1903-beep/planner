"""구글 연동 (OAuth 2.0 Desktop / Loopback).

델파이 uGoogleTasks.pas 의 흐름을 그대로 파이썬으로 옮기되,
Client ID/Secret 을 앱에 내장(config)하여 직원이 [Google 로그인] 한 번으로
끝나도록 했다.  캘린더는 ICS 대신 Calendar API 로 실시간 조회한다.

핵심 흐름
---------
1. [Google 로그인] → 로컬 HTTP 서버(127.0.0.1:임의포트)를 띄운다.
2. 기본 브라우저로 구글 동의 화면을 연다.
3. 동의하면 구글이 http://127.0.0.1:PORT/?code=... 로 리다이렉트.
4. code 를 access_token / refresh_token 으로 교환.
5. refresh_token 을 저장하고 이후 자동 갱신.
"""

from __future__ import annotations

import http.server
import socket
import threading
import urllib.parse
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import requests

from . import config


# ---------------------------------------------------------------------------
# 자료형
# ---------------------------------------------------------------------------
@dataclass
class CalEvent:
    start: datetime
    has_time: bool
    summary: str
    uid: str = ""

    def time_text(self) -> str:
        return self.start.strftime("%H:%M") if self.has_time else "종일"


@dataclass
class GoogleTask:
    id: str
    list_id: str
    title: str
    notes: str = ""
    due: Optional[date] = None
    has_due: bool = False
    list_name: str = ""


class GoogleError(Exception):
    pass


# ---------------------------------------------------------------------------
# 콜백 수신용 초경량 HTTP 핸들러
# ---------------------------------------------------------------------------
class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    server_version = "PlannerOAuth/1.0"

    def do_GET(self):  # noqa: N802
        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        code = params.get("code", [""])[0]
        err = params.get("error", [""])[0]
        self.server.auth_code = code  # type: ignore[attr-defined]
        self.server.auth_error = err  # type: ignore[attr-defined]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if code:
            body = "<h2>인증 완료</h2><p>이 창을 닫고 프로그램으로 돌아가세요.</p>"
        else:
            body = f"<h2>인증 실패</h2><p>{err}</p>"
        self.wfile.write(
            ("<html><body style='font-family:sans-serif;text-align:center;"
             f"padding-top:60px'>{body}</body></html>").encode("utf-8")
        )

    def log_message(self, *args):  # 콘솔 로그 억제
        pass


class GoogleAuth:
    """토큰 보관 + OAuth 로그인 + 자동 갱신."""

    def __init__(self, cfg_file: Path):
        self.cfg_file = cfg_file
        self.refresh_token = ""
        self.access_token = ""
        self.token_expiry = datetime.min
        self._refresh_lock = threading.Lock()
        self._load()

    # ---- 토큰 저장 ----
    def _load(self):
        if not self.cfg_file.exists():
            return
        try:
            import json
            o = json.loads(self.cfg_file.read_text(encoding="utf-8"))
            self.refresh_token = o.get("refresh_token", "")
        except Exception:
            pass

    def _save(self):
        try:
            import json
            self.cfg_file.write_text(
                json.dumps({"refresh_token": self.refresh_token}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    def is_connected(self) -> bool:
        return bool(self.refresh_token)

    def disconnect(self):
        self.refresh_token = ""
        self.access_token = ""
        self.token_expiry = datetime.min
        self._save()

    # ---- 로그인 ----
    def authorize(self, timeout_sec: int = 120) -> None:
        """브라우저 동의 흐름. 실패 시 GoogleError."""
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

        redirect = f"http://127.0.0.1:{port}/"
        auth_url = config.AUTH_ENDPOINT + "?" + urllib.parse.urlencode({
            "client_id": config.GOOGLE_CLIENT_ID,
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": " ".join(config.GOOGLE_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
        })

        webbrowser.open(auth_url)

        # code 수신 대기
        import time as _time
        waited = 0.0
        try:
            while not httpd.auth_code and not httpd.auth_error and waited < timeout_sec:  # type: ignore[attr-defined]
                httpd.handle_request()
                waited += 1.0
        finally:
            httpd.server_close()

        if httpd.auth_error:  # type: ignore[attr-defined]
            raise GoogleError(f"인증이 거부되었습니다: {httpd.auth_error}")  # type: ignore[attr-defined]
        if not httpd.auth_code:  # type: ignore[attr-defined]
            raise GoogleError("인증 시간이 초과되었습니다. 다시 시도하세요.")

        self._exchange_code(httpd.auth_code, redirect)  # type: ignore[attr-defined]

    def _exchange_code(self, code: str, redirect: str) -> None:
        resp = requests.post(config.TOKEN_ENDPOINT, data={
            "code": code,
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect,
            "grant_type": "authorization_code",
        }, timeout=30)
        if resp.status_code != 200:
            raise GoogleError(f"토큰 교환 실패: {resp.text}")
        j = resp.json()
        self.access_token = j.get("access_token", "")
        self.refresh_token = j.get("refresh_token", "") or self.refresh_token
        self.token_expiry = datetime.now() + timedelta(seconds=int(j.get("expires_in", 3600)) - 60)
        self._save()
        if not self.refresh_token:
            raise GoogleError("refresh_token 을 받지 못했습니다. 구글 계정 권한을 해제 후 다시 시도하세요.")

    def _refresh(self) -> None:
        if not self.refresh_token:
            raise GoogleError("연결되지 않았습니다. [Google 로그인]을 먼저 하세요.")
        resp = requests.post(config.TOKEN_ENDPOINT, data={
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        }, timeout=30)
        if resp.status_code != 200:
            if "invalid_grant" in resp.text:
                self.refresh_token = ""
                self._save()
                raise GoogleError("구글 연결이 만료되었습니다. 다시 로그인하세요.")
            raise GoogleError(f"access_token 갱신 실패: {resp.text}")
        j = resp.json()
        self.access_token = j.get("access_token", "")
        self.token_expiry = datetime.now() + timedelta(seconds=int(j.get("expires_in", 3600)) - 60)

    def valid_token(self) -> str:
        if self.access_token and datetime.now() < self.token_expiry:
            return self.access_token
        # 병렬 요청이 동시에 갱신하지 않도록 잠금 (한 번만 refresh)
        with self._refresh_lock:
            if self.access_token and datetime.now() < self.token_expiry:
                return self.access_token
            self._refresh()
        return self.access_token

    def _headers(self) -> dict:
        return {"Authorization": "Bearer " + self.valid_token()}


# ---------------------------------------------------------------------------
# 데이터 조회/수정
# ---------------------------------------------------------------------------
def _parse_rfc3339(s: str) -> tuple[Optional[datetime], bool]:
    """캘린더 start/end 또는 task due 문자열 → (datetime, has_time)."""
    if not s:
        return None, False
    # 날짜만: 'YYYY-MM-DD'
    if len(s) == 10:
        try:
            return datetime.strptime(s, "%Y-%m-%d"), False
        except Exception:
            return None, False
    # 날짜+시간 (타임존 포함 가능)
    try:
        s2 = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s2)
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt, True
    except Exception:
        # 앞 10자만이라도
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d"), False
        except Exception:
            return None, False


def fetch_calendar_events(auth: GoogleAuth, back_days: int = 0,
                          forward_days: int = 7) -> list[CalEvent]:
    """(오늘-back_days) ~ (오늘+forward_days) 구간의 캘린더 이벤트.

    - forward_days: 주간 뷰 표시용(기본 7일)
    - back_days: 계약 후 팔로업 스캔용 과거 구간(출고 일정이 과거이므로 필요)

    속도 최적화:
      - 보이는(선택된) 캘린더 + 기본 캘린더만 조회 (숨긴 구독/공휴일 제외)
      - 캘린더별 요청을 스레드풀로 병렬 처리
      - 필요한 필드만(fields) 받아 응답 크기 축소
    """
    token = auth.valid_token()  # 병렬 진입 전 토큰 준비(갱신 1회)
    headers = {"Authorization": "Bearer " + token}
    today = date.today()
    base = datetime(today.year, today.month, today.day)
    time_min = (base - timedelta(days=back_days)).astimezone().isoformat()
    time_max = (base + timedelta(days=forward_days)).astimezone().isoformat()

    # 1) 캘린더 목록 (선택된 것 위주)
    r = requests.get(config.CALENDAR_LIST_URL, headers=headers, timeout=20,
                     params={"fields": "items(id,selected,primary)"})
    if r.status_code != 200:
        raise GoogleError(f"캘린더 목록 조회 실패 (HTTP {r.status_code})")
    cal_ids = [c["id"] for c in r.json().get("items", [])
               if c.get("id") and (c.get("selected") or c.get("primary"))]
    if not cal_ids:  # 선택 정보가 없으면 전부 조회
        cal_ids = [c["id"] for c in r.json().get("items", []) if c.get("id")]

    def fetch_one(cal_id: str) -> list[CalEvent]:
        url = config.CALENDAR_EVENTS_URL.format(cal_id=urllib.parse.quote(cal_id))
        try:
            er = requests.get(url, headers=headers, params={
                "timeMin": time_min,
                "timeMax": time_max,
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": 250,
                "fields": "items(start,summary,iCalUID,id)",
            }, timeout=20)
        except Exception:
            return []
        if er.status_code != 200:
            return []
        out = []
        for it in er.json().get("items", []):
            start = it.get("start", {})
            s = start.get("dateTime") or start.get("date") or ""
            dt, has_time = _parse_rfc3339(s)
            if dt is None:
                continue
            out.append(CalEvent(
                start=dt,
                has_time=has_time,
                summary=it.get("summary", "(제목 없음)"),
                uid=it.get("iCalUID", it.get("id", "")),
            ))
        return out

    events: list[CalEvent] = []
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(cal_ids)))) as ex:
        for res in ex.map(fetch_one, cal_ids):
            events.extend(res)
    events.sort(key=lambda e: e.start)
    return events


def fetch_tasks(auth: GoogleAuth) -> list[GoogleTask]:
    """모든 작업목록의 미완료 할일 (목록별 병렬 조회)."""
    token = auth.valid_token()
    headers = {"Authorization": "Bearer " + token}
    r = requests.get(config.TASKLISTS_URL, headers=headers, timeout=20,
                     params={"fields": "items(id,title)"})
    if r.status_code != 200:
        raise GoogleError(f"작업목록 조회 실패 (HTTP {r.status_code})")
    lists = [(l.get("id", ""), l.get("title", "")) for l in r.json().get("items", []) if l.get("id")]

    def fetch_one(item):
        list_id, list_name = item
        try:
            tr = requests.get(config.TASKS_URL.format(list_id=list_id), headers=headers, params={
                "showCompleted": "false",
                "maxResults": 100,
                "fields": "items(id,title,notes,due)",
            }, timeout=20)
        except Exception:
            return []
        if tr.status_code != 200:
            return []
        res = []
        for t in tr.json().get("items", []):
            title = (t.get("title") or "").strip()
            if not title:
                continue
            due_dt, _ = _parse_rfc3339(t.get("due", ""))
            res.append(GoogleTask(
                id=t.get("id", ""),
                list_id=list_id,
                title=title,
                notes=t.get("notes", ""),
                due=due_dt.date() if due_dt else None,
                has_due=due_dt is not None,
                list_name=list_name,
            ))
        return res

    out: list[GoogleTask] = []
    if lists:
        with ThreadPoolExecutor(max_workers=min(8, len(lists))) as ex:
            for res in ex.map(fetch_one, lists):
                out.extend(res)
    return out


def insert_task(auth: GoogleAuth, list_id: str, title: str, notes: str, due: Optional[date]) -> None:
    headers = auth._headers()
    body = {"title": title}
    if notes.strip():
        body["notes"] = notes
    if due:
        body["due"] = due.strftime("%Y-%m-%dT00:00:00.000Z")
    lid = list_id or "@default"
    r = requests.post(config.TASKS_URL.format(list_id=lid), headers=headers, json=body, timeout=30)
    if r.status_code not in (200, 201):
        raise GoogleError(_task_write_error(r))


def update_task(auth: GoogleAuth, list_id: str, task_id: str, title: str,
                notes: str, due: Optional[date], has_due: bool) -> None:
    headers = auth._headers()
    body = {"title": title, "notes": notes}
    if has_due and due:
        body["due"] = due.strftime("%Y-%m-%dT00:00:00.000Z")
    else:
        body["due"] = None
    r = requests.patch(config.TASK_ITEM_URL.format(list_id=list_id, task_id=task_id),
                       headers=headers, json=body, timeout=30)
    if r.status_code != 200:
        raise GoogleError(_task_write_error(r))


def complete_task(auth: GoogleAuth, list_id: str, task_id: str) -> None:
    headers = auth._headers()
    r = requests.patch(config.TASK_ITEM_URL.format(list_id=list_id, task_id=task_id),
                       headers=headers, json={"status": "completed"}, timeout=30)
    if r.status_code != 200:
        raise GoogleError(_task_write_error(r))


def delete_task(auth: GoogleAuth, list_id: str, task_id: str) -> None:
    headers = auth._headers()
    r = requests.delete(config.TASK_ITEM_URL.format(list_id=list_id, task_id=task_id),
                        headers=headers, timeout=30)
    if r.status_code not in (200, 204):
        raise GoogleError(_task_write_error(r))


def _task_write_error(r) -> str:
    if r.status_code == 403:
        return ("쓰기 권한이 없습니다 (HTTP 403).\n"
                "[Google 로그아웃] 후 다시 [Google 로그인] 하세요.")
    return f"구글 요청 실패 (HTTP {r.status_code})"


# ---------------------------------------------------------------------------
# 계정 이메일
# ---------------------------------------------------------------------------
def get_user_email(auth: GoogleAuth) -> str:
    try:
        r = requests.get(config.USERINFO_URL, headers=auth._headers(), timeout=15)
        if r.status_code == 200:
            return (r.json().get("email") or "").strip().lower()
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# 캘린더 목록 / 일정 추가(쓰기)
# ---------------------------------------------------------------------------
def fetch_calendar_list(auth: GoogleAuth) -> list[dict]:
    """캘린더 목록: [{id, name, primary, selected, color}] (기본 캘린더 먼저)."""
    r = requests.get(config.CALENDAR_LIST_URL, headers=auth._headers(), timeout=20,
                     params={"fields": "items(id,summary,primary,selected,backgroundColor)"})
    if r.status_code != 200:
        raise GoogleError(f"캘린더 목록 조회 실패 (HTTP {r.status_code})")
    out = []
    for c in r.json().get("items", []):
        out.append({
            "id": c.get("id", ""),
            "name": c.get("summary", c.get("id", "")),
            "primary": bool(c.get("primary")),
            "selected": bool(c.get("selected", True)),
            "color": c.get("backgroundColor", "#5B8FBF"),
        })
    out.sort(key=lambda x: (not x["primary"], x["name"]))
    return out


def insert_event(auth: GoogleAuth, calendar_id: str, summary: str,
                 day: date, start_time=None, end_time=None,
                 all_day: bool = True, description: str = "") -> None:
    """캘린더에 일정 추가. all_day=True면 종일, 아니면 start_time~end_time."""
    headers = auth._headers()
    headers["Content-Type"] = "application/json"
    body = {"summary": summary}
    if description:
        body["description"] = description
    if all_day or start_time is None:
        body["start"] = {"date": day.strftime("%Y-%m-%d")}
        body["end"] = {"date": (day + timedelta(days=1)).strftime("%Y-%m-%d")}
    else:
        tz = datetime.now().astimezone().tzinfo
        sdt = datetime(day.year, day.month, day.day, start_time.hour, start_time.minute, tzinfo=tz)
        if end_time is not None:
            edt = datetime(day.year, day.month, day.day, end_time.hour, end_time.minute, tzinfo=tz)
        else:
            edt = sdt + timedelta(hours=1)
        body["start"] = {"dateTime": sdt.isoformat()}
        body["end"] = {"dateTime": edt.isoformat()}
    cid = urllib.parse.quote(calendar_id or "primary")
    r = requests.post(config.CALENDAR_EVENTS_URL.format(cal_id=cid),
                      headers=headers, json=body, timeout=20)
    if r.status_code not in (200, 201):
        raise GoogleError(_task_write_error(r) if r.status_code == 403
                          else f"일정 추가 실패 (HTTP {r.status_code})")


# ---------------------------------------------------------------------------
# Drive appDataFolder (다중 PC 동기화용 앱 전용 저장공간)
# ---------------------------------------------------------------------------
def drive_find(auth: GoogleAuth, name: str) -> Optional[str]:
    r = requests.get(config.DRIVE_FILES_URL, headers=auth._headers(), timeout=20, params={
        "spaces": "appDataFolder",
        "q": f"name='{name}'",
        "fields": "files(id,name,modifiedTime)",
    })
    if r.status_code != 200:
        raise GoogleError(f"Drive 조회 실패 (HTTP {r.status_code})")
    files = r.json().get("files", [])
    return files[0]["id"] if files else None


def drive_read(auth: GoogleAuth, file_id: str) -> str:
    r = requests.get(f"{config.DRIVE_FILES_URL}/{file_id}", headers=auth._headers(),
                     timeout=20, params={"alt": "media"})
    if r.status_code != 200:
        raise GoogleError(f"Drive 다운로드 실패 (HTTP {r.status_code})")
    return r.text


def drive_write(auth: GoogleAuth, name: str, content: str) -> str:
    """appDataFolder 에 name 파일을 만들거나 갱신. file_id 반환."""
    fid = drive_find(auth, name)
    if fid is None:
        meta = requests.post(config.DRIVE_FILES_URL, headers=auth._headers(), timeout=20,
                             json={"name": name, "parents": ["appDataFolder"]})
        if meta.status_code not in (200, 201):
            raise GoogleError(f"Drive 파일 생성 실패 (HTTP {meta.status_code})")
        fid = meta.json()["id"]
    hdr = auth._headers()
    hdr["Content-Type"] = "application/json; charset=UTF-8"
    up = requests.patch(f"{config.DRIVE_UPLOAD_URL}/{fid}", headers=hdr, timeout=30,
                        params={"uploadType": "media"}, data=content.encode("utf-8"))
    if up.status_code not in (200, 201):
        raise GoogleError(f"Drive 업로드 실패 (HTTP {up.status_code})")
    return fid
