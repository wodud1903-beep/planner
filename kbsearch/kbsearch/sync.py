"""[동기화] — 이 PC 의 자료를 구글과 주고받는다. 누를 때만 돈다.
(회사 공통 자료만은 로그인 없이 저절로도 받는다 — 맨 아래 apply_public)

**회사 공통 자료** — 일정관리기와 같은 스프레드시트의 `업무자료` 탭.
  · 보통은 받기만 한다(시트 → 이 PC). 로그인 계정이 시트에 초대돼 있지 않아도, 시트가
    공개로 열려 있으면 공개 CSV 로 받는다(sheets_kb.read_kb_public).
  · 관리자 계정이 이 PC 에서 고친 것이 있으면(kb_meta.shared_dirty) 시트로 올린다.
    시트 내용을 통째로 바꾸므로 화면이 먼저 묻는다(main_window._sync).

**내 메모** — 일정관리기의 드라이브 동기화 묶음(appDataFolder 의 planner_sync.json)
  안의 `kb_mine.json` 칸을 **같이 쓴다.** 그래서 같은 구글 계정이면 일정관리기에서 적은
  메모가 여기에, 여기서 적은 메모가 일정관리기에 나온다.

  ⚠️ 묶음에는 일정관리기의 할일·알람·멘트·고객메모가 함께 들어 있다. 이 프로그램은
     **kb_mine.json 칸 하나만** 고치고 나머지는 글자 하나 바꾸지 않고 그대로 돌려놓는다.
     묶음을 못 읽으면(인터넷·권한) 절대 쓰지 않는다 — '없음' 으로 착각해 새 묶음을
     쓰면 일정관리기 자료가 통째로 사라진다. 정말 없을 때만 새로 만든다.

  합치는 법은 일정관리기와 같다(sync.py 의 kb_mine 규칙) — 더 최근에 고친 쪽을 앞에 두고,
  제목이 다른 메모는 양쪽 것을 다 남긴다. 시각은 일정관리기와 같은 꼴(UTC 문자열)로 적는다.
  더해서, 이 PC 에서 지우거나 이름을 바꾼 메모(kb_meta.deleted)는 다른 쪽에 남아 있어도
  되살리지 않는다.

**첨부** — 이 PC 에만 두었던 첨부(local-…)를 먼저 드라이브에 올린 뒤에 내보낸다.
  하나라도 못 올리면 그 묶음은 내보내지 않는다(다른 PC 가 받을 수 없는 첨부를 싣지 않게).
"""

from __future__ import annotations

import datetime
import json
import os
from dataclasses import dataclass, field

from . import config, google_auth, kb, kb_files, sheets_kb

MINE_KEY = kb.MINE_FILE             # 묶음 안의 칸 이름 — 일정관리기와 같다(kb_mine.json)
_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"      # 일정관리기 sync.py 와 같은 꼴(문자열로 크기를 견준다)


class SyncError(Exception):
    pass


@dataclass
class Result:
    account: str = ""
    shared_pulled: int = -1         # 받은 공통 자료 수(-1 = 안 받음)
    shared_pushed: int = -1         # 올린 공통 자료 수(-1 = 안 올림)
    shared_note: str = ""
    mine_count: int = 0
    mine_added: int = 0             # 다른 곳에서 새로 들어온 메모 수
    uploaded: int = 0               # 올린 첨부 수
    notes: list = field(default_factory=list)

    def summary(self) -> str:
        bits = []
        if self.shared_pushed >= 0:
            bits.append(f"공통 자료 {self.shared_pushed}건 올림")
        elif self.shared_pulled >= 0:
            bits.append(f"공통 자료 {self.shared_pulled}건 받음")
        bits.append(f"내 메모 {self.mine_count}건"
                    + (f"(새로 {self.mine_added}건)" if self.mine_added else ""))
        if self.uploaded:
            bits.append(f"첨부 {self.uploaded}개 올림")
        return " · ".join(bits)


def now_stamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime(_TS_FMT)


def _to_ts(stamp: str) -> float:
    try:
        return datetime.datetime.strptime(stamp, _TS_FMT).replace(
            tzinfo=datetime.timezone.utc).timestamp()
    except Exception:
        return 0.0


def mine_stamp() -> str:
    """이 PC 의 내 메모 파일을 마지막으로 고친 때(UTC 문자열). 없으면 ""."""
    p = config.data_file(kb.MINE_FILE)
    try:
        if p.exists():
            return datetime.datetime.fromtimestamp(
                p.stat().st_mtime, datetime.timezone.utc).strftime(_TS_FMT)
    except Exception:
        pass
    return ""


def _set_mine_stamp(stamp: str) -> None:
    t = _to_ts(stamp)
    if t:
        try:
            os.utime(config.data_file(kb.MINE_FILE), (t, t))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 합치기
# ---------------------------------------------------------------------------
def merge_mine(local: list, remote: list, local_newer: bool, dead: set) -> list:
    """두 메모 목록을 합친다. 더 최근 쪽을 앞에 두고, 다른 쪽에만 있는 제목을 뒤에 붙인다.

    `dead`(이 PC 에서 지우거나 이름을 바꾼 제목)는 어느 쪽에 있든 뺀다.
    """
    first, second = (local, remote) if local_newer else (remote, local)
    out, seen = [], set()
    for it in list(first) + list(second):
        t = (it.get("title") or "").strip()
        if not t or t in seen or t in dead:
            continue
        seen.add(t)
        out.append(it)
    return out


# ---------------------------------------------------------------------------
# 일정관리기 묶음
# ---------------------------------------------------------------------------
def read_bundle(auth):
    """(묶음 dict 또는 None, 파일 id 또는 None). 못 읽으면 SyncError — 그때는 쓰면 안 된다."""
    try:
        fid = google_auth.appdata_find(auth, config.PLANNER_SYNC_FILE)
    except google_auth.GoogleError as e:
        raise SyncError(f"내 메모를 확인하지 못했습니다: {e}")
    if not fid:
        return None, None                      # 정말 없음 — 처음 쓰는 계정
    try:
        text = google_auth.appdata_read(auth, fid)
    except google_auth.GoogleError as e:
        raise SyncError(f"내 메모를 받지 못했습니다: {e}")
    try:
        b = json.loads(text)
    except Exception:
        raise SyncError("드라이브의 동기화 묶음을 읽을 수 없습니다(모양이 깨짐).\n"
                        "일정관리기 자료를 지키려고 내 메모 동기화를 멈췄습니다.")
    if not isinstance(b, dict):
        raise SyncError("드라이브의 동기화 묶음 모양이 예상과 다릅니다 — 내 메모 동기화를 멈췄습니다.")
    return b, fid


def remote_mine(bundle) -> tuple:
    """묶음 안의 (내 메모 목록, 그 시각)."""
    if not bundle:
        return [], ""
    text = str((bundle.get("files") or {}).get(MINE_KEY) or "")
    items = kb._parse(text) if text.strip() else []
    times = bundle.get("times") or {}
    stamp = str(times.get(MINE_KEY) or bundle.get("updatedAt") or "") if text.strip() else ""
    return items, stamp


def put_mine(bundle, items: list, stamp: str) -> dict:
    """묶음의 kb_mine.json 칸만 바꾼 새 묶음. 나머지 칸은 그대로 둔다."""
    if not bundle:
        return {"updatedAt": stamp, "files": {MINE_KEY: kb.dumps(items)},
                "times": {MINE_KEY: stamp}}
    out = dict(bundle)
    files = dict(out.get("files") or {})
    files[MINE_KEY] = kb.dumps(items)
    out["files"] = files
    times = dict(out.get("times") or {})
    times[MINE_KEY] = stamp
    out["times"] = times
    # updatedAt 은 건드리지 않는다 — 시각표가 없는 옛 칸들이 이 값을 자기 시각으로 쓴다
    return out


# ---------------------------------------------------------------------------
# 첨부
# ---------------------------------------------------------------------------
def _upload_locals(auth, items: list, public: bool, done: dict) -> tuple:
    """items 안의 local- 첨부를 올리고 진짜 첨부로 바꾼 (새 목록, 올린 수)."""
    n = 0
    out = []
    for it in items:
        files = it.get("files") or []
        if not any(kb_files.is_local(f) for f in files):
            out.append(it)
            continue
        new_files = []
        for f in files:
            if kb_files.is_local(f):
                key = (f.get("id"), public)
                if key not in done:
                    try:
                        done[key] = kb_files.upload_local(auth, f, public)
                    except Exception as e:
                        raise SyncError(f"첨부를 올리지 못했습니다: {e}\n"
                                        "인터넷을 확인한 뒤 다시 [동기화] 해 주세요.")
                    n += 1
                up = dict(done[key])
                up["name"] = f.get("name") or up.get("name", "")
                if up["name"] != done[key].get("name"):
                    kb_files.rename_remote(auth, up["id"], up["name"])
                    kb_files.rename_cache(done[key], up["name"])
                new_files.append(up)
            else:
                new_files.append(f)
        it = dict(it)
        it["files"] = new_files
        out.append(it)
    return out, n


def _drop_unused_locals(old: list, new: list) -> None:
    """시트 내용으로 바꿀 때, 옛 공통 자료에만 붙어 있던 이 PC 첨부(local-)를 지운다."""
    keep = {f.get("id") for it in list(new) + kb.load_mine() for f in (it.get("files") or [])}
    keep |= kb.local_file_ids()         # 이 PC 에서만 고친 공통 자료가 쓰는 것
    for it in old:
        for f in it.get("files") or []:
            if kb_files.is_local(f) and f.get("id") not in keep:
                kb_files.drop_local(f)


def _flush_queue(auth) -> None:
    """로그인 없이 빼거나 이름을 바꾼 '이미 올린' 첨부를 드라이브에 반영한다(실패해도 넘어간다)."""
    m = kb.load_meta()
    trash = [x for x in (m.get("trash") or []) if x]
    renames = [x for x in (m.get("renames") or []) if isinstance(x, list) and len(x) == 2]
    if not trash and not renames:
        return
    # 동기화로 되살아난 자료(다른 곳에서 더 나중에 고친 메모 등)가 아직 쓰는 첨부는 남긴다
    used = {f.get("id") for it in kb.load_shared() + kb.load_mine()
            for f in (it.get("files") or [])} | kb.local_file_ids()
    trash = [x for x in trash if x not in used]
    kb_files.trash(auth, trash)
    for fid, name in renames:
        if fid not in trash:
            kb_files.rename_remote(auth, fid, name)
    kb.update_meta(trash=[], renames=[])


# ---------------------------------------------------------------------------
# 한 번 동기화
# ---------------------------------------------------------------------------
def run(auth, push_shared: bool = False) -> Result:
    """동기화 한 번. 실패하면 SyncError(이미 끝낸 단계는 이 PC 에 반영돼 있다).

    push_shared=True 는 관리자가 '이 PC 의 공통 자료를 시트로 올린다' 고 고른 경우다.
    """
    res = Result(account=getattr(auth, "email", "") or "")
    admin = config.is_admin(res.account)
    meta = kb.load_meta()
    done: dict = {}                     # (local id, 공개여부) → 올린 첨부(한 번만 올린다)

    # 1) 회사 공통 자료
    if push_shared and admin:
        shared = kb.load_shared()
        shared, n = _upload_locals(auth, shared, True, done)
        res.uploaded += n
        kb.save_shared(shared)          # 올라간 첨부 id 를 먼저 이 PC 에 남긴다
        try:
            sheets_kb.write_kb(auth, shared)
        except google_auth.GoogleError as e:
            raise SyncError(f"공통 자료를 시트에 올리지 못했습니다:\n{e}")
        kb.update_meta(shared_dirty=False)
        res.shared_pushed = len(shared)
    else:
        try:
            got = sheets_kb.read_kb(auth)
        except google_auth.GoogleError as e:
            # 로그인으로 못 읽어도(시트에 초대 안 된 계정) 공개로는 읽힐 수 있다
            try:
                got = sheets_kb.read_kb_public()
            except sheets_kb.NotPublic:
                raise SyncError(f"공통 자료를 받지 못했습니다:\n{e}")
        if got:
            _drop_unused_locals(kb.load_shared(), got)
            kb.save_shared(got)
            kb.update_meta(shared_dirty=False,
                           shared_at=datetime.datetime.now().isoformat(timespec="seconds"))
            res.shared_pulled = len(got)
        else:
            res.shared_note = "시트에 아직 공통 자료가 없어 이 PC 의 자료를 그대로 둡니다."

    # 2) 내 메모 — 시각은 올리기 전에 잰다(올린 뒤 저장하면 '방금 고친 것' 으로 보인다)
    lstamp = mine_stamp()
    mine = kb.load_mine()
    mine, n = _upload_locals(auth, mine, False, done)
    res.uploaded += n
    if n:
        kb.save_mine(mine, track=False)
    bundle, fid = read_bundle(auth)
    remote, rstamp = remote_mine(bundle)
    dead = kb.deleted_titles()
    merged = merge_mine(mine, remote, local_newer=(lstamp >= rstamp), dead=dead)
    before = {it["title"] for it in mine}
    res.mine_added = sum(1 for it in merged if it["title"] not in before)
    res.mine_count = len(merged)

    if kb.clean_list(merged) != kb.clean_list(remote) or not bundle:
        stamp = now_stamp()
        try:
            google_auth.appdata_write(auth, config.PLANNER_SYNC_FILE,
                                      json.dumps(put_mine(bundle, merged, stamp),
                                                 ensure_ascii=False), fid)
        except google_auth.GoogleError as e:
            raise SyncError(f"내 메모를 올리지 못했습니다: {e}")
    else:
        stamp = rstamp or now_stamp()
    kb.save_mine(merged, track=False)
    _set_mine_stamp(stamp)

    # 3) 정리 — 올린 첨부의 이 PC 사본(local-)과 미뤄 둔 드라이브 일.
    #    이 PC 에서만 고친 공통 자료는 올리지 않으므로, 같은 그림을 쓰면 사본을 남긴다.
    keep = kb.local_file_ids()
    for f in [k for k in done]:
        if f[0] not in keep:
            kb_files.drop_local({"id": f[0]})
    _flush_queue(auth)

    kb.update_meta(pending=False, account=res.account,
                   last_sync=datetime.datetime.now().isoformat(timespec="seconds"))
    if meta.get("account") and meta.get("account") != res.account:
        res.notes.append(f"이전 계정({meta.get('account')}) 대신 {res.account} 와 동기화했습니다.")
    return res


# ---------------------------------------------------------------------------
# 로그인 없이 — 회사 공통 자료 저절로 받기
# ---------------------------------------------------------------------------
def apply_public(got) -> dict:
    """공개 CSV 로 받은 공통 자료(sheets_kb.read_kb_public)를 이 PC 에 맞춘다.

    받기(인터넷)는 일꾼 스레드가, 이 함수(파일 쓰기)는 **화면 스레드**가 부른다 — 자료 편집
    창의 저장과 엇갈려 고친 것을 덮어쓰지 않게(main_window.auto_pull).

    반환 {"changed": 바뀌었나, "count": 받은 수, "skipped": 안 맞춘 이유("" 면 맞춤)}
      · "dirty" — 관리자가 이 PC 에서 고친 공통 자료가 아직 안 올라갔다. 덮어쓰면 그게
                  사라지므로 손대지 않는다([동기화] 가 올릴지 묻는다).
      · "empty" — 시트가 비었다(관리자가 막 고쳐 쓰는 중일 수도). 이 PC 것을 둔다.
    """
    if kb.load_meta().get("shared_dirty"):
        return {"changed": False, "count": 0, "skipped": "dirty"}
    if not got:
        return {"changed": False, "count": 0, "skipped": "empty"}
    old = kb.load_shared()
    changed = (not kb.has_shared_cache()) or kb.clean_list(got) != kb.clean_list(old)
    if changed:
        _drop_unused_locals(old, got)
        kb.save_shared(got)
    kb.update_meta(shared_at=datetime.datetime.now().isoformat(timespec="seconds"))
    return {"changed": changed, "count": len(got), "skipped": ""}


def reset_mine_for_account() -> None:
    """다른 계정으로 바꿀 때 — 이 PC 의 내 메모를 비운다(그 계정 것을 새로 받는다)."""
    keep = kb.local_file_ids()          # 이 PC 에서만 고친 공통 자료는 계정과 상관없다
    for it in kb.load_mine():
        for f in it.get("files") or []:
            if f.get("id") not in keep:
                kb_files.drop_local(f)
    kb.save_mine([], track=False)
    kb.update_meta(deleted={}, account="", trash=[], renames=[])
