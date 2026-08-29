"""다중 PC 동기화 — Drive appDataFolder 에 계정별 데이터 번들 저장.

한 사람이 사무실 PC 와 집 PC 를 번갈아 쓰는 것을 전제로 한다.

**파일마다 따로 판단한다.** 예전엔 묶음 전체를 시각 하나로 비교해서, 한쪽 PC 에서
할일 하나만 고쳐도 멘트·자료·고객메모까지 그 PC 것으로 올라갔다. 다른 PC 에서
고친 멘트가 그 순간 사라졌다. 이제 파일별로 더 최신인 쪽을 고른다.

**올릴 때도 먼저 합친다.** 예전 push 는 이 PC 의 파일을 그대로 덮어썼다. 그 사이
다른 PC 가 올린 파일이 있으면 지워졌다. 이제 원격을 읽어 합친 결과를 올린다.

**목록은 항목 단위로 합친다.** 멘트 문구처럼 양쪽에서 각각 채널을 더한 경우,
파일 단위로 고르면 한쪽 것이 통째로 사라진다. 이름이 다르면 둘 다 남기고,
같으면 파일이 더 최신인 쪽을 쓴다.

시각은 **디스크의 수정시각(mtime)** 을 그대로 쓴다. 받아 쓴 파일은 mtime 을 보낸
쪽 시각으로 되돌린다 — 안 그러면 받은 PC 가 '내 것이 더 최신' 이라 여겨 되돌려
보내고, 두 PC 가 서로 밀어내는 핑퐁이 된다.
"""

from __future__ import annotations

import datetime
import json
import os

from . import config, google_client

SYNC_FILE = "planner_sync.json"
_FILES = ["todos.json", "pcalarms.json", "taskalarms.json", "plan_cfg.json",
          "followups.json", "ment_copied.json", "customer_notes.json",
          "terms_presets.json", "commission_rates.json", "greetings.json",
          "kb_shared.json", "kb_mine.json", "customer_docs.json"]

# 항목 단위로 합치는 파일 → (모양, 열쇠)
#   list    : [{...}]        열쇠 값이 같으면 한 건으로 본다
#   dictlist: {키: [...]}    키별로 목록을 합친다
#   set     : [문자열]       합집합 (지워지면 안 되는 기록)
# 여기 없는 파일은 파일 단위로 최신인 쪽을 그대로 쓴다.
# 할일·서류체크를 넣지 않은 이유: 완료·삭제가 정상 동작이라 합치면 지운 것이 되살아난다.
_MERGE = {
    "greetings.json": ("list", "name"),
    "kb_mine.json": ("list", "title"),
    "terms_presets.json": ("dictlist", None),
    "customer_notes.json": ("dictlist", None),
    "ment_copied.json": ("set", None),
    "followups.json": ("set", None),
}

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _now() -> str:
    return datetime.datetime.utcnow().strftime(_TS_FMT)


def _to_ts(stamp: str) -> float:
    """"2026-08-30T05:12:33Z" → epoch 초. 못 읽으면 0."""
    try:
        return datetime.datetime.strptime(stamp, _TS_FMT).replace(
            tzinfo=datetime.timezone.utc).timestamp()
    except Exception:
        return 0.0


def file_stamp(name: str) -> str:
    """파일의 수정시각(UTC 문자열). 없으면 ""."""
    p = config.data_dir() / name
    try:
        if p.exists():
            return datetime.datetime.utcfromtimestamp(
                p.stat().st_mtime).strftime(_TS_FMT)
    except Exception:
        pass
    return ""


def _read(name: str) -> str:
    p = config.data_dir() / name
    try:
        if p.exists():
            return p.read_text(encoding="utf-8")
    except Exception:
        pass
    return ""


def _write(name: str, text: str, stamp: str) -> None:
    """파일을 쓰고 수정시각을 `stamp` 로 맞춘다.

    시각을 안 맞추면 방금 받은 파일이 '이 PC 에서 지금 고친 것' 으로 보여
    다음 동기화 때 보낸 쪽으로 되돌아간다.
    """
    p = config.data_dir() / name
    config.atomic_write(p, text)
    t = _to_ts(stamp)
    if t:
        try:
            os.utime(p, (t, t))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 로컬 변경 시각 (오프라인 대비 기록 — 판단에는 파일별 시각을 쓴다)
# ---------------------------------------------------------------------------
def _meta_path():
    return config.data_dir() / "sync_meta.json"


def _local_updated() -> str:
    p = _meta_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8")).get("updatedAt", "")
        except Exception:
            return ""
    return ""


def _set_local_updated(ts: str) -> None:
    try:
        config.atomic_write(_meta_path(), json.dumps({"updatedAt": ts}))
    except Exception:
        pass


def touch_local() -> None:
    """로컬 데이터가 바뀐 시각을 기록한다(참고용).

    실제 판단은 파일별 수정시각으로 한다. 이 값은 마지막으로 뭔가 한 때를
    남겨 두는 용도로만 쓴다.
    """
    _set_local_updated(_now())


def migrate_legacy() -> None:
    """계정 폴더가 비어 있고 예전 공용 폴더에 데이터가 있으면 1회 복사."""
    acc = config.data_dir()
    if (acc / "todos.json").exists():
        return
    legacy = config.base_dir()
    if legacy.resolve() == acc.resolve():
        return
    copied = False
    for n in _FILES:
        src = legacy / n
        if src.exists():
            try:
                (acc / n).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
                copied = True
            except Exception:
                pass
    if copied:
        _set_local_updated(_now())


# ---------------------------------------------------------------------------
# 항목 단위 합치기
# ---------------------------------------------------------------------------
def _key_of(item, key: str) -> str:
    if isinstance(item, dict):
        return str(item.get(key, "")).strip()
    return str(item).strip()


def _merge_list(new, old, key: str):
    """최신 쪽을 먼저 놓고, 옛 쪽에만 있는 항목을 뒤에 붙인다."""
    if not isinstance(new, list) or not isinstance(old, list):
        return new if isinstance(new, list) else old
    seen = {_key_of(x, key) for x in new}
    out = list(new)
    for x in old:
        k = _key_of(x, key)
        if k and k not in seen:
            out.append(x)
            seen.add(k)
    return out


def _merge_dictlist(new, old):
    """{키: [...]} — 키별로 목록을 합친다(중복은 한 번만)."""
    if not isinstance(new, dict) or not isinstance(old, dict):
        return new if isinstance(new, dict) else old
    out = {k: list(v) if isinstance(v, list) else v for k, v in new.items()}
    for k, ov in old.items():
        if not isinstance(ov, list):
            out.setdefault(k, ov)
            continue
        cur = out.get(k)
        if not isinstance(cur, list):
            out[k] = list(ov)
            continue
        seen = {json.dumps(x, ensure_ascii=False, sort_keys=True) for x in cur}
        for x in ov:
            s = json.dumps(x, ensure_ascii=False, sort_keys=True)
            if s not in seen:
                cur.append(x)
                seen.add(s)
    return out


def _merge_set(new, old):
    """[문자열] — 합집합. 순서를 고정해 두 PC 가 같은 파일을 갖게 한다."""
    if not isinstance(new, list) or not isinstance(old, list):
        return new if isinstance(new, list) else old
    return sorted({str(x) for x in new} | {str(x) for x in old})


def merge_text(name: str, new_txt: str, old_txt: str) -> str:
    """같은 파일의 두 판을 합친다. 합칠 수 없으면 최신(new) 쪽을 그대로.

    `new` 는 더 최신인 쪽, `old` 는 그보다 오래된 쪽이다.
    """
    how = _MERGE.get(name)
    if not how or not (old_txt or "").strip():
        return new_txt
    kind, key = how
    try:
        new = json.loads(new_txt)
        old = json.loads(old_txt)
    except Exception:
        return new_txt          # 한쪽이 깨졌으면 최신 쪽을 살린다
    try:
        if kind == "list":
            got = _merge_list(new, old, key)
        elif kind == "dictlist":
            got = _merge_dictlist(new, old)
        else:
            got = _merge_set(new, old)
        return json.dumps(got, ensure_ascii=False, indent=2)
    except Exception:
        return new_txt


# ---------------------------------------------------------------------------
# 번들
# ---------------------------------------------------------------------------
def build_bundle() -> dict:
    """올릴 번들. **없는 파일은 키 자체를 넣지 않는다.**

    예전엔 없는 파일을 "" 로 채워 올렸다. 받는 쪽은 그 "" 를 파일에 그대로 써서
    멀쩡한 데이터를 0바이트로 만들었고, 읽기가 예외를 삼켜 조용히 사라졌다.

    `times` 는 파일별 시각표다. 옛 버전은 이 키를 몰라 그냥 지나가므로
    번들을 같이 써도 안전하다.
    """
    files, times = {}, {}
    for n in _FILES:
        txt = _read(n)
        if txt.strip():
            files[n] = txt
            times[n] = file_stamp(n)
    return {"updatedAt": _now(), "files": files, "times": times}


def _remote_bundle(auth):
    fid = google_client.drive_find(auth, SYNC_FILE)
    if not fid:
        return None
    try:
        b = json.loads(google_client.drive_read(auth, fid))
    except Exception:
        return None
    return b if isinstance(b, dict) else None


def _remote_time(b: dict, name: str) -> str:
    """번들 안 파일의 시각. 시각표가 없는 옛 번들은 묶음 시각을 쓴다."""
    times = b.get("times") or {}
    return str(times.get(name) or b.get("updatedAt") or "")


def apply_remote(b: dict) -> bool:
    """원격 번들을 로컬에 반영. 바뀌면 True.

    파일이 더 최신인 쪽을 고르되, **목록 파일은 내 것이 더 최신이어도 합친다.**
    안 그러면 저쪽에서 추가한 채널을 이쪽은 영영 못 본다(내 파일이 더 최신이라는
    이유로 통째로 건너뛰게 된다).
    """
    changed = False
    for n, content in (b.get("files") or {}).items():
        if n not in _FILES or not str(content or "").strip():
            continue          # 빈 내용으로 멀쩡한 로컬 파일을 지우지 않는다
        rt = _remote_time(b, n)
        lt = file_stamp(n)
        cur = _read(n)
        if not lt:                       # 이 PC 엔 없는 파일
            text, stamp = content, rt
        elif rt > lt:                    # 원격이 더 최신 → 원격을 앞에 두고 합친다
            text, stamp = merge_text(n, content, cur), rt
        elif _MERGE.get(n):              # 내가 더 최신 → 내 것을 앞에 두고 합친다
            text, stamp = merge_text(n, cur, content), lt
        else:
            continue                     # 목록이 아니고 내 것이 최신 → 그대로
        if text != cur:
            _write(n, text, stamp)
            changed = True
    return changed


def merged_bundle(b) -> dict:
    """올릴 번들 — 원격에만 더 최신인 파일이 있으면 그쪽을 살려서 담는다."""
    out = build_bundle()
    if not b:
        return out
    for n, content in (b.get("files") or {}).items():
        if n not in _FILES or not str(content or "").strip():
            continue
        rt = _remote_time(b, n)
        lt = out["times"].get(n, "")
        if not lt:                       # 이 PC 엔 없는 파일 → 원격 것을 그대로
            out["files"][n] = content
            out["times"][n] = rt
        elif rt > lt:                    # 원격이 더 최신 → 합쳐서 올린다
            out["files"][n] = merge_text(n, content, out["files"].get(n, ""))
            out["times"][n] = rt
        elif _MERGE.get(n):              # 내가 더 최신이라도 목록은 합쳐 둔다
            out["files"][n] = merge_text(n, out["files"].get(n, ""), content)
    return out


# ---------------------------------------------------------------------------
# 주고받기
# ---------------------------------------------------------------------------
def pull(auth) -> bool:
    """원격에서 더 최신인 파일을 내려받는다. 바뀌면 True."""
    b = _remote_bundle(auth)
    if not b:
        return False
    changed = apply_remote(b)
    if changed:
        _set_local_updated(_now())
    return changed


def push(auth) -> None:
    """로컬을 올린다. **먼저 원격을 읽어 합친다** — 남의 최신 파일을 지우지 않게."""
    b = _remote_bundle(auth)
    out = merged_bundle(b)
    google_client.drive_write(auth, SYNC_FILE, json.dumps(out, ensure_ascii=False))
    _set_local_updated(out["updatedAt"])


def sync_now(auth) -> bool:
    """받고 → 합쳐서 올린다. 로컬이 바뀌었으면 True.

    [지금 동기화] 버튼과 주기 동기화가 쓴다.
    """
    b = _remote_bundle(auth)
    changed = apply_remote(b) if b else False
    out = merged_bundle(b)
    google_client.drive_write(auth, SYNC_FILE, json.dumps(out, ensure_ascii=False))
    _set_local_updated(out["updatedAt"])
    return changed
