"""카톡 매크로 발송 기록 — 고객 목록(customers.tsv) · 발송 로그를 내 구글 계정에 올려 어느 PC 에서나(v1.38).

지점장: "자주 쓰는 문구 및 고객 발송 로그는 원래 PC 에 저장했었는데, 로그인된 구글 드라이브에 올려서 자동으로
불러올 수 있도록 리스트를 만들어줘." (자주 쓰는 문구 · 발송 간격은 v1.37 부터 계정 — kakao_macro.Prefs)
일정관리기 · 업무자료검색이 이 파일을 **그대로** 쓴다(사본). Qt 를 모른다 — 목록 화면은 kakao_macro_view.

계정 — 앱 전용 공간의 kakao_history.json 하나(두 프로그램 · 모든 PC 가 같은 파일):
  {"v": 1,
   "devices":   {pc: PC 이름},
   "customers": {이름: [처음 본 날, 마지막 발송, {pc: 그 PC 가 보낸 횟수}, 수신거부 0|1, 메모]},
   "events":    [[id, 시각, ok|skip|stop, 이름, 내용, pc], …]}       ← 새것이 앞 · 최대 EVENTS_MAX 줄
  시각은 PC 시각 그대로 'YYYY-MM-DD HH:MM:SS'(A1Auto 로그 · customers.tsv 와 같은 모양).

이 PC — customers.tsv 옆(두 프로그램이 함께 쓴다):
  customers.tsv        A1Auto 모양 그대로. 맞추면 계정 것을 합쳐 써서 '최근 N일 내 발송함' 이 PC 사이에서도 맞는다.
  customers.sync.json  지난번에 맞춘 것(계정 사본) — 이 PC 가 새로 보낸 횟수를 셀 기준 · 인터넷 없을 때 목록.
  customers.new.jsonl  아직 맞추지 않은 로그 줄(보낼 때마다 한 줄씩 덧붙인다 — 갑자기 꺼져도 남게).
  logs\\*.txt          A1Auto 가 닫을 때 쓰던 로그 · [A1Auto 기록 가져오기]로 옮긴 것 — 새 파일이면 읽어 올린다.

합치는 규칙(PC 여러 대 · 두 프로그램 · 몇 번을 맞춰도 같은 결과)
  · 처음 본 날 = 이른 쪽, 마지막 발송 = 늦은 쪽.
  · 횟수 = PC 마다 센 것의 합. 이 PC 몫은 customers.tsv 의 횟수가 지난번 합보다 늘어난 만큼 더한다(다른 PC 몫을
    이 PC 가 보낸 것으로 두 번 세지 않게). PC 마다 큰 쪽을 남긴다 — 같은 것을 두 번 맞춰도 늘지 않는다.
  · 수신거부 · 메모(엑셀에서 고친 것) = 지난번 맞춘 뒤 이 PC 에서 고쳤으면 이 PC 것, 아니면 계정 것.
  · 로그 줄은 글로 정한 id — 새로 쓴 줄 · 닫을 때 쓴 로그 파일 · 다른 PC 에서 옮겨 온 같은 파일이 겹치지 않는다.
  · 다른 계정으로 맞춘 사본이면 기준을 비우고 이 PC 기록을 지금 계정에 올린다.
  · 계정 파일이 깨졌으면 쓰지 않는다(남의 것을 덮지 않게).
맞추기는 둘로 나눈다 — prepare(뒤에서: 읽기 · 합치기 · 올리기)와 apply(화면 쪽, 매크로가 쉬는 중에만: 이 PC 파일
쓰기). 그사이 customers.tsv · 사본이 바뀌었으면(매크로 · 다른 프로그램) apply 는 쓰지 않고 다시 맞추게 한다.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import socket
import threading
import uuid
from pathlib import Path

from . import kakao_macro as km

REMOTE_NAME = "kakao_history.json"
EVENTS_MAX = 20000                 # 줄 하나 ≈ 70바이트 — 1.4MB 쯤에서 오래된 것부터 버린다
KINDS = ("ok", "skip", "stop")
KIND_TEXT = {"ok": "발송", "skip": "건너뜀", "stop": "중단"}

_DT = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"
_DT_RE = re.compile(_DT)
# '✅ 2026-11-27 09:00:00 → 홍길동 발송완료' — 앞 표시는 가리지 않는다(예전 A1Auto 가 ANSI 로 저장해 '?' 가 된 줄)
_LINE_RE = re.compile(r"^\S*\s*(" + _DT + r") → (.*)$")
_DUP_RE = re.compile(r"^최근 \d+일 내 발송함: (.*)$")


class HistoryError(Exception):
    pass


# ---------------------------------------------------------------------------
# 로그 줄 · 이 PC
# ---------------------------------------------------------------------------
def parse_line(line):
    """A1Auto 로그 한 줄 → (시각, ok|skip|stop, 이름, 내용) · 로그 줄이 아니면 None."""
    m = _LINE_RE.match(str(line or "").strip())
    if not m:
        return None
    at, rest = m.group(1), m.group(2)
    if rest.startswith("중단: "):
        return at, "stop", "", rest[4:].strip()
    if rest.startswith("건너뜀: "):
        what = rest[5:].strip()
        d = _DUP_RE.match(what)
        return at, "skip", (d.group(1).strip() if d else ""), what
    if rest.endswith(" 발송완료"):
        who = rest[:-5].strip()
        return (at, "ok", who, "") if who else None
    return None


def event_id(at: str, kind: str, who: str, what: str) -> str:
    return hashlib.sha1(f"{at}|{kind}|{who}|{what}".encode("utf-8")).hexdigest()[:16]


def make_event(at: str, kind: str, who: str, what: str, dev: str) -> list:
    return [event_id(at, kind, who, what), at, kind, who, what, dev]


def device(path=None) -> tuple:
    """이 PC 의 표 → (id, 이름). 처음 한 번 만들어 A1Auto 폴더 device.json 에 둔다(두 프로그램이 같은 표)."""
    p = Path(path) if path else km.base_dir() / "device.json"
    try:
        o = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(o, dict) and re.fullmatch(r"[0-9a-f]{8,32}", str(o.get("id", ""))):
            return str(o["id"]), str(o.get("name") or "")[:40]
    except (OSError, ValueError):
        pass
    did = uuid.uuid4().hex[:12]
    try:
        name = (os.environ.get("COMPUTERNAME") or socket.gethostname() or "").strip()[:40]
    except OSError:
        name = ""
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"id": did, "name": name}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return did, name


# ---------------------------------------------------------------------------
# 문서 — 다듬기 · 합치기(계산만)
# ---------------------------------------------------------------------------
def empty() -> dict:
    return {"v": 1, "devices": {}, "customers": {}, "events": []}


def _ds(s) -> str:
    s = str(s or "").strip()
    return s if _DT_RE.fullmatch(s) else ""


def _first(a: str, b: str) -> str:
    xs = [x for x in (a, b) if x]
    return min(xs) if xs else ""


def _finish_events(evs) -> list:
    seen, out = set(), []
    for e in evs:
        if e[0] in seen:
            continue
        seen.add(e[0])
        out.append(e)
    out.sort(key=lambda e: (e[1], e[0]), reverse=True)
    return out[:EVENTS_MAX]


def clean(o) -> dict:
    """계정 · 사본 문서를 다듬는다(모르는 값 · 깨진 줄은 버린다)."""
    o = o if isinstance(o, dict) else {}
    d = o.get("devices")
    devs = {str(k): str(v or "")[:40] for k, v in d.items()} if isinstance(d, dict) else {}
    cus = {}
    c = o.get("customers")
    for name, r in (c.items() if isinstance(c, dict) else ()):
        name = km.CustomerStore.normalize_key(name)
        if not name or not isinstance(r, list):
            continue
        r = list(r) + [""] * (5 - len(r))
        n = ({str(k): int(v) for k, v in r[2].items() if isinstance(v, int) and not isinstance(v, bool) and v > 0}
             if isinstance(r[2], dict) else {})
        cus[name] = [_ds(r[0]), _ds(r[1]), n, 1 if r[3] in (1, True, "1") else 0, km._sanitize(r[4])]
    evs = []
    e_ = o.get("events")
    for e in (e_ if isinstance(e_, list) else ()):
        if not isinstance(e, list) or len(e) < 6 or e[2] not in KINDS:
            continue
        at = _ds(e[1])
        if not at or not str(e[0] or ""):
            continue
        evs.append([str(e[0]), at, e[2], str(e[3] or ""), str(e[4] or ""), str(e[5] or "")])
    return {"v": 1, "devices": devs, "customers": cus, "events": _finish_events(evs)}


def merge(local: dict, remote: dict, base: dict) -> dict:
    """이 PC 것(local) + 계정 것(remote) → 합친 것. base = 지난번 맞춘 것(수신거부 · 메모를 이 PC 에서 고쳤나)."""
    out = empty()
    out["devices"] = {**remote["devices"], **local["devices"]}
    L, R, B = local["customers"], remote["customers"], base["customers"]
    for nm in list(L) + [n for n in R if n not in L]:
        lr, rr, br = L.get(nm), R.get(nm), B.get(nm)
        if lr is None or rr is None:
            out["customers"][nm] = copy.deepcopy(lr if rr is None else rr)
            continue
        n = dict(rr[2])
        for k, v in lr[2].items():
            n[k] = max(n.get(k, 0), v)
        if br is None:
            opt = 1 if (lr[3] or rr[3]) else 0
            memo = lr[4] or rr[4]
        else:
            opt = lr[3] if lr[3] != br[3] else rr[3]
            memo = lr[4] if lr[4] != br[4] else rr[4]
        out["customers"][nm] = [_first(lr[0], rr[0]), max(lr[1], rr[1]), n, opt, memo]
    # 같은 줄이면 계정에 먼저 올라간 것(그 PC 이름)을 남긴다
    out["events"] = _finish_events(list(remote["events"]) + list(local["events"]))
    return out


def build_local(items: dict, base: dict, me: str, pc: str, new_events) -> dict:
    """지난번 맞춘 것(base) 위에 이 PC 의 customers.tsv · 새 로그 줄을 얹는다."""
    L = copy.deepcopy(base)
    L["devices"][me] = pc
    for key, cu in items.items():
        rec = L["customers"].get(key) or ["", "", {}, 0, ""]
        total = sum(rec[2].values())
        if cu.send_count > total:          # 지난번 맞춘 뒤 이 PC(이 프로그램 · 옆 프로그램)가 보낸 만큼
            rec[2][me] = rec[2].get(me, 0) + (cu.send_count - total)
        rec[0] = _first(rec[0], km._date_to_str(cu.first_seen))
        rec[1] = max(rec[1], km._date_to_str(cu.last_sent))
        rec[3] = 1 if cu.opt_out else 0
        rec[4] = km._sanitize(cu.memo)
        L["customers"][key] = rec
    L["events"] = _finish_events(list(L["events"]) + list(new_events))
    return L


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


class Plan:
    """prepare 가 만든 것 — apply 가 이 PC 파일에 쓴다."""

    def __init__(self):
        self.doc = empty()
        self.account = ""
        self.ver = ""             # 계정 파일 판(md5) — 같으면 다음엔 받지 않는다
        self.files = {}           # 읽은 로그 파일 {이름: 크기:고친 시각}
        self.nbytes = 0           # 맞춘 새 줄 파일의 앞부분(이만큼 지운다)
        self.fp = None            # 시작할 때의 customers.tsv · 사본 모양 — apply 때 다르면 쓰지 않는다
        self.same = False         # 바뀐 것이 없다(받지도 쓰지도 않음)
        self.pushed = False       # 계정에 올렸다
        self.online = False       # 계정과 맞췄다(로그인 전이면 이 PC 것만 정리)


# ---------------------------------------------------------------------------
# 이 PC 의 발송 기록
# ---------------------------------------------------------------------------
class HistoryBook:
    def __init__(self, tsv=None, logs=None, device_file=None):
        self.tsv = Path(tsv) if tsv else km.data_file()
        self._logs = Path(logs) if logs else None
        self.sync_path = self.tsv.with_name(self.tsv.stem + ".sync.json")
        self.new_path = self.tsv.with_name(self.tsv.stem + ".new.jsonl")
        self.me, self.pc = device(device_file)
        self.lock = threading.Lock()

    def logs_dir(self) -> Path:
        return self._logs if self._logs is not None else km.logs_dir()

    # ---- 사본 ----
    def load_mirror(self) -> dict:
        try:
            o = json.loads(self.sync_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            o = {}
        o = o if isinstance(o, dict) else {}
        f = o.get("files")
        return {"account": str(o.get("account") or ""), "ver": str(o.get("ver") or ""),
                "files": {str(k): str(v) for k, v in f.items()} if isinstance(f, dict) else {},
                "doc": clean(o.get("doc"))}

    def _save_mirror(self, m: dict) -> None:
        text = json.dumps(m, ensure_ascii=False, separators=(",", ":"))
        self.sync_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.sync_path.with_name(f"{self.sync_path.name}.{os.getpid()}.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, self.sync_path)

    # ---- 새 로그 줄 ----
    def note(self, line: str) -> bool:
        """매크로가 로그 한 줄을 찍었다(✅ ⏭ ❌) — 다음 맞추기에 올리게 덧붙여 둔다."""
        ev = parse_line(line)
        if not ev:
            return False
        rec = make_event(*ev, self.me)
        with self.lock:
            try:
                self.new_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.new_path, "a", encoding="utf-8", newline="\n") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            except OSError:
                return False
        return True

    def _pending(self) -> tuple:
        """→ (새 줄들, 읽은 바이트 수). 다 쓰지 못한 마지막 줄은 다음에."""
        try:
            raw = self.new_path.read_bytes()
        except OSError:
            return [], 0
        end = raw.rfind(b"\n") + 1
        evs = []
        for ln in raw[:end].split(b"\n"):
            try:
                e = json.loads(ln.decode("utf-8")) if ln.strip() else None
            except ValueError:
                continue
            if isinstance(e, list) and len(e) >= 6 and e[2] in KINDS and _ds(e[1]):
                evs.append([str(x or "") for x in e[:6]])
        return evs, end

    def _consume(self, nbytes: int) -> None:
        if nbytes <= 0:
            return
        with self.lock:
            try:
                raw = self.new_path.read_bytes()
                rest = raw[nbytes:] if raw[:nbytes].endswith(b"\n") else raw
                if rest == raw:
                    return
                if rest:
                    self.new_path.write_bytes(rest)
                else:
                    self.new_path.unlink()
            except OSError:
                pass

    # ---- 로그 파일 ----
    def _scan_logs(self, seen: dict) -> tuple:
        files = dict(seen)
        evs = []
        try:
            paths = sorted(self.logs_dir().glob("*.txt"))
        except OSError:
            paths = []
        for p in paths:
            try:
                st = p.stat()
                sig = f"{st.st_size}:{int(st.st_mtime)}"
                if files.get(p.name) == sig:
                    continue
                text = km.load_log_text(p)
            except OSError:
                continue
            for line in km._lines(text):
                ev = parse_line(line)
                if ev:
                    evs.append(make_event(*ev, self.me))
            files[p.name] = sig
        return evs, files

    def _fingerprint(self) -> tuple:
        """customers.tsv · 사본의 내용 표 — 고친 시각은 같은 순간(몇 ms)에 두 번 쓰면 같을 수 있어 내용으로 본다."""
        out = []
        for p in (self.tsv, self.sync_path):
            try:
                out.append(hashlib.md5(p.read_bytes()).hexdigest())
            except OSError:
                out.append(None)
        return tuple(out)

    def _store(self) -> km.CustomerStore:
        st = km.CustomerStore(self.tsv)
        st.load()
        return st

    # ---- 맞추기 ----
    def prepare(self, io, account: str) -> Plan:
        """뒤에서 — 이 PC 것을 모으고, 로그인했으면 계정 것과 합쳐 올린다(이 PC 파일은 쓰지 않는다)."""
        plan = Plan()
        plan.fp = self._fingerprint()
        m = self.load_mirror()
        account = (account or "").strip().lower()
        base, files, ver = m["doc"], m["files"], m["ver"]
        if m["account"] and account and m["account"] != account:
            # 다른 계정의 사본 — 기준을 비우고 이 PC 기록(customers.tsv · 이 PC 가 찍은 로그 줄)을 지금 계정에 새로
            own = [e for e in base["events"] if e[5] == self.me]
            base, files, ver = empty(), {}, ""
            base["events"] = own
        pend, plan.nbytes = self._pending()
        log_evs, plan.files = self._scan_logs(files)
        L = build_local(self._store().items, base, self.me, self.pc, pend + log_evs)
        plan.account = account or m["account"]
        plan.doc, plan.ver = L, ver
        dirty = L != base or plan.files != files or plan.account != m["account"]
        if io is None:
            plan.same = not dirty and plan.nbytes == 0
            return plan
        plan.online = True
        fid, rver = None, ""
        meta = getattr(io, "meta", None)
        if meta is not None:
            fid, rver = meta(REMOTE_NAME)
            if not dirty and plan.nbytes == 0 and rver and rver == ver:
                plan.same = True                   # 계정 것도 이 PC 것도 그대로 — 받지 않는다
                return plan
        else:
            fid = io.find(REMOTE_NAME)
        remote = None
        if fid:
            txt = io.read(fid)
            try:
                o = json.loads(txt) if (txt or "").strip() else {}
            except ValueError:
                raise HistoryError("계정의 발송 기록 파일이 깨져 있어 맞추지 않았습니다.")
            if not isinstance(o, dict):
                raise HistoryError("계정의 발송 기록 파일이 깨져 있어 맞추지 않았습니다.")
            remote = clean(o)
        R = remote if remote is not None else empty()
        out = merge(L, R, base)
        # 매크로를 한 번도 안 쓴 계정엔 파일을 만들지 않는다(PC 이름만으로는 올리지 않음)
        if out != R and (out["customers"] or out["events"]):
            text = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
            io.write(REMOTE_NAME, text)
            rver = _md5(text)
            plan.pushed = True
        plan.doc, plan.ver = out, rver
        return plan

    def apply(self, plan: Plan) -> str:
        """화면 쪽에서(매크로가 쉬는 중) — 사본 · customers.tsv 에 쓴다. → 'applied' · 'same' · 'stale'."""
        if plan.same:
            return "same"
        if self._fingerprint() != plan.fp:
            return "stale"                         # 그사이 이 PC 에서 바뀌었다 — 다시 맞춘다
        m = self.load_mirror()
        new_m = {"account": plan.account, "ver": plan.ver, "files": plan.files, "doc": plan.doc}
        if new_m != m:
            self._save_mirror(new_m)               # 사본 먼저 — 그 뒤 꺼져도 횟수를 두 번 세지 않는다
        st = self._store()
        changed = False
        for nm, r in plan.doc["customers"].items():
            cu = st.items.get(nm)
            want = (km._str_to_date(r[0]), km._str_to_date(r[1]), sum(r[2].values()), bool(r[3]), r[4])
            if cu is not None and (cu.first_seen, cu.last_sent, cu.send_count, cu.opt_out, km._sanitize(cu.memo)) == want:
                continue
            if cu is None:
                cu = km.Customer(nm)
                st.items[nm] = cu
            cu.first_seen, cu.last_sent, cu.send_count, cu.opt_out, cu.memo = want
            changed = True
        if changed:
            st.save()
        self._consume(plan.nbytes)
        return "applied"

    # ---- 목록 화면 ----
    def snapshot(self) -> dict:
        """지금 보이는 것 — 지난번 맞춘 것 + 이 PC 의 customers.tsv · 아직 안 맞춘 줄(인터넷 · 파일 쓰기 없음)."""
        m = self.load_mirror()
        pend, _n = self._pending()
        return build_local(self._store().items, m["doc"], self.me, self.pc, pend)

    def pc_name(self, doc: dict, dev: str) -> str:
        if dev == self.me:
            return "이 PC"
        return doc["devices"].get(dev) or ("PC " + dev[:4] if dev else "")
